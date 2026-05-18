# Gimle-Palace — Branch Flow

> Extracted from former `CLAUDE.md` "Branch Flow" section during UAA Phase H1
> CLAUDE.md decompose (2026-05-17).

## Single mainline: `develop`

Feature branches cut from develop, PR'd back. `main` is an optional
release-stable reference.

```
feature/GIM-N-<slug>    (all work: code, spec, plan, research, docs)
      │
      ▼  PR → squash-merge (CI green + CR paperclip APPROVE + CR GitHub review + QA evidence present)
develop                   (integration tip; iMac deploys from here)
      │
      ▼  .github/workflows/release-cut.yml (label `release-cut` on a merged PR, or workflow_dispatch)
main                      (stable release ref — tags live here)
```

## Iron rules

- Every change — product code, spec, plan, research, postmortem, role-file, CLAUDE.md itself — goes through a feature branch + PR. Zero direct human commits to `develop` or `main`.
- Force push forbidden on `develop` / `main`; on feature branches only `--force-with-lease` AND only when you are the sole writer of the current phase (see `paperclip-shared-fragments` repo, `fragments/git/commit-and-push.md`).
- Branch protection on develop + main: admin-bypass disabled. All required checks must pass for PR merge. `main` accepts push only from `github-actions[bot]` via `release-cut.yml`.
- Feature branches live in paperclip-managed worktrees; primary repo stays on `develop`.
- **Operator/Board checkout location:** a separate clone, typically `~/<project>-board/` or `~/Android/<project>/`. Never use the production deploy checkout (`/Users/Shared/Ios/<project>/`) for spec/plan writing.

**Spec + plan location:** `docs/superpowers/specs/` and `docs/superpowers/plans/` on the feature branch. After squash-merge they land on develop. Main gets them only when `release-cut.yml` Action runs.

## Required status checks on develop

- `lint`
- `typecheck`
- `test`
- `docker-build`
- `qa-evidence-present` (verifies PR body has `## QA Evidence` with SHA, unless `micro-slice` label)

## CR approval path

CR posts full compliance comment on paperclip issue AND `gh pr review --approve` on the GitHub PR (the GitHub review satisfies branch-protection's "Require PR reviews" rule).

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
