#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DEFAULT_MANIFEST="$REPO_ROOT/services/palace-mcp/scripts/uw-ios-bundle-manifest.json"
DEFAULT_ENV_FILE="$REPO_ROOT/.env"
DEFAULT_MCP_URL="${PALACE_MCP_URL:-http://localhost:8080/mcp}"
DEFAULT_REPO_BASE="${PALACE_SWIFT_KIT_REPO_BASE:-/repos-hs}"
DEFAULT_HOST_REPO_BASE="${PALACE_SWIFT_KIT_HOST_REPO_BASE:-/Users/Shared/Ios/HorizontalSystems}"
PALACE_MCP_SERVICE_DIR="$REPO_ROOT/services/palace-mcp"

DEFAULT_EXTRACTORS=(
    symbol_index_swift
    git_history
    dependency_surface
    public_api_surface
    dead_symbol_binary_surface
    hotspot
    cross_module_contract
    code_ownership
    cross_repo_version_skew
    crypto_domain_model
)

usage() {
    cat <<'EOF'
Usage: ingest_swift_kit.sh <kit-slug> [options]

Register a single Swift kit, update PALACE_SCIP_INDEX_PATHS, and run the
configured extractor cascade.

Options:
  --bundle <name>           Optional bundle to add the project to
  --extractors <csv>        Override extractor list
  --mcp-url <url>           palace-mcp MCP URL
  --repo-base <path>        Container-visible repo base (default: /repos-hs)
  --host-repo-base <path>   Host repo base for preflight checks
                            (default: /Users/Shared/Ios/HorizontalSystems)
  --parent-mount <name>     Explicit register_project parent_mount
  --relative-path <path>    Explicit repo-relative path under repo-base
  --manifest <path>         Manifest used for slug -> relative_path lookup
  --env-file <path>         Env file to update atomically (default: repo .env)
  --dry-run                 Print intended actions without changing state
  --help, -h                Show this message

Notes:
  - When a manifest contains the slug, its relative_path and tier are reused.
  - Dry-run still validates slug, manifest resolution, repo mount, and SCIP
    existence, but it skips docker and MCP mutations.
EOF
}

log() {
    printf '[%s] %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*"
}

die() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

require_command() {
    command -v "$1" >/dev/null 2>&1 || die "missing required command: $1"
}

validate_slug() {
    local slug="$1"
    [[ "$slug" =~ ^[a-z0-9]([a-z0-9-]{0,62}[a-z0-9])?$ ]] || \
        die "invalid slug '$slug' (must match [a-z0-9-]{1,64})"
}

json_bool() {
    if [[ "$1" == "true" ]]; then
        printf 'true'
    else
        printf 'false'
    fi
}

resolve_manifest_member() {
    local manifest="$1"
    local slug="$2"
    [[ -f "$manifest" ]] || return 0
    python3 - "$manifest" "$slug" <<'PY'
import json
import sys
from pathlib import Path

manifest_path = Path(sys.argv[1])
slug = sys.argv[2]
data = json.loads(manifest_path.read_text())
for member in data.get("members", []):
    if member.get("slug") == slug:
        print(json.dumps({
            "relative_path": member.get("relative_path"),
            "tier": member.get("tier"),
            "bundle_name": data.get("bundle_name"),
            "bundle_description": data.get("bundle_description"),
            "parent_mount": data.get("parent_mount"),
        }))
        raise SystemExit(0)
PY
}

update_env_json_key() {
    local env_file="$1"
    local key="$2"
    local value="$3"
    local tmp_file
    local replaced="false"

    tmp_file="$(mktemp "${env_file}.tmp.XXXXXX")"
    while IFS= read -r line || [[ -n "$line" ]]; do
        if [[ "$line" == "$key="* ]]; then
            if [[ "$replaced" == "false" ]]; then
                printf '%s=%s\n' "$key" "$value" >> "$tmp_file"
                replaced="true"
            fi
        else
            printf '%s\n' "$line" >> "$tmp_file"
        fi
    done < "$env_file"

    if [[ "$replaced" == "false" ]]; then
        printf '%s=%s\n' "$key" "$value" >> "$tmp_file"
    fi

    mv "$tmp_file" "$env_file"
}

