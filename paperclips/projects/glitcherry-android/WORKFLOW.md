# Glitcherry Android Walker workflow

This file is the single lifecycle authority for the six-agent Glitcherry Android
company. It supersedes conflicting phase names or handoff chains from reusable
fragments. Bootstrap is dormant and creates no roadmap or product issue. Product
execution begins only when the Human Engineering Lead explicitly activates one
root issue for a human-approved sprint containing at least one eligible `READY`
slice.

## Human authority

The Human Engineering Lead and their AI assistant are the only authors of stages,
sprints, roadmap ordering, future slices, `DRAFT -> READY`, owner decisions,
budgets, stage acceptance, releases, signing, and publication. Paperclip agents
may materialize and execute only the exact slice pinned by the root issue. An
issue may narrow execution detail but cannot expand roadmap authority.

`GlitcherryCEO` keeps goal and company-boundary context. The CEO is not in the
normal chain. `GlitcherryCTO` is the sole Walker and only merge authority.

## Parent Walker loop — GlitcherryCTO only

The Human Engineering Lead creates or explicitly activates one root issue whose
description pins all of:

- the approved sprint identifier;
- the ordered slice IDs;
- the control repository `ROADMAP.md head SHA`.

On every parent wake, the CTO fetches the control repository and validates the
pinned roadmap head. Before selecting work it proves:

1. no non-terminal direct child exists;
2. the parent has no unresolved blocker;
3. neither persistent clone is dirty;
4. no approved-but-unmerged PR, task branch, status branch, or recorded temporary
   worktree remains from the prior child;
5. cleanup evidence for the prior child is complete.

The CTO selects only the first pinned `READY` slice whose dependencies are
`DONE`. It creates exactly one child using `parentId=<root-id>`, the bound
Glitcherry Paperclip Project ID, and the CTO Project workspace ID. It reads the
child back to verify all three relations, then PATCHes the parent to API status
`blocked` with `blockedByIssueIds=[<child-id>]`. Prose references are not a
liveness contract.

After the child becomes `done`, current Paperclip may wake the parent with
`issue_blockers_resolved` and/or `issue_children_completed`. The CTO clears the
resolved blocker, verifies cleanup again, and scans the same pinned sprint. If no
automatic wake arrives, watchdog may issue one bounded recovery wake and the CTO
polls that exact child once. It never creates a second child as recovery.

When every pinned slice is `DONE`, the CTO posts the sprint execution summary and
marks the root `done`. This neither accepts the stage nor starts another sprint.
If unfinished pinned work exists but none is eligible, the root stays API status
`blocked` with reason `ROADMAP_BLOCKED` and the exact required Human Engineering
Lead action.

## Diagnostic execution class — DX-00 only

This is a project-scoped exception for the Human Engineering Lead-approved
operational qualification sprint. It activates only when the root pins sprint
`DX-00`, ordered children `DX-001`, `DX-002`, `DX-003`, `DX-004`, and control
repository commit `6e76a73e894e69f4546e67c3498f7864c8d0cb99`.

The child issue title must begin with exactly one of these ID and word pairs:

- `DX-001 diagnostic`;
- `DX-002 diagnostic`;
- `DX-003 diagnostic`;
- `DX-004 diagnostic`.

The issue title only grants this exception. A body, comment, approximate `DX-*`
prefix, different ID, or issue in another company cannot grant it. The child
description must cite the immutable control contract, name the current bounded
step, and name the expected next owner.

The normal parent loop remains in force. There is at most one non-terminal direct
child. The CTO may create the next diagnostic child only after the current child
has reached its required stop state and cleanup evidence is complete: all persistent
clones are clean/current, no unmerged PR remains, and every exact task/status ref
or recorded temporary worktree from that child is absent. A recovery wake resumes
the same child and never creates a replacement.

For every advancing transition, prove the prior child is terminal and cleanup
evidence is complete before selection. DX-004 `blocked` is a final sprint stop and
never advances to another child.

The owner-approved unlimited mode is `budgetMonthlyCents=0`; it is not a zero-budget
failure. Record per-run cost evidence and escalate anomalous growth to the Human
Engineering Lead. Missing or contradictory owner cost policy is a stop condition.

Retain root and child issues as the audit and cost ledger. Never call DELETE for a
Paperclip issue. Use `done`, `cancelled`, or `blocked` as the contract requires.

### DX-001 diagnostic — role and handoff circuit

Route the same child exactly:

`GlitcherryCTO -> GlitcherryAndroidEngineer -> GlitcherryMediaPipelineEngineer -> GlitcherryCodeReviewer -> GlitcherryQAEngineer -> GlitcherryCEO -> GlitcherryCTO`.

