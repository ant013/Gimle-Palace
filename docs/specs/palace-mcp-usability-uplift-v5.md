# Spec — palace-mcp usability uplift v5 (post-3-reviewer-audit)

Status: ready for operator approval.
Supersedes: v1 (withdrawn), v3 (operator rejected), v4 (3-reviewer audit
found 10 blockers + 6 majors + 11 should-fix + 2 promoted). v5 fixes
all NEEDED items + commits defaults where v4 left choices to operator.

---

## v4 → v5 change log (audit-driven)

**Blockers fixed (10):**

| ID | Was | Now |
| --- | --- | --- |
| B1 | `def_end_line = range[2]` (silently stores end_char for 3-tuple ranges) | `def_end_line = range[2] if len(range)==4 else range[0]` |
| B2 | Path said `extractors/foundation/scip_parser.py` | Real path: `extractors/scip_parser.py` |
| B3 | `def_commit_sha` from `git rev-parse HEAD` at ingest time (HEAD may have moved since SCIP build) | Read from `index.scip.meta.json` (SCIP build artefact metadata); error if missing |
| B4 | S1 backfill cypher invoked non-existent `palace.scip.decode_short_name` procedure | Python migration script `scripts/migrate_short_name.py` + 0.5d effort |
| B5 | F5a/`get_code_snippet` reads working tree at stored anchor → wrong content after HEAD moves | Rule: `if HEAD != def_commit_sha: read via 'git show <def_commit_sha>:<path>'` |
| C1 | Q1 kill-gate: "superset of grep ground-truth" (mathematically wrong for top-K semantic) | Q1: **recall ≥80% at limit=20** vs grep ground-truth |
| C2 | F5b relied on un-indexed `:IngestRun(group_id)` lookup | New S0 deliverable: `CREATE INDEX ingest_run_group_idx FOR (r:IngestRun) ON (r.group_id)` |
| F5a-8h | Migration estimate "~1h on MPS" | Conservative **~8h** (380k / 13 sec ≈ 29k sec) + mandatory checkpoint/resume |
| F4.0-N20 | "Operator runs Q1, metrics show breakdown" (N=1 invalid for p50/p95) | Kill-gate protocol: **N≥50 identical Q1 queries on warm process** before reading metrics |
| Q1-cold | `p95<15s` SLO without cold-start carve-out | Explicit precondition: `model_load_seconds == 0` (warm-run gate; cold runs excluded) |

**Majors fixed (6):**

| ID | Was | Now |
| --- | --- | --- |
| C3 | "Fold backfill into GIM-1062" (punts work to other team) | Explicit Phase 1 deploy slice: `backfill_short_name + backfill_anchors` (+0.75d already in budget) |
| C4 | `terminal=true` flag on disambiguation envelope (honor-system, agent loops) | Server-side rate-limit: **3 consecutive `ambiguous_name` for same project in 60s → `error_code=disambiguation_loop_detected`** |
| C5 | "Q2 pass + Q1 fail → operator decides Phase 2 funding" (same indecision as v3) | **Default committed: Q2 pass → fund Phase 2 regardless of Q1. Archive only on Q2 fail.** |
| C6 | F4.0 ring buffer in-process (multi-worker uvicorn splits metrics) | Hard constraint: palace-mcp deployed as **single uvicorn worker** (`--workers 1`); documented in `services/palace-mcp/scripts/launch_native_macos.sh` + iMac compose |
| C7 | Phase 2 iMac contract = hard error | Phase 2 ships dev-Mac live + **P2.5 OPTIONAL** fixture-snapshot for top-3 iMac projects (+1-2d, not gating P2) |
| C8 | No "what if kill-gate evidence contradicts gate design?" clause | **New §Gate adjustment protocol**: 1-day window between Phase ship and evaluation when CTO+operator can revise Q-criteria on telemetry shape; after window, criteria frozen |

**Should-fix promoted to spec (11 + 2 NICE→SHOULD):**

