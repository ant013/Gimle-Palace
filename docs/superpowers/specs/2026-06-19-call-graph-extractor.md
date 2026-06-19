# Spec — Precise Swift call graph (`:CALLS` edges) for trace_call_path

**Status:** rev3 — Phase 2-3 design spike after Phase 1 + GIM-1684 viability confirmation (2026-06-19).
**Grounding:** `origin/develop` `6a8b6a701fa902cd620cd5a4d2aaadfcf213e97e`; local verification against `/Library/Developer/CommandLineTools/usr/lib/libIndexStore.dylib`.
**Owner:** Phase 1 → CXMCPEngineer; Phase 2 implementation → CXMCPEngineer after this rev3 review.

## Current code — VERIFIED
- `code/indexstore.py:find_callers` searches the IndexStore by **short symbol name** and returns target occurrence records only: target symbol USR + `(source_file, line, col, roles)`. It does **not** identify the enclosing caller symbol.
- The local `libIndexStore.dylib` exports the needed relation primitives: `indexstore_occurrence_relations_apply_f`, `indexstore_symbol_relation_get_roles`, and `indexstore_symbol_relation_get_symbol` (`nm -gU /Library/Developer/CommandLineTools/usr/lib/libIndexStore.dylib`).
- Upstream IndexStoreDB models call occurrences as `call` roles with relation roles including `calledBy` and `containedBy`; `IndexStoreSymbolRelation.roles` is read as “the base symbol is contained by/called by the related symbol.”
- The local Swift SCIP emitter already builds SCIP symbols from IndexStore USRs via `SymbolBuilder.scipSymbol(usr:)`; Python already has equivalent `_swift_qname_from_usr` / `_escape_swift_usr_for_descriptor` logic in `cross_module_contract.py`.
- The SCIP parser currently emits `ScipSymbolInfo.qualified_name` but drops the raw `sym_info.symbol`; `Symbol` nodes are keyed by `(qualified_name, group_id)`, not USR.
- The SCIP emitter drops `.call` entirely (`ScipEmitter.mapRoles` maps def/import/write/read only), so call-ness is not recoverable from `symbol_index_swift`.
- `code/edges.py:CALL_EDGES` currently includes `CALLS`, `REFERENCES`, and structural reachability edges. `native_trace_call_path` therefore cannot become precise merely by adding `:CALLS`.
- `symbol_node_writer.py` writes `:REFERENCES`, `:CONFORMS_TO`, `:EXTENDS`, and `:EXTENSION_OF` directly between `:Symbol` nodes. `graphiti_schema/edges.py:make_calls` also exists for Graphiti `EntityEdge`, but the current symbol graph path is direct Neo4j relationships.

## Phase 2 — DESIGN CHOSEN

Goal: materialize precise Swift `(:Symbol)-[:CALLS {via:'indexstore'}]->(:Symbol)` edges from a v5 IndexStore in one bounded pass, and make `trace_call_path` use only those call edges when answering call traversal.

### C1 — caller resolution

Use IndexStore occurrence relations. Do **not** use line-range containment in Phase 2.

Mechanism:
1. Extend `code/indexstore.py` ctypes bindings with:
   - `indexstore_occurrence_relations_apply_f`
   - `indexstore_symbol_relation_get_roles`
   - `indexstore_symbol_relation_get_symbol`
2. Add relation-role constants:
   - `_ROLE_REL_CALLEDBY = 1 << 13`
   - `_ROLE_REL_CONTAINEDBY = 1 << 16`
3. In a new single-pass collector, walk each record occurrence once.
4. Keep only occurrences whose primary roles include `_ROLE_CALL`.
5. Treat the occurrence symbol USR as the callee.
6. Inspect occurrence relations; pick the related symbol whose relation roles include both `_ROLE_REL_CALLEDBY` and `_ROLE_REL_CONTAINEDBY` as the enclosing caller. If a toolchain emits only one of those roles, count it as unresolved unless a fixture proves it still identifies the enclosing callable unambiguously.
7. Convert both caller and callee USRs to current `Symbol.qualified_name` using the same format as `SymbolBuilder.scipSymbol(usr:)`: `"<module> <escaped-usr>"`. Reuse or extract the existing Python helper from `cross_module_contract.py`; do not add a second escaping implementation.
8. Drop unresolved edges where either endpoint has no active `:Symbol` node in the target `group_id`; report counters for `calls_seen`, `calls_resolved`, `missing_caller_symbol`, `missing_callee_symbol`, and `missing_relation`.

Why this is enough for the load-bearing attribution test:

```swift
func F() { G() }
func G() {}
```

The occurrence for `G()` has primary role `call`, callee USR `G`, and relation `calledBy|containedBy -> F`. The collector writes `F -[:CALLS]-> G`; no file node participates, and a neighboring `H` cannot win unless IndexStore reports `H` as the relation target.

Cost: small/medium. This is a binding + collector slice in existing `indexstore.py` style. No SCIP emitter range work is required.

### C2 — precision gain

Adding `:CALLS` alone does not improve `trace_call_path` while the traversal still unions `REFERENCES`.

