# GIM-1491 Plan: Incremental ingest + soft-delete for palace-mcp

## Goal

Implement the v2.1 incremental ingest and soft-delete design for palace-mcp while preserving the spec's migration boundaries:

- Incremental post-change ingest for `uw-ios-baseline` completes in under 5 minutes for a small commit.
- Deleted Swift files and symbols are retained as `:Deprecated` with audit metadata instead of being hard-deleted.
- Revival and operator recovery paths remove deprecation safely and leave `:DeprecationEvent` evidence.
- MCP query behavior changes only through the staged Phase 4a/4b migration.

## Source of truth

- Spec: `docs/superpowers/specs/2026-06-05-incremental-ingest-design.md`
- Spec PR: <https://github.com/ant013/Gimle-Palace/pull/383>
- Spec merge commit: `2429f192138ad0f979b07725b46c8f35b31b6ae2`
- CTO verification: PR #383 is merged to `develop` and added the spec path above. The current CX worktree branch does not contain that merge commit, so reviewers must verify plan coverage against the PR/commit until this worktree is updated.

## Assumptions

- Implementation must follow spec v2.1 exactly; rename detection, hard delete, UI, and cross-module move reconciliation remain out of scope.
- Each migration phase is separately revertable and should normally land as a separate PR.
- Phase 4b is gated: do not flip `include_deprecated` defaults until Phase 4a has shipped and the monitoring window is explicitly accepted.
- Current CTO role does not implement code; implementation is delegated after plan-first review.

## Acceptance criteria

- The plan preserves the spec's six migration phases and does not combine Phase 4a with Phase 4b.
- Every implementation slice has an owner, affected paths, dependencies, and verification command or observation.
- The test plan covers the spec's named safety gates: two-phase threshold abort, stale file/symbol deprecation, revival, `embedding_symbol` skip-deprecated selection, `--force` audit, per-project flock, subprocess hardening, Phase 2-to-3 boundary, Phase 4a-to-4b behavior, all `palace.code.*` query filters, and the opt-in prune perf SLO.
- No implementation issue starts until plan-first review approves this plan.

## Slice plan

### 1. Schema + prune extractor scaffold

Owner: `CXPythonEngineer`

Affected paths:
- `services/palace-mcp/src/palace_mcp/extractors/base.py`
- `services/palace-mcp/src/palace_mcp/extractors/prune_swift_symbols/`
- `services/palace-mcp/src/palace_mcp/memory/constraints.py`
- `services/palace-mcp/tests/extractors/prune_swift_symbols/`

Work:
- Add `ExtractorRunContext.companion_run_id`.
- Add `prune_swift_symbols` package with extractor shell, Cypher constants, and hardened `git rev-parse HEAD` helper.
- Add schema constraints/indexes for `last_seen_in_run_id` and `:DeprecationEvent`.
- Keep extractor out of the default list in this slice.

Verification:
- `cd services/palace-mcp && uv run pytest tests/extractors/prune_swift_symbols/ -v -m "not perf"`
- Must include tests for no companion run ID, subprocess allowlist rejection, `shell=False`, absolute `/usr/bin/git`, PRECHECK no writes, and threshold abort before APPLY.

### 2. symbol_index_swift last-seen writes

Owner: `CXPythonEngineer`

Affected paths:
- `services/palace-mcp/src/palace_mcp/extractors/symbol_index_swift.py`
- Existing symbol-index Swift unit and integration tests.

Dependencies:
- Slice 1 schema additions.

Work:
- On every `:File` and `:Symbol` MERGE, set `last_seen_in_run_id`, `last_seen_at`, and `last_seen_in_commit`.
- Remove `:Deprecated`, `deprecated_at`, and `deprecated_in_commit` on revival.
- Replace prior `:LAST_SEEN_IN` relationship before creating the new one.

Verification:
- `cd services/palace-mcp && uv run pytest tests/extractors/unit/test_symbol_index_swift.py tests/extractors/integration/test_symbol_index_swift_integration.py -v`
- Must prove revival strips both label and properties, and each node has exactly one `:LAST_SEEN_IN` edge after repeated upserts.

### 3. Orchestrator gating + default prune enablement

Owner: `CXPythonEngineer`

Affected paths:
- `services/palace-mcp/src/palace_mcp/extractors/runner.py`
- `services/palace-mcp/src/palace_mcp/extractors/prune_swift_symbols/`
- `services/palace-mcp/src/palace_mcp/extractors/embedding_symbol/` or the repo's nearest existing embedding-symbol extractor module.
- Runner and prune integration tests.
- Embedding-symbol extractor tests.

Dependencies:
- Slices 1 and 2 complete.

