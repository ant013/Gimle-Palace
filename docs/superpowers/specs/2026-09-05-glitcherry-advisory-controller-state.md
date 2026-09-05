# Glitcherry advisory controller state

Date: 2026-09-05  
Status: APPROVED  
Branch: `fix/glitcherry-advisory-controller-state`  
Baseline: `db0295893313ccc8c96134919bdc5d479a8f1572` (`origin/develop`)

## Goal

Remove the remaining long-lived workflow locks from the Glitcherry slice
controller. Paperclip's live issue assignment and one shared task worktree remain
the sequential execution mechanism. The controller becomes an auditable state
ledger that follows the current clean worktree instead of refusing work because
its recorded owner or HEAD is stale.

## Assumptions

- Paperclip assigns one issue to one role at a time and the watchdog interrupts a
  stranded previous run during deterministic handoff recovery.
- Every role boundary is a clean commit. Reviewers and QA never review a dirty
  worktree.
- One active slice, one Paperclip execution workspace, one task worktree, one
  branch, and one PR remain mandatory.
- The short process-local file mutex used only around an atomic JSON rewrite is
  not a workflow lease. It is retained to prevent a torn state file and cannot
  survive a command or block the next agent.

## Scope

### In scope

- Treat `expected_owner` as routing/audit metadata, not claim authorization.
- Let a currently assigned role adopt a different controller owner while
  recording the correction.
- Let a claim or blocked-resume adopt the task worktree's current clean commit
  when branch, path, repository, and worktree identity still match.
- Remove active-lease prerequisites from obsolete recovery/checkpoint paths.
- Update generated Glitcherry role instructions and workflow documentation so
  agents do not report owner/HEAD drift as a Board blocker.
- Preserve phase, review-rejection, merge-evidence, and cleanup invariants that
  express product workflow rather than mutual exclusion.

### Out of scope

- Parallel agents editing the same task worktree.
- A second worktree, branch, slice, issue, or PR.
- Bypassing clean-commit review boundaries or allowing reviewers to modify code.
- Automatically resuming a genuine product/roadmap/credential/stage-gate block.
- Direct Paperclip database mutation or deletion of Paperclip issues.

## Affected areas

- `paperclips/projects/glitcherry-android/scripts/slice-worktree.py`
- Glitcherry controller tests under
  `paperclips/projects/glitcherry-android/tests/`
- `paperclips/projects/glitcherry-android/overlays/codex/_common.md`
- `paperclips/projects/glitcherry-android/WORKFLOW.md`
- Generated role bundles and assembly snapshots affected by those sources

## Acceptance criteria

1. `claim` creates no lease and does not fail solely because
   `expected_owner != --owner`.
2. On a clean matching task worktree, `claim` records the actual HEAD when the
   controller HEAD is stale and appends auditable owner/HEAD adoption evidence.
3. Normal handoff, review approval/rejection, merge recording, and cleanup do
   not fail solely on stale `expected_owner`; their existing phase and role
   authorization rules remain.
4. A clean blocked worktree may resume on its current clean HEAD without the
   multi-command lease/checkpoint-adoption choreography.
5. Dirty implementation recovery remains with the live assigned implementation
   role; reviewer/QA instructions still refuse dirty review evidence.
6. Terminal slices, wrong branches/worktree paths, duplicate active slices,
   unreviewed merges, missing two-repository merge evidence, and unsafe cleanup
   still fail closed.
7. Generated Glitcherry instructions never tell an agent to wait for, release,
   recover, or reconcile a controller lease/lock.
8. The watchdog's marker-based Paperclip reassignment remains the sole recovery
   mechanism for a stranded prior runtime.

## Verification plan

- Focused controller unit tests for stale-owner and clean-stale-HEAD adoption.
- Regression tests for dirty review rejection, terminal state, wrong
  branch/worktree, review cycles, merge evidence, and cleanup.
- Glitcherry prompt assembly/snapshot tests.
- Focused watchdog handoff tests to prove the marker recovery path is unchanged.
- `ruff`, `mypy`, `git diff --check`, and generated-bundle marker checks.

## Risks and rollback

- Risk: a stale agent calls the controller after reassignment. Mitigation: live
  Paperclip assignment is checked by every role before repository access; the
  marker watchdog interrupts the stranded run, and clean commit/phase rules
  prevent dirty review or merge.
- Risk: silent controller drift hides useful evidence. Mitigation: every
  automatic owner/HEAD adoption is appended to an audit list with actor, run,
  old/new value, and timestamp.
- Rollback: revert this controller/instruction change and redeploy the previous
  generated Glitcherry bundle. No product repository or Paperclip storage
  migration is involved.

## Open questions

None. The Human Engineering Lead explicitly approved removal of technical
workflow locks while retaining sequential Paperclip assignment and clean commit
boundaries.
