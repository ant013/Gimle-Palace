# GIM-114 — Plan-implementation drift discipline (rev2)

> **Supersedes:** rev1 (commit `af440a3`). Revised per CodeReviewer Phase 1.2 REQUEST CHANGES.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close plan-implementation drift failure mode discovered in GIM-104. Add file-count verification discipline to Phase 3.1 (CR) and coverage matrix audit to Phase 3.2 (Opus). Symmetric with GIM-108 (merge-readiness discipline) — together they harden Phase 3.x against the two main failure patterns: escalate-without-evidence and silent-scope-reduction.

**Predecessor SHA:** `5da4847` (GIM-108 merge) + `54691a7` (GIM-104 — incident source)

**Spec:** Issue body GIM-114 (Board-authored)

**Root path prefix:** `paperclips/` — fragments in submodule `paperclips/fragments/shared/`, roles in `paperclips/roles/`.

### CR Phase 1.2 findings addressed (rev2)

| # | Finding | Severity | Resolution |
|---|---------|----------|------------|
| 1 | Fragment density: `git-workflow.md` at 5 KB (2.5x cap) | CRITICAL | **New fragment** `phase-review-discipline.md` instead of extending `git-workflow.md`. Git-workflow stays git-only. |
| 2 | Task 4: opus-architect-reviewer.md has no Phase 3.2 section | WARNING | Task 4 revised: **create** new section `## Phase 3.2 — Coverage matrix audit discipline` after `## Anti-patterns` (line ~83). |
| 3 | Task 5: python-engineer.md has no Phase 2 section | WARNING | Task 5 revised: append to existing `## Technical conventions (hard rules)` (line 21). |
| 4 | Task 3: anchor placement ambiguity | WARNING | Task 3 revised: new subsection `### Phase 3.1 — Plan vs Implementation file-structure check` inserted **before** `### Phase 3.1 GitHub PR review bridge` (line 117). Separate concern: discipline before bridge. |
| 5 | Content should be fragment-grade, not role-file-grade | NOTE | Tasks 1–2: fragment = rule + mandatory command. Role files = enforcement examples + forbidden patterns. |

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `paperclips/fragments/shared/fragments/phase-review-discipline.md` | **Create** (submodule) | New fragment: §Phase 3.1 + §Phase 3.2 rules |
| `paperclips/roles/code-reviewer.md` | Modify | Wire §Phase 3.1 reference |
| `paperclips/roles/opus-architect-reviewer.md` | Modify | Wire §Phase 3.2 reference + new section |
| `paperclips/roles/python-engineer.md` | Modify | Wire scope-reduction transparency rule |
| `paperclips/fragments/shared` (submodule pointer) | Bump | After submodule PR merges |

---

## Task 1: Create Phase 3.1 file-structure check in new fragment (submodule)

**Files:**
- **Create:** `paperclips/fragments/shared/fragments/phase-review-discipline.md`

**Steps:**
- [ ] Create new fragment file `phase-review-discipline.md` in the submodule fragments directory.
- [ ] Add section `## Phase 3.1 — Plan vs Implementation file-structure check` with **fragment-grade** content:
  - Imperative one-liner: CR must paste `git diff --name-only <base>..<head>` and compare count against plan's file table before APPROVE.
  - One-line why: GIM-104 — PE silently reduced 6→2 files; tooling checks don't catch scope drift.
  - Mandatory command block:
    ```bash
    git diff --name-only <base>..<head> | sort
    # Compare against plan's "File Structure" table. Count must match.
    ```
  - One-liner: PE scope reduction without comment = REQUEST CHANGES.
- [ ] Keep content under 1 KB for this section (fragment density rule).

**Acceptance criteria:**
- New file `phase-review-discipline.md` exists in submodule.
- Phase 3.1 section is fragment-grade: rule + command + one-line why.
- File total stays under 2 KB soft cap.

**NOTE:** This requires a commit in the `paperclip-shared-fragments` submodule repo (`git@github.com:ant013/paperclip-shared-fragments.git`), not in Gimle-Palace directly. Create a branch in the submodule, commit, push, PR.

---

## Task 2: Add Phase 3.2 coverage matrix audit to the same new fragment (submodule)

