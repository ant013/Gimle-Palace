#!/usr/bin/env bash
# Paperclip REST API curl wrappers per UAA spec §8. Source-only.
# Requires _common.sh sourced first (for `die`/`require_*`).

require_command curl
require_command jq

paperclip_get() {
  local path="$1"
  require_env PAPERCLIP_API_URL
  require_env PAPERCLIP_API_KEY
  curl -fsS -X GET "${PAPERCLIP_API_URL%/}${path}" \
    -H "Authorization: Bearer $PAPERCLIP_API_KEY" \
    -H "User-Agent: uaa-bootstrap/1.0"
}

paperclip_post() {
  local path="$1"; local body="$2"
  require_env PAPERCLIP_API_URL
  require_env PAPERCLIP_API_KEY
  curl -fsS -X POST "${PAPERCLIP_API_URL%/}${path}" \
    -H "Authorization: Bearer $PAPERCLIP_API_KEY" \
    -H "Content-Type: application/json" \
    -H "User-Agent: uaa-bootstrap/1.0" \
    --data-binary "$body"
}

paperclip_put() {
  local path="$1"; local body="$2"
  require_env PAPERCLIP_API_URL
  require_env PAPERCLIP_API_KEY
  curl -fsS -X PUT "${PAPERCLIP_API_URL%/}${path}" \
    -H "Authorization: Bearer $PAPERCLIP_API_KEY" \
    -H "Content-Type: application/json" \
    -H "User-Agent: uaa-bootstrap/1.0" \
    --data-binary "$body"
}

paperclip_patch() {
  local path="$1"; local body="$2"
  require_env PAPERCLIP_API_URL
  require_env PAPERCLIP_API_KEY
  curl -fsS -X PATCH "${PAPERCLIP_API_URL%/}${path}" \
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

paperclip_get_agent_config() {
  local agent_id="$1"
  paperclip_get "/api/agents/${agent_id}/configuration"
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
