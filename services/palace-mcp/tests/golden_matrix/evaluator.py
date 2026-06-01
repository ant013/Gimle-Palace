"""Golden matrix evaluator — GIM-922.

Loads a YAML matrix, runs each row against a response (live or fixture),
evaluates pass/fail, and computes aggregate metrics.
"""

from __future__ import annotations

import fnmatch
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


# ── Data model ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class MatchCriterion:
    patterns: list[str]
    n: int | None = None  # None → use row.top_k


@dataclass
class MatrixRow:
    id: str
    split: str  # dev | holdout | live_probe
    class_: str  # mandatory | advisory | no_answer
    query: str
    projects: list[str]
    top_k: int
    must_match_all_in_top_n: list[MatchCriterion]
    must_match_any_in_top_n: list[MatchCriterion]
    must_not_match_in_top_n: list[MatchCriterion]
    min_hits: int
    max_noise_hits: int | None
    source_scopes: list[str] | None
    required_context_status: str | None
    row_pass_rule: str
    description: str
    tags: list[str]


@dataclass
class HitEvidence:
    project: str
    qualified_name: str
    file_path: str | None
    source_scope: str | None
    score: float
    context_status: str  # "present" | "absent"
    embedding_input_hash: str | None


@dataclass
class RowResult:
    row_id: str
    split: str
    class_: str
    query: str
    passed: bool
    failure_reasons: list[str]
    hits: list[HitEvidence]
    returned_count: int
    # Per-row metrics
    precision_at_k: float
    recall_at_k: float
    mrr: float
    ndcg: float
    scope_leak_count: int  # hits with unexpected source_scope
    context_present_count: int
    determinism_hash_count: int  # hits with non-null embedding_input_hash


@dataclass
class MatrixReport:
    dev_results: list[RowResult]
    holdout_results: list[RowResult]
    live_probe_results: list[RowResult]
    gate_results: list[RowResult]
    # Aggregate metrics per split
    dev_metrics: dict[str, float]
    holdout_metrics: dict[str, float]
    live_probe_metrics: dict[str, float]
    gate_metrics: dict[str, float]
    mandatory_failures: list[str]  # row ids
    advisory_failures: list[str]


# ── Loader ────────────────────────────────────────────────────────────────────


def load_matrix(path: Path) -> list[MatrixRow]:
    with path.open() as f:
        data = yaml.safe_load(f)

    rows = []
    for raw in data["rows"]:
        rows.append(
            MatrixRow(
                id=raw["id"],
                split=raw["split"],
                class_=raw["class"],
                query=raw["query"],
                projects=raw["projects"],
                top_k=raw["top_k"],
                must_match_all_in_top_n=[
                    MatchCriterion(
                        patterns=c["patterns"],
                        n=c.get("n"),
                    )
                    for c in raw.get("must_match_all_in_top_n", [])
                ],
                must_match_any_in_top_n=[
                    MatchCriterion(
                        patterns=c["patterns"],
                        n=c.get("n"),
                    )
                    for c in raw.get("must_match_any_in_top_n", [])
                ],
                must_not_match_in_top_n=[
                    MatchCriterion(
                        patterns=c["patterns"],
                        n=c.get("n"),
                    )
                    for c in raw.get("must_not_match_in_top_n", [])
                ],
                min_hits=raw.get("min_hits", 0),
                max_noise_hits=raw.get("max_noise_hits"),
                source_scopes=raw.get("source_scopes"),
                required_context_status=raw.get("required_context_status"),
                row_pass_rule=raw.get("row_pass_rule", "all"),
                description=raw.get("description", ""),
                tags=raw.get("tags", []),
            )
        )
    return rows


# ── Pattern matching ──────────────────────────────────────────────────────────


def _hit_matches_pattern(hit: dict[str, Any], pattern: str) -> bool:
    qn = str(hit.get("qualified_name", ""))
    fp = str(hit.get("file_path", "") or "")
    # Prepend "/" so that patterns like "*/DerivedData/*" match relative paths
    fp_abs = fp if fp.startswith("/") else "/" + fp
    return (
        fnmatch.fnmatch(qn, pattern)
        or fnmatch.fnmatch(fp, pattern)
        or fnmatch.fnmatch(fp_abs, pattern)
    )


def _hit_matches_any_pattern(hit: dict[str, Any], patterns: list[str]) -> bool:
    return any(_hit_matches_pattern(hit, p) for p in patterns)


def _is_relevant(row: MatrixRow, hit: dict[str, Any]) -> bool:
    """A hit is 'relevant' if it satisfies any must_match criterion."""
    for c in row.must_match_all_in_top_n:
        if _hit_matches_any_pattern(hit, c.patterns):
            return True
    for c in row.must_match_any_in_top_n:
        if _hit_matches_any_pattern(hit, c.patterns):
            return True
    return False


