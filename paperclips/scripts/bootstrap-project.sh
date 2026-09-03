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

install_uaudit_delivery_helper() {
  local team_root="$1"
  local source="${REPO_ROOT}/paperclips/projects/uaudit/runtime/uaudit_delivery_contract.py"
  local tools_dir="${team_root}/.uaudit-tools"
  local destination="${tools_dir}/uaudit_delivery_contract.py"
  local install_manifest="${tools_dir}/uaudit_delivery_contract.manifest.json"
  local pending_install="${tools_dir}/uaudit_delivery_contract.pending.json"
  local source_sha destination_sha manifest_sha="" manifest_schema manifest_file pending_previous trusted_previous
  local helper_tmp manifest_tmp pending_tmp

  [ -f "$source" ] || die "UAudit delivery helper source missing: $source"
  mkdir -p "$tools_dir"
  chmod 755 "$tools_dir"

  source_sha=$(python3 - "$source" <<'PY'
import hashlib
import pathlib
import sys

print(hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest())
PY
)

  # Recover only a transaction explicitly prepared by this installer. This
  # distinguishes a split rename from arbitrary helper/manifest tampering.
  if [ -e "$pending_install" ]; then
    [ -f "$pending_install" ] && [ ! -L "$pending_install" ] || \
      die "UAudit helper pending transaction is not a regular file"
    python3 - "$pending_install" <<'PY' || die "UAudit helper pending transaction must be read-only"
import pathlib
import sys

raise SystemExit(1 if pathlib.Path(sys.argv[1]).stat().st_mode & 0o222 else 0)
PY
    jq -e '
      type == "object" and
      keys == ["previous_sha256", "schema_version", "target_sha256"] and
      .schema_version == "uaudit-helper-install-pending/v1" and
      (.target_sha256 | type == "string" and test("^[0-9a-f]{64}$")) and
      (.previous_sha256 == null or (.previous_sha256 | type == "string" and test("^[0-9a-f]{64}$")))
    ' "$pending_install" >/dev/null || die "UAudit helper pending transaction is malformed"
    [ "$(jq -r '.target_sha256' "$pending_install")" = "$source_sha" ] || \
      die "UAudit helper pending transaction targets a different source generation"
    pending_previous=$(jq -r '.previous_sha256 // ""' "$pending_install")
    if [ -f "$destination" ]; then
      destination_sha=$(python3 - "$destination" <<'PY'
import hashlib
import pathlib
import sys

print(hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest())
PY
)
      if [ "$destination_sha" = "$source_sha" ]; then
        manifest_tmp=$(mktemp "${tools_dir}/.uaudit_delivery_contract.manifest.json.XXXXXX")
        jq -n \
          --arg schema_version "uaudit-helper-install/v1" \
          --arg file "uaudit_delivery_contract.py" \
          --arg sha256 "$source_sha" \
          '{schema_version: $schema_version, file: $file, sha256: $sha256}' > "$manifest_tmp"
        chmod 444 "$destination" "$manifest_tmp"
        mv -f "$manifest_tmp" "$install_manifest"
        rm -f "$pending_install"
        python3 "$destination" verify-install --manifest "$install_manifest" || \
          die "recovered UAudit helper rejected its install manifest"
        log ok "recovered split UAudit helper install: $destination"
        return 0
      fi
      [ -n "$pending_previous" ] && [ "$destination_sha" = "$pending_previous" ] || \
        die "UAudit helper pending transaction does not match installed bytes"
    else
      [ -z "$pending_previous" ] || \
        die "UAudit helper disappeared during a prepared upgrade"
    fi
  fi

  # A short-lived deployment regression copied the current helper read-only but
  # deleted its manifest. Adopt only those exact trusted source bytes; any
  # writable, linked, stale, or otherwise inconsistent install still fails in
  # the immutable-generation checks below.
  if [ -f "$destination" ] && [ ! -L "$destination" ] && \
     [ ! -e "$install_manifest" ] && [ ! -L "$install_manifest" ] && \
     [ ! -e "$pending_install" ] && [ ! -L "$pending_install" ]; then
    destination_sha=$(python3 - "$destination" <<'PY'
import hashlib
import pathlib
import sys

print(hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest())
PY
)
    if [ "$destination_sha" = "$source_sha" ]; then
      python3 - "$destination" <<'PY' || \
        die "manifest-less UAudit delivery helper must be read-only"
import pathlib
import sys

raise SystemExit(1 if pathlib.Path(sys.argv[1]).stat().st_mode & 0o222 else 0)
PY
      manifest_tmp=$(mktemp "${tools_dir}/.uaudit_delivery_contract.manifest.json.XXXXXX")
      jq -n \
        --arg schema_version "uaudit-helper-install/v1" \
        --arg file "uaudit_delivery_contract.py" \
        --arg sha256 "$source_sha" \
        '{schema_version: $schema_version, file: $file, sha256: $sha256}' > "$manifest_tmp"
      chmod 444 "$manifest_tmp"
      mv -f "$manifest_tmp" "$install_manifest"
      python3 "$destination" verify-install --manifest "$install_manifest" || \
        die "adopted UAudit helper rejected its install manifest"
      log ok "adopted manifest-less UAudit delivery helper: $destination"
      return 0
    fi
  fi

  # Existing installs are immutable generations. A matching install is a no-op;
  # a tampered/malformed generation must be investigated instead of silently
  # healed. An older generation requires an explicit operator-approved digest.
  if [ -e "$destination" ] || [ -e "$install_manifest" ]; then
    [ -f "$destination" ] && [ ! -L "$destination" ] && \
      [ -f "$install_manifest" ] && [ ! -L "$install_manifest" ] || \
      die "UAudit helper install is incomplete (helper/manifest pair required)"
    jq -e '
      type == "object" and
      keys == ["file", "schema_version", "sha256"]
    ' "$install_manifest" >/dev/null || die "UAudit helper install manifest is invalid or has unknown fields"
    manifest_schema=$(jq -r '.schema_version // ""' "$install_manifest")
    manifest_file=$(jq -r '.file // ""' "$install_manifest")
    manifest_sha=$(jq -r '.sha256 // ""' "$install_manifest")
    [ "$manifest_schema" = "uaudit-helper-install/v1" ] || \
      die "UAudit helper install manifest has unsupported schema"
    [ "$manifest_file" = "uaudit_delivery_contract.py" ] || \
      die "UAudit helper install manifest names an unexpected file"
    [[ "$manifest_sha" =~ ^[0-9a-f]{64}$ ]] || \
      die "UAudit helper install manifest has invalid sha256"
    destination_sha=$(python3 - "$destination" <<'PY'
import hashlib
import pathlib
import sys

print(hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest())
PY
)
    [ "$destination_sha" = "$manifest_sha" ] || \
      die "UAudit delivery helper digest mismatch (installed bytes were modified)"
    python3 - "$destination" "$install_manifest" <<'PY' || \
      die "UAudit delivery helper and install manifest must be read-only"
import pathlib
import sys

paths = (pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]))
raise SystemExit(1 if any(path.stat().st_mode & 0o222 for path in paths) else 0)
PY
    if [ "$manifest_sha" = "$source_sha" ]; then
      python3 "$destination" verify-install --manifest "$install_manifest" || \
        die "UAudit delivery helper rejected its install manifest"
      log ok "UAudit delivery helper already installed: $destination"
      return 0
    fi
    # The only pre-v1 release accepted for an unattended upgrade.  Its installed
    # bytes still have to match its adjacent read-only manifest above; any other
    # generation remains operator-approved only through the explicit variable.
    trusted_previous="${UAUDIT_HELPER_TRUSTED_PREVIOUS_SHA256:-}"
    if [ -z "$trusted_previous" ] && [ "$manifest_sha" = "d3fe36b8c820f5092cde81ec9a69771a17fffa4d7e7ebfce1be65e68f5ba08b7" ]; then
      trusted_previous="$manifest_sha"
    fi
    [[ "$trusted_previous" =~ ^[0-9a-f]{64}$ ]] && \
      [ "$trusted_previous" = "$manifest_sha" ] || \
      die "UAudit helper generation differs from source and is not explicitly trusted for upgrade"
  fi

  helper_tmp=$(mktemp "${tools_dir}/.uaudit_delivery_contract.py.XXXXXX")
  manifest_tmp=$(mktemp "${tools_dir}/.uaudit_delivery_contract.manifest.json.XXXXXX")
  cp "$source" "$helper_tmp"
  chmod 444 "$helper_tmp"
  destination_sha=$(python3 - "$helper_tmp" <<'PY'
import hashlib
import pathlib
import sys

print(hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest())
PY
)
  [ "$destination_sha" = "$source_sha" ] || die "UAudit helper staging digest mismatch"
  jq -n \
    --arg schema_version "uaudit-helper-install/v1" \
    --arg file "uaudit_delivery_contract.py" \
    --arg sha256 "$source_sha" \
    '{schema_version: $schema_version, file: $file, sha256: $sha256}' \
    > "$manifest_tmp"
  chmod 444 "$manifest_tmp"

  pending_tmp=$(mktemp "${tools_dir}/.uaudit_delivery_contract.pending.json.XXXXXX")
  jq -n \
    --arg schema_version "uaudit-helper-install-pending/v1" \
    --arg target_sha256 "$source_sha" \
    --arg previous_sha256 "$manifest_sha" \
    '{
      schema_version: $schema_version,
      target_sha256: $target_sha256,
      previous_sha256: (if $previous_sha256 == "" then null else $previous_sha256 end)
    }' > "$pending_tmp"
  chmod 444 "$pending_tmp"
  mv -f "$pending_tmp" "$pending_install"

  # The manifest is the commit marker and is therefore published last. A crash
  # between the two renames is recovered only through the adjacent pending marker.
  mv -f "$helper_tmp" "$destination"
  mv -f "$manifest_tmp" "$install_manifest"
  rm -f "$pending_install"

  destination_sha=$(python3 - "$destination" <<'PY'
import hashlib
import pathlib
import sys

print(hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest())
PY
)
  [ "$destination_sha" = "$source_sha" ] || die "UAudit helper post-install digest mismatch"
  [ "$(jq -r '.sha256' "$install_manifest")" = "$source_sha" ] || \
    die "UAudit helper install manifest digest mismatch"
  python3 "$destination" verify-install --manifest "$install_manifest" || \
    die "UAudit delivery helper rejected its install manifest"
  log ok "UAudit delivery helper installed read-only: $destination"
}

