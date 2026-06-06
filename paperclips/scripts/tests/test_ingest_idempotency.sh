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
    "$TMP_DIR/dev/Toolchains/swift-5.9.0-RELEASE.xctoolchain" \
    "$TMP_DIR/emitter" \
    "$TMP_DIR/repos-hs/HDWalletKit.Swift/.swiftpm/xcode/package.xcworkspace" \
    "$TMP_DIR/repos-hs/HsExtensions/scip" \
    "$TMP_DIR/repos-hs/HsExtensions.Swift/scip" \
    "$TMP_DIR/repos-hs/HsCryptoKit.Swift/.swiftpm/xcode/package.xcworkspace/xcshareddata/xcschemes" \
    "$TMP_DIR/repos-hs/MarketKit.Swift/iOS Example/iOS Example.xcodeproj/xcshareddata/xcschemes" \
    "$TMP_DIR/repos-hs/MarketKit.Swift/iOS Example/iOS Example.xcworkspace" \
    "$TMP_DIR/repos-hs/MissingToolchainKit.Swift/scip" \
    "$TMP_DIR/repos-hs/TronKit.Swift/scip" \
    "$TMP_DIR/repos-hs/BitcoinKit.Swift/scip"
printf 'fixture-scip\n' > "$TMP_DIR/repos-hs/HsExtensions/scip/index.scip"
printf 'fixture-scip\n' > "$TMP_DIR/repos-hs/HsExtensions.Swift/scip/index.scip"
printf 'fixture-scip\n' > "$TMP_DIR/repos-hs/TronKit.Swift/scip/index.scip"
printf 'fixture-scip\n' > "$TMP_DIR/repos-hs/BitcoinKit.Swift/scip/index.scip"
cat > "$TMP_DIR/repos-hs/HsExtensions.Swift/Package.swift" <<'EOF'
// fixture
EOF
cat > "$TMP_DIR/repos-hs/TronKit.Swift/Package.swift" <<'EOF'
// fixture
EOF
printf '5.8\n' > "$TMP_DIR/tron.swift-version"
ln -s "$TMP_DIR/tron.swift-version" "$TMP_DIR/repos-hs/TronKit.Swift/.swift-version"
cat > "$TMP_DIR/repos-hs/BitcoinKit.Swift/Package.swift" <<'EOF'
// fixture
EOF
cat > "$TMP_DIR/repos-hs/MissingToolchainKit.Swift/Package.swift" <<'EOF'
// fixture
EOF
printf '5.7.1\n' > "$TMP_DIR/repos-hs/MissingToolchainKit.Swift/.swift-version"
cat > "$TMP_DIR/repos-hs/HsCryptoKit.Swift/Package.swift" <<'EOF'
// fixture
EOF
cat > "$TMP_DIR/repos-hs/HDWalletKit.Swift/Package.swift" <<'EOF'
// fixture
EOF
cat > "$TMP_DIR/repos-hs/MarketKit.Swift/Package.swift" <<'EOF'
// fixture
EOF
cat > "$TMP_DIR/repos-hs/MarketKit.Swift/iOS Example/iOS Example.xcodeproj/xcshareddata/xcschemes/iOS Example.xcscheme" <<'EOF'
<Scheme/>
EOF
cat > "$TMP_DIR/repos-hs/HsCryptoKit.Swift/.swiftpm/xcode/package.xcworkspace/xcshareddata/xcschemes/HsCryptoKit.Swift.xcscheme" <<'EOF'
<Scheme/>
EOF
cat > "$TMP_DIR/repos-hs/HsCryptoKit.Swift/.swiftpm/xcode/package.xcworkspace/xcshareddata/xcschemes/HsCryptoKitTests.xcscheme" <<'EOF'
<Scheme/>
EOF
ln -s HsCryptoKit.Swift "$TMP_DIR/repos-hs/hs-crypto-kit"
ln -s HDWalletKit.Swift "$TMP_DIR/repos-hs/hd-wallet-kit"
cat > "$TMP_DIR/.env" <<'EOF'
PALACE_SCIP_INDEX_PATHS={"existing":"/repos/existing/scip/index.scip"}
PALACE_SCIP_INDEX_PATHS={"legacy":"/repos/legacy/scip/index.scip"}
OTHER_VAR=1
EOF
cat > "$TMP_DIR/hs-extensions-manifest.json" <<'EOF'
{
  "members": [
    {
      "slug": "hs-extensions",
      "relative_path": "HsExtensions"
    }
  ]
}
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
    symbol_count="${MOCK_SYMBOL_COUNT:-1}"
    printf '{"slug":"tron-kit","name":"tron-kit","tags":[],"entity_counts":{"IngestRun":1,"Symbol":%s},"last_ingest_started_at":"now","last_ingest_finished_at":"later"}\n' "$symbol_count"
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

