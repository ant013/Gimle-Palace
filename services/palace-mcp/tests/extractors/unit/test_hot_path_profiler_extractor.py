"""Unit tests for hot_path_profiler orchestration."""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from palace_mcp.extractors.base import ExtractorConfigError, ExtractorRunContext
from palace_mcp.extractors.hot_path_profiler.extractor import HotPathProfilerExtractor
from palace_mcp.extractors.hot_path_profiler.models import HotPathSample, HotPathSummary


def _ctx(repo_path: Path) -> ExtractorRunContext:
    return ExtractorRunContext(
        project_slug="testproj",
        group_id="project/testproj",
        repo_path=repo_path,
        run_id="run-1",
        duration_ms=0,
        logger=logging.getLogger("test.hot_path_profiler"),
    )


@pytest.mark.asyncio
async def test_run_requires_profiles_directory(tmp_path: Path) -> None:
    graphiti = MagicMock()
    graphiti.driver = MagicMock()

    with pytest.raises(ExtractorConfigError, match="profiles directory"):
        await HotPathProfilerExtractor().run(graphiti=graphiti, ctx=_ctx(tmp_path))


@pytest.mark.asyncio
async def test_run_processes_trace_files(tmp_path: Path) -> None:
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    trace = profiles / "track-a.json"
    trace.write_text("{}", encoding="utf-8")

    graphiti = MagicMock()
    graphiti.driver = MagicMock()
    summary = HotPathSummary(
        trace_id="track-a",
        source_format="instruments",
        total_cpu_samples=100,
        total_wall_ms=50,
        hot_function_count=1,
        threshold_cpu_share=0.05,
    )
    sample = HotPathSample(
        trace_id="track-a",
        source_format="instruments",
        symbol_name="WalletApp.AppDelegate.bootstrap()",
        cpu_samples=60,
        wall_ms=20,
        total_samples_in_trace=100,
        total_wall_ms_in_trace=50,
    )

    with (
        patch.object(
            HotPathProfilerExtractor,
            "_parse_trace",
            return_value=(summary, [sample]),
        ),
        patch(
            "palace_mcp.extractors.hot_path_profiler.extractor.symbol_resolver.resolve_samples",
            new=AsyncMock(return_value=([sample], [])),
        ) as resolver,
        patch(
            "palace_mcp.extractors.hot_path_profiler.extractor.neo4j_writer.write_snapshot",
            new=AsyncMock(return_value=(2, 1)),
        ) as writer,
    ):
        stats = await HotPathProfilerExtractor().run(
            graphiti=graphiti, ctx=_ctx(tmp_path)
        )

    resolver.assert_awaited_once()
    writer.assert_awaited_once()
    assert stats.nodes_written == 2
    assert stats.edges_written == 1


@pytest.mark.asyncio
async def test_run_recomputes_hot_function_count_from_resolved_samples(
    tmp_path: Path,
) -> None:
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    trace = profiles / "track-a.json"
    trace.write_text("{}", encoding="utf-8")

    graphiti = MagicMock()
    graphiti.driver = MagicMock()
    summary = HotPathSummary(
        trace_id="track-a",
        source_format="instruments",
        total_cpu_samples=100,
        total_wall_ms=50,
        hot_function_count=2,
        threshold_cpu_share=0.05,
    )
    resolved = HotPathSample(
        trace_id="track-a",
        source_format="instruments",
        symbol_name="WalletApp.AppDelegate.bootstrap()",
        qualified_name="WalletApp.AppDelegate.bootstrap()",
        cpu_samples=60,
        wall_ms=20,
        total_samples_in_trace=100,
        total_wall_ms_in_trace=50,
    )
    unresolved = HotPathSample(
        trace_id="track-a",
        source_format="instruments",
        symbol_name="ThirdParty.LegacyCryptoSigner.sign()",
        cpu_samples=10,
        wall_ms=5,
        total_samples_in_trace=100,
        total_wall_ms_in_trace=50,
    )

    with (
        patch.object(
            HotPathProfilerExtractor,
            "_parse_trace",
            return_value=(summary, [resolved, unresolved]),
        ),
        patch(
            "palace_mcp.extractors.hot_path_profiler.extractor.symbol_resolver.resolve_samples",
            new=AsyncMock(return_value=([resolved], [unresolved])),
        ),
        patch(
            "palace_mcp.extractors.hot_path_profiler.extractor.neo4j_writer.write_snapshot",
            new=AsyncMock(return_value=(3, 1)),
        ) as writer,
    ):
        await HotPathProfilerExtractor().run(graphiti=graphiti, ctx=_ctx(tmp_path))

    assert writer.await_count == 1
    effective_summary = writer.await_args.kwargs["summary"]
    assert effective_summary.hot_function_count == 1
