# GIM-1519 Plan: palace-mcp Native Passthrough Unification

## Grounding

- Issue: GIM-1519, "palace-mcp native passthrough unification - drop CM-sidecar read-path dependency [spec v3]"
- Spec source: `docs/superpowers/specs/2026-06-07-palace-mcp-native-passthrough-unification.md` on PR #398, branch `feature/palace-native-passthrough-spec`
- Spec head reviewed for this plan: `b5ea43403187a7fe8ded9c4d51692084d8568c77`
- Integration base for this plan branch: `origin/develop` at `edac991c8ce1e927f4d21b184d9a834687703a61`
- Scope rule: implement 6 native read-path tools plus optional CM fallback; keep `search_code` native work out of scope for Phase 1.

## Goal

Replace the current CM-sidecar-only read path for `query_graph`, `get_code_snippet`, `detect_changes`, `trace_call_path`, `search_graph`, and `get_architecture` with native Palace implementations over Neo4j/Tantivy where Palace knows the project, while preserving CM fallback for CM-only projects. Ship this as seven small PRs so each surface has a clear test gate and review boundary.

## Assumptions

- PR #398 is the authoritative v3 spec until merged; implementers must rebase their branches after that spec lands if branch protection requires it.
- `search_code` remains CM-only in this slice and returns a clear `phase2_required`/fallback envelope when no CM substrate can serve it.
- Native project identity is resolved through `palace_mcp.code.namespace.resolve` / `assert_known_project`; do not invent a new resolver or project-kind discriminator.
- All native code paths must keep the existing FastMCP flat-argument surface.
- CM fallback is optional, not a hard runtime dependency for Palace-registered projects.

## Plan-First Resolutions

### Q2: `:Function` coverage for `get_code_snippet`

Phase 1.2 must not require full `:Function` coverage. `native_get_code_snippet` should first locate the `:Symbol`, derive the short function name, and attempt the `:Function` join for a better window. If hotspot/function data is absent, the tool must degrade to occurrence-window or file-head snippets with `snippet_quality` set to `approximate_window` or `file_head`; it must not fail solely because hotspot ingest has not run.

Acceptance criterion: tests cover both a `:Function` hit and a missing-`:Function` degradation path.

### Q4: `:Symbol.start_line/end_line`

Adding `:Symbol.start_line/end_line` is a Phase 2 prerequisite and is not part of this walker. Phase 1 must reserve `snippet_quality: "exact"` for future line-span support and return explicit approximate qualities today.

Acceptance criterion: Phase 1.2 docs/tests assert `exact` is not emitted unless real symbol spans exist.

## Slice Graph

Run Phase 1.0+1.3 first. Phase 1.1+1.2, 1.4, 1.5, and 1.6 depend on the router table/fallback helper from Phase 1.0+1.3. Phase 1.7 depends on all native tool PRs. Phase 1.8 can start after Phase 1.0+1.3, but final runbook content must cite the actual merged tool behavior.

## Phase 1.0+1.3: Router, Fallback, `detect_changes`, Edge Registry

- Suggested owner: CXPythonEngineer
- Branch: `feature/GIM-1519-router-detect-changes`
- Affected paths:
  - `services/palace-mcp/src/palace_mcp/code_router.py`
  - `services/palace-mcp/src/palace_mcp/code/edges.py`
  - `services/palace-mcp/src/palace_mcp/code/native_detect_changes.py`
  - `services/palace-mcp/tests/code/test_passthrough_dispatch.py`
  - `services/palace-mcp/tests/code/test_native_detect_changes.py`
  - `services/palace-mcp/tests/code/test_edges_registry.py`

Work:
- Introduce `PassthroughEntry` and one dispatch function that selects native, CM fallback, or structured error.
- Preserve `search_code` as CM-only / Phase 2.
- Emit structured INFO `passthrough.dispatch` logs with `{tool, decision, project, duration_ms}`.
- Add `CALL_EDGES` and `KNOWN_NON_CALL_EDGES` as the single edge registry.
- Implement `native_detect_changes` files-list mode by wrapping existing `palace.git.diff` behavior and validating `since` before argv construction.

