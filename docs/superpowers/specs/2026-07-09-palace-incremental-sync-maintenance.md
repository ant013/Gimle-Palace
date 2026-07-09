# Spec — Palace incremental sync maintenance and extractor fallback removal

**Status:** draft for operator review (2026-07-09).  
**Grounded in:** `origin/develop` / `develop` @ `172cf8d1188d694631e80177d4ef052832c72686`.  
**Owner:** design = Codex; implementation = palace-mcp slice(s) after approval.  
**Origin:** live dogfood run on 2026-07-09 across HorizontalSystems iOS repos.

## Problem

The operator needs Palace to stay synchronized with active iOS repos several
times per day. The latest measured run completed, but the end-to-end sync took
about **1h 38m**:

- git updates across 19 HorizontalSystems repos: about **4s**;
- `unstoppable-wallet-ios` SCIP emit: **498s**, emitted 6,129 docs and
  1,212,437 occurrences;
- `stable-wallet-ios` thin SCIP emit: **318s**, emitted 226 docs and 30,127
  occurrences;
- `uw-ios-app` `project_analyze(mode=incremental)`: **3,778s**;
- `stable-wallet-ios` `project_analyze(mode=incremental)`: **841s**.

Run-level incremental orchestration worked, but the expensive Swift extractors
still fell back to full work inside the run. The logs showed:

- `symbol_index_swift.tantivy.plan` with `tantivy_mode="full_reprocess"`;
- `graph_mode="full"`;
- `graph_fallback_reason="previous_commit_missing"`;
- body-hash mismatch on a small changed-file set for `uw-ios-app`, and a larger
  changed/removed set for `stable-wallet-ios`.

That means `project_analyze` selected incremental correctly, but the extractor
could not prove a safe previous baseline and chose the full path.

## Clarification: do not exclude the UW project

Do **not** exclude the real `unstoppable-wallet-ios` project from Palace. It is
the main `uw-ios-app` target and must remain fully indexed.

The exclusion discussed here is only for the nested path:

```text
stable-wallet-ios/unstoppable/
```

`stable-wallet-ios` contains `unstoppable/` as a submodule or embedded checkout.
When Palace scans `stable-wallet-ios`, audit-style filesystem walkers can walk
that subtree and scan the whole UW app again as if it were part of stable. That
duplicates work and pollutes stable's scope. The intended policy is:

- `uw-ios-app`: scan `/.../unstoppable-wallet-ios` normally;
- `stable-wallet-ios`: scan stable's own files, but exclude `unstoppable/**`
  plus generated/build/vendor trees.

## Assumptions

- Mainline remains `develop`; all implementation lands by feature branch and PR.
- The hot path is iOS Swift sync for `uw-ios-app` and `stable-wallet-ios`.
- `xcodebuild` / SCIP emit time is a real floor; this spec targets graph/analyze
  work after SCIP is emitted.
- Existing incremental work is partially live:
  - `project_analyze` accepts and reports `mode=incremental`;
  - `symbol_index_swift` can attempt selected-path Tantivy/graph work when
    `PALACE_INCREMENTAL_INGEST=true`;
  - `call_edge_swift` has an incremental selected-source path;
  - audit extractors vary by extractor and still need scope hygiene.
- A one-time full baseline per project is acceptable after a schema or state
  migration. Repeated full rebuilds during normal sync are not acceptable.

## Scope

This spec covers a repeatable operator workflow and the code changes required
to make that workflow fast and trustworthy:

1. sequential repo sync/update workflow for all mounted repos;
2. direct verification queries after sync, not just "command exited 0";
3. durable baseline state so Swift extractors do not fall back with
   `previous_commit_missing`;
4. project-scoped path exclusions so stable does not scan nested UW;
5. performance acceptance gates for 1-file, 10-file, and no-change updates.

Out of scope:

- replacing SCIP emit or removing the `xcodebuild` floor;
- changing git remotes or branch policies in upstream HorizontalSystems repos;
- excluding `uw-ios-app` from Palace;
- broad extractor rewrites unrelated to sync latency.

