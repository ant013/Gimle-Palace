---
slug: dead-symbol-binary-surface
issue: GIM-193
spec: docs/superpowers/specs/2026-05-04-roadmap-33-dead-symbol-binary-surface.md
date: 2026-05-04
branch: feature/roadmap-33-dead-symbol-binary-surface
---

# Roadmap #33 - Dead Symbol & Binary Surface Extractor - Implementation Plan

Docs-only Phase 1.1 plan for `dead_symbol_binary_surface`. Do not implement
extractor code until this spec/plan is reviewed and a Paperclip issue is
assigned.

## Phase Chain

| Phase | Owner | Output |
|---|---|---|
| 1.1 Formalization | CTO / operator | This spec + plan branch |
| 1.2 Plan review | CXCodeReviewer | Approve/request changes before Gate 0 |
| 1.3 Tool Output Gate | CXPythonEngineer -> CXCodeReviewer | Periphery fixture contract captured, pushed, and explicitly signed off before implementation |
| 2 Implementation | CXPythonEngineer | TDD implementation on a real GIM branch after Gate 0 sign-off |
| 3.1 Mechanical review | CXCodeReviewer | Correctness, scope, tests |
| 3.2 Architecture review | CodexArchitectReviewer | False-positive model and graph semantics |
| 4.1 QA smoke | CXQAEngineer | Docker/review-profile evidence |
| 5 Merge | Operator / allowed merger | Merge after QA evidence and branch checks |

## File Structure

| Area | Files | Status |
|---|---|---|
| Extractor package | `extractors/dead_symbol_binary_surface/` | NEW |
| Models | `extractors/dead_symbol_binary_surface/models.py` | NEW |
| Periphery parser | `extractors/dead_symbol_binary_surface/parsers/periphery.py` | NEW |
| Reaper skip model | `extractors/dead_symbol_binary_surface/parsers/reaper.py` | NEW no-op skip |
| Correlation | `extractors/dead_symbol_binary_surface/correlation.py` | NEW |
| Neo4j writer | `extractors/dead_symbol_binary_surface/neo4j_writer.py` | NEW |
| Extractor entry | `extractors/dead_symbol_binary_surface/extractor.py` | NEW |
| ID helper | `extractors/dead_symbol_binary_surface/identifiers.py` or foundation helper | NEW |
| Schema | `extractors/foundation/schema.py` | EXTEND |
| Registry | `extractors/registry.py` | EXTEND |
| Fixtures | `tests/extractors/fixtures/dead-symbol-binary-surface-mini-project/` | NEW |
| Unit tests | `tests/extractors/unit/test_dead_symbol_binary_surface*.py` | NEW |
| Integration test | `tests/extractors/integration/test_dead_symbol_binary_surface_integration.py` | NEW |
| Runbook | `docs/runbooks/dead-symbol-binary-surface.md` | NEW |

No public MCP/router/API files are in v1 scope.

## Blocking Gate 0 - Tool Output Spike And Reviewer Sign-Off

### Goal

Freeze the exact input shape before writing parser code. This is a hard
precondition for Phase 2, not an implementation task that can run in parallel.

### Owner And Handoff

- Suggested owner: CXPythonEngineer, because the work creates fixture artifacts
  and validates parser-input shape before extractor implementation.
- Reviewer/sign-off owner: CXCodeReviewer.
- Status transition: after Phase 1.2 plan approval, assign Gate 0 to
  CXPythonEngineer. When the fixture contract is pushed, CXPythonEngineer must
  PATCH `status=in_review`, `assigneeAgentId=CXCodeReviewer`, and include a
  formal mention for fixture-schema sign-off. CXCodeReviewer either requests
  changes on the fixture contract or signs off and reassigns Phase 2
  implementation to CXPythonEngineer.
- Phase 2 must not begin from this plan, a child issue, or a direct assignment
  until the CXCodeReviewer Gate 0 sign-off comment exists.

### Affected Files

- `docs/research/2026-05-04-dead-symbol-tool-output-spike/README.md`
- `services/palace-mcp/tests/extractors/fixtures/dead-symbol-binary-surface-mini-project/`
- This spec/plan only if the captured fixture invalidates parser assumptions.

