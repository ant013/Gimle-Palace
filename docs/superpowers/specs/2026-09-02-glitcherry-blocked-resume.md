# Glitcherry blocked-slice resume

Status: Approved by Human Engineering Lead

- Date: 2026-09-02
- Baseline: `92dcb7f549f96063989da2d57f51e0f6e992d1ed`
- Branch: `fix/glitcherry-blocked-resume`
- Incident: GLA-16 / TP0-002

## Goal

Add one controller-supported way to resume the same Glitcherry slice, branch,
and worktree after a concrete `blocked` condition has been resolved. Preserve
dirty implementation work, exclusive ownership, exact HEAD checks, and the
audit trail without direct JSON/database edits, a replacement issue, or a
second worktree.

## Incident evidence

GLA-16 was blocked during the first AVD 36 run after the implementation agent
found that an `androidTest`-only activity resolves to the test package rather
than the target application process. The agent correctly stopped the emulator,
preserved evidence and dirty work, and called the controller's `block` command.

The Board then answered the structured interaction: use the existing
`MainActivity` only as the instrumentation runtime host and harden the runner's
JUnit-result parsing. Paperclip woke the CTO, but the controller could not
continue:

- state is `phase=blocked`, `expected_owner=null`, `lease=null`;
- `claim` rejects every blocked state;
- `recover` applies only to a terminated run that still owns an active lease;
- the worktree is dirty with the preserved TP0-002 implementation, so merely
  changing the phase to `plan_revision` would make the normal clean `claim`
  fail on the next check.

This is a missing controller transition, not a product or Media3 failure.

## Assumptions

- The answered Paperclip interaction remains the authoritative human decision.
- GLA-16, its recorded branch, HEAD, worktree path, and primary implementer are
  retained exactly.
- Dirty files belong to the primary implementer and must not be staged,
  committed, stashed, reset, or deleted by the CTO or operator.
- Local WIP commits are allowed as an ownership handoff mechanism; the branch
  is not pushed and no PR is opened until implementation is reviewable.
- No global role or shared agent-fragment change is needed for this incident.
  The durable process description belongs in the Glitcherry project workflow.

## Scope

### Included

- Add a `resume-blocked` command to the Glitcherry slice controller.
- Record enough block/resume audit metadata to explain every transition.
- Support a bounded dirty-worktree recovery phase owned only by the recorded
  primary implementer.
- Keep ordinary claims clean by default.
- Add focused behavior tests for clean and dirty blocked-state recovery.
- Document the operator/CTO sequence in the Glitcherry project workflow.
- Deploy the merged controller and use it to resume GLA-16.

### Excluded

- Product code, TP0-002 acceptance criteria, thresholds, or roadmap changes.
- Direct edits of private controller state or the Paperclip database.
- Replacement issues, branches, worktrees, stashes, or copied recovery trees.
- Broad relaxation of clean-worktree, lease, owner, HEAD, or branch checks.
- Changes to global role files or shared fragments for this Android-specific
  controller edge case.
- Automatic resolution of unanswered Board interactions.

## Design

### Block evidence

Before changing state, `block` verifies the recorded worktree with
`clean=False`, confirms the branch and HEAD still match the controller record,
and records:

- the phase and owner that entered the block;
- the exact recorded HEAD;
- the block reason and timestamp.

The existing reason remains visible after resume. Additive metadata must remain
compatible with current schema-v1 state files.

### `resume-blocked`

The new command accepts the issue key, CTO identity/current run id, requested
resume owner and phase, and bounded decision evidence. It runs under the
existing state lock and rejects unless:

- the state is exactly `blocked`;
- there is no expected owner or active lease;
- the recorded worktree, branch, and HEAD still match;
- no Android/control merge or cleanup has begun;
- the operator is `GlitcherryCTO`;
- the evidence is non-empty and names the resolved decision.

It never creates, removes, resets, commits, or stashes repository state.

If the worktree is clean, the only supported destination for this incident
class is `GlitcherryCTO / plan_revision`.

If the worktree is dirty, the only supported destination is the recorded
primary implementer in `implementation_recovery`. This prevents the CTO from
claiming somebody else's uncommitted implementation.

