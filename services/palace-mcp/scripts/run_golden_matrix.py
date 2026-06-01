"""Golden matrix runner — GIM-922.

Runs the semantic search golden matrix against a live Neo4j graph or
pre-canned fixture responses, prints per-row evidence, and exits non-zero
if any mandatory row fails.

Usage (fixture mode — no server required):
    uv run python services/palace-mcp/scripts/run_golden_matrix.py --fixture

Usage (live mode — requires palace-mcp running):
    uv run python services/palace-mcp/scripts/run_golden_matrix.py \\
        --live --project gimle [--mcp-url http://localhost:8000/mcp]

Usage (fixture mode from custom matrix):
    uv run python services/palace-mcp/scripts/run_golden_matrix.py \\
        --fixture --matrix path/to/matrix.yaml --fixture-dir path/to/fixtures

Output:
    Per-row evidence + pass/fail, then split-level metric tables.
    Exits 0 if all mandatory rows pass; exits 1 if any mandatory row fails;
    exits 2 on configuration/load error.

GIM-922
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

_SERVICE_ROOT = Path(__file__).resolve().parent.parent  # services/palace-mcp/
_DEFAULT_MATRIX = (
    _SERVICE_ROOT / "tests" / "golden_matrix" / "semantic_search_matrix.yaml"
)
_DEFAULT_FIXTURE_DIR = _SERVICE_ROOT / "tests" / "golden_matrix" / "fixtures"

sys.path.insert(0, str(_SERVICE_ROOT / "src"))
sys.path.insert(0, str(_SERVICE_ROOT))

from tests.golden_matrix.evaluator import (  # noqa: E402
    MatrixReport,
    MatrixRow,
    RowResult,
    load_matrix,
    run_matrix,
)


# ── Formatting helpers ────────────────────────────────────────────────────────


_GREEN = "\033[32m"
_RED = "\033[31m"
_YELLOW = "\033[33m"
_CYAN = "\033[36m"
_BOLD = "\033[1m"
_RESET = "\033[0m"

_USE_COLOR = sys.stdout.isatty()


def _c(color: str, text: str) -> str:
    return f"{color}{text}{_RESET}" if _USE_COLOR else text


def _print_row(result: RowResult, row: MatrixRow) -> None:
    status = _c(_GREEN, "PASS") if result.passed else _c(_RED, "FAIL")
    class_badge = {
        "mandatory": _c(_RED, "[mandatory]"),
        "advisory": _c(_YELLOW, "[advisory]"),
        "no_answer": _c(_CYAN, "[no_answer]"),
    }.get(result.class_, result.class_)
    print(f"\n{_c(_BOLD, result.row_id)} {class_badge} — {status}")
    print(f"  query: {result.query!r}")
    print(
        f"  split: {result.split}  hits: {result.returned_count}"
        f"  P@k: {result.precision_at_k:.2f}  R@k: {result.recall_at_k:.2f}"
        f"  MRR: {result.mrr:.2f}  nDCG: {result.ndcg:.2f}"
    )

    if result.failure_reasons:
        for reason in result.failure_reasons:
            print(f"  {_c(_RED, 'x')} {reason}")

    if result.hits:
        print(f"  top-{row.top_k} evidence:")
        for i, hit in enumerate(result.hits, 1):
            scope_tag = f"[{hit.source_scope}]" if hit.source_scope else ""
            ctx_tag = "[ctx]" if hit.context_status == "present" else ""
            fp = hit.file_path or ""
            print(
                f"    {i}. {hit.score:.3f} {hit.qualified_name}  {scope_tag}{ctx_tag}"
            )
            if fp:
                print(f"        {fp}")
    else:
        print("  (no hits returned)")


def _print_metrics(label: str, metrics: dict[str, float]) -> None:
    if not metrics:
        print(f"\n  {label}: (no rows)")
        return
    print(f"\n  {_c(_BOLD, label)}:")
    print(
        f"    rows total={int(metrics['rows_total'])}"
        f"  executed={int(metrics['rows_executed'])}"
        f"  passed={int(metrics['rows_passed'])}"
        f"  failed={int(metrics['rows_failed'])}"
    )
    print(
        f"    P@k={metrics['precision_at_k_mean']:.3f}"
        f"  R@k={metrics['recall_at_k_mean']:.3f}"
        f"  MRR={metrics['mrr_mean']:.3f}"
        f"  nDCG={metrics['ndcg_mean']:.3f}"
    )
    print(
        f"    scope_leak={metrics['scope_leak_rate']:.3f}"
        f"  context_avail={metrics['context_availability_rate']:.3f}"
        f"  det_hash_match={metrics['determinism_hash_match_rate']:.3f}"
    )


def _print_report(report: MatrixReport, rows_by_id: dict[str, MatrixRow]) -> None:
    all_results = (
        report.dev_results
        + report.holdout_results
        + report.live_probe_results
        + report.gate_results
    )

    print(f"\n{'━' * 70}")
    print(_c(_BOLD, "GOLDEN MATRIX RESULTS"))
    print(f"{'━' * 70}")

    if report.dev_results:
        print(f"\n{_c(_BOLD, '── DEV ROWS')}")
        for result in report.dev_results:
            _print_row(result, rows_by_id[result.row_id])

    if report.holdout_results:
        print(f"\n{_c(_BOLD, '── HOLDOUT ROWS')}")
        for result in report.holdout_results:
            _print_row(result, rows_by_id[result.row_id])

    if report.live_probe_results:
        print(f"\n{_c(_BOLD, '── LIVE PROBE ROWS')}")
        for result in report.live_probe_results:
            _print_row(result, rows_by_id[result.row_id])

    if report.gate_results:
        print(f"\n{_c(_BOLD, '── GATE ROWS')}")
        for result in report.gate_results:
            _print_row(result, rows_by_id[result.row_id])

    print(f"\n{'━' * 70}")
    print(_c(_BOLD, "AGGREGATE METRICS"))
    _print_metrics("DEV", report.dev_metrics)
    _print_metrics("HOLDOUT", report.holdout_metrics)
    _print_metrics("LIVE PROBE", report.live_probe_metrics)
    if report.gate_metrics:
        _print_metrics("GATE", report.gate_metrics)

    print(f"\n{'━' * 70}")
    total = len(all_results)
    passed = sum(1 for r in all_results if r.passed)
    if report.mandatory_failures:
        print(
            _c(
                _RED,
                f"FAIL — {len(report.mandatory_failures)} mandatory row(s) failed:"
                f" {report.mandatory_failures}",
            )
        )
    else:
        print(
            _c(
                _GREEN,
                f"PASS — all mandatory rows passed ({passed}/{total} total passed)",
            )
        )
    if report.advisory_failures:
        print(
            _c(
                _YELLOW,
                f"WARN — {len(report.advisory_failures)} advisory row(s) failed:"
                f" {report.advisory_failures}",
            )
        )
    print()


# ── Fixture mode ──────────────────────────────────────────────────────────────


def _load_fixture_responses(
    fixture_dir: Path, rows: list[MatrixRow]
) -> dict[str, dict]:
    responses_path = fixture_dir / "responses.json"
    if not responses_path.exists():
        print(f"ERROR: fixture file not found: {responses_path}", file=sys.stderr)
        sys.exit(2)
    data = json.loads(responses_path.read_text())
    return {row.id: data[row.id] for row in rows if row.id in data}


# ── Live mode ─────────────────────────────────────────────────────────────────


async def _run_live(
    rows: list[MatrixRow],
    mcp_url: str,
    project_override: str | None,
) -> dict[str, dict]:
    """Call palace.code.semantic_search via MCP for each row."""
    try:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client
    except ImportError as exc:
        print(f"ERROR: mcp package unavailable: {exc}", file=sys.stderr)
        sys.exit(2)

    responses: dict[str, dict] = {}

    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            for row in rows:
                projects = (
                    [project_override]
                    if project_override
                    else [p for p in row.projects if p != "__fixture__"]
                )
                if not projects:
                    print(
                        f"  SKIP {row.id} — no live project configured", file=sys.stderr
                    )
                    responses[row.id] = {"ok": True, "result": [], "returned_count": 0}
                    continue

                params: dict = {
                    "query": row.query,
                    "limit": row.top_k,
                }
                if len(projects) == 1:
                    params["project"] = projects[0]
                else:
                    params["projects"] = projects
                if row.source_scopes:
                    params["source_scopes"] = row.source_scopes

                print(f"  → {row.id}", end="", flush=True)
                try:
                    result = await session.call_tool(
                        "palace.code.semantic_search", params
                    )
                    text = result.content[0].text if result.content else "{}"
                    payload = json.loads(text)
                except Exception as exc:
                    print(f" ERROR: {exc}")
                    payload = {
                        "ok": False,
                        "error_code": "mcp_call_failed",
                        "message": str(exc),
                        "result": [],
                    }
                else:
                    count = payload.get(
                        "returned_count", len(payload.get("result", []))
                    )
                    print(f" {count} hits")
                responses[row.id] = payload

    return responses


# ── Main ──────────────────────────────────────────────────────────────────────


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Run the semantic search golden matrix and report results."
    )
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--fixture", action="store_true", help="Run in fixture mode (no server)"
    )
    mode.add_argument("--live", action="store_true", help="Run against live palace-mcp")

    p.add_argument(
        "--matrix", type=Path, default=_DEFAULT_MATRIX, help="Path to matrix YAML"
    )
    p.add_argument("--fixture-dir", type=Path, default=_DEFAULT_FIXTURE_DIR)
    p.add_argument("--mcp-url", default="http://localhost:8000/mcp")
    p.add_argument(
        "--project", default=None, help="Override project slug for live mode"
    )
    p.add_argument(
        "--splits",
        default="dev,holdout,live_probe",
        help="Comma-separated splits to run (default: all)",
    )
    p.add_argument(
        "--gate-only",
        action="store_true",
        help="Run only gate-split rows (overrides --splits); for Gate 1 verdict runs",
    )
    p.add_argument(
        "--json-report", type=Path, default=None, help="Write JSON report to file"
    )
    return p.parse_args()


def main() -> None:
    args = _parse_args()

    if not args.matrix.exists():
        print(f"ERROR: matrix file not found: {args.matrix}", file=sys.stderr)
        sys.exit(2)
    rows = load_matrix(args.matrix)

    allowed_splits = (
        {"gate"} if args.gate_only else {s.strip() for s in args.splits.split(",")}
    )
    rows = [r for r in rows if r.split in allowed_splits]

    # Zero-row guard
    if not rows:
        print(
            "ERROR: no rows to execute — check --splits filter and matrix file",
            file=sys.stderr,
        )
        sys.exit(2)

    rows_by_id = {r.id: r for r in rows}

    if args.fixture:
        print(f"Loading fixture responses from {args.fixture_dir}…")
        responses = _load_fixture_responses(args.fixture_dir, rows)
    else:
        print(f"Running live mode against {args.mcp_url}…")
        responses = asyncio.run(_run_live(rows, args.mcp_url, args.project))

    report = run_matrix(rows, responses)
    _print_report(report, rows_by_id)

    if args.json_report:
        import dataclasses

        report_dict = dataclasses.asdict(report)
        args.json_report.write_text(json.dumps(report_dict, indent=2))
        print(f"JSON report written to {args.json_report}")

    if report.mandatory_failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
