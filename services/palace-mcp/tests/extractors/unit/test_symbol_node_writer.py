"""Unit tests for symbol_node_writer (mocked Neo4j driver)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from palace_mcp.extractors.foundation.symbol_node_writer import (
    _BUMP_UNCHANGED_SYMBOL_LIVENESS,
    _DELETE_STALE_RELATIONSHIPS,
    _MERGE_CONFORMS_TO,
    _MERGE_EXTENDS,
    _MERGE_EXTENSION_OF,
    _MERGE_REFERENCES,
    _MERGE_SYMBOLS,
    _SOFT_DELETE_ABSENT,
    _SOFT_DELETE_FILE_SCOPED,
    build_symbol_shadow_rows,
    build_symbol_node_rows,
    soft_delete_symbols,
    soft_delete_symbols_for_paths,
)


class TestMergeQueryClearsDeletedAt:
    def test_merge_symbols_sets_deleted_at_null(self) -> None:
        """Re-ingesting a symbol via MERGE must clear deleted_at."""
        assert "deleted_at" in _MERGE_SYMBOLS
        assert "null" in _MERGE_SYMBOLS

    def test_merge_symbols_sets_last_seen_and_clears_deprecation(self) -> None:
        assert "last_seen_in_run_id" in _MERGE_SYMBOLS
        assert "last_seen_at" in _MERGE_SYMBOLS
        assert "last_seen_in_commit" in _MERGE_SYMBOLS
        assert "REMOVE s:Deprecated" in _MERGE_SYMBOLS
        assert "REMOVE s.deprecated_at, s.deprecated_in_commit" in _MERGE_SYMBOLS

    def test_merge_symbols_replaces_last_seen_in_edge(self) -> None:
        assert "OPTIONAL MATCH (s)-[old:LAST_SEEN_IN]->()" in _MERGE_SYMBOLS
        assert "DELETE old" in _MERGE_SYMBOLS
        assert "MERGE (s)-[:LAST_SEEN_IN]->(run)" in _MERGE_SYMBOLS

    def test_merge_symbols_sets_line_range(self) -> None:
        # dogfood W8c: get_code_snippet windows on s.line_start/s.line_end and
        # otherwise falls back to the file head.
        assert "s.line_start" in _MERGE_SYMBOLS
        assert "s.line_end" in _MERGE_SYMBOLS

    def test_merge_symbols_uses_row_access_modifier(self) -> None:
        assert "s.access_modifier        = r.access_modifier" in _MERGE_SYMBOLS

    def test_soft_delete_query_uses_group_id_and_qnames(self) -> None:
        assert "$group_id" in _SOFT_DELETE_ABSENT
        assert "$qnames" in _SOFT_DELETE_ABSENT
        assert "$now" in _SOFT_DELETE_ABSENT
        assert "NOT" in _SOFT_DELETE_ABSENT

    def test_soft_delete_file_scoped_query_uses_paths_and_qnames(self) -> None:
        assert "$group_id" in _SOFT_DELETE_FILE_SCOPED
        assert "$file_paths" in _SOFT_DELETE_FILE_SCOPED
        assert "$qnames" in _SOFT_DELETE_FILE_SCOPED
        assert "s.file_path IN $file_paths" in _SOFT_DELETE_FILE_SCOPED

    def test_bump_unchanged_symbol_liveness_is_group_scoped_and_batched(self) -> None:
        assert "group_id" in _BUMP_UNCHANGED_SYMBOL_LIVENESS
        assert "deleted_at IS NULL" in _BUMP_UNCHANGED_SYMBOL_LIVENESS
        assert "NOT s:Deprecated" in _BUMP_UNCHANGED_SYMBOL_LIVENESS
        assert "written_changed_qnames" in _BUMP_UNCHANGED_SYMBOL_LIVENESS
        assert "IN TRANSACTIONS OF 10000 ROWS" in _BUMP_UNCHANGED_SYMBOL_LIVENESS

    def test_relationship_queries_stamp_last_seen_in_run_id(self) -> None:
        queries = (
            _MERGE_REFERENCES,
            _MERGE_CONFORMS_TO,
            _MERGE_EXTENDS,
            _MERGE_EXTENSION_OF,
        )
        for query in queries:
            assert "last_seen_in_run_id" in query

    def test_backed_by_symbol_shadow_lookup_uses_symbol_id(self) -> None:
        from palace_mcp.extractors.foundation.symbol_node_writer import (
            _MERGE_BACKED_BY_SYMBOL_SHADOWS,
        )

        assert "symbol_id: r.symbol_id" in _MERGE_BACKED_BY_SYMBOL_SHADOWS

    def test_delete_stale_relationships_query_targets_expected_scope(self) -> None:
        assert (
            "REFERENCES|CONFORMS_TO|EXTENDS|EXTENSION_OF" in _DELETE_STALE_RELATIONSHIPS
        )
        assert "a.file_path IN $changed_file_paths" in _DELETE_STALE_RELATIONSHIPS
        assert "b.deleted_at IS NOT NULL" in _DELETE_STALE_RELATIONSHIPS
        assert "b:Deprecated" in _DELETE_STALE_RELATIONSHIPS


class TestBuildSymbolNodeRows:
    def test_rows_include_required_fields(self) -> None:
        from palace_mcp.extractors.scip_parser import ScipSymbolInfo

        si = ScipSymbolInfo(
            qualified_name="App.Foo",
            scip_kind_name="Class",
            module_name="App",
            relationships=(),
        )
        rows = build_symbol_node_rows([si], {}, "project/test")
        assert len(rows) == 1
        row = rows[0]
        assert row["qualified_name"] == "App.Foo"
        assert row["group_id"] == "project/test"
        assert row["kind"] == "class"
        assert row["label"] == "Class"
        assert row["short_name"] == "Foo"
        assert row["file_path"] is None
        assert row["access_modifier"] == ""
        # No def_line_starts → line_start/line_end null (snippet falls back).
        assert row["line_start"] is None
        assert row["line_end"] is None

    def test_rows_preserve_access_modifier(self) -> None:
        from palace_mcp.extractors.scip_parser import ScipSymbolInfo

        si = ScipSymbolInfo(
            qualified_name="App.Foo",
            scip_kind_name="Class",
            module_name="App",
            relationships=(),
            access_modifier="public",
        )
        rows = build_symbol_node_rows([si], {}, "project/test")
        assert rows[0]["access_modifier"] == "public"

    def test_line_start_from_def_line_starts(self) -> None:
        # dogfood W8c: declaration line threaded onto the row so get_code_snippet
        # windows on the symbol instead of returning the file head.
        from palace_mcp.extractors.scip_parser import ScipSymbolInfo

        si = ScipSymbolInfo(
            qualified_name="App.Foo",
            scip_kind_name="Class",
            module_name="App",
            relationships=(),
        )
        rows = build_symbol_node_rows(
            [si], {}, "project/test", def_line_starts={"App.Foo": 42}
        )
        assert rows[0]["line_start"] == 42
        assert rows[0]["line_end"] is None


class TestBuildSymbolShadowRows:
    def test_rows_include_symbol_id_for_composite_shadow_lookup(self) -> None:
        from palace_mcp.extractors.scip_parser import ScipSymbolInfo

        si = ScipSymbolInfo(
            qualified_name="App.Foo",
            scip_kind_name="Class",
            module_name="App",
            relationships=(),
        )
        rows = build_symbol_shadow_rows([si], "project/test", {"App.Foo": 123456789})
        assert rows == [
            {
                "qualified_name": "App.Foo",
                "group_id": "project/test",
                "symbol_id": 123456789,
            }
        ]

    def test_rows_skip_shadow_backing_when_symbol_id_missing(self) -> None:
        from palace_mcp.extractors.scip_parser import ScipSymbolInfo

        si = ScipSymbolInfo(
            qualified_name="App.Foo",
            scip_kind_name="Class",
            module_name="App",
            relationships=(),
        )
        assert build_symbol_shadow_rows([si], "project/test", {}) == []


class TestSoftDeleteSymbols:
    def _make_driver(self, *, properties_set: int = 3) -> MagicMock:
        summary = MagicMock()
        summary.counters.properties_set = properties_set
        result = AsyncMock()
        result.consume = AsyncMock(return_value=summary)
        session = AsyncMock()
        session.run = AsyncMock(return_value=result)
        session_cm = MagicMock()
        session_cm.__aenter__ = AsyncMock(return_value=session)
        session_cm.__aexit__ = AsyncMock(return_value=False)
        driver = MagicMock()
        driver.session.return_value = session_cm
        return driver

    @pytest.mark.asyncio
    async def test_returns_properties_set_count(self) -> None:
        driver = self._make_driver(properties_set=2)
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        count = await soft_delete_symbols(driver, "project/x", {"A.Foo", "A.Bar"}, now)
        assert count == 2

    @pytest.mark.asyncio
    async def test_passes_qnames_list_and_group_id_to_driver(self) -> None:
        driver = self._make_driver(properties_set=0)
        seen = {"App.Alpha", "App.Beta"}
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        await soft_delete_symbols(driver, "project/y", seen, now)

        session = driver.session.return_value.__aenter__.return_value
        kwargs = session.run.call_args.kwargs
        assert kwargs["group_id"] == "project/y"
        assert set(kwargs["qnames"]) == seen
        assert kwargs["now"] == now

    @pytest.mark.asyncio
    async def test_idempotent_when_all_qnames_present(self) -> None:
        """When seen_qnames covers everything, no nodes should be deleted (0 returned)."""
        driver = self._make_driver(properties_set=0)
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        count = await soft_delete_symbols(driver, "project/z", {"Sym.A"}, now)
        assert count == 0

    @pytest.mark.asyncio
    async def test_soft_delete_symbols_for_paths_passes_file_scope(self) -> None:
        driver = self._make_driver(properties_set=1)
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)

        count = await soft_delete_symbols_for_paths(
            driver,
            "project/files",
            {"Sources/App/Changed.swift", "Sources/App/Removed.swift"},
            {"App.Alive"},
            now,
        )

        assert count == 1
        session = driver.session.return_value.__aenter__.return_value
        kwargs = session.run.call_args.kwargs
        assert kwargs["group_id"] == "project/files"
        assert set(kwargs["file_paths"]) == {
            "Sources/App/Changed.swift",
            "Sources/App/Removed.swift",
        }
        assert set(kwargs["qnames"]) == {"App.Alive"}