| ID | Was | Now |
| --- | --- | --- |
| S1 | Word-boundary regex `[._/<(]` | Expanded: `[._/<>():?!&,\s]` (covers Swift generics, optionals, protocols, composition) |
| S2 | Disambiguation cap=5 (arbitrary; "Adapter" returns 8 legit) | Cap=**15**; configurable via `max_candidates: int = 15` param |
| S3 | F3 telemetry counter `palace.semantic_search.dedup_default_used` has no sink in F4.0 | F4.0 schema includes `counters: dict[str, int]` alongside `histograms` |
| S4 | F4.0 ring buffer keying unspecified | Keying: `(tool_name, phase) → ringbuf(1000)`. Separate buckets per (tool, phase) combo |
| S5 | F4.1 pre-warm OOM/error: lifespan behavior unspecified | Log error + yield anyway (degrade to cold path); operator gets `palace.startup.qodo_prewarm_failed` metric + log |
| S6 | F4.3 60s TTL drops correctness during interactive `git pull` | Documented in tool description: "include_staleness can lag git operations by ≤60s; restart process for editor-grade freshness" |
| S8 | F5b walk excludes missing `Build/`, `Index.noindex/`, `.swiftpm/` | Expanded list + edge case documented: if DerivedData lives outside repo root via build settings, F5b will NOT walk it → no false-positive re-ingest |
| S9 | F1b `prepareCallHierarchy` returns null for unopened files | Explicit `textDocument/didOpen` step before prepareCallHierarchy + wait-for-indexed |
| S10 | F1b "kept warm" without memory budget (1-3GB × 9 workspaces = 27GB) | **LRU eviction**: max 3 warm sourcekit-lsp subprocesses; cold-start ~5s for evicted workspace; documented `PALACE_LSP_MAX_WARM=3` env |
| S11 | F4.2 cache_version_token race (concurrent extractor finalize) | Atomic recount+token write via single Cypher transaction with `apoc.do.case` ordering |
| N3 promoted | Global Neo4j write contention at 9 parallel ingests | Global write semaphore: **max 2 concurrent extractor runs** across all projects; per-project mutex unchanged |
| N5 promoted | `palace.ops.recount_anchors` mentioned in S0 but no spec | New §Ops tools section: contract for `recount_anchors`, `recount_coverage_cache` (both simple Cypher-only ops, 0.25d combined) |

**Nice-to-have remaining (2; not in spec, ship in runbook):**

- N1: F4.1 warmup string `"function foo() { return 42 }"` instead of `"warmup"` (realistic Swift idiom for embedding)
- N2: index size estimate in deploy runbook (~25 MB short_name + ~80 MB anchors for 380k symbols)

---

## Phase plan — three phases, two kill gates, **committed defaults**

