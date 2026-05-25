# GIM-839 Productized Smoke And Semantic Quality Task Plan

## Branch And Gate

- Spec branch: `docs/GIM-839-productized-smoke-semantic-quality`
- Target branch: `develop`
- Spec:
  `docs/superpowers/specs/2026-05-25-GIM-839-productized-smoke-and-semantic-quality_spec.md`
- Status: rev4 routing-ready branch; ready for CEO walker assignment.

## Objective

Split the GIM-839 follow-up into tasks that can be assigned to Claude and
Codex/CX in parallel where safe. Rev2-rev4 adds explicit contract tasks before
parallel work so agents do not implement incompatible recipe, metadata, or
snippet boundaries.

## Plan Type

This is an orchestration and routing plan, not a per-slice TDD implementation
plan. Each child issue created by the CEO/walker must still produce its own
Paperclip phase plan with failing-test -> implementation -> verification steps
before code changes. This file is the dependency, ownership, and scheduling
contract for those child plans.

## Canonical Decomposition

The canonical unit of work is a slice row in the DAG table below. Do not create
track-sized children such as "all Track A" or "all Track B"; those are too broad
for review and make QA evidence ambiguous.

Paperclip may assign real issue numbers. The stable slice ids are:

- `D0`: contract lock, includes A0 and B0.
- `A1` through `A7`: runtime smoke productization.
- `B1` through `B6`: semantic search quality.
- `C1` through `C3`: runtime and product evidence.

Titles should include the slice id, for example
`GIM-839 A5: Xcode workspace adapter and UW recipe`.

## CEO Walker Execution Protocol

Use the Trading project's roadmap-walker pattern with one CEO parent issue and
bounded child issue creation. The CEO/walker is a dispatcher, not an implementer.

### Parent Issue

- Title: `GIM-839 Productized smoke + semantic quality CEO walker`.
- Assignee: CEO/roadmap walker.
- Inputs:
  - this plan;
  - the companion spec;
  - current child issue status;
  - CTO availability.
- Output:
  - one child issue at a time for blocking work;
  - at most one active child per available CTO for non-blocking work;
  - updated slice status comments when children close.

The parent issue status comment is the single source of truth for slice state.
Use this structured block and update it in place:

```markdown
<!-- GIM-839-WALKER-STATUS -->
| Slice | State | Owner | Issue | Branch | Merged SHA | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| D0 | pending | Claude CTO | - | - | - | contract lock |
| A1 | pending | Claude CTO | - | - | - | blocked by D0 |
| A2 | pending | Claude CTO | - | - | - | can run after spec approval |
| A3 | pending | Claude CTO | - | - | - | blocked by D0,A2 |
| A4 | pending | Claude CTO | - | - | - | blocked by D0,A1 |
| A5 | pending | Codex/CX CTO | - | - | - | blocked by D0,A1 |
| A6 | pending | Claude CTO | - | - | - | blocked by D0 |
| A7 | pending | Claude CTO | - | - | - | blocked by A3,A5,A6 |
| B1 | pending | Claude CTO | - | - | - | blocked by D0 |
| B2 | pending | Claude CTO | - | - | - | blocked by D0 |
| B3 | pending | Claude CTO | - | - | - | blocked by D0,B1 |
| B4 | pending | Claude CTO | - | - | - | blocked by D0,B3 |
| B5 | pending | Claude CTO | - | - | - | blocked by D0 |
| B6 | pending | Claude CTO | - | - | - | blocked by B3,B4,B5 |
| C1 | pending | Operator/Codex QA | - | - | - | blocked by A3,A4,A5,A6 |
| C2 | pending | Codex/CX QA | - | - | - | blocked by A3,A4,A5,A6,B1,B2 |
| C3 | pending | Claude QA | - | - | - | blocked by B3,B4,B5,B6,C2 |
<!-- /GIM-839-WALKER-STATUS -->
```

Allowed states: `pending`, `active`, `blocked`, `merged`, `skipped`.
Only `merged` counts as done for dependency checks.

### Pick Rule

