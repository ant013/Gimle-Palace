# Glitcherry shared execution workspace and role-instruction isolation

Status: Proposed for Human Engineering Lead approval; specification only

Date: 2026-09-03
Baseline: `b38fbd22b5105cc305fc278b3e829270db32c894` (`origin/develop`)
Spec branch: `feature/glitcherry-shared-execution-workspace-spec`

## Goal

Make Paperclip, the Glitcherry slice controller, and every phase owner agree on
one physical Git worktree for one slice while preserving the correct independent
instruction bundle for each agent.

The intended invariant is:

> one active slice -> one Project anchor -> one Execution workspace -> one Git
> branch/worktree -> one controller record -> one exclusive phase owner;
> reassignment changes the owner and injected role instructions, not the code
> directory.

This removes the current false requirement that the issue's Project workspace
must change whenever the role changes. It also makes Paperclip aware of the same
task worktree that the Glitcherry controller already protects.

## Why this change is needed

The existing single-worktree protocol correctly gives all phase owners one
controller-managed task worktree, but the Paperclip handoff still changes
`projectWorkspaceId` to a role-named Project workspace. That field is being used
as an agent-identity check even though a Paperclip Project workspace represents
a durable project/codebase root, not a role.

The live state inspected before authoring this spec showed:

- six role-named Project workspaces for one Glitcherry project;
- each role workspace points to an instruction-root directory rather than the
  slice's Git worktree;
- GLA-17 has no issue-level `executionWorkspaceId`;
- 46 active execution-workspace records had accumulated for GLA-17 across CTO,
  Media Engineer, and Code Reviewer wake-ups;
- the instance setting `enableIsolatedWorkspaces` is disabled, so issue-level
  execution-workspace selection is stripped rather than persisted;
- every Glitcherry agent uses the same local environment boundary and already
  has an absolute role-specific `adapterConfig.instructionsFilePath`.

The Code Reviewer therefore received the right role name but was blocked because
the issue still named the Media Engineer's Project workspace. This did not
protect the code. It only compared two administrative labels while the real
shared task worktree remained known exclusively to the controller.

## Assumptions

- The Glitcherry Android project continues to use `develop` as its integration
  branch.
- `/Users/anton/Android/Glitcherry-Android` remains the clean canonical Android
  clone on the iMac and becomes the shared Project workspace anchor.
- The generated per-agent workspace directories remain local instruction roots.
  They are not deleted and do not become Git execution directories.
- `adapterConfig.instructionsFilePath` remains absolute and unique per agent.
- The task worktree contains only tracked project-wide repository instructions;
  it never contains a copied role bundle.
- One slice has only one live phase owner and one controller lease at a time.
- The CTO remains the Walker, sole merge authority, and cleanup coordinator.
- Normal product slices route CTO -> one primary engineer -> Code Reviewer ->
  CTO. QA remains a sprint-end gate, not a normal per-slice phase.
- GLA-17 finishes under the currently deployed protocol. Migration begins only
  after GLA-17 is terminal and its retained worktree/refs are cleanly resolved,
  before any GLA-18 child is started.
- No Paperclip issue is deleted. Historical workspace/run records are archived
  or retained through supported APIs.

## Scope

### Included

- Replace six selectable role-specific Project workspaces with one primary
  project-scoped Android workspace for execution routing.
- Keep the six generated role instruction roots and inject the current assignee's
  bundle independently of the execution cwd.
- Enable and configure Paperclip execution workspaces for Glitcherry slices.
- Add a backward-compatible strict Codex-adapter option that refuses to launch
  when a configured role instruction file cannot be read.
- Use one isolated Git-worktree Execution workspace per slice and reuse its exact
  ID, cwd, branch, and HEAD across sequential role handoffs.
- Change the slice controller from worktree creator to the authority that adopts,
  records, leases, validates, and cleans the Paperclip-created worktree.
- Remove role-specific Project-workspace rebinding from every handoff.
- Add a post-GLA-17 migration, diagnostic canary, archival procedure, rollback,
  and watchdog rules.
- Update source instructions, generated bundles, scripts, tests, and runbooks so
  they describe one contract.

### Excluded

- Product code or roadmap-slice implementation.
- Changing the single-writer, three-review-rejection, sprint-end smoke, merge,
  or no-issue-deletion policies.
