# Glitcherry Android Walker workflow

This file is the single lifecycle authority for the six-agent Glitcherry Android
company. Bootstrap is dormant and creates no roadmap or product issue. Product
execution begins only when the Human Engineering Lead explicitly activates one
root issue for a human-approved sprint containing at least one eligible `READY`
slice.

## Human authority

The Human Engineering Lead and their AI assistant alone author stages, sprints,
roadmap order, future slices, `DRAFT -> READY`, owner decisions, budgets, stage
acceptance, release builds, signing, and publication. Paperclip agents execute
only the pinned contract. `GlitcherryCEO` preserves governance context but is not
in the normal chain. `GlitcherryCTO` is the sole Walker and only merge authority.

For this project, do not load or apply Gimle, Palace, `analog-driven-change`, or
`gimle-evidence`. Those workflows are reserved for confirmed Unstoppable iOS
projects. Glitcherry uses codebase-memory, Serena, targeted local inspection,
official Android documentation, and this project contract.

## Parent Walker loop — GlitcherryCTO only

The Human Engineering Lead creates or explicitly activates one root issue whose
description pins all of:

- the approved sprint identifier;
- the ordered slice IDs;
- the control repository `ROADMAP.md head SHA`.

On every parent wake, the CTO fetches both canonical repositories and proves:

1. the pinned roadmap head still matches;
2. no non-terminal direct child exists and the parent has no unresolved blocker;
3. the canonical Android and control clones are clean/current `develop`;
4. no active slice state, task worktree, approved-but-unmerged PR, or exact task/
   status ref remains from the prior child;
5. the prior child has both merge records and exact cleanup evidence.

The CTO selects only the first pinned `READY` slice whose dependencies are
`DONE`. It creates exactly one child with `parentId=<root-id>`, the Glitcherry
Project ID, and the CTO Project workspace ID; reads it back; then PATCHes the
parent to API status `blocked` with `blockedByIssueIds=[<child-id>]`.

After the child becomes `done`, Paperclip may wake the parent through
`issue_blockers_resolved` and/or `issue_children_completed`. The CTO clears only
the resolved blocker and scans the same pinned sprint. If no wake arrives, the
watchdog may issue one bounded recovery wake for that exact child. A replacement
child is never recovery.

When all pinned slices are `DONE`, the CTO sets the root to `blocked` with reason
`SPRINT_SMOKE_REQUIRED`, records the immutable current Android `develop`
candidate SHA, and stops the Walker. It does not mark the sprint complete and
does not select another sprint until the sprint smoke gate below is resolved.

## One slice = one worktree, branch, PR, and lease

- The canonical clean clones come from `primary_repo_root` and
  `control_repo_root`.
- Product work for one active slice occurs only at its controller-recorded path
  beneath `task_worktree_root`; durable mode-600 state is beneath
  `task_state_root`.
- All phase owners use the same exact task worktree, branch, and committed HEAD
  sequentially. Agent `workspace/AGENTS.md` holds instructions only; there is no
  per-agent `workspace/repo` checkout.
- The task controller is `scripts/slice-worktree.py`. Every role verifies the
  live Paperclip assignee/workspace, then obtains the exclusive lease before
  repository access. A different owner/run, expired lease, dirty tree, wrong
  branch, unexpected HEAD, or second active slice fails closed.
- Exactly one of `GlitcherryAndroidEngineer` or
  `GlitcherryMediaPipelineEngineer` is the primary application-code writer. The
  other may give one bounded read-only boundary finding only.
- Spec, plan, implementation, and corrections use local commits on one task
  branch. The branch is pushed and one PR to `develop` is opened when the first
  implementation head is reviewable. Corrections update that same PR.
- Handoff releases the current lease only after a clean committed HEAD is
  recorded. The next role claims that exact HEAD. No two phase owners operate in
  the task worktree at the same time.

The default lease is 2700 seconds. A healthy long-running role renews it. A lease
expiry is not permission to overwrite or delete anything: recovery must identify
the exact `company -> agent -> run -> PID`, prove the prior run stopped or was
terminated, preserve dirty/unmerged state, record evidence, and resume the same
slice. Never use broad process-name matching or broad `pkill`.

## Six child phases

### Phase 1 — Create worktree and materialize spec