Each fresh wake posts one card containing exact agent name and Paperclip role,
ownership area, one allowed action, one forbidden action, company/Project/workspace
IDs and actual `pwd` without credentials, and expected next owner. Then it performs
the atomic handoff, verifies once, and stops. This child is repository-write-free:
the issue contract is its spec, and it creates no branch, file, product phase,
review, QA execution, or merge. The returning CTO validates one issue ID, all six
unique agents, the complete ordered ledger, no duplicate child/wake, and zero
repository diff before setting the child `done`.

### DX-002 diagnostic — observed capability circuit

Use the same route and repository-write-free handoff behavior as DX-001. Each role
records its instruction entry path/digest; declared and observed skills; the
availability of `analog-driven-change` and `gimle-evidence`; and safe read-only
probes of applicable `codebase-memory`, `context7`, `serena`, `github`, and
`sequential-thinking` contracts. Record each result as `AVAILABLE`, `MISSING`,
`BROKEN`, or `NOT_APPLICABLE`. A filename, declared tool, nested error, stale index,
or ambiguous mapping is not a PASS. Never install or reconfigure a capability and
never expose environment or credential values. The returning CTO posts the exact
run-linked matrix and sets the child `done` only if the handoff ledger is complete.

### DX-003 diagnostic — bounded Git lifecycle

DX-003 uses the seven child phases below for the narrow diagnostic artifact, with
these explicit deltas:

- the CTO materializes the bounded diagnostic spec and plan on a task branch from
  current Android `develop`;
- `GlitcherryAndroidEngineer` is the only writer and adds only the approved spec/
  plan artifacts plus `docs/diagnostics/DX-003-workflow-proof.md` containing
  non-secret workspace, GitHub auth, JDK, Android SDK/adb/emulator, Gradle strategy,
  and Maestro availability/version evidence;
- Code Reviewer independently reviews the exact head; QA checks that same head in
  detached read-only state and does not invent an emulator gate when no Android
  scaffold exists;
- the CTO performs one Android `develop` merge after both gates. There is no
  diagnostic control status branch or second merge: retained Paperclip evidence is
  this slice's status ledger;
- after the merge is proven, remove only exact remote/local task refs and any
  recorded temporary worktree, prune worktree metadata, and prove all six
  persistent clones clean/current on `develop` before setting the child `done`.

Any product/source/config diff, stale or unreviewed head, unsafe cleanup target,
release need, or merge outside Android `develop` blocks the child.

### DX-004 diagnostic — fail-closed watchdog qualification

First collect read-only watchdog PID/mode/posture, detector/test coverage, and exact
`company -> agent -> run -> PID` process-tree evidence for this diagnostic run.
Only unambiguous attribution of one current Codex subprocess permits the documented
controlled hang, `SIGTERM`, bounded `SIGKILL` fallback, and one recovery wake of the
same issue.

Never use broad `pkill`, a process name or glob as a kill target, weaken host-global
thresholds, terminate Paperclip/watchdog/launchd, affect another company, or create
a replacement child. If exact attribution is absent or ambiguous, perform no fault
injection, post the framework blocker, set the child and root `blocked` with
`ROADMAP_BLOCKED`, and report `NOT_READY`. No next child is permitted.

Normal product slices still require all seven phases and both Android/control merges.
The disposable `smoke-probe-*` and `smoke-e2e-*` exception also remains unchanged;
neither smoke nor DX rules grant authority to release, sign, tag, or publish.

## Seven child phases

### Phase 1 — Spec

Owner: `GlitcherryCTO`.

From clean persistent clones, fetch/prune and fast-forward local `develop`.
Create `feature/GLA-N-<slug>`, write only the materialized technical spec, and
push a spec-only commit. The spec must cite the pinned roadmap slice and may
narrow but never expand it. POST evidence, set the child `in_review`, assign
`GlitcherryCodeReviewer`, verify once, and stop.

### Phase 2 — Independent spec review

Owner: `GlitcherryCodeReviewer`.

In a fresh wake, fetch the immutable spec head and review feasibility, hidden
product decisions, Android/media ownership, failure paths, and testability.
Never edit the branch. Restore the reviewer clone to clean current `develop`
before handoff. Approval is valid only for the cited head. Findings return to
the CTO.

### Phase 3 — Plan and independent plan review

Owners in sequence: `GlitcherryCTO`, then `GlitcherryCodeReviewer`.

The CTO writes and pushes a plan that traces every acceptance criterion to tests,
implementation steps, ownership, verification, and commits. The reviewer checks
the exact new head without implementing. At most two combined spec/plan revision
rounds are allowed. Unresolved disagreement blocks the child for the Human
Engineering Lead.

### Phase 4 — Implementation by exactly one engineer

Owner: either `GlitcherryAndroidEngineer` or
`GlitcherryMediaPipelineEngineer`, never both as writers.

