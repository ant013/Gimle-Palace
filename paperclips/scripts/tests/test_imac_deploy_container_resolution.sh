#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
DEPLOY_SCRIPT="$REPO_ROOT/paperclips/scripts/imac-deploy.sh"

TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/gim328-imac-deploy.XXXXXX")"
trap 'rm -rf "$TMP_DIR"' EXIT

fail() {
    printf 'FAIL: %s\n' "$*" >&2
    exit 1
}

extract_function() {
    local name="$1"
    awk -v name="$name" '
        $0 ~ ("^" name "\\(\\) \\{") {capture=1}
        capture {
            print
            opens += gsub(/\{/, "{")
            closes += gsub(/\}/, "}")
            if (capture && opens == closes) {
                exit
            }
        }
    ' "$DEPLOY_SCRIPT"
}

mkdir -p "$TMP_DIR/bin"
cat > "$TMP_DIR/bin/docker" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >> "$MOCK_DOCKER_LOG"

if [[ "$1" == "compose" && "$2" == "--profile" && "$3" == "review" && "$4" == "ps" && "$5" == "-q" && "$6" == "neo4j" ]]; then
    count=0
    if [[ -f "$MOCK_NEO4J_PS_COUNT_FILE" ]]; then
        count="$(cat "$MOCK_NEO4J_PS_COUNT_FILE")"
    fi
    count=$((count + 1))
    printf '%s\n' "$count" > "$MOCK_NEO4J_PS_COUNT_FILE"
    case "${MOCK_SCENARIO:-steady-healthy}" in
        transient-empty)
            if [[ "$count" -eq 1 ]]; then
                exit 0
            fi
            printf 'actual-neo4j-id\n'
            exit 0
            ;;
        missing-neo4j)
            exit 0
            ;;
        *)
            printf 'actual-neo4j-id\n'
            exit 0
            ;;
    esac
fi

if [[ "$1" == "inspect" && "$2" == "--format={{.State.Health.Status}}" && "$3" == "gimle-palace-neo4j-1" ]]; then
    exit 1
fi

if [[ "$1" == "inspect" && "$2" == "--format={{.State.Health.Status}}" && "$3" == "gimle-palace-palace-mcp-1" ]]; then
    exit 1
fi

if [[ "$1" == "inspect" && "$2" == "--format={{.State.Health.Status}}" && "$3" == "actual-neo4j-id" ]]; then
    case "${MOCK_SCENARIO:-steady-healthy}" in
        missing-neo4j)
            exit 1
            ;;
        *)
            printf 'healthy\n'
            exit 0
            ;;
    esac
fi

if [[ "$1" == "compose" && "$2" == "--profile" && "$3" == "review" && "$4" == "ps" && "$5" == "-q" && "$6" == "palace-mcp" ]]; then
    printf 'actual-palace-id\n'
    exit 0
fi

if [[ "$1" == "inspect" && "$2" == "--format={{.State.Health.Status}}" && "$3" == "actual-palace-id" ]]; then
    printf 'healthy\n'
    exit 0
fi

if [[ "$1" == "exec" && "$2" == "actual-palace-id" ]]; then
    printf 'git_history\nsymbol_index_swift\n'
    exit 0
fi

printf 'unexpected docker call: %s\n' "$*" >&2
exit 1
EOF
chmod +x "$TMP_DIR/bin/docker"

FUNCTIONS_FILE="$TMP_DIR/functions.sh"
{
    extract_function "resolve_container_ref"
    printf '\n'
    extract_function "wait_healthy"
} > "$FUNCTIONS_FILE"

