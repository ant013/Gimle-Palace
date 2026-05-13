"""Integration test — hotspot extractor with real Neo4j.

Uses testcontainers Neo4j (or COMPOSE_NEO4J_URI reuse).
Churn data seeded directly (no GitHistoryExtractor invocation) to avoid
tantivy/budget infra requirements.
"""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from neo4j import AsyncDriver

from palace_mcp.extractors.base import ExtractorRunContext
from palace_mcp.extractors.hotspot.extractor import HotspotExtractor

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "hotspot-mini-project"
_BUILD_SCRIPT = FIXTURE_DIR / "_build_fixture_repo.py"


def _build_repo(tmp: Path) -> Path:
    """Build the fixture git repo into tmp via the build script."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("_bfr", _BUILD_SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    out = tmp / "repo"
    mod.main(str(out))
    return out


def _fake_settings() -> MagicMock:
    s = MagicMock()
    s.palace_hotspot_lizard_batch_size = 50
    s.palace_hotspot_lizard_timeout_s = 30
    s.palace_hotspot_lizard_timeout_behavior = "drop_batch"
    s.palace_hotspot_churn_window_days = 90
    return s


def _ctx(
    repo_path: Path, run_id: str, project_slug: str = "hs-integ"
) -> ExtractorRunContext:
    return ExtractorRunContext(
        project_slug=project_slug,
        group_id=f"project/{project_slug}",
        repo_path=repo_path,
        run_id=run_id,
        duration_ms=0,
        logger=logging.getLogger("test.hotspot"),
    )


async def _seed_git_history_run(driver: AsyncDriver, project_slug: str) -> None:
    """Seed a successful git_history IngestRun so the prerequisite guard passes."""
    async with driver.session() as session:
        await session.run(
            "MERGE (r:IngestRun {project: $project, extractor_name: 'git_history'}) "
            "SET r.success = true",
            project=project_slug,
        )


async def _seed_churn(
    driver: AsyncDriver, project_id: str, churn_map: dict[str, int]
) -> None:
    """Seed :File + :Commit + :TOUCHED nodes to satisfy the churn query."""
    async with driver.session() as session:
        for path, count in churn_map.items():
            await session.run(
                "MERGE (f:File {project_id: $pid, path: $path})",
                pid=project_id,
                path=path,
            )
            for i in range(count):
                await session.run(
                    "MATCH (f:File {project_id: $pid, path: $path}) "
                    "CREATE (c:Commit {sha: $sha, committed_at: datetime('2026-04-01T00:00:00Z')}) "
                    "CREATE (c)-[:TOUCHED]->(f)",
                    pid=project_id,
                    path=path,
                    sha=f"{path.replace('/', '_')}_{i}",
                )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_hotspot_full_pipeline(
    driver: AsyncDriver, graphiti_mock: MagicMock, tmp_path: Path
) -> None:
    repo = _build_repo(tmp_path)
    project_id = "project/hs-integ"
    await _seed_git_history_run(driver, "hs-integ")
    await _seed_churn(
        driver,
        project_id,
        {
            "src/python_simple.py": 2,
            "src/python_complex.py": 4,
            "src/main.kt": 1,
            "src/util.ts": 1,
        },
    )

    with patch("palace_mcp.mcp_server.get_settings", return_value=_fake_settings()):
        stats = await HotspotExtractor().run(
            graphiti=graphiti_mock, ctx=_ctx(repo, "run-1")
        )

    assert stats.nodes_written > 0

    async with driver.session() as session:
        result = await session.run(
            "MATCH (f:File {project_id: $p, path: 'src/python_complex.py'}) "
            "RETURN f.ccn_total AS ccn, f.churn_count AS churn, "
            "f.hotspot_score AS score, f.complexity_status AS status",
            p=project_id,
        )
        row = await result.single()
        assert row is not None
        assert row["ccn"] == 6
        assert row["churn"] == 4
        assert row["score"] > 0
        assert row["status"] == "fresh"

        result2 = await session.run(
            "MATCH (f:File {project_id: $p, path: 'src/python_complex.py'})"
            "-[:CONTAINS]->(fn:Function) RETURN count(fn) AS n",
            p=project_id,
        )
        n_row = await result2.single()
        assert n_row is not None
        assert n_row["n"] >= 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_hotspot_idempotent_via_consume_counters(
    driver: AsyncDriver, graphiti_mock: MagicMock, tmp_path: Path
) -> None:
    repo = _build_repo(tmp_path)
    project_id = "project/hs-integ"
    await _seed_git_history_run(driver, "hs-integ")
    await _seed_churn(
        driver,
        project_id,
        {
            "src/python_simple.py": 2,
            "src/python_complex.py": 4,
            "src/main.kt": 1,
            "src/util.ts": 1,
        },
    )

    with patch("palace_mcp.mcp_server.get_settings", return_value=_fake_settings()):
        hot = HotspotExtractor()
        ctx = _ctx(repo, "run-2")
        await hot.run(graphiti=graphiti_mock, ctx=ctx)
        await hot.run(graphiti=graphiti_mock, ctx=ctx)

    async with driver.session() as session:
        result = await session.run(
            "MERGE (f:File {project_id: $p, path: 'src/python_simple.py'}) "
            "ON CREATE SET f._marker = true",
            p=project_id,
        )
        summary = await result.consume()
        assert summary.counters.nodes_created == 0
        assert summary.counters.relationships_created == 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_hotspot_eviction_removes_dead_functions(
    driver: AsyncDriver, graphiti_mock: MagicMock, tmp_path: Path
) -> None:
    repo = _build_repo(tmp_path)
    project_id = "project/hs-integ"
    await _seed_git_history_run(driver, "hs-integ")
    await _seed_churn(
        driver,
        project_id,
        {
            "src/python_simple.py": 2,
            "src/python_complex.py": 4,
            "src/main.kt": 1,
            "src/util.ts": 1,
        },
    )

    with patch("palace_mcp.mcp_server.get_settings", return_value=_fake_settings()):
        await HotspotExtractor().run(graphiti=graphiti_mock, ctx=_ctx(repo, "run-3a"))

        # Remove util.ts from repo, then re-run
        (repo / "src" / "util.ts").unlink()
        await HotspotExtractor().run(graphiti=graphiti_mock, ctx=_ctx(repo, "run-3b"))

    async with driver.session() as session:
        result = await session.run(
            "MATCH (f:File {project_id: $p, path: 'src/util.ts'}) "
            "RETURN f.ccn_total AS ccn, f.complexity_status AS status",
            p=project_id,
        )
        row = await result.single()
        assert row is not None
        assert row["ccn"] == 0
        assert row["status"] == "stale"

        result2 = await session.run(
            "MATCH (f:File {project_id: $p, path: 'src/util.ts'})"
            "-[:CONTAINS]->(fn:Function) RETURN count(fn) AS n",
            p=project_id,
        )
        n_row = await result2.single()
        assert n_row is not None
        assert n_row["n"] == 0
