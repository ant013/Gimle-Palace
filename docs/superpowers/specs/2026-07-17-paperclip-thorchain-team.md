# Paperclip ThorChainKit Team, Repository, and Product-Retirement Spec

**Status:** Design review gate; no implementation or destructive action is authorized by this document alone.
**Date:** 2026-07-17
**Source branch:** `feature/paperclip-thorchain-team`
**Source baseline:** `origin/develop@b56232d5b49183cfac04c9d403659a4a45cfcceb`
**Target Paperclip runtime:** local MacBook instance at `/Users/ant013/Data/AI/paperclip`, pinned to `paperclipai@2026.618.0`
**Target product repository:** private `ant013/ThorChainKit.Swift`, local root `/Users/ant013/Data/AI/thorchain`

## 1. Decision Summary

Create a separate Paperclip company for ThorChainKit with five `codex_local`
agents, all pinned to `gpt-5.6-sol` with `xhigh` reasoning. Preserve the proven
two-loop delivery model while separating CEO outer-roadmap ownership from CTO
child-delivery ownership.

Create the private English-language `ant013/ThorChainKit.Swift` repository from
the existing documentation workspace. The initial repository commit is a
governance and design seed, not an implementation of Sprint 1: it contains no
production `Package.swift` or `Sources` deliverable. Product code begins only
through the approved roadmap walker.

Retire only the old Unstoppable product state inside Paperclip after the new
ThorChain team passes live acceptance:

- delete old issues, projects, and project-workspace records;
- remove only old-project wake sources such as routines/monitors after they are
  exported and the old team is quiesced;
- move the three Paperclip-managed product checkouts into a timestamped local
  backup archive before deleting their records;
- preserve the old Unstoppable company, its five agents, materialized role
  bundles, run logs, exports, and every external source repository.

The old company itself is explicitly outside the deletion boundary.

## 2. Goals

1. Add a current-tree ThorChain UAA assembly with exact role identity, topology,
   model, path, and workflow contracts.
2. Make UAA distinguish prompt capability (`profile`) from live Paperclip
   identity (`paperclip_role`, `paperclip_icon`, `workflow_role`).
3. Make canary and smoke selection identify the technical CTO explicitly rather
   than taking the first `profile: cto` agent.
4. Extend greenfield bootstrap rollback so every mutation made by the run has an
   inverse or a fail-closed recovery instruction.
5. Bind every future repository-changing slice to `analog-driven-change`,
   `gimle-evidence`, codebase-memory, exact-tree Serena verification, and the
   approved Vultisig/Horizontal Systems reference boundary.
6. Create and seed the private ThorChainKit repository in English, with no
   co-author trailers.
7. Create one ThorChain Paperclip project and one primary local project
   workspace bound to `/Users/ant013/Data/AI/thorchain` on `main`.
8. Prove all five agents, their bundle identity, runtime model, role boundaries,
   and a disposable end-to-end handoff without starting the roadmap.
9. Export and remove only the old product/issues/project-workspaces after a
   second recoverable checkpoint.

## 3. Non-Goals

- Updating Paperclip or changing its installed version.
- Deploying to the production iMac or changing the iMac Paperclip instance.
- Deleting the Unstoppable Paperclip company or its five agents.
- Deleting run logs, materialized role bundles, SQL backups, or portable exports.
- Deleting or modifying `/Users/ant013/Ios/HorizontalSystems/*` source repos or
  `ant013/multi-swap-ios` Git/GitHub history.
- Implementing ThorChainKit source code, `Package.swift`, the Example app, or
  Maestro flows during this assembly task.
- Creating or starting a roadmap-walker issue during bootstrap.
- Adding Maestro to Unstoppable Wallet. Later Maestro acceptance remains scoped
  to the ThorChainKit `iOS Example` repository surface.
- Updating or cherry-picking polluted commit `c62cef3e`.

## 4. Assumptions and Authorizations to Confirm by Approval

