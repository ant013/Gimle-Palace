#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
SCIP_EMIT_SCRIPT="$REPO_ROOT/paperclips/scripts/scip_emit_swift_kit.sh"

TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/gim839-scip-kit-test.XXXXXX")"
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
    "$TMP_DIR/emitter" \
    "$TMP_DIR/repos/BitcoinKit.Swift"

cat > "$TMP_DIR/repos/BitcoinKit.Swift/Package.swift" <<'EOF'
// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "BitcoinKit",
    products: [],
    targets: []
)
EOF

git -C "$TMP_DIR/repos/BitcoinKit.Swift" init >/dev/null
git -C "$TMP_DIR/repos/BitcoinKit.Swift" config user.name "Test User"
git -C "$TMP_DIR/repos/BitcoinKit.Swift" config user.email "test@example.com"
git -C "$TMP_DIR/repos/BitcoinKit.Swift" add Package.swift
git -C "$TMP_DIR/repos/BitcoinKit.Swift" commit -m "test fixture" >/dev/null

cat > "$TMP_DIR/bin/xcode-select" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
printf '/Applications/Xcode.app/Contents/Developer\n'
EOF
chmod +x "$TMP_DIR/bin/xcode-select"

cat > "$TMP_DIR/bin/swift" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
exit 0
EOF
chmod +x "$TMP_DIR/bin/swift"

cat > "$TMP_DIR/bin/xcrun" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
if [[ "$1" == "swift" ]]; then
    exit 0
fi
printf 'unexpected xcrun invocation:'
printf ' %q' "$@"
printf '\n' >&2
exit 1
EOF
chmod +x "$TMP_DIR/bin/xcrun"

cat > "$TMP_DIR/bin/xcodebuild" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == "-version" ]]; then
    printf 'Xcode 26.3\nBuild version 17E300\n'
    exit 0
fi
printf '%s\n' "$*" > "$XCODEBUILD_ARGS_LOG"
exit 0
EOF
chmod +x "$TMP_DIR/bin/xcodebuild"

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
EOF
chmod +x "$TMP_DIR/emitter/mock-emitter"

export XCODEBUILD_ARGS_LOG="$TMP_DIR/xcodebuild-args.log"
PATH="$TMP_DIR/bin:$PATH"
export PATH

OUT="$TMP_DIR/script.out"
bash "$SCIP_EMIT_SCRIPT" \
    bitcoin-kit \
    --repo-path "$TMP_DIR/repos/BitcoinKit.Swift" \
    --emitter-dir "$TMP_DIR/emitter" \
    --emitter-bin "$TMP_DIR/emitter/mock-emitter" \
    --no-remote-copy >"$OUT"

assert_contains "$XCODEBUILD_ARGS_LOG" "-package-path $TMP_DIR/repos/BitcoinKit.Swift"
assert_contains "$XCODEBUILD_ARGS_LOG" "-scheme BitcoinKit"
assert_not_contains "$XCODEBUILD_ARGS_LOG" "package.xcworkspace"
assert_contains "$OUT" "destination=$TMP_DIR/repos/BitcoinKit.Swift/scip/index.scip"
assert_contains "$OUT" "remote_copy=false"
assert_contains "$TMP_DIR/repos/BitcoinKit.Swift/scip/index.scip.meta.json" '"artifact_origin": "local"'

printf 'PASS: swift kit SCIP emit uses xcodebuild package-path flow\n'
