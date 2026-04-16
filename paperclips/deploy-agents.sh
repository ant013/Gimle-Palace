#!/usr/bin/env bash
# Deploy updated AGENTS.md to live paperclip agent bundles (Gimle-Palace).
# Compatible with bash 3.2 (macOS stock).
#
# Two modes:
#   --local   Direct file cp (run ON the iMac server)
#   --api     HTTP API (requires PAPERCLIP_API_KEY env var)
#
# Usage:
#   ./paperclips/deploy-agents.sh --local [agent-name]
#   ./paperclips/deploy-agents.sh --api [agent-name]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DIST_DIR="$SCRIPT_DIR/dist"

COMPANY_ID="9d8f432c-ff7d-4e3a-bbe3-3cd355f73b64"
API_BASE="${PAPERCLIP_API_URL:-https://paperclip.ant013.work}"

PAPERCLIP_DATA="${PAPERCLIP_DATA_DIR:-$HOME/.paperclip/instances/default}"
AGENTS_BASE="$PAPERCLIP_DATA/companies/$COMPANY_ID/agents"

# Gimle agents (CEO excluded — no role file; if added, map here)
AGENT_NAMES="code-reviewer cto infra-engineer python-engineer qa-engineer"

agent_id() {
  case "$1" in
    code-reviewer)    echo "bd2d7e20-7ed8-474c-91fc-353d610f4c52" ;;
    cto)              echo "7fb0fdbb-e17f-4487-a4da-16993a907bec" ;;
    infra-engineer)   echo "89f8f76b-844b-4d1f-b614-edbe72a91d4b" ;;
    python-engineer)  echo "127068ee-b564-4b37-9370-616c81c63f35" ;;
    qa-engineer)      echo "58b68640-1e83-4d5d-978b-51a5ca9080e0" ;;
    *)                echo "" ;;
  esac
}

deploy_local() {
  local name="$1"
  local aid
  aid=$(agent_id "$name")
  local dist_file="$DIST_DIR/$name.md"
  local target="$AGENTS_BASE/$aid/instructions/AGENTS.md"

  if [ ! -f "$dist_file" ]; then
    echo "  SKIP: $dist_file not found"
    return
  fi

  printf "  %-18s → " "$name"

  if [ ! -d "$(dirname "$target")" ]; then
    echo "SKIP (no bundle dir at $(dirname "$target"))"
    return
  fi

  cp "$dist_file" "$target"
  echo "OK ($(wc -l < "$dist_file" | tr -d ' ') lines)"
}

deploy_api() {
  local name="$1"
  local aid
  aid=$(agent_id "$name")
  local dist_file="$DIST_DIR/$name.md"

  if [ ! -f "$dist_file" ]; then
    echo "  SKIP: $dist_file not found"
    return
  fi

  printf "  %-18s → " "$name"

  local content
  content=$(python3 -c "import json,sys; print(json.dumps(sys.stdin.read()))" < "$dist_file")

  local response
  response=$(curl -sS -w "\n%{http_code}" -X PUT \
    "$API_BASE/api/agents/$aid/instructions-bundle/file" \
    -H "Authorization: Bearer $PAPERCLIP_API_KEY" \
    -H "Content-Type: application/json" \
    -d "{\"path\":\"AGENTS.md\",\"content\":$content}" 2>&1)

  local http_code
  http_code=$(echo "$response" | tail -1)

  if [ "$http_code" = "200" ] || [ "$http_code" = "204" ]; then
    echo "OK ($http_code)"
  else
    local body
    body=$(echo "$response" | sed '$d')
    echo "FAILED ($http_code): $body"
    return 1
  fi
}

MODE=""
TARGET=""

for arg in "$@"; do
  case "$arg" in
    --local) MODE="local" ;;
    --api)   MODE="api" ;;
    *)       TARGET="$arg" ;;
  esac
done

if [ -z "$MODE" ]; then
  if [ -d "$AGENTS_BASE" ]; then
    MODE="local"
    echo "Auto-detected: --local (found $AGENTS_BASE)"
  elif [ -n "${PAPERCLIP_API_KEY:-}" ]; then
    MODE="api"
    echo "Auto-detected: --api (PAPERCLIP_API_KEY set)"
  else
    echo "ERROR: Cannot auto-detect mode. Use --local or --api."
    exit 1
  fi
fi

if [ "$MODE" = "api" ] && [ -z "${PAPERCLIP_API_KEY:-}" ]; then
  echo "ERROR: --api mode requires PAPERCLIP_API_KEY" >&2
  exit 1
fi

TARGET="${TARGET:-all}"

echo ""
echo "Mode: $MODE"
echo "Source: $DIST_DIR"
[ "$MODE" = "local" ] && echo "Target: $AGENTS_BASE"
[ "$MODE" = "api" ]   && echo "API: $API_BASE"
echo ""

deploy_one() {
  if [ "$MODE" = "local" ]; then
    deploy_local "$1"
  else
    deploy_api "$1"
  fi
}

if [ "$TARGET" = "all" ]; then
  FAILED=0
  for name in $AGENT_NAMES; do
    deploy_one "$name" || FAILED=$((FAILED+1))
  done
  echo ""
  if [ "$FAILED" -gt 0 ]; then
    echo "WARNING: $FAILED agent(s) failed"
    exit 1
  else
    echo "All agents deployed. Paperclip reads AGENTS.md fresh on each run — no restart needed."
  fi
else
  aid=$(agent_id "$TARGET")
  if [ -z "$aid" ]; then
    echo "Unknown agent: $TARGET"
    echo "Available: $AGENT_NAMES"
    exit 1
  fi
  deploy_one "$TARGET"
fi
