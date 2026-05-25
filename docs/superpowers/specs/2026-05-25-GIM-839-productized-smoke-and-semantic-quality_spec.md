# GIM-839 Follow-up: Productized Runtime Smoke And Semantic Search Quality

**Document date:** 2026-05-25
**Status:** Rev3 draft for review
**Issue:** GIM-839 follow-up
**Branch:** `docs/GIM-839-productized-smoke-semantic-quality`
**Companion plan:** `docs/superpowers/plans/2026-05-25-GIM-839-productized-smoke-and-semantic-quality.md`
**Target branch:** `develop`

## 1. Goal

Turn the successful GIM-839 MacBook smoke into a repeatable product path and
raise `palace.code.semantic_search` quality from "technically callable" to
"useful for code investigation".

The result should let an operator bind Palace to clean local checkouts of an app
or library, run a known recipe, build or emit SCIP, register the project, run the
extractor cascade, and receive a structured evidence report. It should also let
an agent ask semantic questions such as "find timers in the app" and get
source-scoped, ranked, snippet-backed results instead of dependency or SDK noise.

## 2. Rev2/Rev3 Decisions

Rev1 and rev2 review found several places where implementation would otherwise
fork into incompatible contracts. Rev2/rev3 fixes those decisions:

- Versioned project recipes must not contain machine-local absolute paths.
  Local checkout paths live in a runtime binding supplied by CLI, environment,
  or an ignored local manifest.
- `source_scope` is persisted on `:Symbol` during extraction. Query-time
  derivation is only a legacy fallback when old symbols do not carry the field.
- Runtime smoke and semantic quality probe are separate modes with separate
  success criteria. A healthy ingest should not fail because ranking still needs
  tuning.
- v1 ranking uses a fixed, documented formula with deterministic tie-breakers.
  Ranking weights are hardcoded constants for this task.
- Bounded embeddings must disclose coverage and use deterministic source-first
  candidate ordering.
- Snippet hydration is tied to registered project root plus commit/revision
  evidence. Stale or mismatched source returns an explicit warning.
- Xcode smoke must be host-aware: simulator architecture is `auto` by default,
  SwiftPM resolution is opt-in, and Xcode host preflight is mandatory.
- Existing GIM-837 callers are signature-compatible, not behavior-identical:
  default result scope changes to first-party symbols. The implementation must
  document this migration and test the new default.
- Legacy symbols without `source_scope` must be classified from recipe roots
  when recipe metadata is available. They are treated as dependency-like only
  when no reliable recipe/root evidence exists.

## 3. Background

GIM-839 proved the full runtime path on a clean MacBook workspace:

- `bitcoin-core`, `bitcoin-kit`, `dash-kit`, `evm-kit`, and `uw-ios-app` were
  indexed through `symbol_index_swift`, `dead_code`, and `embedding_symbol`.
- Qodo local cache and Docker images were prepared and verified.
- `unstoppable-wallet-ios` required the real workspace path:
  `Wallet.xcworkspace`, scheme `Development`, simulator build, signing disabled,
  and a local `Config.xcconfig` copied from `Config.template.xcconfig`.
- The app SCIP artifact was produced at `scip/index.scip` and was large enough
  to prove real app coverage.

The smoke also exposed product gaps:

- The steps were too manual and encoded operator knowledge that should live in a
  recipe, adapter, or runtime binding.
- MCP runtime calls need a stable Streamable HTTP caller with correct tool names
  and argument shapes.
- Semantic search can return technically valid but useless top hits when ranking
  is pure vector score over a bounded embedding sample.
- `include_context=true` can still return `snippet_provider_unavailable` for
  local app symbols, which prevents agents from acting on results without a
  second manual lookup.

## 4. Assumptions

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
- Source roots and dependency roots are recipe-defined when automatic detection
  is ambiguous.
- Cross-project semantic search remains explicit. It must be possible to search
  an app and kits together, but every hit must preserve project/source
  provenance.

## 5. Scope

### 5.1 Productized Runtime Smoke

In scope:

