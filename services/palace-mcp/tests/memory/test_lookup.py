"""Tests for palace_mcp.memory.lookup — graphiti-core substrate (N+1a).

Tests focus on the Python-level schema contract (LookupResponse,
LookupResponseItem, warnings field) and _edge_filter_matches logic.
Full integration tests (perform_lookup with Graphiti mock) live in
test_lookup_graphiti.py.
"""

from __future__ import annotations

import pytest

from palace_mcp.memory.lookup import _edge_filter_matches
from palace_mcp.memory.schema import LookupResponse, LookupResponseItem


# ── LookupResponse schema ─────────────────────────────────────────────────────


def test_lookup_response_warnings_empty_by_default() -> None:
    """warnings defaults to [] when no unknown filters exist."""
    resp = LookupResponse(items=[], total_matched=0, query_ms=1)
    assert resp.warnings == []


def test_lookup_response_warnings_populated() -> None:
    """warnings carries unknown-filter messages when provided."""
    msgs = [
        "unknown filter 'bogus' for entity_type 'Issue' \u2014 ignored",
        "unknown filter 'xyz' for entity_type 'Issue' \u2014 ignored",
    ]
    resp = LookupResponse(items=[], total_matched=0, query_ms=1, warnings=msgs)
    assert resp.warnings == msgs


def test_lookup_response_warnings_single_item_with_data() -> None:
    """warnings coexists with regular response items."""
    item = LookupResponseItem(id="abc", type="Agent", properties={"name": "bot"})
    resp = LookupResponse(
        items=[item],
        total_matched=1,
        query_ms=5,
        warnings=["unknown filter 'foo' for entity_type 'Agent' \u2014 ignored"],
    )
    assert len(resp.items) == 1
    assert len(resp.warnings) == 1
    assert "foo" in resp.warnings[0]


# ── _edge_filter_matches ──────────────────────────────────────────────────────


def test_edge_filter_matches_issue_assignee_name_match() -> None:
    related = {"assignee": {"name": "CTO"}, "comments": []}
    assert _edge_filter_matches(related, "Issue", {"assignee_name": "CTO"}) is True


def test_edge_filter_matches_issue_assignee_name_no_match() -> None:
    related = {"assignee": {"name": "MCPEngineer"}, "comments": []}
    assert _edge_filter_matches(related, "Issue", {"assignee_name": "CTO"}) is False


def test_edge_filter_matches_issue_no_assignee() -> None:
    related = {"assignee": None, "comments": []}
    assert _edge_filter_matches(related, "Issue", {"assignee_name": "CTO"}) is False


def test_edge_filter_matches_comment_issue_key_match() -> None:
    related = {"issue": {"key": "GIM-42"}, "author": None}
    assert _edge_filter_matches(related, "Comment", {"issue_key": "GIM-42"}) is True


def test_edge_filter_matches_comment_issue_key_no_match() -> None:
    related = {"issue": {"key": "GIM-1"}, "author": None}
    assert _edge_filter_matches(related, "Comment", {"issue_key": "GIM-42"}) is False


def test_edge_filter_matches_comment_author_name_match() -> None:
    related = {"issue": None, "author": {"name": "CodeReviewer"}}
    assert _edge_filter_matches(related, "Comment", {"author_name": "CodeReviewer"}) is True


def test_edge_filter_matches_comment_author_name_no_match() -> None:
    related = {"issue": None, "author": None}
    assert _edge_filter_matches(related, "Comment", {"author_name": "CodeReviewer"}) is False


def test_edge_filter_matches_empty_filters_always_true() -> None:
    related: dict = {}
    assert _edge_filter_matches(related, "Issue", {}) is True


def test_edge_filter_matches_agent_no_edge_filters() -> None:
    """Agent type has no edge filters; empty filters always match."""
    assert _edge_filter_matches({}, "Agent", {}) is True
