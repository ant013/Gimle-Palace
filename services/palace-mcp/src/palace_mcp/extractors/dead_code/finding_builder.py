"""Build DeadFinding objects from algorithm outputs."""

from __future__ import annotations

from palace_mcp.extractors.dead_code.extension_chain import (
    compute_extension_chain_findings,
    find_alive_extensions,
)
from palace_mcp.extractors.dead_code.models import (
    DeadFinding,
    FindingKind,
    MemberEntry,
    SymbolGraph,
)
from palace_mcp.extractors.dead_code.scc_analyzer import classify_scc_findings, compute_sccs
from palace_mcp.extractors.dead_code.severity import rank_severity


def build_findings(
    graph: SymbolGraph,
    dead_candidates: frozenset[str],
    project: str,
) -> list[DeadFinding]:
    """Run Steps 3-5 and assemble all findings.

    Step 3: extension chain pass
    Step 4: SCC analysis
    Step 5: severity ranking

    Returns unsorted list of DeadFinding objects (git enrichment is applied
    separately by the extractor after this call).
    """
    # Step 3: extension chain
    alive_extensions = find_alive_extensions(graph, dead_candidates)
    remaining = frozenset(qn for qn in dead_candidates if qn not in alive_extensions)

    findings: list[DeadFinding] = []

    # Extension chain findings (medium severity)
    ext_chain_data = compute_extension_chain_findings(graph, remaining)
    for target_type_qn, dead_ext_qns, conformance_checks in ext_chain_data:
        members = _build_members(graph, dead_ext_qns)
        kind = FindingKind.DEAD_EXTENSION_CHAIN
        findings.append(
            DeadFinding(
                kind=kind,
                severity=rank_severity(kind),
                project=project,
                members=members,
                size=len(members),
                target_dead_type=target_type_qn,
                protocol_conformance_checks=conformance_checks,
                evidence_query=_evidence_query(findings, members),
            )
        )

    # Step 4: SCC on remaining dead candidates
    ext_chain_members = frozenset(
        m.qualified_name for f in findings for m in f.members
    )
    scc_candidates = frozenset(qn for qn in remaining if qn not in ext_chain_members)
    sccs = compute_sccs(graph, scc_candidates)
    scc_finding_data = classify_scc_findings(sccs, graph)

    scc_covered: set[str] = set()
    for kind_str, scc_members, coverage in scc_finding_data:
        kind = FindingKind(kind_str)
        members = _build_members(graph, list(scc_members))
        f = DeadFinding(
            kind=kind,
            severity=rank_severity(kind),
            project=project,
            members=members,
            size=len(members),
            module_coverage_ratio=coverage,
            evidence_query=_evidence_query(findings, members),
        )
        findings.append(f)
        scc_covered.update(scc_members)

    # Step 5: single-symbol findings for remaining dead candidates
    single_candidates = frozenset(
        qn
        for qn in remaining
        if qn not in ext_chain_members and qn not in scc_covered
    )
    for qn in sorted(single_candidates):
        sym = graph.symbols.get(qn)
        if sym is None:
            continue
        member = MemberEntry(
            qualified_name=qn,
            kind=sym.kind,
            file_path=sym.file_path,
        )
        kind = FindingKind.DEAD_SYMBOL
        f = DeadFinding(
            kind=kind,
            severity=rank_severity(kind),
            project=project,
            members=[member],
            size=1,
            evidence_query=f"MATCH (f:DeadFinding {{finding_id: '?'}})-[:DEAD_SYMBOL]->(s) WHERE s.qualified_name = '{qn}' RETURN s",
        )
        findings.append(f)

    return findings


def _build_members(graph: SymbolGraph, qns: list[str]) -> list[MemberEntry]:
    members: list[MemberEntry] = []
    for qn in sorted(qns):
        sym = graph.symbols.get(qn)
        members.append(
            MemberEntry(
                qualified_name=qn,
                kind=sym.kind if sym else "unknown",
                file_path=sym.file_path if sym else None,
            )
        )
    return members


def _evidence_query(existing: list[DeadFinding], members: list[MemberEntry]) -> str:
    if not members:
        return ""
    return (
        f"MATCH (f:DeadFinding)-[:DEAD_SYMBOL]->(s:Symbol) "
        f"WHERE s.qualified_name IN {[m.qualified_name for m in members[:3]]!r} RETURN f, s"
    )