1. Read this plan top-to-bottom.
2. Skip slices already marked done in the parent issue status comment.
3. Find the first not-done slice whose dependencies are satisfied.
4. If the slice is blocking, create one child issue for the required CTO and do
   not create work that depends on it until it closes. The CEO may still create
   independent ready slices whose dependencies are already satisfied, such as
   A2 while D0 is active.
5. If the slice is non-blocking, assign it to the correct free CTO, then scan
   forward for one compatible non-blocking slice for the second free CTO.
6. Do not create child issues for a CTO that already has an active child.
7. Do not create downstream validation children until their dependency slices
   are closed.
8. If the preferred CTO is unavailable for two consecutive pick cycles and the
   slice declares a fallback owner, assign the fallback owner instead of waiting
   indefinitely.
9. If the dependency graph or ownership is ambiguous, comment on the CEO parent,
   PATCH the issue assignee/status so Paperclip wakes the operator-facing agent,
   and wait for operator input instead of guessing.

A CTO is "free" only when there is no `active` child assigned to that CTO in the
structured status block and no known active Paperclip run for that CTO on this
GIM-839 parent. A child is active from creation until it reaches `merged`,
`skipped`, or a reopened failure state.

### Completion Rule

When a child closes:

1. CEO/walker reads the child close summary and merged branch/commit/PR.
2. CEO/walker verifies the child landed on `develop` with a merge/squash SHA.
3. If no merged-to-`develop` SHA exists, CEO/walker does not mark the slice
   done. It reopens, respawns, or escalates the child based on the close reason.
4. CEO/walker marks the matching slice `merged` in the parent status block only
   after the merge SHA is known.
5. CEO/walker records any follow-up blockers reported by the child.
6. CEO/walker re-runs the pick rule.
7. When all slices are done, CEO/walker posts the final rollup and closes the
   parent.

### Branching Strategy

Use one PR per slice, branched from current `develop`, squash-merged back to
`develop`. Do not aggregate multiple slices into one walker PR. This keeps CI,
code review, and QA evidence attached to the slice boundary.

Branch names:

- `feature/GIM-839-D0-contract-lock`
- `feature/GIM-839-A1-recipe-fixtures`
- `feature/GIM-839-A2-mcp-caller`
- `feature/GIM-839-A3-runtime-runner`
- `feature/GIM-839-A4-swiftpm-adapter`
- `feature/GIM-839-A5-xcode-uw-recipe`
- `feature/GIM-839-A6-runtime-preflight`
- `feature/GIM-839-A7-runtime-runbook`
- `feature/GIM-839-B1-source-scope`
- `feature/GIM-839-B2-embedding-policy`
- `feature/GIM-839-B3-semantic-filters`
- `feature/GIM-839-B4-hybrid-ranking`
- `feature/GIM-839-B5-snippet-provider`
- `feature/GIM-839-B6-golden-matrix`
- `feature/GIM-839-C1-macbook-prep`
- `feature/GIM-839-C2-runtime-evidence`
- `feature/GIM-839-C3-semantic-evidence`

Each branch has one writer. If ownership changes, the current child must push,
stop, and hand off explicitly in the issue before another agent writes to that
branch.

### Normative DAG

This table is the only normative dependency and scheduling source. If text in
the per-slice sections below conflicts with this table, fix the per-slice text
instead of overriding this table.

