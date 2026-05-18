#!/usr/bin/env bash
# UAA Phase C: extract agent UUIDs from legacy sources into
# ~/.paperclip/projects/<key>/bindings.yaml per spec §6.3.
#
# Sources (in order, first wins):
#   1. paperclips/codex-agent-ids.env  (gimle codex team only)
#   2. paperclips/projects/<key>/paperclip-agent-assembly.yaml (inline agent_id fields)
#   3. GET /api/companies/<id>/agents   (gimle claude team — needs PAPERCLIP_API_KEY)

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# shellcheck source=lib/_common.sh
source "${SCRIPT_DIR}/lib/_common.sh"
# shellcheck source=lib/_paperclip_api.sh
source "${SCRIPT_DIR}/lib/_paperclip_api.sh"

DRY_RUN=0
CHECK_CONFLICTS=0
project_key=""

usage() {
  cat <<EOF
Usage:
  $(basename "$0") <project-key>                     # extract → ~/.paperclip/projects/<key>/bindings.yaml
  $(basename "$0") <project-key> --dry-run           # print bindings.yaml contents without writing
  $(basename "$0") <project-key> --check-conflicts   # compare legacy env vs current bindings
                                                       # exit 0 on agreement (incl. pre-bootstrap with no sources)
                                                       # exit 1 on disagreement (lists CONFLICT lines to stderr)
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    --check-conflicts) CHECK_CONFLICTS=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) project_key="$1"; shift ;;
  esac
done

[ -n "$project_key" ] || { usage; die "project-key required"; }
validate_project_key "$project_key"

manifest="${REPO_ROOT}/paperclips/projects/${project_key}/paperclip-agent-assembly.yaml"
[ -f "$manifest" ] || die "manifest not found: $manifest"

# Phase D Task 4: --check-conflicts mode runs the dual-read resolver against
# the existing bindings + legacy env and exits 1 if any agent UUID differs.
# Runs BEFORE the extraction logic — no writes, just diagnostics.
if [ "$CHECK_CONFLICTS" -eq 1 ]; then
  legacy_for_check="${REPO_ROOT}/paperclips/codex-agent-ids.env"
  bindings_for_check="${HOME}/.paperclip/projects/${project_key}/bindings.yaml"
  require_command python3
  PYTHONPATH="${REPO_ROOT}" python3 - "$legacy_for_check" "$bindings_for_check" "$project_key" <<'PY'
import sys
from pathlib import Path
from paperclips.scripts.resolve_bindings import resolve_all

legacy_arg, bindings_arg, project_key = sys.argv[1], sys.argv[2], sys.argv[3]
legacy = Path(legacy_arg) if project_key == "gimle" else None
if legacy is not None and not legacy.is_file():
    legacy = None
bindings = Path(bindings_arg) if Path(bindings_arg).is_file() else None

try:
    out = resolve_all(legacy_env_path=legacy, bindings_yaml_path=bindings)
except FileNotFoundError:
    # Pre-bootstrap project (no legacy env, no bindings yet) — not an error.
    # CI cron + operator dry-runs see this as 'nothing to check', exit 0.
    print(f"skipped: no sources for project '{project_key}' (pre-bootstrap)",
          file=sys.stderr)
    sys.exit(0)

if out["conflicts"]:
    for c in out["conflicts"]:
        print(f"CONFLICT: {c['agent']} legacy={c['legacy']} bindings={c['bindings']}",
              file=sys.stderr)
    sys.exit(1)
print(f"no conflicts ({len(out['agents'])} agents merged from sources={out['sources_used']})")
PY
  exit $?
fi

target_dir="${HOME}/.paperclip/projects/${project_key}"
target_file="${target_dir}/bindings.yaml"

log info "extracting bindings for project: $project_key"

declare -A AGENT_UUIDS
# Explicit zero-init: under `set -u`, ${#AGENT_UUIDS[@]} on a declared-but-never-
# assigned assoc-array raises 'unbound variable' in bash 4+. The empty assignment
# anchors it as a defined-empty array.
AGENT_UUIDS=()
COMPANY_ID=""

