#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DEFAULT_ENV_FILE="$REPO_ROOT/.env"
DEFAULT_MCP_URL="${PALACE_MCP_URL:-http://localhost:8080/mcp}"
DEFAULT_HOST_REPO_PATH="${PALACE_KOTLIN_REPO_PATH:-/Users/Shared/Android/unstoppable-wallet-android}"
DEFAULT_CONTAINER_REPO_PATH="${PALACE_KOTLIN_CONTAINER_REPO_PATH:-/repos/uw-android}"
DEFAULT_COMPOSE_PROJECT_NAME="${PALACE_COMPOSE_PROJECT_NAME:-gimle-palace}"
DEFAULT_COMPOSE_FILE="${PALACE_COMPOSE_FILE:-$REPO_ROOT/docker-compose.yml}"
DEFAULT_SCIP_JAVA="${SCIP_JAVA:-$HOME/Library/Application Support/Coursier/bin/scip-java}"
DEFAULT_GRADLE_BIN="./gradlew"
DEFAULT_GRADLE_TASK="compileDebugKotlin"
PINNED_SHA="c0489d5a33f5da441f07b1f685d42b25b805ffd1"
SEMANTICDB_VERSION="0.5.0"
PALACE_MCP_SERVICE_DIR="$REPO_ROOT/services/palace-mcp"

DEFAULT_EXTRACTORS=(
    symbol_index_java
    arch_layer
    git_history
    code_ownership
    dependency_surface
    hotspot
    coding_convention
    cross_repo_version_skew
    public_api_surface
    cross_module_contract
    hot_path_profiler
    testability_di
)

usage() {
    cat <<'EOF'
Usage: ingest_kotlin_module.sh [project-slug] [options]

Generate SCIP for a pinned Android/Kotlin repo, register the project, and run a
curated extractor set.

Options:
  --host-repo-path <path>       Host repo path (default: /Users/Shared/Android/unstoppable-wallet-android)
  --container-repo-path <path>  Container-visible repo path (default: /repos/uw-android)
  --extractors <csv>            Override extractor list
  --env-file <path>             Env file to update atomically (default: repo .env)
  --mcp-url <url>               palace-mcp MCP URL
  --compose-project-name <name> Docker compose project name (default: gimle-palace)
  --compose-file <path>         Docker compose file used for palace-mcp recreation
  --scip-java <path>            scip-java binary path
  --gradle-bin <path>           Gradle executable relative to repo or absolute
  --gradle-task <name>          Gradle task to run (default: compileDebugKotlin)
  --force-restart-palace-mcp    Recreate palace-mcp even if PALACE_SCIP_INDEX_PATHS is unchanged
  --dry-run                     Validate inputs and print the plan
  --help, -h                    Show this message

Notes:
  - The repo must already be pinned to UW@c0489d5a3 (pre-AGP-9).
  - The script injects semanticdb-kotlinc 0.5.0 via a temporary Gradle init script.
  - Default extractor set is intentionally broader than the built-in android_kit
    audit profile so the ingest summary surfaces useful coverage.
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
    if [[ -n "${PALACE_MCP_CLI_BIN:-}" ]]; then
        "$PALACE_MCP_CLI_BIN" tool call "$tool_name" --url "$MCP_URL" --json "$payload"
    else
        uv run --directory "$PALACE_MCP_SERVICE_DIR" \
            python -m palace_mcp.cli tool call "$tool_name" --url "$MCP_URL" --json "$payload"
    fi
}

docker_compose() {
    (
        cd "$REPO_ROOT"
        docker compose -p "$COMPOSE_PROJECT_NAME" --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"
    )
}

wait_for_mcp_health() {
    local health_url="${MCP_URL%/mcp}/healthz"
    local i
    for ((i = 1; i <= 30; i++)); do
        if curl -fsS "$health_url" >/dev/null 2>&1; then
            return 0
        fi
        sleep 2
    done
    return 1
}