```
GIM-1063 + GIM-1062 + GIM-1064 (audit chain) ── must land first ──┐
                                                                   │
                                                                   ▼
Phase 1 — foundation (6.5 dev-days now; was 5.5 in v4)            ┌───────────────────┐
  S0   source anchors + IngestRun.group_id index   (2 days)       │ Phase 1 KILL GATE │
  S1+F2 human-name resolution                      (2 days)       │ (post-Phase 1)    │
       (Python migration script for backfill)                     │                   │
  F3   dedup_by_file=False flag                    (0.25 day)     │ Q1: recall≥80%    │
  F4.0 telemetry (histograms + counters)           (0.75 day)     │     @ limit=20    │
  F4.1 Qodo pre-warm + yield-on-fail               (0.5 day)      │     + warm SLO    │
  F4.3 git-stale-check opt-in hoist                (0.5 day)      │ Q2: must-pass     │
  Ops tools: recount_anchors, recount_coverage    (0.25 day)     │     refs (30/31)  │
  Backfill (anchors via re-ingest of UW projects) (0.25 day)     │ Q3: SKIP (P2 gate)│
  Tests + Q1/Q2 controlled benchmark harness       (0.5 day)      │                   │
                                                                   │ N≥50 warm runs    │
                                                                   │ via benchmark     │
                                                                   │ before reading    │
                                                                   │ F4.0 metrics      │
                                                                   └───────────────────┘
   ↓                                                                       │
   Phase 1 ships ──┐                                                       │
                   ├── Q2 pass + Q1 pass? → fund Phase 2                   │
                   ├── Q2 pass + Q1 fail? → fund Phase 2 (default v5)     │
                   └── Q2 fail?            → archive palace                │
                                                                           ▼
Phase 2 — call hierarchy (3-4 days; iMac documented as degraded)
  F1b  sourcekit-lsp proxy MCP tool                  (3-4 days)
       LRU max 3 warm subprocesses
       didOpen → prepareCallHierarchy → calls
  P2.5 OPTIONAL fixture snapshot for iMac (+1-2d)   ┌───────────────────┐
                                                    │ Phase 2 KILL GATE │
   ↓                                                │                   │
   Phase 2 ships ──┐                                │ Q3: ≥3 callers    │
                   ├── Q3 pass? → fund Phase 3      │     for           │
                   └── Q3 fail? → ship as-is,       │     MoneroAdapter │
                                  P3 deferred       │     .send +       │
                                                    │     p50<5s warm   │
                                                    └───────────────────┘
                                                            │
                                                            ▼
Phase 3 — freshness (conditional, 3-4 days)
  F5a   body_hash uses S0 anchors + commit_sha guard (1 day)
        Migration: 8h conservative + checkpoint/resume
  F5b   mtime vs IngestRun.finished_at periodic       (1 day)
        File walk ignore list + DerivedData edge case
        Per-project flock + global write semaphore
  F4.2  coverage cache + atomic invalidation          (1 day)
        Single-transaction recount+token write
  F5c   fswatch reactivity (OPTIONAL)                 (1-2 days)
```

---

## Backend / host / iMac-degraded contract matrix (unchanged from v4)

See v4 §"Backend / host / iMac-degraded contract matrix" — applies as-is.

---

## §Gate adjustment protocol (NEW per C8)

After each Phase ships and before kill-gate evaluation, a **1-day window**
opens during which CTO + operator may revise the Phase's kill-gate criteria
based on actual F4.0 telemetry shape. Adjustments require:

1. Written justification appended to this spec's decision log
2. Documented in `bench/runs/phase-{N}/gate-adjustment-{N}.md` with
   before/after thresholds + reason
3. Co-signed by operator + reviewing agent (CR or OpusReviewer)

After the window closes, criteria are frozen and the Phase is evaluated
against the published gate. This prevents goal-post moving but allows
honest correction when measurement reveals the gate's premise was wrong.

---

## §Ops tools (NEW per N5 promotion)

Two ops-only Cypher tools shipped in Phase 1 as escape hatches:

### `palace.ops.recount_anchors(project: str)`
Forces re-write of `def_start_line` / `def_end_line` / `def_commit_sha`
on `:Symbol` nodes for the given project by re-running `symbol_index_swift`
extractor with `--anchors-only` flag (skips embedding refresh).
Returns: `{ok: bool, nodes_updated: int, duration_ms: int}`.
Use case: after S0 deploy if backfill cypher silently missed nodes.

### `palace.ops.recount_coverage_cache(project: str)`
Forces re-computation of `:Project.symbol_total_cached` +
`symbol_embedded_cached` + new `cache_version_token`. Issues single
Cypher transaction with atomic recount + token write (per S11 fix).
Returns: `{ok: bool, symbol_total: int, symbol_embedded: int, token: str}`.
Use case: after partial extractor run that crashed before finalize.

---

## Phase 1 specs (v5 — fixes inlined)

### S0 — source anchors + IngestRun index

**Fix B1 — range[2] semantics:** SCIP `Occurrence.range` is either
3-tuple `[start_line, start_char, end_char]` (single-line, most common
case) or 4-tuple `[start_line, start_char, end_line, end_char]`. Per
verified reading of `extractors/scip_parser.py:343-350` (CORRECT path —
B2 fix) the parser already handles both forms for ranges in some code
paths but doesn't extract end_line for symbols. Decoder for S0:

```python
def extract_def_range(occurrence_range: list[int]) -> tuple[int, int]:
    """Return (start_line_1indexed, end_line_1indexed)."""
    if len(occurrence_range) == 4:
        start_line, _start_char, end_line, _end_char = occurrence_range
    elif len(occurrence_range) == 3:
        start_line, _start_char, _end_char = occurrence_range
        end_line = start_line  # single-line occurrence
    else:
        raise ValueError(f"unexpected SCIP range arity: {len(occurrence_range)}")
    return start_line + 1, end_line + 1  # SCIP is 0-indexed
```

**Fix B3 — commit_sha source:** Don't call `git rev-parse HEAD` at
ingest time. SCIP build artefact at `<repo>/scip/index.scip.meta.json`
already contains `{"git_sha": "..."}` per
`scip_emit_swift_kit.sh:metadata_write_line`. Extract from there.
Error envelope `error_code=scip_meta_missing` if absent or malformed.

**Fix C2 — IngestRun.group_id index:** Add to S0 deliverables:
```cypher
CREATE INDEX ingest_run_group_idx FOR (r:IngestRun) ON (r.group_id)
```
Required for F5b's `MAX(finished_at)` query in Phase 3 to not full-scan.

**Persisted fields on :Symbol (extending existing writer at
`extractors/foundation/symbol_node_writer.py:55-72`):**
- `def_start_line: int` (1-indexed)
- `def_end_line: int` (1-indexed)
- `def_commit_sha: str` (40-char git hash from index.scip.meta.json)

**Effort: 2 days** (was 1.5 in v4; +0.5 for IngestRun index migration +
git-sha-source change + ops.recount_anchors tool).

---

### S1 + F2 — Human-name resolution

**Fix B4 — Python migration script:** Backfill `short_name` via
standalone script `services/palace-mcp/scripts/migrate_short_name.py`:

```python
#!/usr/bin/env python3
"""One-time migration: populate Symbol.short_name from SCIP qualified_name.

Run after deploying S1 schema change but BEFORE rolling out F2 resolver
(otherwise resolver returns 0 hits for backfilled symbols).
"""
from palace_mcp.extractors.scip_parser import decode_scip_short_name

# batched: SELECT 1000 rows where short_name IS NULL, decode, UPDATE
```

Decoder `decode_scip_short_name(qualified_name)` lives in
`extractors/scip_parser.py` as exported function — Python migration
imports and calls it. NOT a Neo4j procedure (cypher cannot decode
SCIP mangling).

**Fix C4 — disambiguation rate-limit:** Server-side counter keyed by
`(session_id, project_slug)`. After **3 consecutive `ambiguous_name`
envelopes within 60s for same project** → return
`error_code=disambiguation_loop_detected` + `next_action=use SCIP qn
or restart MCP session`. Counter resets on successful non-ambiguous
resolution.

**Fix S1 — regex char class:** Word-boundary regex updated to
`(?i).*(^|[._/<>():?!&,\s])` + `($|[._/<>():?!&,\s])` — covers Swift
generics (`Foo<Bar>`), protocols (`: Bar`), optionals (`?`/`!`),
composition (`Foo & Bar`), tuple params (`,`).

**Fix S2 — disambiguation cap:** Default `max_candidates: int = 15`
(was 5); operator can pass higher for legit cases like "Adapter"
returning 8+. Limit imposed only on disambiguation envelope; underlying
cypher always returns at most 50 to bound scan cost.

**Effort: 2 days** (was 1.5; +0.5 for Python migration script + rate-limit
state).

---

### F3 — dedup_by_file (unchanged from v4)

`default=False`, opt-in flag, deprecation telemetry via F4.0 counter
(S3 fix wires it). Effort: 0.25 day.

---

### F4.0 — telemetry (S3 + S4 fixes)

**Fix S3 — counters:** Schema:
```python
{
    "histograms": dict[(tool_name, phase), list[float]],  # rolling 1000
    "counters": dict[str, int],  # cumulative since process start
    "process_start_ts": float,
}
```

