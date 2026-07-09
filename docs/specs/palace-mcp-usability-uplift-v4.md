# Spec — palace-mcp usability uplift v4 (honest scope, decision-gated)

Status: ready for operator review.
Tracking: paperclip epic to be filed after operator approval.
Supersedes: v1 (withdrawn after voltAgent review), v3 (operator rejected
2026-06-01 — kill gate math wrong, F0 internally contradictory, F5a/F5b
underestimated, ownership unclear).

---

## What changed v3 → v4

v3 was rejected on 7 concrete grounds. v4 fixes each:

| v3 blocker | v4 response |
| --- | --- |
| Kill gate `≤3× vanilla wall-time` is mathematically impossible (Qodo MPS floor 3-5s vs grep 67ms) | Split gate by task type. Q1 = absolute SLO + actionable-set comparison, not wall-time ratio. Q2 = must-pass after Phase 1. Q3 = gate AFTER call-graph ships, not before. |
| Phase 1 fails Q3 by definition because call graph is Phase 2 | Q3 moved out of Phase 1 gate. Phase 1 gate measures only what Phase 1 ships. |
| F0 mixed `name` vs `short_name`; current writer has neither | Unified: writer extends to populate `short_name`, composite index `(group_id, short_name)`. Explicit `symbol_node_writer.py` patch. |
| F5a body_hash needs source anchors (start_line/end_line/body) that current :Symbol doesn't store | Promoted S0 prerequisite: persist source anchors first. F5a becomes a follow-up that depends on S0. |
| F5b `git diff HEAD..HEAD~1` misses working-tree edits; no `:Project.last_ingest_at` | F5b reworked: file mtime vs last `:IngestRun.finished_at` for that project. Working-tree edits caught. |
| F4.2 cache_coverage misses soft deletes / partial runs | F4.2 deferred until freshness model defined. Replaced by F4.3-only (git hoist) for Phase 1. |
| Backend ownership across palace.code.* mixed | New section: per-tool backend / host / iMac-degraded contract matrix. |

---

## Phase plan — three phases, two kill gates, honest scopes

```
GIM-1063 + GIM-1062 + GIM-1064 (audit chain) ── must land first ──┐
                                                                   │
                                                                   ▼
Phase 1 — foundation (5.5 dev-days):                              ┌─────────────────────┐
  S0  source anchors persisted on :Symbol     (1.5 days)          │                     │
  S1+F2  human-name resolution (short_name +  (1.5 days)          │   ┌─ Phase 1 KILL  │
         composite index + friendly find_refs)│                   │   │   GATE          │
  F3  dedup_by_file=False back-compat flag    (0.25 day)          │   │  (post-Phase 1) │
  F4.0 + F4.1 telemetry + Qodo pre-warm       (1 day)             │   │                 │
  F4.3 git-stale-check hoist (opt-in)         (0.5 day)           │   │   Q1: actionable│
  Backfill cyphers + tests                    (0.75 day)          │   │      set + SLO  │
                                                                   │   │   Q2: must-pass │
                                                                   │   │      (refs)     │
   ↓                                                               │   │   Q3: SKIP      │
                                                                   │   │      (P2 gate)  │
   Phase 1 ships ───┐                                              │   └─────────────────┘
                    ├── Q1 actionable-set check + Q2 refs pass?    │
                    │                                              │
                    ├── YES → Phase 2 funded                       │
                    └── NO → archive palace                        │
                                                                   ▼
Phase 2 — call hierarchy (3-4 days):                              ┌─────────────────────┐
  F1b  sourcekit-lsp proxy MCP tool                               │   ┌─ Phase 2 KILL  │
       on dev-Mac (iMac degraded contract documented)             │   │   GATE          │
                                                                   │   │  (post-Phase 2) │
   ↓                                                               │   │                 │
                                                                   │   │   Q3: must-pass │
   Phase 2 ships ───┐                                              │   │      (call      │
                    ├── Q3 call-graph correctness check?           │   │       graph)    │
                    ├── YES → Phase 3 conditional                  │   └─────────────────┘
                    └── NO → palace-as-is, document limitations    │
                                                                   ▼
Phase 3 — freshness (conditional, 3-4 days):
  F5a  body_hash uses S0 anchors (now possible)         (1 day)
  F5b  mtime-vs-IngestRun.finished_at periodic re-ingest (1 day)
  F4.2 coverage cache w/ proper invalidation             (1 day)
  F5c  fswatch reactivity                                (1-2 days, optional)
```

