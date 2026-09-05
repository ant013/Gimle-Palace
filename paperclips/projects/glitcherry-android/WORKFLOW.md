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
Project ID, the shared Project workspace ID, and explicit
`executionWorkspaceSettings.mode=isolated_workspace`; reads it back; then
PATCHes the parent to API status `blocked` with
`blockedByIssueIds=[<child-id>]`. The issue-level override prevents accidental
inheritance of the root's execution workspace.

After the child becomes `done`, Paperclip may wake the parent through
`issue_blockers_resolved` and/or `issue_children_completed`. The CTO clears only
the resolved blocker and scans the same pinned sprint. If no wake arrives, the
watchdog may issue one bounded recovery wake for that exact child. A replacement
child is never recovery.

When all pinned slices are `DONE`, the CTO sets the root to `blocked` with reason
`SPRINT_SMOKE_REQUIRED`, records the immutable current Android `develop`
candidate SHA, and stops the Walker. It does not mark the sprint complete and
does not select another sprint until the sprint smoke gate below is resolved.

## One slice = one worktree, branch, PR, and sequential owner

<!-- GLITCHERRY_INTERRUPT_HANDOFF_V2 -->

- The canonical clean clones come from `primary_repo_root` and
  `control_repo_root`.
- Product work for one active slice occurs only at its controller-recorded path
  beneath `task_worktree_root`; durable mode-600 state is beneath
  `task_state_root`.
- All phase owners use the same exact Paperclip `executionWorkspaceId`, task
  worktree, branch, and committed HEAD sequentially. Each role's absolute
  required `instructionsFilePath` supplies its own generated `AGENTS.md`; there
  is no per-agent product checkout.
- The task controller is `scripts/slice-worktree.py`. Every role verifies the
  live Paperclip assignee/workspace and exact worktree/branch before repository
  access. `claim` is optional reconciliation: it creates no persistent ownership
  record and audibly adopts stale controller owner or clean committed HEAD
  metadata. A dirty review boundary, wrong worktree/branch, or second active
  slice still fails closed.
- Exactly one of `GlitcherryAndroidEngineer` or
  `GlitcherryMediaPipelineEngineer` is the primary application-code writer. The
  other may give one bounded read-only boundary finding only.
- Spec, plan, implementation, and corrections use local commits on one task
  branch. The branch is pushed and one PR to `develop` is opened when the first
  implementation head is reviewable. Corrections update that same PR.
- Handoff records a clean committed HEAD and posts evidence naming the exact next
  agent ID. Its final line is `GLITCHERRY_HANDOFF_TARGET_V2` followed by exactly
  one canonical `agent://<next-agent-uuid>` link; no other agent link appears in
  that comment. It then reassigns the same issue without `interrupt` as the old
  run's final action. Agent credentials cannot use Paperclip's Board-only interrupt.
  The old role stops immediately; no role polls `executionRunId`, performs a
  release/reassign loop, or asks Board to clear ownership. If reassignment is
  stranded, the Board-authenticated watchdog sends one update containing its own
  recovery `comment`, exact assignment, and `interrupt: true` on the first eligible
  scan. No two phase owners operate in the task worktree at the same time.

## Standing autonomous correction policy

<!-- GLITCHERRY_STANDING_AUTONOMY_V1 -->

The Human Engineering Lead grants a permanent, project-wide delegation for
bounded corrections inside an approved slice. This is not tied to GLA-41, TP1,
or one plan revision. Correcting actual buggy behavior so it conforms to the
already approved behavior does not change the approved product contract.

The primary implementer fixes product code, tests, fixtures, harnesses,
diagnostics, verification tooling, synchronization, parsing, evidence capture,
and local build wiring autonomously when the approved behavior/acceptance,
threshold and pass/fail meaning, roadmap/scope/order, production dependencies,
toolchain/API floor, accepted ADRs, explicitly named architecture boundaries,
security policy, and single-writer ownership remain unchanged. Reversible
internal implementation choices inside those boundaries belong to CTO plus the
primary implementer and independent Code Reviewer; the word "architecture" by
itself never creates a human gate.

Use these exact routes:

- A finding made by the implementer before review stays in `implementation` or
  `implementation_fix`; correct it, commit, run focused checks, and hand the new
  clean HEAD to `GlitcherryCodeReviewer / code_review`.
- A Code Reviewer finding uses controller `reject` to the recorded primary
  implementer. The controller enters `implementation_fix`; the corrected new
  HEAD returns to `code_review` on the same PR.
