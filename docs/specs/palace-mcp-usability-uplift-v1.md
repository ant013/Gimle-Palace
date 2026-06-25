# Spec — palace-mcp usability uplift v1 (5 fixes to make palace beat grep)

Status: draft, awaiting Board approval.
Tracking: paperclip epic **GIM-1079** with child issues **GIM-1080..GIM-1084**.
Scheduled: after GIM-1063 audit chain (#5-#7) lands on develop.
Motivated by: `docs/research/gimle-physical-test-2026-06-01.md` —
palace lost 3-of-3 real dev queries to vanilla grep.

---

## Why now

The physical test on 2026-06-01 confirmed palace currently delivers
**negative value** vs `grep`/`find` on UW iOS for typical dev questions.
Five concrete defects explain the loss. Fix them — palace either becomes
worth its tokens, or we honestly retire the project. No middle ground
after another inconclusive benchmark.

---

## F1 — Swift CALL edges in code graph (the big one)

### Problem

`palace.code.trace_call_path(qualified_name=<any swift symbol>)` returns
`{}` empty graph because the Swift SCIP indexer extracts:
- `:Symbol` nodes (DEFs)
- `:File` nodes  
- `:Symbol-[:OCCURS_IN]->:File` (USE occurrences as relations)

It does NOT emit `:Symbol-[:CALLS]->:Symbol` edges. So the canonical
graph-only operation — "what does X call? what calls X transitively?" —
is non-functional for the largest project in the corpus.

### Fix

Extend `symbol_index_swift` extractor (`services/palace-mcp/src/palace_mcp/
extractors/symbol_index_swift/`) to:

1. Parse SCIP `occurrence.symbol_roles` field. SCIP encodes role bits
   per occurrence: 1 = DEFINITION, 2 = IMPORT, 4 = WRITE_ACCESS,
   8 = READ_ACCESS, 16 = GENERATED, **32 = TEST**, 64 = FORWARD_DEFINITION.
   No native "call" bit — but SCIP's `expression` field on occurrences
   identifies call sites in source. We need to walk `Document.occurrences`
   and detect: `enclosing_range` of a USE that lands inside a function
   body whose `symbol_kind` is `Function`/`Method` → record CALL edge.
2. Emit `:Symbol-[:CALLS]->:Symbol` edges into Neo4j.
3. New ingest field `:CALLS{call_site_file, call_site_line}` for
   provenance.
4. Update `find_semantic.py` and graph cypher queries that power
   `trace_call_path` to traverse `:CALLS` edges instead of returning
   empty.

### Acceptance

- `palace.code.trace_call_path(qualified_name="<MoneroAdapter qn>",
  mode="calls", depth=3)` returns ≥10 edges for uw-ios-app
- Performance: query latency <500ms for depth=3
- Backward compat: existing `:OCCURS_IN` relations preserved; CALLS are
  additive

### Effort estimate

3-5 days. Largest single piece of work in this spec. Worth filing as
its own slice (GIM-1080).

---

## F2 — Friendly `find_references` API (short name → qualified_name resolution)

### Problem

`palace.code.find_references(qualified_name="BalanceData")` returns 0
hits because the real qualified_name in palace's Neo4j is
`s%3A11Unstoppable11BalanceDataV` (SCIP-encoded). Developers / Claude
agents calling palace from the outside don't know the SCIP encoding.

### Fix

Augment `find_references` (in `palace_mcp/code/find_references.py`):

1. **Short-name resolution** — if `qualified_name` does NOT match the
   SCIP regex `^[a-z]\s%[0-9A-Fa-f]{2}.*`, treat as a short name and run
   `MATCH (s:Symbol) WHERE s.name = $sn OR s.qualified_name CONTAINS $sn
   RETURN s LIMIT 20`.
2. If exactly 1 match → use that symbol's full qn for references lookup
3. If multiple matches → return disambiguation response: list of
   `{qn, kind, file_path}` candidates, error_code = `ambiguous_name`,
   `next_action: "call find_references again with full qn from this list"`
4. If 0 matches → existing `project_not_indexed` / no-results semantics

### Acceptance

- `find_references("BalanceData")` returns 31 refs (matching `grep -rl`
  ground truth) OR disambiguation list with `BalanceData` as the one
  candidate then auto-proceeds
- `find_references("send")` returns disambiguation list (too generic)
- Existing SCIP-qn callers still work unchanged

### Effort estimate

1 day. GIM-1081.

---

## F3 — Per-file dedup in semantic_search / search_graph results

### Problem

`semantic_search(query="add new EVM chain", limit=8)` returned 8 hits
which collapsed to 2 unique files (different methods of same class each
shown separately). Consumer has to dedup manually.

### Fix

Add `dedup_by_file: bool = True` parameter to:
- `palace.code.semantic_search`
- `palace.code.search_graph`

When true, post-process Neo4j result list: group by `s.file_path`, keep
the highest-scoring symbol per file (for semantic) or the first symbol
per file (for graph). Return at most `limit` unique files.

Add `total_occurrences_in_file: int` field to each result for the
operator who DOES want depth.

### Acceptance

- `semantic_search(query=..., limit=8, dedup_by_file=True)` returns at
  most 8 unique file paths
- `dedup_by_file=False` preserves current behavior (back-compat)
- Default is `True` (the friendlier behavior)

### Effort estimate

0.5 day. GIM-1082.

---

## F4 — Sub-second response latency

### Problem

`semantic_search` takes 5-35 seconds per call (query embed + HNSW
lookup + payload fetch + serialization). For an LLM agent loop, this
adds turn-multiplied wall-clock that dominates the experience.

### Fix

Three sub-fixes:

1. **Pre-warm model on palace-mcp startup** — load
   `Qodo-Embed-1-1.5B` model into memory at app boot, not on first
   query. Eliminates ~9s cold-start.
2. **Optional smaller model for hot queries** — register
   `PALACE_EMBEDDING_FAST_BACKEND` env (default off) that swaps to a
   smaller, faster embedding (e.g. `BAAI/bge-small-en-v1.5`, 33M
   params, ~50ms embed vs ~500ms for Qodo). Operator/agent can
   request fast backend via `backend: "fast"` param. Quality trade-off
   documented.
3. **In-memory result cache** — LRU cache keyed by
   `(query, project, scope_filter, limit)` with 5-min TTL. Repeat
   identical queries (agents often re-ask) hit cache.

### Acceptance

- Cold `palace.code.semantic_search` → p50 <2s, p95 <5s
- Warm (cached) repeat → p50 <50ms
- Fast-backend path → p50 <300ms
- Existing query results unchanged (just faster)

### Effort estimate

2-3 days (model pre-warm trivial; fast backend needs new
QodoEmbeddingBackend variant; cache needs cypher key normalization).
GIM-1083.

---

## F5 — Live re-index on file change

### Problem

After any `git pull` or local edit, palace's index is stale until a
manual `palace.ingest.run_extractor name=symbol_index_swift` re-run.
For Claude Code agents working on a live working tree, this means palace
queries return results that don't match what the agent is actually
editing.

### Fix

1. **Native macOS `fswatch` daemon** at
   `services/palace-mcp/scripts/palace-fswatch.sh` watching every
   registered project's source root. On debounced change (2-second
   batching), enqueue an incremental re-ingest.
