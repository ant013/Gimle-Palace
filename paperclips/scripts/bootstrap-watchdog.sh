#!/usr/bin/env bash
# UAA Phase C2: config-first watchdog install per spec §9.4.
#
# Why separate from install-paperclip.sh: `gimle_watchdog install` calls
# load_config(~/.paperclip/watchdog-config.yaml) which requires non-empty
# companies list. On a clean machine, watchdog cannot be installed before
# any project exists. This script is called from bootstrap-project.sh step 13.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
TPL_DIR="${REPO_ROOT}/paperclips/templates"

# shellcheck source=lib/_common.sh
source "${SCRIPT_DIR}/lib/_common.sh"

REMOVE=0
SKIP_LAUNCHD=0
project_key=""

while [ $# -gt 0 ]; do
  case "$1" in
    --remove) REMOVE=1; shift ;;
    --skip-launchd) SKIP_LAUNCHD=1; shift ;;
    -h|--help)
      cat <<EOF
Usage:
  $(basename "$0") <project-key>            # add project to watchdog config + install service
  $(basename "$0") <project-key> --remove   # remove project from watchdog config
  $(basename "$0") <project-key> --skip-launchd  # config only, don't install launchd service
EOF
      exit 0
      ;;
    *) project_key="$1"; shift ;;
  esac
done

[ -n "$project_key" ] || die "project-key required"

require_command python3
require_command yq

manifest="${REPO_ROOT}/paperclips/projects/${project_key}/paperclip-agent-assembly.yaml"
bindings="${HOME}/.paperclip/projects/${project_key}/bindings.yaml"

[ -f "$manifest" ] || die "manifest not found: $manifest"
[ -f "$bindings" ] || die "bindings.yaml not found: $bindings (run bootstrap-project.sh first)"

display_name=$(yq -r '.project.display_name' "$manifest")
company_id=$(yq -r '.company_id' "$bindings")

[ -n "$display_name" ] && [ "$display_name" != "null" ] || die "project.display_name missing"
[ -n "$company_id" ] && [ "$company_id" != "null" ] || die "company_id missing in bindings"

config="${HOME}/.paperclip/watchdog-config.yaml"
config_tpl="${TPL_DIR}/watchdog-config.yaml.template"
block_tpl="${TPL_DIR}/watchdog-company-block.yaml.template"

# Create config from template if missing
if [ ! -f "$config" ] && [ "$REMOVE" -eq 0 ]; then
  log info "config missing — initializing from template"
  mkdir -p "$(dirname "$config")"
  base_url="${PAPERCLIP_API_URL:-http://localhost:3100}"
  api_key_source="${PAPERCLIP_API_KEY_SOURCE:-env:PAPERCLIP_API_KEY}"
  sed -e "s|{{ host.paperclip.base_url }}|${base_url}|" \
      -e "s|{{ host.paperclip.api_key_source }}|${api_key_source}|" \
      "$config_tpl" > "$config"
  log ok "created $config"
fi

[ -f "$config" ] || die "config still missing — cannot proceed"

# Render company block
block=$(sed -e "s|{{ bindings.company_id }}|${company_id}|" \
            -e "s|{{ project.display_name }}|${display_name}|" \
            "$block_tpl")

if [ "$REMOVE" -eq 1 ]; then
  log info "removing company $company_id from watchdog config"
  yq -i "del(.companies[] | select(.id == \"${company_id}\"))" "$config"
  log ok "removed"
  exit 0
fi

# Idempotent append: add only if not present
existing=$(yq -r ".companies[] | select(.id == \"${company_id}\") | .id" "$config" 2>/dev/null || true)
if [ -n "$existing" ]; then
  log info "company $company_id already in config — no-op"
else
  log info "appending company block for $display_name ($company_id)"
  # Append via yq merge
  echo "$block" | yq -i '.companies += [load_str("/dev/stdin")[0]]' "$config" 2>/dev/null || {
    # Fallback: literal append (yq versions differ)
    echo "$block" >> "$config"
    log warn "yq merge fallback used; verify $config structure manually"
  }
  log ok "appended"
fi

# Install or kickstart launchd service
if [ "$SKIP_LAUNCHD" -eq 1 ]; then
  log info "--skip-launchd specified; not touching launchd"
  exit 0
fi

plist="${HOME}/Library/LaunchAgents/work.ant013.gimle-watchdog.plist"
if [ ! -f "$plist" ]; then
  log info "installing launchd service via gimle_watchdog install"
  cd "${REPO_ROOT}/services/watchdog"
  uv run python -m gimle_watchdog install --config "$config" || die "gimle_watchdog install failed"
else
  log info "launchd plist exists; kickstarting"
  uid=$(id -u)
  launchctl kickstart "gui/${uid}/work.ant013.gimle-watchdog" 2>/dev/null || \
    log warn "launchctl kickstart failed (may not be loaded yet)"
fi
log ok "watchdog ready for project $project_key"