- Initially ambiguous evidence is committed if legitimate slice work is dirty,
  then handed to `GlitcherryCTO / technical_triage`. CTO classifies it against
  the pinned contract and hands the unchanged clean HEAD to the recorded primary
  implementer in `implementation`. It does not revise the plan merely to narrate
  the correction.
- A clean correction-only incident already in controller `blocked` resumes by
  supported `resume-blocked` to `GlitcherryCTO / plan_revision`, using the
  accepted standing-policy merge SHA as decision evidence. CTO validates it, makes
  no synthetic plan edit, and hands the unchanged HEAD to the recorded primary
  implementer in `implementation`.
- A dirty correction-only incident already in `blocked` resumes to the recorded
  primary implementer in `implementation_recovery`. That implementer preserves
  legitimate files in one commit and hands them to CTO in `plan_revision`; CTO
  makes no synthetic plan edit and routes the clean HEAD back to that implementer
  in `implementation`.
- A correction discovered after Code Review approval invalidates that approval.
  CTO returns the clean HEAD to the primary implementer in `implementation`; the
  new correction HEAD must pass `code_review` again before integration.

Local implementer attempts before the first Code Review do not consume a review
cycle. Every controller `reject` from `code_review` consumes exactly one of the
three cycles, for product or support code alike. CTO routing never resets or
bypasses this counter.

A harness, fixture, emulator-startup, adb-transport, or evidence-capture attempt
that fails before valid application evidence does not consume a product
verification attempt. Each new clean correction HEAD gets the one focused rerun
needed to verify its correction and affected acceptance criterion. Do not retry
an unchanged failing HEAD, run a full matrix/per-slice QA, add a second emulator,
or weaken a threshold or pass/fail meaning.

Board interaction is reserved for changing approved product behavior or
acceptance, a threshold/pass-fail meaning, roadmap/slice scope/order/READY state,
production dependency, toolchain/API floor, a cited accepted ADR or explicitly
named architecture boundary, credentials, signing/publication, destructive
external authority, or a sprint/stage gate. A real conflict between current
authoritative contracts also returns one structured question. For that human
decision only: preserve legitimate dirty work in one implementer WIP commit,
hand the clean HEAD to `GlitcherryCTO / plan_revision`, create one interaction,
and wait on the same issue/worktree. After the answer, CTO applies any required
plan change and routes the exact plan revision through independent review.

Use controller `block` only when there is genuinely no safe next transition.
When a previously blocked decision is later resolved, never edit controller JSON
or the Paperclip database and never create a replacement child or worktree. CTO
uses `resume-blocked` with the decision evidence. A clean worktree resumes
directly to the HEL-authorized next role/phase on its current linear commit; a
stale controller HEAD is adopted and audited. A dirty worktree resumes only to
its recorded primary implementer in `implementation_recovery`. That implementer
preserves the files in one local WIP commit and hands the resulting clean HEAD
onward.

Legacy `recover` and `adopt-recovery-checkpoint` commands remain readable only
for historical state created before this contract, but no longer require an
active lease. New runs never create a lease or enter lease-recovery choreography.
A clean committed worktree ahead of stale controller metadata is adopted by the
next assigned role's normal claim/resume command.

## Six child phases

### Phase 1 — Adopt Paperclip worktree and materialize spec

Owner: `GlitcherryCTO`.

Paperclip creates the exact `feature/GLA-N-<slug>` isolated worktree from the
pinned `origin/develop` base before the adapter starts. Read the live child and
execution workspace, then use controller `adopt` once with the exact shared
Project workspace ID, execution workspace ID, cwd, branch, base SHA, issue, and
run. Do not create a second worktree. Materialize only the approved technical
spec, cite the pinned roadmap slice, and commit locally. The spec may narrow
execution detail but cannot expand product scope. Record the clean HEAD, hand
controller ownership to `GlitcherryCodeReviewer` for `spec_review`, perform the atomic
Paperclip handoff, and stop.

### Phase 2 — Independent spec review

Owner: `GlitcherryCodeReviewer`.

Validate the same worktree and recorded spec HEAD. Review feasibility,
hidden product choices, Android/media ownership, failure paths, and testability.
Never edit or commit. Approval hands the same clean HEAD to the CTO. Findings
return to the CTO with one consolidated list. At most two spec/plan revision
rounds are allowed; unresolved product or architecture ambiguity blocks for the
Human Engineering Lead.