Acceptance criteria:
- Native impl takes precedence for Palace-known projects.
- Native `fallback_to_cm` sentinel invokes CM exactly once when CM is available.
- Native terminal errors do not fall through to CM.
- CM unavailable returns `cm_fallback_unavailable` for CM-only/unserved calls.
- Spec AC-6: `palace.code.search_code(project="uw-ios-baseline", pattern="HD")` returns `{ok: false, error_code: "phase2_required"}` when no CM substrate can serve it; native `search_code` is not implemented in this slice.
- `detect_changes.since` accepts ISO/approxidate examples and rejects malformed values.
- Edge registry test fails for unclassified relationship types.
- `passthrough.dispatch` is asserted by `caplog`.

Verification:
- `cd services/palace-mcp && uv run ruff check`
- `cd services/palace-mcp && uv run ruff format --check`
- `cd services/palace-mcp && uv run mypy src/`
- `cd services/palace-mcp && uv run pytest tests/code/test_passthrough_dispatch.py tests/code/test_native_detect_changes.py tests/code/test_edges_registry.py`
  - Includes AC-6 coverage for the `search_code` `phase2_required` response on `uw-ios-baseline` when CM is unavailable.
- `cd services/palace-mcp && uv run pytest`

## Phase 1.1+1.2: `query_graph` and `get_code_snippet`

- Suggested owner: CXPythonEngineer
- Branch: `feature/GIM-1519-query-snippet`
- Blocked by: Phase 1.0+1.3
- Affected paths:
  - `services/palace-mcp/src/palace_mcp/code/native_query_graph.py`
  - `services/palace-mcp/src/palace_mcp/code/native_get_code_snippet.py`
  - `services/palace-mcp/src/palace_mcp/code/snippet_short_name.py`
  - `services/palace-mcp/src/palace_mcp/code_router.py`
  - `services/palace-mcp/tests/code/test_native_query_graph.py`
  - `services/palace-mcp/tests/code/test_native_get_code_snippet.py`

Work:
- Implement read-only `native_query_graph` with write/admin deny-lists, reserved param rejection, mandatory scope predicate enforcement, row cap, byte budget, and redacted `cypher_error`.
- Strip or neutralize Cypher comments before write-keyword enforcement so comment-smuggling tests cannot create writes.
- Ensure string-literal write words like `"CREATE"` are not rejected as keywords.
- Implement `native_get_code_snippet` with symbol lookup, short-name derivation, heuristic function join, sync `resolve_snippet` adapter, and explicit `snippet_quality`.

Acceptance criteria:
- `query_graph` accepts scoped read queries and returns rows/columns/truncation metadata.
- Write/admin queries are rejected before driver execution where possible.
- Scope-less and partially scoped multi-MATCH queries return `scope_predicate_required`.
- Spec AC-19: string-literal write words such as `"CREATE"` are not rejected by the write/admin deny-list and run as reads.
- Byte and row caps return `truncated_reason`.
- `cypher_error` redacts stack/schema/path details.
- `get_code_snippet` returns `approximate_function_match`, `approximate_window`, or `file_head` as appropriate.
- Missing `:Function` coverage does not fail the snippet tool by itself.
- `exact` snippet quality is reserved for Phase 2 symbol spans.

Verification:
- `cd services/palace-mcp && uv run ruff check`
- `cd services/palace-mcp && uv run ruff format --check`
- `cd services/palace-mcp && uv run mypy src/`
- `cd services/palace-mcp && uv run pytest tests/code/test_native_query_graph.py tests/code/test_native_get_code_snippet.py`
  - Includes AC-19 coverage for read queries containing `"CREATE"` inside a string literal.
- `cd services/palace-mcp && uv run pytest`

## Phase 1.4: `trace_call_path`

- Suggested owner: CXPythonEngineer
- Branch: `feature/GIM-1519-trace-call-path`
- Blocked by: Phase 1.0+1.3
- Affected paths:
  - `services/palace-mcp/src/palace_mcp/code/native_trace_call_path.py`
  - `services/palace-mcp/src/palace_mcp/code/edges.py`
  - `services/palace-mcp/src/palace_mcp/code_router.py`
  - `services/palace-mcp/tests/code/test_native_trace_call_path.py`

