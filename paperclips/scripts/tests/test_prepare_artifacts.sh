#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
PREPARE_SCRIPT="$REPO_ROOT/paperclips/scripts/prepare_swift_kit_artifacts.sh"
INGEST_SCRIPT="$REPO_ROOT/paperclips/scripts/ingest_swift_kit.sh"

TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/gim757-prepare-test.XXXXXX")"
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
        fail "unexpected '$needle' in $file"
    fi
}

# ── Fixtures ──────────────────────────────────────────────────────────────────

make_repo() {
    local repo="$1"
    mkdir -p "$repo"
    printf '// swift-tools-version:5.5\nimport PackageDescription\nlet package = Package(name: "TestKit")\n' \
        > "$repo/Package.swift"
}

make_periphery_artefacts() {
    local repo="$1"
    local schema_version="${2:-periphery-json-3.7.4}"
    mkdir -p "$repo/periphery"
    printf '[]' > "$repo/periphery/periphery-3.7.4-swiftpm.json"
    printf '{"tool_output_schema_version":"%s"}\n' "$schema_version" \
        > "$repo/periphery/contract.json"
}

make_swiftinterface() {
    local repo="$1"
    mkdir -p "$repo/.palace/public-api/swift"
    printf '// swift-interface-format-version: 1.0\n' \
        > "$repo/.palace/public-api/swift/TestKit.swiftinterface"
}

make_full_artefacts() {
    local repo="$1"
    make_periphery_artefacts "$1"
    make_swiftinterface "$1"
}

mtime() {
    python3 -c 'import os, sys; print(int(os.stat(sys.argv[1]).st_mtime))' "$1"
}

# ── Mock periphery binary ─────────────────────────────────────────────────────

mkdir -p "$TMP_DIR/bin"
cat > "$TMP_DIR/bin/periphery" <<'MOCK'
#!/usr/bin/env bash
case "${1:-}" in
    version|--version)
        printf '3.9.0\n'
        ;;
    scan)
        printf '[]\n'
        ;;
esac
MOCK
chmod +x "$TMP_DIR/bin/periphery"

cat > "$TMP_DIR/bin/xcrun" <<'MOCK'
#!/usr/bin/env bash
# Mock xcrun swift build — create a fake .swiftinterface in build path
shift  # remove 'swift'
shift  # remove 'build'
build_path="${TMPDIR:-/tmp}/mock-build"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --build-path) build_path="$2"; shift 2 ;;
        *) shift ;;
    esac
done
mkdir -p "$build_path/release/TestKit.build"
printf '// swift-interface-format-version: 1.0\n' \
    > "$build_path/release/TestKit.build/TestKit.swiftinterface"
MOCK
chmod +x "$TMP_DIR/bin/xcrun"

PATH="$TMP_DIR/bin:$PATH"
export PATH

# ── Test 1: --help exits 0 and prints usage ───────────────────────────────────

HELP_OUT="$TMP_DIR/help.out"
bash "$PREPARE_SCRIPT" --help > "$HELP_OUT"
assert_contains "$HELP_OUT" "prepare_swift_kit_artifacts.sh"
assert_contains "$HELP_OUT" "--dry-run"
assert_contains "$HELP_OUT" "periphery"
printf 'PASS: --help\n'

# ── Test 2: requires --slug or --repo-path ────────────────────────────────────

NO_ARG_OUT="$TMP_DIR/no-arg.out"
if bash "$PREPARE_SCRIPT" >"$NO_ARG_OUT" 2>&1; then
    fail "expected failure with no args"
fi
assert_contains "$NO_ARG_OUT" "prepare_swift_kit_artifacts.sh"
printf 'PASS: no-args exit\n'

# ── Test 3: --dry-run does not mutate repo ────────────────────────────────────

REPO_DRY="$TMP_DIR/repo-dry"
make_repo "$REPO_DRY"