---

## Backend / host / iMac-degraded contract matrix

Cross-cutting clarification before per-feature spec.

| MCP tool | Backend | Host requirement | iMac contract |
| --- | --- | --- | --- |
| `palace.code.semantic_search` | Neo4j HNSW + Qodo MPS embed | MPS = dev-Mac native; iMac = Docker CPU (~37× slower per measurements) | Works on iMac, slow (~3 min per query). On dev-Mac native: ~3-5s warm after Phase 1. |
| `palace.code.find_references` | Neo4j only | Any | Works everywhere. F2 makes it friendly without backend change. |
| `palace.code.search_graph` | Neo4j only | Any | Works everywhere. |
| `palace.code.search_code` | Tantivy text index | Any | Works everywhere. |
| `palace.code.semantic_search` cache (F4.2 P3) | Computed at ingest finalize | Any (counter on :Project) | Works on iMac after P3. |
| `palace.code.call_hierarchy` (NEW, P2) | sourcekit-lsp proxy via LSP-over-stdio | **Dev-Mac only** — needs Xcode 16+, `xcode-build-server config`, `xcodebuild` to populate `DerivedData/<workspace>/Index.noindex/DataStore` | **iMac degraded:** returns `error_code=call_hierarchy_unavailable` + `reason=lsp_requires_dev_mac` + `next_action=run on dev-Mac` |
| `palace.git.*` | git CLI in container | Any with checkout | Works everywhere via mount. |
| `palace.memory.*` | Graphiti + Neo4j | Any | Works everywhere. |
| `palace.ingest.run_extractor` | Per-extractor module | Any with SCIP build artefacts mounted | Works everywhere. |

Phase 2 `call_hierarchy` is the ONLY tool with a hard host requirement.
All other Phase 1 work is host-agnostic.

---

## Phase 1 specs — foundation

### S0 — Persist source anchors on :Symbol (PREREQUISITE)

**Problem (verified):** Current `:Symbol` writer at
`services/palace-mcp/src/palace_mcp/extractors/foundation/symbol_node_writer.py:55-72`
persists: `kind`, `file_path`, `module_name`, `source_scope`,
`access_modifier`, plus 7 boolean modifiers. **No line ranges, no body
hash, no commit_sha.** This means downstream features that need to
read the source body (F5a body_hash, F4.3 stale-check by file+commit,
snippet hydration) have to re-parse SCIP every time or read whole files.

**Fix:**

1. Extend SCIP parser at
   `services/palace-mcp/src/palace_mcp/extractors/foundation/scip_parser.py`
   to capture for each `:Symbol` DEFINITION occurrence: `range[0]` (start
   line, 1-indexed), `range[2]` (end line) from the SCIP `Occurrence`
   protobuf. These fields already exist in SCIP — we just don't persist
   them.
2. Extend `symbol_node_writer.py` MERGE to set:
   - `def_start_line: int` (1-indexed; matches `range[0] + 1`)
   - `def_end_line: int` (1-indexed; `range[2] + 1`)
   - `def_commit_sha: str` (read once per ingest run from
     `git -C <repo> rev-parse HEAD`)
3. Backfill cypher (run once during deploy): for existing nodes with
   NULL anchors, no auto-backfill — they'll be repopulated on next
   `symbol_index_swift` run. Add `palace.ops.recount_anchors` tool
   to force-trigger if needed.
4. New Neo4j index: `CREATE INDEX symbol_anchor_idx FOR (s:Symbol)
   ON (s.def_start_line)` — supports range queries in snippet hydration.

**Acceptance:**
- New `:Symbol` nodes have `def_start_line`, `def_end_line`,
  `def_commit_sha` populated.
- Existing nodes get populated on next ingest (idempotent re-run).
- `palace.code.get_code_snippet(qualified_name)` reads body using
  `def_start_line..def_end_line` instead of N+5 heuristic.
- Schema drift test in `tests/extractors/unit/test_schema.py` updated.