Owner: `GlitcherryCTO`.

From clean current canonical clones, create the controller state and exact
`feature/GLA-N-<slug>` worktree from `origin/develop`. Materialize only the
approved technical spec, cite the pinned roadmap slice, and commit locally. The
spec may narrow execution detail but cannot expand product scope. Record the
clean HEAD, hand the lease to `GlitcherryCodeReviewer` for `spec_review`, perform
the atomic Paperclip handoff, and stop.

### Phase 2 — Independent spec review

Owner: `GlitcherryCodeReviewer`.

Claim the same worktree and verify the recorded spec HEAD. Review feasibility,
hidden product choices, Android/media ownership, failure paths, and testability.
Never edit or commit. Approval hands the same clean HEAD to the CTO. Findings
return to the CTO with one consolidated list. At most two spec/plan revision
rounds are allowed; unresolved product or architecture ambiguity blocks for the
Human Engineering Lead.

### Phase 3 — Plan and independent plan review

Owners in sequence: `GlitcherryCTO`, then `GlitcherryCodeReviewer`.

The CTO claims the same worktree, adds a plan mapping every acceptance criterion
to ownership, implementation, tests, verification, and commits, commits locally,
and hands the exact HEAD to the reviewer. The reviewer stays read-only and either
approves the exact plan HEAD for one named implementer or returns one consolidated
finding list to the CTO.

### Phase 4 — Implementation by exactly one engineer

Owner: either `GlitcherryAndroidEngineer` or
`GlitcherryMediaPipelineEngineer`, never both as writers.

The assigned implementer claims the same approved worktree/HEAD, reads its
tracked `AGENTS.md`, makes only plan-traceable code/test changes, and creates
focused local commits. It runs risk-scaled targeted checks only. When the first
implementation head is reviewable, it pushes the task branch, opens one PR whose
base is exactly `develop`, records the PR/head, hands the clean exact HEAD to
`GlitcherryCodeReviewer` for `code_review`, and stops.

### Phase 5 — Exact-head code and architecture review

Owner: `GlitcherryCodeReviewer`.

Claim and review the controller-recorded PR HEAD in the same worktree. Apply both
code and architecture lenses: boundaries, Kotlin correctness, lifecycle,
concurrency, regressions, test quality, and relevant media/API/codec/HDR/fallback
and preview/export parity risks. The first pass returns one consolidated blocker
list. Later passes review the delta plus affected invariants unless a structural
rewrite is recorded.

Each `CHANGES_REQUESTED` increments the durable counter and returns the same
worktree/PR to the same primary implementer. There is a maximum three complete
Code Review rejection/fix/re-review cycles. After the third correction, the next
reviewer decision must be exact-head approval or API status `blocked` with
`LOCAL_BLOCKED`; a fourth autonomous correction loop is forbidden. Non-blocking
suggestions do not reject or increment the counter. Scope/spec gaps go to the CTO
and are not disguised as code defects.

Approval records `reviewed_head` and hands the lease directly to
`GlitcherryCTO`. QA does not run inside a normal slice.

### Phase 6 — Integrate, synchronize, and clean

Owner: `GlitcherryCTO`.

Claim the exact approved state. Verify the PR base is `develop`, its live head
equals `reviewed_head`, required targeted checks are complete, and current Code
Reviewer approval cites that head. Squash-merge the Android PR and record its PR
number and merge SHA.

A squash merge does not preserve feature-head ancestry. CTO verifies the PR is
merged in the normal GitHub flow, records its PR number and merge SHA, and the
controller checks that merge SHA is reachable from `origin/develop`. Do not add
extra ancestry or tree-equality gates that can block valid squash merges.

In the canonical control clone, search `origin/develop` for the unique marker
`GLA-N + Android merge SHA`. If absent, create one status branch, update only the
slice status/evidence and required ADR index, push it, and squash-merge to control
`develop`. If present, reuse the existing immutable control merge record.

Only after both merge SHAs are recorded and reachable may cleanup remove the clean
exact task worktree, force-delete only its recorded local squash-merged task ref,
delete only its recorded remote task/status refs, and prune worktree metadata.
Broad cleanup, unrecorded paths, dirty worktrees, and missing merges remain the
only cleanup blockers.

