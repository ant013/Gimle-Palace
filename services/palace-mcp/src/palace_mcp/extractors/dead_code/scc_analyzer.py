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
    """Iterative Tarjan's SCC on the dead-candidate subgraph.

    Explicit-stack implementation — handles 10k+ node graphs without RecursionError.
    Returns SCCs with size >= 2. Caller applies the ≥3 threshold for
    "dead cluster" and ≥50% module coverage for "dead module".
    """
    adj: dict[str, list[str]] = {}
    for qn in candidates:
        adj[qn] = [n for n in graph.adj(qn) if n in candidates]

    index_counter = [0]
    tarjan_stack: list[str] = []
    lowlink: dict[str, int] = {}
    index: dict[str, int] = {}
    on_stack: dict[str, bool] = {}
    sccs: list[frozenset[str]] = []

    for start in candidates:
        if start in index:
            continue

        index[start] = index_counter[0]
        lowlink[start] = index_counter[0]
        index_counter[0] += 1
        tarjan_stack.append(start)
        on_stack[start] = True
        # call_stack entries: (node, next-neighbor-index)
        call_stack: list[tuple[str, int]] = [(start, 0)]

        while call_stack:
            v, i = call_stack[-1]
            neighbors = adj.get(v, [])

            if i < len(neighbors):
                w = neighbors[i]
                call_stack[-1] = (v, i + 1)
                if w not in index:
                    index[w] = index_counter[0]
                    lowlink[w] = index_counter[0]
                    index_counter[0] += 1
                    tarjan_stack.append(w)
                    on_stack[w] = True
                    call_stack.append((w, 0))
                elif on_stack.get(w):
                    lowlink[v] = min(lowlink[v], index[w])
            else:
                call_stack.pop()
                if call_stack:
                    parent = call_stack[-1][0]
                    lowlink[parent] = min(lowlink[parent], lowlink[v])
                if lowlink[v] == index[v]:
                    scc: set[str] = set()
                    while True:
                        w = tarjan_stack.pop()
                        on_stack[w] = False
                        scc.add(w)
                        if w == v:
                            break
                    if len(scc) >= 2:
                        sccs.append(frozenset(scc))

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