cat > "$TMP_DIR/bin/git" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

if [[ "$#" -ge 5 && "$1" == "-C" && "$3" == "remote" && "$4" == "get-url" && "$5" == "origin" ]]; then
    case "$2" in
        */TronKit.Swift)
            printf '%s\n' 'https://github.com/example/TronKit.Swift.git'
            exit 0
            ;;
        */BitcoinKit.Swift)
            printf '%s\n' 'https://github.com/example/BitcoinKit.Swift.git'
            exit 0
            ;;
    esac
fi

exit 1
EOF
chmod +x "$TMP_DIR/bin/git"

for cmd in scp ssh swift xcrun; do
    cat > "$TMP_DIR/bin/$cmd" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
exit 0
EOF
    chmod +x "$TMP_DIR/bin/$cmd"
done
cat > "$TMP_DIR/bin/xcodebuild" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

if [[ "$1" == "-version" ]]; then
    printf 'Xcode 16.0\nBuild version 16A242d\n'
    exit 0
fi

if [[ "$*" == *"-list -json"* && "$*" == *"HDWalletKit.Swift"* ]]; then
    cat <<'JSON'
{"workspace":{"schemes":["HdWalletKit"]}}
JSON
    exit 0
fi

if [[ "$*" == *"-list -json"* && "$*" == *"TronKit.Swift"* ]]; then
    printf 'xcodebuild: error: scheme discovery failed\n' >&2
    exit 1
fi
EOF
chmod +x "$TMP_DIR/bin/xcodebuild"

PATH="$TMP_DIR/bin:$PATH"
export PALACE_MCP_CLI_BIN="$TMP_DIR/bin/mock-mcp-cli"
export MOCK_MCP_LOG="$TMP_DIR/mcp.log"
export MOCK_DOCKER_LOG="$TMP_DIR/docker.log"

INVALID_OUT="$TMP_DIR/invalid.out"
if bash "$INGEST_SCRIPT" "INVALID SLUG" --dry-run --env-file "$TMP_DIR/.env" >"$INVALID_OUT" 2>&1; then
    fail "invalid slug unexpectedly succeeded"
fi
assert_contains "$INVALID_OUT" "invalid slug"

HELP_OUT="$TMP_DIR/help.out"
bash "$INGEST_SCRIPT" --help >"$HELP_OUT"
assert_contains "$HELP_OUT" "--auto-resolve-by-convention"

SCIP_INVALID_OUT="$TMP_DIR/scip-invalid.out"
if bash "$SCIP_EMIT_SCRIPT" --repo-root="$TMP_DIR" "INVALID SLUG" >"$SCIP_INVALID_OUT" 2>&1; then
    fail "scip_emit invalid slug unexpectedly succeeded"
fi
assert_contains "$SCIP_INVALID_OUT" "invalid slug"

SCIP_DRY_RUN_OUT="$TMP_DIR/scip-dry-run.out"
DEVELOPER_DIR="$TMP_DIR/dev" bash "$SCIP_EMIT_SCRIPT" "tron-kit" \
    --dry-run \
    --repo-path "$TMP_DIR/repos-hs/TronKit.Swift" \
    --remote-relative-path "TronKit.Swift" \
    --emitter-dir "$TMP_DIR/emitter" >"$SCIP_DRY_RUN_OUT"