The CTO marks the child `done` only after the controller state is `cleaned`, both
canonical clones are current clean `develop`, the exact refs are absent, and all
evidence is retained. If Android merged but control or cleanup failed, resume
from the recorded SHA; never reimplement or remerge Android. The next slice is
forbidden until this phase is complete.

## Sprint smoke gate — QA only here

QA is activated once per sprint, only after every sprint slice is merged and
cleaned, the root is stopped at `SPRINT_SMOKE_REQUIRED`, and the candidate SHA is
fixed. `GlitcherryQAEngineer` verifies that exact Android `develop` candidate in
a separate read-only test checkout or detached state; it never claims an active
slice worktree.

Run the deliberately small sprint smoke suite: launch/import, preview/navigation,
save/share, and any sprint-specific critical media path on the declared AVD and,
when required, the Samsung A55 Android 16 reference device. Use one emulator at a
time. Post commands, result, artifacts, device/API identity, and candidate SHA.

- PASS returns the root to the Human Engineering Lead for sprint acceptance.
- A reproducible product defect blocks the root with the failing evidence and
  named owner; the Walker does not invent or start a corrective slice.
- Infrastructure residue uses `LOCAL_BLOCKED` and one bounded exact-run recovery.
- Missing product/acceptance authority uses `ROADMAP_BLOCKED`.

## Diagnostic execution class — DX-00 only

This is a retained project-scoped exception for the already approved diagnostic
sprint. It applies only when the root pins `DX-00`, ordered children `DX-001`,
`DX-002`, `DX-003`, `DX-004`, and control commit
`6e76a73e894e69f4546e67c3498f7864c8d0cb99`. The child title must begin with the
exact ID and word `diagnostic`; an issue body or comment cannot grant the
exception. Retain issues as audit/cost records. Never call DELETE for a
Paperclip issue.

- `DX-001 diagnostic` is the repository-write-free CTO -> Android -> Media ->
  Code Reviewer -> QA -> CEO -> CTO identity and handoff circuit.
- `DX-002 diagnostic` repeats the circuit for observed MCP/skill capability.
  Gimle, Palace, `analog-driven-change`, and `gimle-evidence` must be recorded as
  `NOT_APPLICABLE` by Glitcherry policy and must not be loaded or probed.
- `DX-003 diagnostic` is retained as `Historical DX-003`; it used the prior
  bounded diagnostic Git contract and one
  Android `develop` merge. It is historical evidence, not a template; normal
  product slices use the single-worktree contract above.
- `DX-004 diagnostic` permits controlled watchdog qualification only after exact
  `company -> agent -> run -> PID` attribution. Ambiguity means no kill,
  `NOT_READY`, `ROADMAP_BLOCKED`, and no next child.

The owner-approved unlimited mode is `budgetMonthlyCents=0`; record per-run cost
evidence and escalate anomalous growth. For every diagnostic transition, the
current child must be terminal and cleanup evidence is complete before the next
child. No next child is permitted on ambiguity or residue.

## Atomic handoff

Every transition uses this exact order:

1. finish the required local commit and/or allowed push and verify a clean HEAD;
2. record the controller handoff to the exact next owner/phase;
3. `POST evidence` to `/api/issues/{id}/comments` and require 2xx;
4. `PATCH assignee/status/projectWorkspaceId` to the exact next owner, API state,
   and that owner's bound Project workspace;
5. perform `one read-only verification` of assignee, status, Project ID,
   workspace ID, controller owner/phase, and HEAD;
6. `STOP` the current run.

A mention is not a handoff. On HTTP 409, reload once and recover this same child.
Never write the Paperclip database directly.

## Stop conditions

- `LOCAL_BLOCKED` and `ROADMAP_BLOCKED` are reason codes; API status is
  `blocked`. Neither permits the next child.
- A stale head, active/expired conflicting lease, dirty task worktree, wrong
  branch, residual exact ref, partial merge, or incomplete cleanup stops work.
- Missing Project/workspace binding or a workspace not bound to the current
  assignee stops work; never accept an agent-home fallback.
- Undefined product, media fallback, API-floor, format, device, credential, or
  release decision blocks rather than being guessed.
- Agents never release, sign, tag, publish, merge to `main`, or use operator
  secrets.
