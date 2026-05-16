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
project_key=""

usage() {
  cat <<EOF
Usage: $(basename "$0") <project-key> [--dry-run]

Extract agent UUIDs from legacy sources into ~/.paperclip/projects/<key>/bindings.yaml.
With --dry-run, prints the bindings.yaml contents to stdout without writing.
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) project_key="$1"; shift ;;
  esac
done

[ -n "$project_key" ] || { usage; die "project-key required"; }
validate_project_key "$project_key"

manifest="${REPO_ROOT}/paperclips/projects/${project_key}/paperclip-agent-assembly.yaml"
[ -f "$manifest" ] || die "manifest not found: $manifest"

target_dir="${HOME}/.paperclip/projects/${project_key}"
target_file="${target_dir}/bindings.yaml"

log info "extracting bindings for project: $project_key"

declare -A AGENT_UUIDS
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
    # CRIT-4 fix: preserve well-known acronyms (CTO, QA, MCP, ...) per uaudit
    # manifest convention (UWICTO, UWIQAEngineer). Plain camelCase would emit
    # 'CXCto'/'CXQaEngineer'/'CXMcpEngineer' which don't match paperclip-API names.
    ACRONYMS="CTO QA MCP CEO CFO CIO COO CSO CRO API CLI CI CD AI ML DB IT IO UI UX UWI UWA UW"
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

# Source 2: inline manifest agent_id fields (trading/uaudit)
if command -v yq >/dev/null 2>&1; then
  while IFS='|' read -r name uuid; do
    [ -z "$name" ] && continue
    [ -z "$uuid" ] && continue
    [ "$uuid" = "null" ] && continue
    # Don't overwrite an entry already populated from source 1.
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
