# Palace MCP Uplift - Walker Execution Plan v8

Spec: `docs/specs/palace-mcp-usability-uplift-v8.md`
Grounded at repo state: `origin/develop` / `5d9329f62b453e94bda2fca6431c7e0d7b2e5b8a`
(`GIM-1096: human-name resolution and result dedup`).

Supersedes: `docs/plans/palace-mcp-uplift-walker-plan-v6.md`.

Pattern: walker orchestrates issue creation and blocking only. CTO drafts
gate verdicts from evidence. Operator co-signs funding, archive, threshold,
and optional-investment decisions.

---

## 1. Walker Contract

```
loop:
  walker reads this roadmap and picks the next 1-2 slices
  if both teams are available and file sets do not overlap:
    post one Claude-track issue and one Codex-track issue
  else:
    post the single next slice
  walker self-blocks with blockedBy=[slice IDs]
  wait for slice-complete notifications
  when all blockers are complete, unblock and repeat
end
```

Rules:
- Max two simultaneous slices: one Claude-track and one Codex-track.
- Never create the whole epic up front.
- Re-verify file paths and line references against `origin/develop` at issue
  POST time.
- Do not run overlapping file edits in the same cycle unless the merge order
  is explicit.
- Walker records gate outcomes but does not draft verdicts.
- CTO drafts gate verdicts; operator co-signs.
- Walker never decides archive, P2.5, threshold changes, or spec amendments.

---

## 2. Real Repo File Map

| Functionality | Real location at `5d9329f6` |
| --- | --- |
| MCP tool registration | `services/palace-mcp/src/palace_mcp/mcp_server.py` |
| `run_extractor` MCP tool | `mcp_server.py:_palace_ingest_run_extractor()` |
| Extractor runner call site | `services/palace-mcp/src/palace_mcp/extractors/runner.py` |
| `CREATE_INGEST_RUN` Cypher | `services/palace-mcp/src/palace_mcp/extractors/cypher.py` |
| Checkpoint IngestRun writer | `services/palace-mcp/src/palace_mcp/extractors/foundation/checkpoint.py` |
| Schema/index declarations | `services/palace-mcp/src/palace_mcp/extractors/foundation/schema.py` |
| Swift SCIP extractor | `services/palace-mcp/src/palace_mcp/extractors/symbol_index_swift.py` |
| SCIP parser | `services/palace-mcp/src/palace_mcp/extractors/scip_parser.py` |
| Symbol writer | `services/palace-mcp/src/palace_mcp/extractors/foundation/symbol_node_writer.py` |
| Semantic search core | `services/palace-mcp/src/palace_mcp/code/find_semantic.py` |
| Snippet hydration/staleness | `services/palace-mcp/src/palace_mcp/code/snippet_provider.py` |
| Human-name resolver/search_graph composite | `services/palace-mcp/src/palace_mcp/code_composite.py` |
| FastAPI lifespan | `services/palace-mcp/src/palace_mcp/main.py` |
| Qodo backend | `services/palace-mcp/src/palace_mcp/embeddings/qodo.py` |

`code/find_references.py`, `code/search_graph.py`, and
`extractors/mcp_server.py` do not exist. Slice issues must not reference
those paths.

---

## 3. Slice Catalog

