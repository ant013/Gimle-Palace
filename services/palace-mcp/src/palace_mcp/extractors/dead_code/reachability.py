"""Step 2: BFS reachability from union(public seeds, dynamic seeds)."""

from __future__ import annotations

from collections import deque

from palace_mcp.extractors.dead_code.models import SymbolGraph


def compute_reachable_set(
    graph: SymbolGraph,
    seeds: frozenset[str],
) -> frozenset[str]:
    """BFS from seeds through CALLS/REFERENCES/EXTENDS/CONFORMS_TO edges.

    Returns the full set of reachable qualified names. Any symbol NOT in
    this set is a dead-candidate for further analysis.
    """
    visited: set[str] = set()
    queue: deque[str] = deque(seeds)
    while queue:
        current = queue.popleft()
        if current in visited:
            continue
        visited.add(current)
        for neighbor in graph.adj(current):
            if neighbor not in visited and neighbor in graph.symbols:
                queue.append(neighbor)
    return frozenset(visited)


def compute_dead_candidates(
    graph: SymbolGraph,
    reachable: frozenset[str],
) -> frozenset[str]:
    """Return qualified names of symbols not reachable from any seed."""
    return frozenset(qn for qn in graph.symbols if qn not in reachable)
