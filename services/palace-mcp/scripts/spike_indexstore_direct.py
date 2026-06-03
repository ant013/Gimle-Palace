#!/usr/bin/env python3
"""
GIM-1167 F1B-SPIKE-V2 — IndexStore direct-read spike runner.

Proves BalanceData caller retrieval from the DerivedData IndexStoreDB
without sourcekit-lsp.

Usage::

    uv run scripts/spike_indexstore_direct.py \
        --store-path ~/Library/Developer/Xcode/DerivedData/UnstoppableWallet-xxx/Index.noindex/DataStore \
        --symbol BalanceData

Acceptance criteria:
  - caller_count >= 30
  - latency_warm_s < 5.0
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from palace_mcp.code.indexstore import find_callers

_DEFAULT_STORE = (
    Path.home()
    / "Library/Developer/Xcode/DerivedData"
    / "UnstoppableWallet-ckzuwqnwaudkmzfuszkpjajwyplw"
    / "Index.noindex/DataStore"
)


def main() -> None:
    parser = argparse.ArgumentParser(description="IndexStore direct-read spike")
    parser.add_argument(
        "--store-path",
        default=str(_DEFAULT_STORE),
        help="Path to IndexStoreDB DataStore directory",
    )
    parser.add_argument(
        "--symbol",
        default="BalanceData",
        help="Short symbol name to query (default: BalanceData)",
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=500,
        help="Maximum caller records to collect",
    )
    parser.add_argument(
        "--timing-runs",
        type=int,
        default=2,
        help="Number of timing runs (first=cold, rest=warm)",
    )
    args = parser.parse_args()

    store_path = str(Path(args.store_path).expanduser())
    print(f"Store:  {store_path}")
    print(f"Symbol: {args.symbol}")
    print()

    all_times: list[float] = []
    results: list = []

    for run_idx in range(args.timing_runs):
        t0 = time.perf_counter()
        results = find_callers(args.symbol, store_path, max_results=args.max_results)
        elapsed = time.perf_counter() - t0
        all_times.append(elapsed)
        label = "cold" if run_idx == 0 else "warm"
        print(
            f"  Run {run_idx + 1} ({label}): {elapsed:.3f}s  → {len(results)} occurrences"
        )

    print()
    print(f"caller_count : {len(results)}")
    print(f"latency_cold : {all_times[0]:.3f}s")
    if len(all_times) > 1:
        print(f"latency_warm : {all_times[-1]:.3f}s")

    print()
    print("--- Acceptance Criteria ---")
    count_ok = len(results) >= 30
    warm_lat = all_times[-1] if len(all_times) > 1 else all_times[0]
    lat_ok = warm_lat < 5.0
    print(f"  caller_count >= 30 : {'PASS' if count_ok else 'FAIL'}  ({len(results)})")
    print(f"  latency_warm < 5s  : {'PASS' if lat_ok else 'FAIL'}  ({warm_lat:.3f}s)")
    print()

    if results:
        print("--- Sample callers (first 10) ---")
        for r in results[:10]:
            short_file = Path(r.source_file).name if r.source_file else r.record_name
            print(
                f"  {short_file}:{r.line}:{r.col}  roles={r.roles:#010x}  usr={r.symbol_usr[:40]}"
            )

    print()
    summary = {
        "symbol": args.symbol,
        "store_path": store_path,
        "caller_count": len(results),
        "latency_cold_s": round(all_times[0], 3),
        "latency_warm_s": round(all_times[-1], 3) if len(all_times) > 1 else None,
        "criteria_count_pass": count_ok,
        "criteria_latency_pass": lat_ok,
    }
    print("JSON summary:")
    print(json.dumps(summary, indent=2))

    sys.exit(0 if (count_ok and lat_ok) else 1)


if __name__ == "__main__":
    main()
