# Glitcherry single-worktree Paperclip protocol

Status: Approved by Human Engineering Lead; implementation in progress

## Goal

Change the deployed Glitcherry Android Paperclip project from six persistent
Android clones to one disposable slice worktree shared sequentially by all phase
owners. Enforce exclusive ownership, one primary writer, one task PR, no more
than three complete Code Review rejection cycles, and sprint-end-only QA smoke.

The source-of-truth product contract is the companion Glitcherry specification:
`docs/specs/single-slice-worktree-protocol.md` on branch
`feature/task-worktree-protocol`.

## Assumptions

- Gimle-Palace uses `develop` as the integration branch for this project because
  the existing `glitcherry-android` assembly is present there and absent from
  `main`.
- Paperclip still needs one Project workspace per role to load the correct
  generated `AGENTS.md`; those workspace roots remain agent-specific.
- Slice repository work happens outside those roots in one issue-pinned path
  visible to all roles.
- `/Users/anton/Android/Glitcherry-Android` remains the canonical clean Android
  host clone used to create Git worktrees. The host-local paths file supplies a
  dedicated task-worktree root rather than embedding machine paths in source.
- The CTO remains the sole Walker and merge authority. Exactly one of Android
  Engineer or Media Pipeline Engineer is the slice writer.
- QA performs the full smoke gate only after all sprint slices are merged and
  cleaned and the Walker is paused on an immutable candidate SHA.

## Scope

### Included

- Update the Glitcherry workflow and all six role overlays so every phase uses
  the same issue-pinned task worktree and exact HEAD sequentially.
- Add host-path configuration for a dedicated task-worktree/state root.
- Replace per-agent Android clone preparation with validation of one canonical
  clean host clone, persistent agent prompt workspaces, and the CTO control clone.
- Add a small fail-closed slice-worktree controller for create, inspect, claim,
  handoff, review-counter, merge-proof, and cleanup operations.
- Store lease/state metadata outside the Git worktree so protocol state never
  dirties the task branch.
- Keep one PR open from the first reviewable implementation head through all
  correction cycles.
- Remove QA from the normal product-slice chain and define one sprint smoke gate.
- Update generated bundle expectations and focused behavior tests.
- Re-render, deploy, reconcile the existing company idempotently, and run a
  repository-write-free canary before resuming roadmap execution.

### Excluded

- Product code, roadmap content, or automatic authoring of corrective slices.
- Parallel slices, parallel owners, or two writers in one worktree.
- Release, signing, tags, store publication, or credential changes.
- Rewriting historical diagnostic evidence.
- Deleting existing Paperclip issues or audit history.

## Runtime design

### Layout

- Keep per-agent Project workspace roots and generated `workspace/AGENTS.md`.
- Do not use or require `workspace/repo` as slice state.
- Validate one canonical Android host clone from `primary_repo_root`.
- Add `task_worktree_root` to host-local `paths.yaml`. A slice path is derived
  only from a validated issue key and slug beneath that root.
- Validate the canonical control clone from `control_repo_root` for roadmap
  status/evidence. The role workspaces remain instruction roots only.
- Store state beneath a private host-local state directory, keyed by exact issue
  ID/key. State includes branch, base/head SHA, worktree path, phase, owner,
  expected next owner, rejection count, and recovery marker.

### Exclusive lease

The controller must fail closed and use an atomic local ownership primitive. A
role may claim only when Paperclip assignment, expected owner, branch, worktree,
clean status, and HEAD all match. A living prior run or ambiguous PID prevents a
claim. Handoff records the clean committed HEAD and expected next owner; the next
role must claim before accessing the worktree.

Recovery never creates a replacement worktree or child. It preserves dirty or
unmerged state, requires exact `company -> agent -> run -> PID` attribution before
termination, and resumes the same issue.

### Review ceiling

- First review is full and must report one consolidated blocker list.
- Each later pass reviews the delta and affected invariants unless a structural
  rewrite is explicitly recorded.
- Each `CHANGES_REQUESTED` increments a durable counter. At most three such
  correction cycles may complete.
- After the third correction, the next reviewer decision is approval or
  `LOCAL_BLOCKED` escalation; no fourth autonomous fix loop is allowed.
- Non-blocking suggestions do not increment the counter or reject the slice.
- Scope/spec gaps route to CTO and cannot be counted as ordinary code defects.

