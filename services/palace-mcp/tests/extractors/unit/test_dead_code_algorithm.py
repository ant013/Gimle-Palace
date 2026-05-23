"""Mandatory fixture tests for the dead_code extractor (G0d spec §Tests).

Six mandatory tests from spec §G0d rev3.2:
1. @objc dynamic method never called → safe_to_delete_score ≤ 0.3, severity low
2. NSManagedObject subclass with zero callers → excluded from dead-candidate set
3. Class used only via Mirror(reflecting:) → safe_to_delete_score ≤ 0.5
4. Extension adding protocol conformance to existential-used protocol → ALIVE
5. SwiftUI @AppStorage wrapper type → excluded from dead-candidate set
6. SCC cluster (mutually-dead cycle) → DEAD_SCC_CLUSTER finding, severity HIGH
"""

from __future__ import annotations

from palace_mcp.extractors.dead_code.finding_builder import build_findings
from palace_mcp.extractors.dead_code.scc_analyzer import compute_sccs
from palace_mcp.extractors.dead_code.git_enrichment import (
    compute_safe_to_delete_score,
    enrich_findings_with_git,
)
from palace_mcp.extractors.dead_code.models import (
    FindingKind,
    GraphEdge,
    Severity,
    SymbolGraph,
    SymbolNode,
)
from palace_mcp.extractors.dead_code.reachability import (
    compute_dead_candidates,
    compute_reachable_set,
)
from palace_mcp.extractors.dead_code.seeds import compute_all_seeds


def _make_graph(
    *symbols: SymbolNode, edges: list[GraphEdge] | None = None
) -> SymbolGraph:
    g = SymbolGraph()
    for sym in symbols:
        g.symbols[sym.qualified_name] = sym
    g.edges = edges or []
    g.build_indexes()
    return g


# ---------------------------------------------------------------------------
# Test 1: @objc dynamic method — safe_to_delete_score ≤ 0.3, severity low
# ---------------------------------------------------------------------------


def test_objc_dynamic_method_score_capped_at_0_3() -> None:
    """@objc dynamic method with no callers → score ≤ 0.3, finding severity low."""
    sym = SymbolNode(
        qualified_name="MyModule.LegacyVC.oldAction()",
        kind="function",
        module_name="MyModule",
        is_objc=True,
        is_dynamic=True,
    )
    score = compute_safe_to_delete_score(sym, last_modified_days_ago=400, churn_count=0)
    assert score <= 0.3


def test_objc_dynamic_method_finding_severity_is_low() -> None:
    sym = SymbolNode(
        qualified_name="MyModule.LegacyVC.oldAction()",
        kind="function",
        module_name="MyModule",
        is_objc=True,
        is_dynamic=True,
    )
    # Public seed: one public entry that is reachable; sym has no edges pointing to it
    public_seed = SymbolNode(
        qualified_name="MyModule.AppDelegate",
        kind="class",
        module_name="MyModule",
        is_public=True,
        is_main_entry=True,
    )
    graph = _make_graph(sym, public_seed)
    seeds = compute_all_seeds(graph)
    reachable = compute_reachable_set(graph, seeds)
    dead = compute_dead_candidates(graph, reachable)

    assert sym.qualified_name in dead
    findings = build_findings(graph, dead, project="test")
    sym_findings = [
        f
        for f in findings
        if any(m.qualified_name == sym.qualified_name for m in f.members)
    ]
    assert sym_findings, "expected a finding for the @objc dynamic method"
    f = sym_findings[0]
    assert f.severity == Severity.LOW
    assert f.kind == FindingKind.DEAD_SYMBOL

    enriched = enrich_findings_with_git(
        findings,
        {sym.qualified_name: {"days_ago": 400, "churn_count": 0}},
        graph.symbols,
    )
    sym_enriched = [
        e
        for e in enriched
        if any(m.qualified_name == sym.qualified_name for m in e.members)
    ]
    assert sym_enriched[0].safe_to_delete_score <= 0.3


# ---------------------------------------------------------------------------
# Test 2: NSManagedObject subclass → excluded (dynamic dispatch seed)
# ---------------------------------------------------------------------------


