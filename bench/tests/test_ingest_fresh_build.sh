#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$REPO_ROOT/bench/ingest-fresh-build.sh"

tmpdir=$(mktemp -d)
trap 'rm -rf "$tmpdir"' EXIT

mkdir -p "$tmpdir/bin" "$tmpdir/repo/Wallet.xcworkspace"

cat >"$tmpdir/bin/xcodebuild" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
cat "${MOCK_XCODEBUILD_LIST:?}"
EOF
chmod +x "$tmpdir/bin/xcodebuild"

PATH="$tmpdir/bin:$PATH"

assert_scheme() {
    local expected=$1
    local list_file=$2
    local actual

    export MOCK_XCODEBUILD_LIST="$list_file"
    actual=$(resolve_scheme "AUTO_UW_IOS" "$tmpdir/repo")
    if [[ "$actual" != "$expected" ]]; then
        echo "expected scheme '$expected', got '$actual'" >&2
        return 1
    fi
}

assert_resolution_failure() {
    local list_file=$1
    local actual=""

    export MOCK_XCODEBUILD_LIST="$list_file"
    if actual=$(resolve_scheme "AUTO_UW_IOS" "$tmpdir/repo" 2>"$tmpdir/error.txt"); then
        echo "expected resolver failure, got '$actual'" >&2
        return 1
    fi
    if ! grep -q "unable to resolve unstoppable-wallet-ios scheme" "$tmpdir/error.txt"; then
        echo "expected resolver error output" >&2
        return 1
    fi
}

cat >"$tmpdir/production.txt" <<'EOF'
Information about workspace "Wallet":
    Schemes:
        Production
        Development
EOF

cat >"$tmpdir/development.txt" <<'EOF'
Information about workspace "Wallet":
    Schemes:
        Development
EOF

cat >"$tmpdir/legacy.txt" <<'EOF'
Information about workspace "Wallet":
    Schemes:
        UnstoppableWallet
EOF

cat >"$tmpdir/unknown.txt" <<'EOF'
Information about workspace "Wallet":
    Schemes:
        SomeOtherScheme
EOF

assert_scheme "Production" "$tmpdir/production.txt"
assert_scheme "Development" "$tmpdir/development.txt"
assert_scheme "UnstoppableWallet" "$tmpdir/legacy.txt"
assert_resolution_failure "$tmpdir/unknown.txt"

echo "ok"