- Parallel phase owners or parallel slices.
- Sharing an agent conversation/session between different agents.
- Moving secrets into repositories or generated instruction bundles.
- Direct database/JSON state edits, destructive cleanup by glob, or deleting
  historical Paperclip audit evidence.
- Migrating a live GLA-17 worktree in place.

## Terms

- **Project workspace**: the durable Paperclip pointer to the canonical Android
  Git project. It is project-scoped, not agent-scoped.
- **Execution workspace**: the actual checkout used for one issue run. For a
  slice, it is the one isolated Git worktree reused by every sequential phase.
- **Role instruction root**: a generated local directory containing one agent's
  `AGENTS.md`. It supplies instructions but is not a code checkout.
- **Task worktree**: the filesystem directory and Git branch represented by the
  slice's Execution workspace.
- **Controller state**: the durable Glitcherry record of exact issue, branch,
  worktree, HEAD, execution workspace, phase, owner, lease, and cleanup state.
- **Runtime finalize barrier**: Paperclip's completion of workspace finalization
  after an agent process exits; the parent may perform cleanup only after it.

## Instruction assembly

Changing to one execution workspace must not weaken role identity. Every wake is
assembled from four independent layers:

1. Paperclip injects the current agent's absolute
   `adapterConfig.instructionsFilePath`. This is the private role bundle for CTO,
   Android Engineer, Media Engineer, Code Reviewer, QA, or CEO.
2. The generated role bundle imports the shared Glitcherry workflow and common
   fragments. Deployment records and verifies the expected bundle hash.
3. Codex loads tracked repository `AGENTS.md` files from the actual task-worktree
   cwd. These instructions are project-wide and must not impersonate a role.
4. The Paperclip issue and approved slice spec provide task-specific authority,
   boundaries, and acceptance criteria.

The current `codex-local` adapter only emits a warning and continues when
`instructionsFilePath` cannot be read. That is unsafe for this topology. A narrow
Paperclip prerequisite adds `requireInstructionsFile=true`: when enabled, an
empty, unreadable, or non-file `instructionsFilePath` fails the run before Codex
is launched. Its default remains `false` for backward compatibility. Glitcherry
sets it to `true` for all six agents.

The runtime therefore fails before Codex starts only when the configured role
instruction file is missing or unreadable. Rendered/deployed bundle hashes are
checked once during deployment and the diagnostic canary, not on every wake.
Bundle deployment is avoided during an active slice; if an emergency deployment
is needed, the current slice may continue with its already loaded version unless
the changed instruction fixes a process-breaking defect.

Paperclip agent task sessions are agent-scoped. A handoff may resume the same
agent's own session, but it must not reuse another role's session. The canary and
tests verify distinct agent/session identity even though the cwd is shared.

## Enforcement budget

The controller is not a general proof system. It blocks only conditions that can
cause concurrent writes, work on the wrong code, loss of uncommitted work, or a
new slice starting before the old one is cleaned:

- another valid owner lease already exists;
- the execution-workspace ID, task path, Git branch, or handed-off HEAD points to
  different code than the recorded slice;
- a handoff is attempted with uncommitted changes;
- the prior slice still has an unmerged change, live lease, or retained task
  worktree when the Walker tries to start the next slice;
- the required role instruction file cannot be loaded.

Everything else is either checked once at deployment/canary, logged as a warning,
or investigated only after a real failure. A stale non-authoritative timestamp,
extra historical execution row, missing optional evidence field, bundle hash
that was already accepted at deployment, or a briefly alive process that no
longer owns the repository lease must not stop ordinary progress.

## Alternatives considered

### A. Keep six Project workspaces and make role rebinding atomic

This is the smallest patch, but it preserves the category error: Project
workspace remains a role label while the controller owns the real code path.
It would prevent the immediate mismatch yet leave Paperclip blind to the task
worktree and continue producing disposable execution records. Rejected.

### B. Use one shared Project workspace without an issue Execution workspace

This removes role mismatch but still makes Paperclip launch from the canonical
clone or create untracked runtime records rather than bind to the exact slice
worktree. The controller and Paperclip would continue to disagree. Rejected.

### C. One Project anchor plus one reusable isolated Execution workspace per slice

