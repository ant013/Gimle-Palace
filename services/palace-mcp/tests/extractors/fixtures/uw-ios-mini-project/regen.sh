#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$ROOT/../../../../../.." && pwd)"
EMITTER_DIR="$REPO_ROOT/services/palace-mcp/scip_emit_swift"
PACKAGE_DIR="$ROOT/UwMiniCore"
INDEX_STORE="$ROOT/.index-store"
DERIVED_DATA="$ROOT/.derived-data"
OUT="$ROOT/scip/index.scip"

rm -rf "$INDEX_STORE" "$DERIVED_DATA"
rm -rf "$PACKAGE_DIR/.build"
mkdir -p "$DERIVED_DATA/Index.noindex" "$ROOT/scip"

echo "==> 1/4 Build palace-swift-scip-emit"
xcrun swift build -c release --package-path "$EMITTER_DIR"

echo "==> 2/4 Build UwMiniCore with IndexStoreDB"
xcrun swift build \
  --package-path "$PACKAGE_DIR" \
  -Xswiftc -index-store-path \
  -Xswiftc "$INDEX_STORE"

echo "==> 3/4 Prepare DerivedData layout"
cp -R "$INDEX_STORE" "$DERIVED_DATA/Index.noindex/DataStore"

echo "==> 4/4 Emit SCIP"
"$EMITTER_DIR/.build/release/palace-swift-scip-emit-cli" \
  --derived-data "$DERIVED_DATA" \
  --project-root "$PACKAGE_DIR" \
  --output "$OUT" \
  --verbose

test -s "$OUT"
echo "Wrote $OUT"
