#!/usr/bin/env bash
# Reconcile the Glitcherry Paperclip Project and one local workspace per agent.

set -euo pipefail
umask 077

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../../.." && pwd)"

# shellcheck source=../../../scripts/lib/_common.sh
source "${REPO_ROOT}/paperclips/scripts/lib/_common.sh"
# shellcheck source=../../../scripts/lib/_paperclip_api.sh
source "${REPO_ROOT}/paperclips/scripts/lib/_paperclip_api.sh"

PROJECT_KEY="glitcherry-android"
PROJECT_NAME="Glitcherry Android Development"
MANIFEST="${REPO_ROOT}/paperclips/projects/${PROJECT_KEY}/paperclip-agent-assembly.yaml"
PATHS_FILE="${HOME}/.paperclip/projects/${PROJECT_KEY}/paths.yaml"
BINDINGS_FILE="${HOME}/.paperclip/projects/${PROJECT_KEY}/bindings.yaml"

usage() {
  cat <<'USAGE'
Usage: reconcile-paperclip-project.sh [options]

Options:
  --manifest FILE   Assembly manifest.
  --paths FILE      Host-local paths.yaml (mode 600).
  --bindings FILE   Host-local bindings.yaml (mode 600).
  -h, --help        Show this help.

Creates or reuses one exact Paperclip Project and six local Project workspaces.
It never creates issues, wakes agents, deletes resources, or stores credentials.
USAGE
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --manifest)
      [ "$#" -ge 2 ] || die "--manifest requires a file"
      MANIFEST="$2"
      shift 2
      ;;
    --paths)
      [ "$#" -ge 2 ] || die "--paths requires a file"
      PATHS_FILE="$2"
      shift 2
      ;;
    --bindings)
      [ "$#" -ge 2 ] || die "--bindings requires a file"
      BINDINGS_FILE="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *) die "unknown option" ;;
  esac
done

for command_name in curl jq python3 yq; do
  require_command "$command_name"
done
require_env PAPERCLIP_API_URL
require_env PAPERCLIP_API_KEY

validate_private_file() {
  local file_path="$1"
  local label="$2"
  python3 - "$file_path" <<'PY' >/dev/null 2>&1 || die "$label must be an owner-controlled regular mode-600 file"
import os
import stat
import sys

value = os.lstat(sys.argv[1])
valid = (
    stat.S_ISREG(value.st_mode)
    and value.st_uid == os.getuid()
    and stat.S_IMODE(value.st_mode) == 0o600
)
raise SystemExit(0 if valid else 1)
PY
}

validate_workspace_directory() {
  local directory_path="$1"
  local label="$2"
  python3 - "$directory_path" <<'PY' >/dev/null 2>&1 || die "$label must be an existing absolute non-symlink directory"
import os
import pathlib
import stat
import sys

path = pathlib.Path(sys.argv[1])
if not path.is_absolute() or str(path) == "/" or "\n" in str(path):
    raise SystemExit(1)
try:
    value = os.lstat(path)
except OSError:
    raise SystemExit(1)
raise SystemExit(0 if stat.S_ISDIR(value.st_mode) else 1)
PY
  [ -f "${directory_path}/AGENTS.md" ] && [ ! -L "${directory_path}/AGENTS.md" ] || \
    die "$label has no generated AGENTS.md"
  [ -d "${directory_path}/repo/.git" ] && [ ! -L "${directory_path}/repo/.git" ] || \
    die "$label has no prepared Android repository"
}

is_uuid() {
  [[ "$1" =~ ^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$ ]]
}

validate_private_file "$PATHS_FILE" "paths file"
validate_private_file "$BINDINGS_FILE" "bindings file"
[ "$(yq -r '.schemaVersion // ""' "$PATHS_FILE")" = "2" ] || die "paths file schemaVersion must be 2"
[ "$(yq -r '.schemaVersion // ""' "$BINDINGS_FILE")" = "2" ] || die "bindings file schemaVersion must be 2"

COMPANY_ID="$(yq -r '.company_id // ""' "$BINDINGS_FILE")"
is_uuid "$COMPANY_ID" || die "bindings file has an invalid company identifier"
TEAM_ROOT="$(yq -r '.team_workspace_root // ""' "$PATHS_FILE")"
[ -n "$TEAM_ROOT" ] || die "team_workspace_root is missing"

AGENT_NAMES=()
while IFS= read -r agent_name; do
  [ -n "$agent_name" ] || continue
  [[ "$agent_name" =~ ^[A-Za-z][A-Za-z0-9_-]*$ ]] || die "manifest contains an unsafe agent name"
  AGENT_NAMES+=("$agent_name")