### Dependencies

- Depends on Phase 1.2 plan approval.
- Blocks every Phase 2 implementation task below.
- Must not depend on Reaper, CodeQL, Android alternatives, or production
  Xcode/Gradle project edits.

### Work

- Generate or commit a small Periphery output fixture for the Swift mini project.
- Record `tool_name`, `tool_version`, `output_format`, and
  `tool_output_schema_version` in the fixture.
- Add parser contract notes for unknown-key handling.
- Document that Reaper has no public offline report-file contract for v1; parser
  behavior is no-op skip only.
- Optionally spike Android alternatives (`bye-bye-dead-code`, Detekt custom
  rules, or another R8/file-output tool). Selecting one requires spec revision.

### Acceptance

- `docs/research/2026-05-04-dead-symbol-tool-output-spike/README.md` exists.
- Fixture files exist under the extractor fixture directory.
- The README records the exact Periphery command, working directory, target or
  project selection, Periphery version, output format, and a trimmed copy of the
  raw output used to derive the fixture.
- CXPythonEngineer posts the validation output in the Gate 0 handoff comment.
- The spec is updated if the tool output invalidates parser assumptions.
- CXCodeReviewer explicitly signs off on the fixture schema before Phase 2.

## Task Dependency Map

| Step | Suggested owner | Depends on | Affected paths |
|---|---|---|---|
| Gate 0 - Tool Output Spike | CXPythonEngineer -> CXCodeReviewer | Phase 1.2 plan approval | `docs/research/2026-05-04-dead-symbol-tool-output-spike/`, fixture directory |
| Task 1 - Models/IDs | CXPythonEngineer | Gate 0 sign-off | `extractors/dead_symbol_binary_surface/models.py`, `identifiers.py` |
| Task 2 - Periphery Parser | CXPythonEngineer | Gate 0 sign-off, Task 1 | `parsers/periphery.py`, parser tests, fixture directory |
| Task 3 - Reaper No-Op | CXPythonEngineer | Task 1 | `parsers/reaper.py`, Reaper parser tests |
| Task 4 - Correlation/Safety | CXPythonEngineer | Tasks 1-3, GIM-190/GIM-192 fixtures | `correlation.py`, correlation tests |
| Task 5 - Neo4j Writer | CXPythonEngineer | Tasks 1 and 4 | `neo4j_writer.py`, `foundation/schema.py`, writer tests |
| Task 6 - Extractor Orchestrator | CXPythonEngineer | Tasks 2-5 | `extractor.py`, `__init__.py`, `registry.py`, orchestrator tests |
| Task 7 - Integration Fixture | CXPythonEngineer | Tasks 2-6 | integration test and fixture directory |
| Task 8 - Runbook | CXPythonEngineer or CXTechnicalWriter if hired | Tasks 2-7 | `docs/runbooks/dead-symbol-binary-surface.md` |
| Task 9 - Validation Bundle | CXPythonEngineer, then CXQAEngineer | Tasks 1-8 | command evidence and Phase 4.1 smoke output |

## Task 1 - Deterministic IDs And Pydantic Models

### Tests First

Create `test_dead_symbol_binary_surface_models.py` with exact tests:

- `test_dead_symbol_id_for_returns_128_bit_hex`
- `test_dead_symbol_id_for_is_stable_across_calls`
- `test_dead_symbol_id_excludes_schema_version`
- `test_parsed_dead_symbol_candidate_valid_minimal`
- `test_binary_surface_record_valid_minimal`
- `test_candidate_rejects_empty_symbol_key_without_file_line_fallback`
- `test_candidate_rejects_unknown_confidence`
- `test_candidate_rejects_unused_candidate_with_skip_reason`
- `test_candidate_rejects_skipped_without_skip_reason`
- `test_models_are_frozen`

Use `class X(str, Enum)` for high-cardinality enum-like fields:
`language`, `kind`, `evidence_source`, `evidence_mode`, `confidence`,
`candidate_state`, `skip_reason`, and `surface_kind`. Do not model those as
large `Literal[...]` unions.

### Implementation

