# Spec — palace-mcp usability uplift v3 (evidence-backed, decision-gated)

Status: ready for operator approval.
Tracking: paperclip epic **GIM-1079 (re-create)** + child issues.
Scheduled: after GIM-1063 + GIM-1064 audit chain settles on develop.
Supersedes: `palace-mcp-usability-uplift-v1.md` (withdrawn after voltAgent
review found F1 technically wrong + F4 attacking wrong bottleneck +
F5 partially infeasible).

---

## What changed from v1 → v3

**v1 was reworked because three independent voltAgent reviewers
(architect, performance-engineer, code-reviewer) found:**

1. F1's SCIP claim was technically wrong (`Occurrence.expression` doesn't
   exist; `enclosing_range` exists but `scip-swift` doesn't populate it).
2. F4 attacked cold-load (~9s) and ignored the actual 20+s warm-path
   bottlenecks (dual full-table Neo4j scans + serial git stale-check).
3. F5's "incremental SCIP delta for Swift" is infeasible (xcodebuild =
   whole-module).
4. Missing F0: `:Symbol(name)` Neo4j index — foundation for both F1 and F2.
5. F2's short-name regex too broad + SCIP detector regex wrong.
6. F3's default=True was a silent breaking change + extension-grouping bug.

**All claims were verified against actual source on 2026-06-01.**
Evidence:

| Claim | Verified | Evidence |
| --- | --- | --- |
| `Occurrence.expression` doesn't exist | ✓ | `scip_emit_swift/Sources/PalaceSwiftScipEmitCore/Proto/scip.proto` — 7 fields, no `expression` |
| `scip-swift` doesn't populate `enclosing_range` | ✓ | `ScipEmitter.swift:24-61` never sets it; Python parser never reads it |
| No CALL role bit | ✓ | proto enum SymbolRole: 7 values, none = CALL |
| 2 full-table scans/query | ✓ | `find_semantic.py:711-724` — `_load_coverage` + `_count_embedded_symbols` both unconditional, no LIMIT |
| Body changes don't invalidate embedding | ✓ | `embedding_symbol.py:69-77` — `_embedding_text` from qn+kind+module+file_path only |
| sourcekit-lsp ships callHierarchy | ✓ | Xcode 26.3 — `callHierarchyProvider: true` in initialize response. **But needs xcode-build-server + xcodebuild built index**; works dev-Mac only (not iMac) |

---

## Architecture decision: split into two phases gated by kill-test

```
GIM-1063 + GIM-1062 + GIM-1064 (audit chain)
   ↓
Phase 1: cheap fixes (6 dev-days, ~$2k spend)
   ↓
KILL GATE: re-run physical test (3 Q's from gimle-physical-test-2026-06-01.md).
            If palace wins ≥2/3 on completeness + ≤3× wall-time, proceed to Phase 2.
            Else archive palace entirely.
   ↓
Phase 2 (only if gate passes): F1 call-graph via sourcekit-lsp proxy (3-4d).
                                F5 fswatch + body_hash already in P1.
```

Rationale: voltAgent reviewers' core complaint was "spec funds expensive
risky F1/F5 speculatively before proving the cheap fixes restore baseline
competitiveness". v3 fixes that. Phase 1 budget is bounded and produces
either a working tool or a clear kill signal.

---

## Phase 1 — cheap fixes that fix verified-real bottlenecks

### F0 (NEW) — `:Symbol(name)` Neo4j index + denormalized short_name

