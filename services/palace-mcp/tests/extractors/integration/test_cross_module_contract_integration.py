"""Integration tests for the cross_module_contract extractor."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from neo4j import AsyncDriver

from palace_mcp.config import Settings
from palace_mcp.extractors import registry
from palace_mcp.extractors.cross_module_contract import CrossModuleContractExtractor
from palace_mcp.extractors.foundation.identifiers import symbol_id_for
from palace_mcp.extractors.foundation.models import (
    Language,
    PublicApiArtifactKind,
    PublicApiSurface,
    PublicApiSymbol,
    PublicApiSymbolKind,
    PublicApiVisibility,
    SymbolKind,
    SymbolOccurrence,
    build_symbol_occurrence_doc_key,
)
from palace_mcp.extractors.foundation.tantivy_bridge import TantivyBridge
from palace_mcp.extractors.runner import run_extractor
from palace_mcp.extractors.schema import ensure_extractors_schema

FIXTURE_ROOT = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "cross-module-contract-mini-project"
)
_HEAD_SHA = "feedfacefeedfacefeedfacefeedfacefeedface"
_OLD_SHA = "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef"


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
            slug="contract-mini",
            name="ContractMini",
        )
        await session.run(
            """
            CREATE (consumer:Module {group_id: $group_id, name: 'ConsumerApp'})
            CREATE (producer:Module {group_id: $group_id, name: 'ProducerKit'})
            CREATE (consumer_file:File {
                group_id: $group_id,
                path: 'ConsumerApp/Sources/ConsumerApp/WalletFeature.swift'
            })
            CREATE (producer_file:File {
                group_id: $group_id,
                path: 'ProducerKit/Sources/ProducerKit/InternalUse.swift'
            })
            CREATE (consumer)-[:CONTAINS]->(consumer_file)
            CREATE (producer)-[:CONTAINS]->(producer_file)
            """,
            group_id="project/contract-mini",
        )

    repo = tmp_path / "repos" / "contract-mini"
    shutil.copytree(FIXTURE_ROOT, repo)
    git_dir = repo / ".git"
    git_dir.mkdir()
    (git_dir / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    ref_dir = git_dir / "refs" / "heads"
    ref_dir.mkdir(parents=True)
    (ref_dir / "main").write_text(f"{_HEAD_SHA}\n", encoding="utf-8")
    return tmp_path / "repos"


@pytest.mark.asyncio
async def test_cross_module_contract_run_writes_snapshot_and_symbol_edges(
    driver: AsyncDriver,
    graphiti_mock: MagicMock,
    _project_and_repo: Path,
    tmp_path: Path,
) -> None:
    await ensure_extractors_schema(driver)
    tantivy_dir = tmp_path / "tantivy"
    tantivy_dir.mkdir()
    settings = Settings(
        neo4j_password="password",
        openai_api_key="test-key",
        palace_tantivy_index_path=str(tantivy_dir),
        palace_tantivy_heap_mb=50,
    )

    with (
        patch("palace_mcp.extractors.runner.REPOS_ROOT", _project_and_repo),
        patch("palace_mcp.mcp_server.get_driver", return_value=driver),
        patch("palace_mcp.mcp_server.get_settings", return_value=settings),
    ):
        public_api_result = await run_extractor(
            name="public_api_surface",
            project="contract-mini",
            driver=driver,
            graphiti=graphiti_mock,
        )
    assert public_api_result["ok"] is True

    await _seed_previous_public_api_surface(driver)
    await _seed_occurrences(tantivy_dir)

    with (
        patch("palace_mcp.extractors.runner.REPOS_ROOT", _project_and_repo),
        patch("palace_mcp.mcp_server.get_driver", return_value=driver),
        patch("palace_mcp.mcp_server.get_settings", return_value=settings),
        # Force a fresh extractor instance so this integration test does not
        # inherit mutated registry state from earlier tests in the full suite.
        patch.dict(
            registry.EXTRACTORS,
            {"cross_module_contract": CrossModuleContractExtractor()},
        ),
    ):
        result = await run_extractor(
            name="cross_module_contract",
            project="contract-mini",
            driver=driver,
            graphiti=graphiti_mock,
        )

    assert result["ok"] is True
    assert result["extractor"] == "cross_module_contract"
    assert result["success"] is True
    assert result["nodes_written"] >= 3
    assert result["edges_written"] >= 11

    async with driver.session() as session:
        duplicate_result = await session.run(
            "MATCH (n:ContractSymbol) RETURN count(n) AS count"
        )
        duplicate_row = await duplicate_result.single()

        snapshot_result = await session.run(
            """
            MATCH (snap:ModuleContractSnapshot {project: $project})
            RETURN snap.consumer_module_name AS consumer_module_name,
                   snap.producer_module_name AS producer_module_name,
                   snap.commit_sha AS commit_sha,
                   snap.symbol_count AS symbol_count,
                   snap.use_count AS use_count,
                   snap.file_count AS file_count,
                   snap.skipped_symbol_count AS skipped_symbol_count
            ORDER BY snap.commit_sha
            """,
            project="contract-mini",
        )
        snapshots = await snapshot_result.data()

        edge_result = await session.run(
            """
            MATCH (snap:ModuleContractSnapshot {project: $project})
                  -[rel:CONSUMES_PUBLIC_SYMBOL]->(symbol:PublicApiSymbol)
            RETURN snap.consumer_module_name AS consumer_module_name,
                   symbol.fqn AS fqn,
                   symbol.commit_sha AS symbol_commit_sha,
                   rel.match_symbol_id AS match_symbol_id,
                   rel.evidence_paths_sample AS evidence_paths_sample,
                   rel.first_seen_path AS first_seen_path
            ORDER BY snap.commit_sha, symbol.fqn
            """,
            project="contract-mini",
        )
        edges = await edge_result.data()

        delta_result = await session.run(
            """
            MATCH (delta:ModuleContractDelta {project: $project})
                  -[:DELTA_FROM]->(from_snapshot:ModuleContractSnapshot)
            MATCH (delta)-[:DELTA_TO]->(to_snapshot:ModuleContractSnapshot)
            RETURN delta.from_commit_sha AS from_commit_sha,
                   delta.to_commit_sha AS to_commit_sha,
                   delta.removed_consumed_symbol_count AS removed_consumed_symbol_count,
                   delta.signature_changed_consumed_symbol_count AS signature_changed_consumed_symbol_count,
                   delta.added_consumed_symbol_count AS added_consumed_symbol_count,
                   delta.affected_use_count AS affected_use_count,
                   from_snapshot.commit_sha AS from_snapshot_commit_sha,
                   to_snapshot.commit_sha AS to_snapshot_commit_sha
            """,
            project="contract-mini",
        )
        deltas = await delta_result.data()

        affected_result = await session.run(
            """
            MATCH (delta:ModuleContractDelta {project: $project})
                  -[rel:AFFECTS_PUBLIC_SYMBOL]->(symbol:PublicApiSymbol)
            RETURN rel.change_kind AS change_kind,
                   rel.affected_use_count AS affected_use_count,
                   symbol.fqn AS fqn,
                   symbol.commit_sha AS symbol_commit_sha
            ORDER BY symbol.fqn
            """,
            project="contract-mini",
        )
        affected_symbols = await affected_result.data()

        invalid_target_result = await session.run(
            """
            MATCH (:ModuleContractSnapshot)-[r:CONSUMES_PUBLIC_SYMBOL]->(s)
            WHERE NOT s:PublicApiSymbol
            RETURN count(r) AS count
            """
        )
        invalid_target_row = await invalid_target_result.single()

        invalid_delta_target_result = await session.run(
            """
            MATCH (:ModuleContractDelta)-[r:AFFECTS_PUBLIC_SYMBOL]->(s)
            WHERE NOT s:PublicApiSymbol
            RETURN count(r) AS count
            """
        )
        invalid_delta_target_row = await invalid_delta_target_result.single()

        cross_commit_result = await session.run(
            """
            MATCH (snap:ModuleContractSnapshot)-[r:CONSUMES_PUBLIC_SYMBOL]->(sym:PublicApiSymbol)
            WHERE snap.commit_sha <> sym.commit_sha
            RETURN count(r) AS count
            """
        )
        cross_commit_row = await cross_commit_result.single()

        same_module_result = await session.run(
            """
            MATCH (snap:ModuleContractSnapshot)
            WHERE snap.consumer_module_name = snap.producer_module_name
            RETURN count(snap) AS count
            """
        )
        same_module_row = await same_module_result.single()

        package_result = await session.run(
            """
            MATCH (:ModuleContractSnapshot {project: $project})
                  -[:CONSUMES_PUBLIC_SYMBOL]->(symbol:PublicApiSymbol {visibility: 'package'})
            RETURN count(symbol) AS count
            """,
            project="contract-mini",
        )
        package_row = await package_result.single()

    assert duplicate_row is not None and duplicate_row["count"] == 0
    assert snapshots == [
        {
            "consumer_module_name": "ConsumerApp",
            "producer_module_name": "ProducerKit",
            "commit_sha": _OLD_SHA,
            "symbol_count": 2,
            "use_count": 2,
            "file_count": 1,
            "skipped_symbol_count": 1,
        },
        {
            "consumer_module_name": "ConsumerApp",
            "producer_module_name": "ProducerKit",
            "commit_sha": _HEAD_SHA,
            "symbol_count": 2,
            "use_count": 2,
            "file_count": 1,
            "skipped_symbol_count": 3,
        },
    ]
    assert edges == [
        {
            "consumer_module_name": "ConsumerApp",
            "fqn": "Wallet.balance()",
            "symbol_commit_sha": _OLD_SHA,
            "match_symbol_id": symbol_id_for("Wallet.balance()"),
            "evidence_paths_sample": [
                "ConsumerApp/Sources/ConsumerApp/WalletFeature.swift"
            ],
            "first_seen_path": "ConsumerApp/Sources/ConsumerApp/WalletFeature.swift",
        },
        {
            "consumer_module_name": "ConsumerApp",
            "fqn": "staleExport()",
            "symbol_commit_sha": _OLD_SHA,
            "match_symbol_id": symbol_id_for("staleExport()"),
            "evidence_paths_sample": [
                "ConsumerApp/Sources/ConsumerApp/WalletFeature.swift"
            ],
            "first_seen_path": "ConsumerApp/Sources/ConsumerApp/WalletFeature.swift",
        },
        {
            "consumer_module_name": "ConsumerApp",
            "fqn": "Wallet.balance()",
            "symbol_commit_sha": _HEAD_SHA,
            "match_symbol_id": symbol_id_for("Wallet.balance()"),
            "evidence_paths_sample": [
                "ConsumerApp/Sources/ConsumerApp/WalletFeature.swift"
            ],
            "first_seen_path": "ConsumerApp/Sources/ConsumerApp/WalletFeature.swift",
        },
        {
            "consumer_module_name": "ConsumerApp",
            "fqn": "Wallet.init(id: Swift.String)",
            "symbol_commit_sha": _HEAD_SHA,
            "match_symbol_id": symbol_id_for("Wallet.init(id: Swift.String)"),
            "evidence_paths_sample": [
                "ConsumerApp/Sources/ConsumerApp/WalletFeature.swift"
            ],
            "first_seen_path": "ConsumerApp/Sources/ConsumerApp/WalletFeature.swift",
        },
    ]
    assert deltas == [
        {
            "from_commit_sha": _OLD_SHA,
            "to_commit_sha": _HEAD_SHA,
            "removed_consumed_symbol_count": 1,
            "signature_changed_consumed_symbol_count": 1,
            "added_consumed_symbol_count": 1,
            "affected_use_count": 3,
            "from_snapshot_commit_sha": _OLD_SHA,
            "to_snapshot_commit_sha": _HEAD_SHA,
        }
    ]
    assert affected_symbols == [
        {
            "change_kind": "signature_changed",
            "affected_use_count": 1,
            "fqn": "Wallet.balance()",
            "symbol_commit_sha": _HEAD_SHA,
        },
        {
            "change_kind": "added",
            "affected_use_count": 1,
            "fqn": "Wallet.init(id: Swift.String)",
            "symbol_commit_sha": _HEAD_SHA,
        },
        {
            "change_kind": "removed",
            "affected_use_count": 1,
            "fqn": "staleExport()",
            "symbol_commit_sha": _OLD_SHA,
        },
    ]
    assert invalid_target_row is not None and invalid_target_row["count"] == 0
    assert (
        invalid_delta_target_row is not None and invalid_delta_target_row["count"] == 0
    )
    assert cross_commit_row is not None and cross_commit_row["count"] == 0
    assert same_module_row is not None and same_module_row["count"] == 0
    assert package_row is not None and package_row["count"] == 0


@pytest.mark.asyncio
async def test_cross_module_contract_skips_when_public_api_surface_is_missing(
    driver: AsyncDriver,
    graphiti_mock: MagicMock,
    _project_and_repo: Path,
    tmp_path: Path,
) -> None:
    await ensure_extractors_schema(driver)
    tantivy_dir = tmp_path / "tantivy-empty"
    tantivy_dir.mkdir()
    settings = Settings(
        neo4j_password="password",
        openai_api_key="test-key",
        palace_tantivy_index_path=str(tantivy_dir),
        palace_tantivy_heap_mb=50,
    )

    with (
        patch("palace_mcp.extractors.runner.REPOS_ROOT", _project_and_repo),
        patch("palace_mcp.mcp_server.get_driver", return_value=driver),
        patch("palace_mcp.mcp_server.get_settings", return_value=settings),
        patch.dict(
            registry.EXTRACTORS,
            {"cross_module_contract": CrossModuleContractExtractor()},
        ),
    ):
        result = await run_extractor(
            name="cross_module_contract",
            project="contract-mini",
            driver=driver,
            graphiti=graphiti_mock,
        )

    assert result["ok"] is True
    assert result["success"] is True
    assert result["outcome"] == "skipped"
    assert "PublicApiSurface/PublicApiSymbol" in (result.get("message") or "")


async def _seed_occurrences(tantivy_dir: Path) -> None:
    fixture_path = (
        FIXTURE_ROOT / ".palace" / "cross-module-contract" / "occurrences.json"
    )
    rows = json.loads(fixture_path.read_text(encoding="utf-8"))
    async with TantivyBridge(tantivy_dir, heap_size_mb=50) as bridge:
        for row in rows:
            qname = row["symbol_qualified_name"]
            symbol_id = symbol_id_for(qname)
            await bridge.add_or_replace_async(
                occ=SymbolOccurrence(
                    doc_key=build_symbol_occurrence_doc_key(
                        symbol_id=symbol_id,
                        file_path=row["file_path"],
                        line=row["line"],
                        col_start=row["col_start"],
                        commit_sha=row["commit_sha"],
                    ),
                    symbol_id=symbol_id,
                    symbol_qualified_name=qname,
                    kind=SymbolKind.USE,
                    language=Language.SWIFT,
                    file_path=row["file_path"],
                    line=row["line"],
                    col_start=row["col_start"],
                    col_end=row["col_end"],
                    importance=1.0,
                    commit_sha=row["commit_sha"],
                    ingest_run_id="cross-module-seed",
                ),
                phase=row["phase"],
            )


async def _seed_previous_public_api_surface(driver: AsyncDriver) -> None:
    surface = PublicApiSurface(
        id="surface-producerkit-old",
        group_id="project/contract-mini",
        project="contract-mini",
        module_name="ProducerKit",
        language=Language.SWIFT,
        commit_sha=_OLD_SHA,
        artifact_path=".palace/public-api/swift/ProducerKit.swiftinterface",
        artifact_kind=PublicApiArtifactKind.SWIFTINTERFACE,
        tool_name="swiftc",
        tool_version="6.2.4",
    )
    symbols = [
        PublicApiSymbol(
            id="symbol-wallet-old",
            group_id="project/contract-mini",
            project="contract-mini",
            module_name="ProducerKit",
            language=Language.SWIFT,
            commit_sha=_OLD_SHA,
            fqn="Wallet",
            display_name="Wallet",
            kind=PublicApiSymbolKind.STRUCT,
            visibility=PublicApiVisibility.PUBLIC,
            signature="public struct Wallet",
            signature_hash="sig-wallet-old",
            source_artifact_path=surface.artifact_path,
            source_line=5,
            symbol_qualified_name="Wallet",
        ),
        PublicApiSymbol(
            id="symbol-wallet-balance-old",
            group_id="project/contract-mini",
            project="contract-mini",
            module_name="ProducerKit",
            language=Language.SWIFT,
            commit_sha=_OLD_SHA,
            fqn="Wallet.balance()",
            display_name="Wallet.balance()",
            kind=PublicApiSymbolKind.METHOD,
            visibility=PublicApiVisibility.PUBLIC,
            signature="public func balance() -> Swift.String",
            signature_hash="sig-wallet-balance-old",
            source_artifact_path=surface.artifact_path,
            source_line=7,
            symbol_qualified_name="Wallet.balance()",
        ),
        PublicApiSymbol(
            id="symbol-stale-export-old",
            group_id="project/contract-mini",
            project="contract-mini",
            module_name="ProducerKit",
            language=Language.SWIFT,
            commit_sha=_OLD_SHA,
            fqn="staleExport()",
            display_name="staleExport()",
            kind=PublicApiSymbolKind.FUNCTION,
            visibility=PublicApiVisibility.PUBLIC,
            signature="public func staleExport() -> Swift.String",
            signature_hash="sig-stale-export-old",
            source_artifact_path=surface.artifact_path,
            source_line=10,
            symbol_qualified_name="staleExport()",
        ),
    ]

    async with driver.session() as session:
        await session.run(
            """
            MERGE (surface:PublicApiSurface {id: $surface_id})
            SET surface += $surface_props
            """,
            surface_id=surface.id,
            surface_props=surface.model_dump(mode="json", exclude_none=True),
        )
        for symbol in symbols:
            await session.run(
                """
                MATCH (surface:PublicApiSurface {id: $surface_id})
                MERGE (symbol:PublicApiSymbol {id: $symbol_id})
                SET symbol += $symbol_props
                MERGE (surface)-[:EXPORTS]->(symbol)
                """,
                surface_id=surface.id,
                symbol_id=symbol.id,
                symbol_props=symbol.model_dump(mode="json", exclude_none=True),
            )
