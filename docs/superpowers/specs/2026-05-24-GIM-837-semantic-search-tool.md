# GIM-837: palace.code.semantic_search MCP tool

## Goal

Ship G0.5.5: a first usable semantic symbol search MCP tool backed by the
existing Qodo embedding backend, `:Symbol.embedding`, and Neo4j vector index.
The tool should let an agent ask natural-language questions such as
`"signature verification"` for one registered project or an explicit set of
related projects/kits and get ranked matching symbols with enough metadata to
decide which symbols to inspect next.
v1 also returns best-effort snippet/context for each hit when the local code
context providers can resolve the symbol.

## Assumptions

- `origin/develop` is the integration branch.
- G0.5.1-G0.5.4 are already merged:
  - `EmbeddingBackend` and `EmbeddingBackendDispatcher`;
  - `QodoEmbeddingBackend`;
  - vector index `symbol_embedding_idx`;
  - `embedding_symbol` extractor writing `s.embedding`.
- Scope is mandatory. The v1 tool accepts either one `project` slug or an
  explicit `projects` list and queries only the matching project group ids.
  Cross-project search is allowed for use cases such as finding a helper that
  may live in `uw-ios-app`, `HsToolKit`, or one of the wallet kits, but every
  hit must identify its source project.
- v1 includes best-effort snippet/context. Search results remain valid even
  when snippet hydration is unavailable, because `:Symbol` nodes do not carry a
  source range by themselves.
- The implementation uses the existing synchronous embedding interface
  (`embed_text` / `embed_batch`) through an async offload boundary so model
  inference does not block the MCP event loop.
- The default embedding backend remains Qodo, but callers can explicitly select
  any dispatcher-registered backend by name.

## Scope

In scope:

- Add a semantic search implementation module under
  `services/palace-mcp/src/palace_mcp/code/`.
- Register MCP tool `palace.code.semantic_search`.
- Generate one query embedding through the existing embedding backend.
- Query Neo4j vector index `symbol_embedding_idx` with
  `db.index.vector.queryNodes`.
- Filter returned nodes to the requested project groups.
- Return stable response fields:
  - `ok`
  - `scope`
  - `query`
  - `backend`
  - `include_context`
  - `limit`
  - `returned_count`
  - `warnings[]`
  - `result[]` with `project`, `group_id`, `qualified_name`,
    `occurrence_symbol_id`, `kind`, `file_path`, `module_name`, `score`,
    optional `embedding_input_hash`, and optional `context`.
- Add best-effort context hydration:
  - snippet from the existing code-context/snippet path when available;
  - usage preview from Tantivy when available, capped by `context_limit`.
- Add focused unit tests for query shaping, project validation, result mapping,
  and backend injection.
- Add MCP registration/wire-shape coverage so the tool appears exactly once.

Out of scope:

- G0.5.6 cascade re-ingest across bitcoin-core, evm-kit, bitcoin-kit,
  dash-kit, and uw-ios-app.
- G0.5.7 manual top-3 semantic validation and latency matrix.
- Unbounded "search every indexed project" mode.
- Changing embedding text format or re-embedding existing symbols.
- New vector index schema changes unless the current index name/dimensions are
  proven wrong.
- Making snippet/context mandatory for a successful semantic result.
- Reliably classifying definition/declaration versus usage from the current
  occurrence store when the store does not provide that role metadata.

## Affected areas

- `services/palace-mcp/src/palace_mcp/code/find_semantic.py`
- `services/palace-mcp/src/palace_mcp/mcp_server.py`
- `services/palace-mcp/tests/test_mcp_server.py`
- `services/palace-mcp/tests/code/test_find_semantic.py` or equivalent focused
  test module
- `services/palace-mcp/src/palace_mcp/embeddings/__init__.py` or equivalent
  process-scoped factory for a lazy MCP embedding dispatcher/backend cache.

## Design

### Tool signature

