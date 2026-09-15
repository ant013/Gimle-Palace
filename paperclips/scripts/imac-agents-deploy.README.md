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

**UAudit runs only on iMac.** From another machine, first connect with
`ssh -p 2222 imac-ssh.ant013.work`, then run every UAudit deploy or audit command in
that SSH session. Do not run UAudit against the caller's local filesystem.

UAudit prompt deploy uses the same wrapper:

```bash
# Phase 1: deploy only the v1/v2-compatible tools from develop
bash paperclips/scripts/imac-agents-deploy.sh uaudit --from-develop --uaudit-runtime-only

# Phase 2: project-wide schema-v3 deploy after both cursor migrations
bash paperclips/scripts/imac-agents-deploy.sh uaudit
```

UAudit schema-v3 rollout is a two-platform barrier, not two independent deploys:

1. Run the runtime-only command above; it installs both manifest-bound tools and performs no journal, API, agent, or workspace mutation.
2. Stop both scheduled routines, drain nonterminal runs, and verify that no legacy or neutral platform lock is held.
3. Acquire both neutral maintenance locks in order: Android, then iOS.
4. Use the deployed resolver `migrate-cursor` command for Android and iOS with each explicit current branch and authoritative remote. Each migration requires cursor SHA to equal the advertised/fetched branch head and writes a read-only v1 backup plus receipt.
5. Run `uaudit_schema_epoch.py --target-schema 3 --project-root <uaudit-project-root> --mode full`; mixed v1/v2 or any non-v2 pair blocks.
6. Run the full wrapper deploy. Its trusted-checkout preflight repeats the epoch check before invoking the target bootstrap.
7. Dry-run and then apply stable routine reconciliation:

```bash
python3 paperclips/scripts/reconcile_uaudit_routines.py --project-key uaudit
python3 paperclips/scripts/reconcile_uaudit_routines.py --project-key uaudit --apply
```

8. While both maintenance locks remain held and both routines remain stopped, smoke Android and iOS. Enable routines only after both pass; if the second enable fails, disable the first again and post-read verify both stopped.
9. Release both maintenance locks only after the two-platform smoke/enable result is confirmed.

After cursor v2 is established, an ordinary `--target-sha` to schema-v2 runtime is forbidden and the wrapper blocks it. Recovery below that epoch requires stopped routines, both maintenance locks, and an explicit restoration from the read-only v1 backups; it is not a normal agent deploy rollback.

The reconciliation config is `paperclips/projects/uaudit/daily-version-branch-routines.yaml`. It refers to agents by name and routines by stable `routine_key`, with a same-major release policy instead of a concrete minor branch. The script resolves existing Paperclip UUIDs, renders host-local repo/cursor paths, epoch-checks before apply, and updates description/assignee drift with `baseRevisionId`. Missing or ambiguous routines fail by default and are not created implicitly. A partial apply exits non-zero with `updated`, `failed`, and `not_attempted` records; re-run after a fresh read to converge.
