# Meta-workflow migration — feature-branch flow as single source of truth

**Date:** 2026-04-19
**Slice:** Meta-workflow-migration (next after GIM-54)
**Author:** Board (operator-driven, post-GIM-54 reconciliation)
**Status:** Awaiting formalization (Phase 1.1)
**Branch:** `feature/meta-workflow-migration` (this spec lives on the feature branch — first slice to follow the new flow it defines)
**Predecessors pinned:**
- `develop@f3489b6` — reconcile merge (main → develop). main and develop pointed at same tip for the first time since bootstrap.
- `main@f3489b6` — same.
- `develop@85be40e` — GIM-54 squash-merge (the last slice run under split-mainline rules).

**Scope:** change `CLAUDE.md`, `paperclips/fragments/shared/fragments/*.md`, a few role files, deploy the new fragment bundle, adjust GitHub branch protection. Zero product code touched.

## 1. Context — what today's session exposed

`GIM-54` (git-mcp read-only exposure) went green end-to-end in ~2h40m. During the pipeline and the subsequent reconciliation, five concrete failures surfaced — each mapping to a structural gap in the current workflow:

1. **Stale CTO checkout (08:17).** CTO reported `main@98c89a7`, `develop@e629d97` — days stale. He escalated `@Board blocked: artifacts don't exist on main`. Root cause: per-issue worktree reuses the parent clone's fetch state; nobody ran `git fetch origin` at the start of his run.

2. **CTO can't do Phase 1.1 mechanics (08:22).** `cto-no-code-ban.md` forbids `git commit` / `git push` / `Edit` / `Write`. Mechanical plan rename (`GIM-NN` → `GIM-54` in one file, one commit, one push) was outside CTO's allowed toolbox. He had to create sub-issue `0346aa96` and hand off to PythonEngineer. Same ceremony repeated at `2be99875` for the CR-finding rev. +2 paperclip issues per slice purely for mechanical rename/edit of meta-docs.

3. **Board bypasses `no-direct-push-to-main` rule (~10:05, ~10:30).** GitHub: `Bypassed rule violations for refs/heads/main: 4 of 4 required status checks are expected`. Twice in one session: pushing spec+plan commits to main, and pushing the reconcile merge. Branch-protection rule exists but admin-override is honored. Board never goes through PR. 535-line spec merged without a single independent reviewer on the PR path — mechanism had to be improvised (independent reviewer reached via a separate Claude Code session as a one-off).

4. **Ghost runs after async waits (~10:30-10:58).** MCPE finished QA Phase 4.1 handoff → opened a run → did nothing visible → closed. Again after opening PR → his run ended "waiting for CI" → CI completed in ~1 min → nobody told him → he sat closed. Twice waking him manually via `release + reassign` dance to unstick progress. Each wait between phases = 1 operator-side poll.

5. **Plans on two branches (pre-reconcile).** Plan file `2026-04-19-GIM-54-git-mcp-read-only.md` lived simultaneously on `main` (via Board push: `e3dc359` → `66cdcae` → `623b275`) and on feature branch (via `c8b52dc chore(plan): copy plan to feature branch`). Same logical artifact, two write-paths, non-zero risk of divergence if Board edits main while MCPEngineer edits the feature branch.

**Root cause, one sentence:** workflow rules live in a shared fragment that agents follow, but **Board (human operator + Claude Code session) is outside the fragment system**, and CLAUDE.md's `Branch Flow` section actively describes a *different* flow — direct commits to main for meta. The two authorities contradict each other.

## 2. Goal

After this slice:

- **develop = single mainline.** Everything (code + spec + plan + research + postmortem) flows into develop through feature branches.
- **main = stable release mirror.** Updated exclusively via `git merge --ff-only origin/develop` (only when explicitly cutting a release). No direct pushes, ever.
- **Board uses the same flow as agents.** Specs and plans are committed on a feature branch, pushed, reviewed via PR (by CR + Opus if the slice is non-trivial).
- **CTO can commit meta-docs** (plan renames, rev-updates) on the slice's feature branch — narrow, explicit exemption to `cto-no-code-ban.md` scoped to doc files under `docs/superpowers/**` and `docs/runbooks/**`. Still cannot touch code.
- **Fresh-fetch discipline enforced** at start of every run: `git fetch origin` before anything else.
- **Admin-override off on `main` and `develop`.** All merges go via PR with all 4 CI checks green; no bypass.

**Success criterion.** After this slice merges:
1. `CLAUDE.md` Branch Flow section rewritten to match `git-workflow.md` — no contradiction between them.
2. Any new slice (GIM-N+1) started after this merge does **not** direct-push anything to main; spec + plan live on `feature/GIM-(N+1)-*` from commit #1.
3. CTO of GIM-N+1 runs `git mv` + `git commit` + `git push` on the feature branch at Phase 1.1 without creating a sub-issue.
4. Attempted `git push origin main` (direct) from any session fails with branch-protection error — no admin-bypass.
5. MCPEngineer role file carries a `ci-wait` discipline note (not full solution — out of scope, just a placeholder flag).

## 3. Architecture — changes, minimal

### 3.1 `CLAUDE.md` Branch Flow rewrite

**Replace** the current section:

```md
## Branch Flow

feature/* → develop (PR, CodeReviewer sign-off required)
develop → main (release PR, CTO approval required)

Rules:
- All work in feature branches cut from develop
- PRs open against develop, never main
- main holds meta (specs, plans, research, postmortems); develop holds product code + plan-files
- Force-push to main/develop is forbidden
- No admin CI override on merge
```

**With**:

```md
## Branch Flow

Single mainline: `develop`. Feature branches cut from develop, PR'd back.
`main` is a downstream release-stable mirror.

```
feature/GIM-N-<slug>    (all work: code, spec, plan, research, docs)
      │
      ▼  PR → squash-merge (after CI green + CR approve + QA evidence)
develop                   (integration tip, iMac deploys from here)
      │
      ▼  git merge --ff-only origin/develop   (only at release cuts)
main                      (stable release ref — tags live here)
```

**Iron rules:**
- Every change — product code, spec, plan, research, postmortem, role-file edit, CLAUDE.md change — goes through a feature branch + PR. Zero direct commits to `develop` or `main`.
- Force push forbidden on `develop` / `main`; on feature branches only `--force-with-lease`.
- Branch protection: admin-bypass disabled. All 4 CI checks must be green for PR merge.
- Feature branches live in paperclip-managed worktrees; primary repo stays on `develop`.
- `main` never receives a PR. It follows `develop` via fast-forward merge, manual at release cuts.

**Spec + plan location:** `docs/superpowers/specs/` and `docs/superpowers/plans/` on the feature branch. After squash-merge, they land on develop. Main gets them when release catches up.
```

### 3.2 `paperclips/fragments/shared/fragments/git-workflow.md` — reinforce + add fetch discipline

**Append** to existing fragment:

```md
### Fresh-fetch on wake

Before any `git log` / `git show` / `git checkout` in a new run:

```bash
git fetch origin --prune
```

Parent clone is shared across worktrees; a stale parent means stale `origin/*` refs for every worktree on the same host. A single `fetch` updates all. Skip this and you will chase artifacts "not found on main" when they're pushed but uncached locally.

### What applies to Board, too

This fragment binds **all writers** to the repo — agents, Board session, human operator. When Board writes a spec or plan, it goes on a feature branch. When Board pushes, it's via `git push origin feature/...`, then PR. No exceptions for "meta-only" or "docs-only" pushes.
```

### 3.3 `paperclips/fragments/shared/fragments/cto-no-code-ban.md` — narrow exemption

**Replace**:

```md
- **DO NOT run** `git commit`, `git push`, `git checkout -- <file>`, `git stash`, `git worktree`.
- **DO NOT use** `Edit`, `Write`, `NotebookEdit`, `git apply` tools. Your only write tools: comments in the Paperclip API + issue updates via API.
```

**With**:

```md
- **DO NOT run** `git checkout -- <file>` (discard WD changes), `git stash`, `git worktree add/remove`.
- **DO NOT use** `Edit`, `Write`, `NotebookEdit` tools on files under `services/`, `tests/`, `src/`, or any path outside `docs/` and `paperclips/roles/`. Code is engineer turf.
- **MAY run** `git commit` / `git push` / `git mv` / `Edit` / `Write` **only** when modifying files under `docs/superpowers/**` or `docs/runbooks/**` on a feature branch (Phase 1.1 mechanical work: plan renames, GIM-NN placeholder swaps, rev-updates to address CR findings). Never on `develop` / `main` directly.
```

Rationale: Phase 1.1 is inherently mechanical meta-doc edit. The ban was overloaded — guarding both against "CTO writes code" (correct) and "CTO commits anything" (over-broad). Narrowed to the safe intent.

### 3.4 `paperclips/fragments/shared/fragments/phase-handoff.md` — Phase 1.1 no longer requires sub-issue

**Replace** the `Handoff matrix` row:

```md
| 1.1 Formalization (CTO) | 1.2 Plan-first review | `assignee=CodeReviewer` + @CodeReviewer |
```

**With** (more specific):

```md
| 1.1 Formalization (CTO) | 1.2 Plan-first review | CTO does `git mv` / rename / GIM-NN swap **on the feature branch directly** (no sub-issue), pushes, then `assignee=CodeReviewer` + @CodeReviewer. Sub-issues for Phase 1.1 mechanical work are anti-pattern — see `cto-no-code-ban.md` narrowed scope. |
```

### 3.5 `paperclips/roles/cto.md` — align with narrowed ban

Remove or rewrite the paragraph:

> If you catch yourself opening Edit/Write tool — that's a behavior bug, stop immediately: "Caught myself trying to write code. Block me or give explicit permission."

Replace with scoped version:

> If you catch yourself opening Edit/Write tool on files under `services/`, `tests/`, `src/`, or outside `docs/` / `paperclips/roles/` — that's a behavior bug, stop immediately and escalate. Edit/Write on `docs/superpowers/**` and `docs/runbooks/**` for Phase 1.1 mechanical work is allowed and expected.

### 3.6 `paperclips/roles/mcp-engineer.md` — placeholder `ci-wait` note

Add a short section (`## Waiting for CI`):

> After `git push origin feature/...`, CI triggers automatically. Do not end your run until CI reports all 4 checks completed. Use `gh pr checks <PR#> --watch` (blocks until checks resolve, budget ~3 min on this repo). If `--watch` exceeds 5 min, fall back to `gh pr checks <PR#>` poll every 30 s up to a 10 min total budget, then post a status comment and end the run for a Board re-prod. Do **not** post `Phase 4.2 in progress — waiting for CI` and terminate silently — that produces ghost runs.

Full CI-feedback solution is a separate slice (async-signal-integration); this is a defensive placeholder.

### 3.7 GitHub branch protection — tighten

On `github.com/ant013/Gimle-Palace`, update branch-protection rules for `main` and `develop`:

- `Require status checks to pass before merging` ← already on; enforce for admins too (`Do not allow bypassing the above settings` ← currently unchecked; flip it).
- `Require pull request reviews before merging` ← at least 1 approval on `develop` (for CR); on `main` — same (for release cuts).
- `Restrict who can push to matching branches` ← only the merge-bot / GitHub's internal merge mechanism, no humans.

Implementation: `gh api -X PUT /repos/ant013/Gimle-Palace/branch-protection/main` with the updated protection rules, same for develop.

## 4. Out of scope

- **CI-feedback loop / async signal integration.** Making agents automatically know when CI completes (webhooks, `gh pr checks --watch` full-treatment, paperclip-side notifier). Separate slice. This one adds only a placeholder note in MCPE role.
- **Paperclip per-issue auto-`git fetch origin` on worktree creation.** Upstream paperclip change. Our slice just documents the "run `git fetch` on wake" expectation; infra followup.
- **Full Board role fragment.** Board (human operator + Claude Code session) behavior is defined in this spec and in CLAUDE.md, but is not yet its own fragment/role file. If a second operator joins, formalize then.
- **`main` retirement.** If at some point `main` becomes pure dead weight (nothing consumes release refs), remove it. Not now — keeps release-pinning option open.
- **Retroactive cleanup of old specs/plans** on main's history. Already on develop via reconcile merge `f3489b6`. History of main pre-reconcile stays as-is — no rewriting.

## 5. Acceptance criteria

- [ ] CLAUDE.md Branch Flow section rewritten per §3.1; no contradiction with `git-workflow.md`.
- [ ] `git-workflow.md` has the `Fresh-fetch on wake` and `What applies to Board, too` sections.
- [ ] `cto-no-code-ban.md` allows `Edit` / `Write` / `git commit` / `git push` on `docs/superpowers/**` and `docs/runbooks/**` only, explicitly on feature branches.
- [ ] `phase-handoff.md` Phase 1.1 row updated — CTO does rename itself, no sub-issue.
- [ ] `paperclips/roles/cto.md` scoped behavior-bug-check.
- [ ] `paperclips/roles/mcp-engineer.md` has `## Waiting for CI` placeholder section.
- [ ] `deploy-agents.sh` run against all 11 agents — all of them have the new fragment bundle (verify via one agent: `docker exec ... cat /path/to/AGENTS.md | head -20`).
- [ ] GitHub branch-protection on `main` and `develop`: admin-bypass disabled. Verify by attempting direct `git push origin main` from any clone → rejected.
- [ ] This slice's own spec + plan live on `feature/meta-workflow-migration`, merged into develop via a PR (not direct-pushed to main). Serves as the first reference implementation of the new flow.
- [ ] Submodule `paperclips/fragments/shared` bumped to a new tag/commit containing the updated fragments.

## 6. Risks

1. **CTO accidentally edits code.** Narrowed ban still forbids code files; if CTO violates, that's a regular incident, handled by PR review + CR rejecting the PR. Low blast radius (feature branch, not merged).
2. **Board human momentum — operator pushes to develop out of habit.** Branch-protection makes it fail hard, which is the right failure. Small friction, one-time learning.
3. **Agents' existing worktrees from before this slice** may persist under old fragment bundle. `deploy-agents.sh` run post-merge + `POST /api/agents/<id>/reload` or similar re-pulls the AGENTS.md bundle; may need a paperclip restart.
4. **`gh pr checks --watch` ties up a run for 2-10 min** — burns tokens. Placeholder note only; full solution is a separate slice.
5. **Release cut to main becomes manual and forgettable.** We don't currently need a release ref (no external consumers tracking `main`); not-releasing is low-cost. If it becomes a real need, automate separately.

## 7. Decomposition (plan-first ready)

Expected plan file: `docs/superpowers/plans/2026-04-19-GIM-NN-meta-workflow-migration.md` on this same feature branch. CTO swaps `GIM-NN` during Phase 1.1.

| Phase | Step | Owner | Description |
|---|---|---|---|
| 1.1 | 1.1.1 | CTO | Rename plan file: `GIM-NN` → `GIM-<this issue>`. Swap in-body placeholders. Commit + push **on feature branch** (first use of newly-allowed mechanical permission). |
| 1.1 | 1.1.2 | CTO | Handoff to CR with PR-preview link. |
| 1.2 | 1.2.1 | CodeReviewer | Plan-first review. Verify every §5 acceptance criterion maps to a Phase 2 task. APPROVE or findings. |
| 2 | 2.1 | TechnicalWriter | Rewrite `CLAUDE.md` Branch Flow section per §3.1. |
| 2 | 2.2 | TechnicalWriter | Append `git-workflow.md` per §3.2. |
| 2 | 2.3 | TechnicalWriter | Rewrite `cto-no-code-ban.md` per §3.3. |
| 2 | 2.4 | TechnicalWriter | Update `phase-handoff.md` Phase 1.1 row per §3.4. |
| 2 | 2.5 | TechnicalWriter | Update `cto.md` scoped behavior check per §3.5. |
| 2 | 2.6 | TechnicalWriter | Update `mcp-engineer.md` `Waiting for CI` placeholder per §3.6. |
| 2 | 2.7 | InfraEngineer | In `paperclip-shared-fragments` submodule: push the fragment updates, bump ref in Gimle `paperclips/fragments/shared`. Run `./paperclips/build.sh` to refresh role bundles in `dist/`. |
| 2 | 2.8 | InfraEngineer | Run `./paperclips/deploy-agents.sh` to push new bundles to all 11 agents. Verify on 1 agent: `cat AGENTS.md` matches new content. |
| 2 | 2.9 | InfraEngineer | Update GitHub branch-protection on `main` and `develop` to disable admin-bypass + require all 4 checks green. Test: `git push origin main` direct attempt → rejected. |
| 3.1 | 3.1 | CodeReviewer | Mechanical: `ruff` / `mypy` not applicable (no code); check CLAUDE.md renders, fragments don't contain syntax errors, deploy-agents output matches expected. |
| 3.2 | 3.2 | OpusArchitectReviewer | Adversarial: corner cases — what if a Medic project also uses the submodule? What if an in-flight paperclip slice starts mid-migration? How do operators roll back this migration if it breaks agent behavior? |
| 4.1 | 4.1 | QAEngineer | Dogfood Phase 4.1: cut a dummy `feature/GIM-NN+1-smoke` from develop, commit a test change, push, verify branch protection blocks direct push to develop + main. Roll back dummy branch + issue. Evidence comment with the pushed commits / blocked-push log. |
| 4.2 | 4.2 | CTO | Squash-merge this feature branch to develop via PR. After merge, operator runs `git switch main && git merge --ff-only origin/develop && git push origin main` manually — last time a human will push to main under old-style privilege (tests that the new protection allows this specific fast-forward). If FF is also blocked, we know to script release cuts through PR as well. |

## 8. Size estimate

- Fragment + CLAUDE.md + role file edits: ~250 LOC of prose.
- `deploy-agents.sh` run: automation.
- Submodule PR on `paperclip-shared-fragments`: separate, ~30 LOC.
- 2 PRs (this slice + shared-fragments).
- Duration: ~0.5 day agent-time.

## 9. Followups

- **CI-feedback slice** (async signal integration). After this lands, MCPE's `Waiting for CI` placeholder needs a real implementation: either paperclip-side GitHub webhook consumer, or an agent-side bounded `gh pr checks --watch` with budget, or a third pattern. Scope depends on paperclip upstream capabilities.
- **Retire `main`** once pattern is settled and it's clearly unused. If we don't cut releases in 30 days, remove it.
- **Operator cheat-sheet** in `docs/runbooks/` explaining the new flow for humans (what to do when you open a Claude Code session to write a spec).
- **`paperclip-shared-fragments` CI** — today it doesn't seem to run CI on the submodule repo itself. Adding a lint on markdown fragments (validate headers, link checks) would reduce drift.

## 10. Pinning — note on meta

This spec lives on `feature/meta-workflow-migration`, NOT on `main`. This is intentional and self-referential: under the old flow this spec would have been pushed to main directly. Under the new flow (defined by this spec) it lives on a feature branch. That was the plan: the first slice under the new flow is the one that defines the new flow.
