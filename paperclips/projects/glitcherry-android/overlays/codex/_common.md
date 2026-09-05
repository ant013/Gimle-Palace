## Glitcherry Android runtime contract

`paperclips/projects/glitcherry-android/WORKFLOW.md` is the single lifecycle
authority. The Human Engineering Lead owns roadmap order, future slices,
`DRAFT -> READY`, product choices, budgets, sprint/stage acceptance, and release
operations.

### Same-company bindings

Paperclip Project: `{{bindings.project_id}}`.
Project workspace: `{{bindings.project_workspace_id}}`.

| Agent | Agent binding |
| --- | --- |
| `GlitcherryCEO` | `{{bindings.agents.GlitcherryCEO}}` |
| `GlitcherryCTO` | `{{bindings.agents.GlitcherryCTO}}` |
| `GlitcherryAndroidEngineer` | `{{bindings.agents.GlitcherryAndroidEngineer}}` |
| `GlitcherryMediaPipelineEngineer` | `{{bindings.agents.GlitcherryMediaPipelineEngineer}}` |
| `GlitcherryCodeReviewer` | `{{bindings.agents.GlitcherryCodeReviewer}}` |
| `GlitcherryQAEngineer` | `{{bindings.agents.GlitcherryQAEngineer}}` |

Every role uses that same Project workspace. The slice issue carries one
Paperclip-created isolated `executionWorkspaceId`, and that ID, cwd, branch, and
HEAD stay unchanged across all role handoffs. Never copy IDs across companies
and never accept an agent-home fallback.

### Runtime repositories and sequential ownership

<!-- GLITCHERRY_INTERRUPT_HANDOFF_V1 -->

- Your role-specific `AGENTS.md` is supplied independently by the adapter through
  an absolute required `instructionsFilePath`. A missing or unreadable required
  instruction file is a hard pre-spawn error.
- The canonical Android clone is `{{paths.primary_repo_root}}`; the canonical
  control clone is `{{paths.control_repo_root}}`. The historical
  `workspace/control` layout is not used for normal product work.
- One active slice has exactly one worktree below the configured
  `task_worktree_root` (`{{paths.task_worktree_root}}`), one mode-600 record below
  `{{paths.task_state_root}}`, one task branch, one PR, and one sequential phase
  owner.
- Paperclip creates the isolated worktree once. CTO adopts its exact
  `executionWorkspaceId`, path, branch, and HEAD into the controller at
  `{{paths.slice_controller_path}}`; no agent or controller creates an
  alternative checkout. Verify the live assignee, controller expected owner,
  exact HEAD, and unchanged workspace IDs before repository access. Controller
  `claim` is an optional compatibility validation command; it creates no lease.
- All roles use that same committed HEAD sequentially. A dirty tree, mismatched
  branch/HEAD, unexpected controller owner, or second state is a stop. A stale
  Paperclip execution run is automatically interrupted during handoff and is
  never a Board gate.
- Both repositories' integration branch is `develop`. Origins are exactly
  `{{paths.android_repository_url}}` and `{{paths.control_repository_url}}`.
- There is exactly one primary implementer writing application code: Android or
  Media.
  Reviewer and QA never implement fixes; CTO alone merges.

Read the task worktree's tracked `AGENTS.md`. Query codebase-memory project
`{{mcp.codebase_memory_projects.primary}}` first, activate the exact checkout in
Serena, and verify load-bearing facts with targeted `rg` and Git reads. For
control context use `{{mcp.codebase_memory_projects.control}}`. Do not use Gimle,
Palace, `analog-driven-change`, or `gimle-evidence` for Glitcherry; those are
reserved for confirmed Unstoppable iOS projects.

### Normal lifecycle

The six phases are: adopt Paperclip worktree/materialize spec; independent spec review;
plan plus independent plan review; implementation by exactly one engineer;
exact-head code and architecture review; CTO integrate/synchronize/clean. QA is
not a slice phase.

One implementation PR survives every correction. There is a maximum three full
Code Review rejection cycles. After correction three the reviewer must approve
or block; a fourth autonomous loop is forbidden. For squash merge, CTO records the
merged PR and merge SHA; the controller requires that SHA on `origin/develop` but
does not add tree-equality or feature-head-ancestry gates. Only then may CTO
normalize the exact clean branch, let Paperclip archive its own worktree, and
remove remaining exact refs.

