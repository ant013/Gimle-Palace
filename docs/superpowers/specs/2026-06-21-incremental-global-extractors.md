# Spec — Incremental global extractors (dead_code / hotspot / cross_module_contract)

**Status:** draft **rev2** (2026-06-21) — Phase-4 follow-up to the incremental-update epic (GIM-1689).
Grounded in live develop @ `09a2d2b` + a 3-lens voltAgent review (architect / performance / qa) with live
measurements on the `:7688`/`:7687` Neo4j (248,077 symbols, ~180k call/ref edges, 28,423 files). rev1→rev2
changelog at the bottom.
**Owner:** design = Board; implementation = palace-mcp slice(s).
**Problem.** The incremental orchestrator (`project_analyze(mode=incremental)`, B3) SKIPS `dead_code`, `hotspot`,
`cross_module_contract` (`project_analyze.py:64-66`), stamping them `stale_since`. This spec designs **correct,
robust incremental implementations** so they refresh per-commit, removing the last "stale until full" gap.

> **Design rule:** the most robust + architecturally-correct variant for each — correct under *every* edit type
> (symbol add/remove/move, edge add/remove, visibility/seed change, cycles, **batched multi-edge commits**) with a
> **bounded fall-back to full**; never a silently-wrong incremental result.

---

## 0. Why these three are "global"

A file-scoped extractor is incrementalizable because file *X*'s answer depends only on *X*. These three don't:
- `dead_code`: reachability from seeds over the **whole** graph (`graph_loader.py:14,39` load ALL symbols/edges;
  `reachability.py` BFS + `scc_analyzer.py` Tarjan).
- `hotspot`: relative top-N ranking of churn×complexity over a history window.
- `cross_module_contract`: cross-module / two-commit public-API contract diff.

**Unifying technique:** affected-set (from the change-set) → recompute only the affected set from a fixed correct
frontier → bounded fall-back to full + `stale_since` safety net. Ship order: **hotspot → cross_module → dead_code**.

---

## 0.5 PREREQUISITE LAYER — delta resolution (NEW; required by all three)

**The blocker the rev1 design silently assumed away.** rev1 said all three "consume the Phase-1 `incremental_scope`
change-set (changed/added/removed files + symbol/edge deltas)." **That is false:** `incremental_scope.py:60-65`
exposes ONLY file paths —
```python
class IncrementalPathScope:
    mode: IncrementalMode; changed_paths: set[str]; removed_paths: set[str]; reason: str | None
```
— from `git diff --name-status`. There is no symbol-delta, edge-delta, or visibility/seed-delta anywhere in `src/`.

**Required deliverable (foundation for §1 and §3):** a `delta_resolution` sublayer that, given `changed_paths ∪
removed_paths`, produces:
- **symbol delta** — symbols added / removed / moved (qn unchanged, `file_path`/`module_name` changed);
- **edge delta** — added / removed `CALLS|REFERENCES|EXTENDS|CONFORMS_TO|EXTENSION_OF|EXISTENTIAL_USE` edges whose
  source is a changed file;
- **seed delta** — symbols whose `access_modifier`/seed flags flipped (gain/lose seed status);
- **public-API delta** — `:PublicApiSymbol` added/removed/`signature_hash`-changed for changed files.

It derives these by re-parsing changed files' SCIP and diffing the *new* per-file symbol/edge set against the
persisted prior state (the graph already retains it via `last_seen_in_run_id`/`deleted_at`,
`symbol_node_writer.py:55,82-94`). **Ordering gate:** the symbol-writer's stale-edge sweep is batched/throttled
(`_DELETE_STALE_RELATIONSHIPS … LIMIT $batch_size`, `symbol_node_writer.py:147`), so delta resolution + the global
extractors MUST run after that sweep completes for the commit, else the edge delta is not yet materialized. This
layer is ~half the dead_code slice and was invisible in rev1.

---

## 1. `dead_code` — incremental (HARDEST)