**Files:**
- Modify: `paperclips/fragments/shared/fragments/phase-review-discipline.md` (same file as Task 1)

**Steps:**
- [ ] Add section `## Phase 3.2 — Adversarial coverage matrix audit` (after Phase 3.1 section from Task 1).
- [ ] Fragment-grade content:
  - Imperative one-liner: Opus Phase 3.2 must include coverage matrix audit for fixture/vendored-data PRs.
  - One-line why: GIM-104 — Opus focused on architectural risks, missed that fixture coverage was halved.
  - Output template (compact):
    ```
    | Spec'ed case | Landed | File |
    |--------------|--------|------|
    | <case>       | ✓ / ✗  | path:LINE |
    ```
  - One-liner: Missing rows → REQUEST CHANGES (not NUDGE).
- [ ] Verify total file size stays under 2 KB soft cap.

**Acceptance criteria:**
- Section exists with compact template and enforcement rule.
- Total `phase-review-discipline.md` stays under 2 KB.
- Clearly states missing coverage = REQUEST CHANGES.

**Depends on:** Task 1 (same file, coordinate insertion order).

---

## Task 3: Wire Phase 3.1 reference into code-reviewer.md

**Files:**
- Modify: `paperclips/roles/code-reviewer.md`

**Steps:**
- [ ] Insert a **new subsection** `### Phase 3.1 — Plan vs Implementation file-structure check` **before** the existing `### Phase 3.1 GitHub PR review bridge` (line ~117). These are separate concerns: discipline (the check) before bridge (posting the GitHub approve).
- [ ] Content (role-file-grade — enforcement details belong here, not in fragment):
  - Before mechanical APPROVE, paste output of `git diff --name-only <base>..<head>` and explicit comparison vs plan file structure.
  - Forbidden APPROVE patterns:
    - APPROVE without pasted `git diff --name-only` matching plan's file count.
    - APPROVE when PE cut scope without mention in commit/comment/plan revision.
    - "LGTM, all tests pass" without file-structure comparison.
  - If PE reduced scope with justification: evaluate argument, either APPROVE reduced scope or REQUEST CHANGES for full scope.
  - Reference: `See phase-review-discipline.md#phase-31`.
- [ ] Ensure the reference uses the exact section anchor from Task 1.

**Acceptance criteria:**
- code-reviewer.md has new subsection before the bridge section.
- Contains forbidden patterns and enforcement procedure.
- References new fragment.

**Depends on:** Task 1 (need final section header for correct anchor).

---

## Task 4: Wire Phase 3.2 reference into opus-architect-reviewer.md

**Files:**
- Modify: `paperclips/roles/opus-architect-reviewer.md`

**Steps:**
- [ ] **Create new section** `## Phase 3.2 — Coverage matrix audit discipline` after the `## Anti-patterns` section (line ~83, before `## MCP / Subagents / Skills`).
- [ ] Content (role-file-grade):
  - Adversarial review must include coverage matrix audit for fixture/vendored-data PRs.
  - Not limited to architectural risks — also verify all spec'ed edge cases landed in test fixtures.
  - Coverage matrix output template (from fragment).
  - Missing rows = REQUEST CHANGES (blocking finding, not NUDGE).
  - Reference: `See phase-review-discipline.md#phase-32`.

**Acceptance criteria:**
- opus-architect-reviewer.md has new `## Phase 3.2` section in the correct location.
- Coverage matrix audit is explicitly required, not optional.
- References new fragment.

**Depends on:** Task 2 (need final section header).

---

## Task 5: Wire scope-reduction transparency rule into python-engineer.md

**Files:**
- Modify: `paperclips/roles/python-engineer.md`

**Steps:**
- [ ] Append to existing `## Technical conventions (hard rules)` section (line 21) — do NOT create a new section that doesn't exist.
- [ ] Add bullet: `- **Scope reduction transparency.** If scope reduction necessary — ALWAYS post comment with reasoning before commit. Silent reduction = REQUEST CHANGES at Phase 3.1. See `phase-review-discipline.md`.`

**Acceptance criteria:**
- python-engineer.md contains the transparency rule as a bullet in `## Technical conventions (hard rules)`.
- Rule references the new fragment.

