"""Unit tests for dead_code models and severity ranking."""

from __future__ import annotations

import pytest

from palace_mcp.extractors.dead_code.models import (
    DeadFinding,
    FindingKind,
    MemberEntry,
    Severity,
    SymbolGraph,
    SymbolNode,
)
from palace_mcp.extractors.dead_code.severity import rank_severity


def test_rank_severity_dead_module_is_critical() -> None:
    assert rank_severity(FindingKind.DEAD_MODULE) == Severity.CRITICAL


def test_rank_severity_scc_cluster_is_high() -> None:
    assert rank_severity(FindingKind.DEAD_SCC_CLUSTER) == Severity.HIGH


def test_rank_severity_extension_chain_is_medium() -> None:
    assert rank_severity(FindingKind.DEAD_EXTENSION_CHAIN) == Severity.MEDIUM


def test_rank_severity_single_symbol_is_low() -> None:
    assert rank_severity(FindingKind.DEAD_SYMBOL) == Severity.LOW


def test_dead_finding_finding_id_auto_generated() -> None:
    f = DeadFinding(
        kind=FindingKind.DEAD_SYMBOL,
        severity=Severity.LOW,
        project="test",
        members=[MemberEntry(qualified_name="Foo.bar()", kind="function")],
        size=1,
    )
    assert f.finding_id.startswith("fd_")


def test_dead_finding_safe_to_delete_score_bounds() -> None:
    with pytest.raises(ValueError):
        DeadFinding(
            kind=FindingKind.DEAD_SYMBOL,
            severity=Severity.LOW,
            project="test",
            members=[MemberEntry(qualified_name="Foo.bar()", kind="function")],
            size=1,
            safe_to_delete_score=1.5,
        )


def test_symbol_graph_build_indexes_adjacency() -> None:
    from palace_mcp.extractors.dead_code.models import GraphEdge

    g = SymbolGraph()
    g.symbols["A"] = SymbolNode(qualified_name="A", kind="class")
    g.symbols["B"] = SymbolNode(qualified_name="B", kind="class")
    g.edges = [GraphEdge(source="A", target="B", kind="CALLS")]
    g.build_indexes()
    assert "B" in g.adj("A")


def test_symbol_graph_existential_protocol_tracked() -> None:
    from palace_mcp.extractors.dead_code.models import GraphEdge

    g = SymbolGraph()
    g.symbols["Proto"] = SymbolNode(qualified_name="Proto", kind="protocol")
    g.edges = [GraphEdge(source="caller", target="Proto", kind="EXISTENTIAL_USE")]
    g.build_indexes()
    assert g.used_via_existential("Proto")
    assert not g.used_via_existential("OtherProto")


def test_symbol_graph_extensions_of() -> None:
    from palace_mcp.extractors.dead_code.models import GraphEdge

    g = SymbolGraph()
    g.symbols["Type"] = SymbolNode(qualified_name="Type", kind="class")
    g.symbols["Ext"] = SymbolNode(qualified_name="Ext", kind="extension")
    g.edges = [GraphEdge(source="Ext", target="Type", kind="EXTENSION_OF")]
    g.build_indexes()
    assert g.extensions_of("Type") == ["Ext"]


def test_finding_id_deterministic_across_runs():
    """Regression: GIM-785 CXCR found DeadFinding writes are append-only
    across reruns because finding_id was random UUID per run. Now it's a
    deterministic hash of (project, kind, sorted member qnames) — re-runs
    produce identical finding_id, MERGE updates same node, no inflation."""
    from palace_mcp.extractors.dead_code.models import (
        DeadFinding,
        FindingKind,
        MemberEntry,
        Severity,
    )

    m1 = MemberEntry(qualified_name="Mod.Foo", kind="struct")
    m2 = MemberEntry(qualified_name="Mod.Bar", kind="class")

    f1 = DeadFinding(
        kind=FindingKind.DEAD_SCC_CLUSTER,
        severity=Severity.MEDIUM,
        project="myproj",
        members=[m1, m2],
        size=2,
    )
    # Order-independent: members list reversed produces same id
    f2 = DeadFinding(
        kind=FindingKind.DEAD_SCC_CLUSTER,
        severity=Severity.MEDIUM,
        project="myproj",
        members=[m2, m1],
        size=2,
    )
    assert f1.finding_id == f2.finding_id
    assert f1.finding_id.startswith("fd_")
    assert len(f1.finding_id) == 19  # fd_ + 16 hex chars

    # Different project → different id
    f3 = DeadFinding(
        kind=FindingKind.DEAD_SCC_CLUSTER,
        severity=Severity.MEDIUM,
        project="otherproj",
        members=[m1, m2],
        size=2,
    )
    assert f3.finding_id != f1.finding_id

    # Different kind → different id
    f4 = DeadFinding(
        kind=FindingKind.DEAD_MODULE,
        severity=Severity.MEDIUM,
        project="myproj",
        members=[m1, m2],
        size=2,
    )
    assert f4.finding_id != f1.finding_id

    # Explicit finding_id overrides auto-derive
    f5 = DeadFinding(
        finding_id="fd_custom",
        kind=FindingKind.DEAD_SYMBOL,
        severity=Severity.LOW,
        project="myproj",
        members=[m1],
        size=1,
    )
    assert f5.finding_id == "fd_custom"
