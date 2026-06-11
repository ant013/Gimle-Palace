# Broken iOS extractor repair plan

Grounded in `origin/develop` at `2bfaa2309af565613f491fcc0f9d1500e6cb8ded`.

## Assumptions

- The target corpus is the seven dedicated iOS clones under
  `/Users/Shared/Ios/Gimle-Repos/HorizontalSystems`; do not read or mutate the
  developer working clones under `/Users/Shared/Ios/HorizontalSystems`.
- Android extraction is out of scope for this repair.
- Palace runs against native macOS Neo4j, not Docker Neo4j.
- The current audit showed 19 registered extractors. This spec only covers the
  extractors that are broken, partial in a misleading way, or reporting green
  success for missing input.
- Work must be split and run sequentially. Do not launch parallel Paperclip
  implementation tasks against the same branch.

## Problem Summary

The rebaseline graph has enough valid data to use `dependency_surface`,
`dead_symbol_binary_surface`, `hotspot`, `symbol_index_swift`,
`embedding_symbol`, `coding_convention`, `crypto_domain_model`,
`error_handling_policy`, `localization_accessibility`, and `testability_di`.

The audit split is important: some extractors are broken, some already return
the correct `ExtractorOutcome` but upstream persistence hides it, and one is
verify-only.

- `arch_layer`: writes only 19 nodes and 1 edge for seven iOS repos because it
  mostly sees `Package.swift`/Gradle shape and misses Xcode/SCIP module truth.
- `git_history`: `Commit` identity is keyed globally by SHA, and the schema has
  a global `Commit(sha)` uniqueness constraint. Shared commits are captured by
  the first project that writes them, causing later per-project counts to be
  wrong. Old groups such as `project/uw-ios-baseline` amplify the confusion.
- `code_ownership`: checkpoints are project-scoped, but rebaseline orchestration
  does not wipe stale `OwnershipCheckpoint` rows and the extractor can return
  `no_change` before verifying that a baseline actually exists.
- `public_api_surface`: the extractor already returns `MISSING_INPUT` when
  artifacts are absent. The missing work is artifact generation/registration and
  upstream persistence of that outcome; `uw-ios-app` should be treated as app
  `NOT_APPLICABLE` unless a deliberate public API artifact is generated for it.
- `cross_module_contract`: GIM-1603 already writes deterministic zero-consumer
  snapshots when producer surfaces exist. The real remaining failure is Swift
  name correlation: `.swiftinterface` FQNs do not match SCIP/Tantivy descriptor
  qualified names, so consumer edges stay at zero.
- `cross_repo_version_skew`: bundle mode reads `:HAS_MEMBER` while bundle
  registration writes `:CONTAINS`, and the skew computation considers only
  resolved versions, ignoring declared constraint skew.
- `reactive_dependency_tracer`: already returns `MISSING_INPUT` when
  `reactive_facts.json` is absent. It needs upstream persistence and regression
  tests, not a main extractor rewrite.
- `hot_path_profiler`: already returns `NOT_APPLICABLE` or `MISSING_INPUT`
  before successful trace parsing. It is verify-only, plus live project
  `expected_profile` validation.

## Scope

1. Add an extractor result quality contract so `ExtractorOutcome`,
   `message`, and `next_action` are persisted to `IngestRun` and surfaced in
   reports. This must cover both extractor lifecycle Cypher and the older
   paperclip/memory ingest-run Cypher path. Missing input must not look
   equivalent to successful zero data.
2. Propagate outcome through bundle ingestion. `IngestRunResult`, bundle state,
   and bundle counters must distinguish `ok`, `missing_input`,
   `not_applicable`, and hard failures. `success` may remain true for a valid
   missing-input run, but outcome must be queryable.
3. Fix `arch_layer` for iOS by deriving module/file structure from Xcode
   targets and/or SCIP symbols. It must create meaningful Module, File, and
   ownership edges for all seven iOS repos.
4. Make `public_api_surface` artifacts complete for the SwiftPM kits that can
   generate `.swiftinterface` on the dev Mac. Keep the extractor artifact-driven;
   do not add a regex source fallback unless interface generation is proven
   impossible for a specific kit.