**Effort: 1.5 days.** This is a prerequisite slice that unlocks F5a,
honest snippet hydration, and proper staleness detection.

---

### S1 + F2 — Human-name resolution (unified slice)

**Problem (verified):**
- `services/palace-mcp/src/palace_mcp/code_composite.py:140` uses
  suffix-regex resolution `qn_pattern=.*{qn}$` — NOT short-name lookup.
  Caller must already know enough of the qn.
- `symbol_node_writer.py` doesn't persist a `short_name` property —
  there's no indexable column for "what humans call this symbol".
- v3 spec confusingly mixed `name` and `short_name`.

**Fix (single slice; F0+F2 merged):**

1. Add `short_name: str` to `:Symbol`. Computed at ingest from the
   SCIP qualified_name. For Swift symbols like
   `s%3A11Unstoppable13MoneroAdapterC` → `short_name = "MoneroAdapter"`.
   Decoder lives in `scip_parser.py` (extract last identifier component
   from SCIP qn after URL-decode + descriptor-strip).
2. Composite Neo4j index: `CREATE INDEX symbol_short_name_idx FOR
   (s:Symbol) ON (s.group_id, s.short_name)`. Composite (not global)
   because cross-project name collisions are normal — every project
   has its own `Adapter`.
3. Backfill cypher (one-time on deploy):
   ```cypher
   MATCH (s:Symbol) WHERE s.short_name IS NULL
   CALL { WITH s
     // decode SCIP qn to short_name; pseudo, real implementation in Python migration
     WITH s, palace.scip.decode_short_name(s.qualified_name) AS sn
     SET s.short_name = sn
   } IN TRANSACTIONS OF 1000 ROWS
   ```
   Takes ~30s for 380k nodes.
4. `find_references` resolution path:
   - **Input classification:** SCIP qn detector =
     `qn.startswith("scip-") or "%3" in qn`. (No regex; verified
     against real SCIP output — qns have NO whitespace.)
   - **If SCIP:** existing exact-match path.
   - **If short name + project:** `MATCH (s:Symbol {group_id: $gid,
     short_name: $sn}) RETURN s` (indexed, <50ms).
   - **If 0 hits:** case-insensitive retry
     `WHERE toLower(s.short_name) = toLower($sn)`.
   - **If 0 hits:** word-boundary regex on qualified_name
     `WHERE s.qualified_name =~ '(?i).*(^|[._/<(])' + $sn + '($|[._/<(]).*'`.
     Capped at LIMIT 50 to bound scan cost.
   - **If 0 still:** existing `project_not_indexed` envelope.
5. **Disambiguation envelope:**
   - 1 match → auto-proceed to references lookup.
   - 2-5 matches → `error_code=ambiguous_name` + list of candidates
     with `{qn, kind, file_path, def_start_line}` (uses S0 anchors).
   - >5 matches → `error_code=too_broad`, suggest narrowing.
   - `terminal=true` flag on ambiguous envelope so agent doesn't loop.

**Acceptance:**
- `find_references("MoneroAdapter", project="uw-ios-app")` returns
  references list (≥1 file) without operator knowing SCIP encoding.
- `find_references("Adapter", project="uw-ios-app")` returns
  disambiguation list, no auto-pick.
- `find_references("BalanceData", project="uw-ios-app")` returns
  the 31 grep-ground-truth references (with optional `dedup_by_file=true`
  via F3 below).
- Existing SCIP-qn callers unchanged.
- All resolution paths <100ms on 380k-node graph.

**Effort: 1.5 days** (decoder + writer extension + composite index +
backfill + resolution path + tests).

---

### F3 — dedup_by_file=False back-compat flag

**Problem:** v1 proposed `dedup_by_file=True` as new default → silent
breaking change for existing callers.

**Fix (minimal Phase 1 only):**
1. Add parameter `dedup_by_file: bool = False` to:
   - `palace.code.semantic_search`
   - `palace.code.search_graph`
2. When True: group by `s.file_path`, keep highest-scoring symbol per
   file. Return ≤limit unique paths. Add `total_symbols_in_file: int`.
3. **Deprecation telemetry** — log when called with default to track
   migration; flip default to True in v5 once telemetry shows callers
   have migrated.
