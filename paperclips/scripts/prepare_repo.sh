#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DEFAULT_MANIFEST="$REPO_ROOT/services/palace-mcp/scripts/uw-ios-bundle-manifest.json"
DEFAULT_BASE="${PALACE_SWIFT_KIT_HOST_REPO_BASE:-/Users/Shared/Ios/HorizontalSystems}"
DEFAULT_GITHUB_ORG="${PALACE_SWIFT_KIT_GITHUB_ORG:-https://github.com/horizontalsystems}"

usage() {
    cat <<'EOF'
Usage:
  prepare_repo.sh --github <clone-url> [--base <path>] [--manifest <path>]
  prepare_repo.sh --slug <slug> [--base <path>] [--manifest <path>]

Clone a HorizontalSystems kit repo into the iMac repo base and create the
matching slug symlink next to it.

Options:
  --github <clone-url>   Repo clone URL or path. Repo name derives from basename.
  --slug <slug>          Palace slug. Repo name resolves from manifest or convention.
  --base <path>          Host repo base (default: /Users/Shared/Ios/HorizontalSystems)
  --manifest <path>      Manifest used for slug -> repo-dir resolution
  --help, -h             Show this message

Stdout:
  Emits one JSON object with slug, repo_name, repo_path, symlink_path, clone_url,
  and booleans showing whether clone/symlink mutations happened.
EOF
}

die() {
    echo "ERROR: $*" >&2
    exit 1
}

require_command() {
    command -v "$1" >/dev/null 2>&1 || die "missing required command: $1"
}

validate_slug() {
    local slug="$1"
    [[ "$slug" =~ ^[a-z0-9]([a-z0-9-]{0,62}[a-z0-9])?$ ]] || \
        die "invalid slug '$slug' (must match [a-z0-9-]{1,64})"
}

slug_from_repo_name() {
    python3 - "$1" <<'PY'
import re
import sys

name = re.sub(r"\.(swift|Swift)$", "", sys.argv[1])
name = re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", name)
name = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1-\2", name)
print(name.replace("_", "-").lower())
PY
}

pascal_case_slug() {
    python3 - "$1" <<'PY'
import sys

parts = [part for part in sys.argv[1].split("-") if part]
print("".join(part[:1].upper() + part[1:] for part in parts))
PY
}

repo_name_from_manifest() {
    local manifest="$1"
    local slug="$2"
    [[ -f "$manifest" ]] || return 0
    python3 - "$manifest" "$slug" <<'PY'
import json
import sys
from pathlib import Path

manifest_path = Path(sys.argv[1])
slug = sys.argv[2]
data = json.loads(manifest_path.read_text())
for member in data.get("members", []):
    if member.get("slug") == slug:
        rel_path = member.get("relative_path") or ""
        if rel_path:
            print(Path(rel_path).name)
            break
PY
}

repo_name_from_slug() {
    local manifest="$1"
    local slug="$2"
    local repo_name

    repo_name="$(repo_name_from_manifest "$manifest" "$slug")"
    if [[ -n "$repo_name" ]]; then
        printf '%s' "$repo_name"
        return 0
    fi

    if [[ "$slug" == *-kit ]]; then
        printf '%sKit.Swift' "$(pascal_case_slug "${slug%-kit}")"
        return 0
    fi

    printf '%s.Swift' "$(pascal_case_slug "$slug")"
}

normalize_clone_url() {
    local clone_url="${1%/}"
    case "$clone_url" in
        http://*|https://*|ssh://*|git@*)
            if [[ "$clone_url" == *.git ]]; then
                printf '%s' "$clone_url"
            else
                printf '%s.git' "$clone_url"
            fi
            ;;
        *)
            printf '%s' "$clone_url"
            ;;
    esac
}

emit_result() {
    python3 - "$@" <<'PY'
import json
import sys

slug, repo_name, repo_path, symlink_path, clone_url, cloned, symlinked = sys.argv[1:]
print(
    json.dumps(
        {
            "slug": slug,
            "repo_name": repo_name,
            "repo_path": repo_path,
            "symlink_path": symlink_path,
            "clone_url": clone_url,
            "cloned": cloned == "true",
            "symlinked": symlinked == "true",
        }
    )
)
PY
}

CLONE_URL=""
SLUG=""
BASE_DIR="$DEFAULT_BASE"
MANIFEST_PATH="$DEFAULT_MANIFEST"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --github)
            [[ $# -ge 2 ]] || die "--github requires a value"
            CLONE_URL="$2"
            shift 2
            ;;
        --slug)
            [[ $# -ge 2 ]] || die "--slug requires a value"
            SLUG="$2"
            shift 2
            ;;
        --base)
            [[ $# -ge 2 ]] || die "--base requires a value"
            BASE_DIR="$2"
            shift 2
            ;;
        --manifest)
            [[ $# -ge 2 ]] || die "--manifest requires a value"
            MANIFEST_PATH="$2"
            shift 2
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            die "unknown argument: $1"
            ;;
    esac
done

if [[ -z "$CLONE_URL" && -z "$SLUG" ]]; then
    usage
    exit 1
fi

require_command git
require_command python3

if [[ -n "$CLONE_URL" ]]; then
    CLONE_URL="$(normalize_clone_url "$CLONE_URL")"
    REPO_NAME="$(basename "${CLONE_URL%/}")"
    REPO_NAME="${REPO_NAME%.git}"
    if [[ -z "$SLUG" ]]; then
        SLUG="$(slug_from_repo_name "$REPO_NAME")"
    fi
else
    validate_slug "$SLUG"
    REPO_NAME="$(repo_name_from_slug "$MANIFEST_PATH" "$SLUG")"
    CLONE_URL="${DEFAULT_GITHUB_ORG%/}/${REPO_NAME}.git"
fi

validate_slug "$SLUG"
mkdir -p "$BASE_DIR"

REPO_PATH="$BASE_DIR/$REPO_NAME"
SYMLINK_PATH="$BASE_DIR/$SLUG"
CLONED="false"
SYMLINKED="false"

if [[ -d "$REPO_PATH/.git" ]]; then
    :
elif [[ -e "$REPO_PATH" ]]; then
    die "repo path already exists and is not a git checkout: $REPO_PATH"
else
    git clone --depth=1 --quiet "$CLONE_URL" "$REPO_PATH"
    CLONED="true"
fi

if [[ "$SYMLINK_PATH" != "$REPO_PATH" ]]; then
    if [[ -L "$SYMLINK_PATH" ]]; then
        current_target="$(readlink "$SYMLINK_PATH")"
        if [[ "$current_target" != "$REPO_NAME" && "$current_target" != "$REPO_PATH" ]]; then
            rm "$SYMLINK_PATH"
            ln -s "$REPO_NAME" "$SYMLINK_PATH"
            SYMLINKED="true"
        fi
    elif [[ -e "$SYMLINK_PATH" ]]; then
        die "slug path already exists and is not a symlink: $SYMLINK_PATH"
    else
        ln -s "$REPO_NAME" "$SYMLINK_PATH"
        SYMLINKED="true"
    fi
fi

emit_result "$SLUG" "$REPO_NAME" "$REPO_PATH" "$SYMLINK_PATH" "$CLONE_URL" "$CLONED" "$SYMLINKED"