write_gradle_init_script() {
    cat > "$1" <<EOF
allprojects { project ->
    def semanticdbTargetRoot = rootProject.layout.buildDirectory.dir("semanticdb-targetroot")

    project.configurations.matching { it.name == "kotlinCompilerPluginClasspath" }.all { cfg ->
        cfg.dependencies.add(project.dependencies.create("com.sourcegraph:semanticdb-kotlinc:${SEMANTICDB_VERSION}"))
    }

    project.tasks.configureEach { task ->
        def className = task.class.name
        if (!className.contains("Kotlin")) {
            return
        }
        if (task.hasProperty("compilerOptions")) {
            task.compilerOptions.freeCompilerArgs.addAll(
                "-P=plugin:semanticdb-kotlinc:sourceroot=${HOST_REPO_PATH}",
                "-P=plugin:semanticdb-kotlinc:targetroot=\${semanticdbTargetRoot.get().asFile.absolutePath}"
            )
        } else if (task.hasProperty("kotlinOptions")) {
            task.kotlinOptions.freeCompilerArgs += [
                "-P=plugin:semanticdb-kotlinc:sourceroot=${HOST_REPO_PATH}",
                "-P=plugin:semanticdb-kotlinc:targetroot=\${semanticdbTargetRoot.get().asFile.absolutePath}"
            ]
        }
    }
}
EOF
}

emit_summary() {
    jq -nc \
        --arg slug "$SLUG" \
        --arg host_repo_path "$HOST_REPO_PATH" \
        --arg container_repo_path "$CONTAINER_REPO_PATH" \
        --arg scip_path "$SCIP_PATH" \
        --arg pinned_sha "$PINNED_SHA" \
        --arg actual_sha "$ACTUAL_SHA" \
        --arg mcp_url "$MCP_URL" \
        --arg compose_project_name "$COMPOSE_PROJECT_NAME" \
        --arg gradle_task "$GRADLE_TASK" \
        --argjson dry_run "$(json_bool "$DRY_RUN")" \
        --argjson env_changed "$(json_bool "$ENV_CHANGED")" \
        --argjson palace_restarted "$(json_bool "$PALACE_RESTARTED")" \
        --argjson force_restart_palace_mcp "$(json_bool "$FORCE_RESTART_PALACE_MCP")" \
        --argjson semanticdb_count "$SEMANTICDB_COUNT" \
        --argjson scip_bytes "$SCIP_BYTES" \
        --argjson duration_seconds "$DURATION_SECONDS" \
        --argjson extractors "$EXTRACTOR_RESULTS_JSON" \
        --argjson project_registration "$(json_or_null "$PROJECT_REGISTRATION_JSON")" \
        '{
            slug: $slug,
            host_repo_path: $host_repo_path,
            container_repo_path: $container_repo_path,
            scip_path: $scip_path,
            pinned_sha: $pinned_sha,
            actual_sha: $actual_sha,
            mcp_url: $mcp_url,
            compose_project_name: $compose_project_name,
            gradle_task: $gradle_task,
            dry_run: $dry_run,
            env_changed: $env_changed,
            palace_restarted: $palace_restarted,
            force_restart_palace_mcp: $force_restart_palace_mcp,
            semanticdb_count: $semanticdb_count,
            scip_bytes: $scip_bytes,
            duration_seconds: $duration_seconds,
            extractors: $extractors,
            project_registration: $project_registration
        }'
}

SLUG="uw-android"
HOST_REPO_PATH="$DEFAULT_HOST_REPO_PATH"
CONTAINER_REPO_PATH="$DEFAULT_CONTAINER_REPO_PATH"
EXTRACTORS_CSV=""
ENV_FILE="$DEFAULT_ENV_FILE"
MCP_URL="$DEFAULT_MCP_URL"
COMPOSE_PROJECT_NAME="$DEFAULT_COMPOSE_PROJECT_NAME"
COMPOSE_FILE="$DEFAULT_COMPOSE_FILE"
SCIP_JAVA_BIN="$DEFAULT_SCIP_JAVA"
GRADLE_BIN="$DEFAULT_GRADLE_BIN"
GRADLE_TASK="$DEFAULT_GRADLE_TASK"
FORCE_RESTART_PALACE_MCP="false"
DRY_RUN="false"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --host-repo-path) HOST_REPO_PATH="$2"; shift 2 ;;
        --host-repo-path=*) HOST_REPO_PATH="${1#*=}"; shift ;;
        --container-repo-path) CONTAINER_REPO_PATH="$2"; shift 2 ;;
        --container-repo-path=*) CONTAINER_REPO_PATH="${1#*=}"; shift ;;
        --extractors) EXTRACTORS_CSV="$2"; shift 2 ;;
        --extractors=*) EXTRACTORS_CSV="${1#*=}"; shift ;;
        --env-file) ENV_FILE="$2"; shift 2 ;;
        --env-file=*) ENV_FILE="${1#*=}"; shift ;;
        --mcp-url) MCP_URL="$2"; shift 2 ;;
        --mcp-url=*) MCP_URL="${1#*=}"; shift ;;
        --compose-project-name) COMPOSE_PROJECT_NAME="$2"; shift 2 ;;
        --compose-project-name=*) COMPOSE_PROJECT_NAME="${1#*=}"; shift ;;
        --compose-file) COMPOSE_FILE="$2"; shift 2 ;;
        --compose-file=*) COMPOSE_FILE="${1#*=}"; shift ;;
        --scip-java) SCIP_JAVA_BIN="$2"; shift 2 ;;
        --scip-java=*) SCIP_JAVA_BIN="${1#*=}"; shift ;;
        --gradle-bin) GRADLE_BIN="$2"; shift 2 ;;
        --gradle-bin=*) GRADLE_BIN="${1#*=}"; shift ;;
        --gradle-task) GRADLE_TASK="$2"; shift 2 ;;
        --gradle-task=*) GRADLE_TASK="${1#*=}"; shift ;;
        --force-restart-palace-mcp) FORCE_RESTART_PALACE_MCP="true"; shift ;;
        --dry-run) DRY_RUN="true"; shift ;;
        --help|-h) usage; exit 0 ;;
        --*) die "unknown option: $1" ;;
        *) SLUG="$1"; shift ;;
    esac