- Define a versioned recipe schema for apps and libraries:
  `slug`, `name`, `language`, `build_system`, `source_roots`,
  `workspace_package_roots`, `dependency_roots`, `generated_roots`,
  `derived_roots`, `scip_path`, typed `prepare_steps`, typed `build`, and
  extractor cascade.
- Define a local runtime binding contract for machine-local data:
  `repo_path`, `parent_mount`, optional package cache path, optional Docker
  compose override path, Qodo cache path for embedding smoke, and MCP URL.
- Add Swift adapters for:
  - Swift Package repositories;
  - Xcode workspace repositories;
  - Xcode project repositories, when the workspace path is not required.
- Add a repo recipe for `unstoppable-wallet-ios` that uses:
  - `Wallet.xcworkspace`;
  - scheme `Development`;
  - host-aware simulator architecture: `auto|arm64|x86_64`;
  - signing disabled;
  - local `Config.xcconfig` created from `Config.template.xcconfig` only when
    missing;
  - isolated repo-local DerivedData;
  - source roots that prioritize `Unstoppable/` and first-party packages.
- Add a smoke runner with stages:
  `preflight`, `prepare`, `build_scip`, `register_project`, `run_extractors`,
  and `report`.
- Add a separate semantic probe mode that runs after successful runtime smoke.
- Add a structured report containing command status, durations, SCIP size,
  document count, occurrence count, symbol count, embedding count, bounded
  embedding coverage, warnings, resolved host settings, and resource notes.
- Add MCP call helpers that use Streamable HTTP and the current tool contract,
  including `palace.memory.register_project` with both `name` and `slug`.
- Add Docker/Qodo/Neo4j/Xcode preflight checks.
- Add a runbook for repeating the smoke on a clean machine.

Out of scope:

- Running full heavyweight smoke in normal CI.
- Downloading model caches, Docker images, or SwiftPM dependencies during unit
  tests.
- Hardcoding a one-off path that only works for one developer machine.
- Raw shell-string recipe commands as the primary contract. v1 uses typed
  adapters; raw commands are out of scope.
- Adding every future language adapter in this task.
- Replacing existing GIM-262 ingestion automation when it can be reused or
  extended.

### 5.2 Semantic Search Quality

In scope:

- Persist `source_scope` on each `:Symbol` during extraction:
  `project`, `workspace_package`, `dependency`, `generated`, `derived`, or
  `sdk`.
- Persist or expose enough symbol source metadata for local snippets:
  `file_path`, optional `line_start`, optional `line_end`, `commit_sha`, and
  project mount/root identity.
- Make default semantic search prefer first-party source:
  `project` and `workspace_package` by default; dependencies, generated code,
  derived data, and SDK symbols only when explicitly requested.
- Add query parameters for source filtering:
  `source_scopes`, `include_dependencies`, `include_generated`, and
  `include_sdk`.
- Preserve explicit cross-project search:
  `projects=["uw-ios-app", "bitcoin-kit", "evm-kit"]` is valid, but result
  identity must include `project`, `group_id`, file path, and source scope.
- Improve ranking with a fixed v1 hybrid formula:
  vector score, lexical/name/path match, source scope score, module/path boosts,
  symbol kind boosts, and penalties for symbol traits such as accessors and
  synthetic symbols.
- Improve embedding candidate selection so bounded runs index useful first-party
  definitions before dependency or generated symbols.
- Make `include_context=true` return local source snippets for resolvable local
  symbols by using persisted paths/ranges and a direct local file provider before
  falling back to codebase-memory.
- Add a golden query matrix with explicit query text, expected project/module
  families, disallowed noise, minimum relevant hit counts, and snippet
  requirements.

Out of scope:

- Replacing Qodo with another embedding model.
- Claiming semantic search is exhaustive when only bounded embeddings were
  generated.
- Adding unbounded "search every indexed project" as the default path.
- Building a UI for search result exploration.

## 6. Affected Files And Areas

Expected implementation areas:

- `paperclips/scripts/` for a recipe-driven runtime smoke runner and tests.
  The target script path is `paperclips/scripts/palace_runtime_smoke.py`.
- `docs/runbooks/` for productized runtime smoke and semantic-search validation
  runbooks.
