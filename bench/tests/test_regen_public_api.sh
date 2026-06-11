#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT="$REPO_ROOT/bench/regen-public-api.sh"

tmpdir="$(mktemp -d "${TMPDIR:-/tmp}/regen-public-api-test.XXXXXX")"
trap 'rm -rf "$tmpdir"' EXIT

fail() {
    printf 'FAIL: %s\n' "$*" >&2
    exit 1
}

assert_contains() {
    local file="$1"
    local needle="$2"
    grep -Fq -- "$needle" "$file" || fail "expected '$needle' in $file"
}

cat >"$tmpdir/mock-prepare.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$@" > "$MOCK_ARGS_FILE"
EOF
chmod +x "$tmpdir/mock-prepare.sh"

export PALACE_REGEN_PUBLIC_API_PREPARE_SCRIPT="$tmpdir/mock-prepare.sh"
export MOCK_ARGS_FILE="$tmpdir/args.txt"

HELP_OUT="$tmpdir/help.out"
bash "$SCRIPT" --help >"$HELP_OUT"
assert_contains "$HELP_OUT" "regen-public-api.sh <kit-slug>"
assert_contains "$HELP_OUT" "evm-kit"
assert_contains "$HELP_OUT" "/Users/Shared/Ios/Gimle-Repos/HorizontalSystems"
printf 'PASS: --help\n'

NO_ARG_OUT="$tmpdir/no-arg.out"
if bash "$SCRIPT" >"$NO_ARG_OUT" 2>&1; then
    fail "expected no-arg invocation to fail"
fi
assert_contains "$NO_ARG_OUT" "regen-public-api.sh <kit-slug>"
printf 'PASS: no-args exit\n'

bash "$SCRIPT" evm-kit --dry-run --repo-base /tmp/repos
line1="$(sed -n '1p' "$tmpdir/args.txt")"
line2="$(sed -n '2p' "$tmpdir/args.txt")"
line3="$(sed -n '3p' "$tmpdir/args.txt")"
line4="$(sed -n '4p' "$tmpdir/args.txt")"
line5="$(sed -n '5p' "$tmpdir/args.txt")"
line6="$(sed -n '6p' "$tmpdir/args.txt")"
[[ "$line1" == "--slug" ]] || fail "expected --slug passthrough"
[[ "$line2" == "evm-kit" ]] || fail "expected evm-kit slug"
[[ "$line3" == "--public-api-only" ]] || fail "expected --public-api-only passthrough"
[[ "$line4" == "--dry-run" ]] || fail "expected --dry-run passthrough"
[[ "$line5" == "--repo-base" ]] || fail "expected --repo-base passthrough"
[[ "$line6" == "/tmp/repos" ]] || fail "expected repo-base value passthrough"
printf 'PASS: forwards slug and extra args\n'

printf '\nPASS: test_regen_public_api.sh - all tests passed\n'