run_success_case() {
    local docker_log="$TMP_DIR/docker-success.log"
    local neo4j_ps_count="$TMP_DIR/neo4j-ps-count-success.txt"
    local result

    : > "$docker_log"
    rm -f "$neo4j_ps_count"

    result="$(
        PATH="$TMP_DIR/bin:$PATH" \
        COMPOSE_PROFILE="review" \
        HEALTH_POLL_MAX=2 \
        HEALTH_POLL_SLEEP=0 \
        MOCK_DOCKER_LOG="$docker_log" \
        MOCK_NEO4J_PS_COUNT_FILE="$neo4j_ps_count" \
        MOCK_SCENARIO="transient-empty" \
        PALACE_CONTAINER="gimle-palace-palace-mcp-1" \
        NEO4J_CONTAINER="gimle-palace-neo4j-1" \
        bash -c '
            set -euo pipefail
            log() { :; }
            die() { printf "%s\n" "$1" >&2; exit "${2:-1}"; }
            source "'"$FUNCTIONS_FILE"'"
            wait_healthy neo4j "$NEO4J_CONTAINER"
            wait_healthy palace-mcp "$PALACE_CONTAINER"
            palace_ref="$(resolve_container_ref palace-mcp "$PALACE_CONTAINER")"
            docker exec "$palace_ref" python3 -c "print(\"ok\")"
            printf "%s\n" "$palace_ref"
        '
    )"

    [[ "$result" == $'git_history\nsymbol_index_swift\nactual-palace-id' ]] || \
        fail "expected docker exec output plus resolved palace id, got: $result"
    [[ "$(grep -Fc 'compose --profile review ps -q neo4j' "$docker_log")" -eq 2 ]] || \
        fail "neo4j health wait did not re-resolve the container ref on later polls"
    grep -Fqx 'compose --profile review ps -q palace-mcp' "$docker_log" || \
        fail "compose ps -q palace-mcp was not used"
    grep -Fqx 'inspect --format={{.State.Health.Status}} actual-neo4j-id' "$docker_log" || \
        fail "health wait did not inspect resolved neo4j container id"
    grep -Fqx 'inspect --format={{.State.Health.Status}} actual-palace-id' "$docker_log" || \
        fail "health wait did not inspect resolved palace container id"
    grep -Fq 'exec actual-palace-id python3 -c print("ok")' "$docker_log" || \
        fail "registry verification did not exec against resolved palace container id"
    if grep -Fq 'gimle-palace-palace-mcp-1' "$docker_log"; then
        fail "legacy palace container name leaked into docker calls"
    fi
}

run_fail_closed_case() {
    local docker_log="$TMP_DIR/docker-fail.log"
    local neo4j_ps_count="$TMP_DIR/neo4j-ps-count-fail.txt"
    local stderr_file="$TMP_DIR/wait-healthy-fail.stderr"
    local status=0

    : > "$docker_log"
    : > "$stderr_file"
    rm -f "$neo4j_ps_count"

    set +e
    PATH="$TMP_DIR/bin:$PATH" \
    COMPOSE_PROFILE="review" \
    HEALTH_POLL_MAX=1 \
    HEALTH_POLL_SLEEP=0 \
    MOCK_DOCKER_LOG="$docker_log" \
    MOCK_NEO4J_PS_COUNT_FILE="$neo4j_ps_count" \
    MOCK_SCENARIO="missing-neo4j" \
    NEO4J_CONTAINER="gimle-palace-neo4j-1" \
    bash -c '
        set -euo pipefail
        log() { :; }
        die() { printf "%s\n" "$1" >&2; exit "${2:-1}"; }
        source "'"$FUNCTIONS_FILE"'"
        wait_healthy neo4j "$NEO4J_CONTAINER"
    ' >/dev/null 2>"$stderr_file"
    status=$?
    set -e

    [[ "$status" -ne 0 ]] || fail "wait_healthy unexpectedly succeeded when neo4j never appeared"
    grep -Fq 'did not become healthy within 0s' "$stderr_file" || \
        fail "wait_healthy did not fail closed with the expected timeout error"
}

run_success_case
run_fail_closed_case

printf 'PASS: imac deploy re-resolves container refs during health wait and fails closed when missing\n'
