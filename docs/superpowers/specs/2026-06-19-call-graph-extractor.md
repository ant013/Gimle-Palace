# Spec — Precise Swift call graph (`:CALLS` edges) for trace_call_path

**Status:** rev2 — revised after voltAgent architect + QA review (2026-06-19). rev1 claimed "hard part shipped, rest is config" — **false**. Re-scoped: Phase 1 is shippable now; Phases 2-3 are sent back for redesign with named blockers.
**Owner:** Phase 1 → CXMCPEngineer; Phases 2-3 → design spike first (CXResearchAgent + CXMCPEngineer).

## Current code — VERIFIED (corrects rev1's stale claims)
- `code/indexstore.py:find_callers` searches the IndexStore by **short symbol name** (`call_hierarchy.py:132`) and each `CallerRecord` carries the **target** symbol's USR + the occurrence `(source_file, line, col)` (`indexstore.py:55-66`). **It does NOT identify the enclosing caller symbol.** No occurrence-relations API is bound (`indexstore_occurrence_relations_apply_f` absent).
- The **SCIP emitter drops `.call`** entirely (`scip_emit_swift/Sources/PalaceSwiftScipEmitCore/ScipEmitter.swift:mapRoles :63-78` maps def/import/write/read, no `.call`) — call-ness never reaches `symbol_index_swift`.
- `code/call_hierarchy.py:43-58` already returns `index_store_format_unsupported` for **Xcode 16+ UniDB** stores (flat `.db`, no `v5/`). The whole `:CALLS` path is pinned to a v5 DataStore.
- `code/edges.py:5` `CALL_EDGES` **already traverses both `:CALLS` AND `:REFERENCES` (union)**; `native_trace_call_path.py:255-299` already distinguishes `not_extracted` vs empty (tested `test_native_trace_call_path.py:452-499`).
- `symbol_node_writer.py:172`: `:Symbol.line_end` is **null on every symbol** ("left null until the emitter surfaces an enclosing range").
- `config.py:237` `palace_indexstore_paths` exists, default `{}` (the live gap). `scip_emit_uw_ios_app.sh:316` unconditionally `rm -rf`s DerivedData.

## Phase 1 — SHIP NOW (S, low risk, real value)
Deliver the interactive `call_hierarchy` win with zero new ingest code:
1. In `scip_emit_uw_ios_app.sh`, **retain** `$DERIVED_DATA/Index.noindex/DataStore` after the build (don't delete it); record its path.
2. **Verify the retained store is v5, not UniDB** (`_detect_store_format`) — if UniDB on the operator's toolchain, Phase 1 reports the limitation and STOPS (do not greenlight Phases 2-3 against a dead format). This is the gating acceptance.
3. Configure `PALACE_INDEXSTORE_PATHS={"uw-ios-app": <DataStore>}` (env / emit `--env-file` merge, mirroring `PALACE_SCIP_INDEX_PATHS`).
- **Acceptance:** integration test (skip-guarded) — `call_hierarchy_tool(project="uw-ios-app")` returns ≥1 caller whose location matches `grep -rn <fn>`; smoke-assert `$DERIVED_DATA/Index.noindex/DataStore/v5/*.IDXU` exists after the emit.

## Phases 2-3 — REJECTED as scoped; redesign required
The goal (materialize precise `(caller)-[:CALLS]->(callee)` edges so trace_call_path beats REFERENCES) is blocked on **unsolved, un-costed core problems**:

- **C1 — caller resolution has no primitive.** Building `(caller)->(callee)` needs the *enclosing function* of a call site `(file,line,col)`. `find_callers` gives only the target USR + location. Two candidate mechanisms, both net-new, must be chosen + costed: (a) new ctypes bindings for IndexStore occurrence *relations* (`childOf`/`calledBy`) reading the parent USR; or (b) line-range containment — **blocked by null `line_end`** (`symbol_node_writer.py:172`); requires the emitter to surface enclosing ranges first (separate emitter work).
- **C2 — no precision gain without removing REFERENCES from `CALL_EDGES`.** Materializing `:CALLS` while `code/edges.py:5` still unions `:REFERENCES` yields zero improvement in trace_call_path output. The design must specify deprioritizing/removing `:REFERENCES` from the call traversal (and the dead_code reachability impact of doing so).
- **C3 — perf.** `find_callers` is O(units × records × occurrences) per symbol name with a Python ctypes callback per occurrence. Running it per defined symbol over 256k symbols = 256k full-store scans (hours-to-days, far worse than the 44-min ingest). Needs a single-pass walk of all occurrences building caller→callee in one store traversal, not per-symbol.
- **C4 — schema consistency.** `graphiti_schema/edges.py:150` models `:CALLS` as a graphiti `EntityEdge`; a raw-MERGE `(caller)-[:CALLS {via:'indexstore'}]->(callee)` risks two incompatible `:CALLS` shapes. Pick one.

## Acceptance for the redesigned Phase 2 (must be specified before any walker)
- **Caller-attribution test (load-bearing, the spec's whole value):** a call inside function F to G produces `F -[:CALLS]-> G` — NOT `<file> -[:CALLS]-> G`, NOT `H -[:CALLS]-> G`. Cannot pass with current primitives → C1 must be solved first.
- **Role-filter unit test:** parametrized `_is_call_site(roles)` — `_ROLE_CALL`→True, `_ROLE_REFERENCE`/`_ROLE_DECLARATION`/`_ROLE_DEFINITION`→False.
- **Round-trip integration (real Neo4j):** seed Caller/Callee + a CALL-role record and a REFERENCE-role record → exactly one `:CALLS {via:'indexstore'}` edge, zero `:REFERENCES` written by the extractor.
- **Replace-snapshot idempotency:** two runs → identical `:CALLS` count (per `test_dead_symbol_run_replaces_snapshot_on_real_neo4j`).
- **dead_code direction:** adding `:CALLS` (subset of REFERENCES reachability) can only REDUCE the dead set — assert `dead_after ≤ dead_before` (rev1's "doesn't over-prune" was the wrong risk axis).
- Perf: `call_edge_swift` on the mini fixture completes < 30s (catches O(N²) resolution).

## Recommendation
Ship **Phase 1 standalone** (config + retain + v5-gate + live call_hierarchy verification). Do **not** assign Phases 2-3 to the walker until a design spike resolves C1 (caller resolution mechanism + its emitter/ctypes dependency), C2 (REFERENCES traversal), and C3 (single-pass perf), each with the acceptance test above named and shown achievable.