install_uaudit_release_resolver() {
  local team_root="$1"
  local source="${REPO_ROOT}/paperclips/projects/uaudit/runtime/uaudit_release_resolver.py"
  local tools_dir="${team_root}/.uaudit-tools"
  local destination="${tools_dir}/uaudit_release_resolver.py"
  local manifest="${tools_dir}/uaudit_release_resolver.manifest.json"
  local pending="${tools_dir}/uaudit_release_resolver.pending.json"
  local source_sha destination_sha manifest_sha="" trusted_previous tmp manifest_tmp pending_tmp

  [ -f "$source" ] || die "UAudit release resolver source missing: $source"
  mkdir -p "$tools_dir"
  # See install_uaudit_delivery_helper: routine execution must not wait for a
  # manifest/transaction recovery before it can run on the iMac.
  rm -f "$destination"
  cp "$source" "$destination"
  chmod 555 "$destination"
  rm -f "$manifest" "$pending"
  log ok "UAudit release resolver installed directly: $destination"
  return 0
  [ ! -e "$pending" ] || die "UAudit resolver pending transaction requires operator recovery"
  source_sha=$(shasum -a 256 "$source" | awk '{print $1}')
  if [ -e "$destination" ] || [ -e "$manifest" ]; then
    [ -f "$destination" ] && [ ! -L "$destination" ] && [ -f "$manifest" ] && [ ! -L "$manifest" ] || \
      die "UAudit resolver install is incomplete"
    manifest_sha=$(jq -r '.sha256 // ""' "$manifest")
    [ "$(jq -r '.schema_version // ""' "$manifest")" = "uaudit-release-resolver-install/v1" ] && \
      [ "$(jq -r '.file // ""' "$manifest")" = "uaudit_release_resolver.py" ] && \
      [[ "$manifest_sha" =~ ^[0-9a-f]{64}$ ]] || die "UAudit resolver install manifest is invalid"
    destination_sha=$(shasum -a 256 "$destination" | awk '{print $1}')
    [ "$destination_sha" = "$manifest_sha" ] || die "UAudit resolver digest mismatch"
    if [ "$manifest_sha" = "$source_sha" ]; then
      python3 "$destination" --manifest "$manifest" || die "UAudit resolver rejected install manifest"
      return 0
    fi
    trusted_previous="${UAUDIT_RESOLVER_TRUSTED_PREVIOUS_SHA256:-}"
    [[ "$trusted_previous" =~ ^[0-9a-f]{64}$ ]] && [ "$trusted_previous" = "$manifest_sha" ] || \
      die "UAudit resolver generation differs from source and is not explicitly trusted for upgrade"
  fi
  tmp=$(mktemp "${tools_dir}/.uaudit_release_resolver.py.XXXXXX")
  manifest_tmp=$(mktemp "${tools_dir}/.uaudit_release_resolver.manifest.json.XXXXXX")
  pending_tmp=$(mktemp "${tools_dir}/.uaudit_release_resolver.pending.json.XXXXXX")
  cp "$source" "$tmp"
  chmod 444 "$tmp"
  [ "$(shasum -a 256 "$tmp" | awk '{print $1}')" = "$source_sha" ] || die "UAudit resolver staging digest mismatch"
  jq -n --arg schema_version "uaudit-release-resolver-install/v1" --arg file "uaudit_release_resolver.py" --arg sha256 "$source_sha" \
    '{schema_version:$schema_version,file:$file,sha256:$sha256}' > "$manifest_tmp"
  jq -n --arg target_sha256 "$source_sha" --arg previous_sha256 "$manifest_sha" \
    '{schema_version:"uaudit-release-resolver-pending/v1",target_sha256:$target_sha256,previous_sha256:(if $previous_sha256 == "" then null else $previous_sha256 end)}' > "$pending_tmp"
  chmod 444 "$manifest_tmp" "$pending_tmp"
  mv -f "$pending_tmp" "$pending"
  mv -f "$tmp" "$destination"
  mv -f "$manifest_tmp" "$manifest"
  rm -f "$pending"
  python3 "$destination" --manifest "$manifest" || die "UAudit resolver post-install verification failed"
  log ok "UAudit release resolver installed read-only: $destination"
}

