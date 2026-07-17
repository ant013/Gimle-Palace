#!/usr/bin/env bash
# UAA Phase C2: per-project hire + deploy + smoke per spec §9.2.
#
# Idempotent. Journal-snapshotted (per spec §8.5). Supports --canary 2-stage
# deploy (writer/research first, then cto, then fan-out per spec §8.6).
# Topological hire ordering by reportsTo dependency graph.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# shellcheck source=lib/_common.sh
source "${SCRIPT_DIR}/lib/_common.sh"
# shellcheck source=lib/_paperclip_api.sh
source "${SCRIPT_DIR}/lib/_paperclip_api.sh"
# shellcheck source=lib/_journal.sh
source "${SCRIPT_DIR}/lib/_journal.sh"
# shellcheck source=lib/_prompts.sh
source "${SCRIPT_DIR}/lib/_prompts.sh"

CANARY=0
CONFIG_FILE=""
REUSE_BINDINGS=""
PRUNE=0
project_key=""

while [ $# -gt 0 ]; do
  case "$1" in
    --canary) CANARY=1; shift ;;
    --config) CONFIG_FILE="$2"; shift 2 ;;
    --reuse-bindings) REUSE_BINDINGS="$2"; shift 2 ;;
    --prune) PRUNE=1; shift ;;
    -h|--help)
      cat <<EOF
Usage:
  $(basename "$0") <project-key>                          # interactive bootstrap
  $(basename "$0") <project-key> --config FILE            # non-interactive
  $(basename "$0") <project-key> --reuse-bindings FILE    # migrate from legacy UUIDs
  $(basename "$0") <project-key> --canary                 # 2-stage canary deploy
  $(basename "$0") <project-key> --prune                  # remove agents in bindings but not in manifest

Per UAA spec §9.2 — 13 steps (idempotent, journal-snapshotted).
EOF
      exit 0
      ;;
    *) project_key="$1"; shift ;;
  esac
done

[ -n "$project_key" ] || die "project-key required (try --help)"
validate_project_key "$project_key"

require_command yq
require_command jq
require_command python3
require_env PAPERCLIP_API_URL
require_env PAPERCLIP_API_KEY

manifest="${REPO_ROOT}/paperclips/projects/${project_key}/paperclip-agent-assembly.yaml"
[ -f "$manifest" ] || die "manifest not found: $manifest"

# Step 1: validate manifest
log info "[1/13] validating manifest"
"${SCRIPT_DIR}/validate-manifest.sh" "$project_key" || die "manifest validation failed"

# Step 2: journal snapshot
log info "[2/13] opening journal"
journal=$(journal_open "bootstrap-${project_key}")
log ok "journal: $journal"

# Step 3: host paths setup
log info "[3/13] host-local directory setup"
host_dir="${HOME}/.paperclip/projects/${project_key}"
host_dir_preexisting=0
[ -d "$host_dir" ] && host_dir_preexisting=1
mkdir -p "$host_dir"
if [ "$host_dir_preexisting" -eq 0 ]; then
  journal_record "$journal" "$(jq -n --arg p "$host_dir" '{kind:"host_directory_create",path:$p}')"
fi
bindings="${host_dir}/bindings.yaml"
paths_file="${host_dir}/paths.yaml"
plugins_file="${host_dir}/plugins.yaml"
bindings_preexisting=0
[ -f "$bindings" ] && bindings_preexisting=1

record_host_file_create() {
  local path="$1"
  journal_record "$journal" "$(jq -n --arg p "$path" '{kind:"host_file_create",path:$p}')"
}

# Step 4: paths.yaml (prompt or load from --config)
if [ ! -f "$paths_file" ]; then
  if [ -n "$CONFIG_FILE" ] && [ -f "$CONFIG_FILE" ]; then
    log info "loading paths from $CONFIG_FILE"
    cp "$CONFIG_FILE" "$paths_file"
  else
    log info "interactive paths.yaml setup"
    proot=$(prompt_with_default "Local project root" "/Users/Shared/${project_key^}")
    twroot=$(prompt_with_default "Team workspace root" "/Users/Shared/runs/${project_key}")
    pcheckout=$(prompt_with_default "Production checkout" "$proot")
    cat > "$paths_file" <<EOF
