"""Phase 2.3.1: unit tests for ADR writer (idempotent section upsert)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest


def _make_mock_driver() -> tuple[MagicMock, AsyncMock]:
    mock_session = AsyncMock()
    mock_session.run = AsyncMock()
    mock_driver = MagicMock()
    mock_driver.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_driver.session.return_value.__aexit__ = AsyncMock(return_value=False)
    return mock_driver, mock_session


class TestWriteAdr:
    @pytest.mark.asyncio
    async def test_write_creates_file_with_all_sections(self, tmp_path: Path) -> None:
        from palace_mcp.adr.writer import write_adr

        driver, _ = _make_mock_driver()
        result = await write_adr(
            slug="test-adr",
            section="PURPOSE",
            body="This is the purpose.",
            decision_id=None,
            base_dir=tmp_path,
            driver=driver,
        )

        assert result["ok"] is True
        path = tmp_path / "test-adr.md"
        assert path.exists()
        content = path.read_text()
        # All 6 section headers present
        for section in ("PURPOSE", "STACK", "ARCHITECTURE", "PATTERNS", "TRADEOFFS", "PHILOSOPHY"):
            assert f"## {section}" in content
        assert "This is the purpose." in content

    @pytest.mark.asyncio
    async def test_write_is_idempotent_same_body(self, tmp_path: Path) -> None:
        from palace_mcp.adr.models import body_hash_for
        from palace_mcp.adr.writer import write_adr

        driver, _ = _make_mock_driver()
        kwargs = dict(
            slug="test-adr",
            section="PURPOSE",
            body="Idempotent content.",
            decision_id=None,
            base_dir=tmp_path,
            driver=driver,
        )
        result1 = await write_adr(**kwargs)
        mtime1 = (tmp_path / "test-adr.md").stat().st_mtime_ns
        result2 = await write_adr(**kwargs)
        mtime2 = (tmp_path / "test-adr.md").stat().st_mtime_ns

        assert result1["ok"] is True
        assert result2["ok"] is True
        # body_hash identical on both calls
        assert result1["body_hash"] == result2["body_hash"]
        assert result1["body_hash"] == body_hash_for("Idempotent content.")
        # file not modified on second call (no mtime change)
        assert mtime1 == mtime2

    @pytest.mark.asyncio
    async def test_write_updates_section_body(self, tmp_path: Path) -> None:
        from palace_mcp.adr.models import body_hash_for
        from palace_mcp.adr.writer import write_adr

        driver, _ = _make_mock_driver()
        base = dict(slug="test-adr", decision_id=None, base_dir=tmp_path, driver=driver)
        await write_adr(section="PURPOSE", body="v1 content", **base)
        result = await write_adr(section="PURPOSE", body="v2 content", **base)

        assert result["ok"] is True
        assert result["body_hash"] == body_hash_for("v2 content")
        content = (tmp_path / "test-adr.md").read_text()
        assert "v2 content" in content
        assert "v1 content" not in content

    @pytest.mark.asyncio
    async def test_write_triggers_graph_upsert(self, tmp_path: Path) -> None:
        from palace_mcp.adr.writer import write_adr

        driver, session = _make_mock_driver()
        await write_adr(
            slug="test-adr",
            section="PURPOSE",
            body="content",
            decision_id=None,
            base_dir=tmp_path,
            driver=driver,
        )

        assert session.run.call_count > 0, "Expected Cypher calls for graph upsert"

    @pytest.mark.asyncio
    async def test_write_invalid_section_returns_error(self, tmp_path: Path) -> None:
        from palace_mcp.adr.writer import write_adr

        driver, _ = _make_mock_driver()
        result = await write_adr(
            slug="test-adr",
            section="INVALID_SECTION",  # type: ignore[arg-type]
            body="content",
            decision_id=None,
            base_dir=tmp_path,
            driver=driver,
        )

        assert result["ok"] is False
        assert result["error_code"] == "invalid_section"

    @pytest.mark.asyncio
    async def test_write_invalid_slug_returns_error(self, tmp_path: Path) -> None:
        from palace_mcp.adr.writer import write_adr

        driver, _ = _make_mock_driver()
        result = await write_adr(
            slug="INVALID!",
            section="PURPOSE",
            body="content",
            decision_id=None,
            base_dir=tmp_path,
            driver=driver,
        )

        assert result["ok"] is False
        assert result["error_code"] == "invalid_slug"

    @pytest.mark.asyncio
    async def test_write_existing_file_updates_only_target_section(
        self, tmp_path: Path
    ) -> None:
        from palace_mcp.adr.writer import write_adr

        driver, _ = _make_mock_driver()
        base = dict(slug="test-adr", decision_id=None, base_dir=tmp_path, driver=driver)
        await write_adr(section="PURPOSE", body="purpose content", **base)
        await write_adr(section="STACK", body="stack content", **base)

        content = (tmp_path / "test-adr.md").read_text()
        assert "purpose content" in content
        assert "stack content" in content
