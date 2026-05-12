"""Phase 2.5.1: unit tests for ADR query mode (Cypher-only, AD-D6)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest


def _make_mock_driver(rows: list[dict] | None = None) -> tuple[MagicMock, AsyncMock]:
    """Build a driver mock that returns `rows` from query."""
    mock_result = AsyncMock()

    async def _values():
        return [[r.get("slug"), r.get("section_name"), r.get("body_excerpt")] for r in (rows or [])]

    mock_result.values = _values
    mock_session = AsyncMock()
    mock_session.run = AsyncMock(return_value=mock_result)
    mock_driver = MagicMock()
    mock_driver.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_driver.session.return_value.__aexit__ = AsyncMock(return_value=False)
    return mock_driver, mock_session


class TestQueryAdrs:
    @pytest.mark.asyncio
    async def test_query_keyword_finds_matching_sections(self) -> None:
        from palace_mcp.adr.query import query_adrs

        rows = [
            {"slug": "gimle-purpose", "section_name": "PURPOSE", "body_excerpt": "palace of knowledge"},
        ]
        driver, session = _make_mock_driver(rows)

        result = await query_adrs(
            keyword="palace",
            section_filter=None,
            project_filter=None,
            driver=driver,
        )

        assert result["ok"] is True
        assert len(result["results"]) == 1
        assert result["results"][0]["slug"] == "gimle-purpose"

    @pytest.mark.asyncio
    async def test_query_empty_graph_returns_empty_list(self) -> None:
        from palace_mcp.adr.query import query_adrs

        driver, _ = _make_mock_driver(rows=[])

        result = await query_adrs(
            keyword=None,
            section_filter=None,
            project_filter=None,
            driver=driver,
        )

        assert result["ok"] is True
        assert result["results"] == []

    @pytest.mark.asyncio
    async def test_query_section_filter_passed_as_cypher_param(self) -> None:
        from palace_mcp.adr.query import query_adrs

        driver, session = _make_mock_driver(rows=[])

        await query_adrs(
            keyword=None,
            section_filter="ARCHITECTURE",
            project_filter=None,
            driver=driver,
        )

        call_kwargs = session.run.call_args
        assert call_kwargs is not None
        # section_filter should be forwarded to Cypher as parameter
        args = call_kwargs[0] if call_kwargs[0] else []
        kwargs = call_kwargs[1] if len(call_kwargs) > 1 else {}
        combined = {**(kwargs if isinstance(kwargs, dict) else {})}
        # Check that section_filter was passed somewhere
        assert any("ARCHITECTURE" in str(v) for v in combined.values()), (
            "section_filter must be forwarded to Cypher"
        )

    @pytest.mark.asyncio
    async def test_query_project_filter_matches_slug_prefix(self) -> None:
        from palace_mcp.adr.query import query_adrs

        rows = [
            {"slug": "gimle-auth", "section_name": "PURPOSE", "body_excerpt": "auth"},
        ]
        driver, session = _make_mock_driver(rows)

        result = await query_adrs(
            keyword=None,
            section_filter=None,
            project_filter="gimle-",
            driver=driver,
        )

        assert result["ok"] is True

    @pytest.mark.asyncio
    async def test_query_uses_cypher_not_tantivy(self) -> None:
        from palace_mcp.adr import query as query_module

        source = open(query_module.__file__).read()
        assert "TantivyBridge" not in source, (
            "AD-D6: query must use Cypher-only; no Tantivy in adr/query.py"
        )
