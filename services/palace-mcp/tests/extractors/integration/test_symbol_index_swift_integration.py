"""Integration test: SymbolIndexSwift runtime path via runner + real Neo4j/Tantivy."""

from __future__ import annotations

from pathlib import Path
import shutil
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from neo4j import AsyncDriver

from palace_mcp.extractors.foundation.importance import BoundedInDegreeCounter
from palace_mcp.extractors.foundation.identifiers import symbol_id_for
from palace_mcp.extractors.foundation.tantivy_bridge import TantivyBridge
from palace_mcp.extractors.base import ExtractorRunContext
from palace_mcp.extractors.prune_swift_symbols import PruneSwiftSymbols
from palace_mcp.extractors.symbol_index_swift import SymbolIndexSwift
from palace_mcp.extractors.runner import run_extractor
from palace_mcp.extractors.schema import ensure_extractors_schema
from palace_mcp.extractors.scip_parser import parse_scip_file
from palace_mcp.proto import scip_pb2
from tests.extractors.unit.test_real_scip_fixtures import (
    _UW_IOS_N_DOCUMENTS,
    _UW_IOS_TOOL_NAME,
    requires_scip_uw_ios,
)
from tests.extractors.fixtures.scip_factory import (
    build_swift_struct_scip_index_with_symbol_infos,
    write_scip_fixture,
)

_RUN_ID = "swift-integration-run-001"
_RERUN_ID = "swift-integration-run-002"
_HEAD_SHA = "0123456789abcdef0123456789abcdef01234567"
_STORE_QNAME = "UwMiniCore s%3A10UwMiniCore11WalletStoreC"
_SELECT_QNAME = "UwMiniCore s%3A10UwMiniCore11WalletStoreC6select8walletIDySi_tF"
FIXTURE_SCIP = (
    Path(__file__).parent.parent
    / "fixtures"
    / "uw-ios-mini-project"
    / "scip"
    / "index.scip"
)
FIXTURE_REPO = (
    Path(__file__).parent.parent / "fixtures" / "uw-ios-mini-project" / "UwMiniCore"
)
_INCREMENTAL_RUN_1 = "swift-incremental-run-001"
_INCREMENTAL_RUN_2 = "swift-incremental-run-002"
_PRUNE_RUN_2 = "swift-prune-run-002"
_SCIP_KIND_CLASS = 7
_INCREMENTAL_UNCHANGED_QNAMES = [
    "IncrementalMini FileAOne",
    "IncrementalMini FileATwo",
    "IncrementalMini FileBOne",
    "IncrementalMini FileBTwo",
]
_INCREMENTAL_CHANGED_QNAME = "IncrementalMini FileCOne"
_INCREMENTAL_FILE_DOCS = {
    "Sources/Incremental/FileA.swift": [
        ("scip-swift apple IncrementalMini . FileAOne", 1, _SCIP_KIND_CLASS),
        ("scip-swift apple IncrementalMini . FileATwo", 2, _SCIP_KIND_CLASS),
    ],
    "Sources/Incremental/FileB.swift": [
        ("scip-swift apple IncrementalMini . FileBOne", 1, _SCIP_KIND_CLASS),
        ("scip-swift apple IncrementalMini . FileBTwo", 2, _SCIP_KIND_CLASS),
    ],
}