4. **No extension grouping in Phase 1.** Swift `Foo+Ext.swift` extension
   files surface as separate paths. Operator can post-process if needed.
   Defer extension grouping to a later slice — requires class-membership
   metadata not currently persisted.

**Acceptance:**
- `dedup_by_file=False` (default) → existing behaviour byte-identical.
- `dedup_by_file=True` → ≤limit unique paths in result.
- Telemetry counter `palace.semantic_search.dedup_default_used`
  increments per call.

**Effort: 0.25 day.**

---

### F4.0 — telemetry (mandatory; gates everything else)

**Problem:** All claims about latency are unverified guesses. v3 hand-
waved "Qodo MPS embed 3-5s" without measurement. Without telemetry the
kill gate is unfalsifiable.

**Fix:**
1. Add `palace.health.metrics` tool returning per-tool latency
   histograms (p50/p95/p99) over the last hour, broken down by phase
   tag for `semantic_search`:
   - `model_load_seconds` (cold only)
   - `embed_query_seconds`
   - `coverage_query_seconds`
   - `count_embedded_seconds`
   - `hnsw_query_seconds`
   - `neo4j_fetch_seconds`
   - `snippet_hydration_seconds`
   - `git_stale_check_seconds`
   - `serialize_seconds`
2. Internal implementation: in-process `collections.defaultdict(list)`
   ring buffer, 1000-event window, percentile via `statistics.quantiles`.
   No external Prometheus dependency for Phase 1.
3. Instrumentation points added to `find_semantic.py` around each
   already-identified bottleneck.

**Acceptance:**
- `palace.health.metrics` returns histogram dict after 5+ calls.
- Operator runs physical-test Q1; metrics show concrete breakdown
  matching voltAgent's estimate (or contradicting it).
- Phase 1 kill gate uses metrics as evidence (not stopwatch wall-time).

**Effort: 0.5 day.**

---

### F4.1 — Qodo pre-warm in lifespan

**Problem (verified):** `services/palace-mcp/src/palace_mcp/main.py:76`
lifespan doesn't initialize embedding backend. First call to
`semantic_search` triggers ~9s cold load.

**Fix:**
1. In `main.py` lifespan startup phase (after Neo4j driver, before
   yield): call `QodoEmbeddingBackend().embed_batch(["warmup"])` to
   force model load + MPS device allocation + Metal kernel compile.
2. Log `palace.startup.qodo_prewarm_seconds` for telemetry.
3. Add `PALACE_QODO_PREWARM=1` env (default 1) so operators with
   memory-constrained boxes can opt out.

**Acceptance:**
- First call to `semantic_search` after restart returns within metrics
  `model_load_seconds = 0` (warm).
- Process startup time increases by ~9s (acceptable for a daemon).

**Effort: 0.5 day.**

---

### F4.3 — Hoist git stale-check (opt-in)

**Problem (verified partially):** `find_semantic.py:809-837` hydration
loop is sequential awaits. `snippet_provider.py` `_check_stale` calls
`subprocess.run(["git", "rev-parse", "HEAD"])` **only if** `commit_sha`
provided. Currently triggered for each hit with commit_sha → for
limit=10 with include_context=True: 500-2000ms latency.

**Fix:**
1. Hot-path default change: `include_staleness` becomes opt-in flag
   on `semantic_search` (default False). When False → no `_check_stale`
   subprocess fires regardless of commit_sha presence.
2. When True (caller wants staleness): collect distinct `commit_sha`
   values across all hits, resolve each ONCE via batch
   `git rev-parse HEAD` per repo. In-memory cache TTL=60s.
3. Document tradeoff in tool description: "include_staleness=True
   adds 50-500ms; useful for editor-integration use cases, optional
   for analysis loops."

**Acceptance:**
- Default semantic_search (no flag) → no subprocess in hot path.
- `include_staleness=True` → subprocess count = `len(unique commit_shas)`,
  not `len(hits)`.
- Latency: hot path drops 500-2000ms (verified via F4.0 telemetry).

**Effort: 0.5 day.**

---

### Phase 1 budget + backfill + tests

**Effort:**

