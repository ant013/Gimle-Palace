# GIM-839 Productized Smoke And Semantic Quality Task Plan

## Branch And Gate

- Spec branch: `docs/GIM-839-productized-smoke-semantic-quality`
- Target branch: `develop`
- Spec:
  `docs/superpowers/specs/2026-05-25-GIM-839-productized-smoke-and-semantic-quality_spec.md`
- Status: rev3 spec-only branch; wait for review before implementation changes.

## Objective

Split the GIM-839 follow-up into tasks that can be assigned to Claude and
Codex/CX in parallel where safe. Rev2/rev3 adds explicit contract tasks before
parallel work so agents do not implement incompatible recipe, metadata, or
snippet boundaries.

## Suggested Issue Structure

If Paperclip supports child issues, keep one parent and four children:

- Parent: `GIM-839` follow-up: Productized runtime smoke and semantic quality.
- Child A: `GIM-839A` Productized runtime smoke recipes and runner.
- Child B: `GIM-839B` Semantic search source scoping, ranking, and snippets.
- Child C: `GIM-839C` MacBook runtime evidence and golden query validation.
- Child D: `GIM-839D` metadata/API contract lock, if the team wants a
  separate short gate before implementation.

If issue ids must be unique top-level tickets, create separate tickets with the
same titles and link them back to GIM-839.

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

### Pick Rule

1. Read this plan top-to-bottom.
2. Skip slices already marked done in the parent issue status comment.
3. Find the first not-done slice whose dependencies are satisfied.
4. If the slice is blocking, create one child issue for the required CTO and
   block the CEO parent until the child closes.
5. If the slice is non-blocking, assign it to the correct free CTO, then scan
   forward for one compatible non-blocking slice for the second free CTO.
6. Do not create child issues for a CTO that already has an active child.
7. Do not create downstream validation children until their dependency slices
   are closed.
8. If the dependency graph or ownership is ambiguous, comment on the CEO parent
   and wait for operator input instead of guessing.

### Completion Rule

When a child closes:

1. CEO/walker reads the child close summary and merged branch/commit/PR.
2. CEO/walker marks the matching slice done in the parent issue status comment.
3. CEO/walker records any follow-up blockers reported by the child.
4. CEO/walker re-runs the pick rule.
5. When all slices are done, CEO/walker posts the final rollup and closes the
   parent.

### Branching Strategy

Create a small contract-lock branch first. Do not start broad implementation
branches until it lands.

- Contract lock branch:
  `feature/GIM-839-contract-lock`
- Claude runtime branch after contract lock:
  `feature/GIM-839A-runtime-smoke-walker`
- Claude semantic branch after contract lock:
  `feature/GIM-839B-semantic-quality-walker`
- Codex/CX native validation branch if split from runtime:
  `feature/GIM-839C-xcode-scip-validation`

If the team chooses one PR per slice, each child may create a short-lived branch
from the relevant walker branch and merge back into that walker branch before
the walker branch merges to `develop`. If the team chooses one PR per walker,
each child commits directly to its walker branch. Do not mix runtime and
semantic edits in one child unless the spec dependency explicitly requires it.

### Blocking Slices

Blocking slices stop the CEO from launching dependent work:

- Contract lock: A0 and B0. No A1/A3/A4/A5 or B1-B6 can start before this is
  closed.
- Runtime runner readiness: A3 must close before C1/C2 runtime evidence can
  start.
- Native build readiness: A5 and A6 must close before C2 app runtime evidence.
- Semantic metadata readiness: B1 and B2 must close before C2 evidence can claim
  `source_scope` and bounded coverage.
- Semantic product readiness: B3, B4, B5, and B6 must close before C3.

### Non-Blocking Parallel Slices

After contract lock closes, CEO may run these in parallel when CTOs are free:

- Runtime side:
  - A1 recipe fixtures;
  - A2 MCP caller;
  - A6 preflight;
  - A5 Xcode workspace adapter, preferably Codex/CX.
- Semantic side:
  - B1 source scope classification;
  - B2 embedding candidate policy;
  - B5 snippet provider.

CEO should prefer assigning Codex/CX to native/Xcode/SCIP slices and Claude to
Python/MCP/search/test slices. If Codex/CX is not free, CEO assigns only Claude
work and does not create a second child just to fill the queue.

### Initial CEO Schedule

1. Spawn child `GIM-839D Contract lock: recipe/binding + symbol/search API`.
   - Owner: Claude CTO.
   - Includes A0 and B0.
   - Blocking: yes.
2. After contract lock closes, if both CTOs are free:
   - spawn runtime child for A1/A2/A6 to Claude CTO;
   - spawn native child for A5 to Codex/CX CTO.
3. When A1/A2/A6 close, spawn A3 runtime runner skeleton to Claude CTO.
4. When A0/A1 close and Codex/CX is free, spawn A4 Swift Package adapter or keep
   it with Claude if Codex/CX is occupied.
5. In parallel on the semantic side after B0:
   - spawn B1/B2 to Claude CTO;
   - after B1 closes, spawn B3;
   - after B3 closes, spawn B4;
   - after B0 closes and metadata contract is stable, spawn B5.
6. After B3/B4/B5 close, spawn B6 golden matrix runner.
7. After A3/A4/A5/A6 and B1/B2 close, spawn C2 runtime evidence.
8. After B3/B4/B5/B6 and C2 close, spawn C3 semantic evidence and final
   closure recommendation.

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
- close requirement: post commit/PR, tests run, and any unresolved blocker.

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

## Parallel Execution Plan

Contract phase after spec approval:

- Claude: A0 and B0.
- Codex/CX: review Xcode/SCIP constraints and provide A5 notes.

Safe parallel start after A0/B0:

- Claude: A1, A2, A6, B1, B2, B5.
- Codex/CX: A5 implementation or review.

Next wave:

- Claude: A3 after A0/A2; B3 after B0/B1.
- Claude or Codex/CX: A4 after A0/A1.

Final wave:

- Claude: B4 after B3, B6 after B3/B4/B5.
- Operator/Codex/CX: C1 after A3/A4/A5/A6; C2 after A3/A4/A5/A6 and B1/B2.
- Claude + operator: C3 after B3/B4/B5/B6/C2.

Sequential fallback if only Claude is available:

1. A0 recipe/runtime binding contract.
2. B0 symbol metadata/search API contract.
3. A2 MCP caller.
4. A6 preflight.
5. A1 recipe fixtures.
6. A3 runner skeleton.
7. A4 Swift Package adapter.
8. A5 Xcode workspace adapter and UW recipe.
9. B1 source scope.
10. B2 embedding candidate policy.
11. B3 semantic filters.
12. B5 snippet provider.
13. B4 hybrid ranking.
14. A7 runbook.
15. B6 golden query matrix.
16. C1-C3 runtime evidence on the MacBook host.

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

## Review Checklist Before Implementation

- Confirm whether tasks remain under GIM-839 or become new issue ids.
- Confirm four-of-five golden matrix pass, including one non-app row, is
  sufficient for v1 closure.
- Confirm full unbounded embeddings move to a separate post-smoke validation
  issue.
