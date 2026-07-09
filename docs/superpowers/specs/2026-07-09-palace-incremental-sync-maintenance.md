# Spec rev2 - Palace incremental sync maintenance and extractor fallback removal

**Status:** rev2 - revised after four-lens voltAgents review
(architecture, performance, QA, MCP implementation) on 2026-07-09.  
**Grounded in:** `origin/develop` / `develop` @
`172cf8d1188d694631e80177d4ef052832c72686`.  
**Branch:** `feature/palace-incremental-sync-performance-spec`.  
**Owner:** design = Codex; implementation = palace-mcp slice(s) after
operator approval.  
**Origin:** live dogfood run on 2026-07-09 across HorizontalSystems iOS repos.

## Rev2 verdict

Rev1 identified the right operator pain but was **NO-GO for implementation**:
it treated `previous_commit_missing` as the main fix while leaving the durable
baseline authority, commit-field contract, project exclude semantics, hidden
O(project) work, and live evidence schema under-specified.

Rev2 turns those review findings into binding design decisions. Implementation
must not start from rev1 behavior or rev1 open questions.

## Problem

The operator needs Palace to stay synchronized with active iOS repos several
times per day. The latest measured run completed, but end-to-end sync took
about **1h 38m**:

- git updates across 19 HorizontalSystems repos: about **4s**;
- `unstoppable-wallet-ios` SCIP emit: **498s**, emitted 6,129 docs and
  1,212,437 occurrences;
- `stable-wallet-ios` thin SCIP emit: **318s**, emitted 226 docs and 30,127
  occurrences;
- `uw-ios-app` `project_analyze(mode=incremental)`: **3,778s**;
- `stable-wallet-ios` `project_analyze(mode=incremental)`: **841s**.

Run-level incremental orchestration worked, but expensive extractor internals
still behaved like a full-project run. The logs showed:

- `symbol_index_swift.tantivy.plan` with `tantivy_mode="full_reprocess"`;
- `graph_mode="full"`;
- `graph_fallback_reason="previous_commit_missing"`;
- body-hash mismatch on a small changed-file set for `uw-ios-app`, and a larger
  changed/removed set for `stable-wallet-ios`.

Removing `previous_commit_missing` is necessary, but not sufficient. The
current implementation still has hidden O(project) work in incremental-looking
paths:

- `symbol_index_swift` parses the SCIP snapshot before decisions, hashes all
  SCIP source files, reads all stored file hashes, loops occurrences for the
  in-degree counter, and may refresh graph state over the full snapshot.
- `call_edge_swift` can select changed source files, but IndexStore collection
  still walks global unit/record state before filtering.

The target is therefore not "make the mode label say incremental." The target
is a measurable reduction in graph/analyze work after SCIP exists.

## Non-negotiable design decisions

### D1. Baseline authority is Neo4j

The durable baseline authority is a Neo4j node, not a local JSON file:

```cypher
(:ExtractorBaseline {
  project_id,
  project_slug,
  extractor,
  baseline_kind,
  state_version,
  commit_sha,
  indexed_commit,
  scip_digest,
  scip_path,
  scip_document_count,
  scip_occurrence_count,
  body_hash_manifest_digest,
  file_count,
  successful_run_id,
  status,
  invalid_reason,
  updated_at
})
```

Required identity:

```text
(project_id, extractor, baseline_kind)
```

For this work:

```text
extractor = "symbol_index_swift"
baseline_kind = "swift_symbol_scope"
state_version = 1
```

Local JSON artifacts may still be written for evidence/debugging, but they are
not authoritative for incremental decisions.

### D2. Durable baseline is distinct from delta-resolution artifacts

Existing run-scoped delta-resolution artifacts are not replaced by this
baseline. They are captured before some graph mutations so companion extractors
such as `dead_code` can compare before/after state.

The new `:ExtractorBaseline` is written only after `symbol_index_swift` has
completed successfully and its graph/Tantivy state is safe to use as the next
run's base. A failed or partial run must not advance it.

### D3. Commit contract uses real Palace fields

Do not introduce or validate against a fictional `:Project.commit_sha`.

Verification and delta derivation must use:

- project-level current indexed commit: `Project.indexed_commit` where the
  existing project model/reporting exposes it;
- file-level commit fields: `coalesce(f.last_seen_in_commit, f.commit_sha)`;
- durable baseline commit: `:ExtractorBaseline.commit_sha`;
- repo HEAD: `git rev-parse HEAD`.

Acceptance must compare these fields explicitly. If a field is absent for a
project, the report must say which contract is unavailable and why.

### D4. One shared Swift delta scope