call_mcp() {
    local tool_name="$1"
    local payload="$2"
    local -a cmd

    if [[ -n "${PALACE_MCP_CLI_BIN:-}" ]]; then
        cmd=("$PALACE_MCP_CLI_BIN" tool call "$tool_name" --url "$MCP_URL" --json "$payload")
    else
        cmd=(uv run --directory "$PALACE_MCP_SERVICE_DIR" python -m palace_mcp.cli tool call "$tool_name" --url "$MCP_URL" --json "$payload")
    fi

    set +e
    local output
    output="$("${cmd[@]}")"
    local rc=$?
    set -e
    printf '%s' "$output"
    return "$rc"
}

docker_compose() {
    (
        cd "$REPO_ROOT"
        docker compose "$@"
    )
}

emit_summary() {
    local stage="$1"
    local status="$2"
    local message="$3"
    jq -nc \
        --arg stage "$stage" \
        --arg status "$status" \
        --arg message "$message" \
        --arg slug "$SLUG" \
        --arg repo_base "$REPO_BASE" \
        --arg host_repo_base "$HOST_REPO_BASE" \
        --arg parent_mount "${PARENT_MOUNT:-}" \
        --arg relative_path "$RELATIVE_PATH" \
        --arg repo_path "$HOST_REPO_PATH" \
        --arg container_repo_path "$CONTAINER_REPO_PATH" \
        --arg host_scip_path "$HOST_SCIP_PATH" \
        --arg scip_path "$SCIP_PATH" \
        --arg bundle "${BUNDLE:-}" \
        --arg mcp_url "$MCP_URL" \
        --argjson dry_run "$(json_bool "$DRY_RUN")" \
        --argjson env_changed "$(json_bool "$ENV_CHANGED")" \
        --argjson palace_restarted "$(json_bool "$PALACE_RESTARTED")" \
        --argjson extractors "$EXTRACTOR_RESULTS_JSON" \
        --argjson project_registration "$PROJECT_REGISTRATION_JSON" \
        --argjson bundle_registration "$BUNDLE_REGISTRATION_JSON" \
        --argjson bundle_membership "$BUNDLE_MEMBERSHIP_JSON" \
        --argjson health "$LAST_HEALTH_JSON" \
        '{
            stage: $stage,
            status: $status,
            message: $message,
            slug: $slug,
            repo_base: $repo_base,
            host_repo_base: $host_repo_base,
            parent_mount: (if $parent_mount == "" then null else $parent_mount end),
            relative_path: $relative_path,
            repo_path: $repo_path,
            container_repo_path: $container_repo_path,
            host_scip_path: $host_scip_path,
            scip_path: $scip_path,
            bundle: (if $bundle == "" then null else $bundle end),
            mcp_url: $mcp_url,
            dry_run: $dry_run,
            env_changed: $env_changed,
            palace_restarted: $palace_restarted,
            project_registration: $project_registration,
            bundle_registration: $bundle_registration,
            bundle_membership: $bundle_membership,
            extractors: $extractors,
            health: $health
        }'
}