- The repository is private, named exactly `ant013/ThorChainKit.Swift`, with
  default integration branch `main`.
- Repository prose, commits, issue templates, PR text, and role bundles are in
  English. The existing Russian documentation remains untouched in the source
  folder until translated files are verified; imported repository copies are
  English.
- Commits use the configured operator identity and contain no
  `Co-authored-by:` trailer.
- The new Paperclip company is named `ThorChainKit`, with issue prefix `THOR`.
- All five agents use `adapterType=codex_local`, model `gpt-5.6-sol`, and
  `modelReasoningEffort=xhigh`.
- Each Paperclip agent has `maxConcurrentRuns=1`. Bounded Codex review
  subagents execute inside the owning run and inherit `gpt-5.6-sol`; they are
  not additional Paperclip agents.
- The local Paperclip runtime is started only at its pinned installed version.
- The new repository is indexed as `Users-ant013-Data-AI-thorchain` before team
  activation; if the index slug differs, bindings use the exact returned slug.
- Approval of this exact spec authorizes the scoped local Paperclip mutations,
  private repository creation, and recoverable movement of the three old
  Paperclip-managed checkout directories. It does not authorize deletion of
  the old company, agents, archived workspaces, or external repositories.

## 5. Current-State Evidence

### 5.1 Palace/UAA

- Clean baseline `b56232d` contains the current Trading UAA family, build,
  binding resolution, deployment, rollback, smoke scripts, and tests.
- `paperclips/projects/trading/paperclip-agent-assembly.yaml` is a schema-v2,
  five-agent assembly with host-local IDs and paths.
- `paperclips/projects/trading/WORKFLOW.md` provides the outer walker, seven
  child phases, QA routing, and roadmap marker convention.
- Current bootstrap forwards per-agent model and reasoning effort and hires in
  `reportsTo` order.
- Current rollback does not invert company creation, canonical bindings/paths,
  created workspace directories, or watchdog state.
- Current canary and smoke select the first `profile: cto`; this is ambiguous
  when CEO and CTO both use orchestration capability.

### 5.2 Historical Unstoppable Evidence

The preserved runtime has 194 NDJSON run logs and five materialized role
bundles. Twelve roadmap children were examined: eight completed the full seven
phases and four exposed violations. The preserved evidence establishes the
following reusable invariants:

- one active roadmap child at a time;
- parent `status=blocked` with `blockedByIssueIds=[activeChild]`;
- committed integration-branch roadmap marker is completion authority;
- spec, independent spec review, plan, implementation, code review, QA, then
  CTO merge;
- evidence comment before ownership transfer, one read-only verification, then
  stop.

It also establishes counterexamples that must not be copied: CEO rendered as
CTO, missing parent disposition, roadmap-only PR, premature merge, stale reopen,
`PR #TBD`, and internal review being treated as user design approval.

### 5.3 Local Paperclip

- Installed runtime: `paperclipai@2026.618.0`; the server is currently stopped.
- Last snapshot inventory: one Unstoppable company, five agents, three projects,
  three primary project workspaces, and 21 issues. Live preflight must replace
  these counts before mutation.
- Existing newest backup:
  `paperclip-20260618-202325.sql.gz`, SHA-256
  `df229fd0c9f43dfba498de14f1d240b2dca0931842839216b93e4eb1eff3e426`.
  Its timestamp predates later database-directory writes, so it is evidence,
  not a deletion checkpoint.
- Paperclip 2026.618 provides explicit `db:backup`, portable company
  export/import, issue delete, project-workspace delete, and project delete
  commands.
- The three old Paperclip-managed checkouts are exactly:
  `/Users/ant013/Data/AI/paperclip/workspace/unstoppable-wallet-ios`,
  `/Users/ant013/Data/AI/paperclip/workspace/stable-wallet-ios`, and
  `/Users/ant013/Data/AI/paperclip/workspace/multi-swap-ios`.