Each successful resume appends an audit record containing the prior block
reason, operator/run, evidence, dirty/clean observation, destination owner and
phase, exact HEAD, and timestamp. The command leaves `lease=null`; Paperclip
assignment/wake remains responsible for starting the destination owner's new
run.

### Dirty recovery claim and handoff

Normal `claim` behavior remains unchanged. Only
`phase=implementation_recovery` may claim a dirty recorded worktree, and only
when the claimant is the recorded primary implementer and HEAD is still the
recorded HEAD.

That implementer may inspect its own preserved changes, create one explicit
local WIP commit containing only the existing slice work, and then use the
normal clean handoff to `GlitcherryCTO / plan_revision`. No push or PR occurs at
this point. The normal handoff's clean-tree and exact-HEAD checks remain the
gate.

The CTO then updates the existing plan, commits it on the same branch, and
routes the exact plan head through the existing independent review flow before
returning implementation to the same primary implementer.

## Affected files and areas

- `paperclips/projects/glitcherry-android/scripts/slice-worktree.py`
  - add the bounded command, audit metadata, and dirty recovery claim rules.
- `paperclips/tests/test_glitcherry_slice_worktree.py`
  - add exact clean/dirty resume, rejection, preservation, and audit tests.
- `paperclips/projects/glitcherry-android/WORKFLOW.md`
  - document the project-local blocked-decision recovery sequence.
- This specification only; no generated agent roles or global fragments.

## Acceptance criteria

1. A blocked clean state can resume only to CTO plan revision through the new
   command; the following ordinary CTO claim succeeds.
2. A blocked dirty state cannot be assigned to CTO, Reviewer, QA, or another
   implementer.
3. A blocked dirty state can resume only to its recorded primary implementer in
   `implementation_recovery`; its claim verifies the same branch and HEAD while
   preserving every dirty byte.
4. The recovery implementer must produce a clean committed HEAD before normal
   handoff to CTO plan revision; dirty handoff is still rejected.
5. Wrong phase, operator, run-id syntax, owner, worktree, branch, HEAD, active
   lease, merge state, or missing decision evidence fails closed without
   changing the state file.
6. Resume never creates/deletes a worktree, branch, issue, stash, commit, or
   Paperclip record.
7. The original block reason and an append-only resume audit record remain in
   private state after the transition.
8. Existing create/claim/handoff/reject/approve/block/recover/merge/cleanup
   tests remain green.
9. The merged controller is deployed from current `develop`; GLA-16 resumes in
   its exact recorded worktree, first under Media Pipeline Engineer recovery,
   then CTO plan revision and independent review.
10. No product source, global agent role, or shared fragment changes appear in
    the PR.

## Verification plan

- Reproduce the pre-fix failure in an isolated Git fixture: dirty implementation
  + `block` + answered-decision scenario cannot be claimed.
- Run the focused controller suite:

  ```bash
  uv run pytest paperclips/tests/test_glitcherry_slice_worktree.py
  ```

- Add negative tests for every rejection in criteria 2, 4, and 5 and assert the
  state file is byte-identical after rejection.
- Assert dirty file contents and status are byte-identical before and after
  `resume-blocked` and the recovery claim.
- Run the touched script help and syntax checks and the repository's required
  paperclip-bundle checks for the changed paths.
- Inspect the final diff for the closed file set and run `git diff --check`.
- After merge, run `bash paperclips/scripts/imac-deploy.sh`, compare the deployed
  controller to `origin/develop`, and exercise `resume-blocked` on GLA-16.
- Verify Paperclip starts exactly one destination run, GLA-16 keeps the same
  issue/branch/worktree, and no second product child appears.

## Risks and rollback

- Risk: a generic unblock command could become an ownership bypass. Mitigation:
  exact blocked/no-lease state, CTO-only operator, closed destinations, recorded
  primary implementer, exact worktree/branch/HEAD, and negative tests.
- Risk: dirty work could be attributed to the wrong role. Mitigation: only the
  recorded primary implementer may claim dirty recovery.
- Risk: repeated resume erases why the slice stopped. Mitigation: preserve the
  block reason and append a resume audit entry.
- Rollback: revert the controller PR and redeploy. Never roll back GLA-16 by
  deleting its issue, state, branch, worktree, or dirty files.

## Open questions

None. The Board already selected the TP0-002 harness behavior; this change only
restores the missing safe continuation path.