| Item | Days |
| --- | --- |
| S0 source anchors | 1.5 |
| S1+F2 human-name resolution | 1.5 |
| F3 dedup flag | 0.25 |
| F4.0 telemetry | 0.5 |
| F4.1 Qodo pre-warm | 0.5 |
| F4.3 git stale-check hoist | 0.5 |
| Backfill cyphers + integration tests | 0.75 |
| **Phase 1 total** | **5.5 dev-days** |

Anthropic budget for Claude-agent implementation + review: ~$2-3k.
Calendar: ~1 week with operator availability for sign-off per slice.

---

## Phase 1 KILL GATE — split by question

Run **after** Phase 1 ships. Uses F4.0 telemetry, not stopwatch.

### Q1 (add EVM chain): actionable-set + absolute SLO

NOT "≤3× vanilla wall-time" (v3's contradiction). New criterion:

- **Actionable-set:** palace returns a **superset** of the files vanilla
  grep found (the 10 candidate files from physical test). Misses are
  blocker.
- **Latency SLO:** p50 wall-time <8s (warm), p95 <15s. Measured via
  F4.0 telemetry, not stopwatch. Justification: this is "answer
  enhances reasoning" tool, not "reflex grep replacement".
- **Pass:** superset returned AND p50<8s.
- **Fail:** miss any of the 10 grep-ground-truth files OR p50>8s.

### Q2 (BalanceData refs): MUST PASS

Phase 1 directly addresses this via S1+F2 human-name resolution.

- **Pass:** `find_references("BalanceData", project="uw-ios-app")`
  returns ≥30 of 31 grep-ground-truth references within p50 <1s.
- **Fail:** any number short of 30 OR latency >2s p95.

This is the bellwether: if Phase 1 can't fix human-name lookup, palace
fundamentals are broken, archive.

### Q3 (MoneroAdapter call trace): SKIPPED FOR PHASE 1 GATE

Reason: Phase 1 doesn't ship call graph (that's F1b in Phase 2). Using
Q3 as Phase 1 kill criterion would archive palace for not having a
feature Phase 1 wasn't building. v3's circular failure mode.

Q3 becomes the Phase 2 gate.

### Phase 1 verdict outcomes

- **Q1 pass + Q2 pass** → fund Phase 2 (F1b call hierarchy).
- **Q2 pass + Q1 fail** → palace works as "human-name code lookup"
  but not "concept-based search". Operator decides whether to fund
  F1b speculatively or archive.
- **Q2 fail** → **archive palace.** Fundamentals broken; no path
  to differentiating from grep.

---

## Phase 2 spec — F1b sourcekit-lsp proxy (conditional)

Spec details unchanged from v3 since verification showed sourcekit-lsp
ships in Xcode 26.3 and supports `textDocument/callHierarchy` natively.
Reproduced here briefly:

**Tool:** `palace.code.call_hierarchy(symbol, mode=incoming|outgoing,
depth=N, project=<slug>)`.

**Implementation:**
1. Per-project sourcekit-lsp subprocess, kept warm via stdio JSON-RPC
   client (~80 LOC Python; `lsprotocol` for typed messages).
2. Pre-flight: verify `<workspace>/buildServer.json` exists +
   `<DerivedData>/Index.noindex/DataStore` populated. If not →
   `error_code=index_not_ready` + `next_action=run xcode-build-server
   config + xcodebuild build`.
3. Resolve `symbol` → file/position using S1 short_name index (Phase 1
   prerequisite). Then `textDocument/prepareCallHierarchy` →
   `incomingCalls` / `outgoingCalls`.
4. Marshal LSP response to palace's existing result envelope.
5. **iMac contract** (per ownership matrix above): tool returns
   `error_code=call_hierarchy_unavailable` + `reason=requires_dev_mac`
   on iMac. Document in tool description.

**Effort: 3-4 dev-days** (per voltAgent estimate, verified by
sourcekit-lsp probe that confirmed `callHierarchyProvider: true`).

### Phase 2 KILL GATE — Q3 only

- **Pass:** `call_hierarchy("MoneroAdapter.send", mode=incoming,
  depth=3)` returns ≥3 callers including the grep-ground-truth files
  on dev-Mac with built workspace. Latency p50 <5s warm.
- **Fail:** any number short of 3 callers OR consistently errors
  even when workspace is built.

