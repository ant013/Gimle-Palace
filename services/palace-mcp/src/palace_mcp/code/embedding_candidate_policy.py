"""Deterministic embedding candidate ordering (spec §7.6).

When PALACE_EMBEDDING_MAX_SYMBOLS is set, candidates are sorted into 7 buckets:
  0  project definitions/declarations
  1  workspace_package definitions/declarations
  2  project non-accessor methods/functions
  3  workspace_package non-accessor methods/functions
  4  dependency public API
  5  generated / derived
  6  sdk

Within each bucket rows are ordered by (file_path, qualified_name).
Accessor and synthetic symbols are skipped unless no better candidates remain.
"""

from __future__ import annotations

from typing import TypedDict

from palace_mcp.code.semantic_contract import EmbeddingCoverage


class CandidateRow(TypedDict):
    qualified_name: str
    kind: str | None
    file_path: str | None
    source_scope: str | None


_DEFINITION_KINDS = frozenset({
    "class",
    "struct",
    "enum",
    "protocol",
    "interface",
    "type_alias",
    "typedef",
    "trait",
    "namespace",
    "module",
    "extension",
    "object",
    "record",
})

_ACCESSOR_KINDS = frozenset({
    "accessor",
    "getter",
    "setter",
})


def _is_accessor(row: CandidateRow) -> bool:
    kind = (row.get("kind") or "").lower()
    if kind in _ACCESSOR_KINDS:
        return True
    qname = row.get("qualified_name") or ""
    return "$" in qname


def _is_definition(row: CandidateRow) -> bool:
    kind = (row.get("kind") or "").lower()
    return kind in _DEFINITION_KINDS


def _bucket(row: CandidateRow) -> int | None:
    """Return bucket index or None to skip entirely."""
    scope = (row.get("source_scope") or "").lower()
    accessor = _is_accessor(row)

    if scope == "project":
        if accessor:
            return None
        return 0 if _is_definition(row) else 2

    if scope == "workspace_package":
        if accessor:
            return None
        return 1 if _is_definition(row) else 3

    if scope == "dependency":
        return None if accessor else 4

    if scope in ("generated", "derived"):
        return 5

    if scope == "sdk":
        return 6

    # unknown scope → treat as dependency
    return None if accessor else 4


def apply_policy(
    rows: list[CandidateRow],
    max_symbols: int | None,
) -> tuple[list[CandidateRow], EmbeddingCoverage]:
    """Sort by policy buckets and truncate at max_symbols.

    Returns (selected_rows, coverage_metadata).
    """
    keyed: list[tuple[int, str, str, CandidateRow]] = []
    skipped = 0

    for row in rows:
        b = _bucket(row)
        if b is None:
            skipped += 1
            continue
        keyed.append(
            (b, row.get("file_path") or "", row.get("qualified_name") or "", row)
        )

    keyed.sort(key=lambda t: (t[0], t[1], t[2]))

    bounded = max_symbols is not None
    if bounded and len(keyed) > max_symbols:  # type: ignore[operator]
        selected = [t[3] for t in keyed[:max_symbols]]
    else:
        selected = [t[3] for t in keyed]

    scope_counts: dict[str, int] = {}
    for row in selected:
        s = row.get("source_scope") or "unknown"
        scope_counts[s] = scope_counts.get(s, 0) + 1

    coverage = EmbeddingCoverage(
        bounded=bounded,
        max_symbols=max_symbols,
        embedded_symbols=len(selected),
        eligible_symbols=len(keyed) + skipped,
        source_scope_counts=scope_counts,
    )
    return selected, coverage