`symbol_index_swift`, `call_edge_swift`, and Swift audit extractors must not
derive incompatible changed-file scopes.

Introduce a shared Swift delta scope contract:

```text
SwiftDeltaScope {
  project_id
  project_slug
  baseline_commit_sha
  head_commit_sha
  mode: full | incremental | skip
  reason
  changed_paths
  removed_paths
  scip_paths_digest
  body_hash_manifest_digest
  validated_by: symbol_index_swift | baseline_only
}
```

For runs where `symbol_index_swift` executes, it is the preferred producer of
the validated scope because it can intersect git changes, SCIP document paths,
and body hashes. `call_edge_swift` consumes that scope when present. If the
scope is absent, `call_edge_swift` may use a baseline-only git diff scope, but
the report must label it as less validated.

### D5. `stable-wallet-ios/unstoppable/**` is a repo-relative path glob

Do **not** exclude the real `unstoppable-wallet-ios` Palace project. It remains
the main `uw-ios-app` target.

The exclusion applies only when scanning the `stable-wallet-ios` project:

```text
unstoppable/**
```

Matcher semantics:

- input path is POSIX repo-relative;
- glob is anchored at the stable repo root;
- `unstoppable/**` excludes `stable-wallet-ios/unstoppable/...`;
- it must not exclude `Sources/UnstoppableFeature.swift`;
- it must not affect the separate `uw-ios-app` project.

This is not just an audit-only rule. It applies to all stable project file
enumeration paths that can contribute stable-owned files or findings:

- semgrep-backed extractors;
- shared filesystem walkers;
- hotspot/file inventory walkers;
- any generic project file inventory used by analyze/status.

SCIP emit remains governed by the stable emit script; this spec requires Palace
file enumeration not to treat the nested UW checkout as stable-owned input.

### D6. Operator wrapper is observability, not the main latency fix

Git sync took about 4 seconds in the measured run. The sequential update/status
wrapper is still useful because it answers "all repos updated?" and prevents
ambiguous state, but it is not the performance solution. The performance
solution is extractor delta correctness plus removal or scheduling of hidden
O(project) work.

### D7. Performance gates require internal counters

A run is not accepted as "incremental" merely because checkpoint mode says so.
Every relevant extractor must expose counters in structured report metadata:

- SCIP parse time and bytes;
- SCIP documents scanned;
- SCIP occurrences iterated;
- source files hashed;
- Neo4j file-hash rows read;
- Neo4j symbols/files/edges upserted and deleted;
- Tantivy docs deleted and written;
- IndexStore units, records, and occurrences visited;
- changed and removed path counts;
- fallback reason.

The performance gates in this spec are invalid unless these counters are
available in the evidence bundle.

## Assumptions

- Mainline remains `develop`; all implementation lands by feature branch and PR.
- The hot path is iOS Swift sync for `uw-ios-app` and `stable-wallet-ios`.
- `xcodebuild` / SCIP emit time is a real floor; this spec targets graph/analyze
  work after SCIP is emitted.
- A one-time full baseline per project is acceptable after adding the baseline
  schema or invalidating state.
- Repeated full rebuilds during normal small syncs are not acceptable.
- Global analysis that cannot be made file-local must move off the hot path and
  carry `stale_since` metadata.

## Scope

In scope:

1. durable Swift baseline state in Neo4j;
2. shared Swift delta scope;
3. removal of normal `previous_commit_missing` fallback after a valid baseline;
4. instrumentation that proves or falsifies hidden O(project) work;
5. file-scoped or scheduled behavior for `symbol_index_swift` and
   `call_edge_swift`;
6. project-level repo-relative exclude globs, especially stable's
   `unstoppable/**`;
7. sequential repo sync/status wrapper with direct verification queries;
8. live evidence bundles for no-change, 1-file, 10-file, stable-exclude, and
   fallback scenarios.

Out of scope:

- replacing SCIP emit or removing the `xcodebuild` floor;
- changing git remotes or branch policies in upstream HorizontalSystems repos;
- excluding `uw-ios-app` from Palace;
- broad extractor rewrites unrelated to sync correctness/latency;
- changing existing run-scoped delta-resolution artifacts except to document
  their separation from durable baseline state.

## Current Code Facts

- `project_analyze.py` decides run-level `full` vs `incremental`, creates
  per-extractor checkpoints, skips known global extractors on incremental runs,
  and reports per-checkpoint mode.
- `symbol_index_swift.py`:
  - compares current SCIP file body hashes with stored `:File.body_hash`;
  - attempts incremental only when `PALACE_INCREMENTAL_INGEST` is enabled and
    changed ratio is below threshold;
  - currently calls `_read_existing_commit_sha()` before deriving incremental
    graph scope;
  - returns `previous_commit_missing` when stored file commit state does not
    yield exactly one previous commit;
  - still performs full-snapshot work in paths that can be labelled incremental.