This models the actual entities, keeps role instructions independent, permits
one exclusive lease, and gives Paperclip and the controller the same cwd and
identity. Paperclip creates the worktree on the first CTO wake; the controller
then adopts that exact persisted workspace. Selected.

### D. Create a fresh worktree for every phase

This improves physical isolation but forces a push/fetch or patch transfer at
every handoff, multiplies cleanup and state, and makes iterative review slower
without improving correctness in a strictly sequential workflow. Rejected.

## Selected runtime design

### Project topology

- Reconcile one primary Project workspace named for the Glitcherry Android
  project, with `cwd` equal to the canonical Android clone.
- Set the project execution policy to `enabled=true`, default mode
  `shared_workspace`, `allowIssueOverride=true`, and use the shared Project
  workspace as `defaultProjectWorkspaceId`.
- Root/roadmap/controller issues use the shared default and do not receive a
  disposable Git worktree.
- Slice children explicitly select `isolated_workspace` with the Git-worktree
  strategy and reuse semantics.
- Retain the six legacy role Project workspace records as advanced historical
  entries during rollout. Mark them non-primary and never bind new issues to
  them. Remove them only in a later separately approved cleanup if Paperclip has
  a supported archival operation and no historical reference is damaged.
- Keep every role directory and `workspace/AGENTS.md` because it remains the
  source for that role's absolute `instructionsFilePath`.

### Slice creation and controller adoption

Paperclip owns initial worktree realization; the controller adopts the result:

1. Root CTO proves that no prior slice, retained worktree, lease, merge, or
   cleanup is pending.
2. Root CTO creates exactly one child in `todo` without an assignee, with the
   shared Project workspace and explicit `isolated_workspace` settings but no
   Execution workspace ID. Its issue-level strategy pins `type=git_worktree`, the
   exact approved base SHA, branch template
   `feature/{{issue.identifier}}-{{slug}}`, and the host-local task-worktree root.
   The explicit settings prevent accidental inheritance of the root's shared
   Execution workspace; the missing assignee prevents a premature wake.
3. Root adds the child as its explicit blocker, assigns CTO, moves the child to
   the runnable state, and wakes it.
4. Paperclip derives branch/path from the strategy, creates one Git worktree,
   persists its `executionWorkspaceId`, and launches CTO inside that directory.
5. CTO calls controller `adopt`, which reads the live issue and Execution
   workspace and creates controller state plus the initial lease only when issue,
   Project workspace, Execution workspace, cwd, branch, base/HEAD, and owner
   agree.
6. Later role wakes use the persisted `executionWorkspaceId` with
   `reuse_existing`; they do not realize another worktree.

The selected convention is branch `feature/<ISSUE-KEY>-<slug>` and filesystem
path `<task_worktree_root>/feature/<ISSUE-KEY>-<slug>`. This formula is tested
once before activation. If first wake or reassignment creates a second path or
Execution workspace, the canary fails and rollout stops; ordinary product slices
do not repeat a separate adoption proof.

### Controller state v2

The controller schema records at least:

- company, project, issue ID/key, and root ID;
- shared `projectWorkspaceId` and slice `executionWorkspaceId`;
- canonical repository root, exact worktree path, branch, base SHA, and current
  committed HEAD;
- phase, current owner, expected next owner, lease identity/timestamps, and
  review-rejection count;
- Android/control merge SHAs;
- runtime-finalize state and cleanup state.

No transition may infer identity from a role workspace name. A claim requires:

- issue assignee equals the expected controller owner;
- issue `projectWorkspaceId` equals the shared project anchor;
- issue `executionWorkspaceId` equals the recorded slice workspace;
- adapter cwd, Execution-workspace cwd, and controller path resolve to the same
  directory;
- branch and clean committed HEAD match;
- no other valid lease exists.

### Sequential handoff

Every handoff uses the same slice `projectWorkspaceId` and
`executionWorkspaceId`. Only controller phase/owner, Paperclip assignee/status,
and the new agent's injected role bundle change.

1. Current owner completes the required local commit and targeted verification.
2. Controller validates clean status and records exact handed-off HEAD and next
   owner, then releases the current lease.
