"""Phase 2.4.1: unit tests for ADR supersede mode."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest


_SAMPLE_OLD = """\
# Old ADR

## PURPOSE
Old purpose.

## STACK
## ARCHITECTURE
## PATTERNS
## TRADEOFFS
## PHILOSOPHY
"""

_SAMPLE_NEW = """\
# New ADR

## PURPOSE
New purpose.

## STACK
## ARCHITECTURE
## PATTERNS
## TRADEOFFS
## PHILOSOPHY
"""


def _make_mock_driver_with_query(
    records: list | None = None,
) -> tuple[MagicMock, AsyncMock]:
    """Driver mock that returns pre-set records from session.run().single()."""
    mock_result = AsyncMock()
    mock_result.single = AsyncMock(return_value=None if not records else records[0])
    mock_session = AsyncMock()
    mock_session.run = AsyncMock(return_value=mock_result)
    mock_driver = MagicMock()
    mock_driver.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_driver.session.return_value.__aexit__ = AsyncMock(return_value=False)
    return mock_driver, mock_session


class TestSupersede:
    @pytest.mark.asyncio
    async def test_supersede_updates_old_status_in_graph(self, tmp_path: Path) -> None:
        from palace_mcp.adr.supersede import supersede_adr

        (tmp_path / "old-adr.md").write_text(_SAMPLE_OLD)
        (tmp_path / "new-adr.md").write_text(_SAMPLE_NEW)
        driver, session = _make_mock_driver_with_query()

        result = await supersede_adr(
            old_slug="old-adr",
            new_slug="new-adr",
            reason="Better approach found.",
            base_dir=tmp_path,
            driver=driver,
        )

        assert result["ok"] is True
        # Graph writes must have occurred
        assert session.run.call_count > 0

    @pytest.mark.asyncio
    async def test_supersede_adds_banner_to_old_file(self, tmp_path: Path) -> None:
        from palace_mcp.adr.supersede import supersede_adr

        (tmp_path / "old-adr.md").write_text(_SAMPLE_OLD)
        (tmp_path / "new-adr.md").write_text(_SAMPLE_NEW)
        driver, _ = _make_mock_driver_with_query()

        await supersede_adr(
            old_slug="old-adr",
            new_slug="new-adr",
            reason="Better approach.",
            base_dir=tmp_path,
            driver=driver,
        )

        old_content = (tmp_path / "old-adr.md").read_text()
        assert "SUPERSEDED" in old_content
        assert "new-adr" in old_content
        assert "Better approach." in old_content

    @pytest.mark.asyncio
    async def test_supersede_idempotent(self, tmp_path: Path) -> None:
        from palace_mcp.adr.supersede import supersede_adr

        (tmp_path / "old-adr.md").write_text(_SAMPLE_OLD)
        (tmp_path / "new-adr.md").write_text(_SAMPLE_NEW)
        driver, _ = _make_mock_driver_with_query()

        args = dict(
            old_slug="old-adr",
            new_slug="new-adr",
            reason="Reason.",
            base_dir=tmp_path,
            driver=driver,
        )
        result1 = await supersede_adr(**args)
        result2 = await supersede_adr(**args)

        assert result1["ok"] is True
        assert result2["ok"] is True
        # Banner should not be duplicated
        old_content = (tmp_path / "old-adr.md").read_text()
        assert old_content.count("SUPERSEDED") == 1

    @pytest.mark.asyncio
    async def test_supersede_missing_old_slug_returns_error(
        self, tmp_path: Path
    ) -> None:
        from palace_mcp.adr.supersede import supersede_adr

        (tmp_path / "new-adr.md").write_text(_SAMPLE_NEW)
        driver, _ = _make_mock_driver_with_query()

        result = await supersede_adr(
            old_slug="nonexistent",
            new_slug="new-adr",
            reason="Reason.",
            base_dir=tmp_path,
            driver=driver,
        )

        assert result["ok"] is False
        assert result["error_code"] == "adr_not_found"