| Slice | Depends on | Owner | Fallback | Blocking? | File scope | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| D0 | spec approval | Claude CTO | none | yes | docs, tests/fixtures for contracts | Combines A0+B0 contract lock. |
| A1 | D0 | Claude CTO | none | no | runtime recipe fixtures/tests | Recipe fixtures. |
| A2 | spec approval | Claude CTO | none | no | MCP caller helper/tests | May run in parallel with D0. |
| A3 | D0, A2 | Claude CTO | none | yes for C1/C2 | runtime runner/tests | Runner skeleton. |
| A4 | D0, A1 | Claude CTO | Codex/CX CTO review | yes for C2 | SwiftPM adapter/tests | Kit path. |
| A5 | D0, A1 | Codex/CX CTO | Claude CTO | yes for A7/C2 | Xcode adapter/UW recipe/tests | Native path. |
| A6 | D0 | Claude CTO | Codex/CX CTO review | yes for A7/C2 | preflight/tests | Docker/Neo4j/Qodo/Xcode. |
| A7 | A3, A5, A6 | Claude CTO | none | no | runtime runbook | Operator docs. |
| B1 | D0 | Claude CTO | none | yes for B3/C2 | symbol extraction metadata/tests | `source_scope`. |
| B2 | D0 | Claude CTO | none | yes for C2 | embedding policy/tests | Bounded coverage. |
| B3 | D0, B1 | Claude CTO | none | yes for B4/C3 | semantic search filters/tests | Search defaults. |
| B4 | D0, B3 | Claude CTO | none | yes for B6/C3 | ranking/tests | Hybrid scoring. |
| B5 | D0 | Claude CTO | none | yes for B6/C3 | snippet provider/tests | Path safety. |
| B6 | B3, B4, B5 | Claude CTO | none | yes for C3 | golden matrix/runner/tests | Product eval. |
| C1 | A3, A4, A5, A6 | Operator/Codex QA | Claude QA | no | MacBook binding/evidence | Prep only. |
| C2 | A3, A4, A5, A6, B1, B2 | Codex/CX QA | Claude QA | yes for C3 | runtime evidence | App+kit cascade. |
| C3 | B3, B4, B5, B6, C2 | Claude QA | Operator support | yes | semantic evidence | Final product gate. |

### File-Overlap Matrix

CEO uses this matrix to decide whether two ready non-blocking slices are
compatible for parallel assignment. Compatible means expected write scopes are
disjoint or one slice is docs/evidence-only.

| Slice group | Expected write scope | Parallel-safe with | Not parallel-safe with |
| --- | --- | --- | --- |
| A1 recipes | recipe fixtures and recipe validation tests | A2, A6, B1/B2/B5 after D0 | A3/A4/A5 until schema stabilizes |
| A2 MCP caller | MCP caller helper and tests | D0, A1, A6, B-slices | A3 if both edit runner-call boundary simultaneously |
| A3 runner | runtime runner and script tests | B1/B2/B5 if contract stable | A2 until caller interface is settled |
| A4 SwiftPM adapter | SwiftPM adapter and tests | B-slices | A1 if recipe fixture schema still moving |
| A5 Xcode adapter | Xcode adapter, UW recipe, native tests | B-slices | A1 if recipe fixture schema still moving |
| A6 preflight | preflight checks and tests | A1, A2, B-slices | A3 if report schema is moving |
| B1/B2/B3/B4/B5 | semantic extraction/search/ranking/snippet code and tests | runtime A-slices after D0 | each other unless explicitly bundled under same Claude child |
| B6 | golden matrix and runner | A7/C1 docs/evidence | B3/B4/B5 until APIs settle |
| C1/C2/C3 | evidence reports and runtime logs | docs-only work | implementation slices they validate |

Because most B-slices touch adjacent semantic surfaces, CEO should keep B1-B6
on the same Claude CTO lane unless a later child plan proves disjoint files.
Do not assign B1 to one CTO and B2/B3/B4/B5 to another by default.

### Child Issue Template

Each CEO-created child issue should include:

- parent id: CEO/walker issue id;
- slice ids covered, for example `A5` or `B3+B4`;
- owner CTO;
- branch name;
- spec path:
  `docs/superpowers/specs/2026-05-25-GIM-839-productized-smoke-and-semantic-quality_spec.md`;
- plan path:
  `docs/superpowers/plans/2026-05-25-GIM-839-productized-smoke-and-semantic-quality.md`;
- exact dependencies that must already be closed;
- acceptance criteria copied from the slice;
- verification commands or runtime evidence expected;
- close requirement: post merged-to-`develop` commit/PR, tests run, and any
  unresolved blocker.

## Track A: Productized Runtime Smoke

### A0. Lock Recipe And Runtime Binding Contract

- Owner: Claude
- Parallelizable: no; this gates A1, A3, A4, and A5. A2 can start after spec
  approval because it only depends on the current MCP contract.