SLUG=""
BUNDLE=""
EXTRACTORS_CSV=""
MCP_URL="$DEFAULT_MCP_URL"
REPO_BASE="$DEFAULT_REPO_BASE"
HOST_REPO_BASE="$DEFAULT_HOST_REPO_BASE"
PARENT_MOUNT=""
RELATIVE_PATH=""
MANIFEST_PATH="$DEFAULT_MANIFEST"
ENV_FILE="$DEFAULT_ENV_FILE"
DRY_RUN="false"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --bundle=*)
            BUNDLE="${1#*=}"
            shift
            ;;
        --bundle)
            [[ $# -ge 2 ]] || die "--bundle requires a value"
            BUNDLE="$2"
            shift 2
            ;;
        --extractors=*)
            EXTRACTORS_CSV="${1#*=}"
            shift
            ;;
        --extractors)
            [[ $# -ge 2 ]] || die "--extractors requires a value"
            EXTRACTORS_CSV="$2"
            shift 2
            ;;
        --mcp-url=*)
            MCP_URL="${1#*=}"
            shift
            ;;
        --mcp-url)
            [[ $# -ge 2 ]] || die "--mcp-url requires a value"
            MCP_URL="$2"
            shift 2
            ;;
        --repo-base=*)
            REPO_BASE="${1#*=}"
            shift
            ;;
        --repo-base)
            [[ $# -ge 2 ]] || die "--repo-base requires a value"
            REPO_BASE="$2"
            shift 2
            ;;
        --host-repo-base=*)
            HOST_REPO_BASE="${1#*=}"
            shift
            ;;
        --host-repo-base)
            [[ $# -ge 2 ]] || die "--host-repo-base requires a value"
            HOST_REPO_BASE="$2"
            shift 2
            ;;
        --parent-mount=*)
            PARENT_MOUNT="${1#*=}"
            shift
            ;;
        --parent-mount)
            [[ $# -ge 2 ]] || die "--parent-mount requires a value"
            PARENT_MOUNT="$2"
            shift 2
            ;;
        --relative-path=*)
            RELATIVE_PATH="${1#*=}"
            shift
            ;;
        --relative-path)
            [[ $# -ge 2 ]] || die "--relative-path requires a value"
            RELATIVE_PATH="$2"
            shift 2
            ;;
        --manifest=*)
            MANIFEST_PATH="${1#*=}"
            shift
            ;;
        --manifest)
            [[ $# -ge 2 ]] || die "--manifest requires a value"
            MANIFEST_PATH="$2"
            shift 2
            ;;
        --env-file=*)
            ENV_FILE="${1#*=}"
            shift
            ;;
        --env-file)
            [[ $# -ge 2 ]] || die "--env-file requires a value"
            ENV_FILE="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN="true"
            shift
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        --*)
            die "unknown option: $1"
            ;;
        *)
            if [[ -z "$SLUG" ]]; then
                SLUG="$1"
                shift
            else
                die "unexpected positional argument: $1"
            fi
            ;;
    esac
done

[[ -n "$SLUG" ]] || {
    usage >&2
    exit 2
}

validate_slug "$SLUG"
require_command jq
require_command python3

MANIFEST_JSON="$(resolve_manifest_member "$MANIFEST_PATH" "$SLUG" || true)"
MANIFEST_JSON="${MANIFEST_JSON:-}"
if [[ -z "$MANIFEST_JSON" ]]; then
    MANIFEST_JSON='{}'
fi
if [[ -z "$RELATIVE_PATH" ]]; then
    RELATIVE_PATH="$(printf '%s' "$MANIFEST_JSON" | jq -r '.relative_path // empty')"
fi
if [[ -z "$RELATIVE_PATH" ]]; then
    RELATIVE_PATH="$SLUG"
fi
if [[ -z "$PARENT_MOUNT" ]]; then
    PARENT_MOUNT="$(printf '%s' "$MANIFEST_JSON" | jq -r '.parent_mount // empty')"
fi
if [[ -z "$PARENT_MOUNT" && "$REPO_BASE" == /repos-* ]]; then
    PARENT_MOUNT="${REPO_BASE#/repos-}"
fi

HOST_REPO_PATH="$HOST_REPO_BASE/$RELATIVE_PATH"
CONTAINER_REPO_PATH="$REPO_BASE/$RELATIVE_PATH"
HOST_SCIP_PATH="$HOST_REPO_PATH/scip/index.scip"
SCIP_PATH="$CONTAINER_REPO_PATH/scip/index.scip"

PROJECT_REGISTRATION_JSON='null'
BUNDLE_REGISTRATION_JSON='null'
BUNDLE_MEMBERSHIP_JSON='null'
LAST_HEALTH_JSON='null'
EXTRACTOR_RESULTS_JSON='[]'
ENV_CHANGED="false"
PALACE_RESTARTED="false"

