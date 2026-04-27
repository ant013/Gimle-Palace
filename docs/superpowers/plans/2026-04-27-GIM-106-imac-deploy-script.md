---
slug: GIM-106-imac-deploy-script
status: plan-ready
branch: feature/GIM-106-imac-deploy-script
paperclip_issue: GIM-106
spec: docs/superpowers/specs/2026-04-27-GIM-106-imac-deploy-script-design.md
date: 2026-04-27
---

# GIM-106 Implementation Plan — imac-deploy.sh

Single idempotent bash deploy script for palace-mcp on iMac production checkout.

## Summary

Create `paperclips/scripts/imac-deploy.sh` that codifies the 5-gotcha deploy pattern from GIM-102. Pure bash, no external deps beyond Docker. Accompanied by README with rollback procedure and CLAUDE.md update.

## Tasks

### T1 — Create `paperclips/scripts/imac-deploy.sh`

**Owner:** InfraEngineer
**Deps:** none
**Affected files:** `paperclips/scripts/imac-deploy.sh`

**Description:**
Write the main deploy script with these sections:
1. Shebang + `set -euo pipefail` (with gotcha #2 mitigation — avoid pipefail on git-piped commands)
2. PATH augmentation (gotcha #1)
3. Argument parsing (`--target <sha>`, `--expect-extractor <name>`, `--help`)
4. Pre-flight checks: cwd assertion, branch=develop, tracked-tree clean (gotcha #4 — report untracked, don't abort)
5. Git fetch + pull --ff-only (gotcha #5 — no worktree)
6. Optional `--target` SHA assertion after pull
7. `docker compose --profile review build palace-mcp`
8. `docker compose --profile review up -d palace-mcp neo4j`
9. Healthcheck polling loop (45×2s = 90s timeout)
10. In-container extractor registry verify (gotcha #3 — one-liner python)
11. Optional `--expect-extractor` assertion
12. Baseline log line append to `paperclips/scripts/imac-deploy.log`
13. `tee` all output to `/tmp/imac-deploy-<utc>.log`

**Acceptance:**
- [ ] File exists, executable bit set (`chmod +x`)
- [ ] `shellcheck paperclips/scripts/imac-deploy.sh` passes (no errors, warnings acceptable with annotation)
- [ ] All 5 gotchas addressed with inline comments referencing gotcha number
- [ ] Exit codes: 1=pre-flight, 2=docker, 3=verify, 4=arg
- [ ] Idempotent: second run on unchanged develop succeeds (skip pull = already up-to-date, still rebuild+verify)
- [ ] Pure bash — no python/node as script dependency (python only inside container via `docker exec`)

### T2 — Create `paperclips/scripts/imac-deploy.README.md`

**Owner:** InfraEngineer
**Deps:** T1
**Affected files:** `paperclips/scripts/imac-deploy.README.md`

**Description:**
Write README covering:
- Usage examples (basic deploy, pinned deploy, extractor assertion)
- Prerequisites (Docker Desktop running, PATH locations)
- Gotchas section (all 5, with explanation)
- Rollback procedure (`docker tag` + restart)
- Log file location and format
- Exit code reference table

**Acceptance:**
- [ ] All five gotchas documented with explanation
- [ ] Rollback procedure is copy-pasteable
- [ ] Prerequisites section lists Docker Desktop + PATH requirements

### T3 — `.gitignore` update

**Owner:** InfraEngineer
**Deps:** none
**Affected files:** `.gitignore`

**Description:**
Add entry to ignore `paperclips/scripts/imac-deploy.log` (per-host runtime artifact, not version-controlled).

**Acceptance:**
- [ ] `git check-ignore paperclips/scripts/imac-deploy.log` returns the path

### T4 — `CLAUDE.md` update

**Owner:** InfraEngineer
**Deps:** T1
**Affected files:** `CLAUDE.md`

**Description:**
Add subsection `## Production deploy on iMac` after the "Docker Compose Profiles" section. Content:
- Reference to `paperclips/scripts/imac-deploy.sh` and its README
- Basic usage: `bash paperclips/scripts/imac-deploy.sh`
- Note that the script must be run ON the iMac (not remotely)
- Mention `--target <sha>` for pinned deploys
- Link to rollback in README

**Acceptance:**
- [ ] New section exists in CLAUDE.md
- [ ] References correct file paths
- [ ] Does not duplicate information already in README (links instead)

## Phase assignments

| Phase | Agent | Task |
|-------|-------|------|
| 1.1 Formalize | CTO | This plan + spec (done) |
| 1.2 Plan review | CodeReviewer | Validate plan completeness |
| 2 Implement | InfraEngineer | T1–T4 on feature branch |
| 3.1 Mechanical review | CodeReviewer | shellcheck + gotcha coverage + idempotency |
| 3.2 Adversarial review | OpusArchitectReviewer | Failure mode analysis |
| 4.1 Live smoke | QAEngineer | Execute on iMac, post evidence |
| 4.2 Merge | CTO | Squash to develop |