3. Current owner posts durable evidence.
4. Paperclip changes the assignee without changing either workspace ID.
5. One read-back proves the new assignee, expected controller phase, unchanged
   Execution workspace ID, and handed-off HEAD.
6. Current process stops.
7. Next owner wakes, receives its own absolute role instructions, claims the
   controller lease, and verifies the same code state before changing it.

There is never more than one live owner. A mention is not a handoff. A reviewer
rejection returns the same issue/worktree/PR to the primary engineer; it does not
create a replacement workspace.

### Merge, runtime finalization, and cleanup

An isolated Execution workspace cannot be archived while its child issue is
nonterminal, and a process cannot safely delete its own cwd. Cleanup therefore
uses an explicit parent-finalized state:

1. CTO obtains exact-head approval, squash-merges the one Android PR and required
   control-plane change, and verifies both merge SHAs on `origin/develop`.
2. The controller preserves the approved feature HEAD and merge SHAs. In the
   exact clean disposable worktree, it then moves only the local task branch to
   the verified Android merge SHA so Paperclip's normal `git branch -d` cleanup
   can succeed after a squash merge.
3. Controller enters `merged_pending_parent_cleanup`; no new slice is selectable.
4. CTO marks the child `done` and exits the child run without deleting its cwd.
5. Paperclip may emit an early structural `issue_children_completed` root wake.
   Root treats it as a cleanup opportunity only, never as authority to select a
   new slice. The child is also an explicit root blocker, so the authoritative
   dependency continuation remains subject to Paperclip's workspace-finalize
   barrier.
6. After `workspace_finalize=succeeded`, root CTO verifies the exact Execution
   workspace ID, clean worktree, merge evidence, and no live lease.
7. Root CTO archives that exact Execution workspace through the supported API;
   Paperclip removes its worktree and normalized local task branch.
8. The controller deletes any remaining exact remote task/status refs, proves the
   path and refs absent, confirms the recorded child dependency is resolved, and
   enters `cleaned`.
9. Only now may the Walker select or create the next slice child.

This deliberately means the child reaches Paperclip `done` immediately before
physical cleanup. `done` and an early root wake are not sufficient for
progression: root selection is gated on `workspace_finalize=succeeded` and
controller `cleaned`. If archive or ref cleanup fails, the root stays on cleanup
for the same completed child; it does not start the next slice.

### Watchdog behavior

- The deployed iMac watchdog uses the slice's exact Execution workspace ID and
  controller lease together with company -> agent -> run -> PID when it needs to
  stop a stuck run.
- It may terminate only an exactly attributed stuck process and must preserve the
  shared worktree, committed HEAD, controller state, and issue.
- Normal handoff serialization relies on the exclusive controller lease. Exact
  PID attribution is required only when the watchdog must kill a stuck process,
  not as a routine gate on every handoff.
- After a kill, recovery resumes the same agent/issue/execution workspace or
  hands off through a supported controller transition. It never creates a second
  worktree.
- Rollout must verify the watchdog is actually loaded and active on the iMac;
  repository configuration alone is not evidence.

## Migration and rollout

### Gate 0 — do not disturb GLA-17

- Finish or recover GLA-17 with the currently deployed protocol.
- Prove its child terminal, branch merged or explicitly retained, worktree clean
  and removed, controller state clean, and no live attributed run.
- Pause the root before any GLA-18 child is created.

### Gate 1 — preflight and inventory

- Record Paperclip version/commit, instance experimental settings, project
  policy, all Glitcherry Project/Execution workspaces, nonterminal issues, active
  runs, agent environments, and watchdog status.
- Prove all six agents remain in the compatible local environment and have
  unique absolute instruction paths.
- Inventory all other companies/projects before changing the instance-wide
  isolated-workspace flag. Activation requires either no enabled non-Glitcherry
  execution-workspace policy or an explicit recorded confirmation that every
  affected project is already compatible. This is a one-time migration check,
  not a per-slice gate.
- Archive obsolete GLA-17 execution rows opportunistically after GLA-17 is
  terminal and supported readiness checks allow it. Residual historical rows are
  not allowed to block GLA-18 when the new slice has one unambiguous current
  Execution workspace ID. Preserve issues and audit comments.

### Gate 2 — deploy dormant contract

- Implement and test controller state v2, common workflow, role instructions,
  reconciliation, runtime adoption, and diagnostic tooling.
