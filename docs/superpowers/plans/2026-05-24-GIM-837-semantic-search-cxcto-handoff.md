# GIM-837 Semantic Search CXCTO Handoff

## Branch

- Branch: `origin/feature/GIM-837-semantic-search-tool`
- Reviewed spec commit before this handoff: `f0ead09a`
- Canonical spec:
  `docs/superpowers/specs/2026-05-24-GIM-837-semantic-search-tool.md`

## Objective

Review and approve the G0.5.5 plan for MCP tool
`palace.code.semantic_search`, then route implementation in Gimle.

The tool should let agents search code symbols by meaning across one project or
an explicit set of related projects/kits. Example target use cases:

- "find timer/scheduler implementations in the app"
- "find Data-to-hex conversion helpers that may live in HsToolKit or a wallet
  kit"

## Current State

The branch contains a spec only. No implementation files have been changed.

The spec has already been reviewed through multiple independent passes focused
on API contract, architecture, MCP feasibility, QA coverage, and code-review
risks. The latest spec revision addresses the main findings:

- cross-project search is explicit via `projects`;
- every hit carries source `project` and `group_id`;
- public hit identity is `project + group_id + qualified_name`;
- `occurrence_symbol_id` is only the signed i64 Tantivy join key;
- context/snippet is best-effort and scoped to the hit's source project;
- vector-search underfill is reported explicitly;
- embedded-symbol readiness is checked before vector search;
- embedding inference must run off the MCP event loop;
- Qodo backend construction must be process-scoped/lazy, not per request;
- tests must use fake embedding backends and include MCP wire coverage.

## Decisions Needed

1. Confirm `GIM-837` is the correct issue id for G0.5.5.
2. Confirm public parameter names:
   - `backend`
   - `include_context`
   - `context_limit`
3. Confirm scope shape:
   - `project` for one project;
   - `projects` for explicit cross-project search;
   - no unbounded "all indexed projects" mode in v1.
4. Confirm v1 context policy:
   - snippet by `qualified_name + project` when CM is available;
   - usage preview only when commit-scoped occurrence evidence is available;
   - otherwise per-hit warning, no top-level failure.
5. Confirm approximate ranking semantics:
   Neo4j vector query is global top-K followed by scope filtering, so v1 returns
   best-effort scoped results with `candidate_limit`, `returned_count`,
   `embedded_symbol_count`, and warnings.

## Recommended Implementation Order

1. Add backend lifecycle boundary:
   process-scoped lazy embedding dispatcher/backend factory, with fake backend
   injection for tests.
2. Add `services/palace-mcp/src/palace_mcp/code/find_semantic.py`:
   validation, scope resolution, embedded-symbol preflight, async embedding
   offload, vector query, result mapping.
3. Wire `palace.code.semantic_search` in `mcp_server.py`.
4. Add best-effort context hydration:
   CM snippet first; Tantivy usage preview only when scoped evidence is
   available.
5. Add tests:
   unit tests for validation/query/result mapping/backend failures;
   registration test in `tests/test_mcp_server.py`;
   streamable HTTP integration test with seeded data and fake backend.
6. Run local verification from the spec, then plan live smoke after G0.5.6 data
   exists.

## Non-Negotiable Test Cases

- Empty query -> `invalid_query`.
- Missing or ambiguous `project/projects` -> `invalid_scope`.
- Unknown project -> `project_not_registered`.
- Project validation uses `p.slug`, not any helper returning `p.name AS slug`.
- Backend init/inference failure returns explicit embedding backend envelope.
- Two tool calls reuse the same injected backend/dispatcher instance.
- Registered scope with no embeddings returns `ok=true`, empty result, and
  `embeddings_not_ready`.
- Two projects with the same `qualified_name` return distinct hits with correct
  `project/group_id`.
- `include_context=false` does not call context providers.
- `context_limit=0` yields empty `usages_preview`.
- Streamable HTTP test proves `tools/list` and `call_tool` work.

## Risks To Preserve In Implementation

- `:Symbol` nodes are keyed by `qualified_name + group_id`; do not invent a
  string `symbol_id` field.
- `occurrence_symbol_id = symbol_id_for(qualified_name)` is a Tantivy join key,
  not a globally unique public identity across projects.
- CM snippets currently resolve by `qualified_name + project`; scope it by the
  hit's source project.
- Basic Tantivy lookup by symbol id is global. Use usage preview only when the
  lookup can be commit/project scoped, or omit with warning.
- Qodo is heavyweight and synchronous. Never construct it per request or run
  inference directly on the async MCP event loop.
- `returned_count=0` is not enough to diagnose readiness. Use
  `embedded_symbol_count` to distinguish no embeddings from vector underfill.

## Suggested CXCTO Outcome

If the decisions above are accepted, route implementation from this branch or
from a new implementation branch based on it. Do not merge the spec branch to
`develop` until the implementation path and issue id are confirmed.