- `services/palace-mcp/src/palace_mcp/code/find_semantic.py`
- `services/palace-mcp/src/palace_mcp/extractors/symbol_index_swift.py`
- `services/palace-mcp/src/palace_mcp/extractors/embedding_symbol.py`
- `services/palace-mcp/src/palace_mcp/extractors/foundation/` writer helpers
  for persisted symbol metadata.
- `services/palace-mcp/src/palace_mcp/git/path_resolver.py`
- Focused tests under `services/palace-mcp/tests/`.
- `docs/superpowers/fixtures/gim839_semantic_golden_matrix.json`

Reference areas:

- `docs/superpowers/specs/2026-05-24-GIM-837-semantic-search-tool.md`
- `docs/superpowers/specs/2026-05-10-GIM-262-per-kit-ingestion-automation_spec.md`
- `docs/superpowers/plans/2026-05-24-GIM-837-semantic-search-cxcto-handoff.md`

## 7. Design Requirements

### 7.1 Recipe And Runtime Binding Contract

A recipe is committed and portable. It must not contain machine-local absolute
paths.

Example versioned recipe:

```yaml
slug: uw-ios-app
name: unstoppable-wallet-ios
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
generated_roots:
  - Unstoppable/Generated
derived_roots:
  - .palace-scip-derived-data
scip_path: scip/index.scip
prepare_steps:
  - type: ensure_config_from_template
    template: Config.template.xcconfig
    destination: Config.xcconfig
build:
  workspace: Wallet.xcworkspace
  scheme: Development
  destination: generic/platform=iOS Simulator
  simulator_arch: auto
  derived_data_path: .palace-scip-derived-data
  code_signing_allowed: false
  package_resolution: locked
extractors:
  - symbol_index_swift
  - dead_code
  - embedding_symbol
```

Example local runtime binding:

```yaml
repo_path: /ABS/PATH/HorizontalSystems/unstoppable-wallet-ios
parent_mount: /ABS/PATH/HorizontalSystems
mcp_url: http://localhost:8000/mcp
qodo_cache_path: /ABS/PATH/hf-cache/huggingface
swiftpm_cache_path: /ABS/PATH/swiftpm-cache
docker_compose_override: docker-compose.macbook-smoke.yml
```

Runtime binding fields:

| Field | Required | Meaning |
| --- | --- | --- |
| `repo_path` | yes | Absolute checkout path for this recipe on the current host. |
| `parent_mount` | yes | Absolute mounted root that contains `repo_path`. |
| `mcp_url` | yes | Streamable HTTP MCP endpoint. |
| `qodo_cache_path` | required for embedding smoke | Host-local Hugging Face/Qodo cache. |
| `swiftpm_cache_path` | optional | Host-local SwiftPM cache used by Xcode/SwiftPM adapters. |
| `docker_compose_override` | optional | Path relative to the Palace checkout unless absolute. |

Invariants:

- `repo_path` must resolve inside `parent_mount`.
- local binding files must be ignored by git unless they are sanitized fixtures;
- reports may include resolved host settings, but must not include config file
  contents or secret-like values.

The implementation may choose JSON, YAML, or Python dataclasses, but the
operator contract must remain inspectable and testable.

### 7.2 Runtime Smoke Runner

The runner must:

- validate required tools before mutating runtime state;
- verify mounts and repository paths from the runtime binding;
- avoid hidden downloads unless the operator uses an explicit
  `--allow-package-resolution` or equivalent mode;
- use locked SwiftPM resolution by default:
  `-disableAutomaticPackageResolution` and
  `-onlyUsePackageVersionsFromResolvedFile` where supported;
- reject unexpected `absolute:` workspace references unless the recipe or
  binding explicitly maps them, or generate a transient sanitized workspace and
  report that behavior;
- prepare repo-local ignored files idempotently;
- build or emit SCIP through the adapter selected by the recipe;
- register projects idempotently through MCP;
- run extractors with structured per-extractor status;
- continue collecting evidence after non-fatal extractor failures;
- emit machine-readable JSON plus readable log lines;
- make bounded embedding limits and coverage explicit in the report.

