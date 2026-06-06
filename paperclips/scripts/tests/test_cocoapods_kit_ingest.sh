#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
EMIT_SCRIPT="$REPO_ROOT/paperclips/scripts/scip_emit_cocoapods_kit.sh"
INGEST_SCRIPT="$REPO_ROOT/paperclips/scripts/ingest_cocoapods_kit.sh"

TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/gim951-cocoapods-test.XXXXXX")"
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
    "$TMP_DIR/repos-hs/hd-wallet-kit-ios/Example/HdWalletKit.xcworkspace" \
    "$TMP_DIR/repos-hs/hd-wallet-kit-ios/Example/HdWalletKit.xcodeproj/xcshareddata/xcschemes" \
    "$TMP_DIR/repos-hs/component-kit-ios/Example/ComponentKit.xcworkspace" \
    "$TMP_DIR/repos-hs/component-kit-ios/Example/ComponentKit.xcodeproj/xcshareddata/xcschemes"

cat > "$TMP_DIR/repos-hs/hd-wallet-kit-ios/Example/Podfile" <<'EOF'
platform :ios, '11'
target 'HdWalletKitTests' do
  pod 'HdWalletKit.swift', :path => '../'
end
EOF

cat > "$TMP_DIR/repos-hs/component-kit-ios/Example/Podfile" <<'EOF'
platform :ios, '13'
target 'ComponentKitExample' do
  pod 'ComponentKit.swift', :path => '../'
end
EOF

cat > "$TMP_DIR/repos-hs/hd-wallet-kit-ios/Example/HdWalletKit.xcodeproj/project.pbxproj" <<'EOF'
// fixture
EOF
cat > "$TMP_DIR/repos-hs/component-kit-ios/Example/ComponentKit.xcodeproj/project.pbxproj" <<'EOF'
// fixture
EOF
cat > "$TMP_DIR/repos-hs/hd-wallet-kit-ios/Example/HdWalletKit.xcodeproj/xcshareddata/xcschemes/HdWalletKitTests.xcscheme" <<'EOF'
<Scheme/>
EOF
cat > "$TMP_DIR/repos-hs/component-kit-ios/Example/ComponentKit.xcodeproj/xcshareddata/xcschemes/ComponentKitExample.xcscheme" <<'EOF'
<Scheme/>
EOF
cat > "$TMP_DIR/repos-hs/component-kit-ios/Example/ComponentKit.xcodeproj/xcshareddata/xcschemes/PinKitTests.xcscheme" <<'EOF'
<Scheme/>
EOF

cat > "$TMP_DIR/.env" <<'EOF'
PALACE_SCIP_INDEX_PATHS={"existing":"/repos/existing/scip/index.scip"}
OTHER_VAR=1
EOF

cat > "$TMP_DIR/bin/xcode-select" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
printf '/Applications/Xcode.app/Contents/Developer\n'
EOF
chmod +x "$TMP_DIR/bin/xcode-select"

cat > "$TMP_DIR/bin/pod" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$PWD" >> "$MOCK_POD_LOG"
exit 0
EOF
chmod +x "$TMP_DIR/bin/pod"

cat > "$TMP_DIR/bin/ssh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
exit 0
EOF
chmod +x "$TMP_DIR/bin/ssh"

cat > "$TMP_DIR/bin/scp" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
exit 0
EOF
chmod +x "$TMP_DIR/bin/scp"

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
mkdir -p "$(dirname "$output")"
printf 'mock scip\n' > "$output"
printf 'emitter-ran\n' > "${output}.marker"
EOF
chmod +x "$TMP_DIR/emitter/mock-emitter"

cat > "$TMP_DIR/bin/xcrun" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
if [[ "$1" == "-f" && "$2" == "xcodebuild" ]]; then
    printf '/Applications/Xcode.app/Contents/Developer/usr/bin/xcodebuild\n'
    exit 0
fi
if [[ "$1" != "xcodebuild" ]]; then
    exit 0
fi

derived_data=""
status="${MOCK_XCODEBUILD_STATUS:-0}"
emit_index="${MOCK_XCODEBUILD_EMIT_INDEX:-1}"
while [[ $# -gt 0 ]]; do
    case "$1" in
        -derivedDataPath)
            derived_data="$2"
            shift 2
            ;;
        *)
            shift
            ;;
    esac
done

if [[ "$emit_index" == "1" ]]; then
    mkdir -p "$derived_data/Index.noindex/DataStore"
    printf 'unit\n' > "$derived_data/Index.noindex/DataStore/mock.unit"
fi

exit "$status"
EOF
chmod +x "$TMP_DIR/bin/xcrun"

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
  {"name":"git_history","description":"git"}
]}
JSON
    ;;
  palace.memory.register_project)
    cat <<'JSON'
{"slug":"hd-wallet-kit","name":"hd-wallet-kit","tags":[],"parent_mount":"hs","relative_path":"hd-wallet-kit-ios","entity_counts":{}}
JSON
    ;;
  palace.ingest.run_extractor)
    name="$(printf '%s' "$json" | python3 -c 'import json,sys; print(json.load(sys.stdin)["name"])')"
    printf '{"ok":true,"run_id":"run-%s","extractor":"%s","project":"hd-wallet-kit","started_at":"now","finished_at":"later","duration_ms":1,"nodes_written":1,"edges_written":0,"success":true}\n' "$name" "$name"
    ;;
  palace.memory.get_project_overview)
    cat <<'JSON'
{"slug":"hd-wallet-kit","name":"hd-wallet-kit","tags":[],"entity_counts":{"IngestRun":1,"Symbol":1},"last_ingest_started_at":"now","last_ingest_finished_at":"later"}
JSON
    ;;
  palace.memory.register_bundle)
    echo '{"ok":true,"name":"uw-ios"}'
    ;;
  palace.memory.add_to_bundle)
    echo '{"ok":true}'
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