# Source 1: codex-agent-ids.env (gimle only)
legacy_env="${REPO_ROOT}/paperclips/codex-agent-ids.env"
if [ "$project_key" = "gimle" ] && [ -f "$legacy_env" ]; then
  log info "reading legacy: paperclips/codex-agent-ids.env"
  while IFS='=' read -r key value; do
    [[ "$key" =~ ^# ]] && continue
    [ -z "$key" ] && continue
    [ -z "$value" ] && continue
    # CX_PYTHON_ENGINEER_AGENT_ID -> CXPythonEngineer
    # CODEX_ARCHITECT_REVIEWER_AGENT_ID -> CodexArchitectReviewer
    stripped=$(printf '%s' "$key" | sed -E 's/_AGENT_ID$//')
    case "$stripped" in
      CX_*)
        rest=${stripped#CX_}
        prefix="CX"
        ;;
      CODEX_*)
        rest=${stripped#CODEX_}
        prefix="Codex"
        ;;
      *)
        rest="$stripped"
        prefix=""
        ;;
    esac
    # CRIT-4 + D-fix C-4: preserve canonical acronyms per uaudit manifest convention.
    # Single source of truth shared with Python resolver:
    #   paperclips/scripts/lib/canonical_acronyms.txt
    ACRONYM_FILE="${SCRIPT_DIR}/lib/canonical_acronyms.txt"
    if [ -f "$ACRONYM_FILE" ]; then
      ACRONYMS=$(grep -vE '^\s*(#|$)' "$ACRONYM_FILE" | tr '\n' ' ')
    else
      ACRONYMS="CTO QA MCP CEO CFO CIO COO CSO CRO API CLI CI CD AI ML DB IT IO UI UX UWI UWA UW"
    fi
    camel=$(printf '%s' "$rest" | awk -F_ -v acr="$ACRONYMS" '
      BEGIN { split(acr, a, " "); for (i in a) is_acr[a[i]] = 1 }
      { out = ""
        for (i=1; i<=NF; i++) {
          tok = toupper($i)
          if (is_acr[tok]) { out = out tok }
          else { out = out toupper(substr($i,1,1)) tolower(substr($i,2)) }
        }
        print out
      }')
    name="${prefix}${camel}"
    AGENT_UUIDS["$name"]="$value"
  done < "$legacy_env"
fi

# Source 2: inline manifest agent_id fields (trading/uaudit).
# Prefer python3+yaml (always available per Phase D); yq is optional fallback.
if command -v python3 >/dev/null 2>&1; then
  manifest_lines=$(python3 - "$manifest" <<'PY' 2>/dev/null || true
import sys, yaml
m = yaml.safe_load(open(sys.argv[1])) or {}
cid = (m.get("project") or {}).get("company_id") or ""
print(f"__COMPANY_ID__|{cid}")
for a in m.get("agents", []) or []:
    name = a.get("agent_name") or ""
    uuid = a.get("agent_id") or ""
    if name and uuid:
        print(f"{name}|{uuid}")
PY
)
  while IFS='|' read -r name uuid; do
    [ -z "$name" ] && continue
    if [ "$name" = "__COMPANY_ID__" ]; then
      [ -n "$uuid" ] && [ "$uuid" != "null" ] && COMPANY_ID="$uuid"
      continue
    fi
    [ -z "$uuid" ] && continue
    [ "$uuid" = "null" ] && continue
    if [ -z "${AGENT_UUIDS[$name]:-}" ]; then
      AGENT_UUIDS["$name"]="$uuid"
    fi
  done <<< "$manifest_lines"
elif command -v yq >/dev/null 2>&1; then
  while IFS='|' read -r name uuid; do
    [ -z "$name" ] && continue
    [ -z "$uuid" ] && continue
    [ "$uuid" = "null" ] && continue
    if [ -z "${AGENT_UUIDS[$name]:-}" ]; then
      AGENT_UUIDS["$name"]="$uuid"
    fi
  done < <(yq -r '.agents[]? | select(.agent_id != null) | "\(.agent_name)|\(.agent_id)"' "$manifest" 2>/dev/null || true)
  cid=$(yq -r '.project.company_id // ""' "$manifest" 2>/dev/null || true)
  [ -n "$cid" ] && [ "$cid" != "null" ] && COMPANY_ID="$cid"
fi

# Source 3: paperclip API (gimle claude team) — only with API key + company id
if [ "$project_key" = "gimle" ] && [ -n "${PAPERCLIP_API_KEY:-}" ] && [ -n "$COMPANY_ID" ]; then
  log info "querying paperclip API for live agent UUIDs"
  agents_json=$(paperclip_get "/api/companies/${COMPANY_ID}/agents" 2>/dev/null || echo "[]")
  while IFS='|' read -r name uuid; do
    [ -z "$name" ] && continue
    [ -z "$uuid" ] && continue
    if [ -z "${AGENT_UUIDS[$name]:-}" ]; then
      AGENT_UUIDS["$name"]="$uuid"
    fi
  done < <(printf '%s' "$agents_json" | jq -r '.[] | "\(.name)|\(.id)"' 2>/dev/null || true)
fi

[ "${#AGENT_UUIDS[@]}" -gt 0 ] || die "no UUIDs extracted from any source for project: $project_key"

log ok "extracted ${#AGENT_UUIDS[@]} agent UUIDs"

# Build bindings.yaml content (sorted keys for idempotency)
yaml_content="schemaVersion: 2
company_id: \"${COMPANY_ID:-UNKNOWN}\"
agents:
"
for name in $(printf '%s\n' "${!AGENT_UUIDS[@]}" | LC_ALL=C sort); do
  yaml_content="${yaml_content}  ${name}: \"${AGENT_UUIDS[$name]}\"
"
done

if [ "$DRY_RUN" -eq 1 ]; then
  log info "DRY RUN — would write to: $target_file"
  printf '%s' "$yaml_content"
  exit 0
fi

mkdir -p "$target_dir"
chmod 700 "$target_dir"
printf '%s' "$yaml_content" > "$target_file"
chmod 600 "$target_file"
log ok "wrote $target_file"