### 7.3 Preflight Contract

Preflight must check at least:

- Docker availability and required image presence;
- Neo4j reachability;
- MCP URL reachability and `tools/list`;
- Qodo cache path and local-only mode when requested;
- repo path, parent mount, and SCIP output path writability;
- `xcode-select -p`;
- `xcodebuild -version`;
- accepted Xcode license status when detectable;
- available iOS SDK and simulator runtime;
- host architecture and resolved simulator architecture;
- SwiftPM package resolution mode and package cache path;
- workspace `absolute:` file references;
- whether `Config.xcconfig` exists or can be created from template.

Preflight must fail before downloads or build steps in locked/offline mode.
SwiftPM build plugins and package scripts are accepted only for trusted
first-party repositories; locked mode remains the default smoke path.

### 7.4 Semantic Source Scoping

v1 persists `source_scope` on `:Symbol` during extraction. Query-time
classification is a legacy fallback only when an existing node lacks
`source_scope`.

Classification precedence uses first match in the order below after normalizing
paths relative to the project root. If multiple roots in the same category
match, the longest matching root wins.

1. `derived` for DerivedData and `.palace-scip-derived-data` paths.
2. `generated` for recipe `generated_roots` and generated-file heuristics.
3. `sdk` for Apple SDK/system framework paths.
4. `workspace_package` for recipe `workspace_package_roots`.
5. `dependency` for recipe `dependency_roots`.
6. `project` for recipe `source_roots`.
7. `dependency` for unknown external package paths.

Every semantic result must return `source_scope`. Unknown scope is not a normal
value. For legacy symbols without persisted `source_scope`, query-time fallback
must classify from recipe roots when recipe metadata is available. Only symbols
that cannot be classified from recipe/root evidence should produce a warning and
be treated as dependency-like for default filtering. Runtime closure requires
re-extracting the projects used in the MacBook evidence path so the primary
path exercises persisted `source_scope`.

### 7.5 Semantic Search Request Contract

`palace.code.semantic_search` remains signature-compatible with GIM-837, but the
default behavior intentionally changes from "all embedded symbols in scope" to
"first-party symbols in scope". The implementation must include a migration note
for existing agents/scripts and a regression test that proves dependency/SDK
results are excluded by default and included only by explicit scope controls.

- exactly one of `project` or `projects` is required;
- `project` is a convenience alias for a one-item `projects` list;
- `projects` order is preserved for deterministic tie-breakers;
- `source_scopes`, when provided, is the authoritative filter;
- if `source_scopes` is absent:
  - default scopes are `["project", "workspace_package"]`;
  - `include_dependencies=true` adds `dependency`;
  - `include_generated=true` adds `generated` and `derived`;
  - `include_sdk=true` adds `sdk`;
- there is no separate `include_derived` in v1; `derived` is controlled by
  `include_generated` or explicit `source_scopes`;
- `source_scopes=[]` is invalid;
- every hit returns `project`, `group_id`, `qualified_name`, `file_path`,
  `source_scope`, `score`, and `score_components`;
- v1 does not deduplicate equivalent concepts across projects. Two projects may
  return the same helper name as separate hits because provenance is part of the
  answer.

### 7.6 Bounded Embedding Policy

When `PALACE_EMBEDDING_MAX_SYMBOLS` or a smoke runner bound is active, candidate
ordering is deterministic:

1. `project` definitions and declarations;
2. `workspace_package` definitions and declarations;
3. `project` non-accessor methods/functions/classes;
4. `workspace_package` non-accessor methods/functions/classes;
5. `dependency` public API symbols;
6. `generated` and `derived` only when explicitly enabled;
7. `sdk` only when explicitly enabled.

Within each bucket, order by file path, then qualified name. Accessors,
synthetic symbols, and generated paths are skipped unless no better candidates
remain or an explicit include flag is set.

Reports and search responses must disclose partial coverage:

```json
{
  "embedding_coverage": {
    "bounded": true,
    "max_symbols": 128,
    "embedded_symbols": 128,
    "eligible_symbols": 252718,
    "source_scope_counts": {
      "project": 120,
      "workspace_package": 8
    }
  }
}
```

