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
from palace_mcp.extractors.foundation.incremental_scope import (
    IncrementalMode,
    IncrementalPathScope,
)


def _ctx(tmp_path: Path, run_id: str) -> ExtractorRunContext:
    return ExtractorRunContext(
        project_slug="gimle",
        group_id="project/gimle",
        repo_path=tmp_path,
        run_id=run_id,
        duration_ms=0,
        logger=logging.getLogger("test"),
    )


async def _seed_symbol(
    driver: AsyncDriver,
    *,
    qname: str,
    file_path: str | None = None,
    deleted: bool = False,
) -> None:
    async with driver.session() as session:
        await session.run(
            """
            MERGE (s:Symbol {qualified_name: $qname, group_id: $group_id})
            SET s.file_path = $file_path
            FOREACH (_ IN CASE WHEN $deleted THEN [1] ELSE [] END |
              SET s.deleted_at = datetime()
              SET s:Deprecated
            )
            FOREACH (_ IN CASE WHEN $deleted THEN [] ELSE [1] END |
              SET s.deleted_at = null
              REMOVE s:Deprecated
            )
            """,
            qname=qname,
            group_id="project/gimle",
            file_path=file_path,
            deleted=deleted,
        )


async def _seed_call_edge(
    driver: AsyncDriver,
    *,
    group_id: str,
    source: str,
    target: str,
    run_id: str,
) -> None:
    async with driver.session() as session:
        await session.run(
            """
            MATCH (source:Symbol {qualified_name: $source, group_id: $group_id})
            MATCH (target:Symbol {qualified_name: $target, group_id: $group_id})
            MERGE (source)-[rel:CALLS {via: 'indexstore'}]->(target)
            SET rel.last_seen_in_run_id = $run_id
            """,
            group_id=group_id,
            source=source,
            target=target,
            run_id=run_id,
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
        ref_result = await session.run(
            "MATCH ()-[rel:REFERENCES]->() RETURN count(rel) AS count"
        )
        call_record = await call_result.single()
        ref_record = await ref_result.single()

    assert call_record is not None
    assert call_record["count"] == 1
    assert call_record["last_run"] == "run-2"
    assert ref_record is not None
    assert ref_record["count"] == 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_call_edge_swift_incremental_replaces_changed_callers_only(
    driver: AsyncDriver,
    graphiti_mock: MagicMock,
    tmp_path: Path,
) -> None:
    changed_file = "Sources/ChangedCaller.swift"
    unchanged_file = "Sources/UnchangedCaller.swift"
    callee_file = "Sources/Callee.swift"
    await _seed_symbol(driver, qname="Changed caller", file_path=changed_file)
    await _seed_symbol(driver, qname="Old callee", file_path=callee_file)
    await _seed_symbol(driver, qname="New callee", file_path=callee_file)
    await _seed_symbol(driver, qname="Stable caller", file_path=unchanged_file)
    await _seed_symbol(driver, qname="Stable callee", file_path=callee_file)
    await _seed_call_edge(
        driver,
        group_id="project/gimle",
        source="Changed caller",
        target="Old callee",
        run_id="run-before",
    )
    await _seed_call_edge(
        driver,
        group_id="project/gimle",
        source="Stable caller",
        target="Stable callee",
        run_id="run-before",
    )

    store_path = tmp_path / "DataStore"
    (store_path / "v5").mkdir(parents=True)
    scan_result = CallEdgeScanResult(
        edges=(
            CallEdgeRecord(
                source="Changed caller",
                target="New callee",
                source_file=str((tmp_path / changed_file).resolve()),
            ),
        ),
        counters={"calls_seen": 1, "missing_relation": 0},
        records_scanned=1,
        occurrences_scanned=1,
    )
    extractor = CallEdgeSwiftExtractor()

    with (
        patch("palace_mcp.mcp_server.get_driver", return_value=driver),
        patch(
            "palace_mcp.mcp_server.get_settings",
            return_value=SimpleNamespace(
                palace_indexstore_paths={"gimle": str(store_path)},
                palace_sourcekit_index_store_path=None,
                palace_incremental_ingest=True,
            ),
        ),
        patch(
            "palace_mcp.extractors.call_edge_swift.derive_incremental_path_scope",
            return_value=IncrementalPathScope(
                mode=IncrementalMode.INCREMENTAL,
                changed_paths={changed_file},
                removed_paths=set(),
            ),
        ),
        patch(
            "palace_mcp.extractors.call_edge_swift.collect_call_edges",
            return_value=scan_result,
        ),
    ):
        await extractor.run(graphiti=graphiti_mock, ctx=_ctx(tmp_path, "run-2"))

    async with driver.session() as session:
        changed = await (
            await session.run(
                """
                MATCH (:Symbol {qualified_name: 'Changed caller', group_id: $group_id})
                      -[rel:CALLS {via: 'indexstore'}]->
                      (:Symbol {group_id: $group_id})
                RETURN collect(rel.last_seen_in_run_id) AS runs
                """,
                group_id="project/gimle",
            )
        ).single()
        stable = await (
            await session.run(
                """
                MATCH (:Symbol {qualified_name: 'Stable caller', group_id: $group_id})
                      -[rel:CALLS {via: 'indexstore'}]->
                      (:Symbol {qualified_name: 'Stable callee', group_id: $group_id})
                RETURN count(rel) AS count, max(rel.last_seen_in_run_id) AS last_run
                """,
                group_id="project/gimle",
            )
        ).single()

    assert changed is not None
    assert changed["runs"] == ["run-2"]
    assert stable is not None
    assert stable["count"] == 1
    assert stable["last_run"] == "run-before"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_call_edge_swift_incremental_deletes_orphan_for_renamed_callee(
    driver: AsyncDriver,
    graphiti_mock: MagicMock,
    tmp_path: Path,
) -> None:
    changed_file = "Sources/RenamedCallee.swift"
    caller_file = "Sources/StableCaller.swift"
    await _seed_symbol(driver, qname="Stable caller", file_path=caller_file)
    await _seed_symbol(
        driver,
        qname="Old callee",
        file_path=changed_file,
        deleted=True,
    )
    await _seed_symbol(driver, qname="New callee", file_path=changed_file)
    await _seed_call_edge(
        driver,
        group_id="project/gimle",
        source="Stable caller",
        target="Old callee",
        run_id="run-before",
    )

    store_path = tmp_path / "DataStore"
    (store_path / "v5").mkdir(parents=True)
    extractor = CallEdgeSwiftExtractor()

    with (
        patch("palace_mcp.mcp_server.get_driver", return_value=driver),
        patch(
            "palace_mcp.mcp_server.get_settings",
            return_value=SimpleNamespace(
                palace_indexstore_paths={"gimle": str(store_path)},
                palace_sourcekit_index_store_path=None,
                palace_incremental_ingest=True,
            ),
        ),
        patch(
            "palace_mcp.extractors.call_edge_swift.derive_incremental_path_scope",
            return_value=IncrementalPathScope(
                mode=IncrementalMode.INCREMENTAL,
                changed_paths={changed_file},
                removed_paths=set(),
            ),
        ),
        patch(
            "palace_mcp.extractors.call_edge_swift.collect_call_edges",
            return_value=CallEdgeScanResult(
                edges=tuple(),
                counters={"calls_seen": 0, "missing_relation": 0},
                records_scanned=0,
                occurrences_scanned=0,
            ),
        ),
    ):
        await extractor.run(graphiti=graphiti_mock, ctx=_ctx(tmp_path, "run-2"))

    async with driver.session() as session:
        record = await (
            await session.run(
                """
                MATCH (:Symbol {qualified_name: 'Stable caller', group_id: $group_id})
                      -[rel:CALLS {via: 'indexstore'}]->
                      (:Symbol {qualified_name: 'Old callee', group_id: $group_id})
                RETURN count(rel) AS count
                """,
                group_id="project/gimle",
            )
        ).single()

    assert record is not None
    assert record["count"] == 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_call_edge_swift_incremental_is_group_scoped(
    driver: AsyncDriver,
    graphiti_mock: MagicMock,
    tmp_path: Path,
) -> None:
    changed_file = "Sources/ChangedCaller.swift"
    await _seed_symbol(driver, qname="Gimle caller", file_path=changed_file)
    await _seed_symbol(driver, qname="Gimle callee", file_path="Sources/Callee.swift")

    async with driver.session() as session:
        await session.run(
            """
            MERGE (source:Symbol {qualified_name: 'Other caller', group_id: 'project/other'})
            SET source.file_path = $file_path, source.deleted_at = null
            REMOVE source:Deprecated
            MERGE (target:Symbol {qualified_name: 'Other callee', group_id: 'project/other'})
            SET target.file_path = 'Sources/Callee.swift', target.deleted_at = null
            REMOVE target:Deprecated
            MERGE (source)-[rel:CALLS {via: 'indexstore'}]->(target)
            SET rel.last_seen_in_run_id = 'other-run'
            """,
            file_path=changed_file,
        )

    store_path = tmp_path / "DataStore"
    (store_path / "v5").mkdir(parents=True)
    extractor = CallEdgeSwiftExtractor()

    with (
        patch("palace_mcp.mcp_server.get_driver", return_value=driver),
        patch(
            "palace_mcp.mcp_server.get_settings",
            return_value=SimpleNamespace(
                palace_indexstore_paths={"gimle": str(store_path)},
                palace_sourcekit_index_store_path=None,
                palace_incremental_ingest=True,
            ),
        ),
        patch(
            "palace_mcp.extractors.call_edge_swift.derive_incremental_path_scope",
            return_value=IncrementalPathScope(
                mode=IncrementalMode.INCREMENTAL,
                changed_paths={changed_file},
                removed_paths=set(),
            ),
        ),
        patch(
            "palace_mcp.extractors.call_edge_swift.collect_call_edges",
            return_value=CallEdgeScanResult(
                edges=(
                    CallEdgeRecord(
                        source="Gimle caller",
                        target="Gimle callee",
                        source_file=str((tmp_path / changed_file).resolve()),
                    ),
                ),
                counters={"calls_seen": 1, "missing_relation": 0},
                records_scanned=1,
                occurrences_scanned=1,
            ),
        ),
    ):
        await extractor.run(graphiti=graphiti_mock, ctx=_ctx(tmp_path, "run-2"))

    async with driver.session() as session:
        record = await (
            await session.run(
                """
                MATCH (:Symbol {qualified_name: 'Other caller', group_id: 'project/other'})
                      -[rel:CALLS {via: 'indexstore'}]->
                      (:Symbol {qualified_name: 'Other callee', group_id: 'project/other'})
                RETURN count(rel) AS count, max(rel.last_seen_in_run_id) AS last_run
                """
            )
        ).single()

    assert record is not None
    assert record["count"] == 1
    assert record["last_run"] == "other-run"
