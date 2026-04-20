# Meta-workflow migration — feature-branch flow as single source of truth

**Date:** 2026-04-19 (rev2 — post independent review)
**Slice:** Meta-workflow-migration (next after GIM-54)
**Author:** Board (operator-driven)
**Status:** Awaiting formalization (Phase 1.1)
**Branch:** `feature/GIM-57-meta-workflow-migration` (this spec lives on the feature branch — first slice to follow the new flow it defines)
**Predecessors pinned:**
- `develop@f3489b6` — reconcile merge (main → develop). main and develop pointed at same tip for the first time since bootstrap.
- `main@f3489b6` — same.
- `develop@85be40e` — GIM-54 squash-merge (the last slice run under split-mainline rules).

**Rev 2 delta:** adds QA-evidence gate (§3.8), CR GitHub-approval bridge (§3.9), release-cut Action (§3.10), rollback runbook (§11). Fixes ordering bug between branch-protection rollout and final FF push. Replaces active-polling CI-wait placeholder with "end run with marker" formalization. Clarifies Board checkout location. Addresses 13 findings from independent review.

**Scope:** changes to `CLAUDE.md`, `paperclips/fragments/shared/fragments/*.md`, a few role files, new `.github/workflows/*.yml` automations, branch-protection config. No application code touched; meta-doc + role-behavior changes with an 11-agent deploy radius.

## 1. Context — what today's session exposed

`GIM-54` (git-mcp read-only exposure) went green end-to-end in ~2h40m. During the pipeline and the subsequent reconciliation, five concrete failures surfaced — each mapping to a structural gap:

1. **Stale CTO checkout (08:17).** CTO reported `main@98c89a7`, `develop@e629d97` — days stale. He escalated `@Board blocked: artifacts don't exist on main`. Root cause: per-issue worktree reuses the parent clone's fetch state; nobody ran `git fetch origin` at the start of his run.

2. **CTO can't do Phase 1.1 mechanics (08:22).** `cto-no-code-ban.md` forbids `git commit` / `git push` / `Edit` / `Write`. Mechanical plan rename (`GIM-NN` placeholder → `GIM-54` in one file, one commit, one push) was outside CTO's allowed toolbox. He created sub-issue `0346aa96` and handed to PythonEngineer. Same ceremony repeated at `2be99875` for CR-rev. +2 paperclip issues per slice purely for mechanical doc-edit.

3. **Board bypasses no-direct-push rule (~10:05, ~10:30).** GitHub: `Bypassed rule violations for refs/heads/main: 4 of 4 required status checks are expected`. Twice: pushing spec+plan commits, and pushing reconcile merge. Branch-protection rule exists but admin-override is honored. Board never goes through PR.

4. **Ghost runs after async waits (~10:30-10:58).** MCPE finished QA handoff → opened a run → no visible work → closed. Again after opening PR → run ended "waiting for CI" → CI completed in ~1 min → nobody told him → closed. Twice woken manually via `release + reassign`.

5. **Plans on two branches (pre-reconcile).** Plan file `2026-04-19-GIM-54-git-mcp-read-only.md` lived on main (Board: `e3dc359` → `66cdcae` → `623b275`) and on feature branch (`c8b52dc chore(plan): copy plan to feature branch`). Same logical artifact, two write-paths, divergence risk.

**GIM-48 vectors closed by this slice (2 of 3):**
- ✅ Admin-bypass on merge → §3.7 + §3.10
- ✅ Direct-push-to-main gap → §3.1 + §3.10 (release automation)
- ✅ QA-evidence as enforceable gate → §3.8 (new in rev2)
- ⚠ Mocked-substrate test-design — **explicit out of scope**, separate slice (test-design-discipline).

**Root cause, one sentence:** workflow rules live in a shared fragment that agents follow, but Board is outside the fragment system, and CLAUDE.md's `Branch Flow` describes a *different* flow (direct-to-main for meta). The two authorities contradict each other.

## 2. Goal

After this slice:

