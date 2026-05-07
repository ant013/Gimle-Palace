"""Integration tests for reactive_dependency_tracer."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from neo4j import AsyncDriver

from palace_mcp.extractors.base import ExtractorRunContext
from palace_mcp.extractors.reactive_dependency_tracer.extractor import (
    ReactiveDependencyTracerExtractor,
)

FIXTURE_ROOT = (
    Path(__file__).resolve().parents[1] / "fixtures" / "reactive-dependency-swift-mini"
)
PROJECT_SLUG = "reactive-dependency-mini"
GROUP_ID = f"project/{PROJECT_SLUG}"
HEAD_SHA = "0123456789abcdef0123456789abcdef01234567"


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
def fixture_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "reactive-repo"
    shutil.copytree(FIXTURE_ROOT, repo)
    git_dir = repo / ".git"
    git_dir.mkdir()
    (git_dir / "HEAD").write_text(f"{HEAD_SHA}\n", encoding="utf-8")
    return repo


@pytest.mark.integration
async def test_reactive_dependency_tracer_writes_expected_graph(
    driver: AsyncDriver, fixture_repo: Path
) -> None:
    extractor = ReactiveDependencyTracerExtractor()
    ctx = _make_ctx(fixture_repo)

    with patch("palace_mcp.mcp_server.get_driver", return_value=driver):
        stats = await extractor.run(graphiti=MagicMock(), ctx=ctx)

    assert stats.nodes_written >= 4
    assert stats.edges_written >= 3

    async with driver.session() as session:
        result = await session.run(
            "MATCH (n:ReactiveComponent {project: $project}) RETURN count(n) AS cnt",
            project=PROJECT_SLUG,
        )
        component_count = await result.single()
        result = await session.run(
            "MATCH (n:ReactiveState {project: $project}) RETURN count(n) AS cnt",
            project=PROJECT_SLUG,
        )
        state_count = await result.single()
        result = await session.run(
            "MATCH (n:ReactiveEffect {project: $project}) RETURN count(n) AS cnt",
            project=PROJECT_SLUG,
        )
        effect_count = await result.single()
        result = await session.run(
            "MATCH (n:ReactiveDiagnostic {project: $project}) RETURN count(n) AS cnt",
            project=PROJECT_SLUG,
        )
        diagnostic_count = await result.single()
        result = await session.run(
            """
            MATCH (:ReactiveComponent {project: $project})
                  -[:DECLARES_STATE]->
                  (:ReactiveState {project: $project})
            RETURN count(*) AS cnt
            """,
            project=PROJECT_SLUG,
        )
        declares_count = await result.single()
        result = await session.run(
            """
            MATCH (:ReactiveState {project: $project})
                  -[:TRIGGERS_EFFECT]->
                  (:ReactiveEffect {project: $project})
            RETURN count(*) AS cnt
            """,
            project=PROJECT_SLUG,
        )
        triggers_count = await result.single()
        result = await session.run(
            """
            MATCH (:ReactiveDiagnostic {project: $project})
                  -[:DIAGNOSTIC_FOR]->
                  (:ReactiveComponent {project: $project})
            RETURN count(*) AS cnt
            """,
            project=PROJECT_SLUG,
        )
        diagnostic_edge_count = await result.single()

    assert component_count is not None and component_count["cnt"] == 1
    assert state_count is not None and state_count["cnt"] == 1
    assert effect_count is not None and effect_count["cnt"] == 1
    assert diagnostic_count is not None and diagnostic_count["cnt"] == 1
    assert declares_count is not None and declares_count["cnt"] == 1
    assert triggers_count is not None and triggers_count["cnt"] == 1
    assert diagnostic_edge_count is not None and diagnostic_edge_count["cnt"] == 1


@pytest.mark.integration
async def test_reactive_dependency_tracer_rerun_keeps_graph_counts_stable(
    driver: AsyncDriver, fixture_repo: Path
) -> None:
    extractor = ReactiveDependencyTracerExtractor()
    ctx = _make_ctx(fixture_repo)

    with patch("palace_mcp.mcp_server.get_driver", return_value=driver):
        await extractor.run(graphiti=MagicMock(), ctx=ctx)
        await extractor.run(graphiti=MagicMock(), ctx=ctx)

    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (c:ReactiveComponent {project: $project})
            WITH count(c) AS components
            MATCH (s:ReactiveState {project: $project})
            WITH components, count(s) AS states
            MATCH (e:ReactiveEffect {project: $project})
            WITH components, states, count(e) AS effects
            MATCH (d:ReactiveDiagnostic {project: $project})
            WITH components, states, effects, count(d) AS diagnostics
            MATCH (:ReactiveComponent {project: $project})-[:DECLARES_STATE]->(:ReactiveState {project: $project})
            WITH components, states, effects, diagnostics, count(*) AS declares_edges
            MATCH (:ReactiveState {project: $project})-[:TRIGGERS_EFFECT]->(:ReactiveEffect {project: $project})
            RETURN components, states, effects, diagnostics, declares_edges, count(*) AS trigger_edges
            """,
            project=PROJECT_SLUG,
        )
        record = await result.single()

    assert record is not None
    assert record["components"] == 1
    assert record["states"] == 1
    assert record["effects"] == 1
    assert record["diagnostics"] == 1
    assert record["declares_edges"] == 1
    assert record["trigger_edges"] == 1
