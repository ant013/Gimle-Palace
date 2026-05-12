"""Phase 2.1.1: failing unit tests for ADR schema + Pydantic models."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest


class TestAdrDocumentModel:
    def test_round_trip(self) -> None:
        from palace_mcp.adr.models import AdrDocument

        now = datetime(2026, 5, 12, 0, 0, 0, tzinfo=timezone.utc)
        doc = AdrDocument(
            slug="gimle-purpose",
            title="Gimle Purpose",
            created_at=now,
            updated_at=now,
            source_path="docs/postulates/gimle-purpose.md",
        )
        dumped = doc.model_dump()
        restored = AdrDocument.model_validate(dumped)
        assert restored.slug == "gimle-purpose"
        assert restored.status == "active"
        assert restored.head_sha == "unknown"

    def test_slug_and_status_fields(self) -> None:
        from palace_mcp.adr.models import AdrDocument

        now = datetime.now(tz=timezone.utc)
        doc = AdrDocument(
            slug="test-adr",
            title="Test",
            status="superseded",
            created_at=now,
            updated_at=now,
            source_path="docs/postulates/test-adr.md",
        )
        assert doc.status == "superseded"


class TestAdrSectionModel:
    def test_body_hash_derives_from_sha256(self) -> None:
        from palace_mcp.adr.models import AdrSection

        body = "This is the purpose of the project."
        expected_hash = hashlib.sha256(body.encode()).hexdigest()
        section = AdrSection(
            section_name="PURPOSE",
            body=body,
            last_edit=datetime.now(tz=timezone.utc),
        )
        assert section.body_hash == expected_hash

    def test_body_excerpt_truncated_at_500(self) -> None:
        from palace_mcp.adr.models import AdrSection

        body = "x" * 600
        section = AdrSection(
            section_name="STACK",
            body=body,
            last_edit=datetime.now(tz=timezone.utc),
        )
        assert section.body_excerpt == "x" * 500

    def test_body_excerpt_short_body_unchanged(self) -> None:
        from palace_mcp.adr.models import AdrSection

        body = "short"
        section = AdrSection(
            section_name="ARCHITECTURE",
            body=body,
            last_edit=datetime.now(tz=timezone.utc),
        )
        assert section.body_excerpt == "short"

    def test_body_hash_for_helper(self) -> None:
        from palace_mcp.adr.models import body_hash_for

        body = "hello world"
        assert body_hash_for(body) == hashlib.sha256(body.encode()).hexdigest()


class TestValidateSlug:
    def test_valid_slug(self) -> None:
        from palace_mcp.adr.models import validate_slug

        assert validate_slug("gimle-purpose") == "gimle-purpose"
        assert validate_slug("test") == "test"
        assert validate_slug("abc123") == "abc123"

    def test_invalid_slug_starts_with_digit(self) -> None:
        from palace_mcp.adr.models import validate_slug

        with pytest.raises(ValueError, match="Invalid ADR slug"):
            validate_slug("1bad")

    def test_invalid_slug_has_uppercase(self) -> None:
        from palace_mcp.adr.models import validate_slug

        with pytest.raises(ValueError, match="Invalid ADR slug"):
            validate_slug("Bad-slug")


class TestEnsureAdrSchema:
    @pytest.mark.asyncio
    async def test_sends_constraints_and_indexes(self) -> None:
        from palace_mcp.adr.schema import ensure_adr_schema

        mock_session = AsyncMock()
        mock_driver = MagicMock()
        mock_driver.session.return_value.__aenter__ = AsyncMock(
            return_value=mock_session
        )
        mock_driver.session.return_value.__aexit__ = AsyncMock(return_value=False)

        await ensure_adr_schema(mock_driver)

        calls = [call.args[0] for call in mock_session.run.call_args_list]
        assert any("AdrDocument" in c and "UNIQUE" in c for c in calls), (
            "Expected UNIQUE constraint for AdrDocument"
        )
        assert any(
            "INDEX" in c and "AdrDocument" in c and "status" in c for c in calls
        ), "Expected INDEX on AdrDocument.status"
        assert any(
            "INDEX" in c and "AdrSection" in c and "section_name" in c for c in calls
        ), "Expected INDEX on AdrSection.section_name"

    @pytest.mark.asyncio
    async def test_idempotent_uses_if_not_exists(self) -> None:
        from palace_mcp.adr.schema import _CONSTRAINTS, _INDEXES

        for stmt in [*_CONSTRAINTS, *_INDEXES]:
            assert "IF NOT EXISTS" in stmt, (
                f"Schema statement must be idempotent (IF NOT EXISTS): {stmt!r}"
            )
