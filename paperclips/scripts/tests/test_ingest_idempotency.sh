#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
INGEST_SCRIPT="$REPO_ROOT/paperclips/scripts/ingest_swift_kit.sh"
SCIP_EMIT_SCRIPT="$REPO_ROOT/paperclips/scripts/scip_emit_swift_kit.sh"

TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/gim262-ingest-test.XXXXXX")"
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

mkdir -p "$TMP_DIR/bin" "$TMP_DIR/repos-hs/TronKit.Swift/scip"
printf 'fixture-scip\n' > "$TMP_DIR/repos-hs/TronKit.Swift/scip/index.scip"
cat > "$TMP_DIR/.env" <<'EOF'
PALACE_SCIP_INDEX_PATHS={"existing":"/repos/existing/scip/index.scip"}
OTHER_VAR=1
EOF

cat > "$TMP_DIR/bin/mock-mcp-cli" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

tool=""
json='{}'
while [[ $# -gt 0 ]]; do
  case "$1" in
    tool|call|--url)
      if [[ "$1" == "--url" ]]; then
        shift 2
      else
        shift
      fi
      ;;
    --json)
      json="$2"
      shift 2
      ;;
    *)
      if [[ -z "$tool" ]]; then
        tool="$1"
      fi
      shift
      ;;
  esac
done

printf '%s\t%s\n' "$tool" "$json" >> "$MOCK_MCP_LOG"

case "$tool" in
  palace.ingest.list_extractors)
    cat <<'JSON'
{"ok":true,"extractors":[
  {"name":"symbol_index_swift","description":"swift"},
  {"name":"git_history","description":"git"},
  {"name":"dependency_surface","description":"deps"}
]}
JSON
    ;;
  palace.memory.register_project)
    cat <<'JSON'
{"slug":"tron-kit","name":"tron-kit","tags":[],"parent_mount":"hs","relative_path":"TronKit.Swift","entity_counts":{}}
JSON
    ;;
  palace.memory.register_bundle)
    echo '{"ok":true,"name":"uw-ios"}'
    ;;
  palace.memory.add_to_bundle)
    echo '{"ok":true}'
    ;;
  palace.ingest.run_extractor)
    name="$(printf '%s' "$json" | python3 -c 'import json,sys; print(json.load(sys.stdin)["name"])')"
    printf '{"ok":true,"run_id":"run-%s","extractor":"%s","project":"tron-kit","started_at":"now","finished_at":"later","duration_ms":1,"nodes_written":1,"edges_written":0,"success":true}\n' "$name" "$name"
    ;;
  palace.memory.get_project_overview)
    cat <<'JSON'
{"slug":"tron-kit","name":"tron-kit","tags":[],"entity_counts":{"IngestRun":1},"last_ingest_started_at":"now","last_ingest_finished_at":"later"}
JSON
    ;;
  *)
    echo '{"ok":false,"error_code":"unexpected_tool","message":"unexpected tool"}'
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
  printf 'mock-palace-mcp\n'
fi
exit 0
EOF
chmod +x "$TMP_DIR/bin/docker"

cat > "$TMP_DIR/bin/curl" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
exit 0
EOF
chmod +x "$TMP_DIR/bin/curl"

PATH="$TMP_DIR/bin:$PATH"
export PALACE_MCP_CLI_BIN="$TMP_DIR/bin/mock-mcp-cli"
export MOCK_MCP_LOG="$TMP_DIR/mcp.log"
export MOCK_DOCKER_LOG="$TMP_DIR/docker.log"

INVALID_OUT="$TMP_DIR/invalid.out"
if bash "$INGEST_SCRIPT" "INVALID SLUG" --dry-run --env-file "$TMP_DIR/.env" >"$INVALID_OUT" 2>&1; then
    fail "invalid slug unexpectedly succeeded"
fi
assert_contains "$INVALID_OUT" "invalid slug"

SCIP_INVALID_OUT="$TMP_DIR/scip-invalid.out"
if bash "$SCIP_EMIT_SCRIPT" --repo-root="$TMP_DIR" "INVALID SLUG" >"$SCIP_INVALID_OUT" 2>&1; then
    fail "scip_emit invalid slug unexpectedly succeeded"
fi
assert_contains "$SCIP_INVALID_OUT" "invalid slug"