### 7.7 Ranking

v1 ranking uses hardcoded weights. The final score is clamped to `0..1`:

```text
score =
  0.70 * vector_score_normalized +
  0.15 * lexical_match +
  0.07 * source_scope_score +
  0.05 * symbol_kind_boost +
  0.03 * module_path_boost -
  penalty
```

Component rules:

- `vector_score_normalized` is the Neo4j vector score normalized to `0..1`.
- `lexical_match` is computed from query token overlap with qualified name,
  symbol name, module name, and file path.
- `source_scope_score`: `project=1.0`, `workspace_package=0.8`,
  `dependency=0.2`, `generated=0.0`, `derived=0.0`, `sdk=0.0`.
- `symbol_kind_boost` prefers functions, methods, classes, structs, protocols,
  and enums over variables/accessors.
- `module_path_boost` rewards recipe source roots and expected module families.
- `penalty` is additive, capped at `0.20`, and does not include source-scope
  penalties because scope already affects `source_scope_score`:
  - accessor or compiler-synthesized accessor: `0.10`;
  - synthetic/compiler-generated symbol name: `0.10`;
  - no source line metadata when equivalent candidates have line metadata:
    `0.03`;
  - stale embedding coverage warning for the hit's source scope: `0.05`.

Tie-breakers:

1. final score descending;
2. source scope order: project, workspace_package, dependency, generated,
   derived, sdk;
3. caller's `projects` order;
4. lexical match descending;
5. qualified name ascending.

Each result returns score components for debugging.

### 7.8 Snippet Context

Snippet provider order:

1. local file provider using registered project root, file path, commit/revision
   evidence, and persisted line span when available;
2. local file provider using a bounded symbol-neighborhood fallback when line
   span is unavailable;
3. codebase-memory snippet provider;
4. unavailable warning.

For local file snippets:

- treat persisted `file_path` as untrusted input;
- reject absolute persisted file paths and any path containing `..`;
- resolve the path against the registered project root, then apply
  `realpath`/symlink resolution;
- require the resolved file to remain inside the resolved project root.
  `parent_mount` may be used to locate project roots, but it is not a broad
  read boundary for snippets;
- compare current checkout commit to the indexed `commit_sha` when available;
- return `context.available=false` and warning code `stale_source` when the
  checkout no longer matches indexed evidence;
- default snippet window is the symbol span plus up to five context lines before
  and after;
- snippets are capped at 120 lines or 16 KiB, whichever comes first.

Desired response:

```json
{
  "context": {
    "available": true,
    "source": "local_file",
    "file_path": "Unstoppable/Services/Balance/BalanceService.swift",
    "line_start": 120,
    "line_end": 148,
    "snippet": "func refreshBalance() { balanceService.refresh() }"
  }
}
```

If snippet hydration fails, the result remains valid but must include a warning
that identifies which provider failed and why.

### 7.9 Golden Query Matrix

The implementation must create and maintain a machine-readable golden matrix at
`docs/superpowers/fixtures/gim839_semantic_golden_matrix.json`. The matrix must
be consumed by a runner that prints per-row pass/fail and top-5 evidence.

Matrix row schema:

```json
{
  "query_id": "timer",
  "query": "timer scheduler refresh balance",
  "projects": ["uw-ios-app"],
  "source_scopes": ["project", "workspace_package"],
  "expected_patterns": {
    "qualified_name_regex": ["(?i)(timer|scheduler|refresh)"],
    "file_globs": ["Unstoppable/**"],
    "module_regex": ["(?i)(balance|refresh|sync|timer)"]
  },
  "disallowed_patterns": {
    "qualified_name_regex": ["CoreFoundation", "CGFloat"],
    "source_scopes": ["sdk", "generated", "derived"]
  },
  "min_relevant_top5": 3,
  "min_snippets": 2,
  "mandatory": true
}
```

A hit is relevant only if it matches at least one expected qualified-name,
file-glob, or module pattern and does not match disallowed patterns. Minimum
rows:

