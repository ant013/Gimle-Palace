# GIM-1705 Plan: Batch dead_code DeadFinding Neo4j Writes

## Grounding

- Issue: GIM-1705, "Prerequisite: batch dead_code DeadFinding Neo4j writes"
- Parent issue: GIM-1702, P-DC2 prerequisite for dead_code incremental work
- Spec context: `docs/superpowers/specs/2026-06-20-incremental-update-orchestration.md`
- Integration base for this plan branch: `origin/develop` at `80df1e1ad0e30793b834df3de4001f3d811f354c`
- Code graph checked first: `write_dead_findings` currently calls `session.execute_write(_write_finding, ...)` once per finding, then runs `_evict_stale_findings`.

## Goal

Replace the per-finding Neo4j write transaction loop in `write_dead_findings` with a batched write path that preserves current `:DeadFinding` node, `:Symbol`, `:DEAD_SYMBOL`, summary, and stale-finding eviction semantics.

## Assumptions

- Scope is P-DC2 only. Do not implement P-DC1 access-modifier fixes, P-DC3 non-destructive incremental eviction, or the broader GIM-1702 incremental algorithm in this PR.
- Existing public API stays stable: `write_dead_findings(driver, findings, group_id) -> DeadFindingWriteSummary`.
- `created_at` values already live on the `DeadFinding` input model; batching must not add a new timestamp source.
- Empty `findings` still evicts all stale findings for the `group_id`, matching today's behavior.
- Member edge behavior must not expand scope. Preserve the current MERGE-only behavior; do not add member-edge deletion unless a test proves the current writer already required it.

## Acceptance Criteria

- `write_dead_findings` opens at most one write transaction for all finding/member upserts in a non-empty call, plus the existing stale-eviction transaction.
- The writer uses `UNWIND`-style batched Cypher over prepared rows instead of one `execute_write` call per finding.
- Existing full-output semantics stay stable: same finding ids, same stored node properties, same `members_json`, same `:Symbol` keys, same `:DEAD_SYMBOL` relationships, excluding timestamp fields already supplied by fixtures.
- Stale-finding eviction remains after successful batched upsert and still deletes findings absent from the latest full run.
- Tests fail on the current per-finding implementation and pass on the batched implementation.
- The PR or Paperclip implementation handoff leaves a concrete real-Neo4j verification path for Board runtime confirmation.

## Step 1: Add Batched-Behavior Tests

- Suggested owner: CXPythonEngineer
- Affected paths:
  - `services/palace-mcp/tests/extractors/unit/test_dead_code_neo4j_writer.py`
  - `services/palace-mcp/tests/extractors/integration/test_dead_code_neo4j_writer.py`

Work:
- Add a focused unit test with a fake async driver/session that calls `write_dead_findings` with at least two findings and asserts the writer does not call `execute_write` once per finding.
- Assert the non-empty write path has one batched upsert transaction and one stale-eviction transaction.
- Add or keep an empty-findings case proving eviction still runs with `kept_ids=[]`.
- Keep the existing real-Neo4j stale eviction integration test and extend it only if needed to assert properties/relationships remain stable after batching.

Acceptance:
- The new unit test fails against the current implementation because it observes per-finding write transactions.
- The existing integration stale-eviction test remains meaningful and is not replaced by a mocked happy path.

Verification:
- `cd services/palace-mcp && uv run pytest tests/extractors/unit/test_dead_code_neo4j_writer.py`
- `cd services/palace-mcp && uv run pytest tests/extractors/integration/test_dead_code_neo4j_writer.py`

## Step 2: Implement Batched Upserts

- Suggested owner: CXPythonEngineer
- Affected path:
  - `services/palace-mcp/src/palace_mcp/extractors/dead_code/neo4j_writer.py`
- Depends on: Step 1

Work:
- Extract finding property preparation from `_write_finding` into a small helper reusable by the batch path.
- Build two row lists: finding rows with `{finding_id, props}` and member rows with `{finding_id, qualified_name, group_id}`.
- Replace the per-finding loop with a single transaction helper such as `_write_findings_batch(tx, finding_rows, member_rows)`.
- Use `UNWIND $rows AS row` for finding node MERGEs and for member-symbol relationship MERGEs.
- Preserve `DeadFindingWriteSummary` counter aggregation from Neo4j result counters.
- For `findings=[]`, skip the batch upsert transaction and still run stale eviction.

Acceptance:
- `write_dead_findings` no longer loops over findings to call `session.execute_write`.
- `DeadFindingWriteSummary.nodes_created`, `relationships_created`, `properties_set`, and `nodes_deleted` continue to reflect consumed Neo4j counters.
- `group_id` is present on stored `:DeadFinding` props and `:Symbol` MERGE keys exactly as before.

Verification:
- `cd services/palace-mcp && uv run pytest tests/extractors/unit/test_dead_code_neo4j_writer.py tests/extractors/integration/test_dead_code_neo4j_writer.py`

## Step 3: Final Checks and Evidence

- Suggested owner: CXPythonEngineer
- Depends on: Step 2

Work:
- Run the local checks required for `services/palace-mcp`.
- In the implementation handoff, include exact command output and the branch/commit SHA.
- Include a Board-facing real-Neo4j verification note: run a representative full `dead_code` extraction before/after this PR against the production-sized graph and compare write duration, expected to drop from roughly 60 minutes to the few-minute range. The implementation PR does not need to mutate production data itself.

Acceptance:
- Local checks pass before pushing handoff commits.
- The handoff identifies the batched transaction count evidence and the real-Neo4j runtime confirmation path.

Verification:
- `cd services/palace-mcp && uv run ruff check`
- `cd services/palace-mcp && uv run ruff format --check`
- `cd services/palace-mcp && uv run mypy src/`
- `cd services/palace-mcp && uv run pytest tests/extractors/unit/test_dead_code_neo4j_writer.py tests/extractors/integration/test_dead_code_neo4j_writer.py`
- `cd services/palace-mcp && uv run pytest`

## Handoff Chain

1. CXCodeReviewer performs plan-first review of this plan.
2. On approval, hand off to CXPythonEngineer for implementation on `feature/GIM-1705-batch-dead-code-writes`.
3. Implementation returns to CXCodeReviewer for mechanical review, then CodexArchitectReviewer, then CXQAEngineer, then CXCTO merge.