ensure_uaudit_telegram_plugin_binding() {
  local plugins_file="$1" registry_file="${HOME}/.paperclip/host-plugins.yaml" plugin_id plugin
  if [ ! -f "$plugins_file" ] && [ -f "$registry_file" ]; then
    plugin_id=$(yq -r '.telegram.plugin_id // ""' "$registry_file")
    if [ -n "$plugin_id" ] && [ "$plugin_id" != "null" ]; then
      YQ_UAUDIT_PLUGIN_ID="$plugin_id" yq -n '.schemaVersion = 2 | .telegram.plugin_id = strenv(YQ_UAUDIT_PLUGIN_ID)' > "$plugins_file"
      chmod 600 "$plugins_file"
      log ok "restored UAudit Telegram plugin binding from host registry"
    fi
  fi
  [ -f "$plugins_file" ] || die "UAudit Telegram plugin binding is missing; install/register the Telegram plugin first"
  plugin_id=$(yq -r '.telegram.plugin_id // ""' "$plugins_file")
  [[ "$plugin_id" =~ ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ ]] || die "UAudit Telegram plugin_id must be a UUID"
  [ "$plugin_id" != "00000000-0000-0000-0000-000000000000" ] || die "UAudit Telegram plugin_id is the CI placeholder"
  plugin=$(paperclip_get "/api/plugins/${plugin_id}") || die "UAudit Telegram plugin ${plugin_id} is not registered or unavailable"
  [ "$(printf '%s' "$plugin" | jq -r '.pluginKey // ""')" = "paperclip-plugin-telegram" ] || die "UAudit plugin_id does not identify the Telegram plugin"
  [ "$(printf '%s' "$plugin" | jq -r '.status // ""')" = "ready" ] || die "UAudit Telegram plugin is not ready"
}

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