- **develop = single mainline.** Everything (code + spec + plan + research + postmortem) flows into develop through feature branches.
- **main = optional release ref.** Follows develop via automated fast-forward (GitHub Action triggered by label `release-cut`). Never receives a direct human push. If never labeled, main drifts behind and that's OK — release-ref is optional. May retire entirely (§9 followup).
- **Board uses the same flow as agents.** Specs and plans committed on a feature branch, pushed, reviewed via PR.
- **CTO can commit meta-docs** on feature branches — narrow exemption to `cto-no-code-ban.md` scoped to `docs/superpowers/**` and `docs/runbooks/**` only. Still forbidden from code.
- **QA evidence is a required check.** GitHub Action scans PR body for `## QA Evidence` section with SHA + evidence links; missing → check fails → merge blocked.
- **CR GitHub-review bridges paperclip-approve to merge gate.** CR posts `gh pr review --approve --body "<compliance>"` at end of Phase 3.1 run, alongside paperclip compliance comment.
- **Fresh-fetch on wake** enforced in fragment (immediate); environment-level hook followup.
- **Admin-override off on `main` and `develop`.** Enabled at the very end of migration (§7 Phase 4.3), after the last direct FF push main catch-up.

**Success criterion.** After this slice merges:
1. `CLAUDE.md` Branch Flow rewritten to match `git-workflow.md` — no contradiction.
2. Any new slice started after this merge does NOT direct-push anything to main. Spec + plan live on `feature/GIM-(N+1)-*` from commit #1.
3. CTO of next slice runs `git mv` + `git commit` + `git push` on feature branch at Phase 1.1 without creating a sub-issue.
4. Attempted `git push origin main` (direct, non-Action) from any clone → rejected by branch-protection.
5. PR without `## QA Evidence` section → `qa-evidence-present` check FAIL → merge blocked.
6. CR's paperclip compliance comment is mirrored as a GitHub PR review (Approve) before merge.
7. Label `release-cut` on a PR (or dedicated workflow dispatch) → main fast-forwards to develop automatically via Action.

## 3. Architecture — changes, minimal

### 3.1 `CLAUDE.md` Branch Flow rewrite

**Replace** the current section with:

```md
## Branch Flow

Single mainline: `develop`. Feature branches cut from develop, PR'd back.
`main` is an optional release-stable reference.

```
feature/GIM-N-<slug>    (all work: code, spec, plan, research, docs)
      │
      ▼  PR → squash-merge (CI green + CR paperclip APPROVE + CR GitHub review + QA evidence present)
develop                   (integration tip, iMac deploys from here)
      │
      ▼  .github/workflows/release-cut.yml (triggered by `release-cut` label on a PR, or manual workflow_dispatch)
main                      (stable release ref — tags live here)
```

**Iron rules:**
- Every change — product code, spec, plan, research, postmortem, role-file edit, CLAUDE.md change — goes through a feature branch + PR. Zero direct human commits to `develop` or `main`.
- Force push forbidden on `develop` / `main`; on feature branches only `--force-with-lease` AND only when you are the sole writer of the current phase (if QA is adding evidence-docs to the same branch, coordinate first).
- Branch protection on develop + main: admin-bypass disabled. All required checks must pass for PR merge.
- `main` never receives a direct push. Updates only via `release-cut.yml` Action (runs as GitHub bot).
- Feature branches live in paperclip-managed worktrees; primary repo stays on `develop`.
- Operator/Board checkout: **separate clone**, typically `~/<project>-board/` or `~/Android/<project>/`. Never use the production deploy checkout (`/Users/Shared/Ios/<project>/`) for spec/plan writing.

**Spec + plan location:** `docs/superpowers/specs/` and `docs/superpowers/plans/` on the feature branch. After squash-merge, they land on develop. Main gets them only when release-cut Action runs.

**This PR (meta-workflow-migration) is reviewed under old-flow rules** (direct-push possible; CR approves via paperclip comment without GitHub review gate). New-flow rules start effectively with the first merge AFTER this PR. During migration itself there will be one last legitimate state where protection is partially off — see migration plan §7 Phase 4.3.
```

### 3.2 `paperclips/fragments/shared/fragments/git-workflow.md` — reinforce + fetch + force discipline

**Append** to existing fragment:

