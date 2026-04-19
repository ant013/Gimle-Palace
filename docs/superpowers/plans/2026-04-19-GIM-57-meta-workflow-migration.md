# Meta-workflow migration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-04-19-meta-workflow-migration-design.md` on `feature/GIM-57-meta-workflow-migration` @ `7da9d5d` (rev2).

**Goal:** Close the 3 structural gaps exposed by GIM-54 (stale checkout, Board direct-push to main, ghost runs after async waits) by making every writer (agents + Board) use a single feature-branch flow, enforced by branch protection + GitHub Actions.

**Architecture:** Two new GitHub Actions (qa-evidence-check + release-cut), one narrow relaxation of the CTO no-code ban (scoped to `docs/superpowers/**` and `docs/runbooks/**`), updates to 4 shared fragments + 3 role files + CLAUDE.md. Branch protection on main and develop with admin-bypass disabled, applied **only after** the migration slice itself merges.

**Tech Stack:** GitHub Actions (YAML), `gh` CLI for API calls, bash shell scripts, Markdown for roles/fragments, JSON for branch-protection config.

**Predecessors pinned:**
- `develop@f3489b6` — reconcile merge (main → develop unified).
- `feature/GIM-57-meta-workflow-migration@7da9d5d` — current spec rev2 on this branch.

**Language rule:** code / docstrings / commit messages / YAML / JSON in English; Russian only in UI text (per `language.md` fragment).

**Agents used:** TechnicalWriter (`0e8222fd-88b9-4593-98f6-847a448b0aab`), InfraEngineer (`89f8f76b-844b-4d1f-b614-edbe72a91d4b`) — both extant in 11-agent roster per `reference_agent_ids.md`.

---

## File structure

### New files on this branch (feature/GIM-57-meta-workflow-migration)

```
.github/workflows/qa-evidence-check.yml         # §3.8 — required check
.github/workflows/release-cut.yml               # §3.10 — main FF automation
.github/branch-protection/develop.json          # §3.7 target config (applied in Phase 4.3)
.github/branch-protection/main.json             # §3.7 target config
docs/runbooks/2026-04-19-meta-workflow-migration-rollback.md  # §11 runbook
```

### Modified files in Gimle repo

```
CLAUDE.md                                       # §3.1 Branch Flow section rewrite
paperclips/roles/cto.md                         # §3.5 scoped behavior check
paperclips/roles/mcp-engineer.md                # §3.6 ## Waiting for CI section
paperclips/roles/code-reviewer.md               # §3.9 gh pr review --approve step
paperclips/fragments/shared                     # submodule ref bump (pointer only)
```

### Modified files in paperclip-shared-fragments (submodule, separate repo)

```
fragments/git-workflow.md                       # §3.2 fetch + force + Board
fragments/cto-no-code-ban.md                    # §3.3 narrowed exemption
fragments/phase-handoff.md                      # §3.4 Phase 1.1 row
```

### File responsibility boundaries

- `.github/workflows/qa-evidence-check.yml` — validates PR body has `## QA Evidence` with commit SHA, unless `micro-slice` label.
- `.github/workflows/release-cut.yml` — FF-merges develop into main when triggered by `release-cut` label on a merged PR OR manual `workflow_dispatch`.
- `.github/branch-protection/*.json` — declarative target config; applied via `gh api` in Phase 4.3.
- `docs/runbooks/2026-04-19-meta-workflow-migration-rollback.md` — 7-step reversal if migration breaks flow.
- `CLAUDE.md` — project-level dev guide; holds branch flow iron-rules matching fragments.
- `paperclips/roles/*.md` — per-agent behavior; include shared fragments via `@include`.
- Shared fragments — cross-agent behavior rules; rebuilt into `dist/` by `build.sh`, deployed to 11 agents by `deploy-agents.sh`.

---

## Phase 1 — Formalization

### Task 1.1: CTO formalize (rename GIM-57 to real issue number)

**Owner:** CTO

**Files:**
- Modify: `docs/superpowers/plans/2026-04-19-GIM-57-meta-workflow-migration.md` (rename)

- [ ] **Step 1: Fetch origin first** (compensation control from GIM-54 lesson)

```bash
git fetch origin --prune
git switch feature/GIM-57-meta-workflow-migration
git pull --ff-only
git log --oneline -3    # expect 7da9d5d spec rev2, 794a5ae spec rev1, f3489b6 reconcile
```

- [ ] **Step 2: Create paperclip issue via API**

```bash
set -a; source .env; set +a
COMPANY_ID="9d8f432c-ff7d-4e3a-bbe3-3cd355f73b64"
cat > /tmp/issue-body.json <<'EOF'
{
  "title": "Meta-workflow migration (feature-branch flow, single mainline)",
  "companyId": "9d8f432c-ff7d-4e3a-bbe3-3cd355f73b64",
  "projectId": "e0cd7a7a-910d-4893-8b73-bfa1124ccb8f",
  "assigneeAgentId": "7fb0fdbb-e17f-4487-a4da-16993a907bec",
  "priority": "high",
  "status": "in_progress",
  "description": "## Summary\n\nClose 2 of 3 GIM-48 failure vectors (admin-bypass + QA-evidence-gate). Migrate to single feature-branch flow for all writers. Self-referential: this slice's PR follows old-flow rules; new-flow takes effect from next merge.\n\n## Artifacts\n\n- **Spec:** `docs/superpowers/specs/2026-04-19-meta-workflow-migration-design.md` on `feature/GIM-57-meta-workflow-migration@7da9d5d`\n- **Plan:** `docs/superpowers/plans/2026-04-19-GIM-57-meta-workflow-migration.md` (this file — CTO to rename after creating this issue).\n- **Predecessor:** `develop@f3489b6` (reconcile merge unifying main + develop)\n\n## Phase 1.1 (assignee: CTO)\n\n1. Rename this plan file: `GIM-57` → `GIM-<this issue number>`.\n2. Swap all `GIM-57` in plan body.\n3. Commit + push on `feature/GIM-57-meta-workflow-migration` (first legitimate use of narrowed CTO commit permission).\n4. Reassign to CodeReviewer for Phase 1.2.\n\n## Pipeline\n\n| Phase | Owner | Scope |\n|---|---|---|\n| 1.1 | CTO | Rename plan. |\n| 1.2 | CodeReviewer | Plan-first review. |\n| 2 | TechnicalWriter | §3.1-§3.6, §3.9 doc edits. |\n| 2 | InfraEngineer | §3.7, §3.8, §3.10 workflows + branch-protection JSON. |\n| 3.1 | CodeReviewer | Mechanical review. |\n| 3.2 | OpusArchitectReviewer | Adversarial. |\n| 4.1 | QAEngineer | Dogfood: attempt PR without evidence, verify checks block. |\n| 4.2 | CTO | Squash-merge. |\n| 4.3 | Operator + InfraEng | Final FF, tighten protection, verify blocks. |\n\n## Reminders\n\n- All commits on `feature/GIM-57-meta-workflow-migration`, no direct push to develop/main.\n- CTO Phase 1.1 rename done WITHOUT sub-issue (per new narrowed ban).\n- Submodule `paperclips-shared-fragments` needs its own PR for fragment changes.\n- Rollback runbook `docs/runbooks/2026-04-19-meta-workflow-migration-rollback.md` is part of acceptance.\n\n## Size\n\n~300 LOC prose + ~80 LOC YAML/JSON. 2 PRs (this + shared-fragments). ~1 day agent-time."
}
EOF
RESPONSE=$(curl -sS -X POST -H "Authorization: Bearer $PAPERCLIP_API_KEY" \
  -H "Content-Type: application/json" \
  -d @/tmp/issue-body.json \
  "$PAPERCLIP_API_URL/api/companies/$COMPANY_ID/issues")
ISSUE_ID=$(echo "$RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['id'])")
echo "issue_id: $ISSUE_ID"
```

Note the issue number (CTO records as `GIM-<N>`). Paperclip doesn't auto-number; N is the next-free GIM number visible on paperclip UI (expected GIM-57 after GIM-54 closed).

- [ ] **Step 3: Rename plan file with `git mv` (first narrowed-ban exercise)**

Assuming `N` = 55 (verify on paperclip UI):

```bash
N=55
git mv docs/superpowers/plans/2026-04-19-GIM-57-meta-workflow-migration.md \
       docs/superpowers/plans/2026-04-19-GIM-${N}-meta-workflow-migration.md
```

- [ ] **Step 4: Swap placeholders in plan body**

```bash
sed -i '' "s/GIM-57/GIM-${N}/g" docs/superpowers/plans/2026-04-19-GIM-${N}-meta-workflow-migration.md
```

(Linux: `sed -i "s/.../"` without the empty `''`.)

