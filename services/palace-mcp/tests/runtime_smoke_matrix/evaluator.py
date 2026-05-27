"""Runtime smoke matrix evaluator for PR7.

Loads the committed PR7 runtime smoke matrix, validates required row fields,
evaluates fixture/live evidence, and renders JSON/markdown artifacts for QA.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class RuntimeMatrixRow:
    id: str
    host_class: str
    repo: str
    ref: str
    compose_profile: str
    required_stage_sequence: list[str]
    expected_artifacts: list[str]
    min_graph_counts: dict[str, int]
    embedding_limit: int | None
    allowed_skip_codes: list[str]
    row_pass_rule: str
    command: list[str]
    product_probe: dict[str, Any]
    graph_invariant_query: dict[str, Any]
    description: str


@dataclass(frozen=True)
class StageEvidence:
    stage: str
    status: str
    error_code: str | None
    evidence: str
    artifacts: list[str]


@dataclass(frozen=True)
class RuntimeRowResult:
    row_id: str
    passed: bool
    failure_phase: str | None
    failure_reasons: list[str]
    stage_results: list[StageEvidence]
    actual_artifacts: list[str]
    graph_counts: dict[str, int]
    product_probe_ok: bool
    invariant_ok: bool
    coverage_label: str


@dataclass(frozen=True)
class RuntimeMatrixReport:
    results: list[RuntimeRowResult]
    mandatory_failures: list[str]

    @property
    def passed(self) -> bool:
        return len(self.mandatory_failures) == 0 and len(self.results) > 0


def load_matrix(path: Path) -> tuple[str, str, list[RuntimeMatrixRow]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    rows: list[RuntimeMatrixRow] = []
    for raw in data["rows"]:
        rows.append(
            RuntimeMatrixRow(
                id=raw["id"],
                host_class=raw["host_class"],
                repo=raw["repo"],
                ref=raw["ref"],
                compose_profile=raw["compose_profile"],
                required_stage_sequence=list(raw["required_stage_sequence"]),
                expected_artifacts=list(raw["expected_artifacts"]),
                min_graph_counts=dict(raw["min_graph_counts"]),
                embedding_limit=raw.get("embedding_limit"),
                allowed_skip_codes=list(raw.get("allowed_skip_codes", [])),
                row_pass_rule=raw["row_pass_rule"],
                command=list(raw["command"]),
                product_probe=dict(raw["product_probe"]),
                graph_invariant_query=dict(raw["graph_invariant_query"]),
                description=raw.get("description", ""),
            )
        )
    return (
        str(data.get("matrix_schema_version", "1")),
        str(data.get("runner_version", "unknown")),
        rows,
    )


def _collect_stage_results(response: dict[str, Any]) -> list[StageEvidence]:
    stage_results: list[StageEvidence] = []
    for raw in response.get("stage_results", []):
        stage_results.append(
            StageEvidence(
                stage=str(raw["stage"]),
                status=str(raw["status"]),
                error_code=(
                    str(raw["error_code"]) if raw.get("error_code") is not None else None
                ),
                evidence=str(raw.get("evidence", "")),
                artifacts=[str(item) for item in raw.get("artifacts", [])],
            )
        )
    return stage_results


def evaluate_row(row: RuntimeMatrixRow, response: dict[str, Any]) -> RuntimeRowResult:
    failure_reasons: list[str] = []
    failure_phase: str | None = None
    stage_results = _collect_stage_results(response)
    stage_map = {stage.stage: stage for stage in stage_results}

    actual_artifacts = set(str(item) for item in response.get("artifacts", []))
    for stage in stage_results:
        actual_artifacts.update(stage.artifacts)

    first_failure_index: int | None = None
    for index, stage_name in enumerate(row.required_stage_sequence):
        stage = stage_map.get(stage_name)
        if stage is None:
            failure_reasons.append(f"missing required stage: {stage_name}")
            if first_failure_index is None:
                first_failure_index = index
            continue
        if stage.status == "passed":
            continue
        if stage.status == "skipped" and stage.error_code in row.allowed_skip_codes:
            failure_reasons.append(
                f"required stage {stage_name} skipped with allowed code {stage.error_code}; required stages cannot be skipped"
            )
        else:
            detail = f" ({stage.error_code})" if stage.error_code else ""
            failure_reasons.append(
                f"required stage {stage_name} status={stage.status}{detail}"
            )
        if first_failure_index is None:
            first_failure_index = index

    missing_artifacts = [
        artifact
        for artifact in row.expected_artifacts
        if artifact not in actual_artifacts
    ]
    if missing_artifacts:
        failure_reasons.append(
            f"missing expected artifacts: {', '.join(sorted(missing_artifacts))}"
        )

    product_probe = dict(response.get("product_probe", {}))
    product_probe_ok = product_probe.get("status") == "passed"
    if not product_probe_ok:
        failure_reasons.append("product probe did not pass")

    graph_invariant = dict(response.get("graph_invariant", {}))
    invariant_ok = graph_invariant.get("status") == "passed"
    if not invariant_ok:
        failure_reasons.append("graph invariant query did not pass")

    graph_counts = {
        str(key): int(value)
        for key, value in dict(graph_invariant.get("counts", {})).items()
    }
    for key, minimum in row.min_graph_counts.items():
        actual = graph_counts.get(key, 0)
        if actual < minimum:
            failure_reasons.append(
                f"min_graph_counts.{key}={actual} < required {minimum}"
            )

    actual_embedding_limit = response.get("embedding_limit")
    coverage_label = "bounded" if row.embedding_limit is not None else "full"
    if row.embedding_limit is not None and actual_embedding_limit != row.embedding_limit:
        failure_reasons.append(
            f"embedding_limit={actual_embedding_limit} != required {row.embedding_limit}"
        )

    if first_failure_index is not None:
        failure_phase = (
            "build_or_emit" if first_failure_index == 0 else "extractor"
        )
    elif not product_probe_ok or not invariant_ok:
        failure_phase = "probe"

    return RuntimeRowResult(
        row_id=row.id,
        passed=len(failure_reasons) == 0,
        failure_phase=failure_phase,
        failure_reasons=failure_reasons,
        stage_results=stage_results,
        actual_artifacts=sorted(actual_artifacts),
        graph_counts=graph_counts,
        product_probe_ok=product_probe_ok,
        invariant_ok=invariant_ok,
        coverage_label=coverage_label,
    )


def run_matrix(
    rows: list[RuntimeMatrixRow],
    responses: dict[str, dict[str, Any]],
) -> RuntimeMatrixReport:
    results = [evaluate_row(row, responses.get(row.id, {})) for row in rows]
    mandatory_failures = [result.row_id for result in results if not result.passed]
    return RuntimeMatrixReport(results=results, mandatory_failures=mandatory_failures)


def build_json_summary(
    *,
    schema_version: str,
    runner_version: str,
    commit_sha: str,
    rows: list[RuntimeMatrixRow],
    report: RuntimeMatrixReport,
) -> dict[str, Any]:
    rows_by_id = {row.id: row for row in rows}
    return {
        "matrix_schema_version": schema_version,
        "runner_version": runner_version,
        "commit_sha": commit_sha,
        "repo_refs": {row.id: row.ref for row in rows},
        "passed": report.passed,
        "rows": [
            {
                "id": result.row_id,
                "repo": rows_by_id[result.row_id].repo,
                "ref": rows_by_id[result.row_id].ref,
                "host_class": rows_by_id[result.row_id].host_class,
                "compose_profile": rows_by_id[result.row_id].compose_profile,
                "passed": result.passed,
                "failure_phase": result.failure_phase,
                "failure_reasons": result.failure_reasons,
                "graph_counts": result.graph_counts,
                "embedding_limit": rows_by_id[result.row_id].embedding_limit,
                "coverage_label": result.coverage_label,
                "product_probe": rows_by_id[result.row_id].product_probe,
                "graph_invariant_query": rows_by_id[result.row_id].graph_invariant_query,
                "required_stage_sequence": rows_by_id[result.row_id].required_stage_sequence,
                "expected_artifacts": rows_by_id[result.row_id].expected_artifacts,
            }
            for result in report.results
        ],
    }


def render_markdown_report(
    *,
    schema_version: str,
    runner_version: str,
    commit_sha: str,
    rows: list[RuntimeMatrixRow],
    report: RuntimeMatrixReport,
) -> str:
    rows_by_id = {row.id: row for row in rows}
    lines = [
        "# PR7 Runtime Smoke Matrix",
        "",
        f"- matrix_schema_version: `{schema_version}`",
        f"- runner_version: `{runner_version}`",
        f"- commit_sha: `{commit_sha}`",
        "",
        "| Row | Host | Ref | Status | Coverage | Failure Phase |",
        "|---|---|---|---|---|---|",
    ]
    for result in report.results:
        row = rows_by_id[result.row_id]
        status = "PASS" if result.passed else "FAIL"
        failure_phase = result.failure_phase or "-"
        coverage = (
            "bounded embeddings only"
            if result.coverage_label == "bounded"
            else "full coverage"
        )
        lines.append(
            f"| `{row.id}` | `{row.host_class}` | `{row.ref}` | {status} | {coverage} | `{failure_phase}` |"
        )
        lines.append("")
        lines.append(f"## {row.id}")
        lines.append("")
        lines.append(row.description)
        lines.append("")
        lines.append(
            f"- required_stage_sequence: `{', '.join(row.required_stage_sequence)}`"
        )
        lines.append(f"- expected_artifacts: `{', '.join(row.expected_artifacts)}`")
        lines.append(
            f"- product_probe: `{row.product_probe['tool']}` -> {row.product_probe['success_hint']}"
        )
        lines.append(
            f"- graph_invariant_query: `{row.graph_invariant_query['tool']}` -> {row.graph_invariant_query['success_hint']}"
        )
        lines.append(f"- command: `{ ' '.join(row.command) }`")
        if result.failure_reasons:
            lines.append(f"- failure_reasons: `{'; '.join(result.failure_reasons)}`")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"