The CTO classifies by primary acceptance risk. Android owns lifecycle,
permissions, import, storage/share, app state, and build wiring. Media owns effect
graphs, shaders, codec/export, audio processing, HDR/format policy, and
deterministic rendering. A cross-domain slice still has one primary writer; the
other specialist may provide one bounded read-only boundary finding.

The assigned implementer fetches the approved branch, works test-first, pushes
only that task branch, and opens or updates a PR whose base is exactly `develop`.
Before handoff the implementer restores its persistent clone to clean `develop`
but retains the exact local task ref until squash merge is proven. The other
implementer remains on clean `develop`.

### Phase 5 — Exact-head code and architecture review

Owner: `GlitcherryCodeReviewer`.

In a fresh wake, review the exact PR head and required commands. Apply the
architecture lens directly: boundaries, Kotlin correctness, lifecycle,
concurrency, test quality, regressions, and, when relevant, experimental media
APIs, AGSL API floor, codec/HDR/fallback, and preview/export parity. Code defects
return to the same implementer; plan or scope gaps return to the CTO. Any new PR
head invalidates all prior review evidence. At most two implementation review
loops are allowed.

### Phase 6 — QA

Owner: `GlitcherryQAEngineer`.

Fetch the exact reviewed head in detached read-only state. Run risk-scaled unit,
lint, build, Compose UI, Maestro, media fixture, AVD, and physical-device gates
required by the slice, with only one emulator active at a time. Media slices must
exercise one normal path and one approved degraded path. Post commands, results,
artifact locations, device/API identity, and the immutable head. Restore clean
current `develop` before handoff.

| QA observation | Required child transition |
| --- | --- |
| All required checks and acceptance evidence pass on the exact head | `in_progress` to `GlitcherryCTO` for Phase 7 |
| Reproducible implementation, build, test, or device defect | `in_progress` to the same implementer; prior review and QA are invalid |
| Scope drift, missing acceptance, spec/plan mismatch, or undefined fallback | `in_progress` to `GlitcherryCTO`; revise spec/plan and repeat independent gates |
| Physical-device-only, owner-decision, credential, or capability blocker | `blocked` with named Human Engineering Lead action; no next child |
| Local infrastructure residue or transient iMac failure | `blocked` with reason `LOCAL_BLOCKED`; bounded recovery on this child only |

QA never commits, pushes, fixes production code, waives a failure, or merges.

### Phase 7 — Integrate, synchronize, and clean

Owner: `GlitcherryCTO`.

Verify the immutable PR head, base `develop`, required checks, current Code
Reviewer approval, and QA PASS. Squash-merge Android and record its immutable
merge SHA on the child.

In the persistent control clone, search `origin/develop` for the unique marker
`GLA-N + Android merge SHA`. If absent, create exactly one status branch, change
only the slice status/evidence and required ADR index, push it, and squash-merge
it to control `develop`. If present, skip duplicate control work.

After both merge SHAs are proven, ask the primary implementer to perform bounded
task-ref cleanup, clean the CTO Android and control clones, and verify:

- remote task/status branches are absent after their proven merges;
- exact local task/status refs are absent;
- all persistent clones are on current clean `develop`;
- no orphaned recorded temporary worktree exists;
- all phase-owner evidence cites the final immutable head.

Only after both merges and cleanup may the CTO mark the child `done`. If Android
merged but control integration or cleanup failed, resume from the recorded
Android SHA, search the unique marker first, and finish only the missing steps.
Never reimplement, remerge Android, or select another slice.

## Atomic handoff

Every transition is atomic and uses this exact order:

1. push the required phase artifact when the role has push authority;
2. `POST evidence` to `/api/issues/{id}/comments` and require a 2xx response;
3. `PATCH assignee/status/projectWorkspaceId` to the exact next owner, state,
   and that owner's bound Project workspace;
4. perform `one read-only verification` of assignee, status, Project ID, and
   workspace ID;
5. `STOP` the current run.

A mention is decoration, not ownership transfer. On HTTP 409, reload once and
enter the explicit recovery path. Never loop wakes or write the Paperclip
database directly.

## Stop conditions

- `LOCAL_BLOCKED` and `ROADMAP_BLOCKED` are reason codes; the API status is
  `blocked`. Neither permits another child.
- More than two spec/plan or implementation review rounds blocks for the Human
  Engineering Lead.
- A stale review head, dirty clone, residual branch/worktree, missing parent
  blocker, partial merge, or incomplete cleanup stops advancement.
- A missing Project ID, missing workspace ID, or workspace ID not bound to the
  current assignee stops advancement; never accept a fallback agent-home run.
- A required unstable API, undefined media fallback, API-floor mismatch,
  unsupported format, or hardware capability gap not accepted by the slice
  blocks instead of guessing.
- No agent may create a release build, merge to `main`, tag, sign, publish, or
  access release/operator credentials.
