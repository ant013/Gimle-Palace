#!/usr/bin/env bash
# Heavy one-time build: clone fresh repos + xcodebuild + SCIP emit.
# Run this ONCE per workspace setup. After that use ingest-fresh-replay.sh.
#
# Outputs:
#   /Users/ant013/Ios/uw-fresh-2026-06-04/<kit>/scip/index.scip
#   /Users/ant013/Ios-fresh → uw-fresh-2026-06-04 (symlink for parent_mount="fresh")
#
# Idempotent: existing SCIP files are skipped unless --force.
# Takes 60-120 min total on first run.

set -euo pipefail

FRESH=/Users/ant013/Ios/uw-fresh-2026-06-04
SYMLINK=/Users/ant013/Ios-fresh
EMITTER=/Users/ant013/Android/Gimle-Palace/services/palace-mcp/scip_emit_swift/.build/release/palace-swift-scip-emit-cli

FORCE=0
PICKED=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        --force) FORCE=1; shift ;;
        -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
        *) PICKED+=("$1"); shift ;;
    esac
done

# slug | scheme | dir | branch (default: master)
ALL_KITS=(
    "unstoppable-wallet-ios|Production|unstoppable-wallet-ios|version/0.49"
    "BitcoinCore.Swift|BitcoinCore|BitcoinCore.Swift|master"
    "BitcoinKit.Swift|BitcoinKit|BitcoinKit.Swift|master"
    "ComponentKit.Swift|ComponentKit|ComponentKit.Swift|main"
    "DashKit.Swift|DashKit|DashKit.Swift|master"
    "EvmKit.Swift|EvmKit|EvmKit.Swift|master"
    "HdWalletKit.Swift|HdWalletKit|HdWalletKit.Swift|main"
    "HsCryptoKit.Swift|HsCryptoKit|HsCryptoKit.Swift|main"
    "HsExtensions.Swift|HsExtensions|HsExtensions.Swift|main"
    "HsToolKit.Swift|HsToolKit|HsToolKit.Swift|main"
    "LitecoinKit.Swift|LitecoinKit|LitecoinKit.Swift|master"
    "MarketKit.Swift|MarketKit|MarketKit.Swift|master"
    "MoneroKit.Swift|MoneroKit|MoneroKit.Swift|master"
)

mkdir -p "$FRESH"
ln -sfn "$FRESH" "$SYMLINK"

echo "[1/3] clone any missing repos"
for entry in "${ALL_KITS[@]}"; do
    IFS='|' read -r repo scheme dir branch <<< "$entry"
    [[ -n "${PICKED[*]:-}" ]] && [[ ! " ${PICKED[*]} " =~ " $dir " ]] && continue
    if [[ ! -d "$FRESH/$dir/.git" ]]; then
        echo "  clone $repo @ $branch"
        rm -rf "$FRESH/$dir"
        git clone --quiet --branch "$branch" --single-branch --depth 1 \
            "https://github.com/horizontalsystems/$repo.git" "$FRESH/$dir"
    else
        echo "  skip $dir (cloned)"
    fi
done

echo "[2/3] build emitter if missing"
if [[ ! -x "$EMITTER" ]]; then
    (cd /Users/ant013/Android/Gimle-Palace/services/palace-mcp/scip_emit_swift && xcrun swift build -c release)
fi

echo "[3/3] xcodebuild + SCIP emit per kit"
ARCH=$(uname -m)
for entry in "${ALL_KITS[@]}"; do
    IFS='|' read -r repo scheme dir branch <<< "$entry"
    [[ -n "${PICKED[*]:-}" ]] && [[ ! " ${PICKED[*]} " =~ " $dir " ]] && continue
    REPO_DIR="$FRESH/$dir"
    SCIP="$REPO_DIR/scip/index.scip"
    if [[ -s "$SCIP" && $FORCE -eq 0 ]]; then
        echo "  ✓ $dir already has SCIP ($(wc -c < "$SCIP" | tr -d ' ')B)"
        continue
    fi
    echo "=== $dir ==="
    cd "$REPO_DIR"
    rm -rf .palace-scip-derived-data .palace-scip-build
    mkdir -p .palace-scip-derived-data scip

    echo "  [resolve]"
    xcodebuild -scheme "$scheme" \
        -configuration Debug -sdk iphonesimulator \
        -destination "generic/platform=iOS Simulator" \
        -derivedDataPath "$REPO_DIR/.palace-scip-derived-data" \
        -resolvePackageDependencies >"/tmp/resolve-$dir.log" 2>&1

    # Patch GRDB if present (StatementAuthorizer.swift needs explicit Foundation import)
    SA="$REPO_DIR/.palace-scip-derived-data/SourcePackages/checkouts/GRDB.swift/GRDB/Core/StatementAuthorizer.swift"
    if [[ -f "$SA" ]]; then
        chmod u+w "$SA"
        if ! head -1 "$SA" | grep -q "^import Foundation"; then
            { echo "import Foundation"; cat "$SA"; } > "$SA.new" && mv "$SA.new" "$SA"
            echo "  [patched GRDB StatementAuthorizer.swift]"
        fi
    fi

    echo "  [build]"
    xcodebuild -scheme "$scheme" \
        -configuration Debug -sdk iphonesimulator \
        -destination "generic/platform=iOS Simulator" \
        -derivedDataPath "$REPO_DIR/.palace-scip-derived-data" \
        SYMROOT="$REPO_DIR/.palace-scip-build" \
        ARCHS="$ARCH" ONLY_ACTIVE_ARCH=YES \
        CODE_SIGNING_ALLOWED=NO CODE_SIGNING_REQUIRED=NO \
        build >"/tmp/build-$dir.log" 2>&1
    if ! grep -q "BUILD SUCCEEDED" "/tmp/build-$dir.log"; then
        echo "  ❌ BUILD FAILED (see /tmp/build-$dir.log)"
        grep "error:" "/tmp/build-$dir.log" | head -3
        continue
    fi

    echo "  [emit]"
    "$EMITTER" --derived-data "$REPO_DIR/.palace-scip-derived-data" \
        --project-root "$REPO_DIR" --output "$SCIP" >"/tmp/emit-$dir.log" 2>&1
    echo "  ✅ $(wc -c < "$SCIP" | tr -d ' ')B"
done

echo
echo "[done] heavy build complete. Now run: bench/ingest-fresh-replay.sh"