# ── Metrics ───────────────────────────────────────────────────────────────────


def _precision_at_k(hits: list[dict[str, Any]], k: int, row: MatrixRow) -> float:
    if k == 0:
        return 0.0
    window = hits[:k]
    relevant = sum(1 for h in window if _is_relevant(row, h))
    return relevant / k


def _recall_at_k(hits: list[dict[str, Any]], k: int, row: MatrixRow) -> float:
    window = hits[:k]
    total_relevant = sum(1 for h in hits if _is_relevant(row, h))
    if total_relevant == 0:
        return 1.0 if row.class_ == "no_answer" else 0.0
    relevant_in_k = sum(1 for h in window if _is_relevant(row, h))
    return relevant_in_k / total_relevant


def _mrr(hits: list[dict[str, Any]], row: MatrixRow) -> float:
    for i, h in enumerate(hits):
        if _is_relevant(row, h):
            return 1.0 / (i + 1)
    return 0.0


def _ndcg(hits: list[dict[str, Any]], k: int, row: MatrixRow) -> float:
    window = hits[:k]
    dcg = sum(
        (1.0 if _is_relevant(row, h) else 0.0) / math.log2(i + 2)
        for i, h in enumerate(window)
    )
    ideal_count = sum(1 for h in hits if _is_relevant(row, h))
    ideal_count = min(ideal_count, k)
    idcg = sum(1.0 / math.log2(i + 2) for i in range(ideal_count))
    if idcg == 0:
        return 1.0 if row.class_ == "no_answer" else 0.0
    return dcg / idcg


# ── Row evaluator ─────────────────────────────────────────────────────────────


def _context_status(hit: dict[str, Any]) -> str:
    ctx = hit.get("context")
    if ctx is None:
        return "absent"
    if isinstance(ctx, list) and len(ctx) == 0:
        return "absent"
    return "present"


def evaluate_row(row: MatrixRow, response: dict[str, Any]) -> RowResult:
    hits_raw: list[dict[str, Any]] = response.get("result", [])
    failure_reasons: list[str] = []

    # Check ok flag
    if not response.get("ok", False):
        error_code = response.get("error_code", "unknown")
        failure_reasons.append(f"response ok=false: {error_code}")

    # min_hits check
    if len(hits_raw) < row.min_hits:
        failure_reasons.append(
            f"min_hits not met: got {len(hits_raw)}, expected >= {row.min_hits}"
        )

    # Evaluate constraint windows
    for criterion in row.must_match_all_in_top_n:
        n = criterion.n if criterion.n is not None else row.top_k
        window = hits_raw[:n]
        if not any(_hit_matches_any_pattern(h, criterion.patterns) for h in window):
            failure_reasons.append(
                f"must_match_all not satisfied in top-{n}: none of {criterion.patterns[:3]}…"
            )

    # must_match_any: at least ONE criterion group must have a match (OR semantics)
    if row.must_match_any_in_top_n:
        any_group_matched = any(
            any(
                _hit_matches_any_pattern(h, criterion.patterns)
                for h in hits_raw[
                    : criterion.n if criterion.n is not None else row.top_k
                ]
            )
            for criterion in row.must_match_any_in_top_n
        )
        if not any_group_matched:
            all_patterns = [p for c in row.must_match_any_in_top_n for p in c.patterns]
            failure_reasons.append(
                f"must_match_any not satisfied: none of {all_patterns[:3]}…"
            )

    for criterion in row.must_not_match_in_top_n:
        n = criterion.n if criterion.n is not None else row.top_k
        window = hits_raw[:n]
        violating = [
            h.get("qualified_name") or h.get("file_path", "?")
            for h in window
            if _hit_matches_any_pattern(h, criterion.patterns)
        ]
        if violating:
            failure_reasons.append(
                f"must_not_match violated in top-{n}: {violating[:3]}"
            )

    # max_noise_hits check
    if row.max_noise_hits is not None:
        noise = sum(1 for h in hits_raw[: row.top_k] if not _is_relevant(row, h))
        if noise > row.max_noise_hits:
            failure_reasons.append(
                f"max_noise_hits exceeded: {noise} noise hits > {row.max_noise_hits}"
            )

    # context status check
    if row.required_context_status is not None:
        for h in hits_raw[: row.top_k]:
            cs = _context_status(h)
            if cs != row.required_context_status:
                failure_reasons.append(
                    f"required_context_status={row.required_context_status} but hit"
                    f" '{h.get('qualified_name')}' has context={cs}"
                )
                break

    # Build evidence
    evidence = [
        HitEvidence(
            project=str(h.get("project", "")),
            qualified_name=str(h.get("qualified_name", "")),
            file_path=h.get("file_path"),
            source_scope=h.get("source_scope"),
            score=float(h.get("score", 0.0)),
            context_status=_context_status(h),
            embedding_input_hash=h.get("embedding_input_hash"),
        )
        for h in hits_raw[: row.top_k]
    ]

    # Metrics
    k = row.top_k
    p_at_k = _precision_at_k(hits_raw, k, row)
    r_at_k = _recall_at_k(hits_raw, k, row)
    mrr = _mrr(hits_raw, row)
    ndcg = _ndcg(hits_raw, k, row)

    # Scope leak: hits with source_scope not in the requested scopes
    allowed_scopes = (
        set(row.source_scopes)
        if row.source_scopes
        else {"project", "workspace_package"}
    )
    scope_leak_count = sum(
        1 for h in evidence if h.source_scope and h.source_scope not in allowed_scopes
    )
    context_present_count = sum(1 for e in evidence if e.context_status == "present")
    determinism_hash_count = sum(
        1 for e in evidence if e.embedding_input_hash is not None
    )

    return RowResult(
        row_id=row.id,
        split=row.split,
        class_=row.class_,
        query=row.query,
        passed=len(failure_reasons) == 0,
        failure_reasons=failure_reasons,
        hits=evidence,
        returned_count=len(hits_raw),
        precision_at_k=p_at_k,
        recall_at_k=r_at_k,
        mrr=mrr,
        ndcg=ndcg,
        scope_leak_count=scope_leak_count,
        context_present_count=context_present_count,
        determinism_hash_count=determinism_hash_count,
    )


