# Spec — True incremental project analysis, including embeddings

**Status:** Draft — awaiting approval before implementation

**Grounded in:** `origin/develop` at `14c52e1110cbe9cfe59f20ac09010b646ac9dd04` (2026-08-20)

**Production evidence:** native service revision `0f0a3957`; Stable run `f7292ffd-7aa4-4d65-a490-6458483a623a`
**Problem statement:** an analysis can be labelled `incremental` while one or more extractors scan or mutate the full project. This makes an incremental audit unexpectedly take hours and makes its status misleading.

## Goal

For every extractor included in `project_analyze`, an incremental run must do one of the following explicitly:

1. process only the durable source/symbol delta from the selected commit range;
2. be skipped with a durable stale/coverage reason; or
3. be refused before execution because the requested contract cannot be satisfied.

No extractor may silently turn an incremental request into a full-project scan. A full baseline or a deliberate embedding backfill remains supported, but is a separately named operation with separately reported progress.

## Verified current behaviour

- `ProjectAnalyzer` resolves `effective_mode=incremental` and `changed_file_count`, but `_default_executor` calls `run_extractor` with only extractor name, project, and (for two extractors) a companion run ID.
- `ExtractorRunContext` contains no execution mode, base/target commit, changed-file set, removed-file set, or changed-symbol set.
- `embedding_symbol` reads every non-deprecated Symbol in the project and selects candidates by missing/mismatched embedding hash. It has no access to the commit delta.
- The running native service sets `PALACE_EMBEDDING_MAX_SYMBOLS=300000`; Stable contains about 266k symbols. Consequently that cap is a broad backfill allowance, not an incremental limit.
- Existing B2 candidate policy orders a global candidate list. It does not make that list delta-scoped.
- Existing `symbol_index_swift` body-hash/baseline behaviour and `prune_swift_symbols` safety mechanisms must be preserved; this proposal does not weaken their full-symbol freshness semantics.

## Non-goals

- Replacing the embedding provider or vector schema.
- Changing the meaning of `:Deprecated` or removing the existing safe prune threshold.
- Rewriting project-wide analyses to be delta algorithms where no sound delta contract exists. They must instead advertise `skipped`/`stale` in incremental runs.
- Retrospectively treating the current Stable embedding job as an incremental job.

## Design

### 1. Durable delta contract

Introduce an immutable `AnalysisDelta` created before the first checkpoint starts. It carries:

- project slug and group ID;
- base indexed commit and target HEAD commit;
- effective mode and fallback reason;
- changed, added, renamed, and removed repository-relative paths;
- a durable ID referenced by every checkpoint;
- after `symbol_index_swift`, changed Symbol identities and changed/removed Symbol source paths.

Persist it with the `AnalysisRun` (or in a dedicated graph entity owned by that run), not only in process memory. A resumed run must consume the same delta and must never recompute a different range against a later HEAD.

The contract passed to extractors must add an explicit `execution_mode` and `analysis_delta`/`delta_id` to `ExtractorRunContext`. `run_extractor` and all direct runner boundaries must accept and preserve it. The checkpoint mode becomes evidence of the actual payload passed to the extractor, not an orchestration label.

### 2. Extractor capability manifest

Every registered extractor declares one capability:

| Capability | Incremental behaviour |
| --- | --- |
| `DELTA` | Receives `AnalysisDelta` and must operate only on its declared delta inputs. |
| `GLOBAL_STALE` | Is skipped during incremental runs, records the exact stale-since commit and required full refresh. |
| `FULL_ONLY` | Is not run by an incremental request. The API reports `requires_full` rather than silently executing full work. |

The profile registry and `project_analyze` validate this manifest before scheduling. An extractor result whose reported execution scope disagrees with the checkpoint mode is a run failure, not a cosmetic status.

### 3. `symbol_index_swift` as delta producer

Keep the current full-symbol freshness/soft-delete safety pass where required for pruning correctness. In addition, write a durable symbol delta after a successful run:

- symbols defined, removed, or whose embedding input fields changed;
- source path and stable symbol identity;
- target commit and companion ingest run ID.

When the body-hash path correctly skips a symbol re-ingest, it produces an empty symbol delta. It must not cause downstream extractors to scan all historical symbols.

The existing high-change-ratio fallback to full symbol reprocessing remains allowed, but must be recorded as `effective_mode=full` with a concrete reason. It does not grant unrelated extractors permission to hide full scans under an `incremental` label.

### 4. Delta-only embeddings

`embedding_symbol` becomes a `DELTA` extractor.

For an incremental analysis it must:

1. load only `AnalysisDelta.changed_symbol_ids` (plus changed symbols whose embedding input hash changed);
2. skip with `no_changed_symbols` when the durable symbol delta is empty;
3. write embeddings only for that closed candidate set;
4. report selected, skipped-up-to-date, written, and removed counts linked to the delta ID.

It must not query the entire project merely because historical symbols lack embeddings. `PALACE_EMBEDDING_MAX_SYMBOLS` may guard an explicit backfill, but must not truncate or expand an incremental delta. If an unusually large real delta exceeds an operational cap, the run becomes resumable with a deterministic delta cursor; it never substitutes unrelated global candidates.

### 5. Explicit embedding backfill

