# Palace MCP Uplift — Walker Execution Plan v6

Spec: `docs/specs/palace-mcp-usability-uplift-v6.md`
Supersedes: v1 plan (rejected with v5 — fictional file paths, missed
prerequisites, file overlap errors, gate goalpost-moving).

Pattern: walker orchestrates, each chain sequential, two parallel teams
(Claude / Codex) with file-overlap-verified parallelism.

---

## §1 Walker contract (unchanged from v1 plan)

```
loop:
  walker picks next 1-2 slices from roadmap (one Claude, one Codex —
      if both teams free AND files don't overlap)
  POST issue to paperclip, assignee={Claude PE, Codex PE}
  walker self-block: blockedBy=[slice IDs], status=blocked
  await: both notify done
  unblock → next pair
end
```

**Rules (committed):**
- Never >1 in-flight task per team
- Never assign overlapping files in the same cycle
- Walker creates the **next pair only after the prior pair finishes**
  (no upfront mass-creation)
- Gate evaluation is walker's responsibility but verdict requires
  operator + CTO co-sign

---

## §2 Real-repo file map (B4 fix — verified)

All slice file references in this plan checked against actual repo
2026-06-01. v5 plan had fictional `code/find_references.py` and
`code/search_graph.py`. **The truth:**

| Functionality | Real location |
| --- | --- |
| qualified_name resolution | `services/palace-mcp/src/palace_mcp/code_composite.py:_resolve_qn()` line 140 |
| graph search (palace.code.search_graph) | `code_composite.py` (search graph implementation) |
| semantic search core | `services/palace-mcp/src/palace_mcp/code/find_semantic.py` ✓ exists |
| snippet hydration | `services/palace-mcp/src/palace_mcp/code/snippet_provider.py` ✓ exists |
| SCIP parsing | `services/palace-mcp/src/palace_mcp/extractors/scip_parser.py` ✓ |
| Symbol writer | `services/palace-mcp/src/palace_mcp/extractors/foundation/symbol_node_writer.py` ✓ |
| Schema declarations | `services/palace-mcp/src/palace_mcp/extractors/foundation/schema.py` ✓ |
| symbol_index_swift extractor | `services/palace-mcp/src/palace_mcp/extractors/symbol_index_swift.py` ✓ (NOT subdir) |
| embedding_symbol extractor | `services/palace-mcp/src/palace_mcp/extractors/embedding_symbol.py` ✓ |
| IngestRun writer #1 (CREATE_INGEST_RUN cypher) | `extractors/runner.py:322` |
| IngestRun writer #2 (checkpoint) | `extractors/foundation/checkpoint.py:24` (KEY: `run_id`) |
| run_extractor MCP tool | `extractors/mcp_server.py:_palace_ingest_run_extractor()` line 826 |
| Lifespan (for F4.1 pre-warm) | `palace_mcp/main.py:lifespan()` line 76 |
| Qodo backend (for pre-warm helper) | `palace_mcp/embeddings/qodo.py` |

`code/find_references.py` and `code/search_graph.py` **DO NOT EXIST**.
Resolver is in `code_composite.py`. semantic_search core is
`find_semantic.py` (correctly referenced in v6).

---

## §3 Slice catalog (15 slices + 2 gate evaluations)