done

validate_slug "$SLUG"
require_command jq
require_command python3
require_command git

[[ -f "$ENV_FILE" ]] || die "env file not found: $ENV_FILE"
[[ -d "$HOST_REPO_PATH" ]] || die "repo path not found: $HOST_REPO_PATH"
[[ -f "$HOST_REPO_PATH/gradlew" ]] || die "gradlew not found in $HOST_REPO_PATH"
[[ -f "$COMPOSE_FILE" ]] || die "compose file not found: $COMPOSE_FILE"

ACTUAL_SHA="$(git -C "$HOST_REPO_PATH" rev-parse HEAD)"
[[ "$ACTUAL_SHA" == "$PINNED_SHA" ]] || \
    die "repo HEAD $ACTUAL_SHA does not match required pin $PINNED_SHA"

[[ -f "$HOST_REPO_PATH/local.properties" || -n "${ANDROID_HOME:-}" ]] || \
    die "no local.properties and ANDROID_HOME not set for $HOST_REPO_PATH"

if [[ -n "$EXTRACTORS_CSV" ]]; then
    IFS=',' read -r -a EXTRACTORS <<<"$EXTRACTORS_CSV"
else
    EXTRACTORS=("${DEFAULT_EXTRACTORS[@]}")
fi

SCIP_PATH="$CONTAINER_REPO_PATH/scip/index.scip"
PROJECT_REGISTRATION_JSON='null'
EXTRACTOR_RESULTS_JSON='[]'
ENV_CHANGED="false"
PALACE_RESTARTED="false"
SEMANTICDB_COUNT=0
SCIP_BYTES=0
DURATION_SECONDS=0
START_TS="$(date +%s)"

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

if [[ "$DRY_RUN" == "true" ]]; then
    emit_summary
    exit 0
fi

require_command docker
require_command curl
if [[ -z "${PALACE_MCP_CLI_BIN:-}" ]]; then
    require_command uv
fi
[[ -x "$SCIP_JAVA_BIN" ]] || die "scip-java not executable: $SCIP_JAVA_BIN"