Add frozen Pydantic v2 models under
`extractors/dead_symbol_binary_surface/models.py`. Add
`dead_symbol_id_for(...) -> str` in the extractor package unless CR requests a
foundation helper. It must mirror `_stable_id` 128-bit hex style and must not
reuse `symbol_id_for(...)`.

### Acceptance

`uv run pytest tests/extractors/unit/test_dead_symbol_binary_surface_models.py -v`
passes.

## Task 2 - Periphery Parser

### Tests First

Create `test_dead_symbol_binary_surface_parser_periphery.py` with exact tests:

- `test_parse_periphery_fixture_requires_tool_output_schema_version`
- `test_parse_periphery_fixture_rejects_unknown_top_level_key`
- `test_parse_periphery_unused_swift_class`
- `test_parse_periphery_unused_swift_function`
- `test_parse_periphery_unused_swift_property`
- `test_parse_periphery_public_symbol_retained_not_unused`
- `test_parse_periphery_generated_path_skipped_by_skiplist`
- `test_parse_periphery_objc_dynamic_entry_skipped_by_skiplist`
- `test_parse_periphery_malformed_finding_emits_warning_not_crash`
- `test_parse_periphery_normalized_symbol_key_is_deterministic`

### Implementation

Add `parsers/periphery.py` that returns normalized findings and parser warnings.
Keep raw output parsing isolated from graph models.

### Acceptance

Targeted Periphery parser tests pass and no production graph code is touched.

## Task 3 - Reaper No-Op Skip And Android Alternative Guard

### Tests First

Create `test_dead_symbol_binary_surface_parser_reaper.py` with exact tests:

- `test_reaper_ios_report_unavailable_returns_skip`
- `test_reaper_android_report_unavailable_returns_skip`
- `test_reaper_skip_contains_no_synthetic_candidates`
- `test_reaper_skip_does_not_fail_periphery_only_run`
- `test_android_alternative_not_selected_without_spike_file`

### Implementation

Add `parsers/reaper.py` as explicit no-op skip implementation. Do not parse
synthetic Reaper findings.

### Acceptance

Reaper tests document the no-op v1 behavior explicitly.

## Task 4 - Correlation And Safety Guards

### Tests First

Create `test_dead_symbol_binary_surface_correlation.py` with exact tests:

- `test_exact_match_to_public_api_symbol_qualified_name`
- `test_exact_match_to_phase1_symbol_id_for_join_key`
- `test_ambiguous_match_is_skipped`
- `test_public_api_symbol_becomes_retained_public_api`
- `test_open_api_symbol_becomes_retained_public_api`
- `test_gim192_consumed_symbol_creates_blocked_by_contract_symbol`
- `test_blocked_by_contract_symbol_carries_consumer_provenance`
- `test_missing_key_with_file_line_becomes_low_confidence`
- `test_missing_key_without_file_line_is_skipped`
- `test_kotlin_finding_does_not_match_swift_symbol_key`
- `test_swift_finding_does_not_match_kotlin_symbol_key`

### Implementation

Add correlation helper and safety guard functions. Do not query fuzzy matches.
The GIM-192 blocker edge targets `PublicApiSymbol` with copied per-symbol
provenance, not `ModuleContractSnapshot` alone.

### Acceptance

All correlation tests pass and include negative cases for each forbidden fallback.

## Task 5 - Neo4j Schema And Writer

### Tests First

Create `test_dead_symbol_binary_surface_neo4j_writer.py` with exact tests:

- `test_writer_creates_candidate_and_binary_surface_constraints`
- `test_writer_uses_execute_write_for_batch_atomicity`
- `test_writer_merges_candidate_once`
- `test_writer_merges_binary_surface_once`
- `test_writer_merges_backed_by_symbol_once`
- `test_writer_merges_backed_by_public_api_once`
- `test_writer_merges_has_binary_surface_once`
- `test_writer_merges_blocked_by_contract_symbol_once`
- `test_writer_rerun_reports_zero_nodes_relationships_and_properties`
- `test_writer_third_run_after_upstream_change_updates_only_expected_properties`
- `test_writer_does_not_create_blocker_edge_without_public_symbol`

