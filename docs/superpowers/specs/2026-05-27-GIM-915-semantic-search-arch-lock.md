# GIM-915 PR0a: Semantic-Search Architecture Lock

**Date**: 2026-05-27
**Branch**: `pr0a/GIM-914-semantic-arch-lock`
**Slice**: G0.6 PR0a

---

## Purpose

Pin the authoritative implementation boundary for `palace.code.semantic_search`
so that PR3–PR6 child issues edit the right files and a second semantic-search
stack is never introduced.

---

## Current implementation files (v1 — authoritative)

| File | Role |
|------|------|
| `services/palace-mcp/src/palace_mcp/code/find_semantic.py` | Implementation: candidate retrieval, scope validation, embedding dispatch, Neo4j vector query, group-id filtering, context hydration, result serialisation |
| `services/palace-mcp/src/palace_mcp/code/semantic_contract.py` | Contract types: `SemanticSearchRequest`, `SemanticSearchHit`, `EmbeddingCoverage`, `SymbolSourceMetadata`, `ScoreComponents` |
| `services/palace-mcp/src/palace_mcp/mcp_server.py` | MCP tool registration (line 1414–1449): `palace.code.semantic_search` |

---

## MCP route

```
Tool name : palace.code.semantic_search
Handler   : palace_code_semantic_search (mcp_server.py:1422)
Impl call : find_semantic.semantic_search(driver, settings, query,
             project, projects, limit, backend, include_context, context_limit)
```

---

## Embedding backend

- Resolved via `get_embedding_dispatcher()` → `dispatcher.backend(name)`
- Default backend: `qodo` (Qodo-Embed-1-1.5B, self-hosted)
- Inference runs through `asyncio.to_thread(backend.embed_text, query)` — off
  the event loop, single text call per request

---

## Neo4j vector query

```cypher
CALL db.index.vector.queryNodes('symbol_embedding_idx', $query_k, $embedding)
YIELD node, score
WITH node AS s, score
WHERE s:Symbol AND s.group_id IN $group_ids
RETURN
  s.group_id, s.qualified_name, s.kind, s.file_path, s.module_name,
  s.source_scope, s.embedding_input_hash, s.commit_sha, score
ORDER BY score DESC
LIMIT $limit
```

- Index: `symbol_embedding_idx` (cosine, 1536 dimensions — G0.5.3)
- Over-fetch: `candidate_limit = min(max(limit × scope_size × 10, 50), 500)`
  compensates for pre-filter global top-K behaviour
- Score: raw Neo4j cosine similarity, descending — no additional ranking in v1

---

## Module ownership (v1)

| Responsibility | Owner |
|----------------|-------|
| Candidate retrieval | `find_semantic.py` — `_vector_search()` |
| Scope validation | `find_semantic.py` — `_normalize_scope()`, `_validate_projects()` |
| Embedding dispatch | `find_semantic.py` — calls `get_embedding_dispatcher()` |
| Group-id filtering | Neo4j WHERE clause inside `_VECTOR_QUERY` |
| Result mapping | `find_semantic.py` — per-row `hit` dict construction |
| Snippet hydration | `find_semantic.py` — `_load_snippet_context()` via CM `get_code_snippet` |
| Usage preview | `find_semantic.py` — `_load_usage_preview()` via `TantivyBridge` |
| Response serialisation | `find_semantic.py` — `semantic_search()` return value |
| Request/response types | `semantic_contract.py` |
| MCP wire shape | `mcp_server.py` `palace_code_semantic_search()` |

---

## Contract gap (v1 known delta)

`semantic_contract.py` defines `SemanticSearchRequest` (with `source_scopes`,
`include_dependencies`, `include_sdk` flags and `effective_scopes()` resolution)
and `ScoreComponents` (with `lexical_match`, `symbol_kind_boost` etc.).

**Neither is wired into `find_semantic.py` in v1.**  Current implementation
validates scope inline and uses raw cosine score.

Closing this gap is the job of PR3–PR6:

- PR3a decides whether hybrid (sparse + dense) retrieval is warranted
- PR3 wires a deterministic `ScoreComponents` into ranking
- PR4 wires `SemanticSearchRequest.effective_scopes()` into filtering
- PR5 hardens snippet/context provider paths

Until those PRs merge, `semantic_contract.py` is a forward-looking type
library, not a runtime dependency of `find_semantic.py`.

---

## Candidate retrieval: dense-only for v1

v1 uses **dense-only** retrieval: a single cosine vector query against
`symbol_embedding_idx`.  No sparse lexical component is mixed in.

`ScoreComponents.lexical_match` exists in the contract for when PR3a decides
to introduce BM25 or keyword boosting.  That decision is explicitly deferred
to **PR3a** with dev-matrix evidence.

PR3a acceptance gate: produce a comparison table (dense vs hybrid) on ≥2
projects before committing to an approach.

---

## Files in scope for PR3–PR6

Child issues implementing PR3a, PR3, PR4, PR5, PR6 **must** stay within:

| File | Notes |
|------|-------|
| `services/palace-mcp/src/palace_mcp/code/find_semantic.py` | Core implementation — primary edit target |
| `services/palace-mcp/src/palace_mcp/code/semantic_contract.py` | Types — extend here, do not duplicate in new modules |
| `services/palace-mcp/tests/code/test_find_semantic.py` | Unit tests |
| `services/palace-mcp/tests/code/test_semantic_search_contract.py` | Contract type tests |
| `services/palace-mcp/tests/integration/test_find_semantic_search_tool.py` | Integration/MCP wire tests |

**Forbidden**: creating a parallel `semantic_search.py`, `search_semantic.py`,
or any new module in `code/semantic/` that re-implements candidate retrieval or
response serialisation.  The C6 roadmap row is ✅ closed; the implementation
lives in `find_semantic.py`.

---

## rg verification (per GIM-915 acceptance criteria)

Matches in `services/palace-mcp/src` at PR0a merge:

| File | Matches |
|------|---------|
| `mcp_server.py` | `find_semantic` import (line 63), `palace.code.semantic_search` registration (line 1415), tool function (line 1422), impl call (line 1439) |
| `code/find_semantic.py` | module docstring, `semantic_search` function |
| `code/semantic_contract.py` | module docstring, `SemanticSearchRequest` class docstring |
| `code/embedding_candidate_policy.py` | `EmbeddingCoverage` import from `semantic_contract` |

No file named `semantic_search.py` exists in `services/palace-mcp/src`.
