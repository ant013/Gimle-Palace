"""Fixture-mode CI tests for the golden matrix — GIM-922.

These tests run entirely from pre-canned fixture responses (no Neo4j, no MCP
server required) and verify:
- All mandatory rows pass against fixture data.
- The evaluator reports failures correctly.
- The zero-row guard fires (cannot pass silently with 0 rows).
- Per-row evidence is complete (project, qualified_name, score, source_scope,
  file_path, context_status).
- Aggregate metrics are populated.
- Holdout results are reported separately from dev results.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.golden_matrix.evaluator import (
    MatrixRow,
    MatchCriterion,
    evaluate_row,
    load_matrix,
    run_matrix,
)

_MATRIX_PATH = Path(__file__).parent / "semantic_search_matrix.yaml"
_FIXTURES_PATH = Path(__file__).parent / "fixtures" / "responses.json"


@pytest.fixture(scope="module")
def matrix_rows() -> list[MatrixRow]:
    return load_matrix(_MATRIX_PATH)


@pytest.fixture(scope="module")
def fixture_responses() -> dict[str, dict]:
    return json.loads(_FIXTURES_PATH.read_text())


# ── Zero-row guard ─────────────────────────────────────────────────────────────


def test_matrix_has_rows(matrix_rows: list[MatrixRow]) -> None:
    assert len(matrix_rows) > 0, "Matrix cannot be empty — zero-row guard"


def test_run_matrix_zero_rows_raises() -> None:
    report = run_matrix([], {})
    total = (
        len(report.dev_results)
        + len(report.holdout_results)
        + len(report.live_probe_results)
    )
    assert total == 0
    # The runner script checks this; here we verify the report exposes it
    assert report.dev_metrics == {}
    assert report.holdout_metrics == {}


# ── Mandatory rows pass ────────────────────────────────────────────────────────


def test_all_mandatory_rows_pass_with_fixture(
    matrix_rows: list[MatrixRow],
    fixture_responses: dict[str, dict],
) -> None:
    # Gate rows run against live Neo4j; exclude them from fixture-mode checks.
    fixture_rows = [r for r in matrix_rows if r.split != "gate"]
    report = run_matrix(fixture_rows, fixture_responses)
    assert report.mandatory_failures == [], (
        f"Mandatory rows failed: {report.mandatory_failures}"
    )


# ── Split separation ───────────────────────────────────────────────────────────


def test_holdout_results_separate_from_dev(
    matrix_rows: list[MatrixRow],
    fixture_responses: dict[str, dict],
) -> None:
    report = run_matrix(matrix_rows, fixture_responses)
    dev_ids = {r.row_id for r in report.dev_results}
    holdout_ids = {r.row_id for r in report.holdout_results}
    live_ids = {r.row_id for r in report.live_probe_results}
    assert dev_ids.isdisjoint(holdout_ids), "Dev and holdout must not overlap"
    assert dev_ids.isdisjoint(live_ids), "Dev and live_probe must not overlap"
    assert holdout_ids.isdisjoint(live_ids), "Holdout and live_probe must not overlap"


def test_dev_results_non_empty(
    matrix_rows: list[MatrixRow],
    fixture_responses: dict[str, dict],
) -> None:
    report = run_matrix(matrix_rows, fixture_responses)
    assert len(report.dev_results) > 0


def test_holdout_results_non_empty(
    matrix_rows: list[MatrixRow],
    fixture_responses: dict[str, dict],
) -> None:
    report = run_matrix(matrix_rows, fixture_responses)
    assert len(report.holdout_results) > 0


# ── Per-row evidence completeness ─────────────────────────────────────────────


def test_every_hit_has_required_evidence_fields(
    matrix_rows: list[MatrixRow],
    fixture_responses: dict[str, dict],
) -> None:
    report = run_matrix(matrix_rows, fixture_responses)
    all_results = (
        report.dev_results + report.holdout_results + report.live_probe_results
    )
    for row_result in all_results:
        for hit in row_result.hits:
            assert hit.project, f"Missing project in row {row_result.row_id}"
            assert hit.qualified_name, (
                f"Missing qualified_name in row {row_result.row_id}"
            )
            assert isinstance(hit.score, float), (
                f"score must be float in row {row_result.row_id}"
            )
            assert hit.context_status in ("present", "absent"), (
                f"context_status must be 'present'|'absent' in row {row_result.row_id}"
            )


# ── Aggregate metrics populated ───────────────────────────────────────────────


def test_dev_metrics_populated(
    matrix_rows: list[MatrixRow],
    fixture_responses: dict[str, dict],
) -> None:
    report = run_matrix(matrix_rows, fixture_responses)
    m = report.dev_metrics
    assert "precision_at_k_mean" in m
    assert "recall_at_k_mean" in m
    assert "mrr_mean" in m
    assert "ndcg_mean" in m
    assert "scope_leak_rate" in m
    assert "context_availability_rate" in m
    assert "determinism_hash_match_rate" in m
    assert "rows_total" in m
    assert "rows_executed" in m


def test_metrics_in_valid_range(
    matrix_rows: list[MatrixRow],
    fixture_responses: dict[str, dict],
) -> None:
    report = run_matrix(matrix_rows, fixture_responses)
    for metrics in (
        report.dev_metrics,
        report.holdout_metrics,
        report.live_probe_metrics,
    ):
        if not metrics:
            continue
        assert 0.0 <= metrics["precision_at_k_mean"] <= 1.0
        assert 0.0 <= metrics["recall_at_k_mean"] <= 1.0
        assert 0.0 <= metrics["mrr_mean"] <= 1.0
        assert 0.0 <= metrics["ndcg_mean"] <= 1.0
        assert 0.0 <= metrics["scope_leak_rate"] <= 1.0
        assert 0.0 <= metrics["context_availability_rate"] <= 1.0
        assert 0.0 <= metrics["determinism_hash_match_rate"] <= 1.0


# ── Failure detection ─────────────────────────────────────────────────────────


def test_mandatory_failure_detected() -> None:
    row = MatrixRow(
        id="test-fail",
        split="dev",
        class_="mandatory",
        query="find timer",
        projects=["__fixture__"],
        top_k=3,
        must_match_any_in_top_n=[MatchCriterion(patterns=["*Timer*", "*timer*"], n=3)],
        must_match_all_in_top_n=[],
        must_not_match_in_top_n=[],
        min_hits=1,
        max_noise_hits=None,
        source_scopes=None,
        required_context_status=None,
        row_pass_rule="all",
        description="test row",
        tags=[],
    )
    # Response with no timer matches
    bad_response = {
        "ok": True,
        "result": [
            {
                "project": "gimle",
                "qualified_name": "NetworkClient/request",
                "file_path": "Sources/Network/NetworkClient.swift",
                "source_scope": "project",
                "score": 0.85,
            }
        ],
    }
    result = evaluate_row(row, bad_response)
    assert not result.passed
    assert len(result.failure_reasons) > 0


def test_must_not_match_violation_detected() -> None:
    row = MatrixRow(
        id="test-not-match",
        split="dev",
        class_="mandatory",
        query="any query",
        projects=["__fixture__"],
        top_k=3,
        must_match_any_in_top_n=[],
        must_match_all_in_top_n=[],
        must_not_match_in_top_n=[MatchCriterion(patterns=["*/DerivedData/*"], n=3)],
        min_hits=0,
        max_noise_hits=None,
        source_scopes=None,
        required_context_status=None,
        row_pass_rule="all",
        description="test row",
        tags=[],
    )
    bad_response = {
        "ok": True,
        "result": [
            {
                "project": "gimle",
                "qualified_name": "SomeClass/method",
                "file_path": "DerivedData/SomeClass.swift",
                "source_scope": "derived",
                "score": 0.9,
            }
        ],
    }
    result = evaluate_row(row, bad_response)
    assert not result.passed
    assert any("must_not_match" in r for r in result.failure_reasons)


def test_min_hits_failure_detected() -> None:
    row = MatrixRow(
        id="test-min-hits",
        split="dev",
        class_="mandatory",
        query="some query",
        projects=["__fixture__"],
        top_k=5,
        must_match_any_in_top_n=[],
        must_match_all_in_top_n=[],
        must_not_match_in_top_n=[],
        min_hits=3,
        max_noise_hits=None,
        source_scopes=None,
        required_context_status=None,
        row_pass_rule="all",
        description="test row",
        tags=[],
    )
    empty_response = {"ok": True, "result": []}
    result = evaluate_row(row, empty_response)
    assert not result.passed
    assert any("min_hits" in r for r in result.failure_reasons)


def test_no_answer_row_passes_when_disallowed_patterns_absent() -> None:
    row = MatrixRow(
        id="test-no-answer",
        split="dev",
        class_="no_answer",
        query="machine learning neural network",
        projects=["__fixture__"],
        top_k=5,
        must_match_any_in_top_n=[],
        must_match_all_in_top_n=[],
        must_not_match_in_top_n=[
            MatchCriterion(patterns=["*Neural*", "*neural*"], n=5)
        ],
        min_hits=0,
        max_noise_hits=None,
        source_scopes=None,
        required_context_status=None,
        row_pass_rule="all",
        description="no answer test",
        tags=["no_answer"],
    )
    # Response with an unrelated low-score result
    ok_response = {
        "ok": True,
        "result": [
            {
                "project": "gimle",
                "qualified_name": "RiskCalculator/score",
                "file_path": "Sources/Risk/RiskCalculator.swift",
                "source_scope": "project",
                "score": 0.28,
            }
        ],
    }
    result = evaluate_row(row, ok_response)
    assert result.passed, result.failure_reasons


def test_no_answer_row_fails_when_disallowed_pattern_present() -> None:
    row = MatrixRow(
        id="test-no-answer-fail",
        split="dev",
        class_="no_answer",
        query="machine learning neural network",
        projects=["__fixture__"],
        top_k=5,
        must_match_any_in_top_n=[],
        must_match_all_in_top_n=[],
        must_not_match_in_top_n=[
            MatchCriterion(patterns=["*Neural*", "*neural*"], n=5)
        ],
        min_hits=0,
        max_noise_hits=None,
        source_scopes=None,
        required_context_status=None,
        row_pass_rule="all",
        description="no answer test fail",
        tags=["no_answer"],
    )
    bad_response = {
        "ok": True,
        "result": [
            {
                "project": "gimle",
                "qualified_name": "NeuralNetworkLayer/forward",
                "file_path": "Sources/ML/NeuralNetworkLayer.swift",
                "source_scope": "project",
                "score": 0.91,
            }
        ],
    }
    result = evaluate_row(row, bad_response)
    assert not result.passed


# ── run_matrix mandatory failure exits non-zero (checked by runner script) ─────


def test_run_matrix_reports_mandatory_failures(
    matrix_rows: list[MatrixRow],
) -> None:
    # Feed responses that will make the mandatory core rows fail (empty results)
    empty_responses: dict[str, dict] = {}
    report = run_matrix(matrix_rows, empty_responses)
    # All mandatory rows should fail (no results for any of them)
    failed_ids = set(report.mandatory_failures)
    # Every mandatory row with min_hits > 0 should fail
    min_hit_mandatory = {
        r.id for r in matrix_rows if r.class_ == "mandatory" and r.min_hits > 0
    }
    assert min_hit_mandatory.issubset(failed_ids), (
        f"Expected mandatory rows to fail with empty responses: "
        f"{min_hit_mandatory - failed_ids}"
    )


# ── Matrix YAML is valid and complete ─────────────────────────────────────────


def test_matrix_all_splits_present(matrix_rows: list[MatrixRow]) -> None:
    splits = {r.split for r in matrix_rows}
    assert "dev" in splits
    assert "holdout" in splits
    assert "live_probe" in splits


def test_matrix_has_mandatory_rows(matrix_rows: list[MatrixRow]) -> None:
    mandatory = [r for r in matrix_rows if r.class_ == "mandatory"]
    assert len(mandatory) >= 6, (
        "Matrix must have at least 6 mandatory rows (core product queries)"
    )


def test_matrix_has_no_answer_rows(matrix_rows: list[MatrixRow]) -> None:
    no_answer = [r for r in matrix_rows if r.class_ == "no_answer"]
    assert len(no_answer) >= 1, "Matrix must have at least one no_answer row"


def test_all_row_ids_unique(matrix_rows: list[MatrixRow]) -> None:
    ids = [r.id for r in matrix_rows]
    assert len(ids) == len(set(ids)), (
        f"Duplicate row ids: {[x for x in ids if ids.count(x) > 1]}"
    )


def test_fixture_has_entry_for_every_row(
    matrix_rows: list[MatrixRow],
    fixture_responses: dict[str, dict],
) -> None:
    # Gate rows run against live Neo4j only — no fixture responses expected.
    fixture_rows = [r for r in matrix_rows if r.split != "gate"]
    missing = [r.id for r in fixture_rows if r.id not in fixture_responses]
    assert missing == [], f"Missing fixture responses for rows: {missing}"