**Fix S4 — keying:** Per-`(tool_name, phase)` ring buffer, 1000-event
window. Example keys: `("palace.code.semantic_search", "embed_query")`,
`("palace.code.find_references", "cypher_resolve")`, etc.

**Tool surface:**
- `palace.health.metrics()` returns full snapshot dict
- `palace.health.metrics(tool_pattern="semantic_search")` filters

**Effort: 0.75 day** (was 0.5; +0.25 for counters + keying complexity).

---

### F4.1 — Qodo pre-warm (S5 fix)

**Fix S5 — failure mode:** Wrap pre-warm in try/except in
`main.py:76` lifespan. On exception:
- Log `palace.startup.qodo_prewarm_failed` with traceback
- Increment F4.0 counter `qodo_prewarm_failures`
- **Yield anyway** (degrade to cold-path on first query); do NOT
  fail-fast the container

**Fix N1 — realistic warmup string:** Use
`"public func balance() async throws -> Decimal { return 0 }"`
(real Swift idiom; ensures tokenizer + embed are exercised over
realistic syntax).

**Effort: 0.5 day** (unchanged).

---

### F4.3 — git stale-check hoist (S6 fix)

**Fix S6 — TTL documentation:** Tool description for `semantic_search`
when `include_staleness=true` is set:

> Adds 50-500ms latency for staleness metadata. Cache TTL=60s per
> repo. If you `git pull` mid-session, staleness flags may lag by
> up to 60s. For editor-grade freshness, restart palace-mcp.

Plus detached-HEAD / rebase mid-state handling: `git rev-parse HEAD`
returns commit hash in both cases (correct semantics for our equality
check, just may not match a branch tip — fine).

**Effort: 0.5 day** (unchanged).

---

### Tests + Q1/Q2 controlled benchmark harness (NEW per F4.0-N20 fix)

**Fix F4.0-N20 — N≥50 controlled benchmark:** New harness at
`bench/scripts/phase1-kill-gate.sh`:

```bash
# 1. Ensure palace-mcp running, model pre-warmed (F4.1).
# 2. Reset F4.0 metrics.
# 3. Run Q1 ("add EVM chain" prompt) × 50 with identical query string
#    via MCP HTTP, all on warm process.
# 4. Run Q2 ("find references to BalanceData") × 50.
# 5. Read palace.health.metrics, extract p50/p95 per (tool, phase).
# 6. Compare against gate thresholds, emit pass/fail per Q.
```

Output: `bench/runs/phase1-gate-YYYY-MM-DD/{metrics.json, verdict.md}`.

**Fix Q1-cold — warm precondition:** Harness step 2 asserts
`model_load_seconds == 0` across all 50 runs; if any cold-start
detected → re-run from step 1.

**Effort: 0.5 day**.

---

### Backfill slice (C3 fix)

**Fix C3 — explicit Phase 1 deploy step:** Three backfills, each via
its own command:

1. `short_name`: run `migrate_short_name.py` (one-time, ~30-60s for 380k)
2. `def_start_line`/`def_end_line`/`def_commit_sha`: re-run
   `palace.ingest.run_extractor name=symbol_index_swift --anchors-only`
   per registered project (folded into ops.recount_anchors). ~5 min total.
3. `IngestRun.group_id` index: pure DDL, instant.

Document in `docs/runbooks/palace-phase1-deploy.md`.

**Effort: 0.25 day** (unchanged; N5 ops tools cover the work).

---

### Phase 1 budget (revised v5)

| Slice | Days | Track |
| --- | --- | --- |
| S0 source anchors + IngestRun index + ops.recount_anchors | 2.0 | Codex |
| S1+F2 human-name resolution + migration + rate-limit | 2.0 | Codex |
| F3 dedup flag | 0.25 | Claude |
| F4.0 telemetry (histograms+counters+keying) | 0.75 | Claude |
| F4.1 Qodo pre-warm + yield-on-fail + realistic warmup | 0.5 | Claude |
| F4.3 git stale-check opt-in hoist + TTL doc | 0.5 | Claude |
| Ops tools (recount_anchors, recount_coverage_cache) | 0.25 | Codex |
| Backfill cyphers + integration tests | 0.25 | Codex |
| Q1/Q2 controlled benchmark harness | 0.5 | Claude |
| **Total Phase 1** | **6.5 dev-days** | — |

