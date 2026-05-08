"""End-to-end tests for the extractor orchestrator on seeded fixture."""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from palace_mcp.extractors.base import ExtractorRunContext
from palace_mcp.extractors.cross_repo_version_skew.extractor import (
    CrossRepoVersionSkewExtractor,
)


async def _seed(driver) -> None:  # type: ignore[no-untyped-def]
    async with driver.session() as session:
        await session.run("MATCH (n) DETACH DELETE n")
        await session.run("""
            MERGE (a:Project {slug: 'uw-ios-app'})
            MERGE (m:Project {slug: 'marketkit'})
            MERGE (e:Project {slug: 'evmkit'})
            MERGE (b:Project {slug: 'bitcoinkit'})
            MERGE (bd:Bundle {name: 'uw-ios-mini'})
            MERGE (bd)-[:HAS_MEMBER]->(a)
            MERGE (bd)-[:HAS_MEMBER]->(m)
            MERGE (bd)-[:HAS_MEMBER]->(e)
            MERGE (bd)-[:HAS_MEMBER]->(b)

            MERGE (mk_15:ExternalDependency {purl: 'pkg:github/horizontalsystems/marketkit@1.5.0'})
              SET mk_15.ecosystem = 'github', mk_15.resolved_version = '1.5.0'
            MERGE (mk_20:ExternalDependency {purl: 'pkg:github/horizontalsystems/marketkit@2.0.1'})
              SET mk_20.ecosystem = 'github', mk_20.resolved_version = '2.0.1'

            MERGE (a)-[:DEPENDS_ON {scope: 'main', declared_in: 'Package.swift', declared_version_constraint: '^1.5.0'}]->(mk_15)
            MERGE (m)-[:DEPENDS_ON {scope: 'main', declared_in: 'Package.swift', declared_version_constraint: '^2.0.0'}]->(mk_20)
        """)


async def _seed_ingest_run(driver, run_id: str) -> None:  # type: ignore[no-untyped-def]
    async with driver.session() as session:
        await session.run(
            """
            CREATE (r:IngestRun {id: $run_id, extractor_name: 'cross_repo_version_skew', success: true})
        """,
            run_id=run_id,
        )


def _ctx(*, project_slug: str, run_id: str = "test-run-001") -> ExtractorRunContext:
    return ExtractorRunContext(
        project_slug=project_slug,
        group_id=f"project/{project_slug}",
        repo_path=Path("/tmp/fake-repo"),
        run_id=run_id,
        duration_ms=30_000,
        logger=logging.getLogger("test"),
    )


def _patch_mcp(driver):  # type: ignore[no-untyped-def]
    mock_settings = MagicMock()
    mock_settings.palace_version_skew_query_timeout_s = 30
    return patch.multiple(
        "palace_mcp.mcp_server",
        get_driver=MagicMock(return_value=driver),
        get_settings=MagicMock(return_value=mock_settings),
    )


@pytest.mark.asyncio
async def test_acceptance_1_bootstrap_project_mode(driver):  # type: ignore[no-untyped-def]
    await _seed(driver)
    run_id = "test-run-project-001"
    await _seed_ingest_run(driver, run_id)
    ext = CrossRepoVersionSkewExtractor()
    with _patch_mcp(driver):
        stats = await ext.run(
            graphiti=MagicMock(), ctx=_ctx(project_slug="marketkit", run_id=run_id)
        )
    assert stats.nodes_written == 1
    assert stats.edges_written == 0

    async with driver.session() as session:
        out = await session.run(
            """
            MATCH (r:IngestRun {id: $run_id})
            RETURN r.mode AS mode, r.target_slug AS target
        """,
            run_id=run_id,
        )
        row = await out.single()
    assert row["mode"] == "project"
    assert row["target"] == "marketkit"


