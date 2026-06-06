# GIM-765 Neo4j APOC Trigger Deployment Plan

## Goal

Install and verify APOC-backed `require_group_id` enforcement for the live Neo4j 5.26 stack, restoring Layer 2 protection for direct Cypher writes that bypass Python ingest paths.

## Assumptions

- `services/palace-mcp/src/palace_mcp/memory/constraints.py` is the canonical trigger bootstrap path.
- Neo4j 5 APOC trigger deployment should use `apoc.trigger.install/show` from the `system` database; `apoc.trigger.add` is legacy/deprecated.
- Existing dirty workspace changes may include partial GIM-765 work. Implementation must keep only changes required for this issue and must not revert unrelated files.
- The branch for implementation should be `feature/GIM-765-neo4j-apoc-trigger`.

## Acceptance Criteria

- `docker compose --profile review up -d neo4j palace-mcp` starts Neo4j with APOC loaded.
- `CALL apoc.version()` returns a version string.
- `CALL apoc.trigger.show('neo4j')` shows active `require_group_id`; if `apoc.trigger.list()` is available, it must show the same trigger.
- Raw `CREATE (:Function {cm_id: 'test-no-gid'})` fails with a missing `group_id` error.
- Raw `CREATE (:Function {cm_id: 'test-with-gid', group_id: 'project/test'})` succeeds.
- Raw `CREATE (:Bundle {cm_id: 'bundle-test'})` succeeds.
- `bash paperclips/scripts/ingest_swift_kit.sh bitcoin-core --skip-artefact-check` completes without extractor failures.
- `docs/runbooks/neo4j-apoc-trigger-deploy.md` documents plugin install, trigger deploy, manual verification, and redeploy after container recreate.

## Steps

1. Reconcile existing implementation state.
   - Owner: CXInfraEngineer.
   - Affected paths: `docker-compose.yml`, `services/palace-mcp/src/palace_mcp/memory/constraints.py`, `services/palace-mcp/tests/memory/test_constraints.py`.
   - Check: identify whether the current APOC env vars and trigger bootstrap are already correct for Neo4j 5.26.

2. Make the smallest required infra/code changes.
   - Owner: CXInfraEngineer.
   - Affected paths: only the paths required by Step 1, plus the runbook path below.
   - Check: unit/integration tests cover missing trigger install and direct-write enforcement.

3. Add operator runbook.
   - Owner: CXInfraEngineer.
   - Affected path: `docs/runbooks/neo4j-apoc-trigger-deploy.md`.
   - Check: runbook includes copy-paste-safe commands for APOC version, trigger show/list, negative write, positive write, exempt Bundle write, and redeploy.

4. Run focused verification.
   - Owner: CXInfraEngineer.
   - Check: capture output for `uv run pytest services/palace-mcp/tests/memory/test_constraints.py`, compose startup, APOC version, trigger show/list, three manual writes, and bitcoin-core ingest.

5. Open PR to `develop`.
   - Owner: CXInfraEngineer.
   - Check: PR body links this plan and includes a `## QA Evidence` block with the commands from Step 4.

6. Review pipeline.
   - Owner: CXCodeReviewer, then CodexArchitectReviewer, then CXQAEngineer, then CXCTO merge.
   - Check: mechanical review, adversarial review, live smoke, and merge gate all cite the same PR head commit.

## References

- Neo4j APOC trigger docs: `apoc.trigger.install` and `apoc.trigger.show` are the Neo4j 5 path for eventually installed triggers.
- GIM-759 showed Python bootstrap work was not enough while the live container lacked APOC.
