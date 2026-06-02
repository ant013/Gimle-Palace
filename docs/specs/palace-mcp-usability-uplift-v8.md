# Spec — palace-mcp usability uplift v8 (paperclip-launch-ready)

Status: ready for operator approval + paperclip walker launch.
Grounded at repo state: `origin/develop` /
`5d9329f62b453e94bda2fca6431c7e0d7b2e5b8a`
(`GIM-1096: human-name resolution and result dedup`).
Supersedes: v1, v3, v4, v5, v6, v7. v7's 3-voltAgent critical review
returned 6 blockers + 9 major/should-fix findings. v8 fixes all NEEDED
items + verifies every claim against actual source/git log.

---

## §0 v7 → v8 changelog (audit-verified, source-grounded)

### Verified TRUE from audit chain (v7 §0 claims confirmed)

| v7 claim | Verification |
| --- | --- |
| PR #360 (`2cd0acb`) GIM-1063 storage contract merged to develop | ✅ `git log` shows `2cd0acb0 docs(GIM-1063): extractors storage contract — Tantivy/Neo4j split (#360)` |
| PR #361 (`9775409`) GIM-1064 audit doc merged | ✅ `git log` shows `97754094 docs(GIM-1064): extractor count sanity audit (#361)` |
| PR #362 (`e6c1b855`) GIM-1062 re-ingest merged | ✅ `git log` shows `e6c1b855 fix(GIM-1062): re-ingest 9 false-done projects, resolve 45 GIM-1071 failures (#362)` |
| GIM-1071 root cause = ConstraintCreationFailed on (:Symbol qualified_name, group_id) | ✅ Origin: `470f0d69 feat(GIM-1057): Symbol soft-delete + unique constraint (Block A)` (feature branch); develop-merged at `722f10d2 (#348)` added the constraint; re-ingest in `e6c1b855 (#362)` resolved the 45 failures the constraint caused on existing duplicate-bearing data |
| `symbol_index_swift` writes to Neo4j :Symbol | ✅ confirmed via PR #360 storage contract doc |

### Verified FALSE in v7 (fixed in v8)

