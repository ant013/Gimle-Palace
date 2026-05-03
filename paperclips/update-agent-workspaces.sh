#!/usr/bin/env bash
# Patch live Paperclip agent adapterConfig.cwd values for isolated team roots.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
API_BASE="${PAPERCLIP_API_URL:-https://paperclip.ant013.work}"
ID_FILE="${PAPERCLIP_CODEX_AGENT_IDS_FILE:-$SCRIPT_DIR/codex-agent-ids.env}"
CLAUDE_WORKSPACE="${PAPERCLIP_CLAUDE_WORKSPACE:-/Users/Shared/Ios/worktrees/claude/Gimle-Palace}"
CODEX_WORKSPACE="${PAPERCLIP_CODEX_WORKSPACE:-/Users/Shared/Ios/worktrees/cx/Gimle-Palace}"

MODE="dry-run"
TARGET_TEAM="all"

if [ -f "$ID_FILE" ]; then
  # shellcheck disable=SC1090
  . "$ID_FILE"
fi

CLAUDE_AGENT_NAMES="code-reviewer cto infra-engineer python-engineer qa-engineer technical-writer mcp-engineer research-agent blockchain-engineer security-auditor opus-architect-reviewer"
CODEX_AGENT_NAMES="cx-code-reviewer cx-cto codex-architect-reviewer cx-python-engineer cx-infra-engineer cx-mcp-engineer cx-qa-engineer cx-research-agent cx-technical-writer"

usage() {
  cat <<'USAGE'
Usage:
  ./paperclips/update-agent-workspaces.sh --dry-run [all|claude|codex]
  ./paperclips/update-agent-workspaces.sh --api [all|claude|codex]

Environment:
  PAPERCLIP_API_KEY              required
  PAPERCLIP_API_URL              defaults to https://paperclip.ant013.work
  PAPERCLIP_CLAUDE_WORKSPACE     defaults to /Users/Shared/Ios/worktrees/claude/Gimle-Palace
  PAPERCLIP_CODEX_WORKSPACE      defaults to /Users/Shared/Ios/worktrees/cx/Gimle-Palace
  PAPERCLIP_CODEX_AGENT_IDS_FILE optional env file with CX_* agent ids

This script only changes adapterConfig.cwd. It refuses adapter type mismatches.
USAGE
}

claude_agent_id() {
  case "$1" in
    code-reviewer) echo "bd2d7e20-7ed8-474c-91fc-353d610f4c52" ;;
    cto) echo "7fb0fdbb-e17f-4487-a4da-16993a907bec" ;;
    infra-engineer) echo "89f8f76b-844b-4d1f-b614-edbe72a91d4b" ;;
    python-engineer) echo "127068ee-b564-4b37-9370-616c81c63f35" ;;
    qa-engineer) echo "58b68640-1e83-4d5d-978b-51a5ca9080e0" ;;
    technical-writer) echo "0e8222fd-88b9-4593-98f6-847a448b0aab" ;;
    mcp-engineer) echo "274a0b0c-ebe8-4613-ad0e-3e745c817a97" ;;
    research-agent) echo "bbcef02c-b755-4624-bba6-84f01e5d49c8" ;;
    blockchain-engineer) echo "9874ad7a-dfbc-49b0-b3ed-d0efda6453bb" ;;
    security-auditor) echo "a56f9e4a-ef9c-46d4-a736-1db5e19bbde4" ;;
    opus-architect-reviewer) echo "8d6649e2-2df6-412a-a6bc-2d94bab3b73f" ;;
    *) echo "" ;;
  esac
}

codex_agent_id() {
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

json_field() {
  python3 -c 'import json,sys; data=json.load(sys.stdin); print(data'"$1"')'
}

patch_one() {
  local team="$1"
  local name="$2"
  local aid="$3"
  local expected_adapter="$4"
  local target_cwd="$5"

  if [ -z "$aid" ]; then
    echo "  PENDING: $name has no agent id"
    return 1
  fi

  local config
  config=$(curl -sS "$API_BASE/api/agents/$aid/configuration" \
    -H "Authorization: Bearer $PAPERCLIP_API_KEY")

  local adapter
  adapter=$(printf "%s" "$config" | json_field '["adapterType"]')
  local current_cwd
  current_cwd=$(printf "%s" "$config" | json_field '.get("adapterConfig", {}).get("cwd", "")')

  printf "  %-24s %-11s %s -> %s\n" "$name" "($team)" "$current_cwd" "$target_cwd"

  if [ "$adapter" != "$expected_adapter" ]; then
    echo "    REFUSE: expected $expected_adapter, got $adapter" >&2
    return 1
  fi

  if [ "$current_cwd" = "$target_cwd" ]; then
    echo "    already current"
    return 0
  fi

  if [ "$MODE" = "dry-run" ]; then
    return 0
  fi

  local payload
  payload=$(printf "%s" "$config" | python3 -c '
import json, sys
data = json.load(sys.stdin)
adapter_config = data.get("adapterConfig") or {}
adapter_config["cwd"] = sys.argv[1]
print(json.dumps({"adapterConfig": adapter_config}))
' "$target_cwd")

  local response
  response=$(curl -sS -w "\n%{http_code}" -X PATCH \
    "$API_BASE/api/agents/$aid" \
    -H "Authorization: Bearer $PAPERCLIP_API_KEY" \
    -H "Content-Type: application/json" \
    --data-binary "$payload" 2>&1)

  local http_code
  http_code=$(echo "$response" | tail -1)
  if [ "$http_code" = "200" ] || [ "$http_code" = "204" ]; then
    echo "    patch: OK ($http_code)"
  else
    echo "    patch: FAILED ($http_code): $(echo "$response" | sed '$d')" >&2
    return 1
  fi
}

patch_team() {
  local team="$1"
  local failed=0
  local name aid

  if [ "$team" = "claude" ]; then
    for name in $CLAUDE_AGENT_NAMES; do
      aid=$(claude_agent_id "$name")
      patch_one "$team" "$name" "$aid" "claude_local" "$CLAUDE_WORKSPACE" || failed=$((failed+1))
    done
  else
    for name in $CODEX_AGENT_NAMES; do
      aid=$(codex_agent_id "$name")
      patch_one "$team" "$name" "$aid" "codex_local" "$CODEX_WORKSPACE" || failed=$((failed+1))
    done
  fi

  [ "$failed" -eq 0 ] || return 1
}

for arg in "$@"; do
  case "$arg" in
    --dry-run) MODE="dry-run" ;;
    --api) MODE="api" ;;
    -h|--help) usage; exit 0 ;;
    all|claude|codex) TARGET_TEAM="$arg" ;;
    *) echo "Unknown argument: $arg" >&2; usage; exit 1 ;;
  esac
done

if [ -z "${PAPERCLIP_API_KEY:-}" ]; then
  echo "ERROR: PAPERCLIP_API_KEY is required" >&2
  exit 1
fi

echo ""
echo "Mode: $MODE"
echo "API: $API_BASE"
echo "Claude workspace: $CLAUDE_WORKSPACE"
echo "Codex workspace:  $CODEX_WORKSPACE"
echo ""

case "$TARGET_TEAM" in
  all)
    patch_team claude
    patch_team codex
    ;;
  claude|codex)
    patch_team "$TARGET_TEAM"
    ;;
esac