[[ -f "$ENV_FILE" ]] || die "env file not found: $ENV_FILE"
[[ -d "$HOST_REPO_PATH" ]] || die "repo mount not found: $HOST_REPO_PATH"
[[ -f "$HOST_SCIP_PATH" ]] || die "SCIP index not found: $HOST_SCIP_PATH"

if [[ "$DRY_RUN" == "false" ]]; then
    require_command docker
    if [[ -z "${PALACE_MCP_CLI_BIN:-}" ]]; then
        require_command uv
    fi
    docker_compose version >/dev/null
fi

if [[ -n "$EXTRACTORS_CSV" ]]; then
    IFS=',' read -r -a EXTRACTORS <<<"$EXTRACTORS_CSV"
else
    EXTRACTORS=("${DEFAULT_EXTRACTORS[@]}")
fi

current_scip_json="$(grep '^PALACE_SCIP_INDEX_PATHS=' "$ENV_FILE" | tail -n 1 | cut -d= -f2- || true)"
if [[ -z "$current_scip_json" ]]; then
    current_scip_json='{}'
fi
printf '%s' "$current_scip_json" | jq -e . >/dev/null || \
    die "PALACE_SCIP_INDEX_PATHS is not valid JSON in $ENV_FILE"

merged_scip_json="$(jq -nc \
    --argjson current "$current_scip_json" \
    --arg slug "$SLUG" \
    --arg path "$SCIP_PATH" \
    '$current + {($slug): $path}')"

if [[ "$merged_scip_json" != "$current_scip_json" ]]; then
    log "updating PALACE_SCIP_INDEX_PATHS in $ENV_FILE"
    if [[ "$DRY_RUN" == "false" ]]; then
        update_env_json_key "$ENV_FILE" "PALACE_SCIP_INDEX_PATHS" "$merged_scip_json"
    else
        printf 'DRY-RUN: update %s PALACE_SCIP_INDEX_PATHS -> %s\n' "$ENV_FILE" "$merged_scip_json"
    fi
    ENV_CHANGED="true"
else
    log "PALACE_SCIP_INDEX_PATHS already contains $SLUG"
fi

if [[ "$ENV_CHANGED" == "true" ]]; then
    log "recreating palace-mcp after env change"
    if [[ "$DRY_RUN" == "false" ]]; then
        docker_compose up -d --force-recreate palace-mcp
    else
        printf 'DRY-RUN: docker compose up -d --force-recreate palace-mcp\n'
    fi
    PALACE_RESTARTED="true"
fi

if [[ "$DRY_RUN" == "true" ]]; then
    emit_summary "dry-run" "planned" "validated inputs; skipped docker and MCP mutations"
    exit 0
fi

registered_extractors_json="$(call_mcp "palace.ingest.list_extractors" '{}' || true)"
registered_extractors=""
if [[ -n "$registered_extractors_json" ]] && printf '%s' "$registered_extractors_json" | jq -e '.ok == true' >/dev/null 2>&1; then
    registered_extractors="$(printf '%s' "$registered_extractors_json" | jq -r '.extractors[].name')"
else
    log "WARN: unable to list extractors up front; will rely on run_extractor responses"
fi

project_payload="$(jq -nc \
    --arg slug "$SLUG" \
    --arg name "$SLUG" \
    --arg parent_mount "$PARENT_MOUNT" \
    --arg relative_path "$RELATIVE_PATH" \
    '{slug: $slug, name: $name}
     + (if $parent_mount != "" then {parent_mount: $parent_mount, relative_path: $relative_path} else {} end)')"
PROJECT_REGISTRATION_JSON="$(call_mcp "palace.memory.register_project" "$project_payload")" || {
    emit_summary "register_project" "failed" "memory.register_project failed"
    exit 1
}

