# imac-agents-deploy.sh — iMac AGENTS.md Deploy

Single idempotent script that deploys updated AGENTS.md role files to live
paperclip agents on iMac via a temporary git worktree from `origin/main`.
Symmetric to `imac-deploy.sh` (palace-mcp container deploy, GIM-106).

Paperclip reads AGENTS.md fresh on each agent run — no agent restart needed
after deploy.

**Must be run on the iMac directly** (or via SSH by a user who already has a
session on the iMac). It does not initiate any SSH connection itself.

---

## Prerequisites

- Git available (`git --version` must succeed) — no Docker needed
- Python 3.12+ with `pyyaml>=6.0,<7.0` (UAA Phase B builder dependency — script
  auto-installs via `pip install --user` if missing)
- Repo checked out at `/Users/Shared/Ios/Gimle-Palace` on branch `develop`
- SSH key that can read `git@github.com:…/paperclip-shared-fragments.git`
  (needed for submodule fetch in the worktree — see Gotcha #1)
- Agent bundle directories present at:
  `~/.paperclip/instances/default/companies/<CID>/agents/<AID>/instructions/`
  (created by Paperclip on first agent run — no manual setup needed)

---

## Usage

```bash
# Deploy from origin/main tip (release-cut content) for a given project
bash paperclips/scripts/imac-agents-deploy.sh <project-key>

# Deploy specific main SHA (rollback or pinned deploy)
bash paperclips/scripts/imac-agents-deploy.sh <project-key> --target-sha abc1234

# Pre-release-cut smoke test: deploy from origin/develop instead of main
bash paperclips/scripts/imac-agents-deploy.sh <project-key> --from-develop
```

`<project-key>` is required. Examples: `gimle`, `trading`, `uaudit`. The script
lists available keys (under `~/.paperclip/projects/`) in its own `--help`.

### Idempotency

Running the script twice when `origin/main` is unchanged is safe:

- Stale worktree at `/tmp/gimle-agents-deploy` is removed before creating a new one
- `bootstrap-project.sh --reuse-bindings` rebuilds dist + redeploys (idempotent)
- A new baseline log line is appended either way

---

## Gotchas

### Gotcha #1 — Submodule init required

`git worktree add` does **not** auto-init submodules. The script runs
`git submodule update --init --recursive` explicitly in the worktree.

If the submodule SSH key is unavailable, this step will fail with exit code 2.
Verify with `ssh -T git@github.com` (or the relevant host) before running.

### Gotcha #2 — Worktree cleanup on interrupt

The script registers `trap cleanup EXIT` so `/tmp/gimle-agents-deploy` is
removed even on ctrl-C, set-e failures, or normal exit.

If `git worktree remove --force` fails (e.g. active git process holds a lock),
the trap falls back to `rm -rf` + `git worktree prune`.

### Gotcha #3 — Production checkout drift

After cleanup the trap verifies `git rev-parse --abbrev-ref HEAD` is still
`develop`. This should never drift (the worktree is detached), but the check
provides an audit trail. A WARNING is logged if it does.

### Gotcha #4 — PATH augmentation

`/usr/local/bin` and `/opt/homebrew/bin` are prepended to PATH so that `git`
and shell utilities are found when the script is invoked via `bash -s` over
SSH. Docker paths are **not** added — this script does not use Docker.

### Gotcha #5 — dist/ directory lives in the worktree

The `paperclips/dist/` directory where `build.sh` writes rendered AGENTS.md
files lives inside the temporary worktree at `/tmp/gimle-agents-deploy/`.
The `DEPLOYED_COUNT` metric is captured **before** the cleanup trap removes
the worktree, so the log line always reflects the actual deploy count.

---

## Rollback

Re-run the script pointing at the previous `main_sha` from the deploy log:

```bash
# Find the previous main_sha
tail -2 paperclips/scripts/imac-agents-deploy.log

# Re-deploy with that SHA
bash paperclips/scripts/imac-agents-deploy.sh --target-sha <previous-main-sha>
```

---

## Log files

### Baseline log — `paperclips/scripts/imac-agents-deploy.log`

Gitignored (`*.log` pattern). Appended on every successful deploy:

```
2026-04-28T10:15:00Z	main_sha=abc1234def5678…	deployed_agents=11
```

Fields: UTC timestamp, main SHA deployed, count of dist files copied.

### Transient run log — `/tmp/imac-agents-deploy-<utc>.log`

Full stdout+stderr of the run. Persists in `/tmp` until system reboot or
manual cleanup. Useful for postmortem if a deploy fails.

---

## Exit code reference

| Code | Meaning | When |
|------|---------|------|
| 0 | Success | All steps passed |
| 1 | Pre-flight / argument error | Wrong cwd, wrong branch, bad `--target-sha`, unknown flag |
| 2 | Worktree failure | `git fetch`, `git worktree add`, or `git submodule update` failed |
| 3 | Build or deploy failure | `paperclips/build.sh` or `paperclips/deploy-agents.sh --local` failed |
| 4 | Verify failure | Marker not found in deployed CTO AGENTS.md, or file missing |
---

## UAudit Dispatcher Deploy And Routine Reconciliation

UAudit prompt deploy uses the same wrapper:

```bash
# Pre-release smoke from develop
bash paperclips/scripts/imac-agents-deploy.sh uaudit --from-develop

# Production deploy after release-cut to main
bash paperclips/scripts/imac-agents-deploy.sh uaudit

# Rollback to a previous known-good SHA
bash paperclips/scripts/imac-agents-deploy.sh uaudit --target-sha <previous-good-sha>
```

For the CTO dispatcher split, deploy order is:

1. Deploy UAudit prompts.
2. Verify generated `UWACTO`/`UWICTO` bundles match authoritative Paperclip-managed instructions.
3. Run one synthetic no-op daily issue assigned to the platform CTO.
4. Only after smoke passes, reconcile Paperclip routine assignees with:

```bash
python3 paperclips/scripts/reconcile_uaudit_routines.py --project-key uaudit
python3 paperclips/scripts/reconcile_uaudit_routines.py --project-key uaudit --apply
```

The reconciliation config is `paperclips/projects/uaudit/daily-version-branch-routines.yaml`. It refers to agents by name and routines by stable `routine_key`; the script resolves existing Paperclip UUIDs, renders host-local repo/cursor paths, and applies description/assignee drift with `baseRevisionId`. Missing or ambiguous routines fail by default and are not created implicitly. A partial apply exits non-zero with `updated`, `failed`, and `not_attempted` records; re-run after a fresh read to converge.
