#!/usr/bin/env bash
# Paperclip REST API curl wrappers per UAA spec §8. Source-only.
# Requires _common.sh sourced first (for `die`/`require_*`).

require_command curl
require_command jq

paperclip_get() {
  local path="$1"
  require_env PAPERCLIP_API_URL
  require_env PAPERCLIP_API_KEY
  curl -fsS --max-time 30 --connect-timeout 10 -X GET "${PAPERCLIP_API_URL%/}${path}" \
    -H "Authorization: Bearer $PAPERCLIP_API_KEY" \
    -H "User-Agent: uaa-bootstrap/1.0"
}

paperclip_post() {
  local path="$1"; local body="$2"
  require_env PAPERCLIP_API_URL
  require_env PAPERCLIP_API_KEY
  curl -fsS --max-time 30 --connect-timeout 10 -X POST "${PAPERCLIP_API_URL%/}${path}" \
    -H "Authorization: Bearer $PAPERCLIP_API_KEY" \
    -H "Content-Type: application/json" \
    -H "User-Agent: uaa-bootstrap/1.0" \
    --data-binary "$body"
}

paperclip_put() {
  local path="$1"; local body="$2"
  require_env PAPERCLIP_API_URL
  require_env PAPERCLIP_API_KEY
  curl -fsS --max-time 30 --connect-timeout 10 -X PUT "${PAPERCLIP_API_URL%/}${path}" \
    -H "Authorization: Bearer $PAPERCLIP_API_KEY" \
    -H "Content-Type: application/json" \
    -H "User-Agent: uaa-bootstrap/1.0" \
    --data-binary "$body"
}

paperclip_patch() {
  local path="$1"; local body="$2"
  require_env PAPERCLIP_API_URL
  require_env PAPERCLIP_API_KEY
  curl -fsS --max-time 30 --connect-timeout 10 -X PATCH "${PAPERCLIP_API_URL%/}${path}" \
    -H "Authorization: Bearer $PAPERCLIP_API_KEY" \
    -H "Content-Type: application/json" \
    -H "User-Agent: uaa-bootstrap/1.0" \
    --data-binary "$body"
}

# Hire an agent — exact payload per UAA spec §8.1
paperclip_hire_agent() {
  local company_id="$1"
  local payload="$2"  # full JSON string per §8.1
  paperclip_post "/api/companies/${company_id}/agent-hires" "$payload"
}

# Deploy AGENTS.md per UAA spec §8.2
paperclip_deploy_agents_md() {
  local agent_id="$1"
  local content="$2"
  local body
  body=$(jq -n --arg p "AGENTS.md" --arg c "$content" '{path: $p, content: $c}')
  paperclip_put "/api/agents/${agent_id}/instructions-bundle/file" "$body"
}

# Phase C followup CRIT-1: fetch current AGENTS.md so deploy can journal the
# OLD content as a rollback snapshot. Returns empty string + exit 0 on HTTP 404
# (first-time deploy). Returns non-zero on 401/403/5xx so caller dies under set -e.
paperclip_get_agent_instructions() {
  local agent_id="$1"
  require_env PAPERCLIP_API_URL
  require_env PAPERCLIP_API_KEY
  local response http body
  response=$(curl -sS --max-time 30 --connect-timeout 10 \
    -o - -w '\n%{http_code}' \
    -H "Authorization: Bearer $PAPERCLIP_API_KEY" \
    -H "User-Agent: uaa-bootstrap/1.0" \
    "${PAPERCLIP_API_URL%/}/api/agents/${agent_id}/instructions-bundle/file" 2>/dev/null) || return 1
  http=$(printf '%s' "$response" | tail -1)
  body=$(printf '%s' "$response" | sed '$d')
  case "$http" in
    200) printf '%s' "$body" ;;
    404) printf '' ;;
    *) return 1 ;;
  esac
}

paperclip_get_agent_config() {
  local agent_id="$1"
  paperclip_get "/api/agents/${agent_id}/configuration"
}

# Phase C followup CRIT-1 part 2: inverse of paperclip_hire_agent for rollback.
paperclip_delete_agent() {
  local agent_id="$1"
  require_env PAPERCLIP_API_URL
  require_env PAPERCLIP_API_KEY
  curl -fsS --max-time 30 --connect-timeout 10 -X DELETE "${PAPERCLIP_API_URL%/}/api/agents/${agent_id}" \
    -H "Authorization: Bearer $PAPERCLIP_API_KEY" \
    -H "User-Agent: uaa-bootstrap/1.0"
}

# Plugin endpoints — per UAA spec §8.4 (replace-mode, MUST GET first)
paperclip_plugin_get_config() {
  local plugin_id="$1"
  paperclip_get "/api/plugins/${plugin_id}"
}

paperclip_plugin_set_config() {
  local plugin_id="$1"
  local config_json="$2"
  paperclip_post "/api/plugins/${plugin_id}/config" "$config_json"
}

# Phase C followup IMP-B: distinguish 404 (first-time, return {}) from 401/403/5xx
# (caller dies under set -e). Prevents telegram defaultChatId wipe on expired JWT.
paperclip_plugin_get_config_safe() {
  local plugin_id="$1"
  require_env PAPERCLIP_API_URL
  require_env PAPERCLIP_API_KEY
  local response http body
  response=$(curl -sS --max-time 30 --connect-timeout 10 \
    -o - -w '\n%{http_code}' \
    -H "Authorization: Bearer $PAPERCLIP_API_KEY" \
    -H "User-Agent: uaa-bootstrap/1.0" \
    "${PAPERCLIP_API_URL%/}/api/plugins/${plugin_id}" 2>/dev/null) || return 1
  http=$(printf '%s' "$response" | tail -1)
  body=$(printf '%s' "$response" | sed '$d')
  case "$http" in
    200) printf '%s' "$body" ;;
    404) printf '{}' ;;
    *) log err "plugin GET returned HTTP $http (expected 200 or 404)"; return 1 ;;
  esac
}
