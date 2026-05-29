#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
SOURCE_SCRIPT="$REPO_ROOT/paperclips/scripts/palace_ingest.sh"

TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/gim1061-palace-ingest.XXXXXX")"
trap 'rm -rf "$TMP_DIR"' EXIT

fail() {
    printf 'FAIL: %s\n' "$*" >&2
    exit 1
}

assert_exists() {
    local path="$1"
    [[ -e "$path" ]] || fail "expected path to exist: $path"
}

assert_missing() {
    local path="$1"
    [[ ! -e "$path" ]] || fail "expected path to be removed: $path"
}

assert_contains() {
    local file="$1"
    local needle="$2"
    grep -Fq -- "$needle" "$file" || fail "expected '$needle' in $file"
}

TEST_REPO="$TMP_DIR/repo"
LOCAL_BASE="$TMP_DIR/local"
LOCAL_REPO="$LOCAL_BASE/TronKit.Swift"

mkdir -p "$TEST_REPO/paperclips/scripts" "$TMP_DIR/bin" "$LOCAL_REPO/.git"
cp "$SOURCE_SCRIPT" "$TEST_REPO/paperclips/scripts/palace_ingest.sh"

cat > "$TEST_REPO/paperclips/scripts/scip_emit_swift_kit.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

repo_path=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --repo-path)
            repo_path="$2"
            shift 2
            ;;
        *)
            shift
            ;;
    esac
done

[[ -n "$repo_path" ]] || exit 1
mkdir -p "$repo_path/.palace-scip-build" "$repo_path/.palace-scip-derived-data"
printf 'fixture\n' > "$repo_path/.palace-scip-build/marker.txt"
printf 'fixture\n' > "$repo_path/.palace-scip-derived-data/marker.txt"
EOF
chmod +x "$TEST_REPO/paperclips/scripts/scip_emit_swift_kit.sh"

cat > "$TMP_DIR/bin/ssh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

printf '%s\n' "$*" >> "$MOCK_SSH_LOG"
command="${*: -1}"

case "$command" in
    *prepare_repo.sh*)
        cat <<'JSON'
{"slug":"tron-kit","repo_name":"TronKit.Swift","clone_url":"https://github.com/example/TronKit.Swift.git"}
JSON
        ;;
    *ingest_swift_kit.sh*)
        exit 0
        ;;
    *)
        exit 1
        ;;
esac
EOF
chmod +x "$TMP_DIR/bin/ssh"

export MOCK_SSH_LOG="$TMP_DIR/ssh.log"
export PALACE_LOCAL_REPO_BASE="$LOCAL_BASE"
PATH="$TMP_DIR/bin:$PATH"

RUN1_OUT="$TMP_DIR/run-default.out"
bash "$TEST_REPO/paperclips/scripts/palace_ingest.sh" --slug tron-kit >"$RUN1_OUT" 2>&1
assert_missing "$LOCAL_REPO/.palace-scip-build"
assert_missing "$LOCAL_REPO/.palace-scip-derived-data"
assert_contains "$RUN1_OUT" "cleaning local build artifacts"

RUN2_OUT="$TMP_DIR/run-keep-build.out"
bash "$TEST_REPO/paperclips/scripts/palace_ingest.sh" --slug tron-kit --keep-build >"$RUN2_OUT" 2>&1
assert_exists "$LOCAL_REPO/.palace-scip-build"
assert_exists "$LOCAL_REPO/.palace-scip-derived-data"
assert_contains "$RUN2_OUT" "keeping local build artifacts"
