"""Integration tests for dead_symbol_binary_surface."""

from __future__ import annotations

import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from neo4j import AsyncDriver

from palace_mcp.extractors.foundation.identifiers import symbol_id_for
from palace_mcp.extractors.runner import run_extractor
from palace_mcp.extractors.schema import ensure_extractors_schema

PROJECT_SLUG = "dead-symbol-mini"
GROUP_ID = f"project/{PROJECT_SLUG}"
FIXTURE_ROOT = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "dead-symbol-binary-surface-mini-project"
)
_HEAD_SHA = "feedfacefeedfacefeedfacefeedfacefeedface"
_HAS_NEO4J_RUNTIME = (
    bool(os.environ.get("COMPOSE_NEO4J_URI")) or Path("/var/run/docker.sock").exists()
)


def _settings(repo_path: Path) -> MagicMock:
    return MagicMock(
        palace_max_occurrences_total=1000,
        dead_symbol_periphery_report_path=str(
            repo_path / "periphery" / "periphery-3.7.4-swiftpm.json"
        ),
        dead_symbol_periphery_contract_path=str(
            repo_path / "periphery" / "contract.json"
        ),
        dead_symbol_skiplist_path=str(
            repo_path / ".palace" / "dead-symbol-skiplist.yaml"
        ),
    )