## Current Code Facts

- `services/palace-mcp/src/palace_mcp/project_analyze.py` decides run-level
  `full` vs `incremental`, creates per-extractor checkpoints, skips known global
  extractors on incremental runs, and reports per-checkpoint mode.
- `services/palace-mcp/src/palace_mcp/extractors/symbol_index_swift.py`:
  - compares current SCIP file body hashes with `:File.body_hash`;
  - attempts incremental only when `PALACE_INCREMENTAL_INGEST` is enabled and
    the changed ratio is below threshold;
  - calls `_read_existing_commit_sha()` before deriving the incremental graph
    scope;
  - returns `previous_commit_missing` when existing `:File.commit_sha` values
    do not yield exactly one previous commit;
  - falls back to full graph/Tantivy work when selected paths cannot be derived.
- `services/palace-mcp/src/palace_mcp/extractors/call_edge_swift.py` already
  has selected-source incremental mechanics, but it requires a configured v5
  IndexStore path and still needs operational baseline evidence.
- `services/palace-mcp/src/palace_mcp/extractors/foundation/walk.py` and
  `semgrep_runner.py` support extra directory excludes, but there is no accepted
  project-level exclude contract yet for `stable-wallet-ios/unstoppable/**`.

## Target Workflow

### Phase 0 — Manual Baseline and Observability

1. Run a one-time full baseline for each Palace project that lacks valid Swift
   baseline state.
2. Record a durable per-project baseline after every successful
   `symbol_index_swift` run:
   - project slug and `group_id`;
   - repo HEAD commit;
   - SCIP file path and digest;
   - body-hash manifest digest and file count;
   - previous successful `symbol_index_swift` run id;
   - schema/state version;
   - timestamp and extractor mode.
3. Expose baseline health in the analyze report and logs:
   - `baseline_state=present|missing|invalid`;
   - `baseline_commit_sha`;
   - explicit fallback reason when invalid.

Acceptance:

- A fresh project reports `baseline_state=missing` and requires one full run.
- A second run with no content changes reports `body_hash_match` and skips
  Swift reingest.
- A second run with one changed Swift file does not report
  `previous_commit_missing`.

### Phase 1 — Sequential Repo Sync Command

Add or update an operator script/runbook that performs repo updates in a stable
order:

1. enumerate mounted repos under the configured HorizontalSystems root;
2. for each repo:
   - `git fetch --prune`;
   - resolve the expected branch or explicit configured ref;
   - fast-forward only when clean and fast-forwardable;
   - for repos without upstream tracking, compare to the explicit remote branch;
   - update submodules only where the project policy requires it;
3. collect per-repo status:
   - local HEAD SHA;
   - upstream/ref SHA;
   - ahead/behind counts;
   - dirty tracked files;
   - dirty untracked files;
   - submodule SHA and dirty state.

Acceptance:

- 19/19 HorizontalSystems repos report `ahead=0`, `behind=0` or a named
  intentional exception.
- Repos without upstream tracking are not marked "unknown" if the explicit
  configured ref matches.
- Dirty pre-existing files are reported, not reverted.
- The script prints total git-update wall time.

### Phase 2 — SCIP Emit Per Project

Run SCIP emit after git sync, project by project:

1. `uw-ios-app`: emit from the real `unstoppable-wallet-ios` repo.
2. `stable-wallet-ios`: emit from stable only; do not treat
   `stable-wallet-ios/unstoppable/` as stable-owned source.
3. Store artifact metadata:
   - SCIP path;
   - byte size;
   - document count;
   - occurrence count;
   - wrapper exit code;
   - underlying `xcodebuild` exit code when available;
   - elapsed seconds.

Acceptance:

- SCIP emit can be nonzero internally only when the wrapper still emits a valid
  SCIP and records the build failure reason.
- No Palace analyze run starts without a fresh SCIP artifact or an explicit
  "reuse existing SCIP" decision in the report.

