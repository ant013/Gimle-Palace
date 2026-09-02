# Glitcherry recovery checkpoint adoption

Status: Proposed for Human Engineering Lead review

- Date: 2026-09-02
- Baseline: `87626106d5029c8ac2e73add600facf37bf8c303`
- Branch: `fix/gla16-adopt-checkpoint-transition`
- Incident: GLA-16 / TP0-002

## Goal

Add one narrow, controller-supported transition that lets GlitcherryCTO adopt a
clean committed checkpoint created by the recorded primary implementer when a
terminated implementation run advanced the task worktree but failed before the
controller could record the new HEAD. Preserve the same issue, branch,
worktree, commits, recovery evidence, and exclusive ownership without editing
private state directly or resuming implementation.

## Incident evidence

The TP0-002 Media implementation began from controller HEAD
`aa39fa8164bbd85b7ca2344a478f5ff946f2de58`. The primary implementer made
bounded local commits while investigating the AVD 36 timing failure and left the
same task worktree clean at
`16bcaa8b574cf2e3e96244857d0d3f71871c7deb`.

The implementer's attempt to enter the controller's blocked state failed closed
because `block` requires the worktree HEAD to equal the already recorded HEAD.
After the implementation heartbeat ended, the supported `recover` command
removed its stale lease and recorded exact terminated-run evidence. The
resulting state is:

- `phase=recovery`;
- `expected_owner=GlitcherryCTO`;
- `lease=null`;
- controller `head_sha=aa39fa8...`;
- clean recorded worktree HEAD `16bcaa8...`;
- `recovery_resume_owner=GlitcherryMediaPipelineEngineer`;
- `recovery_resume_phase=implementation`.

`claim` correctly rejects the mismatch, but no existing transition can validate
and record the retained checkpoint. `handoff` requires a lease, `recover`
requires a matching active lease, and `resume-blocked` applies only to
`phase=blocked` while still requiring an equal HEAD. This is a controller
recovery gap, not permission to weaken ordinary handoff checks.

Separately, the Human Engineering Lead has authorized the recommended timing
path: CTO will revise the existing TP0-002 plan for a Media3 1.11.0-compatible
measurement method and send that exact plan HEAD through independent review
before implementation resumes. This controller change only restores the safe
same-slice route to that plan revision.

## Assumptions

- GLA-16 remains the same Paperclip issue and retains its recorded task branch,
  worktree path, primary implementer, and local commits.
- The current worktree is clean and the retained checkpoint is a linear
  descendant of the controller-recorded HEAD.
- The latest controller recovery record names the exact terminated primary
  implementer run that produced or retained the advanced checkpoint.
- GlitcherryCTO invokes the new transition from a real Paperclip heartbeat with
  its current run ID after the merged controller is deployed.
- Adoption records repository state only. It does not approve the product
  result, change acceptance criteria, resume implementation, push a branch, or
  open a PR.
- Existing schema-v1 state files remain readable. New audit fields are additive.

## Scope

### Included

- Add an `adopt-recovery-checkpoint` command to the Glitcherry slice controller.
- Validate the exact old HEAD, exact current clean worktree HEAD, linear
  ancestry, recovery owner, recovery phase, branch, path, lease, and merge state
  before changing controller state.
- Append an audit record tying the old/new HEAD pair to the CTO run, human
  evidence, and latest terminated-run recovery record.
- Keep the controller in `phase=recovery`, owned by CTO with no lease, so the
  normal `claim` and handoff to CTO `plan_revision` remain mandatory.
- Add focused success and fail-closed tests.
- Document the incident class and recovery sequence in the Glitcherry workflow.
- After merge, deploy the controller, adopt the exact GLA-16 checkpoint, answer
  the existing timing interaction with the authorized revised-plan option, and
  wake the same CTO-owned issue.

### Excluded

- Android product or test-harness code changes.
- Selecting the replacement timing implementation inside this PR.
- Editing the TP0-002 plan or acceptance criteria in Gimle Palace.
- Direct controller JSON or Paperclip database edits.
- Creating a replacement issue, branch, worktree, commit, stash, or copied
  recovery tree.
