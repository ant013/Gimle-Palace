#!/usr/bin/env bash
# Prepare the persistent Glitcherry Git checkouts after bootstrap and before wake.

set -euo pipefail
umask 077
export GIT_TERMINAL_PROMPT=0
export GCM_INTERACTIVE=Never

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../../.." && pwd)"
PROJECT_KEY="glitcherry-android"
MANIFEST="${REPO_ROOT}/paperclips/projects/${PROJECT_KEY}/paperclip-agent-assembly.yaml"
PATHS_FILE="${HOME}/.paperclip/projects/${PROJECT_KEY}/paths.yaml"
BINDINGS_FILE="${HOME}/.paperclip/projects/${PROJECT_KEY}/bindings.yaml"
ALLOW_LOCAL_TEST_REMOTES=0
ANDROID_GITHUB_URL="https://github.com/ant013/Glitcherry-Android.git"
CONTROL_GITHUB_URL="https://github.com/ant013/Glitcherry.git"

usage() {
  cat <<'USAGE'
Usage: prepare-runtime-workspaces.sh [options]

Options:
  --manifest FILE                  Assembly manifest (normally project-owned).
  --paths FILE                     Host-local paths.yaml (mode 600).
  --bindings FILE                  Host-local bindings.yaml (mode 600).
  --allow-local-test-remotes       Allow absolute local bare repositories in tests.
  -h, --help                       Show this help.

The production path accepts only the exact ant013 Glitcherry HTTPS origins. It
prepares clean, current develop clones under each persistent agent workspace and
the CTO control clone. It never writes repository AGENTS.md or removes a
persistent workspace.
USAGE
}

die() {
  printf 'ERROR: %s\n' "$1" >&2
  exit 1
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
    --allow-local-test-remotes)
      ALLOW_LOCAL_TEST_REMOTES=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "unknown option"
      ;;
  esac
done

for command_name in git yq python3; do
  command -v "$command_name" >/dev/null 2>&1 || die "required command is unavailable: $command_name"
done

validate_regular_file() {
  local file_path="$1"
  local label="$2"
  python3 - "$file_path" <<'PY' >/dev/null 2>&1 || die "$label must be a regular non-symlink file"
import os
import stat
import sys

value = os.lstat(sys.argv[1])
raise SystemExit(0 if stat.S_ISREG(value.st_mode) else 1)
PY
}