Phase 2 must introduce a `CALLS`-only traversal for `native_trace_call_path` call mode. Minimal acceptable shape:
- Add a separate `TRACE_CALL_EDGES = frozenset({"CALLS"})` or inline equivalent for `native_trace_call_path._path_query`.
- Keep the existing broad reachability set for `dead_code.graph_loader` in this phase: `CALLS|REFERENCES|EXTENDS|CONFORMS_TO|EXTENSION_OF|EXISTENTIAL_USE`.
- Update tests so `trace_call_path` proves `REFERENCES` is not in the call traversal query, while `dead_code` keeps its current broad reachability contract.

Do not globally remove `REFERENCES` from shared edge registries in this slice; that would silently change dead-code semantics and is a separate policy decision.

Cost: small. One query/registry split plus tests.

### C3 — performance

Do **not** call `find_callers` per symbol. That would scan the full store once per symbol and is not acceptable for 256k symbols.

Use one store traversal:
1. Collect unit names.
2. Collect unique record names and file paths from unit dependencies.
3. For each unique record, open the record once and iterate all occurrences.
4. For `_ROLE_CALL` occurrences, read the callee symbol + relation symbols, resolve endpoints, and append a deduped `(caller_qname, callee_qname)` pair.
5. Batch-write resolved edges to Neo4j.

Expected complexity: O(units + records + occurrences + edges), matching the current `find_callers` inner traversal once instead of N times. The Python callback still runs per occurrence, so Phase 2 acceptance uses the mini fixture for a hard budget and requires counters for future live sizing.

Cost: medium. It reuses current traversal code but changes the result model from “records for one short name” to “all call edges.”

### C4 — schema consistency

For Phase 2, write direct Neo4j `:CALLS` relationships between existing `:Symbol` nodes, matching `symbol_node_writer.py` and `dead_code.graph_loader`. Do not mix in Graphiti `EntityEdge` for this extractor.

Relationship shape:

```cypher
MATCH (a:Symbol {qualified_name: r.source, group_id: r.group_id})
MATCH (b:Symbol {qualified_name: r.target, group_id: r.group_id})
MERGE (a)-[rel:CALLS]->(b)
SET rel.via = 'indexstore',
    rel.last_seen_in_run_id = $run_id,
    rel.last_seen_at = datetime($seen_at)
```

Snapshot replacement must delete or mark stale only prior `:CALLS {via:'indexstore'}` edges for the same `group_id`; it must not touch Graphiti-authored `:CALLS` or SCIP-authored `:REFERENCES`.

Cost: small/medium. It mirrors existing direct edge writers with one extra `via` guard.

## Phase 2 acceptance

- **Caller-attribution test:** fixture `func F() { G() }` plus `func H() {}` produces exactly `F -[:CALLS {via:'indexstore'}]-> G`, and does not produce `<file> -[:CALLS]-> G` or `H -[:CALLS]-> G`.
- **Relation binding unit test:** mocked occurrence relation with `_ROLE_REL_CALLEDBY | _ROLE_REL_CONTAINEDBY` resolves the caller USR; missing relation increments `missing_relation` and writes no edge.
- **Role-filter unit test:** `_is_call_site(roles)` returns true for `_ROLE_CALL`, false for `_ROLE_REFERENCE`, `_ROLE_DECLARATION`, and `_ROLE_DEFINITION`.
- **USR bridge test:** `s:10UwMiniCore11WalletStoreC6select8walletIDySi_tF` maps to the same `qualified_name` as `SymbolBuilder.scipSymbol(usr:)` / `_swift_qname_from_usr`.
- **Round-trip Neo4j integration:** seed active `:Symbol` nodes for F and G plus one CALL occurrence and one REFERENCE occurrence; extractor writes exactly one `:CALLS {via:'indexstore'}` edge and no `:REFERENCES`.
- **Trace precision test:** `trace_call_path` path query for call mode includes `CALLS` and excludes `REFERENCES`; a graph with only `A -[:REFERENCES]-> B` returns no call path.
- **dead_code compatibility test:** `dead_code.graph_loader` still loads broad reachability edges after the traversal split.
- **Replace-snapshot idempotency:** two extractor runs over the same fixture produce the same `:CALLS {via:'indexstore'}` count.
- **Perf guard:** `call_edge_swift` on the mini fixture completes in < 30s and reports `records_scanned` and `occurrences_scanned`; no per-symbol scan API is used.

## Phase 3 — later

Phase 3 can decide whether dead-code should offer a strict-call reachability mode. That is not part of Phase 2, because removing `REFERENCES` from dead-code reachability can increase the dead set and requires product review.

## Recommendation

Assign Phase 2 implementation as a small/medium slice:
1. Add relation ctypes bindings + single-pass `call_edge_swift` collector.
2. Write direct `:CALLS {via:'indexstore'}` Symbol edges with snapshot replacement.
3. Split `trace_call_path` to use `CALLS` only for call traversal.
4. Keep dead-code broad reachability unchanged.

Do not assign line-range containment or SCIP emitter `.call` support for this slice; IndexStore relations solve caller attribution directly.