assert_contains "$SCIP_DRY_RUN_OUT" "DRY-RUN: xcodebuild"
assert_contains "$SCIP_DRY_RUN_OUT" "-scheme"
assert_contains "$SCIP_DRY_RUN_OUT" "TronKit"
assert_contains "$SCIP_DRY_RUN_OUT" "-toolchain"
assert_contains "$SCIP_DRY_RUN_OUT" "swift-5.8.1-RELEASE"
assert_contains "$SCIP_DRY_RUN_OUT" "-derivedDataPath"
assert_contains "$SCIP_DRY_RUN_OUT" "generic/platform=iOS\\ Simulator"
assert_contains "$SCIP_DRY_RUN_OUT" "--derived-data"
assert_not_contains "$SCIP_DRY_RUN_OUT" "xcrun swift build --package-path"
[[ ! -e "$TMP_DIR/repos-hs/TronKit.Swift/.palace-scip-build" ]] || fail "dry-run created scratch path"
[[ ! -e "$TMP_DIR/repos-hs/TronKit.Swift/.palace-scip-derived-data" ]] || fail "dry-run created derived data"

SCIP_SCHEME_ONLY_OUT="$TMP_DIR/scip-scheme-only.out"
DEVELOPER_DIR="$TMP_DIR/dev" bash "$SCIP_EMIT_SCRIPT" "tron-kit" \
    --scheme-only-check \
    --repo-path "$TMP_DIR/repos-hs/TronKit.Swift" \
    --remote-relative-path "TronKit.Swift" \
    --emitter-dir "$TMP_DIR/emitter" >"$SCIP_SCHEME_ONLY_OUT"
assert_contains "$SCIP_SCHEME_ONLY_OUT" "scheme=TronKit"
assert_contains "$SCIP_SCHEME_ONLY_OUT" "slug=tron-kit"
assert_contains "$SCIP_SCHEME_ONLY_OUT" "toolchain=swift-5.8.1-RELEASE"
assert_not_contains "$SCIP_SCHEME_ONLY_OUT" "DRY-RUN: xcodebuild"
[[ ! -e "$TMP_DIR/repos-hs/TronKit.Swift/.palace-scip-build" ]] || fail "scheme-only-check created scratch path"
[[ ! -e "$TMP_DIR/repos-hs/TronKit.Swift/.palace-scip-derived-data" ]] || fail "scheme-only-check created derived data"

SCIP_BITCOIN_KIT_OUT="$TMP_DIR/scip-bitcoin-kit.out"
bash "$SCIP_EMIT_SCRIPT" "bitcoin-kit" \
    --dry-run \
    --repo-path "$TMP_DIR/repos-hs/BitcoinKit.Swift" \
    --remote-relative-path "BitcoinKit.Swift" \
    --emitter-dir "$TMP_DIR/emitter" >"$SCIP_BITCOIN_KIT_OUT"
assert_contains "$SCIP_BITCOIN_KIT_OUT" "slug=bitcoin-kit"
assert_contains "$SCIP_BITCOIN_KIT_OUT" "destination=imac-ssh.ant013.work:/Users/Shared/Ios/HorizontalSystems/BitcoinKit.Swift/scip/index.scip"
assert_contains "$SCIP_BITCOIN_KIT_OUT" "BitcoinKit"
assert_not_contains "$SCIP_BITCOIN_KIT_OUT" "-toolchain"

MISSING_TOOLCHAIN_OUT="$TMP_DIR/scip-missing-toolchain.out"
if DEVELOPER_DIR="$TMP_DIR/dev" bash "$SCIP_EMIT_SCRIPT" "missing-toolchain-kit" \
    --dry-run \
    --repo-path "$TMP_DIR/repos-hs/MissingToolchainKit.Swift" \
    --remote-relative-path "MissingToolchainKit.Swift" \
    --emitter-dir "$TMP_DIR/emitter" >"$MISSING_TOOLCHAIN_OUT" 2>&1; then
    fail "missing toolchain unexpectedly succeeded"
fi
assert_contains "$MISSING_TOOLCHAIN_OUT" "toolchain not installed: swift-5.7.1-RELEASE"