Verify:

```bash
grep -n 'GIM-57' docs/superpowers/plans/2026-04-19-GIM-${N}-meta-workflow-migration.md || echo 'clean — no GIM-57 left'
```

Expected: `clean — no GIM-57 left`.

- [ ] **Step 5: Commit + push**

```bash
git add -A
git commit -m "docs(plan): rename to GIM-${N} (paperclip issue ${ISSUE_ID})"
git push origin feature/GIM-57-meta-workflow-migration
```

- [ ] **Step 6: Open draft PR (if not yet open)**

```bash
gh pr create --draft --base develop --head feature/GIM-57-meta-workflow-migration \
  --title "Meta-workflow migration (single mainline, GIM-${N})" \
  --body "$(cat <<'EOF'
## Summary

See paperclip issue (link in first comment) + spec at `docs/superpowers/specs/2026-04-19-meta-workflow-migration-design.md`.

## QA Evidence

(To be added in Phase 4.1 by QAEngineer.)

Closes GIM-${N}.
EOF
)"
```

Draft state — CR will review in Phase 1.2; converts to "ready for review" after Phase 3.1 APPROVE.

- [ ] **Step 7: Handoff to CodeReviewer**

POST comment on paperclip issue:

```
## Phase 1.1 complete

- Plan renamed: docs/superpowers/plans/2026-04-19-GIM-57-meta-workflow-migration.md
- Commit: <sha> pushed to feature/GIM-57-meta-workflow-migration
- Draft PR: <link>
- Zero `GIM-57` remain in plan body.

@CodeReviewer your turn — Phase 1.2 plan-first review.
```

Then via API:

```bash
curl -sS -X PATCH -H "Authorization: Bearer $PAPERCLIP_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"assigneeAgentId":"bd2d7e20-7ed8-474c-91fc-353d610f4c52"}' \
  "$PAPERCLIP_API_URL/api/issues/$ISSUE_ID"
```

### Task 1.2: CodeReviewer plan-first review

**Owner:** CodeReviewer

- [ ] **Step 1: Fetch fresh on wake**

```bash
git fetch origin --prune
git switch feature/GIM-57-meta-workflow-migration
git pull --ff-only
```

- [ ] **Step 2: Read spec + plan top-to-bottom**

Files:
- `docs/superpowers/specs/2026-04-19-meta-workflow-migration-design.md`
- `docs/superpowers/plans/2026-04-19-GIM-${N}-meta-workflow-migration.md` (this file)

- [ ] **Step 3: Verify every §5 spec acceptance criterion maps to a Phase 2 or Phase 4 task**

Walk the spec's §5 list (18 items). For each, find the task in this plan. List any gaps.

- [ ] **Step 4: Verify every plan task is concrete**

No "TBD", no "similar to Task X", no "add error handling" without specific code, no references to undefined types.

- [ ] **Step 5: Verify Phase 4.3 ordering correctness**

Critical: Phase 4.3 step 4.3.1 (operator FF) MUST precede step 4.3.2 (apply protection). Otherwise migration fails to merge itself.

- [ ] **Step 6: Post compliance checklist + APPROVE or findings**

