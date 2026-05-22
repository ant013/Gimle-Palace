from __future__ import annotations

from typing import Any

import pytest

from palace_mcp.extractors.coding_convention.models import (
    ConventionFinding,
    ConventionViolation,
)
from palace_mcp.extractors.coding_convention.neo4j_writer import (
    replace_project_snapshot,
)


class _FakeTx:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def run(self, query: str, **kwargs: object) -> None:
        self.calls.append((query, dict(kwargs)))


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


def _finding() -> ConventionFinding:
    return ConventionFinding(
        project_id="coding-mini",
        module="WalletCore",
        kind="naming.type_class",
        dominant_choice="upper_camel",
        confidence="heuristic",
        sample_count=5,
        outliers=1,
        run_id="run-1",
    )


def _violation() -> ConventionViolation:
    return ConventionViolation(
        project_id="coding-mini",
        module="WalletCore",
        kind="naming.type_class",
        file="Sources/WalletCore/WALLET_LEGACY.swift",
        start_line=1,
        end_line=1,
        message="Outlier for naming.type_class: WALLET_LEGACY uses upper_snake",
        severity="high",
        run_id="run-1",
    )


@pytest.mark.asyncio
async def test_replace_project_snapshot_uses_single_execute_write() -> None:
    tx = _FakeTx()
    session = _FakeSession(tx)
    driver = _FakeDriver(session)

    await replace_project_snapshot(
        driver,
        project_id="coding-mini",
        findings=[_finding()],
        violations=[_violation()],
    )

    assert session.execute_write_calls == 1
    assert [query for query, _ in tx.calls] == [
        """
MATCH (n)
WHERE (n:Convention OR n:ConventionViolation) AND n.project_id = $project_id
DETACH DELETE n
""",
        "CREATE (n:Convention) SET n += $props",
        "CREATE (n:ConventionViolation) SET n += $props",
    ]
    assert tx.calls[1][1]["props"]["group_id"] == "coding-mini"
    assert tx.calls[2][1]["props"]["group_id"] == "coding-mini"
