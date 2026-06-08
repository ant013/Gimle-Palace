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
    "$TMP_DIR/dev/Toolchains/swift-5.8.0-RELEASE.xctoolchain" \
    "$TMP_DIR/dev/Toolchains/swift-5.8.1-RELEASE.xctoolchain" \
    "$TMP_DIR/emitter" \
    "$TMP_DIR/repos/BitcoinKit.Swift" \
    "$TMP_DIR/repos/MissingToolchainKit.Swift" \
    "$TMP_DIR/repos/TronKit.Swift"

cat > "$TMP_DIR/repos/BitcoinKit.Swift/Package.swift" <<'EOF'
// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "BitcoinKit",
    products: [],
    targets: []
)
EOF

cat > "$TMP_DIR/repos/MissingToolchainKit.Swift/Package.swift" <<'EOF'
// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "MissingToolchainKit",
    products: [],
    targets: []
)
EOF

cat > "$TMP_DIR/repos/TronKit.Swift/Package.swift" <<'EOF'
// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "TronKit",
    products: [],
    targets: []
)
EOF

printf '5.8\n' > "$TMP_DIR/tron.swift-version"
ln -s "$TMP_DIR/tron.swift-version" "$TMP_DIR/repos/TronKit.Swift/.swift-version"
printf '5.7.1\n' > "$TMP_DIR/repos/MissingToolchainKit.Swift/.swift-version"

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
if [[ "$*" == *"-list -json"* && "$PWD" == *"/TronKit.Swift" ]]; then
    printf 'xcodebuild: error: scheme probe failed\n' >&2
    exit 1
fi
for arg in "$@"; do
    if [[ "$arg" == "-package-path" ]]; then
        printf 'unexpected xcodebuild invocation:'
        printf ' %q' "$@"
        printf '\n' >&2
        exit 1
    fi
done
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

TRON_SCHEME_ONLY_OUT="$TMP_DIR/tron-scheme-only.out"
DEVELOPER_DIR="$TMP_DIR/dev" bash "$SCIP_EMIT_SCRIPT" \
    tron-kit \
    --scheme-only-check \
    --repo-path "$TMP_DIR/repos/TronKit.Swift" \
    --remote-relative-path TronKit.Swift \
    --emitter-dir "$TMP_DIR/emitter" >"$TRON_SCHEME_ONLY_OUT"
assert_contains "$TRON_SCHEME_ONLY_OUT" "slug=tron-kit"
assert_contains "$TRON_SCHEME_ONLY_OUT" "scheme=TronKit"
assert_contains "$TRON_SCHEME_ONLY_OUT" "toolchain=swift-5.8.1-RELEASE"

TRON_SCHEME_EXPLICIT_OUT="$TMP_DIR/tron-scheme-explicit.out"
DEVELOPER_DIR="$TMP_DIR/dev" bash "$SCIP_EMIT_SCRIPT" \
    tron-kit \
    --scheme TronKit \
    --scheme-only-check \
    --repo-path "$TMP_DIR/repos/TronKit.Swift" \
    --remote-relative-path TronKit.Swift \
    --emitter-dir "$TMP_DIR/emitter" >"$TRON_SCHEME_EXPLICIT_OUT"
assert_contains "$TRON_SCHEME_EXPLICIT_OUT" "scheme=TronKit"
assert_contains "$TRON_SCHEME_EXPLICIT_OUT" "toolchain=swift-5.8.1-RELEASE"

MISSING_TOOLCHAIN_OUT="$TMP_DIR/missing-toolchain.out"
if DEVELOPER_DIR="$TMP_DIR/dev" bash "$SCIP_EMIT_SCRIPT" \
    missing-toolchain-kit \
    --scheme-only-check \
    --repo-path "$TMP_DIR/repos/MissingToolchainKit.Swift" \
    --remote-relative-path MissingToolchainKit.Swift \
    --emitter-dir "$TMP_DIR/emitter" >"$MISSING_TOOLCHAIN_OUT" 2>&1; then
    fail "missing toolchain unexpectedly succeeded"
fi
assert_contains "$MISSING_TOOLCHAIN_OUT" "ERROR: toolchain not installed: swift-5.7.1-RELEASE"

OUT="$TMP_DIR/script.out"
bash "$SCIP_EMIT_SCRIPT" \
    bitcoin-kit \
    --repo-path "$TMP_DIR/repos/BitcoinKit.Swift" \
    --emitter-dir "$TMP_DIR/emitter" \
    --emitter-bin "$TMP_DIR/emitter/mock-emitter" \
    --no-remote-copy >"$OUT"

assert_contains "$XCODEBUILD_ARGS_LOG" "-scheme BitcoinKit"
assert_not_contains "$XCODEBUILD_ARGS_LOG" "package.xcworkspace"
assert_contains "$OUT" "destination=$TMP_DIR/repos/BitcoinKit.Swift/scip/index.scip"
assert_contains "$OUT" "remote_copy=false"
assert_contains "$TMP_DIR/repos/BitcoinKit.Swift/scip/index.scip.meta.json" '"artifact_origin": "local"'

printf 'PASS: swift kit SCIP emit builds from the package root without xcodebuild package-path\n'
