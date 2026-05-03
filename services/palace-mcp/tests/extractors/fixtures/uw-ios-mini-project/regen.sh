#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

EMITTER_BIN="${PALACE_SWIFT_SCIP_EMIT_BIN:-../../../scip_emit_swift/.build/release/palace-swift-scip-emit-cli}"
DERIVED_DATA_DIR="${DERIVED_DATA_DIR:-$PWD/DerivedData}"
OUTPUT_PATH="${OUTPUT_PATH:-$PWD/scip/index.scip}"

if [ ! -x "$EMITTER_BIN" ]; then
  echo "ERROR: Swift emitter binary not found at $EMITTER_BIN"
  echo "Build it first from services/palace-mcp/scip_emit_swift:"
  echo "  xcrun swift build -c release"
  exit 1
fi

if [ ! -f project.yml ]; then
  echo "ERROR: fixture source tree is not staged yet (missing project.yml)"
  echo "Add the uw-ios-mini-project sources before running regen."
  exit 1
fi

if ! command -v xcodegen >/dev/null 2>&1; then
  echo "ERROR: xcodegen is required to materialize the fixture Xcode project"
  echo "Install via: brew install xcodegen"
  exit 1
fi

echo "==> 1/4 Generate Xcode project from project.yml"
xcodegen generate

echo "==> 2/4 Build fixture to populate DerivedData"
rm -rf "$DERIVED_DATA_DIR"
xcodebuild \
  -project UwMiniApp.xcodeproj \
  -scheme UwMiniApp \
  -derivedDataPath "$DERIVED_DATA_DIR" \
  -destination "generic/platform=iOS Simulator" \
  build

echo "==> 3/4 Emit canonical SCIP"
mkdir -p "$(dirname "$OUTPUT_PATH")"
"$EMITTER_BIN" \
  --derived-data "$DERIVED_DATA_DIR" \
  --project-root "$PWD" \
  --output "$OUTPUT_PATH" \
  --verbose

echo "==> 4/4 Verify output exists"
test -s "$OUTPUT_PATH"
wc -c "$OUTPUT_PATH"

echo "Regen complete. Commit scip/index.scip and update REGEN.md oracle counts."
