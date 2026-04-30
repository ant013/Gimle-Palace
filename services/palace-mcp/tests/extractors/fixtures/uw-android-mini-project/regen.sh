#!/usr/bin/env bash
# Regenerate scip/index.scip for uw-android-mini-project.
# Phase 1.0 path: manual semanticdb-kotlinc compiler plugin + scip-java index-semanticdb.
# (scip-java auto-mode `index` does not produce SemanticDB for Kotlin-only modules.)
set -euo pipefail

cd "$(dirname "$0")"

SCIP_JAVA="${SCIP_JAVA:-$HOME/Library/Application Support/Coursier/bin/scip-java}"
if [ ! -x "$SCIP_JAVA" ]; then
  echo "ERROR: scip-java not found at $SCIP_JAVA"
  echo "Install via: brew install coursier/formulas/coursier && cs install --contrib scip-java"
  exit 1
fi

if [ ! -f local.properties ] && [ -z "${ANDROID_HOME:-}" ]; then
  echo "ERROR: no local.properties and ANDROID_HOME not set"
  echo "Run: echo \"sdk.dir=\$HOME/Library/Android/sdk\" > local.properties"
  exit 1
fi

echo "==> 1/3 Compile all 4 modules (semanticdb-kotlinc plugin auto-injected via build.gradle.kts)"
gradle :app-mini:compileDebugKotlin :core-mini:compileDebugKotlin \
       :components:icons-mini:compileDebugKotlin :components:chartview-mini:compileDebugKotlin \
       --no-daemon --warning-mode=summary

SEMANTICDB_COUNT=$(find build/semanticdb-targetroot -name "*.semanticdb" 2>/dev/null | wc -l | tr -d ' ')
echo "  SemanticDB files: $SEMANTICDB_COUNT"
test "$SEMANTICDB_COUNT" -gt 0 || { echo "ERROR: no SemanticDB output — semanticdb-kotlinc not working"; exit 1; }

echo "==> 2/3 Convert SemanticDB → SCIP via scip-java index-semanticdb"
"$SCIP_JAVA" index-semanticdb --targetroot ./build/semanticdb-targetroot --output ./scip/index.scip

echo "==> 3/3 Verify index.scip + AC#4 KSP-source-visibility"
test -s scip/index.scip || { echo "ERROR: index.scip empty/missing"; exit 1; }
echo "  size: $(wc -c < scip/index.scip) bytes"

if grep -q "WalletDao_Impl" scip/index.scip 2>/dev/null; then
  echo "  AC#4 PASS — Branch A: KSP-generated WalletDao_Impl visible in index.scip"
else
  echo "  AC#4 FAIL — KSP source not visible; investigate semanticdb-kotlinc + KSP source-set integration"
  exit 1
fi
