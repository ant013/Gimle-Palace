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

config_dir="$tmpdir/repo/Unstoppable/Unstoppable/Configuration"
template_path="$config_dir/Config.template.xcconfig"
config_path="$config_dir/Config.xcconfig"
mkdir -p "$config_dir"

assert_prepare_copies_template() {
    rm -f "$config_path"
    printf 'FROM_TEMPLATE=1\n' >"$template_path"

    prepare_uw_ios_config "$tmpdir/repo" >"$tmpdir/prepare.out"

    if [[ "$(cat "$config_path")" != "FROM_TEMPLATE=1" ]]; then
        echo "expected Config.xcconfig to be copied from template" >&2
        return 1
    fi
    if ! grep -q "\[prepare\] copied Unstoppable/Unstoppable/Configuration/Config.template.xcconfig -> Config.xcconfig" "$tmpdir/prepare.out"; then
        echo "expected prepare log output" >&2
        return 1
    fi
}

assert_prepare_keeps_existing_config() {
    printf 'FROM_TEMPLATE=2\n' >"$template_path"
    printf 'KEEP_ME=1\n' >"$config_path"

    prepare_uw_ios_config "$tmpdir/repo" >"$tmpdir/prepare.out"

    if [[ "$(cat "$config_path")" != "KEEP_ME=1" ]]; then
        echo "expected existing Config.xcconfig to be preserved" >&2
        return 1
    fi
    if [[ -s "$tmpdir/prepare.out" ]]; then
        echo "did not expect prepare log output when Config.xcconfig already exists" >&2
        return 1
    fi
}

assert_prepare_fails_without_template() {
    rm -f "$template_path" "$config_path"

    if prepare_uw_ios_config "$tmpdir/repo" >"$tmpdir/prepare.out" 2>"$tmpdir/prepare.err"; then
        echo "expected prepare_uw_ios_config to fail without template" >&2
        return 1
    fi
    if ! grep -q "missing unstoppable-wallet-ios config template" "$tmpdir/prepare.err"; then
        echo "expected missing template error output" >&2
        return 1
    fi
    if ! grep -q "Unstoppable/Unstoppable/Configuration/Config.template.xcconfig" "$tmpdir/prepare.err"; then
        echo "expected missing template path in error output" >&2
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
assert_prepare_copies_template
assert_prepare_keeps_existing_config
assert_prepare_fails_without_template

echo "ok"
