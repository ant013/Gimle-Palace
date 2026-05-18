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
    printf 'actual-neo4j-id\n'
    exit 0
fi

if [[ "$1" == "compose" && "$2" == "--profile" && "$3" == "review" && "$4" == "ps" && "$5" == "-q" && "$6" == "palace-mcp" ]]; then
    printf 'actual-palace-id\n'
    exit 0
fi

if [[ "$1" == "inspect" && "$2" == "--format={{.State.Health.Status}}" && "$3" == "actual-neo4j-id" ]]; then
    printf 'healthy\n'
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

MOCK_DOCKER_LOG="$TMP_DIR/docker.log"
export MOCK_DOCKER_LOG

RESULT="$(
    PATH="$TMP_DIR/bin:$PATH" \
    COMPOSE_PROFILE="review" \
    HEALTH_POLL_MAX=1 \
    HEALTH_POLL_SLEEP=0 \
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

[[ "$RESULT" == $'git_history\nsymbol_index_swift\nactual-palace-id' ]] || \
    fail "expected docker exec output plus resolved palace id, got: $RESULT"
grep -Fqx 'compose --profile review ps -q neo4j' "$MOCK_DOCKER_LOG" || \
    fail "compose ps -q neo4j was not used"
grep -Fqx 'compose --profile review ps -q palace-mcp' "$MOCK_DOCKER_LOG" || \
    fail "compose ps -q palace-mcp was not used"
grep -Fqx 'inspect --format={{.State.Health.Status}} actual-neo4j-id' "$MOCK_DOCKER_LOG" || \
    fail "health wait did not inspect resolved neo4j container id"
grep -Fqx 'inspect --format={{.State.Health.Status}} actual-palace-id' "$MOCK_DOCKER_LOG" || \
    fail "health wait did not inspect resolved palace container id"
grep -Fq 'exec actual-palace-id python3 -c print("ok")' "$MOCK_DOCKER_LOG" || \
    fail "registry verification did not exec against resolved palace container id"
if grep -Fq 'gimle-palace-neo4j-1' "$MOCK_DOCKER_LOG"; then
    fail "legacy neo4j container name leaked into docker calls"
fi
if grep -Fq 'gimle-palace-palace-mcp-1' "$MOCK_DOCKER_LOG"; then
    fail "legacy palace container name leaked into docker calls"
fi

printf 'PASS: imac deploy resolves live compose container ids for health wait and registry verify\n'