### 5.4 Repository Analogs

`TronKit.Swift` is the primary repository-shape analog: Swift Package library,
test target, and `iOS Example`. `EvmKit.Swift` independently confirms the
package-plus-example convention. Their legacy `master`, Swift tools 5.5, and
the missing EvmKit test target are counterexamples, not greenfield defaults.

## 6. Selected Analog Family and Delta Matrix

| Slice | Primary spine | Supporting evidence | Required delta | Failure introduced | Verification |
|---|---|---|---|---|---|
| Reversible product replacement | Paperclip 2026.618 backup/export/delete lifecycle | UAA deployment and smoke seams | Two checkpoints, full portable export, exact-ID transaction manifest, recoverable workspace archive | Partial cleanup or rollback restores old DB but not filesystem | Backup integrity/count manifest, export dry-run, archive inventory, post-state queries |
| Five-agent assembly | Trading schema-v2 UAA | Preserved Swift role and local Codex 5.6 runtime | Separate prompt profile from Paperclip/workflow identity; Codex-only roster | CEO/CTO ambiguity or unsupported role/model | Manifest tests, rendered bundle tests, live agent API/config checks |
| Roadmap walker | Trading two-loop workflow | 194 Unstoppable runs and 12 child histories | CEO owns outer loop; CTO owns child phases; explicit user approval; POST then PATCH | Parallel child, premature merge, stale reopen, invalid marker | Workflow lint, role-boundary probes, disposable handoff, no roadmap issue |
| Repository seed | TronKit package/test/example shape | EvmKit consumer example | Private `main`; English docs only at bootstrap; product scaffold deferred | Bootstrap falsely claims Sprint 1 or imports legacy defaults | GitHub visibility/default branch, file allowlist, English/provenance audit |

## 7. Target Team and Identity Contract

| Agent | Paperclip role | Prompt profile | Workflow role | Reports to | Allowed responsibility |
|---|---|---|---|---|---|
| `ThorChainCEO` | `ceo` | `cto` | `outer_walker` | none | Select one roadmap slice, manage parent blocker, stop/resume, portfolio status |
| `ThorChainCTO` | `cto` | `cto` | `inner_orchestrator` | CEO | Child spec, post-review plan, architecture rulings, merge gate |
| `ThorChainCodeReviewer` | `engineer` | `reviewer` | `reviewer` | CTO | Adversarial spec review and code review; never merge |
| `ThorChainSwiftEngineer` | `engineer` | `implementer` | `implementer` | CTO | TDD implementation and PR; never merge |
| `ThorChainQAEngineer` | `qa` | `qa` | `qa` | CTO | Independent acceptance; never merge or implement fixes |

Every manifest entry explicitly sets:

```yaml
target: codex
model: gpt-5.6-sol
modelReasoningEffort: xhigh
paperclip_role: <table value>
paperclip_icon: <crown|shield|eye|code|bug>
workflow_role: <table value>
```

`profile` continues to select capability composition. It no longer determines
live identity when `paperclip_role` is present. Existing manifests without the
new keys retain current fallback behavior.

## 8. Roadmap Walker Contract

### 8.1 Outer loop — CEO only

1. Read the live parent issue and reject closed, foreign, or stale wakes.
2. If an active child exists, ensure the parent is blocked by exactly that child
   and stop.
3. Fast-forward/fetch `origin/main` and scan `ROADMAP.md` top-to-bottom.
4. A slice is complete only if a valid `**Status:** ✅` line exists within the
   next three lines on `origin/main`.
5. Create exactly one child assigned to `ThorChainCTO`.
6. Comment selection evidence, set parent `blocked` with
   `blockedByIssueIds=[child]`, verify once, and stop.
7. Never write spec, plan, code, or merge from the parent run.

### 8.2 Inner loop — one child

1. CTO creates a fresh feature branch from `main`, writes and pushes the slice
   spec.