if [[ -n "$BUNDLE" ]]; then
    bundle_description="$(printf '%s' "$MANIFEST_JSON" | jq -r \
        --arg bundle "$BUNDLE" \
        'if .bundle_name == $bundle then (.bundle_description // ("Bundle " + $bundle)) else ("Bundle " + $bundle) end')"
    bundle_tier="$(printf '%s' "$MANIFEST_JSON" | jq -r '.tier // "first-party"')"

    bundle_payload="$(jq -nc --arg name "$BUNDLE" --arg description "$bundle_description" \
        '{name: $name, description: $description}')"
    BUNDLE_REGISTRATION_JSON="$(call_mcp "palace.memory.register_bundle" "$bundle_payload")" || {
        emit_summary "register_bundle" "failed" "memory.register_bundle failed"
        exit 1
    }

    membership_payload="$(jq -nc --arg bundle "$BUNDLE" --arg project "$SLUG" --arg tier "$bundle_tier" \
        '{bundle: $bundle, project: $project, tier: $tier}')"
    BUNDLE_MEMBERSHIP_JSON="$(call_mcp "palace.memory.add_to_bundle" "$membership_payload")" || {
        emit_summary "add_to_bundle" "failed" "memory.add_to_bundle failed"
        exit 1
    }
fi

for extractor in "${EXTRACTORS[@]}"; do
    extractor="$(printf '%s' "$extractor" | xargs)"
    [[ -n "$extractor" ]] || continue

    if [[ -n "$registered_extractors" ]] && ! printf '%s\n' "$registered_extractors" | grep -qx "$extractor"; then
        item="$(jq -nc --arg name "$extractor" --arg status "skipped" --arg reason "not_registered" \
            '{name: $name, status: $status, reason: $reason}')"
        EXTRACTOR_RESULTS_JSON="$(jq -nc --argjson arr "$EXTRACTOR_RESULTS_JSON" --argjson item "$item" '$arr + [$item]')"
        continue
    fi

    payload="$(jq -nc --arg name "$extractor" --arg project "$SLUG" '{name: $name, project: $project}')"
    set +e
    extractor_json="$(call_mcp "palace.ingest.run_extractor" "$payload")"
    rc=$?
    set -e

    if [[ -n "$extractor_json" ]]; then
        health_payload="$(jq -nc --arg slug "$SLUG" '{slug: $slug}')"
        LAST_HEALTH_JSON="$(call_mcp "palace.memory.get_project_overview" "$health_payload" || printf 'null')"
    fi

    if [[ $rc -eq 0 ]] && printf '%s' "$extractor_json" | jq -e '.ok == true' >/dev/null 2>&1; then
        item="$(printf '%s' "$extractor_json" | jq -c '. + {status: "ok"}')"
    else
        error_code="$(printf '%s' "$extractor_json" | jq -r '.error_code // "unknown_error"' 2>/dev/null || printf 'unknown_error')"
        message="$(printf '%s' "$extractor_json" | jq -r '.message // "extractor invocation failed"' 2>/dev/null || printf 'extractor invocation failed')"
        if [[ "$error_code" == "unknown_extractor" ]]; then
            item="$(jq -nc --arg name "$extractor" --arg status "skipped" --arg reason "$error_code" --arg message "$message" \
                '{name: $name, status: $status, reason: $reason, message: $message}')"
        else
            item="$(jq -nc --arg name "$extractor" --arg status "failed" --arg error_code "$error_code" --arg message "$message" \
                '{name: $name, status: $status, error_code: $error_code, message: $message}')"
        fi
    fi

    EXTRACTOR_RESULTS_JSON="$(jq -nc --argjson arr "$EXTRACTOR_RESULTS_JSON" --argjson item "$item" '$arr + [$item]')"
done

failed_count="$(printf '%s' "$EXTRACTOR_RESULTS_JSON" | jq '[.[] | select(.status == "failed")] | length')"
if [[ "$failed_count" -gt 0 ]]; then
    emit_summary "extractors" "partial_failure" "one or more extractors failed"
    exit 1
fi

emit_summary "complete" "ok" "ingestion finished"
