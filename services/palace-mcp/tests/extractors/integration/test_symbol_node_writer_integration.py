"""Integration tests for symbol_node_writer soft-delete + unique constraint."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from neo4j import AsyncDriver

from palace_mcp.extractors.foundation.schema import ensure_custom_schema
from palace_mcp.extractors.foundation.symbol_node_writer import (
    soft_delete_symbols,
    write_symbol_nodes,
)
from palace_mcp.extractors.scip_parser import ScipSymbolInfo

_GROUP = "project/test-soft-delete"
_NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

_SYM_A = ScipSymbolInfo(
    qualified_name="App.Alpha",
    scip_kind_name="Class",
    module_name="App",
    relationships=(),
)
_SYM_B = ScipSymbolInfo(
    qualified_name="App.Beta",
    scip_kind_name="Function",
    module_name="App",
    relationships=(),
)
_SYM_C = ScipSymbolInfo(
    qualified_name="App.Gamma",
    scip_kind_name="Struct",
    module_name="App",
    relationships=(),
)


async def _count_active(driver: AsyncDriver, group_id: str) -> int:
    """Count Symbol nodes with no deleted_at (active)."""
    async with driver.session() as session:
        result = await session.run(
            "MATCH (s:Symbol {group_id: $g}) WHERE s.deleted_at IS NULL RETURN count(s) AS n",
            g=group_id,
        )
        record = await result.single()
        return int(record["n"]) if record else 0


async def _count_deleted(driver: AsyncDriver, group_id: str) -> int:
    """Count Symbol nodes with deleted_at set."""
    async with driver.session() as session:
        result = await session.run(
            "MATCH (s:Symbol {group_id: $g}) WHERE s.deleted_at IS NOT NULL RETURN count(s) AS n",
            g=group_id,
        )
        record = await result.single()
        return int(record["n"]) if record else 0


async def _get_deleted_at(driver: AsyncDriver, group_id: str, qname: str) -> object:
    async with driver.session() as session:
        result = await session.run(
            "MATCH (s:Symbol {group_id: $g, qualified_name: $q}) RETURN s.deleted_at AS d",
            g=group_id,
            q=qname,
        )
        record = await result.single()
        return record["d"] if record else None


@pytest.mark.integration
class TestSymbolSoftDelete:
    @pytest.mark.asyncio
    async def test_reingest_same_scip_does_not_increase_active_count(
        self, driver: AsyncDriver
    ) -> None:
        """Acceptance: re-ingesting identical SCIP keeps count(:Symbol {deleted_at: null}) stable."""
        await ensure_custom_schema(driver)

        syms = [_SYM_A, _SYM_B]
        seen = {s.qualified_name for s in syms}

        # First ingest
        await write_symbol_nodes(driver, syms, {}, _GROUP)
        await soft_delete_symbols(driver, _GROUP, seen, _NOW)
        count_after_first = await _count_active(driver, _GROUP)

        # Second ingest (identical)
        await write_symbol_nodes(driver, syms, {}, _GROUP)
        await soft_delete_symbols(driver, _GROUP, seen, _NOW)
        count_after_second = await _count_active(driver, _GROUP)

        assert count_after_first == 2
        assert count_after_second == count_after_first

    @pytest.mark.asyncio
    async def test_absent_symbol_gets_deleted_at_set(self, driver: AsyncDriver) -> None:
        """Acceptance: ingest A+B+C, then ingest A+B → C has deleted_at set."""
        await ensure_custom_schema(driver)

        syms_a = [_SYM_A, _SYM_B, _SYM_C]
        seen_a = {s.qualified_name for s in syms_a}

        await write_symbol_nodes(driver, syms_a, {}, _GROUP)
        await soft_delete_symbols(driver, _GROUP, seen_a, _NOW)

        assert await _count_active(driver, _GROUP) == 3
        assert await _count_deleted(driver, _GROUP) == 0

        # Second ingest: Gamma removed
        syms_b = [_SYM_A, _SYM_B]
        seen_b = {s.qualified_name for s in syms_b}

        now2 = datetime(2026, 1, 2, 12, 0, 0, tzinfo=timezone.utc)
        await write_symbol_nodes(driver, syms_b, {}, _GROUP)
        await soft_delete_symbols(driver, _GROUP, seen_b, now2)

        assert await _count_active(driver, _GROUP) == 2
        assert await _count_deleted(driver, _GROUP) == 1

        gamma_deleted_at = await _get_deleted_at(driver, _GROUP, "App.Gamma")
        assert gamma_deleted_at is not None

    @pytest.mark.asyncio
    async def test_symbol_undeleted_when_it_reappears(
        self, driver: AsyncDriver
    ) -> None:
        """A symbol soft-deleted in one run is cleared when it reappears in the next."""
        await ensure_custom_schema(driver)

        syms_a = [_SYM_A, _SYM_B]
        seen_a = {s.qualified_name for s in syms_a}
        await write_symbol_nodes(driver, syms_a, {}, _GROUP)
        await soft_delete_symbols(driver, _GROUP, seen_a, _NOW)

        # Remove B
        syms_b = [_SYM_A]
        seen_b = {s.qualified_name for s in syms_b}
        now2 = datetime(2026, 1, 2, 12, 0, 0, tzinfo=timezone.utc)
        await write_symbol_nodes(driver, syms_b, {}, _GROUP)
        await soft_delete_symbols(driver, _GROUP, seen_b, now2)

        assert await _get_deleted_at(driver, _GROUP, "App.Beta") is not None

        # B comes back
        syms_c = [_SYM_A, _SYM_B]
        seen_c = {s.qualified_name for s in syms_c}
        now3 = datetime(2026, 1, 3, 12, 0, 0, tzinfo=timezone.utc)
        await write_symbol_nodes(driver, syms_c, {}, _GROUP)
        await soft_delete_symbols(driver, _GROUP, seen_c, now3)

        assert await _get_deleted_at(driver, _GROUP, "App.Beta") is None
        assert await _count_active(driver, _GROUP) == 2
        assert await _count_deleted(driver, _GROUP) == 0