| Phase | Slice ID | Files touched | Effort | Owner | Depends on |
| --- | --- | --- | --- | --- | --- |
| 0 | PHASE0-INGESTRUN | `extractors/cypher.py`, `extractors/runner.py`, `extractors/foundation/checkpoint.py`, `extractors/foundation/schema.py`, migration `services/palace-mcp/migrations/2026-06-XX-ingest-run-normalize.cypher`, tests, repo-wide `IngestRun` old-key touch-point sweep | 1.0d | Codex | audit chain already merged |
| 1 | PALACE-F40 | new `palace_mcp/telemetry/`, `main.py`, `code/find_semantic.py`, `code_composite.py`, `mcp_server.py`, tests | 1.0d | Claude | none |
| 1 | PALACE-S0 | `scip_parser.py`, `symbol_node_writer.py`, `symbol_index_swift.py`, `mcp_server.py`, tests | 2.0d | Codex | PHASE0-INGESTRUN |
| 1 | PALACE-S1F2 | `scip_parser.py`, `symbol_node_writer.py`, `code_composite.py`, `mcp_server.py`, `services/palace-mcp/scripts/migrate_short_name.py`, tests | 2.0d | Codex | PALACE-S0 |
| 1 | PALACE-F41 | `main.py`, `embeddings/qodo.py`, tests | 0.5d | Claude | PALACE-F40 |
| 1 | PALACE-F43 | `code/find_semantic.py`, `code/snippet_provider.py`, `mcp_server.py`, tests | 0.5d | Claude | PALACE-F40 |
| 1 | PALACE-F44 | `code/find_semantic.py`, telemetry instrumentation, tool descriptions, harness precision diagnostic | 0.5d | Codex | PALACE-F40 |
| 1 | PALACE-F3 | `code/find_semantic.py`, `code_composite.py`, tests | 0.25d | Claude | PALACE-F40 |
| 1 | PALACE-GOLD | new `bench/gold/phase1-frozen-2026-06-XX/` | 0.5d | Codex | PALACE-S0 and current Phase 1 service SHA known |
| 1 | PALACE-DEPLOY | `services/palace-mcp/scripts/phase1-deploy.sh`, `docs/runbooks/palace-phase1-deploy.md`, provisioning notes | 0.5d | Codex | S0, S1F2, F40, F41, F43, F44, F3 |
| 1 | PALACE-Q1Q2-HARNESS | `bench/scripts/phase1-kill-gate.sh`, `bench/scripts/run-controlled-benchmark.py`, tests | 0.75d | Claude | PALACE-F40, PALACE-F44, PALACE-GOLD |
| Gate | PALACE-GATE1 | N>=50 benchmark run, metrics JSONL, verdict draft, co-sign | 0.5d ops | CTO + operator, walker records | all Phase 1 |
| 2 | PALACE-F1B-SPIKE | `services/palace-mcp/scripts/lsp-spike.py`, `bench/runs/lsp-spike-2026-06-XX/results.md` | 1.0d | Codex | GATE1 pass, dev-Mac available |
| 2 | PALACE-F1B-IMPL | new `palace_mcp/lsp/`, `mcp_server.py`, tests | 2.0d | Codex | F1B-SPIKE |
| 2 | PALACE-F1B-HARDEN | `palace_mcp/lsp/`, failure-mode docs, tests | 1-2d | Codex | F1B-IMPL |
| Gate | PALACE-GATE2 | Q3 benchmark and verdict | 0.5d ops | CTO + operator, walker records | all Phase 2 |
| 3 | PALACE-F5A | `embedding_symbol.py`, `code/snippet_provider.py`, `scripts/migrate_body_hash.py`, tests | 1.0d + overnight migration | Codex | GATE2 pass, S0 |
| 3 | PALACE-F5B | `services/palace-mcp/scripts/palace-periodic-reingest.sh`, `palace_mcp/ops/detect_stale_files.py`, launchd plist, `mcp_server.py`, tests | 1.0d | Codex | GATE2 pass, PHASE0-INGESTRUN |
| 3 | PALACE-F42 | `code/find_semantic.py`, `extractors/runner.py`, `mcp_server.py`, tests | 1.0d | Claude | GATE2 pass, F40 |
| Optional | PALACE-P25-IMAC-FIXTURE | `services/palace-mcp/fixtures/lsp-snapshots/`, `scripts/build-lsp-snapshot.sh`, LSP fallback wiring | 1-2d | Codex | operator request after GATE2 |

Total budget before optional P2.5: Phase 0 (1.0d) + Phase 1 (8.5d) +
Phase 2 (4-5d) + Phase 3 (3.0d conditional) = 16.5-17.5 dev-days.
With P2.5: 17.5-19.5 dev-days.

---

## 4. Track Allocation