- Dependencies: spec approval
- Deliverables:
  - versioned recipe schema without machine-local absolute paths;
  - local runtime binding schema for `repo_path`, mount, caches, compose
    override, and MCP URL;
  - required/optional runtime binding field table;
  - invariant that `repo_path` resolves inside `parent_mount`;
  - typed adapter contract; raw shell command recipes explicitly out of scope.
- Acceptance:
  - tests reject `repo_path` inside versioned recipes;
  - tests reject `repo_path` outside `parent_mount`;
  - tests accept repo path only through runtime binding;
  - `unstoppable-wallet-ios` can be represented without hardcoding a home
    directory.

### A1. Define Recipe Fixtures

- Owner: Claude
- Parallelizable: after A0
- Dependencies: A0
- Deliverables:
  - fixture for one Swift Package repo;
  - fixture for `unstoppable-wallet-ios`;
  - validation errors for missing build target, invalid roots, unsafe paths, and
    unsupported build systems.
- Acceptance:
  - fixture tests prove invalid recipes fail before command execution.

### A2. Implement MCP Streamable HTTP Caller

- Owner: Claude
- Parallelizable: yes after spec approval
- Dependencies: current MCP contract
- Deliverables:
  - helper for `tools/list` and `call_tool`;
  - support for `palace.memory.register_project`;
  - extractor call support with structured status.
- Acceptance:
  - tests assert tool name and arguments include both `name` and `slug`;
  - errors preserve MCP response body enough for debugging.

### A3. Implement Runtime Smoke Runner Skeleton

- Owner: Claude
- Parallelizable: starts after A0/A2
- Dependencies: A0, A2
- Deliverables:
  - stage runner for `preflight`, `prepare`, `build_scip`,
    `register_project`, `run_extractors`, and `report`;
  - separate `semantic_probe` mode, not part of runtime smoke pass/fail;
  - JSON report writer;
  - readable operator log output.
- Acceptance:
  - stage order is deterministic;
  - failures are structured per stage;
  - dry-run mode validates recipe and binding without mutating runtime state.

### A4. Implement Swift Package Adapter

- Owner: Claude, Codex/CX optional reviewer
- Parallelizable: yes after A0/A1
- Dependencies: A0, A1
- Deliverables:
  - SwiftPM package build/index command adapter;
  - support for existing `scip/index.scip` reuse when present;
  - locked package-resolution behavior by default.
- Acceptance:
  - adapter works for one HorizontalSystems Swift kit recipe;
  - tests cover command construction without running Xcode or network access.

### A5. Implement Xcode Workspace Adapter And UW Recipe

- Owner: Codex/CX preferred, Claude fallback
- Parallelizable: yes after A0/A1
- Dependencies: A0, A1
- Deliverables:
  - Xcode workspace adapter;
  - `unstoppable-wallet-ios` recipe;
  - smoke-safe `Config.xcconfig` prepare step from template;
  - host-aware simulator architecture: `auto|arm64|x86_64`;
  - isolated repo-local DerivedData path;
  - locked package-resolution mode and opt-in package resolution mode;
  - workspace `absolute:` reference detection or explicit mapping.
- Acceptance:
  - generated command uses `-workspace Wallet.xcworkspace`, scheme
    `Development`, generic iOS Simulator destination, resolved architecture, and
    signing disabled;
  - it does not use direct `-project Unstoppable/Unstoppable.xcodeproj`;
  - prepare step is idempotent and does not overwrite an existing config;
  - no-download preflight fails fast instead of fetching packages.

### A6. Add Docker, Neo4j, Qodo, And Xcode Preflight

- Owner: Claude
- Parallelizable: yes after A0
- Dependencies: A0
- Deliverables:
  - checks for Docker availability, image presence, Neo4j reachability, MCP
    `tools/list`, mounted repo root, model cache path, local-only model mode,
    embedding limits, `xcode-select`, `xcodebuild -version`, license readiness,
    iOS SDK/runtime, host architecture, SwiftPM cache, and workspace absolute
    references.
