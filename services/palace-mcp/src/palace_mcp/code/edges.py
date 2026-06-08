"""Shared relationship registry for code graph tools."""

from __future__ import annotations

CALL_EDGES = frozenset({"CALLS"})

KNOWN_NON_CALL_EDGES = frozenset(
    {
        "ASYNC_CALLS",
        "CONCERNS",
        "CONTAINS",
        "DEFINES",
        "DEFINES_METHOD",
        "FILE_CHANGES_WITH",
        "HANDLES",
        "HTTP_CALLS",
        "IMPLEMENTS",
        "IMPORTS",
        "INFORMED_BY",
        "INHERITS",
        "LOCATES_IN",
        "MEMBER_OF",
        "MODIFIES",
        "READS",
        "RESOLVES",
        "TESTS",
        "THROWS",
        "TOUCHES",
        "TRACED_AS",
        "USAGE",
        "USES_TYPE",
        "WRITES",
    }
)
