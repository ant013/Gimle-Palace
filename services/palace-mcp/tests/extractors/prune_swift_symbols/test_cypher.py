"""Cypher contract tests for prune_swift_symbols."""

from __future__ import annotations

from palace_mcp.extractors.prune_swift_symbols.cypher import PRECHECK_STALE


def test_precheck_returns_counts_no_writes() -> None:
    uppercase = PRECHECK_STALE.upper()

    assert "RETURN STALE_TOTAL, OVERALL_TOTAL" in uppercase
    for keyword in ("CREATE ", "MERGE ", "SET ", "DELETE ", "REMOVE ", "DETACH "):
        assert keyword not in uppercase


def test_precheck_excludes_deprecated_from_overall_total() -> None:
    assert "WHERE (m:Symbol OR m:File)" in PRECHECK_STALE
    assert "AND NOT m:Deprecated" in PRECHECK_STALE
