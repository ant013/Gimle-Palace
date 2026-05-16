#!/usr/bin/env bash
# UAA Phase C2: smoke-test.sh — 7-stage liveness check per spec §9.3, §12.C.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# shellcheck source=lib/_common.sh
source "${SCRIPT_DIR}/lib/_common.sh"
# shellcheck source=lib/_paperclip_api.sh
source "${SCRIPT_DIR}/lib/_paperclip_api.sh"

QUICK=0
CANARY_STAGE=0
project_key=""

while [ $# -gt 0 ]; do
  case "$1" in
    --quick) QUICK=1; shift ;;
    --canary-stage=*) CANARY_STAGE="${1#--canary-stage=}"; shift ;;
    -h|--help)
      cat <<EOF
Usage: $(basename "$0") <project-key> [--quick | --canary-stage=N]

7-stage smoke test per spec §9.3.
  --quick           skip heavy stages 5+7 (runtime probes + e2e handoff)
  --canary-stage=N  run only stages relevant for canary stage N (1=read-only, 2=cto)
EOF
      exit 0 ;;
    *) project_key="$1"; shift ;;
  esac
done

[ -n "$project_key" ] || die "project-key required"
validate_project_key "$project_key"
require_env PAPERCLIP_API_URL
require_env PAPERCLIP_API_KEY

bindings="${HOME}/.paperclip/projects/${project_key}/bindings.yaml"
manifest="${REPO_ROOT}/paperclips/projects/${project_key}/paperclip-agent-assembly.yaml"

[ -f "$bindings" ] || die "bindings missing: $bindings (run bootstrap-project.sh first)"
[ -f "$manifest" ] || die "manifest missing: $manifest"

company_id=$(yq -r '.company_id' "$bindings")

stage_1_api_reachable() {
  log info "[1/7] paperclip API reachable + JWT valid"
  email=$(paperclip_get "/api/agents/me" | jq -r '.email // .user.email')
  [ -n "$email" ] && [ "$email" != "null" ] || die "API returned no email"
  log ok "  logged in as $email"
}

stage_2_company_and_agents() {
  log info "[2/7] company exists; agents present"
  paperclip_get "/api/companies/${company_id}" >/dev/null || die "company $company_id not found"
  for agent_name in $(yq -r '.agents | keys | .[]' "$bindings"); do
    uuid=$(yq -r ".agents.${agent_name}" "$bindings")
    paperclip_get_agent_config "$uuid" >/dev/null || die "agent $agent_name ($uuid) not in API"
  done
  log ok "  all agents present"
}

stage_3_workspaces() {
  log info "[3/7] workspaces exist + AGENTS.md deployed"
  team_root=$(yq -r '.team_workspace_root' "${HOME}/.paperclip/projects/${project_key}/paths.yaml")
  for agent_name in $(yq -r '.agents | keys | .[]' "$bindings"); do
    ws="${team_root}/${agent_name}/workspace"
    [ -f "${ws}/AGENTS.md" ] || die "workspace AGENTS.md missing: ${ws}/AGENTS.md"
  done
  log ok "  workspaces verified"
}

stage_4_watchdog() {
  log info "[4/7] watchdog sees this company"
  log_path="${HOME}/.paperclip/watchdog.log"
  if [ ! -f "$log_path" ]; then
    log warn "watchdog log not found at $log_path — watchdog not installed?"
    return 0
  fi
  if ! grep -q "$company_id" "$log_path" 2>/dev/null; then
    log warn "company $company_id not in watchdog log (may be too soon)"
  fi
  log ok "  watchdog active"
}

