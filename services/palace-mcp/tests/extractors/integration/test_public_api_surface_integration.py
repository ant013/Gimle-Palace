"""Integration tests for the public_api_surface extractor."""

from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from neo4j import AsyncDriver

from palace_mcp.extractors.runner import run_extractor
from palace_mcp.extractors.schema import ensure_extractors_schema

FIXTURE_ROOT = (
    Path(__file__).resolve().parents[1] / "fixtures" / "public-api-surface-mini-project"
)
_HEAD_SHA = "cafebabecafebabecafebabecafebabecafebabe"


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
            slug="public-api-mini",
            name="PublicApiMini",
        )
        await session.run(
            """
            UNWIND $rows AS row
            MERGE (s:SymbolOccurrenceShadow {
                symbol_id: row.symbol_id,
                symbol_qualified_name: row.symbol_qualified_name,
                group_id: row.group_id
            })
            SET s.importance = 1.0,
                s.kind = 'def',
                s.tier_weight = 1.0,
                s.last_seen_at = $now,
                s.schema_version = 1
            """,
            rows=[
                {
                    "symbol_id": 101,
                    "symbol_qualified_name": "com.example.wallet.Wallet",
                    "group_id": "project/public-api-mini",
                },
                {
                    "symbol_id": 102,
                    "symbol_qualified_name": "Wallet.balance()",
                    "group_id": "project/public-api-mini",
                },
            ],
            now=datetime.now(tz=timezone.utc).isoformat(),
        )

    repo = tmp_path / "repos" / "public-api-mini"
    shutil.copytree(FIXTURE_ROOT, repo)
    git_dir = repo / ".git"
    git_dir.mkdir()
    (git_dir / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    ref_dir = git_dir / "refs" / "heads"
    ref_dir.mkdir(parents=True)
    (ref_dir / "main").write_text(f"{_HEAD_SHA}\n", encoding="utf-8")
    return tmp_path / "repos"


@pytest.mark.asyncio
async def test_public_api_surface_run_writes_surfaces_symbols_and_backing_edges(
    driver: AsyncDriver,
    graphiti_mock: MagicMock,
    _project_and_repo: Path,
) -> None:
    await ensure_extractors_schema(driver)

    with (
        patch("palace_mcp.extractors.runner.REPOS_ROOT", _project_and_repo),
        patch("palace_mcp.mcp_server.get_driver", return_value=driver),
    ):
        result = await run_extractor(
            name="public_api_surface",
            project="public-api-mini",
            driver=driver,
            graphiti=graphiti_mock,
        )

    assert result["ok"] is True
    assert result["extractor"] == "public_api_surface"
    assert result["project"] == "public-api-mini"
    assert result["success"] is True
    assert result["nodes_written"] > 0

    async with driver.session() as session:
        surface_result = await session.run(
            "MATCH (s:PublicApiSurface {project: $project}) "
            "RETURN s.module_name AS module_name, s.language AS language, s.commit_sha AS commit_sha "
            "ORDER BY module_name",
            project="public-api-mini",
        )
        surfaces = await surface_result.data()

        export_result = await session.run(
            "MATCH (:PublicApiSurface {project: $project})-[:EXPORTS]->(symbol:PublicApiSymbol) "
            "RETURN count(symbol) AS count",
            project="public-api-mini",
        )
        export_row = await export_result.single()

        public_result = await session.run(
            """
            MATCH (:PublicApiSurface {
                project: $project,
                module_name: $module_name,
                language: $language,
                commit_sha: $commit_sha
            })-[:EXPORTS]->(symbol:PublicApiSymbol)
            WHERE symbol.visibility <> 'package'
            RETURN collect(symbol.fqn) AS fqns
            """,
            project="public-api-mini",
            module_name="UwMiniKit",
            language="swift",
            commit_sha=_HEAD_SHA,
        )
        public_row = await public_result.single()

        package_result = await session.run(
            "MATCH (symbol:PublicApiSymbol {project: $project, visibility: 'package'}) "
            "RETURN collect(symbol.fqn) AS fqns",
            project="public-api-mini",
        )
        package_row = await package_result.single()

        backing_result = await session.run(
            "MATCH (symbol:PublicApiSymbol)-[:BACKED_BY_SYMBOL]->(:SymbolOccurrenceShadow) "
            "RETURN collect(symbol.fqn) AS fqns",
        )
        backing_row = await backing_result.single()

    assert surfaces == [
        {"module_name": "UwMiniCore", "language": "kotlin", "commit_sha": _HEAD_SHA},
        {"module_name": "UwMiniKit", "language": "swift", "commit_sha": _HEAD_SHA},
    ]
    assert export_row is not None and export_row["count"] >= 12
    assert public_row is not None
    assert "packageHelper()" not in public_row["fqns"]
    assert package_row is not None and package_row["fqns"] == ["packageHelper()"]
    assert backing_row is not None
    assert set(backing_row["fqns"]) == {"Wallet.balance()", "com.example.wallet.Wallet"}