@pytest.mark.asyncio
async def test_acceptance_2_bootstrap_bundle_mode(driver):  # type: ignore[no-untyped-def]
    await _seed(driver)
    run_id = "test-run-bundle-001"
    await _seed_ingest_run(driver, run_id)
    ext = CrossRepoVersionSkewExtractor()
    with _patch_mcp(driver):
        stats = await ext.run(
            graphiti=MagicMock(), ctx=_ctx(project_slug="uw-ios-mini", run_id=run_id)
        )
    assert stats.nodes_written == 1

    async with driver.session() as session:
        out = await session.run(
            """
            MATCH (r:IngestRun {id: $run_id})
            RETURN r.mode AS mode, r.skew_groups_total AS total
        """,
            run_id=run_id,
        )
        row = await out.single()
    assert row["mode"] == "bundle"
    assert row["total"] == 1  # marketkit major skew


@pytest.mark.asyncio
async def test_acceptance_3_no_skew_target(driver):  # type: ignore[no-untyped-def]
    await _seed(driver)
    async with driver.session() as session:
        await session.run("""
            MERGE (lonely:Project {slug: 'lonely-project'})
            MERGE (d:ExternalDependency {purl: 'pkg:pypi/foo@1.0.0'})
              SET d.ecosystem = 'pypi', d.resolved_version = '1.0.0'
            MERGE (lonely)-[:DEPENDS_ON {scope: 'main', declared_in: 'pyproject.toml', declared_version_constraint: '1.0.0'}]->(d)
        """)
    run_id = "test-run-lonely-001"
    await _seed_ingest_run(driver, run_id)
    ext = CrossRepoVersionSkewExtractor()
    with _patch_mcp(driver):
        stats = await ext.run(
            graphiti=MagicMock(), ctx=_ctx(project_slug="lonely-project", run_id=run_id)
        )
    assert stats.nodes_written == 1

    async with driver.session() as session:
        out = await session.run(
            """
            MATCH (r:IngestRun {id: $run_id})
            RETURN r.skew_groups_total AS total
        """,
            run_id=run_id,
        )
        row = await out.single()
    assert row["total"] == 0


@pytest.mark.asyncio
async def test_acceptance_14_pure_read_invariant(driver):  # type: ignore[no-untyped-def]
    """Snapshot graph counts before/after run; delta = +0 nodes (IngestRun pre-seeded) + extras only."""
    await _seed(driver)
    run_id = "test-run-read-invariant"
    await _seed_ingest_run(driver, run_id)

    async with driver.session() as session:
        before = await (await session.run("MATCH (n) RETURN count(n) AS n")).single()
        before_e = await (
            await session.run("MATCH ()-[r]->() RETURN count(r) AS n")
        ).single()

    ext = CrossRepoVersionSkewExtractor()
    with _patch_mcp(driver):
        await ext.run(
            graphiti=MagicMock(), ctx=_ctx(project_slug="uw-ios-mini", run_id=run_id)
        )

    async with driver.session() as session:
        after = await (await session.run("MATCH (n) RETURN count(n) AS n")).single()
        after_e = await (
            await session.run("MATCH ()-[r]->() RETURN count(r) AS n")
        ).single()

    assert after["n"] == before["n"], (
        "No new nodes (IngestRun was pre-seeded; extractor only sets props)"
    )
    assert after_e["n"] == before_e["n"], "No new edges"


@pytest.mark.asyncio
async def test_acceptance_17_re_run_creates_distinct_ingest_run(driver):  # type: ignore[no-untyped-def]
    await _seed(driver)
    ext = CrossRepoVersionSkewExtractor()

    run_id_1 = "test-run-rerun-001"
    run_id_2 = "test-run-rerun-002"
    await _seed_ingest_run(driver, run_id_1)
    await _seed_ingest_run(driver, run_id_2)

    with _patch_mcp(driver):
        await ext.run(
            graphiti=MagicMock(), ctx=_ctx(project_slug="uw-ios-mini", run_id=run_id_1)
        )
        await ext.run(
            graphiti=MagicMock(), ctx=_ctx(project_slug="uw-ios-mini", run_id=run_id_2)
        )

    async with driver.session() as session:
        rows = await (
            await session.run("""
            MATCH (r:IngestRun {extractor_name: 'cross_repo_version_skew'})
            RETURN count(r) AS n
        """)
        ).single()
    assert rows["n"] == 2
