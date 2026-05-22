#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
INGEST_SCRIPT="$REPO_ROOT/paperclips/scripts/ingest_xcode_app.sh"

TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/gim766-ingest-xcode-test.XXXXXX")"
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

assert_exit_code() {
    local expected="$1"
    local actual="$2"
    local label="$3"
    [[ "$actual" -eq "$expected" ]] || fail "$label: expected exit $expected, got $actual"
}

# ─── fixture setup ───────────────────────────────────────────────────────────

REPO_HS="$TMP_DIR/HorizontalSystems"
REPO_PATH="$REPO_HS/unstoppable-wallet-ios"
mkdir -p "$REPO_PATH/scip"
touch "$REPO_PATH/.git"
mkdir -p "$REPO_PATH/Wallet.xcworkspace"
printf 'fixture-scip\n' > "$REPO_PATH/scip/index.scip"

cat > "$TMP_DIR/.env" <<'EOF'
PALACE_SCIP_INDEX_PATHS={"existing":"/repos/existing/scip/index.scip"}
OTHER_VAR=1
EOF

mkdir -p "$TMP_DIR/bin"

cat > "$TMP_DIR/bin/mock-mcp-cli" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

tool=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    tool|call)    shift ;;
    --url)        shift 2 ;;
    --json)       shift 2 ;;
    *)
      if [[ -z "$tool" ]]; then
        tool="$1"
      fi
      shift
      ;;
  esac
done

printf '%s\n' "$tool" >> "$MOCK_MCP_LOG"

case "$tool" in
  palace.ingest.list_extractors)
    printf '{"ok":true,"extractors":[{"name":"symbol_index_swift","description":"swift"},{"name":"git_history","description":"git"}]}\n'
    ;;
  palace.memory.register_project)
    printf '{"slug":"uw-ios-app","name":"uw-ios-app","tags":[],"parent_mount":"hs","relative_path":"unstoppable-wallet-ios","entity_counts":{}}\n'
    ;;
  palace.memory.register_bundle)
    printf '{"ok":true,"name":"uw-ios"}\n'
    ;;
  palace.memory.add_to_bundle)
    printf '{"ok":true}\n'
    ;;
  palace.ingest.run_extractor)
    printf '{"ok":true,"run_id":"run-1","extractor":"x","project":"uw-ios-app","started_at":"now","finished_at":"later","duration_ms":1,"nodes_written":1,"edges_written":0,"success":true}\n'
    ;;
  palace.memory.get_project_overview)
    printf '{"slug":"uw-ios-app","name":"uw-ios-app","tags":[],"entity_counts":{"IngestRun":1}}\n'
    ;;
  *)
    printf '{"ok":false,"error_code":"unexpected_tool","message":"unexpected tool"}\n'
    exit 1
    ;;
esac
EOF
chmod +x "$TMP_DIR/bin/mock-mcp-cli"

cat > "$TMP_DIR/bin/docker" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >> "$MOCK_DOCKER_LOG"
if [[ "$*" == *"ps -q palace-mcp"* ]]; then
    printf 'mock-palace-mcp-id\n'
fi
if [[ "$*" == *"exec mock-palace-mcp-id"* ]]; then
    exit 0
fi
exit 0
EOF
chmod +x "$TMP_DIR/bin/docker"

cat > "$TMP_DIR/bin/curl" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
chmod +x "$TMP_DIR/bin/curl"

export PATH="$TMP_DIR/bin:$PATH"
export PALACE_MCP_CLI_BIN="$TMP_DIR/bin/mock-mcp-cli"
export MOCK_MCP_LOG="$TMP_DIR/mcp.log"
export MOCK_DOCKER_LOG="$TMP_DIR/docker.log"
touch "$MOCK_MCP_LOG" "$MOCK_DOCKER_LOG"

# ─── test: --help exits 0 ────────────────────────────────────────────────────

HELP_OUT="$TMP_DIR/help.out"
bash "$INGEST_SCRIPT" --help >"$HELP_OUT"
assert_contains "$HELP_OUT" "--repo-path"
assert_contains "$HELP_OUT" "--slug"

