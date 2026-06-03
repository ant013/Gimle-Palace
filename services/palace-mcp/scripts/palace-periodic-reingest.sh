#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PALACE_MCP_SERVICE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
LOCK_DIR="${PALACE_PERIODIC_REINGEST_LOCK_DIR:-/tmp/palace-periodic-reingest}"

mkdir -p "$LOCK_DIR"

DETECT_ARGS=()
if [[ -n "${PALACE_PERIODIC_REINGEST_PROJECTS:-}" ]]; then
    IFS=',' read -r -a PROJECTS <<<"$PALACE_PERIODIC_REINGEST_PROJECTS"
    for project in "${PROJECTS[@]}"; do
        [[ -n "$project" ]] || continue
        DETECT_ARGS+=(--project "$project")
    done
fi

DETECT_JSON="$(
    uv run --directory "$PALACE_MCP_SERVICE_DIR" \
        python -m palace_mcp.ops.detect_stale_files "${DETECT_ARGS[@]}"
)"

STATUS=0

while IFS=$'\t' read -r kind slug repo_path language_profile; do
    [[ -n "$kind" ]] || continue
    if [[ "$kind" == "ERROR" ]]; then
        printf 'ERROR: %s\n' "$slug" >&2
        STATUS=1
        continue
    fi
    if [[ "$kind" != "RUN" ]]; then
        continue
    fi
    if [[ -z "$language_profile" ]]; then
        printf 'ERROR: %s missing language_profile for re-ingest\n' "$slug" >&2
        STATUS=1
        continue
    fi

    lock_file="$LOCK_DIR/$slug.lock"
    printf '[periodic-reingest] project=%s repo=%s\n' "$slug" "$repo_path"
    if ! flock -n -E 75 "$lock_file" \
        uv run --directory "$PALACE_MCP_SERVICE_DIR" \
            python -m palace_mcp.cli project analyze \
            --repo-path "$repo_path" \
            --slug "$slug" \
            --language-profile "$language_profile"; then
        rc=$?
        if [[ "$rc" -eq 75 ]]; then
            printf '[periodic-reingest] skip lock busy for %s\n' "$slug" >&2
            if [[ "$STATUS" -eq 0 ]]; then
                STATUS=75
            fi
            continue
        fi
        printf '[periodic-reingest] re-ingest failed for %s (rc=%s)\n' "$slug" "$rc" >&2
        STATUS=2
    fi
done < <(
    python3 - "$DETECT_JSON" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
for project in payload.get("projects", []):
    errors = project.get("errors") or []
    if errors:
        print(f"ERROR\t{project.get('project')}: {'; '.join(errors)}\t\t")
        continue
    if project.get("requires_reingest"):
        print(
            "RUN\t{project}\t{repo_path}\t{language_profile}".format(
                project=project.get("project", ""),
                repo_path=project.get("repo_path", ""),
                language_profile=project.get("language_profile") or "",
            )
        )
PY
)

exit "$STATUS"
