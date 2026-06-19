#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
SCIP_EMIT_SCRIPT="$REPO_ROOT/paperclips/scripts/scip_emit_uw_ios_app.sh"

TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/gim392-scip-app-test.XXXXXX")"
trap 'rm -rf "$TMP_DIR"' EXIT

fail() {
    printf 'FAIL: %s\n' "$*" >&2
    exit 1
}

assert_contains() {
    local file="$1"
    local needle="$2"
    grep -Fq -- "$needle" "$file" || fail "expected '$needle' in $file"
}

assert_not_contains() {
    local file="$1"
    local needle="$2"
    if grep -Fq -- "$needle" "$file"; then
        fail "did not expect '$needle' in $file"
    fi
}

mkdir -p \
    "$TMP_DIR/bin" \
    "$TMP_DIR/repo/Wallet.xcworkspace" \
    "$TMP_DIR/repo/Unstoppable/Unstoppable/Configuration" \
    "$TMP_DIR/emitter"

printf 'API_HOST = example.invalid\n' \
    > "$TMP_DIR/repo/Unstoppable/Unstoppable/Configuration/Config.template.xcconfig"

cat > "$TMP_DIR/bin/xcode-select" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
printf '/Applications/Xcode.app/Contents/Developer\n'
EOF
chmod +x "$TMP_DIR/bin/xcode-select"

cat > "$TMP_DIR/bin/ssh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
exit 0
EOF
chmod +x "$TMP_DIR/bin/ssh"

cat > "$TMP_DIR/bin/scp" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
exit 0
EOF
chmod +x "$TMP_DIR/bin/scp"

cat > "$TMP_DIR/emitter/mock-emitter" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
output=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --output)
            output="$2"
            shift 2
            ;;
        *)
            shift
            ;;
    esac
done
[[ -n "$output" ]] || exit 1
printf 'mock scip\n' > "$output"
printf 'emitter-ran\n' > "${output}.marker"
EOF
chmod +x "$TMP_DIR/emitter/mock-emitter"

cat > "$TMP_DIR/bin/xcrun" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
if [[ "$1" == "-f" && "$2" == "xcodebuild" ]]; then
    printf '/Applications/Xcode.app/Contents/Developer/usr/bin/xcodebuild\n'
    exit 0
fi
if [[ "$1" != "xcodebuild" ]]; then
    exit 0
fi

derived_data=""
status="${MOCK_XCODEBUILD_STATUS:-0}"
emit_index="${MOCK_XCODEBUILD_EMIT_INDEX:-0}"
indexstore_format="${MOCK_INDEXSTORE_FORMAT:-v5}"
while [[ $# -gt 0 ]]; do
    case "$1" in
        -derivedDataPath)
            derived_data="$2"
            shift 2
            ;;
        *)
            shift
            ;;
    esac
done

if [[ "$emit_index" == "1" ]]; then
    case "$indexstore_format" in
        v5)
            mkdir -p "$derived_data/Index.noindex/DataStore/v5/units"
            printf 'unit\n' > "$derived_data/Index.noindex/DataStore/v5/units/mock-unit"
            ;;
        unidb)
            mkdir -p "$derived_data/Index.noindex/DataStore"
            printf 'db\n' > "$derived_data/Index.noindex/DataStore/index.db"
            ;;
        *)
            exit 2
            ;;
    esac
fi

exit "$status"
EOF
chmod +x "$TMP_DIR/bin/xcrun"

PATH="$TMP_DIR/bin:$PATH"
export PATH

SUCCESS_OUT="$TMP_DIR/success.out"
MOCK_XCODEBUILD_STATUS=65 \
MOCK_XCODEBUILD_EMIT_INDEX=1 \
bash "$SCIP_EMIT_SCRIPT" \
    --repo-path "$TMP_DIR/repo" \
    --derived-data "$TMP_DIR/derived-success" \
    --output "$TMP_DIR/output-success/index.scip" \
    --env-file "$TMP_DIR/.env" \
    --emitter-dir "$TMP_DIR/emitter" \
    --emitter-bin "$TMP_DIR/emitter/mock-emitter" \
    --no-remote-copy >"$SUCCESS_OUT"
