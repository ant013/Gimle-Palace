#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
BUNDLE_SCRIPT="$REPO_ROOT/paperclips/scripts/scip_emit_uw_ios_bundle.sh"

TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/gim855-scip-bundle-test.XXXXXX")"
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

mkdir -p \
    "$TMP_DIR/repos/unstoppable-wallet-ios" \
    "$TMP_DIR/repos/EvmKit.Swift" \
    "$TMP_DIR/bin"

cat > "$TMP_DIR/manifest.json" <<'JSON'
{
  "bundle_name": "uw-ios",
  "parent_mount": "hs",
  "members": [
    {"slug": "uw-ios-app", "relative_path": "unstoppable-wallet-ios", "tier": "user"},
    {"slug": "evm-kit", "relative_path": "EvmKit.Swift", "tier": "first-party"}
  ]
}
JSON

cat > "$TMP_DIR/app-emit.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
repo_path=""
slug=""
relative_path=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --repo-path) repo_path="$2"; shift 2 ;;
        --slug) slug="$2"; shift 2 ;;
        --relative-path) relative_path="$2"; shift 2 ;;
        *) shift ;;
    esac
done
printf 'app slug=%s repo=%s relative=%s\n' "$slug" "$repo_path" "$relative_path" >> "$APP_CALL_LOG"
printf 'source=%s/scip/index.scip\n' "$repo_path"
printf 'destination=imac:%s/scip/index.scip\n' "$relative_path"
printf 'size_bytes=11\n'
EOF
chmod +x "$TMP_DIR/app-emit.sh"

cat > "$TMP_DIR/kit-emit.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
slug="$1"
shift
repo_path=""
relative_path=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --repo-path) repo_path="$2"; shift 2 ;;
        --remote-relative-path) relative_path="$2"; shift 2 ;;
        *) shift ;;
    esac
done
printf 'kit slug=%s repo=%s relative=%s\n' "$slug" "$repo_path" "$relative_path" >> "$KIT_CALL_LOG"
printf 'source=%s/scip/index.scip\n' "$repo_path"
printf 'destination=imac:%s/scip/index.scip\n' "$relative_path"
printf 'size_bytes=13\n'
EOF
chmod +x "$TMP_DIR/kit-emit.sh"

export APP_CALL_LOG="$TMP_DIR/app-calls.log"
export KIT_CALL_LOG="$TMP_DIR/kit-calls.log"

OUT="$TMP_DIR/bundle.out"
if bash "$BUNDLE_SCRIPT" \
    --scope full \
    --repo-root "$TMP_DIR/repos" \
    --manifest "$TMP_DIR/manifest.json" \
    --emit-script "$TMP_DIR/kit-emit.sh" \
    --app-emit-script "$TMP_DIR/app-emit.sh" \
    --remote-host imac \
    --remote-base /Users/Shared/Ios/HorizontalSystems >"$OUT"; then
    fail "bundle emit unexpectedly met full-scope threshold with two mocked members"
else
    [[ "$?" -eq 1 ]] || fail "bundle emit exited with unexpected status"
fi

assert_contains "$APP_CALL_LOG" "app slug=uw-ios-app"
assert_contains "$APP_CALL_LOG" "relative=unstoppable-wallet-ios"
assert_contains "$KIT_CALL_LOG" "kit slug=evm-kit"
assert_contains "$KIT_CALL_LOG" "relative=EvmKit.Swift"
assert_contains "$OUT" '"members_ok": 2'
assert_contains "$OUT" '"meets_success_threshold": false'

printf 'PASS: uw-ios bundle SCIP emit routing\n'
