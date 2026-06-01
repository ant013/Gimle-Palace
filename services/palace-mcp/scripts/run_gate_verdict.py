"""Gate 1 verdict runner — GIM-1108.

Loads the frozen GOLD corpus manifest, runs Gate 1 gate rows 3× each
(warm SLO), applies Q1/Q2 thresholds, and outputs a structured JSON verdict.

Usage:
    uv run python services/palace-mcp/scripts/run_gate_verdict.py \\
        [--mcp-url http://localhost:8000/mcp] [--project uw-ios-app] \\
        [--strict] [--output gate_verdict.json]

Exit codes:
    0  Q2 passes (overall gate pass)
    1  Q2 fails (archive signal)
    2  Config / environment error

GIM-1108
"""

from __future__ import annotations

import argparse
import asyncio
import fnmatch
import hashlib
import json
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_SERVICE_ROOT = Path(__file__).resolve().parent.parent  # services/palace-mcp/
_DEFAULT_MATRIX = (
    _SERVICE_ROOT / "tests" / "golden_matrix" / "semantic_search_matrix.yaml"
)
_DEFAULT_MANIFEST = (
    _SERVICE_ROOT.parent.parent / "docs" / "specs" / "gold-corpus" / "manifest.json"
)

sys.path.insert(0, str(_SERVICE_ROOT / "src"))
sys.path.insert(0, str(_SERVICE_ROOT))

from tests.golden_matrix.evaluator import (  # noqa: E402
    HitEvidence,
    MatrixRow,
    RowResult,
    evaluate_row,
    load_matrix,
)

# ── Gate 1 thresholds ─────────────────────────────────────────────────────────

_Q2_ROW_ID = "gate-q2-balance-data-refs"
_Q1_ROW_ID = "gate-q1-evm-chain-adapters"

# Q2: must find ≥30 of 31 known BalanceData refs in top-40
_Q2_GROUND_TRUTH = 31
_Q2_THRESHOLD = 30 / 31  # ~0.9677
_Q2_PATTERNS = ["*BalanceData*", "*balanceData*"]

# Q1: informational — fraction of top-20 results that are EVM-related ≥0.80
_Q1_TOP_K = 20
_Q1_THRESHOLD = 0.80
_Q1_PATTERNS = [
    "*EvmAdapter*",
    "*Evm*Adapter*",
    "*EthereumAdapter*",
    "*evm*adapter*",
    "*EvmBlockchain*",
    "*EvmKit*",
]

_SLO_THRESHOLD_MS = 8000.0
_WARM_RUNS = 3


# ── Pattern helpers ───────────────────────────────────────────────────────────


def _evidence_matches(hit: HitEvidence, patterns: list[str]) -> bool:
    qn = hit.qualified_name
    fp = hit.file_path or ""
    fp_abs = fp if fp.startswith("/") else "/" + fp
    for p in patterns:
        if (
            fnmatch.fnmatch(qn, p)
            or fnmatch.fnmatch(fp, p)
            or fnmatch.fnmatch(fp_abs, p)
        ):
            return True
    return False


def _count_matches(hits: list[HitEvidence], patterns: list[str]) -> int:
    return sum(1 for h in hits if _evidence_matches(h, patterns))


# ── MCP execution ─────────────────────────────────────────────────────────────


async def _call_row(
    session: object,
    row: MatrixRow,
    project_override: str | None,
) -> tuple[dict, float]:
    projects = (
        [project_override]
        if project_override
        else [p for p in row.projects if p != "__fixture__"]
    )
    params: dict = {"query": row.query, "limit": row.top_k}
    if len(projects) == 1:
        params["project"] = projects[0]
    else:
        params["projects"] = projects
    if row.source_scopes:
        params["source_scopes"] = row.source_scopes

    t0 = time.monotonic()
    try:
        result = await session.call_tool("palace.code.semantic_search", params)  # type: ignore[attr-defined]
        text = result.content[0].text if result.content else "{}"
        payload = json.loads(text)
    except Exception as exc:
        payload = {
            "ok": False,
            "error_code": "mcp_call_failed",
            "message": str(exc),
            "result": [],
        }
    latency_ms = (time.monotonic() - t0) * 1000.0
    payload["_latency_ms"] = latency_ms
    return payload, latency_ms


async def _run_gate_rows(
    rows: list[MatrixRow],
    mcp_url: str,
    project_override: str | None,
) -> dict[str, tuple[RowResult, list[float]]]:
    """Run each gate row _WARM_RUNS times. Returns (last RowResult, latencies)."""
    try:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client
    except ImportError as exc:
        print(f"ERROR: mcp package unavailable: {exc}", file=sys.stderr)
        sys.exit(2)

    row_data: dict[str, tuple[RowResult, list[float]]] = {}

    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            for row in rows:
                latencies: list[float] = []
                last_result: RowResult | None = None
                for run_n in range(1, _WARM_RUNS + 1):
                    print(f"  → {row.id}  run {run_n}/{_WARM_RUNS}", end="", flush=True)
                    payload, latency_ms = await _call_row(
                        session, row, project_override
                    )
                    last_result = evaluate_row(row, payload)
                    latencies.append(latency_ms)
                    print(f"  {latency_ms:.0f}ms  hits={last_result.returned_count}")
                assert last_result is not None
                row_data[row.id] = (last_result, latencies)

    return row_data


