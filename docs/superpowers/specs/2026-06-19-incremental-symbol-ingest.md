# Spec — Incremental symbol_index_swift re-ingest (Tantivy-incremental)

**Status:** rev2 — revised after voltAgent architect + QA review (2026-06-19). rev1 was written against a stale code model and would have removed an existing safety mechanism; corrected below.
**Owner:** CXMCPEngineer
**Origin:** dogfood — per-commit re-ingest must not cost the full-project ingest (~44 min @ uw-ios-app). Companion to the merged `force` flag (#6 part 1, PR #470).

## Current code — VERIFIED (cite file:line; do not re-derive from memory)
- `extractors/symbol_index_swift.py:run()`: body_hash match → `_refresh_graph_state` then SKIP (`:197-223`); mismatch → `_refresh_graph_state` (`:345`) then full Tantivy phases 1-3.
- **`_refresh_graph_state` (`symbol_index_swift.py:471-548`) already iterates ALL `iter_scip_symbol_infos` and calls `write_symbol_nodes`** → `_MERGE_SYMBOLS` sets `s.last_seen_in_run_id=$run_id` for **every current symbol** (`symbol_node_writer.py:55`). It runs on BOTH the skip and the reingest path.
- `prune_swift_symbols/cypher.py:22-27` deprecates only symbols with `last_seen_in_run_id <> companion_run_id`. **So unchanged-file symbols already get the run_id bump and are NOT pruned today.** (rev1's "mandatory freshness bump" duplicated this — DELETED from the design.)
- `tantivy_bridge.py:156`: `file_path` is added with **`index_option="basic"` (tokenized)** — `delete_documents("file_path", path)` would tokenize the path on `/` and delete the wrong docs / nothing. See blocker B1.
- `_build_file_body_hashes` (`:417-425`) reads every changed file's body; the SCIP parse + `iter_scip_symbol_infos` is O(project) regardless.

## Problem (re-stated precisely)
The **dominant per-commit cost is the Tantivy occurrence ingest** (1.2M occurrences across phases 1-3), not the Neo4j symbol/freshness layer (which `_refresh_graph_state` already does cheaply over all symbols). Make ONLY the Tantivy occurrence ingest incremental; **leave `_refresh_graph_state` (full-symbol-set freshness) untouched** so the existing no-wrongful-prune guarantee is preserved.

## Blockers to resolve first
- **B1 — Tantivy `file_path` is tokenized.** Exact delete-by-file requires the field indexed `raw` (untokenized), like `doc_key`/`symbol_id`. Changing the field tokenizer is a **schema change → requires a one-time full Tantivy rebuild** of every project (gate this; do it in the same maintenance window as the first incremental rollout). Until B1 lands, delete-by-file is unsafe — do not ship incremental Tantivy.
- **B2 — in-degree CMS counter + SymbolOccurrenceShadow** are rebuilt from the full occurrence stream today (`:342-343`, `_build_shadow_rows`). Incremental Tantivy must keep these correct (recompute the counter delta for changed files only, or accept documented importance drift and recompute periodically).

## Design (Tantivy-incremental; freshness untouched)
On `body_hash` mismatch AND `not ctx.force` AND `previous_body_hashes` present AND incremental enabled:
1. `_refresh_graph_state(...)` **unchanged** — full symbol MERGE + freshness bump + soft_delete (already correct; keeps all live symbols fresh; handles moved/renamed symbols via the full set).
2. Diff: `changed = {p : current[p] != previous.get(p)}`, `removed = previous.keys() - current.keys()`.
3. Tantivy delta (requires B1): `delete_by_file_paths_async(changed ∪ removed)` (exact-term, raw field), then run phases 1-3 over **only occurrences whose `file_path ∈ changed`**. File-keyed checkpoint so a crash mid-delta is resumable (existing checkpoints are phase-keyed only — add file-set to the checkpoint payload).
4. Recompute the in-degree counter for changed files (B2).
Fallback to full reprocess when: first ingest / force / incremental disabled / `|changed ∪ removed|` ≥ a HIGH threshold (default 80% — keep the common medium refactor on the *fast* path, only the near-total rewrite falls back; rev1's 60% was backwards).

## Acceptance — operational, not wall-clock-on-fixture
- **A1 (load-bearing, integration, real Neo4j):** `test_incremental_run_does_not_deprecate_unchanged_file_symbols` — 3 files × 2 symbols; full run (RUN_1) → edit FileC only → incremental run (RUN_2, force=False) → run `prune_swift_symbols` with **companion_run_id=RUN_2** → assert: (a) FileA/FileB symbols have `last_seen_in_run_id==RUN_2`; (b) **zero** unchanged-file symbols `:Deprecated`; (c) FileC symbols re-written with RUN_2; (d) Tantivy: FileA/FileB docs survive, FileC's RUN_1 docs gone. Assert (b) MUST run real prune (not mocked) — it is the only assertion that fails on a wrong-group_id / wrong-companion_run_id bug.
- **A2 (integration, real Tantivy not mocked bridge):** delete-by-file deletes exactly the target file's docs, leaves other files' docs intact (catches B1 tokenizer bug).
- **A3 (unit, mock call counts — not wall clock):** with 1 of N files changed, phase ingest touches only changed-file occurrences; full-reprocess path NOT invoked.
- **A4 (integration):** cross-group isolation — incremental on project A does not advance `last_seen_in_run_id` on project B (the freshness/MERGE Cypher must be group_id-scoped).
- **A5:** threshold fallback fires (4/5 files changed → full reprocess, asserted via decision log + mock counts).
- **A6:** crash after Neo4j freshness-bump / before Tantivy commit → next run leaves no orphan Tantivy docs.

All new integration tests carry `@pytest.mark.integration` + `skipif(not _HAS_NEO4J_RUNTIME)`; extend the settings mock (`_force_settings`) with the new flag so they don't silently test the disabled path. No tautological mock-driver freshness assertions (see `feedback_wire_test_tautological_assertions`).

## Risk
HIGH — core ingest; silent index corruption on a graph the operator dogfoods. Ship behind `PALACE_INCREMENTAL_INGEST` (default off). Do not enable until A1+A2 pass on real Neo4j+Tantivy and a live re-ingest window validates B1's one-time rebuild.