Introduce a separately named, resumable operation such as `embedding_backfill` (MCP endpoint/CLI form decided during implementation). It is the only path allowed to scan all symbols missing embeddings.

- It uses the existing B2 prioritisation policy and global `PALACE_EMBEDDING_MAX_SYMBOLS`.
- It records a backfill cursor, selected count, remaining count, and estimated work.
- It cannot be implicitly appended to `project_analyze(mode="incremental")`.
- Operator status distinguishes `incremental audit ready` from `semantic backfill pending`.

### 6. Freshness and audit truthfulness

Update `Project.indexed_commit` atomically once the source/symbol delta has been durably applied to the target HEAD. Downstream optional-analysis or embedding failures must not erase that source-index fact; they instead affect a separate audit-coverage status.

`palace_memory_get_project_overview` must expose at least:

- source index commit/tree freshness;
- last successful symbol delta commit and delta ID;
- embedding coverage state (`current_delta`, `backfill_pending`, `backfill_running`, or `unavailable`);
- project-wide extractor findings that are stale by design.

An analysis report may not claim a fully fresh project-wide audit when `GLOBAL_STALE`, `FULL_ONLY`, missing inputs, or failed checkpoints remain.

## Affected areas

- `services/palace-mcp/src/palace_mcp/project_analyze.py`
- `services/palace-mcp/src/palace_mcp/extractors/base.py`
- `services/palace-mcp/src/palace_mcp/extractors/embedding_symbol.py`
- `services/palace-mcp/src/palace_mcp/extractors/symbol_index_swift.py`
- extractor registry/profile capability definitions and runner boundary
- project/analysis graph schema and overview queries
- MCP project-analysis status/report contracts
- focused unit and real-Neo4j/Tantivy integration tests
- deployment configuration and operator runbook for the explicit backfill command

## Migration and rollout

1. Add the durable delta contract, capability manifest, and tests with the feature disabled by default if a rollout flag is needed.
2. Migrate `symbol_index_swift` and `embedding_symbol` together; do not release a mode flag that can label global embeddings incremental.
3. Backfill missing historical embeddings only through the explicit backfill operation, with a bounded cursor and observability.
4. Enable true incremental analysis first on a small Swift kit, then Stable and Unstoppable Wallet.
5. Verify source freshness and embedding delta counts against one real changed-file commit per project before general enablement.

## Acceptance criteria

1. Editing one Swift file in a real Neo4j/Tantivy fixture produces an `AnalysisDelta` containing only that path and its changed symbols.
2. The corresponding incremental embedding run sends embeddings only for that changed symbol set. A fixture with 1,000 unchanged symbols and two changed symbols must make exactly two embedding candidates available; a full-project load/query is forbidden by test instrumentation.
3. With an empty symbol delta, `embedding_symbol` is `SKIPPED` with `no_changed_symbols`; it makes no provider request.
4. Missing embeddings on unchanged historical symbols do not cause an incremental run to enqueue them. The explicit backfill operation does enqueue them and reports its cursor/remaining count.
5. A delta larger than the configured incremental batch cap resumes over the same delta cursor; it never reorders into unrelated project symbols and never converts itself to a backfill.
6. Every registered extractor has a declared capability. Incremental `GLOBAL_STALE` and `FULL_ONLY` extractors are visibly skipped/refused with stale-since evidence.
7. `Project.indexed_commit`, dominant symbol commit, and local tree HEAD agree after a successful symbol delta, including when optional downstream analysis later fails.
8. Existing prune safety integration tests still prove unchanged symbols are not deprecated after an incremental symbol run.
9. A real Stable-like fixture with a 70-file delta cannot schedule a 266k-symbol embedding pass. Runtime assertions are based on candidate counts/provider calls, not a wall-clock threshold.
10. MCP status and reports distinguish source-index freshness from semantic-backfill coverage and cannot call the run fully incremental when any extractor reports full scope.

## Verification plan

- Unit tests for delta construction, immutable resume semantics, capability validation, candidate selection, and cursor continuation.
- Real Neo4j/Tantivy integration tests for symbol delta production, prune safety, changed-symbol embeddings, and indexed-commit persistence.
- Fake/recording embedding backend tests proving exact candidate counts and zero calls for empty deltas.
- MCP contract tests for `project_analyze`, status, overview, and explicit backfill progress.
- A live smoke on one small kit, then Stable and Unstoppable Wallet, using a committed one-file change and recording base/target SHA, changed symbols, provider candidate count, and resulting freshness fields.

## Assumptions

- `symbol_index_swift` remains the authoritative producer of Swift symbol deltas.
- A stable symbol identity plus repository-relative path is available for all emitted Swift symbols.
- Existing full ingestion/backfill capability remains required for first-time projects and schema migrations.
- No implementation begins from this spec until it is approved.

## Open questions

1. Should `AnalysisDelta` be a dedicated graph node with child records or a compact immutable JSON property/artifact referenced from `AnalysisRun`?
2. Which existing MCP/CLI surface should host `embedding_backfill`, and what operator role owns it?
3. What production limits should bound delta embedding batches, provider concurrency, and resumable cursor duration?
4. Should the current `PALACE_EMBEDDING_MAX_SYMBOLS` be renamed to make its backfill-only semantics unambiguous?
