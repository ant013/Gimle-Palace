"""Step 4: SCC analysis via Tarjan's algorithm (pure Python fallback for GDS).

GDS gds.alpha.scc / gds.scc is the production path (risk-tagged per spec §G0d rev3.2:
Commons Clause licensing — swap to own Johnson's SCC before first paying client).
This module ships Tarjan's as the default to avoid the GDS licensing requirement.
"""

from __future__ import annotations

from palace_mcp.extractors.dead_code.models import SymbolGraph


def compute_sccs(
    graph: SymbolGraph,
    candidates: frozenset[str],
) -> list[frozenset[str]]:
    """Tarjan's SCC on the dead-candidate subgraph.

    Returns SCCs with size >= 2. Caller applies the ≥3 threshold for
    "dead cluster" and ≥50% module coverage for "dead module".
    """
    # Build adjacency restricted to dead candidates
    adj: dict[str, list[str]] = {}
    for qn in candidates:
        neighbors = [n for n in graph.adj(qn) if n in candidates]
        adj[qn] = neighbors

    index_counter = [0]
    stack: list[str] = []
    lowlink: dict[str, int] = {}
    index: dict[str, int] = {}
    on_stack: dict[str, bool] = {}
    sccs: list[frozenset[str]] = []

    def strongconnect(v: str) -> None:
        index[v] = index_counter[0]
        lowlink[v] = index_counter[0]
        index_counter[0] += 1
        stack.append(v)
        on_stack[v] = True

        for w in adj.get(v, []):
            if w not in index:
                strongconnect(w)
                lowlink[v] = min(lowlink[v], lowlink[w])
            elif on_stack.get(w):
                lowlink[v] = min(lowlink[v], index[w])

        if lowlink[v] == index[v]:
            scc: set[str] = set()
            while True:
                w = stack.pop()
                on_stack[w] = False
                scc.add(w)
                if w == v:
                    break
            if len(scc) >= 2:
                sccs.append(frozenset(scc))

    import sys

    # Iterative Tarjan to avoid Python recursion limits on large graphs
    sys.setrecursionlimit(max(sys.getrecursionlimit(), len(candidates) + 1000))
    for v in candidates:
        if v not in index:
            strongconnect(v)

    return sccs


def classify_scc_findings(
    sccs: list[frozenset[str]],
    graph: SymbolGraph,
) -> list[tuple[str, frozenset[str], float | None]]:
    """Map SCCs to finding kinds.

    Returns list of (kind, member_names, module_coverage_ratio_or_None).
    kind is "dead_scc_cluster" (size >= 3) or "dead_scc_pair" (size 2, excluded).
    Module coverage ratio set when SCC covers >= 50% of module top-level types.
    """
    results: list[tuple[str, frozenset[str], float | None]] = []
    for scc in sccs:
        if len(scc) < 3:
            continue
        coverage = _compute_module_coverage(scc, graph)
        kind = "dead_module" if coverage is not None and coverage >= 0.5 else "dead_scc_cluster"
        results.append((kind, scc, coverage))
    return results


def _compute_module_coverage(
    scc: frozenset[str],
    graph: SymbolGraph,
) -> float | None:
    """Ratio of SCC members to all top-level types in their module.

    Returns None if module cannot be determined or has zero types.
    """
    module_names: set[str] = set()
    for qn in scc:
        sym = graph.symbols.get(qn)
        if sym and sym.module_name:
            module_names.add(sym.module_name)

    if len(module_names) != 1:
        return None

    module = next(iter(module_names))
    top_level_types = sum(
        1
        for sym in graph.symbols.values()
        if sym.module_name == module
        and sym.kind in ("class", "struct", "enum", "protocol", "actor")
    )
    if top_level_types == 0:
        return None
    return len(scc) / top_level_types