```python
async def palace_code_semantic_search(
    query: str,
    project: str | None = None,
    projects: list[str] | None = None,
    limit: int = 10,
    backend: str | None = None,
    include_context: bool = True,
    context_limit: int = 3,
) -> dict[str, Any]:
    ...
```

Validation:

- `query.strip()` must be non-empty.
- Exactly one of `project` or `projects` must be provided.
- `project` and every `projects[]` entry must be a valid non-empty project
  slug.
- `projects` must not be empty and must not exceed 10 entries in v1.
- `backend`, when provided, must resolve through the existing
  `EmbeddingBackendDispatcher`.
- `limit < 1` or `limit > 50` is rejected with `ok=false`,
  `error_code="invalid_limit"`.
- `context_limit` is rejected outside `0..10` with
  `error_code="invalid_context_limit"`.
- `context_limit=0` is valid and means context may include a snippet/location,
  but `usages_preview` must be empty.
- If Neo4j driver is unavailable, return the existing code-tool style
  `driver_unavailable` envelope.
- If any requested project is not registered, return `project_not_registered`
  with `missing_projects`.
- If the requested backend is not registered, return `unknown_embedding_backend`.
- If embedding backend initialization or inference fails, return
  `embedding_backend_unavailable` or `embedding_backend_failed`.
- If a registered scope has no embedded symbols, return `ok=true`,
  `returned_count=0`, `result=[]`, and a warning code
  `embeddings_not_ready`.
- Project validation must use `MATCH (p:Project {slug: $slug})` or equivalent
  direct `p.slug` matching. Do not use helper paths that alias `p.name AS slug`.

### Query flow

1. Resolve scope slugs from `project` or `projects`.
2. Resolve `group_ids = [f"project/{slug}" for slug in scope]`.
3. Verify every requested `(:Project {slug})` exists by direct `p.slug` lookup.
4. Resolve embedding backend. `backend=None` uses the default dispatcher backend,
   currently Qodo.
5. Compute `query_embedding = backend.embed_text(query)` through
   `asyncio.to_thread` or an equivalent executor-backed boundary.
6. Preflight scoped embedding readiness:

```cypher
MATCH (s:Symbol)
WHERE s.group_id IN $group_ids AND s.embedding IS NOT NULL
RETURN count(s) AS embedded_symbol_count
```

If `embedded_symbol_count == 0`, return `ok=true`, `returned_count=0`,
`result=[]`, and `warnings[] = [{"code": "embeddings_not_ready", ...}]`
without running vector search.

7. Query Neo4j:

```cypher
CALL db.index.vector.queryNodes('symbol_embedding_idx', $candidate_limit, $embedding)
YIELD node, score
WITH node AS s, score
WHERE s:Symbol AND s.group_id IN $group_ids
RETURN
  s.group_id AS group_id,
  s.qualified_name AS qualified_name,
  s.kind AS kind,
  s.file_path AS file_path,
  s.module_name AS module_name,
  s.embedding_input_hash AS embedding_input_hash,
  score AS score
ORDER BY score DESC
LIMIT $limit
```

Neo4j vector search returns global top-K before the `group_id` filter. That
makes scoped search approximate when the index contains many projects. v1 must
over-fetch and report that behavior:

- `candidate_limit = min(max(limit * len(scope) * 10, 50), 500)`.
- The response includes `candidate_limit`.
- `returned_count` is the number of returned rows, not the total number of
  possible semantic matches.
- The response includes `embedded_symbol_count` for the requested scope.
- If fewer than `limit` rows are returned, the response may include
  `warnings[] = [{"code": "scope_filter_underfilled", ...}]`.
- v1 has no hard relevance threshold; a scoped result set with embeddings but
  zero returned hits should be treated as candidate starvation/filter
  underfill, not proof that no semantic match exists.

### Context hydration

For each returned symbol, if `include_context=true`:

1. Use the hit's `project`, `group_id`, and `qualified_name` as the context
   lookup scope. Do not hydrate context from `qualified_name` without the hit's
   source project.