2. CodeReviewer performs adversarial spec review, using bounded parallel
   reviewers when the slice calls for them.
3. CTO resolves findings and writes the concrete implementation plan.
4. The child becomes `blocked` on explicit Board/user approval required by
   `analog-driven-change`; internal role approval is insufficient.
5. SwiftEngineer implements TDD and opens the PR.
6. CodeReviewer reviews the exact PR head and records commands/results.
7. QA independently verifies the same head, including the kit Example and
   Maestro only when the slice scope requires it.
8. CTO verifies reviewer/QA evidence, adds the exact marker in the same PR,
   squash-merges without co-author trailers, verifies `origin/main`, then closes
   the child.

### 8.3 Atomic handoff

```text
push phase artifacts
POST evidence comment ending in the formal next-owner mention
PATCH assignee and status
one read-only verification
STOP
```

The smoke contract must require both `/comments` POST and `/issues/{id}` PATCH.
A mention alone does not transfer ownership. A non-2xx comment blocks the
handoff. HTTP 409 is an execution-lock conflict and is never bypassed with SQL.

### 8.4 Activation boundary

Bootstrap creates no parent roadmap issue and no product child issue. Runtime
acceptance may create disposable issues whose exact UUIDs are recorded and
deleted after evidence capture. The autonomous walker starts only after a later
explicit operator instruction.

## 9. Repository Seed Design

The existing `/Users/ant013/Data/AI/thorchain` folder becomes the local clone of
the private repository. Before initialization, `.DS_Store` and machine-local
artifacts are excluded. Before any in-place translation, the full pre-Git
documentation tree is copied to
`/Users/ant013/Data/AI/paperclip/backups/thorchain-repository-seed-<UTC>/source-docs-ru/`
and receives a SHA-256 manifest. The archive is outside the future repository
and is never modified by the translation step. The initial `main` commit
contains:

- English `README.md`, `ROADMAP.md`, and `AGENTS.md`;
- English `docs/research/`, `docs/roadmap/`, `docs/specs/`, and `docs/reports/`;
- the approved roadmap-walker contract and the preserved historical analysis in
  English;
- `.gitignore` and documentation navigation.

The initial file allowlist excludes `Package.swift`, `Sources/`, `Tests/`,
`iOS Example/`, and `.maestro/`. Those are S1-01 deliverables and must be
created by the approved child workflow. No license is inferred for the private
repository.

### 9.1 Agent Development Evidence Contract

The committed ThorChain `AGENTS.md` and rendered role bundles require this order
for every repository-changing roadmap slice:

1. Load `analog-driven-change` and its automatic `gimle-evidence` companion
   from the host-local `{{paths.gimle_skills_root}}`; never use the legacy
   `analog-driven-development` workflow.
2. Query codebase-memory project `Users-ant013-Data-AI-thorchain` first, then
   activate the exact issue workspace with Serena and verify load-bearing
   candidates through targeted `rg`/Git reads.
3. Use Horizontal Systems kits and Unstoppable only as verified architecture
   analogs. Load `uw-ios-analog-profile` only for an exact Unstoppable checkout
   and a host-integration slice.
4. Use the pinned Vultisig iOS checkout as THOR-specific supporting evidence,
   never as the primary lifecycle/ownership spine without a new approved
   design decision.
5. Persist the slice evidence report under `docs/reports/gimle/`, complete
   adversarial review, push the final spec/plan, and block for explicit user
   approval before implementation.
6. Keep Maestro in the ThorChainKit `iOS Example`; Unstoppable acceptance uses
   adapter/AppTests/manual gates only.

For adversarial spec review, CodeReviewer launches three fresh, bounded,
read-only Codex workers in parallel: architecture/boundaries,
security/protocol-safety, and verification/operability. Their findings are
aggregated into one severity-tagged review. Runtime trace evidence must show
that these workers inherited `gpt-5.6-sol`; they never create Paperclip agents.