# ─── test: missing --slug exits 2 ────────────────────────────────────────────

MISSING_SLUG_OUT="$TMP_DIR/missing-slug.out"
set +e
bash "$INGEST_SCRIPT" --repo-path "$REPO_PATH" >"$MISSING_SLUG_OUT" 2>&1
MISSING_SLUG_RC=$?
set -e
assert_exit_code 2 "$MISSING_SLUG_RC" "missing --slug"
assert_contains "$MISSING_SLUG_OUT" "--slug is required"

# ─── test: missing --repo-path exits 2 ───────────────────────────────────────

MISSING_REPO_PATH_OUT="$TMP_DIR/missing-repo-path.out"
set +e
bash "$INGEST_SCRIPT" --slug "uw-ios-app" >"$MISSING_REPO_PATH_OUT" 2>&1
MISSING_REPO_PATH_RC=$?
set -e
assert_exit_code 2 "$MISSING_REPO_PATH_RC" "missing --repo-path"
assert_contains "$MISSING_REPO_PATH_OUT" "--repo-path is required"

# ─── test: Package.swift present → error about ingest_swift_kit.sh ───────────

touch "$REPO_PATH/Package.swift"
PKG_OUT="$TMP_DIR/pkg-swift.out"
set +e
bash "$INGEST_SCRIPT" --repo-path "$REPO_PATH" --slug "uw-ios-app" \
    --dry-run --env-file "$TMP_DIR/.env" >"$PKG_OUT" 2>&1
PKG_RC=$?
set -e
[[ "$PKG_RC" -ne 0 ]] || fail "Package.swift check: expected non-zero exit"
assert_contains "$PKG_OUT" "ingest_swift_kit.sh"
rm -f "$REPO_PATH/Package.swift"

# ─── test: no xcworkspace/xcodeproj → error ───────────────────────────────────

rmdir "$REPO_PATH/Wallet.xcworkspace"
NO_XC_OUT="$TMP_DIR/no-xc.out"
set +e
bash "$INGEST_SCRIPT" --repo-path "$REPO_PATH" --slug "uw-ios-app" \
    --dry-run --env-file "$TMP_DIR/.env" >"$NO_XC_OUT" 2>&1
NO_XC_RC=$?
set -e
[[ "$NO_XC_RC" -ne 0 ]] || fail "no xcworkspace check: expected non-zero exit"
assert_contains "$NO_XC_OUT" ".xcworkspace"
mkdir -p "$REPO_PATH/Wallet.xcworkspace"

# ─── test: --dry-run with valid repo exits 0, no env mutation ────────────────

cp "$TMP_DIR/.env" "$TMP_DIR/.env.before-dry"
DRY_RUN_OUT="$TMP_DIR/dry-run.out"
bash "$INGEST_SCRIPT" \
    --repo-path "$REPO_PATH" \
    --slug "uw-ios-app" \
    --workspace "Wallet.xcworkspace" \
    --parent-mount "hs" \
    --env-file "$TMP_DIR/.env" \
    --dry-run >"$DRY_RUN_OUT"
cmp -s "$TMP_DIR/.env.before-dry" "$TMP_DIR/.env" || fail "dry-run mutated env file"
assert_contains "$DRY_RUN_OUT" '"status":"planned"'
assert_contains "$DRY_RUN_OUT" '"slug":"uw-ios-app"'
assert_contains "$DRY_RUN_OUT" '"parent_mount":"hs"'

# ─── test: --extractors CSV override passes through ──────────────────────────

EXTRACTOR_OUT="$TMP_DIR/extractor-override.out"
bash "$INGEST_SCRIPT" \
    --repo-path "$REPO_PATH" \
    --slug "uw-ios-app" \
    --workspace "Wallet.xcworkspace" \
    --parent-mount "hs" \
    --env-file "$TMP_DIR/.env" \
    --extractors "symbol_index_swift,git_history" \
    --dry-run >"$EXTRACTOR_OUT"