Use the CR compliance-table pattern from `plan-first-review.md` fragment. Paperclip comment only (new GitHub-review bridge §3.9 is NOT yet deployed at Phase 1.2 — that's what this slice introduces).

- [ ] **Step 7: Reassign to TechnicalWriter (start Phase 2 doc edits)**

Via paperclip API, `assigneeAgentId=0e8222fd-88b9-4593-98f6-847a448b0aab`.

---

## Phase 2 — Implementation

All Phase 2 work happens on `feature/GIM-57-meta-workflow-migration`. No branch switching mid-phase. Commits can be made by whichever agent is active; the branch tracks the whole slice's history before squash-merge.

### Task 2.1: CLAUDE.md Branch Flow section rewrite

**Owner:** TechnicalWriter

**Files:**
- Modify: `CLAUDE.md` (top section `## Branch Flow`)

- [ ] **Step 1: Replace the Branch Flow section**

Open `CLAUDE.md`. Find the section starting with `## Branch Flow` and ending before `## Docker Compose Profiles`. Replace with:

````markdown
## Branch Flow

Single mainline: `develop`. Feature branches cut from develop, PR'd back.
`main` is an optional release-stable reference.

```
feature/GIM-N-<slug>    (all work: code, spec, plan, research, docs)
      │
      ▼  PR → squash-merge (CI green + CR paperclip APPROVE + CR GitHub review + QA evidence present)
develop                   (integration tip; iMac deploys from here)
      │
      ▼  .github/workflows/release-cut.yml (label `release-cut` on a merged PR, or workflow_dispatch)
main                      (stable release ref — tags live here)
```

**Iron rules:**
- Every change — product code, spec, plan, research, postmortem, role-file, CLAUDE.md itself — goes through a feature branch + PR. Zero direct human commits to `develop` or `main`.
- Force push forbidden on `develop` / `main`; on feature branches only `--force-with-lease` AND only when you are the sole writer of the current phase (see `git-workflow.md` fragment).
- Branch protection on develop + main: admin-bypass disabled. All required checks must pass for PR merge. `main` accepts push only from `github-actions[bot]` via `release-cut.yml`.
- Feature branches live in paperclip-managed worktrees; primary repo stays on `develop`.
- **Operator/Board checkout location:** a separate clone, typically `~/<project>-board/` or `~/Android/<project>/`. Never use the production deploy checkout (`/Users/Shared/Ios/<project>/`) for spec/plan writing.

**Spec + plan location:** `docs/superpowers/specs/` and `docs/superpowers/plans/` on the feature branch. After squash-merge they land on develop. Main gets them only when `release-cut.yml` Action runs.

**Required status checks on develop:**
- `lint`
- `typecheck`
- `test`
- `docker-build`
- `qa-evidence-present` (verifies PR body has `## QA Evidence` with SHA, unless `micro-slice` label)

**CR approval path:** CR posts full compliance comment on paperclip issue AND `gh pr review --approve` on the GitHub PR (the GitHub review satisfies branch-protection's "Require PR reviews" rule).

**Release-cut procedure:** to update `main`:
1. Add label `release-cut` to a merged develop PR, OR
2. Run `gh workflow run release-cut.yml`.

The Action fast-forwards `main` to `origin/develop` using `RELEASE_CUT_TOKEN` (GitHub App or PAT with `contents: write`). No human pushes `main`, ever.

See also:
- `paperclips/fragments/shared/fragments/git-workflow.md` — per-agent rules.
- `docs/runbooks/2026-04-19-meta-workflow-migration-rollback.md` — if branch protection or the new workflows cause a block and need to be reverted.
````

- [ ] **Step 2: Verify CLAUDE.md still valid markdown**

```bash
# Basic sanity — headers still structured, no broken code-fences
python3 -c "import sys; content = open('CLAUDE.md').read(); \
  assert '## Branch Flow' in content; \
  assert content.count('```') % 2 == 0, 'unclosed code fence'; \
  print('OK')"
```

Expected: `OK`.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(CLAUDE): Branch Flow rewrite — single mainline, Board in flow"
```

### Task 2.2: git-workflow.md fragment append

**Owner:** TechnicalWriter

**Files:**
- Modify: `paperclips/fragments/shared/fragments/git-workflow.md` (in submodule)

The submodule `paperclips/fragments/shared` is its own git repo. Edits go on a branch in that submodule repo; the Gimle repo only sees the submodule pointer. Full submodule workflow in Task 2.11.

For THIS task, just edit the file in the worktree; Task 2.11 bundles the submodule-side commit + push.

- [ ] **Step 1: Append new sections**

Open `paperclips/fragments/shared/fragments/git-workflow.md`. Append at the end:

```markdown

### Fresh-fetch on wake

Before any `git log` / `git show` / `git checkout` in a new run:

```bash
git fetch origin --prune
```

Parent clone is shared across worktrees; a stale parent means stale `origin/*` refs for every worktree on the host. A single `fetch` updates all. Skip this and you will chase artifacts "not found on main" when they are pushed but uncached locally.

This is a **compensation control** (agent remembers). An environment-level hook (paperclip worktree pre-wake fetch or a `deploy-agents.sh` wrapper) is a followup — until it lands, this rule is load-bearing.

### Force-push discipline on feature branches

- `--force-with-lease` allowed on **feature branches only**.
- Use it ONLY when:
  1. You have fetched immediately prior (`git fetch origin`).
  2. You are the **sole writer** of the current phase (no parallel QA evidence, no parallel CR-rev from another agent).
- Multi-writer phases (e.g., QA adding evidence-docs alongside MCPEngineer's impl commits): regular `git push` only, and rebase-then-push instead of force.
- Force-push on `develop` / `main` — forbidden, always. Protection will reject; don't retry with `--force`.

### What applies to Board, too

This fragment binds **all writers** — agents, Board session, human operator. When Board writes a spec or plan, it goes on a feature branch. Board checkout location: a separate clone per `CLAUDE.md § Branch Flow`. When Board pushes, it's to `feature/...` then PR — never `main` or `develop` directly.
```

- [ ] **Step 2: Verify markdown balanced**

```bash
python3 -c "c=open('paperclips/fragments/shared/fragments/git-workflow.md').read(); \
  assert c.count('\`\`\`') % 2 == 0, 'unclosed fence'; \
  print('OK')"
```

- [ ] **Step 3: No separate commit yet** — bundled in Task 2.11 submodule push.

### Task 2.3: cto-no-code-ban.md narrowed exemption

**Owner:** TechnicalWriter

**Files:**
- Modify: `paperclips/fragments/shared/fragments/cto-no-code-ban.md`

- [ ] **Step 1: Replace the two relevant bullets**

Open `paperclips/fragments/shared/fragments/cto-no-code-ban.md`.

Replace:

```markdown
- **DO NOT run** `git commit`, `git push`, `git checkout -- <file>`, `git stash`, `git worktree`.
- **DO NOT use** `Edit`, `Write`, `NotebookEdit`, `git apply` tools. Your only write tools: comments in the Paperclip API + issue updates via API.
```

With:

```markdown
- **DO NOT run** `git checkout -- <file>` (discard working-directory changes), `git stash`, `git worktree add/remove`.
- **DO NOT use** `Edit`, `Write`, `NotebookEdit` tools on files under `services/`, `tests/`, `src/`, or any path outside `docs/` and `paperclips/roles/`. Code is engineer turf.
- **MAY run** `git commit` / `git push` / `git mv` / `Edit` / `Write` **only** when modifying files under `docs/superpowers/**` or `docs/runbooks/**` **on a feature branch** (Phase 1.1 mechanical work: plan renames, `GIM-57` placeholder swaps, rev-updates addressing CR findings). Never on `develop` / `main` directly.
```

- [ ] **Step 2: Verify the rest of fragment unchanged**

```bash
grep -c 'DO NOT resurrect' paperclips/fragments/shared/fragments/cto-no-code-ban.md
# Expected: 1 (tail of fragment intact)
```

- [ ] **Step 3: No separate commit yet** — bundled in Task 2.11.

### Task 2.4: phase-handoff.md Phase 1.1 row update

**Owner:** TechnicalWriter

**Files:**
- Modify: `paperclips/fragments/shared/fragments/phase-handoff.md`

- [ ] **Step 1: Replace the Phase 1.1 row**

Open fragment, find row:

```markdown
| 1.1 Formalization (CTO) | 1.2 Plan-first review | `assignee=CodeReviewer` + @CodeReviewer |
```

Replace with:

```markdown
| 1.1 Formalization (CTO) | 1.2 Plan-first review | CTO does `git mv` / rename / `GIM-57` swap **on the feature branch directly** (no sub-issue), pushes, then `assignee=CodeReviewer` + @CodeReviewer. Sub-issues for Phase 1.1 mechanical work are anti-pattern per the narrowed `cto-no-code-ban.md` scope. |
```

- [ ] **Step 2: No separate commit yet** — bundled in Task 2.11.

### Task 2.5: paperclips/roles/cto.md scoped behavior-bug-check

**Owner:** TechnicalWriter

**Files:**
- Modify: `paperclips/roles/cto.md`

- [ ] **Step 1: Find and replace the unscoped behavior-bug-check paragraph**

Open `paperclips/roles/cto.md`. Find:

```markdown
If you catch yourself opening Edit/Write tool — that's a **behavior bug**, stop immediately: *"Caught myself trying to write code. Block me or give explicit permission."*
```

Replace with:

```markdown
If you catch yourself opening `Edit` / `Write` tool on files under `services/`, `tests/`, `src/`, or outside `docs/` / `paperclips/roles/` — that's a **behavior bug**, stop immediately: *"Caught myself trying to write code outside allowed scope. Block me or give explicit permission."*

`Edit` / `Write` on `docs/superpowers/**` and `docs/runbooks/**` for Phase 1.1 mechanical work **is allowed and expected** (plan renames, `GIM-57` swaps, rev-updates to address CR findings). See `cto-no-code-ban.md` narrowed scope.
```

- [ ] **Step 2: Commit**

```bash
git add paperclips/roles/cto.md
git commit -m "docs(cto role): scope behavior-bug-check to exclude docs edits"
```

### Task 2.6: paperclips/roles/mcp-engineer.md `## Waiting for CI` section

**Owner:** TechnicalWriter

**Files:**
- Modify: `paperclips/roles/mcp-engineer.md`

- [ ] **Step 1: Find a sensible place to insert the new section**

Open `paperclips/roles/mcp-engineer.md`. Scroll to near the end, before the final `<!-- @include ... -->` block. Add the section before the fragment includes (so role-specific guidance appears before shared fragments in the rendered bundle).

- [ ] **Step 2: Append the section**

```markdown

## Waiting for CI — do not active-poll

After `git push origin feature/...` at Phase 2→3.1, Phase 3.1 re-push (after CR findings), or Phase 4.2 PR-merge attempt, CI triggers automatically. Choose one of two patterns:

### Pattern 1 (default, zero token cost during wait)

Post a CI-pending marker on the paperclip issue and end your run:

```
## CI pending — awaiting Board re-wake

PR: <link>
Commit: <sha>
Expected green: lint, typecheck, test, docker-build, qa-evidence-present (5 checks).
Re-wake me (@MCPEngineer) when all checks green to continue Phase 4.2 merge.
```

Board re-wakes via `release + reassign` when CI reports green. You resume from the merge step in a fresh run.

### Pattern 2 (bounded active poll — only if urgency justifies token burn)

For hotfixes or when Board is unavailable:

```bash
gh pr checks <PR#> --watch      # blocks up to ~3 min on this repo
```

If not complete within 3 min, fall back to poll:

```bash
for i in $(seq 1 10); do
  sleep 60
  status=$(gh pr checks <PR#> --required | awk '{print $2}' | sort -u)
  if ! echo "$status" | grep -q pending; then break; fi
done
gh pr checks <PR#>
```

Total budget 10 min. Beyond that, fall back to Pattern 1 with a pending marker.

### DO NOT

Post `Phase 4.2 in progress — waiting for CI` and terminate silently **without** a re-wake marker. That produces ghost runs — MCPEngineer's state machine pending forever, Board left guessing if you're working or stuck.

A full async-signal integration (paperclip CI webhook → automatic agent wake on green) is a followup slice.
```

- [ ] **Step 3: Commit**

```bash
git add paperclips/roles/mcp-engineer.md
git commit -m "docs(mcp-engineer role): add Waiting for CI section with marker pattern"
```

### Task 2.7: paperclips/roles/code-reviewer.md — `gh pr review --approve` step + dry-run verify

**Owner:** TechnicalWriter

**Files:**
- Modify: `paperclips/roles/code-reviewer.md`

- [ ] **Step 1: Find the Phase 3.1 mechanical review section**

Open `paperclips/roles/code-reviewer.md`. Locate the Phase 3.1 guidance (currently describes paperclip compliance comment only).

- [ ] **Step 2: Append GitHub-review bridge**

Add after the existing Phase 3.1 description:

```markdown

### Phase 3.1 GitHub PR review bridge

After posting the paperclip compliance comment with full tool output (`ruff check`, `mypy --strict`, `pytest -q`), mirror the approval on the GitHub PR:

```bash
PR_NUMBER=$(gh pr list --head "$BRANCH" --json number -q '.[0].number')
gh pr review "$PR_NUMBER" --approve --body "Paperclip compliance APPROVE — see paperclip issue ${ISSUE_ID} comment ${COMPLIANCE_COMMENT_ID}.

- ruff: green
- mypy --strict: green
- pytest: <N> passed, <M> skipped, <T>s

Full output pasted in the paperclip comment. This GitHub review satisfies branch-protection 'Require PR reviews' rule."
```

**Iteration:** each re-review round (after MCPEngineer addresses findings) runs `gh pr review --approve` again on the new HEAD commit. GitHub retains previous reviews; this adds a fresh approve on the new commit.

**Why both paperclip comment AND GitHub review:**
- Paperclip comment = full output, discoverable by other agents, lives in issue history.
- GitHub review = required by branch-protection "Require PR reviews" (since this slice's §3.7).

If `gh pr review --approve` fails with "insufficient permissions", immediately escalate to Board — CR's `gh` token needs `repo` scope with `review:write`.
```

- [ ] **Step 3: Commit**

```bash
git add paperclips/roles/code-reviewer.md
git commit -m "docs(code-reviewer role): Phase 3.1 GitHub PR review bridge"
```

- [ ] **Step 4: DRY-RUN verification (CR's gh token has review scope)**

Before continuing to Task 2.8, confirm CR can actually `gh pr review --approve`. Run from CR's execution environment (or simulate from operator's with CR's token if convenient):

```bash
# On a throwaway commit in a throwaway PR (can use feature/GIM-57-meta-workflow-migration itself):
gh pr review "$PR_NUM" --approve --body "Dry-run: verifying gh pr review --approve permission. Not a real APPROVE."
```

If this succeeds, CR has the scope. If it fails with "insufficient permissions", **stop Phase 2 and escalate to Board** — without this permission, the new flow's CR-approve bridge can't function.

- [ ] **Step 5: Revert the dry-run approve** (it was not a real review):

```bash
# Dismiss the dry-run approval
gh pr review "$PR_NUM" --body "Dismissing the dry-run approval above — was a permission check only, not a real CR verdict." --request-changes
```

(If `gh` doesn't support dismiss, document the dry-run commentary in the PR comment so downstream CR is not confused.)

### Task 2.8: qa-evidence-check.yml GitHub Action

**Owner:** InfraEngineer

**Files:**
- Create: `.github/workflows/qa-evidence-check.yml`

- [ ] **Step 1: Write the Action file**

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
      - name: Check QA Evidence section or waiver label
        env:
          BODY: ${{ github.event.pull_request.body }}
          IS_MICRO_SLICE: ${{ contains(github.event.pull_request.labels.*.name, 'micro-slice') }}
        run: |
          set -euo pipefail
          if [ "$IS_MICRO_SLICE" = "true" ]; then
            echo "Label 'micro-slice' present — QA evidence waived."
            exit 0
          fi
          if echo "$BODY" | grep -q '^## QA Evidence'; then
            echo "QA Evidence section detected."
            SECTION=$(echo "$BODY" | awk '/^## QA Evidence/,/^## /')
            if echo "$SECTION" | grep -qE '[0-9a-f]{7,40}'; then
              echo "Commit SHA reference found in QA Evidence section."
              exit 0
            else
              echo "::error::QA Evidence section has no commit SHA (need 7-40 hex chars)."
              exit 1
            fi
          fi
          echo "::error::PR body must contain '## QA Evidence' section with commit SHA, OR add label 'micro-slice' to waive."
          exit 1
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/qa-evidence-check.yml
git commit -m "feat(ci): qa-evidence-present required check (GIM-48 vector #2)"
git push origin feature/GIM-57-meta-workflow-migration
```

- [ ] **Step 3: DRY-RUN — verify Action fires on PR**

Push triggers the Action on the draft PR automatically. Check:

```bash
gh pr view --json statusCheckRollup -q '.statusCheckRollup[] | select(.name == "qa-evidence-present")'
```

Initially expect: FAILURE (the PR's own body doesn't yet have `## QA Evidence` section until Phase 4.1 evidence is added).

- [ ] **Step 4: DRY-RUN — waive via label**

```bash
gh pr edit --add-label micro-slice
sleep 30
gh pr view --json statusCheckRollup -q '.statusCheckRollup[] | select(.name == "qa-evidence-present") | .conclusion'
```

Expected: `SUCCESS` (waived).

- [ ] **Step 5: Remove the waiver label** (meta-migration is NOT a micro-slice; real evidence comes in Phase 4.1):

```bash
gh pr edit --remove-label micro-slice
```

After removing, the check should fail again until Phase 4.1 adds the evidence. That's expected — the slice's own PR body will gain `## QA Evidence` in Phase 4.1.

### Task 2.9: release-cut.yml GitHub Action

**Owner:** InfraEngineer

**Files:**
- Create: `.github/workflows/release-cut.yml`

- [ ] **Step 1: Write the Action file**

```yaml
name: release-cut
on:
  workflow_dispatch:
    inputs:
      reason:
        description: "Reason for release cut"
        required: false
        default: "manual dispatch"
  pull_request:
    types: [closed]
    branches: [develop]

jobs:
  cut:
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
          set -euo pipefail
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git fetch origin develop main
          git checkout main
          BEFORE=$(git rev-parse HEAD)
          git merge --ff-only origin/develop
          AFTER=$(git rev-parse HEAD)
          git push origin main
          echo "Released main: $BEFORE -> $AFTER"
          echo "## Release cut" >> "$GITHUB_STEP_SUMMARY"
          echo "" >> "$GITHUB_STEP_SUMMARY"
          echo "- before: $BEFORE" >> "$GITHUB_STEP_SUMMARY"
          echo "- after:  $AFTER" >> "$GITHUB_STEP_SUMMARY"
          echo "- trigger: ${{ github.event_name }}" >> "$GITHUB_STEP_SUMMARY"
```

- [ ] **Step 2: Create RELEASE_CUT_TOKEN secret (ops step)**

Manual step (operator runs):

```bash
# Generate a fine-grained PAT (or GitHub App) with contents: write scope on the Gimle-Palace repo only.
# Set expiration 90 days. Repository: ant013/Gimle-Palace. Permissions: Contents (read+write), Metadata (read).
# Save the token value, then:

gh secret set RELEASE_CUT_TOKEN --repo ant013/Gimle-Palace
# Paste token when prompted.
```

**Document this step in rollback runbook** — if the token expires or is revoked, release-cuts stop working, and the restore path is a new token.

- [ ] **Step 3: Commit workflow file**

```bash
git add .github/workflows/release-cut.yml
git commit -m "feat(ci): release-cut workflow for main FF via bot (no human direct push)"
git push origin feature/GIM-57-meta-workflow-migration
```

- [ ] **Step 4: DRY-RUN — manual dispatch WHILE branch protection still off**

Branch protection on main is not yet tightened (§7 Phase 4.3). Run:

```bash
gh workflow run release-cut.yml -f reason="dry-run at Phase 2.9 — verify Action pipeline"
sleep 20
gh run list --workflow release-cut.yml --limit 1 --json conclusion,status
```

Expected: `status=completed, conclusion=success` (if develop is ahead of main; if develop == main, FF is no-op and Action may log "Already up-to-date" — also treat as success).

Verify main tip:

```bash
git fetch origin
git log --oneline origin/main -2
# Expected: origin/main tip should match origin/develop tip (whichever commit each is on at the time of Task 2.9 dry-run).
```

If Action failed because token absent/expired, fix token and re-dispatch. **Do not proceed to Phase 4.3 with a broken release-cut.yml** — that would mean main can never update post-protection.

### Task 2.10: Commit branch-protection JSON configs (declarative, not yet applied)

**Owner:** InfraEngineer

**Files:**
- Create: `.github/branch-protection/develop.json`
- Create: `.github/branch-protection/main.json`

These are reference configs — committed now so the Phase 4.3 apply step is reproducible, and the rollback step has a clear "before" to restore if needed.

- [ ] **Step 1: Write `.github/branch-protection/develop.json`**

```json
{
  "required_status_checks": {
    "strict": true,
    "contexts": ["lint", "typecheck", "test", "docker-build", "qa-evidence-present"]
  },
  "enforce_admins": true,
  "required_pull_request_reviews": {
    "required_approving_review_count": 1,
    "dismiss_stale_reviews": false,
    "require_code_owner_reviews": false,
    "require_last_push_approval": false
  },
  "restrictions": null,
  "required_linear_history": false,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "block_creations": false,
  "required_conversation_resolution": false,
  "lock_branch": false,
  "allow_fork_syncing": false
}
```

- [ ] **Step 2: Write `.github/branch-protection/main.json`**

```json
{
  "required_status_checks": null,
  "enforce_admins": true,
  "required_pull_request_reviews": null,
  "restrictions": {
    "users": [],
    "teams": [],
    "apps": ["github-actions"]
  },
  "required_linear_history": true,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "block_creations": false,
  "required_conversation_resolution": false,
  "lock_branch": false,
  "allow_fork_syncing": false
}
```

Note on `main.json`:
- `required_status_checks: null` — main never receives a PR, so checks don't gate it.
- `restrictions.apps: ["github-actions"]` — only the GitHub Actions bot can push (via release-cut.yml).
- `required_linear_history: true` — FF merges only (no merge commits from random merges).

- [ ] **Step 3: Commit**

```bash
git add .github/branch-protection/develop.json .github/branch-protection/main.json
git commit -m "feat(ci): branch-protection JSON configs (applied in Phase 4.3)"
git push origin feature/GIM-57-meta-workflow-migration
```

Not applied yet. `gh api -X PUT` call happens in Task 4.3.2.

### Task 2.11: Submodule — push fragment edits, bump ref

**Owner:** InfraEngineer

**Files:** (in `paperclip-shared-fragments` repo, not Gimle)
- Modified: `fragments/git-workflow.md` (from Task 2.2)
- Modified: `fragments/cto-no-code-ban.md` (from Task 2.3)
- Modified: `fragments/phase-handoff.md` (from Task 2.4)

Gimle side:
- Modify: `paperclips/fragments/shared` (pointer)

- [ ] **Step 1: cd into submodule, create branch**

```bash
# Ensure submodule initialized (cold-clone safety) — CR WARNING #3
git submodule update --init paperclips/fragments/shared
cd paperclips/fragments/shared
git fetch origin
git checkout -b meta-workflow-migration origin/main
git status
# Expected: 3 modified files (git-workflow, cto-no-code-ban, phase-handoff)
git diff --stat
# Expected: 3 files changed, roughly +40 -8 lines total
```

- [ ] **Step 2: Commit + push in submodule**

```bash
git add fragments/git-workflow.md fragments/cto-no-code-ban.md fragments/phase-handoff.md
git commit -m "feat(fragments): feature-branch flow + fetch-discipline + CTO meta-doc exemption

- git-workflow.md: Fresh-fetch on wake, Force-push discipline, Board-included rule.
- cto-no-code-ban.md: narrow ban — allow Edit/Write/git commit on docs/superpowers/** and docs/runbooks/** on feature branches only.
- phase-handoff.md: Phase 1.1 row — CTO does mechanical rename itself, no sub-issue.

Consumed by Gimle meta-workflow-migration slice (GIM-${N})."
git push origin meta-workflow-migration
```

- [ ] **Step 3: Open PR on `paperclip-shared-fragments` repo**

```bash
gh pr create --repo ant013/paperclip-shared-fragments \
  --base main --head meta-workflow-migration \
  --title "feat: feature-branch flow + fetch + CTO meta-doc exemption" \
  --body "Consumed by Gimle meta-workflow-migration (GIM-${N}). See Gimle PR #<N> for consumer context.

Changes:
- git-workflow.md: new sections for Fresh-fetch + Force-push + Board binding.
- cto-no-code-ban.md: narrowed to allow docs/superpowers/** + docs/runbooks/** edits.
- phase-handoff.md: Phase 1.1 row — no sub-issue for mechanical rename.

No breaking change for other consumers (Medic); new rules are additive or narrow existing bans."
```

- [ ] **Step 4: Wait for + merge submodule PR**

This PR doesn't have the complex Gimle CI; typically lint + markdown-check. Merge when review passes.

After merge on `paperclip-shared-fragments@main`, note the new HEAD SHA — call it `$FRAG_SHA`:

```bash
cd paperclips/fragments/shared
git fetch origin
git switch main
git pull --ff-only
FRAG_SHA=$(git rev-parse HEAD)
echo "new shared-fragments main: $FRAG_SHA"
```

- [ ] **Step 5: Bump submodule pointer in Gimle**

```bash
cd /path/to/gimle-board-checkout   # back to top-level Gimle repo
git status
# Expected: modified: paperclips/fragments/shared (new commits)
git add paperclips/fragments/shared
git commit -m "chore(submodule): bump paperclip-shared-fragments to ${FRAG_SHA} (meta-workflow-migration fragments)"
git push origin feature/GIM-57-meta-workflow-migration
```

- [ ] **Step 6: Rebuild role bundles in dist/**

```bash
./paperclips/build.sh
git status
# Expected: modified: paperclips/dist/**/*.md (rebuilt bundles)
git add paperclips/dist/
git commit -m "chore(dist): rebuild role bundles with new shared fragments"
git push origin feature/GIM-57-meta-workflow-migration
```

- [ ] **Step 7: Verify distbundle content for one agent (CTO)**

```bash
grep -A 3 'MAY run.*git commit' paperclips/dist/cto.md
# Expected: the narrowed-ban exemption bullet rendered in the deployed bundle
```

### Task 2.12: Deploy new bundles to 11 agents + verify

**Owner:** InfraEngineer

- [ ] **Step 1: Run deploy script**

```bash
./paperclips/deploy-agents.sh --local    # or without --local if targeting paperclip API directly
```

Expected output: `✅ Deployed <agent-name> bundle to <agent-id>` for each of 11 agents (CTO, CodeReviewer, InfraEngineer, PythonEngineer, QAEngineer, TechnicalWriter, MCPEngineer, ResearchAgent, BlockchainEngineer, SecurityAuditor, OpusArchitectReviewer).

- [ ] **Step 2: Verify 2 agents have new bundle (CTO + CodeReviewer)**

```bash
set -a; source .env; set +a
for AGENT in "7fb0fdbb-e17f-4487-a4da-16993a907bec:CTO" "bd2d7e20-7ed8-474c-91fc-353d610f4c52:CodeReviewer"; do
  ID="${AGENT%%:*}"
  NAME="${AGENT##*:}"
  echo "=== $NAME ==="
  curl -sS -H "Authorization: Bearer $PAPERCLIP_API_KEY" \
    "$PAPERCLIP_API_URL/api/agents/$ID" \
    | python3 -c "import sys, json; d = json.load(sys.stdin); \
        instr = d.get('instructions') or ''; \
        print('git-workflow/Fresh-fetch section present:', 'Fresh-fetch on wake' in instr); \
        print('cto-ban narrow exemption present:', 'MAY run' in instr or 'docs/superpowers/**' in instr);"
done
```

Expected: both booleans `True` for CTO; at minimum `Fresh-fetch on wake: True` for CR (CR doesn't have cto-no-code-ban).

- [ ] **Step 3: Commit nothing new** — deploy is runtime, not code.

---

## Phase 3 — Review

### Task 3.1: CodeReviewer mechanical review

**Owner:** CodeReviewer

- [ ] **Step 1: Fetch fresh on wake + checkout**

```bash
git fetch origin --prune
git switch feature/GIM-57-meta-workflow-migration
git pull --ff-only
```

- [ ] **Step 2: Lint check on changed files (markdown + YAML + JSON)**

```bash
# YAML syntax
python3 -c "import yaml; [yaml.safe_load(open(f)) for f in ['.github/workflows/qa-evidence-check.yml', '.github/workflows/release-cut.yml']]; print('YAML OK')"

# JSON syntax
python3 -c "import json; [json.load(open(f)) for f in ['.github/branch-protection/develop.json', '.github/branch-protection/main.json']]; print('JSON OK')"

# Markdown unclosed fences
for f in CLAUDE.md paperclips/roles/cto.md paperclips/roles/mcp-engineer.md paperclips/roles/code-reviewer.md; do
  fences=$(grep -c '^```' "$f")
  if [ $((fences % 2)) -ne 0 ]; then
    echo "::error::$f has unclosed code fence"
    exit 1
  fi
done
echo "Markdown fences balanced"
```

- [ ] **Step 3: Spec §5 compliance checklist**

Walk each of the 18 acceptance items from spec §5. For each, find the task in this plan that implements it.

Paste full table in paperclip compliance comment:

```
| # | §5 criterion | Task | Status |
|---|---|---|---|
| 1 | CLAUDE.md Branch Flow rewrite | Task 2.1 | ✅ |
| 2 | git-workflow.md has 3 sections | Task 2.2 | ✅ |
| 3 | cto-no-code-ban.md narrowed | Task 2.3 | ✅ |
| 4 | phase-handoff.md Phase 1.1 updated | Task 2.4 | ✅ |
| 5 | cto.md scoped | Task 2.5 | ✅ |
| 6 | mcp-engineer.md Waiting for CI | Task 2.6 | ✅ |
| 7 | code-reviewer.md gh pr review --approve | Task 2.7 | ✅ |
| 8 | qa-evidence-check.yml present + required | Task 2.8 + 4.3.2 | ✅ (Action committed; required-check enforced in 4.3.2) |
| 9 | release-cut.yml present + dry-run | Task 2.9 | ✅ |
| 10 | RELEASE_CUT_TOKEN secret set | Task 2.9 Step 2 | ✅ (ops-doc step) |
| 11 | deploy-agents.sh run on 11 agents + verified 2 | Task 2.12 | ✅ |
| 12 | Branch protection on develop applied in 4.3 | Task 4.3.2 | ⏳ (planned, not Phase 2) |
| 13 | Branch protection on main applied in 4.3 | Task 4.3.2 | ⏳ |
| 14 | Direct push to main rejected | Task 4.3.3 | ⏳ |
| 15 | PR without QA Evidence blocked | Task 4.1 | ⏳ |
| 16 | CR GitHub review required | Task 4.3.2 | ⏳ |
| 17 | gh workflow run release-cut.yml works | Task 2.9 Step 4 | ✅ |
| 18 | Submodule bumped + rollback runbook | Tasks 2.11 + this slice | ✅ |
```

- [ ] **Step 4: Paperclip APPROVE comment**

```
## Phase 3.1 APPROVE

Spec §5 compliance (18 items): all checked. Phase 4.3 items (⏳) are intentionally deferred — branch protection enables AFTER this PR merges per spec §3.7 ordering constraint.

Mechanical checks:
- YAML syntax: OK
- JSON syntax: OK
- Markdown fences: balanced across CLAUDE.md + 3 role files

Ruff / mypy / pytest: N/A (no Python code changed this slice).

@OpusArchitectReviewer your turn — Phase 3.2 adversarial.
```

- [ ] **Step 5: GitHub review on PR** (testing the new bridge introduced by this slice, even though it's not yet enforced)

```bash
gh pr review <PR#> --approve --body "Paperclip compliance APPROVE — see issue ${ISSUE_ID}.

This review is a dry-run of the §3.9 bridge introduced by this slice. Branch protection requiring it turns on in Phase 4.3."
```

- [ ] **Step 6: Reassign to Opus**

```bash
curl -sS -X PATCH -H "Authorization: Bearer $PAPERCLIP_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"assigneeAgentId":"8d6649e2-2df6-412a-a6bc-2d94bab3b73f"}' \
  "$PAPERCLIP_API_URL/api/issues/$ISSUE_ID"
```

### Task 3.2: OpusArchitectReviewer adversarial

**Owner:** OpusArchitectReviewer

- [ ] **Step 1: Fetch + read**

```bash
git fetch origin --prune
git switch feature/GIM-57-meta-workflow-migration
git pull --ff-only
```

- [ ] **Step 2: Adversarial questions to address**

For each, either dismiss with reasoning or flag as finding:

1. **Medic project using same shared-fragments submodule.** Will Medic's agents break with new fragment content? Check: narrow exemption (`cto-no-code-ban.md`) shouldn't break Medic (additive permission). Fresh-fetch rule (additive). Phase 1.1 handoff row more specific, still valid for Medic. Verdict: probably safe; if Medic CI breaks, their followup to align — flag.

2. **In-flight Gimle slice starting mid-migration.** If an agent checks out a worktree for a new GIM-N+1 **while** this slice's fragments are being deployed (between Task 2.11 submodule merge and Task 2.12 deploy-agents.sh), the agent reads old bundle. Mitigation: deploy-agents.sh run is fast (<1 min typically). Worst case: a brief window where rules don't match. Accept.

3. **`RELEASE_CUT_TOKEN` scope too wide.** Fine-grained PAT scoped to `ant013/Gimle-Palace` only with `contents: write`. OK. Rotation: 90-day expiration reminder in ops runbook. Flag if no rotation plan.

4. **QA-evidence regex false-positives.** `[0-9a-f]{7,40}` matches any hex span 7-40 chars. A SHA-like string in commit body (e.g., "see 0123456 for reference") would pass even without real evidence. Severity: Low — if QAEngineer adds a real SHA in the section, it's fine; if someone puts "abcdef1" as a typo, false-pass. Worth flagging but not blocking.

5. **Release-cut on label `release-cut` auto-fires on EVERY PR merge with that label.** What if someone accidentally adds the label? Verification: the action logs before/after SHAs; easy to roll back. Accept.

6. **Phase 4.3 Step 4.3.1 — operator manual FF push.** At that moment, branch protection on main is still OFF (protection enables in 4.3.2). But the spec's iron rule says "no human direct push to main". Audit: this is the LAST legit direct push, documented as the transition point in spec §10. Accept with clear commit message.

7. **Rollback-in-emergency: `git push origin main --force-with-lease`** to rewind main. Violates "no force on main" iron rule. But §11 explicitly frames it as emergency escape hatch. Accept with runbook caveat: the rule applies during normal operation, not during migration rollback.

- [ ] **Step 3: Post adversarial review comment**

```
## Phase 3.2 adversarial review

### NUDGEs (non-blocking)

1. **QA-evidence regex false-positive risk (Medium).** A stray hex SHA in the section would pass the check. Mitigation in practice: QAEngineer pastes real logs with real SHAs; low abuse surface since only trusted agents write PR bodies. Accept.

2. **`RELEASE_CUT_TOKEN` rotation schedule undefined.** 90-day fine-grained PAT. Add a calendar reminder and document in ops runbook. Followup, not blocker.

3. **Medic project fragment compatibility.** All fragment changes are additive or narrowing; Medic should not break. Flag for Medic team to verify after this merge.

### No CRITICAL findings.

Plan is internally consistent. Phase 4.3 ordering is correct. Rollback runbook exists. CR bridge has a dry-run verification step.

APPROVE.

@QAEngineer your turn — Phase 4.1 dogfood.
```

- [ ] **Step 4: Reassign to QAEngineer**

```bash
curl -sS -X PATCH -H "Authorization: Bearer $PAPERCLIP_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"assigneeAgentId":"58b68640-1e83-4d5d-978b-51a5ca9080e0"}' \
  "$PAPERCLIP_API_URL/api/issues/$ISSUE_ID"
```

---

## Phase 4 — QA + Merge + Protection

### Task 4.1: QAEngineer dogfood — attempt PR merge blocks without evidence, with label, etc.

**Owner:** QAEngineer

**Goal:** verify the new flow rules BLOCK in the intended ways BEFORE they become universally enforced in Phase 4.3.

- [ ] **Step 1: Fetch + checkout + confirm state**

```bash
git fetch origin --prune
git switch feature/GIM-57-meta-workflow-migration
git pull --ff-only
gh pr view --json number,url,statusCheckRollup -q '{pr: .number, url: .url, checks: [.statusCheckRollup[] | {name, status: .status, conclusion: .conclusion}]}'
```

Record the PR number (`PR_NUM`) for the rest of the phase.

- [ ] **Step 2: Dogfood scenario A — PR body WITHOUT `## QA Evidence` section → check fails**

The PR body at this point is the Phase 1.1 template (no QA Evidence yet). Verify:

```bash
gh pr view $PR_NUM --json body | python3 -c "import sys, json; b = json.load(sys.stdin)['body']; print('Has QA Evidence:', '## QA Evidence' in b)"
# Expected: Has QA Evidence: False (or True with "(To be added...)" placeholder — placeholder doesn't satisfy the regex)

gh pr checks $PR_NUM --required | grep qa-evidence-present
# Expected: FAIL
```

Save output as `evidence/scenario-a-no-evidence-fails.txt`.

- [ ] **Step 3: Dogfood scenario B — add `micro-slice` label → check passes**

```bash
gh pr edit $PR_NUM --add-label micro-slice
sleep 30
gh pr checks $PR_NUM --required | grep qa-evidence-present
# Expected: PASS (waived by label)
```

Save as `scenario-b-waiver-passes.txt`.

- [ ] **Step 4: Remove label (meta-migration is not a micro-slice)**

```bash
gh pr edit $PR_NUM --remove-label micro-slice
sleep 30
gh pr checks $PR_NUM --required | grep qa-evidence-present
# Expected: FAIL again
```

- [ ] **Step 5: Dogfood scenario C — edit PR body with real QA evidence → check passes**

Build evidence body and edit the PR:

```bash
SHA=$(git rev-parse HEAD)
cat > /tmp/pr-body.md <<EOF
## Summary

Meta-workflow migration slice: single mainline, Board-in-flow, narrowed CTO ban, QA-evidence gate, release-cut Action.

Spec: \`docs/superpowers/specs/2026-04-19-meta-workflow-migration-design.md\`
Plan: \`docs/superpowers/plans/2026-04-19-GIM-${N}-meta-workflow-migration.md\`

## QA Evidence

Commit tested: \`${SHA}\` (HEAD of feature/GIM-57-meta-workflow-migration).

### Scenarios executed (Phase 4.1)

1. **No evidence → qa-evidence-present check fails.** ✅ Verified by Scenario A (no \`## QA Evidence\` section in initial PR body, check red).
2. **micro-slice label → check waived.** ✅ Verified by Scenario B (adding label flipped check to green; removing label flipped back to red).
3. **Real evidence with SHA → check passes.** ✅ This very PR body, now containing SHA \`${SHA}\`, makes the check pass.
4. **release-cut.yml dry-run (Task 2.9 Step 4).** ✅ Manual dispatch succeeded; main FF'd to develop tip at time of dry-run.
5. **CR gh pr review --approve (Task 3.1 Step 5).** ✅ CR posted GitHub review with approve; visible via \`gh pr view ${PR_NUM} --json reviews\`.

No direct-push-to-main attempts in Phase 4.1 — those are Phase 4.3 verification after branch protection is applied.

Closes GIM-${N}.
EOF

gh pr edit $PR_NUM --body-file /tmp/pr-body.md

sleep 30
gh pr checks $PR_NUM --required | grep qa-evidence-present
# Expected: PASS (real SHA in section)
```

- [ ] **Step 6: Verify all required checks status**

```bash
gh pr checks $PR_NUM --required
# Expected (before protection tightened):
#   lint         pass
#   typecheck    pass (or N/A for docs-only PR — may not run)
#   test         pass (or N/A — same)
#   docker-build pass (or N/A — same)
#   qa-evidence-present  pass
```

Note: some CI jobs may be skipped on docs-only PRs by their workflow triggers. That's fine for meta-migration (docs + .github only). At Phase 4.3.3 we verify the protection rules only require checks that actually ran.

- [ ] **Step 7: Post Phase 4.1 evidence comment**

On paperclip issue:

```
## Phase 4.1 PASS

**Commit tested:** <sha> (feature/GIM-57-meta-workflow-migration HEAD)

### Scenarios
- A: No evidence section → qa-evidence-present FAIL (log attached).
- B: micro-slice label → qa-evidence-present PASS (waiver works).
- C: Real SHA in evidence → qa-evidence-present PASS.
- Task 2.9 dry-run: release-cut.yml FF'd main, no errors.
- Task 3.1 Step 5: CR gh pr review --approve posted (visible on PR).

No regression on pytest/ruff/mypy — this slice touches no Python code (services/ unchanged).

@CTO your turn — Phase 4.2 squash-merge.
```

Attach scenario logs as comments or as gist links if size >4KB.

- [ ] **Step 8: Reassign to CTO**

```bash
curl -sS -X PATCH -H "Authorization: Bearer $PAPERCLIP_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"assigneeAgentId":"7fb0fdbb-e17f-4487-a4da-16993a907bec"}' \
  "$PAPERCLIP_API_URL/api/issues/$ISSUE_ID"
```

### Task 4.2: CTO squash-merge

**Owner:** CTO

- [ ] **Step 1: Fetch + mark PR ready for review**

```bash
git fetch origin --prune
git switch feature/GIM-57-meta-workflow-migration
git pull --ff-only

# Convert draft to ready-for-review (if still draft)
gh pr ready $PR_NUM
```

- [ ] **Step 2: Confirm all checks green + CR review present**

```bash
gh pr checks $PR_NUM --required
# Expected: all pass

gh pr view $PR_NUM --json reviews -q '.reviews[] | select(.state == "APPROVED") | {authorLogin, submittedAt}'
# Expected: at least one APPROVED review from CR
```

- [ ] **Step 3: Squash-merge via `gh pr merge`**

```bash
gh pr merge $PR_NUM --squash --delete-branch --subject "feat(workflow): meta-workflow migration — single mainline, Board-in-flow, new required checks (GIM-${N})"
```

- [ ] **Step 4: Verify merge landed**

```bash
git fetch origin
git log origin/develop -3 --oneline
# Expected: top commit is the squash-merge from above
```

- [ ] **Step 5: Reassign to Operator for Phase 4.3.1 manual FF**

Post comment:

```
## Phase 4.2 done — squash-merge <sha> on develop

Feature branch deleted. @Operator (Board) — Phase 4.3.1 one-time manual FF of main is yours (last legit direct push to main under old rules, before 4.3.2 tightens protection).
```

Reassign: no specific agent for Operator role — leave `status=in_progress, assignee=CTO` with the comment @-mentioning Operator/Board.

### Task 4.3.1: Operator (Board) manual FF main → develop tip

**Owner:** Operator (human + Claude Code session)

- [ ] **Step 1: Fetch**

```bash
git fetch origin --prune
```

- [ ] **Step 2: Switch to main, FF to develop**

```bash
git switch main
git pull --ff-only   # should already be at whatever origin/main was
git merge --ff-only origin/develop
```

Expected: `Fast-forward`, no merge commit. If `git merge` refuses non-FF, something diverged — STOP and escalate (shouldn't happen if Phase 4.3 sequencing was followed).

- [ ] **Step 3: Push (last direct human push to main, ever)**

```bash
git push origin main
```

Expected success. If admin-bypass warning appears again: OK (protection still off at this point; 4.3.2 turns it on).

- [ ] **Step 4: Verify sync**

```bash
MAIN=$(git rev-parse origin/main)
DEV=$(git rev-parse origin/develop)
[ "$MAIN" = "$DEV" ] && echo "SYNCED: $MAIN" || echo "STILL DIVERGED"
```

Expected: `SYNCED: <sha>`.

- [ ] **Step 5: Hand off to InfraEngineer**

Post comment on paperclip issue:

```
## Phase 4.3.1 done

main FF'd to develop: <sha>. Last legitimate direct human push to main (per spec §10 transition). @InfraEngineer Phase 4.3.2 — apply branch protection.
```

Reassign to InfraEngineer (`89f8f76b-844b-4d1f-b614-edbe72a91d4b`).

### Task 4.3.2: Apply branch protection on main + develop

**Owner:** InfraEngineer

- [ ] **Step 1: Fetch + read config files**

```bash
git fetch origin --prune
git switch main
git pull --ff-only
cat .github/branch-protection/develop.json
cat .github/branch-protection/main.json
```

- [ ] **Step 2: Apply to develop**

```bash
gh api -X PUT -H "Accept: application/vnd.github+json" \
  /repos/ant013/Gimle-Palace/branches/develop/protection \
  --input .github/branch-protection/develop.json \
  | python3 -c "import sys, json; d = json.load(sys.stdin); print('develop protection URL:', d.get('url'))"
```

Expected: URL returned; no error.

- [ ] **Step 3: Apply to main**

```bash
gh api -X PUT -H "Accept: application/vnd.github+json" \
  /repos/ant013/Gimle-Palace/branches/main/protection \
  --input .github/branch-protection/main.json \
  | python3 -c "import sys, json; d = json.load(sys.stdin); print('main protection URL:', d.get('url'))"
```

- [ ] **Step 4: Hand off to self for verification**

No reassign — same agent continues to Task 4.3.3.

### Task 4.3.3: Verify branch protection blocks the right things

**Owner:** InfraEngineer

- [ ] **Step 1: Attempt direct push to main → should be rejected**

```bash
git switch main
git commit --allow-empty -m "TEST: this should be rejected by branch protection"
git push origin main 2>&1 | tee /tmp/main-push-attempt.log
```

Expected: `remote: error: GH006: Protected branch update failed for refs/heads/main.` (or similar). Non-zero exit.

- [ ] **Step 2: Undo the test commit locally** (if push failed as expected, local main is 1 commit ahead of origin/main)

```bash
git reset --hard origin/main
```

- [ ] **Step 3: Attempt direct push to develop → should be rejected**

```bash
git switch develop
git commit --allow-empty -m "TEST: this should be rejected on develop too"
git push origin develop 2>&1 | tee /tmp/develop-push-attempt.log
```

Expected: rejected with protected-branch error.

- [ ] **Step 4: Undo**

```bash
git reset --hard origin/develop
```

- [ ] **Step 5: Verify release-cut Action still works after protection**

```bash
gh workflow run release-cut.yml -f reason="Phase 4.3.3 verification — main FF post-protection"
sleep 30
gh run list --workflow release-cut.yml --limit 1 --json conclusion,status
```

Expected: `status=completed, conclusion=success` (or `neutral` if main == develop with nothing to FF).

- [ ] **Step 6: Post verification comment**

```
## Phase 4.3.3 verification PASS

### Evidence

- Direct push to main: REJECTED (log: main-push-attempt.log).
- Direct push to develop: REJECTED (log: develop-push-attempt.log).
- release-cut.yml dispatch (post-protection): SUCCESS — bot push-path still works.

New-flow enforcement live from <timestamp>. @CTO close the issue.
```

Reassign to CTO.

### Task 4.3.4: CTO close issue

**Owner:** CTO

- [ ] **Step 1: Verify acceptance checklist (§5 of spec)**

All 18 items. Items that were ⏳ in Phase 3.1 CR compliance table should now be ✅ based on Phase 4.1-4.3 evidence.

- [ ] **Step 2: Close paperclip issue**

```bash
curl -sS -X PATCH -H "Authorization: Bearer $PAPERCLIP_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"status":"done"}' \
  "$PAPERCLIP_API_URL/api/issues/$ISSUE_ID"
```

- [ ] **Step 3: Final closing comment**

```
## GIM-${N} closed

- Squash-merge on develop: <sha>
- main post-4.3.1 FF: <sha>
- Branch protection live on main + develop.
- qa-evidence-present check active; tested pass+fail+waiver scenarios.
- release-cut.yml verified post-protection.
- CR `gh pr review --approve` bridge in place for next slice.
- Submodule paperclip-shared-fragments bumped to <sha>.

GIM-48 vectors:
- ✅ Admin-bypass (this slice).
- ✅ QA-evidence gate (this slice).
- ⏳ Mocked-substrate test-design — separate followup slice.

Next recommended slice: async-signal-integration (MCPEngineer CI-wait automation) OR test-design-discipline (GIM-48 vector #3) OR N+2 extractor kickoff.
```

### Task 4.3.5: Update operator auto-memory

**Owner:** Operator (Board)

Not a paperclip step, but part of closing the loop.

- [ ] **Step 1: Update memory files**

Update:
- `project_backlog.md` — mark GIM-${N} closed with merge SHA and durations.
- `reference_main_develop_split.md` — mark superseded, replace with reference to new flow (or replace content with "Split retired 2026-04-19 via GIM-${N}").
- Add new `reference_feature_branch_flow.md` describing:
  - Single mainline develop.
  - Branch protection rules.
  - Release-cut via Action.
  - Board checkout location.
  - CR GitHub-review bridge.
- Update `MEMORY.md` index to point to the new reference.

- [ ] **Step 2: No git commit for memory** — memory lives outside the project repo, in `/Users/ant013/.claude/projects/.../memory/`.

---

## Out of scope for this plan (still followups)

From spec §4 + §9:
- CI-feedback / async-signal integration (separate slice; MCPE `## CI pending` marker is the placeholder formalized here).
- Environment-level `git fetch` hook (local wrapper in `deploy-agents.sh` or paperclip pre-wake, 2-4h estimate).
- Full Board role fragment (only relevant if second operator joins).
- `main` retirement (if no release cut in 30 days + no external consumer).
- Test-design discipline (GIM-48 vector #3 — separate slice).
- Multi-project submodule drift coordination.
- `paperclip-shared-fragments` CI (markdown lint, link-check).

## Rollback

If any step in Phase 4.3 breaks the workflow irrecoverably, follow `docs/runbooks/2026-04-19-meta-workflow-migration-rollback.md`. The runbook is created as part of Task 2.10 (actually Task 2.13 below — see addition).

### Task 2.13: Rollback runbook

**Owner:** TechnicalWriter

**Files:**
- Create: `docs/runbooks/2026-04-19-meta-workflow-migration-rollback.md`

- [ ] **Step 1: Write the runbook**

```markdown
# Meta-workflow migration — rollback runbook

**Date:** 2026-04-19
**Consumed by:** spec `docs/superpowers/specs/2026-04-19-meta-workflow-migration-design.md` §11.
**Trigger conditions:** any of
- Branch protection on main/develop blocks legitimate operations we need now.
- qa-evidence-present check false-positives blocking real merges repeatedly.
- CR GitHub-review bridge fails for technical reasons and blocks merges.
- Agent behavior regression after fragment deploy.

## Pre-rollback snapshot

Record before executing:

```bash
PRE_MAIN=$(git rev-parse origin/main)
PRE_DEV=$(git rev-parse origin/develop)
PRE_FRAG=$(cd paperclips/fragments/shared && git rev-parse HEAD)
echo "PRE_MAIN=$PRE_MAIN PRE_DEV=$PRE_DEV PRE_FRAG=$PRE_FRAG" | tee /tmp/migration-rollback-snapshot.env
```

## Steps

### 1. Remove branch protection (immediate unblock)

```bash
gh api -X DELETE /repos/ant013/Gimle-Palace/branches/main/protection
gh api -X DELETE /repos/ant013/Gimle-Palace/branches/develop/protection
```

### 2. Disable the new workflows

```bash
gh workflow disable qa-evidence-present
gh workflow disable release-cut
```

Or delete the files on a revert branch (step 4).

### 3. Restore pre-migration fragment bundle

Identify the migration-merge-sha on develop:

```bash
MERGE_SHA=$(git log origin/develop --oneline | grep 'meta-workflow migration' | head -1 | awk '{print $1}')
```

Revert it on a new branch:

```bash
git fetch origin
git switch -c rollback/meta-workflow-migration origin/develop
git revert -m 1 $MERGE_SHA
# Resolve any submodule conflict — restore to pre-migration fragments ref
cd paperclips/fragments/shared
git checkout <pre-migration-submodule-sha>    # from PRE_FRAG snapshot
cd ../../..
git add paperclips/fragments/shared
git commit -m "rollback: restore pre-migration shared fragments"
git push origin rollback/meta-workflow-migration
```

### 4. Merge the revert via PR (or direct-push, protection is off)

```bash
gh pr create --base develop --head rollback/meta-workflow-migration \
  --title "rollback: meta-workflow migration (GIM-N)" \
  --body "Emergency rollback per runbook. Reason: <describe>.

Pre-rollback state:
- develop: $PRE_DEV
- main: $PRE_MAIN
- submodule: $PRE_FRAG"
gh pr merge <PR#> --squash --delete-branch
```

### 5. Redeploy old fragment bundle to 11 agents

```bash
./paperclips/build.sh
./paperclips/deploy-agents.sh --local
```

### 6. If release-cut already moved main, rewind main via FF-back

Only works while main is still a direct ancestor-or-descendant of the rollback commit:

```bash
git switch main
git reset --hard $PRE_MAIN
git push origin main --force-with-lease    # emergency escape hatch ONLY during rollback
```

(Force-with-lease on main is forbidden during normal operation. During rollback, with branch protection already removed in Step 1, it is the restore path.)

### 7. Notify all 11 agents

Deploy step 5 + paperclip UI refresh. If some agent is mid-run, reassign or release its execution lock.

## Post-rollback

- Record in `project_backlog.md` memory: slice rolled back, with reason + pre/post SHAs.
- Open a new paperclip issue for followup (what went wrong + what to try next).
- Re-apply branch protection manually if you want to keep admin-bypass closure WITHOUT the other changes — create a minimal `branches/develop/protection` JSON with only admin-enforce + required checks (no qa-evidence, no CR-review requirement).

## Time budget

Steps 1-2: 2 min (immediate unblock).
Steps 3-5: 20-30 min (revert + rebuild + deploy).
Step 6-7: 10 min if needed.
Total: 30-45 min for a full rollback.
```

- [ ] **Step 2: Commit**

```bash
git add docs/runbooks/2026-04-19-meta-workflow-migration-rollback.md
git commit -m "docs(runbook): meta-workflow migration rollback procedure"
git push origin feature/GIM-57-meta-workflow-migration
```

---

## Self-review against spec §5 (done at plan completion)

| # | §5 criterion | Task(s) |
|---|---|---|
| 1 | CLAUDE.md Branch Flow rewritten | 2.1 |
| 2 | git-workflow.md has fetch + force + Board sections | 2.2 |
| 3 | cto-no-code-ban.md narrowed | 2.3 |
| 4 | phase-handoff.md Phase 1.1 updated | 2.4 |
| 5 | cto.md scoped | 2.5 |
| 6 | mcp-engineer.md Waiting for CI | 2.6 |
| 7 | code-reviewer.md gh pr review --approve + dry-run | 2.7 |
| 8 | qa-evidence-check.yml present + required | 2.8 + 4.3.2 |
| 9 | release-cut.yml present + dry-run | 2.9 |
| 10 | RELEASE_CUT_TOKEN secret | 2.9 Step 2 |
| 11 | deploy-agents.sh on 11 agents + verify | 2.12 |
| 12 | Branch protection on develop | 4.3.2 |
| 13 | Branch protection on main | 4.3.2 |
| 14 | Direct push to main rejected | 4.3.3 |
| 15 | PR without QA Evidence blocked | 4.1 + 4.3.3 |
| 16 | CR GitHub review required | 4.3.2 (via protection) + 4.1 (tested dry-run in 2.7) |
| 17 | `gh workflow run release-cut.yml` works | 2.9 Step 4 + 4.3.3 Step 5 |
| 18 | Submodule bump + rollback runbook | 2.11 + 2.13 |

**All 18 spec §5 items covered.** No gaps.

Placeholder scan: no TBD / TODO / "similar to Task N" / "add error handling" without code.

Type consistency: function/command names consistent across tasks (`gh pr review --approve`, `qa-evidence-present`, `release-cut.yml`).

---

## Size estimate (final)

- Prose edits (CLAUDE.md + 4 role files + 3 fragments): ~300 LOC.
- YAML workflows + JSON configs: ~90 LOC.
- Rollback runbook: ~60 LOC.
- Plan (this file): ~1000 LOC.
- 2 PRs (this slice + paperclip-shared-fragments submodule PR).
- ~1 day agent-time across 4 phases.
