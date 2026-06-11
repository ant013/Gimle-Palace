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

The following extractors need repair before their numbers can be trusted:

- `arch_layer`: writes only 19 nodes and 1 edge for seven iOS repos because it
  mostly sees `Package.swift`/Gradle shape and misses Xcode/SCIP module truth.
- `public_api_surface`: writes useful data only for BitcoinCore because the
  other repos lack generated `.swiftinterface` artifacts.
- `cross_module_contract`: writes zero snapshots/edges because public API data,
  symbol correlation, and module ownership inputs are missing or mismatched.
- `cross_repo_version_skew`: reports zero even when `DEPENDS_ON` edges exist.
- `code_ownership`: first four repos reported `no_change` and did not create a
  real ownership baseline.
- `git_history`: current commit graph is contaminated by old groups such as
  `project/uw-ios-baseline`, so per-project counts are wrong.
- `reactive_dependency_tracer`: writes diagnostics/missing-input rows when
  `reactive_facts.json` is absent, but runner success makes this look like real
  graph coverage.
- `hot_path_profiler`: zero is expected when trace files are absent, but it
  should surface as missing input / not applicable, not normal green coverage.

## Scope

1. Add an extractor result quality contract so `ExtractorOutcome`,
   `message`, and `next_action` are persisted to `IngestRun` and surfaced in
   reports. Missing input must not look equivalent to successful zero data.
2. Fix `arch_layer` for iOS by deriving module/file structure from Xcode
   targets and/or SCIP symbols. It must create meaningful Module, File, and
   ownership edges for all seven iOS repos.
3. Make `public_api_surface` generation complete for all seven iOS repos and
   make missing artifacts a hard visible missing-input condition.
4. Fix `cross_module_contract` so it can create deterministic snapshots when
   public API exists, and so it has a clear path to correlate `.swiftinterface`
   declarations with SCIP/Tantivy symbols.
5. Fix `cross_repo_version_skew` to compute skew from existing
   `ExternalDependency` / `DEPENDS_ON` graph and persist non-zero run metadata.
6. Fix `code_ownership` checkpoint behavior so a clean rebaseline cannot skip
   repos before writing `OwnershipFileState`.
7. Fix `git_history` group scoping and cleanup behavior so old groups cannot
   pollute current per-project commit counts.
8. Update `reactive_dependency_tracer` and `hot_path_profiler` reporting so
   missing helper JSON or missing traces are explicit missing-input outcomes.

## Out Of Scope

- Deleting application dead code found by `dead_symbol_binary_surface`.
- Refactoring hotspots found by `hotspot`.
- Android repo extraction.
- Replacing native Neo4j with Docker services.
- Broad extractor framework rewrites beyond outcome persistence and the
  specific broken extractor paths listed above.

## Affected Areas

- `services/palace-mcp/src/palace_mcp/extractors/base.py`
- `services/palace-mcp/src/palace_mcp/extractors/runner.py`
- `services/palace-mcp/src/palace_mcp/extractors/schema.py`
- `services/palace-mcp/src/palace_mcp/extractors/arch_layer/`
- `services/palace-mcp/src/palace_mcp/extractors/public_api_surface.py`
- `services/palace-mcp/src/palace_mcp/extractors/cross_module_contract.py`
- `services/palace-mcp/src/palace_mcp/extractors/cross_repo_version_skew/`
- `services/palace-mcp/src/palace_mcp/extractors/code_ownership/`
- `services/palace-mcp/src/palace_mcp/extractors/git_history/`
- `services/palace-mcp/src/palace_mcp/extractors/reactive_dependency_tracer/`
- `services/palace-mcp/src/palace_mcp/extractors/hot_path_profiler/`
- `bench/` and `paperclips/scripts/` only where needed for artifact generation
  or rebaseline verification wrappers.
- Extractor unit/integration tests under
  `services/palace-mcp/tests/extractors/`.
- Native macOS runbooks under `docs/runbooks/`.

## Acceptance Criteria

- `IngestRun` records include outcome, message, and next action for every
  extractor run. Missing-input runs are visible as missing input in queryable
  data and reports.
- `arch_layer` produces module/file graph data for every iOS repo. For
  `uw-ios-app`, module count must be materially greater than the current zero
  Module result, and `MODULE_DEPENDS_ON` / containment edges must be
  explainable from Xcode or SCIP inputs.
- `public_api_surface` either writes `PublicApiSurface` / `PublicApiSymbol`
  for every iOS repo or records a concrete missing-input/build failure per repo.
  A green zero is not acceptable.
- `cross_module_contract` writes at least deterministic
  `ModuleContractSnapshot` rows for repos with public API surfaces. If
  consumer edges remain zero, the run must explain whether this is caused by no
  consumers or by unresolved Swift name correlation.
- `cross_repo_version_skew` reports the version/constraint mismatches already
  visible in `dependency_surface`, including at minimum
  `HsExtensions.Swift`, `HsToolKit.Swift`, `HsCryptoKit.Swift`,
  `BitcoinCore.Swift`, and Apple dependency constraint skew.
- `code_ownership` writes `OwnershipFileState` for all seven iOS repos on a
  clean rebaseline. No repo may skip as `no_change` before a baseline exists.
- `git_history` per-project commit counts must be close to physical
  `git rev-list --count HEAD` for each of the seven repos, and old groups such
  as `project/uw-ios-baseline` must not affect current project counts.
- `reactive_dependency_tracer` without `reactive_facts.json` reports missing
  input rather than usable reactive graph coverage.
- `hot_path_profiler` without trace files reports not-applicable/missing-input
  rather than successful profiler coverage.

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
  - `cross_module_contract`: snapshot and consumer edge counts per project.
  - `cross_repo_version_skew`: skew groups and affected projects.
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

1. Runner outcome persistence and reporting semantics.
2. Clean old group cleanup / graph scoping safeguards.
3. `git_history` and `code_ownership` baseline correctness.
4. `public_api_surface` artifact completeness.
5. `arch_layer` iOS module graph.
6. `cross_module_contract` snapshot/correlation behavior.
7. `cross_repo_version_skew` computation/persistence.
8. `reactive_dependency_tracer` and `hot_path_profiler` missing-input display.
9. Full sequential rebaseline and numeric report.

## Open Questions

- Should `PublicApiSurface` use generated `.swiftinterface` only, or should the
  repair add a source-based fallback for repos where interface generation fails?
- Should old project groups be deleted globally during rebaseline, or should the
  repair add project-scoped uniqueness that makes old groups harmless first?
- Which reactive helper should generate `reactive_facts.json` for Swift, and
  should those artifacts be committed to the dedicated clone or generated only
  during rebaseline?
