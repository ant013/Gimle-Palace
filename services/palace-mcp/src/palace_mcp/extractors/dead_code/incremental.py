from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Set as AbstractSet

from palace_mcp.extractors.dead_code.models import SymbolGraph
from palace_mcp.extractors.foundation.delta_resolution import ResolvedDelta


def build_affected_symbol_set(
    *,
    graph: SymbolGraph,
    delta: ResolvedDelta,
) -> set[str]:
    roots: set[str] = set()
    for edge_delta in delta.edge_deltas:
        roots.add(edge_delta.target)
    for seed_delta in delta.seed_deltas:
        roots.add(seed_delta.qualified_name)
    for symbol_delta in delta.symbol_deltas:
        if symbol_delta.change_kind in {"added", "moved"}:
            roots.add(symbol_delta.qualified_name)

    affected = _forward_closure(graph, roots)
    for symbol_delta in delta.symbol_deltas:
        if symbol_delta.change_kind == "moved":
            affected.add(symbol_delta.qualified_name)
    return affected


def compute_incremental_reachable(
    *,
    graph: SymbolGraph,
    delta: ResolvedDelta,
    previous_live: set[str],
    seeds: AbstractSet[str],
) -> tuple[frozenset[str], set[str]]:
    affected = build_affected_symbol_set(graph=graph, delta=delta)
    if not affected:
        return frozenset(previous_live | set(seeds)), set()

    live_outside = (previous_live - affected) & set(graph.symbols)
    frontier = (live_outside | seeds) & set(graph.symbols)
    reachable_in_affected = _forward_closure(graph, frontier, limit_to=affected)
    reachable = live_outside | seeds | reachable_in_affected
    return frozenset(reachable & set(graph.symbols)), affected


def should_fallback_to_full(
    *,
    affected_count: int,
    total_symbols: int,
    threshold_ratio: float,
) -> bool:
    if total_symbols <= 0:
        return False
    return (affected_count / total_symbols) > threshold_ratio


def _forward_closure(
    graph: SymbolGraph,
    roots: Iterable[str],
    *,
    limit_to: set[str] | None = None,
) -> set[str]:
    allowed = (
        set(graph.symbols) if limit_to is None else set(limit_to) & set(graph.symbols)
    )
    queue: deque[str] = deque()
    seen: set[str] = set()

    for root in roots:
        if root not in graph.symbols:
            continue
        if limit_to is None or root in allowed:
            seen.add(root)
        queue.append(root)

    while queue:
        source = queue.popleft()
        for target in graph.adj(source):
            if target not in graph.symbols:
                continue
            if target in seen:
                continue
            if limit_to is not None and target not in allowed:
                continue
            seen.add(target)
            queue.append(target)

    return seen
