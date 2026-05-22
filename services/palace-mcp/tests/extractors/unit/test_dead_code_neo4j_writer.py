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
from palace_mcp.extractors.dead_code.neo4j_writer import _members_json, _write_finding


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
        {"file_path": "Sources/Foo.swift", "kind": "function", "qualified_name": "Foo/bar()"},
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

    # First tx.run call is the MERGE (f:DeadFinding ...) SET f += $props
    first_call_kwargs = tx.run.call_args_list[0].kwargs
    props_passed = first_call_kwargs["props"]
    assert props_passed["group_id"] == group_id, (
        f"group_id missing from DeadFinding props; got keys: {list(props_passed)}"
    )