Actual absolute roots for Gimle skills and pinned reference checkouts live only
in host-local `paths.yaml`. Committed examples use sanitized placeholder paths.

## 10. Paperclip Project and Workspace

Create one project in the new ThorChain company:

- name: `ThorChainKit.Swift`;
- status: `planned`;
- icon: `package`;
- integration branch/default ref: `main`;
- primary project workspace name: `thorchain-kit-swift`;
- source type: `local_path`;
- cwd: `/Users/ant013/Data/AI/thorchain`;
- repo URL: the private GitHub SSH/HTTPS URL returned by `gh`;
- execution policy: `shared_workspace`, with issue override enabled.

The shared project workspace makes the current folder the product authority.
Paperclip execution-workspace records may refer to it, but the UAA agent idle
directories are not additional product clones.

## 11. Palace/UAA Affected Areas

### New project files

- `paperclips/projects/thorchain/paperclip-agent-assembly.yaml`
- `paperclips/projects/thorchain/WORKFLOW.md`
- `paperclips/projects/thorchain/bindings.local-example.yaml`
- `paperclips/projects/thorchain/paths.local-example.yaml`
- `paperclips/projects/thorchain/fragments/local/agent-roster.md`
- `paperclips/projects/thorchain/overlays/codex/_common.md`
- `paperclips/projects/thorchain/roles-codex/thorchain-ceo.md`
- `paperclips/projects/thorchain/roles-codex/thorchain-cto.md`
- `paperclips/projects/thorchain/roles-codex/thorchain-code-reviewer.md`
- `paperclips/projects/thorchain/roles-codex/thorchain-swift-engineer.md`
- `paperclips/projects/thorchain/roles-codex/thorchain-qa-engineer.md`

All five crafts are project-local, slim UAA roles composed from the existing
capability profiles. This prevents generic Python/release-cut/legacy phase text
from contradicting the ThorChain workflow while preserving the current profile
fragments as the reusable capability layer.

### Existing UAA files

- `paperclips/scripts/bootstrap-project.sh`
- `paperclips/scripts/rollback.sh`
- `paperclips/scripts/smoke-test.sh`
- `paperclips/scripts/lib/_smoke_probes.sh`
- the narrow manifest/bootstrap/rollback/smoke tests under `paperclips/tests/`

Implementation may add one focused ThorChain assembly test module. It must not
refactor unrelated projects or rewrite the UAA framework.

### Required UAA behavior changes

1. Validate optional `paperclip_role`, `paperclip_icon`, and `workflow_role`.
2. Create a new company with both the manifest display name and exact
   `project.issue_prefix`; fail if `THOR` is already allocated.
3. Use explicit role/icon for live hire payloads; preserve current profile
   fallback for existing assemblies.
4. Select canary CTO and handoff source by `workflow_role=inner_orchestrator`.
5. Probe phase responsibility by workflow role instead of capability profile.
6. Update handoff probes to require POST-before-PATCH, one verification, STOP.
7. Record every disposable smoke issue ID and support exact cleanup on exit.
8. Journal a company only when this run created it; journal newly created
   host-local files, managed workspace directories, and watchdog changes.
9. Rollback only exact journaled IDs/paths. A non-empty workspace with unknown
   files is quarantined, never recursively deleted.
10. Resolve `gimle_skills_root`, `vultisig_repo_root`, and exact reference roots
   only from host-local paths; reject unresolved or nonexistent load-bearing
   roots during live preflight.

## 12. Transaction and Rollout Plan

### Stage A — immutable preflight

1. Confirm Palace implementation is merged to `develop` and the exact commit is
   checked out for build/deploy.
2. Confirm GitHub account `ant013`, private-repo scope, and target repo absence.
3. Run one no-write local Codex CLI probe with explicit
   `--model gpt-5.6-sol` and `xhigh` reasoning; record version, model, exit code,
   and a content-free acknowledgement. Abort before Paperclip mutation if the
   model is rejected.