assert_contains "$SUCCESS_OUT" "xcodebuild exited 65 after producing index data; continuing to SCIP emit"
assert_contains "$SUCCESS_OUT" "scip_size_bytes=10"
assert_contains "$SUCCESS_OUT" "container_scip_path=/repos-hs/unstoppable-wallet-ios/scip/index.scip"
assert_contains "$SUCCESS_OUT" "index_store_path=$TMP_DIR/derived-success/Index.noindex/DataStore"
assert_contains "$SUCCESS_OUT" "container_indexstore_path=/repos-hs/unstoppable-wallet-ios/.palace-scip-derived-data-app/Index.noindex/DataStore"
assert_contains "$SUCCESS_OUT" "index_store_format=v5"
assert_contains "$SUCCESS_OUT" "dry_run=false"
[[ -f "$TMP_DIR/output-success/index.scip.marker" ]] || fail "emitter did not run after indexed xcodebuild failure"
[[ -f "$TMP_DIR/repo/Unstoppable/Unstoppable/Configuration/Config.xcconfig" ]] || fail "Config.xcconfig was not prepared"
[[ -f "$TMP_DIR/derived-success/Index.noindex/DataStore/v5/units/mock-unit" ]] || fail "IndexStore v5 unit record was not retained"
assert_contains "$TMP_DIR/.env" 'PALACE_SCIP_INDEX_PATHS={"uw-ios-app":"/repos-hs/unstoppable-wallet-ios/scip/index.scip"}'
assert_contains "$TMP_DIR/.env" 'PALACE_INDEXSTORE_PATHS={"uw-ios-app":"/repos-hs/unstoppable-wallet-ios/.palace-scip-derived-data-app/Index.noindex/DataStore"}'

FAIL_OUT="$TMP_DIR/fail.out"
if MOCK_XCODEBUILD_STATUS=65 \
    MOCK_XCODEBUILD_EMIT_INDEX=0 \
    bash "$SCIP_EMIT_SCRIPT" \
        --repo-path "$TMP_DIR/repo" \
        --derived-data "$TMP_DIR/derived-fail" \
        --output "$TMP_DIR/output-fail/index.scip" \
        --emitter-dir "$TMP_DIR/emitter" \
        --emitter-bin "$TMP_DIR/emitter/mock-emitter" \
        --no-remote-copy >"$FAIL_OUT" 2>&1; then
    fail "xcodebuild failure without index data unexpectedly succeeded"
fi
assert_not_contains "$FAIL_OUT" "continuing to SCIP emit"
[[ ! -f "$TMP_DIR/output-fail/index.scip.marker" ]] || fail "emitter ran without index data"

UNIDB_OUT="$TMP_DIR/unidb.out"
if MOCK_XCODEBUILD_STATUS=0 \
    MOCK_XCODEBUILD_EMIT_INDEX=1 \
    MOCK_INDEXSTORE_FORMAT=unidb \
    bash "$SCIP_EMIT_SCRIPT" \
        --repo-path "$TMP_DIR/repo" \
        --derived-data "$TMP_DIR/derived-unidb" \
        --output "$TMP_DIR/output-unidb/index.scip" \
        --emitter-dir "$TMP_DIR/emitter" \
        --emitter-bin "$TMP_DIR/emitter/mock-emitter" \
        --no-remote-copy >"$UNIDB_OUT" 2>&1; then
    fail "UniDB IndexStore unexpectedly passed the v5 gate"
fi
assert_contains "$UNIDB_OUT" "UniDB format"
[[ ! -f "$TMP_DIR/output-unidb/index.scip.marker" ]] || fail "emitter ran for UniDB IndexStore"

printf 'PASS: uw-ios app SCIP emit helper\n'
