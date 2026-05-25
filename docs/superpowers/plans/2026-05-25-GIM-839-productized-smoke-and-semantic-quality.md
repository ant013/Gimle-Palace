# GIM-839 Productized Smoke And Semantic Quality Task Plan

## Branch And Gate

- Spec branch: `docs/GIM-839-productized-smoke-semantic-quality`
- Target branch: `develop`
- Spec:
  `docs/superpowers/specs/2026-05-25-GIM-839-productized-smoke-and-semantic-quality_spec.md`
- Status: spec-only branch; wait for review before implementation changes.

## Objective

Split the GIM-839 follow-up into tasks that can be assigned to Claude and
Codex/CX in parallel where safe. If Codex/CX is not available, Claude can take
the tasks sequentially using the dependency order below.

## Suggested Issue Structure

If Paperclip supports child issues, keep one parent and three children:

- Parent: `GIM-839` follow-up: Productized runtime smoke and semantic quality.
- Child A: `GIM-839A` Productized runtime smoke recipes and runner.
- Child B: `GIM-839B` Semantic search source scoping, ranking, and snippets.
- Child C: `GIM-839C` MacBook runtime evidence and golden query validation.

If issue ids must be unique top-level tickets, create three new tickets with the
same titles and link them back to GIM-839.

## Track A: Productized Runtime Smoke

### A1. Define Project Recipe Contract

- Owner: Claude
- Parallelizable: yes
- Dependencies: spec approval
- Deliverables:
  - recipe schema for app/library inputs;
  - fixtures for Swift Package and Xcode workspace recipes;
  - validation errors for missing repo path, invalid slug, invalid source root,
    missing build target, and unsafe paths.
- Acceptance:
  - unit tests prove invalid recipes fail before command execution;
  - recipe data can represent `unstoppable-wallet-ios` without hardcoding the
    operator's home directory.

### A2. Implement Runtime Smoke Runner Skeleton

- Owner: Claude
- Parallelizable: starts after A1
- Dependencies: A1
- Deliverables:
  - stage runner for `preflight`, `prepare`, `build_scip`,
    `register_project`, `run_extractors`, `semantic_probe`, and `report`;
  - JSON report writer;
  - readable operator log output.
- Acceptance:
  - stage order is deterministic;
  - failures are structured per stage;
  - dry-run mode can validate the recipe without mutating runtime state.

### A3. Implement Swift Package Adapter

- Owner: Claude, Codex/CX optional reviewer
- Parallelizable: yes after A1
- Dependencies: A1
- Deliverables:
  - SwiftPM package build/index command adapter;
  - support for existing `scip/index.scip` reuse when present.
- Acceptance:
  - adapter works for one HorizontalSystems Swift kit recipe;
  - tests cover command construction without running Xcode.

### A4. Implement Xcode Workspace Adapter And UW Recipe

- Owner: Codex/CX preferred, Claude fallback
- Parallelizable: yes after A1
- Dependencies: A1
- Deliverables:
  - Xcode workspace adapter;
  - `unstoppable-wallet-ios` recipe;
  - smoke-safe `Config.xcconfig` prepare step from template;
  - signing-disabled simulator build settings.
- Acceptance:
  - generated command uses `Wallet.xcworkspace`, scheme `Development`,
    generic iOS Simulator destination, `ARCHS=arm64`, and signing disabled;
  - it does not use `Wallet.xcodeproj` for UW app smoke;
  - prepare step is idempotent and does not overwrite an existing config.

### A5. Implement MCP Streamable HTTP Caller

- Owner: Claude
- Parallelizable: yes after spec approval
- Dependencies: none beyond current MCP contract
- Deliverables:
  - helper for `tools/list` and `call_tool`;
  - support for `palace.memory.register_project`;
  - extractor call support with structured status.
- Acceptance:
  - tests assert tool name and arguments include both `name` and `slug`;
  - errors preserve MCP response body enough for debugging.

### A6. Add Docker, Neo4j, And Qodo Preflight

- Owner: Claude
- Parallelizable: yes after spec approval
- Dependencies: none
- Deliverables:
  - checks for Docker availability, image presence, Neo4j reachability, mounted
    repo root, model cache path, local-only model mode, and embedding limits.
- Acceptance:
  - missing large assets produce actionable preflight failures;
  - preflight does not download model files or images by default.

### A7. Runtime Runbook

- Owner: Claude
- Parallelizable: yes after A2 shape is stable
- Dependencies: A2, A5, A6
- Deliverables:
  - `docs/runbooks/productized-runtime-smoke.md`;
  - known-good MacBook command examples;
  - troubleshooting for workspace/project confusion, missing config,
    SwiftPM dependency fetch, Docker resources, and bounded embeddings.
- Acceptance:
  - a new operator can repeat the smoke without reading chat history.

## Track B: Semantic Search Quality

### B1. Source Scope Classification

- Owner: Claude
- Parallelizable: yes
- Dependencies: spec approval
- Deliverables:
  - classify symbols as `project`, `workspace_package`, `dependency`,
    `generated`, `derived`, or `sdk`;
  - use recipe roots when available;
  - fall back to safe path heuristics when recipe roots are absent.
- Acceptance:
  - tests cover app source, workspace package, `.build`, DerivedData, SDK, and
    dependency paths;
  - every semantic result can expose `source_scope`.

### B2. Embedding Candidate Policy

