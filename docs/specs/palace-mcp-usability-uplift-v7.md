# Spec — palace-mcp usability uplift v7 (post-audit-chain, evidence-grounded)

Status: ready for voltAgent review.
Supersedes: v1, v3 (operator rejected), v4 (3-reviewer audit), v5 (8 contract
errors), v6 (drafted on hypothesis that audit chain GIM-1062/1063/1064
prerequisites would land; now they HAVE landed and provide additional
evidence).

**v7 is self-contained.** Read this doc + the walker plan v7 to execute.

---

## §0 What changed v6 → v7 (audit-chain findings inlined)

The audit chain (GIM-1062 + GIM-1063 + GIM-1064 + their children
GIM-1089 + GIM-1090) closed on 2026-06-01. v6 was drafted on hypothesis
that some of those issues might invalidate Phase 0/1 foundations.
**Verdicts now in:**

### Audit verdict 1 — GIM-1063 (Tantivy/Neo4j store divergence)
- **PR #360 merged 2026-06-01 (`2cd0acb`)** — documented per-extractor
  storage contract.
- **`symbol_index_swift` DOES write to Neo4j `:Symbol` nodes** (was the
  primary concern in v6 paranoia). Tantivy is a separate text search
  index, NOT a replacement for the Neo4j graph.
- **`tantivy_bridge.py:153`** writes a separate `repo_id` field; that's
  the index Tantivy maintains for `palace.code.search_code`.
- **`dead_code` extractor** does `MERGE (:Symbol …)` (upsert), which is
  where the apparent `nodes_written` discrepancy came from in early
  observation — but the Neo4j :Symbol nodes WERE there once
  `symbol_index_swift` ran successfully.
- **Forward-compat note from PR #360:** `codebase_memory_bridge` writes
  to Graphiti (separate store), NOT to Neo4j `:Symbol`. v7 Phase 2
  `palace.code.call_hierarchy` does NOT depend on Graphiti.

**v7 implication:** S0 (extend `symbol_node_writer.py` with anchors)
remains the correct extension point. v6 paranoia about non-existent
write path was unfounded.

### Audit verdict 2 — GIM-1064 (suspicious extractor counts)
- **PR #361 merged 2026-06-01 (`9775409`)** — audit document landed.
- **Confirmed bugs:**
  - `DeadFinding = count(Symbol)` — every symbol marked dead in a
    join-instance bug at `dead_code/seeds.py:16`. Cause: relationship
    counted as instance.
  - `PublicApi = 140` — too low for 70k-symbol app (UW has hundreds
    of public types).
  - `DiPattern = 1`, `LocaleResource = 18`, `CryptoFinding = 69`,
    `Author = 11` — all under-counted vs baseline expectations.
- **Follow-up issues scoped** for: dead_code seeds, public_api_surface,
  git_history (author count), di_pattern, locale_resource, crypto_domain.
  These are SEPARATE work-streams, NOT blockers for Phase 0/1.

**v7 implication:**
- Q2 gate (`find_references("BalanceData") ≥30 of 31 refs`) reads
  Neo4j `:Symbol` directly, NOT DeadFinding. Q2 gate is UNAFFECTED
  by the join-instance bug.
- Q1 gate (semantic_search recall ≥80%) reads `:Symbol.embedding` —
  also unaffected by DeadFinding bug.
- Phase 1 work-tree compatible with current Neo4j state.
- **v7 explicitly documents that GIM-1064 follow-ups are out-of-scope
  for this epic** — they're tracked separately to avoid scope creep.

### Audit verdict 3 — GIM-1062 (8+ false-done projects)
- **Root cause confirmed:** **GIM-1071 `ConstraintCreationFailed`** on
  `(:Symbol {qualified_name, group_id})` blocked 5 extractors × 9
  projects = 45 failed rows. **NOT** a Tantivy/Neo4j architectural
  problem (initial hypothesis was wrong).
