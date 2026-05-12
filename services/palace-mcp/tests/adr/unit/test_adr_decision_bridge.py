"""Phase 2.6.1: unit tests for ADR decision bridge (CITED_BY edge)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

_DECISION_UUID = "d9f7a3b2-1234-5678-abcd-ef0123456789"


def _make_session_returning(single_value: object) -> tuple[MagicMock, AsyncMock]:
    """Driver mock where session.run().single() returns `single_value`."""
    mock_result = AsyncMock()
    mock_result.single = AsyncMock(return_value=single_value)
    mock_session = AsyncMock()
    mock_session.run = AsyncMock(return_value=mock_result)
    mock_driver = MagicMock()
    mock_driver.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_driver.session.return_value.__aexit__ = AsyncMock(return_value=False)
    return mock_driver, mock_session


class TestDecisionBridge:
    @pytest.mark.asyncio
    async def test_creates_cited_by_edge_when_decision_exists(self) -> None:
        from palace_mcp.adr.decision_bridge import create_cited_by_edge

        # session.run().single() returns a record (decision found)
        driver, session = _make_session_returning({"uuid": _DECISION_UUID})

        result = await create_cited_by_edge(
            decision_id=_DECISION_UUID,
            slug="test-adr",
            driver=driver,
        )

        assert result["ok"] is True
        # At least 2 Cypher calls: CHECK + CREATE_EDGE
        assert session.run.call_count >= 2

    @pytest.mark.asyncio
    async def test_returns_error_when_decision_not_found(self) -> None:
        from palace_mcp.adr.decision_bridge import create_cited_by_edge

        # session.run().single() returns None (decision not found)
        driver, session = _make_session_returning(None)

        result = await create_cited_by_edge(
            decision_id="nonexistent-id",
            slug="test-adr",
            driver=driver,
        )

        assert result["ok"] is False
        assert result["error_code"] == "decision_not_found"
        # Only 1 call: CHECK (no CREATE_EDGE without valid Decision)
        assert session.run.call_count == 1

    @pytest.mark.asyncio
    async def test_write_without_decision_id_no_edge(self, tmp_path: Path) -> None:
        """write() without decision_id must NOT create any CITED_BY edge."""
        from palace_mcp.adr.writer import write_adr

        mock_result = AsyncMock()
        mock_result.single = AsyncMock(return_value=None)
        mock_session = AsyncMock()
        mock_session.run = AsyncMock(return_value=mock_result)
        mock_driver = MagicMock()
        mock_driver.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_driver.session.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await write_adr(
            slug="test-adr",
            section="PURPOSE",
            body="content",
            decision_id=None,
            base_dir=tmp_path,
            driver=mock_driver,
        )

        assert result["ok"] is True
        # No CITED_BY Cypher call — only UPSERT_DOC + UPSERT_SECTION
        calls = [str(c.args[0]) for c in mock_session.run.call_args_list]
        assert not any("CITED_BY" in c for c in calls), (
            "No CITED_BY Cypher must be issued when decision_id is None"
        )

    @pytest.mark.asyncio
    async def test_write_with_nonexistent_decision_id_returns_error(
        self, tmp_path: Path
    ) -> None:
        """write() with nonexistent decision_id must return error_code=decision_not_found."""
        from palace_mcp.adr.writer import write_adr

        mock_result = AsyncMock()
        mock_result.single = AsyncMock(return_value=None)  # decision not found
        mock_session = AsyncMock()
        mock_session.run = AsyncMock(return_value=mock_result)
        mock_driver = MagicMock()
        mock_driver.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_driver.session.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await write_adr(
            slug="test-adr",
            section="PURPOSE",
            body="content",
            decision_id="nonexistent-uuid",
            base_dir=tmp_path,
            driver=mock_driver,
        )

        assert result["ok"] is False
        assert result["error_code"] == "decision_not_found"
