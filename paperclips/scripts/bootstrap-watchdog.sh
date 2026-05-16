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
validate_project_key "$project_key"

require_command python3
# CRIT-6 fix: bootstrap-watchdog uses python3 for all YAML (no yq dependency).
# yq's load_str syntax differs across v3/v4 and the literal-append fallback
# produces invalid YAML. python3+PyYAML is already required upstream.

manifest="${REPO_ROOT}/paperclips/projects/${project_key}/paperclip-agent-assembly.yaml"
bindings="${HOME}/.paperclip/projects/${project_key}/bindings.yaml"

[ -f "$manifest" ] || die "manifest not found: $manifest"
[ -f "$bindings" ] || die "bindings.yaml not found: $bindings (run bootstrap-project.sh first)"

display_name=$(python3 -c "import yaml,sys; print(yaml.safe_load(open(sys.argv[1])).get('project',{}).get('display_name',''))" "$manifest")
company_id=$(python3 -c "import yaml,sys; print(yaml.safe_load(open(sys.argv[1])).get('company_id',''))" "$bindings")

[ -n "$display_name" ] && [ "$display_name" != "None" ] || die "project.display_name missing"
[ -n "$company_id" ] && [ "$company_id" != "None" ] || die "company_id missing in bindings"

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
  python3 - "$config" "$company_id" <<'PY'
import sys, yaml
config_path, cid = sys.argv[1], sys.argv[2]
with open(config_path) as f:
    cfg = yaml.safe_load(f) or {}
cfg.setdefault("companies", [])
cfg["companies"] = [c for c in cfg["companies"] if c.get("id") != cid]
with open(config_path, "w") as f:
    yaml.safe_dump(cfg, f, sort_keys=False)
PY
  log ok "removed"
  exit 0
fi

# Idempotent append: deterministic python3 merge (CRIT-6 fix).
log info "appending company block for $display_name ($company_id)"
python3 - "$config" "$block" "$company_id" <<'PY'
import sys, yaml
config_path, block_yaml, cid = sys.argv[1], sys.argv[2], sys.argv[3]
with open(config_path) as f:
    cfg = yaml.safe_load(f) or {}
cfg.setdefault("companies", [])
if any(c.get("id") == cid for c in cfg["companies"]):
    print(f"company {cid} already in config — no-op", file=sys.stderr)
    sys.exit(0)
new = yaml.safe_load(block_yaml)
if isinstance(new, list):
    cfg["companies"].extend(new)
else:
    cfg["companies"].append(new)
with open(config_path, "w") as f:
    yaml.safe_dump(cfg, f, sort_keys=False)
PY
log ok "appended (or already present)"

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
