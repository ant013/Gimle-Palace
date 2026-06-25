# Spec — palace-mcp usability uplift v6 (audit-execution-ready)

Status: ready for operator approval.
Supersedes: v5 (operator rejected 2026-06-01 — 8 contract-level errors:
wrong SCIP metadata key, non-existent extractor flag, audit-chain
prerequisites mis-stated, walker file map fictional, IngestRun lifecycle
not normalized, gate-adjustment allows goalpost moving, telemetry not
audit-grade, F1B too coarse).

**v6 is self-contained** — no required cross-references to v4/v5 except
this changelog.

---

## v5 → v6 change log (8 audit blockers fixed)

| ID | v5 had | v6 fix |
| --- | --- | --- |
| B1 | `{"git_sha": ...}` from `index.scip.meta.json` | `{"repo_head_sha": ...}` — verified in `cli.py:_write_scip_metadata()` + `scip_emit_swift_kit.sh:475` |
| B2 | `recount_anchors` calls extractor with `--anchors-only` (doesn't exist in contract) | Two options consolidated: (a) extend `BaseExtractor.run` + `run_extractor` MCP tool with `anchors_only: bool = False` param, OR (b) full re-run via existing contract. v6 picks (a) — 0.5d to plumb the flag. |
| B3 | Walker plan blocked PALACE-S0 only on GIM-1063 | v6 spec + plan: **ALL THREE** audit-chain issues (1062 + 1063 + 1064) must land before Phase 1 starts. Walker enforces via explicit blockedBy list. |
| B4 | Walker plan referenced non-existent `code/find_references.py`, `code/search_graph.py` | v6 walker plan uses **only verified file paths**: resolver lives in `code_composite.py:_resolve_qn()` (line 140), graph search in `code_composite.py:_search_graph()`. See File Map §. |
| B5 | F4.2/F5b depend on consistent `:IngestRun` model, but two writers use different keys (`id` vs `run_id`) | New prerequisite slice **S(-1) Data Lifecycle Normalization**: unify on `run_id`, deprecate `id`, migration cypher, single `IngestRun` contract documented |
| B6 | Gate adjustment protocol allowed threshold revision post-evidence | Tightened: adjustment scope **explicitly limited to harness bugs**. Threshold change = new spec version + fresh re-run. Cannot loosen Q1 SLO mid-evaluation. |
| B7 | F4.0 telemetry is process-lifetime ring buffer; harness "reset metrics" incompatible | v6: F4.0 ships **two surfaces** — (1) live in-process histograms for ops, (2) **run-scoped JSONL sink** at `bench/runs/<run-id>/metrics.jsonl` for audit-grade benchmark evidence. Sink decoupled from ring buffer. |
| B8 | F1B = single 3-4d slice covering all of palace_mcp/lsp/ from scratch | Split into 3 slices: **F1B-spike (1d)** prove sourcekit-lsp end-to-end on one workspace → **F1B-impl (2d)** workspace pool + tool + LRU → **F1B-harden (1-2d)** error envelopes + iMac contract + tests |

---

## Phase plan (v6 — 4 phases, 2 kill gates, normalized data lifecycle)

```
GIM-1062 + GIM-1063 + GIM-1064 (audit chain) ──── must land first ─────┐
                                                                        │
                                                                        ▼
Phase 0 — Data Lifecycle Normalization (NEW; 2 dev-days)
  S(-1)  Unify :IngestRun contract (run_id key)                         │
         Active Symbol contract (deleted_at semantics)                  │
         Freshness primitives (mtime, finished_at indexed)              │
                                                                        │
   ↓                                                                    │
                                                                        ▼
Phase 1 — Foundation + Gold Freeze (8 dev-days)
  S0    Source anchors + IngestRun.group_id index +                    │
        repo_head_sha extraction + recount_anchors w/ anchors_only      │
        extractor flag                                                  │
  S1+F2 Human-name resolution + Python migration + rate-limit          │
  F3    dedup_by_file=False flag                                        │
  F4.0  Telemetry (ring buf + JSONL sink) + counters + keying          │
  F4.1  Qodo pre-warm + yield-on-fail                                  │
  F4.3  git stale-check opt-in hoist                                   │
  GOLD  Frozen gold corpus (queries + repo SHA + expected refs)       │
  DEPLOY Phase 1 deploy runbook + provisioning slice                   │
                                                                        │
                                                                        ▼
                                              ┌─ GATE 1 (1-day window) │
                                              │  Q1 recall ≥80% + warm │
                                              │  Q2 must-pass refs     │
                                              │  Adjust window: harness│
                                              │  bugs ONLY, not thresh │
                                              └────────────────────────┘
                                                        │
                                                        ▼
Phase 2 — Call Hierarchy (3-spike+impl+harden, 4-5 dev-days)
  F1B-spike   One workspace end-to-end (1d)
  F1B-impl    Workspace pool + LRU + MCP tool (2d)
  F1B-harden  Error envelopes + iMac contract + tests (1-2d)
                                                        │
                                                        ▼
                                              ┌─ GATE 2 (1-day window) │
                                              │  Q3 must-pass call     │
                                              │  hierarchy             │
                                              └────────────────────────┘
                                                        │
                                                        ▼
Phase 3 — Freshness (conditional, 3 dev-days)
  F5a   body_hash + commit_sha guard + checkpoint migration
  F5b   mtime vs IngestRun.finished_at periodic + ignore list
  F4.2  coverage cache + atomic invalidation + global semaphore
```

**Total: ~17-18 dev-days plus 2 gate windows ≈ 4 calendar weeks** (with
parallel tracks; see walker plan).

---

## §1 Backend / host / iMac-degraded contract matrix (inlined per "self-contained")

| MCP tool | Backend | Host requirement | iMac contract |
| --- | --- | --- | --- |
| `palace.code.semantic_search` | Neo4j HNSW + Qodo MPS | MPS best on dev-Mac native; iMac Docker CPU works but slow | Works on iMac, ~3 min/query (vs ~3-5s dev-Mac post-Phase 1) |
| `palace.code.find_references` (post-F2) | Neo4j only | Any | Works everywhere |
| `palace.code.search_graph` | Neo4j only | Any | Works everywhere |
| `palace.code.search_code` | Tantivy text index | Any | Works everywhere |
| `palace.code.call_hierarchy` (NEW Phase 2) | sourcekit-lsp proxy over stdio | **Dev-Mac only** (needs Xcode 16+ + xcode-build-server + DerivedData/<workspace>/Index.noindex/DataStore) | Returns `error_code=call_hierarchy_unavailable, reason=requires_dev_mac` — opt-in P2.5 fixture snapshot can restore degraded mode for top-3 projects |
| `palace.git.*` | git CLI | Any with checkout | Works |
| `palace.memory.*` | Graphiti + Neo4j | Any | Works |
| `palace.ingest.run_extractor` | Per-extractor module | Any with SCIP artefacts mounted | Works |
| `palace.ops.recount_anchors` (NEW Phase 1) | re-runs symbol_index_swift with `anchors_only=true` | Any | Works |
| `palace.ops.recount_coverage_cache` (NEW Phase 1) | atomic Cypher transaction on :Project | Any | Works |
| `palace.health.metrics` (NEW Phase 1) | F4.0 in-process snapshot | Any | Works |
| `palace.ops.detect_stale_files` (NEW Phase 3) | Walk repo + Cypher max(IngestRun.finished_at) | Any with checkout | Works |

Phase 2 `call_hierarchy` is the ONLY hard-host-restricted tool.

---

## §2 Phase 0 — Data Lifecycle Normalization (NEW per B5)

### S(-1) — Unify `:IngestRun` contract + active Symbol semantics

**Problem (verified):** Two writers create `:IngestRun` with different
keys:

| Writer | Key field | Other fields | Location |
| --- | --- | --- | --- |
| `extractors/runner.py:322` (CREATE_INGEST_RUN cypher) | `id` | source, group_id, started_at, finished_at | per-extractor run lifecycle |
| `extractors/foundation/checkpoint.py:24` | `run_id` | project, extractor_name, started_at, success, error_code | checkpoint within extractor |

Downstream queries that read `IngestRun.finished_at` per project (F5b,
F4.2 cache invalidation) cannot rely on a single shape. Cypher
`MATCH (r:IngestRun {group_id: ...}) RETURN MAX(r.finished_at)` may
miss rows depending on which writer created them.

**Fix:**
1. **Canonical contract:** single `:IngestRun` node with fields
   `{run_id, group_id, source, extractor_name, started_at, finished_at,
   success, error_code}`. All fields required.
2. **Migration:**
   - cypher: `MATCH (r:IngestRun) WHERE r.run_id IS NULL AND r.id IS NOT NULL
     SET r.run_id = r.id REMOVE r.id` (one-time, ~ms)
   - update `runner.py` CREATE_INGEST_RUN cypher to use `run_id` key
   - update `foundation/checkpoint.py` to also write `group_id` + `source` +
     `finished_at` if missing (currently only writes some)
3. **Indexes:**
   - `CREATE INDEX ingest_run_id_idx FOR (r:IngestRun) ON (r.run_id)` (unique)
   - `CREATE INDEX ingest_run_group_idx FOR (r:IngestRun) ON (r.group_id)`
4. **Active Symbol contract:**
   - Today: `:Symbol` has no `deleted_at`; soft-delete missing
   - Add: `deleted_at: datetime | null` property (NULL = active)
   - Update all read queries in `code_composite.py`, `find_semantic.py`
     to filter `WHERE s.deleted_at IS NULL`
   - Provides foundation for F4.2 cache: cache counts use
     `deleted_at IS NULL` predicate; deletions invalidate cache.

**Acceptance:**
- `MATCH (r:IngestRun) WHERE r.run_id IS NULL RETURN count(r)` = 0
  after migration
- `CREATE INDEX ingest_run_id_idx ...` unique constraint holds
- Existing extractors still write valid IngestRuns
- Schema drift test in `tests/extractors/unit/test_schema.py` updated

**Effort: 2 days.** Migration script + two writer updates + 4 cypher
patches across read sites + tests.

---

## §3 Phase 1 — Foundation + Gold Freeze (8 dev-days)

### S0 — Source anchors + IngestRun.group_id index + ops.recount_anchors

**Fix B1 — `repo_head_sha` not `git_sha`:** SCIP metadata writer
at `cli.py:_write_scip_metadata()` produces payload with key
`"repo_head_sha"`. v6 reads same key. Code:

```python
# extractors/scip_parser.py — NEW function
def read_scip_commit_sha(scip_path: Path) -> str:
    meta_path = scip_path.parent / "index.scip.meta.json"
    if not meta_path.exists():
        raise ExtractorError(error_code="scip_meta_missing",
                             message=f"missing {meta_path}")
    meta = json.loads(meta_path.read_text())
    sha = meta.get("repo_head_sha")  # NOT "git_sha"
    if not sha or not _SHA_REGEX.match(sha):
        raise ExtractorError(error_code="scip_meta_malformed",
                             message=f"repo_head_sha missing/invalid in {meta_path}")
    return sha
```

**Fix B2 — `anchors_only` extractor flag:** Extend extractor contract.

Step 1: `BaseExtractor.run()` signature:
```python
async def run(self, *, graphiti, ctx, anchors_only: bool = False) -> ExtractorStats
```

Step 2: `run_extractor` MCP tool (`mcp_server.py:_palace_ingest_run_extractor`):
```python
async def _palace_ingest_run_extractor(
    name: str,
    project: str | None = None,
    bundle: str | None = None,
    scip_path: str | None = None,
    anchors_only: bool = False,  # NEW
) -> dict[str, Any]:
```

Step 3: `symbol_index_swift.run()` honors `anchors_only`:
- When True: only update `def_start_line`/`def_end_line`/`def_commit_sha`
  on existing `:Symbol` nodes; skip embedding refresh, skip Tantivy write
- When False: full extractor behavior (default; back-compat)

Step 4: `palace.ops.recount_anchors(project)` MCP tool calls
`run_extractor(name="symbol_index_swift", project=project, anchors_only=True)`.

**Fix C2 — IngestRun.group_id index** moved to Phase 0 (S(-1)) since
it's lifecycle normalization. S0 no longer carries it.

**Persisted on `:Symbol`:**
- `def_start_line: int` (1-indexed)
- `def_end_line: int` (1-indexed)
- `def_commit_sha: str`

**Decoder (with both range arities):**
```python
def extract_def_range(occ_range: list[int]) -> tuple[int, int]:
    if len(occ_range) == 4:
        start_line, _, end_line, _ = occ_range
    elif len(occ_range) == 3:
        start_line, _, _ = occ_range
        end_line = start_line  # single-line
    else:
        raise ValueError(f"unexpected range arity: {len(occ_range)}")
    return start_line + 1, end_line + 1  # SCIP 0-indexed → 1-indexed
```

**Effort: 2 days** (was 2.0 in v5; same).

---

### S1 + F2 — Human-name resolution + Python migration + rate-limit

Unchanged from v5 except all file references corrected:

- Resolver lives in `code_composite.py:_resolve_qn()` (line 140); the v5
  reference to `code/find_references.py` was wrong. v6 patches
  `code_composite.py` directly.
- Migration script at `services/palace-mcp/scripts/migrate_short_name.py`
  (Python, not Cypher procedure).
- Rate-limit state in `code_composite.py` via in-process dict keyed by
  `(session_id, project_slug)`; reset on successful non-ambiguous resolve.

Word-boundary regex: `[._/<>():?!&,\s]`. Disambiguation cap: 15
(configurable via `max_candidates`).

**Effort: 2 days.**

---

### F3 — dedup_by_file=False flag

Patches `code/find_semantic.py` (the actual semantic_search; this file
exists, confirmed). `code/search_graph.py` does NOT exist — search_graph
is in `code_composite.py`. v6 patches `code_composite.py` for that
half too.

**Effort: 0.25 day.**

---

### F4.0 — Telemetry (B7 fix: ring buffer + JSONL sink)

**Fix B7 — two surfaces decoupled:**

**Surface 1: live process telemetry** (existing v5 design — kept):
- `palace_mcp/telemetry/ring_buffer.py` — per `(tool_name, phase)` ring
  buffers of 1000 events each
- `palace_mcp/telemetry/counters.py` — cumulative since process start
- `palace.health.metrics(tool_pattern=None)` returns snapshot
- Used for ops monitoring (long-lived process)

**Surface 2: run-scoped audit sink** (NEW per B7):
- Env: `PALACE_BENCHMARK_RUN_ID=<id>` set by harness before query
- When set: every instrumented event ALSO appends a JSONL row to
  `bench/runs/<run-id>/metrics.jsonl` with full event data (no
  aggregation, raw measurements)
- When unset: no JSONL write; only ring-buffer/counter ops
- Harness reads JSONL post-run, computes p50/p95 on ENTIRE run's
  events (no ring-buffer eviction concern)
- Audit-grade: raw events traceable per benchmark run

**Counter schema:**
```python
{
  "histograms": {(tool, phase): [floats...]},  # ring buf, ops
  "counters": {key: int},  # cumulative, ops
  "process_start_ts": float,
}
```

JSONL schema (per event):
```jsonl
{"ts":1717235123.456,"run_id":"phase1-gate-2026-06-XX","tool":"palace.code.semantic_search","phase":"embed_query","duration_ms":3812,"meta":{...}}
```

**Effort: 1 day** (was 0.75; +0.25 for JSONL sink).

---

### F4.1 — Qodo pre-warm + yield-on-fail

Unchanged from v5. Pre-warm string: realistic Swift snippet
`"public func balance() async throws -> Decimal { return 0 }"`.
On exception: log + increment counter + yield (degrade to cold-path).

**Effort: 0.5 day.**

---

### F4.3 — Git stale-check opt-in hoist

Unchanged from v5. Tool description doc note re 60s TTL.
Patches `code/find_semantic.py` + `code/snippet_provider.py`.

**Effort: 0.5 day.**

---

### GOLD — Frozen gold corpus (NEW per operator's "freeze gold")

**Problem:** v3/v4/v5 gates referenced "grep ground truth" but the
ground-truth files + queries + expected refs were never frozen. Re-running
benchmark next week against different repo HEAD would invalidate
comparison.

**Fix:** new directory `bench/gold/phase1-frozen-2026-06-XX/`:

```
bench/gold/phase1-frozen-2026-06-XX/
├── README.md                    # version + freeze date + repo SHA
├── repo-pins.json               # {"uw-ios-app": {"sha": "<40-char>"}, ...}
├── Q1-add-evm-chain/
│   ├── prompt.txt               # exact query string
│   ├── expected-files.json      # 10 grep ground-truth files
│   ├── precision-recall-rules.md# how to score
│   └── reference-runs/          # raw response artifacts from baseline runs
│       ├── grep-baseline.txt
│       └── palace-baseline.json
├── Q2-balance-data-refs/
│   ├── prompt.txt
│   ├── expected-references.json # 31 grep ground-truth refs
│   └── ...
└── Q3-monero-adapter-calls/
    └── ...
```

**Build steps:**
1. Pin `uw-ios-app` to current SHA (or specific commit operator chooses)
2. Run grep ground-truth for each Q, save expected-files.json
3. Document precision-recall scoring rules
4. Save reference baselines (palace + grep raw responses)
5. Commit to git (no LFS; <1MB total)

**Acceptance:** any benchmark re-run uses the same pinned SHA + same
prompts; results comparable across phases.

**Effort: 0.5 day.**

---

### DEPLOY — Phase 1 deploy + provisioning slice (NEW per operator)

**Problem:** v5 hand-waved deploy. v6 explicit:

1. `services/palace-mcp/scripts/phase1-deploy.sh`:
   - Run `migrations/2026-06-XX-ingest-run-normalize.cypher` (Phase 0 / S(-1))
   - Run `python3 scripts/migrate_short_name.py` (S1)
   - Run `palace.ops.recount_anchors` per registered project (S0)
   - Run `cypher` to create new indexes (idempotent IF NOT EXISTS)
   - Verify schema drift test passes
   - Restart palace-mcp with F4.1 pre-warm
2. Runbook `docs/runbooks/palace-phase1-deploy.md`:
   - Pre-checks: GIM-1062/1063/1064 merged, Phase 0 ran
   - Step-by-step
   - Rollback procedure (cypher to drop new indexes; revert mcp-server)
   - Smoke tests (F2 returns ≥1 hit on `find_references("MoneroAdapter")`)
3. Provisioning sanity:
   - iMac container: pin palace-mcp image with v6 features
   - dev-Mac native: launchd plist update

**Effort: 0.5 day.**

---

### Tests + Q1/Q2 controlled benchmark harness

`bench/scripts/phase1-kill-gate.sh`:
- Asserts `model_load_seconds == 0` (warm precondition per Q1-cold fix)
- Sets `PALACE_BENCHMARK_RUN_ID=phase1-gate-YYYY-MM-DD` (triggers JSONL sink)
- N=50 controlled identical-query runs for Q1 + Q2
- Reads `bench/runs/phase1-gate-YYYY-MM-DD/metrics.jsonl` directly
- Computes precision-recall per Q vs `bench/gold/phase1-frozen-2026-06-XX/`
- Writes `verdict.md`

**Effort: 0.75 day** (was 0.5 — added gold comparison logic).

---

### Phase 1 budget (revised v6)

| Slice | Days | Track |
| --- | --- | --- |
| S0 source anchors + repo_head_sha + recount_anchors w/ flag | 2.0 | Codex |
| S1+F2 human-name resolution + migration + rate-limit | 2.0 | Codex |
| F3 dedup flag | 0.25 | Claude |
| F4.0 telemetry (ring buf + JSONL sink) | 1.0 | Claude |
| F4.1 Qodo pre-warm + yield-on-fail | 0.5 | Claude |
| F4.3 git stale-check opt-in hoist | 0.5 | Claude |
| GOLD frozen gold corpus | 0.5 | Codex |
| DEPLOY runbook + provisioning | 0.5 | Codex |
| Q1/Q2 controlled benchmark harness | 0.75 | Claude |
| **Total Phase 1** | **8.0 dev-days** | — |

**Track split: Claude 3.0d (37%), Codex 5.0d (62%)** — close to 30/70.

Phase 0 (S(-1)) precedes Phase 1: **+2 days Codex**.

**Total Phase 0 + Phase 1: 10 dev-days.**

---

## §4 Kill gate (v6 — tightened per B6)

### §4.1 Gate adjustment protocol (B6 fix)

After Phase ships, a 1-day window opens. Permitted adjustments:

| What | Allowed? |
| --- | --- |
| Fix harness bug (wrong file path, broken assertion) | ✅ |
| Re-pin repo SHA if frozen gold corpus drifted unintentionally | ✅ |
| Fix telemetry collection bug | ✅ |
| **Change Q1/Q2/Q3 threshold values** | ❌ → requires v6.1 spec + fresh re-run |
| **Drop a kill criterion** | ❌ → requires v6.1 spec + co-sign |
| **Add carve-outs** | ❌ |

Goalpost moving is explicitly forbidden. If evidence shows the gate is
unattainable as defined, that's a real signal — write v6.1, restart Phase.

### §4.2 Q1 (add EVM chain): recall + warm SLO

- **Recall:** palace returns ≥80% of `bench/gold/phase1-frozen-*/Q1-add-evm-chain/expected-files.json`
  at `limit=20` (8 of 10 files minimum).
- **Latency:** warm-only (asserted by harness), p50<8s, p95<15s,
  measured via JSONL sink over N=50 controlled runs.
- **Pass:** recall ≥80% AND latency thresholds met.

### §4.3 Q2 (BalanceData refs): MUST PASS

- **Recall:** `find_references("BalanceData", project="uw-ios-app")`
  returns ≥30 of 31 expected refs.
- **Latency:** p50<1s, p95<2s warm.
- **Pass:** both met.
- **Fail outcome:** **archive palace** (default v5/C5 committed).

### §4.4 Q3: SKIPPED for Phase 1 gate (deferred to Phase 2)

### §4.5 Outcomes (committed defaults)

- Q2 pass + Q1 pass → fund Phase 2
- Q2 pass + Q1 fail → fund Phase 2 anyway (per C5 commit)
- Q2 fail → archive palace

---

## §5 Phase 2 — Call Hierarchy (B8 split)

### F1B-spike (1 dev-day, Codex)

**Goal:** prove sourcekit-lsp call hierarchy end-to-end on one
real workspace (uw-ios-app) before building infrastructure.

**Deliverable:**
- Standalone Python script `services/palace-mcp/scripts/lsp-spike.py`
  using `lsprotocol` lib over stdio
- Manual setup: `cd unstoppable-wallet-ios && xcode-build-server config
  -workspace UnstoppableWallet.xcworkspace -scheme Development &&
  xcodebuild build` (operator runs once on dev-Mac)
- Script: spawn sourcekit-lsp, didOpen MoneroAdapter.swift, wait for
  indexed, prepareCallHierarchy, incomingCalls, dump JSON
- Measure: cold-start ms, prepareCallHierarchy ms, incomingCalls ms
- Write `bench/runs/lsp-spike-2026-06-XX/results.md`: pass if ≥3
  callers returned in <10s wall (cold).

**Effort: 1 day.** Spike succeeds → fund F1B-impl. Spike fails →
abandon F1B; Phase 2 deferred.

### F1B-impl (2 dev-days, Codex)

**Builds on spike. New code:**
- `palace_mcp/lsp/__init__.py`
- `palace_mcp/lsp/sourcekit_client.py` — JSON-RPC stdio client
  (~80-120 LOC); uses `lsprotocol`
- `palace_mcp/lsp/workspace_pool.py` — LRU dict, max 3 warm workspaces,
  evict on 4th request; per-workspace lifecycle (spawn, didOpen file
  cache, shutdown)
- `palace_mcp/lsp/call_hierarchy.py` — orchestrates resolve→didOpen→
  prepareCallHierarchy→{incoming|outgoing}Calls
- New MCP tool `palace.code.call_hierarchy(symbol, mode, depth=N, project)`
  in `mcp_server.py`
- Env: `PALACE_LSP_MAX_WARM=3`, `PALACE_LSP_TIMEOUT_S=30`

**Acceptance:**
- `call_hierarchy(MoneroAdapter.send, incoming, depth=3)` returns
  ≥3 callers on dev-Mac with built workspace.
- LRU eviction tested with 4 workspaces.
- Subprocess shutdown clean on palace-mcp restart.

**Effort: 2 days.**

### F1B-harden (1-2 dev-days, Codex)

- Error envelopes for: `lsp_not_ready_for_file`, `lsp_unavailable`,
  `index_not_built`, `workspace_pool_full`, `lsp_timeout`
- iMac contract: detect platform, return
  `error_code=call_hierarchy_unavailable, reason=requires_dev_mac` early
- Integration tests with mock LSP
- Failure-mode catalog appended to `docs/runbooks/palace-mcp-failure-modes.md`

**Effort: 1-2 days.**

### Phase 2 total: 4-5 dev-days, all Codex.

---

## §6 Phase 2 gate

### Q3 (MoneroAdapter call trace): MUST PASS for Phase 3

- **Correctness:** `call_hierarchy(MoneroAdapter.send, incoming,
  depth=3)` returns ≥3 callers including
  `bench/gold/phase1-frozen-*/Q3-monero-adapter-calls/expected-callers.json`.
- **Latency:** p50<5s warm.
- **Pass:** both met.
- **Fail:** ship as-is, Phase 3 deferred indefinitely.

---

## §7 Phase 3 — Freshness (conditional)

### F5a — body_hash + commit_sha guard + migration

Unchanged from v5 substantively. File paths corrected:
- `extractors/embedding_symbol.py:69-77` (existing) extend `_embedding_text`
- `code/snippet_provider.py` (existing) add commit_sha guard in
  `resolve_snippet`
- New `scripts/migrate_body_hash.py` with checkpoint/resume
- Migration: ~8h conservative on MPS for 380k symbols

**Effort: 1 day** (excluding 8h overnight migration runtime).

### F5b — periodic re-ingest

File paths corrected:
- New `services/palace-mcp/scripts/palace-periodic-reingest.sh`
- New `palace_mcp/ops/detect_stale_files.py`
- launchd plist in `services/palace-mcp/scripts/work.ant013.palace-periodic-reingest.plist`
- IngestRun.finished_at query uses Phase 0 normalized contract
- Ignore list: `.git`, `.build`, `Build`, `Index.noindex`, `DerivedData`,
  `.swiftpm`, `xcuserdata`, `SourcePackages`, `Pods`, `node_modules`,
  `.DS_Store`

**Effort: 1 day.**

### F4.2 — coverage cache + atomic invalidation + global semaphore

- `:Project.symbol_total_cached`, `symbol_embedded_cached`,
  `cache_version_token` (atomic transaction with `apoc.do.case`)
- Global semaphore via `asyncio.Semaphore(2)` in `extractors/runner.py`
- Active Symbol filter (`WHERE deleted_at IS NULL`) inherited from Phase 0

**Effort: 1 day.**

### Phase 3 total: 3 dev-days + 8h overnight migration.

---

## §8 Open decisions for operator (v6 — 2 remaining)

1. **Phase 0 + Phase 1 budget approval** — 10 dev-days + ~$3-4k Anthropic.
2. **P2.5 iMac fixture** — deferred to post-Phase 2; default = accept
   iMac as call-graph-degraded unless explicitly requested.

---

## §9 Decision log

- 2026-05-30 (v1), 2026-06-01 (v1 review by 3 voltAgents → withdrawn)
- 2026-06-01 (v3 → operator rejected, 7 blockers)
- 2026-06-01 (v4 → 3-reviewer audit, 10 blockers + 6 majors + 11 should-fix)
- 2026-06-01 (v5 → operator rejected, 8 contract-level errors)
- 2026-06-01 (v6) — fixes all 8 v5 blockers (B1-B8) + adds Phase 0
  Data Lifecycle Normalization + tightens gate adjustment + splits F1B
  + freezes gold corpus + corrects walker file map. **Self-contained.**
- **Next:** operator approves Phase 0+1 budget, walker starts.