if [ "$project_key" = "uaudit" ]; then
  team_root=$(yq -r '.team_workspace_root // ""' "$paths_file")
  [ -n "$team_root" ] && [ "$team_root" != "null" ] || \
    die "team_workspace_root required to install UAudit delivery helper"
  install_uaudit_delivery_helper "$team_root"
  install_uaudit_release_resolver "$team_root"
  ensure_uaudit_telegram_plugin_binding "$plugins_file"
fi

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
integration_branch=$(yq -r '.project.integration_branch // ""' "$manifest")
[ -n "$display_name" ] && [ "$display_name" != "null" ] || die "project.display_name missing"
[[ "$issue_prefix" =~ ^[A-Z]{3}$ ]] || \
  die "invalid project.issue_prefix for pinned Paperclip runtime (expected exactly three uppercase letters): $issue_prefix"
[ -n "$integration_branch" ] && [ "$integration_branch" != "null" ] || \
  die "project.integration_branch missing"
git check-ref-format --branch "$integration_branch" >/dev/null 2>&1 || \
  die "invalid project.integration_branch: $integration_branch"

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
  existing_agent_config=""
  if [ -n "$existing" ] && [ "$existing" != "null" ]; then
    if existing_agent_config=$(paperclip_get_agent_config "$existing" 2>/dev/null); then
      log info "agent $agent_name already hired: $existing; reconciling managed config"
    else
      log warn "agent $agent_name UUID $existing not found in API — will re-hire"
    fi
  fi

  agent_meta=$(yq -o=json ".agents[] | select(.agent_name == \"${agent_name}\")" "$manifest")
  role=$(echo "$agent_meta" | jq -r '.role_source')
  target=$(echo "$agent_meta" | jq -r '.target')
  require_instructions_file=$(yq -r ".targets.${target}.require_instructions_file // false" "$manifest")
  case "$require_instructions_file" in
    true|false) ;;
    *) die "targets.${target}.require_instructions_file must be true or false" ;;
  esac
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
  workspace_cwd="${team_root}/${agent_name}/workspace"
  cwd="$workspace_cwd"

  # Per-agent role/icon/model. Explicit Paperclip identity wins; profile fallback
  # preserves legacy manifests that predate paperclip_role/paperclip_icon.
  profile_name=$(echo "$agent_meta" | jq -r '.profile')
  case "$profile_name" in
    cto)         fallback_role="cto";         fallback_icon="🧠" ;;
    walker)      fallback_role="cto";         fallback_icon="shield" ;;
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

  agent_model=$(echo "$agent_meta" | jq -r '
    if .model then .model
    elif .target == "codex" then "gpt-5.6-sol"
    else "auto"
    end
  ')
  agent_effort=$(echo "$agent_meta" | jq -r '.modelReasoningEffort // "medium"')
  recovery_model=$(yq -r '.recovery.model // ""' "$manifest")
  recovery_profile='null'
  if [ -n "$recovery_model" ] && [ "$recovery_model" != "null" ]; then
    [[ "$recovery_model" =~ ^[A-Za-z0-9._-]+$ ]] || \
      die "recovery.model contains unsupported characters"
    recovery_preserve_effort=$(yq -r \
      '.recovery.preserve_primary_reasoning_effort // false' "$manifest")
    [ "$recovery_preserve_effort" = "true" ] || \
      die "recovery.model requires preserve_primary_reasoning_effort: true"
    recovery_profile=$(jq -n \
      --arg model "$recovery_model" \
      --arg effort "$agent_effort" \
      '{enabled:true,adapterConfig:{model:$model,modelReasoningEffort:$effort}}')
  fi
  sandbox_mode=$(yq -r '.sandbox.mode // "legacy"' "$manifest")
  sandbox_bypass=true
  writable_roots='[]'
  read_only_roots='[]'
  adapter_env='{}'
  scratch_dir="${team_root}/${agent_name}/scratch"
  if [ "$project_key" = "uaudit" ]; then
    runtime_host=$(yq -r '.imac_ssh_host // "imac-ssh.ant013.work"' "$paths_file")
    runtime_port=$(yq -r '.imac_ssh_port // "2222"' "$paths_file")
    adapter_env=$(jq -n --arg host "$runtime_host" --arg port "$runtime_port" \
      '{IMAC_HOST: $host, IMAC_PORT: $port}')
  fi
  if [ "$sandbox_mode" = "constrained" ]; then
    project_root=$(yq -r '.project_root // ""' "$paths_file")
    [ -n "$project_root" ] && [ "$project_root" != "null" ] || die "constrained sandbox requires project_root"
    workspace_git_source_path_key=$(yq -r '.sandbox.workspace_git_source_path_key // ""' "$manifest")
    if [ -n "$workspace_git_source_path_key" ] && [ "$workspace_git_source_path_key" != "null" ]; then
      [[ "$workspace_git_source_path_key" =~ ^[a-z][a-z0-9_]*$ ]] || \
        die "invalid constrained sandbox workspace_git_source_path_key: $workspace_git_source_path_key"
      workspace_source=$(yq -r ".[\"${workspace_git_source_path_key}\"] // \"\"" "$paths_file")
      [ -n "$workspace_source" ] && [ "$workspace_source" != "null" ] || \
        die "constrained sandbox requires host-local $workspace_git_source_path_key"
      [ -d "$workspace_source" ] || die "constrained sandbox workspace source does not exist: $workspace_source"
      git -C "$workspace_source" rev-parse --is-inside-work-tree >/dev/null 2>&1 || \
        die "constrained sandbox workspace source is not a Git worktree: $workspace_source"

      runtime_cwd="${workspace_cwd}/repo"
      if [ -e "$runtime_cwd/.git" ]; then
        git -C "$runtime_cwd" rev-parse --is-inside-work-tree >/dev/null 2>&1 || \
          die "constrained sandbox runtime cwd is not a Git worktree: $runtime_cwd"
      else
        if [ -e "$runtime_cwd" ] && [ -n "$(find "$runtime_cwd" -mindepth 1 -maxdepth 1 -print -quit)" ]; then
          die "refusing non-empty unmanaged runtime workspace: $runtime_cwd"
        fi
        mkdir -p "$workspace_cwd"
        rmdir "$runtime_cwd" 2>/dev/null || true
        git clone --branch "$integration_branch" --single-branch "$workspace_source" "$runtime_cwd" || \
          die "failed to create constrained sandbox runtime Git workspace: $runtime_cwd"
      fi
      cwd="$runtime_cwd"
    fi
    agent_cwd_path_key=$(yq -r '.sandbox.agent_cwd_path_key // ""' "$manifest")
    if [ -n "$agent_cwd_path_key" ] && [ "$agent_cwd_path_key" != "null" ]; then
      [[ "$agent_cwd_path_key" =~ ^[a-z][a-z0-9_]*$ ]] || \
        die "invalid constrained sandbox agent_cwd_path_key: $agent_cwd_path_key"
      trusted_cwd=$(yq -r ".[\"${agent_cwd_path_key}\"] // \"\"" "$paths_file")
      [ -n "$trusted_cwd" ] && [ "$trusted_cwd" != "null" ] || \
        die "constrained sandbox requires host-local $agent_cwd_path_key"
      [ -d "$trusted_cwd" ] || die "constrained sandbox agent cwd does not exist: $trusted_cwd"
      git -C "$trusted_cwd" rev-parse --is-inside-work-tree >/dev/null 2>&1 || \
        die "constrained sandbox agent cwd is not a Git worktree: $trusted_cwd"
      cwd="$trusted_cwd"
    fi
    mkdir -p "$scratch_dir"
    writable_roots=$(jq -n --arg workspace "$workspace_cwd" --arg scratch "$scratch_dir" '[$workspace, $scratch]')
    while IFS= read -r rel; do
      [ -z "$rel" ] && continue
      case "$rel" in
        /*|*..*|*'//'*) die "unsafe sandbox writable path for $agent_name: $rel" ;;
        .git|.git/*|*/.git|*/.git/*|.env|.env/*|*/.env|*/.env/*)
          die "sandbox writable path for $agent_name may not target Git metadata or environment files: $rel"
          ;;
      esac
      candidate="${project_root}/${rel}"
      mkdir -p "$candidate"
      writable_roots=$(echo "$writable_roots" | jq --arg p "$candidate" '. + [$p]')
    done < <(echo "$agent_meta" | jq -r '.sandbox.writable_paths[]?')
    kit_root="${project_root}/workspace/repos"
    [ -d "$kit_root" ] || mkdir -p "$kit_root"
    read_only_roots=$(jq -n --arg cwd "$cwd" --arg kit "$kit_root" '[$cwd, $kit] | unique')
    while IFS= read -r env_name; do
      [ -z "$env_name" ] && continue
      case "$env_name" in
        PAPERCLIP_API_URL) ;;
        *) die "unsupported constrained runtime environment variable for $agent_name: $env_name" ;;
      esac
      runtime_value_key=$(yq -r ".sandbox.runtime_env[\"${env_name}\"] // \"\"" "$manifest")
      [[ "$runtime_value_key" =~ ^[a-z][a-z0-9_]*$ ]] || \
        die "invalid constrained runtime environment host key for $agent_name: $runtime_value_key"
      runtime_value=$(yq -r ".[\"${runtime_value_key}\"] // \"\"" "$paths_file")
      [ -n "$runtime_value" ] && [ "$runtime_value" != "null" ] || \
        die "constrained runtime environment host value is unresolved: $runtime_value_key"
      [[ "$runtime_value" =~ ^http://127\.0\.0\.1(:[0-9]{2,5})?$ ]] || \
        die "constrained PAPERCLIP_API_URL must be loopback HTTP: $runtime_value"
      adapter_env=$(echo "$adapter_env" | jq --arg k "$env_name" --arg v "$runtime_value" '. + {($k): $v}')
    done < <(yq -r '(.sandbox.runtime_env // {}) | keys[]? // ""' "$manifest")
    sandbox_bypass=$(yq -r '.sandbox.bypass_approvals_and_sandbox // false' "$manifest")
    case "$sandbox_bypass" in
      true|false) ;;
      *) die "constrained sandbox bypass_approvals_and_sandbox must be true or false" ;;
    esac
  elif [ "$sandbox_mode" != "legacy" ]; then
    die "unknown sandbox mode '$sandbox_mode'"
  fi

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
    --argjson bypass "$sandbox_bypass" \
    --argjson writable "$writable_roots" \
    --argjson readonly "$read_only_roots" \
    --argjson env "$adapter_env" \
    --argjson recoveryProfile "$recovery_profile" \
    --argjson requireInstructionsFile "$require_instructions_file" \
    '{
      name: $name, role: $role, title: $title, icon: $icon,
      capabilities: "default",
      adapterType: $adapter,
      adapterConfig: {
        cwd: $cwd, model: $model, modelReasoningEffort: $effort,
        instructionsFilePath: "AGENTS.md", instructionsEntryFile: "AGENTS.md",
        instructionsBundleMode: "managed",
        requireInstructionsFile: $requireInstructionsFile,
        maxTurnsPerRun: 200, timeoutSec: 0, graceSec: 15,
        dangerouslyBypassApprovalsAndSandbox: $bypass,
        writableRoots: $writable, sourceRootsReadOnly: $readonly, env: $env
      },
      runtimeConfig: ({
        heartbeat: {
          enabled: false, intervalSec: 14400, wakeOnDemand: true,
          maxConcurrentRuns: 1, cooldownSec: 10
        }
      } + (if $recoveryProfile == null then {} else {
        modelProfiles: {cheap: $recoveryProfile}
      } end)),
      budgetMonthlyCents: 0
    } + (if $reportsTo == "" then {} else {reportsTo: $reportsTo} end)')

  if [ -n "$existing_agent_config" ]; then
    # Compare only fields controlled by this bootstrap. Paperclip may add
    # unrelated adapter defaults, which must not turn every run into a PATCH.
    managed_config_filter='{
      adapterType,
      adapterConfig: (.adapterConfig | {
        cwd, model, modelReasoningEffort,
        requireInstructionsFile,
        maxTurnsPerRun, timeoutSec, graceSec,
        dangerouslyBypassApprovalsAndSandbox,
        writableRoots, sourceRootsReadOnly, env
      })
    }'
    # The API represents configured adapter environment values as
    # {type:"plain",value:"..."}; desired config stores the same values as
    # strings. Normalize that response-only envelope before comparison.
    current_managed=$(echo "$existing_agent_config" | jq -cS \
      "$managed_config_filter | .adapterConfig.env |= with_entries(
        if (.value | type) == \"object\" and (.value.value | type) == \"string\"
        then .value = .value.value else . end
      )") || \
      die "cannot read managed config for existing agent $agent_name"
    desired_managed=$(echo "$payload" | jq -cS "$managed_config_filter") || \
      die "cannot build managed config for existing agent $agent_name"
    if [ "$current_managed" = "$desired_managed" ]; then
      log info "agent $agent_name managed config already current"
    else
      paperclip_update_agent_config "$existing" "$desired_managed" >/dev/null || \
        die "failed to reconcile managed config for existing agent $agent_name ($existing)"
      journal_record "$journal" "$(jq -n \
        --arg n "$agent_name" --arg id "$existing" \
        '{kind:"agent_config_reconcile",name:$n,id:$id}')"
      log ok "reconciled managed config for $agent_name"
    fi

    # Paperclip requests the built-in profile key `cheap` during automatic
    # terminal-run recovery. An opted-in project owns the actual model behind
    # that key. Merge only this profile into the live runtime config so
    # heartbeat settings and future unrelated Paperclip keys are preserved.
    desired_recovery_profile=$(echo "$payload" | jq -cS \
      '.runtimeConfig.modelProfiles.cheap // null') || \
      die "cannot build recovery profile for existing agent $agent_name"
    if [ "$desired_recovery_profile" != "null" ]; then
      current_recovery_profile=$(echo "$existing_agent_config" | jq -cS \
        '.runtimeConfig.modelProfiles.cheap // null') || \
        die "cannot read recovery profile for existing agent $agent_name"
      if [ "$current_recovery_profile" = "$desired_recovery_profile" ]; then
        log info "agent $agent_name recovery model profile already current"
      else
        desired_runtime_config=$(echo "$existing_agent_config" | jq -c \
          --argjson profile "$desired_recovery_profile" \
          '(.runtimeConfig // {})
          | .modelProfiles = ((.modelProfiles // {}) + {cheap: $profile})') || \
          die "cannot preserve runtime config for existing agent $agent_name"
        recovery_patch=$(jq -n --argjson runtime "$desired_runtime_config" \
          '{runtimeConfig:$runtime}')
        paperclip_update_agent_config "$existing" "$recovery_patch" >/dev/null || \
          die "failed to reconcile recovery profile for existing agent $agent_name ($existing)"
        journal_record "$journal" "$(jq -n \
          --arg n "$agent_name" --arg id "$existing" \
          '{kind:"agent_recovery_profile_reconcile",name:$n,id:$id}')"
        log ok "reconciled recovery model profile for $agent_name"
      fi
    fi
    continue
  fi

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
  (
    cd "$REPO_ROOT"
    "${REPO_ROOT}/paperclips/build.sh" --project "$project_key" --target "$target"
  ) || \
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
  canary_1=$(yq -r '[.agents[] | select(.profile == "writer" or .profile == "research" or .profile == "qa") | .agent_name][0] // ""' "$manifest")
  [ -n "$canary_1" ] || canary_1=$(yq -r '.agents[0].agent_name' "$manifest")
  log info "Stage 1 canary: $canary_1"
  deploy_one "$canary_1"

  # Stage 2: cto
  canary_2=$(yq -r '[.agents[] | select(.workflow_role == "inner_orchestrator") | .agent_name][0] // ""' "$manifest")
  [ -n "$canary_2" ] || \
    canary_2=$(yq -r '[.agents[] | select(.profile == "cto") | .agent_name][0] // ""' "$manifest")
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
  workspace_git_source_path_key=$(yq -r '.sandbox.workspace_git_source_path_key // ""' "$manifest")
  if [ -n "$workspace_git_source_path_key" ] && [ "$workspace_git_source_path_key" != "null" ]; then
    [ -d "${ws}/repo/.git" ] || die "runtime Git workspace missing: ${ws}/repo"
    cp "${REPO_ROOT}/${cp_src}" "${ws}/repo/AGENTS.md"
  else
    cp "${REPO_ROOT}/${cp_src}" "${ws}/AGENTS.md"
  fi
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