**Track split: Claude 2.0d (31%), Codex 4.5d (69%)** — matches
operator's "30/70" target.

---

## Phase 1 KILL GATE (v5 — revised)

### Q1 (add EVM chain): recall criterion + warm SLO

NOT "≤3× wall-time" (v3) NOT "superset" (v4). New:

- **Recall ≥80%** at limit=20 vs grep ground-truth (10 files →
  palace's top-20 must include ≥8 of them).
- **Latency:** warm-only (precondition: `model_load_seconds == 0`),
  p50 <8s, p95 <15s, measured via F4.0 over N≥50 controlled runs.
- **Pass:** recall ≥80% AND p50<8s AND p95<15s (with cold-start excl).
- **Fail:** recall <80% OR latency floor exceeded.

### Q2 (BalanceData refs): MUST PASS

- **Pass:** `find_references("BalanceData", project="uw-ios-app")`
  returns ≥30 of 31 grep-ground-truth references within p50 <1s,
  p95 <2s (warm).
- **Fail:** any number short of 30 OR latency exceeded.

### Q3: SKIPPED (Phase 2 gate)

### Outcomes (v5 default committed per C5)

- Q2 pass → **fund Phase 2** (regardless of Q1 outcome)
- Q2 fail → **archive palace**
- Q1 fail (with Q2 pass) → document as "semantic search uncompetitive
  for some classes of query; human-name lookup works"; Phase 2
  proceeds anyway

---

## Phase 2 specs (v5 — F1b with S9, S10, C7 fixes)

### F1b — sourcekit-lsp proxy

**Fix S9 — didOpen first:** Sequence:
1. Resolve symbol → file path + position via S1 short_name index
2. **`textDocument/didOpen`** with file content (read once, cache)
3. Wait for `window/workDoneProgress/end` (sourcekit-lsp indexed signal)
4. `textDocument/prepareCallHierarchy`
5. `callHierarchy/incomingCalls` or `outgoingCalls`

If step 4 returns null → return `error_code=lsp_not_ready_for_file` +
`next_action=retry or check buildServer.json`.

**Fix S10 — LRU memory cap:** Max 3 warm sourcekit-lsp subprocesses
across all projects. LRU eviction on 4th workspace request. Per-
workspace cold-start ~5s (acceptable for less-frequently-queried
projects). Env: `PALACE_LSP_MAX_WARM=3` (operator can lower for
memory-constrained dev-Macs).

**Fix C7 — P2.5 OPTIONAL fixture for iMac:** Separate slice, not
gating Phase 2. Effort 1-2 days. Builds index-store snapshot from
dev-Mac for top-3 projects (UW iOS, EvmKit, BitcoinCore), commits
to `services/palace-mcp/fixtures/lsp-snapshots/` (size ~300 MB),
mounts in iMac container. Document `data_freshness_warning` returned
with each iMac call. Operator decides post-P2 whether to invest.

**Effort: 3-4 days** for F1b, +1-2d for P2.5.

---

## Phase 3 specs (v5 — F5a, F5b, F4.2 with B5, S8, S11, N3 fixes)

### F5a — body_hash + commit_sha guard (1 day)

**Fix B5 — commit_sha guard for snippet hydration:**

```python
def get_symbol_body(symbol: dict) -> str:
    head = git_head(symbol['repo_path'])
    if head == symbol['def_commit_sha']:
        return read_file_lines(symbol['file_path'], symbol['def_start_line'], symbol['def_end_line'])
    else:
        # repo moved since ingest; read from immutable git object
        return git_show_blob(symbol['def_commit_sha'], symbol['file_path'], symbol['def_start_line'], symbol['def_end_line'])
```

`git_show_blob` uses `git show <sha>:<path>` + slice lines. Cached
per (sha, path) for 5 min to avoid repeated subprocess calls.

**Fix F5a-8h — migration: 8h conservative + checkpoint/resume:**

Migration script `scripts/migrate_body_hash.py`:
- Resumes from last completed `qualified_name` via persistent file
  `~/.palace/migration-body-hash-v2.checkpoint`
- Processes batches of 1000 symbols at a time
- Crash-safe: re-running picks up where it stopped
- Documented in `docs/runbooks/palace-phase3-deploy.md`:
  "Expected duration ~8h on MPS for 380k symbols; safe to interrupt
  and resume."

### F5b — periodic re-ingest + ignore list (S8 fix; 1 day)

**Fix S8 — ignore list:**
```python
IGNORE_DIRS = {
    '.git', '.build', 'Build', 'Index.noindex', 'DerivedData',
    '.swiftpm', 'xcuserdata', 'SourcePackages', 'Pods',
    'node_modules', '.DS_Store'
}
# Edge case: if DerivedData lives outside repo root via Xcode build
# settings, F5b will NOT walk it — false-negative-safe (won't trigger
# stale ingest), but documented in runbook.
```

### F4.2 — coverage cache + atomic invalidation (S11 fix; 1 day)

**Fix S11 — atomic recount+token:** Single Cypher transaction:
```cypher
MATCH (p:Project {slug: $slug})
WITH p, randomUUID() AS new_token
CALL {
    WITH p
    MATCH (s:Symbol {group_id: 'project/' + p.slug})
    RETURN count(s) AS total, sum(CASE WHEN s.embedding IS NOT NULL THEN 1 ELSE 0 END) AS embedded
}
SET p.symbol_total_cached = total,
    p.symbol_embedded_cached = embedded,
    p.cache_version_token = new_token,
    p.cache_updated_at = datetime()
RETURN total, embedded, new_token
```

Single atomic commit; no race window between count and token write.

### N3 — global Neo4j write semaphore (promoted to SHOULD-FIX)

In-process semaphore via `asyncio.Semaphore(2)` in
`extractors/runner.py`. Max 2 concurrent `run_extractor` calls across
ALL projects. Per-project flock unchanged (still serializes within
project). Documented as `PALACE_INGEST_GLOBAL_CONCURRENCY=2` env.

---

## Cross-cutting (unchanged from v4 except where noted)

- Failure-mode catalog: still mandated per slice
- Telemetry-driven gate decisions: still F4.0 evidence required
- Backfill stories: now explicit Phase 1 deploy slice (C3)

---

## Open decisions for operator (v5 — reduced to 2)

v4 had 5 open decisions. v5 commits defaults on 3 (per C5 + N4 + C7).
Remaining:

1. **Phase 1 budget approval** — 6.5 dev-days + ~$2-3k Anthropic.
   Acceptable to validate kill-gate? Yes/no.
2. **P2.5 iMac fixture investment** — after Phase 2 ships and dev-Mac
   call_hierarchy works, do you want to spend 1-2 days building the
   iMac fixture snapshot, or accept iMac as call-graph-degraded?
   (Decision deferred to post-P2; default = accept iMac degraded
   unless explicitly requested.)

---

## Decision log

- 2026-05-30 (v1) — initial 5-fix spec.
- 2026-06-01 (v1 review) — 3 voltAgents rejected.
- 2026-06-01 (v3) — phase-split + sourcekit-lsp alt.
- 2026-06-01 (v3 review) — operator rejected: 7 blockers.
- 2026-06-01 (v4) — fixed 7 v3 blockers; left 5 open decisions.
- 2026-06-01 (v4 review) — 3 voltAgents found 10 blockers + 6 majors
  + 11 should-fix + 5 nice-to-have.
- 2026-06-01 (v5) — fixed all NEEDED items (10 blockers, 6 majors,
  11 should-fix, 2 promoted), committed defaults on C5 + N4 + C7.
  Reduced open decisions to 2.