| Phase | Slice ID | Files touched | Effort | Owner | Depends on |
| --- | --- | --- | --- | --- | --- |
| **Phase 0 prerequisite** | | | | | |
| 0 | **PHASE0-LIFECYCLE** | `extractors/runner.py` (CREATE_INGEST_RUN cypher), `extractors/foundation/checkpoint.py`, `extractors/foundation/schema.py` (indexes), `code_composite.py` (`deleted_at IS NULL` filters), `code/find_semantic.py` (same), tests, migration `services/palace-mcp/migrations/2026-06-XX-ingest-run-normalize.cypher` | 2.0d | Codex | GIM-1062 + GIM-1063 + GIM-1064 all merged |
| **Phase 1** | | | | | |
| 1A | **PALACE-S0** anchors+repo_head_sha+recount_anchors+anchors_only flag | `extractors/scip_parser.py` (read_scip_commit_sha), `extractors/foundation/symbol_node_writer.py` (3 new fields), `extractors/symbol_index_swift.py` (honor anchors_only), `extractors/base.py` (BaseExtractor signature), `extractors/runner.py` (pass anchors_only), `mcp_server.py` (add `anchors_only` param to run_extractor, add `palace.ops.recount_anchors`), tests | 2.0d | Codex | PHASE0-LIFECYCLE |
| 1B | **PALACE-S1F2** human-name resolution | `extractors/scip_parser.py` (add decode_scip_short_name), `extractors/foundation/symbol_node_writer.py` (short_name field), `code_composite.py` (`_resolve_qn` extended w/ short_name path + rate-limit), `mcp_server.py` (rate-limit state), new `scripts/migrate_short_name.py`, tests | 2.0d | Codex | PALACE-S0 (uses anchors for disambiguation list) |
| 1C | **PALACE-GOLD** frozen gold corpus | new `bench/gold/phase1-frozen-2026-06-XX/` (README, repo-pins.json, Q1/Q2/Q3 prompt+expected+rules+reference-runs) | 0.5d | Codex | — (parallel-safe) |
| 1D | **PALACE-DEPLOY** Phase 1 deploy runbook + provisioning | new `services/palace-mcp/scripts/phase1-deploy.sh`, new `docs/runbooks/palace-phase1-deploy.md`, iMac compose + dev-Mac launchd plist updates | 0.5d | Codex | PALACE-S0, PALACE-S1F2 |
| 1E | **PALACE-F3** dedup_by_file flag | `code/find_semantic.py` (param + group), `code_composite.py` (search_graph half), tests | 0.25d | Claude | PALACE-F40 (uses counter) |
| 1F | **PALACE-F40** telemetry (ring buffer + JSONL sink) | new `palace_mcp/telemetry/__init__.py`, `palace_mcp/telemetry/ring_buffer.py`, `palace_mcp/telemetry/jsonl_sink.py`, instrument points in `main.py`/`code/find_semantic.py`/`code_composite.py`, `mcp_server.py` (`palace.health.metrics` tool), tests | 1.0d | Claude | — (parallel-safe with PHASE0) |
| 1G | **PALACE-F41** Qodo pre-warm + yield-on-fail | `main.py:lifespan()` (pre-warm), `embeddings/qodo.py` (warmup helper), tests | 0.5d | Claude | PALACE-F40 (uses counter) |
| 1H | **PALACE-F43** git stale-check opt-in hoist | `code/find_semantic.py` (hot path), `code/snippet_provider.py` (`_check_stale` batching), `mcp_server.py` (tool description re include_staleness), tests | 0.5d | Claude | PALACE-F40 |
| 1I | **PALACE-Q1Q2-HARNESS** controlled benchmark | new `bench/scripts/phase1-kill-gate.sh`, new `bench/scripts/run-controlled-benchmark.py`, integration test | 0.75d | Claude | PALACE-F40 (reads JSONL sink), PALACE-GOLD (uses pinned corpus) |
| **GATE 1** | **PALACE-GATE1** evaluation + 1-day adjustment window (B6: harness bugs ONLY) | N=50 controlled runs via PALACE-Q1Q2-HARNESS, verdict | 0.5d ops | Walker + operator + CTO co-sign | All Phase 1 slices |
| **Phase 2** | | | | | |
| 2A | **PALACE-F1B-SPIKE** sourcekit-lsp end-to-end on one workspace | new `services/palace-mcp/scripts/lsp-spike.py` (~100 LOC), manual `xcode-build-server config + xcodebuild build`, write `bench/runs/lsp-spike-2026-06-XX/results.md` | 1.0d | Codex | GATE 1 pass + dev-Mac available |
| 2B | **PALACE-F1B-IMPL** workspace pool + tool | new `palace_mcp/lsp/__init__.py`, `palace_mcp/lsp/sourcekit_client.py`, `palace_mcp/lsp/workspace_pool.py`, `palace_mcp/lsp/call_hierarchy.py`, `mcp_server.py` (new `palace.code.call_hierarchy` tool), tests | 2.0d | Codex | PALACE-F1B-SPIKE |
| 2C | **PALACE-F1B-HARDEN** error envelopes + iMac contract | `palace_mcp/lsp/call_hierarchy.py` (error envelopes), `palace_mcp/lsp/sourcekit_client.py` (subprocess shutdown), `docs/runbooks/palace-mcp-failure-modes.md` (new section), tests | 1-2d | Codex | PALACE-F1B-IMPL |
| **GATE 2** | **PALACE-GATE2** evaluation + 1-day window | `bench/scripts/phase2-kill-gate.sh` (uses PALACE-GOLD Q3) | 0.5d ops | Walker + operator + CTO co-sign | All Phase 2 slices |
| **Phase 3 (conditional)** | | | | | |
| 3A | **PALACE-F5A** body_hash + commit_sha guard + migration | `extractors/embedding_symbol.py` (`_embedding_text` extend), `code/snippet_provider.py` (`git show` fallback), new `scripts/migrate_body_hash.py` (checkpoint/resume), tests | 1.0d (+8h overnight migration) | Codex | GATE 2 pass + PALACE-S0 (anchors) |
| 3B | **PALACE-F5B** periodic re-ingest + ignore list | new `services/palace-mcp/scripts/palace-periodic-reingest.sh`, new `palace_mcp/ops/detect_stale_files.py`, launchd plist, mcp_server.py (new `palace.ops.detect_stale_files` tool), tests | 1.0d | Codex | GATE 2 pass + PHASE0-LIFECYCLE (IngestRun) |
| 3C | **PALACE-F42** coverage cache + atomic invalidation + global semaphore | `code/find_semantic.py` (read cache), `extractors/runner.py` (semaphore + atomic recount), `mcp_server.py` (wire `palace.ops.recount_coverage_cache`), tests | 1.0d | Claude | GATE 2 pass + PALACE-F40 |
| **P2.5 (optional)** | | | | | |
| OPT | **PALACE-P25-IMAC-FIXTURE** index-store snapshot for top-3 projects | new `services/palace-mcp/fixtures/lsp-snapshots/`, new `scripts/build-lsp-snapshot.sh`, `palace_mcp/lsp/call_hierarchy.py` (iMac fallback path), docker compose mount, `data_freshness_warning` envelope, tests | 1-2d | Codex | GATE 2 pass + operator request |