def _build_incremental_prune_scip(*, file_c_lines: tuple[int, int]) -> object:
    index = scip_pb2.Index()  # type: ignore[attr-defined]
    metadata = scip_pb2.Metadata()  # type: ignore[attr-defined]
    metadata.version = scip_pb2.ProtocolVersion.UnspecifiedProtocolVersion  # type: ignore[attr-defined]
    metadata.tool_info.name = "palace-swift-scip-emit"
    metadata.tool_info.version = "0.1.0"
    metadata.project_root = "file:///test"
    index.metadata.CopyFrom(metadata)

    docs = dict(_INCREMENTAL_FILE_DOCS)
    docs["Sources/Incremental/FileC.swift"] = [
        (
            "scip-swift apple IncrementalMini . FileCOne",
            file_c_lines[0],
            _SCIP_KIND_CLASS,
        ),
        (
            "scip-swift apple IncrementalMini . FileCTwo",
            file_c_lines[1],
            _SCIP_KIND_CLASS,
        ),
    ]

    for path, symbols in docs.items():
        doc = index.documents.add()
        doc.relative_path = path
        doc.language = "swift"
        for symbol, line, kind in symbols:
            occ = doc.occurrences.add()
            occ.range.extend([line, 0, 10])
            occ.symbol = symbol
            occ.symbol_roles = 1

            sym_info = doc.symbols.add()
            sym_info.symbol = symbol
            sym_info.kind = kind

    return index


def _write_incremental_repo(repo: Path, *, file_c_suffix: str) -> None:
    files = {
        "Sources/Incremental/FileA.swift": "struct FileAOne {}\nstruct FileATwo {}\n",
        "Sources/Incremental/FileB.swift": "struct FileBOne {}\nstruct FileBTwo {}\n",
        "Sources/Incremental/FileC.swift": (
            f"struct FileCOne {{}}\nstruct FileCTwo {{}}\n{file_c_suffix}\n"
        ),
    }
    for relative_path, content in files.items():
        target = repo / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


def _copy_fixture_repo(repo: Path) -> None:
    for relative_path in ("Package.swift", "Sources", "Pods"):
        source = FIXTURE_REPO / relative_path
        destination = repo / relative_path
        if source.is_dir():
            shutil.copytree(source, destination, dirs_exist_ok=True)
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)