MISSING_REPO_OUT="$TMP_DIR/missing-repo.out"
if bash "$INGEST_SCRIPT" "tron-kit" \
    --dry-run \
    --repo-base="$TMP_DIR/missing-base" \
    --host-repo-base="$TMP_DIR/missing-base" \
    --relative-path="TronKit.Swift" \
    --env-file="$TMP_DIR/.env" >"$MISSING_REPO_OUT" 2>&1; then
    fail "missing repo unexpectedly succeeded"
fi
assert_contains "$MISSING_REPO_OUT" "repo mount not found"

rm -f "$TMP_DIR/repos-hs/TronKit.Swift/scip/index.scip"
MISSING_SCIP_OUT="$TMP_DIR/missing-scip.out"
if bash "$INGEST_SCRIPT" "tron-kit" \
    --dry-run \
    --repo-base=/repos-hs \
    --host-repo-base="$TMP_DIR/repos-hs" \
    --relative-path="TronKit.Swift" \
    --env-file="$TMP_DIR/.env" >"$MISSING_SCIP_OUT" 2>&1; then
    fail "missing SCIP unexpectedly succeeded"
fi
assert_contains "$MISSING_SCIP_OUT" "SCIP index not found"
printf 'fixture-scip\n' > "$TMP_DIR/repos-hs/TronKit.Swift/scip/index.scip"

cp "$TMP_DIR/.env" "$TMP_DIR/.env.before-dry-run"
DRY_RUN_OUT="$TMP_DIR/dry-run.out"
bash "$INGEST_SCRIPT" "tron-kit" \
    --dry-run \
    --repo-base=/repos-hs \
    --host-repo-base="$TMP_DIR/repos-hs" \
    --parent-mount=hs \
    --relative-path="TronKit.Swift" \
    --env-file="$TMP_DIR/.env" >"$DRY_RUN_OUT"
cmp -s "$TMP_DIR/.env.before-dry-run" "$TMP_DIR/.env" || fail "dry-run mutated env file"
assert_contains "$DRY_RUN_OUT" '"status":"planned"'

RUN1_OUT="$TMP_DIR/run1.out"
bash "$INGEST_SCRIPT" "tron-kit" \
    --bundle=uw-ios \
    --repo-base=/repos-hs \
    --host-repo-base="$TMP_DIR/repos-hs" \
    --parent-mount=hs \
    --relative-path="TronKit.Swift" \
    --env-file="$TMP_DIR/.env" >"$RUN1_OUT"
assert_contains "$RUN1_OUT" '"status":"ok"'
assert_contains "$RUN1_OUT" '"reason":"not_registered"'
ENV_AFTER_RUN1="$(cat "$TMP_DIR/.env")"
PATH_JSON="$(grep '^PALACE_SCIP_INDEX_PATHS=' "$TMP_DIR/.env" | cut -d= -f2-)"
printf '%s' "$PATH_JSON" | jq -e '.existing == "/repos/existing/scip/index.scip"' >/dev/null || \
    fail "existing PALACE_SCIP_INDEX_PATHS entry was not preserved"
printf '%s' "$PATH_JSON" | jq -e '."tron-kit" == "/repos-hs/TronKit.Swift/scip/index.scip"' >/dev/null || \
    fail "tron-kit PALACE_SCIP_INDEX_PATHS entry missing"

RUN2_OUT="$TMP_DIR/run2.out"
bash "$INGEST_SCRIPT" "tron-kit" \
    --bundle=uw-ios \
    --repo-base=/repos-hs \
    --host-repo-base="$TMP_DIR/repos-hs" \
    --parent-mount=hs \
    --relative-path="TronKit.Swift" \
    --env-file="$TMP_DIR/.env" >"$RUN2_OUT"
[[ "$ENV_AFTER_RUN1" == "$(cat "$TMP_DIR/.env")" ]] || fail "second run changed env file"

RESTART_COUNT="$(grep -c 'up -d --force-recreate palace-mcp' "$MOCK_DOCKER_LOG" || true)"
[[ "$RESTART_COUNT" -eq 1 ]] || fail "expected exactly one palace-mcp restart, got $RESTART_COUNT"
assert_contains "$MOCK_DOCKER_LOG" "--env-file $TMP_DIR/.env"

printf 'PASS: ingest idempotency test suite\n'
