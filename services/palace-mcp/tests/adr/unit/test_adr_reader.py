"""Phase 2.2.1: unit tests for ADR reader (file-to-graph projection)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest


_SAMPLE_ADR = """\
# Gimle Purpose

## PURPOSE
This project exists to build a palace of knowledge.

## STACK
Python 3.13, Neo4j, FastAPI.

## ARCHITECTURE
Single-service FastAPI with MCP protocol.

## PATTERNS
TDD, atomic commits, code-router pattern.

## TRADEOFFS
Speed vs correctness — correctness wins.

## PHILOSOPHY
Every decision is an ADR.
"""


def _make_mock_driver() -> tuple[MagicMock, AsyncMock]:
    mock_session = AsyncMock()
    mock_session.run = AsyncMock()
    mock_driver = MagicMock()
    mock_driver.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_driver.session.return_value.__aexit__ = AsyncMock(return_value=False)
    return mock_driver, mock_session


class TestReadAdr:
    @pytest.mark.asyncio
    async def test_read_returns_body_and_sections(self, tmp_path: Path) -> None:
        from palace_mcp.adr.reader import read_adr

        (tmp_path / "gimle-purpose.md").write_text(_SAMPLE_ADR)
        driver, _ = _make_mock_driver()

        result = await read_adr(slug="gimle-purpose", base_dir=tmp_path, driver=driver)

        assert result["ok"] is True
        assert result["slug"] == "gimle-purpose"
        assert result["title"] == "Gimle Purpose"
        assert result["body"] == _SAMPLE_ADR
        assert "PURPOSE" in result["sections"]
        assert "STACK" in result["sections"]
        assert "ARCHITECTURE" in result["sections"]
        assert "PATTERNS" in result["sections"]
        assert "TRADEOFFS" in result["sections"]
        assert "PHILOSOPHY" in result["sections"]

    @pytest.mark.asyncio
    async def test_read_nonexistent_returns_error(self, tmp_path: Path) -> None:
        from palace_mcp.adr.reader import read_adr

        driver, _ = _make_mock_driver()

        result = await read_adr(slug="nonexistent", base_dir=tmp_path, driver=driver)

        assert result["ok"] is False
        assert result["error_code"] == "adr_not_found"

    @pytest.mark.asyncio
    async def test_read_triggers_graph_projection(self, tmp_path: Path) -> None:
        from palace_mcp.adr.reader import read_adr

        (tmp_path / "test-adr.md").write_text(_SAMPLE_ADR)
        driver, session = _make_mock_driver()

        await read_adr(slug="test-adr", base_dir=tmp_path, driver=driver)

        assert session.run.call_count > 0, "Expected graph projection Cypher calls"

    @pytest.mark.asyncio
    async def test_read_projection_idempotent_on_second_call(
        self, tmp_path: Path
    ) -> None:
        from palace_mcp.adr.reader import read_adr

        (tmp_path / "test-adr.md").write_text(_SAMPLE_ADR)
        driver, session = _make_mock_driver()

        result1 = await read_adr(slug="test-adr", base_dir=tmp_path, driver=driver)
        result2 = await read_adr(slug="test-adr", base_dir=tmp_path, driver=driver)

        assert result1["ok"] is True
        assert result2["ok"] is True

    @pytest.mark.asyncio
    async def test_read_invalid_slug_returns_error(self, tmp_path: Path) -> None:
        from palace_mcp.adr.reader import read_adr

        driver, _ = _make_mock_driver()
        result = await read_adr(slug="INVALID_SLUG!", base_dir=tmp_path, driver=driver)

        assert result["ok"] is False
        assert result["error_code"] == "invalid_slug"

    @pytest.mark.asyncio
    async def test_read_without_driver_skips_projection(self, tmp_path: Path) -> None:
        from palace_mcp.adr.reader import read_adr

        (tmp_path / "test-adr.md").write_text(_SAMPLE_ADR)

        result = await read_adr(slug="test-adr", base_dir=tmp_path, driver=None)

        assert result["ok"] is True
        assert result["title"] == "Gimle Purpose"


class TestParseAdrFile:
    def test_parse_extracts_title_and_sections(self) -> None:
        from palace_mcp.adr.reader import _parse_adr_file

        title, sections = _parse_adr_file(_SAMPLE_ADR)
        assert title == "Gimle Purpose"
        section_names = [s["name"] for s in sections]
        assert section_names == [
            "PURPOSE",
            "STACK",
            "ARCHITECTURE",
            "PATTERNS",
            "TRADEOFFS",
            "PHILOSOPHY",
        ]

    def test_parse_section_body_stripped(self) -> None:
        from palace_mcp.adr.reader import _parse_adr_file

        _, sections = _parse_adr_file(_SAMPLE_ADR)
        purpose = next(s for s in sections if s["name"] == "PURPOSE")
        assert purpose["body"] == "This project exists to build a palace of knowledge."

    def test_parse_empty_file_returns_empty(self) -> None:
        from palace_mcp.adr.reader import _parse_adr_file

        title, sections = _parse_adr_file("")
        assert title == ""
        assert sections == []

    def test_parse_ignores_unknown_sections(self) -> None:
        from palace_mcp.adr.reader import _parse_adr_file

        content = "# Title\n\n## UNKNOWN\nsome content\n\n## PURPOSE\nreal content\n"
        _, sections = _parse_adr_file(content)
        section_names = [s["name"] for s in sections]
        assert "UNKNOWN" not in section_names
        assert "PURPOSE" in section_names
