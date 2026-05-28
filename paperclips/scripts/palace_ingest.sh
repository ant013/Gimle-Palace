#!/usr/bin/env bash
# GIM-952: one-command iOS-library ingest into Gimle/Palace.
# Orchestrates: prepare_repo (iMac) -> SCIP gen (local Xcode) -> scp+ingest (iMac).
#
# Usage:
#   palace_ingest.sh --github <clone-url> [--extractors <csv>] [--skip-embedding] [--scheme <name>]
#   palace_ingest.sh --slug   <slug>       [--extractors <csv>] [--skip-embedding] [--scheme <name>]
#
# --scheme overrides the SCIP-step Xcode scheme; required for kits whose real
# scheme name differs from `basename(repo) - ".Swift"`. Workaround for GIM-984.
#
# Env overrides:
#   PALACE_IMAC_HOST           ssh alias for the iMac (default: imac-ssh.ant013.work)
#   PALACE_IMAC_REPO_PATH      Gimle-Palace checkout on iMac (default: /Users/Shared/Ios/Gimle-Palace)
#   PALACE_LOCAL_REPO_BASE     macbook fallback base for kit checkouts (default: /Users/ant013/Ios/HorizontalSystems)
#
# Expects on the macbook:
#   - Xcode (full install), git, ssh access to PALACE_IMAC_HOST.
#   - A Gimle-Palace checkout in $PWD or one parent up, so the helper scripts resolve.

set -euo pipefail

IMAC_HOST="${PALACE_IMAC_HOST:-imac-ssh.ant013.work}"
IMAC_REPO="${PALACE_IMAC_REPO_PATH:-/Users/Shared/Ios/Gimle-Palace}"
LOCAL_BASE="${PALACE_LOCAL_REPO_BASE:-/Users/ant013/Ios/HorizontalSystems}"
EXTRACTORS="symbol_index_swift,dead_code,embedding_symbol"
GITHUB_URL=""
INPUT_SLUG=""
SCHEME=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --github) GITHUB_URL="$2"; shift 2 ;;
        --slug)   INPUT_SLUG="$2"; shift 2 ;;
        --extractors) EXTRACTORS="$2"; shift 2 ;;
        --skip-embedding) EXTRACTORS="symbol_index_swift,dead_code"; shift ;;
        --scheme) SCHEME="$2"; shift 2 ;;
        --help|-h)
            sed -n '2,18p' "$0"
            exit 0 ;;
        *) echo "ERROR: unknown option: $1" >&2; exit 2 ;;
    esac
done

if [[ -z "$GITHUB_URL" && -z "$INPUT_SLUG" ]]; then
    echo "ERROR: pass --github <url> or --slug <slug>" >&2
    exit 2
fi

# Resolve the Gimle-Palace checkout on the macbook (caller's repo or parent).
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCIP_SCRIPT="$REPO_ROOT/paperclips/scripts/scip_emit_swift_kit.sh"
[[ -x "$SCIP_SCRIPT" ]] || { echo "ERROR: $SCIP_SCRIPT not executable on macbook" >&2; exit 3; }

log() { printf '[palace-ingest] %s\n' "$*"; }

# Step 1: prepare repo + slug on iMac (clone + symlink).
log "step 1/4: prepare_repo on $IMAC_HOST"
if [[ -n "$GITHUB_URL" ]]; then
    PREP_ARGS="--github $GITHUB_URL"
else
    PREP_ARGS="--slug $INPUT_SLUG"
fi
PREP_JSON="$(ssh -o BatchMode=yes -o ConnectTimeout=20 "$IMAC_HOST" \
    "cd $IMAC_REPO && bash paperclips/scripts/prepare_repo.sh $PREP_ARGS")"
echo "$PREP_JSON" | python3 -m json.tool >&2 || { echo "ERROR: prepare_repo did not emit JSON: $PREP_JSON" >&2; exit 4; }
SLUG="$(echo "$PREP_JSON" | python3 -c "import sys,json;print(json.load(sys.stdin)['slug'])")"
REPO_NAME="$(echo "$PREP_JSON" | python3 -c "import sys,json;print(json.load(sys.stdin)['repo_name'])")"
CLONE_URL="$(echo "$PREP_JSON" | python3 -c "import sys,json;print(json.load(sys.stdin)['clone_url'])")"
log "resolved slug=$SLUG repo=$REPO_NAME"

# Step 2: locate or clone the repo on the macbook (Xcode needs Package.swift here).
LOCAL_REPO="$LOCAL_BASE/$REPO_NAME"
if [[ ! -d "$LOCAL_REPO/.git" ]]; then
    # also check /Users/Shared/Ios/HorizontalSystems (alternate base)
    ALT="/Users/Shared/Ios/HorizontalSystems/$REPO_NAME"
    if [[ -d "$ALT/.git" ]]; then
        LOCAL_REPO="$ALT"
    else
        log "step 2/4: cloning $CLONE_URL -> $LOCAL_REPO (not found locally)"
        mkdir -p "$LOCAL_BASE"
        git clone "$CLONE_URL" "$LOCAL_REPO"
    fi
fi
log "local repo: $LOCAL_REPO"

# Step 3: SCIP gen on macbook (uses Xcode), pushes SCIP to iMac via scp_emit's --remote-host default.
log "step 3/4: SCIP gen on macbook"
SCIP_ARGS=("$SLUG" "--repo-path" "$LOCAL_REPO")
if [[ -n "$SCHEME" ]]; then
    SCIP_ARGS+=("--scheme" "$SCHEME")
fi
bash "$SCIP_SCRIPT" "${SCIP_ARGS[@]}"

# Step 4: ingest_swift_kit.sh on iMac (auto-registers :Project per GIM-949).
log "step 4/4: ingest_swift_kit.sh $SLUG on $IMAC_HOST (extractors=$EXTRACTORS)"
ssh -o BatchMode=yes -o ConnectTimeout=20 "$IMAC_HOST" \
    "cd $IMAC_REPO && bash paperclips/scripts/ingest_swift_kit.sh $SLUG --extractors $EXTRACTORS --skip-artefact-check"

log "done: $SLUG ingested. Verify via Cypher: MATCH (s:Symbol {group_id:'project/$SLUG'}) RETURN count(s)"
