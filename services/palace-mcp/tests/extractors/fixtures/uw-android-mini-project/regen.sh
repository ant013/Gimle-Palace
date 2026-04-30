#!/usr/bin/env bash
# Regenerate scip/index.scip for uw-android-mini-project.
# Phase 1.0 oracle gate: run end-to-end + grep WalletDao_Impl + count occurrences.
set -euo pipefail

cd "$(dirname "$0")"

echo "==> 1/3 Compile all 4 modules"
gradle :app-mini:compileDebugKotlin :core-mini:compileDebugKotlin \
       :components:icons-mini:compileDebugKotlin :components:chartview-mini:compileDebugKotlin \
       --no-daemon --warning-mode=summary

echo "==> 2/3 Run scip-java index"
npx --yes @sourcegraph/scip-java index --output ./scip/index.scip

echo "==> 3/3 Verify index.scip"
test -s scip/index.scip || { echo "ERROR: index.scip empty/missing"; exit 1; }
echo "  size: $(wc -c < scip/index.scip) bytes"

echo "==> AC#4 KSP-source-visibility check"
if grep -q "WalletDao_Impl" scip/index.scip 2>/dev/null; then
  echo "  PASS — Branch A: WalletDao_Impl present"
else
  echo "  FAIL — Branch B required (workaround sourceSets OR drop AC#4 to B-2)"
fi