### Phase 3 — Palace Analyze Incremental

For each updated project, run `project_analyze(mode=incremental)` only after its
SCIP artifact and baseline state are known.

Required extractor behavior:

1. `symbol_index_swift`:
   - uses durable baseline state, not only current `:File.commit_sha`
     aggregation, to derive `previous_commit_sha`;
   - falls back to full only for first baseline, forced run, schema mismatch,
     truncated git diff, SCIP/git path mismatch, or high changed ratio;
   - logs `graph_mode=incremental` for small Swift changes;
   - deletes/upserts only changed/removed file docs in Tantivy;
   - keeps live unchanged symbols fresh and protected from prune.
2. `call_edge_swift`:
   - uses the same change-set contract;
   - skips clean runs;
   - replaces caller edges for changed caller files;
   - deletes stale callee edges when changed files rename or move symbols;
   - reports `MISSING_INPUT` only when IndexStore is genuinely unavailable and
     the project policy allows the degraded mode.
3. Audit extractors:
   - consume project-level exclude paths;
   - for stable, exclude `unstoppable/**`;
   - use changed-file scope where the extractor has a safe per-file replace
     contract;
   - mark inherently global findings with `stale_since` instead of blocking the
     hot path.

Acceptance:

- Small `uw-ios-app` update: no `symbol_index_swift` full fallback after a
  valid baseline exists.
- Small `stable-wallet-ios` update: stable analyze does not scan files under
  `unstoppable/**`.
- Incremental run report lists per-extractor mode as
  `incremental|skipped|stale|missing_input`, not an ambiguous run-level summary.

### Phase 4 — Direct Verification Queries

After each sync, run direct checks and save a compact status artifact:

Git checks:

- repo HEAD equals expected remote/ref for every configured repo;
- submodule SHA equals expected SHA where submodules are pinned;
- tracked dirty files are listed.

Palace checks:

- latest `AnalysisRun` per project has the expected HEAD commit;
- latest run status is `SUCCEEDED` or `SUCCEEDED_WITH_SKIPS`;
- no checkpoint has `RUN_FAILED`;
- no checkpoint has unexpected `MISSING_INPUT`;
- `symbol_index_swift` log/metadata for small changes has
  `graph_mode=incremental`;
- no `graph_fallback_reason=previous_commit_missing` after baseline;
- `:Project.commit_sha`, `:File.commit_sha`, and baseline commit agree;
- navigation smoke queries return data:
  - `semantic_search`;
  - `find_references`;
  - `get_code_snippet`;
  - `trace_call_path` when IndexStore is available.

Acceptance:

- The operator can answer "all updated?" from one status report.
- The report includes elapsed times for git, SCIP, analyze, and total.
- The report includes explicit exceptions instead of hiding skips.

### Phase 5 — Performance Gates

Use real repos, not toy-only fixtures, for final validation:

| Scenario | Expected graph/analyze behavior | Target after SCIP |
|---|---|---|
| no source changes | Swift symbol skip, call-edge skip | `< 2 min` |
| 1 Swift file changed | file-scoped symbol/Tantivy/call-edge work | `< 5 min` |
| 10 Swift files changed | file-scoped graph work, no full fallback | `< 10 min` |
| high churn / refactor | explicit full fallback with reason | no silent fallback |

End-to-end time can exceed these targets because SCIP emit is still bounded by
`xcodebuild`. The operator-facing SLA is:

```text
SCIP emit time + <10 minutes graph/analyze time for ordinary small updates.
```

## Affected Areas

