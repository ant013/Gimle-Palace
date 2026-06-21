# Spec — Incremental update orchestration (detect_changes → selective extractors)

**Status:** draft **rev2** (2026-06-20) — grounded in live develop @ `d9fd544`, the 2026-06-20 full UW re-ingest,
and a 3-lens voltAgent review (architect / performance / qa). rev1 → rev2 changelog at the bottom.
**Owner:** design = Board; implementation = palace-mcp slice(s).
**Problem (operator):** a normal commit touches 10–15 files; there are 2–3/day. Today a per-commit
`project_analyze` re-runs the full extractor suite on the whole project → **~10–15 h** for `uw-ios-app`
(248k symbols). That makes the graph un-maintainable between full re-ingests. We need a per-commit update
that finishes in **minutes of graph work** (on top of the unavoidable xcodebuild floor), staying **correct**
(no stale-as-live, no over-deprecation, no orphan edges).

> **SLA wording (corrected from rev1):** the honest target is **"incremental xcodebuild time + < ~10 min of graph
> update"**, NOT "single-digit minutes end-to-end". The xcodebuild re-emit is an unavoidable floor (2–15 min for a
> protocol-touching change) that no graph optimization removes — see §5.

---

## 0. What is already incremental (do NOT rebuild these)

| Layer | Mechanism | State |
|---|---|---|
| `symbol_index_swift` no-change skip | `body_hash` of all files matches → whole extractor SKIPPED | ✅ live |
| `symbol_index_swift` Tantivy writes | `PALACE_INCREMENTAL_INGEST` (default OFF): if `changed_ratio < 0.8`, `delete_by_file_paths` + rewrite only changed files | ✅ live (flagged, #6) |
| `embedding_symbol` | `embedding_input_hash` skip — only new/changed symbols embedded | ✅ live |
| `git_history` | checkpoint `since=last_commit` — only new commits | ✅ live |
| SCIP re-emit | DerivedData reuse (`scip_emit_uw_ios_app.sh`, commit 222b564c) → incremental xcodebuild | ✅ live (but is the floor, §5) |
| `prune_swift_symbols` | delta — deprecates stale files/symbols by `last_seen_in_run_id` | ✅ live (but see B1 + threshold bug §1.1) |
| `detect_changes` MCP tool | `native_detect_changes.py` — git-diff changed/added/removed files for a registered project | ✅ live primitive (but see B4 limits) |

## 0b. What is NOT incremental (full rebuild every run — the 10–15 h)

| Extractor | Current behavior | Evidence |
|---|---|---|
| `symbol_index_swift` **Neo4j writes** | `_refresh_graph_state` → full UPSERT of all symbols every run | `symbol_index_swift.py:384` (full `scip_index`, no `selected_paths`) |
| `symbol_index_swift` **SCIP iteration** | 7 full passes over the 165 MB protobuf in Python every run (body_hash, USE counter, 3 Tantivy phases, def_file_paths, shadow) | `symbol_index_swift.py` USE loop ~275, `_refresh_graph_state` 553-577 |
| `soft_delete_symbols` | sends ALL 248k qualified_names as one `IN $list` bolt parameter every run | `symbol_node_writer.py:284-287` |
| `call_edge_swift` | `_DELETE_INDEXSTORE_CALLS` deletes ALL `:CALLS {via:'indexstore'}` + full IndexStore re-scan | `call_edge_swift.py:20-22` |
| `dead_code` | full graph-reachability (BFS + Tarjan SCC); **loads deprecated/deleted nodes — bug, see §1.2** | `dead_code/graph_loader.py:13-39` |
| `dead_symbol_binary_surface` | replace-snapshot (full DETACH DELETE + rewrite) | `dead_symbol_binary_surface/neo4j_writer.py:19-22` |
| `code_ownership`, `coding_convention`, `crypto_domain_model`, `error_handling_policy`, `testability_di`, `localization_accessibility`, `hotspot`, … | full per-project re-analysis each run | — |

---

## 1. Load-bearing blocker — B1: prune liveness vs file-scoped symbol writes

`write_symbol_nodes` MERGEs `(:Symbol {qualified_name, group_id})` and sets `s.last_seen_in_run_id = $run_id`
per symbol (`symbol_node_writer.py:55`). `prune_swift_symbols` then deprecates any `:Symbol`/`:File` whose
`last_seen_in_run_id <> companion_run_id` (`prune_swift_symbols/cypher.py:22-36`), guarded by a `threshold_ratio`
(default 0.5).

**This is why the Neo4j write is full today:** to keep unchanged-file symbols alive, every run bumps
`last_seen_in_run_id` on ALL of them. A file-scoped write leaves the unchanged majority on the *previous* run-id →
`prune` deprecates them. (The #6 A1 invariant: "an incremental run must NOT deprecate live unchanged-file symbols.")

**B1 fix — B1-a (revised after review), the cheap liveness bump, with the corrections that make it correct + safe:**

```cypher
CALL {
  MATCH (s:Symbol {group_id: $group_id})
  WHERE NOT s:Deprecated AND s.deleted_at IS NULL
    AND NOT s.qualified_name IN $written_changed_qnames
  SET s.last_seen_in_run_id = $run_id
} IN TRANSACTIONS OF 10000 ROWS
```

Three review-driven corrections vs rev1:
1. **Predicate is "all still-live symbols we did NOT just write", not `= $prev_run_id`.** A prior partial/failed run
   (runs finalize even on failure: `symbol_index_swift.py:419-428`) can leave nodes on a different run-id; the
   `= $prev_run_id` form would miss them and prune would wrongly deprecate them. (architect)
2. **MUST carry the `group_id` filter** (shown) — without it the bump crosses projects in the shared Neo4j and
   silently suppresses prune for every other project. Add a cross-project isolation test (P1-TC-08). (qa)
3. **MUST batch (`CALL { } IN TRANSACTIONS OF 10000`)** + **add an index `(:Symbol group_id, last_seen_in_run_id)`**
   (absent from `EXPECTED_SCHEMA`). One unbatched `SET` over 248k nodes is 2–5 min, holds a write lock that
   **blocks all live `search_graph`/`semantic_search` reads** on the uvicorn server for the duration, and risks GC
   pressure. Batched + indexed it should be < 60 s — make "< 60 s, no read-block" the acceptance bar. (performance)

### 1.1 prune threshold denominator bug (fix alongside B1)

`prune_swift_symbols/cypher.py:16-18` computes `overall_total = count(m where m:Symbol OR m:File)` **without a
`NOT m:Deprecated` filter**, while `stale_total` excludes deprecated. Over sustained incremental operation the
deprecated population grows monotonically, inflating the denominator and silently **loosening the 0.5 guard exactly
when it matters most**. Fix: exclude `:Deprecated` from `overall_total`. Add boundary tests (T-B1/T-B2).

### 1.2 dead_code liveness filter (Phase-1 prerequisite, independent of incrementality)

`dead_code/graph_loader.py:14,37` loads `(:Symbol {group_id})` and its edges with **no `deleted_at`/`:Deprecated`
filter** — unlike `call_edge_swift.py:35-39` (`_ACTIVE_SYMBOLS`) which filters to live. On a full re-ingest this is
masked (everything is rewritten fresh); under incremental + prune the deprecated population is real and persistent,
so `dead_code` computes reachability over deprecated nodes + stale edges → **false-dead and false-live**. Add
`WHERE s.deleted_at IS NULL AND NOT s:Deprecated` to both loader queries. **This ships in Phase 1, not Phase 3** —
decoupling dead_code's *schedule* (B3) does not fix its *correctness on a pruned graph*.

**Acceptance for B1 (load-bearing, real Neo4j):** after a file-scoped incremental write + B1-a bump + prune on
1 changed file of N → **ZERO unchanged-file symbols `:Deprecated`**, changed-file symbols updated to new values,
removed-file symbols deprecated, **and the bump did not touch any other project's symbols**.

---

## 2. Load-bearing blocker — B6 (NEW): REFERENCES-family edges have no delete path / no liveness

rev1 Phase-1 step 6 claimed `:REFERENCES`/`:CONFORMS_TO`/`:EXTENDS`/`:EXTENSION_OF` are "re-derived like `:CALLS`".
**That is factually wrong.** `symbol_node_writer.py:88-114` — all four are pure `MERGE (a)-[:REL]->(b)`: **no
`last_seen_in_run_id` on the edge, no DELETE anywhere** (`grep DELETE.*REFERENCES src/` → empty). Consequence: a
reference that *disappears* from a changed file is never removed — true even on full re-ingest today, worse under
incremental. `dead_code/graph_loader.py:37` traverses these edges for reachability → a stale `:REFERENCES` makes a
deleted symbol look **false-live**. This breaks the spec's core "no stale-as-live" promise.

**B6 fix (Phase 1, same tier as B1):** stamp `last_seen_in_run_id` on all four edge types (mirror
`call_edge_swift.py:31-33`), and add a delete-stale-edges step scoped to changed-source-file symbols
(`MATCH (a)-[r:REFERENCES|CONFORMS_TO|EXTENDS|EXTENSION_OF]->() WHERE a.file_path IN $changed AND r.last_seen_in_run_id <> $run_id DELETE r`).
Cover the "edge whose source is unchanged but target moved/renamed" orphan case (same shape as B2).

---

## 3. Design — phases

### Phase 1 — incremental `symbol_index_swift` Neo4j layer (highest value)

1. **Change-set (see B4):** `changed/added/removed` = **git-diff (`detect_changes`) ∩ SCIP document paths**, against
   the freshly re-emitted SCIP HEAD. Hard-fall-back to a full run if `detect_changes` returns `truncated=true`.
2. **Tantivy:** already incremental (#6) — `delete_by_file_paths(changed ∪ removed)` + rewrite changed.
3. **Neo4j symbols:** `build_symbol_node_rows` scoped to `changed ∪ added`; `write_symbol_nodes` MERGEs just those.
   **Filter the SCIP iteration too** (performance): in incremental mode `_refresh_graph_state` must not iterate all
   248k `iter_scip_symbol_infos` to build `seen_qnames` — scope it, or the 3–6 min Python pass remains.
4. **Liveness:** B1-a batched bump (§1) so unchanged symbols stay live; prune denominator fix (§1.1).
5. **Removed files:** replace `soft_delete_symbols`' 248k-`IN`-list with a **file-scoped** delete
   (`MATCH (s:Symbol {group_id}) WHERE s.file_path IN $removed_files SET s.deleted_at = …`) — `symbol_node_writer.py:284`.
6. **Edges:** B6 — stamp + delete-stale `:REFERENCES`-family for changed-source files; MERGE the new ones.
7. **dead_code loader liveness filter** (§1.2) ships here.

**Acceptance:** edit 1 file of uw → graph-update wall-clock **< ~3 min** (excl. xcodebuild); search/semantic/
find_references/get_code_snippet reflect the edit; unchanged symbols + their embeddings + edges intact (B1+B6);
removed-file symbols + their edges gone/deprecated; no cross-project bleed. Full test catalog §6.

### Phase 2 — incremental `call_edge_swift` + file-scoped audit extractors

1. **call_edge_swift:** delete `:CALLS` whose **caller** is in a changed file (not all), re-collect from changed
   files' IndexStore records, MERGE back (edges carry `last_seen_in_run_id`). **B2:** also delete inbound `:CALLS`
   to symbols in changed files to avoid orphans when a callee's qn changes; or schedule a periodic full rebuild.
2. **File-scoped audit extractors** (`code_ownership`, `coding_convention`, `crypto_domain_model`,
   `error_handling_policy`, `testability_di`, `localization_accessibility`, `dead_symbol_binary_surface`): re-run on
   only changed files, replacing those files' findings. Each needs a per-file delete API it does not have today —
   audit which are truly per-file vs need cross-file context before scoping.

**Acceptance:** changed files' call-graph + ownership + conventions + error/crypto current; unchanged files'
findings byte-identical pre/post (assert via query, not prose); per-file SLA stated + benchmarked.

### Phase 3 — orchestration + inherently-global extractors

1. **Orchestrator:** `project_analyze(mode="incremental")` (or `incremental_update`): `detect_changes` →
   `changed_ratio < 0.8` runs the incremental path (+ embedding hash-skip + git checkpoint), else full. Emit a
   per-extractor `incremental | full | skipped` report. `truncated=true` → full.
2. **Inherently-global** — `dead_code` (reachability), `hotspot` (churn×complexity), `cross_module_contract`:
   cannot be file-local. DECOUPLE to a schedule with an explicit `stale_since=<commit>` stamp on results (consistent
   with W1). Per-commit path keeps symbols/search/call-graph/ownership fresh; global audits trail, visibly stale.
   (All 3 reviewers endorse the scheduling call; it requires the §1.2 liveness fix to be *correct*, not just late.)

**Acceptance:** 10–15-file commit → graph update **< ~10 min** (excl. xcodebuild); navigation tools 0 commits behind
(assert `last_seen_in_commit` == `git HEAD`); global audits carry `stale_since`.

---

## 4. Named blockers

- **B1 — prune liveness** (Phase 1, load-bearing). B1-a batched + indexed + `group_id`-scoped + "bump all still-live
  not-just-written". Plus §1.1 threshold-denominator fix.
- **B6 — REFERENCES-family edge liveness/delete** (Phase 1, load-bearing, NEW). No delete path today → false-live.
- **dead_code loader liveness filter** (Phase 1 prerequisite). `graph_loader.py:14,37`. Not optional, not Phase 3.
- **B2 — call_edge cross-file orphan edges** (Phase 2). Delete inbound `:CALLS` to changed-file symbols too.
- **B3 — `dead_code`/`hotspot`/`cross_module` are global** (Phase 3). Schedule + `stale_since`; needs §1.2 to be correct.
- **B4 — change-set integrity** (Phase 1). Authoritative = **git ∩ SCIP** paths. Handle: (a) SCIP-only generated/
  vendored docs (`symbol_index_swift.py:750-759` vendor list) — never silently drop; (b) `detect_changes` 500-file
  truncation (`native_detect_changes.py:121`) → full fallback; (c) renames — `git diff` runs without `-M`
  (`native_detect_changes.py:109`) so a rename = old(removed)+new(changed); verify prune deprecates old qn, adds new,
  no dup; (d) assert SCIP `file_path` and git path are byte-identical repo-relative (don't assume).
- **B5 — embedding already incremental; in-degree counter is a COST not a risk.** Hash-skip handles embeddings.
  The importance/in-degree counter is recomputed over the full occurrence stream every run by construction
  (`importance.py` run-id reset + `symbol_index_swift.py:275-277`) — it is correct, but it is a full-stream-scan cost
  the "minutes" budget must include, not a consistency concern.

## 5. Performance reality (honest budget for a 10-file uw commit, post Phases 1–2)

True bottleneck ranking (performance review, grounded):

| Layer | Realistic | Note |
|---|---|---|
| **xcodebuild incremental re-emit** | **2–15 min** | The floor. Protocol/interface change cascades module recompiles. Unaddressed by any graph fix. **Benchmark on representative commits before promising an SLA.** |
| SCIP parse + Python passes (165 MB) | 3–6 min | Must filter iteration in incremental mode (Phase 1 step 3) or it stays |
| B1-a bulk bump | < 60 s | ONLY if batched + indexed; else 2–5 min + read-block |
| `soft_delete` (file-scoped) | < 30 s | vs 1–2 min for the current 248k-IN-list |
| Tantivy (changed files) | 1–2 min | needs flag ON |
| Neo4j MERGE (changed symbols) | < 30 s | ~300 symbols for 10 files |
| Embedding (changed + model load) | ~1.5 min | model cold-load ~60–90 s dominates; warm if uvicorn persistent |
| call_edge (file-scoped) | < 30 s | Phase 2 |
| `dead_code` / `hotspot` | minutes–~52 min | Phase 3: off the hot path, `stale_since` |

**Honest end-to-end:** xcodebuild floor (2–15 min) + **~5–8 min graph** = realistically **10–25 min**, dominated by
xcodebuild. The graph-side target of "< ~10 min" is achievable; "single-digit minutes end-to-end" is not, because of
xcodebuild. State the SLA as **"xcodebuild + < 10 min"**.

## 6. Test catalog (the rev1 gap — QA said NO-GO on tests without this)

The existing #6 integration test (`tests/extractors/integration/test_symbol_index_swift_integration.py:241-396`,
`test_incremental_run_does_not_deprecate_unchanged_file_symbols`) drives the **full-write** path
(`assert second_run.nodes_written == 6`), NOT the proposed file-scoped + B1-a path — it must be **rewritten** for
Phase 1 (the assertion will flip to the changed-file count). Required cases before a slice merges:

**Phase 1 — symbol_index (real Neo4j, testcontainers + real git repo):**
- P1-TC-01 edit 1 file → unchanged symbols not deprecated (existing A1, rewritten for file-scoped path).
- P1-TC-02 edit → **changed file's Neo4j props actually updated** (positive assertion — guards the B4 silent-noop).
- P1-TC-03 add file → new symbols appear, zero deprecations.
- P1-TC-04 delete file → its symbols + `:File` deprecated, others intact.
- P1-TC-05 git **rename** → old path deprecated, new live, no duplicates.
- P1-TC-06 symbol **moved** between files (same qn) → `file_path` updated to new location, old file not stale.
- P1-TC-07 file with **zero symbols** → `:File` liveness bumped (else prune kills it next run).
- P1-TC-08 **cross-project isolation** — incremental on project A does NOT bump project B's symbols (B1-a `group_id`).
- P1-TC-09 **idempotency** — same incremental twice → zero net delta.
- P1-TC-10 **changed_ratio ≥ 0.8** → orchestrator falls back to full.
- P1-TC-11 **SCIP-only generated/vendored doc** not in git diff (B4) → not silently dropped.
- P1-TC-12 **`detect_changes truncated=true`** (>500 files) → full fallback.
- P1-TC-13 **B6 edge hygiene** — a removed reference's `:REFERENCES` edge is deleted (no stale → no false-live).
- P1-TC-14 **Tantivy↔Neo4j consistency** post-prune (removed-file path, not just unchanged).

**Phase 2 — call_edge:** P2-TC-01 changed-caller edges replaced, unchanged intact; P2-TC-02 **qn-change orphan**
(B2) — old `:CALLS` to renamed callee deleted; P2-TC-03 cross-project edge isolation.

**Threshold boundaries (prune):** T-B1 ratio 0.50 exactly **proceeds** (strict `>` at `extractor.py:143`), 0.51
skips; T-B2 `overall_total == 0` → no div-by-zero, proceeds; T-B5 multi-generation graph (run N-2 symbols correctly
deprecated, run N-1 correctly bumped).

**3 deadliest silent holes to specifically defend (qa):** (1) B4 path-mismatch → changed file silently not updated
while A1 passes (P1-TC-02 catches); (2) B1-a cross-project over-bump invisible to A1 (P1-TC-08 catches); (3) stale
REFERENCES edges to deprecated targets (P1-TC-13 catches).

---

## 7. Phasing recommendation

1. **Phase 1** — biggest cost + all the correctness blockers (B1, B6, §1.1, §1.2, B4). Gated on small testable
   fixes. Highest value, but **not** as small as rev1 implied — B6 + dead_code filter + B4 are real scope.
2. **Phase 2** — call_edge + per-file audit scoping.
3. **Phase 3** — orchestrator + global decoupling (`stale_since`). This is what the operator calls per commit.

Each phase ships behind `PALACE_INCREMENTAL_INGEST` (already exists), default OFF until the B1/B6/B4 correctness
tests (§6) pass on real Neo4j.

---

## rev1 → rev2 changelog (from the 3-lens voltAgent review)

- **Added B6** (REFERENCES-family edges have no delete/liveness → false-live) as a load-bearing Phase-1 blocker;
  corrected the rev1 false claim that these edges are "re-derived like :CALLS".
- **Moved the dead_code loader liveness filter into Phase 1** (§1.2) — it's a correctness bug independent of
  incrementality; "nightly" (B3) makes dead_code late, not correct.
- **Rewrote B1-a:** predicate "all still-live not-just-written" (not `= $prev_run_id`), mandatory `group_id` filter,
  mandatory batching + a new `(group_id, last_seen_in_run_id)` index; acceptance "< 60 s, no read-block".
- **Added §1.1** prune threshold-denominator bug (counts deprecated → guard erodes).
- **Tightened B4:** authoritative change-set = git ∩ SCIP; handle SCIP-only generated docs, 500-file truncation,
  renames (no `-M`), path-normalization assertion.
- **Added §5 performance reality:** xcodebuild is the unaddressed floor; SCIP 7-pass iteration + `soft_delete`
  248k-IN-list are unfiltered costs; softened the SLA from "single-digit minutes" to "xcodebuild + < 10 min".
- **Added §6 test catalog** (14 Phase-1 + 3 Phase-2 + threshold cases; the existing #6 test must be rewritten).
- **Corrected B5:** in-degree counter is a full-stream-scan cost, not a consistency risk.
