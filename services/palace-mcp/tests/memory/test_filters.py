"""Tests for Python-level filter resolution in palace_mcp.memory.lookup.

Replaces the Cypher-clause tests (filters.py deleted in N+1a).
Verifies that _DIRECT_FILTER_KEYS / _EDGE_FILTER_KEYS / _apply_direct_filter
behave correctly.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from palace_mcp.memory.lookup import (
    _DIRECT_FILTER_KEYS,
    _EDGE_FILTER_KEYS,
    _apply_direct_filter,
)
from graphiti_core.nodes import EntityNode


def _make_node(attributes: dict) -> MagicMock:
    node = MagicMock(spec=EntityNode)
    node.attributes = attributes
    return node


# ── Direct filter key whitelists ─────────────────────────────────────────────


def test_issue_direct_filter_keys_include_key_and_status() -> None:
    assert "key" in _DIRECT_FILTER_KEYS["Issue"]
    assert "status" in _DIRECT_FILTER_KEYS["Issue"]


def test_issue_direct_filter_keys_include_date_range() -> None:
    assert "source_updated_at_gte" in _DIRECT_FILTER_KEYS["Issue"]
    assert "source_updated_at_lte" in _DIRECT_FILTER_KEYS["Issue"]


def test_issue_edge_filter_keys_include_assignee_name() -> None:
    assert "assignee_name" in _EDGE_FILTER_KEYS["Issue"]


def test_comment_edge_filter_keys_include_issue_key_and_author() -> None:
    assert "issue_key" in _EDGE_FILTER_KEYS["Comment"]
    assert "author_name" in _EDGE_FILTER_KEYS["Comment"]


def test_agent_has_no_edge_filter_keys() -> None:
    assert len(_EDGE_FILTER_KEYS["Agent"]) == 0


# ── _apply_direct_filter ──────────────────────────────────────────────────────


def test_apply_direct_filter_exact_match() -> None:
    nodes = [
        _make_node({"status": "done"}),
        _make_node({"status": "todo"}),
        _make_node({"status": "done"}),
    ]
    result = _apply_direct_filter(nodes, "status", "done")
    assert len(result) == 2


def test_apply_direct_filter_gte() -> None:
    nodes = [
        _make_node({"source_updated_at": "2024-01-01T00:00:00+00:00"}),
        _make_node({"source_updated_at": "2024-06-01T00:00:00+00:00"}),
        _make_node({"source_updated_at": "2024-12-01T00:00:00+00:00"}),
    ]
    result = _apply_direct_filter(nodes, "source_updated_at_gte", "2024-06-01T00:00:00+00:00")
    assert len(result) == 2  # June and December


def test_apply_direct_filter_lte() -> None:
    nodes = [
        _make_node({"source_updated_at": "2024-01-01T00:00:00+00:00"}),
        _make_node({"source_updated_at": "2024-06-01T00:00:00+00:00"}),
        _make_node({"source_updated_at": "2024-12-01T00:00:00+00:00"}),
    ]
    result = _apply_direct_filter(nodes, "source_updated_at_lte", "2024-06-01T00:00:00+00:00")
    assert len(result) == 2  # January and June


def test_apply_direct_filter_empty_input() -> None:
    result = _apply_direct_filter([], "status", "done")
    assert result == []


def test_apply_direct_filter_no_match() -> None:
    nodes = [_make_node({"key": "GIM-1"}), _make_node({"key": "GIM-2"})]
    result = _apply_direct_filter(nodes, "key", "GIM-99")
    assert result == []


def test_apply_direct_filter_missing_attr_excluded() -> None:
    nodes = [
        _make_node({}),  # no 'key' attr
        _make_node({"key": "GIM-5"}),
    ]
    result = _apply_direct_filter(nodes, "key", "GIM-5")
    assert len(result) == 1


def test_apply_direct_filter_none_attr_excluded_in_gte() -> None:
    """None attribute values are treated as '' for comparison — should be excluded."""
    nodes = [
        _make_node({"source_updated_at": None}),
        _make_node({"source_updated_at": "2024-06-01T00:00:00+00:00"}),
    ]
    result = _apply_direct_filter(nodes, "source_updated_at_gte", "2024-01-01T00:00:00+00:00")
    assert len(result) == 1  # None treated as '' which is < cutoff