assert_contains "$EXTRACTOR_OUT" '"status":"planned"'

# ─── test: auto-derive parent_mount from HorizontalSystems path ──────────────

AUTO_MOUNT_OUT="$TMP_DIR/auto-mount.out"
bash "$INGEST_SCRIPT" \
    --repo-path "$REPO_PATH" \
    --slug "uw-ios-app" \
    --workspace "Wallet.xcworkspace" \
    --env-file "$TMP_DIR/.env" \
    --dry-run >"$AUTO_MOUNT_OUT"
assert_contains "$AUTO_MOUNT_OUT" '"parent_mount":"hs"'

# ─── test: invalid slug is rejected ──────────────────────────────────────────

INVALID_SLUG_OUT="$TMP_DIR/invalid-slug.out"
set +e
bash "$INGEST_SCRIPT" --repo-path "$REPO_PATH" --slug "INVALID SLUG" \
    --dry-run --env-file "$TMP_DIR/.env" >"$INVALID_SLUG_OUT" 2>&1
INVALID_SLUG_RC=$?
set -e
[[ "$INVALID_SLUG_RC" -ne 0 ]] || fail "invalid slug: expected non-zero exit"
assert_contains "$INVALID_SLUG_OUT" "invalid slug"

# ─── test: live-style run updates env and calls MCP ──────────────────────────

RUN1_OUT="$TMP_DIR/run1.out"
bash "$INGEST_SCRIPT" \
    --repo-path "$REPO_PATH" \
    --slug "uw-ios-app" \
    --workspace "Wallet.xcworkspace" \
    --parent-mount "hs" \
    --bundle "uw-ios" \
    --env-file "$TMP_DIR/.env" >"$RUN1_OUT"
assert_contains "$RUN1_OUT" '"status":"ok"'

PATH_JSON="$(grep '^PALACE_SCIP_INDEX_PATHS=' "$TMP_DIR/.env" | cut -d= -f2-)"
printf '%s' "$PATH_JSON" | jq -e '.existing == "/repos/existing/scip/index.scip"' >/dev/null || \
    fail "existing PALACE_SCIP_INDEX_PATHS entry was not preserved"
printf '%s' "$PATH_JSON" | jq -e '."uw-ios-app" == "/repos-hs/unstoppable-wallet-ios/scip/index.scip"' >/dev/null || \
    fail "uw-ios-app PALACE_SCIP_INDEX_PATHS entry missing or wrong"

assert_contains "$MOCK_MCP_LOG" "palace.memory.register_project"
assert_contains "$MOCK_MCP_LOG" "palace.memory.register_bundle"
assert_contains "$MOCK_MCP_LOG" "palace.memory.add_to_bundle"
assert_contains "$MOCK_MCP_LOG" "palace.ingest.run_extractor"

RESTART_COUNT="$(grep -c 'up -d --force-recreate palace-mcp' "$MOCK_DOCKER_LOG" || true)"
[[ "$RESTART_COUNT" -ge 1 ]] || fail "expected at least one palace-mcp restart, got $RESTART_COUNT"

# ─── test: idempotency — second run does not restart palace-mcp ──────────────

ENV_AFTER_RUN1="$(cat "$TMP_DIR/.env")"
RUN2_OUT="$TMP_DIR/run2.out"
bash "$INGEST_SCRIPT" \
    --repo-path "$REPO_PATH" \
    --slug "uw-ios-app" \
    --workspace "Wallet.xcworkspace" \
    --parent-mount "hs" \
    --env-file "$TMP_DIR/.env" >"$RUN2_OUT"
[[ "$ENV_AFTER_RUN1" == "$(cat "$TMP_DIR/.env")" ]] || fail "second run changed env file"

RESTART_COUNT2="$(grep -c 'up -d --force-recreate palace-mcp' "$MOCK_DOCKER_LOG" || true)"
[[ "$RESTART_COUNT2" -eq "$RESTART_COUNT" ]] || \
    fail "second run triggered unexpected palace-mcp restart"

printf 'PASS: ingest_xcode_app test suite\n'
