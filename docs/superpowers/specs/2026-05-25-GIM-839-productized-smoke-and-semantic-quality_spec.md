# GIM-839 Follow-up: Productized Runtime Smoke And Semantic Search Quality

**Document date:** 2026-05-25
**Status:** Draft for review
**Issue:** GIM-839 follow-up
**Branch:** `docs/GIM-839-productized-smoke-semantic-quality`
**Companion plan:** `docs/superpowers/plans/2026-05-25-GIM-839-productized-smoke-and-semantic-quality.md`
**Target branch:** `develop`

## 1. Goal

Turn the successful GIM-839 MacBook smoke into a repeatable product path and
raise `palace.code.semantic_search` quality from "technically callable" to
"useful for code investigation".

The result should let an operator point Palace at a clean local checkout of an
app or library, run a known recipe, build or emit SCIP, register the project,
run the extractor cascade, and receive a structured evidence report. It should
also let an agent ask semantic questions such as "find timers in the app" and
get source-scoped, ranked, snippet-backed results instead of dependency or SDK
noise.

## 2. Background

GIM-839 proved the full runtime path on a clean MacBook workspace:

- `bitcoin-core`, `bitcoin-kit`, `dash-kit`, `evm-kit`, and `uw-ios-app` were
  indexed through `symbol_index_swift`, `dead_code`, and `embedding_symbol`.
- Qodo local cache and Docker images were prepared and verified.
- `unstoppable-wallet-ios` required the real workspace path:
  `Wallet.xcworkspace`, scheme `Development`, simulator arm64, signing disabled,
  and a local `Config.xcconfig` copied from `Config.template.xcconfig`.
- The app SCIP artifact was produced at `scip/index.scip` and was large enough
  to prove real app coverage.

The smoke also exposed product gaps:

- The steps were too manual and encoded operator knowledge that should live in a
  recipe or adapter.
- MCP runtime calls need a stable Streamable HTTP caller with correct tool names
  and argument shapes.
- Semantic search can return technically valid but useless top hits when ranking
  is pure vector score over a bounded embedding sample.
- `include_context=true` can still return `snippet_provider_unavailable` for
  local app symbols, which prevents agents from acting on results without a
  second manual lookup.

## 3. Assumptions

- `origin/develop` remains the integration branch.
- Paperclip/Gimle owns product code, scripts, tests, specs, and runbooks.
- MacBook or another developer Mac remains the heavy runtime validation host for
  Xcode, SwiftPM, Docker, Neo4j, and Qodo model execution.
- Runtime validation may create ignored local artifacts such as
  `Config.xcconfig`, `.palace-scip-derived-data/`, `scip/index.scip`, Docker
  volumes, and model caches.
- Real API secrets are not required for smoke. Where an app needs a config file,
  a template-derived smoke-safe config is acceptable only if the app can build
  without secret values.
- Source roots and dependency roots can be recipe-defined when automatic
  detection is ambiguous.
- Cross-project semantic search remains explicit. It must be possible to search
  an app and kits together, but every hit must preserve project/source
  provenance.

## 4. Scope

### 4.1 Productized Runtime Smoke

In scope:

- Define a recipe schema for apps and libraries:
  `slug`, `name`, `repo_path`, `language`, `build_system`, `source_roots`,
  `workspace_package_roots`, `dependency_roots`, `scip_path`,
  `build_or_index_command`, `prepare_steps`, and extractor cascade.
- Add Swift adapters for:
  - Swift Package repositories;
  - Xcode workspace repositories;
  - Xcode project repositories, when the workspace path is not required.
- Add a repo recipe for `unstoppable-wallet-ios` that uses:
  - `Wallet.xcworkspace`;
  - scheme `Development`;
  - simulator arm64 destination;
  - signing disabled;
  - local `Config.xcconfig` created from `Config.template.xcconfig` only when
    missing;
  - source roots that prioritize `Unstoppable/` and first-party packages.
- Add a smoke runner with stages:
  `preflight`, `prepare`, `build_scip`, `register_project`, `run_extractors`,
  `semantic_probe`, and `report`.
- Add a structured report containing command status, durations, SCIP size,
  document count, occurrence count, symbol count, embedding count, warnings, and
  resource notes.
- Add MCP call helpers that use Streamable HTTP and the current tool contract,
  including `palace.memory.register_project` with both `name` and `slug`.
- Add Docker/Qodo preflight checks for image presence, model cache availability,
  local-only mode, Neo4j reachability, and mounted repo root.
- Add a runbook for repeating the smoke on a clean machine.

Out of scope:

- Running full heavyweight smoke in normal CI.
- Downloading model caches or large Docker images as part of unit tests.
- Hardcoding a one-off path that only works for one developer machine.
- Adding every future language adapter in this task.
- Replacing existing GIM-262 ingestion automation when it can be reused or
  extended.

