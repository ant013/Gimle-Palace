# GIM-349 - symbol_index_swift counter recovery plan

**Status:** Phase 1.2 plan-first review approved; ready for implementation.
**Issue:** GIM-349 (`420e6f52-20bd-4ded-9839-fe129b56bce7`).
**Branch target:** `develop`.
**Primary owner after review:** CXPythonEngineer.

## Goal

Make symbol-index counter state self-recovering after a Neo4j/domain reset, so `ingest_swift_kit.sh <slug>` succeeds without an operator deleting `/var/lib/palace/tantivy/in_degree_counter.json`.

## Assumptions

- Option A is selected: corrupt or stale counter state is auto-detected and reset with a warning.
- `PALACE_COUNTER_RESET=1` remains supported as an explicit reset override and must actually remove or replace the persisted counter before reuse.
- The fix applies to all symbol index extractors that use the shared `in_degree_counter.json`, not only Swift.
- No admin MCP reset tool is in scope unless implementation proves self-heal cannot be made safe.
- Sequential-thinking MCP is not available in this runtime; decomposition below is based on issue context plus codebase-memory graph inspection.

## Codebase Findings

- `_load_or_reset_counter` is duplicated in `symbol_index_swift.py`, `symbol_index_python.py`, `symbol_index_typescript.py`, `symbol_index_java.py`, `symbol_index_solidity.py`, and `symbol_index_clang.py`.
- `BoundedInDegreeCounter.from_disk(path, expected_run_id)` returns `False` for missing, corrupt, wrong-version, bad-shape, bad-count, or stale-run-id state.
- Current caller behavior raises `COUNTER_STATE_CORRUPT` unless `PALACE_COUNTER_RESET=1`, then returns a fresh in-memory counter without explicitly deleting the bad persisted file.

## Scope

### In

- Counter load/reset behavior for symbol index extractors using `in_degree_counter.json`.
- Focused tests for corrupt JSON, stale `run_id`, and explicit `PALACE_COUNTER_RESET=1`.
- One extractor-level integration/regression path proving rerun after reset succeeds on first try.
- Runbook update for the new operator-visible behavior.
- Live `bitcoin-core` smoke evidence before merge.

### Out

- New MCP admin tool.
- Broad extractor refactors unrelated to counter recovery.
- Changes to Tantivy schema, Neo4j schema, or Swift SCIP emitter behavior.
- Manual production cleanup beyond verification setup.

## Acceptance Criteria

- Corrupt or stale counter state no longer hard-fails symbol indexing; the extractor logs a warning and starts from a fresh counter.
- `PALACE_COUNTER_RESET=1` removes or replaces the persisted counter state before load, so the documented escape hatch works deterministically.
- Unit tests cover corrupt JSON, stale run id, and explicit reset.
- Integration test simulates domain state reset/re-run and passes without deleting `in_degree_counter.json` externally.
- `docs/runbooks/symbol-index-swift-counter-recovery.md` documents the working recovery path.
- PR to `develop` includes CI evidence, code review approval, adversarial review, QA smoke, and `bitcoin-core` live success evidence.

## Phase Steps

| Step | Description | Acceptance Criteria | Suggested Owner | Affected Files / Paths | Dependencies |
|---|---|---|---|---|---|
| 1.1 | CTO formalizes scope and codebase findings. | This plan exists; issue body links it; no code files changed. | CXCTO | `docs/superpowers/plans/2026-05-18-GIM-349-symbol-index-swift-counter-recovery.md` | Issue assignment. |
| 1.2 | Plan-first review. | CXCodeReviewer approves Option A + reset override scope, owner routing, and verification gates. | CXCodeReviewer | This plan; issue thread. | Step 1.1. |
| 2.1 | Add failing tests for counter recovery. | Tests reproduce current failure for corrupt/stale persisted state and explicit reset before implementation. | CXPythonEngineer | `services/palace-mcp/tests/extractors/unit/test_importance.py`; symbol index unit tests as needed. | Step 1.2. |
| 2.2 | Implement minimal shared recovery behavior. | All six symbol index extractors use one recovery path or equivalent minimal shared helper; corrupt/stale state resets with warning; `PALACE_COUNTER_RESET=1` deletes/replaces persisted state before loading. | CXPythonEngineer | `services/palace-mcp/src/palace_mcp/extractors/foundation/importance.py` or a narrow foundation helper; `services/palace-mcp/src/palace_mcp/extractors/symbol_index_*.py` | Step 2.1. |
| 2.3 | Add extractor-level regression. | Test simulates first run with persisted counter, domain/run reset causing stale run id, then successful first retry without manual file deletion. | CXPythonEngineer | `services/palace-mcp/tests/extractors/integration/test_symbol_index_swift_integration.py` or shared symbol-index integration test. | Step 2.2. |
| 2.4 | Update runbook. | Runbook says normal path is self-heal; documents optional `PALACE_COUNTER_RESET=1`; removes any implication that host-side `rm` is required. | CXPythonEngineer | `docs/runbooks/symbol-index-swift-counter-recovery.md` | Step 2.2. |
| 3.1 | Mechanical review. | CXCodeReviewer verifies focused diff, tests, lint/typecheck evidence, PR body QA Evidence block, and no silent scope reduction. | CXCodeReviewer | PR diff. | Step 2.x PR opened. |
| 3.2 | Adversarial review. | CodexArchitectReviewer checks no silent data-loss regression beyond intended counter reset, no broad extractor behavior change, and no new operator-only recovery dependency. | CodexArchitectReviewer | PR diff and plan. | Step 3.1. |
| 4.1 | QA live smoke. | CXQAEngineer runs targeted tests plus `bitcoin-core` live smoke after simulated Neo4j/domain reset and posts command output evidence. | CXQAEngineer | Runtime environment; issue comment. | Step 3.2. |
| 4.2 | Merge gate. | CXCTO merges only with green CI, approved CR review, clean merge state, no conflict markers, valid plan reference, and QA evidence. | CXCTO | PR to `develop`; issue thread. | Step 4.1. |

## Review Decisions

- 2026-05-18 Phase 1.2: CXCodeReviewer approved Option A self-heal plus deterministic `PALACE_COUNTER_RESET=1` override. Implementation should stay narrow: one shared counter recovery path if it reduces duplicated edits, focused corrupt/stale/reset tests, runbook update, and live `bitcoin-core` smoke evidence.

## Verification Commands

Targeted development checks:

```bash
cd services/palace-mcp
uv run pytest tests/extractors/unit/test_importance.py
uv run pytest tests/extractors/unit/test_symbol_index_swift.py
uv run pytest tests/extractors/integration/test_symbol_index_swift_integration.py
```

Pre-review implementation gate:

```bash
cd services/palace-mcp
uv run ruff check src/palace_mcp/extractors tests/extractors
uv run mypy src
uv run pytest tests/extractors
```

Live smoke gate:

```bash
docker compose --profile review up -d --force-recreate palace-mcp
./scripts/ingest_swift_kit.sh bitcoin-core
```

QA must include evidence that a stale or corrupt `/var/lib/palace/tantivy/in_degree_counter.json` existed before the smoke, and that the extractor completed without host-side deletion.

## Risks

- Auto-reset loses prior in-degree counts. This is acceptable only when the persisted counter is corrupt or belongs to another run id; the log warning must make the reset visible.
- Duplicated `_load_or_reset_counter` implementations can drift. Prefer one narrow shared helper if it reduces changed lines and keeps extractor behavior identical.
- If `PALACE_COUNTER_RESET=1` is only read inside a long-lived process after startup, container-level env verification is not enough. Tests should exercise the same load path used by extractors.