4. Confirm Paperclip is stopped, has no stale `postmaster.pid`, and port 3100 is
   free; then start only installed version 2026.618.0.
5. Verify loopback health/version and resolve live old company, agent, issue,
   project, project-workspace, and physical-path inventory.
6. Inventory product routines, monitors, execution workspaces, runtime services,
   environment leases, and active runs; classify every row by exact old project
   ID before any cleanup decision.
7. Verify Board-authorized create/delete access without printing credentials;
   company-scoped or expired credentials block the rollout.
8. Verify issue prefix `THOR` is free.
9. Abort on any company/path identity mismatch or any workspace path outside
   `/Users/ant013/Data/AI/paperclip/workspace/<exact-name>`.

### Stage B — preservation checkpoint A

1. Run `db:backup` with explicit config/data/output paths.
2. Run full portable export for the old company with
   `company,agents,projects,issues,tasks,skills`.
3. Record SHA-256, size, timestamp, source runtime version, object counts, and
   exact old IDs in a mode-600 transaction manifest.
4. Create backup/export roots with mode 700 and backup, export, and transaction
   files with mode 600. Final reports contain paths/digests, never database,
   token, secret, or adapter environment contents.
5. Run `gzip -t` on the SQL backup and portable-import `--dry-run` against the
   export.
6. Copy the 194 run logs and five materialized bundles into the same immutable
   preservation manifest by path, count, and digest; do not remove originals.

No mutation follows if either backup or export verification fails.

### Stage C — repository and assembly

1. Before translation, create and checksum the external Russian source-doc
   archive defined in section 9 and verify that every source document is
   represented exactly once.
2. Translate and stage the approved English documentation allowlist.
3. Initialize `/Users/ant013/Data/AI/thorchain` on `main`, create the private
   repository, push the initial commit, and verify visibility/default branch.
4. Index the exact local repository with codebase-memory and record the returned
   project slug/freshness in host-local bindings.
5. Build and validate all five ThorChain bundles from the merged Palace commit.
6. Create the ThorChain company with prefix `THOR`; bootstrap five agents in
   topological order; record every returned UUID.
7. Create the planned Paperclip project and primary local workspace bound to the
   new repository.
8. Keep all heartbeats disabled/wake-on-demand, set
   `maxConcurrentRuns=1`, and create no roadmap issue.

### Stage D — live acceptance

1. Verify company, project, workspace, five role identities, `reportsTo`,
   `codex_local`, model, effort, and managed-bundle SHA.
2. Run real runtime role-boundary probes for all five agents.
3. Run one disposable reviewer probe that launches the three bounded parallel
   review workers and records their model identity without changing files.
4. Run one disposable CTO-to-reviewer handoff issue through the real runtime.
5. Capture comments, assignee/status transitions, model identity, and exit
   result; close and delete only the exact smoke issue IDs.
6. Verify zero open ThorChain issues and zero roadmap-walker issues.

### Stage E — preservation checkpoint B

After ThorChain acceptance and before old-product cleanup, create a second full
SQL backup and checksum manifest. Checkpoint B is the authoritative rollback
point because it includes the new repository bindings, company, agents,
project, and workspace while retaining all old state.

### Stage F — old product retirement

1. Snapshot old agent statuses, then pause all five old agents and keep their
   heartbeats disabled.
2. Disable every old-project routine, monitor, and watchdog found in preflight.
   Product-specific rows are removed only after their IDs and definitions are
   present in checkpoint B/export evidence.
3. Through Paperclip APIs, release or close active runs, runtime services,
   environment leases, and execution workspaces associated with the three old
   projects. Abort if any row remains active or cannot be attributed exactly.
4. Verify a quiescence barrier: zero active old runs, leases, runtime services,
   monitors, or execution workspaces capable of waking an old issue.
5. Move the three exact Paperclip-managed checkout directories to
   `/Users/ant013/Data/AI/paperclip/backups/unstoppable-retirement-<UTC>/workspaces/`.
   Record original/archive paths and Git HEAD/status. Do not use recursive
   deletion.