- Render bundles and prove deployed/rendered hashes agree.
- Reconcile the one shared Project workspace while leaving legacy role records
  retained and non-primary.
- Do not activate isolated slice execution yet.

### Gate 3 — enable and diagnostic canary

- Enable `enableIsolatedWorkspaces` through the supported Paperclip setting/API
  path only after the instance-wide impact check passes.
- Run one retained, explicitly diagnostic child with no product changes.
  Paperclip creates its one isolated Execution workspace and the controller
  adopts it.
- Route the same clean committed no-op checkpoint through CTO -> Android Engineer
  -> Media Engineer -> Code Reviewer -> QA -> CEO -> CTO. This full identity
  circuit is a diagnostic exception; normal product slices still exclude QA/CEO.
- Every role records its agent ID/name, role bundle path, both workspace IDs,
  cwd, branch, HEAD, and controller owner. The renderer/deployment step records
  bundle hashes once for the entire canary.
- Finish the child, wait for runtime finalization, archive the exact execution
  workspace, delete exact refs, and retain the issue as `done` or `cancelled`.
- Prove that there was one task worktree, one execution workspace, the expected
  role at every step, no product merge, and no residual branch/path/lease.

### Gate 4 — activate for the next product slice

- Promote GLA-18 only after the diagnostic record is accepted by the Human
  Engineering Lead.
- Root creates the isolated child unassigned, then assigns CTO; Paperclip creates
  one worktree, the controller adopts it, and the normal CTO -> writer -> Reviewer
  -> CTO flow begins.
- Observe at least the first complete product-slice lifecycle before considering
  removal of legacy role Project workspace records.

## Recovery and rollback

- Before activation, rollback disables the isolated-workspace flag, restores the
  prior project policy/reconciler from the reviewable implementation commit, and
  keeps the root stopped. It does not alter GLA-17 history.
- During the canary, a second worktree/execution ID, wrong role instructions,
  overlapping lease, or unsafe cleanup is a hard failure. Preserve evidence,
  cancel/complete the canary through supported APIs, clean only exact known
  resources, disable activation, and return to the previous protocol.
- After a product slice starts, dirty/unmerged work is always preserved. Rollback
  first recovers or completes that same slice; it never migrates it to a new
  worktree or silently changes workspace mode mid-run.
- Never edit Paperclip database rows directly. If the supported state machine
  cannot advance, record the blocker and fix the state transition in reviewed
  code.

## Affected files and areas

Expected Gimle-Palace changes after spec approval:

- `paperclips/projects/glitcherry-android/WORKFLOW.md` — replace role-workspace
  handoffs with stable Project/Execution workspace invariants and parent cleanup.
- `paperclips/projects/glitcherry-android/overlays/codex/_common.md` — verify
  shared cwd plus independent role bundle on every claim.
- `paperclips/projects/glitcherry-android/roles-codex/glitcherry-cto.md` — add
  adopt/finalize/cleanup responsibilities.
- `paperclips/projects/glitcherry-android/roles-codex/android-engineer.md` and
  `media-pipeline-engineer.md` — require the same execution ID and cwd at writer
  handoff.
- `paperclips/projects/glitcherry-android/roles-codex/code-reviewer.md` — remove
  role-specific Project-workspace blocking and verify its own instruction bundle.
- `paperclips/projects/glitcherry-android/roles-codex/qa-engineer.md` and
  `glitcherry-ceo.md` — support only the diagnostic identity circuit and existing
  sprint/root responsibilities.
- `paperclips/projects/glitcherry-android/paperclip-agent-assembly.yaml` — expose
  the revised shared invariants to rendered bundles.
- `paperclips/projects/glitcherry-android/scripts/slice-worktree.py` — add state
  v2, adoption checks, stable workspace IDs, finalize/cleanup states, and
  exact recovery.
- `paperclips/projects/glitcherry-android/scripts/reconcile-paperclip-project.sh`
  — create/reuse one primary Project workspace, retain legacy records, configure
  policy, and fail closed on ambiguous topology.
- `paperclips/projects/glitcherry-android/scripts/prepare-runtime-workspaces.sh`
  — validate the canonical project anchor and role instruction roots without
  treating role roots as Project workspaces.