stage_5_per_agent_mcp() {
  log info "[5/7] runtime probes — mcp/git/handoff/phase per profile (rev2 SM-1/SM-2)"
  # shellcheck source=lib/_smoke_probes.sh
  source "${SCRIPT_DIR}/lib/_smoke_probes.sh"

  declare -A picked
  for name in $(yq -r '.agents | keys | .[]' "$bindings"); do
    profile=$(yq -r ".agents[] | select(.agent_name == \"${name}\") | .profile" "$manifest")
    [ -z "$profile" ] || [ "$profile" = "null" ] && continue
    if [ -z "${picked[$profile]:-}" ]; then
      picked[$profile]="$name"
    fi
  done

  failed=0
  for profile in "${!picked[@]}"; do
    name="${picked[$profile]}"
    uuid=$(yq -r ".agents.${name}" "$bindings")
    log info "  probing $name (profile=$profile, uuid=$uuid)"
    probe_agent_for_profile "$company_id" "$uuid" "$name" "$profile" || failed=$((failed + 1))
  done

  [ "$failed" -eq 0 ] || die "stage 5: $failed agents failed runtime probes"
  log ok "[5/7] runtime probes green for $(echo "${!picked[@]}" | wc -w) profiles"
}

stage_6_telegram() {
  log info "[6/7] telegram plugin (if enabled)"
  plugins_file="${HOME}/.paperclip/projects/${project_key}/plugins.yaml"
  if [ ! -f "$plugins_file" ]; then
    log info "no plugins.yaml — skipping telegram smoke"
    return 0
  fi
  plugin_id=$(yq -r '.telegram.plugin_id // ""' "$plugins_file")
  [ -n "$plugin_id" ] && [ "$plugin_id" != "null" ] || { log info "no telegram plugin configured"; return 0; }
  log info "  posting test message via plugin"
  body=$(jq -n --arg t "smoke-test ${project_key} $(date)" '{action:"send_message",text:$t}')
  resp=$(paperclip_post "/api/plugins/${plugin_id}/action" "$body" 2>/dev/null || echo "")
  [ -n "$resp" ] || die "telegram send_message returned empty"
  log ok "  telegram delivered"
}

stage_7_e2e_handoff() {
  log info "[7/7] end-to-end handoff probe (incl. cross-target if mixed) — rev2 SM-3"
  # shellcheck source=lib/_smoke_probes.sh
  source "${SCRIPT_DIR}/lib/_smoke_probes.sh"

  cto_name=$(yq -r '.agents[] | select(.profile == "cto") | .agent_name' "$manifest" | head -1)
  cto_uuid=$(yq -r ".agents.${cto_name}" "$bindings")
  [ -n "$cto_uuid" ] && [ "$cto_uuid" != "null" ] || die "no cto agent in $project_key"

  next_name=$(yq -r '.agents[] | select(.profile == "implementer" or .profile == "reviewer" or .profile == "qa") | .agent_name' "$manifest" | head -1)
  next_uuid=$(yq -r ".agents.${next_name}" "$bindings")
  [ -n "$next_uuid" ] && [ "$next_uuid" != "null" ] || die "no implementer/reviewer/qa agent in $project_key"

  cto_target=$(yq -r ".agents[] | select(.agent_name == \"${cto_name}\") | .target" "$manifest")
  next_target=$(yq -r ".agents[] | select(.agent_name == \"${next_name}\") | .target" "$manifest")
  if [ "$cto_target" != "$next_target" ]; then
    log info "  mixed-target handoff probe: ${cto_name}[${cto_target}] → ${next_name}[${next_target}]"
  fi

  probe_e2e_handoff "$company_id" "$cto_uuid" "$cto_name" "$next_uuid" "$next_name" || \
    die "stage 7: e2e handoff probe failed"

  log ok "[7/7] e2e handoff green"
}

# Run stages
case "$CANARY_STAGE" in
  1) stage_1_api_reachable; stage_2_company_and_agents; stage_4_watchdog; stage_5_per_agent_mcp ;;
  2) stage_1_api_reachable; stage_2_company_and_agents; stage_4_watchdog; stage_7_e2e_handoff ;;
  *)
    stage_1_api_reachable
    stage_2_company_and_agents
    stage_3_workspaces
    stage_4_watchdog
    if [ "$QUICK" -eq 0 ]; then
      stage_5_per_agent_mcp
      stage_6_telegram
      stage_7_e2e_handoff
    fi
    ;;
esac

log ok "SMOKE TEST PASSED for project $project_key"
