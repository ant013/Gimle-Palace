"""Unit tests for symbol_node_writer (mocked Neo4j driver)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from palace_mcp.extractors.foundation.symbol_node_writer import (
    _MERGE_BACKED_BY_SYMBOL_SHADOWS,
    _MERGE_SYMBOLS,
    _SOFT_DELETE_ABSENT,
    build_symbol_shadow_rows,
    build_symbol_node_rows,
    soft_delete_symbols,
    write_symbol_nodes,
)


class TestMergeQueryClearsDeletedAt:
    def test_merge_symbols_sets_deleted_at_null(self) -> None:
        """Re-ingesting a symbol via MERGE must clear deleted_at."""
        assert "deleted_at" in _MERGE_SYMBOLS
        assert "null" in _MERGE_SYMBOLS

    def test_soft_delete_query_uses_group_id_and_qnames(self) -> None:
        assert "$group_id" in _SOFT_DELETE_ABSENT
        assert "$qnames" in _SOFT_DELETE_ABSENT
        assert "$now" in _SOFT_DELETE_ABSENT
        assert "NOT" in _SOFT_DELETE_ABSENT


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
        assert row["file_path"] is None

    def test_rows_map_type_kind(self) -> None:
        from palace_mcp.extractors.scip_parser import ScipSymbolInfo

        si = ScipSymbolInfo(
            qualified_name="App.BalanceData",
            scip_kind_name="Type",
            module_name="App",
            relationships=(),
        )
        rows = build_symbol_node_rows([si], {}, "project/test")

        assert rows[0]["kind"] == "type"

    def test_shadow_rows_include_only_supported_non_callable_kinds(self) -> None:
        from palace_mcp.extractors.scip_parser import ScipSymbolInfo

        rows = build_symbol_shadow_rows(
            [
                ScipSymbolInfo(
                    qualified_name="App.BalanceData",
                    scip_kind_name="Struct",
                    module_name="App",
                    relationships=(),
                ),
                ScipSymbolInfo(
                    qualified_name="App.run()",
                    scip_kind_name="Function",
                    module_name="App",
                    relationships=(),
                ),
            ],
            "project/test",
        )

        assert rows == [
            {
                "qualified_name": "App.BalanceData",
                "group_id": "project/test",
            }
        ]


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


class TestWriteSymbolNodes:
    def _make_driver(self) -> MagicMock:
        result = AsyncMock()
        result.consume = AsyncMock()
        session = AsyncMock()
        session.run = AsyncMock(return_value=result)
        session_cm = MagicMock()
        session_cm.__aenter__ = AsyncMock(return_value=session)
        session_cm.__aexit__ = AsyncMock(return_value=False)
        driver = MagicMock()
        driver.session.return_value = session_cm
        return driver

    @pytest.mark.asyncio
    async def test_non_callable_symbols_merge_backing_shadow_edges(self) -> None:
        from palace_mcp.extractors.scip_parser import ScipSymbolInfo

        driver = self._make_driver()
        await write_symbol_nodes(
            driver,
            [
                ScipSymbolInfo(
                    qualified_name="App.BalanceData",
                    scip_kind_name="Struct",
                    module_name="App",
                    relationships=(),
                )
            ],
            {},
            "project/test",
        )

        session = driver.session.return_value.__aenter__.return_value
        shadow_calls = [
            call
            for call in session.run.call_args_list
            if call.args and call.args[0] == _MERGE_BACKED_BY_SYMBOL_SHADOWS
        ]

        assert len(shadow_calls) == 1
        assert shadow_calls[0].kwargs["rows"] == [
            {
                "qualified_name": "App.BalanceData",
                "group_id": "project/test",
            }
        ]