GRADLE_CMD=("$GRADLE_BIN")
if [[ "$GRADLE_BIN" != /* ]]; then
    GRADLE_CMD=("$HOST_REPO_PATH/$GRADLE_BIN")
fi
[[ -x "${GRADLE_CMD[0]}" ]] || die "gradle executable not found: ${GRADLE_CMD[0]}"

init_script="$(mktemp /tmp/palace-kotlin-init.XXXXXX)"
trap 'rm -f "$init_script"' EXIT
write_gradle_init_script "$init_script"

log "compiling $SLUG with semanticdb-kotlinc $SEMANTICDB_VERSION"
rm -rf "$HOST_REPO_PATH/build/semanticdb-targetroot"
mkdir -p "$HOST_REPO_PATH/scip"
(
    cd "$HOST_REPO_PATH"
    "${GRADLE_CMD[@]}" "$GRADLE_TASK" \
        --init-script "$init_script" \
        --rerun-tasks \
        --no-daemon \
        --warning-mode=summary
)

SEMANTICDB_COUNT="$(find "$HOST_REPO_PATH/build/semanticdb-targetroot" -name '*.semanticdb' 2>/dev/null | wc -l | tr -d ' ')"
[[ "$SEMANTICDB_COUNT" -gt 0 ]] || die "no SemanticDB output produced under build/semanticdb-targetroot"

log "converting SemanticDB to SCIP"
(
    cd "$HOST_REPO_PATH"
    "$SCIP_JAVA_BIN" index-semanticdb \
        --targetroot ./build/semanticdb-targetroot \
        --output ./scip/index.scip
)
[[ -s "$HOST_REPO_PATH/scip/index.scip" ]] || die "scip/index.scip missing or empty after index-semanticdb"
SCIP_BYTES="$(wc -c < "$HOST_REPO_PATH/scip/index.scip" | tr -d ' ')"

if [[ "$merged_scip_json" != "$current_scip_json" ]]; then
    log "updating PALACE_SCIP_INDEX_PATHS in $ENV_FILE"
    update_env_json_key "$ENV_FILE" "PALACE_SCIP_INDEX_PATHS" "$merged_scip_json"
    ENV_CHANGED="true"
fi

if [[ "$ENV_CHANGED" == "true" || "$FORCE_RESTART_PALACE_MCP" == "true" ]]; then
    log "recreating palace-mcp"
    docker_compose up -d --no-deps --force-recreate palace-mcp
    PALACE_RESTARTED="true"
fi

if ! wait_for_mcp_health; then
    die "palace-mcp did not become healthy at ${MCP_URL%/mcp}/healthz"
fi

project_payload="$(jq -nc \
    --arg slug "$SLUG" \
    --arg name "$SLUG" \
    --arg language "kotlin" \
    --arg framework "android" \
    --arg repo_url "https://github.com/horizontalsystems/unstoppable-wallet-android" \
    --arg language_profile "android_kit" \
    '{slug: $slug, name: $name, language: $language, framework: $framework, repo_url: $repo_url, language_profile: $language_profile}')"
PROJECT_REGISTRATION_JSON="$(call_mcp "palace.memory.register_project" "$project_payload")" || \
    die "memory.register_project failed"

registered_extractors_json="$(call_mcp "palace.ingest.list_extractors" '{}' || true)"
registered_extractors=""
if [[ -n "$registered_extractors_json" ]] && printf '%s' "$registered_extractors_json" | jq -e '.ok == true' >/dev/null 2>&1; then
    registered_extractors="$(printf '%s' "$registered_extractors_json" | jq -r '.extractors[].name')"
fi

for extractor in "${EXTRACTORS[@]}"; do
    extractor="$(printf '%s' "$extractor" | xargs)"
    [[ -n "$extractor" ]] || continue

    if [[ -n "$registered_extractors" ]] && ! printf '%s\n' "$registered_extractors" | grep -qx "$extractor"; then
        item="$(jq -nc --arg name "$extractor" --arg status "NOT_REGISTERED" \
            '{name: $name, status: $status}')"
        EXTRACTOR_RESULTS_JSON="$(jq -nc --argjson arr "$EXTRACTOR_RESULTS_JSON" --argjson item "$item" '$arr + [$item]')"
        continue
    fi

    payload="$(jq -nc --arg name "$extractor" --arg project "$SLUG" '{name: $name, project: $project}')"
    set +e
    extractor_json="$(call_mcp "palace.ingest.run_extractor" "$payload")"
    rc=$?
    set -e

    if [[ $rc -eq 0 ]] && printf '%s' "$extractor_json" | jq -e '.ok == true' >/dev/null 2>&1; then
        item="$(jq -nc --argjson res "$extractor_json" --arg name "$extractor" \
            '$res + {name: ($res.extractor_name // $res.name // $name), status: "OK"}')"
    else
        error_code="$(printf '%s' "$extractor_json" | jq -r '.error_code // "unknown_error"' 2>/dev/null || printf 'unknown_error')"
        message="$(printf '%s' "$extractor_json" | jq -r '.message // "extractor invocation failed"' 2>/dev/null || printf 'extractor invocation failed')"
        item="$(jq -nc --arg name "$extractor" --arg status "RUN_FAILED" --arg error_code "$error_code" --arg message "$message" \
            '{name: $name, status: $status, error_code: $error_code, message: $message}')"
    fi

    EXTRACTOR_RESULTS_JSON="$(jq -nc --argjson arr "$EXTRACTOR_RESULTS_JSON" --argjson item "$item" '$arr + [$item]')"
done

DURATION_SECONDS="$(( $(date +%s) - START_TS ))"
emit_summary