schemaVersion: 2
project_root: "${proot}"
primary_repo_root: "${proot}"
production_checkout: "${pcheckout}"
team_workspace_root: "${twroot}"
operator_memory_dir: "${HOME}/.claude/projects/-${project_key}/memory"
overlay_root: "paperclips/projects/${project_key}/overlays"
EOF
    log ok "wrote $paths_file"
  fi
  chmod 600 "$paths_file"
  record_host_file_create "$paths_file"
fi

# Resolve load-bearing reference roots only from host-local paths.yaml. The
# committed manifest carries key names, never operator-specific absolute paths.
while IFS= read -r required_key; do
  [ -z "$required_key" ] && continue
  [[ "$required_key" =~ ^[a-z][a-z0-9_]*$ ]] || \
    die "invalid host-local path key in host_paths.required_existing: $required_key"
  required_value=$(yq -r ".[\"${required_key}\"] // \"\"" "$paths_file")
  [ -n "$required_value" ] && [ "$required_value" != "null" ] || \
    die "required host-local path '$required_key' is unresolved in $paths_file"
  case "$required_value" in
    /*) ;;
    *) die "required host-local path '$required_key' must be absolute: $required_value" ;;
  esac
  [ -d "$required_value" ] || \
    die "required host-local path '$required_key' does not exist: $required_value"
done < <(yq -r '.host_paths.required_existing[]? // ""' "$manifest")

# Step 5: company create-or-reuse
log info "[5/13] company create-or-reuse"
if [ -n "$REUSE_BINDINGS" ]; then
  if [ "$REUSE_BINDINGS" != "$bindings" ]; then
    cp "$REUSE_BINDINGS" "$bindings"
  else
    log info "bindings already at canonical location, skip cp"
  fi
  log info "imported bindings from $REUSE_BINDINGS"
  if [ "$bindings_preexisting" -eq 0 ]; then
    chmod 600 "$bindings"
    record_host_file_create "$bindings"
    bindings_preexisting=1
  fi
fi

company_id=""
if [ -f "$bindings" ]; then
  company_id=$(yq -r '.company_id // ""' "$bindings")
fi

display_name=$(yq -r '.project.display_name' "$manifest")
issue_prefix=$(yq -r '.project.issue_prefix' "$manifest")
[ -n "$display_name" ] && [ "$display_name" != "null" ] || die "project.display_name missing"
[[ "$issue_prefix" =~ ^[A-Z]{3}$ ]] || \
  die "invalid project.issue_prefix for pinned Paperclip runtime (expected exactly three uppercase letters): $issue_prefix"

companies_resp=$(paperclip_get "/api/companies")
prefix_owner=$(printf '%s' "$companies_resp" | jq -r --arg prefix "$issue_prefix" '
  (if type == "array" then . else (.companies // .items // []) end)
  | map(select((.issuePrefix // .issue_prefix // "") == $prefix))
  | first.id // ""
')

if [ -z "${company_id}" ] || [ "$company_id" = "null" ]; then
  [ -z "$prefix_owner" ] || \
    die "issue prefix $issue_prefix is already allocated to company $prefix_owner"
  log info "creating new company with temporary prefix seed: $issue_prefix"
  company_resp=$(paperclip_post "/api/companies" "$(jq -n --arg n "$issue_prefix" '{name:$n}')")
  company_id=$(echo "$company_resp" | jq -r '.id')
  [ -n "$company_id" ] && [ "$company_id" != "null" ] || die "company creation returned no id"

  rollback_created_company_or_die() {
    local reason="$1"
    if paperclip_delete_company "$company_id" >/dev/null; then
      journal_finalize "$journal" "failure" || \
        log warn "failed to finalize journal after company compensation: $journal"
      die "$reason; exact created company $company_id was rolled back"
    fi
    journal_finalize "$journal" "failure" || true
    die "$reason; automatic rollback of exact created company $company_id failed — replay $journal"
  }

  company_journal_entry=$(jq -n \
    --arg n "$display_name" \
    --arg creation_name "$issue_prefix" \
    --arg id "$company_id" \
    --arg prefix "$issue_prefix" \
    '{kind:"company_create",name:$n,creation_name:$creation_name,id:$id,issue_prefix:$prefix}')
  journal_record "$journal" "$company_journal_entry" || \
    rollback_created_company_or_die "failed to journal newly created company"

  created_company=$(paperclip_get "/api/companies/${company_id}") || \
    rollback_created_company_or_die "new company $company_id is not readable"
  created_name=$(printf '%s' "$created_company" | jq -r '.name // ""')
  created_prefix=$(printf '%s' "$created_company" | jq -r '.issuePrefix // .issue_prefix // ""')
  [ "$created_name" = "$issue_prefix" ] || \
    rollback_created_company_or_die "new company seed-name mismatch: expected $issue_prefix, got ${created_name:-<empty>}"
  [ "$created_prefix" = "$issue_prefix" ] || \
    rollback_created_company_or_die "new company prefix mismatch: expected $issue_prefix, got ${created_prefix:-<empty>}"

  paperclip_patch "/api/companies/${company_id}" \
    "$(jq -n --arg n "$display_name" '{name:$n}')" >/dev/null || \
    rollback_created_company_or_die "failed to rename new company to $display_name"

  final_company=$(paperclip_get "/api/companies/${company_id}") || \
    rollback_created_company_or_die "renamed company $company_id is not readable"
  final_name=$(printf '%s' "$final_company" | jq -r '.name // ""')
  final_prefix=$(printf '%s' "$final_company" | jq -r '.issuePrefix // .issue_prefix // ""')
  [ "$final_name" = "$display_name" ] || \
    rollback_created_company_or_die "final company name mismatch: expected $display_name, got ${final_name:-<empty>}"
  [ "$final_prefix" = "$issue_prefix" ] || \
    rollback_created_company_or_die "final company prefix mismatch: expected $issue_prefix, got ${final_prefix:-<empty>}"

  cat > "$bindings" <<EOF
schemaVersion: 2
company_id: "${company_id}"
agents: {}
EOF
  chmod 600 "$bindings"
  chmod 700 "$(dirname "$bindings")"
  if [ "$bindings_preexisting" -eq 0 ]; then
    record_host_file_create "$bindings"
    bindings_preexisting=1
  fi
  log ok "company created: $company_id"
else
  company_resp=$(paperclip_get "/api/companies/${company_id}") || \
    die "bound company $company_id not found"
  live_name=$(printf '%s' "$company_resp" | jq -r '.name // ""')
  live_prefix=$(printf '%s' "$company_resp" | jq -r '.issuePrefix // .issue_prefix // ""')
  [ "$live_name" = "$display_name" ] || \
    die "bound company $company_id display name mismatch: expected $display_name, got ${live_name:-<empty>}"
  [ "$live_prefix" = "$issue_prefix" ] || \
    die "bound company $company_id prefix mismatch: expected $issue_prefix, got ${live_prefix:-<empty>}"
  [ -z "$prefix_owner" ] || [ "$prefix_owner" = "$company_id" ] || \
    die "issue prefix $issue_prefix is already allocated to company $prefix_owner"
  log ok "company reused: $company_id"
fi

# Step 6: topological hire ordering
log info "[6/13] topological hire ordering by reportsTo"

hire_order=$(python3 - <<PY
import yaml, sys
m = yaml.safe_load(open("$manifest"))
agents = m.get("agents", [])
deps = {a["agent_name"]: a.get("reportsTo") for a in agents}
order = []
visited = set()
visiting = set()
def visit(n, path):
    if n in visited: return
    if n in visiting:
        cycle = " -> ".join(path + [n])
        print(f"ERROR: reportsTo cycle: {cycle}", file=sys.stderr)
        sys.exit(1)
    visiting.add(n)
    parent = deps.get(n)
    if parent and parent in deps:
        visit(parent, path + [n])
    visiting.discard(n)
    visited.add(n)
    order.append(n)
for a in agents:
    visit(a["agent_name"], [])
print("\n".join(order))
PY
) || die "topological hire ordering failed"

log info "hire order: $(echo "$hire_order" | tr '\n' ' ')"

# Step 7: hire each agent
for agent_name in $hire_order; do
  validate_agent_name "$agent_name"
  # Bracket-syntax: kebab agent_names (e.g., `cx-cto`) — yq dot-path would treat `-` as subtraction.
  existing=$(yq -r ".agents[\"${agent_name}\"] // \"\"" "$bindings")
  if [ -n "$existing" ] && [ "$existing" != "null" ]; then
    if paperclip_get_agent_config "$existing" >/dev/null 2>&1; then
      log info "agent $agent_name already hired: $existing"
      continue
    else
      log warn "agent $agent_name UUID $existing not found in API — will re-hire"
    fi
  fi

  agent_meta=$(yq -o=json ".agents[] | select(.agent_name == \"${agent_name}\")" "$manifest")
  role=$(echo "$agent_meta" | jq -r '.role_source')
  target=$(echo "$agent_meta" | jq -r '.target')
  reports_to_name=$(echo "$agent_meta" | jq -r '.reportsTo // ""')
  reports_to_uuid=""
  if [ -n "$reports_to_name" ] && [ "$reports_to_name" != "null" ]; then
    # Security H2-followup CRIT-1: validate + use bracket-syntax — same protection
    # as agent_name (yq dot-path would interpret `-` as subtraction; unvalidated
    # reportsTo from manifest could yq-inject).
    validate_agent_name "$reports_to_name"
    reports_to_uuid=$(yq -r ".agents[\"${reports_to_name}\"] // \"\"" "$bindings")
    [ -n "$reports_to_uuid" ] || die "reportsTo $reports_to_name has no UUID (topo order broken?)"
  fi

  team_root=$(yq -r '.team_workspace_root // ""' "$paths_file")
  cwd="${team_root}/${agent_name}/workspace"

  # Per-agent role/icon/model. Explicit Paperclip identity wins; profile fallback
  # preserves legacy manifests that predate paperclip_role/paperclip_icon.
  profile_name=$(echo "$agent_meta" | jq -r '.profile')
  case "$profile_name" in
    cto)         fallback_role="cto";         fallback_icon="🧠" ;;
    reviewer)    fallback_role="reviewer";    fallback_icon="🔎" ;;
    implementer) fallback_role="implementer"; fallback_icon="🛠" ;;
    qa)          fallback_role="qa";          fallback_icon="🧪" ;;
    research)    fallback_role="research";    fallback_icon="📚" ;;
    writer)      fallback_role="writer";      fallback_icon="✍" ;;
    minimal|custom) fallback_role="implementer"; fallback_icon="🧑" ;;
    *) die "unknown profile '$profile_name' for agent $agent_name" ;;
  esac
  hire_role=$(echo "$agent_meta" | jq -r --arg fallback "$fallback_role" '.paperclip_role // $fallback')
  hire_icon=$(echo "$agent_meta" | jq -r --arg fallback "$fallback_icon" '.paperclip_icon // $fallback')

  agent_model=$(echo "$agent_meta" | jq -r '.model // "auto"')
  agent_effort=$(echo "$agent_meta" | jq -r '.modelReasoningEffort // "medium"')

  payload=$(jq -n \
    --arg name "$agent_name" \
    --arg role "$hire_role" \
    --arg title "$agent_name" \
    --arg icon "$hire_icon" \
    --arg cwd "$cwd" \
    --arg reportsTo "$reports_to_uuid" \
    --arg adapter "${target}_local" \
    --arg model "$agent_model" \
    --arg effort "$agent_effort" \
    '{
      name: $name, role: $role, title: $title, icon: $icon,
      reportsTo: $reportsTo, capabilities: "default",
      adapterType: $adapter,
      adapterConfig: {
        cwd: $cwd, model: $model, modelReasoningEffort: $effort,
        instructionsFilePath: "AGENTS.md", instructionsEntryFile: "AGENTS.md",
        instructionsBundleMode: "managed",
        maxTurnsPerRun: 200, timeoutSec: 0, graceSec: 15,
        dangerouslyBypassApprovalsAndSandbox: true, env: {}
      },
      runtimeConfig: {
        heartbeat: {
          enabled: false, intervalSec: 14400, wakeOnDemand: true,
          maxConcurrentRuns: 1, cooldownSec: 10
        }
      },
      budgetMonthlyCents: 0
    }')

  log info "hiring $agent_name (profile=$profile_name target=$target)"
  resp=$(paperclip_hire_agent "$company_id" "$payload")
  agent_id=$(echo "$resp" | jq -r '.agent.id // .id')
  [ -n "$agent_id" ] && [ "$agent_id" != "null" ] || die "hire returned no id for $agent_name"

  yq -i ".agents[\"${agent_name}\"] = \"${agent_id}\"" "$bindings"
  journal_record "$journal" "$(jq -n --arg n "$agent_name" --arg id "$agent_id" '{kind:"agent_hire",name:$n,id:$id}')"
  log ok "hired $agent_name → $agent_id"
done

# Step 8: telegram plugin config (if plugins.yaml exists)
if [ -f "$plugins_file" ]; then
  log info "[8/13] telegram plugin config"
  plugin_id=$(yq -r '.telegram.plugin_id // ""' "$plugins_file")
  chat_id=$(yq -r '.telegram.chat_id // ""' "$plugins_file")
  if [ -n "$plugin_id" ] && [ -n "$chat_id" ] && [ "$chat_id" != "<operator-fills>" ]; then
    log info "  configuring plugin $plugin_id with chat $chat_id"
    # rev2 F-1: GET → diff → POST (replace mode per spec §8.4)
    # CRIT-2 fix: snapshot current_config BEFORE POST so rollback can restore.
    # IMP-B fix: _safe variant treats 404 as empty {} but dies on 401/403/5xx
    #   so an expired JWT cannot silently wipe defaultChatId.
    current_config=$(paperclip_plugin_get_config_safe "$plugin_id") || \
      die "plugin GET failed for $plugin_id (likely auth issue — check PAPERCLIP_API_KEY)"
    journal_record "$journal" "$(jq -n \
      --arg pid "$plugin_id" \
      --argjson cfg "$current_config" \
      '{kind:"plugin_config_snapshot",plugin_id:$pid,old_config:$cfg}')"
    new_config=$(echo "$current_config" | jq --arg cid "$chat_id" '.config.defaultChatId = $cid')
    paperclip_plugin_set_config "$plugin_id" "$new_config" >/dev/null
    log ok "  telegram plugin configured"
  else
    log info "  plugins.yaml present but telegram chat_id empty/placeholder — skipping"
  fi
else
  log info "[8/13] no plugins.yaml; skipping telegram config"
fi

# Step 9: build prompts
log info "[9/13] building agent prompts"
targets_used=$(yq -r '.agents[].target' "$manifest" | sort -u)
for target in $targets_used; do
  log info "  building target=$target"
  "${REPO_ROOT}/paperclips/build.sh" --project "$project_key" --target "$target" || \
    die "build failed for project=$project_key target=$target"
done

# Step 10: deploy (with optional canary)
log info "[10/13] deploying agent prompts"

deploy_one() {
  local agent_name="$1"
  validate_agent_name "$agent_name"
  local agent_id
  agent_id=$(yq -r ".agents[\"${agent_name}\"]" "$bindings")
  local target
  target=$(yq -r ".agents[] | select(.agent_name == \"${agent_name}\") | .target" "$manifest")
  # Phase H2-followup: prefer manifest's per-agent `output_path` (Phase G gimle uses
  # `legacy_output_paths: true` which writes to paperclips/dist/<name>.md, NOT the
  # canonical paperclips/dist/<project>/<target>/<name>.md). Fall back to canonical.
  local content_path raw_output_path
  raw_output_path=$(yq -r ".agents[] | select(.agent_name == \"${agent_name}\") | .output_path // \"paperclips/dist/${project_key}/${target}/${agent_name}.md\"" "$manifest")
  # Security H2-followup CRIT-2: guard against path traversal in `output_path`.
  # Without this, a malicious manifest with `output_path: /etc/passwd` (absolute) or
  # `../../../etc/shadow` (traversal) would exfiltrate arbitrary files through the
  # PUT-AGENTS.md API call below.
  validate_safe_repo_path "$raw_output_path"
  content_path="${REPO_ROOT}/${raw_output_path}"
  [ -f "$content_path" ] || die "rendered AGENTS.md missing: $content_path"

  # CRIT-1 fix: snapshot OLD AGENTS.md content (kind matches rollback.sh handler).
  local old_content
  old_content=$(paperclip_get_agent_instructions "$agent_id") || \
    die "deploy: failed to fetch current AGENTS.md for agent $agent_id (HTTP error — check JWT)"
  journal_record "$journal" "$(jq -n \
    --arg id "$agent_id" \
    --arg old "$old_content" \
    '{kind:"agent_instructions_snapshot",agent_id:$id,old_content:$old}')"

  content=$(cat "$content_path")
  paperclip_deploy_agents_md "$agent_id" "$content" >/dev/null
  log ok "deployed $agent_name"
}

if [ "$CANARY" -eq 1 ]; then
  log info "CANARY mode: 2-stage deploy per spec §8.6"
  # Stage 1: read-only canary
  canary_1=$(yq -r '.agents[] | select(.profile == "writer" or .profile == "research" or .profile == "qa") | .agent_name' "$manifest" | head -1)
  [ -n "$canary_1" ] || canary_1=$(yq -r '.agents[0].agent_name' "$manifest")
  log info "Stage 1 canary: $canary_1"
  deploy_one "$canary_1"

  # Stage 2: cto
  canary_2=$(yq -r '.agents[] | select(.workflow_role == "inner_orchestrator") | .agent_name' "$manifest" | head -1)
  [ -n "$canary_2" ] || \
    canary_2=$(yq -r '.agents[] | select(.profile == "cto") | .agent_name' "$manifest" | head -1)
  if [ -n "$canary_2" ]; then
    log info "Stage 2 canary: $canary_2"
    deploy_one "$canary_2"
  fi

  # Stage 3: fan-out
  for agent_name in $hire_order; do
    if [ "$agent_name" != "$canary_1" ] && [ "$agent_name" != "$canary_2" ]; then
      deploy_one "$agent_name"
    fi
  done
else
  for agent_name in $hire_order; do
    deploy_one "$agent_name"
  done
fi

# Step 11: workspaces
log info "[11/13] setting up workspaces"
team_root=$(yq -r '.team_workspace_root' "$paths_file")
for agent_name in $hire_order; do
  ws="${team_root}/${agent_name}/workspace"
  workspace_created=0
  if [ ! -d "$ws" ]; then
    mkdir -p "$ws"
    workspace_created=1
    journal_record "$journal" "$(jq -n \
      --arg p "$ws" \
      --arg f "AGENTS.md" \
      '{kind:"managed_workspace_create",path:$p,managed_file:$f}')"
  fi
  target=$(yq -r ".agents[] | select(.agent_name == \"${agent_name}\") | .target" "$manifest")
  # Phase H2-followup: honor manifest `output_path` (same logic as deploy_one).
  cp_src=$(yq -r ".agents[] | select(.agent_name == \"${agent_name}\") | .output_path // \"paperclips/dist/${project_key}/${target}/${agent_name}.md\"" "$manifest")
  # Security H2-followup CRIT-2: same traversal guard as deploy_one.
  validate_safe_repo_path "$cp_src"
  if [ "$workspace_created" -eq 0 ] && [ -f "${ws}/AGENTS.md" ]; then
    old_workspace_content=$(cat "${ws}/AGENTS.md")
    journal_record "$journal" "$(jq -n \
      --arg p "${ws}/AGENTS.md" \
      --arg old "$old_workspace_content" \
      '{kind:"workspace_file_snapshot",path:$p,old_content:$old}')"
  fi
  cp "${REPO_ROOT}/${cp_src}" "${ws}/AGENTS.md"
done

# Step 12: codex subagents deploy
log info "[12/13] codex subagents (.toml deploy)"
codex_agents_dir="${REPO_ROOT}/paperclips/projects/${project_key}/codex-agents"
if [ -d "$codex_agents_dir" ]; then
  if [ "$project_key" = "uaudit" ]; then
    backup_dir="${HOME}/.paperclip/projects/${project_key}/backups/uaudit-codex-agents"
    python3 "${SCRIPT_DIR}/install_uaudit_codex_agents.py" \
      --source-dir "$codex_agents_dir" \
      --codex-home "${SHARED_CODEX_HOME:-${HOME}/.codex}" \
      --backup-dir "$backup_dir" \
      || die "UAudit codex subagent install failed"
    log ok "uaudit codex subagents installed into runtime-visible Codex home"
  else
    target_dir="${HOME}/.codex/projects/${project_key}/agents"
    mkdir -p "$target_dir"
    cp "$codex_agents_dir"/*.toml "$target_dir/" 2>/dev/null || true
    log ok "codex subagents deployed to $target_dir"
  fi
fi

# Step 13: bootstrap watchdog
log info "[13/13] bootstrap-watchdog"
watchdog_config="${HOME}/.paperclip/watchdog-config.yaml"
watchdog_plist="${HOME}/Library/LaunchAgents/work.ant013.gimle-watchdog.plist"
watchdog_config_existed=false
watchdog_plist_existed=false
watchdog_config_content=""
watchdog_plist_content=""
if [ -f "$watchdog_config" ]; then
  watchdog_config_existed=true
  watchdog_config_content=$(cat "$watchdog_config")
fi
if [ -f "$watchdog_plist" ]; then
  watchdog_plist_existed=true
  watchdog_plist_content=$(cat "$watchdog_plist")
fi
journal_record "$journal" "$(jq -n \
  --arg project "$project_key" \
  --arg company "$company_id" \
  --arg config_path "$watchdog_config" \
  --arg config_content "$watchdog_config_content" \
  --arg plist_path "$watchdog_plist" \
  --arg plist_content "$watchdog_plist_content" \
  --argjson config_existed "$watchdog_config_existed" \
  --argjson plist_existed "$watchdog_plist_existed" \
  '{kind:"watchdog_snapshot",project_key:$project,company_id:$company,
    config_path:$config_path,config_existed:$config_existed,config_content:$config_content,
    plist_path:$plist_path,plist_existed:$plist_existed,plist_content:$plist_content}')"
"${SCRIPT_DIR}/bootstrap-watchdog.sh" "$project_key"

journal_finalize "$journal" "success"
log ok "bootstrap complete for $project_key"
log ok "journal: $journal"
log info "next: ./paperclips/scripts/smoke-test.sh $project_key"