validate_private_file() {
  local file_path="$1"
  local label="$2"
  python3 - "$file_path" <<'PY' >/dev/null 2>&1 || die "$label must be owner-controlled and mode 600"
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

validate_absolute_directory() {
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

validate_regular_file "$MANIFEST" "manifest"
validate_private_file "$PATHS_FILE" "paths file"
validate_private_file "$BINDINGS_FILE" "bindings file"

[ "$(yq -r '.schemaVersion // ""' "$PATHS_FILE")" = "2" ] || die "paths file schemaVersion must be 2"
[ "$(yq -r '.schemaVersion // ""' "$BINDINGS_FILE")" = "2" ] || die "bindings file schemaVersion must be 2"

INTEGRATION_BRANCH="$(yq -r '.project.integration_branch // ""' "$MANIFEST")"
[ "$INTEGRATION_BRANCH" = "develop" ] || die "Glitcherry integration branch must be develop"

TEAM_ROOT="$(yq -r '.team_workspace_root // ""' "$PATHS_FILE")"
ANDROID_REMOTE="$(yq -r '.android_repository_url // ""' "$PATHS_FILE")"
CONTROL_REMOTE="$(yq -r '.control_repository_url // ""' "$PATHS_FILE")"
validate_absolute_directory "$TEAM_ROOT" "team workspace root"

validate_uuid() {
  [[ "$1" =~ ^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$ ]]
}

COMPANY_ID="$(yq -r '.company_id // ""' "$BINDINGS_FILE")"
validate_uuid "$COMPANY_ID" || die "bindings file has an invalid company identifier"

AGENT_NAMES=()
while IFS= read -r agent_name; do
  [ -n "$agent_name" ] || continue
  AGENT_NAMES+=("$agent_name")
done < <(yq -r '.agents[]?.agent_name // ""' "$MANIFEST")
[ "${#AGENT_NAMES[@]}" -gt 0 ] || die "manifest has no agents"

CTO_NAMES=()
while IFS= read -r cto_name; do
  [ -n "$cto_name" ] || continue
  CTO_NAMES+=("$cto_name")
done < <(yq -r '.agents[]? | select(.workflow_role == "inner_orchestrator") | .agent_name' "$MANIFEST")
[ "${#CTO_NAMES[@]}" -eq 1 ] || die "manifest must define exactly one inner orchestrator"
CTO_NAME="${CTO_NAMES[0]}"

manifest_names_sorted="$(printf '%s\n' "${AGENT_NAMES[@]}" | LC_ALL=C sort)"
binding_names_sorted="$(yq -r '.agents | keys | .[]' "$BINDINGS_FILE" | LC_ALL=C sort)"
[ "$manifest_names_sorted" = "$binding_names_sorted" ] || die "bindings agents do not exactly match the manifest"

AGENT_IDS=()
for agent_name in "${AGENT_NAMES[@]}"; do
  [[ "$agent_name" =~ ^[A-Za-z][A-Za-z0-9_-]*$ ]] || die "manifest contains an unsafe agent name"
  agent_id="$(yq -r ".agents[\"${agent_name}\"] // \"\"" "$BINDINGS_FILE")"
  validate_uuid "$agent_id" || die "bindings file has an invalid agent identifier"
  [ "$agent_id" != "$COMPANY_ID" ] || die "bindings file reuses the company identifier for an agent"
  AGENT_IDS+=("$agent_id")
done
[ "$(printf '%s\n' "${AGENT_NAMES[@]}" | LC_ALL=C sort -u | wc -l | tr -d ' ')" -eq "${#AGENT_NAMES[@]}" ] || \
  die "manifest contains duplicate agent names"
[ "$(printf '%s\n' "${AGENT_IDS[@]}" | LC_ALL=C sort -u | wc -l | tr -d ' ')" -eq "${#AGENT_IDS[@]}" ] || \
  die "bindings file contains duplicate agent identifiers"

validate_local_remote() {
  local remote_value="$1"
  case "$remote_value" in
    /*) ;;
    *) die "test remotes must be absolute local bare repositories" ;;
  esac
  [ -d "$remote_value" ] && [ ! -L "$remote_value" ] || \
    die "test remote must be an existing local bare repository"
  [ "$(git -C "$remote_value" rev-parse --is-bare-repository 2>/dev/null || true)" = "true" ] || \
    die "test remote must be a bare repository"
}

if [ "$ALLOW_LOCAL_TEST_REMOTES" -eq 1 ]; then
  validate_local_remote "$ANDROID_REMOTE"
  validate_local_remote "$CONTROL_REMOTE"
else
  [ "$ANDROID_REMOTE" = "$ANDROID_GITHUB_URL" ] && [ "$CONTROL_REMOTE" = "$CONTROL_GITHUB_URL" ] || \
    die "repository URLs must be the exact allowlisted GitHub HTTPS origins"
fi

git ls-remote --exit-code --heads "$ANDROID_REMOTE" refs/heads/develop >/dev/null 2>&1 || \
  die "Android origin has no reachable develop branch"
git ls-remote --exit-code --heads "$CONTROL_REMOTE" refs/heads/develop >/dev/null 2>&1 || \
  die "control origin has no reachable develop branch"

workspace_for_agent() {
  printf '%s/%s/workspace' "$TEAM_ROOT" "$1"
}

validate_workspace() {
  local agent_name="$1"
  local workspace_path
  workspace_path="$(workspace_for_agent "$agent_name")"
  validate_absolute_directory "$workspace_path" "agent workspace"
  [ -f "$workspace_path/AGENTS.md" ] && [ ! -L "$workspace_path/AGENTS.md" ] || \
    die "generated workspace AGENTS.md is missing or unsafe"
}

repo_state() {
  local repo_path="$1"
  local expected_remote="$2"
  local label="$3"
  local actual_remote top_level current_head remote_head

  if [ ! -e "$repo_path" ]; then
    printf 'missing'
    return
  fi
  [ ! -L "$repo_path" ] || die "$label repository is an unmanaged symlink"
  [ -d "$repo_path" ] || die "$label repository is unmanaged"
  if [ -z "$(find "$repo_path" -mindepth 1 -maxdepth 1 -print -quit)" ]; then
    printf 'missing'
    return
  fi
  [ -d "$repo_path/.git" ] && [ ! -L "$repo_path/.git" ] || die "$label repository is unmanaged"
  top_level="$(git -C "$repo_path" rev-parse --show-toplevel 2>/dev/null || true)"
  [ -n "$top_level" ] && [ "$top_level" = "$(cd "$repo_path" && pwd -P)" ] || \
    die "$label repository is unmanaged"
  if [ "$label" = "Android" ]; then
    [ -f "$repo_path/AGENTS.md" ] && [ ! -L "$repo_path/AGENTS.md" ] || \
      die "Android repository has no regular tracked AGENTS.md"
    git -C "$repo_path" ls-files --error-unmatch -- AGENTS.md >/dev/null 2>&1 || \
      die "Android repository has no regular tracked AGENTS.md"
  fi
  actual_remote="$(git -C "$repo_path" remote get-url origin 2>/dev/null || true)"
  [ "$actual_remote" = "$expected_remote" ] || die "$label origin does not match the configured allowlist"
  [ -z "$(git -C "$repo_path" status --porcelain --untracked-files=all 2>/dev/null)" ] || \
    die "$label repository is dirty"
  [ "$(git -C "$repo_path" branch --show-current 2>/dev/null || true)" = "$INTEGRATION_BRANCH" ] || \
    die "$label repository is not on current develop"
  git -C "$repo_path" fetch --quiet origin \
    "+refs/heads/${INTEGRATION_BRANCH}:refs/remotes/origin/${INTEGRATION_BRANCH}" >/dev/null 2>&1 || \
    die "$label repository could not fetch current develop"
  current_head="$(git -C "$repo_path" rev-parse HEAD 2>/dev/null || true)"
  remote_head="$(git -C "$repo_path" rev-parse "refs/remotes/origin/${INTEGRATION_BRANCH}" 2>/dev/null || true)"
  [ -n "$current_head" ] && [ "$current_head" = "$remote_head" ] || \
    die "$label repository is not current develop"
  printf 'ready'
}

ANDROID_TARGETS=()
for agent_name in "${AGENT_NAMES[@]}"; do
  validate_workspace "$agent_name"
  workspace_path="$(workspace_for_agent "$agent_name")"
  ANDROID_TARGETS+=("${workspace_path}/repo")
done
CTO_WORKSPACE="$(workspace_for_agent "$CTO_NAME")"
CONTROL_TARGET="${CTO_WORKSPACE}/control"

# Validate every existing target before creating any missing clone.
for target_path in "${ANDROID_TARGETS[@]}"; do
  repo_state "$target_path" "$ANDROID_REMOTE" "Android" >/dev/null
done
repo_state "$CONTROL_TARGET" "$CONTROL_REMOTE" "control" >/dev/null

clone_if_missing() {
  local target_path="$1"
  local expected_remote="$2"
  local label="$3"
  local state
  state="$(repo_state "$target_path" "$expected_remote" "$label")"
  if [ "$state" = "missing" ]; then
    mkdir -p "$target_path"
    git clone --quiet --no-tags --branch "$INTEGRATION_BRANCH" --single-branch \
      "$expected_remote" "$target_path" >/dev/null 2>&1 || die "$label repository clone failed"
  fi
  [ "$(repo_state "$target_path" "$expected_remote" "$label")" = "ready" ] || \
    die "$label repository verification failed"
}

for target_path in "${ANDROID_TARGETS[@]}"; do
  clone_if_missing "$target_path" "$ANDROID_REMOTE" "Android"
done
clone_if_missing "$CONTROL_TARGET" "$CONTROL_REMOTE" "control"

printf 'Prepared %s Android workspaces and one CTO control workspace.\n' "${#ANDROID_TARGETS[@]}"
