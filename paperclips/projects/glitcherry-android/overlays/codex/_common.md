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

### Runtime repositories and lease

- Your role-specific `AGENTS.md` is supplied independently by the adapter through
  an absolute required `instructionsFilePath`. A missing or unreadable required
  instruction file is a hard pre-spawn error.
- The canonical Android clone is `{{paths.primary_repo_root}}`; the canonical
  control clone is `{{paths.control_repo_root}}`. The historical
  `workspace/control` layout is not used for normal product work.
- One active slice has exactly one worktree below the configured
  `task_worktree_root` (`{{paths.task_worktree_root}}`), one mode-600 record below
  `{{paths.task_state_root}}`, one task branch, one PR, and one exclusive lease.
- Paperclip creates the isolated worktree once. CTO adopts its exact
  `executionWorkspaceId`, path, branch, and HEAD into the controller at
  `{{paths.slice_controller_path}}`; no agent or controller creates an
  alternative checkout. Verify the live assignee and unchanged workspace IDs,
  then claim the lease before repository access.
- All roles use that same committed HEAD sequentially. A dirty tree, mismatched
  branch/HEAD, another owner/run, expired lease, or second state is a stop.
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

### Recovery and safety

Lease expiry never grants takeover. Recovery requires exact
`company -> agent -> run -> PID` attribution, proof that the prior run stopped or
was terminated, retained dirty/unmerged state, and a recorded recovery of the
same slice. Never use broad `pkill`, delete an unrecorded path, or start a second
child.

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
and require 2xx, PATCH only the exact assignee/status, perform one read-only verification
that both workspace IDs plus controller state are unchanged, then
STOP. One 409 reload is allowed; repeated conflict is
`LOCAL_BLOCKED`.
