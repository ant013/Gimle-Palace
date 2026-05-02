#!/usr/bin/env bash
# API-only deploy path for Codex Paperclip agent bundles.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DIST_DIR="$SCRIPT_DIR/dist/codex"
COMPANY_ID="${PAPERCLIP_COMPANY_ID:-9d8f432c-ff7d-4e3a-bbe3-3cd355f73b64}"
API_BASE="${PAPERCLIP_API_URL:-https://paperclip.ant013.work}"
ID_FILE="${PAPERCLIP_CODEX_AGENT_IDS_FILE:-$SCRIPT_DIR/codex-agent-ids.env}"

MODE="dry-run"
TARGET="all"

if [ -f "$ID_FILE" ]; then
  # shellcheck disable=SC1090
  . "$ID_FILE"
fi

CODEX_AGENT_NAMES="cx-code-reviewer cx-cto codex-architect-reviewer cx-python-engineer cx-infra-engineer cx-mcp-engineer cx-qa-engineer cx-research-agent cx-technical-writer"

agent_id() {
  case "$1" in
    cx-code-reviewer) echo "${CX_CODE_REVIEWER_AGENT_ID:-}" ;;
    cx-cto) echo "${CX_CTO_AGENT_ID:-}" ;;
    codex-architect-reviewer) echo "${CODEX_ARCHITECT_REVIEWER_AGENT_ID:-}" ;;
    cx-python-engineer) echo "${CX_PYTHON_ENGINEER_AGENT_ID:-}" ;;
    cx-infra-engineer) echo "${CX_INFRA_ENGINEER_AGENT_ID:-}" ;;
    cx-mcp-engineer) echo "${CX_MCP_ENGINEER_AGENT_ID:-}" ;;
    cx-qa-engineer) echo "${CX_QA_ENGINEER_AGENT_ID:-}" ;;
    cx-research-agent) echo "${CX_RESEARCH_AGENT_AGENT_ID:-}" ;;
    cx-technical-writer) echo "${CX_TECHNICAL_WRITER_AGENT_ID:-}" ;;
    *) echo "" ;;
  esac
}

usage() {
  cat <<'USAGE'
Usage:
  ./paperclips/deploy-codex-agents.sh --dry-run [agent-name]
  ./paperclips/deploy-codex-agents.sh --api [agent-name]

Environment:
  PAPERCLIP_API_KEY              required for --api and live adapter preflight
  PAPERCLIP_CODEX_AGENT_IDS_FILE optional env file with CODEX_*_AGENT_ID values
  CX_CODE_REVIEWER_AGENT_ID         Codex code reviewer id after hire approval
  CX_CTO_AGENT_ID                   Codex CTO id
  CODEX_ARCHITECT_REVIEWER_AGENT_ID Codex architectural reviewer id
  CX_PYTHON_ENGINEER_AGENT_ID       Codex Python engineer id
  CX_INFRA_ENGINEER_AGENT_ID        Codex infra engineer id
  CX_MCP_ENGINEER_AGENT_ID          Codex MCP engineer id
  CX_QA_ENGINEER_AGENT_ID           Codex QA engineer id
  CX_RESEARCH_AGENT_AGENT_ID        Codex research agent id
  CX_TECHNICAL_WRITER_AGENT_ID      Codex technical writer id

This script intentionally has no --local mode for the first Codex pilot slice.
USAGE
}

for arg in "$@"; do
  case "$arg" in
    --dry-run) MODE="dry-run" ;;
    --api) MODE="api" ;;
    -h|--help) usage; exit 0 ;;
    *) TARGET="$arg" ;;
  esac
done

if [ ! -d "$DIST_DIR" ]; then
  echo "ERROR: Codex dist not found: $DIST_DIR" >&2
  echo "Run: $SCRIPT_DIR/build.sh --target codex" >&2
  exit 1
fi

if [ "$MODE" = "api" ] && [ -z "${PAPERCLIP_API_KEY:-}" ]; then
  echo "ERROR: --api mode requires PAPERCLIP_API_KEY" >&2
  exit 1
fi

fetch_adapter_type() {
  local aid="$1"
  curl -sS \
    "$API_BASE/api/agents/$aid/configuration" \
    -H "Authorization: Bearer $PAPERCLIP_API_KEY" \
    | python3 -c 'import json,sys; print(json.load(sys.stdin).get("adapterType", ""))'
}

deploy_one() {
  local name="$1"
  local aid
  aid=$(agent_id "$name")
  local dist_file="$DIST_DIR/$name.md"

  if [ ! -f "$dist_file" ]; then
    echo "  SKIP: $dist_file not found"
    return 1
  fi

  if [ -z "$aid" ]; then
    echo "  PENDING: $name has no Codex agent id yet"
    echo "           Set CX_CODE_REVIEWER_AGENT_ID after Paperclip hire approval."
    [ "$MODE" = "dry-run" ] && return 0
    return 1
  fi

  echo "  $name -> $aid"
  echo "    source: $dist_file"

  if [ "$MODE" = "dry-run" ]; then
    if [ -n "${PAPERCLIP_API_KEY:-}" ]; then
      local adapter
      adapter=$(fetch_adapter_type "$aid")
      echo "    live adapterType: $adapter"
      if [ "$adapter" != "codex_local" ]; then
        echo "    REFUSE: expected codex_local"
        return 1
      fi
    else
      echo "    live adapterType: not checked (PAPERCLIP_API_KEY unset)"
    fi
    return 0
  fi

  local adapter
  adapter=$(fetch_adapter_type "$aid")
  if [ "$adapter" != "codex_local" ]; then
    echo "ERROR: refusing upload to $aid; expected codex_local, got '$adapter'" >&2
    return 1
  fi

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
    echo "    upload: OK ($http_code)"
  else
    local body
    body=$(echo "$response" | sed '$d')
    echo "    upload: FAILED ($http_code): $body"
    return 1
  fi
}

echo ""
echo "Mode: $MODE"
echo "Source: $DIST_DIR"
echo "API: $API_BASE"
echo "ID file: $ID_FILE"
echo ""

if [ "$TARGET" = "all" ]; then
  failed=0
  for name in $CODEX_AGENT_NAMES; do
    deploy_one "$name" || failed=$((failed+1))
  done
  [ "$failed" -eq 0 ] || exit 1
else
  known=0
  for name in $CODEX_AGENT_NAMES; do
    if [ "$name" = "$TARGET" ]; then
      known=1
      break
    fi
  done
  if [ "$known" -ne 1 ]; then
    echo "Unknown Codex agent: $TARGET" >&2
    echo "Available: $CODEX_AGENT_NAMES" >&2
    exit 1
  fi
  deploy_one "$TARGET"
fi
