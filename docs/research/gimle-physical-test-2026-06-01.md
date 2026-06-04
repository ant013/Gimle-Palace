# Gimle physical test — UW iOS dev questions, palace vs vanilla grep

Date: 2026-06-01.
Tester: Board (operator + Claude session).
Setup: native palace-mcp on localhost:8765 (380k+ embeddings, 9 projects),
called directly via curl over MCP/HTTP (bypassing Workflow subagent
context which had reachability gaps in prior benchmark).

---

## Test design

Pick 3 realistic dev questions an engineer working on UW iOS would
actually ask. Answer each TWICE in parallel:

- **Path A (palace)** — use `palace.code.*` MCP tools via direct HTTP
- **Path B (vanilla)** — use only `grep`/`find` in working tree

Measure wall-time, hits returned, and whether the answer is actionable.

---

## Results

### Q1 — "Add support for a new EVM chain (e.g. Base, chainId=8453) — what files need touching?"

| | palace | vanilla |
| --- | --- | --- |
| Tool | `palace.code.semantic_search` | `grep -rl` × 4 iterations |
| Wall-time | **35.7s** | **0.14s** |
| Files surfaced | 2 unique (with dupes for each method) | 10 candidates |
| Top hit | `EvmBlockchainManager.swift` ✓ | `EvmBlockchainManager.swift` ✓ (same) |
| Comprehensive? | No — missed `EvmSyncSourceManager`, `BtcBlockchainManager`, `AdapterFactory`, etc. | Yes — included those |

**Winner: vanilla** — 260× faster, 5× more candidate files.

### Q2 — "If I change `BalanceData` signature, what classes break?" (API impact)

| | palace | vanilla |
| --- | --- | --- |
| Tool | `palace.code.find_references` + `palace.code.search_graph` | `grep -rl BalanceData` |
| Wall-time | 717ms (2 calls) | **67ms** |
| References found | **0** | **31 files** |
| Reason for 0 hits | API requires SCIP-encoded `qualified_name` (e.g. `s%3A11Unstoppable11BalanceDataV`) — plain `"BalanceData"` doesn't match | n/a — substring match works |

**Winner: vanilla, outright.** Palace returned a useful-looking error
envelope but zero actual references — the call-graph traversal it's
supposed to enable doesn't trigger from a developer-friendly query.

### Q3 — "Trace call paths from `MoneroAdapter` (calls outbound)"

| | palace | vanilla |
| --- | --- | --- |
| Tool | `palace.code.trace_call_path` | `grep -rln "MoneroAdapter("` then `grep .send` etc. |
| Wall-time | 61ms (graph query) | 98ms (2 grep iterations) |
| Result | **empty graph `{}`** | `AdapterFactory.swift` + 5 caller files |
| Reason for empty | SCIP-derived graph in Neo4j has `:DEFINES`/`:USES` edges but **no `:CALLS` edges** for Swift — Swift extractor doesn't emit expression-level call occurrences | n/a — text match finds invocations |

**Winner: vanilla, outright.** This is the use case where palace was
expected to dominate — graph traversal you can't get with grep — and it
returns nothing.

---

## Verdict

On the codebase we care about (UW iOS) and the kind of tasks a real
developer (or Claude agent doing dev work) would ask, **palace currently
loses to vanilla `grep`/`find` on all three samples**.

Reasons, in priority order:

1. **No CALL edges in the graph** — `trace_call_path` returns empty for
   any Swift symbol. SCIP indexer only extracts symbol definitions and
   USE occurrences, not expression-level call edges. This breaks the
   single graph-only operation that was supposed to be palace's USP.
2. **find_references API requires SCIP-encoded qualified_name** —
   developers (or LLM agents acting like developers) call
   `find_references("BalanceData")`; palace responds with 0 hits because
   the actual identifier is `s%3A11Unstoppable11BalanceDataV`. There's no
   fuzzy/short-name fallback.
3. **Result deduplication is per-occurrence, not per-file** —
   `semantic_search` returns 8 hits but they collapse to 2 unique files.
   Operator has to do post-hoc dedup.
4. **Latency** — embed query + HNSW lookup + payload fetch takes 5-35
   seconds per call. `grep` is sub-second. For interactive use, palace
   feels broken.
5. **Stale index** — any file added after last `embedding_symbol` run is
   invisible. UW iOS app source changes daily; palace would need
   continuous re-ingest to keep up.

**Sample size: 3.** Other tasks may differ (semantic similarity on huge
codebases; cross-language traces; "find me code that does X conceptually"
where grep can't help). But for the tasks the operator typically runs
against UW iOS, the answer is: **palace currently delivers negative
value**.

---

## Remediation (5 features → spec → roadmap)

See `docs/specs/palace-mcp-usability-uplift-v1.md` for the full spec.
Tracked in paperclip as epic GIM-1079 with child issues GIM-1080..GIM-1084,
scheduled after the GIM-1063 audit-chain settles.

The 5 fixes:

1. **CALL edges in Swift graph** (the big one — restores graph USP)
2. **Friendly `find_references` API** — accept short names; resolve to qns
3. **Per-file dedup in semantic_search / search_graph results**
4. **Sub-second response latency** — pre-warm model + smaller embed model
   option + result cache
5. **Live re-index on file change** — fswatch + incremental SCIP delta

Without these 5, palace is paying for itself negatively on every call vs
`grep`.

---

## Cost of physical test

Three `curl` calls + half a dozen `grep` invocations + this writeup.
Marginal cost: ~$0 (no LLM agent invocations for the queries themselves
— operator + Claude session direct).

vs prior gimle-ab-benchmark sweep: ~$46. The physical test produced
clearer signal in 5 minutes of operator time than the structured
benchmark did in 50 minutes / $46. Lesson: **for binary "does it work?"
questions, hand-test 3 real cases — don't over-engineer the harness**.