Work:
- Implement calls-mode traversal with pure Cypher variable-depth paths over `CALL_EDGES`.
- Do not add APOC dependency.
- Clamp depth to `[1, 6]`, cap path count at 5000, and expose `clamped_depth` when input changes.
- Return `phase2_required` for `data_flow` and `cross_service`.

Acceptance criteria:
- Outbound, inbound, and both-direction calls return stable node/edge envelopes.
- Depth `0` and `7+` are clamped and reported.
- Non-calls modes return `phase2_required`.
- Cypher relationship alternation is generated only from `CALL_EDGES`.

Verification:
- `cd services/palace-mcp && uv run ruff check`
- `cd services/palace-mcp && uv run ruff format --check`
- `cd services/palace-mcp && uv run mypy src/`
- `cd services/palace-mcp && uv run pytest tests/code/test_native_trace_call_path.py tests/code/test_edges_registry.py`
- `cd services/palace-mcp && uv run pytest`

## Phase 1.5: `search_graph`

- Suggested owner: CXPythonEngineer
- Branch: `feature/GIM-1519-search-graph`
- Blocked by: Phase 1.0+1.3
- Affected paths:
  - `services/palace-mcp/src/palace_mcp/code/native_search_graph.py`
  - `services/palace-mcp/src/palace_mcp/code_router.py`
  - `services/palace-mcp/tests/code/test_native_search_graph.py`

Work:
- Implement pattern-mode search with label, `name_pattern`, `qn_pattern`, `file_pattern`, degree filters, offset/limit, and test-friendly deterministic ordering.
- Return `phase2_required` for BM25/full-text `query=`.
- Preserve response shape close enough for existing callers and CM contract tests.

Acceptance criteria:
- Pattern filters work independently and in combination.
- Degree filters bound results correctly.
- `query=` returns `phase2_required`.
- CM fallback still works for unregistered/CM-only project strings.

Verification:
- `cd services/palace-mcp && uv run ruff check`
- `cd services/palace-mcp && uv run ruff format --check`
- `cd services/palace-mcp && uv run mypy src/`
- `cd services/palace-mcp && uv run pytest tests/code/test_native_search_graph.py`
- `cd services/palace-mcp && uv run pytest`

## Phase 1.6: `get_architecture`

- Suggested owner: CXPythonEngineer
- Branch: `feature/GIM-1519-get-architecture`
- Blocked by: Phase 1.0+1.3
- Affected paths:
  - `services/palace-mcp/src/palace_mcp/code/native_get_architecture.py`
  - `services/palace-mcp/src/palace_mcp/code_router.py`
  - `services/palace-mcp/tests/code/test_native_get_architecture.py`

Work:
- Aggregate modules, dependencies, file languages, and entry points from the native graph.
- Return `routes: []` with an explicit Phase 2 note; do not add route extractors.
- Preserve CM fallback for CM-only projects.

Acceptance criteria:
- Response includes `languages`, `packages` or modules, dependencies, `entry_points`, and `routes: []`.
- Missing optional graph sections return empty lists, not errors.
- Unregistered/CM-only projects follow the shared fallback path.

Verification:
- `cd services/palace-mcp && uv run ruff check`
- `cd services/palace-mcp && uv run ruff format --check`
- `cd services/palace-mcp && uv run mypy src/`
- `cd services/palace-mcp && uv run pytest tests/code/test_native_get_architecture.py`
- `cd services/palace-mcp && uv run pytest`

## Phase 1.7: Native Passthrough Smoke Gate

- Suggested owner: CXQAEngineer
- Branch: `feature/GIM-1519-native-smoke-gate`
- Blocked by: Phases 1.0+1.3, 1.1+1.2, 1.4, 1.5, 1.6
- Affected paths:
  - `services/palace-mcp/tests/integration/test_passthrough_native_smoke.py`
  - `services/palace-mcp/tests/integration/fixtures/native_passthrough_seed.cypher`
  - Existing integration fixtures only as needed.

