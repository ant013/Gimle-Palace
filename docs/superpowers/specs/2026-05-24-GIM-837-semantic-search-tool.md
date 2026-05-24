# GIM-837: palace.code.semantic_search MCP tool

## Goal

Ship G0.5.5: a first usable semantic symbol search MCP tool backed by the
existing Qodo embedding backend, `:Symbol.embedding`, and Neo4j vector index.
The tool should let an agent ask natural-language questions such as
`"signature verification"` for one registered project and get ranked matching
symbols with enough metadata to decide which symbols to inspect next.
v1 also returns best-effort snippet/context for each hit when the local code
context providers can resolve the symbol.

## Assumptions

- `origin/develop` is the integration branch.
- G0.5.1-G0.5.4 are already merged:
  - `EmbeddingBackend` and `EmbeddingBackendDispatcher`;
  - `QodoEmbeddingBackend`;
  - vector index `symbol_embedding_idx`;
  - `embedding_symbol` extractor writing `s.embedding`.
- Project scoping is mandatory. The v1 tool accepts a `project` slug and
  queries only `:Symbol {group_id: "project/<slug>"}`.
- v1 includes best-effort snippet/context. Search results remain valid even
  when snippet hydration is unavailable, because `:Symbol` nodes do not carry a
  source range by themselves.
- The implementation uses the existing synchronous embedding interface
  (`embed_text` / `embed_batch`) and does not introduce a new worker process.
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
- Filter returned nodes to the requested project group.
- Return stable response fields:
  - `ok`
  - `project`
  - `query`
  - `backend`
  - `include_context`
  - `limit`
  - `total`
  - `result[]` with `qualified_name`, `kind`, `file_path`, `module_name`,
    `score`, optional `embedding_input_hash`, and optional `context`.
- Add best-effort context hydration:
  - definition location from Tantivy/occurrence data when available;
  - snippet from the existing code-context/snippet path when available;
  - usage preview capped by `context_limit`.
- Add focused unit tests for query shaping, project validation, result mapping,
  and backend injection.
- Add MCP registration/wire-shape coverage so the tool appears exactly once.

Out of scope:

- G0.5.6 cascade re-ingest across bitcoin-core, evm-kit, bitcoin-kit,
  dash-kit, and uw-ios-app.
- G0.5.7 manual top-3 semantic validation and latency matrix.
- Multi-project search or cross-repo aggregation.
- Changing embedding text format or re-embedding existing symbols.
- New vector index schema changes unless the current index name/dimensions are
  proven wrong.
- Making snippet/context mandatory for a successful semantic result.

## Affected areas

- `services/palace-mcp/src/palace_mcp/code/find_semantic.py`
- `services/palace-mcp/src/palace_mcp/mcp_server.py`
- `services/palace-mcp/tests/test_mcp_server.py`
- `services/palace-mcp/tests/code/test_find_semantic.py` or equivalent focused
  test module
- Potentially `services/palace-mcp/src/palace_mcp/embeddings/__init__.py` only
  if a small factory/helper is needed to avoid duplicating backend construction.

## Design

### Tool signature

```python
async def palace_code_semantic_search(
    query: str,
    project: str,
    limit: int = 10,
    backend: str | None = None,
    include_context: bool = True,
    context_limit: int = 3,
) -> dict[str, Any]:
    ...
```

Validation:

- `query.strip()` must be non-empty.
- `project.strip()` must be non-empty.
- `backend`, when provided, must resolve through the existing
  `EmbeddingBackendDispatcher`.
- `limit` is clamped or rejected outside a small range. Proposed v1:
  reject `limit < 1` or `limit > 50` with `ok=false`,
  `error_code="invalid_limit"`.
- `context_limit` is rejected outside `0..10` with
  `error_code="invalid_context_limit"`.
- If Neo4j driver is unavailable, return the existing code-tool style
  `driver_unavailable` envelope.
- If the project is not registered, return `project_not_registered`.
- If the requested backend is not registered, return `unknown_embedding_backend`.

### Query flow

1. Resolve `group_id = f"project/{project}"`.
2. Verify `(:Project {slug: project})` exists.
3. Resolve embedding backend. `backend=None` uses the default dispatcher backend,
   currently Qodo.
4. Compute `query_embedding = backend.embed_text(query)`.
5. Query Neo4j:

```cypher
CALL db.index.vector.queryNodes('symbol_embedding_idx', $candidate_limit, $embedding)
YIELD node, score
WITH node AS s, score
WHERE s:Symbol AND s.group_id = $group_id
RETURN
  s.qualified_name AS qualified_name,
  s.kind AS kind,
  s.file_path AS file_path,
  s.module_name AS module_name,
  s.embedding_input_hash AS embedding_input_hash,
  score AS score
ORDER BY score DESC
LIMIT $limit
```

`candidate_limit` should be larger than `limit` so project filtering does not
drop all cross-project hits before the final limit. Proposed v1:
`candidate_limit = min(max(limit * 5, 25), 250)`.

### Context hydration

For each returned symbol, if `include_context=true`:

1. Resolve the symbol id from `qualified_name`.
2. Ask the existing occurrence index for definition/declaration and usage
   occurrences.
3. Hydrate a snippet through the existing code-context path when possible.
4. Attach a `context` object. Missing context does not turn the whole response
   into an error; it sets `context.available=false` and includes
   `context.warning`.

The context object is intentionally best-effort because vector search runs over
Neo4j symbols, while exact source slices are owned by the code-context and
occurrence indexes.

### Response shape

Success:

```json
{
  "ok": true,
  "project": "uw-ios-app",
  "query": "signature verification",
  "backend": "qodo",
  "include_context": true,
  "limit": 10,
  "total": 2,
  "result": [
    {
      "qualified_name": "Module.Type.method()",
      "kind": "function",
      "file_path": "Sources/Module/File.swift",
      "module_name": "Module",
      "embedding_input_hash": "abc123",
      "score": 0.82,
      "context": {
        "available": true,
        "definition_location": {
          "file_path": "Sources/Module/File.swift",
          "line": 42,
          "col_start": 8
        },
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
  "qualified_name": "Module.Type.method()",
  "kind": "function",
  "file_path": "Sources/Module/File.swift",
  "module_name": "Module",
  "score": 0.82,
  "context": {
    "available": false,
    "warning": "definition occurrence or snippet provider unavailable"
  }
}
```

Error:

```json
{
  "ok": false,
  "error_code": "project_not_registered",
  "message": "no :Project {slug: 'uw-ios-app'}",
  "project": "uw-ios-app"
}
```

## Acceptance criteria

1. `palace.code.semantic_search` appears exactly once in MCP tool registration.
2. Empty query returns `ok=false`, `error_code="invalid_query"`.
3. Unknown project returns `ok=false`, `error_code="project_not_registered"`.
4. Invalid limit returns `ok=false`, `error_code="invalid_limit"`.
5. Invalid context limit returns `ok=false`,
   `error_code="invalid_context_limit"`.
6. Unknown backend returns `ok=false`,
   `error_code="unknown_embedding_backend"`.
7. Successful path calls the selected embedding backend once with the raw query
   text.
8. Successful path calls `db.index.vector.queryNodes('symbol_embedding_idx', ...)`.
9. Successful path filters results to `group_id = "project/<slug>"`.
10. Successful response preserves descending score order and includes
   `qualified_name`, `kind`, `file_path`, `module_name`, and `score`.
11. When `include_context=true`, response entries include a `context` object.
12. Context hydration failures are per-hit best-effort warnings, not
   top-level failures.
13. When `include_context=false`, response entries omit `context`.
14. Tests do not download or load the real Qodo model; they use an injected fake
   embedding backend.
15. Existing code-tool registration tests pass after adding the new tool name.

## Verification plan

Focused local checks:

```bash
cd services/palace-mcp
uv run pytest tests/test_mcp_server.py tests/code/test_find_semantic.py
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
  "query": "signature verification",
  "project": "uw-ios-app",
  "limit": 10,
  "backend": "qodo",
  "include_context": true,
  "context_limit": 3
}
```

Expected: `ok=true`, non-empty `result`, and manually sensible top hits.

## Risks

- Neo4j vector query returns global top-K before filtering. Mitigation:
  over-fetch with `candidate_limit`.
- Qodo backend construction is heavyweight. Mitigation: keep injection seam for
  tests and lazy default construction in production path.
- Snippet hydration depends on code-context/occurrence indexes and may be
  unavailable for some hits. Mitigation: make context per-hit best-effort and
  keep the ranked semantic hit list usable.
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