### Phase 3 — Plan and independent plan review

Owners in sequence: `GlitcherryCTO`, then `GlitcherryCodeReviewer`.

The tracked `docs/plans/...` file at the controller-recorded task HEAD is the
slice implementation authority. The Paperclip `plan` document is a
byte-identical mirror of those exact bytes, never a separately authored source
of requirements.

The CTO validates the same worktree, adds a plan mapping every acceptance criterion
to ownership, implementation, tests, and verification, then commits locally.
Before every `plan_review` handoff the CTO must prove the worktree clean, record
the exact Android HEAD, hash the tracked plan bytes, and create or update the
Paperclip mirror using the current `baseRevisionId`. It must read back the exact
created revision and prove the mirrored-body SHA-256 equals the tracked-plan
SHA-256. The handoff evidence records Android HEAD, tracked-plan SHA-256,
mirrored-body SHA-256, and the Paperclip revision ID and revision number. An API
conflict, stale `baseRevisionId`, missing read-back, hash mismatch, or second
writer stops the handoff; it never creates a replacement plan or issue.

Exact-revision Human Engineering Lead confirmation is mandatory when a revision
introduces or changes product behavior, roadmap or slice scope/order, a
production dependency, toolchain, or API floor, a quality threshold or
pass/fail meaning, a cited accepted ADR or explicitly named architecture
boundary, or another choice reserved to the Human Engineering Lead. The standing
autonomous correction policy is sufficient authority when every listed decision
dimension is unchanged, the mirror is byte-identical, and the independent
reviewer approves the exact changed HEAD; no issue-specific delegation or
duplicate confirmation is required.

Acceptance criteria, explicit contract invariants, security constraints,
accepted ADRs, named architecture boundaries, and a file allowlist explicitly
marked `strict` are mandatory. Implementation sketches, helper names, ordinary
file estimates, assertion mechanics, fixture seeding, synchronization, parsing,
and other incidental mechanics are guidance unless the approved acceptance
contract makes them observable. Crossing into a new module or named layer needs
CTO disposition and independent review, not Board confirmation, when the
reserved decision dimensions stay unchanged. An assertion proving an explicit
acceptance criterion/numeric threshold, or the only remaining evidence for an
acceptance criterion, cannot be removed or weakened; an unstated internal-detail
assertion may be repaired or replaced only with equally strong or stronger
stable evidence of the approved behavior.

The reviewer stays read-only. It first verifies the exact HEAD/hash/revision
tuple and returns an absent, stale, or divergent mirror as one consolidated
process finding to CTO before technical review. Once synchronized, it either
approves the exact plan HEAD for one named implementer or returns one
consolidated technical finding list. It must not add a duplicate human gate when
the standing autonomous correction classifier above is fully satisfied.

### Phase 4 — Implementation by exactly one engineer

Owner: either `GlitcherryAndroidEngineer` or
`GlitcherryMediaPipelineEngineer`, never both as writers.

The assigned implementer validates the same approved worktree/HEAD, reads its
tracked `AGENTS.md`, makes changes traceable to the approved acceptance contract
and the plan hierarchy above, and creates focused local commits. It applies the
standing autonomous correction policy during implementation and bounded checks;
an envelope-safe finding is fixed on the same branch without CTO or Board.
When the first implementation head is reviewable, it pushes the task branch,
opens one PR whose base is exactly `develop`, records the PR/head, hands the clean
exact HEAD to `GlitcherryCodeReviewer` for `code_review`, and stops.

### Phase 5 — Exact-head code and architecture review

Owner: `GlitcherryCodeReviewer`.

Validate and review the controller-recorded PR HEAD in the same worktree. Apply both
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
and are not disguised as code defects. Product-code and support-code findings
inside the standing envelope both return directly through `reject`; they do not
trigger a plan revision or Board interaction. Reviewer never fixes them.

Approval records `reviewed_head` and hands controller ownership directly to
`GlitcherryCTO`. QA does not run inside a normal slice.

### Phase 6 — Integrate, synchronize, and clean

Owner: `GlitcherryCTO`.

Validate the exact approved state. Verify the PR base is `develop`, its live head
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

Only after both merge SHAs are recorded and reachable may controller
`prepare-cleanup` retain the approved feature HEAD and move the clean local task
branch to the verified Android merge SHA. CTO then closes the exact Paperclip
execution workspace through its supported archive/finalize API; Paperclip owns
worktree removal and normal local branch deletion. The parent may wake early but
does cleanup only: after successful `workspace_finalize`, controller `cleanup`
verifies the exact worktree is absent and removes only remaining recorded remote
task/status refs.