@pytest.fixture
async def _project_repo_and_seed(driver: AsyncDriver, tmp_path: Path) -> Path:
    repo = tmp_path / "repos" / PROJECT_SLUG
    shutil.copytree(FIXTURE_ROOT, repo)

    git_dir = repo / ".git"
    git_dir.mkdir()
    (git_dir / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    ref_dir = git_dir / "refs" / "heads"
    ref_dir.mkdir(parents=True)
    (ref_dir / "main").write_text(f"{_HEAD_SHA}\n", encoding="utf-8")

    await ensure_extractors_schema(driver)
    async with driver.session() as session:
        await session.run(
            """
            MERGE (p:Project {slug: $slug})
            SET p.group_id = $group_id,
                p.name = 'DeadSymbolMini',
                p.tags = []
            """,
            slug=PROJECT_SLUG,
            group_id=GROUP_ID,
        )
        await session.run(
            """
            UNWIND $rows AS row
            MERGE (shadow:SymbolOccurrenceShadow {
                symbol_id: row.symbol_id,
                symbol_qualified_name: row.symbol_qualified_name,
                group_id: row.group_id
            })
            SET shadow.language = row.language,
                shadow.importance = 1.0,
                shadow.kind = 'def',
                shadow.tier_weight = 1.0,
                shadow.last_seen_at = $now,
                shadow.schema_version = 1
            """,
            rows=[
                {
                    "symbol_id": symbol_id_for("UnusedHelper"),
                    "symbol_qualified_name": "UnusedHelper",
                    "group_id": GROUP_ID,
                    "language": "swift",
                }
            ],
            now=datetime.now(tz=timezone.utc).isoformat(),
        )
        await session.run(
            """
            UNWIND $rows AS row
            MERGE (symbol:PublicApiSymbol {id: row.id})
            SET symbol += row.props
            """,
            rows=[
                {
                    "id": "public-symbol-1",
                    "props": {
                        "group_id": GROUP_ID,
                        "project": PROJECT_SLUG,
                        "module_name": "DeadSymbolMiniCore",
                        "language": "swift",
                        "commit_sha": _HEAD_SHA,
                        "fqn": "PublicButUnused",
                        "display_name": "PublicButUnused",
                        "kind": "enum",
                        "visibility": "public",
                        "signature": "public enum PublicButUnused",
                        "signature_hash": "sig-public-unused",
                        "source_artifact_path": ".palace/public-api/swift/DeadSymbolMiniCore.swiftinterface",
                        "source_line": 1,
                        "is_generated": False,
                        "is_bridge_exported": False,
                        "bridge_source": None,
                        "symbol_qualified_name": "PublicButUnused",
                        "schema_version": 1,
                    },
                }
            ],
        )
        await session.run(
            """
            MERGE (snapshot:ModuleContractSnapshot {id: $snapshot_id})
            SET snapshot.project = $project,
                snapshot.commit_sha = $commit_sha,
                snapshot.consumer_module_name = $consumer_module_name,
                snapshot.producer_module_name = $producer_module_name,
                snapshot.language = 'swift'
            WITH snapshot
            MATCH (symbol:PublicApiSymbol {id: $public_symbol_id})
            MERGE (snapshot)-[rel:CONSUMES_PUBLIC_SYMBOL]->(symbol)
            SET rel.contract_snapshot_id = $snapshot_id,
                rel.consumer_module_name = $consumer_module_name,
                rel.producer_module_name = $producer_module_name,
                rel.commit_sha = $commit_sha,
                rel.use_count = 2,
                rel.evidence_paths_sample = ['Sources/DeadSymbolMiniApp/main.swift']
            """,
            snapshot_id="contract-snapshot-1",
            project=PROJECT_SLUG,
            commit_sha=_HEAD_SHA,
            consumer_module_name="DeadSymbolMiniApp",
            producer_module_name="DeadSymbolMiniCore",
            public_symbol_id="public-symbol-1",
        )

    return tmp_path / "repos"


async def _run_dead_symbol_extractor(
    *,
    driver: AsyncDriver,
    graphiti_mock: MagicMock,
    repos_root: Path,
) -> dict[str, object]:
    repo_path = repos_root / PROJECT_SLUG
    with (
        patch("palace_mcp.extractors.runner.REPOS_ROOT", repos_root),
        patch("palace_mcp.mcp_server.get_driver", return_value=driver),
        patch("palace_mcp.mcp_server.get_settings", return_value=_settings(repo_path)),
    ):
        return await run_extractor(
            name="dead_symbol_binary_surface",
            project=PROJECT_SLUG,
            driver=driver,
            graphiti=graphiti_mock,
        )


async def _update_contract_use_count(driver: AsyncDriver, *, use_count: int) -> None:
    async with driver.session() as session:
        await session.run(
            """
            MATCH (:ModuleContractSnapshot {id: 'contract-snapshot-1'})
                  -[rel:CONSUMES_PUBLIC_SYMBOL]->
                  (:PublicApiSymbol {id: 'public-symbol-1'})
            SET rel.use_count = $use_count
            """,
            use_count=use_count,
        )


@pytest.mark.integration
@pytest.mark.skipif(
    not _HAS_NEO4J_RUNTIME,
    reason="requires Docker socket or COMPOSE_NEO4J_URI for Neo4j integration",
)
async def test_dead_symbol_run_writes_candidates_binary_surfaces_and_edges(
    driver: AsyncDriver,
    graphiti_mock: MagicMock,
    _project_repo_and_seed: Path,
) -> None:
    result = await _run_dead_symbol_extractor(
        driver=driver,
        graphiti_mock=graphiti_mock,
        repos_root=_project_repo_and_seed,
    )

    assert result["ok"] is True
    assert result["extractor"] == "dead_symbol_binary_surface"
    assert result["project"] == PROJECT_SLUG
    assert result["success"] is True

    async with driver.session() as session:
        candidate_result = await session.run(
            "MATCH (c:DeadSymbolCandidate {project: $project}) RETURN count(c) AS count",
            project=PROJECT_SLUG,
        )
        candidate_row = await candidate_result.single()

        shadow_edge_result = await session.run(
            """
            MATCH (:DeadSymbolCandidate {project: $project})
                -[:BACKED_BY_SYMBOL]->(:SymbolOccurrenceShadow)
            RETURN count(*) AS count
            """,
            project=PROJECT_SLUG,
        )
        shadow_edge_row = await shadow_edge_result.single()

        public_edge_result = await session.run(
            """
            MATCH (:DeadSymbolCandidate {project: $project})
                -[:BACKED_BY_PUBLIC_API]->(:PublicApiSymbol)
            RETURN count(*) AS count
            """,
            project=PROJECT_SLUG,
        )
        public_edge_row = await public_edge_result.single()

        binary_surface_result = await session.run(
            """
            MATCH (:DeadSymbolCandidate {project: $project})
                -[:HAS_BINARY_SURFACE]->(:BinarySurfaceRecord)
            RETURN count(*) AS count
            """,
            project=PROJECT_SLUG,
        )
        binary_surface_row = await binary_surface_result.single()

    assert candidate_row is not None and candidate_row["count"] == 3
    assert shadow_edge_row is not None and shadow_edge_row["count"] == 1
    assert public_edge_row is not None and public_edge_row["count"] == 1
    assert binary_surface_row is not None and binary_surface_row["count"] == 1


@pytest.mark.integration
@pytest.mark.skipif(
    not _HAS_NEO4J_RUNTIME,
    reason="requires Docker socket or COMPOSE_NEO4J_URI for Neo4j integration",
)
async def test_dead_symbol_run_is_idempotent_on_real_neo4j(
    driver: AsyncDriver,
    graphiti_mock: MagicMock,
    _project_repo_and_seed: Path,
) -> None:
    first = await _run_dead_symbol_extractor(
        driver=driver,
        graphiti_mock=graphiti_mock,
        repos_root=_project_repo_and_seed,
    )
    second = await _run_dead_symbol_extractor(
        driver=driver,
        graphiti_mock=graphiti_mock,
        repos_root=_project_repo_and_seed,
    )

    assert first["ok"] is True
    assert first["success"] is True
    assert first["nodes_written"] == 4
    assert first["edges_written"] == 4
    assert second["ok"] is True
    assert second["success"] is True
    assert second["nodes_written"] == 0
    assert second["edges_written"] == 0


@pytest.mark.integration
@pytest.mark.skipif(
    not _HAS_NEO4J_RUNTIME,
    reason="requires Docker socket or COMPOSE_NEO4J_URI for Neo4j integration",
)
async def test_public_open_symbols_never_unused_candidates(
    driver: AsyncDriver,
    graphiti_mock: MagicMock,
    _project_repo_and_seed: Path,
) -> None:
    result = await _run_dead_symbol_extractor(
        driver=driver,
        graphiti_mock=graphiti_mock,
        repos_root=_project_repo_and_seed,
    )
    assert result["ok"] is True
    assert result["success"] is True

    async with driver.session() as session:
        state_result = await session.run(
            """
            MATCH (c:DeadSymbolCandidate {project: $project, display_name: 'PublicButUnused'})
            RETURN c.candidate_state AS state, c.skip_reason AS skip_reason
            """,
            project=PROJECT_SLUG,
        )
        state_row = await state_result.single()

        unused_result = await session.run(
            """
            MATCH (c:DeadSymbolCandidate {
                project: $project,
                display_name: 'PublicButUnused',
                candidate_state: 'unused_candidate'
            })
            RETURN count(c) AS count
            """,
            project=PROJECT_SLUG,
        )
        unused_row = await unused_result.single()

    assert state_row is not None
    assert state_row["state"] == "retained_public_api"
    assert state_row["skip_reason"] == "cross_module_contract_consumed"
    assert unused_row is not None and unused_row["count"] == 0


@pytest.mark.integration
@pytest.mark.skipif(
    not _HAS_NEO4J_RUNTIME,
    reason="requires Docker socket or COMPOSE_NEO4J_URI for Neo4j integration",
)
async def test_dead_symbol_third_run_after_upstream_change_updates_expected_rows(
    driver: AsyncDriver,
    graphiti_mock: MagicMock,
    _project_repo_and_seed: Path,
) -> None:
    await _run_dead_symbol_extractor(
        driver=driver,
        graphiti_mock=graphiti_mock,
        repos_root=_project_repo_and_seed,
    )
    await _run_dead_symbol_extractor(
        driver=driver,
        graphiti_mock=graphiti_mock,
        repos_root=_project_repo_and_seed,
    )
    await _update_contract_use_count(driver, use_count=5)

    third = await _run_dead_symbol_extractor(
        driver=driver,
        graphiti_mock=graphiti_mock,
        repos_root=_project_repo_and_seed,
    )

    assert third["ok"] is True
    assert third["success"] is True

    async with driver.session() as session:
        rel_result = await session.run(
            """
            MATCH (:DeadSymbolCandidate {project: $project, display_name: 'PublicButUnused'})
                  -[rel:BLOCKED_BY_CONTRACT_SYMBOL]->
                  (:PublicApiSymbol {id: 'public-symbol-1'})
            RETURN rel.use_count AS use_count
            """,
            project=PROJECT_SLUG,
        )
        rel_row = await rel_result.single()

    assert rel_row is not None
    assert rel_row["use_count"] == 5


@pytest.mark.integration
@pytest.mark.skipif(
    not _HAS_NEO4J_RUNTIME,
    reason="requires Docker socket or COMPOSE_NEO4J_URI for Neo4j integration",
)
async def test_contract_blocked_symbols_never_unused_candidates(
    driver: AsyncDriver,
    graphiti_mock: MagicMock,
    _project_repo_and_seed: Path,
) -> None:
    result = await _run_dead_symbol_extractor(
        driver=driver,
        graphiti_mock=graphiti_mock,
        repos_root=_project_repo_and_seed,
    )
    assert result["ok"] is True
    assert result["success"] is True

    async with driver.session() as session:
        blocked_row_result = await session.run(
            """
            MATCH (c:DeadSymbolCandidate {project: $project, display_name: 'PublicButUnused'})
                  -[rel:BLOCKED_BY_CONTRACT_SYMBOL]->
                  (:PublicApiSymbol {id: 'public-symbol-1'})
            RETURN c.candidate_state AS state,
                   c.skip_reason AS skip_reason,
                   rel.contract_snapshot_id AS contract_snapshot_id,
                   rel.consumer_module_name AS consumer_module_name,
                   rel.producer_module_name AS producer_module_name
            """,
            project=PROJECT_SLUG,
        )
        blocked_row = await blocked_row_result.single()

    assert blocked_row is not None
    assert blocked_row["state"] == "retained_public_api"
    assert blocked_row["skip_reason"] == "cross_module_contract_consumed"
    assert blocked_row["contract_snapshot_id"] == "contract-snapshot-1"
    assert blocked_row["consumer_module_name"] == "DeadSymbolMiniApp"
    assert blocked_row["producer_module_name"] == "DeadSymbolMiniCore"


@pytest.mark.integration
@pytest.mark.skipif(
    not _HAS_NEO4J_RUNTIME,
    reason="requires Docker socket or COMPOSE_NEO4J_URI for Neo4j integration",
)
async def test_public_and_contract_blocked_symbol_has_both_guards(
    driver: AsyncDriver,
    graphiti_mock: MagicMock,
    _project_repo_and_seed: Path,
) -> None:
    result = await _run_dead_symbol_extractor(
        driver=driver,
        graphiti_mock=graphiti_mock,
        repos_root=_project_repo_and_seed,
    )
    assert result["ok"] is True
    assert result["success"] is True

    async with driver.session() as session:
        guard_result = await session.run(
            """
            MATCH (c:DeadSymbolCandidate {project: $project, display_name: 'PublicButUnused'})
            RETURN
                EXISTS {
                    MATCH (c)-[:HAS_BINARY_SURFACE]->(:BinarySurfaceRecord)
                } AS has_binary_surface,
                EXISTS {
                    MATCH (c)-[:BLOCKED_BY_CONTRACT_SYMBOL]->(:PublicApiSymbol {id: 'public-symbol-1'})
                } AS has_contract_blocker,
                c.candidate_state AS state,
                c.skip_reason AS skip_reason
            """,
            project=PROJECT_SLUG,
        )
        guard_row = await guard_result.single()

    assert guard_row is not None
    assert guard_row["has_binary_surface"] is True
    assert guard_row["has_contract_blocker"] is True
    assert guard_row["state"] == "retained_public_api"
    assert guard_row["skip_reason"] == "cross_module_contract_consumed"


@pytest.mark.integration
@pytest.mark.skipif(
    not _HAS_NEO4J_RUNTIME,
    reason="requires Docker socket or COMPOSE_NEO4J_URI for Neo4j integration",
)
async def test_generated_skiplist_entries_are_skipped(
    driver: AsyncDriver,
    graphiti_mock: MagicMock,
    _project_repo_and_seed: Path,
) -> None:
    result = await _run_dead_symbol_extractor(
        driver=driver,
        graphiti_mock=graphiti_mock,
        repos_root=_project_repo_and_seed,
    )
    assert result["ok"] is True
    assert result["success"] is True

    async with driver.session() as session:
        skip_row_result = await session.run(
            """
            MATCH (c:DeadSymbolCandidate {project: $project, display_name: 'AutoGeneratedToken'})
            RETURN c.candidate_state AS state, c.skip_reason AS skip_reason
            """,
            project=PROJECT_SLUG,
        )
        skip_row = await skip_row_result.single()

        unused_result = await session.run(
            """
            MATCH (c:DeadSymbolCandidate {
                project: $project,
                display_name: 'AutoGeneratedToken',
                candidate_state: 'unused_candidate'
            })
            RETURN count(c) AS count
            """,
            project=PROJECT_SLUG,
        )
        unused_row = await unused_result.single()

    assert skip_row is not None
    assert skip_row["state"] == "skipped"
    assert skip_row["skip_reason"] == "generated_code"
    assert unused_row is not None and unused_row["count"] == 0


@pytest.mark.integration
@pytest.mark.skipif(
    not _HAS_NEO4J_RUNTIME,
    reason="requires Docker socket or COMPOSE_NEO4J_URI for Neo4j integration",
)
async def test_cross_extractor_public_api_surface_regression(
    driver: AsyncDriver,
    graphiti_mock: MagicMock,
    _project_repo_and_seed: Path,
) -> None:
    result = await _run_dead_symbol_extractor(
        driver=driver,
        graphiti_mock=graphiti_mock,
        repos_root=_project_repo_and_seed,
    )
    assert result["ok"] is True
    assert result["success"] is True

    async with driver.session() as session:
        public_api_result = await session.run(
            """
            MATCH (symbol:PublicApiSymbol {id: 'public-symbol-1'})
            RETURN
                symbol.visibility AS visibility,
                symbol.symbol_qualified_name AS symbol_qualified_name,
                count(symbol) AS count
            """
        )
        public_api_row = await public_api_result.single()

        backing_result = await session.run(
            """
            MATCH (:DeadSymbolCandidate {project: $project, display_name: 'PublicButUnused'})
                  -[:BACKED_BY_PUBLIC_API]->
                  (symbol:PublicApiSymbol {id: 'public-symbol-1'})
            RETURN count(symbol) AS count
            """,
            project=PROJECT_SLUG,
        )
        backing_row = await backing_result.single()

    assert public_api_row is not None
    assert public_api_row["count"] == 1
    assert public_api_row["visibility"] == "public"
    assert public_api_row["symbol_qualified_name"] == "PublicButUnused"
    assert backing_row is not None and backing_row["count"] == 1


@pytest.mark.integration
@pytest.mark.skipif(
    not _HAS_NEO4J_RUNTIME,
    reason="requires Docker socket or COMPOSE_NEO4J_URI for Neo4j integration",
)
async def test_cross_extractor_cross_module_contract_regression(
    driver: AsyncDriver,
    graphiti_mock: MagicMock,
    _project_repo_and_seed: Path,
) -> None:
    result = await _run_dead_symbol_extractor(
        driver=driver,
        graphiti_mock=graphiti_mock,
        repos_root=_project_repo_and_seed,
    )
    assert result["ok"] is True
    assert result["success"] is True

    async with driver.session() as session:
        contract_result = await session.run(
            """
            MATCH (snapshot:ModuleContractSnapshot {id: 'contract-snapshot-1'})
                  -[rel:CONSUMES_PUBLIC_SYMBOL]->
                  (:PublicApiSymbol {id: 'public-symbol-1'})
            RETURN count(rel) AS count, rel.use_count AS use_count
            """
        )
        contract_row = await contract_result.single()

        copied_result = await session.run(
            """
            MATCH (:DeadSymbolCandidate {project: $project, display_name: 'PublicButUnused'})
                  -[rel:BLOCKED_BY_CONTRACT_SYMBOL]->
                  (:PublicApiSymbol {id: 'public-symbol-1'})
            RETURN count(rel) AS count, rel.use_count AS use_count
            """,
            project=PROJECT_SLUG,
        )
        copied_row = await copied_result.single()

    assert contract_row is not None
    assert contract_row["count"] == 1
    assert contract_row["use_count"] == 2
    assert copied_row is not None
    assert copied_row["count"] == 1
    assert copied_row["use_count"] == 2
