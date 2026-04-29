#!/usr/bin/env bash
# regen.sh — regenerate index.scip for oz-v5-mini-project
#
# Prerequisites:
#   - slither-analyzer>=0.11.5  (pip install slither-analyzer)
#   - solc 0.8.20+  (solc-select use 0.8.20 or brew install solidity)
#   - palace-mcp dev environment activated (uv sync)
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

# Emit SCIP index using scip_emit.solidity
python3 - <<'PYEOF'
import sys
import os
from pathlib import Path

script_dir = Path(os.environ.get("SCRIPT_DIR", ".")).resolve()
palace_mcp_src = Path(os.environ.get("PALACE_MCP_DIR", ".")).resolve() / "src"
sys.path.insert(0, str(palace_mcp_src))

from palace_mcp.scip_emit.solidity import emit_index_from_path

root_path = script_dir
output_path = script_dir / "index.scip"

print(f"[regen] Parsing Solidity contracts in: {root_path}")
index = emit_index_from_path(root_path)

data = index.SerializeToString()
output_path.write_bytes(data)
print(f"[regen] Written {len(data)} bytes to {output_path}")

# Count stats
n_docs = len(index.documents)
n_occs = sum(len(doc.occurrences) for doc in index.documents)
print(f"[regen] Documents: {n_docs}, Total occurrences: {n_occs}")
PYEOF

echo "[regen] Done. Commit index.scip and update oracle table in REGEN.md."
