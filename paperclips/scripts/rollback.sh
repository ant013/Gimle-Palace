#!/usr/bin/env bash
# UAA Phase C: replay inverse mutations from a journal entry per spec §8.5.
#
# Snapshots (recorded by bootstrap-project.sh + update-versions.sh) carry the
# OLD state of each mutation. rollback.sh replays them in reverse order (LIFO)
# to restore the system to its pre-bootstrap state.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# shellcheck source=lib/_common.sh
source "${SCRIPT_DIR}/lib/_common.sh"
# shellcheck source=lib/_paperclip_api.sh
source "${SCRIPT_DIR}/lib/_paperclip_api.sh"

JOURNAL_DIR="${HOME}/.paperclip/journal"

usage() {
  cat <<EOF
Usage:
  $(basename "$0") --list                              # list recent journal entries
  $(basename "$0") <journal-id-or-path>                # replay inverse mutations
  $(basename "$0") <journal-id> --dry-run              # show what would happen

A journal-id is the filename basename, e.g. "20260516T120000Z-bootstrap-trading"
(with or without the trailing ".json").
EOF
}

case "${1:-}" in
  -h|--help) usage; exit 0 ;;
  "") usage; exit 2 ;;
esac

if [ "$1" = "--list" ]; then
  if [ ! -d "$JOURNAL_DIR" ]; then
    log warn "no journal dir at $JOURNAL_DIR — nothing recorded yet"
    exit 0
  fi
  log info "recent journal entries (newest first):"
  found=0
  while IFS= read -r f; do
    [ -z "$f" ] && continue
    found=1
    op=$(jq -r '.op // "?"' "$f" 2>/dev/null || echo "?")
    ts=$(jq -r '.timestamp // "?"' "$f" 2>/dev/null || echo "?")
    outcome=$(jq -r '.outcome // "in-progress"' "$f" 2>/dev/null || echo "?")
    entries=$(jq '.entries | length' "$f" 2>/dev/null || echo 0)
    name=$(basename "$f" .json)
    printf "  %s  %-50s op=%-25s entries=%d  outcome=%s\n" "$ts" "$name" "$op" "$entries" "$outcome"
  done < <(ls -1t "$JOURNAL_DIR"/*.json 2>/dev/null | head -20)
  [ "$found" -eq 0 ] && log warn "no journal files found"
  exit 0
fi

DRY_RUN=0
journal_id=""
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) journal_id="$1"; shift ;;
  esac
done

[ -n "$journal_id" ] || { usage; die "journal-id required"; }
validate_journal_id "$journal_id"

# Resolve to absolute journal path
journal_path=""
if [ -f "$journal_id" ]; then
  journal_path="$journal_id"
elif [ -f "${JOURNAL_DIR}/${journal_id}.json" ]; then
  journal_path="${JOURNAL_DIR}/${journal_id}.json"
elif [ -f "${JOURNAL_DIR}/${journal_id}" ]; then
  journal_path="${JOURNAL_DIR}/${journal_id}"
else
  die "journal not found: $journal_id (looked in $JOURNAL_DIR)"
fi

require_command jq
log info "replaying journal: $journal_path"

quarantine_root="${HOME}/.paperclip/rollback-quarantine/$(basename "$journal_path" .json)"

validate_exact_rollback_path() {
  local path="$1"
  case "$path" in
    ""|/|"$HOME") die "refusing broad rollback path: ${path:-<empty>}" ;;
    /*) ;;
    *) die "rollback path must be absolute: $path" ;;
  esac
  case "$path" in
    *$'\n'*|*$'\r'*) die "rollback path contains a line break" ;;
  esac
}

quarantine_exact_path() {
  local path="$1"; local label="$2"
  validate_exact_rollback_path "$path"
  [ -e "$path" ] || return 0
  mkdir -p "$quarantine_root"
  chmod 700 "$quarantine_root"
  local destination="${quarantine_root}/${label}"
  [ ! -e "$destination" ] || die "quarantine target already exists: $destination"
  mv "$path" "$destination"
  log ok "quarantined $path -> $destination"
}

entries=$(jq '.entries | length' "$journal_path")
log info "found $entries snapshots to replay (reverse order)"

if [ "$entries" -eq 0 ]; then
  log warn "no snapshots in this journal — nothing to roll back"
  exit 0
fi

# Replay each entry in REVERSE order (LIFO)
for i in $(seq $((entries - 1)) -1 0); do
  entry=$(jq -c ".entries[$i]" "$journal_path")
  kind=$(printf '%s' "$entry" | jq -r '.kind')
  case "$kind" in
    agent_instructions_snapshot)
      agent_id=$(printf '%s' "$entry" | jq -r '.agent_id')
      old_content=$(printf '%s' "$entry" | jq -r '.old_content')
      log info "rolling back AGENTS.md for agent $agent_id"
      if [ "$DRY_RUN" -eq 1 ]; then
        bytes=$(printf '%s' "$old_content" | wc -c | tr -d ' ')
        log info "DRY RUN — would PUT old AGENTS.md (${bytes} bytes)"
      else
        paperclip_deploy_agents_md "$agent_id" "$old_content" >/dev/null
        log ok "restored agent $agent_id"
      fi
      ;;
    plugin_config_snapshot)
      plugin_id=$(printf '%s' "$entry" | jq -r '.plugin_id')
      old_config=$(printf '%s' "$entry" | jq -c '.old_config')
      log info "rolling back plugin config $plugin_id"
      if [ "$DRY_RUN" -eq 1 ]; then
        log info "DRY RUN — would POST old config"
      else
        paperclip_plugin_set_config "$plugin_id" "$old_config" >/dev/null
        log ok "restored plugin $plugin_id"
      fi
      ;;
    version_bump_snapshot)
      log warn "version-bump snapshot found — manual rollback required. Entry contents:"
      printf '%s' "$entry" | jq .
      ;;
    agent_hire)
      agent_id=$(printf '%s' "$entry" | jq -r '.id')
      agent_name=$(printf '%s' "$entry" | jq -r '.name')
      log info "rolling back hire of $agent_name ($agent_id)"
      if [ "$DRY_RUN" -eq 1 ]; then
        log info "DRY RUN — would delete agent $agent_name ($agent_id)"
      else
        paperclip_delete_agent "$agent_id" >/dev/null
        log ok "deleted agent $agent_name"
      fi
      ;;
    workspace_file_snapshot)
      path=$(printf '%s' "$entry" | jq -r '.path')
      old_content=$(printf '%s' "$entry" | jq -r '.old_content')
      validate_exact_rollback_path "$path"
      log info "rolling back managed workspace file $path"
      if [ "$DRY_RUN" -eq 1 ]; then
        log info "DRY RUN — would restore workspace file $path"
      else
        atomic_write "$path" "$old_content"
        log ok "restored workspace file $path"
      fi
      ;;
    managed_workspace_create)
      path=$(printf '%s' "$entry" | jq -r '.path')
      managed_file=$(printf '%s' "$entry" | jq -r '.managed_file // "AGENTS.md"')
      validate_exact_rollback_path "$path"
      case "$path" in
        */workspace) ;;
        *) die "refusing non-workspace managed path: $path" ;;
      esac
      log info "rolling back managed workspace $path"
      if [ "$DRY_RUN" -eq 1 ]; then
        log info "DRY RUN — would remove the exact managed workspace or quarantine unknown nonempty content"
      elif [ -d "$path" ]; then
        unknown_count=$(find "$path" -mindepth 1 -maxdepth 1 ! -name "$managed_file" -print | wc -l | tr -d ' ')
        if [ "$unknown_count" -gt 0 ]; then
          quarantine_exact_path "$path" "${i}-workspace-unknown"
        else
          [ ! -e "${path}/${managed_file}" ] || \
            quarantine_exact_path "${path}/${managed_file}" "${i}-${managed_file}"
          rmdir "$path" 2>/dev/null || \
            quarantine_exact_path "$path" "${i}-workspace-residual"
        fi
      fi
      ;;
    host_file_create)
      path=$(printf '%s' "$entry" | jq -r '.path')
      validate_exact_rollback_path "$path"
      case "$path" in
        "${HOME}/.paperclip/projects/"*) ;;
        *) die "refusing non-managed host file path: $path" ;;
      esac
      log info "rolling back created host file $path"
      if [ "$DRY_RUN" -eq 1 ]; then
        log info "DRY RUN — would quarantine exact created host file $path"
      else
        quarantine_exact_path "$path" "${i}-host-$(basename "$path")"
      fi
      ;;
    host_directory_create)
      path=$(printf '%s' "$entry" | jq -r '.path')
      validate_exact_rollback_path "$path"
      case "$path" in
        "${HOME}/.paperclip/projects/"*) ;;
        *) die "refusing non-managed host directory path: $path" ;;
      esac
      log info "rolling back created host directory $path"
      if [ "$DRY_RUN" -eq 1 ]; then
        log info "DRY RUN — would remove empty directory or quarantine exact residual directory"
      elif [ -d "$path" ]; then
        rmdir "$path" 2>/dev/null || quarantine_exact_path "$path" "${i}-host-directory"
      fi
      ;;
    watchdog_snapshot)
      project_key=$(printf '%s' "$entry" | jq -r '.project_key')
      config_path=$(printf '%s' "$entry" | jq -r '.config_path')
      plist_path=$(printf '%s' "$entry" | jq -r '.plist_path')
      config_existed=$(printf '%s' "$entry" | jq -r '.config_existed')
      plist_existed=$(printf '%s' "$entry" | jq -r '.plist_existed')
      config_content=$(printf '%s' "$entry" | jq -r '.config_content')
      plist_content=$(printf '%s' "$entry" | jq -r '.plist_content')
      [ "$config_path" = "${HOME}/.paperclip/watchdog-config.yaml" ] || \
        die "unexpected watchdog config path: $config_path"
      [ "$plist_path" = "${HOME}/Library/LaunchAgents/work.ant013.gimle-watchdog.plist" ] || \
        die "unexpected watchdog plist path: $plist_path"
      log info "rolling back watchdog state for $project_key"
      if [ "$DRY_RUN" -eq 1 ]; then
        log info "DRY RUN — would restore exact watchdog config/plist snapshot"
      else
        if [ "$config_existed" = "true" ]; then
          atomic_write "$config_path" "$config_content"
        else
          quarantine_exact_path "$config_path" "${i}-watchdog-config"
        fi
        if [ "$plist_existed" = "true" ]; then
          atomic_write "$plist_path" "$plist_content"
        else
          if [ -e "$plist_path" ] && command -v launchctl >/dev/null 2>&1; then
            launchctl bootout "gui/$(id -u)/work.ant013.gimle-watchdog" >/dev/null 2>&1 || true
          fi
          quarantine_exact_path "$plist_path" "${i}-watchdog-plist"
        fi
        log ok "restored watchdog snapshot"
      fi
      ;;
    company_create)
      company_id=$(printf '%s' "$entry" | jq -r '.id')
      company_name=$(printf '%s' "$entry" | jq -r '.name')
      creation_name=$(printf '%s' "$entry" | jq -r '.creation_name // ""')
      issue_prefix=$(printf '%s' "$entry" | jq -r '.issue_prefix // ""')
      log info "rolling back created company $company_name ($company_id)"
      if [ "$DRY_RUN" -eq 1 ]; then
        log info "DRY RUN — would delete exact company $company_id"
      else
        live_company=$(paperclip_get_company_if_exists "$company_id") || \
          die "created company $company_id is no longer readable"
        if [ -z "$live_company" ]; then
          log ok "created company $company_id is already absent"
          continue
        fi
        live_name=$(printf '%s' "$live_company" | jq -r '.name // ""')
        live_prefix=$(printf '%s' "$live_company" | jq -r '.issuePrefix // .issue_prefix // ""')
        if [ -n "$creation_name" ]; then
          [ "$live_name" = "$company_name" ] || [ "$live_name" = "$creation_name" ] || \
            die "created company identity mismatch: expected $creation_name or $company_name, got $live_name"
          if [ -n "$issue_prefix" ] && [ "$live_prefix" != "$issue_prefix" ]; then
            log warn "created company prefix mismatch ($live_prefix); deleting exact journaled id after verified create/final name"
          fi
        else
          [ "$live_name" = "$company_name" ] || \
            die "created company identity mismatch: expected $company_name, got $live_name"
          [ -z "$issue_prefix" ] || [ "$live_prefix" = "$issue_prefix" ] || \
            die "created company prefix mismatch: expected $issue_prefix, got $live_prefix"
        fi
        paperclip_delete_company "$company_id" >/dev/null
        log ok "deleted exact created company $company_id"
      fi
      ;;
    *)
      log warn "unknown snapshot kind: $kind — skipping"
      ;;
  esac
done

log ok "rollback complete"
