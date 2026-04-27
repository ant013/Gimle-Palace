---
slug: GIM-106-imac-deploy-script
status: approved
date: 2026-04-27
predecessor_sha: 3c7ba7d
---

# GIM-106 Design — iMac production deploy script

## Problem

Every merge to `develop` that affects `palace-mcp` requires a manual deploy
on iMac: SSH → git pull → docker compose build → up → verify extractors.
Pattern captured during GIM-102 deploy (2026-04-27T17:03Z) with five gotchas
discovered empirically. Without codification operators re-discover them each
time; deploys take 15–30 min instead of 2.

## Solution

Single idempotent bash script `paperclips/scripts/imac-deploy.sh` that:

1. Validates pre-flight state (cwd, branch, tracked-tree clean).
2. Pulls develop tip (ff-only).
3. Rebuilds `palace-mcp` Docker image.
4. Brings containers up with healthcheck wait.
5. Verifies extractor registry in-container.
6. Records baseline for rollback.

## Five gotchas (codified from GIM-102)

| # | Gotcha | Mitigation |
|---|--------|-----------|
| 1 | PATH missing Docker binaries over SSH | Explicit PATH export at script top |
| 2 | `set -o pipefail` + `head \| grep` → SIGPIPE | Use `git rev-parse --verify --quiet` |
| 3 | Multi-line `python -c` in `docker exec` breaks | One-liner with `;` separators |
| 4 | Untracked files (scip/, etc.) trigger false abort | `--untracked-files=no` for dirty-check; report only |
| 5 | Worktree not appropriate for develop deploy | Direct FF-pull on production checkout |

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Pre-flight failure (dirty/wrong-branch/non-FF) |
| 2 | Docker failure (build/up/health) |
| 3 | Verify failure (extractor mismatch) |
| 4 | Argument error (bad flag) |

## Deliverables

1. `paperclips/scripts/imac-deploy.sh` — the script
2. `paperclips/scripts/imac-deploy.README.md` — usage + gotchas + rollback
3. `.gitignore` — ignore `paperclips/scripts/imac-deploy.log`
4. `CLAUDE.md` — add "Production deploy on iMac" subsection

## Scope out

- Remote SSH wrapper (script runs locally on iMac)
- CI auto-deploy on develop push
- Release/main deploy (handled by release-cut-v2)
- Multi-host deploy

## Rollback procedure

Compose uses `build:` directive, not a named `image:` tag. Rollback must
override the compose-generated image name and skip rebuild:

```bash
# prev-image-id is captured in imac-deploy.log before each rebuild
docker tag <prev-image-id> gimle-palace-palace-mcp:latest
docker compose --profile review up -d --no-build palace-mcp
```
