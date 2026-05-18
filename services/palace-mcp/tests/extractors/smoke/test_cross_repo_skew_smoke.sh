#!/usr/bin/env bash
# Cross-repo version skew smoke test — manual iMac run only; NOT in CI.
#
# Usage:
#   bash services/palace-mcp/tests/extractors/smoke/test_cross_repo_skew_smoke.sh <project-slug>
#   bash services/palace-mcp/tests/extractors/smoke/test_cross_repo_skew_smoke.sh --bundle <bundle-name>
#
# Requires: palace-mcp running (docker compose --profile review up -d)
#           mcp-client CLI installed (npx @modelcontextprotocol/cli) or equivalent

set -euo pipefail

SLUG="${1:-gimle}"
BUNDLE_MODE=false
BUNDLE_NAME=""

if [[ "${1:-}" == "--bundle" ]]; then
    BUNDLE_MODE=true
    BUNDLE_NAME="${2:?'Usage: test_cross_repo_skew_smoke.sh --bundle <bundle-name>'}"
    SLUG=""
fi

MCP_CMD="${MCP_CMD:-npx -y @modelcontextprotocol/cli}"
PALACE_URL="${PALACE_MCP_URL:-http://localhost:8000}"

echo "=== GIM-218 Cross-Repo Version Skew — smoke test ==="
echo "Mode: $([ "$BUNDLE_MODE" = true ] && echo "bundle=$BUNDLE_NAME" || echo "project=$SLUG")"
echo

# Step 1: run the extractor
echo "--- Step 1: run_extractor ---"
if [ "$BUNDLE_MODE" = true ]; then
    RESULT=$(curl -sf "$PALACE_URL/mcp" \
        -H 'Content-Type: application/json' \
        -d "{\"method\":\"tools/call\",\"params\":{\"name\":\"palace.ingest.run_extractor\",\"arguments\":{\"name\":\"cross_repo_version_skew\",\"project\":\"$BUNDLE_NAME\"}}}" \
        2>&1 || true)
else
    RESULT=$(curl -sf "$PALACE_URL/mcp" \
        -H 'Content-Type: application/json' \
        -d "{\"method\":\"tools/call\",\"params\":{\"name\":\"palace.ingest.run_extractor\",\"arguments\":{\"name\":\"cross_repo_version_skew\",\"project\":\"$SLUG\"}}}" \
        2>&1 || true)
fi
echo "$RESULT" | python3 -m json.tool 2>/dev/null || echo "$RESULT"

# Step 2: live query
echo
echo "--- Step 2: find_version_skew ---"
if [ "$BUNDLE_MODE" = true ]; then
    QUERY_RESULT=$(curl -sf "$PALACE_URL/mcp" \
        -H 'Content-Type: application/json' \
        -d "{\"method\":\"tools/call\",\"params\":{\"name\":\"palace.code.find_version_skew\",\"arguments\":{\"bundle\":\"$BUNDLE_NAME\",\"min_severity\":\"minor\",\"top_n\":10}}}" \
        2>&1 || true)
else
    QUERY_RESULT=$(curl -sf "$PALACE_URL/mcp" \
        -H 'Content-Type: application/json' \
        -d "{\"method\":\"tools/call\",\"params\":{\"name\":\"palace.code.find_version_skew\",\"arguments\":{\"project\":\"$SLUG\",\"min_severity\":\"minor\",\"top_n\":10}}}" \
        2>&1 || true)
fi
echo "$QUERY_RESULT" | python3 -m json.tool 2>/dev/null || echo "$QUERY_RESULT"

echo
echo "=== smoke done ==="