- **GIM-1089 (PR #362) merged 2026-06-01** — re-ingest of 9 projects
  + coverage CSV update. Result: **141 ok rows, 0 unknown** in
  `palace_extractor_coverage_2026-06-01.csv`.
- **GIM-1090 done** — LitecoinKit.Swift SCIP regenerated on dev-Mac
  (32.2 MB / 234,574 occurrences vs 99-byte empty), copied to iMac.
  All 9 projects now have `:Symbol count > 0` in Neo4j.

**v7 implication:**
- Neo4j is now in a known-good state with all 9 projects populated.
- Q1/Q2 benchmark queries operate on stable data.
- IngestRun two-shape inconsistency (still real per my verification
  of `runner.py:322` vs `checkpoint.py:24`) was NOT the cause of
  GIM-1062; it's an independent concern but still warrants S(-1)
  Phase 0 normalization.

---

## §1 v6 → v7 spec deltas

| v6 had | v7 update |
| --- | --- |
| v6 §0 changelog with hypothesis flagged "if audit chain confirms X then..." | v7 §0 inlined verdict, hypothesis confirmed/refuted with PR links |
| Phase 0 S(-1) IngestRun normalization (block on GIM-1062/1063/1064) | Phase 0 unchanged scope, but now prerequisites HAVE landed; Phase 0 starts immediately |
| Walker plan §1 walker contract "max 1 in-flight per team" | v7 walker plan §1 explicit: **CEO creates MAX 2 simultaneous slices total (1 Claude + 1 Codex), self-blocks on both, on each-done unblock → creates next from roadmap → blocks self again** |
| Tracks Claude 23% / Codex 77% (Phase 2 single-track inflates Codex) | v7 acknowledges 23% (slightly under 30% target); Phase 2 LSP single Codex slice is inherent constraint |
| GIM-1064 follow-ups not mentioned | v7 §0 explicit: GIM-1064 follow-ups (dead_code seeds, public_api, di_pattern, etc.) are **out-of-scope** for this epic; tracked separately. |
| No GIM-1071 reference | v7 §0.audit-verdict-3 cites GIM-1071 as root cause; audit chain prerequisite section updated |
| Track effort split: Phase 1 = 5 Codex + 3 Claude = 37% Claude | Unchanged but explicit per operator's 30/70 reminder |

---

## §2 Phase plan (v7)

```
GIM-1062 + GIM-1063 + GIM-1064 (audit chain) ── DONE 2026-06-01 ──┐
                                                                   │
                                                                   ▼
Phase 0 — Data Lifecycle Normalization (2 dev-days, Codex)
  S(-1)  Unify :IngestRun contract (run_id key) — confirmed real
         per verified two-writer divergence (runner.py:322 vs
         checkpoint.py:24). Active Symbol contract (deleted_at).
         New :IngestRun indexes (id_idx unique, group_idx).
                                                                   │
                                                                   ▼
Phase 1 — Foundation + Gold Freeze (8 dev-days; Claude 3 / Codex 5)
  S0     Source anchors + repo_head_sha + recount_anchors w/ anchors_only flag
  S1+F2  Human-name resolution + Python migration + rate-limit
  F3     dedup_by_file=False flag
  F4.0   Telemetry (ring buf + JSONL sink for benchmark)
  F4.1   Qodo pre-warm + yield-on-fail
  F4.3   git stale-check opt-in hoist
  GOLD   Frozen gold corpus (queries + repo SHA + expected refs)
  DEPLOY Phase 1 deploy runbook + provisioning
                                                                   │
                                              ┌─ GATE 1 (1-day window, B6) │
                                              │  Q1 recall≥80% + warm SLO  │
                                              │  Q2 MUST PASS refs ≥30/31  │
                                              │  Q3 SKIPPED (P2 gate)      │
                                              │  Adjustment: harness bugs ONLY │
                                              └────────────────────────────┘
                                                        │
                                                        ▼
Phase 2 — Call Hierarchy (4-5 dev-days, Codex)
  F1B-SPIKE  One workspace end-to-end (1d)
  F1B-IMPL   Workspace pool + LRU + MCP tool (2d)
  F1B-HARDEN Error envelopes + iMac contract + tests (1-2d)
                                                        │
                                              ┌─ GATE 2 (1-day window)     │
                                              │  Q3 must-pass call hierarchy │
                                              └────────────────────────────┘
                                                        │
                                                        ▼
Phase 3 — Freshness (conditional, 3 dev-days)
  F5a   body_hash + commit_sha guard + 8h migration
  F5b   mtime vs IngestRun.finished_at periodic
  F4.2  Coverage cache + atomic invalidation + global semaphore
```

**Total: ~17-18 dev-days, ~4 calendar weeks with parallel tracks.**

---

## §3 Walker process (explicit per operator's reminder)

```
walker (CEO 10a4968e) state machine:

  state = idle
  loop:
    state = picking_next
    next_slice_pair = walker reads roadmap (from v7 walker plan §5)
      → pair = (1 Claude slice + 1 Codex slice if both available + no overlap)
      OR     = (1 Codex slice only if Phase 2 LSP single-track OR Claude has no work)
      OR     = (1 Claude slice only if all Codex slices done in phase)

    create issue(s) in paperclip, assignee = engineer roles:
      Claude track → PythonEngineer (127068ee)
      Codex track  → CXPythonEngineer (e010d305)

    walker self-block: status = blocked, blockedBy = [slice_ids]

    state = blocked_on_slices

    await: notification(slice X status changed to "done")
      for each X:
        if all_blockers_done:
          unblock walker
          break

    state = unblocking
    walker → continues loop (next pair)
  end
```

**Hard rules (committed v7):**

1. **Max 2 simultaneous slices** — never spawn 3+ in flight; one per
   team max.
2. **No mass upfront creation** — walker creates pair N only after
   pair N-1 completes (or one side fast-tracks if the other still has
   capacity).
3. **File-overlap verified** at slice issue creation — CR pre-merge
   must verify no overlap with sibling.
4. **Gate decisions co-signed** — walker prepares verdict but operator
   + CTO sign off.
5. **Walker NEVER decides** archive, P2.5, P3, or threshold changes —
   surfaces to operator only.

---

## §4 Track allocation (30/70 target, Phase 1 only)

| Phase | Claude effort | Codex effort | Total | Claude % |
| --- | --- | --- | --- | --- |
| Phase 0 | 0 | 2.0 | 2.0 | 0% |
| **Phase 1** | **3.0** | **5.0** | **8.0** | **37%** ← matches operator target |
| Phase 2 | 0 | 4-5 | 4-5 | 0% (LSP single-track) |
| Phase 3 | 1.0 | 2.0 | 3.0 | 33% |
| **Overall** | **4.0** | **13-14** | **17-18** | **~23%** |

Phase 2 LSP proxy is inherently single-track (one Python module
add-on, no parallelism); inflates Codex share. Phase 1 is the
representative 37% Claude split.

---

## §5 Backend / host / iMac-degraded contract matrix

(Same as v6 — unchanged.)

| MCP tool | Backend | Host | iMac contract |
| --- | --- | --- | --- |
| `palace.code.semantic_search` | Neo4j HNSW + Qodo MPS | dev-Mac native ~3-5s; iMac Docker CPU ~3min | works, slow |
| `palace.code.find_references` (post-F2) | Neo4j | any | works |
| `palace.code.search_graph` | Neo4j | any | works |
| `palace.code.search_code` | Tantivy | any | works |
| `palace.code.call_hierarchy` (NEW P2) | sourcekit-lsp via stdio | **dev-Mac only** | `error_code=call_hierarchy_unavailable` |
| `palace.git.*` | git CLI | any | works |
| `palace.memory.*` | Graphiti + Neo4j | any | works |
| `palace.ingest.run_extractor` | per-extractor | any | works |
| `palace.ops.recount_anchors` (NEW P1) | re-runs symbol_index_swift w/ anchors_only=true | any | works |
| `palace.ops.recount_coverage_cache` (NEW P1) | atomic Cypher | any | works |
| `palace.health.metrics` (NEW P1) | F4.0 ring buf + JSONL | any | works |
| `palace.ops.detect_stale_files` (NEW P3) | mtime + IngestRun cypher | any | works |

---

## §6 Phase 0 spec (unchanged from v6 — audit confirmed needed)

### S(-1) — Unify :IngestRun + active Symbol semantics

**Problem (re-confirmed against source):** Two writers create
`:IngestRun` with different keys:

- `services/palace-mcp/src/palace_mcp/extractors/runner.py:322`
  uses CREATE_INGEST_RUN cypher with `id` field
- `services/palace-mcp/src/palace_mcp/extractors/foundation/checkpoint.py:24`
  uses MERGE cypher with `run_id` field

These coexist on `:IngestRun` nodes today; downstream queries (F5b
periodic re-ingest, F4.2 cache invalidation) cannot rely on a single
shape. Audit chain GIM-1062 confirmed NOT to be caused by this
divergence (root was GIM-1071 constraint failure) but lifecycle
normalization is independently necessary.

**Fix:**
1. Canonical contract: `:IngestRun { run_id, group_id, source,
   extractor_name, started_at, finished_at, success, error_code }`
2. Migration: `MATCH (r:IngestRun) WHERE r.run_id IS NULL AND r.id
   IS NOT NULL SET r.run_id = r.id REMOVE r.id`
3. Update both writers to canonical shape
4. Indexes: `ingest_run_id_idx` (unique on `run_id`) +
   `ingest_run_group_idx` (lookup on `group_id`)
5. Active Symbol: add `deleted_at: datetime | null`, update read sites
   to filter `WHERE s.deleted_at IS NULL`
6. Schema drift test updated

**Acceptance:** All `:IngestRun` have `run_id` non-null; unique
constraint holds; existing extractors continue to write valid rows;
all reads include `deleted_at IS NULL` filter.

**Effort: 2 days.**

---

## §7 Phase 1 specs (unchanged from v6)

See v6 §3 — Phase 1 specs (S0, S1+F2, F3, F4.0, F4.1, F4.3, GOLD,
DEPLOY, Q1Q2 harness). All 8 slices apply as written, file map
verified.

### Out-of-scope (explicit per audit chain follow-ups)

GIM-1064 follow-up extractor data quality issues are NOT addressed
in this epic:
- `dead_code/seeds.py:16` join-instance bug (DeadFinding overcount)
- `public_api_surface` under-count
- `git_history` author under-count
- `di_pattern` count
- `locale_resource` count
- `crypto_domain_model` count

These are tracked separately as follow-up issues per GIM-1064
walker Block-A prioritization. v7 epic operates on Neo4j as it is.

---

## §8 Phase 1 KILL GATE (v7 — gates unchanged from v6)

### Q1 (add EVM chain)
- Recall ≥80% at limit=20 vs `bench/gold/phase1-frozen-*/Q1`
- Latency: warm-only (asserted), p50<8s, p95<15s
- N≥50 controlled runs via JSONL sink
- **Pass:** both met

### Q2 (BalanceData refs) — MUST PASS
- ≥30 of 31 grep ground-truth references
- p50<1s, p95<2s warm
- **Fail outcome:** archive palace immediately (committed default)

### Q3 — SKIPPED for Phase 1, deferred to Phase 2 gate

### Outcomes (committed defaults v7)
- Q2 pass + Q1 pass → fund Phase 2
- Q2 pass + Q1 fail → fund Phase 2 anyway
- Q2 fail → archive palace

### Gate adjustment protocol (v7 — same B6 restriction)
- 1-day window after Phase 1 ships, before evaluation runs
- Adjustments **limited to harness bugs**
- Threshold change → new spec version + restart Phase

---

## §9 Phase 2 (unchanged from v6)

F1B-SPIKE (1d) → F1B-IMPL (2d) → F1B-HARDEN (1-2d). Sourcekit-lsp
proxy. iMac degraded contract. P2.5 fixture optional.

---

## §10 Phase 3 (unchanged from v6)

F5a + F5b + F4.2. Body hash, periodic re-ingest, coverage cache.
3 days + 8h overnight migration.

---

## §11 Open decisions for operator (v7 — same 2)

1. **Phase 0 + Phase 1 budget approval** — 10 dev-days + ~$3-4k Anthropic
2. **P2.5 iMac fixture investment** — deferred to post-Phase 2 default
   = accept iMac degraded unless requested

---

## §12 Decision log

- 2026-05-30 (v1) → 2026-06-01 (v1 review by 3 voltAgents → withdrawn)
- 2026-06-01 (v3 → operator rejected, 7 blockers)
- 2026-06-01 (v4 → 3-reviewer audit, 10 blockers + 6 majors)
- 2026-06-01 (v5 → operator rejected, 8 contract errors)
- 2026-06-01 (v6 → drafted but hypothetical about audit chain outcome;
  superseded after chain closed)
- 2026-06-01 (v7) — **audit chain DONE**. Findings inlined:
  - GIM-1063 verdict: `symbol_index_swift` writes to Neo4j (v6 paranoia
    unfounded); per-extractor storage contract documented
  - GIM-1064 verdict: extractor data-quality follow-ups out-of-scope
  - GIM-1062 verdict: root cause was GIM-1071 constraint failure (not
    architectural); now resolved, Neo4j in good state
  - Walker process explicit per operator reminder
  - GIM-1064 follow-ups explicitly out-of-scope
- **Next:** voltAgent critical review → fixes → paperclip launch.
