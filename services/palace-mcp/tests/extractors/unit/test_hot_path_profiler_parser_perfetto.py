"""Unit tests for the Perfetto parser."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

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


@dataclass(frozen=True)
class _Row:
    symbol_name: str
    cpu_samples: int
    wall_ms: int
    thread_name: str


class _FakeTraceProcessor:
    def __init__(self, *, trace: str) -> None:
        self.trace = trace
        self.queries: list[str] = []

    def __enter__(self) -> "_FakeTraceProcessor":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def query(self, sql: str):
        self.queries.append(sql)
        return iter(
            [
                _Row(
                    symbol_name="WalletApp.AppDelegate.bootstrap()",
                    cpu_samples=8,
                    wall_ms=120,
                    thread_name="main",
                ),
                _Row(
                    symbol_name="WalletApp.HomeViewModel.loadDashboard()",
                    cpu_samples=5,
                    wall_ms=80,
                    thread_name="main",
                ),
            ]
        )


def test_parse_perfetto_trace_uses_trace_processor_factory() -> None:
    processor = _FakeTraceProcessor(trace=str(_FIXTURE))

    def _factory(*, trace: str) -> _FakeTraceProcessor:
        assert trace == str(_FIXTURE)
        return processor

    summary, samples = parse_perfetto_trace(_FIXTURE, trace_processor_factory=_factory)

    assert processor.queries == [PERFETTO_HOT_PATH_SQL]
    assert summary.source_format == "perfetto"
    assert summary.total_cpu_samples == 13
    assert summary.total_wall_ms == 200
    assert [sample.cpu_samples for sample in samples] == [8, 5]
    assert samples[0].cpu_share == 8 / 13


def test_perfetto_query_targets_cpu_profile_tables() -> None:
    assert "cpu_profiling_samples" in PERFETTO_HOT_PATH_SQL
    assert "stack_profile_callsite" in PERFETTO_HOT_PATH_SQL
    assert "stack_profile_frame" in PERFETTO_HOT_PATH_SQL
    assert "FROM slice" not in PERFETTO_HOT_PATH_SQL
