#!/usr/bin/env bash
# Benchmark/fresh-workspace replay only: re-run palace extractors against
# already-built SCIP files in the historical `fresh` mount.  This is not the
# canonical procedure for registered Gimle-Repos copies; use
# docs/runbooks/gimle-repos-incremental-replay.md there, because it performs
# source-path, explicit-ref, and SCIP preflight first.
#
# Use this AFTER fixes to upstream code, AFTER neo4j wipe, or AFTER any
# palace-mcp upgrade — fast (~5-10 min), idempotent.
#
# Prereqs (one-time, see ingest-fresh-build.sh):
#   - Fresh repos cloned to /Users/ant013/Ios/uw-fresh-2026-06-04/
#   - /Users/ant013/Ios-fresh → /Users/ant013/Ios/uw-fresh-2026-06-04 symlink
#   - Each <kit>/scip/index.scip present
#   - Projects registered with parent_mount="fresh"
#   - Native palace-mcp uvicorn running on :8765 (uses native neo4j :7687)
#
# Usage:
#   bench/ingest-fresh-replay.sh            # all kits, default extractors
#   bench/ingest-fresh-replay.sh evm-kit    # one kit
#   bench/ingest-fresh-replay.sh --extractors symbol_index_swift,code_ownership

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE=/Users/ant013/Android/Gimle-Palace-native/.env
VENV=/Users/ant013/Android/Gimle-Palace-native/.venv

DEFAULT_EXTRACTORS="git_history,symbol_index_swift,code_ownership,public_api_surface"
EXTRACTORS="$DEFAULT_EXTRACTORS"

KITS_ALL=(
    bitcoin-core bitcoin-kit component-kit dash-kit evm-kit hd-wallet-kit
    hs-crypto hs-extensions hs-toolkit litecoin-kit market-kit monero-kit
    uw-ios-app
)

PICKED=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        --extractors) EXTRACTORS="$2"; shift 2 ;;
        --extractors=*) EXTRACTORS="${1#*=}"; shift ;;
        -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
        *) PICKED+=("$1"); shift ;;
    esac
done
[[ ${#PICKED[@]} -eq 0 ]] && PICKED=("${KITS_ALL[@]}")

echo "[replay] kits=${PICKED[*]}"
echo "[replay] extractors=$EXTRACTORS"

set -a; source "$ENV_FILE"; set +a

# Make venv binaries (lizard for hotspot, periphery, etc.) findable from subprocess calls
export PATH="$VENV/bin:$PATH"

cd "$REPO_ROOT/services/palace-mcp"

# Inline python invokes runner.run_extractor with explicit setup
"$VENV/bin/python" - "$EXTRACTORS" "${PICKED[@]}" <<'PY'
import asyncio, sys

extractors = sys.argv[1].split(",")
projects = sys.argv[2:]

async def main():
    from neo4j import AsyncGraphDatabase
    from palace_mcp.config import Settings
    from palace_mcp.graphiti_runtime import build_graphiti
    from palace_mcp.mcp_server import set_settings, set_driver, set_graphiti
    from palace_mcp.extractors.runner import run_extractor

    settings = Settings()
    pw = settings.neo4j_password.get_secret_value() if hasattr(settings.neo4j_password, "get_secret_value") else str(settings.neo4j_password)
    driver = AsyncGraphDatabase.driver(settings.neo4j_uri, auth=(settings.neo4j_user, pw))
    await driver.verify_connectivity()
    graphiti = build_graphiti(settings)
    set_settings(settings); set_driver(driver); set_graphiti(graphiti)

    for slug in projects:
        for name in extractors:
            print(f"[run] {name:24s} on {slug}")
            r = await run_extractor(name=name, project=slug, driver=driver, graphiti=graphiti)
            ok = r.get("ok")
            if ok is False or r.get("error_code"):
                print(f"  ❌ {r.get('error_code')}: {(r.get('message') or '')[:120]}")
            else:
                print(f"  ✅ nodes={r.get('nodes_written')} edges={r.get('edges_written')} duration_ms={r.get('duration_ms')}")
    await driver.close()

asyncio.run(main())
PY
