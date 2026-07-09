#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PALACE_MCP_SERVICE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

exec uv run --directory "$PALACE_MCP_SERVICE_DIR" \
    python -m palace_mcp.ops.sync_status "$@"
