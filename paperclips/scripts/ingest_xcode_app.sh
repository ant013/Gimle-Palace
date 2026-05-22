#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DEFAULT_ENV_FILE="$REPO_ROOT/.env"
DEFAULT_MCP_URL="${PALACE_MCP_URL:-http://localhost:8080/mcp}"
DEFAULT_STAGE_ROOT="${PALACE_XCODE_APP_STAGE_ROOT:-$HOME/.cache/palace/xcode-app-mounts}"
PALACE_MCP_SERVICE_DIR="$REPO_ROOT/services/palace-mcp"

DEFAULT_EXTRACTORS=(
    symbol_index_swift
    arch_layer
    git_history
    code_ownership
    coding_convention
    crypto_domain_model
    cross_module_contract
    cross_repo_version_skew
    dead_symbol_binary_surface
    dependency_surface
    error_handling_policy
    hot_path_profiler
    hotspot
    localization_accessibility
    public_api_surface
    reactive_dependency_tracer
    testability_di
)

usage() {
    cat <<'EOF'
Usage: ingest_xcode_app.sh --repo-path <path> --slug <name> [options]

Register an Xcode application repo, update PALACE_SCIP_INDEX_PATHS, and run
the configured extractor cascade. Requires a pre-built SCIP index at
<repo>/scip/index.scip (or --scip-path).

Required:
  --repo-path <path>        Host path to the Xcode app repo
                            (must contain .xcworkspace or .xcodeproj, NOT Package.swift)
  --slug <name>             Palace project slug (lowercase letters, numbers, hyphens)

Options:
  --workspace <relpath>     Workspace path relative to --repo-path (auto-detected if omitted)
  --project <relpath>       Use .xcodeproj instead of .xcworkspace (mutually exclusive)
  --scip-path <path>        Host path to SCIP index (default: <repo>/scip/index.scip)
  --bundle <name>           Optional bundle to add the project to
  --extractors <csv>        Override extractor list
  --mcp-url <url>           palace-mcp MCP URL
  --parent-mount <name>     Explicit register_project parent_mount (auto-derived if omitted)
  --env-file <path>         Env file to update atomically (default: repo .env)
  --dry-run                 Print intended actions without changing state
  --help, -h                Show this message

Notes:
  - Xcode apps use .xcworkspace / .xcodeproj, NOT Package.swift.
    Use ingest_swift_kit.sh for SwiftPM kits.
  - SCIP must be built first: bash paperclips/scripts/scip_emit_uw_ios_app.sh
    (or equivalent Xcode build step) and copied to <repo>/scip/index.scip.
  - Dry-run validates slug, repo, and SCIP existence, but skips docker and MCP mutations.
  - parent_mount is auto-derived from --repo-path:
      .../HorizontalSystems/<repo>  -> parent_mount=hs
      Otherwise: lowercase basename of the parent directory.
    Override with --parent-mount if the auto-derived value is wrong.
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

json_or_null() {
    local value="${1:-}"
    if [[ -n "$value" ]] && printf '%s' "$value" | jq -e . >/dev/null 2>&1; then
        printf '%s' "$value"
    else
        printf 'null'
    fi
}

derive_parent_mount() {
    local host_repo_base="$1"
    case "$host_repo_base" in
        */HorizontalSystems)
            printf 'hs'
            ;;
        *)
            basename "$host_repo_base" | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9' '-' | sed 's/--*/-/g; s/^-//; s/-$//'
            ;;
    esac
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
        local -a compose_args
        compose_args=(--env-file "$ENV_FILE" -f "$REPO_ROOT/docker-compose.yml")
        if [[ -f "$REPO_ROOT/docker-compose.override.yml" ]]; then
            compose_args+=(-f "$REPO_ROOT/docker-compose.override.yml")
        fi
        if [[ -n "${COMPOSE_OVERRIDE_FILE:-}" ]]; then
            compose_args+=(-f "$COMPOSE_OVERRIDE_FILE")
        fi
        docker compose "${compose_args[@]}" "$@"
    )
}