- Relaxing normal `claim`, `handoff`, `block`, `resume-blocked`, merge, or
  cleanup HEAD checks.
- Adopting dirty worktrees, divergent commits, merge commits, or a checkpoint
  from an unrecorded recovery event.
- Automatic adoption by watchdog or by a non-CTO role.

## Design

### Command contract

Add:

```text
adopt-recovery-checkpoint
  --issue-key <GLA-N>
  --operator GlitcherryCTO
  --run-id <current Paperclip CTO run>
  --expected-old-head <40-hex controller HEAD>
  --new-head <40-hex retained checkpoint HEAD>
  --evidence <bounded human/recovery evidence>
```

The command executes under the existing state-file lock and performs no Git
write. It rejects unless all of the following are true:

1. The operator is exactly `GlitcherryCTO`, the run ID is valid, and evidence is
   at least twelve non-whitespace characters.
2. State is exactly `phase=recovery`, `expected_owner=GlitcherryCTO`, and
   `lease=null`.
3. Android/control merge recording and cleanup have not started.
4. The latest recovery record exists, has not already been used for a checkpoint
   adoption, and names the current `recovery_resume_owner`.
5. The recovery resume owner is the recorded primary implementer and the
   recovery resume phase is `implementation`, `implementation_fix`, or
   `implementation_recovery`.
6. `--expected-old-head` equals the current controller `head_sha`.
7. The recorded worktree exists at the exact path, is the repository root, is
   on the recorded branch, and is clean including untracked files.
8. `--new-head` is a full SHA, differs from the old HEAD, and equals the actual
   worktree HEAD.
9. The old HEAD is an ancestor of the new HEAD, and the range contains no merge
   commits.

Every rejection occurs before `_write_state`; the state file and worktree must
remain byte-identical.

### Successful state change

On success, append one `checkpoint_adoptions` entry containing:

- old and new HEAD;
- operator and current run ID;
- evidence;
- recovered owner, recovered run ID, recovery phase, and recovery timestamp;
- adoption timestamp.

Then update only:

- `head_sha` to the validated new HEAD;
- `updated_at` to the adoption timestamp.

The command deliberately retains:

- `phase=recovery`;
- `expected_owner=GlitcherryCTO`;
- `lease=null`;
- `primary_implementer`;
- `recovery_resume_owner` and `recovery_resume_phase`;
- prior recovery, block, and resume history.

This makes adoption a bookkeeping repair rather than a phase transition. The
next CTO heartbeat must still perform the ordinary `claim`, then hand the same
clean HEAD to `GlitcherryCTO / plan_revision`. That handoff clears the recovery
resume fields through the existing path. Plan revision and independent plan
review remain unchanged.

### Replay and ambiguity

One recovery record may authorize at most one checkpoint adoption. Reusing it,
trying to adopt the already recorded HEAD, or observing further commits after
adoption fails closed. A later legitimate incident requires a new exact-run
`recover` record.

The controller does not infer which commits are desirable. The human evidence
authorizes retaining the exact new SHA; ancestry, cleanliness, and recovery
identity establish that it is the same bounded work stream. Code correctness is
still decided by the existing plan, Code Reviewer, tests, and merge gates.

## Affected files and areas

- `paperclips/projects/glitcherry-android/scripts/slice-worktree.py`
  - add the new command, validation, and append-only audit record.
- `paperclips/tests/test_glitcherry_slice_worktree.py`
  - reproduce the stale-head recovery incident and cover success/rejection
    invariants.
- `paperclips/projects/glitcherry-android/WORKFLOW.md`
  - document when checkpoint adoption is allowed and the required continuation.
- This specification only; no global fragments, roles, watchdog code, or product
  repository files.

## Acceptance criteria

1. A recovered implementation state with a clean linear advanced checkpoint can
   be adopted only by CTO using exact old/new SHA and bounded evidence.