2. Translate the public project slug to the code-context project name when
   calling code-context providers.
3. Hydrate a snippet through the existing code-context path by calling CM with
   `qualified_name` and the translated project name when possible.
4. Compute `occurrence_symbol_id = symbol_id_for(qualified_name)` for
   occurrence lookups. This is a signed i64 Tantivy join key, not the primary
   public hit identity.
5. Ask the occurrence index for a usage preview only when a project/commit scope
   can be resolved for the hit and the commit-scoped occurrence API can be used.
   If not, omit `usages_preview` and attach a per-hit warning code such as
   `usage_preview_unavailable`.
6. Attach a `context` object. Missing context does not turn the whole response
   into an error; it sets `context.available=false` and includes
   `context.warning_code` plus optional `context.warning`.

The context object is intentionally best-effort because vector search runs over
Neo4j symbols, while exact source slices are owned by the code-context and
occurrence indexes. v1 does not claim that Tantivy occurrences reliably
distinguish definitions from usages unless the underlying occurrence metadata is
present.

### Response shape

Success:

```json
{
  "ok": true,
  "scope": {
    "projects": ["uw-ios-app", "HsToolKit"]
  },
  "query": "signature verification",
  "backend": "qodo",
  "include_context": true,
  "limit": 10,
  "candidate_limit": 200,
  "embedded_symbol_count": 18421,
  "returned_count": 2,
  "warnings": [],
  "result": [
    {
      "project": "uw-ios-app",
      "group_id": "project/uw-ios-app",
      "qualified_name": "Module.Type.method()",
      "occurrence_symbol_id": -8070450532247928833,
      "kind": "function",
      "file_path": "Sources/Module/File.swift",
      "module_name": "Module",
      "embedding_input_hash": "abc123",
      "score": 0.82,
      "context": {
        "available": true,
        "snippet": {
          "language": "swift",
          "start_line": 42,
          "end_line": 58,
          "source": "func verifySignature(...) { ... }"
        },
        "usages_preview": [
          {
            "file_path": "Sources/Module/Caller.swift",
            "line": 77,
            "col_start": 16,
            "role": "reference"
          }
        ]
      }
    }
  ]
}
```

If context cannot be hydrated for a hit:

```json
{
  "project": "uw-ios-app",
  "group_id": "project/uw-ios-app",
  "qualified_name": "Module.Type.method()",
  "occurrence_symbol_id": -8070450532247928833,
  "kind": "function",
  "file_path": "Sources/Module/File.swift",
  "module_name": "Module",
  "score": 0.82,
  "context": {
    "available": false,
    "warning_code": "snippet_provider_unavailable",
    "warning": "snippet provider unavailable"
  }
}
```

Error:

```json
{
  "ok": false,
  "error_code": "project_not_registered",
  "message": "one or more requested projects are not registered",
  "missing_projects": ["uw-ios-app"]
}
```

## Acceptance criteria

1. `palace.code.semantic_search` appears exactly once in MCP tool registration.
2. Empty query returns `ok=false`, `error_code="invalid_query"`.
3. Missing or ambiguous scope returns `ok=false`, `error_code="invalid_scope"`.
4. Unknown project returns `ok=false`, `error_code="project_not_registered"`.
5. Invalid limit returns `ok=false`, `error_code="invalid_limit"`.
6. Invalid context limit returns `ok=false`,
   `error_code="invalid_context_limit"`.
7. Unknown backend returns `ok=false`,
   `error_code="unknown_embedding_backend"`.
8. Backend initialization/inference failure returns an explicit embedding
   backend error envelope.
9. Successful path calls the selected embedding backend once with the raw query
   text through an off-event-loop boundary.
10. The MCP server obtains embedding backends through a process-scoped lazy
   dispatcher/backend cache and does not construct a new Qodo model per request.
