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

# slug | scheme | dir | branch (default: master)
ALL_KITS=(
    "unstoppable-wallet-ios|AUTO_UW_IOS|unstoppable-wallet-ios|version/0.49"
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

resolve_uw_ios_scheme() {
    local repo_dir=$1
    local scheme_list candidate

    if ! scheme_list=$(cd "$repo_dir" && xcodebuild -workspace Wallet.xcworkspace -list 2>&1); then
        echo "unable to list schemes for unstoppable-wallet-ios from Wallet.xcworkspace" >&2
        printf '%s\n' "$scheme_list" >&2
        return 1
    fi
    for candidate in Production Development UnstoppableWallet; do
        if printf '%s\n' "$scheme_list" | grep -Eq "^[[:space:]]*${candidate}[[:space:]]*$"; then
            printf '%s\n' "$candidate"
            return 0
        fi
    done

    echo "unable to resolve unstoppable-wallet-ios scheme from Wallet.xcworkspace" >&2
    printf '%s\n' "$scheme_list" >&2
    return 1
}

resolve_scheme() {
    local scheme=$1
    local repo_dir=$2

    if [[ "$scheme" == "AUTO_UW_IOS" ]]; then
        resolve_uw_ios_scheme "$repo_dir"
        return $?
    fi

    printf '%s\n' "$scheme"
}

prepare_uw_ios_config() {
    local repo_dir=$1
    local config_dir="$repo_dir/Unstoppable/Unstoppable/Configuration"
    local template="$config_dir/Config.template.xcconfig"
    local config="$config_dir/Config.xcconfig"

    if [[ -f "$config" ]]; then
        return 0
    fi
    if [[ ! -f "$template" ]]; then
        echo "missing unstoppable-wallet-ios config template: $template" >&2
        echo "expected Config.template.xcconfig from the repo checkout; cannot prepare $config" >&2
        return 1
    fi

    cp "$template" "$config"
    echo "  [prepare] copied Unstoppable/Unstoppable/Configuration/Config.template.xcconfig -> Config.xcconfig"
}

main() {
    local force=0
    local picked=()
    local entry repo scheme dir branch repo_dir scip resolved_scheme sa arch

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --force) force=1; shift ;;
            -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
            *) picked+=("$1"); shift ;;
        esac
    done

    mkdir -p "$FRESH"
    ln -sfn "$FRESH" "$SYMLINK"

    echo "[1/3] clone any missing repos"
    for entry in "${ALL_KITS[@]}"; do
        IFS='|' read -r repo scheme dir branch <<< "$entry"
        [[ -n "${picked[*]:-}" ]] && [[ ! " ${picked[*]} " =~ " $dir " ]] && continue
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
    arch=$(uname -m)
    for entry in "${ALL_KITS[@]}"; do
        IFS='|' read -r repo scheme dir branch <<< "$entry"
        [[ -n "${picked[*]:-}" ]] && [[ ! " ${picked[*]} " =~ " $dir " ]] && continue
        repo_dir="$FRESH/$dir"
        scip="$repo_dir/scip/index.scip"
        if [[ -s "$scip" && $force -eq 0 ]]; then
            echo "  ✓ $dir already has SCIP ($(wc -c < "$scip" | tr -d ' ')B)"
            continue
        fi
        echo "=== $dir ==="
        cd "$repo_dir"
        rm -rf .palace-scip-derived-data .palace-scip-build
        mkdir -p .palace-scip-derived-data scip
        resolved_scheme=$(resolve_scheme "$scheme" "$repo_dir")
        [[ "$resolved_scheme" != "$scheme" ]] && echo "  [scheme] $resolved_scheme"

        echo "  [resolve]"
        xcodebuild -scheme "$resolved_scheme" \
            -configuration Debug -sdk iphonesimulator \
            -destination "generic/platform=iOS Simulator" \
            -derivedDataPath "$repo_dir/.palace-scip-derived-data" \
            -resolvePackageDependencies >"/tmp/resolve-$dir.log" 2>&1

        # Patch GRDB if present (StatementAuthorizer.swift needs explicit Foundation import)
        sa="$repo_dir/.palace-scip-derived-data/SourcePackages/checkouts/GRDB.swift/GRDB/Core/StatementAuthorizer.swift"
        if [[ -f "$sa" ]]; then
            chmod u+w "$sa"
            if ! head -1 "$sa" | grep -q "^import Foundation"; then
                { echo "import Foundation"; cat "$sa"; } > "$sa.new" && mv "$sa.new" "$sa"
                echo "  [patched GRDB StatementAuthorizer.swift]"
            fi
        fi

        if [[ "$dir" == "unstoppable-wallet-ios" ]]; then
            prepare_uw_ios_config "$repo_dir" || return 1
        fi

        echo "  [build]"
        xcodebuild -scheme "$resolved_scheme" \
            -configuration Debug -sdk iphonesimulator \
            -destination "generic/platform=iOS Simulator" \
            -derivedDataPath "$repo_dir/.palace-scip-derived-data" \
            SYMROOT="$repo_dir/.palace-scip-build" \
            ARCHS="$arch" ONLY_ACTIVE_ARCH=YES \
            CODE_SIGNING_ALLOWED=NO CODE_SIGNING_REQUIRED=NO \
            build >"/tmp/build-$dir.log" 2>&1
        if ! grep -q "BUILD SUCCEEDED" "/tmp/build-$dir.log"; then
            echo "  ❌ BUILD FAILED (see /tmp/build-$dir.log)"
            grep "error:" "/tmp/build-$dir.log" | head -3
            continue
        fi

        echo "  [emit]"
        "$EMITTER" --derived-data "$repo_dir/.palace-scip-derived-data" \
            --project-root "$repo_dir" --output "$scip" >"/tmp/emit-$dir.log" 2>&1
        echo "  ✅ $(wc -c < "$scip" | tr -d ' ')B"
    done

    echo
    echo "[done] heavy build complete. Now run: bench/ingest-fresh-replay.sh"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