### 4.2 Semantic Search Quality

In scope:

- Classify each symbol by source scope, for example:
  `project`, `workspace_package`, `dependency`, `generated`, `derived`, or
  `sdk`.
- Make default semantic search prefer first-party source:
  `project` and `workspace_package` by default; dependencies, generated code,
  derived data, and SDK symbols only when explicitly requested.
- Add query parameters for source filtering, for example:
  `include_dependencies`, `include_generated`, and/or `source_scopes`.
- Preserve explicit cross-project search:
  `projects=["uw-ios-app", "bitcoin-kit", "evm-kit", ...]` is valid, but result
  identity must include `project`, `group_id`, file path, and source scope.
- Improve ranking with hybrid signals:
  vector score, name/BM25 match, module/path boosts, symbol kind boosts, and
  penalties for accessors, generated files, SDK paths, and dependency scopes.
- Improve embedding candidate selection so bounded runs index the most useful
  first-party definitions before dependency or generated symbols.
- Make `include_context=true` return local source snippets for resolvable local
  symbols by using persisted paths/ranges and a direct local file fallback before
  falling back to codebase-memory.
- Add a golden query matrix for known product questions:
  - timer/scheduler/refresh logic in the app;
  - balance refresh;
  - WalletConnect signing;
  - bitcoin transaction signing;
  - Data/bytes to hex conversion across app, HsToolKit, and kits.

Out of scope:

- Replacing Qodo with another embedding model.
- Claiming semantic search is exhaustive when only bounded embeddings were
  generated.
- Adding unbounded "search every indexed project" as the default path.
- Building a UI for search result exploration.

## 5. Affected Files And Areas

Expected implementation areas:

- `paperclips/scripts/` for a recipe-driven runtime smoke runner and tests.
- `docs/runbooks/` for productized runtime smoke and semantic-search validation
  runbooks.
- `services/palace-mcp/src/palace_mcp/code/find_semantic.py`
- `services/palace-mcp/src/palace_mcp/extractors/symbol_index_swift.py`
- `services/palace-mcp/src/palace_mcp/extractors/embedding_symbol.py`
- `services/palace-mcp/src/palace_mcp/extractors/foundation/` writer helpers
  if symbol metadata must be persisted centrally.
- `services/palace-mcp/src/palace_mcp/git/path_resolver.py`
- Focused tests under `services/palace-mcp/tests/`.

Reference areas:

- `docs/superpowers/specs/2026-05-24-GIM-837-semantic-search-tool.md`
- `docs/superpowers/specs/2026-05-10-GIM-262-per-kit-ingestion-automation_spec.md`
- `docs/superpowers/plans/2026-05-24-GIM-837-semantic-search-cxcto-handoff.md`

## 6. Design Requirements

### 6.1 Recipe Contract

A recipe should be data-first and portable enough to run on any machine where
the repositories and required tools exist.

Minimum fields:

```yaml
slug: uw-ios-app
name: unstoppable-wallet-ios
repo_path: /repos/HorizontalSystems/unstoppable-wallet-ios
language: swift
build_system: xcode_workspace
source_roots:
  - Unstoppable
workspace_package_roots:
  - packages/WalletCore
dependency_roots:
  - Carthage
  - Pods
  - .build
scip_path: scip/index.scip
prepare_steps:
  - ensure_config_from_template
build:
  workspace: Wallet.xcworkspace
  scheme: Development
  destination: generic/platform=iOS Simulator
  archs: arm64
  code_signing_allowed: false
extractors:
  - symbol_index_swift
  - dead_code
  - embedding_symbol
```

The implementation may choose JSON, YAML, or Python dataclasses, but the
operator contract must remain inspectable and testable.

### 6.2 Runtime Smoke Runner

The runner must:

- validate required tools before mutating runtime state;
- verify mounts and repository paths;
- avoid hidden downloads unless the operator explicitly chooses a mode that may
  fetch dependencies;
- prepare repo-local ignored files idempotently;
- build or emit SCIP through the adapter selected by the recipe;
- register projects idempotently through MCP;
- run extractors with structured per-extractor status;
- continue collecting evidence after non-fatal extractor failures;
- emit machine-readable JSON plus readable log lines;
- make bounded embedding limits explicit in the report.

### 6.3 Semantic Source Scoping

Symbol indexing should persist or reliably derive a source scope for every
symbol. The default search profile should exclude scopes that make product
queries noisy:

- default included scopes: `project`, `workspace_package`;
- opt-in scopes: `dependency`, `generated`, `derived`, `sdk`;
- every hit must return `source_scope`.

Path classification must use recipe source roots when available and fall back to
safe heuristics only when recipe data is absent.

### 6.4 Ranking

