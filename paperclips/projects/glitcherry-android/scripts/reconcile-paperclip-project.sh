#!/usr/bin/env bash
# Reconcile the Glitcherry Paperclip Project and its single repository anchor.

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
PROJECT_WORKSPACE_NAME="Glitcherry Android"
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

Creates or reuses one exact Paperclip Project and one primary Project workspace.
Existing legacy role workspaces are retained as historical records but are no
longer selected or mutated.
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

validate_directory() {
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
}

validate_workspace_directory() {
  local directory_path="$1"
  local label="$2"
  validate_directory "$directory_path" "$label"
  [ -f "${directory_path}/AGENTS.md" ] && [ ! -L "${directory_path}/AGENTS.md" ] || \
    die "$label has no generated AGENTS.md"
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
PRIMARY_REPO_ROOT="$(yq -r '.primary_repo_root // ""' "$PATHS_FILE")"
[ -n "$PRIMARY_REPO_ROOT" ] || die "primary_repo_root is missing"
TASK_WORKTREE_ROOT="$(yq -r '.task_worktree_root // ""' "$PATHS_FILE")"
[ -n "$TASK_WORKTREE_ROOT" ] || die "task_worktree_root is missing"
validate_workspace_directory "$PRIMARY_REPO_ROOT" "primary Android repository"
git -C "$PRIMARY_REPO_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1 || \
  die "primary Android repository is not a Git worktree"
validate_directory "$TASK_WORKTREE_ROOT" "task worktree root"

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
      '{name:$name,description:"One repository anchor with one isolated execution workspace per Glitcherry slice.",status:"in_progress",leadAgentId:$lead}')"
    PROJECT_ID="$(paperclip_post "/api/companies/${COMPANY_ID}/projects" "$project_payload" | jq -r '.id // ""')"
  fi
  is_uuid "$PROJECT_ID" || die "project reconciliation returned an invalid identifier"
  YQ_PROJECT_ID="$PROJECT_ID" yq -i '.project_id = strenv(YQ_PROJECT_ID)' "$BINDINGS_FILE"
  chmod 600 "$BINDINGS_FILE"
fi

workspaces_response="$(paperclip_get "/api/projects/${PROJECT_ID}/workspaces")"
workspaces="$(printf '%s' "$workspaces_response" | jq -c 'if type == "array" then . else (.workspaces // .items // []) end')"
PROJECT_WORKSPACE_ID="$(yq -r '.project_workspace_id // ""' "$BINDINGS_FILE")"
workspace_json=""

if [ -n "$PROJECT_WORKSPACE_ID" ] && [ "$PROJECT_WORKSPACE_ID" != "null" ]; then
  is_uuid "$PROJECT_WORKSPACE_ID" || die "bindings file has an invalid project workspace identifier"
  workspace_json="$(printf '%s' "$workspaces" | jq -c --arg id "$PROJECT_WORKSPACE_ID" '[.[] | select(.id == $id)] | if length == 1 then .[0] else empty end')"
  [ -n "$workspace_json" ] || die "bound project workspace is absent from the bound project"
else
  matching_count="$(printf '%s' "$workspaces" | jq \
    --arg name "$PROJECT_WORKSPACE_NAME" --arg cwd "$PRIMARY_REPO_ROOT" \
    '[.[] | select(.name == $name or .cwd == $cwd)] | length')"
  [ "$matching_count" -le 1 ] || die "multiple workspaces match the Glitcherry repository anchor"
  if [ "$matching_count" -eq 1 ]; then
    workspace_json="$(printf '%s' "$workspaces" | jq -c \
      --arg name "$PROJECT_WORKSPACE_NAME" --arg cwd "$PRIMARY_REPO_ROOT" \
      '.[] | select(.name == $name or .cwd == $cwd)')"
  else
    workspace_payload="$(jq -n \
      --arg name "$PROJECT_WORKSPACE_NAME" \
      --arg cwd "$PRIMARY_REPO_ROOT" \
      '{name:$name,sourceType:"local_path",cwd:$cwd,isPrimary:true,visibility:"advanced",defaultRef:"develop"}')"
    workspace_json="$(paperclip_post "/api/projects/${PROJECT_ID}/workspaces" "$workspace_payload")"
  fi
  PROJECT_WORKSPACE_ID="$(printf '%s' "$workspace_json" | jq -r '.id // ""')"
  is_uuid "$PROJECT_WORKSPACE_ID" || die "project workspace reconciliation returned an invalid identifier"
  YQ_WORKSPACE_ID="$PROJECT_WORKSPACE_ID" \
    yq -i '.project_workspace_id = strenv(YQ_WORKSPACE_ID)' "$BINDINGS_FILE"
  chmod 600 "$BINDINGS_FILE"
fi

[ "$(printf '%s' "$workspace_json" | jq -r '.cwd // ""')" = "$PRIMARY_REPO_ROOT" ] || \
  die "bound project workspace has the wrong path"
[ "$(printf '%s' "$workspace_json" | jq -r '.sourceType // ""')" = "local_path" ] || \
  die "bound project workspace is not a local path"
if [ "$(printf '%s' "$workspace_json" | jq -r '.isPrimary // false')" != "true" ]; then
  paperclip_patch "/api/projects/${PROJECT_ID}/workspaces/${PROJECT_WORKSPACE_ID}" \
    '{"isPrimary":true}' >/dev/null
fi

project_patch="$(jq -n \
  --arg lead "$CTO_ID" \
  --arg workspace "$PROJECT_WORKSPACE_ID" \
  --arg worktreeRoot "$TASK_WORKTREE_ROOT" \
  '{status:"in_progress",leadAgentId:$lead,executionWorkspacePolicy:{enabled:true,defaultMode:"shared_workspace",allowIssueOverride:true,defaultProjectWorkspaceId:$workspace,workspaceStrategy:{type:"git_worktree",baseRef:"origin/develop",branchTemplate:"feature/{{issue.identifier}}-{{slug}}",worktreeParentDir:$worktreeRoot}}}')"
paperclip_patch "/api/projects/${PROJECT_ID}" "$project_patch" >/dev/null

final_workspaces="$(paperclip_get "/api/projects/${PROJECT_ID}/workspaces")"
final_workspaces="$(printf '%s' "$final_workspaces" | jq -c 'if type == "array" then . else (.workspaces // .items // []) end')"
[ "$(printf '%s' "$final_workspaces" | jq --arg id "$PROJECT_WORKSPACE_ID" '[.[] | select(.id == $id and .isPrimary == true)] | length')" -eq 1 ] || \
  die "Paperclip project does not expose the shared workspace as primary"

printf 'Reconciled one Glitcherry Paperclip Project with one shared repository anchor.\n'
