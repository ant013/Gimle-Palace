from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from neo4j import AsyncDriver

from palace_mcp.code.indexstore import CallEdgeRecord, CallEdgeScanResult
from palace_mcp.extractors.base import ExtractorRunContext
from palace_mcp.extractors.call_edge_swift import CallEdgeSwiftExtractor


def _ctx(tmp_path: Path, run_id: str) -> ExtractorRunContext:
    return ExtractorRunContext(
        project_slug="gimle",
        group_id="project/gimle",
        repo_path=tmp_path,
        run_id=run_id,
        duration_ms=0,
        logger=logging.getLogger("test"),
    )


async def _seed_symbol(driver: AsyncDriver, *, qname: str) -> None:
    async with driver.session() as session:
        await session.run(
            """
            MERGE (s:Symbol {qualified_name: $qname, group_id: $group_id})
            SET s.deleted_at = null
            REMOVE s:Deprecated
            """,
            qname=qname,
            group_id="project/gimle",
        )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_call_edge_swift_writes_calls_edges_and_replaces_snapshot(
    driver: AsyncDriver,
    graphiti_mock: MagicMock,
    tmp_path: Path,
) -> None:
    await _seed_symbol(driver, qname="UwMiniCore caller")
    await _seed_symbol(driver, qname="UwMiniCore callee")

    store_path = tmp_path / "DataStore"
    (store_path / "v5").mkdir(parents=True)
    scan_result = CallEdgeScanResult(
        edges=(
            CallEdgeRecord(source="UwMiniCore caller", target="UwMiniCore callee"),
            CallEdgeRecord(source="UwMiniCore caller", target="UwMiniCore missing"),
        ),
        counters={"calls_seen": 2, "missing_relation": 0},
        records_scanned=1,
        occurrences_scanned=2,
    )
    extractor = CallEdgeSwiftExtractor()

    with (
        patch("palace_mcp.mcp_server.get_driver", return_value=driver),
        patch(
            "palace_mcp.mcp_server.get_settings",
            return_value=SimpleNamespace(
                palace_indexstore_paths={"gimle": str(store_path)},
                palace_sourcekit_index_store_path=None,
            ),
        ),
        patch(
            "palace_mcp.extractors.call_edge_swift.collect_call_edges",
            return_value=scan_result,
        ),
    ):
        first = await extractor.run(graphiti=graphiti_mock, ctx=_ctx(tmp_path, "run-1"))
        second = await extractor.run(
            graphiti=graphiti_mock, ctx=_ctx(tmp_path, "run-2")
        )

    assert first.edges_written == 1
    assert second.edges_written == 1

    async with driver.session() as session:
        call_result = await session.run(
            """
            MATCH (:Symbol {qualified_name: $source, group_id: $group_id})
                  -[rel:CALLS {via: 'indexstore'}]->
                  (:Symbol {qualified_name: $target, group_id: $group_id})
            RETURN count(rel) AS count, max(rel.last_seen_in_run_id) AS last_run
            """,
            source="UwMiniCore caller",
            target="UwMiniCore callee",
            group_id="project/gimle",
        )
        ref_result = await session.run("MATCH ()-[rel:REFERENCES]->() RETURN count(rel) AS count")
        call_record = await call_result.single()
        ref_record = await ref_result.single()

    assert call_record is not None
    assert call_record["count"] == 1
    assert call_record["last_run"] == "run-2"
    assert ref_record is not None
    assert ref_record["count"] == 0