The initial ranking formula does not need to be perfect, but it must be
inspectable. A result should expose enough score components to debug why it was
ranked:

```json
{
  "score": 0.82,
  "score_components": {
    "vector": 0.74,
    "name_match": 0.12,
    "module_boost": 0.04,
    "scope_boost": 0.08,
    "penalty": -0.16
  }
}
```

Acceptance should be based on golden queries rather than intuition from a single
result list.

### 6.5 Snippet Context

For a local source hit with `include_context=true`, the desired response is:

```json
{
  "context": {
    "available": true,
    "source": "local_file",
    "file_path": "Unstoppable/...",
    "line_start": 120,
    "line_end": 148,
    "snippet": "..."
  }
}
```

If snippet hydration fails, the result remains valid but must include a warning
that identifies which provider failed and why.

## 7. Acceptance Criteria

1. A recipe-driven smoke path exists for at least one Swift Package repo and
   `unstoppable-wallet-ios`.
2. The `unstoppable-wallet-ios` recipe uses `Wallet.xcworkspace`, scheme
   `Development`, simulator arm64, signing disabled, and template-derived
   `Config.xcconfig` creation when needed.
3. The smoke runner can execute `preflight`, `prepare`, `build_scip`,
   `register_project`, `run_extractors`, `semantic_probe`, and `report` stages.
4. MCP calls use Streamable HTTP and current tool names/argument shapes.
5. The final report includes SCIP size, document count, occurrence count,
   symbol count, embedding count, durations, warnings, and resource settings.
6. Unit tests cover recipe validation, path traversal rejection, stage ordering,
   MCP call shape, and structured failure reporting.
7. Semantic search defaults exclude dependency/generated/derived/SDK symbols
   from normal product queries.
8. Semantic search supports explicit cross-project search without losing
   project/source provenance.
9. `include_context=true` returns `context.available=true` with a snippet for at
   least one local app source hit in the golden query matrix.
10. Golden queries produce top-5 first-party results for timer/scheduler,
    balance refresh, WalletConnect signing, bitcoin transaction signing, and
    Data/bytes-to-hex use cases, or document a concrete remaining blocker.
11. Tests use fake embeddings and fixtures; they do not require Qodo downloads
    or Docker.
12. A MacBook runtime evidence report is attached to the issue before closure.

## 8. Verification Plan

Spec and unit verification:

```bash
uv run ruff check services/palace-mcp/src services/palace-mcp/tests
uv run pytest services/palace-mcp/tests/code/test_find_semantic.py
uv run pytest services/palace-mcp/tests/extractors
```

Script verification:

```bash
bash -n paperclips/scripts/<runtime-smoke-script>
bash paperclips/scripts/<runtime-smoke-script> --help
uv run pytest paperclips/scripts/tests
```

Runtime verification on the MacBook smoke host:

```bash
# exact command names to be finalized by implementation
paperclips/scripts/<runtime-smoke-script> preflight --recipe uw-ios-app
paperclips/scripts/<runtime-smoke-script> run --recipe uw-ios-app --bounded-embeddings=128
paperclips/scripts/<runtime-smoke-script> report --recipe uw-ios-app
```

Neo4j evidence:

```cypher
MATCH (p:Project)<-[:IN_PROJECT]-(s:Symbol)
RETURN p.slug, count(s) AS symbols, count(s.embedding) AS embeddings
ORDER BY p.slug
```

Semantic probe evidence:

```json
{
  "tool": "palace.code.semantic_search",
  "arguments": {
    "query": "timer scheduler refresh balance",
    "project": "uw-ios-app",
    "include_context": true,
    "limit": 5
  }
}
```

## 9. Task Routing

Preferred routing:

- Claude owns the productized smoke runner, MCP caller, semantic filtering,
  ranking, snippet provider, tests, and runbooks.
- Codex/CX owns or reviews native/Xcode-specific adapter work, SCIP emission
  details, and MacBook runtime validation because those failures are usually
  toolchain- and host-specific.

If Codex/CX is not available, Claude can execute the full implementation
sequentially. The only non-negotiable external dependency is access to a host
that can run the real Xcode/Docker/Qodo smoke.

## 10. Open Questions

1. Should this follow-up stay under GIM-839 as subtasks, or should runtime
   productization, semantic quality, and golden validation become separate
   issue ids?
2. Should `source_scope` be persisted on `:Symbol` nodes during extraction, or
   computed at query time from Project recipe metadata?
3. Should ranking weights be hardcoded for v1, configured by environment, or
   stored in a recipe/search profile?
4. Is bounded embedding validation enough for closure, or should a separate
   long-running full embedding job be required before calling the product path
   complete?
5. Should dependency-inclusive cross-project searches be opt-in with
   `include_dependencies=true`, or should callers pass explicit
   `source_scopes` only?
