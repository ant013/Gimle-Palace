# BitcoinCore full project-analyze rerun (parity with GIM-307 TronKit)

> **Issue:** GIM-334
> **Author:** CTO (formalized from Board spec)
> **Grounded on:** `develop` @ `17196c0` (2026-05-17)
> **Status:** Active

## Context

GIM-307 ran `palace.audit.run(project="tron-kit", depth="full")` and produced a report with suspicious zero-finding extractors. GIM-332 (integrity audit) and GIM-333 (suspicious-zero diagnostic) identified and classified the root causes. Both are done.

Before trusting the audit pipeline as a deliverable, we need a second data point from a different real HS Swift Kit — **BitcoinCore.Swift** — to verify reproducibility and distinguish TronKit-specific findings from cross-project signal.

### Predecessor chain

| Task | Issue | Status | What it delivered |
|------|-------|--------|-------------------|
| Task 0 — Integrity audit | GIM-332 | done | 5-stage matrix, infra blockers IB-1..IB-4, child issues |
| Task 1 — Suspicious-zero diagnostic | GIM-333 | done | Root-cause per extractor, spawned GIM-335 + GIM-336 |
| Task 2 — BitcoinCore rerun | GIM-334 | **this issue** | Second data point + cross-kit diff |

### Open child bug-fixes from GIM-333

- **GIM-335** (`hotspot` template fix) — status: todo
- **GIM-336** (`dead_symbol_binary_surface` silent-success fix) — status: in_progress

These are NOT hard blockers for this task. Running BitcoinCore before the fixes land still produces valid cross-check data: if an extractor returns 0 on both kits, it confirms consistent brokenness. The diff report will note whether findings change if the fixes land later.

### Unfiled infra blockers from GIM-332

PR #205 body mentions IB-2 through IB-4, but only IB-1 (Neo4j healthcheck) was fixed. The remaining three were referenced with wrong issue numbers and **never filed**:

| Blocker | Description | Impact on GIM-334 |
|---------|-------------|-------------------|
| IB-2 | Docker VirtioFS stale cache for `/Users/Shared/` mounts | Could cause stale reads of BitcoinCore repo — **potential blocker** |
| IB-3 | OpenAI API quota exceeded (429 RateLimitError) | Affects `heartbeat` + `codebase_memory_bridge` only — **not in Swift Kit cascade**, no impact |
| IB-4 | Corrupted `:Project` node with `name=NULL` in Neo4j | Could interfere with `register_project` — **potential blocker** |

**Recommendation to operator:** file IB-2 and IB-4 as sibling issues before Step 2 begins. IB-3 is low priority for Swift Kit work.

## Goal

Run the full Swift Kit extractor pipeline against BitcoinCore.Swift, produce a fresh audit report, and diff against TronKit findings.

## Scope

### Target project

- **Slug:** `bitcoin-core`
- **Host path:** `/Users/Shared/Ios/HorizontalSystems/BitcoinCore.Swift`
- **Container mount:** `/repos-hs/BitcoinCore.Swift` (via existing `/repos-hs:ro` volume)
- **Parent mount:** `hs`
- **Relative path:** `BitcoinCore.Swift`

### Extractor cascade (17 DEFAULT_EXTRACTORS)

The `ingest_swift_kit.sh` script runs 17 extractors applicable to Swift Kits:

| # | Extractor | Category |
|---|-----------|----------|
| 1 | `symbol_index_swift` | SCIP-backed |
| 2 | `arch_layer` | config-backed |
| 3 | `git_history` | repo-direct |
| 4 | `code_ownership` | derived (needs git_history) |
| 5 | `coding_convention` | repo-direct |
| 6 | `crypto_domain_model` | repo-direct |
| 7 | `cross_module_contract` | derived (needs symbol_index) |
| 8 | `cross_repo_version_skew` | derived (needs dependency_surface) |
| 9 | `dead_symbol_binary_surface` | derived (needs symbol_index) |
| 10 | `dependency_surface` | repo-direct |
| 11 | `error_handling_policy` | repo-direct |
| 12 | `hot_path_profiler` | artifact-backed |
| 13 | `hotspot` | derived (needs git_history) |
| 14 | `localization_accessibility` | repo-direct |
| 15 | `public_api_surface` | derived (needs symbol_index) |
| 16 | `reactive_dependency_tracer` | artifact-backed |
| 17 | `testability_di` | repo-direct |

**Note:** the issue description says "22 production extractors" — the actual count for Swift Kits is **17** (full registry has 24, but 5 non-Swift `symbol_index_*` variants + `heartbeat` + `codebase_memory_bridge` are excluded from the Swift Kit cascade).

### SCIP dependency (Track B — operator)

SCIP emission requires Xcode toolchain on operator's dev Mac (iMac toolchain can't build modern iOS per `reference_imac_toolchain_limits`). Operator runs `bash paperclips/scripts/scip_emit_swift_kit.sh bitcoin-core` and provides the index path.

## Deliverables

1. **Audit report:** `docs/audit-reports/2026-05-17-bitcoin-core-rerun.md`
2. **Diff report:** `docs/runbooks/bitcoin-core-vs-tron-kit-diff-2026-05-XX.md`
3. **QA evidence comment** on GIM-334 with smoke namespace, AnalysisRun ID, RUN_FAILED count, blind-spots count

## Acceptance criteria

- [ ] BitcoinCore project registered + SCIP indexed + all 17 Swift Kit extractors run successfully
- [ ] `palace.audit.run` returns `ok=true` with blind spots matching TronKit baseline (public_api_surface + cross_module_contract) and 0 RUN_FAILED
- [ ] Diff report committed showing extractor parity vs TronKit
- [ ] Task 1 diagnostic verdicts cross-checked (if GIM-333 said `hotspot` is BROKEN, BitcoinCore should also return 0 — consistent — or non-zero — re-opens debugging)
- [ ] PR merged to develop with CI green + QA evidence

## Out of scope

- Fixing any BitcoinCore-specific extractor failures — file as child issues
- Expanding to other HS Swift Kits
- Addressing IB-2/IB-3/IB-4 infra blockers (separate issues)

## Pipeline

Canonical Gimle phase sequence: 1.1 → 1.2 → 2 → 3.1 → 3.2 → 4.1 → 4.2.