| Query id | Query text | Scope | Expected result families | Disallowed top-5 noise | Pass |
| --- | --- | --- | --- | --- | --- |
| timer | `timer scheduler refresh balance` | `uw-ios-app` | app refresh/scheduler/timer modules | SDK/CoreFoundation/UI sizing symbols | >=3 of top 5 relevant, >=2 snippets |
| balance | `balance refresh wallet balance sync` | `uw-ios-app` | balance service/interactor/view-model refresh paths | generated accessors, SDK symbols | >=3 of top 5 relevant, >=2 snippets |
| wc-signing | `wallet connect sign request transaction` | `uw-ios-app` | WalletConnect signing request flow | unrelated QR/UI layout helpers | >=3 of top 5 relevant, >=2 snippets |
| btc-signing | `bitcoin transaction signer input script` | `bitcoin-kit` or app+kit projects | bitcoin transaction/signing classes | app-only unrelated UI | >=3 of top 5 relevant, >=1 non-app snippet |
| data-hex | `Data bytes hex string conversion` | app+HsToolKit+kit projects | HsToolKit/kits/app byte or hex helpers | SDK NSData-only hits unless explicit SDK scope | >=2 of top 5 relevant, provenance preserved |

The `data-hex` row requires a registered HsToolKit recipe/binding. The example
slug is `hs-toolkit`; if implementation chooses a different slug, the matrix and
cross-project probe must use that exact recipe slug.

Closure requires the golden matrix to pass at least four of five rows. The
passing set must include at least one non-app row (`btc-signing` or `data-hex`).
The remaining row, if any, must have a linked follow-up issue with evidence. If
fewer than four rows pass, or if no non-app row passes, this issue is not
complete.

## 8. Acceptance Criteria

1. A recipe-driven smoke path exists for at least one Swift Package repo and
   `unstoppable-wallet-ios`.
2. Versioned recipes contain no machine-local absolute paths; repo paths are
   provided by runtime binding.
3. The `unstoppable-wallet-ios` recipe uses `Wallet.xcworkspace`, scheme
   `Development`, host-aware simulator architecture, signing disabled,
   isolated DerivedData, locked package resolution by default, and
   template-derived `Config.xcconfig` creation when needed.
4. The UW app adapter uses `-workspace Wallet.xcworkspace`, not direct
   `-project Unstoppable/Unstoppable.xcodeproj`.
5. Preflight covers Docker, Neo4j, MCP, Qodo, Xcode, iOS SDK/runtime, host arch,
   SwiftPM resolution mode, workspace absolute references, and config template
   readiness.
6. The smoke runner can execute `preflight`, `prepare`, `build_scip`,
   `register_project`, `run_extractors`, and `report` stages.
7. Semantic probe is a separate mode with separate pass/fail reporting.
8. MCP calls use Streamable HTTP and current tool names/argument shapes.
9. The final report includes SCIP size, document count, occurrence count,
   symbol count, embedding count, bounded coverage, durations, warnings,
   resolved host settings, and resource settings.
10. Unit tests cover recipe validation, runtime binding validation, path
    traversal rejection, stage ordering, MCP call shape, no-download preflight,
    workspace absolute-reference detection, and structured failure reporting.
11. `source_scope` is persisted on symbols during extraction and returned in
    every semantic result.
12. Semantic search defaults exclude dependency/generated/derived/SDK symbols
    from normal product queries.
13. Semantic search supports explicit cross-project search without losing
    project/source provenance.
14. `include_context=true` returns snippets for local first-party hits according
    to the snippet contract, including at least one non-app first-party hit in
    the golden matrix.
15. Golden query closure requires at least four of five matrix rows passing,
    including at least one non-app row.
16. Tests use fake embeddings and fixtures; they do not require Qodo downloads,
    Docker, Xcode builds, or network access.
17. A MacBook runtime evidence report is attached to the issue before closure.

## 9. Verification Plan

CI-required verification:

```bash
uv run ruff check services/palace-mcp/src services/palace-mcp/tests
uv run pytest services/palace-mcp/tests/code/test_find_semantic.py
uv run pytest services/palace-mcp/tests/extractors
uv run pytest paperclips/scripts/tests
```

