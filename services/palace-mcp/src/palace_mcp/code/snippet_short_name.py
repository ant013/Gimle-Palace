"""Helpers for deriving short symbol names for snippet lookup."""

from __future__ import annotations

from palace_mcp.symbol_identity import (
    canonical_symbol_short_name,
    canonical_symbol_short_name_candidates,
)


def snippet_short_name(value: str) -> str:
    return canonical_symbol_short_name(value)


def snippet_short_name_candidates(value: str) -> list[str]:
    return canonical_symbol_short_name_candidates(value)