def test_ns_managed_object_subclass_excluded_from_dead_candidates() -> None:
    """class WalletEntity: NSManagedObject with zero SCIP callers → not a dead candidate."""
    wallet_entity = SymbolNode(
        qualified_name="MyModule.WalletEntity",
        kind="class",
        module_name="MyModule",
        is_ns_managed=True,
    )
    public_seed = SymbolNode(
        qualified_name="MyModule.AppDelegate",
        kind="class",
        module_name="MyModule",
        is_public=True,
        is_main_entry=True,
    )
    graph = _make_graph(wallet_entity, public_seed)
    seeds = compute_all_seeds(graph)
    # WalletEntity must be in seeds (dynamic dispatch root)
    assert wallet_entity.qualified_name in seeds

    reachable = compute_reachable_set(graph, seeds)
    dead = compute_dead_candidates(graph, reachable)
    assert wallet_entity.qualified_name not in dead


# ---------------------------------------------------------------------------
# Test 3: Mirror(reflecting:) usage → safe_to_delete_score ≤ 0.5
# ---------------------------------------------------------------------------


def test_mirror_reflecting_usage_caps_score_at_0_5() -> None:
    """Class referenced only via Mirror(reflecting:) → score ≤ 0.5."""
    sym = SymbolNode(
        qualified_name="MyModule.DiagnosticsHelper",
        kind="class",
        module_name="MyModule",
        referenced_via_mirror=True,
    )
    score = compute_safe_to_delete_score(sym, last_modified_days_ago=400, churn_count=0)
    assert score <= 0.5


def test_mirror_reflecting_finding_score_capped() -> None:
    sym = SymbolNode(
        qualified_name="MyModule.DiagnosticsHelper",
        kind="class",
        module_name="MyModule",
        referenced_via_mirror=True,
    )
    public_seed = SymbolNode(
        qualified_name="MyModule.AppDelegate",
        kind="class",
        module_name="MyModule",
        is_public=True,
        is_main_entry=True,
    )
    graph = _make_graph(sym, public_seed)
    seeds = compute_all_seeds(graph)
    reachable = compute_reachable_set(graph, seeds)
    dead = compute_dead_candidates(graph, reachable)

    assert sym.qualified_name in dead
    findings = build_findings(graph, dead, project="test")
    enriched = enrich_findings_with_git(
        findings,
        {sym.qualified_name: {"days_ago": 400, "churn_count": 0}},
        graph.symbols,
    )
    sym_enriched = [
        e
        for e in enriched
        if any(m.qualified_name == sym.qualified_name for m in e.members)
    ]
    assert sym_enriched
    assert sym_enriched[0].safe_to_delete_score <= 0.5


# ---------------------------------------------------------------------------
# Test 4: Extension with existential-used protocol conformance → ALIVE
# ---------------------------------------------------------------------------


def test_extension_alive_when_protocol_used_via_existential() -> None:
    """Extension adding conformance to existential-used protocol → not dead."""
    dead_type = SymbolNode(
        qualified_name="MyModule.LegacyAdapter",
        kind="class",
        module_name="MyModule",
    )
    extension = SymbolNode(
        qualified_name="MyModule.LegacyAdapter+Serializable",
        kind="extension",
        module_name="MyModule",
        extends_protocol="MyModule.Serializable",
    )
    public_seed = SymbolNode(
        qualified_name="MyModule.AppDelegate",
        kind="class",
        module_name="MyModule",
        is_public=True,
        is_main_entry=True,
    )
    # Serializable is used as an existential: [Serializable] or any Serializable
    graph = _make_graph(
        dead_type,
        extension,
        public_seed,
        edges=[
            GraphEdge(
                source=extension.qualified_name,
                target=dead_type.qualified_name,
                kind="EXTENSION_OF",
            ),
            GraphEdge(
                source="caller",  # any node using Serializable as existential
                target="MyModule.Serializable",
                kind="EXISTENTIAL_USE",
            ),
        ],
    )
    seeds = compute_all_seeds(graph)
    reachable = compute_reachable_set(graph, seeds)
    dead = compute_dead_candidates(graph, reachable)

    # Both dead_type and extension are unreachable from public seeds
    assert dead_type.qualified_name in dead
    assert extension.qualified_name in dead

    # Build findings — extension should not appear as dead (alive for dispatch)
    findings = build_findings(graph, dead, project="test")
    dead_finding_members = {m.qualified_name for f in findings for m in f.members}
    assert extension.qualified_name not in dead_finding_members, (
        "Extension with existential-used conformance must be excluded from dead findings"
    )