- Owner: Claude
- Parallelizable: yes after B1 design is known
- Dependencies: B1 interface
- Deliverables:
  - bounded embedding runs prioritize first-party definitions;
  - generated/derived/dependency symbols are delayed or skipped unless
    explicitly requested.
- Acceptance:
  - bounded app run no longer spends early embedding slots on SDK/UI accessor
    noise when first-party symbols are available;
  - tests use fixtures and fake backends.

### B3. Semantic Search Filters

- Owner: Claude
- Parallelizable: starts after B1
- Dependencies: B1
- Deliverables:
  - search parameters for dependency/generated scope control;
  - default first-party scope filtering;
  - response fields for `source_scope` and active filters.
- Acceptance:
  - default query excludes dependency/generated/derived/SDK scopes;
  - opt-in search can include dependencies for cases such as hex helpers in
    HsToolKit or kits;
  - cross-project results remain scoped by project and group id.

### B4. Hybrid Ranking

- Owner: Claude
- Parallelizable: starts after B3
- Dependencies: B3
- Deliverables:
  - combine vector score with name/path/module/kind/scope signals;
  - return score components for debugging.
- Acceptance:
  - golden queries improve top-5 first-party relevance versus pure vector score;
  - ranking weights are documented and covered by tests.

### B5. Snippet Provider

- Owner: Claude
- Parallelizable: yes after spec approval
- Dependencies: existing project path resolver and symbol metadata
- Deliverables:
  - local file snippet hydration for resolvable source hits;
  - safe path resolution through project mount metadata;
  - fallback warning when local source cannot be read.
- Acceptance:
  - `include_context=true` returns `context.available=true` for a local source
    hit in a fixture test;
  - path traversal is rejected;
  - codebase-memory remains fallback, not the only provider.

### B6. Golden Query Matrix

- Owner: Claude QA, operator support for live data
- Parallelizable: after B3/B5, before final closure
- Dependencies: B3, B5, runtime indexed data
- Deliverables:
  - documented query set;
  - expected source/module ownership;
  - pass/fail evidence from live MacBook smoke.
- Acceptance:
  - timer/scheduler, balance refresh, WalletConnect signing, bitcoin signing,
    and Data/bytes-to-hex queries have recorded top-5 results;
  - failures include concrete next action instead of vague "ranking bad".

## Track C: Runtime Evidence

### C1. Prepare Clean MacBook Workspace

- Owner: operator or Codex/CX QA
- Parallelizable: after A7 draft
- Dependencies: A6 runbook checks
- Deliverables:
  - clean repo set under a known HorizontalSystems root;
  - Docker images and Qodo cache confirmed;
  - no dirty repo state required for the smoke.
- Acceptance:
  - preflight report is attached to the issue.

### C2. Run App And Kit Cascade

- Owner: Codex/CX QA preferred, Claude fallback with operator access
- Parallelizable: after A2/A4/A5
- Dependencies: A2, A4, A5, A6
- Deliverables:
  - runtime report for `uw-ios-app`;
  - at least one Swift kit runtime report;
  - Neo4j count summary.
- Acceptance:
  - app build/SCIP/cascade path succeeds or fails with structured blocker;
  - report includes symbol and embedding counts.

### C3. Run Semantic Probe And Analyze Results

- Owner: Claude + operator
- Parallelizable: after B3/B5 and C2
- Dependencies: B3, B5, C2
- Deliverables:
  - golden query result report;
  - ranking/snippet pass-fail summary;
  - final closure recommendation.
- Acceptance:
  - top-5 results and snippets are recorded for each golden query;
  - any remaining issue is routed to B4/B5 follow-up with evidence.

## Parallel Execution Plan

Safe parallel start after spec approval:

- Claude: A1, A5, A6, B1, B5.
- Codex/CX: review Xcode/SCIP command shape and prepare A4 implementation notes.

Next wave:

- Claude: A2 after A1; B3 after B1.
- Codex/CX: A4 after A1.
- Claude or Codex/CX: A3 after A1.

Final wave:

- Claude: B4 after B3, B6 after B3/B5.
- Operator/Codex/CX: C1 and C2 after A2/A4/A5/A6.
- Claude + operator: C3 after B3/B5/C2.

Sequential fallback if only Claude is available:

1. A1 recipe contract.
2. A5 MCP caller.
3. A6 preflight.
4. A2 runner skeleton.
5. A3 Swift Package adapter.
6. A4 Xcode workspace adapter and UW recipe.
7. B1 source scope.
8. B2 embedding candidate policy.
9. B3 semantic filters.
10. B5 snippet provider.
11. B4 hybrid ranking.
12. A7 runbook.
13. B6 golden query matrix.
14. C1-C3 runtime evidence on the MacBook host.

## Assignment Summary

- Claude team:
  - primary owner for A1, A2, A3, A5, A6, A7;
  - primary owner for all Track B tasks;
  - prepares docs, tests, and runbooks.
- Codex/CX team:
  - preferred owner for A4 and C2;
  - reviewer for native Swift/Xcode/SCIP command decisions;
  - helps with host-specific runtime blockers.
- Operator:
  - provides MacBook host access, model/image availability, and final smoke
    execution approval.

## Review Checklist Before Implementation

- Confirm whether tasks remain under GIM-839 or become new issue ids.
- Confirm the recipe storage format.
- Confirm whether `source_scope` is persisted or computed.
- Confirm default semantic search filters.
- Confirm whether full unbounded embeddings are required before closure.
