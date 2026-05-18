"""Unit tests for the simpleperf protobuf parser."""

from __future__ import annotations

from pathlib import Path

from palace_mcp.extractors.hot_path_profiler.parsers.simpleperf import (
    parse_simpleperf_trace,
)

_FIXTURE = (
    Path(__file__).parent.parent
    / "fixtures"
    / "hot-path-fixture"
    / "synthetic"
    / "simpleperf-stub.trace"
)


def test_parse_simpleperf_trace_returns_summary_and_samples() -> None:
    summary, samples = parse_simpleperf_trace(_FIXTURE)

    assert summary.trace_id == "simpleperf-stub"
    assert summary.source_format == "simpleperf"
    assert summary.total_cpu_samples == 1000
    assert summary.total_wall_ms == 0
    assert summary.hot_function_count == 3
    assert [sample.symbol_name for sample in samples] == [
        "WalletApp.AppDelegate.bootstrap()",
        "WalletApp.HomeViewModel.loadDashboard()",
        "WalletApp.MarketDataPrefetcher.prefetch()",
    ]
    assert [sample.cpu_samples for sample in samples] == [500, 300, 200]
    assert {sample.thread_name for sample in samples} == {"main"}
