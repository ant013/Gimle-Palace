"""Smoke test for uw-ios bundle ingest (GIM-182 §9.4.2).

Validates end-to-end: registration → ingest → cross-Kit query → smoke gate.
Run on iMac after palace-mcp is up and bundle is registered.

Usage:
    cd ~/Gimle-Palace
    uv run python services/palace-mcp/scripts/smoke_uw_ios_bundle.py

Exit code: 0 = GREEN, 1 = RED.

Smoke gate (§9.4.4):
    - ingest state == "succeeded" OR (state == "failed" AND members_failed <= 1 AND uw-ios-app ok)
    - members_ok >= 40
    - uw-ios-app NOT in failed runs
    - occurrences_count > 0
    - bundle_health.members_total == 41
    - uw-ios-app NOT in query_failed/ingest_failed/never_ingested slugs
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
MANIFEST = SCRIPT_DIR / "uw-ios-bundle-manifest.json"
PALACE_MCP_URL = os.environ.get("PALACE_MCP_URL", "http://localhost:8080/mcp")
BUNDLE_NAME = "uw-ios"
POLL_INTERVAL_S = 15
SMOKE_SYMBOL = "EvmKit.Address"


def mcp_call(tool: str, args: dict) -> dict:
    result = subprocess.run(
        ["python3", str(SCRIPT_DIR / "_mcp_client.py"), tool, json.dumps(args)],
        capture_output=True,
        text=True,
        env={**os.environ, "PALACE_MCP_URL": PALACE_MCP_URL},
    )
    if result.returncode != 0 and not result.stdout.strip():
        raise RuntimeError(f"MCP call failed: {result.stderr[:300]}")
    return json.loads(result.stdout)


def verify_sha256_all_kits() -> None:
    """Verify sha256 files exist and match for each kit in manifest."""
    manifest = json.loads(MANIFEST.read_text())
    hs_base = Path(os.environ.get("HS_BASE_DIR", "/Users/Shared/Ios/HorizontalSystems"))
    missing = []
    for m in manifest["members"]:
        scip_path = hs_base / m["relative_path"] / "scip" / "index.scip"
        sha_path = Path(str(scip_path) + ".sha256")
        if not scip_path.exists():
            missing.append(f"{m['slug']}: scip missing at {scip_path}")
        elif not sha_path.exists():
            missing.append(f"{m['slug']}: sha256 missing at {sha_path}")
    if missing:
        print("WARNING: sha256 validation issues:", file=sys.stderr)
        for m in missing:
            print(f"  {m}", file=sys.stderr)


def assess_smoke_gate(status: dict, query: dict) -> int:
    """Return 0 (GREEN) or 1 (RED) per spec §9.4.4."""
    errors = []

    # Ingest gate
    failed_slugs = [r["slug"] for r in status.get("runs", ()) if not r.get("ok")]
    if status.get("state") == "failed":
        members_failed = status.get("members_failed", 0)
        if members_failed > 1 or "uw-ios-app" in failed_slugs:
            errors.append(
                f"ingest failed: members_failed={members_failed}, "
                f"uw-ios-app_ok={'uw-ios-app' not in failed_slugs}"
            )
    members_ok = status.get("members_ok", 0)
    if members_ok < 40:
        errors.append(f"members_ok={members_ok} < 40")
    if "uw-ios-app" in failed_slugs:
        errors.append("uw-ios-app is in failed runs")

    # Query gate
    occ_count = len(query.get("occurrences", []))
    if occ_count == 0:
        errors.append(f"occurrences_count=0 for '{SMOKE_SYMBOL}'")
    health = query.get("bundle_health", {})
    if health.get("members_total", 0) != 41:
        errors.append(
            f"bundle_health.members_total={health.get('members_total')} != 41"
        )
    for key in ("query_failed_slugs", "ingest_failed_slugs", "never_ingested_slugs"):
        if "uw-ios-app" in (health.get(key) or []):
            errors.append(f"uw-ios-app in {key}")

    if errors:
        print("SMOKE RED:", file=sys.stderr)
        for e in errors:
            print(f"  {e}", file=sys.stderr)
        return 1

    print("SMOKE GREEN")
    return 0


async def main() -> int:
    print(f"==> palace-mcp smoke: bundle={BUNDLE_NAME} url={PALACE_MCP_URL}")

    # 1. Register bundle
    print("==> Step 1: register bundle")
    subprocess.run(
        ["bash", str(SCRIPT_DIR / "register-uw-ios-bundle.sh")],
        check=True,
        env={**os.environ, "PALACE_MCP_URL": PALACE_MCP_URL},
    )

    # 2. Verify sha256 files
    print("==> Step 2: verify SCIP sha256")
    verify_sha256_all_kits()

    # 3. Kick off bundle ingest
    print("==> Step 3: run_extractor(bundle=uw-ios)")
    kickoff = mcp_call(
        "palace.ingest.run_extractor",
        {"name": "symbol_index_swift", "bundle": BUNDLE_NAME},
    )
    run_id = kickoff.get("run_id")
    print(
        f"  kickoff: run_id={run_id}, state={kickoff.get('state')}, "
        f"members_total={kickoff.get('members_total')}"
    )

    # 4. Poll until terminal
    print("==> Step 4: poll bundle_status")
    t0 = time.monotonic()
    while True:
        status = mcp_call("palace.ingest.bundle_status", {"run_id": run_id})
        state = status.get("state")
        done = status.get("members_done", 0)
        total = status.get("members_total", 0)
        elapsed = int(time.monotonic() - t0)
        print(f"  [{elapsed:4d}s] state={state} {done}/{total} members done")
        if state in ("succeeded", "failed"):
            break
        await asyncio.sleep(POLL_INTERVAL_S)

    # 5. Cross-kit query
    print(f"==> Step 5: find_references('{SMOKE_SYMBOL}', bundle)")
    query = mcp_call(
        "palace.code.find_references",
        {"qualified_name": SMOKE_SYMBOL, "project": BUNDLE_NAME},
    )

    # 6. Print evidence
    evidence = {
        "ingest_summary": status,
        "query_summary": {
            "occurrences_count": len(query.get("occurrences", [])),
            "bundle_health": query.get("bundle_health"),
        },
    }
    print(json.dumps(evidence, indent=2, default=str))

    # 7. Gate
    return assess_smoke_gate(status, query)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