@pytest.fixture
async def _project_and_repo(driver: AsyncDriver, tmp_path: Path) -> Path:
    async with driver.session() as session:
        await session.run(
            """
            MERGE (p:Project {slug: $slug})
            SET p.group_id = 'project/' + $slug,
                p.name = $name,
                p.tags = []
            """,
            slug="uw-ios-mini",
            name="UwIosMini",
        )
    repo = tmp_path / "repos" / "uw-ios-mini"
    repo.mkdir(parents=True)
    _copy_fixture_repo(repo)
    (repo / ".git").mkdir()
    (repo / ".git" / "HEAD").write_text(f"{_HEAD_SHA}\n")
    return tmp_path / "repos"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_run_writes_shadow_backing_for_struct_symbol(
    driver: AsyncDriver,
    graphiti_mock: MagicMock,
    tmp_path: Path,
) -> None:
    await ensure_extractors_schema(driver)

    scip_path = write_scip_fixture(
        build_swift_struct_scip_index_with_symbol_infos(),
        tmp_path / "balance-data.scip",
    )
    repo = tmp_path / "repos" / "swift-shadow-mini"
    repo.mkdir(parents=True)
    (repo / "Sources" / "UwMiniCore" / "Models").mkdir(parents=True)
    (repo / "Sources" / "UwMiniCore" / "Models" / "BalanceData.swift").write_text(
        "struct BalanceData {}\n",
        encoding="utf-8",
    )
    (repo / "Sources" / "UwMiniApp").mkdir(parents=True)
    (repo / "Sources" / "UwMiniApp" / "ContentView.swift").write_text(
        "func renderBalanceData() {}\n",
        encoding="utf-8",
    )
    (repo / ".git").mkdir()
    (repo / ".git" / "HEAD").write_text(
        "0123456789abcdef0123456789abcdef01234567\n",
        encoding="utf-8",
    )

    settings = MagicMock()
    tantivy_dir = tmp_path / "tantivy"
    tantivy_dir.mkdir()
    settings.palace_tantivy_index_path = str(tantivy_dir)
    settings.palace_tantivy_heap_mb = 50
    settings.palace_max_occurrences_total = 50_000_000
    settings.palace_max_occurrences_per_project = 10_000_000
    settings.palace_importance_threshold_use = 0.0
    settings.palace_max_occurrences_per_symbol = 5_000
    settings.palace_recency_decay_days = 30.0

    ctx = ExtractorRunContext(
        project_slug="swift-shadow-mini",
        group_id="project/swift-shadow-mini",
        repo_path=repo,
        run_id="swift-shadow-mini-run-001",
        duration_ms=0,
        logger=MagicMock(),
        scip_path=scip_path,
    )

    with (
        patch("palace_mcp.mcp_server.get_driver", return_value=driver),
        patch("palace_mcp.mcp_server.get_settings", return_value=settings),
    ):
        stats = await SymbolIndexSwift().run(graphiti=graphiti_mock, ctx=ctx)

    assert stats.nodes_written >= 2

    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (symbol:Symbol {
                qualified_name: $qualified_name,
                group_id: $group_id
            })-[:BACKED_BY_SYMBOL]->(shadow:SymbolOccurrenceShadow {
                symbol_qualified_name: $qualified_name,
                group_id: $group_id
            })
            RETURN count(shadow) AS n
            """,
            qualified_name="UwMiniCore BalanceData",
            group_id="project/swift-shadow-mini",
        )
        record = await result.single()

    assert record is not None
    assert record["n"] >= 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_incremental_run_does_not_deprecate_unchanged_file_symbols(
    driver: AsyncDriver,
    graphiti_mock: MagicMock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await ensure_extractors_schema(driver)
    async with driver.session() as session:
        await session.run(
            """
            MERGE (p:Project {slug: $slug})
            SET p.group_id = 'project/' + $slug,
                p.name = $name,
                p.tags = []
            """,
            slug="swift-incremental-mini",
            name="SwiftIncrementalMini",
        )

    scip_path = tmp_path / "incremental.scip"
    write_scip_fixture(
        _build_incremental_prune_scip(file_c_lines=(1, 2)),
        scip_path,
    )

    repo_root = tmp_path / "repos"
    monkeypatch.setenv("PALACE_ALLOWED_REPO_ROOTS", str(repo_root))
    repo = repo_root / "swift-incremental-mini"
    repo.mkdir(parents=True)
    _write_incremental_repo(repo, file_c_suffix="// run 1")
    (repo / ".git").mkdir()
    (repo / ".git" / "HEAD").write_text(f"{_HEAD_SHA}\n", encoding="utf-8")

    settings = MagicMock()
    tantivy_dir = tmp_path / "tantivy"
    tantivy_dir.mkdir()
    settings.palace_tantivy_index_path = str(tantivy_dir)
    settings.palace_tantivy_heap_mb = 50
    settings.palace_max_occurrences_total = 50_000_000
    settings.palace_max_occurrences_per_project = 10_000_000
    settings.palace_importance_threshold_use = 0.0
    settings.palace_max_occurrences_per_symbol = 5_000
    settings.palace_recency_decay_days = 30.0
    settings.palace_incremental_ingest = True

    run1_ctx = ExtractorRunContext(
        project_slug="swift-incremental-mini",
        group_id="project/swift-incremental-mini",
        repo_path=repo,
        run_id=_INCREMENTAL_RUN_1,
        duration_ms=0,
        logger=MagicMock(),
        scip_path=scip_path,
    )
    run2_ctx = ExtractorRunContext(
        project_slug="swift-incremental-mini",
        group_id="project/swift-incremental-mini",
        repo_path=repo,
        run_id=_INCREMENTAL_RUN_2,
        duration_ms=0,
        logger=MagicMock(),
        scip_path=scip_path,
    )
    prune_ctx = ExtractorRunContext(
        project_slug="swift-incremental-mini",
        group_id="project/swift-incremental-mini",
        repo_path=repo,
        run_id=_PRUNE_RUN_2,
        duration_ms=0,
        logger=MagicMock(),
        companion_run_id=_INCREMENTAL_RUN_2,
    )

    with (
        patch("palace_mcp.mcp_server.get_driver", return_value=driver),
        patch("palace_mcp.mcp_server.get_settings", return_value=settings),
    ):
        first_run = await SymbolIndexSwift().run(graphiti=graphiti_mock, ctx=run1_ctx)

        _write_incremental_repo(repo, file_c_suffix="// run 2 changed")
        write_scip_fixture(
            _build_incremental_prune_scip(file_c_lines=(10, 20)),
            scip_path,
        )
        second_run = await SymbolIndexSwift().run(graphiti=graphiti_mock, ctx=run2_ctx)
        prune_stats = await PruneSwiftSymbols().run(
            graphiti=SimpleNamespace(driver=driver),
            ctx=prune_ctx,
        )

    assert first_run.nodes_written == 6
    assert second_run.nodes_written == 6
    assert prune_stats.nodes_written == 0

    async with TantivyBridge(
        tantivy_dir, heap_size_mb=settings.palace_tantivy_heap_mb
    ) as bridge:
        unchanged_docs = {}
        for qname in _INCREMENTAL_UNCHANGED_QNAMES:
            unchanged_docs[qname] = await bridge.search_by_symbol_id_async(
                symbol_id_for(qname)
            )
        changed_docs = await bridge.search_by_symbol_id_async(
            symbol_id_for(_INCREMENTAL_CHANGED_QNAME)
        )

    for qname, docs in unchanged_docs.items():
        assert len(docs) == 1, qname
    assert len(changed_docs) == 1
    assert changed_docs[0]["doc_key"][0].endswith(f":10:0:{_HEAD_SHA}")

    async with driver.session() as session:
        unchanged_result = await session.run(
            """
            MATCH (s:Symbol {project_id: $project_id})
            WHERE s.qualified_name IN $qnames
            RETURN collect(s.last_seen_in_run_id) AS run_ids,
                   sum(CASE WHEN s:Deprecated THEN 1 ELSE 0 END) AS deprecated_total
            """,
            project_id="project/swift-incremental-mini",
            qnames=_INCREMENTAL_UNCHANGED_QNAMES,
        )
        unchanged_record = await unchanged_result.single()

        changed_result = await session.run(
            """
            MATCH (s:Symbol {
                project_id: $project_id,
                qualified_name: $qualified_name
            })
            RETURN s.last_seen_in_run_id AS run_id,
                   s:Deprecated AS deprecated
            """,
            project_id="project/swift-incremental-mini",
            qualified_name=_INCREMENTAL_CHANGED_QNAME,
        )
        changed_record = await changed_result.single()

    assert unchanged_record is not None
    assert unchanged_record["deprecated_total"] == 0
    assert unchanged_record["run_ids"] == [_INCREMENTAL_RUN_2] * len(
        _INCREMENTAL_UNCHANGED_QNAMES
    )
    assert changed_record is not None
    assert changed_record["run_id"] == _INCREMENTAL_RUN_2
    assert changed_record["deprecated"] is False


@pytest.mark.integration
@requires_scip_uw_ios
class TestSymbolIndexSwiftIntegration:
    @pytest.mark.asyncio
    async def test_run_extractor_registers_and_ingests_all_three_phases(
        self,
        driver: AsyncDriver,
        graphiti_mock: MagicMock,
        _project_and_repo: Path,
        tmp_path: Path,
    ) -> None:
        await ensure_extractors_schema(driver)
        scip_path = FIXTURE_SCIP
        parsed = parse_scip_file(scip_path)
        assert parsed.metadata.tool_info.name == _UW_IOS_TOOL_NAME
        assert len(parsed.documents) == _UW_IOS_N_DOCUMENTS

        settings = MagicMock()
        settings.palace_scip_index_paths = {"uw-ios-mini": str(scip_path)}
        tantivy_dir = tmp_path / "tantivy"
        tantivy_dir.mkdir()
        settings.palace_tantivy_index_path = str(tantivy_dir)
        settings.palace_tantivy_heap_mb = 50
        settings.palace_max_occurrences_total = 50_000_000
        settings.palace_max_occurrences_per_project = 10_000_000
        settings.palace_importance_threshold_use = 0.0
        settings.palace_max_occurrences_per_symbol = 5_000
        settings.palace_recency_decay_days = 30.0

        with (
            patch("palace_mcp.mcp_server.get_driver", return_value=driver),
            patch("palace_mcp.mcp_server.get_settings", return_value=settings),
            patch("palace_mcp.extractors.runner.REPOS_ROOT", _project_and_repo),
            patch("palace_mcp.extractors.runner.uuid4", return_value=_RUN_ID),
        ):
            res = await run_extractor(
                name="symbol_index_swift",
                project="uw-ios-mini",
                driver=driver,
                graphiti=graphiti_mock,
            )

        assert res["ok"] is True
        assert res["extractor"] == "symbol_index_swift"
        assert res["project"] == "uw-ios-mini"
        assert res["success"] is True
        assert res["nodes_written"] >= 4

        async with driver.session() as session:
            result = await session.run(
                "MATCH (c:IngestCheckpoint {run_id: $rid}) "
                "RETURN c.phase AS phase, c.expected_doc_count AS count",
                rid=_RUN_ID,
            )
            rows = await result.data()
        counts = {row["phase"]: row["count"] for row in rows}
        assert counts["phase1_defs"] > 0
        assert counts["phase2_user_uses"] > counts["phase1_defs"]
        assert counts["phase3_vendor_uses"] > counts["phase2_user_uses"]

        async with TantivyBridge(
            tantivy_dir, heap_size_mb=settings.palace_tantivy_heap_mb
        ) as bridge:
            phase1_docs = await bridge.count_docs_for_run_async(_RUN_ID, "phase1_defs")
            phase2_docs = await bridge.count_docs_for_run_async(
                _RUN_ID, "phase2_user_uses"
            )
            phase3_docs = await bridge.count_docs_for_run_async(
                _RUN_ID, "phase3_vendor_uses"
            )
            hits = await bridge.search_by_symbol_id_async(symbol_id_for(_SELECT_QNAME))

        assert phase1_docs > 0
        assert phase2_docs > 0
        assert phase3_docs > 0
        paths = {hit["file_path"][0] for hit in hits}
        assert "Sources/UwMiniCore/State/WalletStore.swift" in paths
        assert "Sources/UwMiniApp/ContentView.swift" in paths
        assert "Pods/Foo/Foo.swift" in paths

        async with driver.session() as session:
            result = await session.run(
                """
                MATCH (:Symbol {
                    qualified_name: $qname,
                    group_id: $group_id
                })-[:BACKED_BY_SYMBOL]->(shadow:SymbolOccurrenceShadow)
                RETURN count(shadow) AS count,
                       collect(DISTINCT shadow.file_path) AS paths
                """,
                qname=_STORE_QNAME,
                group_id="project/uw-ios-mini",
            )
            record = await result.single()

        assert record is not None
        assert record["count"] >= 1
        assert "Sources/UwMiniCore/State/WalletStore.swift" in record["paths"]

    @pytest.mark.asyncio
    async def test_run_extractor_recovers_from_stale_counter_after_domain_reset(
        self,
        driver: AsyncDriver,
        graphiti_mock: MagicMock,
        _project_and_repo: Path,
        tmp_path: Path,
    ) -> None:
        await ensure_extractors_schema(driver)
        settings = MagicMock()
        settings.palace_scip_index_paths = {"uw-ios-mini": str(FIXTURE_SCIP)}
        tantivy_dir = tmp_path / "tantivy"
        tantivy_dir.mkdir()
        settings.palace_tantivy_index_path = str(tantivy_dir)
        settings.palace_tantivy_heap_mb = 50
        settings.palace_max_occurrences_total = 50_000_000
        settings.palace_max_occurrences_per_project = 10_000_000
        settings.palace_importance_threshold_use = 0.0
        settings.palace_max_occurrences_per_symbol = 5_000
        settings.palace_recency_decay_days = 30.0

        counter_path = tantivy_dir / "in_degree_counter.json"

        with (
            patch("palace_mcp.mcp_server.get_driver", return_value=driver),
            patch("palace_mcp.mcp_server.get_settings", return_value=settings),
            patch("palace_mcp.extractors.runner.REPOS_ROOT", _project_and_repo),
            patch(
                "palace_mcp.extractors.runner.uuid4",
                side_effect=[_RUN_ID, _RERUN_ID],
            ),
        ):
            first_run = await run_extractor(
                name="symbol_index_swift",
                project="uw-ios-mini",
                driver=driver,
                graphiti=graphiti_mock,
            )
            initial_counter = BoundedInDegreeCounter()
            assert (
                initial_counter.from_disk(counter_path, expected_run_id=_RUN_ID) is True
            )
            async with driver.session() as session:
                await session.run("MATCH (n) DETACH DELETE n")
                await session.run(
                    """
                    MERGE (p:Project {slug: $slug})
                    SET p.group_id = 'project/' + $slug,
                        p.name = $name,
                        p.tags = []
                    """,
                    slug="uw-ios-mini",
                    name="UwIosMini",
                )
            second_run = await run_extractor(
                name="symbol_index_swift",
                project="uw-ios-mini",
                driver=driver,
                graphiti=graphiti_mock,
            )

        assert first_run["ok"] is True
        assert first_run["success"] is True

        assert second_run["ok"] is True
        assert second_run["success"] is True

        rerun_counter = BoundedInDegreeCounter()
        assert rerun_counter.from_disk(counter_path, expected_run_id=_RERUN_ID) is True

        stale_counter = BoundedInDegreeCounter()
        assert stale_counter.from_disk(counter_path, expected_run_id=_RUN_ID) is False

    @pytest.mark.asyncio
    async def test_rerun_replaces_last_seen_edge_and_revives_deprecated_nodes(
        self,
        driver: AsyncDriver,
        graphiti_mock: MagicMock,
        _project_and_repo: Path,
        tmp_path: Path,
    ) -> None:
        await ensure_extractors_schema(driver)
        settings = MagicMock()
        settings.palace_scip_index_paths = {"uw-ios-mini": str(FIXTURE_SCIP)}
        tantivy_dir = tmp_path / "tantivy"
        tantivy_dir.mkdir()
        settings.palace_tantivy_index_path = str(tantivy_dir)
        settings.palace_tantivy_heap_mb = 50
        settings.palace_max_occurrences_total = 50_000_000
        settings.palace_max_occurrences_per_project = 10_000_000
        settings.palace_importance_threshold_use = 0.0
        settings.palace_max_occurrences_per_symbol = 5_000
        settings.palace_recency_decay_days = 30.0

        with (
            patch("palace_mcp.mcp_server.get_driver", return_value=driver),
            patch("palace_mcp.mcp_server.get_settings", return_value=settings),
            patch("palace_mcp.extractors.runner.REPOS_ROOT", _project_and_repo),
            patch(
                "palace_mcp.extractors.runner.uuid4",
                side_effect=[_RUN_ID, _RERUN_ID],
            ),
        ):
            first_run = await run_extractor(
                name="symbol_index_swift",
                project="uw-ios-mini",
                driver=driver,
                graphiti=graphiti_mock,
            )

            async with driver.session() as session:
                await session.run(
                    """
                    MATCH (f:File {
                        project_id: $project_id,
                        path: $file_path
                    })
                    SET f:Deprecated,
                        f.deprecated_at = datetime("2026-01-01T00:00:00Z"),
                        f.deprecated_in_commit = "old-commit"
                    WITH 1 AS _
                    MATCH (s:Symbol {
                        project_id: $project_id,
                        qualified_name: $qualified_name
                    })
                    SET s:Deprecated,
                        s.deprecated_at = datetime("2026-01-01T00:00:00Z"),
                        s.deprecated_in_commit = "old-commit"
                    """,
                    project_id="project/uw-ios-mini",
                    file_path="Sources/UwMiniCore/State/WalletStore.swift",
                    qualified_name=_STORE_QNAME,
                )

            wallet_store = (
                _project_and_repo
                / "uw-ios-mini"
                / "Sources"
                / "UwMiniCore"
                / "State"
                / "WalletStore.swift"
            )
            wallet_store.write_text(
                wallet_store.read_text(encoding="utf-8") + "\n// rerun\n",
                encoding="utf-8",
            )

            second_run = await run_extractor(
                name="symbol_index_swift",
                project="uw-ios-mini",
                driver=driver,
                graphiti=graphiti_mock,
            )

        assert first_run["ok"] is True
        assert first_run["success"] is True
        assert second_run["ok"] is True
        assert second_run["success"] is True

        async with driver.session() as session:
            stamp_result = await session.run(
                """
                MATCH (n {project_id: $project_id})
                WHERE n:File OR n:Symbol
                RETURN count(n) AS total,
                       sum(
                           CASE
                               WHEN n.last_seen_in_run_id IS NOT NULL
                                AND n.last_seen_at IS NOT NULL
                                AND n.last_seen_in_commit IS NOT NULL
                               THEN 1
                               ELSE 0
                           END
                       ) AS stamped
                """,
                project_id="project/uw-ios-mini",
            )
            stamp_record = await stamp_result.single()

            file_result = await session.run(
                """
                MATCH (f:File {
                    project_id: $project_id,
                    path: $file_path
                })
                OPTIONAL MATCH (f)-[:LAST_SEEN_IN]->(run:IngestRun)
                RETURN f.last_seen_in_run_id AS run_id,
                       f.last_seen_in_commit AS commit_sha,
                       f.last_seen_at AS seen_at,
                       f:Deprecated AS deprecated,
                       f.deprecated_at AS deprecated_at,
                       f.deprecated_in_commit AS deprecated_in_commit,
                       count(run) AS rel_count,
                       collect(run.run_id) AS rel_run_ids
                """,
                project_id="project/uw-ios-mini",
                file_path="Sources/UwMiniCore/State/WalletStore.swift",
            )
            file_record = await file_result.single()

            symbol_result = await session.run(
                """
                MATCH (s:Symbol {
                    project_id: $project_id,
                    qualified_name: $qualified_name
                })
                OPTIONAL MATCH (s)-[:LAST_SEEN_IN]->(run:IngestRun)
                RETURN s.last_seen_in_run_id AS run_id,
                       s.last_seen_in_commit AS commit_sha,
                       s.last_seen_at AS seen_at,
                       s:Deprecated AS deprecated,
                       s.deprecated_at AS deprecated_at,
                       s.deprecated_in_commit AS deprecated_in_commit,
                       count(run) AS rel_count,
                       collect(run.run_id) AS rel_run_ids
                """,
                project_id="project/uw-ios-mini",
                qualified_name=_STORE_QNAME,
            )
            symbol_record = await symbol_result.single()

        assert stamp_record is not None
        assert stamp_record["total"] > 0
        assert stamp_record["stamped"] == stamp_record["total"]

        assert file_record is not None
        assert file_record["run_id"] == _RERUN_ID
        assert file_record["commit_sha"] == _HEAD_SHA
        assert file_record["seen_at"] is not None
        assert file_record["deprecated"] is False
        assert file_record["deprecated_at"] is None
        assert file_record["deprecated_in_commit"] is None
        assert file_record["rel_count"] == 1
        assert file_record["rel_run_ids"] == [_RERUN_ID]

        assert symbol_record is not None
        assert symbol_record["run_id"] == _RERUN_ID
        assert symbol_record["commit_sha"] == _HEAD_SHA
        assert symbol_record["seen_at"] is not None
        assert symbol_record["deprecated"] is False
        assert symbol_record["deprecated_at"] is None
        assert symbol_record["deprecated_in_commit"] is None
        assert symbol_record["rel_count"] == 1
        assert symbol_record["rel_run_ids"] == [_RERUN_ID]