### 1.1 The real bottleneck is the WRITE, not reachability (rev1 misdiagnosed)
Live measurement of a full run: symbol load **~10s** (`graph_loader.py:13-36`), edge load **~3s** (`:38-45`),
in-memory BFS + Tarjan SCC **<1s** (`reachability.py`, `scc_analyzer.py`), but the **`:DeadFinding` write ≈ 60 min**
— `neo4j_writer.py:52-58` does one `session.execute_write` (MERGE_NODE + MERGE_EDGE) **per finding**; worst case 248k
findings × 2 × ~7.2 ms/round-trip ≈ 3,572 s. **The incremental win is from writing only the delta findings, not
from avoiding reachability.** Reframe the whole section accordingly.

### 1.2 Blocking prerequisites (verified in the live DB)
- **P-DC1 — seeds/`access_modifier` must be populated.** Live DB: `access_modifier=''` for ALL 248k symbols, all
  dynamic-dispatch flags false → `identify_public_seeds` (`seeds.py:8-17`) yields **zero seeds** → every symbol is a
  dead candidate → the §1.5 threshold trips on **every** run → permanent full fall-back, and *both* full and
  incremental output is meaningless. dead_code is **blocked on the symbol indexer populating `access_modifier`/seed
  flags** before either path is valid. (The rev2 review confirmed; gate the slice on this.)
- **P-DC2 — batch the finding write (do first; benefits full AND incremental).** Replace the per-finding
  `execute_write` loop with a batched `UNWIND` MERGE. This alone drops the full run **~60 min → ~3 min** and makes
  the incremental delta-write trivially cheap. Prerequisite, not optional.
- **P-DC3 — non-destructive writer.** Today `_evict_stale_findings` does `DETACH DELETE` of every `:DeadFinding` not
  in the current run's set, by `group_id` (`neo4j_writer.py:24-28`). An incremental run that emits only the affected
  subset would **delete all unaffected findings.** The incremental writer must "upsert affected + evict only the
  affected `finding_id`s that flipped, leave the rest" — a real writer rewrite.
- **P-DC4 — graph-reload floor ~22s per incremental.** palace-mcp is a stateless uvicorn server
  (`mcp_server.py`) — no warm graph cache between calls; every run re-runs `load_symbol_graph()`. Incremental must
  reload 248k symbols (~10s) + edges (~3s) + the new `reachable_run_id` (~8s) → **~22s hard floor regardless of
  affected-set size.** Still ~150× vs 60 min, but state it: incremental dead_code is "~tens of seconds", not
  "sub-second". On a cold start there is no valid `reachable_run_id` → first run after restart must be full.
- **P-DC5 — liveness filter already shipped** (`graph_loader.py:14-16` `WHERE s.deleted_at IS NULL AND NOT
  s:Deprecated`, edge filter `:40-43`). Dependency closed; keep the §0.5 ordering gate so the sweep finishes first.

### 1.3 Live-set materialization
Persist reachability state: stamp `:Symbol.reachable_run_id` (mirrors B1-a `last_seen_in_run_id`). Full run writes
it for all symbols (one-time backfill — first incremental requires a prior full run). New index `(group_id,
reachable_run_id)`.

### 1.4 The robust algorithm — batched-fixpoint affected-frontier re-reachability
rev1 proved single-edge correctness; the real workload is a **commit's batch of many edge/symbol changes**, which
does **not** compose to a single pass. Correct version:
- **Affected set `A`** = `⋃ forward_closure(target)` over ALL removed edges (computed on the post-mutation graph)
  ∪ forward_closure of any symbol that lost seed status ∪ any symbol whose `file_path`/`module_name` changed
  (moved-file — rev1 missed this; `dead_module` coverage and member `file_path` depend on it,
  `scc_analyzer.py:116-128`, `finding_builder.py:90-93`).
- **Added edges / new seeds:** monotone forward-BFS marking newly-reachable (easy direction).
- **Removed edges:** re-derive reachability for `A` to a **fixpoint**, treating `seeds ∪ (live symbols not in A)` as
  the frontier — but frontier symbols **adjacent to `A`** whose out-edges terminated in `A` need one extra
  relaxation layer (their own liveness via `A` must be revalidated). This is a localized fixpoint, not a single BFS.
  Correct for cycles by construction (an SCC in `A` is live iff reached from the frontier) — **no whole-graph SCC
  maintenance**, but see §1.5 for findings.