| v7 claim | Reality | v8 fix |
| --- | --- | --- |
| Phase 0 S(-1) needs to add `deleted_at` to :Symbol | **Already shipped via GIM-1057 (PR #348, commit `470f0d69`).** `symbol_node_writer.py:75,81,196,205` has it + `soft_delete_symbols()` function | Phase 0 scope reduced: drop `deleted_at` work; keep only IngestRun normalization. Phase 0 = 1.0d not 2.0d |
| IngestRun migration: simple `SET r.run_id = r.id REMOVE r.id` | **Two writers have DIFFERENT field sets**, not just different keys. cypher.py:11-27 (CREATE) has `{id, source, group_id, extractor_name, project, started_at, finished_at, duration_ms, nodes_written, edges_written, errors, success}`. checkpoint.py:24-33 (MERGE) has only `{run_id, project, extractor_name, started_at, success, error_code}` | v8 §3 migration is two-pass: (a) key rename, (b) backfill missing `group_id`/`source`; unknown legacy `finished_at` stays NULL and forces re-ingest for freshness consumers |
| `dead_code/seeds.py:16` has join-instance bug | **File:line is wrong** — `seeds.py:14-18` is Python `set.add(qn)`, no Cypher. Actual join-instance bug location TBD by GIM-1064 follow-up team | v8 §0 cites GIM-1064 audit findings without false file:line; defers location to follow-up team |
| HNSW vector index handles in-project queries efficiently | **Index is GLOBAL** (`schema.py:164-171` — no group_id partition). Post-HNSW filter on `group_id IN $group_ids`. At `limit=20`, current `_candidate_limit()` uses `query_k=200` for a single-project query, which yields ~20 in-scope candidates at ~10% per-project share. **Q1 recall ≥80% NOT guaranteed.** | v8 adds new slice **F4.4 — HNSW per-project query budget**: raise single-project query_k to 2000 (10x current Q1 baseline); document tradeoff. Per-project filtered index (option A) deferred to Phase 3 |
| F4.0 telemetry JSONL sink "for benchmark" | **Path/schema/fsync policy unspecified** — not implementable | v8 §F4.0 spec: explicit path `~/.palace/benchmark/<PALACE_BENCHMARK_RUN_ID>.jsonl`, schema, line-buffered (no fsync), one-line-JSON-per-event |
| Gold corpus pins SHA but unspecified WHICH repo | **Must pin BOTH UW iOS source + palace-mcp service code SHAs** (grep ground-truth depends on UW source; embedding query results depend on palace extractor version) | v8 GOLD slice acceptance: `repo-pins.json` MUST have both `uw_ios_sha` and `palace_mcp_sha` fields |
| Hydration loop sequential per result hit | **Already fixed at grounded SHA `5d9329f6`.** `find_semantic.py` now uses `asyncio.gather()` and post-gather accumulator processing. | v8 removes hydration implementation from scope; F4.3 keeps only stale-check opt-in hoist and adds a non-regression assertion that hydration remains parallel |
| Walker = CEO = epic owner | Role-mixing creates ambiguity (walker self-blocks, walker drafts verdict, walker self-unblocks?) | v8 §6 explicit: **CEO acts AS walker** for orchestration (POST + self-block + self-unblock only). **CTO drafts gate verdicts** (separate role). Operator co-signs |
| F1B-SPIKE memory budget unenumerated | sourcekit-lsp 1-3GB + Qodo 6GB + Neo4j heap 8GB + page cache + Python + Tantivy mmap → potential OOM on 32GB dev-Mac | v8 §F1B-SPIKE acceptance: cap LSP pool=1 workspace for spike, document memory ceiling |

---

## §1 Phase plan (v8 — Phase 0 narrowed, F4.4 added)

```
GIM-1062 + GIM-1063 + GIM-1064 (audit chain) ── DONE ─────────────┐
                                                                   │
                                                                   ▼
Phase 0 — IngestRun normalization (1.0d Codex; was 2.0d in v7)
  S(-1)  Unify :IngestRun contract (run_id key) + backfill missing
         group_id/source fields for checkpoint-origin rows; keep unknown
         legacy finished_at NULL and force re-ingest for freshness consumers
         (deleted_at work DROPPED — already shipped via GIM-1057)
                                                                   │
                                                                   ▼
Phase 1 — Foundation + Gold Freeze (8.5 dev-days; Claude 3 / Codex 5.5)
  S0     Source anchors + repo_head_sha + Swift-only recount_anchors tool
  S1+F2  Human-name resolution + Python migration + rate-limit
  F3     dedup_by_file=False flag
  F4.0   Telemetry (ring buf + explicit JSONL sink contract)
  F4.1   Qodo pre-warm + yield-on-fail
  F4.3   git stale-check opt-in hoist; preserve existing parallel hydration
  F4.4   HNSW per-project query budget (NEW; raise query_k cap to 2000 for
         single-project queries; add precision@20 diagnostic)
  GOLD   Frozen gold corpus (uw_ios_sha + palace_mcp_sha)
  DEPLOY Phase 1 deploy runbook + provisioning
  Q1Q2-HARNESS Controlled benchmark with N≥50 + warm precondition
                                                                   │
                                                                   ▼
                                              ┌─ GATE 1 (B6 strict)        │
                                              │  Q1 recall≥80% @ limit=20  │
                                              │     + p50<8s warm          │
                                              │     + precision@20 reported│
                                              │  Q2 MUST PASS              │
                                              │  CTO drafts verdict        │
                                              │  Operator co-signs         │
                                              └────────────────────────────┘
                                                        │
                                                        ▼
Phase 2 — Call Hierarchy (4-5d Codex, single-track)
  F1B-SPIKE  One workspace E2E + memory budget enumerated (1d)
  F1B-IMPL   Workspace pool LRU max 3 + MCP tool (2d)
  F1B-HARDEN Error envelopes + iMac contract + tests (1-2d)
                                                        │
                                              ┌─ GATE 2 (Q3 must pass)     │
                                                        │
                                                        ▼
Phase 3 — Freshness (conditional, 3d)
  F5a   body_hash + commit_sha guard (analog: blame_walker.py:81 pygit2)
  F5b   mtime vs IngestRun.finished_at periodic
  F4.2  Coverage cache + atomic invalidation + global semaphore
  (F4.4-α-OPTIONAL) Per-project vector index (alternative to query_k=2000)
```

**Phase 1 effort 8.0d → 8.5d** (+0.5 for F4.4 HNSW slice; F4.3 remains
0.5d for stale-check opt-in plus hydration non-regression coverage).
**Phase 0 effort 2.0d → 1.0d** (deleted_at work dropped).
**Total Phase 0+1: 9.5 dev-days (was 10).**

---

## §2 Walker process (v8 — role separation per architect concern #6)

```
walker (CEO 10a4968e) state machine:

  CEO acts AS walker.
  CEO does ORCHESTRATION ONLY: POST issues, self-block, self-unblock.
  CEO does NOT draft gate verdicts (CTO drafts; Operator co-signs).
  CEO is also the epic owner — that's OK because orchestration ≠ verdict.

  state = idle
  loop:
    state = picking_next
    pair = walker reads roadmap (next 1-2 slices, claude+codex if both available + no file overlap)
    POST issue(s):
      Claude → PythonEngineer (127068ee)
      Codex  → CXPythonEngineer (e010d305)
    walker self-block: status=blocked, blockedBy=[slice_ids]
    state = blocked_on_slices
    await: notification "slice X done"
      if all_blockers_done: unblock self → continue
    state = unblocking
  end
```

**Hard rules (committed v8):**
1. Max 2 simultaneous slices (1 Claude + 1 Codex)
2. No mass upfront creation
3. File-overlap verified per cycle
4. **Walker MUST re-verify file:line citations against develop tip at
   issue-POST time** (other agents may have moved lines via parallel
   PRs; spec line numbers can drift between draft and execution)
5. Gate verdict drafted by CTO (not walker); operator co-signs
6. Walker NEVER decides archive/P2.5/threshold changes
7. **CEO = orchestrator; CTO = verdict author; operator = sign-off**

---

## §3 Phase 0 — IngestRun normalization (narrowed from v7)

### S(-1) — Unify :IngestRun contract

**Problem (verified):**
- `extractors/cypher.py:13-27` `CREATE_INGEST_RUN`: CREATE node with key `id`, fields `{id, source, group_id, extractor_name, project, started_at, finished_at, duration_ms, nodes_written, edges_written, errors, success}`. **Uses CREATE → duplicate-prone on retry.**
- `extractors/foundation/checkpoint.py:24-33` `_WRITE_INGEST_RUN_CYPHER`: MERGE on key `run_id`, fields `{run_id, project, extractor_name, started_at, success, error_code}`. **No `group_id`, no `source`, no `finished_at`.**

These coexist on `:IngestRun` nodes. F5b cannot rely on `MAX(r.finished_at) WHERE r.group_id = ...` because checkpoint-origin rows have neither.

**Fix:**
1. **Canonical contract:** `:IngestRun {run_id (key), group_id, source, extractor_name, project, started_at, finished_at, duration_ms, nodes_written, edges_written, errors, success, error_code}`.
2. **Migration (two-pass):**
   - Pass 1 — key rename: `MATCH (r:IngestRun) WHERE r.id IS NOT NULL AND r.run_id IS NULL SET r.run_id = r.id REMOVE r.id`
   - Pass 2 — backfill checkpoint-origin: `MATCH (r:IngestRun) WHERE r.group_id IS NULL SET r.group_id = "project/" + r.project, r.source = "extractor." + r.extractor_name`
   - Pass 3 — **leave `finished_at` NULL for completed-but-undated legacy
     rows** (no fabricated timestamps in graph). F5b reads NULL as
     "unknown finished_at — re-ingest required to refresh". This is
     safer than the v7 heuristic `started_at + duration({days: 1})`
     (correct Cypher would be `duration({days: 1})`, not `P1D`, but
     fabricating wall-clock data is wrong regardless).
3. **Update writers:**
   - `cypher.py:CREATE_INGEST_RUN` → `MERGE (r:IngestRun {run_id: $run_id})` instead of `CREATE`. Pass `$run_id` instead of `$id`; initialize `error_code: null`.
   - `cypher.py:FINALIZE_INGEST_RUN` → match on `run_id`, not `id`, and set `error_code = $error_code`.
   - `runner._finalize()` → pass `error_code = null` on success and the structured extractor `error_code` on failure.
   - `checkpoint.py:_WRITE_INGEST_RUN_CYPHER` → also set `group_id`, `source` on create.
4. **Indexes:**
   - `CREATE INDEX ingest_run_id_idx FOR (r:IngestRun) ON (r.run_id)`
   - **Follow-up issue PALACE-S-1-FOLLOWUP-1:** convert `ingest_run_id_idx`
     to UNIQUE constraint after duplicate audit confirms 0 dup `run_id`.
     Filed before Phase 0 ships.
   - `CREATE INDEX ingest_run_group_idx FOR (r:IngestRun) ON (r.group_id)`
5. **Touch-point sweep (per code-reviewer):** grep entire repo for
   `IngestRun`, then update every extractor-owned old-key lifecycle caller
   that creates or matches on `id` instead of `run_id` (examples at this
   repo state: `extractors/cypher.py`, `code/find_owners.py`,
   `extractors/cross_repo_version_skew/neo4j_writer.py`,
   `extractors/testability_di/neo4j_writer.py`,
   `extractors/code_ownership/extractor.py`). Do not rely on a single
   literal such as `IngestRun {id:` because whitespace and variable names
   differ.
6. **Schema drift test** updated in
   `services/palace-mcp/tests/extractors/unit/test_schema.py`.

**Acceptance:**
- 0 `:IngestRun` nodes with NULL `run_id` post-migration
- 0 rows with NULL `group_id` for completed (`success IS NOT NULL`) runs
- Both writers produce canonical rows
- A post-migration extractor run for `project/litecoin-kit` writes a
  canonical row where `finished_at IS NOT NULL`
- Legacy checkpoint-origin rows with unknown finish time may keep
  `finished_at = NULL`; F5b treats that as "unknown, re-ingest required"
- Existing tests pass + new tests for canonical contract

**Effort: 1 day** (was 2.0; soft-delete work dropped — already shipped).

---

## §4 Phase 1 specs

### S0 — Source anchors + repo_head_sha + recount_anchors

**Current verified state:** SCIP metadata writers already emit
`repo_head_sha` (not `git_sha`) in `cli.py:_write_scip_metadata()` and
the Swift emitter scripts. `symbol_index_swift.run()` currently computes
HEAD itself; `run_extractor` currently accepts only `name`, `project`,
`bundle`, and `scip_path`.

**Fix:**
1. Add `read_scip_commit_sha(scip_path: Path) -> str` in
   `extractors/scip_parser.py`. It reads sibling `index.scip.meta.json`,
   requires a valid 40-character `repo_head_sha`, and returns a typed
   extractor error on missing or malformed metadata.
2. Persist definition anchors on `:Symbol` during SCIP-backed writes:
   `def_start_line: int`, `def_end_line: int`, `def_commit_sha: str`.
   SCIP line numbers are 0-indexed; Neo4j fields are 1-indexed.
3. Decode SCIP definition ranges for both arities:
   - `[start_line, start_col, end_col]` -> single-line definition
   - `[start_line, start_col, end_line, end_col]` -> multi-line definition
4. Do **not** change the shared `BaseExtractor.run()` ABI and do **not**
   add `anchors_only` to generic `run_extractor`; that would break
   non-Swift extractors with current signatures.
5. Add a Swift-only helper in `symbol_index_swift.py`, for example
   `recount_swift_symbol_anchors(driver, project, scip_path=None)`, that
   updates only existing `:Symbol` anchor fields and skips embedding
   refresh, Tantivy writes, and relationship rewrites.
6. Add `palace.ops.recount_anchors(project, scip_path=None)` MCP tool as a
   thin Swift+SCIP wrapper around that helper. It returns
   `unsupported_project` for non-Swift/no-SCIP projects instead of trying a
   generic extractor run.

**Acceptance:**
- `run_extractor` and `BaseExtractor.run()` signatures are unchanged.
- `palace.ops.recount_anchors(project, scip_path=None)` works for a
  Swift+SCIP project and returns a structured unsupported/no-scip error for
  other projects.
- Recounting anchors does not rewrite embeddings or Tantivy documents.
- `:Symbol` rows for Swift projects have non-null `def_start_line`,
  `def_end_line`, and `def_commit_sha` after recount.
- Malformed or missing SCIP metadata fails with a clear extractor error.

**Effort: 2.0d.**

### S1+F2 — Human-name resolution

Resolver lives in `code_composite.py:_resolve_qn()` (not in the
non-existent `code/find_references.py`). Search graph wiring also lives in
`code_composite.py`, not `code/search_graph.py`.

**Fix:**
- Add SCIP short-name decoding in `extractors/scip_parser.py`.
- Persist `short_name` in `symbol_node_writer.py`; backfill existing rows
  via `services/palace-mcp/scripts/migrate_short_name.py`.
- Extend `_resolve_qn()` to try exact qualified_name first, then
  `short_name` disambiguation for human names.
- Cap ambiguity results at 15 candidates and rate-limit repeated
  disambiguation loops with in-process state keyed by `(session_id,
  project_slug)`. Reset on successful non-ambiguous resolution.

**Acceptance:**
- Human input like `MoneroAdapter` resolves to a concrete qualified_name or
  returns a bounded `ambiguous_qualified_name` envelope.
- Backfill script is resumable and reports counts.
- Existing exact qualified_name behavior is unchanged.

**Effort: 2.0d.**

### F3 — dedup_by_file=False flag

Patch `code/find_semantic.py` for semantic search and `code_composite.py`
for the search_graph composite path. Add a `dedup_by_file: bool = False`
parameter; `False` is the back-compatible default.

**Acceptance:** callers can request file-level dedup explicitly without
changing default result behavior.

**Effort: 0.25d.**

### F4.0 — Telemetry (CONCRETE spec per code-reviewer blocker)

**Live in-process ring buffer:**
- `palace_mcp/telemetry/ring_buffer.py` — `collections.deque(maxlen=1000)` per `(tool_name, phase)`
- `palace_mcp/telemetry/counters.py` — `collections.Counter` cumulative
- `palace.health.metrics(tool_pattern=None)` returns snapshot

**JSONL audit sink (CONCRETE):**
- Builds on the existing `palace_audit_sink_path`/`PALACE_AUDIT_SINK_PATH`
  setting, which already opens a JSONL file from `main.py:lifespan()`.
- Benchmark harness sets `PALACE_BENCHMARK_RUN_ID=<id>` and, unless an
  explicit audit path is provided, derives sink path
  `~/.palace/benchmark/{run_id}.jsonl` (mkdir if missing).
- **Open mode for benchmark-derived paths:** `os.O_WRONLY | os.O_CREAT |
  os.O_EXCL` on first open. Duplicate `run_id` fails service startup with
  a clear `run_id_collision` startup error; it cannot be returned from an
  MCP tool call because the file is opened during lifespan startup.
- Existing manually configured `PALACE_AUDIT_SINK_PATH` remains supported;
  F4.0 must document whether manual paths use append or exclusive mode.
- Append-only, **line-buffered (`buffering=1`)**, NO fsync
- **Async-safety:** single `asyncio.Lock` per sink; each write emits a
  fully-formed line via single `write()` call inside lock → no
  byte-interleaving from concurrent coroutines
- **Lifecycle owner:** sink lifecycle bound to FastAPI lifespan in
  `services/palace-mcp/src/palace_mcp/main.py` — open on startup if
  env set, register `atexit` cleanup + `lifespan` shutdown handler
- Schema extends the existing audit row shape rather than replacing it.
  Existing fields (`timestamp`, `tool_name`, `request_args`,
  `response_summary`, `latency_ms`, `error`) remain present; benchmark
  rows add `run_id`, `phase`, `duration_ms`, and `meta` where applicable.
  Example:
  ```jsonl
  {"timestamp":"2026-06-02T00:00:00Z","tool_name":"palace.code.semantic_search","request_args":{...},"response_summary":"ok","latency_ms":3812,"error":null,"run_id":"phase1-gate-2026-06-XX","phase":"embed_query","duration_ms":3812,"meta":{...}}
  ```
- Sink closed on process exit (no rotation, no max-size; benchmark runs are bounded)
- On process crash: last OS-buffer (~4KB) may be lost — acceptable since crash invalidates run

**Effort: 1.0d.**

### F4.1 — Qodo pre-warm + yield-on-fail

`main.py:lifespan()` already has a startup hook for Qodo pre-warm. Tighten
it so the warmup uses a realistic semantic query string, records an F4.0
counter on failure, logs the exception, and never blocks service startup.

**Acceptance:** a forced Qodo warmup failure increments the counter and the
MCP server still starts.

**Effort: 0.5d.**

### F4.3 — git stale-check opt-in hoist + hydration non-regression

**Fix:** add an opt-in `include_staleness` flag so the hot path does
not run git freshness checks unless the caller asks for them. Tool
descriptions must state the default and the warning semantics.

**Already shipped at grounded SHA:** hydration now uses
`asyncio.gather()` in `find_semantic.py`, with post-gather accumulator
processing. F4.3 must preserve that behavior and add a regression test or
targeted code assertion that context hydration stays parallel.

**Effort: 0.5d.**

### F4.4 — HNSW per-project query budget (NEW per perf blocker)

**Problem:** Global vector index over 380k symbols + post-HNSW
`group_id IN $group_ids` filter. Current `_candidate_limit()` computes
`query_k=200` for the Q1 single-project gate case (`limit=20`,
`scope_size=1`). At ~10% per-project share, that yields roughly 20
in-scope candidates before final ranking. Q1 recall ≥80% is therefore not
guaranteed.

**Fix:**
1. Modify `_candidate_limit()` in `find_semantic.py:381-382`:
   ```python
   def _candidate_limit(limit: int, scope_size: int) -> int:
       if scope_size == 1:
           return min(max(limit * 100, 500), 2000)  # Q1 limit=20 => 2000
       return min(max(limit * scope_size * 10, 50), 500)  # multi-project: current
   ```
2. Add F4.0 instrument point: `hnsw_query_k_used`, `hnsw_in_scope_ratio`
3. Add `precision@K` (computed from gold corpus) as **diagnostic** in
   Q1 gate report alongside `recall@K`. **Baseline precision recorded
   pre-change** so we can detect noise inflation from larger k.
4. Document the trade-off in tool description: "single-project queries
   use query_k=2000 for higher recall (10x the current Q1 baseline; record
   actual latency and transient-memory impact in the gate report)"

**Deferred to Phase 3 as alt path:**
- F4.4-α: per-project filtered vector index (Neo4j 5.26
  `OPTIONS { partition_filter }`) — fundamentally faster but more
  complex; ship if F4.4 query_k=2000 doesn't get Q1 recall ≥80%

**Effort: 0.5d.**

### GOLD — Frozen gold corpus (concrete pins per code-reviewer blocker)

`bench/gold/phase1-frozen-YYYY-MM-DD/`:
```
repo-pins.json
  {
    "uw_ios_sha": "<40-char>",         # UW iOS app source SHA
    "palace_mcp_sha": "<40-char>",     # palace-mcp service code SHA
    "neo4j_snapshot_path": "neo4j-symbol-counts.json",
    "neo4j_snapshot_format": "json_manifest",
    "freeze_date": "2026-06-XX"
  }
neo4j-symbol-counts.json
  # Per-project :Symbol counts at freeze time:
  # {"uw-ios-app": 70697, "bitcoin-core": 46661, ...}
  # Used to detect drift; NOT a full DB dump (too large).
Q1-add-evm-chain/{prompt.txt, expected-files.json, precision-recall-rules.md, reference-runs/}
Q2-balance-data-refs/{prompt.txt, expected-references.json, ...}
Q3-monero-adapter-calls/{prompt.txt, expected-callers.json, ...}
```

**Acceptance:**
- Both SHAs pinned (uw_ios_sha + palace_mcp_sha)
- `neo4j_snapshot_path` references a JSON manifest of per-project :Symbol
  counts taken AFTER S0 backfill completes (so anchors are present)
- Q1/Q2/Q3 grep ground-truth files run on the pinned UW iOS SHA
- **Pre-gate runbook step:** harness asserts current
  `MATCH (s:Symbol) WHERE s.group_id = $g RETURN count(s)`
  matches snapshot ±5% per project; if drift detected, abort gate
  with `error_code=neo4j_drifted_from_gold` and request operator
  decision (re-pin OR fix the cause)
- If a follow-up PR lands during Phase 1 (e.g. GIM-1064 follow-up extractor fix), gold corpus stays frozen — gate evaluation uses the snapshot, not live Neo4j

**Effort: 0.5d.**

### DEPLOY — Phase 1 deploy + provisioning

Deliver `services/palace-mcp/scripts/phase1-deploy.sh` plus
`docs/runbooks/palace-phase1-deploy.md`.

Runbook must include:
- pre-checks for Phase 0 completion and Phase 1 merged SHA
- S0 `palace.ops.recount_anchors` only for Swift projects with available
  SCIP metadata; non-Swift/no-SCIP projects are explicitly skipped with
  documented reason
- idempotent schema/index creation
- local verification commands for `services/palace-mcp`
- rollback steps for new indexes and MCP wiring
- iMac container and dev-Mac native provisioning notes

**Effort: 0.5d.**

### Q1Q2-HARNESS — Controlled benchmark

Deliver `bench/scripts/phase1-kill-gate.sh` and
`bench/scripts/run-controlled-benchmark.py`.

Harness requirements:
- assert warm precondition before measuring
- set `PALACE_BENCHMARK_RUN_ID=phase1-gate-YYYY-MM-DD`
- run N>=50 controlled identical-query samples for Q1 and Q2
- read the JSONL sink directly
- compute recall, precision@20 diagnostic, p50, and p95
- compare against the frozen gold corpus and write `verdict.md`

**Effort: 0.75d.**

---

## §5 Phase 1 KILL GATE (v8 — strict B6 + precision diagnostic)

### Q1 (add EVM chain)
- **Recall ≥80%** at limit=20 vs frozen gold expected-files
- **precision@20** reported as diagnostic (not threshold)
- **Latency:** warm-only (asserted by harness), p50<8s, p95<15s
- N≥50 controlled runs via JSONL sink
- **Pass:** recall met + latency met

### Q2 (BalanceData refs) — MUST PASS
- ≥30 of 31 expected references
- p50<1s, p95<2s warm
- **Fail outcome:** archive palace immediately (default v5/C5)

### Q3 — SKIPPED for Phase 1

### Gate verdict authority
- **CTO drafts** verdict from harness output + telemetry
- **Operator co-signs** verdict
- Walker (CEO) records verdict, takes action (next pair OR archive)
- Adjustment window (1d): **harness bugs ONLY**; threshold change = new spec + restart

---

## §6 Phase 2 (call hierarchy)

### F1B-SPIKE (v8 with memory budget enumerated)

**Memory budget for spike acceptance:**
- LSP pool capped at 1 workspace
- Concurrent processes during spike: Qodo MPS (6GB) + Neo4j JVM (8GB
  heap + page cache 4GB ≈ 12GB) + Python runtime (~1GB) + Tantivy mmap
  (1-2GB) + sourcekit-lsp 1 workspace (2-3GB) = **22-26 GB**
- Dev-Mac 32GB has 6-10GB headroom; operator MUST NOT run Xcode IDE
  concurrently during spike
- If memory exceeded → spike documents what got OOM and proposes
  workspace pool max ≤2 in F1B-IMPL

**Effort: 1.0d.**

### F1B-IMPL + F1B-HARDEN

F1B-IMPL builds the workspace pool with LRU max 3, sourcekit-lsp stdio
client, and `palace.code.call_hierarchy` MCP tool. F1B-HARDEN adds
structured error envelopes, subprocess shutdown/cleanup, iMac runtime
contract, and tests. P2.5 iMac fixture remains optional and requires
operator approval after Gate 2.

**Effort: 2.0d + 1-2d.**

---

## §7 Phase 3 (freshness)

### F5a — body_hash + commit_sha guard

**Analog (per code-reviewer):**
- pygit2 path in `extractors/code_ownership/blame_walker.py:81-84`:
  `repo[head_commit.tree[path].id]` — read blob without subprocess
- Alternative: `palace_mcp/git/tools.py:205` (`palace_git_show`)
- F5a uses pygit2 (faster, no subprocess fork per file)

**Migration:** ~8h conservative + checkpoint/resume.

**Effort: 1.0d.**

### F5b — Periodic re-ingest

Build `palace_mcp/ops/detect_stale_files.py` and
`services/palace-mcp/scripts/palace-periodic-reingest.sh`. It compares
file mtimes against canonical `:IngestRun.finished_at`; rows with NULL
`finished_at` are stale-by-definition and must trigger re-ingest rather
than silently passing freshness checks. Include an ignore list, per-project
flock, and a global semaphore.

**Effort: 1.0d.**

### F4.2 — Coverage cache

Cache expensive coverage counts behind an atomic invalidation path. The
recount operation uses a single Cypher transaction so readers never observe
partially refreshed coverage values; execution is protected by a global
semaphore.

**Effort: 1.0d.**

### F4.4-α (OPTIONAL alt path)

If F4.4 query_k=2000 doesn't get Q1 recall ≥80%, build per-project
filtered HNSW index. Out of Phase 3 scope unless triggered.

---

## §8 Cross-cutting (unchanged)

- Failure-mode catalog mandated per slice
- F4.0 telemetry evidence for gate decisions
- Backfill stories explicit in Phase 1 deploy slice

---

## §9 Open decisions for operator (v8 — 2 remaining)

1. **Phase 0 + Phase 1 budget approval:** 9.5 dev-days + ~$3-4k Anthropic
2. **P2.5 iMac fixture** — default deferred; operator opt-in post-Phase 2

---

## §10 Decision log

- 2026-05-30 (v1) → 3-voltAgent rejection
- 2026-06-01 (v3) → operator 7 blockers
- 2026-06-01 (v4) → 3-reviewer audit 10 blockers
- 2026-06-01 (v5) → operator 8 contract errors
- 2026-06-01 (v6) → drafted on hypothesis of unfinished audit chain
- 2026-06-01 (v7) → drafted post-audit-chain DONE; 3-reviewer found
  6 blockers + 9 major
- 2026-06-01 (v8) — **fixes all 6 v7 blockers + 9 major**, verified
  every source claim, narrows Phase 0 (deleted_at already shipped),
  adds F4.4 HNSW query budget, concretes F4.0 JSONL sink, expands
  IngestRun migration to backfill missing fields, separates walker
  (CEO orchestrator) from verdict author (CTO).
- **Next:** voltAgent confirm v8 fixes hold → operator approve → paperclip walker launch.