- `services/palace-mcp/src/palace_mcp/project_analyze.py`
- `services/palace-mcp/src/palace_mcp/extractors/symbol_index_swift.py`
- `services/palace-mcp/src/palace_mcp/extractors/call_edge_swift.py`
- `services/palace-mcp/src/palace_mcp/extractors/foundation/incremental_scope.py`
- `services/palace-mcp/src/palace_mcp/extractors/foundation/walk.py`
- `services/palace-mcp/src/palace_mcp/extractors/foundation/semgrep_runner.py`
- audit extractors that run semgrep or filesystem walkers
- project configuration / settings for per-project exclude paths
- operator scripts/runbooks for repo sync, SCIP emit, analyze, and status
- integration tests under `services/palace-mcp/tests/extractors/integration/`
- unit tests for settings, path-scope, and fallback decision logging

## Implementation Slices

1. **Baseline state and fallback diagnostics**
   - Add durable Swift symbol baseline state.
   - Write state only after successful `symbol_index_swift`.
   - Read baseline before `_derive_incremental_graph_scope`.
   - Add tests for missing, valid, schema-mismatched, and corrupted baseline.

2. **Remove `previous_commit_missing` for normal incremental runs**
   - Prefer durable baseline commit over ambiguous `:File.commit_sha` aggregate.
   - Preserve current safety fallbacks for mismatched paths or truncated diffs.
   - Add an integration test proving one changed file uses incremental mode
     after a baseline.

3. **Stable path-exclude contract**
   - Add project-level exclude globs.
   - Thread excludes into shared walkers and semgrep-backed extractors.
   - Configure stable to exclude `unstoppable/**`.
   - Add a fixture test where stable contains a nested `unstoppable/` tree and
     the extractor never receives those paths.

4. **Operator sync/status wrapper**
   - Implement the sequential repo sync + SCIP + analyze runner or document it
     as a single runbook command if code already exists.
   - Emit JSON and Markdown status with timings.
   - Include direct git and Palace verification results.

5. **Live performance validation**
   - Run baseline full once.
   - Run no-change, 1-file, and 10-file updates on real `uw-ios-app`.
   - Run stable with nested `unstoppable/` present and verify it is excluded.
   - Record actual timings in `docs/research/` or an audit report.

## Verification Plan

Local checks for palace-mcp changes:

```bash
cd services/palace-mcp
uv run ruff check
uv run ruff format --check
uv run mypy src/
uv run pytest
```

Targeted tests before full suite:

- `uv run pytest tests/extractors/unit/test_symbol_index_swift.py`
- `uv run pytest tests/extractors/integration/test_symbol_index_swift_integration.py`
- `uv run pytest tests/extractors/unit/test_incremental_scope.py`
- `uv run pytest tests/extractors/integration/test_call_edge_swift_integration.py`
- semgrep/audit extractor tests touched by path excludes
- operator wrapper tests if a new script is added

Live verification:

- run git sync across all configured repos;
- emit SCIP for `uw-ios-app` and `stable-wallet-ios`;
- run `project_analyze(mode=incremental)` for both;
- inspect logs/status for absent `previous_commit_missing`;
- run direct Palace graph/search smoke queries;
- archive elapsed-time report.

## Risks

- Durable baseline state can make an unsafe incremental decision if written
  before a failed or partial run. Mitigation: write only after successful
  extractor finalization and include schema/digest checks.
- Path excludes can hide real stable-owned code if globs are too broad.
  Mitigation: use project-specific `unstoppable/**`, not a global
  `unstoppable*` rule.
- `xcodebuild` remains the dominant cost for some changes. Mitigation: report
  SCIP time separately from graph/analyze time.
- Audit extractors may not all have safe per-file replacement semantics.
  Mitigation: only scope extractors that have delete/replace tests; mark global
  results stale otherwise.

## Open Questions

1. Where should the durable baseline live: Neo4j `:ExtractorBaseline`, local
   JSON artifact under the repo runtime state, or both?
2. Should `stable-wallet-ios/unstoppable/` be excluded only from audit walkers,
   or also from any generic file inventory extractor that contributes stable
   project files?
3. Should the operator wrapper live under `paperclips/scripts/`, `services/`,
   or a new `scripts/` path?
4. What is the acceptable stable end-to-end target after SCIP: `<5 min` or
   `<10 min`?