DRY_OUT="$TMP_DIR/dry.out"
bash "$PREPARE_SCRIPT" --repo-path "$REPO_DRY" --dry-run > "$DRY_OUT" 2>&1
assert_contains "$DRY_OUT" "DRY-RUN"
[[ ! -f "$REPO_DRY/periphery/periphery-3.7.4-swiftpm.json" ]] || \
    fail "dry-run must not write periphery report"
[[ ! -f "$REPO_DRY/periphery/contract.json" ]] || \
    fail "dry-run must not write contract.json"
printf 'PASS: dry-run no mutation\n'

# ── Test 4: full run writes all artefacts ─────────────────────────────────────

REPO_FULL="$TMP_DIR/repo-full"
make_repo "$REPO_FULL"

FULL_OUT="$TMP_DIR/full.out"
bash "$PREPARE_SCRIPT" --repo-path "$REPO_FULL" > "$FULL_OUT" 2>&1

[[ -f "$REPO_FULL/periphery/periphery-3.7.4-swiftpm.json" ]] || \
    fail "periphery report not written"
[[ -f "$REPO_FULL/periphery/contract.json" ]] || \
    fail "contract.json not written"

schema="$(python3 -c "import json,sys; d=json.load(open('$REPO_FULL/periphery/contract.json')); print(d['tool_output_schema_version'])")"
[[ "$schema" =~ ^periphery-json-[0-9]+\.[0-9]+\.[0-9]+$ ]] || \
    fail "contract.json schema_version '$schema' invalid format"

iface_count="$(find "$REPO_FULL/.palace/public-api/swift" -name "*.swiftinterface" -maxdepth 1 | wc -l | tr -d ' ')"
[[ "$iface_count" -gt 0 ]] || fail "no .swiftinterface files emitted"
printf 'PASS: full run writes artefacts\n'

# ── Test 5: idempotency — second run overwrites cleanly ───────────────────────

REPO_IDEM="$TMP_DIR/repo-idem"
make_repo "$REPO_IDEM"

bash "$PREPARE_SCRIPT" --repo-path "$REPO_IDEM" > /dev/null 2>&1
first_mtime="$(mtime "$REPO_IDEM/periphery/contract.json")"
sleep 1
bash "$PREPARE_SCRIPT" --repo-path "$REPO_IDEM" > /dev/null 2>&1
second_mtime="$(mtime "$REPO_IDEM/periphery/contract.json")"
[[ "$second_mtime" -ge "$first_mtime" ]] || fail "second run did not overwrite contract.json"
printf 'PASS: idempotency\n'

# ── Test 6: ingest gate — missing artefacts rejected ─────────────────────────

mkdir -p "$TMP_DIR/repo-gate/scip"
make_repo "$TMP_DIR/repo-gate"
printf 'fake-scip' > "$TMP_DIR/repo-gate/scip/index.scip"

cat > "$TMP_DIR/gate.env" <<'EOF'
PALACE_SCIP_INDEX_PATHS={}
EOF

GATE_OUT="$TMP_DIR/gate.out"
if bash "$INGEST_SCRIPT" "test-kit" \
    --dry-run \
    --host-repo-base="$TMP_DIR" \
    --relative-path="repo-gate" \
    --env-file="$TMP_DIR/gate.env" >"$GATE_OUT" 2>&1; then
    fail "ingest should fail when artefacts are missing"
fi
assert_contains "$GATE_OUT" "artefact missing"
assert_contains "$GATE_OUT" "prepare_swift_kit_artifacts.sh"
printf 'PASS: ingest gate rejects missing artefacts\n'

# ── Test 7: ingest gate — stale/malformed schema version rejected ─────────────

mkdir -p "$TMP_DIR/repo-stale/scip"
make_repo "$TMP_DIR/repo-stale"
printf 'fake-scip' > "$TMP_DIR/repo-stale/scip/index.scip"
make_periphery_artefacts "$TMP_DIR/repo-stale" "bad-schema-version"
make_swiftinterface "$TMP_DIR/repo-stale"