### QA and sprint smoke

Normal product slices route writer -> Code Reviewer -> CTO. The writer and
reviewer run only risk-scaled targeted checks. QA is activated after the entire
sprint is merged and cleaned, against one fixed `develop` candidate SHA while the
Walker is stopped. Smoke failure is reported to the Human Engineering Lead and
does not authorize the Walker to invent a corrective slice.

### Push, merge, and cleanup

- Spec, plan, implementation, and fixes stay on one task branch in one task
  worktree.
- Push/open one PR when implementation first becomes reviewable. All corrections
  update the same PR.
- CTO squash-merges only after exact-head approval and required targeted checks.
- Existing control-plane status/evidence integration remains required.
- Cleanup requires recorded Android/control merge SHAs reachable from each
  `origin/develop`, then removes the exact clean task worktree and recorded
  local/remote task/status refs. It deliberately avoids extra feature-head
  ancestry, tree-equality, or embedded GitHub API gates that can reject a valid
  squash merge.
- The next child remains forbidden until both merges and cleanup are proven.

## Affected files and areas

- `paperclips/projects/glitcherry-android/WORKFLOW.md`.
- `paperclips/projects/glitcherry-android/overlays/codex/_common.md`.
- Role files for CTO, Android Engineer, Media Pipeline Engineer, Code Reviewer,
  and QA Engineer; CEO changes only if shared invariants require it.
- `paperclips/projects/glitcherry-android/paperclip-agent-assembly.yaml`.
- `paperclips/projects/glitcherry-android/paths.local-example.yaml`.
- `paperclips/projects/glitcherry-android/scripts/prepare-runtime-workspaces.sh`.
- A focused slice-worktree controller under
  `paperclips/projects/glitcherry-android/scripts/`.
- `paperclips/tests/test_glitcherry_android_assembly.py`.
- `paperclips/tests/test_glitcherry_android_runtime_workspaces.py`.
- New focused behavior tests for lease, rejection ceiling, handoff, recovery, and
  cleanup; project reconciliation tests only if workspace bindings change.
- Generated `paperclips/dist/glitcherry-android*` artifacts through the existing
  renderer, never by hand.

## Acceptance criteria

1. Six role-specific Paperclip workspaces remain, but no normal phase depends on
   six Android checkouts being synchronized.
2. One active slice resolves to exactly one branch, one task worktree, one state
   record, one primary writer, and one exclusive owner.
3. A concurrent or stale-owner claim is rejected before repository access.
4. Every handoff validates clean status, exact HEAD, owner transition, and prior
   process termination.
5. Normal slice flow has no QA phase; sprint smoke cannot start until all slices
   are merged/clean, candidate SHA is fixed, and Walker is stopped.
6. One task PR survives all corrections and the reviewer cannot cause a fourth
   autonomous rejection/fix cycle.
7. CTO alone merges and cannot select the next slice before Android/control merge
   proof and exact cleanup.
8. Dirty or unmerged work is never deleted during recovery.
9. Source workflow, rendered roles, scripts, tests, and Glitcherry runbooks contain
   no contradictory persistent-clone, per-slice QA, or two-loop rule.
10. Deployment updates the existing company idempotently; a write-free canary
    proves the shared path and overlap guard without starting roadmap work.

## Verification plan

- Run focused assembly/render tests and runtime workspace tests.
- Add temporary Git-fixture tests for create, claim, clean handoff, dirty refusal,
  live-owner refusal, three review cycles, blocked fourth cycle, merge proof, and
  exact cleanup.
- Render the resolved assembly and search all generated roles for matching
  worktree/lease/review/smoke invariants and forbidden stale instructions.
- Run shell syntax/static checks for changed scripts.
- Deploy only from a clean current `develop`-based worktree and reconcile the
  existing Paperclip company.
- Execute a repository-write-free canary that hands the same synthetic task state
  sequentially across applicable roles, deliberately attempts one overlapping
  claim, and confirms fail-closed behavior.
- Verify after canary that no product branch/worktree was created, no duplicate
  child exists, and watchdog did not terminate any unrelated process.

## Open questions

None. Topology, ownership, review ceiling, QA timing, merge authority, and cleanup
order were fixed by the Human Engineering Lead.