SCIP_MARKET_KIT_OUT="$TMP_DIR/scip-market-kit.out"
bash "$SCIP_EMIT_SCRIPT" "market-kit" \
    --dry-run \
    --repo-path "$TMP_DIR/repos-hs/MarketKit.Swift" \
    --remote-relative-path "MarketKit.Swift" \
    --emitter-dir "$TMP_DIR/emitter" >"$SCIP_MARKET_KIT_OUT"
assert_contains "$SCIP_MARKET_KIT_OUT" "scheme=iOS Example"
assert_contains "$SCIP_MARKET_KIT_OUT" "build_target=workspace=iOS Example/iOS Example.xcworkspace"
assert_contains "$SCIP_MARKET_KIT_OUT" "DRY-RUN: xcodebuild"
assert_contains "$SCIP_MARKET_KIT_OUT" "iOS\\ Example/iOS\\ Example.xcworkspace"
assert_contains "$SCIP_MARKET_KIT_OUT" "iOS\\ Example"

SCIP_HS_CRYPTO_KIT_OUT="$TMP_DIR/scip-hs-crypto-kit.out"
bash "$SCIP_EMIT_SCRIPT" "hs-crypto-kit" \
    --dry-run \
    --repo-root "$TMP_DIR/repos-hs" \
    --emitter-dir "$TMP_DIR/emitter" >"$SCIP_HS_CRYPTO_KIT_OUT"
assert_contains "$SCIP_HS_CRYPTO_KIT_OUT" "scheme=HsCryptoKit.Swift"
assert_contains "$SCIP_HS_CRYPTO_KIT_OUT" "build_target=workspace=.swiftpm/xcode/package.xcworkspace"
assert_contains "$SCIP_HS_CRYPTO_KIT_OUT" "local_repo="
assert_contains "$SCIP_HS_CRYPTO_KIT_OUT" "HsCryptoKit.Swift"
assert_contains "$SCIP_HS_CRYPTO_KIT_OUT" ".swiftpm/xcode/package.xcworkspace"

SCIP_HD_WALLET_KIT_OUT="$TMP_DIR/scip-hd-wallet-kit.out"
bash "$SCIP_EMIT_SCRIPT" "hd-wallet-kit" \
    --dry-run \
    --repo-root "$TMP_DIR/repos-hs" \
    --emitter-dir "$TMP_DIR/emitter" >"$SCIP_HD_WALLET_KIT_OUT"
assert_contains "$SCIP_HD_WALLET_KIT_OUT" "scheme=HdWalletKit"
assert_contains "$SCIP_HD_WALLET_KIT_OUT" "build_target=workspace=.swiftpm/xcode/package.xcworkspace"
assert_not_contains "$SCIP_HD_WALLET_KIT_OUT" "scheme=HDWalletKit"

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

CONVENTION_DRY_RUN_OUT="$TMP_DIR/convention-dry-run.out"
bash "$INGEST_SCRIPT" "bitcoin-kit" \
    --auto-resolve-by-convention \
    --dry-run \
    --repo-base=/repos-hs \
    --host-repo-base="$TMP_DIR/repos-hs" \
    --parent-mount=hs \
    --manifest="$TMP_DIR/missing-manifest.json" \
    --env-file="$TMP_DIR/.env" >"$CONVENTION_DRY_RUN_OUT"
assert_contains "$CONVENTION_DRY_RUN_OUT" '"relative_path":"BitcoinKit.Swift"'
assert_contains "$CONVENTION_DRY_RUN_OUT" '"/repos-hs/BitcoinKit.Swift/scip/index.scip"'

CONVENTION_MISSING_OUT="$TMP_DIR/convention-missing.out"
if bash "$INGEST_SCRIPT" "fake-kit" \
    --auto-resolve-by-convention \
    --dry-run \
    --repo-base=/repos-hs \
    --host-repo-base="$TMP_DIR/repos-hs" \
    --parent-mount=hs \
    --manifest="$TMP_DIR/missing-manifest.json" \
    --env-file="$TMP_DIR/.env" >"$CONVENTION_MISSING_OUT" 2>&1; then
    fail "missing convention repo unexpectedly succeeded"