- `paperclips/projects/glitcherry-android/bindings.local-example.yaml` and
  `paths.local-example.yaml` — document the shared workspace/execution fields and
  canonical deterministic paths without secrets.
- `paperclips/tests/test_glitcherry_android_assembly.py` — assert instruction
  layering and remove stale role-workspace text.
- `paperclips/tests/test_glitcherry_android_paperclip_project.py` — test one
  project anchor, retained legacy handling, policy, and idempotent reconciliation.
- `paperclips/tests/test_glitcherry_android_runtime_workspaces.py` — test
  instruction roots separately from execution worktrees.
- `paperclips/tests/test_glitcherry_slice_worktree.py` — test adoption, controller
  schema v2, leases, handoffs, finalization, recovery, and cleanup.
- `paperclips/scripts/smoke-test.sh`,
  `paperclips/scripts/lib/_smoke_probes.sh`, and
  `paperclips/tests/test_phase_c_smoke_test.py` — stop treating six role roots or
  `workspace/repo` directories as six synchronized code checkouts; probe the one
  project anchor and current slice Execution workspace instead.
- Generated `paperclips/dist/glitcherry-android*` artifacts — renderer output
  only; never hand-edited.
- Glitcherry operator/developer runbooks in the control repository — document the
  new topology, diagnostic, incident recovery, watchdog checks, and third-party
  handoff without secrets.

Expected Paperclip prerequisite after spec approval:

- `packages/adapters/codex-local/src/index.ts` and its UI/config contract — expose
  the backward-compatible `requireInstructionsFile` boolean.
- `packages/adapters/codex-local/src/server/execute.ts` and focused tests — throw
  before spawning Codex when strict mode has no readable instruction file; keep
  the current warning behavior when strict mode is disabled.

The Paperclip change is implemented and deployed from its own current
integration-branch-based spec/feature branch before Glitcherry activation. No
other Paperclip core change is assumed. If Gate 3 exposes a missing reuse or
finalization capability, rollout stops and a second narrowly scoped Paperclip
core spec is required.

The generic `paperclips/scripts/rollback.sh` is intentionally not expanded for a
single project migration. The project runbook records a short operator rollback
using supported settings/project APIs and the exact IDs captured by preflight.
This avoids adding untested global rollback machinery to solve a Glitcherry-only
change.

## Acceptance criteria

1. The Glitcherry project has exactly one primary selectable Project workspace
   for new work, pointing at the canonical Android clone; role directories remain
   instruction roots, not code workspaces.
2. One active slice has exactly one issue-linked isolated Execution workspace,
   one branch/worktree, one controller record, and at most one valid lease.
3. `projectWorkspaceId`, `executionWorkspaceId`, cwd, branch, and handed-off HEAD
   remain unchanged across every sequential role reassignment.
4. CTO, Android, Media, Reviewer, QA, and CEO each report their expected role and
   absolute instruction path while sharing the same diagnostic cwd.
5. An unreadable role instruction file, mismatched workspace/path/head, second
   valid owner lease, or dirty uncommitted handoff blocks before code work.
6. A reviewer can inspect and reject the writer's exact committed code without a
   second clone, second worktree, or workspace-ID rebinding.
7. Normal product routing remains CTO -> one writer -> Reviewer -> CTO, with no
   more than three full review-rejection cycles and no per-slice QA gate.
8. Child completion cannot allow the next slice until Paperclip finalization has
   succeeded and the parent proves exact worktree/ref/controller cleanup.
9. GLA-17 is not migrated in place; GLA-18 cannot start until migration gates and
   the retained diagnostic canary are accepted.
10. Historical issues are never deleted. Stale execution records are archived
    only by supported API after readiness checks.
11. The iMac watchdog is observed active and retains the existing exact-attribution
    rule for any real stuck-run recovery; no synthetic kill is required by this
    rollout.
12. Reconciliation and deployment are idempotent and create neither duplicate
    primary workspaces nor duplicate task worktrees on a second run.
13. No secret, token, password, private key, or `.env` value enters source,
    generated bundles, diagnostic comments, or test fixtures.
14. Source workflow, rendered roles, scripts, tests, and runbooks contain no
    contradictory rule requiring role-specific Project-workspace reassignment.