5. Fix `cross_module_contract` Swift symbol correlation so source-facing
   `.swiftinterface` declarations can match SCIP/Tantivy symbol ids, then report
   whether zero consumer edges means real absence of consumers or correlation
   failure.
6. Fix `cross_repo_version_skew` bundle membership from `:HAS_MEMBER` to the
   real `:CONTAINS` relationship, and add declared-constraint skew detection in
   addition to resolved-version skew.
7. Fix `code_ownership` rebaseline behavior: project-scoped checkpoints are
   correct, but clean rebaseline must purge or invalidate stale checkpoints and
   the extractor must not skip when no `OwnershipFileState` baseline exists.
8. Fix `git_history` graph identity: use project-scoped commit identity and a
   matching composite constraint instead of global `Commit(sha)`. Add safe
   migration / purge steps for old groups.
9. Harden `reactive_dependency_tracer` and `hot_path_profiler` tests and live
   verification so their already-correct missing-input/not-applicable outcomes
   cannot regress.

## Out Of Scope

- Deleting application dead code found by `dead_symbol_binary_surface`.
- Refactoring hotspots found by `hotspot`.
- Android repo extraction.
- Replacing native Neo4j with Docker services.
- Broad extractor framework rewrites beyond outcome persistence and the
  specific broken extractor paths listed above.

## Affected Areas

- `services/palace-mcp/src/palace_mcp/extractors/base.py`
- `services/palace-mcp/src/palace_mcp/extractors/cypher.py`
- `services/palace-mcp/src/palace_mcp/extractors/runner.py`
- `services/palace-mcp/src/palace_mcp/extractors/bundle_state.py`
- `services/palace-mcp/src/palace_mcp/extractors/schema.py`
- `services/palace-mcp/src/palace_mcp/memory/cypher.py`
- `services/palace-mcp/src/palace_mcp/memory/models.py`
- `services/palace-mcp/src/palace_mcp/extractors/arch_layer/`
- `services/palace-mcp/src/palace_mcp/extractors/public_api_surface.py`
- `services/palace-mcp/src/palace_mcp/extractors/cross_module_contract.py`
- `services/palace-mcp/src/palace_mcp/extractors/cross_repo_version_skew/`
- `services/palace-mcp/src/palace_mcp/extractors/code_ownership/`
- `services/palace-mcp/src/palace_mcp/extractors/git_history/`
- `services/palace-mcp/src/palace_mcp/extractors/reactive_dependency_tracer/`
- `services/palace-mcp/src/palace_mcp/extractors/hot_path_profiler/`
- `services/palace-mcp/src/palace_mcp/project_analyze.py`
- `bench/` and `paperclips/scripts/` only where needed for artifact generation
  or rebaseline verification wrappers.
- Extractor unit/integration tests under
  `services/palace-mcp/tests/extractors/`.
- Native macOS runbooks under `docs/runbooks/`.

## Acceptance Criteria

- `IngestRun` records include outcome, message, and next action for every
  extractor run from both ingest-run Cypher paths. Missing-input and
  not-applicable runs are visible as such in queryable data and reports.
- Bundle ingest responses include outcome-aware counters, at minimum separating
  `members_ok`, `members_missing_input`, `members_not_applicable`, and
  `members_failed`, without treating all non-failing runs as equivalent full
  coverage.
- `arch_layer` produces module/file graph data for every iOS repo. For
  `uw-ios-app`, module count must be materially greater than the current zero
  Module result, and `MODULE_DEPENDS_ON` / containment edges must be
  explainable from Xcode or SCIP inputs.
- `public_api_surface` writes `PublicApiSurface` / `PublicApiSymbol` for
  interface-capable SwiftPM kits, records missing input with persisted
  `next_action` when artifacts are absent, and records app-level
  `NOT_APPLICABLE` for `uw-ios-app` unless a deliberate artifact source exists.
- `cross_module_contract` continues to write GIM-1603 zero-consumer snapshots,
  and additionally writes real `CONSUMES_PUBLIC_SYMBOL` edges when a Swift API
  symbol has matching SCIP/Tantivy consumers.