done < <(yq -r '.agents[]?.agent_name // ""' "$MANIFEST")
[ "${#AGENT_NAMES[@]}" -eq 6 ] || die "manifest must define exactly six agents"

CTO_NAME="$(yq -r '.agents[]? | select(.workflow_role == "inner_orchestrator") | .agent_name' "$MANIFEST")"
[ -n "$CTO_NAME" ] || die "manifest has no inner orchestrator"
CTO_ID="$(yq -r ".agents[\"${CTO_NAME}\"] // \"\"" "$BINDINGS_FILE")"
is_uuid "$CTO_ID" || die "bindings file has an invalid CTO identifier"

for agent_name in "${AGENT_NAMES[@]}"; do
  agent_id="$(yq -r ".agents[\"${agent_name}\"] // \"\"" "$BINDINGS_FILE")"
  is_uuid "$agent_id" || die "bindings file has an invalid agent identifier"
  validate_workspace_directory "${TEAM_ROOT}/${agent_name}/workspace" "agent workspace"
done

projects_response="$(paperclip_get "/api/companies/${COMPANY_ID}/projects")"
projects="$(printf '%s' "$projects_response" | jq -c 'if type == "array" then . else (.projects // .items // []) end')"
BOUND_PROJECT_ID="$(yq -r '.project_id // ""' "$BINDINGS_FILE")"
PROJECT_ID=""

if [ -n "$BOUND_PROJECT_ID" ] && [ "$BOUND_PROJECT_ID" != "null" ]; then
  is_uuid "$BOUND_PROJECT_ID" || die "bindings file has an invalid project identifier"
  bound_project="$(paperclip_get "/api/projects/${BOUND_PROJECT_ID}")" || die "bound project is not readable"
  [ "$(printf '%s' "$bound_project" | jq -r '.companyId // ""')" = "$COMPANY_ID" ] || \
    die "bound project belongs to another company"
  [ "$(printf '%s' "$bound_project" | jq -r '.name // ""')" = "$PROJECT_NAME" ] || \
    die "bound project name does not match"
  PROJECT_ID="$BOUND_PROJECT_ID"
else
  project_matches="$(printf '%s' "$projects" | jq --arg name "$PROJECT_NAME" '[.[] | select(.name == $name)] | length')"
  [ "$project_matches" -le 1 ] || die "multiple Paperclip projects have the reserved Glitcherry name"
  if [ "$project_matches" -eq 1 ]; then
    PROJECT_ID="$(printf '%s' "$projects" | jq -r --arg name "$PROJECT_NAME" '.[] | select(.name == $name) | .id')"
  else
    project_payload="$(jq -n \
      --arg name "$PROJECT_NAME" \
      --arg lead "$CTO_ID" \
      '{name:$name,description:"Persistent per-agent runtime workspaces for Glitcherry Android.",status:"in_progress",leadAgentId:$lead}')"
    PROJECT_ID="$(paperclip_post "/api/companies/${COMPANY_ID}/projects" "$project_payload" | jq -r '.id // ""')"
  fi
  is_uuid "$PROJECT_ID" || die "project reconciliation returned an invalid identifier"
  YQ_PROJECT_ID="$PROJECT_ID" yq -i '.project_id = strenv(YQ_PROJECT_ID)' "$BINDINGS_FILE"
  chmod 600 "$BINDINGS_FILE"
fi

workspaces_response="$(paperclip_get "/api/projects/${PROJECT_ID}/workspaces")"
workspaces="$(printf '%s' "$workspaces_response" | jq -c 'if type == "array" then . else (.workspaces // .items // []) end')"

is_expected_agent_name() {
  local candidate="$1"
  local expected
  for expected in "${AGENT_NAMES[@]}"; do
    [ "$candidate" = "$expected" ] && return 0
  done
  return 1
}

while IFS= read -r live_name; do
  [ -z "$live_name" ] && continue
  is_expected_agent_name "$live_name" || die "Paperclip project contains an unexpected workspace"
  live_count="$(printf '%s' "$workspaces" | jq --arg name "$live_name" '[.[] | select(.name == $name)] | length')"
  [ "$live_count" -eq 1 ] || die "Paperclip project contains duplicate named workspaces"
  live_workspace="$(printf '%s' "$workspaces" | jq -c --arg name "$live_name" '.[] | select(.name == $name)')"
  [ "$(printf '%s' "$live_workspace" | jq -r '.cwd // ""')" = "${TEAM_ROOT}/${live_name}/workspace" ] || \
    die "Paperclip project contains a workspace with the wrong path"
  [ "$(printf '%s' "$live_workspace" | jq -r '.sourceType // ""')" = "local_path" ] || \
    die "Paperclip project contains a non-local workspace"
