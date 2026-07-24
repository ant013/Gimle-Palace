# Gimle-Palace — Branch Flow

> Extracted from former `CLAUDE.md` "Branch Flow" section during UAA Phase H1
> CLAUDE.md decompose (2026-05-17).

## Single mainline: `develop`

Feature branches cut from develop, PR'd back. `main` is an optional
release-stable reference.

```
feature/GIM-N-<slug>    (all work: code, spec, plan, research, docs)
      │
      ▼  CTO squash-merge per `paperclip-shared-fragments/fragments/universal/cto-merge-authority.md`
       (CI green + CR paperclip APPROVE + QA paperclip PASS, all SHA-pinned)
develop                   (integration tip; iMac deploys from here)
      │
      ▼  .github/workflows/release-cut.yml (label `release-cut` on a merged PR, or workflow_dispatch)
main                      (stable release ref — tags live here)
```

## Iron rules

- Every change — product code, spec, plan, research, postmortem, role-file, CLAUDE.md itself — goes through a feature branch + PR. Zero direct human commits to `develop` or `main`.
- Force push forbidden on `develop` / `main`; on feature branches only `--force-with-lease` AND only when you are the sole writer of the current phase (see `paperclip-shared-fragments` repo, `fragments/git/commit-and-push.md`).
- Branch protection on develop + main: required status checks enforced for PR merge. `--admin` is reserved for the CTO merge action when the shared-GitHub-identity self-review error blocks the standard path (see `paperclip-shared-fragments/fragments/universal/cto-merge-authority.md`). `main` accepts push only from `github-actions[bot]` via `release-cut.yml`.
- Feature branches live in paperclip-managed worktrees; primary repo stays on `develop`.
- **Operator/Board checkout location:** a separate clone, typically `~/<project>-board/` or `~/Android/<project>/`. Never use the production deploy checkout (`/Users/Shared/Ios/<project>/`) for spec/plan writing.

**Spec + plan location:** `docs/superpowers/specs/` and `docs/superpowers/plans/` on the feature branch. After squash-merge they land on develop. Main gets them only when `release-cut.yml` Action runs.

## Worktree lifecycle

Worktree cleanup is ownership-based, not name-based.

### Persistent workspaces

Do not remove these as task cleanup:

- the primary repository checkout;
- production/deployment checkouts;
- the active `PALACE_SERVICE_ROOT` runtime source (currently it may be
  `Gimle-Palace-serving`) and the `Gimle-Palace-native` environment;
- stable `Gimle-Palace-claude` and `Gimle-Palace-cx` team roots;
- `<team_workspace_root>/<AgentName>/workspace/` Paperclip workspaces.

Paperclip workspaces rotate branches between slices while keeping the directory.
Removing one can destroy another agent's state.

### Creator-owned ad hoc worktrees

An ad hoc worktree is ephemeral only when the current session created that
exact path for the current task. Keep it while the task is active, awaiting
spec approval, or otherwise expected to continue.

At terminal success:

1. Remove only untracked/generated files proven to belong to the current
   session. Never discard user-owned changes.
2. Fetch and require a clean tree whose `HEAD` exactly matches its configured
   upstream:

   ```bash
   git -C <exact-created-path> fetch origin --prune
   test -z "$(git -C <exact-created-path> status --short)"
   test "$(git -C <exact-created-path> rev-parse HEAD)" = \
     "$(git -C <exact-created-path> rev-parse '@{upstream}')"
   ```

3. From the owning repository or another directory outside the target, remove
   only that exact registered path:

   ```bash
   git -C <owning-repo> worktree remove <exact-created-path>
   ```

4. Report either successful removal or the preserved path and reason in the
   terminal handoff.

A missing upstream, unequal SHA, dirty status, lock, uncertain ownership, or
persistent path blocks cleanup. Preserve the directory. Do not use `--force`,
do not fall back to `rm -rf`, and do not run broad `git worktree prune` as a
task-cleanup shortcut. A successful `git worktree remove` already removes the
target's administrative metadata.

## Required status checks on develop

- `lint`
- `typecheck`
- `test`
- `docker-build`
- `qa-evidence-present` (verifies PR body has `## QA Evidence` with SHA, unless `micro-slice` label)

## Merge gate

CR posts substantive `APPROVE` on the Paperclip issue (with `ruff/mypy/pytest/coverage` paste). QA posts `QA PASS` on the same issue with PR head SHA. CI green. CTO performs squash-merge per `paperclip-shared-fragments/fragments/universal/cto-merge-authority.md`. The previously required `gh pr review --approve` GitHub click is **removed** — agents share one GitHub identity, so the formal Approve was structurally unobtainable.

## Release-cut procedure

To update `main`:
1. Add label `release-cut` to a merged develop PR, OR
2. Run `gh workflow run release-cut.yml`.

The Action opens a PR `develop → main`, enables auto-merge with rebase
strategy, and (after merge) pushes an annotated tag `release-<date>-<sha>`.
Uses only the workflow's `GITHUB_TOKEN` — no PAT or App needed. No human
pushes `main`, ever.

## See also

- `paperclip-shared-fragments` repo, `fragments/git/` — per-agent commit/push/merge/release rules.
- `docs/runbooks/2026-04-19-meta-workflow-migration-rollback.md` — if branch protection or the new workflows cause a block and need to be reverted.