### 1.5 Findings recompute (SCC + module coverage — rev1's "no SCC maintenance" was wrong)
`dead_scc_cluster`/`dead_module` are NOT pure reachability. `scc_analyzer.py:13-78` runs Tarjan over the
dead-candidate subgraph, and `dead_module` needs a **module-coverage ratio over the module's full top-level-type
census** (`scc_analyzer.py:98,116-131`) — a *global per-module denominator*. A symbol flipping in `A` can change a
cluster's membership (→ new content-addressed `finding_id`, `models.py:39-50`) or a module's coverage. **Recompute
findings over `A ∪ (every module touched by A)`**, re-querying each touched module's full type census (not just `A`).

### 1.6 Bound
If `|A| > THRESHOLD` (start ~15-20% of symbols; env `PALACE_INCREMENTAL_DEADCODE_FULL_THRESHOLD`) → full fall-back,
logged. A removed reference to a high-fan-in core symbol cascades widely.

---

## 2. `hotspot` — incremental (EASIEST; ship first)

Full hotspot on uw-ios-app is **~29s** (lizard ~5s + churn ~0.6s single Cypher aggregation + write ~24s), **not the
52-min class** — calibrate the urgency, but the 29s→~0.8s incremental win is real and worth shipping.

- **Complexity:** per-`:File`, already freshness-tracked (`neo4j_writer.py` `complexity_status: fresh|stale`). Run
  `lizard` ONLY for changed files (`lizard_runner.py`, subprocess per batch).
- **Churn:** single Cypher aggregation over `(Commit)-[:TOUCHED]->(File)` with a date cutoff (`churn_query.py:6-12`)
  — cheap; commits ingested incrementally by git_history. Re-run it (cheap at 28k files).
- **Score + rank:** recompute affected files' scores; ranking is query-time sort.

**Required fixes (parity correctness):**
- **HS-fix1 — pin the churn cutoff to a commit-derived timestamp.** `churn_query.py:26` computes
  `cutoff = run_started_at - window_days` from **wall-clock** call time → two runs at different times give different
  churn for the same commit → "byte-identical parity" impossible. Derive the cutoff from the commit's timestamp
  (`as_of`), not `now()`.
- **HS-fix2 — non-destructive writer.** `PHASE_5_DEAD_CYPHER` (`neo4j_writer.py:51-60`) **zeros `hotspot_score`/
  `ccn_total` for every file not in `preserved_paths`.** An incremental run passing only changed files as
  `preserved_paths` will **wipe every unchanged file's score.** Make the incremental write upsert-only for changed
  files + handle deleted files (zero/evict only those).

---

## 3. `cross_module_contract` — incremental (MEDIUM; rewritten from rev1's wrong mechanism)

rev1 §3 was factually wrong on three points (architect + perf, code-verified). Corrected:
- **Compares `signature_hash`, NOT `signature`.** `build_contract_delta` does
  `if from_symbol.signature_hash == to_symbol.signature_hash: continue` (`cross_module_contract.py:738`);
  `PublicApiSymbol` carries both fields (`models.py:325-326`). Incremental signature-change detection diffs
  `signature_hash`.
- **Consumers are resolved via Tantivy occurrence-search + SourceKit `find_callers`, NOT a graph `REFERENCES`
  query** (16 call-sites, `cross_module_contract.py:824,883-890`; occurrence `file_path` → `resolve_module_owner`,
  `:541-547`). There is no `REFERENCES`-Cypher consumer query. So the "bounded consumer query" is per-delta-symbol
  Tantivy occurrence search (cost is proportional to the delta symbols, not the full surface).
- **Diff is driven by `.palace/cross-module-contract/delta-requests.json` + commit-keyed, content-addressed
  snapshots** (`_stable_id(..., commit_sha, ...)`, `:609,648; :92,425`) — the incremental path feeds the changed
  files' public-API delta as the request set instead of the full surface.