- Acceptance:
  - missing large assets produce actionable preflight failures;
  - preflight does not download model files, Docker images, or SwiftPM packages
    by default.

### A7. Runtime Runbook

- Owner: Claude
- Parallelizable: after A3/A5/A6 shape is stable
- Dependencies: A3, A5, A6
- Deliverables:
  - `docs/runbooks/productized-runtime-smoke.md`;
  - known-good MacBook command examples;
  - troubleshooting for workspace/project confusion, absolute workspace refs,
    missing config, SwiftPM package resolution, Xcode host setup, Docker
    resources, and bounded embeddings.
- Acceptance:
  - a new operator can repeat the smoke without reading chat history.

## Track B: Semantic Search Quality

### B0. Lock Symbol Metadata And Search API Contract

- Owner: Claude
- Parallelizable: no; this gates B1/B2/B3/B4/B5
- Dependencies: spec approval
- Deliverables:
  - persisted `source_scope` contract on `:Symbol`;
  - source metadata contract: file path, optional line span, commit/revision
    evidence, project root identity;
  - exact `semantic_search` request precedence:
    `source_scopes` overrides `include_dependencies`, `include_generated`, and
    `include_sdk`;
  - migration note that GIM-837 compatibility is signature-compatible, not
    behavior-identical;
  - cross-project tie-break and no-dedup behavior.
- Acceptance:
  - unit tests can construct fixture symbols with all required metadata;
  - legacy symbols without `source_scope` are classified from recipe roots when
    recipe metadata exists;
  - unclassifiable legacy symbols are treated as fallback/warning, not normal
    first-party results.

### B1. Source Scope Classification

- Owner: Claude
- Parallelizable: after B0
- Dependencies: B0
- Deliverables:
  - classify symbols as `project`, `workspace_package`, `dependency`,
    `generated`, `derived`, or `sdk`;
  - use recipe roots and documented precedence;
  - query-time fallback only for legacy nodes.
- Acceptance:
  - tests cover app source, workspace package, `.build`, DerivedData, SDK,
    generated roots, overlapping roots, and dependency paths;
  - every semantic result exposes `source_scope`.

### B2. Embedding Candidate Policy

- Owner: Claude
- Parallelizable: yes after B0
- Dependencies: B0
- Deliverables:
  - deterministic bounded candidate ordering;
  - first-party definitions before workspace package before dependency;
  - generated/derived/SDK only when explicitly enabled;
  - coverage metadata in reports/search responses.
- Acceptance:
  - bounded app run no longer spends early embedding slots on SDK/UI accessor
    noise when first-party symbols are available;
  - tests use fixtures and fake backends.

### B3. Semantic Search Filters

- Owner: Claude
- Parallelizable: starts after B0/B1
- Dependencies: B0, B1
- Deliverables:
  - `source_scopes`, `include_dependencies`, `include_generated`, and
    `include_sdk` filtering;
  - default first-party scope filtering;
  - response fields for `source_scope`, active filters, and coverage.
- Acceptance:
  - default query excludes dependency/generated/derived/SDK scopes;
  - opt-in search can include dependencies for cases such as hex helpers in
    HsToolKit or kits;
  - cross-project results remain scoped by project and group id.

### B4. Hybrid Ranking

- Owner: Claude
- Parallelizable: starts after B0/B3
- Dependencies: B0, B3
- Deliverables:
  - fixed v1 ranking formula;
  - vector, lexical, source scope, symbol kind, path/module, and penalty
    components;
  - explicit penalty table and cap;
  - source scope affects continuous score in one place only;
  - deterministic tie-breakers.
- Acceptance:
  - ranking weights are hardcoded for v1 and documented;
  - unit tests cover score composition and tie-breakers;
  - golden queries improve top-5 first-party relevance versus pure vector score.

### B5. Snippet Provider

- Owner: Claude
- Parallelizable: starts after B0
- Dependencies: B0
- Deliverables:
  - local file snippet hydration for resolvable source hits;
  - safe path resolution through registered project root; `parent_mount` is only
    used to locate roots, not as a broad snippet read boundary;
  - commit/revision mismatch warning;
  - snippet window and truncation contract;
  - codebase-memory fallback.
