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
- Repo checked out at `/Users/Shared/Ios/Gimle-Palace` on branch `develop`
- SSH key that can read `git@github.com:…/paperclip-shared-fragments.git`
  (needed for submodule fetch in the worktree — see Gotcha #1)
- Agent bundle directories present at:
  `~/.paperclip/instances/default/companies/<CID>/agents/<AID>/instructions/`
  (created by Paperclip on first agent run — no manual setup needed)

---

## Usage

```bash
# Deploy from origin/main tip
bash paperclips/scripts/imac-agents-deploy.sh

# Deploy specific main SHA (rollback or pinned deploy)
bash paperclips/scripts/imac-agents-deploy.sh --target-sha abc1234

# Custom verification marker (if default "Phase 4.2" is stale)
bash paperclips/scripts/imac-agents-deploy.sh --verify-marker "Phase 4.2 — Merge-readiness"
```

### Idempotency

Running the script twice when `origin/main` is unchanged is safe:

- Stale worktree at `/tmp/gimle-agents-deploy` is removed before creating a new one
- `build.sh` overwrites dist files (idempotent by design)
- `deploy-agents.sh --local` overwrites AGENTS.md files (file copy)
- A new baseline log line is appended either way
- Verify passes again (same content)

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