### Incremental algorithm
1. **Producer delta (file-scoped, from §0.5):** `:PublicApiSymbol`s added / removed / `signature_hash`-changed in
   changed files, compared against the **prior-commit** surface (the `from_commit` snapshot — which MUST NOT be
   overwritten by the incremental update; snapshot the prior `signature_hash` before any surface mutation).
2. **Consumer resolution (bounded):** for each delta public symbol, Tantivy occurrence-search + `find_callers` →
   map occurrence files to consumer modules via `resolve_module_owner`.
3. **Emit `:ModuleContractDelta`** for affected `(consumer_module, producer_module)` pairs only.
4. **Eviction (NEW — rev1 missed; the writer only writes).** When a consumer module loses all cross-module refs to a
   producer (e.g., the module is deleted), its prior `:ModuleContractSnapshot`/`:ModuleContractDelta` must be evicted
   or marked stale (`valid_until_commit` TTL) — else ghost deltas accumulate unboundedly in the audit query
   (`:174-186`).

---

## 4. Shared infrastructure
- **Change-set:** all consume the §0.5 delta-resolution layer (NOT raw `incremental_scope`, which is paths-only).
- **Bounded fall-back** per extractor + `stale_since` while a fall-back runs; log the reason (no silent caps).
- **Run-mode wiring:** remove each from `_INCREMENTAL_GLOBAL_EXTRACTORS` (`project_analyze.py:64`) only once its
  incremental path + parity test pass — per-extractor, reversible.