done < <(printf '%s' "$workspaces" | jq -r '.[].name // ""')

for agent_name in "${AGENT_NAMES[@]}"; do
  desired_cwd="${TEAM_ROOT}/${agent_name}/workspace"
  bound_workspace_id="$(yq -r ".workspaces[\"${agent_name}\"] // \"\"" "$BINDINGS_FILE")"
  workspace_json=""

  if [ -n "$bound_workspace_id" ] && [ "$bound_workspace_id" != "null" ]; then
    is_uuid "$bound_workspace_id" || die "bindings file has an invalid workspace identifier"
    workspace_json="$(printf '%s' "$workspaces" | jq -c --arg id "$bound_workspace_id" '[.[] | select(.id == $id)] | if length == 1 then .[0] else empty end')"
    [ -n "$workspace_json" ] || die "bound workspace is absent from the bound project"
  else
    workspace_matches="$(printf '%s' "$workspaces" | jq --arg name "$agent_name" '[.[] | select(.name == $name)] | length')"
    [ "$workspace_matches" -le 1 ] || die "Paperclip project contains duplicate named workspaces"
    if [ "$workspace_matches" -eq 1 ]; then
      workspace_json="$(printf '%s' "$workspaces" | jq -c --arg name "$agent_name" '.[] | select(.name == $name)')"
    else
      is_primary=false
      [ "$agent_name" = "$CTO_NAME" ] && is_primary=true
      workspace_payload="$(jq -n \
        --arg name "$agent_name" \
        --arg cwd "$desired_cwd" \
        --argjson primary "$is_primary" \
        '{name:$name,sourceType:"local_path",cwd:$cwd,isPrimary:$primary,visibility:"advanced"}')"
      workspace_json="$(paperclip_post "/api/projects/${PROJECT_ID}/workspaces" "$workspace_payload")"
      workspaces="$(printf '%s' "$workspaces" | jq -c --argjson workspace "$workspace_json" '. + [$workspace]')"
    fi
    bound_workspace_id="$(printf '%s' "$workspace_json" | jq -r '.id // ""')"
    is_uuid "$bound_workspace_id" || die "workspace reconciliation returned an invalid identifier"
    YQ_AGENT_NAME="$agent_name" YQ_WORKSPACE_ID="$bound_workspace_id" \
      yq -i '.workspaces[strenv(YQ_AGENT_NAME)] = strenv(YQ_WORKSPACE_ID)' "$BINDINGS_FILE"
    chmod 600 "$BINDINGS_FILE"
  fi

  [ "$(printf '%s' "$workspace_json" | jq -r '.name // ""')" = "$agent_name" ] || \
    die "bound workspace name does not match its agent"
  [ "$(printf '%s' "$workspace_json" | jq -r '.cwd // ""')" = "$desired_cwd" ] || \
    die "bound workspace path does not match its agent"
  [ "$(printf '%s' "$workspace_json" | jq -r '.sourceType // ""')" = "local_path" ] || \
    die "bound workspace is not a local path"
done

CTO_WORKSPACE_ID="$(yq -r ".workspaces[\"${CTO_NAME}\"] // \"\"" "$BINDINGS_FILE")"
is_uuid "$CTO_WORKSPACE_ID" || die "CTO workspace binding is invalid"
project_patch="$(jq -n \
  --arg lead "$CTO_ID" \
  --arg workspace "$CTO_WORKSPACE_ID" \
  '{status:"in_progress",leadAgentId:$lead,executionWorkspacePolicy:{enabled:true,defaultMode:"shared_workspace",allowIssueOverride:true,defaultProjectWorkspaceId:$workspace}}')"
paperclip_patch "/api/projects/${PROJECT_ID}" "$project_patch" >/dev/null

final_workspaces="$(paperclip_get "/api/projects/${PROJECT_ID}/workspaces")"
final_workspaces="$(printf '%s' "$final_workspaces" | jq -c 'if type == "array" then . else (.workspaces // .items // []) end')"
[ "$(printf '%s' "$final_workspaces" | jq 'length')" -eq "${#AGENT_NAMES[@]}" ] || \
  die "Paperclip project does not contain exactly six workspaces"

printf 'Reconciled one Glitcherry Paperclip Project with %s bound workspaces.\n' "${#AGENT_NAMES[@]}"