15. Before the one-time instance flag change, every enabled non-Glitcherry
    execution-workspace policy is absent or explicitly confirmed compatible; this
    inventory is not repeated for ordinary slices.

## Verification plan

### Static and unit verification

- Run `git diff --check`, shell syntax checks, Python compilation, and focused
  Glitcherry tests.
- Render the resolved assembly twice and require deterministic output/hashes.
- Run Paperclip adapter tests proving `requireInstructionsFile=true` fails before
  subprocess launch for absent/unreadable paths and succeeds for a readable
  bundle; prove the default/false behavior remains backward compatible.
- Search changed source and rendered bundles for the old role-workspace handoff
  rule and per-role repository assumptions.
- Use temporary Git repositories for the four process-breaking controller paths:
  initial adoption, clean committed handoff, competing lease refusal, and
  post-squash exact cleanup. Existing tests continue to cover review limits and
  dirty/stale refusal; do not duplicate them in a new exhaustive matrix.

### Paperclip integration verification

- Against a disposable diagnostic issue, verify issue read-back preserves one
  shared Project ID, one Execution ID, isolated mode, reuse preference, and exact
  cwd after every role reassignment.
- Verify Paperclip creates one worktree, the controller adopts it, and no second
  directory or branch appears during handoff.
- Verify each role reports its own instruction marker/path.
- Verify child `done` -> possible early root cleanup wake -> workspace finalize ->
  archive -> controller cleanup -> next-slice eligibility.
- Re-run reconciliation and deployment and prove resource counts/IDs are stable.

### Live acceptance evidence

- A compact before/after inventory of Glitcherry Project/Execution workspaces,
  active runs, Git worktrees/refs, and the instance flag.
- One full diagnostic identity circuit with role, instruction path, workspace
  IDs, cwd, branch, HEAD, and controller owner.
- Current evidence that the iMac watchdog service is loaded and running.
- Final proof of no residual diagnostic path/ref/lease and no unintended change
  to GLA-17 or unrelated Paperclip companies.

## Risks and mitigations

- **Instance-wide flag affects another company.** Inventory all projects first,
  canary while Glitcherry root is paused, and disable the flag on any unrelated
  mode change.
- **A later handoff creates a second worktree.** Persisted Execution ID plus reuse
  preference are verified by the one diagnostic circuit before activation.
- **Role instructions disappear in the shared cwd.** Strict absolute per-agent
  instruction loading stops the run; hashes are checked at deployment/canary.
- **Two agents touch one folder concurrently.** The controller's exclusive lease
  gates code access. PID attribution is used only when recovering a stuck run.
- **Squash merge makes branch deletion non-fast-forward.** After merge proof, the
  controller preserves the approved head in state and normalizes only the clean
  disposable local task branch to the merge SHA before Paperclip archive.
- **Child is done while cleanup is incomplete.** Root selection also requires
  controller `cleaned`; `done` alone never advances the Walker.
- **Legacy execution rows obscure live state.** Archive only terminal-ready rows,
  retain audit history, and query by the exact current execution ID.
- **Recovery invents a replacement state.** Resume the same issue, execution ID,
  worktree, and controller record or stop for a reviewed transition fix.

## Owner decisions embodied by this spec

Approval of this spec approves all of the following together:

1. One Project workspace is the project/codebase anchor; role identity no longer
   uses `projectWorkspaceId`.
2. One isolated Execution workspace is reused by every sequential phase of a
   slice.
3. Role instructions remain separate through absolute per-agent injection and
   strict loading; hashes are verified once at deployment/canary, not every wake.
4. Paperclip creates the deterministic worktree on the first CTO wake and the
   controller adopts the persisted Execution workspace before code work.
5. The instance isolated-workspace feature may be enabled only after the global
   inventory and diagnostic gates pass.
6. A slice child becomes `done` before parent-owned physical cleanup, but the
   next slice remains forbidden until finalize and cleanup are proven.
7. GLA-17 completes under the old topology; cutover occurs before GLA-18.

## Open questions

None for implementation authorization. If the installed Paperclip build cannot
persist/reuse the same Execution workspace or expose finalization state in the
diagnostic canary, that is an implementation blocker requiring a separate
narrowly scoped Paperclip-core spec; it is not authority to improvise a database
edit or alternate workspace topology.