# ── Verdict builder ───────────────────────────────────────────────────────────


def _verdict_status(condition: bool) -> str:
    return "PASS" if condition else "FAIL"


def build_verdict(
    manifest: dict,
    row_data: dict[str, tuple[RowResult, list[float]]],
) -> dict:
    """Build structured Gate 1 JSON verdict from row results and latencies."""
    # Q2: count BalanceData hits / 31 known refs
    q2_result, q2_latencies = row_data.get(_Q2_ROW_ID, (None, []))
    if q2_result is not None:
        q2_match = _count_matches(q2_result.hits, _Q2_PATTERNS)
    else:
        q2_match = 0
    q2_recall = q2_match / _Q2_GROUND_TRUTH
    q2_pass = q2_recall >= _Q2_THRESHOLD

    # Q1: fraction of top-k results that match EVM patterns (informational)
    q1_result, q1_latencies = row_data.get(_Q1_ROW_ID, (None, []))
    if q1_result is not None:
        q1_match = _count_matches(q1_result.hits, _Q1_PATTERNS)
        q1_total = max(q1_result.returned_count, 1)
    else:
        q1_match, q1_total = 0, 1
    q1_recall = q1_match / q1_total
    q1_pass = q1_recall >= _Q1_THRESHOLD

    # Warm SLO: p50 across all gate row runs
    all_latencies = q2_latencies + q1_latencies
    p50_ms = statistics.median(all_latencies) if all_latencies else float("inf")
    slo_pass = p50_ms < _SLO_THRESHOLD_MS

    # Overall: Q2 determines gate outcome; Q1 and SLO are informational
    overall_pass = q2_pass

    return {
        "gate": "gate-1",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "manifest_sha": manifest.get("palace_mcp_sha"),
        "q2": {
            "status": _verdict_status(q2_pass),
            "recall": round(q2_recall, 4),
            "threshold": round(_Q2_THRESHOLD, 4),
            "detail": f"{q2_match}/{_Q2_GROUND_TRUTH} refs found",
        },
        "q1": {
            "status": _verdict_status(q1_pass),
            "recall": round(q1_recall, 4),
            "threshold": _Q1_THRESHOLD,
        },
        "warm_slo": {
            "status": _verdict_status(slo_pass),
            "p50_ms": round(p50_ms, 1),
            "threshold_ms": _SLO_THRESHOLD_MS,
        },
        "overall": _verdict_status(overall_pass),
        "gate_adjustment_applied": False,
    }


# ── Manifest loader ───────────────────────────────────────────────────────────


def _load_manifest(path: Path, strict: bool, matrix_path: Path) -> dict:
    if not path.exists():
        print(f"ERROR: manifest not found: {path}", file=sys.stderr)
        sys.exit(2)
    manifest = json.loads(path.read_text())

    if strict:
        current_sha = hashlib.sha256(matrix_path.read_bytes()).hexdigest()
        manifest_sha = manifest.get("golden_matrix_sha", "")
        if current_sha != manifest_sha:
            print(
                f"ERROR: matrix SHA mismatch (--strict mode)\n"
                f"  manifest: {manifest_sha}\n"
                f"  current:  {current_sha}",
                file=sys.stderr,
            )
            sys.exit(2)

    return manifest


# ── CLI ───────────────────────────────────────────────────────────────────────


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Gate 1 verdict runner — outputs structured JSON gate verdict."
    )
    p.add_argument("--mcp-url", default="http://localhost:8000/mcp")
    p.add_argument(
        "--project", default=None, help="Override project slug for live mode"
    )
    p.add_argument("--matrix", type=Path, default=_DEFAULT_MATRIX)
    p.add_argument("--manifest", type=Path, default=_DEFAULT_MANIFEST)
    p.add_argument(
        "--strict",
        action="store_true",
        help="Fail if golden_matrix_sha in manifest doesn't match current matrix file",
    )
    p.add_argument(
        "--output", type=Path, default=None, help="Write JSON verdict to file"
    )
    return p.parse_args()


def main() -> None:
    args = _parse_args()

    if not args.matrix.exists():
        print(f"ERROR: matrix not found: {args.matrix}", file=sys.stderr)
        sys.exit(2)

    manifest = _load_manifest(args.manifest, args.strict, args.matrix)

    rows = load_matrix(args.matrix)
    gate_rows = [r for r in rows if r.split == "gate"]
    if not gate_rows:
        print("ERROR: no gate rows found in matrix", file=sys.stderr)
        sys.exit(2)

    print(
        f"Running Gate 1 verdict — {len(gate_rows)} gate row(s),"
        f" {_WARM_RUNS} warm runs each…"
    )
    row_data = asyncio.run(_run_gate_rows(gate_rows, args.mcp_url, args.project))

    verdict = build_verdict(manifest, row_data)
    verdict_json = json.dumps(verdict, indent=2)
    print("\n" + verdict_json)

    if args.output:
        args.output.write_text(verdict_json)
        print(f"\nVerdict written to {args.output}")

    sys.exit(0 if verdict["overall"] == "PASS" else 1)


if __name__ == "__main__":
    main()
