# GIM-114 — Plan-implementation drift discipline

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close plan-implementation drift failure mode discovered in GIM-104. Add file-count verification discipline to Phase 3.1 (CR) and coverage matrix audit to Phase 3.2 (Opus). Symmetric with GIM-108 (merge-readiness discipline) — together they harden Phase 3.x against the two main failure patterns: escalate-without-evidence and silent-scope-reduction.

**Predecessor SHA:** `5da4847` (GIM-108 merge) + `54691a7` (GIM-104 — incident source)

**Spec:** Issue body GIM-114 (Board-authored)

**Root path prefix:** `paperclips/` — fragments in submodule `paperclips/fragments/shared/`, roles in `paperclips/roles/`.

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `paperclips/fragments/shared/fragments/git-workflow.md` | Modify (submodule) | Add §Phase 3.1 + §Phase 3.2 sections |
| `paperclips/roles/code-reviewer.md` | Modify | Wire §Phase 3.1 reference |
| `paperclips/roles/opus-architect-reviewer.md` | Modify | Wire §Phase 3.2 reference |
| `paperclips/roles/python-engineer.md` | Modify | Wire scope-reduction transparency rule |
| `paperclips/fragments/shared` (submodule pointer) | Bump | After submodule PR merges |

---

## Task 1: Add Phase 3.1 file-structure check to git-workflow.md (submodule)

**Files:**
- Modify: `paperclips/fragments/shared/fragments/git-workflow.md`

**Steps:**
- [ ] Add new section `### Phase 3.1 — Plan vs Implementation file-structure check` after the existing `### Phase 4.2 — Merge-readiness reality-check` section (or before it, maintaining ascending phase order).
- [ ] Content must include:
  - Mandatory CR step: paste `git diff --name-only <base>..<head>` and compare against plan's file table.
  - Forbidden APPROVE patterns:
    - APPROVE without pasted `git diff --name-only` matching plan's file count.
    - APPROVE when PE cut scope without mention in commit/comment/plan revision.
    - "LGTM, all tests pass" without file-structure comparison.
  - PE scope-reduction protocol: PE must post comment with reasoning before committing reduced scope. CR evaluates: APPROVE reduced scope OR REQUEST CHANGES for full scope. Never silent.
- [ ] Use the same style as existing `### Phase 4.2` section (forbidden response patterns table, mandatory commands block).

**Acceptance criteria:**
- New section exists in git-workflow.md.
- Contains at least: mandatory command, forbidden patterns, PE-reduction protocol.
- Ascending phase order maintained (3.1 before 3.2 before 4.2).

**NOTE:** This requires a commit in the `paperclip-shared-fragments` submodule repo (`git@github.com:ant013/paperclip-shared-fragments.git`), not in Gimle-Palace directly. Create a branch in the submodule, commit, push, PR.

---

## Task 2: Add Phase 3.2 coverage matrix audit to git-workflow.md (submodule)

**Files:**
- Modify: `paperclips/fragments/shared/fragments/git-workflow.md` (same file as Task 1)

**Steps:**
- [ ] Add section `### Phase 3.2 — Adversarial coverage matrix audit` (after Phase 3.1 section from Task 1).
- [ ] Content must include:
  - Opus Phase 3.2 mandate expansion: not just architectural risks, also coverage matrix audit.
  - For every test fixture / vendored data / synthetic factory in the PR, verify all edge cases from spec landed.
  - Output template:
    ```
    Coverage matrix audit:
    | Spec'ed case | Landed | File |
    |--------------|--------|------|
    | <case 1>     | ✓      | path/to/test.py:LINE |
    | <case 2>     | ✗ MISSING | (not found in fixture or test) |
    ```
  - Missing rows → blocking finding (REQUEST CHANGES, not NUDGE).

**Acceptance criteria:**
- Section exists with template and enforcement rule.
- Clearly states missing coverage = REQUEST CHANGES.