6. Delete old issues child-first by exact UUID using `issue delete --yes`.
7. Delete each old project-workspace record by exact project/workspace UUID.
8. Delete the three old projects by exact UUID using `project delete --yes`.
9. Delete only the exact old-product routines and monitors already captured in
   the transaction manifest; leave unrelated company/agent records untouched.
10. Verify the old company and five paused agents still exist, with their run logs and
   materialized bundles unchanged.
11. Verify no old issue/project/project-workspace remains, active workspace paths
   are absent, and the archived directories are readable.
12. Verify the new ThorChain company/project/team remains unchanged and idle.

The archived checkout directories are retained. Their later physical deletion
requires a separate explicit user request.

## 13. Failure and Rollback Matrix

| Failure point | Stop condition | Rollback |
|---|---|---|
| Before checkpoint A | Health/version/identity mismatch | Stop Paperclip; no mutation |
| Backup/export verification | Digest, count, gzip, or dry-run failure | Stop; preserve current state |
| Repository creation | Wrong owner, visibility, branch, or content | Stop; correct the private repo without deleting it |
| UAA bootstrap before acceptance | Wrong agent/model/role/path or failed bundle deploy | Replay exact UAA journal; remove only the newly created ThorChain Paperclip company and managed local files; preserve private repo |
| Live smoke | Any role-boundary or handoff failure | Delete exact disposable smoke issues; keep ThorChain company paused for diagnosis or replay UAA rollback before Stage E |
| Old workspace archive move | Any target mismatch or move failure | Move already archived exact directories back; restore old agent/routine states from the transaction snapshot; do not touch DB |
| Old issue/project cleanup after checkpoint B | Any API failure or post-count mismatch | Stop Paperclip; restore checkpoint-B SQL using the pinned local database recovery procedure; move archived workspaces back to recorded originals; verify both companies |
| Post-cleanup verification | Old company/agents missing or ThorChain drift | Same checkpoint-B restore; task is failed until full inventory matches |

Neither rollback path deletes `ant013/ThorChainKit.Swift` or any external source
repository. Company deletion is allowed only for the newly created ThorChain
company during a failed pre-acceptance bootstrap and only by its recorded UUID.

## 14. Test Plan

### 14.1 Static and unit tests

- ThorChain manifest has exactly five uniquely named Codex agents and the exact
  topology/model/effort/role/icon/workflow-role table.
- Manifest contains no UUID, secret, or absolute host path.
- Builder renders five managed bundles and a complete compatibility manifest.
- Every bundle contains the current analog/Gimle approval gate and resolves the
  host-local skill/reference roots without committing their absolute values.
- Existing Trading/Gimle/UAudit builds remain byte/contract compatible where
  the new optional fields are absent.
- Bootstrap maps explicit Paperclip roles/icons and retains profile fallback.
- Bootstrap creates the new company with exact manifest prefix `THOR`, rejects
  collisions, and never changes an existing company's prefix implicitly.
- Canary and smoke select `inner_orchestrator`, not CEO.
- Workflow-role probes enforce CEO/CTO/reviewer/implementer/QA boundaries.
- Local and live model probes reject any main agent or review worker not running
  `gpt-5.6-sol`; agent runtime concurrency is exactly one.
- Handoff probe text requires POST, PATCH, one verification, and STOP.
- Smoke cleanup deletes only journaled disposable issue UUIDs.
- Rollback dry-run covers created company, agents, host files, workspace dirs,
  instructions, plugin/watchdog state, and refuses unknown/non-managed paths.
- Current Phase B/C/D/E Paperclip tests remain green.

Minimum implementation verification:

```text
python3 -m pytest paperclips/tests/test_phase_b_* \
  paperclips/tests/test_phase_c_* \
  paperclips/tests/test_phase_d_* \
  paperclips/tests/test_phase_e_trading_migration.py
bash paperclips/build.sh --project thorchain --target codex
bash paperclips/scripts/validate-manifest.sh thorchain
```

Run the repository's full relevant Paperclip test suite before PR handoff if the
narrow suite is green.

### 14.2 Repository acceptance

- `gh repo view ant013/ThorChainKit.Swift` reports private visibility and default
  branch `main`.
- Initial committed file set matches the documentation allowlist.
- No `.DS_Store`, secrets, absolute local paths in committed host bindings, or
  production package/source files are present.
- The pre-Git Russian documentation archive has a complete checksum manifest;
  deterministic `rg` over committed Markdown finds no Cyrillic text.
- Backup/export/archive directories and sensitive files satisfy the required
  700/600 permissions, and committed/report text passes a secret scan.
- Commit messages and bodies contain no `Co-authored-by:` trailer.
- English-language audit reports no untranslated normative headings in the
  repository seed; source Russian files outside Git remain untouched.

### 14.3 Live Paperclip acceptance

- Runtime version is exactly 2026.618.0 and bound to loopback.
- The exact ThorChain repository is indexed and current in codebase-memory; each
  bundle names the returned project slug and the exact local Serena boundary.
- New company prefix is `THOR`; one planned project and one primary workspace
  point to the exact local repo and `main`.
- Five live agents match the identity table and all report `gpt-5.6-sol/xhigh`.
- The three disposable CodeReviewer workers report the same model in runtime
  trace metadata and perform no writes.
- Rendered bundle SHA equals deployed bundle SHA for every agent.
- Disposable handoff follows comment -> reassignment -> one verification ->
  stop and is then deleted.
- No ThorChain roadmap issue exists.
- Old company and five paused agents remain; old issues/projects/project-workspaces
  and product wake sources are zero; three old product checkouts exist only in
  the timestamped archive.
- External source repository HEAD, remote, and working-tree fingerprints match
  the preflight inventory.

## 15. Acceptance Criteria

The task is complete only when all of the following are true:

1. Palace PR is merged to `develop` with the ThorChain assembly and UAA safety
   changes, and its required tests are green.
2. `ant013/ThorChainKit.Swift` exists as a private English-language repository
   on `main`, with no co-author trailer and no prematurely implemented product
   scaffold; the original Russian documentation corpus has a verified external
   archive.
3. The separate ThorChain Paperclip company contains exactly the five intended
   agents, one planned project, and one correct primary workspace.
4. Every agent is `codex_local`, `gpt-5.6-sol`, `xhigh`, and has the intended
   live role/topology and verified bundle; bounded review workers inherit the
   same model and the five Paperclip agents each have concurrency one.
5. Disposable runtime probes and the handoff acceptance pass; their issues are
   removed; no roadmap issue has started.
6. Fresh checkpoint A, portable export, and checkpoint B all exist with
   checksums and inventories.
7. Only old issues, projects, and project-workspace records are removed from
   Paperclip; old company/agents/logs/bundles remain.
8. Old Paperclip-managed product checkouts are recoverably archived, while all
   external repositories remain untouched.
9. A final operator report records IDs, commits, backup paths/digests, test
   output, live evidence, cleanup inventory, and rollback readiness without
   secrets.

## 16. Open Questions

None. Approval of this revision selects `THOR`, `main`, the exact five-agent
topology, English-only repository content, preservation of the old company and
agents, and recoverable archival rather than physical deletion of old checkout
directories.

## 17. Gimle Reliability Note

The analog family is verified through current-tree Serena and targeted `rg`.
Gimle trust remains RED because its index still reports stale
`paperclips/projects/unstoppable` paths absent from `origin/develop`. Those
paths and polluted commit `c62cef3e` are rejected and are not load-bearing for
this design. Current Trading/UAA evidence is the primary spine; the stale-index
defect and all fallbacks remain recorded in the durable Gimle report.
