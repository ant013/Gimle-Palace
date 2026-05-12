"""Unit tests for the Perfetto parser."""

from __future__ import annotations

from pathlib import Path

from perfetto.trace_processor import TraceProcessor, TraceProcessorConfig

from palace_mcp.extractors.hot_path_profiler.parsers.perfetto import (
    PERFETTO_HOT_PATH_SQL,
    parse_perfetto_trace,
)

_FIXTURE = (
    Path(__file__).parent.parent
    / "fixtures"
    / "hot-path-fixture"
    / "synthetic"
    / "perfetto-stub.pftrace"
)


def test_parse_perfetto_trace_loads_real_perfetto_fixture() -> None:
    def _factory(*, trace: str) -> TraceProcessor:
        assert trace == str(_FIXTURE)
        return TraceProcessor(
            trace=trace,
            config=TraceProcessorConfig(load_timeout=10),
        )

    summary, samples = parse_perfetto_trace(_FIXTURE, trace_processor_factory=_factory)

    assert summary.source_format == "perfetto"
    assert summary.total_cpu_samples == 4
    assert summary.total_wall_ms == 0
    assert summary.hot_function_count == 3
    assert [sample.symbol_name for sample in samples] == [
        "WalletApp.AppDelegate.bootstrap()",
        "WalletApp.HomeViewModel.loadDashboard()",
        "WalletApp.MarketDataPrefetcher.prefetch()",
    ]
    assert [sample.cpu_samples for sample in samples] == [2, 1, 1]
    assert samples[0].cpu_share == 0.5
    assert all(sample.thread_name is None for sample in samples)


def test_perfetto_query_targets_cpu_profile_tables() -> None:
    assert "cpu_profiling_samples" in PERFETTO_HOT_PATH_SQL
    assert "stack_profile_callsite" in PERFETTO_HOT_PATH_SQL
    assert "stack_profile_frame" in PERFETTO_HOT_PATH_SQL
    assert "FROM slice" not in PERFETTO_HOT_PATH_SQL
