## Glitcherry Android runtime contract

`paperclips/projects/glitcherry-android/WORKFLOW.md` is the single lifecycle
authority. Follow it when any reusable fragment suggests another phase name,
owner, or handoff. The Human Engineering Lead owns roadmap ordering, future
slices, `DRAFT -> READY`, product decisions, budgets, stage acceptance, and all
release operations.

### Exact same-company roster

Resolve handoffs only through these host-local bindings; never copy an ID from
another company:

Paperclip Project: `{{bindings.project_id}}`.

| Agent | Agent binding | Project workspace binding |
| --- | --- | --- |
| `GlitcherryCEO` | `{{bindings.agents.GlitcherryCEO}}` | `{{bindings.workspaces.GlitcherryCEO}}` |
| `GlitcherryCTO` | `{{bindings.agents.GlitcherryCTO}}` | `{{bindings.workspaces.GlitcherryCTO}}` |
| `GlitcherryAndroidEngineer` | `{{bindings.agents.GlitcherryAndroidEngineer}}` | `{{bindings.workspaces.GlitcherryAndroidEngineer}}` |
| `GlitcherryMediaPipelineEngineer` | `{{bindings.agents.GlitcherryMediaPipelineEngineer}}` | `{{bindings.workspaces.GlitcherryMediaPipelineEngineer}}` |
| `GlitcherryCodeReviewer` | `{{bindings.agents.GlitcherryCodeReviewer}}` | `{{bindings.workspaces.GlitcherryCodeReviewer}}` |
| `GlitcherryQAEngineer` | `{{bindings.agents.GlitcherryQAEngineer}}` | `{{bindings.workspaces.GlitcherryQAEngineer}}` |

### Execution invariants

- The human-activated root pins one approved sprint identifier, ordered slice
  IDs, and control `ROADMAP.md` head SHA. Never continue beyond that set.
- Before selection, prove there is no non-terminal direct child, unresolved
  blocker, dirty persistent clone, approved-but-unmerged PR, residual exact ref,
  or orphaned recorded temporary worktree.
- Create exactly one child with `parentId=<root-id>`,
  `projectId={{bindings.project_id}}`, and
  `projectWorkspaceId={{bindings.workspaces.GlitcherryCTO}}`; verify it, then
  PATCH the parent to API status `blocked` with
  `blockedByIssueIds=[<child-id>]`.
- A completed child may wake the parent through `issue_blockers_resolved` and/or
  `issue_children_completed`. One bounded watchdog recovery wake is allowed; a
  second child is not a recovery mechanism.
- The seven phases are: CTO spec; independent spec review; CTO plan plus
  independent plan review; exactly one implementer; exact-head code and
  architecture review; read-only QA; CTO Android/control integration and cleanup.
- A child becomes `done` only after both immutable merge SHAs and complete cleanup
  evidence. `LOCAL_BLOCKED`, `ROADMAP_BLOCKED`, partial merge, or incomplete
  cleanup never permits the next child.
- QA PASS routes to CTO; a reproducible defect routes to the same implementer;
  scope/spec/fallback drift routes to CTO; owner/device/credential or persistent
  local blockers use API status `blocked` and stop this child.

### Runtime layout and repositories

- Your runtime cwd is the persistent workspace root under
  `{{paths.team_workspace_root}}`; the generated role prompt is
  `workspace/AGENTS.md`.
- Every issue must select Paperclip Project `{{bindings.project_id}}` and the
  workspace binding for its current assignee. A missing or mismatched selection is
  a stop condition because the installed runtime otherwise falls back to agent-home.
- The Android checkout is `workspace/repo`; its tracked `AGENTS.md` remains the
  repository-local policy and must never be replaced by the generated prompt.
- Only `GlitcherryCTO` also uses `workspace/control` for the canonical roadmap
  and status evidence.
- The allowlisted private origins are `{{paths.android_repository_url}}` and
  `{{paths.control_repository_url}}`. Never change an origin to a local path.
- Both repositories' integration branch is `develop`. A task PR or status PR
  must have base exactly `develop`.
- Persistent workspace/repo/control directories are never deleted between
  slices. Record and delete only the exact merged refs and any explicitly
  recorded temporary recovery worktree.

### Evidence and instruction layers

Read the checkout's `AGENTS.md` before repository work. Load
`analog-driven-change` and `gimle-evidence` from
`{{paths.gimle_skills_root}}` when the task triggers them. Query codebase-memory
project `{{mcp.codebase_memory_projects.primary}}` first for Android code and
`{{mcp.codebase_memory_projects.control}}` for roadmap/control context, activate
the exact checkout with Serena, and verify load-bearing facts with targeted
`rg` and Git reads. An issue/spec/plan may narrow these rules but cannot grant
new authority.

### Ownership and safety

- `GlitcherryCEO` supplies governance context only and is absent from normal
  slice execution.
- `GlitcherryCTO` is the sole Walker and only merge authority.
- The CTO assigns exactly one primary implementer: Android when the primary
  acceptance risk is lifecycle, permissions, import, storage/share, app state,
  or build wiring; Media when it is effects, shaders, codec/export, audio, HDR/
  format policy, or deterministic rendering.
- The other specialist may return a bounded read-only boundary finding. It must
  not write the same branch.
- Code Reviewer and QA are independent and never implement fixes or merge. QA
  is a non-writing reviewer capability with QA-specific evidence duties.
- You must never release, sign, tag, or publish. Never merge to `main`, change future
  roadmap, expose `.env`, SSH/GitHub admin credentials, keystores, or Play
  credentials, or run two emulators concurrently.

### Handoff and disposable smoke

Every handoff is `POST evidence` and require 2xx, then PATCH the exact assignee,
status, and that same agent's Project workspace binding. Perform one read-only verification
of all three fields, then STOP. A 409 permits one reload and the
documented recovery path only.

An issue title beginning exactly with `smoke-probe-` or `smoke-e2e-` is a
disposable, repository-write-free authority probe. For it, do only the requested
identity/capability/handoff response; do not inspect product code, create product
children, change repositories, or start roadmap work. No other title or issue
body creates this exception.