The CTO marks the child `done` after `prepare-cleanup` and requests the supported
workspace finalization: read `GET /api/execution-workspaces/{id}/close-readiness`,
then `PATCH /api/execution-workspaces/{id}` with `{"status":"archived"}` only
when readiness is not blocked, and verify the latest workspace operation is a
successful `workspace_finalize`. The next slice is forbidden until controller state is
`cleaned`, both canonical clones are current clean `develop`, the exact refs are
absent, and all evidence is retained. If Android merged but control or cleanup
failed, resume from the recorded SHA; never reimplement or remerge Android.

## Sprint smoke gate — QA only here

QA is activated once per sprint, only after every sprint slice is merged and
cleaned, the root is stopped at `SPRINT_SMOKE_REQUIRED`, and the candidate SHA is
fixed. `GlitcherryQAEngineer` verifies that exact Android `develop` candidate in
a separate read-only test checkout or detached state; it never becomes an active
slice worktree writer.

Run the deliberately small sprint smoke suite: launch/import, preview/navigation,
save/share, and any sprint-specific critical media path on the declared AVD and,
when required, the Samsung A55 Android 16 reference device. Use one emulator at a
time. Post commands, result, artifacts, device/API identity, and candidate SHA.

- PASS returns the root to the Human Engineering Lead for sprint acceptance.
- A reproducible product defect blocks the root with the failing evidence and
  named owner; the Walker does not invent or start a corrective slice.
- Infrastructure residue uses `LOCAL_BLOCKED` and one bounded exact-run recovery.
- If an AVD/device check fails before APK installation or before its test body
  starts, the attempt produced no application evidence and does not consume the
  allowed test run. After bounded emulator/adb cleanup, retry it once
  automatically. Repeated infrastructure failure or any started test failure
  blocks; neither permits a fallback or relaxed acceptance.
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
  `NOT_READY`, `ROADMAP_BLOCKED`, and no next child; broad `pkill` remains
  forbidden.

The owner-approved unlimited mode is `budgetMonthlyCents=0`; record per-run cost
evidence and escalate anomalous growth. For every diagnostic transition, the
current child must be terminal and cleanup evidence is complete before the next
child. No next child is permitted on ambiguity or residue.

## Atomic handoff

Every transition uses this exact order:

1. finish the required local commit and/or allowed push and verify a clean HEAD;
2. record the controller handoff to the exact next owner/phase;
3. `POST evidence` to `/api/issues/{id}/comments`, explicitly name the exact next
   agent ID, end with `GLITCHERRY_HANDOFF_TARGET_V2` plus exactly one canonical
   `agent://<next-agent-uuid>` link, and require 2xx;
4. `PATCH assignee/status` to the exact next owner and API state without
   `interrupt`; do not change `projectWorkspaceId` or `executionWorkspaceId`;
5. `STOP` immediately. The reassignment PATCH is the old run's final action; do
   not poll `executionRunId` or perform a post-PATCH read from that process.

A mention is not a handoff. A failed PATCH may be repeated once with the same
target. The watchdog completes a deterministic stranded handoff on its first
eligible scan; it does not wait for Board. Never write the Paperclip database
directly.

## Stop conditions

- `LOCAL_BLOCKED` and `ROADMAP_BLOCKED` are reason codes; API status is
  `blocked`. Neither permits the next child.
- A dirty review boundary, wrong
  branch, residual exact ref, partial merge, or incomplete cleanup stops work.
- Missing/mismatched Project or execution workspace identity stops work. A
  role-specific workspace mismatch is not a condition because all roles share
  one Project workspace.
- Missing authority that actually requires changing the approved product,
  acceptance, roadmap, production dependency/toolchain/API floor, cited ADR,
  named architecture boundary, credential, or release decision blocks rather
  than being guessed. Internal implementation uncertainty is CTO technical
  triage, not a Board stop.
- Unavailability of Serena, codebase-memory, Context7, or another advisory MCP is
  not a blocker. Record it and continue with the remaining indexed tool plus
  targeted `rg`, local reads, compiler/test output, and official Android docs;
  stop only when the active acceptance contract explicitly requires that exact
  tool and no equivalent evidence path exists.
- Agents never release, sign, tag, publish, merge to `main`, or use operator
  secrets.