- `call_edge_swift.py`:
  - can pass `selected_source_files` to IndexStore collection;
  - still derives scope independently from shared file commit aggregation;
  - returns `MISSING_INPUT` when no v5 IndexStore is configured;
  - emits useful scan counters only in a free-form message today.
- `walk.py` and `semgrep_runner.py` support additive directory-name excludes,
  not repo-relative glob semantics.
- Some extractors bypass shared walkers/runners and must be inventoried before
  claiming project-level excludes.

## Implementation Phases

### Phase 0 - Baseline schema, reporting, and migration

1. Add `:ExtractorBaseline` schema/support for the identity in D1.
2. Add read/write helpers, preferably near existing extractor foundation code.
3. Write baseline only after successful `symbol_index_swift` finalization.
4. Do not advance baseline on:
   - extractor exception;
   - partial Tantivy write;
   - graph write failure;
   - `SUCCEEDED_WITH_SKIPS` where `symbol_index_swift` did not establish a new
     safe base.
5. Add report metadata:
   - `baseline_state=missing|present|invalid`;
   - `baseline_commit_sha`;
   - `baseline_state_version`;
   - `baseline_invalid_reason`;
   - `baseline_successful_run_id`.

Acceptance:

- Fresh project reports `baseline_state=missing` and requires one full
  baseline.
- A valid baseline is readable by `symbol_index_swift` and shared delta scope.
- A failed/partial run does not change `:ExtractorBaseline.successful_run_id` or
  `commit_sha`.
- Schema mismatch produces explicit full fallback with
  `baseline_state=invalid`, not `previous_commit_missing`.

### Phase 1 - Shared Swift delta scope

1. Implement `SwiftDeltaScope` helper.
2. Derive scope from:
   - baseline commit;
   - repo HEAD;
   - git diff from baseline to HEAD;
   - SCIP document paths when available;
   - current body-hash manifest when available.
3. Preserve hard full fallbacks for:
   - missing baseline;
   - invalid baseline schema;
   - `git_diff_error`;
   - `git_diff_truncated`;
   - `scip_path_mismatch`;
   - `body_hash_changed_mismatch`;
   - `body_hash_removed_mismatch`;
   - high changed ratio.
4. Store the resolved scope in structured run/checkpoint metadata or a
   run-scoped artifact referenced by the checkpoint.
5. Make `call_edge_swift` consume the produced scope when available.

Acceptance:

- After a successful baseline, a 1-file Swift change does not produce
  `previous_commit_missing`.
- Each allowed fallback reason has a unit test and appears verbatim in the
  report.
- `call_edge_swift` reports whether its scope was `validated_by=symbol_index_swift`
  or `validated_by=baseline_only`.
- `call_edge_swift` integration tests stop patching scope derivation for the
  baseline happy path; at least one test exercises real baseline-derived scope.

### Phase 2 - `symbol_index_swift` hidden O(project) reduction

This phase is required before claiming the Phase 6 performance SLA.

Required behavior:

1. No-change path:
   - must not iterate all SCIP occurrences;
   - must not refresh the full graph state;
   - should validate baseline/scip/body-hash digest cheaply and skip.
2. Changed-file path:
   - avoid repeated full SCIP occurrence passes;
   - filter by selected paths as early as possible;
   - update only changed/removed Tantivy docs;
   - update only changed/removed graph files/symbols plus the minimum liveness
     metadata needed to protect unchanged symbols from prune;
   - update or deliberately defer the in-degree counter instead of rebuilding it
     from every USE occurrence on every small change.
3. If a full SCIP parse is unavoidable for a protobuf-level reason, it must be
   measured separately and bounded in the SLA as "parse floor", not hidden
   inside graph update time.

Acceptance:

- No-change `uw-ios-app` after valid baseline: `symbol_index_swift` structured
  counters show zero full occurrence iteration and no full graph refresh.
- 1-file and 10-file changes: occurrence iteration and writes are proportional
  to selected files or explicitly reported as unavoidable parse floor.
- `symbol_index_swift` no longer reports `mode=incremental` while doing
  full-snapshot graph/Tantivy work.

### Phase 3 - `call_edge_swift` hot-path policy

`call_edge_swift` must not silently spend O(project) work on every small update.

Implementation may choose one of two accepted strategies:

1. **True file-scoped IndexStore path**
   - use `SwiftDeltaScope`;
   - visit only units/records needed for changed caller/callee files;
   - replace caller edges for changed files;
   - delete stale callee edges for changed/removed files;
   - expose IndexStore units/records/occurrences visited.