## 5. Named blockers / risks
- **B0 — delta-resolution layer (§0.5)** does not exist; prerequisite for §1 and §3.
- **DC: P-DC1 seeds/`access_modifier` empty** (blocks meaningful dead_code at all), **P-DC2 batch-write**,
  **P-DC3 non-destructive writer**, **P-DC4 ~22s reload floor + cold-start→full**, **§1.4 batched fixpoint** (not a
  single BFS), **§1.5 SCC/module-census** (re-query touched modules' full census), **moved-file** in the affected set.
- **HS: HS-fix1 cutoff-pinning** (else parity flaky), **HS-fix2 non-destructive writer** (else wipes unchanged scores).
- **CM: signature_hash** (not signature), **Tantivy/`find_callers` consumers** (not REFERENCES), **prior-surface
  snapshot** before mutation, **snapshot eviction policy**.
- **Concurrency:** an incremental global run must be serialized vs other ingest writers (the affected-set/closure is
  computed over live graph state; a concurrent edge write mid-run corrupts it) — gate or isolate.

## 6. Acceptance + tests (real Neo4j; Board/CI only — agents can't reach Neo4j)

### Parity contract (rev1 "byte-identical" is UNACHIEVABLE — define it)
`:DeadFinding.created_at` is a wall-clock default (`models.py:60-62`) and set iteration is `PYTHONHASHSEED`-sensitive.
**Parity = identical SET of `finding_id` + identical stable props `{kind, severity, size, members_json,
module_coverage_ratio}` per matching `finding_id`, EXCLUDING `created_at` and write-order.** Run CI parity tests with
`PYTHONHASHSEED=0`. Same contract per extractor (hotspot: scores+ranks given a pinned `as_of`; cross_module:
delta sets).

### Required acceptance tests (the load-bearing subset; full catalog from the qa review)
**dead_code — MUST include the false-positive guards (rev1 omitted):**
- DC-TC-09 **diamond**: `A→B→D`, `A→C→D`; remove `B→D` → D stays LIVE (still via C). (Guards over-conservative dead.)
- DC-TC-10 **cycle with alternate in-edge**: cycle `{B,C}`, in-edges `A→B` and `X→C`; remove `A→B` → B,C stay LIVE.
- DC-TC-03 cyclic SCC loses all external in-edges → whole cluster dead; DC-TC-01 remove sole ref → dead + closure;
  DC-TC-02 add ref → resurrect; DC-TC-04/05 seed flip public↔internal; DC-TC-15 seed flip inside a cycle resurrects
  it; DC-TC-11 dead symbol gains ref from another dead symbol → stays dead (refcount would fail this);
  DC-TC-17 `dead_module` coverage boundary at 0.5 (re-query module census); DC-TC-14 moved-file (file_path updates,
  no duplicate finding); DC-TC-20 both endpoints of an edge edited in one commit; DC-TC-06 threshold→full fall-back;
  DC-TC-07 **incremental==full parity (per the contract)** on a multi-file commit; DC-TC-08 idempotency;
  DC-TC-21 liveness-filter regression (deleted/deprecated excluded).
**hotspot:** HS-TC-02 lizard called ONLY for changed files (needs a call-count spy — not in the current harness);
HS-TC-05 deleted file → score zeroed/evicted (only that file); HS-TC-03/06 window-boundary churn; HS-TC-04 parity
given a pinned cutoff.
**cross_module:** CM-TC-02 `signature_hash` change → `signature_changed` delta; CM-TC-06 symbol consumed by multiple
modules → delta per consumer; CM-TC-03 public+no-consumer → no false break; CM-TC-04/08 internal/package change →
no delta; CM-TC-09 prior-surface signature_hash NOT overwritten before diff; CM-TC-11 stale-snapshot eviction after
a consumer module is removed; CM-TC-05 parity.

Parity fixtures are synthetic (50-200 symbols, with cycles/diamonds/multi-module), built before/after per commit
pair — not a full UW ingest. Real-Neo4j integration; no agent may claim a green parity result from a mocked run
(GIM-127 fabrication lesson).

## 7. Phasing
1. **hotspot** — lowest risk + smallest; needs only HS-fix1/2 + the §0.5 layer's file-delta. Ship first.
2. **cross_module_contract** — medium; reuses materialized PublicApiSurface; needs the §0.5 public-API delta +
   eviction.
3. **dead_code** — highest; gated on **P-DC1 (seeds)** + **P-DC2 (write-batch)** + the §0.5 delta layer + live-set +
   the §1.4 batched-fixpoint + §1.5 findings recompute + non-destructive writer. Largest slice.

Each ships behind `PALACE_INCREMENTAL_INGEST`, default OFF per extractor until its parity test passes on real Neo4j;
removed from `_INCREMENTAL_GLOBAL_EXTRACTORS` only on green.

---

## rev1 → rev2 changelog (from the 3-lens voltAgent review)
- **Added §0.5 delta-resolution layer** — rev1 assumed `incremental_scope` exposes symbol/edge/seed deltas; it
  exposes only file paths (`incremental_scope.py:60-65`). This missing foundation is required by §1 and §3.
- **dead_code reframed onto the write bottleneck** (measured ~60 min is the per-finding write, not reachability;
  load ~14s, BFS <1s). Added prerequisites: **P-DC1** seeds/`access_modifier` empty (blocks meaningful results),
  **P-DC2** batch-write (60→3 min), **P-DC3** non-destructive writer, **P-DC4** ~22s graph-reload floor +
  cold-start→full.
- **dead_code algorithm corrected:** single-edge proof → **batched-fixpoint** over the union of affected sets +
  frontier-adjacent relaxation; **moved-file** symbols added to the affected set; **§1.5** SCC/`dead_module`
  findings need the touched modules' **full census** (rev1's "no SCC maintenance" was wrong for findings).
- **hotspot:** added **HS-fix1** commit-pinned churn cutoff (rev1 parity unachievable on wall-clock cutoff) +
  **HS-fix2** non-destructive writer (PHASE_5 zeroes non-preserved files); calibrated urgency (full ~29s, not 52 min).
- **cross_module §3 rewritten:** compares **`signature_hash`** (not `signature`), consumers via **Tantivy/
  `find_callers`** (not a graph `REFERENCES` query — which doesn't exist), **delta-request-driven** commit-keyed
  snapshots, + a **snapshot-eviction policy** (rev1 had none → ghost deltas).
- **Acceptance:** replaced "byte-identical" with an explicit **parity contract** (exclude `created_at`,
  `PYTHONHASHSEED=0`, finding_id-set + stable props); promoted the **diamond (DC-TC-09)** and **alternate-cycle-edge
  (DC-TC-10)** false-positive guards to required tests.
- **Added** the concurrency-serialization risk + the §0.5 ordering gate (run after the batched stale-edge sweep).