Script verification:

```bash
uv run python paperclips/scripts/palace_runtime_smoke.py --help
```

Required negative tests:

- invalid recipe slug rejected before path construction;
- versioned recipe with absolute `repo_path` rejected;
- `repo_path` outside `parent_mount` rejected;
- runtime binding path traversal rejected;
- MCP caller sends `palace.memory.register_project` with both `name` and `slug`;
- no-download preflight fails fast when packages are unresolved;
- unexpected workspace `absolute:` reference is rejected unless mapped;
- persisted snippet `file_path` that is absolute, contains `..`, points outside
  project root, or escapes through a symlink is rejected;
- stale source checkout returns `stale_source` snippet warning;
- fixture semantic ranking proves first-party project results outrank dependency
  results when vector scores tie;
- fixture snippet provider returns a local snippet for an in-root symbol and
  rejects outside-root persisted paths;
- bounded embedding response includes coverage metadata.

Runtime verification on the MacBook smoke host:

```bash
uv run python paperclips/scripts/palace_runtime_smoke.py preflight --recipe uw-ios-app --binding local.yml
uv run python paperclips/scripts/palace_runtime_smoke.py run --recipe uw-ios-app --binding local.yml --bounded-embeddings=128
uv run python paperclips/scripts/palace_runtime_smoke.py report --recipe uw-ios-app --binding local.yml

uv run python paperclips/scripts/palace_runtime_smoke.py preflight --recipe bitcoin-kit --binding local.yml
uv run python paperclips/scripts/palace_runtime_smoke.py run --recipe bitcoin-kit --binding local.yml --bounded-embeddings=256
uv run python paperclips/scripts/palace_runtime_smoke.py report --recipe bitcoin-kit --binding local.yml
```

Neo4j evidence:

```cypher
MATCH (s:Symbol)
WHERE s.group_id STARTS WITH 'project/'
RETURN
  s.group_id AS group_id,
  count(s) AS symbols,
  count(s.embedding) AS embeddings,
  collect(DISTINCT s.source_scope) AS source_scopes
ORDER BY group_id
```

Single-project semantic probe:

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

Cross-project semantic probe:

```json
{
  "tool": "palace.code.semantic_search",
  "arguments": {
    "query": "Data bytes hex string conversion",
    "projects": ["uw-ios-app", "hs-toolkit", "bitcoin-kit", "evm-kit"],
    "source_scopes": ["project", "workspace_package", "dependency"],
    "include_context": true,
    "limit": 5
  }
}
```

Required semantic assertions:

- every hit has `project`, `group_id`, `qualified_name`, `file_path`,
  `source_scope`, `score`, and `score_components`;
- no default query returns SDK/generated/derived hits in top 5;
- cross-project hits preserve project provenance;
- golden matrix passes at least four of five rows and includes one passing
  non-app row.

Merge vs closure gates:

- Merge gate: CI-required verification, script verification, unit negative
  tests, and fixture-based ranking/snippet tests pass.
- Runtime closure gate: MacBook app+kit runtime evidence and Neo4j counts are
  attached.
- Product closure gate: semantic golden matrix passes at least four of five
  rows including one non-app row, with snippets as required.

## 10. Task Routing

Preferred routing:

- Claude owns the productized smoke runner, MCP caller, semantic filtering,
  ranking, snippet provider, tests, and runbooks.
- Codex/CX owns or reviews native/Xcode-specific adapter work, SCIP emission
  details, and MacBook runtime validation because those failures are usually
  toolchain- and host-specific.

If Codex/CX is not available, Claude can execute the full implementation
sequentially. The only non-negotiable external dependency is access to a host
that can run the real Xcode/Docker/Qodo smoke.

## 11. Closed Decisions

1. GIM-839 remains the parent. Paperclip may assign real child issue numbers,
   but child titles must include stable slice ids from the plan.
2. Four-of-five golden matrix pass is sufficient for v1 closure only when the
   passing set includes at least one non-app row.
3. Full unbounded embeddings are a separate post-smoke validation issue after
   bounded product smoke is stable.