STALE_OUT="$TMP_DIR/stale.out"
if bash "$INGEST_SCRIPT" "test-kit" \
    --dry-run \
    --host-repo-base="$TMP_DIR" \
    --relative-path="repo-stale" \
    --env-file="$TMP_DIR/gate.env" >"$STALE_OUT" 2>&1; then
    fail "ingest should fail on malformed schema_version"
fi
assert_contains "$STALE_OUT" "bad-schema-version"
printf 'PASS: stale artefact (malformed schema_version) rejected\n'

# ── Test 8: ingest gate — integer schema version rejected (AD-5) ──────────────

mkdir -p "$TMP_DIR/repo-int/scip"
make_repo "$TMP_DIR/repo-int"
printf 'fake-scip' > "$TMP_DIR/repo-int/scip/index.scip"
# Simulate the old integer format that triggered AD-5
mkdir -p "$TMP_DIR/repo-int/periphery"
printf '[]' > "$TMP_DIR/repo-int/periphery/periphery-3.7.4-swiftpm.json"
printf '{"tool_output_schema_version":2}' > "$TMP_DIR/repo-int/periphery/contract.json"
make_swiftinterface "$TMP_DIR/repo-int"

INT_OUT="$TMP_DIR/int.out"
if bash "$INGEST_SCRIPT" "test-kit" \
    --dry-run \
    --host-repo-base="$TMP_DIR" \
    --relative-path="repo-int" \
    --env-file="$TMP_DIR/gate.env" >"$INT_OUT" 2>&1; then
    fail "ingest should fail when schema_version is an integer (not periphery-json-X.Y.Z)"
fi
assert_contains "$INT_OUT" "not valid"
printf 'PASS: integer schema_version (AD-5 regression) rejected\n'

# ── Test 9: --skip-artefact-check bypasses gate ───────────────────────────────

mkdir -p "$TMP_DIR/repo-skip/scip"
make_repo "$TMP_DIR/repo-skip"
printf 'fake-scip' > "$TMP_DIR/repo-skip/scip/index.scip"

cat > "$TMP_DIR/skip.env" <<'EOF'
PALACE_SCIP_INDEX_PATHS={}
EOF

SKIP_OUT="$TMP_DIR/skip.out"
bash "$INGEST_SCRIPT" "test-kit" \
    --dry-run \
    --skip-artefact-check \
    --host-repo-base="$TMP_DIR" \
    --relative-path="repo-skip" \
    --env-file="$TMP_DIR/skip.env" >"$SKIP_OUT" 2>&1
assert_contains "$SKIP_OUT" '"status":"planned"'
assert_not_contains "$SKIP_OUT" "artefact missing"
printf 'PASS: --skip-artefact-check bypasses gate\n'

# ── Test 10: ingest gate passes with valid artefacts ─────────────────────────

mkdir -p "$TMP_DIR/repo-ok/scip"
make_repo "$TMP_DIR/repo-ok"
printf 'fake-scip' > "$TMP_DIR/repo-ok/scip/index.scip"
make_full_artefacts "$TMP_DIR/repo-ok"

cat > "$TMP_DIR/ok.env" <<'EOF'
PALACE_SCIP_INDEX_PATHS={}
EOF

OK_OUT="$TMP_DIR/ok.out"
bash "$INGEST_SCRIPT" "test-kit" \
    --dry-run \
    --host-repo-base="$TMP_DIR" \
    --relative-path="repo-ok" \
    --env-file="$TMP_DIR/ok.env" >"$OK_OUT" 2>&1
assert_contains "$OK_OUT" '"status":"planned"'
assert_contains "$OK_OUT" "artefact gate passed"
printf 'PASS: ingest gate passes with valid artefacts\n'

printf '\nPASS: test_prepare_artifacts.sh — all tests passed\n'