**Depends on:** Task 1 (same file, coordinate insertion order).

---

## Task 3: Wire Phase 3.1 reference into code-reviewer.md

**Files:**
- Modify: `paperclips/roles/code-reviewer.md`

**Steps:**
- [ ] Locate `### Phase 3.1 GitHub PR review bridge` section (line ~117).
- [ ] Add a new subsection or bullet: "Before mechanical APPROVE — paste output of `git diff --name-only <base>..<head>` and explicit comparison vs plan file structure. See `git-workflow.md#phase-31-plan-vs-implementation-file-structure-check`."
- [ ] Ensure the reference uses the exact section anchor from Task 1.

**Acceptance criteria:**
- code-reviewer.md references the new git-workflow.md section.
- Reference is in the Phase 3.1 area of the role file.

**Depends on:** Task 1 (need final section header for correct anchor).

---

## Task 4: Wire Phase 3.2 reference into opus-architect-reviewer.md

**Files:**
- Modify: `paperclips/roles/opus-architect-reviewer.md`

**Steps:**
- [ ] Locate the Phase 3.2 / adversarial review section.
- [ ] Add: "Adversarial review must include coverage matrix audit for fixture/vendored-data PRs. Not limited to architectural risks. See `git-workflow.md#phase-32-adversarial-coverage-matrix-audit`."

**Acceptance criteria:**
- opus-architect-reviewer.md references the new git-workflow.md section.
- Coverage matrix audit is explicitly required, not optional.

**Depends on:** Task 2 (need final section header).

---

## Task 5: Wire scope-reduction transparency rule into python-engineer.md

**Files:**
- Modify: `paperclips/roles/python-engineer.md`

**Steps:**
- [ ] Locate Phase 2 / implementation section.
- [ ] Add: "If scope reduction is necessary — ALWAYS post comment with reasoning before commit. Silent reduction = REQUEST CHANGES at Phase 3.1."

**Acceptance criteria:**
- python-engineer.md contains the transparency rule.
- Rule is in the implementation phase context.

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
- `grep -l 'Phase 3.1' paperclips/dist/*.md` returns hits (new content in built output).

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
| 2a Fragment text | TechnicalWriter | Tasks 1–2: new sections in git-workflow.md (submodule PR) |
| 2b Role file wiring | CTO | Tasks 3–5: role file references (after 2a lands section headers) |
| 2c Submodule bump + build | CTO | Task 6: pointer update + build.sh green |
| 3.1 Mechanical review | CodeReviewer | **Eat your own dog food**: apply new Phase 3.1 discipline on THIS PR |
| 3.2 Adversarial review | OpusArchitectReviewer | Apply new Phase 3.2 coverage matrix audit on THIS PR |
| 4.1 QA | QAEngineer | iMac deploy + cat-grep verify per acceptance |
| 4.2 Merge | CTO | GIM-108 merge-readiness discipline |

## Implementation notes

### Two-repo workflow

This slice spans two repos:
1. **`paperclip-shared-fragments`** (submodule): Tasks 1–2 — new sections in git-workflow.md. Requires its own feature branch + PR.
2. **`Gimle-Palace`** (parent): Tasks 3–6 — role files + submodule bump. Feature branch `feature/GIM-114-drift-discipline`.

Tasks 1–2 must merge in the submodule BEFORE Tasks 3–6 can finalize in the parent (submodule pointer depends on merged SHA).

### Eat-your-own-dog-food

Phase 3.1 CR on THIS PR must apply the new discipline being added:
- CR pastes `git diff --name-only` and compares against this plan's file table.
- This is the first test of the new rule — if CR rubber-stamps, the discipline isn't working.

### QA acceptance dependency

Phase 4.1 verification depends on `imac-agents-deploy.sh` (GIM-112, `feature/GIM-112-imac-agents-deploy` in `/private/tmp/gimle-GIM-112`). If GIM-112 hasn't landed, QA uses manual worktree deploy.
