from __future__ import annotations

from typing import Any

import pytest

from palace_mcp.extractors.testability_di.models import (
    DiPattern,
    TestDouble as DoubleModel,
    UntestableSite,
)
from palace_mcp.extractors.testability_di.neo4j_writer import replace_project_snapshot


class _FakeTx:
    def __init__(self) -> None:
        self.queries: list[str] = []

    async def run(self, query: str, **_: object) -> None:
        self.queries.append(query)


class _FakeSession:
    def __init__(self, tx: _FakeTx) -> None:
        self.tx = tx
        self.execute_write_calls = 0

    async def __aenter__(self) -> "_FakeSession":
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> bool:
        return False

    async def execute_write(self, fn: Any, *args: object, **kwargs: object) -> None:
        self.execute_write_calls += 1
        await fn(self.tx, *args, **kwargs)


class _FakeDriver:
    def __init__(self, session: _FakeSession) -> None:
        self._session = session

    def session(self) -> _FakeSession:
        return self._session


def _pattern() -> DiPattern:
    return DiPattern(
        project_id="project/wallet",
        module="WalletKit",
        language="swift",
        style="init_injection",
        framework=None,
        sample_count=2,
        outliers=0,
        confidence="heuristic",
        run_id="run-1",
    )


def _double() -> DoubleModel:
    return DoubleModel(
        project_id="project/wallet",
        module="WalletKit",
        language="swift",
        kind="fake",
        target_symbol="WalletService",
        test_file="Tests/WalletKitTests/WalletServiceTests.swift",
        run_id="run-1",
    )


def _site() -> UntestableSite:
    return UntestableSite(
        project_id="project/wallet",
        module="WalletKit",
        language="swift",
        file="Sources/WalletKit/WalletManager.swift",
        start_line=8,
        end_line=8,
        category="direct_clock",
        symbol_referenced="Date()",
        severity="medium",
        message="Direct clock access should be abstracted for tests.",
        run_id="run-1",
    )


@pytest.mark.asyncio
async def test_replace_project_snapshot_writes_only_testability_labels() -> None:
    tx = _FakeTx()
    session = _FakeSession(tx)
    driver = _FakeDriver(session)

    await replace_project_snapshot(
        driver,
        project_id="project/wallet",
        run_id="run-1",
        di_patterns=[_pattern()],
        test_doubles=[_double()],
        untestable_sites=[_site()],
    )

    assert session.execute_write_calls == 1
    assert "DiPattern" in tx.queries[0]
    assert "TestDouble" in tx.queries[0]
    assert "UntestableSite" in tx.queries[0]
    assert "Convention" not in tx.queries[0]
    assert any("CREATE (d:DiPattern)" in query for query in tx.queries)
    assert any("CREATE (d:TestDouble)" in query for query in tx.queries)
    assert any("CREATE (u:UntestableSite)" in query for query in tx.queries)
    assert any("MATCH (run:IngestRun {id: $run_id})" in query for query in tx.queries)
