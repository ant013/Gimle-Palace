#!/usr/bin/env bash
# audit-workflow-launcher.sh — launch an Audit-V1 async workflow via Paperclip API.
#
# Creates 1 parent issue + 3 child domain issues. Domain agents post sub-reports
# to their child issues; when all 3 close, the Auditor assembles the final report.
#
# Usage:
#   bash audit-workflow-launcher.sh --project=<slug> --auditor-id=<uuid> [options]
#   bash audit-workflow-launcher.sh --bundle=<name>  --auditor-id=<uuid> [options]
#   bash audit-workflow-launcher.sh --project=<slug> --auditor-id=<uuid> --dry-run
#
# Options:
#   --project=<slug>       Project slug (mutually exclusive with --bundle)
#   --bundle=<name>        Bundle name (mutually exclusive with --project)
#   --auditor-id=<uuid>    Paperclip UUID of the Auditor agent (required)
#   --dry-run              Print all 4 JSON payloads to stdout; do NOT call the API
#   --api-url=<url>        Paperclip API base URL (default: $PAPERCLIP_API_URL or http://localhost:3100)
#   --company-id=<id>      Paperclip company ID (default: $PAPERCLIP_COMPANY_ID or 9d8f432c-ff7d-4e3a-bbe3-3cd355f73b64)
#
# Environment variables (override defaults):
#   PAPERCLIP_API_URL      API base URL
#   PAPERCLIP_API_KEY      Bearer token (optional; omit for local dev)
#   PAPERCLIP_COMPANY_ID   Company UUID
#
# Exit codes:
#   0  Success (or dry-run)
#   1  API error
#   2  Usage / invalid argument

set -euo pipefail

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

PROJECT=""
BUNDLE=""
AUDITOR_ID=""
DRY_RUN=false
API_URL="${PAPERCLIP_API_URL:-http://localhost:3100}"
API_KEY="${PAPERCLIP_API_KEY:-}"
COMPANY_ID="${PAPERCLIP_COMPANY_ID:-9d8f432c-ff7d-4e3a-bbe3-3cd355f73b64}"

# Domain agent roster (from AGENTS.md) — parallel arrays for bash 3.x compat
DOMAIN_ORDER=("audit-arch" "audit-sec" "audit-crypto")
DOMAIN_AGENT_IDS=(
    "8d6649e2-2df6-412a-a6bc-2d94bab3b73f"
    "a56f9e4a-ef9c-46d4-a736-1db5e19bbde4"
    "9874ad7a-dfbc-49b0-b3ed-d0efda6453bb"
)

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

for arg in "$@"; do
    case "$arg" in
        --project=*)  PROJECT="${arg#--project=}" ;;
        --bundle=*)   BUNDLE="${arg#--bundle=}" ;;
        --auditor-id=*) AUDITOR_ID="${arg#--auditor-id=}" ;;
        --api-url=*)  API_URL="${arg#--api-url=}" ;;
        --company-id=*) COMPANY_ID="${arg#--company-id=}" ;;
        --dry-run)    DRY_RUN=true ;;
        *)
            echo "error: unknown argument: $arg" >&2
            exit 2
            ;;
    esac
done

# Validation
if [[ -z "$PROJECT" && -z "$BUNDLE" ]]; then
    echo "error: exactly one of --project=<slug> or --bundle=<name> is required" >&2
    exit 2
fi
if [[ -n "$PROJECT" && -n "$BUNDLE" ]]; then
    echo "error: --project and --bundle are mutually exclusive" >&2
    exit 2
fi
if [[ -z "$AUDITOR_ID" ]]; then
    echo "error: --auditor-id=<uuid> is required" >&2
    exit 2
fi

TARGET="${PROJECT:-$BUNDLE}"

# Validate slug format
if ! echo "$TARGET" | grep -qE '^[a-z0-9]([a-z0-9-]{0,62}[a-z0-9])?$'; then
    echo "error: invalid slug '$TARGET': must match [a-z0-9-]{1,64}" >&2
    exit 2
fi

# ---------------------------------------------------------------------------
# Payload builders
# ---------------------------------------------------------------------------

parent_payload() {
    cat <<EOF
{
  "title": "audit: ${TARGET}",
  "body": "Full Audit-V1 report for \`${TARGET}\`.\n\nOrchestrator: wait for 3 domain child issues to complete, then assemble the final report from their sub-report comments.",
  "assigneeAgentId": "${AUDITOR_ID}",
  "companyId": "${COMPANY_ID}"
}
EOF
}

child_payload() {
    local domain="$1"
    local agent_id="$2"
    local parent_id="$3"
    cat <<EOF
{
  "title": "audit-domain: ${TARGET}/${domain}",
  "body": "Domain audit sub-report for \`${TARGET}\`.\n\nDomain: \`${domain}\`.\nFetch data via \`palace.audit.run(project=\"${TARGET}\")\`, produce a markdown sub-report per Auditor role instructions.",
  "assigneeAgentId": "${agent_id}",
  "parentIssueId": "${parent_id}",
  "companyId": "${COMPANY_ID}"
}
EOF
}

# ---------------------------------------------------------------------------
# Dry-run: print all 4 payloads and exit
# ---------------------------------------------------------------------------

if [[ "$DRY_RUN" == "true" ]]; then
    echo "["
    echo "$(parent_payload | python3 -c 'import json,sys; print(json.dumps(json.load(sys.stdin), indent=2))'),"
    idx=0
    for domain in "${DOMAIN_ORDER[@]}"; do
        agent_id="${DOMAIN_AGENT_IDS[$idx]}"
        payload="$(child_payload "$domain" "$agent_id" "<parent-id-placeholder>" | python3 -c 'import json,sys; print(json.dumps(json.load(sys.stdin), indent=2))')"
        idx=$((idx + 1))
        if [[ $idx -lt ${#DOMAIN_ORDER[@]} ]]; then
            echo "${payload},"
        else
            echo "${payload}"
        fi
    done
    echo "]"
    exit 0
fi

# ---------------------------------------------------------------------------
# Live run: call Paperclip API
# ---------------------------------------------------------------------------

_curl_post() {
    local payload="$1"
    if [[ -n "$API_KEY" ]]; then
        curl -s -f -X POST \
            -H "Content-Type: application/json" \
            -H "Authorization: Bearer ${API_KEY}" \
            -d "$payload" \
            "${API_URL}/api/companies/${COMPANY_ID}/issues"
    else
        curl -s -f -X POST \
            -H "Content-Type: application/json" \
            -d "$payload" \
            "${API_URL}/api/companies/${COMPANY_ID}/issues"
    fi
}

echo "Creating parent issue: audit: ${TARGET} ..."
PARENT_RESP="$(_curl_post "$(parent_payload)")"
PARENT_ID="$(echo "$PARENT_RESP" | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')"
echo "  Parent created: $PARENT_ID"

idx=0
for domain in "${DOMAIN_ORDER[@]}"; do
    agent_id="${DOMAIN_AGENT_IDS[$idx]}"
    idx=$((idx + 1))
    echo "Creating child issue: audit-domain: ${TARGET}/${domain} ..."
    CHILD_RESP="$(_curl_post "$(child_payload "$domain" "$agent_id" "$PARENT_ID")")"
    CHILD_ID="$(echo "$CHILD_RESP" | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')"
    echo "  Child created: $CHILD_ID — audit-domain: ${TARGET}/${domain}"
done

echo ""
echo "Audit workflow launched. Parent issue: ${PARENT_ID}"