fi
assert_contains "$CONVENTION_MISSING_OUT" "convention resolved to FakeKit.Swift but no such directory at $TMP_DIR/repos-hs/FakeKit.Swift"

ALIAS_MANIFEST_OUT="$TMP_DIR/alias-manifest.out"
bash "$INGEST_SCRIPT" "hs-extensions" \
    --dry-run \
    --repo-base=/repos-hs \
    --host-repo-base="$TMP_DIR/repos-hs" \
    --manifest="$TMP_DIR/hs-extensions-manifest.json" \
    --env-file="$TMP_DIR/.env" >"$ALIAS_MANIFEST_OUT"
assert_contains "$ALIAS_MANIFEST_OUT" '"relative_path":"HsExtensions.Swift"'
assert_contains "$ALIAS_MANIFEST_OUT" '"/repos-hs/HsExtensions.Swift/scip/index.scip"'
assert_not_contains "$ALIAS_MANIFEST_OUT" '"/repos-hs/HsExtensions/scip/index.scip"'

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

cp "$TMP_DIR/.env" "$TMP_DIR/zero-symbol.env"
ZERO_SYMBOL_OUT="$TMP_DIR/zero-symbol.out"
if MOCK_SYMBOL_COUNT=0 MOCK_DOCKER_LOG="$TMP_DIR/zero-symbol-docker.log" bash "$INGEST_SCRIPT" "tron-kit" \
    --bundle=uw-ios \
    --repo-base=/repos-hs \
    --host-repo-base="$TMP_DIR/repos-hs" \
    --parent-mount=hs \
    --relative-path="TronKit.Swift" \
    --env-file="$TMP_DIR/zero-symbol.env" >"$ZERO_SYMBOL_OUT" 2>&1; then
    fail "zero-symbol ingest unexpectedly succeeded"
fi
assert_contains "$ZERO_SYMBOL_OUT" '"stage":"graph_validation"'
assert_contains "$ZERO_SYMBOL_OUT" '"status":"failed"'
assert_contains "$ZERO_SYMBOL_OUT" 'zero Symbol nodes after ingest'

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
python3 - "$MOCK_MCP_LOG" <<'PY'
import json
import sys
from pathlib import Path

entries = []
for line in Path(sys.argv[1]).read_text().splitlines():
    tool, payload = line.split("\t", 1)
    entries.append((tool, json.loads(payload)))

register_index = next(
    index for index, (tool, _) in enumerate(entries)
    if tool == "palace.memory.register_project"
)
extractor_index = next(
    index for index, (tool, _) in enumerate(entries)
    if tool == "palace.ingest.run_extractor"
)
if register_index >= extractor_index:
    raise SystemExit("register_project did not happen before run_extractor")

payload = entries[register_index][1]
assert payload["slug"] == "tron-kit"
assert payload["name"] == "tron-kit"
assert payload["language"] == "swift"
assert payload["parent_mount"] == "hs"
assert payload["relative_path"] == "TronKit.Swift"
assert payload["repo_url"] == "https://github.com/example/TronKit.Swift.git"
PY
ENV_AFTER_RUN1="$(cat "$TMP_DIR/.env")"
PATH_JSON="$(grep '^PALACE_SCIP_INDEX_PATHS=' "$TMP_DIR/.env" | cut -d= -f2-)"
[[ "$(grep -c '^PALACE_SCIP_INDEX_PATHS=' "$TMP_DIR/.env")" -eq 1 ]] || \
    fail "expected PALACE_SCIP_INDEX_PATHS to be deduped to one env entry"
printf '%s' "$PATH_JSON" | jq -e '.existing == "/repos/existing/scip/index.scip"' >/dev/null || \
    fail "existing PALACE_SCIP_INDEX_PATHS entry was not preserved"
printf '%s' "$PATH_JSON" | jq -e '.legacy == "/repos/legacy/scip/index.scip"' >/dev/null || \
    fail "legacy PALACE_SCIP_INDEX_PATHS entry was not preserved"
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
assert_contains "$MOCK_DOCKER_LOG" "test -e '/repos-hs/TronKit.Swift/.git'"

printf 'PASS: ingest idempotency test suite\n'
