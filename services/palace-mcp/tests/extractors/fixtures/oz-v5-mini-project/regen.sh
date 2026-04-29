#!/usr/bin/env bash
# regen.sh — regenerate index.scip for oz-v5-mini-project
#
# Prerequisites:
#   - slither-analyzer>=0.11.4  (pip install slither-analyzer)
#   - solc 0.8.20+ on PATH (or pass SOLC=/path/to/solc)
#   - palace-mcp dev environment activated (uv sync) OR palace_mcp on PYTHONPATH
#
# Usage:
#   cd services/palace-mcp/tests/extractors/fixtures/oz-v5-mini-project
#   bash regen.sh
#
# Or from repo root:
#   make regen-solidity-fixture

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../../../.." && pwd)"
PALACE_MCP_DIR="$REPO_ROOT/services/palace-mcp"

echo "[regen] Working directory: $SCRIPT_DIR"
echo "[regen] palace-mcp: $PALACE_MCP_DIR"

# Optional: override solc binary via env var
SOLC_ARG=""
if [ -n "${SOLC:-}" ]; then
    SOLC_ARG="--solc $SOLC"
fi

# Use uv run to execute the CLI inside the palace-mcp venv.
# --foundry-ignore: skip Forge detection, use plain solc (forge not required).
cd "$PALACE_MCP_DIR" && uv run python -m palace_mcp.scip_emit.solidity \
    --project-root "$SCRIPT_DIR" \
    --output "$SCRIPT_DIR/index.scip" \
    --foundry-ignore \
    $SOLC_ARG

echo "[regen] Done. Commit index.scip and update oracle table in REGEN.md."
