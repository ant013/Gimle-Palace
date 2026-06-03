#!/usr/bin/env bash
# spike_call_hierarchy_imac.sh — validate GIM-1166 F1B spike on iMac (full Xcode required)
#
# USAGE:
#   bash scripts/spike_call_hierarchy_imac.sh
#
# REQUIREMENTS:
#   - Full Xcode installed (not just CLT)
#   - UW iOS project at /Users/Shared/Ios/HorizontalSystems/unstoppable-wallet-ios
#     OR set UW_IOS_PATH env var to the actual path
#   - UW iOS project must be buildable (run xcodebuild at least once, or open in Xcode)
#   - palace-mcp venv at services/palace-mcp/.venv
#
# WHAT IT DOES:
#   1. Optionally triggers a minimal xcodebuild index run
#   2. Locates the DerivedData index store
#   3. Runs the spike pytest test with the index store path
#   4. Reports results
#
# ACCEPTANCE CRITERIA (GIM-1166):
#   - BalanceData callHierarchy returns >= 30 references
#   - Latency < 10s (warm), cold OK
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_DIR="$(dirname "$SCRIPT_DIR")"
VENV="$SERVICE_DIR/.venv"

UW_IOS_PATH="${UW_IOS_PATH:-/Users/Shared/Ios/HorizontalSystems/unstoppable-wallet-ios}"
UW_WORKSPACE="$UW_IOS_PATH/UnstoppableWallet"
XCWORKSPACE="$UW_WORKSPACE/UnstoppableWallet.xcworkspace"

log() { echo "[spike] $*"; }

# Require full Xcode
if ! xcodebuild -version &>/dev/null; then
    echo "ERROR: xcodebuild not found. Full Xcode is required for this spike."
    echo "Install Xcode from the App Store, then run: sudo xcode-select --switch /Applications/Xcode.app"
    exit 1
fi
log "Xcode $(xcodebuild -version | head -1) detected"

# Verify workspace exists
if [ ! -f "$XCWORKSPACE/contents.xcworkspacedata" ]; then
    echo "ERROR: UW iOS workspace not found at $XCWORKSPACE"
    echo "Set UW_IOS_PATH env var to the correct path."
    exit 1
fi

# Find DerivedData for UnstoppableWallet
DERIVED_DATA=$(find ~/Library/Developer/Xcode/DerivedData -maxdepth 1 -name "UnstoppableWallet-*" -type d 2>/dev/null | head -1)
INDEX_STORE=""

if [ -n "$DERIVED_DATA" ]; then
    # Old-style index store (DataStore)
    DATA_STORE="$DERIVED_DATA/Index.noindex/DataStore"
    if [ -d "$DATA_STORE/v5/units" ] && [ "$(ls "$DATA_STORE/v5/units" | wc -l)" -gt 0 ]; then
        INDEX_STORE="$DATA_STORE"
        log "Found existing index store: $INDEX_STORE ($(ls "$DATA_STORE/v5/units" | wc -l) units)"
    fi
fi

if [ -z "$INDEX_STORE" ]; then
    log "No pre-built index found. Running xcodebuild to generate index..."
    log "This may take 5-15 minutes on first run..."

    # Build with index store
    CUSTOM_INDEX="/tmp/uw-ios-index-store"
    xcodebuild \
        -workspace "$XCWORKSPACE" \
        -scheme UnstoppableWallet \
        -sdk iphonesimulator \
        -destination "platform=iOS Simulator,name=iPhone 16" \
        OTHER_SWIFT_FLAGS="-index-store-path $CUSTOM_INDEX" \
        build 2>&1 | tail -5

    if [ -d "$CUSTOM_INDEX/v5/units" ] && [ "$(ls "$CUSTOM_INDEX/v5/units" | wc -l)" -gt 0 ]; then
        INDEX_STORE="$CUSTOM_INDEX"
        log "Index built: $INDEX_STORE ($(ls "$CUSTOM_INDEX/v5/units" | wc -l) units)"
    else
        echo "ERROR: xcodebuild succeeded but index store not found at $CUSTOM_INDEX"
        exit 1
    fi
fi

# Run the spike test
log "Running spike test..."
log "  UW_IOS_PATH=$UW_IOS_PATH"
log "  SOURCEKIT_INDEX_STORE_PATH=$INDEX_STORE"

"$VENV/bin/pytest" \
    tests/lsp/test_call_hierarchy_spike.py::test_balance_data_call_hierarchy_spike \
    -v -s \
    --timeout=120 \
    -p no:warnings \
    2>&1 | tee /tmp/spike-results.txt

echo ""
echo "=== SPIKE SUMMARY ==="
grep -E "PASSED|FAILED|callers|Latency|Incoming" /tmp/spike-results.txt || true
