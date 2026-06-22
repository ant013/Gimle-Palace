from __future__ import annotations

from palace_mcp.extractors.dead_code.incremental import (
    build_affected_symbol_set,
    compute_incremental_reachable,
    should_fallback_to_full,
)
from palace_mcp.extractors.dead_code.models import GraphEdge, SymbolGraph, SymbolNode
from palace_mcp.extractors.foundation.delta_resolution import (
    EdgeDelta,
    ResolvedDelta,
    SeedDelta,
    SymbolDelta,
)


def _graph(*symbols: SymbolNode, edges: list[GraphEdge]) -> SymbolGraph:
    graph = SymbolGraph()
    for symbol in symbols:
        graph.symbols[symbol.qualified_name] = symbol
    graph.edges = edges
    graph.build_indexes()
    return graph


def test_incremental_reachable_keeps_diamond_target_live() -> None:
    a = SymbolNode("A", "class", is_public=True, is_main_entry=True)
    b = SymbolNode("B", "class")
    c = SymbolNode("C", "class")
    d = SymbolNode("D", "class")
    graph = _graph(
        a,
        b,
        c,
        d,
        edges=[
            GraphEdge("A", "B", "CALLS"),
            GraphEdge("A", "C", "CALLS"),
            GraphEdge("C", "D", "CALLS"),
        ],
    )
    delta = ResolvedDelta(
        symbol_deltas=(),
        edge_deltas=(EdgeDelta("B", "D", "CALLS", "removed"),),
        seed_deltas=(),
        public_api_deltas=(),
    )

    reachable, affected = compute_incremental_reachable(
        graph=graph,
        delta=delta,
        previous_live={"A", "B", "C", "D"},
        seeds={"A"},
    )

    assert affected == {"D"}
    assert "D" in reachable


def test_incremental_reachable_keeps_cycle_live_via_alternate_in_edge() -> None:
    a = SymbolNode("A", "class", is_public=True, is_main_entry=True)
    x = SymbolNode("X", "class", is_public=True, is_main_entry=True)
    b = SymbolNode("B", "class")
    c = SymbolNode("C", "class")
    graph = _graph(
        a,
        x,
        b,
        c,
        edges=[
            GraphEdge("X", "C", "CALLS"),
            GraphEdge("C", "B", "CALLS"),
            GraphEdge("B", "C", "CALLS"),
        ],
    )
    delta = ResolvedDelta(
        symbol_deltas=(),
        edge_deltas=(EdgeDelta("A", "B", "CALLS", "removed"),),
        seed_deltas=(),
        public_api_deltas=(),
    )

    reachable, affected = compute_incremental_reachable(
        graph=graph,
        delta=delta,
        previous_live={"A", "X", "B", "C"},
        seeds={"A", "X"},
    )

    assert affected == {"B", "C"}
    assert {"B", "C"} <= reachable


def test_incremental_reachable_dead_gains_ref_from_dead_stays_dead() -> None:
    a = SymbolNode("A", "class", is_public=True, is_main_entry=True)
    dead_source = SymbolNode("DeadSource", "class")
    dead_target = SymbolNode("DeadTarget", "class")
    graph = _graph(
        a,
        dead_source,
        dead_target,
        edges=[GraphEdge("DeadSource", "DeadTarget", "CALLS")],
    )
    delta = ResolvedDelta(
        symbol_deltas=(),
        edge_deltas=(EdgeDelta("DeadSource", "DeadTarget", "CALLS", "added"),),
        seed_deltas=(),
        public_api_deltas=(),
    )

    reachable, _affected = compute_incremental_reachable(
        graph=graph,
        delta=delta,
        previous_live={"A"},
        seeds={"A"},
    )

    assert "DeadSource" not in reachable
    assert "DeadTarget" not in reachable


def test_build_affected_symbol_set_includes_moved_symbol() -> None:
    wallet = SymbolNode("Wallet", "class")
    graph = _graph(wallet, edges=[])
    delta = ResolvedDelta(
        symbol_deltas=(
            SymbolDelta(
                qualified_name="Wallet",
                change_kind="moved",
                previous_file_path="Sources/Wallet.swift",
                current_file_path="Sources/Core/Wallet.swift",
            ),
        ),
        edge_deltas=(),
        seed_deltas=(),
        public_api_deltas=(),
    )

    affected = build_affected_symbol_set(graph=graph, delta=delta)

    assert affected == {"Wallet"}


def test_incremental_reachable_handles_seed_loss() -> None:
    a = SymbolNode("A", "class", is_public=True, is_main_entry=True)
    b = SymbolNode("B", "class")
    graph = _graph(a, b, edges=[GraphEdge("A", "B", "CALLS")])
    delta = ResolvedDelta(
        symbol_deltas=(),
        edge_deltas=(),
        seed_deltas=(SeedDelta("A", True, False),),
        public_api_deltas=(),
    )

    reachable, affected = compute_incremental_reachable(
        graph=graph,
        delta=delta,
        previous_live={"A", "B"},
        seeds=set(),
    )

    assert affected == {"A", "B"}
    assert reachable == set()


def test_should_fallback_to_full_when_threshold_exceeded() -> None:
    assert should_fallback_to_full(
        affected_count=21,
        total_symbols=100,
        threshold_ratio=0.2,
    )
    assert not should_fallback_to_full(
        affected_count=20,
        total_symbols=100,
        threshold_ratio=0.2,
    )