11. Successful path calls
   `db.index.vector.queryNodes('symbol_embedding_idx', ...)`.
12. Successful path filters results to the requested `group_ids`.
13. Cross-project success returns each hit with its source `project` and
   `group_id`.
14. Registered scope with no embedded symbols returns `ok=true`,
   `returned_count=0`, `result=[]`, `embedded_symbol_count=0`, and
   `warnings[].code="embeddings_not_ready"`.
15. Successful response preserves descending score order and includes
   `project`, `group_id`, `qualified_name`, `occurrence_symbol_id`, `kind`,
   `file_path`, `module_name`, and `score`.
16. When `include_context=true`, response entries include a `context` object.
17. Context hydration failures are per-hit best-effort warnings, not
   top-level failures.
18. When `include_context=false`, response entries omit `context` and no
   context hydration providers are called.
19. `context_limit=0` returns an empty `usages_preview`.
20. Tests do not download or load the real Qodo model; they use an injected fake
   embedding backend.
21. Two semantic-search tool invocations reuse the same injected backend or
   dispatcher instance in tests.
22. Project validation tests cover `p.slug != p.name` and prove validation uses
   `p.slug`.
23. A cross-project test covers two projects with the same `qualified_name` and
   proves each hit keeps the correct source `project/group_id`.
24. Existing code-tool registration tests pass after adding the new tool name.
25. Streamable HTTP integration coverage verifies `tools/list` and a seeded
   `call_tool` path with a fake backend.

## Verification plan

Focused local checks:

```bash
cd services/palace-mcp
uv run pytest tests/test_mcp_server.py tests/code/test_find_semantic.py
uv run pytest tests/integration/test_find_semantic_search_tool.py
uv run ruff check src/palace_mcp/code/find_semantic.py src/palace_mcp/mcp_server.py tests/code/test_find_semantic.py
uv run mypy src/palace_mcp/code/find_semantic.py
```

Optional live smoke after G0.5.6 data exists:

```cypher
MATCH (s:Symbol {group_id: "project/uw-ios-app"})
WHERE s.embedding IS NOT NULL
RETURN count(s)
```

Then call:

```json
{
  "query": "hex conversion for Data variable bytes string",
  "projects": ["uw-ios-app", "HsToolKit", "bitcoin-kit", "evm-kit", "dash-kit"],
  "limit": 10,
  "backend": "qodo",
  "include_context": true,
  "context_limit": 3
}
```

Expected: `ok=true`, non-empty `result`, every hit has the source `project`,
and manually sensible top hits.

## Risks

- Neo4j vector query returns global top-K before filtering. Mitigation:
  over-fetch with `candidate_limit`, expose `returned_count`, and warn when the
  scope filter underfills the requested limit.
- Qodo backend construction is heavyweight. Mitigation: keep injection seam for
  tests, use a process-scoped lazy backend/dispatcher, and offload synchronous
  inference away from the event loop.
- Snippet hydration depends on code-context/occurrence indexes and may be
  unavailable for some hits. Mitigation: make context per-hit best-effort and
  keep the ranked semantic hit list usable.
- Cross-project context can become ambiguous if hydrated from
  `qualified_name` alone. Mitigation: carry `project`, `group_id`, and
  `qualified_name` on each hit and scope context providers to the hit's project;
  use `occurrence_symbol_id` only as the Tantivy join key.
- Existing `EmbeddingBackend` lacks an explicit dimension property. This slice
  does not need dimension checks because G0.5.3 owns index schema and G0.5.4
  already writes vectors.
- Score semantics depend on Neo4j cosine implementation. v1 treats score as an
  opaque rank value and only orders descending.

## Open questions

- Is `GIM-837` the intended Paperclip issue number for G0.5.5, or should the
  branch/spec be renamed before implementation?
- Confirm final public parameter names: `backend`, `include_context`, and
  `context_limit`.
- Confirm final multi-project scope shape: `project` for one project and
  `projects` for explicit cross-project search.