# ---------------------------------------------------------------------------
# Test 5: SwiftUI @AppStorage type → excluded from dead-candidate set
# ---------------------------------------------------------------------------


def test_tarjan_10k_node_graph_no_recursion_error() -> None:
    """Iterative Tarjan must handle a 10k-node cycle without RecursionError."""
    n = 10_000
    qns = [f"S.node{i}" for i in range(n)]
    g = SymbolGraph()
    for qn in qns:
        g.symbols[qn] = SymbolNode(qualified_name=qn, kind="function", module_name="S")
    # Ring: node0→node1→...→node9999→node0 — one giant SCC
    g.edges = [
        GraphEdge(source=qns[i], target=qns[(i + 1) % n], kind="CALLS")
        for i in range(n)
    ]
    g.build_indexes()

    sccs = compute_sccs(g, frozenset(qns))
    assert len(sccs) == 1
    assert len(sccs[0]) == n


def test_app_storage_type_excluded_from_dead_candidates() -> None:
    """@AppStorage wrapper type with no static refs → in dynamic seeds, not dead."""
    app_storage_type = SymbolNode(
        qualified_name="MyModule.ThemePreferences",
        kind="struct",
        module_name="MyModule",
        is_swift_app_storage=True,
    )
    public_seed = SymbolNode(
        qualified_name="MyModule.AppDelegate",
        kind="class",
        module_name="MyModule",
        is_public=True,
        is_main_entry=True,
    )
    graph = _make_graph(app_storage_type, public_seed)
    seeds = compute_all_seeds(graph)

    assert app_storage_type.qualified_name in seeds

    reachable = compute_reachable_set(graph, seeds)
    dead = compute_dead_candidates(graph, reachable)
    assert app_storage_type.qualified_name not in dead


# ---------------------------------------------------------------------------
# Test 6: SCC cluster — mutually-dead cycle → DEAD_SCC_CLUSTER, severity HIGH
# ---------------------------------------------------------------------------


def test_dead_scc_cluster_cycle_produces_high_severity_finding() -> None:
    """3-node call cycle unreachable from seeds → DEAD_SCC_CLUSTER finding, severity HIGH."""
    foo = SymbolNode(qualified_name="A.foo()", kind="function", module_name="A")
    bar = SymbolNode(qualified_name="A.bar()", kind="function", module_name="A")
    baz = SymbolNode(qualified_name="A.baz()", kind="function", module_name="A")
    public_seed = SymbolNode(
        qualified_name="MyModule.AppDelegate",
        kind="class",
        module_name="MyModule",
        is_public=True,
        is_main_entry=True,
    )
    graph = _make_graph(
        foo,
        bar,
        baz,
        public_seed,
        edges=[
            GraphEdge(source="A.foo()", target="A.bar()", kind="CALLS"),
            GraphEdge(source="A.bar()", target="A.baz()", kind="CALLS"),
            GraphEdge(source="A.baz()", target="A.foo()", kind="CALLS"),
        ],
    )
    seeds = compute_all_seeds(graph)
    reachable = compute_reachable_set(graph, seeds)
    dead = compute_dead_candidates(graph, reachable)

    cycle_names = {foo.qualified_name, bar.qualified_name, baz.qualified_name}
    assert cycle_names <= dead, f"Expected all cycle members in dead set, got {dead}"

    findings = build_findings(graph, dead, project="test")
    scc_findings = [f for f in findings if f.kind == FindingKind.DEAD_SCC_CLUSTER]
    assert scc_findings, "Expected a DEAD_SCC_CLUSTER finding"

    scc_finding = scc_findings[0]
    assert scc_finding.severity == Severity.HIGH
    member_names = {m.qualified_name for m in scc_finding.members}
    assert cycle_names <= member_names, (
        f"Expected all cycle members in finding, got {member_names}"
    )