| Phase | Claude effort | Codex effort | Total |
| --- | --- | --- | --- |
| Phase 0 | 0 | 1.0 | 1.0 |
| Phase 1 | 3.0 | 5.5 | 8.5 |
| Phase 2 | 0 | 4-5 | 4-5 |
| Phase 3 | 1.0 | 2.0 | 3.0 |
| Overall before optional P2.5 | 4.0 | 12.5-13.5 | 16.5-17.5 |

This is below the earlier 30/70 Claude/Codex target because Phase 2 is a
single LSP implementation track and should not be split for artificial
parallelism.

---

## 5. Cycle-by-Cycle Execution

### Cycle 0.1 - Phase 0

| Track | Slice | Effort | Overlap |
| --- | --- | --- | --- |
| Codex | PHASE0-INGESTRUN | 1.0d | solo |
| Claude | idle or unrelated backlog | n/a | no epic work |

Walker posts PHASE0-INGESTRUN to CXPythonEngineer and blocks on it.
No Phase 1 data-dependent slice starts until this lands.

### Cycle 1.1 - Foundation + Telemetry

| Track | Slice | Effort | Overlap |
| --- | --- | --- | --- |
| Codex | PALACE-S0 | 2.0d | `mcp_server.py` with F40 |
| Claude | PALACE-F40 | 1.0d | `mcp_server.py` with S0 |

Merge order: F40 first, then S0 rebases. Conflict risk is limited to tool
registration and descriptions in `mcp_server.py`; CodeReviewer must inspect
the combined tool list.

S0 must not change `BaseExtractor.run()` or generic `run_extractor`. The
anchor recount path is a Swift+SCIP-only `palace.ops.recount_anchors`
helper and must return structured unsupported/no-scip errors for other
projects.

### Cycle 1.2 - Resolver + Staleness

| Track | Slice | Effort | Overlap |
| --- | --- | --- | --- |
| Codex | PALACE-S1F2 | 2.0d | depends on S0 |
| Claude | PALACE-F41 -> PALACE-F43 | 1.0d total | sequential edits in `find_semantic.py` |

Claude-track slices are chained, not parallel with each other, because F43
touches semantic-search hot paths after F40 instrumentation. Hydration
parallelization is already present at the grounded SHA; F43 only adds the
stale-check opt-in and a non-regression assertion that hydration remains
parallel.

### Cycle 1.3a - Gold + Dedup

| Track | Slice | Effort | Overlap |
| --- | --- | --- | --- |
| Codex | PALACE-GOLD | 0.5d | new gold corpus dir |
| Claude | PALACE-F3 | 0.25d | after F43, touches `find_semantic.py` and `code_composite.py` |

GOLD must pin both `uw_ios_sha` and the Phase 1 `palace_mcp_sha`. If any
Phase 1 code PR lands after GOLD, walker must re-run GOLD or ask operator to
accept the stale pin explicitly.

### Cycle 1.3b - HNSW Budget

| Track | Slice | Effort | Overlap |
| --- | --- | --- | --- |
| Codex | PALACE-F44 | 0.5d | solo hot-path edit in `find_semantic.py` |
| Claude | idle or unrelated backlog | n/a | no epic work |

F44 is deliberately solo despite its small size. It changes candidate
budgeting and telemetry diagnostics in the same hot path touched by F43/F3.
Its baseline is the current Q1 path `query_k=200` at `limit=20`, not a
500-candidate baseline.

### Cycle 1.4 - Deploy + Harness

| Track | Slice | Effort | Overlap |
| --- | --- | --- | --- |
| Codex | PALACE-DEPLOY | 0.5d | scripts/docs/provisioning |
| Claude | PALACE-Q1Q2-HARNESS | 0.75d | benchmark scripts |

Both depend on F44, GOLD, and the final Phase 1 service SHA. Deploy must
run `palace.ops.recount_anchors` only for Swift projects with SCIP metadata;
non-Swift/no-SCIP projects are skipped with evidence.

### Gate 1

CTO drafts the verdict from:
- `bench/runs/phase1-gate-<date>/metrics.jsonl`
- Q1 recall, precision@20 diagnostic, p50, p95
- Q2 expected-reference recall and warm latency
- drift check against `bench/gold/phase1-frozen-2026-06-XX/`

Operator co-signs. Walker records the signed verdict and only then creates
Phase 2 issues.