runtime_stage_parent_mount() {
    local base="$1"
    local candidate="${base}-stage"
    if [[ ${#candidate} -le 16 ]]; then
        printf '%s' "$candidate"
    else
        printf 'stage'
    fi
}

host_path_requires_staging() {
    local host_path="$1"
    local docker_context
    docker_context="$(docker context show 2>/dev/null || true)"
    if [[ "$docker_context" != "colima" ]]; then
        return 1
    fi
    case "$host_path" in
        "$HOME"/*)
            return 1
            ;;
        *)
            return 0
            ;;
    esac
}

prepare_runtime_stage() {
    local stage_parent_mount="$1"

    require_command rsync

    STAGE_ROOT="$DEFAULT_STAGE_ROOT/$stage_parent_mount"
    STAGED_REPO_PATH="$STAGE_ROOT/$RELATIVE_PATH"
    COMPOSE_OVERRIDE_FILE="$STAGE_ROOT/palace-mcp.override.yml"

    mkdir -p "$STAGED_REPO_PATH"
    rsync -a --delete --exclude '.build/' "$REPO_PATH/" "$STAGED_REPO_PATH/"

    cat > "$COMPOSE_OVERRIDE_FILE" <<EOF
services:
  palace-mcp:
    volumes:
      - $STAGE_ROOT:/repos-$stage_parent_mount:ro
EOF
}

runtime_repo_visible_in_container() {
    local container_id
    container_id="$(docker_compose ps -q palace-mcp 2>/dev/null || true)"
    if [[ -z "$container_id" ]]; then
        return 1
    fi

    docker exec "$container_id" sh -lc "
        test -e '$CONTAINER_REPO_PATH/.git' &&
        test -d '$CONTAINER_REPO_PATH/$XCODE_PROJECT_RELPATH' &&
        test -f '$SCIP_PATH'
    " >/dev/null 2>&1
}

wait_for_mcp_health() {
    local health_url="${MCP_URL%/mcp}/healthz"
    local attempts=30
    local i
    for ((i = 1; i <= attempts; i++)); do
        if curl -fsS "$health_url" >/dev/null 2>&1; then
            return 0
        fi
        sleep 2
    done
    return 1
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
        --arg repo_path "$REPO_PATH" \
        --arg repo_base "${REPO_BASE:-}" \
        --arg parent_mount "${PARENT_MOUNT:-}" \
        --arg relative_path "${RELATIVE_PATH:-}" \
        --arg container_repo_path "${CONTAINER_REPO_PATH:-}" \
        --arg xcode_project_relpath "${XCODE_PROJECT_RELPATH:-}" \
        --arg host_scip_path "$HOST_SCIP_PATH" \
        --arg scip_path "${SCIP_PATH:-}" \
        --arg bundle "${BUNDLE:-}" \
        --arg mcp_url "$MCP_URL" \
        --arg stage_root "${STAGE_ROOT:-}" \
        --argjson dry_run "$(json_bool "$DRY_RUN")" \
        --argjson env_changed "$(json_bool "$ENV_CHANGED")" \
        --argjson palace_restarted "$(json_bool "$PALACE_RESTARTED")" \
        --argjson runtime_stage_used "$(json_bool "$RUNTIME_STAGE_USED")" \
        --argjson extractors "$EXTRACTOR_RESULTS_JSON" \
        --argjson project_registration "$(json_or_null "$PROJECT_REGISTRATION_JSON")" \
        --argjson bundle_registration "$(json_or_null "$BUNDLE_REGISTRATION_JSON")" \
        --argjson bundle_membership "$(json_or_null "$BUNDLE_MEMBERSHIP_JSON")" \
        --argjson health "$(json_or_null "$LAST_HEALTH_JSON")" \
        '{
            stage: $stage,
            status: $status,
            message: $message,
            slug: $slug,
            repo_path: $repo_path,
            repo_base: (if $repo_base == "" then null else $repo_base end),
            parent_mount: (if $parent_mount == "" then null else $parent_mount end),
            relative_path: (if $relative_path == "" then null else $relative_path end),
            container_repo_path: (if $container_repo_path == "" then null else $container_repo_path end),
            xcode_project_relpath: (if $xcode_project_relpath == "" then null else $xcode_project_relpath end),
            host_scip_path: $host_scip_path,
            scip_path: (if $scip_path == "" then null else $scip_path end),
            bundle: (if $bundle == "" then null else $bundle end),
            mcp_url: $mcp_url,
            stage_root: (if $stage_root == "" then null else $stage_root end),
            dry_run: $dry_run,
            env_changed: $env_changed,
            palace_restarted: $palace_restarted,
            runtime_stage_used: $runtime_stage_used,
            project_registration: $project_registration,
            bundle_registration: $bundle_registration,
            bundle_membership: $bundle_membership,
            extractors: $extractors,
            health: $health
        }'
}

# ─── argument parsing ────────────────────────────────────────────────────────

SLUG=""
REPO_PATH=""
WORKSPACE_RELPATH=""
PROJECT_RELPATH=""
SCIP_PATH_OVERRIDE=""
BUNDLE=""
EXTRACTORS_CSV=""
MCP_URL="$DEFAULT_MCP_URL"
PARENT_MOUNT=""
ENV_FILE="$DEFAULT_ENV_FILE"
DRY_RUN="false"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --repo-path=*)
            REPO_PATH="${1#*=}"
            shift
            ;;
        --repo-path)
            [[ $# -ge 2 ]] || die "--repo-path requires a value"
            REPO_PATH="$2"
            shift 2
            ;;
        --slug=*)
            SLUG="${1#*=}"
            shift
            ;;
        --slug)
            [[ $# -ge 2 ]] || die "--slug requires a value"
            SLUG="$2"
            shift 2
            ;;
        --workspace=*)
            WORKSPACE_RELPATH="${1#*=}"
            shift
            ;;
        --workspace)
            [[ $# -ge 2 ]] || die "--workspace requires a value"
            WORKSPACE_RELPATH="$2"
            shift 2
            ;;
        --project=*)
            PROJECT_RELPATH="${1#*=}"
            shift
            ;;
        --project)
            [[ $# -ge 2 ]] || die "--project requires a value"
            PROJECT_RELPATH="$2"
            shift 2
            ;;
        --scip-path=*)
            SCIP_PATH_OVERRIDE="${1#*=}"
            shift
            ;;
        --scip-path)
            [[ $# -ge 2 ]] || die "--scip-path requires a value"
            SCIP_PATH_OVERRIDE="$2"
            shift 2
            ;;
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
        --parent-mount=*)
            PARENT_MOUNT="${1#*=}"
            shift
            ;;
        --parent-mount)
            [[ $# -ge 2 ]] || die "--parent-mount requires a value"
            PARENT_MOUNT="$2"
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
            die "unexpected positional argument: $1 (use --slug <name>)"
            ;;
    esac
done

[[ -n "$SLUG" ]] || {
    usage >&2
    printf '\nERROR: --slug is required\n' >&2
    exit 2
}
[[ -n "$REPO_PATH" ]] || {
    usage >&2
    printf '\nERROR: --repo-path is required\n' >&2
    exit 2
}
[[ -z "$WORKSPACE_RELPATH" || -z "$PROJECT_RELPATH" ]] || \
    die "--workspace and --project are mutually exclusive"

validate_slug "$SLUG"
require_command jq

# ─── repo validation ─────────────────────────────────────────────────────────

[[ -d "$REPO_PATH" ]] || die "repo path not found: $REPO_PATH"
[[ -e "$REPO_PATH/.git" ]] || die "not a git repo (no .git): $REPO_PATH"

if [[ -f "$REPO_PATH/Package.swift" ]]; then
    die "Package.swift found at $REPO_PATH — this looks like a SwiftPM kit. Use ingest_swift_kit.sh instead."
fi

# auto-detect workspace or project if neither given explicitly
if [[ -z "$WORKSPACE_RELPATH" && -z "$PROJECT_RELPATH" ]]; then
    detected=""
    while IFS= read -r -d '' candidate; do
        detected="$(basename "$candidate")"
        break
    done < <(find "$REPO_PATH" -maxdepth 1 -name "*.xcworkspace" -type d -print0 2>/dev/null)

    if [[ -z "$detected" ]]; then
        while IFS= read -r -d '' candidate; do
            detected="$(basename "$candidate")"
            break
        done < <(find "$REPO_PATH" -maxdepth 1 -name "*.xcodeproj" -type d -print0 2>/dev/null)
    fi

    if [[ -z "$detected" ]]; then
        die "no .xcworkspace or .xcodeproj found at root of $REPO_PATH"
    fi

    if [[ "$detected" == *.xcworkspace ]]; then
        WORKSPACE_RELPATH="$detected"
    else
        PROJECT_RELPATH="$detected"
    fi
fi

# validate the declared workspace/project exists
if [[ -n "$WORKSPACE_RELPATH" ]]; then
    [[ -d "$REPO_PATH/$WORKSPACE_RELPATH" ]] || \
        die ".xcworkspace not found: $REPO_PATH/$WORKSPACE_RELPATH"
    XCODE_PROJECT_RELPATH="$WORKSPACE_RELPATH"
else
    [[ -d "$REPO_PATH/$PROJECT_RELPATH" ]] || \
        die ".xcodeproj not found: $REPO_PATH/$PROJECT_RELPATH"
    XCODE_PROJECT_RELPATH="$PROJECT_RELPATH"
fi

# ─── path derivation ─────────────────────────────────────────────────────────

HOST_SCIP_PATH="${SCIP_PATH_OVERRIDE:-$REPO_PATH/scip/index.scip}"
[[ -f "$HOST_SCIP_PATH" ]] || die "SCIP index not found: $HOST_SCIP_PATH"
[[ -s "$HOST_SCIP_PATH" ]] || die "SCIP index is empty: $HOST_SCIP_PATH"

RELATIVE_PATH="$(basename "$REPO_PATH")"
HOST_REPO_BASE="$(dirname "$REPO_PATH")"

if [[ -z "$PARENT_MOUNT" ]]; then
    PARENT_MOUNT="$(derive_parent_mount "$HOST_REPO_BASE")"
fi

REPO_BASE="/repos-$PARENT_MOUNT"
CONTAINER_REPO_PATH="$REPO_BASE/$RELATIVE_PATH"
SCIP_PATH="$CONTAINER_REPO_PATH/scip/index.scip"
COMPOSE_OVERRIDE_FILE=""
RUNTIME_STAGE_USED="false"
STAGE_ROOT=""

PROJECT_REGISTRATION_JSON='null'
BUNDLE_REGISTRATION_JSON='null'
BUNDLE_MEMBERSHIP_JSON='null'
LAST_HEALTH_JSON='null'
EXTRACTOR_RESULTS_JSON='[]'
ENV_CHANGED="false"
PALACE_RESTARTED="false"

[[ -f "$ENV_FILE" ]] || die "env file not found: $ENV_FILE"

if [[ "$DRY_RUN" == "false" ]]; then
    require_command docker
    require_command curl
    if [[ -z "${PALACE_MCP_CLI_BIN:-}" ]]; then
        require_command uv
    fi

    if host_path_requires_staging "$REPO_PATH"; then
        stage_parent_mount="$(runtime_stage_parent_mount "$PARENT_MOUNT")"
        log "staging $REPO_PATH into $DEFAULT_STAGE_ROOT for docker context colima"
        prepare_runtime_stage "$stage_parent_mount"
        PARENT_MOUNT="$stage_parent_mount"
        REPO_BASE="/repos-$PARENT_MOUNT"
        CONTAINER_REPO_PATH="$REPO_BASE/$RELATIVE_PATH"
        SCIP_PATH="$CONTAINER_REPO_PATH/scip/index.scip"
        RUNTIME_STAGE_USED="true"
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

if [[ "$ENV_CHANGED" == "true" || "$RUNTIME_STAGE_USED" == "true" ]]; then
    if [[ "$RUNTIME_STAGE_USED" == "true" ]]; then
        log "recreating palace-mcp with staged runtime repo mount"
    else
        log "recreating palace-mcp after env change"
    fi
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

if ! runtime_repo_visible_in_container; then
    die "palace-mcp runtime cannot see repo content at $CONTAINER_REPO_PATH (expected .git, $XCODE_PROJECT_RELPATH directory, and scip/index.scip). If docker context is colima, ensure the repo is staged under \$HOME or share $HOST_REPO_BASE into the VM."
fi
if ! wait_for_mcp_health; then
    die "palace-mcp did not become healthy at ${MCP_URL%/mcp}/healthz"
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
    bundle_payload="$(jq -nc --arg name "$BUNDLE" --arg description "Bundle $BUNDLE" \
        '{name: $name, description: $description}')"
    BUNDLE_REGISTRATION_JSON="$(call_mcp "palace.memory.register_bundle" "$bundle_payload")" || {
        emit_summary "register_bundle" "failed" "memory.register_bundle failed"
        exit 1
    }

    membership_payload="$(jq -nc --arg bundle "$BUNDLE" --arg project "$SLUG" --arg tier "first-party" \
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