**Problem:** F2's short-name lookup proposed `WHERE s.name = $sn OR
s.qualified_name CONTAINS $sn` would be a **full scan over 380k Symbol
nodes** without an index. F1's call-graph traversal also needs name-based
lookup for resolving call targets to symbols.

**Fix:**
1. Add Neo4j index: `CREATE INDEX symbol_name_idx FOR (s:Symbol) ON (s.name)`
2. Denormalize a `short_name` property on `:Symbol` at ingest time.
   Decoder lives in `scip_parser.py` — extract the last identifier from
   the SCIP qualified_name (e.g. `s%3A11Unstoppable13MoneroAdapterC` →
   `MoneroAdapter`). Backfill via one-time Cypher on existing nodes.
3. Update `ensure_custom_schema()` in
   `services/palace-mcp/src/palace_mcp/extractors/foundation/schema.py`
   to declare the new index.

**Effort: 0.5 day. Acceptance: index exists; `WHERE s.short_name = $sn`
executes in <50ms over 380k symbols.**

---

### F2 — friendly `find_references` (revised)

**Problem (verified):** `find_references("BalanceData")` returns 0 hits
because real qn is `s%3A11Unstoppable11BalanceDataV`. Plus v1's proposed
regex `^[a-z]\s%[0-9A-Fa-f]{2}.*` is wrong (SCIP qns have no whitespace).

**Fix:**
1. **SCIP detector:** use `qn.startswith("scip-") or "%3" in qn` (no
   regex). Verified prefix against real SCIP output.
2. **Resolution order** (only if not SCIP):
   - `MATCH (s:Symbol {short_name: $name})` (exact, indexed by F0) — typically returns 0-3 hits
   - If 0 hits: case-insensitive fallback `MATCH (s:Symbol) WHERE toLower(s.short_name) = toLower($name)`
   - If 0 hits: word-boundary qn search via regex
     `MATCH (s:Symbol) WHERE s.qualified_name =~ '(?i).*(^|[._/<(])' + $name + '($|[._/<(]).*'`
3. **Disambiguation:**
   - Exactly 1 match → auto-use for references lookup
   - 2-5 matches → return disambiguation list with error_code=`ambiguous_name`
   - >5 matches → return error_code=`too_broad`, suggest narrower name
   - 0 matches → existing `project_not_indexed` semantics
4. **No `CONTAINS` substring** — verified too broad (`BalanceData` would
   match `BalanceDataObservable`).

**Effort: 1 day. Acceptance: `find_references("MoneroAdapter")` returns
≥1 hit; `find_references("Adapter")` returns disambiguation; `find_references("BalanceData")` returns either match or 1-item disambiguation. SCIP-qn callers still work.**

---

### F3 — per-file dedup in semantic_search / search_graph (revised)

**Problem:** `semantic_search(query=..., limit=8)` returned 8 hits = 2
unique files (8 methods of 2 classes). Manual dedup required.

**v1 issues identified by code-reviewer:**
- `default=True` is silent breaking change
- Swift extensions (`MoneroAdapter+Send.swift`) get deduped away
- `total_occurrences_in_file` semantic was undefined

**Fix:**
1. Add `dedup_by_file: bool = False` (NOTE: default FALSE for one release
   to preserve back-compat; flip to True in v2 after caller migration).
2. When True: group by `s.file_path`, keep highest-scoring symbol per
   file. Return ≤limit unique files.
3. **Extension-aware** (Swift specific): if two `:Symbol` nodes share
   `short_name` but live in different files where one file matches
   `{ClassName}+*.swift`, treat both as same logical entity for dedup
   purposes — keep both as separate "parts" with `dedup_key=ClassName`.
4. Add fields per result:
   - `total_symbols_in_file: int` — distinct :Symbol nodes matching
   - `extension_parts: [file_path]` — sibling extension files (Swift only)

**Effort: 0.5 day. Acceptance: `dedup_by_file=true` returns ≤limit
unique paths; `MoneroAdapter` + extension files both surface with
`dedup_key`.**

---

### F4 — kill the REAL latency bottlenecks (redesigned)

**Problem (verified breakdown of 35.7s):**

| Phase | Time | Spec v1 addressed? | v3 addresses? |
| --- | --- | --- | --- |
| Cold model load (Qodo 1.5B) | 8-12s | ✓ pre-warm | ✓ pre-warm |
| Qodo MPS warm embed | 3-8s | ✗ (claimed 500ms wrongly) | ⚠ NOT fixable on Qodo; drop "sub-second" claim |
| `_load_coverage` + `_count_embedded_symbols` (2× full scan, 380k nodes) | 0.2-0.8s | ✗ | ✓ cache at ingest |
| Serial `_check_stale` git subprocess per hit | 0.5-2s | ✗ | ✓ hoist + dedupe by commit_sha |
| HNSW + Neo4j fetch | ~80ms | n/a | n/a |

**Fix (4 sub-tasks):**

1. **F4.0 — Profile first.** Add `palace.health.metrics` tool returning
   per-tool p50/p95 latency histogram + breakdown by phase
   (model_load, embed, coverage_query, stale_check, hnsw, serialize).
   Required before any optimization to verify v3's bottleneck claims.
2. **F4.1 — Pre-warm Qodo on app boot.** Load model in
   `main.py` lifespan. Eliminates 8-12s cold load.
3. **F4.2 — Cache coverage counts.** Compute `_load_coverage` +
   `_count_embedded_symbols` ONCE at ingest completion, store on
   `:Project` node as properties (`symbol_total`, `symbol_embedded`,
   `last_recount_at`). semantic_search reads from `:Project` (1-line
   cypher, <10ms) instead of re-scanning. Invalidate on every
   `embedding_symbol` run completion.
3. **F4.3 — Hoist `_check_stale` git subprocess.** Currently fires per
   hit in serial. Fix:
   - Read `git rev-parse HEAD` ONCE per unique `commit_sha` across all
     hits in the response (collect distinct commits → batch resolve)
   - Better: cache resolution in-memory for 60s (commit doesn't change
     mid-second)
   - Best: remove `_check_stale` entirely from the hot path; staleness
     is cosmetic metadata, push to a separate optional `?include_staleness=true` parameter.
4. **F4.4 — DROP fast-backend (BGE-small).** v1 proposed swapping to
   BGE-small for 10x speed. voltAgent reviewers noted: dim mismatch
   (384 vs 1536) requires SECOND HNSW index (~600MB disk + ~6min re-embed
   per project). Not worth the complexity for a single project's tools.
   Defer to a future epic if proven needed.

**Revised acceptance criteria** (honest, achievable):
- After F4.1+F4.2+F4.3: cold p50 <8s (was 35.7s), warm p50 <5s.
  **Not sub-second.** Qodo MPS embed is the floor at 3-5s warm.
- F4.0 telemetry: histogram exposed via `palace.health.metrics` for
  future tuning + kill-gate evidence.
- Drop "sub-second" promise from headline. Tool is for thinking, not
  for grep-equivalent reflexive use.

**Effort: 2 days (F4.0 = 0.5d, F4.1 = 0.5d, F4.2 = 0.5d, F4.3 = 0.5d).
F4.4 drops scope.**

---

### F5a — body_hash in embedding_input (must-fix before any F5 daemon)

**Problem (verified):** `_embedding_text` in
`embedding_symbol.py:69-77` builds hash from `qualified_name + kind +
module_name + file_path` only. If a function body changes but the
signature stays the same → hash matches → extractor skips re-embed →
**stale vector silently survives.** This silent-staleness bug is more
important than fswatch.

**Fix:**
1. Extend `_LoadedSymbolRow` to include `body_text` (read from source
   file using `enclosing_range` from SCIP, OR fallback to first 5 lines
   after `start_line`).
2. Include `body_text` (or `body_hash = sha256(body_text)`) in
   `_embedding_text` so semantically-changed symbols get re-embedded.
3. One-time migration: bump version of hash format; force re-embed of
   all symbols where `embedding_input_hash` doesn't have version prefix.

**Effort: 1 day. Acceptance: changing a function body and re-running
`embedding_symbol` extractor refreshes that vector even though signature
unchanged.**

---

### F5b — debounced periodic re-ingest (replaces fswatch + incremental SCIP)

**Problem:** v1's "incremental SCIP delta for Swift via xcodebuild" is
infeasible (xcodebuild = whole-module). Live file-watcher with full
re-ingest would also stampede.

**Fix (acknowledged 80% solution):**
1. launchd timer running every 5 minutes on dev-Mac. Checks
   `git diff --name-only HEAD..HEAD~1` OR mtime of source files vs
   `:Project.last_ingest_at`. If any changes → enqueue full
   `symbol_index_swift` re-ingest for that project.
2. Per-project mutex via flock on `~/.palace/ingest-{slug}.lock`.
3. Queue collapsing: if multiple events fire while one ingest runs,
   coalesce to single "re-run after completion" event.
4. Skipped if a manual ingest is in progress (mutex held).

**Effort: 1 day. Acceptance: file edit in working tree picked up by
palace within 5 minutes (not 30s as v1 hand-waved); no concurrent
re-ingest corruption.**

**Defer:** fswatch + ignore list + sub-30s reactivity. Add as F5c
(Phase 2) if Phase 1 kill-gate passes.

---

## Phase 1 summary

| Fix | Effort | Issue ID (to file) |
| --- | --- | --- |
| F0 — :Symbol(name) index | 0.5 day | GIM-1080 (re-numbered if re-created) |
| F2 — friendly find_references | 1 day | GIM-1081 |
| F3 — dedup_by_file (default=False) | 0.5 day | GIM-1082 |
| F4 — profile + pre-warm + coverage cache + git hoist | 2 days | GIM-1083 |
| F5a — body_hash in embedding | 1 day | GIM-1084 |
| F5b — periodic re-ingest | 1 day | GIM-1085 |
| **Total Phase 1** | **6 dev-days** | |

Estimated cost: ~$2k Anthropic tokens for Claude-agent implementation +
review. ~1 week calendar.

---

## Kill gate (mandatory before Phase 2)

After Phase 1 ships:

1. Re-run physical test from
   `docs/research/gimle-physical-test-2026-06-01.md` — same 3 Q's
   (add EVM chain, BalanceData refs, MoneroAdapter call trace).
2. Pass criteria:
   - Palace wins ≥2 of 3 on **completeness** (gives correct/superset answer)
   - Palace wall-time ≤3× vanilla on each Q (was 260× on Q1; needs to be ≤3×)
3. If pass → fund Phase 2 (F1 call-graph).
4. If fail → **archive palace project**. Document lessons in
   `docs/research/palace-postmortem-2026-XX.md`. Cancel epic. Operator
   commits to LSP-proxy or vanilla-grep MCP wrapper as replacement.

This threshold makes Phase 1 a real bet, not a foot in the door.

---

## Phase 2 (CONDITIONAL — only if kill gate passes)

### F1 — Swift call-graph via sourcekit-lsp proxy

**v3 picks F1b (LSP proxy) over F1a (extend SCIP emitter):**

| | F1a: extend scip_emit_swift to populate enclosing_range + post-process | F1b: sourcekit-lsp proxy |
| --- | --- | --- |
| Effort | **8-14 days** (Swift code in PalaceSwiftScipEmitCore + post-processing + handle protocol/extension dispatch) | **3-4 days** (Python LSP client + MCP tool + workspace lifecycle) |
| Quality | Best-effort heuristic interval-tree lookup; protocol dispatch likely wrong (points to protocol method, not impl) | Compiler-grade (Apple maintains it) |
| Works on iMac? | Yes (SCIP fixture flow) | No (needs Xcode + xcode-build-server + populated DerivedData; iMac can't build modern Swift) |
| Works on dev-Mac? | Yes | Yes |
| Maintenance burden | Permanent: every Swift toolchain update may break parsing | Apple maintains LSP; we're just a thin proxy |

**Decision:** F1b for Swift dev-Mac; document iMac as call-graph-degraded
(SCIP fallback remains for OTHER analyses — refs, semantic search, dead
code). Cross-language extractors (Kotlin/Solidity) unchanged.

**Fix:**
1. Add `palace.code.call_hierarchy(symbol, mode=incoming|outgoing,
   depth=N)` MCP tool.
2. Implementation:
   - Lifecycle: spawn `sourcekit-lsp` subprocess per indexed Swift
     project, kept warm with a JSON-RPC stdio client (~80 LOC Python,
     `lsprotocol` for typed messages).
   - Pre-flight: verify `buildServer.json` exists in workspace +
     `Index.noindex/DataStore` populated. If not → return error
     `error_code=index_not_ready` + `next_action=run xcode-build-server config + xcodebuild build`.
   - Resolve `symbol` to file/line via existing palace symbol→file
     lookup (uses F0 index). Hand to sourcekit-lsp via
     `textDocument/prepareCallHierarchy` + `incomingCalls`/`outgoingCalls`.
   - Marshal LSP response to palace's existing schema for tool results.
3. **Fallback path** for iMac / non-built projects: keep existing empty
   `trace_call_path` semantics but add `warning: call_graph_unavailable`
   + explanation of how to enable (build the workspace).

**Effort: 3-4 days. Acceptance: `call_hierarchy(MoneroAdapter.send,
mode=incoming, depth=3)` returns ≥3 callers on dev-Mac with built
workspace; returns clear error envelope on iMac.**

---

### F5c — fswatch reactivity (optional, P2)

If kill-gate passed AND operator wants sub-30s reactivity over 5-min
periodic:

1. fswatch daemon at `services/palace-mcp/scripts/palace-fswatch.sh`
2. Explicit ignore list: `.build/`, `DerivedData/`, `.git/`, `xcuserdata/`,
   `.DS_Store`, `node_modules/`, `Pods/`, `SourcePackages/`
3. 2-second debounce
4. Re-uses F5b's mutex + queue collapsing

**Effort: 2 days. Defer.**

---

## Cross-cutting (always applies)

### Telemetry
F4.0 (`palace.health.metrics`) is mandatory and is the only honest way to
verify the kill gate. Add to Phase 1.

### F1 backfill story
:Symbol nodes already in production Neo4j don't have :CALLS edges.
Fold the backfill into GIM-1062 (re-ingest 8 false-done projects) which
is already in audit chain. After F1b ships, no backfill needed — LSP
proxy doesn't write to Neo4j.

### F0 backfill
Existing :Symbol nodes don't have `short_name` property. One-time
backfill Cypher: 
```cypher
MATCH (s:Symbol) WHERE s.short_name IS NULL
SET s.short_name = <decode-from-qualified_name>
```
Runs once during Phase 1 deploy, ~30s for 380k nodes.

### Failure modes catalog
Each fix surfaces new failure modes. Document in
`docs/runbooks/palace-mcp-failure-modes-v3.md` before each ships:
- F0: index corruption on schema migration → drop index, recreate
- F2: ambiguous-name infinite loop in agent → ambiguous responses
  carry `terminal=true` flag, agent must pick from list
- F3: dedup hides relevant occurrence → operator passes
  `dedup_by_file=false` to get all
- F4.2: stale coverage cache → invalidation runs in ingest finalize;
  manual `palace.ops.recount` tool as escape hatch
- F4.3: removing stale-check loses metadata → opt-in
  `?include_staleness=true` for callers who care
- F5a: body_hash migration mass re-embed → run during off-hours;
  takes ~1h on MPS for 380k symbols
- F5b: periodic re-ingest blocks manual → mutex respects fairness

---

## Open decisions for operator (4 questions)

1. **Phase 1 budget approval** — 6 dev-days + ~$2k Anthropic spend
   acceptable to validate kill-gate? Decision before any commit.
2. **F4.0 telemetry implementation** — implement in palace-mcp directly
   (Python `histogram` deps) OR rely on existing logger + external Prom
   scrape? Decision affects 0.5 day estimate.
3. **F5a hash migration** — accept the ~1h mass re-embed cost during
   deploy? OR introduce hash-version field for opportunistic re-embed?
   Latter cleaner but adds 0.5d to F5a.
4. **F1 fallback on iMac** — for non-built workspaces, return
   `error_code=index_not_ready` (my recommendation) OR fall back to
   empty graph + warning (current behavior)? Decision shapes UX
   for users without dev-Mac.

---

## Decision log

- **2026-05-30 → 2026-06-01 (v1)** — initial 5-fix spec drafted.
- **2026-06-01 (v1 review)** — 3 voltAgent reviewers found F1 wrong, F4
  wrong bottleneck, F5 infeasible. v1 withdrawn.
- **2026-06-01 (verification)** — all critical claims verified against
  actual source code + proto definitions. sourcekit-lsp alt path
  validated as superior for Swift call-graph (Apple-maintained,
  compiler-grade) but requires built workspace (dev-Mac only).
- **2026-06-01 (v3)** — split into Phase 1 cheap-fixes (6d, kill-gate)
  + Phase 2 conditional call-graph (3-4d, sourcekit-lsp proxy).
  Drop F4 sub-second claim. Drop F5 incremental SCIP. Add F0 + F5a.
- **Next:** operator approves Phase 1 budget OR archives palace.
