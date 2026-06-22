"""Unit tests for dead_code neo4j_writer — Neo4j-safe property serialization."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from palace_mcp.extractors.dead_code.models import (
    DeadFinding,
    FindingKind,
    MemberEntry,
    Severity,
)
from palace_mcp.extractors.dead_code.neo4j_writer import (
    _members_json,
    _write_finding,
    write_dead_findings,
)


def _finding(*members: MemberEntry) -> DeadFinding:
    return DeadFinding(
        kind=FindingKind.DEAD_SYMBOL,
        severity=Severity.LOW,
        project="test-project",
        members=list(members),
        size=len(members),
    )


def test_members_json_returns_string() -> None:
    """members_json must be a str, not list[dict], so Neo4j can store it."""
    finding = _finding(
        MemberEntry(
            qualified_name="Foo/bar()",
            kind="function",
            file_path="Sources/Foo.swift",
        )
    )
    result = _members_json(finding)
    assert isinstance(result, str), f"expected str, got {type(result)}"


def test_members_json_round_trips() -> None:
    """Parsed result matches original member fields."""
    finding = _finding(
        MemberEntry(
            qualified_name="Foo/bar()",
            kind="function",
            file_path="Sources/Foo.swift",
        ),
        MemberEntry(
            qualified_name="Baz/init()",
            kind="function",
            file_path=None,
        ),
    )
    parsed = json.loads(_members_json(finding))
    assert parsed == [
        {
            "file_path": "Sources/Foo.swift",
            "kind": "function",
            "qualified_name": "Foo/bar()",
        },
        {"file_path": None, "kind": "function", "qualified_name": "Baz/init()"},
    ]


def test_members_json_empty_finding() -> None:
    finding = _finding()
    assert _members_json(finding) == "[]"


@pytest.mark.asyncio
async def test_write_finding_includes_group_id() -> None:
    """group_id must appear in props so APOC require_group_id trigger passes."""
    finding = _finding()
    group_id = "project/bitcoin-core"

    consumed = MagicMock()
    consumed.counters.nodes_created = 1
    consumed.counters.properties_set = 3
    consumed.counters.relationships_created = 0

    result_mock = AsyncMock()
    result_mock.consume.return_value = consumed

    tx = AsyncMock()
    tx.run.return_value = result_mock

    await _write_finding(tx, finding, group_id)

    # First tx.run call is the batched UNWIND merge over row.props.
    first_call_kwargs = tx.run.call_args_list[0].kwargs
    props_passed = first_call_kwargs["rows"][0]["props"]
    assert props_passed["group_id"] == group_id, (
        f"group_id missing from DeadFinding props; got keys: {list(props_passed)}"
    )


class _FakeCounters:
    def __init__(
        self,
        *,
        nodes_created: int = 0,
        relationships_created: int = 0,
        properties_set: int = 0,
        nodes_deleted: int = 0,
    ) -> None:
        self.nodes_created = nodes_created
        self.relationships_created = relationships_created
        self.properties_set = properties_set
        self.nodes_deleted = nodes_deleted


class _FakeResult:
    def __init__(self, counters: _FakeCounters) -> None:
        self._counters = counters

    async def consume(self) -> MagicMock:
        consumed = MagicMock()
        consumed.counters = self._counters
        return consumed


class _FakeTx:
    def __init__(self, *, nodes_deleted: int = 0) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.nodes_deleted = nodes_deleted

    async def run(self, query: str, **kwargs: object) -> _FakeResult:
        self.calls.append((query, dict(kwargs)))

        if "DETACH DELETE f" in query:
            return _FakeResult(_FakeCounters(nodes_deleted=self.nodes_deleted))
        if "UNWIND $rows AS row" in query:
            rows = kwargs["rows"]
            assert isinstance(rows, list)
            return _FakeResult(
                _FakeCounters(
                    nodes_created=len(rows),
                    properties_set=len(rows) * 3,
                )
            )
        if "UNWIND $edges AS edge" in query:
            edges = kwargs["edges"]
            assert isinstance(edges, list)
            return _FakeResult(
                _FakeCounters(
                    nodes_created=len(edges),
                    relationships_created=len(edges),
                )
            )

        raise AssertionError(f"unexpected query: {query}")


class _FakeSession:
    def __init__(self, tx: _FakeTx) -> None:
        self.tx = tx
        self.execute_write_calls = 0

    async def __aenter__(self) -> "_FakeSession":
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> bool:
        return False

    async def execute_write(self, fn: object, *args: object) -> object:
        self.execute_write_calls += 1
        return await fn(self.tx, *args)


class _FakeDriver:
    def __init__(self, session: _FakeSession) -> None:
        self._session = session

    def session(self) -> _FakeSession:
        return self._session


@pytest.mark.asyncio
async def test_write_dead_findings_batches_findings_into_one_transaction() -> None:
    tx = _FakeTx()
    session = _FakeSession(tx)
    driver = _FakeDriver(session)

    summary = await write_dead_findings(
        driver=driver,
        findings=[
            _finding(
                MemberEntry(
                    qualified_name="Foo/bar()",
                    kind="function",
                    file_path="Sources/Foo.swift",
                )
            ),
            _finding(
                MemberEntry(
                    qualified_name="Baz/qux()",
                    kind="function",
                    file_path="Sources/Baz.swift",
                )
            ),
        ],
        group_id="project/bitcoin-core",
    )

    assert session.execute_write_calls == 2
    assert summary.nodes_deleted == 0


@pytest.mark.asyncio
async def test_write_dead_findings_skips_empty_batch_and_evicts_stale_findings() -> (
    None
):
    tx = _FakeTx(nodes_deleted=2)
    session = _FakeSession(tx)
    driver = _FakeDriver(session)

    summary = await write_dead_findings(
        driver=driver,
        findings=[],
        group_id="project/bitcoin-core",
    )

    assert session.execute_write_calls == 1
    assert len(tx.calls) == 1
    assert "DETACH DELETE f" in tx.calls[0][0]
    assert summary == type(summary)(nodes_deleted=2)