### Implementation

Extend `foundation/schema.py` and add `neo4j_writer.py`. Writer must choose one
transaction boundary explicitly. Default requirement is `session.execute_write`
for the candidate batch; any alternative must be justified in the PR.

### Acceptance

Unit tests prove idempotency at writer level with `nodes_created == 0`,
`relationships_created == 0`, and `properties_set == 0` on unchanged re-run.

## Task 6 - Extractor Orchestrator

### Tests First

Create `test_dead_symbol_binary_surface_extractor.py` with exact tests:

- `test_extractor_periphery_only_happy_path`
- `test_extractor_missing_periphery_file_returns_warning`
- `test_extractor_reaper_unavailable_does_not_fail`
- `test_extractor_codeql_unavailable_does_not_fail`
- `test_extractor_loads_dead_symbol_skiplist`
- `test_extractor_rejects_malformed_skiplist`
- `test_extractor_stats_align_with_writer_result_summary`
- `test_extractor_respects_check_phase_budget`
- `test_extractor_respects_check_resume_budget`
- `test_extractor_concurrent_runs_are_idempotent`

### Implementation

Add `extractor.py` and package `__init__.py`. Register only after tests pass.
Mirror the standard extractor checkpoint discipline from symbol index extractors:
call `check_resume_budget(...)` before work, `check_phase_budget(...)` around
bounded phases, and write an `IngestCheckpoint` after parser, correlation, and
graph-write phases. If implementation argues that the extractor is too small for
checkpointing, that must be an explicit Phase 3.1 review topic with timing
evidence.

### Acceptance

`uv run pytest tests/extractors/unit/test_dead_symbol_binary_surface*.py -q`
passes.

## Task 7 - Integration Fixture

### Tests First

Create `test_dead_symbol_binary_surface_integration.py` with exact tests:

- `test_dead_symbol_run_writes_candidates_binary_surfaces_and_edges`
- `test_dead_symbol_run_is_idempotent_on_real_neo4j`
- `test_dead_symbol_third_run_after_upstream_change_updates_expected_rows`
- `test_public_open_symbols_never_unused_candidates`
- `test_contract_blocked_symbols_never_unused_candidates`
- `test_public_and_contract_blocked_symbol_has_both_guards`
- `test_generated_and_dynamic_skiplist_entries_are_skipped`
- `test_cross_extractor_public_api_surface_regression`
- `test_cross_extractor_cross_module_contract_regression`

### Implementation

Add the fixture and graph setup. The fixture must be small and deterministic.
It must include:

- one used Swift symbol;
- one unused Swift symbol;
- one public retained symbol;
- one generated skipped symbol;
- one symbol that is both public API and blocked by GIM-192 contract evidence;
- `.palace/dead-symbol-skiplist.yaml`.

Dynamic-entry false-positive coverage remains required, but in v1 it is proven
via parser/unit tests against a synthetic `@objc` row rather than the signed
Gate 0 raw integration fixture. We do not fabricate Periphery raw output.

### Acceptance

`uv run pytest tests/extractors/integration/test_dead_symbol_binary_surface_integration.py -v`
passes against real Neo4j via testcontainers or review-profile compose and
asserts direct Cypher graph invariants.

## Task 8 - Runbook

### Work

Add `docs/runbooks/dead-symbol-binary-surface.md` with:

- required pre-generated tool output paths;
- Periphery command used for the fixture;
- Reaper no-op skip evidence path;
- direct Neo4j queries for candidates, retained public API, blockers, and skips;
- false-positive warnings for incomplete target builds.
- required Phase 4.1 evidence paste commands.
- rollback Cypher for candidate labels, binary-surface labels, and the four edge
  families.

### Acceptance

Runbook commands match test names and fixture paths.

## Task 9 - Validation Bundle

Implementation handoff must include:

```bash
cd services/palace-mcp
uv run pytest tests/extractors/unit/test_dead_symbol_binary_surface*.py
uv run pytest tests/extractors/integration/test_dead_symbol_binary_surface_integration.py -v
uv run ruff format --check src tests
uv run ruff check src tests
uv run mypy src
```

