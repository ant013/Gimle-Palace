"""Integration tests for the cross_module_contract extractor."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from neo4j import AsyncDriver

from palace_mcp.config import Settings
from palace_mcp.extractors.foundation.identifiers import symbol_id_for
from palace_mcp.extractors.foundation.models import (
    Language,
    SymbolKind,
    SymbolOccurrence,
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

    await _seed_occurrences(tantivy_dir)

    with (
        patch("palace_mcp.extractors.runner.REPOS_ROOT", _project_and_repo),
        patch("palace_mcp.mcp_server.get_driver", return_value=driver),
        patch("palace_mcp.mcp_server.get_settings", return_value=settings),
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
    assert result["nodes_written"] >= 1
    assert result["edges_written"] >= 2

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
                   rel.match_symbol_id AS match_symbol_id,
                   rel.evidence_paths_sample AS evidence_paths_sample,
                   rel.first_seen_path AS first_seen_path
            ORDER BY symbol.fqn
            """,
            project="contract-mini",
        )
        edges = await edge_result.data()

        invalid_target_result = await session.run(
            """
            MATCH (:ModuleContractSnapshot)-[r:CONSUMES_PUBLIC_SYMBOL]->(s)
            WHERE NOT s:PublicApiSymbol
            RETURN count(r) AS count
            """
        )
        invalid_target_row = await invalid_target_result.single()

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
            "commit_sha": _HEAD_SHA,
            "symbol_count": 1,
            "use_count": 1,
            "file_count": 1,
            "skipped_symbol_count": 4,
        }
    ]
    assert edges == [
        {
            "consumer_module_name": "ConsumerApp",
            "fqn": "Wallet.balance()",
            "match_symbol_id": symbol_id_for("Wallet.balance()"),
            "evidence_paths_sample": [
                "ConsumerApp/Sources/ConsumerApp/WalletFeature.swift"
            ],
            "first_seen_path": "ConsumerApp/Sources/ConsumerApp/WalletFeature.swift",
        }
    ]
    assert invalid_target_row is not None and invalid_target_row["count"] == 0
    assert cross_commit_row is not None and cross_commit_row["count"] == 0
    assert same_module_row is not None and same_module_row["count"] == 0
    assert package_row is not None and package_row["count"] == 0


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
                    doc_key=(
                        f"{symbol_id}:{row['file_path']}:{row['line']}:{row['col_start']}"
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