Work:
- Add a seed fixture containing `:Project`, `:File`, `:Symbol`, `:Function`, `:Module`, `:ExternalDependency`, and classified relationship types.
- Exercise all six native tools through the MCP/FastMCP call path.
- Assert mocked CM session is not invoked for native-served Palace projects.
- Add CM-only fallback integration coverage with mocked CM invocation counts.

Acceptance criteria:
- AC-1 through AC-7 have automated smoke coverage where the spec permits automation.
- Seed fixture documents expected node/edge counts.
- Native project calls do not touch CM.
- CM-only project calls touch CM exactly once per tool.

Verification:
- `cd services/palace-mcp && uv run ruff check`
- `cd services/palace-mcp && uv run ruff format --check`
- `cd services/palace-mcp && uv run mypy src/`
- `cd services/palace-mcp && uv run pytest tests/integration/test_passthrough_native_smoke.py`
- `cd services/palace-mcp && uv run pytest`

## Phase 1.8: Operator Runbook and Project Listing Tool

- Suggested owner: CXInfraEngineer
- Branch: `feature/GIM-1519-native-passthrough-runbook`
- Blocked by: Phase 1.0+1.3 for the listing-tool contract; final text should be updated after Phases 1.1-1.7 land.
- Affected paths:
  - `docs/runbooks/palace-passthrough-native-impl.md`
  - `services/palace-mcp/src/palace_mcp/code/list_passthrough_projects.py`
  - `services/palace-mcp/src/palace_mcp/code_router.py`
  - `services/palace-mcp/tests/code/test_list_passthrough_projects.py`

Work:
- Add `palace.code.list_passthrough_projects` returning `{native: [...], cm_only: [...]}`.
- Document routing decisions, fallback behavior, log inspection, `phase2_required` cases, and how operators verify AC-1..AC-5 on `uw-ios-baseline`.
- Document that `search_code` native implementation is deferred.

Acceptance criteria:
- Tool returns both native and CM-only lists in test fixtures.
- Runbook includes exact operator calls for all six native tools and `search_code` deferred behavior.
- Runbook references `passthrough.dispatch` log fields and common error envelopes.

Verification:
- `cd services/palace-mcp && uv run ruff check`
- `cd services/palace-mcp && uv run ruff format --check`
- `cd services/palace-mcp && uv run mypy src/`
- `cd services/palace-mcp && uv run pytest tests/code/test_list_passthrough_projects.py`
- `cd services/palace-mcp && uv run pytest`

## Review and Merge Gates

Each implementation PR must include:
- The relevant phase number in the title/body.
- The plan path above and spec PR #398 head SHA.
- Targeted command output plus full `uv run pytest` for `services/palace-mcp`.
- CR mechanical review with pasted evidence.
- OpusArchitectReviewer adversarial review for security/architecture-sensitive phases, especially 1.0+1.3, 1.1+1.2, and 1.4.
- QA evidence for manual operator ACs when a phase claims AC-1 through AC-5.

## Child Issue Creation Order

After plan-first review approval, create these child issues:

1. GIM-1519 Phase 1.0+1.3 - Router/fallback/detect_changes/edges, assigned to CXPythonEngineer.
2. GIM-1519 Phase 1.1+1.2 - Native query_graph and get_code_snippet, assigned to CXPythonEngineer, blocked by item 1.
3. GIM-1519 Phase 1.4 - Native trace_call_path, assigned to CXPythonEngineer, blocked by item 1.
4. GIM-1519 Phase 1.5 - Native search_graph, assigned to CXPythonEngineer, blocked by item 1.
5. GIM-1519 Phase 1.6 - Native get_architecture, assigned to CXPythonEngineer, blocked by item 1.
6. GIM-1519 Phase 1.7 - Native smoke gate, assigned to CXQAEngineer, blocked by items 1-5.
7. GIM-1519 Phase 1.8 - Runbook/list_passthrough_projects, assigned to CXInfraEngineer, blocked by item 1 for implementation and by items 2-6 for final text.

Do not create child issues before CodeReviewer approves this plan. Comments are events; the plan file is the source of truth for slice scope.
