# GIM-90 Implementation Plan — QA checkout discipline (restore develop after Phase 4.1)

**Issue:** GIM-90
**Branch:** `feature/GIM-90-qa-checkout-discipline` (from `deec337` develop)
**Submodule SHA (baseline):** `14ce7d9`

## Problem

QAEngineer checks out feature branches on the iMac production checkout (`/Users/Shared/Ios/Gimle-Palace`) during Phase 4.1 smoke testing but does not restore `develop` before exiting. This leaves the production checkout on a stale feature branch, breaking deployments and causing operator intervention. Confirmed observation: 2026-04-25 14:42 UTC (GIM-77 branch left checked out).

## Scope

Add one new section to `worktree-discipline.md` in `ant013/paperclip-shared-fragments`. No new fragment files. Rebuild dist. Bump submodule pointer.

## Tasks

### Task 1 — Extend `worktree-discipline.md` (submodule repo)

**Owner:** PythonEngineer
**Files:** `fragments/worktree-discipline.md`
**What:** Append a new section "QA returns production checkout to develop after Phase 4.1" after the existing "Cross-branch carry-over forbidden" section.

Content must include:
- **Rule:** After posting Phase 4.1 evidence comment, before terminating the run, QA agent MUST run `git checkout develop && git pull --ff-only origin develop` on the production checkout path.
- **Why:** Production checkout must remain on develop. Reference GIM-48 incident (2026-04-18) for the cost of leaving feature branches in production state.
- **Dirty worktree handling:** If working tree is dirty after smoke (e.g. uncommitted compose modifications), commit to the feature branch first OR `git stash`, then checkout develop.
- **Verification:** `git branch --show-current` must output `develop` before run exit.

**Acceptance:**
- Section present with Rule, Why, Dirty worktree handling, Verification subsections.
- `build.sh` passes — `dist/*.md` regenerated with the new rule visible in QA dist.
- No changes to any other fragment.

### Task 2 — Commit and push in submodule repo

**Owner:** PythonEngineer
**What:** Commit Task 1 change in the submodule with message `feat(GIM-90): add QA checkout-restore rule to worktree-discipline`. Push directly to `main` of `ant013/paperclip-shared-fragments` (single-writer submodule, no PR required per established pattern from GIM-82).
**Acceptance:** New SHA on `main` of the submodule repo.

### Task 3 — Bump submodule pointer + rebuild dist in gimle-palace

**Owner:** PythonEngineer
**Files:**
- `paperclips/fragments/shared` (submodule pointer)
- `paperclips/dist/qa-engineer.md` (rebuilt output)
**What:**
1. `cd paperclips/fragments/shared && git checkout <new-sha> && cd ../../..`
2. `git add paperclips/fragments/shared`
3. `bash paperclips/build.sh`
4. `git add paperclips/dist/qa-engineer.md`
5. Commit with message `feat(GIM-90): bump shared-fragments + rebuild dist — QA checkout-restore rule`
**Acceptance:**
- Submodule pointer updated to new SHA.
- `paperclips/dist/qa-engineer.md` contains the new "QA returns production checkout to develop" section.
- `grep -q "returns production checkout" paperclips/dist/qa-engineer.md` succeeds.

### Task 4 — Push feature branch and open PR

**Owner:** PythonEngineer
**What:** Push `feature/GIM-90-qa-checkout-discipline` to origin. Open PR into `develop`.
**Acceptance:** PR open, CI green.

## Phase sequence

| Phase | Agent | What |
|---|---|---|
| 1.1 Formalize | CTO | This plan (done) |
| 1.2 Plan-first review | CodeReviewer | Validate plan completeness |
| 2 Implementation | PythonEngineer | Tasks 1–4 |
| 3.1 Mechanical review | CodeReviewer | Verify fragment text, dist rebuild, submodule bump |
| 3.2 Adversarial review | OpusArchitectReviewer | Check edge cases in the rule (dirty worktree, concurrent agents) |
| 4.1 QA live smoke | QAEngineer | Run Phase 4.1 on any existing slice, verify checkout returns to develop |
| 4.2 Merge | CTO | Squash-merge to develop, chain-trigger GIM-81 |

## Dependencies

None. This is a standalone governance-fragment change.

## Notes

- The QA role file `paperclips/roles/qa-engineer.md` already includes `<!-- @include fragments/shared/fragments/worktree-discipline.md -->`, so the new section will automatically appear in the rebuilt dist. No role file edits needed.
- Chain trigger: after Phase 4.2 merge, CTO starts GIM-81 Phase 1.1 per chain authorization in issue body.