- `cross_repo_version_skew` works through bundles created by the canonical
  bundle registration path (`:CONTAINS`) and reports both resolved-version skew
  and declared-constraint skew, including at minimum
  `HsExtensions.Swift`, `HsToolKit.Swift`, `HsCryptoKit.Swift`,
  `BitcoinCore.Swift`, and Apple dependency constraint skew.
- `code_ownership` writes `OwnershipFileState` for all seven iOS repos on a
  clean rebaseline. No repo may skip as `no_change` before a baseline exists.
- `git_history` per-project commit counts must be close to physical
  `git rev-list --count HEAD` for each of the seven repos, and old groups such
  as `project/uw-ios-baseline` must not affect current project counts.
- `reactive_dependency_tracer` without `reactive_facts.json` persists
  `MISSING_INPUT` and its diagnostic/message in `IngestRun` and bundle state.
- `hot_path_profiler` persists `NOT_APPLICABLE` or `MISSING_INPUT` as returned
  by the extractor. Live `Project.expected_profile` values are verified for
  app projects so profile-gating cannot silently hide missing traces.

## Verification Plan

- Run focused unit tests for every touched extractor.
- Run integration tests with real Neo4j for touched graph writers and runner
  outcome persistence.
- Re-run the extractor bundle sequentially on the seven dedicated iOS repos.
- Query and record per-extractor totals, per-project totals, and outcome
  distribution after the rebaseline.
- Run explicit sanity queries:
  - `arch_layer`: module/file/edge counts per project.
  - `public_api_surface`: public API surface/symbol counts per project.
  - `cross_module_contract`: snapshot count, consumer edge count, and skipped
    symbol/correlation counters per project.
  - `cross_repo_version_skew`: resolved-version skew groups,
    declared-constraint skew groups, and affected projects.
  - `code_ownership`: `OwnershipFileState` counts per project.
  - `git_history`: `Commit` counts compared with local `git rev-list`.
  - `reactive_dependency_tracer`: component/state/effect counts plus missing
    input diagnostics.
  - `hot_path_profiler`: profiler nodes or explicit missing trace outcome.
- Required local checks for `services/palace-mcp` changes:
  - `uv run ruff check`
  - `uv run mypy src/`
  - targeted `uv run pytest ...`
  - full `uv run pytest` before merge if runner/schema behavior changes.

## Implementation Order

1. Outcome persistence and reporting semantics across `extractors/cypher.py`,
   `memory/cypher.py`, `_finalize`, `IngestRunResult`, and bundle counters.
2. Cheap outcome hardening for extractors that still return default OK on
   skipped/no-input/no-change paths.
3. Regression tests and live verification for already-fixed
   `reactive_dependency_tracer` and `hot_path_profiler`.
4. `git_history` project-scoped commit key, composite constraint migration, and
   old-group purge plan.
5. `code_ownership` baseline guard and rebaseline checkpoint purge/invalidate,
   with focused tests for stale checkpoint purge/invalidation and the
   no-baseline guard. The live seven-repo `OwnershipFileState` proof remains
   part of step 10.
6. `public_api_surface` `.swiftinterface` artifact generation on the dev Mac
   for interface-capable SwiftPM kits; app `NOT_APPLICABLE` handling.
7. `arch_layer` iOS module graph from SCIP and/or Xcode targets.
8. `cross_module_contract` Swift FQN-to-SCIP correlation bridge.
9. `cross_repo_version_skew` `:CONTAINS` bundle membership fix and
   declared-constraint skew detection.
10. Full sequential rebaseline and numeric report.

## Open Questions

- Which SwiftPM kits cannot generate `.swiftinterface` on the dev Mac, and what
  concrete compiler/toolchain error blocks them?
- Should old project groups be deleted globally during rebaseline, or should the
  repair add project-scoped uniqueness first and then run a controlled purge?
- Which reactive helper should generate `reactive_facts.json` for Swift, and
  should those artifacts be committed to the dedicated clone or generated only
  during rebaseline?