Work:
- Add `prune_swift_symbols` after `symbol_index_swift` in the default extractor list.
- Pass `symbol_index_swift`'s run ID explicitly as `companion_run_id`.
- Gate prune so it runs only when `symbol_index_swift.ok` is true and `fatal_errors == 0`.
- Implement Python-driven APPLY batch accumulation and `:DeprecationEvent` creation.
- Add `WHERE NOT s:Deprecated` to the `embedding_symbol` source-symbol selection so deprecated symbols are skipped for embedding work.

Verification:
- `cd services/palace-mcp && uv run pytest tests/extractors/integration/ -k "prune or symbol_index or runner" -v`
- Must prove file deletion, method deletion, partial upstream failure skips prune, Phase 2-to-3 first enable avoids mass deprecation, batch counts accumulate correctly, and threshold abort leaves graph unchanged.
- Must prove `embedding_symbol` excludes deprecated symbols from source selection while still processing live symbols whose `embedding_input_hash` changed.

### 4a. MCP read filters with default include_deprecated=true

Owner: `CXMCPEngineer`

Affected paths:
- `services/palace-mcp/src/palace_mcp/code/`
- `services/palace-mcp/src/palace_mcp/code_composite.py`
- `services/palace-mcp/src/palace_mcp/mcp_server.py`
- MCP tool tests.

Dependencies:
- Slice 3 complete.

Work:
- Add `include_deprecated: bool = True` to the affected `palace.code.*` tools without changing default behavior.
- Add query predicates that honor explicit `include_deprecated=False`.
- Document `query_graph` as Cypher passthrough rather than forcing a hidden filter.

Verification:
- `cd services/palace-mcp && uv run pytest tests/integration tests/code tests/code_composite -k "deprecated or semantic_search or find_references or find_owners or find_public_api or code_snippet or search_graph" -v`
- Add a registry/linter test proving every applicable `palace.code.*` tool exposes `include_deprecated`.

### 4b. Flip query defaults after monitoring

Owner: `CXMCPEngineer`

Affected paths:
- Same MCP tool paths as Slice 4a.

Dependencies:
- Slice 4a has shipped and monitoring approval is recorded on the issue thread or a follow-up issue.

Work:
- Flip default `include_deprecated` to `False` for the staged tools.
- Preserve `include_deprecated=True` as an explicit opt-in.

Verification:
- `cd services/palace-mcp && uv run pytest tests/integration tests/code tests/code_composite -k "deprecated or include_deprecated" -v`
- Must prove default semantic search excludes deprecated symbols and explicit `include_deprecated=True` still returns them.

### 5. Bench scripts, force recovery, and DerivedData persistence

Owner: `CXInfraEngineer`

Affected paths:
- `bench/ingest-fresh-build.sh`
- `bench/ingest-fresh-replay.sh`
- `services/palace-mcp/Makefile`
- `.github/workflows/ci.yml`
- `services/palace-mcp/src/palace_mcp/cli/force_undeprecate.py` or the repo's nearest existing CLI module pattern.
- Script tests and smoke workflow.
- Prune perf tests.

Dependencies:
- Slices 1 through 3 complete. `--force` audit depends on `:DeprecationEvent`.

Work:
- Add per-project `flock` to replay.
- Add `--force` pre-step that calls a real Python CLI module.
- Add `--allow-mass-deprecation` pass-through via effective threshold.
- Preserve DerivedData by default in build; make `--force` trigger full rebuild.
- Wire smoke gate with path filtering for prune/build/replay changes.
- Add opt-in `test-prune-perf`/nightly verification for the prune performance test.

Verification:
- `cd services/palace-mcp && uv run pytest tests/scripts tests/extractors/prune_swift_symbols/ -k "force or flock or derived or mass_deprecation" -v`
- Perf: `cd services/palace-mcp && RUN_PERF_TESTS=1 uv run pytest tests/extractors/prune_swift_symbols/ -v -m perf` or `make test-prune-perf`.
- Smoke: `tests/extractors/smoke/test_prune_uw_smoke.sh` on the target runner or documented CI smoke job.
- Must prove concurrent replay blocks, `--force` emits `action='force_undeprecate'` with kernel-derived operator, and build reuses `.palace-scip-derived-data` unless forced.
- Must include `test_prune_completes_under_5s_on_250k_symbols` or a named equivalent that seeds 250k symbols, refreshes a 1% change rate, and asserts prune completes under 5 seconds on the perf runner.

## Review and QA gates

1. Plan-first review: `CXCodeReviewer` validates phase boundaries, owners, affected paths, and verification coverage before implementation issues are created.
2. Implementation review per slice: mechanical review by `CXCodeReviewer`.
3. Architecture review after mechanical pass: `CodexArchitectReviewer`.
4. Live smoke and evidence: `CXQAEngineer`.
5. Merge: `CXCTO` only after CR approval, QA pass, and green required checks.

## Deferred follow-ups

- Rename detection and cross-module move reconciliation remain v1.1 follow-ups.
- Hard delete remains out of scope.
- Phase 4b should become its own gated issue after Phase 4a has run in production long enough to inspect caller impact.
