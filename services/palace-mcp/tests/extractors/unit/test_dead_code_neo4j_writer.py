"""Unit tests for dead_code neo4j_writer — Neo4j-safe property serialization."""

from __future__ import annotations

import json

from palace_mcp.extractors.dead_code.models import (
    DeadFinding,
    FindingKind,
    MemberEntry,
    Severity,
)
from palace_mcp.extractors.dead_code.neo4j_writer import _members_json


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