**Verdict outcomes:**
- Pass → Phase 3 freshness work funded.
- Fail → palace ships as Phase 1+2 capability, call-graph documented
  as "experimental / requires dev-Mac"; Phase 3 deferred indefinitely.

---

## Phase 3 — freshness model (conditional, after Phase 2 passes)

### F5a — body_hash uses S0 anchors

**Now possible** because S0 (Phase 1) persisted `def_start_line` +
`def_end_line` + `def_commit_sha`. Without S0, F5a was hand-wavy.

**Fix:**
1. Extend `_LoadedSymbolRow` to include `def_body_hash`. Compute at
   ingest by reading
   `<repo>/<file_path>` between `def_start_line..def_end_line`,
   `sha256(body_bytes)`. Skip if file unreadable (log warning, fall
   back to current signature-only hash with `body_hash_unavailable`
   marker).
2. Extend `_embedding_text` to include `def_body_hash` in the hashed
   input. Result: body changes → hash changes → re-embed.
3. One-time migration: bump hash format version to `v2`; ingest
   skips re-embed when both versions match; otherwise re-embeds.
   ~1h on MPS for 380k symbols. Acceptable during off-hours.

**Effort: 1 day.**

### F5b — periodic re-ingest via mtime vs IngestRun.finished_at

**Reworked from v3** (operator caught the `git diff` mistake).

**Fix:**
1. New tool `palace.ops.detect_stale_files(project)`:
   - Query `MATCH (r:IngestRun {group_id: 'project/' + $slug})
     RETURN max(r.finished_at) AS last_ingest_at`
   - Walk repo working tree (excluding standard ignore list:
     `.git/`, `.build/`, `DerivedData/`, `xcuserdata/`, `node_modules/`,
     `Pods/`, `SourcePackages/`, `.DS_Store`), collect file mtimes.
   - Return list of `.swift` files with `mtime > last_ingest_at`.
2. launchd timer runs every 5 min on dev-Mac: invokes
   `detect_stale_files` per registered project. If non-empty list →
   enqueue `palace.ingest.run_extractor name=symbol_index_swift
   project=<slug>` (full ingest; no per-file delta — xcodebuild SCIP
   is whole-module).
3. Per-project mutex via flock on `~/.palace/ingest-{slug}.lock`.
4. Queue collapsing: if events fire while ingest runs, coalesce.

**Acceptance:**
- File edit (committed OR working-tree) picked up within 5 min on
  dev-Mac.
- Concurrent re-ingest blocked by mutex; no MERGE corruption.
- `detect_stale_files` returns expected list on a synthetic edit.

**Effort: 1 day.**

### F4.2 — coverage cache with proper invalidation

**Reworked from v3** (operator caught the partial-run hole).

**Fix:**
1. Add `:Project.symbol_total_cached` + `:Project.symbol_embedded_cached`
   + `:Project.cache_version_token` (UUID, regenerated on every event).
2. Invalidation triggers (write new cache_version_token on each):
   - `symbol_index_swift` finalize (added/removed symbols)
   - `embedding_symbol` finalize (changed embedded count)
   - any `palace.ops.delete_symbols` / soft-delete operation
   - manual `palace.ops.recount` tool (escape hatch)
3. `semantic_search` reads cached values; if `cache_version_token`
   matches a server-cached version, use cached counts (1ms). If miss,
   recount + update.
4. Failure-mode catalog: partial extractor runs CAN cause cache drift
   if the run crashes before finalize. Mitigation: `palace.ops.recount`
   tool documented in runbook for on-demand resync.

**Acceptance:**
- `semantic_search` no longer hits full-table coverage scan on hot
  path (verified via F4.0 telemetry: `coverage_query_seconds` and
  `count_embedded_seconds` drop to <10ms).
- `palace.ops.recount` resets cache after partial-run drift.

**Effort: 1 day.**

### F5c — fswatch reactivity (optional)

If F5b's 5-min cadence is too slow for an interactive workflow, F5c
adds fswatch daemon. Tradeoff: complexity vs sub-30s reactivity.
Defer unless explicitly requested by operator after F5b ships.

**Effort: 1-2 days.**

---

## Phase 3 KILL GATE

After F5a+F5b+F4.2:
- Edit a function body without changing signature → re-run physical
  test Q1/Q2 within 6 minutes → results reflect the change.