2. **Incremental SCIP delta** — only re-run SCIP build for files in the
   change set (not full project). For Swift this requires
   `xcodebuild -only-testing` style scoped builds — research first;
   may need ~1 day spike to validate feasibility.
3. **Re-ingest just changed Symbol nodes** — use the file-path filter in
   symbol_index_swift extractor (already supports a path scope per
   GIM-1058) to update only affected nodes; embedding extractor
   idempotent skip handles vector refresh.
4. **Status surfacing** — `palace.health.status` returns
   `last_index_age_seconds` per project; semantic_search adds
   `warnings: [{code: "index_stale", file_count: N}]` when stale window
   >10 min.

### Acceptance

- After file edit, palace index updates within 30 seconds
- `find_references("MyClass")` on a new class returns refs immediately
  after creation
- No regression for fully indexed projects (zero overhead when nothing
  changes)
- Background daemon survives sleep/wake of MacBook (launchd)

### Effort estimate

4-7 days. Largest in scope after F1. May need to defer "incremental SCIP
delta" sub-step if it turns out to need full rebuild every time —
fallback would be a periodic background re-ingest every 5 minutes which
captures most of the value at less risk. GIM-1084.

---

## Roadmap placement

```
develop (today)
  └─ GIM-1063 (Tantivy/Neo4j store divergence) — pending, audit chain #2
  └─ GIM-1062 (re-ingest 8 false-done projects) — pending, audit chain #3
  └─ GIM-1064 (extractor count sanity audit) — pending, audit chain #4

  ↓ THEN
  
  └─ GIM-1079 (epic: palace-mcp usability uplift v1)
       ├─ GIM-1080 — F1: Swift CALL edges (3-5 days)
       ├─ GIM-1081 — F2: friendly find_references (1 day)
       ├─ GIM-1082 — F3: per-file dedup (0.5 day)
       ├─ GIM-1083 — F4: sub-second response (2-3 days)
       └─ GIM-1084 — F5: live re-index (4-7 days)
       Total estimate: 10.5-16.5 dev-days

  ↓ THEN
  
  └─ Re-run physical test on the same 3 Q's. Gate: all 3 must now
     show palace ≥ vanilla on wall-clock + completeness. If not — kill
     palace project.
```

---

## Open decisions for operator

1. **F1 priority** — agreed this is the biggest unlock? Or want to ship
   F2+F3+F4 first (smaller wins, lower risk) and tackle F1 separately?
2. **F4 fast-backend** — operator OK trading embedding quality for 10×
   speed on a `backend: "fast"` opt-in flag? Default stays Qodo
   (full quality).
3. **F5 sub-fix scope** — F5 includes both fswatch trigger AND
   incremental SCIP. If incremental SCIP turns out hard (Swift's SPM
   build doesn't support file-scoped delta), fallback = 5-min
   background re-ingest. Acceptable?
4. **Kill-switch** — after these 5 fixes, if physical test still shows
   palace < vanilla, we admit defeat and archive the project. Agree on
   the kill criterion now so we don't sunk-cost ourselves.

---

## Decision log

- **2026-06-01** — spec drafted after physical test produced 3-of-3
  losses for palace vs vanilla. Filed as roadmap addition after
  audit-chain (GIM-1062/1063/1064) settles.