**Total dev-days:** Phase 0 (2.0) + Phase 1 (8.0) + Phase 2 (4-5) +
Phase 3 (3.0 conditional) + P2.5 (1-2 optional) = **17-20 dev-days**
across 4-5 calendar weeks with parallel tracks.

---

## §4 Track allocation (30% Claude / 70% Codex target)

| Phase | Claude effort | Codex effort | Total | Claude share |
| --- | --- | --- | --- | --- |
| Phase 0 | 0 | 2.0 | 2.0 | 0% |
| Phase 1 | 3.0 | 5.0 | 8.0 | 37% |
| Phase 2 | 0 | 4-5 | 4-5 | 0% |
| Phase 3 | 1.0 | 2.0 | 3.0 | 33% |
| **Overall** | **4.0** | **13-14** | **17-18** | **~23%** |

Slightly under 30% Claude (Phase 2 is all Codex by nature — single
LSP-proxy implementation can't be parallelized). Acceptable per operator
context.

---

## §5 Cycle-by-cycle walker execution

### Phase 0 — single-track (Codex only)

#### Cycle 0.1 — PHASE0-LIFECYCLE (2 days, Codex solo)

| Track | Slice | Files | Effort |
| --- | --- | --- | --- |
| Codex | PHASE0-LIFECYCLE | runner.py + checkpoint.py + schema.py + 2 read sites + migration cypher | 2.0d |
| Claude | _idle this cycle_ — walker takes opportunity to assign Claude something unrelated from backlog (PR review, docs) OR leaves idle |  |  |

Walker: POST PHASE0-LIFECYCLE → CXPE; self-block 2d; done → proceed.

---

### Phase 1 — 4 cycles, parallel pairs (overlap-verified)

#### Cycle 1.1 (~2 days wall)

| Track | Slice | Key files | Overlap with sibling? |
| --- | --- | --- | --- |
| **Codex** | **PALACE-S0** (2d) | scip_parser.py, symbol_node_writer.py, symbol_index_swift.py, base.py, runner.py, mcp_server.py (add anchors_only + recount_anchors), tests | runner.py and mcp_server.py overlap with sibling — **see check below** |
| **Claude** | **PALACE-F40** (1d) | new `telemetry/__init__.py`, `telemetry/ring_buffer.py`, `telemetry/jsonl_sink.py`, main.py (call-site instrumentation), find_semantic.py (instrumentation), code_composite.py (instrumentation), mcp_server.py (add `palace.health.metrics` tool) | **runner.py: NO** (F40 doesn't touch it). **mcp_server.py: YES, both add tools** |

**Overlap resolution:**
- `mcp_server.py`: PALACE-S0 adds `anchors_only` param + `recount_anchors` tool. PALACE-F40 adds `palace.health.metrics` tool. These are different tool definitions; merge conflict risk on the @_tool decorator section only. CR must verify post-merge.
- **Mitigation:** PALACE-F40 commits first (smaller, 1d vs 2d); PALACE-S0 rebases on F40 before merge.

#### Cycle 1.2 (~2 days wall)

| Track | Slice | Key files | Overlap |
| --- | --- | --- | --- |
| **Codex** | **PALACE-S1F2** (2d) | scip_parser.py (decode_scip_short_name), symbol_node_writer.py (short_name field), code_composite.py (`_resolve_qn` extended), mcp_server.py (rate-limit), scripts/migrate_short_name.py, tests | scip_parser.py + symbol_node_writer.py both edited by S0 too — **sequential dep**, not overlap (S1F2 depends on S0) |
| **Claude** | **PALACE-F41** (0.5d) | main.py:lifespan(), embeddings/qodo.py (warmup helper), tests | main.py overlap with F40 — **sequential (F40 done by now)** |
| **Claude** | **PALACE-F43** (0.5d) — chains after F41 | code/find_semantic.py, code/snippet_provider.py, mcp_server.py (tool desc), tests | mcp_server.py: tool description edit; small chunk, low conflict risk |

Cycle 1.2 is **2 parallel + chained**: Codex on S1F2 (2d) while Claude
does F41 then F43 (1d combined). Both done by ~day 2 of cycle.

#### Cycle 1.3 (~0.75 day wall)

| Track | Slice | Key files | Overlap |
| --- | --- | --- | --- |
| **Codex** | **PALACE-GOLD** (0.5d) | new bench/gold/phase1-frozen-2026-06-XX/ | none — new dir |
| **Codex** | **PALACE-DEPLOY** (0.5d, chains after GOLD) | new scripts/phase1-deploy.sh, docs/runbooks/palace-phase1-deploy.md, compose/launchd updates | none |
| **Claude** | **PALACE-F3** (0.25d) | code/find_semantic.py, code_composite.py | F43 already touched find_semantic.py (cycle 1.2) — **sequential, F3 after F43** |
| **Claude** | **PALACE-Q1Q2-HARNESS** (0.75d, chains after F3) | new bench/scripts/phase1-kill-gate.sh, bench/scripts/run-controlled-benchmark.py | uses GOLD + F40, both done |

Cycle 1.3 has serial chains within each team. Wall-time ~1 day.

---

### GATE 1 (1-day window, B6-tightened)

PALACE-GATE1 (walker + operator + CTO):
1. Run `bench/scripts/phase1-kill-gate.sh` from harness
2. Read `bench/runs/phase1-gate-<date>/metrics.jsonl`, compute p50/p95
3. Compare against `bench/gold/phase1-frozen-2026-06-XX/` per Q
4. Apply v6 §4 gate criteria (Q1 recall+SLO, Q2 must-pass)
5. **Adjustment window: harness bugs ONLY** (per B6).
   Threshold disagreement → write v6.1 + restart Phase
6. Verdict in `bench/runs/phase1-gate-<date>/verdict.md`
7. Operator + CTO co-sign

Outcomes:
- Q2 fail → walker creates PALACE-ARCHIVE issue, exits roadmap
- Q2 pass → walker proceeds to Phase 2 (regardless of Q1 outcome, per v6/C5 commit)

---

### Phase 2 — sequential spike+impl+harden

#### Cycle 2.1 — PALACE-F1B-SPIKE (1d, Codex)

| Track | Slice | Files |
| --- | --- | --- |
| **Codex** | **PALACE-F1B-SPIKE** | new scripts/lsp-spike.py; operator runs xcode-build-server config + xcodebuild build once manually; spike result in bench/runs/lsp-spike-<date>/ |
| **Claude** | _idle or assigned unrelated_ |  |

**Decision gate after spike:** spike succeeds (≥3 callers returned on
MoneroAdapter.send in <10s wall cold) → fund F1B-IMPL. Spike fails →
abandon Phase 2; ship as-is.

#### Cycle 2.2 — PALACE-F1B-IMPL (2d, Codex)

Single track, single slice. Walker self-block 2d.

#### Cycle 2.3 — PALACE-F1B-HARDEN (1-2d, Codex)

Single track. Walker self-block 1-2d.

### GATE 2 (1-day window)

Same protocol as GATE 1. Q3 must pass for Phase 3 funding.

---

### Phase 3 — 2 cycles, parallel

#### Cycle 3.1 (~1 day wall)

| Track | Slice | Files | Overlap |
| --- | --- | --- | --- |
| **Codex** | **PALACE-F5A** (1d) | embedding_symbol.py, code/snippet_provider.py, scripts/migrate_body_hash.py | snippet_provider.py touched by F43 in P1 — **sequential, F43 done** |
| **Claude** | **PALACE-F42** (1d) | code/find_semantic.py, extractors/runner.py, mcp_server.py | runner.py touched by PHASE0 + S0 in P1 — **sequential, both done**; find_semantic.py: read cache (small chunk); mcp_server.py: wire existing tool |

#### Cycle 3.2 (~1 day wall)

| Track | Slice | Files |
| --- | --- | --- |
| **Codex** | **PALACE-F5B** (1d) | new scripts/palace-periodic-reingest.sh, new palace_mcp/ops/detect_stale_files.py, launchd plist, mcp_server.py (add detect_stale_files tool), tests |
| **Claude** | _idle (Phase 3 has only 3 slices; cycle is single-track this time)_ |  |

#### Off-hours migration (overnight)

`scripts/migrate_body_hash.py` — ~8h on MPS. Walker pings progress
every 2h via heartbeat. No new task assignment during migration.

---

### Sprint D — P2.5 OPTIONAL

Only if operator approves post-Phase 2:

| Track | Slice | Files | Effort |
| --- | --- | --- | --- |
| **Codex** | **PALACE-P25-IMAC-FIXTURE** | new services/palace-mcp/fixtures/lsp-snapshots/ (~300MB committed; consider Git LFS), new scripts/build-lsp-snapshot.sh, palace_mcp/lsp/call_hierarchy.py (iMac fallback path), docker compose mount | 1-2d |

---

## §6 Walker state machine — Phase 0 + Phase 1 timeline

```
day -3..0:  GIM-1062 + GIM-1063 + GIM-1064 audit chain must merge first
day 0:      walker takes PHASE0-LIFECYCLE → CXPE
            walker self-block 2d
day 2:      PHASE0 done
            walker → cycle 1.1
            POST PALACE-S0 (CXPE) + PALACE-F40 (PE)
            walker block on [S0, F40]
day 3:      F40 done; S0 in progress
            (PE could be assigned next chain slice — but walker rule:
             1 task per team. Walker keeps PE idle until cycle 1.1 closes.)
day 4:      S0 done
            walker → cycle 1.2
            POST PALACE-S1F2 (CXPE) + PALACE-F41 (PE, will chain to F43)
            walker block on [S1F2, F41]
day 4.5:    F41 done. Walker decides: chain F43 immediately or wait for S1F2?
            Rule: one-task-per-team → walker can POST F43 to PE without
            unblocking S1F2 (still blocked on S1F2 + F43 now)
            POST PALACE-F43 (PE)
            walker block on [S1F2, F43]
day 5:      F43 done; S1F2 in progress
day 6:      S1F2 done
            walker → cycle 1.3
            POST PALACE-GOLD (CXPE) + PALACE-F3 (PE)
            walker block on [GOLD, F3]
day 6.25:   F3 done. Walker chains PALACE-Q1Q2-HARNESS → PE
            walker block on [GOLD, Q1Q2-HARNESS]
day 6.5:    GOLD done. Walker chains PALACE-DEPLOY → CXPE
            walker block on [DEPLOY, Q1Q2-HARNESS]
day 7:      DEPLOY done; Q1Q2-HARNESS done
            walker → GATE 1
            POST PALACE-GATE1 (walker self-assigns coordination)
day 7-8:    GATE 1 evaluation + 1-day adjustment window
day 8:      Verdict cosigned by operator + CTO
            outcomes:
              archive → walker exits, files PALACE-POSTMORTEM
              continue → walker → cycle 2.1
```

Total Phase 0 + Phase 1 wall-time: **~8 calendar days** with parallel
tracks (vs ~10 dev-days sequential), assuming no agent restarts.

---

## §7 Risks + mitigations

| Risk | Mitigation |
| --- | --- |
| Walker stuck (claude proc idle hang per `reference_claude_process_idle_hang.md`) | Operator pings; manual `paperclipai heartbeat run --agent-id` on iMac |
| Slice issue scope creep | Each issue carries `spec_ref` to v6 anchor; CR enforces scope |
| File overlap discovered mid-slice | walker pauses sibling; CR mediates merge order |
| GATE 1 evidence shows v6 spec error | B6 explicitly forbids threshold change; new spec required → write v7 + restart Phase |
| Spike PALACE-F1B-SPIKE fails | Pre-committed: abandon Phase 2, ship Phase 1 only; document in `docs/research/lsp-spike-failure-postmortem.md` |
| Codex queue backed up (PE has multiple in-flight from other epics) | Walker uses `paperclip queue length` API check before posting; backs off if PE >2 tasks |
| Migration `migrate_body_hash.py` crashes mid-run | Checkpoint/resume implemented in slice itself; safe to interrupt |

---

## §8 What walker does NOT decide autonomously

- Phase 1 → Phase 2 funding (operator + CTO co-sign GATE 1 verdict)
- Phase 2 → Phase 3 funding (operator + CTO co-sign GATE 2)
- Spike pass/fail interpretation (operator decides if cold-start time
  acceptable)
- P2.5 iMac fixture investment (explicit operator request)
- Archive trigger (operator + CTO co-sign)
- Spec amendments mid-flight (operator initiates)

Walker is execution coordinator, not decision-maker.

---

## §9 Slice issue template

```markdown
# {SLICE-ID}: {short title}

## Spec
docs/specs/palace-mcp-usability-uplift-v6.md#{anchor}

## Scope (max 3 sentences)
{what changes, what files, what's out of scope}

## Files touched (verified against real repo)
- {file 1} — {what changes}
- {file 2} — {what changes}

## Effort
{N.N} dev-days

## Acceptance
- {test 1, with file:line if applicable}
- {test 2}
- All existing tests pass: `uv run pytest`
- Lint: `uv run ruff check`
- Typecheck: `uv run mypy`

## Dependencies (blocked by)
- {prior slice IDs that must merge first}

## Coordination
- Parallel sibling this cycle: {sibling ID or "none"}
- File overlap with sibling: {list overlapping files or "none"}
- Merge order if overlap: {who merges first + rebase plan}

## Reporter
walker (auto-generated for palace uplift epic)
```

---

## §10 Open questions for operator before walker starts

1. **Approve Phase 0 + Phase 1 budget** (10 dev-days + ~$3-4k Anthropic
   spend)?
2. **Confirm v6 strict gate-adjustment** (B6): mid-evaluation threshold
   changes require new spec version + fresh re-run?
3. **Pre-commit:** GATE 1 Q2 fail → archive palace immediately, no
   further discussion?
4. **Approve walker pattern** as in §1?

After approval, walker:
1. Creates epic in paperclip (e.g. `GIM-1085`)
2. Creates PHASE0-LIFECYCLE issue, assigns CXPE
3. Self-blocks on [PHASE0-LIFECYCLE]
4. Waits for completion
5. On done: creates next pair (S0 + F40), continues per timeline