2. **Scheduled/stale policy**
   - if IndexStore cannot provide efficient file-scoped collection, remove
     `call_edge_swift` from the ordinary hot path;
   - mark call graph results with `stale_since=<baseline_commit_or_head>`;
   - run call-edge refresh on a schedule or explicit full/deep sync.

Acceptance:

- The implementation must pick one strategy before merge.
- If strategy 1 is picked, a 1-file change proves bounded IndexStore counters.
- If strategy 2 is picked, ordinary incremental sync does not block on
  `call_edge_swift`, and the report visibly marks call graph freshness.
- Expected `MISSING_INPUT` for IndexStore is controlled by a per-project
  allowlist in the operator report schema, not hidden as generic success.

### Phase 4 - Stable project exclude contract

1. Add project-level repo-relative exclude globs to settings/config.
2. Define one matcher used by all Palace file enumeration paths.
3. Configure `stable-wallet-ios` with:

```text
unstoppable/**
```

4. Inventory extractors and classify each as:
   - `honors_project_excludes`;
   - `does_not_enumerate_files`;
   - `must_be_updated`;
   - `out_of_hot_path_stale_since`.
5. Update semgrep-backed and walker-backed extractors that are in stable's hot
   path.

Acceptance:

- Fixture: `stable-wallet-ios/unstoppable/App.swift` is excluded.
- Fixture: `stable-wallet-ios/Sources/UnstoppableFeature.swift` is not excluded.
- Fixture/live config: separate `uw-ios-app` project still indexes/scans the
  real `unstoppable-wallet-ios` repo.
- A stable analyze evidence bundle lists zero scanned paths under
  `unstoppable/`.

### Phase 5 - Sequential sync/status wrapper

Add or update an operator wrapper/runbook that performs:

1. repo enumeration from configured HorizontalSystems root;
2. per-repo `git fetch --prune`;
3. fast-forward only when clean and fast-forwardable;
4. explicit remote/ref comparison for repos without upstream tracking;
5. submodule update only where project policy requires it;
6. SCIP emit per project;
7. `project_analyze(mode=incremental)` per project;
8. direct git and Palace verification;
9. JSON and Markdown status output.

The wrapper must report, per repo/project:

- local HEAD SHA;
- upstream/ref SHA;
- ahead/behind counts;
- dirty tracked files;
- dirty untracked files;
- submodule SHA and dirty state;
- SCIP metadata;
- analyze run id/status;
- checkpoint modes/outcomes;
- expected and unexpected `MISSING_INPUT`;
- elapsed times for git, SCIP, analyze, and total.

Acceptance:

- 19/19 HorizontalSystems repos report `ahead=0`, `behind=0` or a named
  intentional exception.
- Repos without upstream tracking are not marked unknown when explicit ref
  matches.
- Dirty pre-existing files are reported, not reverted.
- Git sync remains measured separately from SCIP/analyze latency.

### Phase 6 - Live evidence and performance gates

Use real repos, not toy-only fixtures, for final validation.

Evidence bundle schema:

```text
scenario
project_slug
before_sha
after_sha
changed_paths
removed_paths
scip_path
scip_digest
scip_document_count
scip_occurrence_count
git_elapsed_s
scip_elapsed_s
analyze_elapsed_s
total_elapsed_s
analysis_run_id
checkpoint_summary
baseline_state
swift_delta_scope
fallback_reasons
extractor_counters
expected_missing_input
unexpected_missing_input
smoke_query_results
```

Required scenarios:

| Scenario | Required behavior | Target after SCIP |
|---|---|---|
| no source changes | Swift symbol skip, no full occurrence iteration | `< 2 min` |
| 1 Swift file changed | file-scoped symbol/Tantivy work, no hidden full graph refresh | `< 5 min` |
| 10 Swift files changed | file-scoped graph work, no silent full fallback | `< 10 min` |
| stable with nested UW | zero scanned stable paths under `unstoppable/` | `< 5 min` graph/analyze |
| high churn/refactor | explicit full fallback with reason | no silent fallback |

End-to-end time can exceed these targets because SCIP emit is still bounded by
`xcodebuild`. The operator-facing SLA is:

```text
SCIP emit time + <10 minutes graph/analyze time for ordinary small uw-ios-app updates.
SCIP emit time + <5 minutes graph/analyze time for ordinary small stable-wallet-ios updates.
```

## Operator verification contract

The report must not use vague checks like "query returns data." It must define
exact smoke inputs and success conditions per project.

Minimum Palace checks:

- latest `AnalysisRun` for the project has expected HEAD/indexed commit;
- run status is `SUCCEEDED` or `SUCCEEDED_WITH_SKIPS`;
- no checkpoint has `RUN_FAILED`;
- no checkpoint has unexpected `MISSING_INPUT`;
- expected `MISSING_INPUT` is listed by `(project, extractor, reason)`;
- `symbol_index_swift` has no `previous_commit_missing` after valid baseline;
- baseline commit and run metadata match the real contract from D3;
- `semantic_search`, `find_references`, `get_code_snippet`, and
  `trace_call_path` checks assert `ok`, warning state, and minimum result count
  only where deterministic.

## Affected Areas

- `services/palace-mcp/src/palace_mcp/project_analyze.py`
- `services/palace-mcp/src/palace_mcp/extractors/base.py`
- `services/palace-mcp/src/palace_mcp/extractors/runner.py`
- `services/palace-mcp/src/palace_mcp/extractors/symbol_index_swift.py`
- `services/palace-mcp/src/palace_mcp/extractors/call_edge_swift.py`
- `services/palace-mcp/src/palace_mcp/extractors/foundation/incremental_scope.py`
- new or updated Swift delta/baseline helper under extractor foundation
- `services/palace-mcp/src/palace_mcp/extractors/foundation/walk.py`
- `services/palace-mcp/src/palace_mcp/extractors/foundation/semgrep_runner.py`
- semgrep-backed extractors, especially direct semgrep callers
- hotspot/file inventory walkers
- settings/config for per-project exclude globs and expected missing-input
  allowlists
- operator scripts/runbooks for repo sync, SCIP emit, analyze, and status
- integration tests under `services/palace-mcp/tests/extractors/integration/`
- unit tests for settings, path-scope, baseline state, and fallback decision
  logging

## Test Plan

Local checks for palace-mcp changes:

```bash
cd services/palace-mcp
uv run ruff check
uv run ruff format --check
uv run mypy src/
uv run pytest
```

Targeted tests before full suite:

- baseline helper unit tests;
- `uv run pytest tests/extractors/unit/test_symbol_index_swift.py`;
- `uv run pytest tests/extractors/integration/test_symbol_index_swift_integration.py`;
- `uv run pytest tests/extractors/unit/test_incremental_scope.py`;
- `uv run pytest tests/extractors/integration/test_call_edge_swift_integration.py`;
- project-exclude matcher tests;
- semgrep/audit extractor tests touched by path excludes;
- operator wrapper tests if a script is added.

Required negative tests:

- missing baseline -> full fallback;
- schema mismatch -> full fallback;
- `git_diff_error` -> full fallback;
- `git_diff_truncated` -> full fallback;
- `scip_path_mismatch` -> full fallback;
- `body_hash_changed_mismatch` -> full fallback;
- `body_hash_removed_mismatch` -> full fallback;
- failed/partial `symbol_index_swift` does not advance durable baseline;
- stable `unstoppable/**` excluded;
- `Sources/UnstoppableFeature.swift` not excluded;
- real `uw-ios-app` not affected by stable excludes;
- unexpected `MISSING_INPUT` fails the operator report.

Live verification:

- run git sync across all configured repos;
- emit SCIP for `uw-ios-app` and `stable-wallet-ios`;
- run `project_analyze(mode=incremental)` for both;
- inspect structured status for absent `previous_commit_missing`;
- verify expected/actual missing-input classification;
- run direct Palace graph/search smoke queries;
- commit or attach evidence bundles under `docs/research/` or the agreed
  audit-report location.

## Risks

- Baseline split-brain if local artifacts are treated as authority. Mitigation:
  Neo4j `:ExtractorBaseline` is the only authority.
- Unsafe baseline advancement after partial failure. Mitigation: write baseline
  only after successful extractor finalization and test failure cases.
- Hidden O(project) loops can survive behind an incremental mode label.
  Mitigation: structured counters and Phase 2/3 gates.
- Path excludes can hide real stable-owned code if matching is too broad.
  Mitigation: anchored repo-relative glob semantics and negative tests.
- IndexStore may not support efficient file-scoped call-edge extraction.
  Mitigation: choose scheduled/stale policy instead of blocking hot sync.
- `xcodebuild` remains dominant for some changes. Mitigation: report SCIP time
  separately from graph/analyze time.

## Open Questions

No blocking design questions remain for implementation planning. The remaining
operator-tunable values are thresholds, not architecture:

- exact changed-ratio threshold for full fallback;
- final evidence artifact location if `docs/research/` is not preferred;
- final schedule for stale/global extractors after the hot path is fixed.

