"""Integration tests for hot_path_profiler with real Neo4j."""

from __future__ import annotations

import logging
import os
import json
import shutil
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from neo4j import AsyncDriver

from palace_mcp.audit.contracts import RunInfo
from palace_mcp.audit.fetcher import fetch_audit_data
from palace_mcp.extractors.base import ExtractorRunContext
from palace_mcp.extractors.hot_path_profiler.extractor import HotPathProfilerExtractor
from palace_mcp.extractors.schema import ensure_extractors_schema

_HAS_NEO4J_RUNTIME = (
    bool(os.environ.get("COMPOSE_NEO4J_URI")) or Path("/var/run/docker.sock").exists()
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not _HAS_NEO4J_RUNTIME,
        reason="requires Docker socket or COMPOSE_NEO4J_URI for Neo4j integration",
    ),
]

_FIXTURE_ROOT = (
    Path(__file__).parent.parent / "fixtures" / "hot-path-fixture" / "profiles"
)


def _ctx(repo_path: Path, run_id: str = "hot-path-run-1") -> ExtractorRunContext:
    return ExtractorRunContext(
        project_slug="hot-path-integ",
        group_id="project/hot-path-integ",
        repo_path=repo_path,
        run_id=run_id,
        duration_ms=0,
        logger=logging.getLogger("test.hot_path_profiler.integration"),
    )


async def _seed_functions(driver: AsyncDriver, project_id: str) -> None:
    rows = [
        (
            "WalletApp.AppDelegate.bootstrap()",
            "bootstrap",
            "bootstrap()",
            "AppDelegate.swift",
            12,
        ),
        (
            "WalletApp.HomeViewModel.loadDashboard()",
            "loadDashboard",
            "loadDashboard()",
            "HomeViewModel.swift",
            48,
        ),
        (
            "WalletApp.MarketDataPrefetcher.prefetch()",
            "prefetch",
            "prefetch()",
            "MarketDataPrefetcher.swift",
            27,
        ),
    ]
    async with driver.session() as session:
        for qualified_name, name, display_name, path, start_line in rows:
            await session.run(
                """
                CREATE (:Function {
                    project_id: $project_id,
                    qualified_name: $qualified_name,
                    name: $name,
                    display_name: $display_name,
                    path: $path,
                    start_line: $start_line
                })
                """,
                project_id=project_id,
                qualified_name=qualified_name,
                name=name,
                display_name=display_name,
                path=path,
                start_line=start_line,
            )


