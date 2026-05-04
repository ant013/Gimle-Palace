"""Integration tests for DependencySurfaceExtractor — Task 11.

Uses real Neo4j via testcontainers (or COMPOSE_NEO4J_URI reuse).
Fixture: tests/extractors/fixtures/dependency-surface-mini-project/
  - 2 SPM deps (EvmKit.Swift@1.5.3, swift-collections@1.1.4)
  - 2 Gradle deps (appcompat@1.7.1, retrofit@3.0.0)
  - 3 Python deps (neo4j@5.28.2, graphiti-core@0.28.2, pytest@8.3.4)
  Total: 7 nodes, 7 edges on first run.
"""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from palace_mcp.extractors.base import ExtractorRunContext
from palace_mcp.extractors.dependency_surface.extractor import (
    DependencySurfaceExtractor,
)
from palace_mcp.extractors.foundation.schema import ensure_custom_schema

PROJECT_SLUG = "dep-surface-mini"
GROUP_ID = f"project/{PROJECT_SLUG}"
FIXTURE_PATH = (
    Path(__file__).parents[2] / "extractors/fixtures/dependency-surface-mini-project"
)

# Total deps in fixture: 2 SPM + 2 Gradle + 3 Python = 7
EXPECTED_DEP_COUNT = 7


def _make_ctx(repo_path: Path) -> ExtractorRunContext:
    return ExtractorRunContext(
        project_slug=PROJECT_SLUG,
        group_id=GROUP_ID,
        repo_path=repo_path,
        run_id="integration-test-run",
        duration_ms=0,
        logger=logging.getLogger("integration"),
    )


@pytest.fixture
async def registered_project(driver):  # type: ignore[no-untyped-def]
    """Register :Project + schema — bypass runner pre-flight for integration tests."""
    await ensure_custom_schema(driver)
    async with driver.session() as s:
        await s.run(
            "MERGE (p:Project {slug: $slug, group_id: $gid})",
            slug=PROJECT_SLUG,
            gid=GROUP_ID,
        )
    yield
    # Teardown
    async with driver.session() as s:
        await s.run(
            "MATCH (p:Project {slug: $slug}) DETACH DELETE p",
            slug=PROJECT_SLUG,
        )
        await s.run(
            "MATCH (d:ExternalDependency) WHERE NOT (d)<-[:DEPENDS_ON]-() DELETE d"
        )


@pytest.mark.integration
async def test_full_flow_against_fixture(driver, registered_project) -> None:  # type: ignore[no-untyped-def]
    extractor = DependencySurfaceExtractor()
    ctx = _make_ctx(FIXTURE_PATH)

    with patch("palace_mcp.mcp_server.get_driver", return_value=driver):
        stats = await extractor.run(graphiti=MagicMock(), ctx=ctx)

    # Counter-precise: first run creates nodes+edges
    assert stats.nodes_written == EXPECTED_DEP_COUNT
    assert stats.edges_written == EXPECTED_DEP_COUNT

    # Verify in Neo4j
    async with driver.session() as s:
        result = await s.run(
            "MATCH (p:Project {slug: $slug})-[:DEPENDS_ON]->(d:ExternalDependency) "
            "RETURN count(d) AS cnt",
            slug=PROJECT_SLUG,
        )
        record = await result.single()
    assert record is not None
    assert record["cnt"] == EXPECTED_DEP_COUNT


@pytest.mark.integration
async def test_idempotent_remerge_counter_precise(driver, registered_project) -> None:  # type: ignore[no-untyped-def]
    extractor = DependencySurfaceExtractor()
    ctx = _make_ctx(FIXTURE_PATH)

    with patch("palace_mcp.mcp_server.get_driver", return_value=driver):
        stats1 = await extractor.run(graphiti=MagicMock(), ctx=ctx)
        stats2 = await extractor.run(graphiti=MagicMock(), ctx=ctx)

    # First run writes; second run must be zero net changes
    assert stats1.nodes_written == EXPECTED_DEP_COUNT
    assert stats1.edges_written == EXPECTED_DEP_COUNT
    assert stats2.nodes_written == 0, "counter-precise idempotency violated: nodes"
    assert stats2.edges_written == 0, "counter-precise idempotency violated: edges"

    # Node count unchanged after second run
    async with driver.session() as s:
        result = await s.run("MATCH (d:ExternalDependency) RETURN count(d) AS cnt")
        record = await result.single()
    assert record is not None
    assert record["cnt"] == EXPECTED_DEP_COUNT


@pytest.mark.integration
async def test_cross_project_dedup(driver) -> None:  # type: ignore[no-untyped-def]
    """Two projects depending on the same purl → single :ExternalDependency, two edges."""
    await ensure_custom_schema(driver)

    slug_a = "dep-dedup-a"
    slug_b = "dep-dedup-b"
    async with driver.session() as s:
        await s.run(
            "MERGE (p:Project {slug: $slug, group_id: $gid})",
            slug=slug_a,
            gid=f"project/{slug_a}",
        )
        await s.run(
            "MERGE (p:Project {slug: $slug, group_id: $gid})",
            slug=slug_b,
            gid=f"project/{slug_b}",
        )

    # Use fixture path for both projects (both get the same 7 deps with same purls)
    extractor = DependencySurfaceExtractor()

    ctx_a = ExtractorRunContext(
        project_slug=slug_a,
        group_id=f"project/{slug_a}",
        repo_path=FIXTURE_PATH,
        run_id="run-a",
        duration_ms=0,
        logger=logging.getLogger("integration"),
    )
    ctx_b = ExtractorRunContext(
        project_slug=slug_b,
        group_id=f"project/{slug_b}",
        repo_path=FIXTURE_PATH,
        run_id="run-b",
        duration_ms=0,
        logger=logging.getLogger("integration"),
    )

    with patch("palace_mcp.mcp_server.get_driver", return_value=driver):
        stats_a = await extractor.run(graphiti=MagicMock(), ctx=ctx_a)
        stats_b = await extractor.run(graphiti=MagicMock(), ctx=ctx_b)

    # Project A: all nodes created fresh
    assert stats_a.nodes_written == EXPECTED_DEP_COUNT
    # Project B: nodes already exist (dedup via MERGE on purl) → 0 new nodes, only edges
    assert stats_b.nodes_written == 0
    assert stats_b.edges_written == EXPECTED_DEP_COUNT

    # Total :ExternalDependency nodes: exactly EXPECTED_DEP_COUNT (deduped)
    async with driver.session() as s:
        result = await s.run("MATCH (d:ExternalDependency) RETURN count(d) AS cnt")
        record = await result.single()
    assert record is not None
    assert record["cnt"] == EXPECTED_DEP_COUNT

    # Total :DEPENDS_ON edges: 2x (one per project)
    async with driver.session() as s:
        result = await s.run("MATCH ()-[r:DEPENDS_ON]->() RETURN count(r) AS cnt")
        record = await result.single()
    assert record is not None
    assert record["cnt"] == EXPECTED_DEP_COUNT * 2