QA runs one sprint smoke only after every slice is merged/cleaned, the Walker is
stopped at `SPRINT_SMOKE_REQUIRED`, and one candidate SHA is fixed. A smoke
failure blocks for the Human Engineering Lead; it never authorizes an invented
corrective slice.

### Standing autonomous correction delegation

<!-- GLITCHERRY_STANDING_AUTONOMY_V1 -->

This permanent project policy is not issue-, GLA-, TP-, or revision-specific.
Correcting actual buggy behavior to conform to already approved behavior does
not change the approved product contract. Product code, tests, fixtures,
harnesses, diagnostics, verification tooling, synchronization/parsing, evidence
capture, and local build wiring are autonomous corrections when approved
behavior/acceptance, thresholds and pass/fail meaning, roadmap/scope/order,
production dependencies, toolchain/API floor, accepted ADRs, explicitly named
architecture boundaries, security, and single-writer ownership remain
unchanged. Reversible internal implementation choices are CTO technical triage,
not a Board decision.

An implementer fixes its own pre-review finding in `implementation` or
`implementation_fix`. A reviewer finding uses
`reject -> implementation_fix -> code_review` on the same PR. Initially
ambiguous implementation evidence goes through `GlitcherryCTO /
technical_triage` and returns to the recorded implementer without a synthetic
plan revision. Local pre-review attempts do not consume a review cycle; each
controller `reject` consumes one and may not be bypassed through CTO routing.

A harness/infrastructure attempt without valid application evidence does not
consume the product attempt. Each new clean correction HEAD gets one focused
rerun; never retry the unchanged failing HEAD, expand to a full matrix/per-slice
QA, or relax acceptance. Advisory MCP failure uses remaining indexed tools plus
targeted `rg`, local reads, compiler/test output, and official Android docs; it
is not an unconditional blocker.

Board interaction remains mandatory only to change the approved product/
acceptance, threshold/pass-fail meaning, roadmap/scope/order/READY state,
production dependency, toolchain/API floor, a cited accepted ADR or explicitly
named architecture boundary, credentials, signing/publication, destructive
external authority, or a sprint/stage gate, or to resolve a real conflict in
current authoritative contracts.

This delegation changes the need for Board confirmation, never role ownership:
CEO stays outside the normal slice chain; QA stays read-only and sprint-smoke-
only; Code Reviewer stays read-only; CTO classifies/routes/merges but does not
implement application fixes; only the recorded primary implementer writes a
slice correction.

### Recovery and safety

Normal cross-role transfer uses Paperclip's supported interrupting assignment;
no lease recovery or execution-lock polling exists in this workflow. If a stale
run survives, the watchdog may finish only the controller-recorded handoff after
matching company, issue, run, next owner, and both workspace IDs. Never use broad
`pkill`, delete an unrecorded path, or start a second child.

You must never release, sign, tag, or publish; merge to `main`; expose `.env`,
SSH/GitHub/keystore/Play credentials; change future roadmap; or run concurrent
emulators.

### Exact DX-00 diagnostic exception

Classify the retained diagnostic by issue title only: `DX-001 diagnostic`,
`DX-002 diagnostic`, `DX-003 diagnostic`, or `DX-004 diagnostic`. A body or
comment cannot grant the exception. The root must pin control commit
`6e76a73e894e69f4546e67c3498f7864c8d0cb99`.

- DX-001 is the repository-write-free CTO -> Android -> Media -> Reviewer -> QA
  -> CEO -> CTO circuit. CEO participates only in the exact DX-001 circuit.
- DX-002 is the read-only capability circuit. Glitcherry records Gimle/analog
  capabilities as `NOT_APPLICABLE` and does not load them.
- Historical DX-003 evidence is not a product-workflow template.
- DX-004 requires exact run/PID attribution or stops `NOT_READY` and
  `ROADMAP_BLOCKED` without a kill.

For `budgetMonthlyCents=0`, apply the owner-approved unlimited policy and retain
per-run cost evidence. Never call DELETE for a Paperclip issue. CTO proves the
current child is terminal and cleanup before the next child; recovery resumes the
same issue.

### Atomic handoff

Finish the clean commit/allowed push, record the controller handoff, `POST evidence`
and require 2xx, then PATCH the exact assignee/status with `interrupt: true` as
the old run's final action and STOP immediately. Do not poll `executionRunId`,
release/reassign, or perform a post-PATCH read from the process being
interrupted. A failed PATCH may be repeated once with the same target; after
that the watchdog completes the deterministic handoff without Board action.