@pytest.mark.asyncio
async def test_run_integration_writes_samples_and_summary(
    driver: AsyncDriver,
    graphiti_mock: MagicMock,
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    profiles = repo / "profiles"
    profiles.mkdir(parents=True)
    shutil.copy(
        _FIXTURE_ROOT / "track-a-instruments-time-profile.json",
        profiles / "track-a-instruments-time-profile.json",
    )

    await ensure_extractors_schema(driver)
    await _seed_functions(driver, "project/hot-path-integ")

    stats = await HotPathProfilerExtractor().run(
        graphiti=graphiti_mock,
        ctx=_ctx(repo),
    )

    assert stats.nodes_written == 5
    assert stats.edges_written == 3

    async with driver.session() as session:
        sample_result = await session.run(
            "MATCH (s:HotPathSample {project_id: $pid}) RETURN count(s) AS n",
            pid="project/hot-path-integ",
        )
        summary_result = await session.run(
            "MATCH (s:HotPathSummary {project_id: $pid}) RETURN count(s) AS n",
            pid="project/hot-path-integ",
        )
        unresolved_result = await session.run(
            "MATCH (s:HotPathSampleUnresolved {project_id: $pid}) RETURN count(s) AS n",
            pid="project/hot-path-integ",
        )
        function_result = await session.run(
            """
            MATCH (fn:Function {project_id: $pid, qualified_name: $qualified_name})
            RETURN fn.cpu_share AS cpu_share,
                   fn.wall_share AS wall_share,
                   fn.is_hot_path AS is_hot_path
            """,
            pid="project/hot-path-integ",
            qualified_name="WalletApp.AppDelegate.bootstrap()",
        )
        sample_row = await sample_result.single()
        summary_row = await summary_result.single()
        unresolved_row = await unresolved_result.single()
        function_row = await function_result.single()

    assert sample_row is not None and sample_row["n"] == 3
    assert summary_row is not None and summary_row["n"] == 1
    assert unresolved_row is not None and unresolved_row["n"] == 1
    assert function_row is not None
    assert function_row["cpu_share"] == pytest.approx(420 / 1200)
    assert function_row["wall_share"] == pytest.approx(260 / 760)
    assert function_row["is_hot_path"] is True


@pytest.mark.asyncio
async def test_audit_fetcher_reads_hot_path_contract(
    driver: AsyncDriver,
    graphiti_mock: MagicMock,
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    profiles = repo / "profiles"
    profiles.mkdir(parents=True)
    shutil.copy(
        _FIXTURE_ROOT / "track-a-instruments-time-profile.json",
        profiles / "track-a-instruments-time-profile.json",
    )

    await ensure_extractors_schema(driver)
    await _seed_functions(driver, "project/hot-path-integ")
    extractor = HotPathProfilerExtractor()
    await extractor.run(graphiti=graphiti_mock, ctx=_ctx(repo, run_id="run-audit"))

    sections = await fetch_audit_data(
        driver,
        {
            "hot_path_profiler": RunInfo(
                run_id="run-audit",
                extractor_name="hot_path_profiler",
                project="hot-path-integ",
                completed_at="2026-05-12T00:00:00Z",
            )
        },
        {"hot_path_profiler": extractor},
    )

    section = sections["hot_path_profiler"]
    assert len(section.findings) == 3
    assert section.findings[0]["qualified_name"] == "WalletApp.AppDelegate.bootstrap()"


@pytest.mark.asyncio
async def test_run_integration_clears_stale_function_enrichment_on_repeat_run(
    driver: AsyncDriver,
    graphiti_mock: MagicMock,
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    profiles = repo / "profiles"
    profiles.mkdir(parents=True)
    trace_path = profiles / "track-a-instruments-time-profile.json"
    shutil.copy(
        _FIXTURE_ROOT / "track-a-instruments-time-profile.json",
        trace_path,
    )

    await ensure_extractors_schema(driver)
    await _seed_functions(driver, "project/hot-path-integ")
    extractor = HotPathProfilerExtractor()

    await extractor.run(graphiti=graphiti_mock, ctx=_ctx(repo, run_id="run-first"))

    trace_path.write_text(
        json.dumps(
            {
                "trace_id": "track-a-launch",
                "source_format": "instruments",
                "threshold_cpu_share": 0.05,
                "summary": {
                    "total_cpu_samples": 500,
                    "total_wall_ms": 220,
                },
                "samples": [
                    {
                        "symbol_name": "WalletApp.HomeViewModel.loadDashboard()",
                        "cpu_samples": 400,
                        "wall_ms": 160,
                        "thread_name": "com.apple.main-thread",
                    },
                    {
                        "symbol_name": "ThirdParty.LegacyCryptoSigner.sign()",
                        "cpu_samples": 100,
                        "wall_ms": 60,
                        "thread_name": "com.apple.main-thread",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    await extractor.run(graphiti=graphiti_mock, ctx=_ctx(repo, run_id="run-second"))

    async with driver.session() as session:
        bootstrap_result = await session.run(
            """
            MATCH (fn:Function {project_id: $pid, qualified_name: $qualified_name})
            RETURN fn.cpu_share AS cpu_share,
                   fn.wall_share AS wall_share,
                   fn.is_hot_path AS is_hot_path
            """,
            pid="project/hot-path-integ",
            qualified_name="WalletApp.AppDelegate.bootstrap()",
        )
        dashboard_result = await session.run(
            """
            MATCH (fn:Function {project_id: $pid, qualified_name: $qualified_name})
            RETURN fn.cpu_share AS cpu_share,
                   fn.wall_share AS wall_share,
                   fn.is_hot_path AS is_hot_path
            """,
            pid="project/hot-path-integ",
            qualified_name="WalletApp.HomeViewModel.loadDashboard()",
        )
        summary_result = await session.run(
            """
            MATCH (s:HotPathSummary {project_id: $pid, trace_id: $trace_id})
            RETURN s.hot_function_count AS hot_function_count
            """,
            pid="project/hot-path-integ",
            trace_id="track-a-launch",
        )
        bootstrap_row = await bootstrap_result.single()
        dashboard_row = await dashboard_result.single()
        summary_row = await summary_result.single()

    assert bootstrap_row is not None
    assert bootstrap_row["cpu_share"] is None
    assert bootstrap_row["wall_share"] is None
    assert bootstrap_row["is_hot_path"] is False

    assert dashboard_row is not None
    assert dashboard_row["cpu_share"] == pytest.approx(0.8)
    assert dashboard_row["wall_share"] == pytest.approx(160 / 220)
    assert dashboard_row["is_hot_path"] is True

    assert summary_row is not None
    assert summary_row["hot_function_count"] == 1
