"""Step 6: git_history enrichment for safe_to_delete_score."""

from __future__ import annotations

from typing import Any

from palace_mcp.extractors.dead_code.models import DeadFinding, SymbolNode


def compute_safe_to_delete_score(
    sym: SymbolNode,
    *,
    last_modified_days_ago: int | None = None,
    has_external_refs: bool = False,
    churn_count: int = 0,
) -> float:
    """Compute safe_to_delete_score ∈ [0.0, 1.0).

    Higher = safer to delete. Hard caps per spec §G0d rev3.2 Step 6:
    - @objc/dynamic/NSManaged/propertyWrapper/macro: cap < 1.0 (≤ 0.3 for test 1)
    - Mirror usage: cap ≤ 0.5
    - Base score driven by age (last_modified_days_ago) and churn
    """
    if _is_dynamic_annotation_risk(sym):
        base = _base_score(last_modified_days_ago, churn_count)
        return min(base, 0.3)

    if sym.referenced_via_mirror:
        base = _base_score(last_modified_days_ago, churn_count)
        return min(base, 0.5)

    score = _base_score(last_modified_days_ago, churn_count)
    if has_external_refs:
        score *= 0.5
    return min(score, 0.99)


def _base_score(days_ago: int | None, churn: int) -> float:
    """Age + churn heuristic: older + less churned = higher score."""
    age_factor = 0.5
    if days_ago is not None:
        if days_ago > 365:
            age_factor = 0.9
        elif days_ago > 90:
            age_factor = 0.7
        else:
            age_factor = 0.4

    churn_penalty = min(churn * 0.05, 0.4)
    return max(age_factor - churn_penalty, 0.1)


def _is_dynamic_annotation_risk(sym: SymbolNode) -> bool:
    return sym.is_objc or sym.is_dynamic or sym.is_ns_managed or sym.is_property_wrapper


def enrich_findings_with_git(
    findings: list[DeadFinding],
    git_history: dict[str, dict[str, Any]],
    graph_symbols: dict[str, "SymbolNode"],
) -> list[DeadFinding]:
    """Enrich findings with git_history data, return updated findings.

    git_history maps qualified_name → {days_ago, has_external_refs, churn_count,
    last_external_ref_date}.
    """
    enriched: list[DeadFinding] = []
    for finding in findings:
        scores = []
        last_refs: list[str] = []
        for member in finding.members:
            qn = member.qualified_name
            hist = git_history.get(qn, {})
            sym = graph_symbols.get(qn)
            if sym is None:
                scores.append(0.5)
                continue
            score = compute_safe_to_delete_score(
                sym,
                last_modified_days_ago=hist.get("days_ago"),
                has_external_refs=bool(hist.get("has_external_refs", False)),
                churn_count=int(hist.get("churn_count", 0)),
            )
            scores.append(score)
            if ref := hist.get("last_external_ref_date"):
                last_refs.append(str(ref))

        avg_score = sum(scores) / len(scores) if scores else 0.5
        git_last_ref = max(last_refs) if last_refs else None

        enriched.append(
            finding.model_copy(
                update={
                    "safe_to_delete_score": round(avg_score, 4),
                    "git_last_external_ref": git_last_ref,
                }
            )
        )
    return enriched