Gate outcomes:
- Q1 pass and Q2 pass: proceed to Phase 2.
- Q2 fail: archive palace immediately.
- Q1 fail with Q2 pass: do not auto-continue. CTO/operator decide whether
  to amend spec and restart the gate or stop the epic.
- Harness bug only: one-day fix window, then fresh controlled rerun.
- Threshold change or carve-out: new spec version and fresh gate.

### Phase 2

Run sequentially:
1. PALACE-F1B-SPIKE: one real sourcekit-lsp workspace, memory budget
   evidence, no pool yet.
2. PALACE-F1B-IMPL: workspace pool, LRU, MCP tool.
3. PALACE-F1B-HARDEN: error envelopes, shutdown, iMac contract, tests.

Gate 2 uses Q3. CTO drafts, operator co-signs, walker records.

### Phase 3

Only after Gate 2 pass:
- Cycle 3.1: PALACE-F5A (Codex) in parallel with PALACE-F42 (Claude).
- Cycle 3.2: PALACE-F5B (Codex solo).
- Off-hours body-hash migration runs with checkpoint/resume and heartbeat
  progress. Walker should not assign another migration-heavy task during it.

### P2.5 Optional

Do not create this issue unless the operator explicitly approves it after
Gate 2. If approved, keep it single-track because fixture size and LSP
fallback behavior need one owner.

---

## 6. Timeline

```
day 0:   PHASE0-INGESTRUN
day 1:   PALACE-S0 + PALACE-F40
day 2:   F40 done, S0 continues
day 3:   S0 done; start PALACE-S1F2 + PALACE-F41/F43 chain
day 5:   S1F2 and staleness chain done
day 5.5: PALACE-GOLD + PALACE-F3
day 6:   PALACE-F44 solo
day 6.5: PALACE-DEPLOY + PALACE-Q1Q2-HARNESS
day 7.5: Gate 1 evidence run
day 8:   CTO verdict draft + operator co-sign
```

Phase 0 + Phase 1 wall time is about eight calendar days if agents stay
available and no gate rerun is needed.

---

## 7. Risk Controls

| Risk | Control |
| --- | --- |
| Spec/file drift during parallel PRs | Walker re-verifies paths and lines at issue POST time against `origin/develop`. |
| `mcp_server.py` merge conflicts | F40 merges before S0; later slices rebase before PR review. |
| GOLD pinned too early | GOLD must be refreshed if Phase 1 service code changes after the pin. |
| HNSW `query_k=2000` improves recall but hurts latency | F44 records query_k, in-scope ratio, precision@20, p50, and p95 before Gate 1. |
| Legacy `finished_at` NULL rows | Phase 0 keeps them NULL; F5B treats NULL as stale and forces re-ingest. |
| LSP spike exceeds memory budget | Spike caps sourcekit-lsp pool at one workspace and documents measured memory before F1B-IMPL. |
| Gate evidence exposes spec error | Harness bugs can be fixed once; threshold or scope changes require a new spec and fresh gate. |

---

## 8. Slice Issue Template

```markdown
# {SLICE-ID}: {short title}

## Spec
docs/specs/palace-mcp-usability-uplift-v8.md#{anchor}

## Scope
{what changes, what is out of scope}

## Files touched
- {file 1} - {what changes}
- {file 2} - {what changes}

## Acceptance
- {slice-specific test/evidence}
- `uv run ruff check`
- `uv run ruff format --check`
- targeted tests for touched code

## Dependencies
- {prior slice IDs}

## Coordination
- Parallel sibling: {sibling or none}
- File overlap: {none or list}
- Merge order: {required order or none}

## Reporter
walker (palace uplift epic)
```

---

## 9. Operator Decisions Before Launch

1. Approve Phase 0 + Phase 1 budget: 9.5 dev-days plus estimated
   Anthropic spend.
2. Decide whether P2.5 iMac fixture remains deferred by default or should
   be explicitly funded after Gate 2.

After approval, walker creates the epic, posts PHASE0-INGESTRUN, assigns
CXPythonEngineer, self-blocks on that issue, and continues by this plan.