# ── Aggregate metrics ─────────────────────────────────────────────────────────


def _aggregate(results: list[RowResult]) -> dict[str, float]:
    if not results:
        return {}
    n = len(results)
    executed = [r for r in results if r.returned_count > 0 or r.class_ == "no_answer"]
    n_exec = len(executed)
    total_hits = sum(r.returned_count for r in executed)

    return {
        "rows_total": float(n),
        "rows_executed": float(n_exec),
        "rows_passed": float(sum(1 for r in results if r.passed)),
        "rows_failed": float(sum(1 for r in results if not r.passed)),
        "precision_at_k_mean": (
            sum(r.precision_at_k for r in executed) / n_exec if n_exec else 0.0
        ),
        "recall_at_k_mean": (
            sum(r.recall_at_k for r in executed) / n_exec if n_exec else 0.0
        ),
        "mrr_mean": (sum(r.mrr for r in executed) / n_exec if n_exec else 0.0),
        "ndcg_mean": (sum(r.ndcg for r in executed) / n_exec if n_exec else 0.0),
        "scope_leak_rate": (
            sum(r.scope_leak_count for r in executed) / total_hits
            if total_hits > 0
            else 0.0
        ),
        "context_availability_rate": (
            sum(r.context_present_count for r in executed) / total_hits
            if total_hits > 0
            else 0.0
        ),
        "determinism_hash_match_rate": (
            sum(r.determinism_hash_count for r in executed) / total_hits
            if total_hits > 0
            else 0.0
        ),
    }


# ── Full matrix run ───────────────────────────────────────────────────────────


def run_matrix(
    rows: list[MatrixRow],
    responses: dict[str, dict[str, Any]],
) -> MatrixReport:
    """Evaluate all rows and produce a report.

    ``responses`` maps row_id → semantic_search response dict.
    Rows with no fixture entry receive an empty-result response.
    """
    all_results: list[RowResult] = []
    for row in rows:
        response = responses.get(
            row.id, {"ok": True, "result": [], "returned_count": 0}
        )
        result = evaluate_row(row, response)
        all_results.append(result)

    dev = [r for r in all_results if r.split == "dev"]
    holdout = [r for r in all_results if r.split == "holdout"]
    live = [r for r in all_results if r.split == "live_probe"]
    gate = [r for r in all_results if r.split == "gate"]

    mandatory_failures = [
        r.row_id for r in all_results if r.class_ == "mandatory" and not r.passed
    ]
    advisory_failures = [
        r.row_id for r in all_results if r.class_ == "advisory" and not r.passed
    ]

    return MatrixReport(
        dev_results=dev,
        holdout_results=holdout,
        live_probe_results=live,
        gate_results=gate,
        dev_metrics=_aggregate(dev),
        holdout_metrics=_aggregate(holdout),
        live_probe_metrics=_aggregate(live),
        gate_metrics=_aggregate(gate),
        mandatory_failures=mandatory_failures,
        advisory_failures=advisory_failures,
    )
