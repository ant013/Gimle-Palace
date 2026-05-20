# GIM-357 - symbol_index_swift Tantivy lock self-heal plan

**Status:** Phase 1.1 formalized; awaiting plan-first review.
**Issue:** GIM-357 (`c71fd1b5-ba33-41ee-ad7c-bde579839654`).
**Branch target:** `develop`.
**Primary owner after review:** CXPythonEngineer.

## Goal

Extend the GIM-349 counter self-heal path so a stale Tantivy writer lock left by a crashed prior run does not make `symbol_index_swift` fail with `LockBusy` after counter recovery.

## Assumptions

- The fix stays in the symbol-index counter recovery path; no broad extractor lifecycle redesign is in scope.
- Implementation must first prove the actual Tantivy lock artifact used by the installed Python/Tantivy stack. Do not delete `.tantivy-meta.json` unless tests prove it is the stale lock artifact and not required index metadata.
- Only stale locks may be removed. A live writer lock must fail clearly and leave the lock untouched.
- `PALACE_COUNTER_RESET=1` should use the same stale-lock cleanup behavior before returning a fresh counter.
- Sequential-thinking MCP is not available in this runtime; decomposition below is based on issue context plus codebase-memory graph inspection.

## Codebase Findings

- `symbol_index_swift._load_or_reset_counter(tantivy_path, run_id)` delegates to `foundation.importance.load_or_reset_in_degree_counter`.
- `load_or_reset_in_degree_counter` currently self-heals stale or corrupt `in_degree_counter.json` by deleting only that file and returning a fresh `BoundedInDegreeCounter`.
- GIM-349 already added unit coverage for corrupt counter files, stale run ids, and explicit `PALACE_COUNTER_RESET=1`.
- The observed failure happens after the counter self-heal: opening a Tantivy `IndexWriter` reports `Failed to acquire Lockfile: LockBusy`.

## Scope

### In

- Identify the real Tantivy writer-lock file/path for the installed runtime.
- Add stale-lock cleanup in the shared counter recovery path when counter reset/self-heal is triggered.
- Unit tests for stale lock cleanup and live lock preservation.
- Focused symbol-index Swift regression proving counter self-heal proceeds to index write when only a stale lock remains.
- Live `bitcoin-core` smoke after Neo4j/domain reset showing non-empty symbol output.

### Out

- Deleting Tantivy metadata or index files unrelated to the writer lock.
- Clearing locks when no counter reset/self-heal is happening.
- New operator-only cleanup scripts or MCP tools.
- Changes to SCIP emitters, Neo4j schema, Tantivy schema, or unrelated extractors.

## Acceptance Criteria

- `symbol_index_swift` completes successfully on the BitcoinCore reference after Neo4j volume reset.
- Unit test simulates a stale Tantivy writer lock from a crashed prior run; extractor/counter recovery removes only the stale lock and proceeds.
- Unit test simulates a genuinely live writer lock; recovery returns a clear error and does not delete the lock.
- Live `bitcoin-core` smoke proves real symbol data is written, not an empty success.
- No data loss in the Tantivy index from lock cleanup logic.
- PR to `develop` has green CI, CXCodeReviewer approval, adversarial review, QA evidence, and this plan referenced in the PR body.

## Phase Steps

| Step | Description | Acceptance Criteria | Suggested Owner | Affected Files / Paths | Dependencies |
|---|---|---|---|---|---|
| 1.1 | CTO formalizes scope and guardrails. | This plan exists; issue links it; no code files changed. | CXCTO | `docs/superpowers/plans/2026-05-19-GIM-357-symbol-index-swift-tantivy-lock-self-heal.md` | Issue assignment. |
| 1.2 | Plan-first review. | CXCodeReviewer approves the narrow cleanup point, lock-safety guardrails, owner routing, and verification gates before implementation. | CXCodeReviewer | This plan; issue thread. | Step 1.1. |
| 2.1 | Identify lock artifact and add failing tests. | Tests prove the lock filename/path used by the runtime, stale-lock cleanup fails before implementation, and live-lock preservation fails before implementation. | CXPythonEngineer | `services/palace-mcp/tests/extractors/unit/test_importance.py`; optional narrow Tantivy fixture test. | Step 1.2. |
| 2.2 | Implement minimal stale-lock cleanup. | `load_or_reset_in_degree_counter` clears only proven stale Tantivy writer locks when counter reset/self-heal is triggered; live locks raise a clear `LockBusy`-style error and remain untouched. | CXPythonEngineer | `services/palace-mcp/src/palace_mcp/extractors/foundation/importance.py`; narrow helper only if needed. | Step 2.1. |
| 2.3 | Add symbol-index Swift regression. | Regression simulates corrupt/stale counter plus stale Tantivy lock and verifies the Swift path reaches an index write without host-side deletion. | CXPythonEngineer | `services/palace-mcp/tests/extractors/unit/test_symbol_index_swift.py` or closest existing symbol-index Swift test. | Step 2.2. |
| 2.4 | Open PR to `develop`. | PR body links this plan and includes targeted test output plus a `## QA Evidence` placeholder. | CXPythonEngineer | GitHub PR. | Step 2.3. |
| 3.1 | Mechanical review. | CXCodeReviewer verifies diff scope, tests, lint/typecheck evidence, PR checks, plan criteria coverage, and no silent scope reduction. | CXCodeReviewer | PR diff; issue thread. | Step 2.4. |
| 3.2 | Adversarial review. | CodexArchitectReviewer verifies the cleanup cannot delete active locks or index metadata, and cannot mask concurrent writer bugs. | CodexArchitectReviewer | PR diff and plan. | Step 3.1. |
| 4.1 | QA live smoke. | CXQAEngineer runs `bitcoin-core` after reset and posts concrete output: `symbol_index_swift` success, non-zero symbol writes, and no manual lock deletion. | CXQAEngineer | Runtime environment; issue comment. | Step 3.2. |
| 4.2 | Merge gate. | CXCTO merges only with green CI, approved CR review, clean merge state, no conflict markers, valid plan reference, and QA evidence. | CXCTO | PR to `develop`; issue thread. | Step 4.1. |

## Verification Commands

Targeted development checks:

```bash
cd services/palace-mcp
uv run pytest tests/extractors/unit/test_importance.py
uv run pytest tests/extractors/unit/test_symbol_index_swift.py
```

Pre-review implementation gate:

```bash
cd services/palace-mcp
uv run ruff check src/palace_mcp/extractors/foundation tests/extractors/unit/test_importance.py tests/extractors/unit/test_symbol_index_swift.py
uv run mypy src
uv run pytest tests/extractors/unit/test_importance.py tests/extractors/unit/test_symbol_index_swift.py
```

Live smoke gate:

```bash
docker compose --profile review up -d --force-recreate palace-mcp
./scripts/ingest_swift_kit.sh bitcoin-core
```

QA evidence must include the failing-before/fixed-after `LockBusy` condition, the exact lock artifact found, and a non-zero symbol write/query sample from `bitcoin-core`.

## Risks

- Deleting `.tantivy-meta.json` by name guess could corrupt or discard index metadata. The implementation must derive the lock artifact from runtime behavior/tests before cleanup.
- Stale-lock heuristics can be wrong. Prefer a conservative dead-PID or older-than-current-run marker; if liveness cannot be proven, leave the lock and fail clearly.
- Clearing locks outside counter recovery could hide real concurrent writers. Keep cleanup gated to counter reset/self-heal only.
