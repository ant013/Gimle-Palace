# MCP / Pipeline Integrity Audit — verify every extractor's data flow end-to-end

> **Issue:** GIM-332  
> **Author:** Board (operator)  
> **Grounded on:** `develop` @ `7caaba8` (2026-05-17)  
> **Status:** Active

## Context

GIM-307 TronKit project-analyze (SUCCEEDED_WITH_SKIPS, 15/15 fetched, 0 blind spots) produced a report where several extractors returned `0 findings` despite running on a real Swift library with 100+ files and published public API:

- `hotspot` — `scanned 0 files, found 0 issues`
- `dead_symbol_binary_surface` — `0 candidates`
- `public_api_surface` — `0 symbols`
- `cross_module_contract` — `0 deltas`
- `hot_path_profiler` — `0 entries`
- `dependency_surface` — found 9 deps but all `@unresolved` (no `Package.resolved` → no CVE / freshness audit)
- `arch_layer` — DAG-only (no rules file)

These are either valid empties (extractor ran, nothing to find) or **silent gaps** in the pipeline (extractor ran but didn't actually parse Swift / didn't read mounted repo / wrote nodes that audit can't see). The TronKit report itself does not distinguish the two.

Independently, the Paperclip board API token in `.env` was revoked server-side without notice (discovered 2026-05-17) and watchdog has been silently failing on 401 for hours — symptom of the same class of problem: **we don't validate that infrastructure tools actually work end-to-end**.

## Goal

For every one of the 24 production extractors (registry at `services/palace-mcp/src/palace_mcp/extractors/registry.py`), verify the full data path on a real reference project:

1. **Extractor run** writes `:IngestRun{source="extractor.<name>"}` row (verify Cypher count).
2. **Domain nodes/edges written** match what the runbook in `CLAUDE.md` promises (verify per-extractor canonical Cypher query returns rows).
3. **MCP read tools surface them** — `palace.code.*` / `palace.memory.*` returns the same data the extractor wrote (no shadow-table or scoping bug).
4. **`palace.audit.run` consumes them** — the audit report's section for that extractor shows real data, not `No findings` when data exists.
5. **`palace.memory.health` health-grouping** sees the extractor run (known limitation: only paperclip runs surfaced; verify gap or note as fixed).

### Full extractor list (24)

| # | Extractor | Category |
|---|-----------|----------|
| 1 | `heartbeat` | diagnostic |
| 2 | `symbol_index_python` | SCIP-backed |
| 3 | `symbol_index_typescript` | SCIP-backed |
| 4 | `symbol_index_java` | SCIP-backed |
| 5 | `symbol_index_solidity` | SCIP-backed |
| 6 | `symbol_index_swift` | SCIP-backed |
| 7 | `symbol_index_clang` | SCIP-backed |
| 8 | `dependency_surface` | repo-direct |
| 9 | `git_history` | repo-direct |
| 10 | `code_ownership` | derived (needs git_history) |
| 11 | `coding_convention` | repo-direct |
| 12 | `hotspot` | derived (needs git_history) |
| 13 | `hot_path_profiler` | artifact-backed |
| 14 | `reactive_dependency_tracer` | artifact-backed |
| 15 | `localization_accessibility` | repo-direct |
| 16 | `cross_repo_version_skew` | derived (needs dependency_surface) |
| 17 | `arch_layer` | config-backed |
| 18 | `error_handling_policy` | repo-direct |
| 19 | `crypto_domain_model` | repo-direct |
| 20 | `dead_symbol_binary_surface` | derived (needs symbol_index) |
| 21 | `public_api_surface` | derived (needs symbol_index) |
| 22 | `cross_module_contract` | derived (needs symbol_index) |
| 23 | `testability_di` | repo-direct |
| 24 | `codebase_memory_bridge` | integration |

## Scope and reference projects

Run audit on:
- **`gimle`** — the palace-mcp repo itself, Python-indexed and known-good.
- **`uw-ios-mini`** — committed Swift fixture with SCIP index.

Cross-check that suspicious zeros are consistent across both — if `public_api_surface` returns 0 on both gimle AND uw-ios-mini, that's almost certainly a bug.

## Deliverables

- **Coverage matrix** committed at `docs/runbooks/extractor-integrity-audit-2026-05-17.md` — table of 24 extractors × 5 stages × {OK, BROKEN, NOT_APPLICABLE} with evidence Cypher / MCP call output inline.
- **Bug-issues** for each broken stage (one per gap, child of GIM-332).
- **Watchdog token-validity check** — runbook section or new health probe that catches 401-on-token-revoke before agents silently die.

## Acceptance criteria

- [ ] Coverage matrix file lives in `docs/runbooks/extractor-integrity-audit-2026-05-17.md` on a feature branch and includes per-extractor evidence (Cypher rows + MCP tool output).
- [ ] Every `BROKEN` row has a corresponding child issue with reproducer.
- [ ] At minimum the 4 known-suspicious extractors from GIM-307 (`hotspot`, `dead_symbol_binary_surface`, `public_api_surface`, `cross_module_contract` on tron-kit) are explicitly verified as either valid-empty (with reasoning) or broken (with reproducer).
- [ ] Watchdog 401-on-token-revoke gap is either fixed or filed as a child issue with operator playbook.
- [ ] PR merged to `develop` with CI green + QA evidence including a re-run of `palace.audit.run` on the reference project showing matrix matches the report.

## Out of scope (followups)

- Re-test suspicious-zero extractors on TronKit specifically (separate diagnostic issue).
- BitcoinKit full audit rerun (blocked on this issue closing).
- Fixing extractor bugs found here that need real engineering effort — file as child issues.

## Pipeline

Canonical Gimle phase sequence: 1.1 → 1.2 → 2 → 3.1 → 3.2 → 4.1 → 4.2.