2. Successful adoption changes `head_sha`, appends one complete audit record,
   preserves all prior state, and performs no repository write.
3. After adoption, the ordinary CTO `claim` succeeds at the new HEAD; the
   existing CTO-to-self `plan_revision` handoff remains required before plan
   editing.
4. Wrong phase, expected owner, operator, run ID, old SHA, new SHA, worktree,
   branch, dirty state, active lease, missing/mismatched/reused recovery record,
   recovery owner/phase, merge state, divergent history, or merge commit fails
   closed with a byte-identical state file.
5. The command cannot adopt a checkpoint produced outside the recorded primary
   implementer's terminated implementation recovery path.
6. Existing controller commands and tests remain green; their strict HEAD gates
   are unchanged.
7. Workflow documentation says checkpoint adoption is exceptional bookkeeping,
   not approval, implementation resumption, or a substitute for normal handoff.
8. The PR contains only the four declared files and no secrets or GLA-16 private
   state.
9. After squash merge and iMac deployment, the deployed controller is reachable
   from current Gimle Palace `origin/develop` and exposes the new help entry.
10. GLA-16 adopts exactly `aa39fa8... -> 16bcaa8...`, retains the same worktree
    and branch, and then routes the authorized timing-plan revision through CTO
    and independent Code Reviewer before Media implementation resumes.

## Verification plan

- Reproduce the incident in the isolated Git fixture:
  implementation owner holds a lease, creates multiple local commits, its run is
  recovered, controller HEAD remains old, and normal CTO claim fails.
- Add a success test for `adopt-recovery-checkpoint`, then prove CTO can claim
  the exact adopted HEAD and hand it to `plan_revision`.
- Add table-driven rejection tests for every criterion 4 condition and assert:
  controller state bytes, worktree status, branch, and HEAD do not change.
- Prove the old HEAD is an ancestor of the new HEAD and reject a side-branch
  checkpoint plus a merge-commit range.
- Run:

  ```bash
  python3 -m py_compile \
    paperclips/projects/glitcherry-android/scripts/slice-worktree.py
  python3 -m pytest -q paperclips/tests/test_glitcherry_slice_worktree.py
  python3 -m pytest -q \
    paperclips/tests/test_glitcherry_android_assembly.py \
    paperclips/tests/test_validate_instructions.py
  python3 paperclips/projects/glitcherry-android/scripts/slice-worktree.py \
    --paths paperclips/projects/glitcherry-android/paths.local-example.yaml \
    adopt-recovery-checkpoint --help
  git diff --check
  ```

- Inspect the final diff against baseline for the closed file set.
- After merge, run the explicitly requested iMac deployment, compare the
  deployed script hash/ref with merged `origin/develop`, and invoke the command
  from the CTO wake rather than editing state manually.
- Read back controller state, Paperclip issue/interaction, live runs, worktree
  status/HEAD, and ensure no second child/worktree/branch appears.

## Risks and rollback

- Risk: checkpoint adoption becomes a general stale-HEAD bypass. Mitigation:
  recovery-only state, CTO-only caller, exact old/new SHAs, recorded primary
  implementer recovery, clean linear non-merge history, one use per recovery
  event, and fail-closed tests.
- Risk: adoption treats implementation as approved. Mitigation: phase remains
  `recovery`; normal claim, plan revision, independent review, implementation,
  code review, and merge gates are unchanged.
- Risk: a second process advances the worktree during validation. Mitigation:
  state lock plus repeated exact worktree HEAD/clean checks immediately before
  the single state write; no repository write is performed.
- Risk: deployment wakes CTO before the timing decision is recorded. Mitigation:
  deploy first, then answer the existing interaction once, allowing its
  `wake_assignee` path to start exactly one CTO run.
- Rollback: revert the controller PR and redeploy. Do not roll back by deleting
  GLA-16, rewriting its task branch, resetting its worktree, or editing its
  private controller state.

## Open questions

None. The Human Engineering Lead authorized both the exact checkpoint adoption
path and preparation of a newly reviewed timing-collection plan.
