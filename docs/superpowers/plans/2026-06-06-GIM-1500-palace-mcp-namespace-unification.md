# GIM-1500 Plan: palace-mcp Project Namespace Unification

Grounded in `origin/develop` at `1b7611839e8aa44e0dda388f45e0667a6e5753fb` and spec PR [#388](https://github.com/ant013/Gimle-Palace/pull/388) at `bf7d6f89cfffb86be617c592d421bf0291831ccd`.

## Goal

Unify palace-mcp project namespace handling so passthrough `palace.code.*` tools accept registered Palace slugs and canonical codebase-memory names consistently, then ingest `uw-ios-baseline` once the resolver is deployed.

## Assumptions

- Spec PR #388 is authoritative for behavior until it is merged into `develop`.
- Implementation happens as separate PRs to `develop`, with no code changes on this planning PR.
- `palace.code.*` passthrough arguments may omit `project` or pass `project=None`; the wrapper must leave that unchanged and normalize only string `project` values and list-valued `projects`.
- The referenced `bench/ingest-fresh-replay.sh` is not present on `origin/develop`; infra prep is required unless the implementer finds an equivalent slug-aware ingest command accepted by the runbook.

## Resolved Spec Questions

| Question | Resolution |
|---|---|
| Q1 validator location | Move/export reusable `parent_mount` and `relative_path` validators from `palace_mcp.memory.project_tools` into a public location in `palace_mcp.memory.projects`, then import them from `project_tools`, `namespace.py`, and any touched tests. Do not duplicate regexes in `namespace.py`. |
| Q2 ingest script slug support | `bench/ingest-fresh-replay.sh` is absent on `origin/develop`; create a Phase 1.5 infra slice to locate or add a slug-aware ingest command before the operator gate. |
| Q3 current cm-name collisions | Treat as a migration pre-flight requirement. The migration must detect duplicate derivable `cm_project_name` values before any write; if live data collides, stop and escalate with exact colliding slugs. |
| Q4 `project=None` behavior | Preserve no-scope semantics. `_register_passthrough` skips normalization when `project is None`; it also skips missing `project` and normalizes only `str` values. |

## Acceptance Criteria

- AC-1: After Phase 3, `palace.code.search_code(project="uw-ios-baseline", pattern="HD")` returns at least one hit.
- AC-2: Automated mocked CM test proves `palace.code.semantic_search(query="rpc url validation", project="evm-kit")` sends the resolved CM project name and returns hits.
- AC-3: `palace.code.search_code(project="totally-bogus")` returns a structured `project_not_found` envelope without exception bubbling.
- AC-4: Native composite behavior remains unchanged; existing composite regression suites stay green.
- AC-5: One DEBUG structured `namespace.resolve` log is emitted per resolution with redacted CM name.
- AC-6: After Phase 3, `palace.memory.get_project_overview(slug="uw-ios-baseline").entity_counts` shows files and symbols.
- AC-7: New tests and existing relevant suites pass locally and in CI for each implementation PR.
- AC-8: `docs/runbooks/uw-ios-baseline-first-ingest.md` is committed and reviewed before operator ingest.
- AC-9: `:Project.cm_project_name` is populated for post-Phase-1 registrations and safely backfilled where derivable.
- AC-10: `register_project` invalidates namespace cache with no TTL lag.

## Work Plan

1. [ ] Phase 1 - Add canonical namespace resolver and schema field.
   - Owner: `CXPythonEngineer`.
   - Files: `services/palace-mcp/src/palace_mcp/code/namespace.py`, `services/palace-mcp/src/palace_mcp/memory/projects.py`, `services/palace-mcp/src/palace_mcp/memory/project_tools.py`, migration module under the existing palace-mcp migration path, focused tests under `services/palace-mcp/tests/code/` and `services/palace-mcp/tests/memory/`.
   - Acceptance: `assert_known_project`, slug and CM-name lookup, `SlugRegisteredButUnmapped`, `invalidate`, DEBUG redaction, `cm_project_name` write/backfill, collision pre-flight, and post-register cache invalidation are covered by tests.
   - Verification: from `services/palace-mcp`, run `uv run ruff check`, `uv run ruff format --check`, and targeted pytest for namespace, project registration, and migration tests.

2. [ ] Phase 1.5 - Make first-ingest command real.
   - Owner: `CXInfraEngineer`.
   - Files: `bench/` command path if needed, `docs/runbooks/uw-ios-baseline-first-ingest.md`.
   - Acceptance: the runbook names one slug-aware command for `uw-ios-baseline`, documents required env/port assumptions, and includes the two manual verification calls.
   - Verification: run the script help/dry-run or the narrow local command equivalent; if no dry-run exists, document why and show shell-level existence/argument validation.

3. [ ] Phase 2 - Wire passthrough and composite callers through the canonical resolver.
   - Owner: `CXPythonEngineer`.
   - Files: `services/palace-mcp/src/palace_mcp/code_router.py`, `services/palace-mcp/src/palace_mcp/code_composite.py`, affected tests in `services/palace-mcp/tests/`.
   - Acceptance: `_register_passthrough` normalizes string `project` and list `projects`, caps `projects` at 64, leaves `project=None` and missing `project` unchanged, does not rewrite `query_graph.query`, and removes old duplicate `_slug_to_cm_project` / `_cm_project_to_slug` helpers.
   - Verification: run `uv run ruff check`, `uv run ruff format --check`, targeted passthrough/composite tests, and `rg "_slug_to_cm_project|_cm_project_to_slug" services/palace-mcp/src` with no matches.

4. [ ] Phase 3 - Run first `uw-ios-baseline` ingest.
   - Owner: `Operator`.
   - Dependencies: Phase 1 and Phase 1.5 merged and deployed to the target MCP environment; Phase 2 merged if operator verifies passthrough behavior in the same session.
   - Acceptance: the baseline project has non-zero entities and `search_code(project="uw-ios-baseline", pattern="HD")` returns hits.
   - Verification: paste exact MCP calls and outputs for AC-1 and AC-6 into the Paperclip issue.

5. [ ] Phase 4 - Add smoke gate and final QA evidence.
   - Owner: `CXQAEngineer`.
   - Files: `services/palace-mcp/tests/integration/test_namespace_smoke.py`, `services/palace-mcp/pyproject.toml` marker registration if needed.
   - Acceptance: CI has a seed-fixture smoke that exercises slug-form passthrough without requiring live operator data, and QA evidence covers AC-1 through AC-10.
   - Verification: run the smoke test locally, then confirm PR checks `lint`, `typecheck`, `test`, `docker-build`, and `qa-evidence-present` are green before merge.

## Handoff Sequence

1. CXCTO sends this plan to `CXCodeReviewer` for plan-first review.
2. After approval, CXCTO creates child issues for Phase 1, Phase 1.5, Phase 2, Phase 3, and Phase 4 with `parentId=GIM-1500`; Phase 2 is blocked by Phase 1, Phase 3 is blocked by Phase 1.5 and the relevant implementation merges, and Phase 4 is blocked by implementation and operator evidence.
3. Each implementation slice opens its own PR to `develop`; no slice is merged without CodeReviewer approval, adversarial review, QA evidence, and green required checks.

## Risks

- Spec PR #388 is still open. If it changes, update this plan before creating implementation children.
- Live `:Project` rows may contain derivable `cm_project_name` collisions. The migration must fail before writes and surface exact rows to Board/operator.
- Operator ingest is a manual gate. If access or live MCP substrate is unavailable, mark the operator slice blocked rather than substituting mocked evidence.