- F4.0 telemetry confirms `coverage_query_seconds < 10ms` post-cache.
- No regression in Q2/Q3 pass criteria.

Failure → Phase 3 features documented as experimental, ship as-is.

---

## Cross-cutting concerns (all phases)

### Failure-mode catalog

Per-feature failure modes documented at
`docs/runbooks/palace-mcp-failure-modes.md` before each ships:

| Failure | Mitigation |
| --- | --- |
| S0 SCIP parse error (malformed occurrence) | Log + skip; default to file:line=None |
| S1 short_name collision in disambiguation | Disambiguation envelope, terminal=true |
| F3 dedup hides relevant data | Operator passes `dedup_by_file=false` |
| F4.1 pre-warm OOM | Opt-out via `PALACE_QODO_PREWARM=0` |
| F4.3 staleness data missing | Opt-in via `include_staleness=true` |
| F1b sourcekit-lsp crash | Restart subprocess on next call; surface as `lsp_unavailable` |
| F5a body file unreadable | Hash falls back to signature-only with marker |
| F5b mutex deadlock | TTL on lock (10 min); auto-release |
| F4.2 cache drift after partial run | `palace.ops.recount` tool |

### Telemetry-driven decisions

F4.0 is mandatory and gates everything. Each kill-gate decision MUST
cite F4.0 telemetry. No more eyeball wall-time judgments.

### Backfill stories

- S0 anchors: idempotent on re-ingest; no migration needed beyond
  re-run `symbol_index_swift` per project. Fold into GIM-1062 (re-ingest
  8 false-done projects) since that's already pending.
- S1 short_name: one-time cypher backfill (~30s for 380k nodes) during
  deploy.
- F5a body_hash: hash-version bump triggers natural re-embed on next
  `embedding_symbol` run.

---

## Open decisions for operator (5 questions)

1. **Phase 1 budget approval** — 5.5 dev-days + ~$2-3k Anthropic spend
   to ship foundation + kill-gate evidence. Acceptable?
2. **Q1 actionable-set criterion** — pass = superset of grep
   ground-truth files. Acceptable? Alternative: pass if palace returns
   ≥80% recall.
3. **Q2 failure → immediate archive** — strict gate. Operator agrees
   archive is the right action if Q2 fails?
4. **F1b iMac contract** — Phase 2 documents iMac as call-graph-
   degraded (clear error). Acceptable? Alternative: build a fixture
   index-store snapshot pinned to a known commit (more work, but
   restores iMac).
5. **F5c fswatch** — keep deferred unless operator explicitly asks?

---

## Decision log

- **2026-05-30 → 2026-06-01 (v1)** — initial 5-fix spec drafted.
- **2026-06-01 (v1 review)** — 3 voltAgent reviewers found F1 wrong,
  F4 wrong bottleneck, F5 infeasible. v1 withdrawn.
- **2026-06-01 (v2 skipped)** — went straight to v3 with verification.
- **2026-06-01 (v3)** — split into Phase 1 + Phase 2 + Phase 3, dropped
  sub-second claim, added sourcekit-lsp alt.
- **2026-06-01 (v3 review)** — operator caught 7 blockers: kill gate
  math wrong, Q3 in Phase 1 gate but no Phase 1 fix, F0 internally
  contradictory (name vs short_name), F5a needs source anchors not in
  schema, F5b's `git diff` doesn't catch working-tree edits, F4.2
  cache misses partial-run / soft-delete cases, backend ownership
  unclear. v3 withdrawn.
- **2026-06-01 (v4)** — fixes all 7 v3 blockers:
  - Kill gate split by question type, Q3 moved to Phase 2 gate.
  - S0 source anchors promoted to prerequisite slice (1.5 days).
  - S1+F2 unified into human-name resolution with explicit
    `short_name` property + composite `(group_id, short_name)` index.
  - F5b uses file mtime vs `IngestRun.finished_at`, catches working-
    tree edits.
  - F4.2 deferred to Phase 3 until proper freshness model + multi-
    trigger invalidation defined.
  - Backend ownership matrix added.
  - Failure-mode catalog mandated per feature.
- **Next:** operator approves Phase 1 budget OR rejects v4 with new
  blockers. Iterate or archive.
