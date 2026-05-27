"""Fixture tests for the PR7 runtime smoke matrix."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.runtime_smoke_matrix.evaluator import (
    build_json_summary,
    evaluate_row,
    load_matrix,
    render_markdown_report,
    run_matrix,
)

_ROOT = Path(__file__).parent
_MATRIX_PATH = _ROOT / "runtime_smoke_matrix.yaml"
_FIXTURES_PATH = _ROOT / "fixtures" / "responses.json"


@pytest.fixture(scope="module")
def matrix_bundle() -> tuple[str, str, list]:
    return load_matrix(_MATRIX_PATH)


@pytest.fixture(scope="module")
def fixture_responses() -> dict[str, dict]:
    return json.loads(_FIXTURES_PATH.read_text(encoding="utf-8"))


def test_matrix_has_expected_rows(matrix_bundle: tuple[str, str, list]) -> None:
    _schema_version, _runner_version, rows = matrix_bundle
    assert len(rows) == 4
    assert {row.id for row in rows} == {
        "uw-ios-app-full",
        "bitcoin-kit-ios-full",
        "palace-mcp-server-full",
        "uw-ios-app-embedding-bounded",
    }


def test_all_rows_pass_with_fixture(
    matrix_bundle: tuple[str, str, list],
    fixture_responses: dict[str, dict],
) -> None:
    _schema_version, _runner_version, rows = matrix_bundle
    report = run_matrix(rows, fixture_responses)
    assert report.mandatory_failures == []


def test_build_failure_is_distinguished_from_extractor_failure(
    matrix_bundle: tuple[str, str, list],
) -> None:
    _schema_version, _runner_version, rows = matrix_bundle
    row = next(item for item in rows if item.id == "uw-ios-app-full")

    build_failure = evaluate_row(
        row,
        {
            "stage_results": [
                {
                    "stage": "build_scip",
                    "status": "failed",
                    "error_code": "toolchain_unsupported"
                }
            ],
            "product_probe": {"status": "failed"},
            "graph_invariant": {"status": "failed", "counts": {}}
        },
    )
    extractor_failure = evaluate_row(
        row,
        {
            "artifacts": row.expected_artifacts,
            "stage_results": [
                {"stage": "build_scip", "status": "passed"},
                {"stage": "symbol_index_swift", "status": "failed", "error_code": "extractor_runtime_error"},
                {"stage": "dead_symbol_binary_surface", "status": "passed"},
                {"stage": "embedding_symbol", "status": "passed"}
            ],
            "product_probe": {"status": "passed"},
            "graph_invariant": {"status": "passed", "counts": {"nodes": 1000, "edges": 1000}}
        },
    )

    assert build_failure.failure_phase == "build_or_emit"
    assert extractor_failure.failure_phase == "extractor"


def test_required_stage_skip_still_fails_even_with_allowed_code(
    matrix_bundle: tuple[str, str, list],
) -> None:
    _schema_version, _runner_version, rows = matrix_bundle
    row = next(item for item in rows if item.id == "uw-ios-app-full")
    mutated_row = row.__class__(
        id=row.id,
        host_class=row.host_class,
        repo=row.repo,
        ref=row.ref,
        compose_profile=row.compose_profile,
        required_stage_sequence=row.required_stage_sequence,
        expected_artifacts=row.expected_artifacts,
        min_graph_counts=row.min_graph_counts,
        embedding_limit=row.embedding_limit,
        allowed_skip_codes=["toolchain_unsupported"],
        row_pass_rule=row.row_pass_rule,
        command=row.command,
        product_probe=row.product_probe,
        graph_invariant_query=row.graph_invariant_query,
        description=row.description,
    )

    result = evaluate_row(
        mutated_row,
        {
            "artifacts": row.expected_artifacts,
            "stage_results": [
                {"stage": "build_scip", "status": "skipped", "error_code": "toolchain_unsupported"},
                {"stage": "symbol_index_swift", "status": "passed"},
                {"stage": "dead_symbol_binary_surface", "status": "passed"},
                {"stage": "embedding_symbol", "status": "passed"}
            ],
            "product_probe": {"status": "passed"},
            "graph_invariant": {"status": "passed", "counts": {"nodes": 1000, "edges": 1000}}
        },
    )

    assert not result.passed
    assert any("required stages cannot be skipped" in reason for reason in result.failure_reasons)


def test_bounded_embedding_row_is_rendered_as_partial_coverage(
    matrix_bundle: tuple[str, str, list],
    fixture_responses: dict[str, dict],
) -> None:
    schema_version, runner_version, rows = matrix_bundle
    report = run_matrix(rows, fixture_responses)
    markdown = render_markdown_report(
        schema_version=schema_version,
        runner_version=runner_version,
        commit_sha="deadbeef",
        rows=rows,
        report=report,
    )

    assert "uw-ios-app-embedding-bounded" in markdown
    assert "bounded embeddings only" in markdown
    assert "full coverage" in markdown


def test_json_summary_includes_repo_refs_and_schema_version(
    matrix_bundle: tuple[str, str, list],
    fixture_responses: dict[str, dict],
) -> None:
    schema_version, runner_version, rows = matrix_bundle
    report = run_matrix(rows, fixture_responses)
    payload = build_json_summary(
        schema_version=schema_version,
        runner_version=runner_version,
        commit_sha="deadbeef",
        rows=rows,
        report=report,
    )

    assert payload["matrix_schema_version"] == schema_version
    assert payload["repo_refs"]["uw-ios-app-full"] == "pr7/GIM-914-runtime-smoke-matrix"
    bounded_row = next(item for item in payload["rows"] if item["id"] == "uw-ios-app-embedding-bounded")
    assert bounded_row["embedding_limit"] == 200
    assert bounded_row["coverage_label"] == "bounded"

