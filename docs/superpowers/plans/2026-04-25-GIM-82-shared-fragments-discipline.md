# GIM-82 Implementation Plan — Shared-fragments discipline updates

**Spec:** `docs/superpowers/specs/2026-04-25-shared-fragments-discipline-design.md`
**Branch:** `feature/GIM-82-shared-fragments-discipline` (from `09e7a66`)
**Submodule SHA (baseline):** `6374423`

## Scope

Extend 3 existing fragments in `ant013/paperclip-shared-fragments` repo (no new files). Bump submodule pointer in this repo. Rebuild agent bundles.

## Tasks

### Task 1 — Extend `worktree-discipline.md` (submodule repo)

**Owner:** PythonEngineer (or any available engineer)
**Files:** `fragments/worktree-discipline.md`
**What:** Append "Cross-branch carry-over forbidden" section per spec §3.1.
**Acceptance:**
- Section present with Rule, Why, Practical guidance, How CR enforces subsections.
- `build.sh` passes — `dist/*.md` regenerated.
- No changes to any other fragment.

### Task 2 — Extend `compliance-enforcement.md` (submodule repo)

**Owner:** Same engineer as Task 1
**Files:** `fragments/compliance-enforcement.md`
**What:** Append "Evidence rigor" + "Scope audit" sections per spec §3.2.
**Acceptance:**
- Both sections present with exact tool-output examples.
- `build.sh` passes.

### Task 3 — Extend `pre-work-discovery.md` (submodule repo)

**Owner:** Same engineer as Task 1
**Files:** `fragments/pre-work-discovery.md`
**What:** Append "External library reference rule" + "Existing-field semantic-change rule" sections per spec §3.3.
**Acceptance:**
- Both sections present with Why blocks referencing N+1a incidents.
- `build.sh` passes.

### Task 4 — PR in submodule repo

**Owner:** Same engineer
**What:** Open PR in `ant013/paperclip-shared-fragments` with Tasks 1–3 as a single commit. Get it merged.
**Acceptance:** PR merged, new SHA recorded.

### Task 5 — Bump submodule pointer in gimle-palace

**Owner:** Same engineer
**What:** `cd paperclips/fragments/shared && git checkout <new-sha> && cd ../../.. && git add paperclips/fragments/shared`
**Files:** `paperclips/fragments/shared` (submodule pointer)
**Acceptance:** `git submodule status` shows new SHA.

### Task 6 — Rebuild agent bundles

**Owner:** Same engineer
**What:** Run `paperclips/build.sh` to regenerate `paperclips/dist/*.md`.
**Acceptance:**
- `grep -l 'carry-over' paperclips/dist/*.md` returns ≥1 agent bundle.
- `grep -l 'Evidence rigor' paperclips/dist/*.md` returns ≥1 agent bundle.
- `grep -l 'External library reference rule' paperclips/dist/*.md` returns ≥1 agent bundle.

### Task 7 — Push & open PR in gimle-palace

**Owner:** Same engineer
**What:** Commit submodule bump + rebuilt dist, push branch, open PR → develop.
**Acceptance:** PR open with CI checks queued.

## Dependencies

- Tasks 1–3 are independent of each other, can be done in parallel or serial (same commit).
- Task 4 depends on Tasks 1–3.
- Tasks 5–7 depend on Task 4.
- No code dependencies on other GIM issues — this slice is doc-only.

## Phase flow

| Phase | Agent | Work |
|-------|-------|------|
| 1.1 Formalize | CTO | Verify spec, cut branch, write plan ← **this** |
| 1.2 Plan-first review | CodeReviewer | Validate plan completeness |
| 2 Implement | PythonEngineer | Tasks 1–7 |
| 3.1 Mechanical review | CodeReviewer | Verify fragment text + dist grep |
| 3.2 Adversarial review | OpusArchitectReviewer | Check for rule gaps/conflicts |
| 4.1 QA live smoke | QAEngineer | Verify deployed bundles on iMac |
| 4.2 Merge | CTO | Squash-merge to develop |

## Risks

- Submodule PR cycle adds latency (separate repo). Mitigation: engineer can self-merge if submodule repo has no branch protection.
- Fragment text may conflict with existing wordings. Mitigation: CR Phase 1.2 validates no contradiction with existing rules.
