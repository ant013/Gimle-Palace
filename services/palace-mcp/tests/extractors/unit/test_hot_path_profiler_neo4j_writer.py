"""Unit tests for hot_path_profiler Neo4j writer orchestration."""

from __future__ import annotations

from typing import Any

import pytest

from palace_mcp.extractors.hot_path_profiler.models import HotPathSample, HotPathSummary
from palace_mcp.extractors.hot_path_profiler.neo4j_writer import write_snapshot


class _FakeCursor:
    async def consume(self) -> None:
        return None


class _FakeTx:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def run(self, query: str, /, **params: Any) -> _FakeCursor:
        self.calls.append((query, params))
        return _FakeCursor()


class _FakeSession:
    def __init__(self, tx: _FakeTx) -> None:
        self._tx = tx

    async def __aenter__(self) -> "_FakeSession":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def execute_write(self, fn, *args):
        return await fn(self._tx, *args)


class _FakeDriver:
    def __init__(self, tx: _FakeTx) -> None:
        self._tx = tx

    def session(self) -> _FakeSession:
        return _FakeSession(self._tx)


@pytest.mark.asyncio
async def test_write_snapshot_counts_nodes_and_edges() -> None:
    tx = _FakeTx()
    driver = _FakeDriver(tx)
    summary = HotPathSummary(
        trace_id="track-a",
        source_format="instruments",
        total_cpu_samples=100,
        total_wall_ms=50,
        hot_function_count=1,
        threshold_cpu_share=0.05,
    )
    resolved = [
        HotPathSample(
            trace_id="track-a",
            source_format="instruments",
            symbol_name="WalletApp.AppDelegate.bootstrap()",
            qualified_name="WalletApp.AppDelegate.bootstrap()",
            cpu_samples=60,
            wall_ms=25,
            total_samples_in_trace=100,
            total_wall_ms_in_trace=50,
        )
    ]
    unresolved = [
        HotPathSample(
            trace_id="track-a",
            source_format="instruments",
            symbol_name="ThirdParty.LegacyCryptoSigner.sign()",
            cpu_samples=10,
            wall_ms=5,
            total_samples_in_trace=100,
            total_wall_ms_in_trace=50,
        )
    ]

    nodes, edges = await write_snapshot(
        driver,
        project_id="project/test",
        run_id="run-1",
        summary=summary,
        resolved=resolved,
        unresolved=unresolved,
    )

    assert nodes == 3
    assert edges == 1
    assert len(tx.calls) == 5
    assert "SET fn.cpu_share = null" in tx.calls[0][0]
    assert tx.calls[0][1] == {
        "project_id": "project/test",
        "trace_id": "track-a",
    }