---

## Task 6: Bump submodule pointer + build verification

**Files:**
- Update: `paperclips/fragments/shared` (submodule pointer in Gimle-Palace)

**Steps:**
- [ ] After Tasks 1–2 PR merges in `paperclip-shared-fragments`:
  ```bash
  cd paperclips/fragments/shared
  git fetch origin && git checkout <merged-sha>
  cd ../../..
  git add paperclips/fragments/shared
  ```
- [ ] Run `bash paperclips/build.sh` — verify dist files contain new Phase 3.1 + 3.2 content.
- [ ] Commit submodule bump + role file changes together.

**Acceptance criteria:**
- Submodule pointer updated to SHA containing Tasks 1–2 changes.
- `bash paperclips/build.sh` succeeds.
- `grep -l 'phase-review-discipline' paperclips/dist/*.md` returns hits (new fragment content in built output).

**Depends on:** Tasks 1–2 merged in submodule repo.

---

## Task 7: CI verification + PR

**Steps:**
- [ ] Push feature branch `feature/GIM-114-drift-discipline`.
- [ ] Open PR into `develop`.
- [ ] PR description references GIM-114, predecessor `5da4847` (GIM-108), and GIM-104 (incident).
- [ ] CI checks pass (lint, typecheck, test, docker-build).
- [ ] Note: `qa-evidence-present` check may need `micro-slice` label since this is docs/process-only (no `services/` code changes).

**Acceptance criteria:**
- CI green.
- PR references GIM-114.

---

## Phase chain

| Phase | Owner | Gate |
|-------|-------|------|
| 1.1 Formalize | CTO | Plan file exists, GIM-114 confirmed |
| 1.2 Plan-first review | CodeReviewer | Every task has clear output; flag gaps |
| 1.2-rev2 Plan revision | CTO | Address CR findings, resubmit |
| 2a Fragment text | TechnicalWriter | Tasks 1–2: new fragment `phase-review-discipline.md` (submodule PR) |
| 2b Role file wiring | CTO | Tasks 3–5: role file references (after 2a lands section headers) |
| 2c Submodule bump + build | CTO | Task 6: pointer update + build.sh green |
| 3.1 Mechanical review | CodeReviewer | **Eat your own dog food**: apply new Phase 3.1 discipline on THIS PR |
| 3.2 Adversarial review | OpusArchitectReviewer | Apply new Phase 3.2 coverage matrix audit on THIS PR |
| 4.1 QA | QAEngineer | iMac deploy + cat-grep verify per acceptance |
| 4.2 Merge | CTO | GIM-108 merge-readiness discipline |

## Implementation notes

### Two-repo workflow

This slice spans two repos:
1. **`paperclip-shared-fragments`** (submodule): Tasks 1–2 — **new file** `phase-review-discipline.md`. Requires its own feature branch + PR.
2. **`Gimle-Palace`** (parent): Tasks 3–6 — role files + submodule bump. Feature branch `feature/GIM-114-drift-discipline`.

Tasks 1–2 must merge in the submodule BEFORE Tasks 3–6 can finalize in the parent (submodule pointer depends on merged SHA).

### Fragment density compliance (CR finding #1)

Original plan extended `git-workflow.md` (5 KB, 2.5x cap). Revised: create new fragment `phase-review-discipline.md`. This keeps `git-workflow.md` git-only and respects the 2 KB soft cap per fragment.

Content split: fragment = imperative rules + mandatory commands (fragment-grade). Role files = enforcement details, forbidden patterns, examples (role-file-grade per CR finding #5).

### Eat-your-own-dog-food

Phase 3.1 CR on THIS PR must apply the new discipline being added:
- CR pastes `git diff --name-only` and compares against this plan's file table.
- This is the first test of the new rule — if CR rubber-stamps, the discipline isn't working.

### QA acceptance dependency

Phase 4.1 verification depends on `imac-agents-deploy.sh` (GIM-112, `feature/GIM-112-imac-agents-deploy` in `/private/tmp/gimle-GIM-112`). If GIM-112 hasn't landed, QA uses manual worktree deploy.