if [[ "$#" -ge 4 && "$1" == "-C" && "$3" == "rev-parse" && "$4" == "HEAD" ]]; then
    printf '%s\n' 'deadbeefdeadbeefdeadbeefdeadbeefdeadbeef'
    exit 0
fi
if [[ "$#" -ge 5 && "$1" == "-C" && "$3" == "remote" && "$4" == "get-url" && "$5" == "origin" ]]; then
    case "$2" in
        */hd-wallet-kit-ios)
            printf '%s\n' 'https://github.com/horizontalsystems/hd-wallet-kit-ios.git'
            exit 0
            ;;
        */component-kit-ios)
            printf '%s\n' 'https://github.com/horizontalsystems/component-kit-ios.git'
            exit 0
            ;;
    esac
fi
exit 1
EOF
chmod +x "$TMP_DIR/bin/git"

PATH="$TMP_DIR/bin:$PATH"
export PATH
export PALACE_MCP_CLI_BIN="$TMP_DIR/bin/mock-mcp-cli"
export MOCK_MCP_LOG="$TMP_DIR/mcp.log"
export MOCK_DOCKER_LOG="$TMP_DIR/docker.log"
export MOCK_POD_LOG="$TMP_DIR/pod.log"

HELP_OUT="$TMP_DIR/help.out"
bash "$EMIT_SCRIPT" --help >"$HELP_OUT"
assert_contains "$HELP_OUT" "--podfile-dir"
assert_contains "$HELP_OUT" "Auto scheme detection"

HD_DRY_RUN_OUT="$TMP_DIR/hd-dry-run.out"
bash "$EMIT_SCRIPT" hd-wallet-kit \
    --dry-run \
    --repo-path "$TMP_DIR/repos-hs/hd-wallet-kit-ios" \
    --emitter-dir "$TMP_DIR/emitter" \
    --emitter-bin "$TMP_DIR/emitter/mock-emitter" >"$HD_DRY_RUN_OUT"
assert_contains "$HD_DRY_RUN_OUT" "DRY-RUN: (cd"
assert_contains "$HD_DRY_RUN_OUT" "pod install"
assert_contains "$HD_DRY_RUN_OUT" "scheme=HdWalletKitTests"
assert_contains "$HD_DRY_RUN_OUT" "workspace=$TMP_DIR/repos-hs/hd-wallet-kit-ios/Example/HdWalletKit.xcworkspace"

COMPONENT_DRY_RUN_OUT="$TMP_DIR/component-dry-run.out"
bash "$EMIT_SCRIPT" component-kit \
    --dry-run \
    --repo-path "$TMP_DIR/repos-hs/component-kit-ios" \
    --emitter-dir "$TMP_DIR/emitter" \
    --emitter-bin "$TMP_DIR/emitter/mock-emitter" >"$COMPONENT_DRY_RUN_OUT"
assert_contains "$COMPONENT_DRY_RUN_OUT" "scheme=ComponentKitExample"
assert_not_contains "$COMPONENT_DRY_RUN_OUT" "scheme=PinKitTests"

RUN_OUT="$TMP_DIR/run.out"
MOCK_XCODEBUILD_STATUS=65 \
MOCK_XCODEBUILD_EMIT_INDEX=1 \
bash "$INGEST_SCRIPT" hd-wallet-kit-ios \
    --repo-base /repos-hs \
    --host-repo-base "$TMP_DIR/repos-hs" \
    --env-file "$TMP_DIR/.env" \
    --emitter-dir "$TMP_DIR/emitter" \
    --emitter-bin "$TMP_DIR/emitter/mock-emitter" >"$RUN_OUT"

assert_contains "$RUN_OUT" '"status":"ok"'
assert_contains "$RUN_OUT" '"slug":"hd-wallet-kit"'
assert_contains "$RUN_OUT" '"relative_path":"hd-wallet-kit-ios"'
assert_contains "$RUN_OUT" '"scip_path":"/repos-hs/hd-wallet-kit-ios/scip/index.scip"'
assert_contains "$RUN_OUT" '"extractor":"symbol_index_swift"'
assert_contains "$TMP_DIR/pod.log" "hd-wallet-kit-ios/Example"
[[ -f "$TMP_DIR/repos-hs/hd-wallet-kit-ios/scip/index.scip.marker" ]] || fail "emitter did not run"
assert_contains "$TMP_DIR/.env" 'PALACE_SCIP_INDEX_PATHS={"existing":"/repos/existing/scip/index.scip","hd-wallet-kit":"/repos-hs/hd-wallet-kit-ios/scip/index.scip"}'
assert_contains "$TMP_DIR/docker.log" "test -f '/repos-hs/hd-wallet-kit-ios/Example/Podfile'"

python3 - "$MOCK_MCP_LOG" <<'PY'
import json
import sys
from pathlib import Path

entries = []
for line in Path(sys.argv[1]).read_text().splitlines():
    tool, payload = line.split("\t", 1)
    entries.append((tool, json.loads(payload)))

register_payload = next(payload for tool, payload in entries if tool == "palace.memory.register_project")
assert register_payload["slug"] == "hd-wallet-kit"
assert register_payload["relative_path"] == "hd-wallet-kit-ios"
assert register_payload["parent_mount"] == "hs"
assert register_payload["repo_url"] == "https://github.com/horizontalsystems/hd-wallet-kit-ios.git"
PY

printf 'PASS: cocoa pods kit ingest helper\n'