If Docker/testcontainers is required and unavailable locally, implementation must
wait for GitHub CI and cite the exact run URL and failing/passing test name.

Phase 4.1 QA must additionally run review-profile smoke:

```bash
docker compose --profile review up -d --wait --build
```

Review-profile note:

- `palace-mcp` health/MCP path is host-side `http://localhost:8080`.
- Neo4j is **not** published as host-side `127.0.0.1:7687` in the shared
  `docker-compose.yml`, so QA Cypher evidence must run via
  `docker compose exec neo4j cypher-shell ...`.
- The shared compose file mounts the primary checkout at `/repos/gimle`, not the
  active paperclip worktree. QA must either override the bind mount to the
  active worktree or copy current-branch artifacts into the running container
  before review smoke.

The PR body or QA comment must paste:

```cypher
MATCH (d:DeadSymbolCandidate) RETURN d.candidate_state, count(*) ORDER BY d.candidate_state;
MATCH (b:BinarySurfaceRecord) RETURN count(b);
MATCH (d:DeadSymbolCandidate {candidate_state: 'unused_candidate'})-[:BACKED_BY_PUBLIC_API]->(p:PublicApiSymbol)
WHERE p.visibility IN ['public', 'open']
RETURN count(*) AS invalid_public_unused;
MATCH (d:DeadSymbolCandidate {candidate_state: 'unused_candidate'})-[:BLOCKED_BY_CONTRACT_SYMBOL]->(:PublicApiSymbol)
RETURN count(*) AS invalid_contract_unused;
MATCH (d:DeadSymbolCandidate)-[rel:BLOCKED_BY_CONTRACT_SYMBOL]->(p:PublicApiSymbol)
RETURN d.id AS candidate_id,
       p.id AS public_symbol_id,
       p.symbol_qualified_name AS public_symbol_key,
       properties(rel) AS blocker_provenance
LIMIT 5;
MATCH (:DeadSymbolCandidate)-[rel:BLOCKED_BY_CONTRACT_SYMBOL]->(:PublicApiSymbol)
WHERE rel.contract_snapshot_id IS NULL
   OR rel.consumer_module_name IS NULL
   OR rel.producer_module_name IS NULL
   OR rel.commit_sha IS NULL
   OR rel.use_count IS NULL
   OR rel.evidence_paths_sample IS NULL
RETURN count(*) AS missing_contract_blocker_provenance;
```

Expected invalid counts and `missing_contract_blocker_provenance` are zero. The
sample rows must prove the relationship target is `PublicApiSymbol` and that
`blocker_provenance` contains `contract_snapshot_id`, `consumer_module_name`,
`producer_module_name`, `commit_sha`, `use_count`, and `evidence_paths_sample`.
QA must also paste the JSON response from
`palace.ingest.run_extractor(name="dead_symbol_binary_surface", project=...)`.

## Rollback

- Remove `dead_symbol_binary_surface` from `extractors/registry.py`.
- Drop only labels/constraints introduced for `DeadSymbolCandidate` and
  `BinarySurfaceRecord` if no other extractor has started using them.
- Cleanup Cypher for a rollback runbook:

```cypher
MATCH (d:DeadSymbolCandidate {project: $project}) DETACH DELETE d;
MATCH (b:BinarySurfaceRecord {project: $project}) DETACH DELETE b;
DROP CONSTRAINT dead_symbol_candidate_id_unique IF EXISTS;
DROP CONSTRAINT binary_surface_record_id_unique IF EXISTS;
```

- Leave fixture docs and research spike for post-mortem unless operator asks for
  cleanup.

## Review Checklist

CXCodeReviewer must verify:

- No public MCP/API/router files changed.
- No production app build files modified to install Reaper or Periphery.
- No auto-delete behavior exists.
- Public API and contract blockers are represented as retention/blocking facts.
- Reaper and CodeQL absence are explicit skip paths, not silent green paths.
- Idempotency is proven with `nodes_created`, `relationships_created`, and
  `properties_set`, not just object counts.
- Task 0 sign-off happened before implementation.
- Test names from this plan exist verbatim or any rename is justified in the PR.