- Acceptance:
  - `include_context=true` returns `context.available=true` for a local source
    hit in a fixture test;
  - at least one non-app first-party hit is covered in golden validation;
  - path traversal is rejected;
  - persisted absolute paths, `..` paths, outside-root paths, and symlink
    escapes are rejected;
  - stale checkout returns `stale_source`.

### B6. Golden Query Matrix

- Owner: Claude QA, operator support for live data
- Parallelizable: after B3/B4/B5, before final closure
- Dependencies: B3, B4, B5, runtime indexed data
- Deliverables:
  - machine-readable golden matrix with exact query text;
  - path and schema for the matrix file;
  - expected qualified-name/file/module patterns;
  - disallowed top-5 patterns;
  - runner that prints per-row pass/fail and top-5 evidence;
  - pass/fail evidence from live MacBook smoke.
- Acceptance:
  - timer/scheduler, balance refresh, WalletConnect signing, bitcoin signing,
    and Data/bytes-to-hex rows have recorded top-5 results;
  - at least four of five rows pass, including at least one non-app row;
  - failures include linked follow-up evidence and do not silently close the
    parent when fewer than four rows pass.

## Track C: Runtime Evidence

### C1. Prepare Clean MacBook Workspace

- Owner: operator or Codex/CX QA
- Parallelizable: after A7 draft
- Dependencies: A6 runbook checks
- Deliverables:
  - clean repo set under a known HorizontalSystems root;
  - runtime binding file;
  - Docker images and Qodo cache confirmed;
  - no dirty repo state required for the smoke.
- Acceptance:
  - preflight report is attached to the issue.

### C2. Run App And Kit Cascade

- Owner: Codex/CX QA preferred, Claude fallback with operator access
- Parallelizable: after A3/A4/A5/A6 and B1/B2
- Dependencies: A3, A4, A5, A6, B1, B2
- Deliverables:
  - runtime report for `uw-ios-app`;
  - runtime report for at least one Swift kit;
  - Neo4j count summary including `source_scope` values;
  - bounded embedding coverage summary.
- Acceptance:
  - app build/SCIP/cascade path succeeds or fails with structured blocker;
  - kit build/SCIP/cascade path succeeds or fails with structured blocker;
  - report includes symbol and embedding counts.

### C3. Run Semantic Probe And Analyze Results

- Owner: Claude + operator
- Parallelizable: after B3/B4/B5/B6 and C2
- Dependencies: B3, B4, B5, B6, C2
- Deliverables:
  - golden query result report;
  - single-project and cross-project semantic probe evidence;
  - ranking/snippet pass-fail summary;
  - final closure recommendation.
- Acceptance:
  - top-5 results and required snippets are recorded for each golden query;
  - at least four of five rows pass, including at least one non-app row;
  - any remaining row has a linked follow-up with evidence.

## Scheduling Source Of Truth

The Normative DAG is the scheduling source of truth. The per-slice sections
above provide detail and acceptance criteria; they do not override the DAG. CEO
must not use a separate hard-coded schedule. If only Claude is available, CEO
still follows the same DAG and simply assigns every ready slice with a Claude
fallback to the Claude lane.

## Assignment Summary

- Claude team:
  - primary owner for A0, A1, A2, A3, A4, A6, A7;
  - primary owner for all Track B tasks;
  - prepares docs, tests, and runbooks.
- Codex/CX team:
  - preferred owner for A5 and C2;
  - reviewer for native Swift/Xcode/SCIP command decisions;
  - helps with host-specific runtime blockers.
- Operator:
  - provides MacBook host access, model/image availability, and final smoke
    execution approval.

## Closed Routing Decisions

- Keep GIM-839 as the parent. Paperclip may assign real child issue numbers,
  but child titles must include stable slice ids such as `D0`, `A5`, or `B4`.
- Four-of-five golden matrix pass, including one non-app row, is sufficient for
  v1 closure.
- Full unbounded embeddings are a separate post-smoke validation issue, not a
  blocker for this bounded productized smoke.