```md
### Fresh-fetch on wake

Before any `git log` / `git show` / `git checkout` in a new run:

```bash
git fetch origin --prune
```

Parent clone is shared across worktrees; a stale parent means stale `origin/*` refs for every worktree on the host. A single `fetch` updates all. Skip this and you will chase artifacts "not found on main" when they are pushed but uncached locally.

This is a **compensation control** (agent remembers). An environment-level hook (paperclip worktree pre-wake fetch or a `deploy-agents.sh` wrapper) is a followup — until it lands, the fragment rule is load-bearing.

### Force-push discipline on feature branches

- `--force-with-lease` allowed on **feature branches only**.
- Use `--force-with-lease` ONLY when:
  1. You have fetched immediately prior (`git fetch origin`).
  2. You are the **sole writer** of the current phase (no parallel QA evidence, no parallel CR-rev from another agent).
- Multi-writer phases (e.g., QA adding evidence docs alongside MCPE's impl commits): regular `git push` only, and rebase-then-push instead of force.
- Force-push on `develop` / `main` — forbidden, always. Protection will reject; don't retry with `--force`.

### What applies to Board, too

This fragment binds **all writers** — agents, Board session, human operator. When Board writes a spec or plan, it goes on a feature branch. Board checkout location: separate clone per `CLAUDE.md § Branch Flow`. When Board pushes, it's to `feature/...` then PR — never `main` or `develop` directly.
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
- **MAY run** `git commit` / `git push` / `git mv` / `Edit` / `Write` **only** when modifying files under `docs/superpowers/**` or `docs/runbooks/**` **on a feature branch** (Phase 1.1 mechanical work: plan renames, GIM-57 placeholder swaps, rev-updates to address CR findings). Never on `develop` / `main` directly.
```

### 3.4 `paperclips/fragments/shared/fragments/phase-handoff.md` — Phase 1.1 no longer requires sub-issue

**Replace** the row:

```md
| 1.1 Formalization (CTO) | 1.2 Plan-first review | `assignee=CodeReviewer` + @CodeReviewer |
```

**With**:

```md
| 1.1 Formalization (CTO) | 1.2 Plan-first review | CTO does `git mv` / rename / GIM-57 swap **on the feature branch directly** (no sub-issue), pushes, then `assignee=CodeReviewer` + @CodeReviewer. Sub-issues for Phase 1.1 mechanical work are anti-pattern per narrowed `cto-no-code-ban.md`. |
```

### 3.5 `paperclips/roles/cto.md` — align with narrowed ban

Remove/rewrite:

> If you catch yourself opening Edit/Write tool — that's a behavior bug, stop immediately: "Caught myself trying to write code. Block me or give explicit permission."

Replace with scoped:

> If you catch yourself opening Edit/Write tool on files under `services/`, `tests/`, `src/`, or outside `docs/` / `paperclips/roles/` — that's a behavior bug, stop immediately and escalate. Edit/Write on `docs/superpowers/**` and `docs/runbooks/**` for Phase 1.1 mechanical work is allowed and expected.

### 3.6 `paperclips/roles/mcp-engineer.md` — CI-wait: end run with explicit marker

Add section (`## Waiting for CI — do not active-poll`):

> After `git push origin feature/...` at Phase 2→3.1, Phase 3.1 re-push, or Phase 4.2 PR-merge attempt, CI triggers automatically. Two options:
>
> 1. **Post a CI-pending marker and end run** (default, zero token cost during wait):
>    ```
>    ## CI pending — awaiting Board re-wake
>    PR: <link>
>    Commit: <sha>
>    Expected green: lint, typecheck, test, docker-build (4 checks).
>    Re-wake me (@MCPEngineer) when all 4 green to continue Phase 4.2 merge.
>    ```
>    Board re-wakes via `release + reassign` when CI reports green. You resume from the merge step.
>
> 2. **Bounded active poll** (only if urgency justifies token burn — e.g., production hotfix): `gh pr checks <PR#> --watch` blocks up to 3 min; if not complete, poll `gh pr checks <PR#>` every 60 s up to 5 min total, then fall to option 1 with pending marker.
>
> Do NOT post `Phase 4.2 in progress — waiting for CI` and terminate silently with no re-wake marker — that produces ghost runs (MCPE's state machine pending forever).
>
> A full async-signal integration (paperclip CI webhook → automatic agent wake on green) is a followup slice.

### 3.7 GitHub branch protection — tighten (timing matters)

> ⚠ **SUPERSEDED 2026-04-20 (GIM-60 retrofit).** Two flaws discovered during GIM-59 merge:
>
> 1. `Require pull request reviews before merging` on develop is **structurally unsatisfiable** under single-token reality — every Gimle agent AND Board share the same GitHub token (`ant013`), so self-approve always returns GitHub 422. Rule removed 2026-04-20. See `feedback_single_token_review_gate.md`.
> 2. Required context `qa-evidence-present` is the workflow name; GitHub matches by **check-run name** = job name, which is `check` in `qa-evidence-check.yml`. Required context changed to `check`.
> 3. `Restrict who can push to matching branches` on main with `apps: ["github-actions"]` is **org-only**; GitHub 422 on personal repo. Dropped.
>
> Live branch-protection as of 2026-04-20 matches `.github/branch-protection/develop.json` + `main.json` in the repo (retrofit by GIM-60 from the stale config this section originally described). Read those files for ground truth, NOT the text below.

On `ant013/Gimle-Palace`, update branch-protection rules for `main` and `develop`:

- `Require status checks to pass before merging` — enforce for admins (`Do not allow bypassing the above settings` ← flip to on). Checks required: `lint`, `typecheck`, `test`, `docker-build`, `qa-evidence-present` (new, §3.8).
- `Require pull request reviews before merging` on `develop` — at least 1 approval from CR's GitHub account (see §3.9).
- `Restrict who can push to matching branches` on `main`: only `github-actions[bot]` (for release-cut Action) — all humans blocked.
- On `develop`: no humans direct-push; merge via PR only.

**Critical timing:** these rules are enabled in Phase 4.3, **after** the migration-slice PR itself is merged, and after an optional one-time FF of main → develop is performed manually under old rules (§7 Phase 4.3 Task 4.3.1). Enabling earlier would block the migration slice from merging at all.

Implementation: `gh api -X PUT /repos/ant013/Gimle-Palace/branches/develop/protection` with JSON config committed in `.github/branch-protection/develop.json` (and `main.json`) for reproducibility and rollback.

### 3.8 NEW — QA-evidence required check

New file `.github/workflows/qa-evidence-check.yml`:

```yaml
name: qa-evidence-present
on:
  pull_request:
    types: [opened, synchronize, edited, labeled, unlabeled]
    branches: [develop]
jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - name: Verify QA Evidence section
        env:
          BODY: ${{ github.event.pull_request.body }}
          LABELS: ${{ toJson(github.event.pull_request.labels.*.name) }}
        run: |
          if [ "${{ contains(github.event.pull_request.labels.*.name, 'micro-slice') }}" = "true" ]; then
            echo "micro-slice label present — QA evidence waived."
            exit 0
          fi
          if echo "$BODY" | grep -q '^## QA Evidence'; then
            echo "QA Evidence section present."
            # Must contain at least a SHA reference
            echo "$BODY" | awk '/^## QA Evidence/,/^## /' | grep -qE '[0-9a-f]{7,40}' || {
              echo "::error::QA Evidence section has no commit SHA"
              exit 1
            }
            exit 0
          fi
          echo "::error::PR body must contain '## QA Evidence' section (or label 'micro-slice' to waive)"
          exit 1
```

Added to `develop` required status checks in §3.7. MCPE's PR creation template gains `## QA Evidence` stub; QAEngineer fills it during Phase 4.1 by editing the PR body with evidence links and commit SHAs.

**Waiver**: label `micro-slice` (for trivial docs-only PRs) bypasses the QA-evidence check. Use sparingly — default is evidence required.

### 3.9 NEW — CR GitHub-review bridge

> ⚠ **SUPERSEDED 2026-04-20 (GIM-60).** Bridge is structurally unsatisfiable under current setup: CR's GitHub MCP token authenticates as `ant013` — same identity that opens PRs. GitHub returns 422 "Cannot approve your own pull request" regardless of tool (gh CLI or GitHub MCP). Since §3.7 `required_pull_request_reviews` was removed on 2026-04-20, this bridge is also **no longer required** for merging.
>
> Compliance paperclip comment (with full tool output) remains the single CR APPROVE signal. No `gh pr review --approve` step in current flow. If separate GitHub identity (bot account / App installation) is ever provisioned for CR, this bridge becomes viable again and should be re-enabled alongside restoring `required_pull_request_reviews`. Until then, rules here describe a future state, not the active one. See `feedback_single_token_review_gate.md`.

CR's Phase 3.1 role update (`paperclips/roles/code-reviewer.md` or `plan-first-review.md` fragment):

At end of Phase 3.1 APPROVE (after posting paperclip compliance comment with full output paste):

```bash
PR_NUMBER=$(gh pr list --head "$BRANCH" --json number -q '.[0].number')
gh pr review "$PR_NUMBER" --approve --body "Paperclip compliance APPROVE — see paperclip issue $ISSUE_ID comment.

ruff: green
mypy --strict: green
pytest: <N> passed, <M> skipped

Full output in paperclip comment; this GitHub review satisfies branch-protection review requirement."
```

For re-reviews (Phase 3.1 re-review after MCPE addresses findings): `gh pr review --approve` is called again on each iteration after paperclip re-APPROVE.

### 3.10 NEW — Release-cut Action

New file `.github/workflows/release-cut.yml`:

```yaml
name: release-cut
on:
  workflow_dispatch:
  pull_request:
    types: [closed]
    branches: [develop]
jobs:
  cut:
    # Run only if PR was merged AND had 'release-cut' label
    if: |
      github.event_name == 'workflow_dispatch' ||
      (github.event.pull_request.merged == true &&
       contains(github.event.pull_request.labels.*.name, 'release-cut'))
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
          token: ${{ secrets.RELEASE_CUT_TOKEN }}
      - name: Fast-forward main to develop
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git fetch origin develop main
          git checkout main
          git merge --ff-only origin/develop
          git push origin main
          SHA=$(git rev-parse HEAD)
          echo "Released main at $SHA"
```

`RELEASE_CUT_TOKEN` is a PAT with `contents: write` on the repo — added to repo secrets manually. Only this bot can push to `main` (per §3.7 restriction).

Manual release: `gh workflow run release-cut.yml`. Label-triggered: add `release-cut` label to a PR before merge.

## 4. Out of scope

- **CI-feedback loop / async signal integration.** Automatic agent wake on CI completion. Separate slice. This one formalizes `## CI pending` marker pattern (§3.6).
- **Paperclip per-issue auto-`git fetch origin` on worktree creation.** Upstream change. Fragment-level fetch rule (§3.2) covers it until then; realistic local environment-level fix via `deploy-agents.sh` pre-wake hook is 2-4h work (not 1h as initially estimated) and belongs in its own small slice.
- **Full Board role fragment.** Board behavior is in CLAUDE.md + spec + `git-workflow.md`. If a second operator joins, formalize then.
- **`main` retirement.** §9 followup.
- **Retroactive cleanup of old specs/plans on main.** History stays. Already on develop via reconcile.
- **Multi-project submodule drift.** Single-operator today. When Medic or second Gimle project runs concurrent slices touching `paperclip-shared-fragments`, coordination needed. Flag in §9.
- **Test-design discipline** (mocked-substrate vs real-integration rule, GIM-48 vector #3). Separate slice — too large for this one.

## 5. Acceptance criteria

- [ ] CLAUDE.md Branch Flow section rewritten per §3.1; no contradiction with `git-workflow.md`.
- [ ] `git-workflow.md` has `Fresh-fetch on wake`, `Force-push discipline`, `What applies to Board, too`.
- [ ] `cto-no-code-ban.md` allows `Edit` / `Write` / `git commit` / `git push` on `docs/superpowers/**` and `docs/runbooks/**` only, on feature branches.
- [ ] `phase-handoff.md` Phase 1.1 row updated — CTO does rename itself, no sub-issue.
- [ ] `paperclips/roles/cto.md` scoped behavior-bug-check.
- [ ] `paperclips/roles/mcp-engineer.md` has `## Waiting for CI — do not active-poll` with `## CI pending` marker pattern + bounded-poll option.
- [ ] `paperclips/roles/code-reviewer.md` (or `plan-first-review.md` fragment) has `gh pr review --approve` step at Phase 3.1 end.
- [ ] `.github/workflows/qa-evidence-check.yml` present; required on develop branch.
- [ ] `.github/workflows/release-cut.yml` present; tested via `workflow_dispatch` dry-run.
- [ ] `RELEASE_CUT_TOKEN` secret set in repo settings (manual ops step).
- [ ] `paperclips/deploy-agents.sh` run against all 11 agents — all have new fragment bundle. Verify on 2 agents: `diff <(gh api .../agents/<id>/instructions) expected-bundle`.
- [ ] Branch-protection on `develop`: admin-bypass disabled; `qa-evidence-present` required; PR review required (CR GitHub account). Enabled in Phase 4.3 AFTER migration-slice merge.
- [ ] Branch-protection on `main`: admin-bypass disabled; only `github-actions[bot]` can push. Enabled in Phase 4.3.
- [ ] Attempted direct `git push origin main` from any clone → rejected.
- [ ] PR without `## QA Evidence` section and without `micro-slice` label → merge blocked by `qa-evidence-present` check.
- [ ] CR paperclip-APPROVE without subsequent `gh pr review --approve` → merge blocked by "Require PR reviews".
- [ ] Manual `gh workflow run release-cut.yml` → main fast-forwards to develop tip. Verify `git log origin/main -1` == develop HEAD.
- [ ] Submodule `paperclips/fragments/shared` bumped to a new commit containing updated fragments.
- [ ] Rollback runbook exists in `docs/runbooks/2026-04-19-meta-workflow-migration-rollback.md` (§11).

**Agents used:** TechnicalWriter (`0e8222fd-88b9-4593-98f6-847a448b0aab`) and InfraEngineer (`89f8f76b-844b-4d1f-b614-edbe72a91d4b`) — both present in current 11-agent roster per `reference_agent_ids.md`.

## 6. Risks

1. **CTO accidentally edits code.** Narrowed ban still forbids code. CR rejects in review. Low blast radius (feature branch, not merged).
2. **Board human pushes to develop/main out of habit.** Branch-protection (after Phase 4.3) makes it fail hard. One-time learning.
3. **`gh pr review --approve` auth.** If CR's paperclip runtime doesn't have a GitHub token scoped for review-approve, §3.9 fails. Verify in Phase 2.7 with a dry-run on a throwaway PR before enabling the `Require PR reviews` rule.
4. **QA-evidence Action false-positive/negative.** Regex-based SHA detection might miss unconventional SHAs or accept false matches. Start strict (require `[0-9a-f]{7,40}`), refine if genuine need surfaces.
5. **Release-cut token scope too wide.** `RELEASE_CUT_TOKEN` with `contents: write` is a privileged credential. Scope narrowly to single repo; rotate on 90-day schedule.
6. **Existing worktrees persist under old fragment bundle.** `deploy-agents.sh` + paperclip bundle-reload solve it; may need manual paperclip restart. Flag in rollback (§11) for debugging.
7. **Phase 4.3 ordering bug.** If protection is enabled before the final FF on main, we cannot complete the migration. §7 makes protection the **last** step.
8. **CI-pending marker pattern adds operator workload.** Every MCPE phase-transition requires Board to re-wake on CI green. Mitigated by followup (full async-signal slice) and by the fact that we already do this manually on GIM-54 with zero friction.

## 7. Decomposition (plan-first ready)

Expected plan file: `docs/superpowers/plans/2026-04-19-GIM-57-meta-workflow-migration.md` on this same feature branch. CTO swaps `GIM-57` during Phase 1.1.

| Phase | Step | Owner | Description |
|---|---|---|---|
| 1.1 | 1.1.1 | CTO | Rename plan file `GIM-57` → `GIM-<issue>`. Swap placeholders. Commit + push on feature branch (first use of newly-allowed mechanical perm). |
| 1.1 | 1.1.2 | CTO | Handoff to CR with PR-preview link. |
| 1.2 | 1.2.1 | CodeReviewer | Plan-first review. Verify every §5 acceptance criterion maps to a Phase 2 task. APPROVE or findings. |
| 2 | 2.1 | TechnicalWriter | Rewrite `CLAUDE.md` Branch Flow per §3.1 (incl. Board checkout location). |
| 2 | 2.2 | TechnicalWriter | Append `git-workflow.md` per §3.2 (fetch + force + Board). |
| 2 | 2.3 | TechnicalWriter | Rewrite `cto-no-code-ban.md` per §3.3. |
| 2 | 2.4 | TechnicalWriter | Update `phase-handoff.md` Phase 1.1 row per §3.4. |
| 2 | 2.5 | TechnicalWriter | Update `cto.md` scoped behavior-bug-check per §3.5. |
| 2 | 2.6 | TechnicalWriter | Update `mcp-engineer.md` with `## Waiting for CI` pattern per §3.6. |
| 2 | 2.7 | TechnicalWriter | Update `code-reviewer.md` (or `plan-first-review.md`) with `gh pr review --approve` step per §3.9. Dry-run on throwaway PR to verify CR's GitHub token has required scope. |
| 2 | 2.8 | InfraEngineer | Add `.github/workflows/qa-evidence-check.yml` per §3.8. Dry-run on throwaway PR without evidence section → check fails. Add evidence section → check passes. Waive with `micro-slice` label → check passes. |
| 2 | 2.9 | InfraEngineer | Add `.github/workflows/release-cut.yml` per §3.10. Manual create `RELEASE_CUT_TOKEN` secret. Dry-run `gh workflow run release-cut.yml` → verify main FFs (at this stage protection still off, so FF push works). |
| 2 | 2.10 | InfraEngineer | Commit `.github/branch-protection/{develop,main}.json` — config files representing the target rules (not applied yet). |
| 2 | 2.11 | InfraEngineer | Submodule: push fragment updates to `paperclip-shared-fragments`, bump ref in Gimle `paperclips/fragments/shared`. Run `./paperclips/build.sh` to refresh role bundles. |
| 2 | 2.12 | InfraEngineer | Run `./paperclips/deploy-agents.sh` — push new bundles to all 11 agents. Verify 2 agents via API diff. |
| 3.1 | 3.1 | CodeReviewer | Mechanical: markdown-lint (if exists) on changed fragments; YAML schema check on new workflows; compliance table against §5 acceptance. Post paperclip APPROVE + `gh pr review --approve`. |
| 3.2 | 3.2 | OpusArchitectReviewer | Adversarial: what if Medic also uses the submodule? What if in-flight slice starts mid-migration? Is `RELEASE_CUT_TOKEN` scoped tightly? Are there QA-evidence regex false-positive cases? |
| 4.1 | 4.1 | QAEngineer | Dogfood Phase 4.1 (before protection turned on): (a) cut throwaway `feature/GIM-57-smoke-dogfood`, edit any file, commit, push, open PR to develop, attempt merge without `## QA Evidence` — check fails. (b) Add QA Evidence section with SHA — check passes. (c) Verify `gh pr review --approve` is required to merge. (d) Run `gh workflow run release-cut.yml` to FF main. Close dogfood PR without merge. Attach logs/screenshots as this-slice's QA evidence. |
| 4.2 | 4.2 | CTO | Squash-merge this feature branch to develop via PR. CI must include `qa-evidence-present` passing (evidence from 4.1 in this PR's body). |
| **4.3** | 4.3.1 | Operator (Board, manual) | One-time FF: `git switch main && git merge --ff-only origin/develop && git push origin main`. This is the last legitimate direct human push to main, done under old-flow rules before protection tightens. |
| **4.3** | 4.3.2 | InfraEngineer | Apply branch protection: `gh api -X PUT /repos/.../branches/develop/protection -d @.github/branch-protection/develop.json` + same for main. Admin-bypass off. Push restriction: `github-actions[bot]` only for main. |
| **4.3** | 4.3.3 | InfraEngineer | Verification: attempt `git push origin main` directly from a clone → rejected. Attempt `git push origin develop` directly → rejected. `gh pr merge` without QA evidence → blocked. Attach logs as final evidence. |
| **4.3** | 4.3.4 | CTO | Close paperclip issue with merge SHA + `qa-evidence-present` check link + branch-protection config link. |

## 8. Size estimate

- Fragment + CLAUDE.md + role file edits: ~300 LOC of prose.
- 2 new GitHub Actions + 2 branch-protection JSON files: ~80 LOC.
- `deploy-agents.sh` run: automation.
- Submodule PR on `paperclip-shared-fragments`: ~50 LOC.
- Rollback runbook: ~60 LOC.
- 2 PRs (this slice + shared-fragments).
- Duration: ~1 day agent-time (1.5x initial estimate — rev2 scope is larger).

## 9. Followups

- **CI-feedback slice** (async signal integration). Either paperclip webhook consumer for GitHub CI events, or bounded agent-side `gh pr checks --watch` with heartbeat guarantees. Scope depends on paperclip upstream capabilities.
- **Environment-level `git fetch` hook.** Local wrapper in `deploy-agents.sh` or paperclip pre-wake. 2-4h.
- **Retire `main`.** If no release is cut in 30 days post-migration and no external consumer surfaces, remove main. Update CLAUDE.md + workflows.
- **Operator cheat-sheet** in `docs/runbooks/` — new flow for humans opening a Claude Code session.
- **`paperclip-shared-fragments` CI** — markdown lint on fragments, link-check, schema validation.
- **Multi-project submodule coordination.** When concurrent slices in Gimle + Medic both modify shared fragments, need a merge-trains pattern or coordination channel.
- **Test-design discipline** (GIM-48 vector #3). Rule against mocked-substrate tests, mandate real-integration fixture for substrate code.

## 10. Pinning — note on meta

This spec lives on `feature/GIM-57-meta-workflow-migration`, NOT on `main`. This is intentional and self-referential: under the old flow this spec would have been pushed to main directly. Under the new flow (defined by this spec) it lives on a feature branch.

**Transition status — explicit:** This PR is reviewed under **old-flow rules**:
- CR approves via paperclip comment only (no `gh pr review --approve` yet — that's what §3.9 introduces).
- QA-evidence-present check does not yet exist (§3.8 introduces it).
- Branch protection on develop allows admin-bypass (that's what §3.7 closes).

New-flow rules take effect from the **first merge after this one**. Phase 4.3 is the transition point: after this spec merges, operator performs a one-time FF on main, then InfraEngineer tightens branch protection. From that moment, every subsequent PR obeys new rules.

## 11. Rollback procedure

Documented in `docs/runbooks/2026-04-19-meta-workflow-migration-rollback.md` (created as part of Phase 2). Concise version:

```bash
# 1. Rollback branch protection (if migrations Phase 4.3 applied but broke flow)
gh api -X DELETE /repos/ant013/Gimle-Palace/branches/main/protection
gh api -X DELETE /repos/ant013/Gimle-Palace/branches/develop/protection

# 2. Restore pre-migration fragment bundle
cd paperclips/fragments/shared
git checkout <pre-migration-submodule-sha>
cd ../../..
git add paperclips/fragments/shared
git commit -m "rollback: restore pre-migration shared fragments"

# 3. Redeploy old bundle to 11 agents
./paperclips/deploy-agents.sh

# 4. Revert the merge commit on develop
git revert -m 1 <migration-merge-sha>
git push origin develop

# 5. If release-cut already moved main, rewind main via FF-back
#    (only works while main is still a direct parent of the rollback commit)
git switch main
git reset --hard <pre-migration-main-sha>
git push origin main --force-with-lease
# (force-with-lease on main is the escape hatch only during rollback;
#  normal rule still prohibits force on main)

# 6. Disable new workflows
# Remove via: gh api -X DELETE /repos/.../actions/workflows/qa-evidence-check.yml/disable
# (Actually: move the files or add workflow dispatch only conditions. See runbook.)

# 7. Notify all 11 agents via deploy-agents.sh --reload
```

Full procedure (with checklist and verification commands) in the runbook file. Runbook is part of acceptance — spec doesn't merge without it.
