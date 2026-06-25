# Palace MCP Uplift — Walker Execution Plan

Spec: `docs/specs/palace-mcp-usability-uplift-v5.md`
Pattern: walker orchestrates, each chain sequential, two parallel teams
(Claude 30% / Codex 70% by effort).

---

## Walker контракт (one-liner повторяемый паттерн)

```
loop:
  walker берёт следующие 1-2 задачи из roadmap (одну для Claude, одну для Codex —
      если у обеих команд есть свободные слоты И задачи не пересекаются по файлам)
  → POST issue в paperclip с assignee=Team{Claude|Codex}
  → walker self-block: blockedBy=[слайс-N], status=blocked
  → ждёт notification что обе ушли в "done"
  → unblock → берёт следующие → повторяет
end
```

Walker **никогда не запускает >1 задачи на команду одновременно**
(операторское правило). Если у Claude task A in_progress — walker не
ставит ему task B пока A не закроется.

---

## Сводка по slice'ам (всего 13 slice'ов + 2 gate evaluation)

| Phase | # slices | Claude effort | Codex effort | Wall-time |
| --- | --- | --- | --- | --- |
| Phase 1 (foundation) | 8 | 2.0d (4 slices) | 4.5d (4 slices) | ~4-5 calendar days с parallel |
| GATE 1 | 1 | walker + operator | — | 1 day evaluation window |
| Phase 2 (call hierarchy) | 1 | — | 3-4d (1 slice) | ~4 days (serial; can't parallelize one slice) |
| GATE 2 | 1 | walker + operator | — | 1 day |
| Phase 3 (freshness, conditional) | 3 | 0.25d (1 slice) | 2.75d (2 slices) | ~3 days с parallel |
| P2.5 (iMac fixture, optional) | 1 | — | 1-2d | 2 days (post-P2 decision) |

**Total realistic calendar:** ~3 недели от старта Phase 1 до Phase 3 ship,
включая gate windows и operator review.

---

## Sprint A — Phase 1 (foundation)

Walker pairs 4 cycles: каждый цикл = 1 Claude slice + 1 Codex slice
параллельно, no file overlap.

### Cycle A.1 (день 1-2 wall)

| Track | Slice ID | Owner | Files touched | Effort | Depends on |
| --- | --- | --- | --- | --- | --- |
| **Codex** | **PALACE-S0** — source anchors + IngestRun index + ops.recount_anchors | CXPE | `extractors/scip_parser.py`, `extractors/foundation/symbol_node_writer.py`, `extractors/foundation/schema.py`, `code_composite.py` (ops tool), tests | **2.0d** | GIM-1063 merged |
| **Claude** | **PALACE-F4.0** — telemetry (histograms + counters + per-(tool,phase) keying) | PE | `main.py` (instrumentation hooks), new `palace_mcp/telemetry/__init__.py`, `mcp_server.py` (`palace.health.metrics` tool), tests | **0.75d** | — |

Walker workflow A.1:
1. POST PALACE-S0 → CXPE
2. POST PALACE-F4.0 → PE
3. Walker → `status=blocked`, `blockedBy=[S0, F4.0]`
4. Both notify `done` → walker unblocks → cycle A.2

**File overlap check:** PALACE-S0 not touching `main.py` / `telemetry/`;
PALACE-F4.0 not touching `extractors/` or `code_composite.py`. **No
overlap, safe parallel.**

### Cycle A.2 (день 2-3 wall)

| Track | Slice ID | Owner | Files | Effort | Depends on |
| --- | --- | --- | --- | --- | --- |
| **Codex** | **PALACE-S1F2** — human-name resolution + Python migration + rate-limit | CXPE | `extractors/scip_parser.py` (decoder), `extractors/foundation/symbol_node_writer.py` (short_name), `code/find_references.py` (resolver), new `scripts/migrate_short_name.py`, rate-limit in `mcp_server.py`, tests | **2.0d** | PALACE-S0 (uses anchors) |
| **Claude** | **PALACE-F4.1** — Qodo pre-warm + yield-on-fail + realistic warmup | PE | `main.py` (lifespan), `embeddings/qodo.py` (warmup helper), F4.0 instrument | **0.5d** | PALACE-F4.0 (uses counter) |

**Overlap:** Both touch `main.py` (S1F2 doesn't; F4.1 does). PALACE-S1F2
touches `symbol_node_writer.py` (S0 finished that). PALACE-F4.1 touches
`main.py` + `embeddings/qodo.py`. **No file overlap.**

### Cycle A.3 (день 3-4 wall)

| Track | Slice ID | Owner | Files | Effort | Depends on |
| --- | --- | --- | --- | --- | --- |
| **Codex** | **PALACE-OPS-BACKFILL** — ops.recount_coverage_cache tool + Phase 1 deploy backfill runbook | CXPE | `mcp_server.py` (recount_coverage tool), `scripts/migrate_short_name.py` (final), `scripts/phase1-deploy.sh`, `docs/runbooks/palace-phase1-deploy.md` | **0.5d** (combined: ops tool 0.25 + backfill scripts 0.25) | PALACE-S0, PALACE-S1F2 |
| **Claude** | **PALACE-F4.3** — git stale-check opt-in hoist + TTL doc | PE | `code/find_semantic.py` (hot path), `code/snippet_provider.py` (_check_stale), `mcp_server.py` (tool description), tests | **0.5d** | PALACE-F4.0 |

**Overlap:** No. Backfill is scripts/docs; F4.3 is find_semantic /
snippet_provider.

### Cycle A.4 (день 4-5 wall)

| Track | Slice ID | Owner | Files | Effort | Depends on |
| --- | --- | --- | --- | --- | --- |
| **Codex** | **PALACE-F3** — dedup_by_file=False flag | CXPE | `code/find_semantic.py` (param + group logic), `code/search_graph.py`, tests | **0.25d** | PALACE-F4.0 (uses counter) |
| **Claude** | **PALACE-Q1Q2-HARNESS** — controlled benchmark harness for kill-gate | PE | new `bench/scripts/phase1-kill-gate.sh`, `bench/scripts/run-controlled-benchmark.py`, `bench/runs/phase1-gate-template/`, integration tests | **0.5d** | PALACE-F4.0 (reads metrics) |

**Overlap:** F3 in find_semantic; harness in bench/. **No overlap.**

---

## GATE 1 (день 5-6 wall — 1-day adjustment window per C8)

Walker single-issue **PALACE-GATE1-EVAL**:
- Run `bench/scripts/phase1-kill-gate.sh` against deployed Phase 1
- N≥50 controlled Q1 + Q2 queries on warm process
- Read F4.0 metrics, compute p50/p95 per (tool, phase)
- Apply v5 gate criteria:
  - Q2 recall ≥30/31 + latency p50<1s → must pass else **archive palace**
  - Q1 recall ≥80% at limit=20 + p50<8s warm + p95<15s warm → fund Phase 2
  - Q2 pass + Q1 fail → fund Phase 2 anyway (default committed v5/C5)
- Write `bench/runs/phase1-gate-YYYY-MM-DD/verdict.md`
- Operator + CTO co-sign verdict

Walker → blocks on GATE1-EVAL. Outcome determines next branch:
- **Archive path:** walker creates PALACE-ARCHIVE issue, post-mortem doc;
  exits.
- **Continue path:** walker proceeds to Sprint B.

---

## Sprint B — Phase 2 (call hierarchy)

### Cycle B.1 (день 7-10 wall)

Phase 2 = single slice (can't parallelize 1 LSP-proxy implementation):

| Track | Slice ID | Owner | Files | Effort | Depends on |
| --- | --- | --- | --- | --- | --- |
| **Codex** | **PALACE-F1B** — sourcekit-lsp proxy MCP tool | CXPE | new `palace_mcp/lsp/__init__.py`, `palace_mcp/lsp/sourcekit_client.py`, `palace_mcp/lsp/workspace_pool.py` (LRU max 3), new `palace.code.call_hierarchy` MCP tool in `mcp_server.py`, didOpen sequencing, integration test using uw-ios-app fixture | **3-4d** | GATE 1 passed + S1 (uses short_name index) |
| **Claude** | **PALACE-P2-EVAL-PREP** — prepare phase 2 kill-gate harness (Q3 callers list, expected ≥3) + telemetry analysis from Phase 1 results | PE | `bench/scripts/phase2-kill-gate.sh`, `bench/gold/T3-callers-ground-truth.json` (grep MoneroAdapter.send callers), F4.0 query helpers | **0.5d** | GATE 1 passed |

**Overlap:** F1B in `lsp/` + `mcp_server.py` (new tool); P2-EVAL-PREP in
`bench/`. **No file overlap.**

---

## GATE 2 (день 11-12 wall — 1-day window)

Walker single-issue **PALACE-GATE2-EVAL**:
- `bench/scripts/phase2-kill-gate.sh` on dev-Mac with built workspace
- Q3 (`call_hierarchy MoneroAdapter.send incoming depth=3`) → ≥3 callers
  including grep ground-truth, p50<5s warm
- Verdict in `bench/runs/phase2-gate-YYYY-MM-DD/verdict.md`
- Outcomes:
  - Pass → fund Phase 3
  - Fail → ship as-is (P1+P2), Phase 3 deferred indefinitely

---

## Sprint C — Phase 3 (freshness, conditional)

Only runs if GATE 2 passes.

### Cycle C.1 (день 13-14 wall)

| Track | Slice ID | Owner | Files | Effort | Depends on |
| --- | --- | --- | --- | --- | --- |
| **Codex** | **PALACE-F5A** — body_hash + commit_sha guard + migration script | CXPE | `extractors/embedding_symbol.py` (extend `_embedding_text` with body), `code/snippet_provider.py` (commit_sha guard for hydration), new `scripts/migrate_body_hash.py` (checkpoint/resume), tests | **1d** | PALACE-S0 (anchors), GATE 2 pass |
| **Claude** | **PALACE-F4.2** — coverage cache + atomic invalidation + global Neo4j semaphore | PE | `code/find_semantic.py` (read cache), `extractors/runner.py` (semaphore + finalize cache write), `mcp_server.py` (`palace.ops.recount_coverage` already exists from A.3, wire), tests | **1d** | PALACE-F4.0, PALACE-OPS-BACKFILL |

**Overlap:** F5A in `embedding_symbol.py` + `snippet_provider.py`;
F4.2 in `find_semantic.py` + `runner.py`. **No overlap.**

### Cycle C.2 (день 14-15 wall)

| Track | Slice ID | Owner | Files | Effort | Depends on |
| --- | --- | --- | --- | --- | --- |
| **Codex** | **PALACE-F5B** — mtime vs IngestRun periodic re-ingest + ignore list + launchd | CXPE | new `services/palace-mcp/scripts/palace-periodic-reingest.sh`, plist for launchd, `palace.ops.detect_stale_files` tool, per-project flock helper, tests | **1d** | PALACE-S0 (uses IngestRun index) |
| **Claude** | _(no parallel slice — wait for F5B)_ | — | — | — | — |

**Note:** Cycle C.2 has only one slice. Claude track idle this cycle —
walker takes opportunity to assign Claude something low-priority from
backlog (e.g. PR-review pass, docs cleanup) OR leaves Claude idle if no
unrelated work.

### Migration runs (день 15-22 wall — 7-day overnight)

- `migrate_body_hash.py` run during off-hours — ~8h on MPS
- Checkpoint/resume safe
- Walker monitors via heartbeat, no new tasks assigned

---

## Sprint D — P2.5 OPTIONAL (post-P2, only on operator request)

### Cycle D.1 (день 23-25 wall, only if approved)

| Track | Slice ID | Owner | Files | Effort | Depends on |
| --- | --- | --- | --- | --- | --- |
| **Codex** | **PALACE-P25-IMAC-FIXTURE** — index-store snapshot for top-3 projects (UW/EvmKit/BitcoinCore) | CXPE | new `services/palace-mcp/fixtures/lsp-snapshots/` (300MB committed via LFS), `scripts/build-lsp-snapshot.sh`, docker compose mount, iMac fallback path in `palace_mcp/lsp/sourcekit_client.py`, `data_freshness_warning` envelope, tests | **1-2d** | F1B + GATE 2 pass |

---

## Walker state machine — full Phase 1 timeline

```
day 0:  walker takes PALACE-S0 + PALACE-F4.0 → POST to CXPE, PE
        walker self-block on [S0, F4.0]
day 1:  PE finishes F4.0; CXPE still working S0
        walker still blocked on S0 (rule: don't unblock partially)
day 2:  CXPE finishes S0
        walker unblocks → cycle A.2
        walker takes PALACE-S1F2 + PALACE-F4.1 → POST to CXPE, PE
        walker self-block on [S1F2, F4.1]
day 3:  PE finishes F4.1; CXPE still on S1F2
day 4:  CXPE finishes S1F2
        walker unblocks → cycle A.3
        walker takes PALACE-OPS-BACKFILL + PALACE-F4.3 → POST
day 4.5:Both finish (each 0.5d)
        walker → cycle A.4
        walker takes PALACE-F3 + PALACE-Q1Q2-HARNESS → POST
day 5:  Both finish (each 0.25-0.5d)
        walker → GATE 1
        walker takes PALACE-GATE1-EVAL → assigns to itself or QA
day 5-6: GATE 1 evaluation + 1-day adjustment window
day 6:  Verdict: continue (or archive — exits)
        walker → Sprint B
day 7:  walker takes PALACE-F1B + PALACE-P2-EVAL-PREP
day 7-10: CXPE on F1B (3-4d); PE finishes P2-EVAL-PREP on day 7
day 11: F1B done → walker → GATE 2
day 11-12: GATE 2 + 1-day window
day 12: Verdict: continue (or ship-as-is)
day 13: walker → Cycle C.1 (F5A + F4.2 parallel)
day 14: both done → Cycle C.2
day 14-15: F5B (Codex only; Claude idle or unrelated work)
day 15: F5B done → walker triggers off-hours `migrate_body_hash.py`
day 15-22: Migration runs overnight; walker pings progress every 2h
day 22: Phase 3 ships
day 22+: walker awaits operator decision on P2.5
```

---

## Risk mitigations baked into the plan

1. **Operator catches v5 spec error mid-execution** → § Gate adjustment
   protocol allows mid-Phase edits to next gate criteria; doesn't allow
   moving criteria of in-flight gate.
2. **CXPE blocked on file someone else has** → walker enforces no file
   overlap at slice issue creation; CR review must verify same.
3. **PE/Claude session loses context mid-slice** → all slice issues
   carry `spec_ref=docs/specs/palace-mcp-usability-uplift-v5.md#<anchor>`
   so fresh agent can re-pick up.
4. **Walker itself gets stuck (claude proc idle hang per memory
   `reference_claude_process_idle_hang.md`)** → operator pings walker
   directly; walker can self-rescue via `paperclipai heartbeat run`
   on iMac per `reference_gimle_no_autowake.md`.
5. **Phase 1 gate evidence weaker than expected** → C8 1-day window
   allows revising Q1 SLO upward (e.g. p50<10s instead of <8s) if
   F4.0 telemetry shows MPS variance higher than estimated.

---

## What walker does NOT decide autonomously

- Phase 1 → Phase 2 funding (operator + CTO co-sign GATE 1 verdict)
- Phase 2 → Phase 3 funding (operator + CTO co-sign GATE 2 verdict)
- P2.5 iMac fixture investment (explicit operator decision)
- Archive triggering (operator + CTO co-sign)
- Spec amendments mid-flight (operator request only)

Walker is execution coordinator, not decision-maker. All branches
require explicit operator green light.

---

## Slice issue template (walker uses this when creating each)

```markdown
# {SLICE-ID}: {short title}

## Spec reference
`docs/specs/palace-mcp-usability-uplift-v5.md#<section-anchor>`

## Scope
{1-paragraph: what changes, what files}

## Files touched
- {file 1} — {what changes}
- {file 2} — ...

## Effort
{N.N} dev-days

## Acceptance
- {acceptance test 1}
- {acceptance test 2}
- All existing tests pass
- Lint + typecheck pass

## Dependencies (blocked by)
- {prior slice IDs}

## Coordination
- Parallel slice this cycle: {sibling slice ID} — files {list};
  CR verify no overlap before merge
- Walker self-block: [<this slice ID>, <sibling slice ID>]

## Reporter
walker (auto-generated as part of palace uplift epic)
```

---

## Open questions for operator before walker starts

1. Approve Phase 1 budget (6.5 dev-days + ~$2-3k LLM spend)?
2. Approve walker pattern as described (1 slice per team per cycle,
   no overlap, walker self-blocks on pair)?
3. Confirm gate verdicts require operator + CTO co-sign (not walker
   auto-decide)?
4. Pre-commit to default: GATE 1 Q2 fail → archive palace, no further
   discussion?

After approval, walker creates paperclip epic + cycle A.1 issues
(PALACE-S0 + PALACE-F4.0) and posts. No mass-creation of all 13
slices upfront — walker creates the next pair only after the prior
pair finishes (per operator's "не all-at-once" rule).
