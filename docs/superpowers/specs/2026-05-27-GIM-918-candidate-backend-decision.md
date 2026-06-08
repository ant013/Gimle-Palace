# GIM-918 PR3a: Semantic Candidate Backend Decision

**Date**: 2026-05-27
**Branch**: `pr3a/GIM-914-candidate-backend-decision`
**Slice**: G0.6 PR3a
**Depends on**: [GIM-915 arch lock](2026-05-27-GIM-915-semantic-search-arch-lock.md)

---

## Decision

**v1 candidate retrieval strategy: dense-only (status quo).**

No hybrid or sparse path is introduced in v1. The rationale and comparison
evidence are in the sections below.

---

## Candidate strategies evaluated

| Strategy | Available now | Implementation risk | Operational dependencies |
|----------|--------------|---------------------|--------------------------|
| Dense (Neo4j `symbol_embedding_idx` cosine) | ✅ | None — already shipped | Neo4j vector index, Qodo embedding model |
| Sparse/Tantivy symbol-name text search | ❌ Not available | High — new Tantivy schema required | New symbol-name Tantivy index, index population pipeline |
| Hybrid (dense + sparse RRF fusion) | ❌ | High — blocked on sparse | All of the above |

### Dense-only (current implementation)

`find_semantic.py` executes a single Neo4j vector query:

```cypher
CALL db.index.vector.queryNodes('symbol_embedding_idx', $query_k, $embedding)
YIELD node, score
WHERE s:Symbol AND s.group_id IN $group_ids
ORDER BY score DESC
LIMIT $limit
```

- Query embedding: single `backend.embed_text(query)` call off the event loop
- Candidate pool: `_candidate_limit = min(max(limit × scope_size × 10, 50), 500)`
- Sort: cosine similarity descending — deterministic for fixed embedding input
- All unit + integration tests pass on develop (see GIM-915 CI evidence)

### Sparse/Tantivy symbol-name text search

`TantivyBridge` exists in `extractors/foundation/tantivy_bridge.py` but its
only public method is `search_occurrences_async(symbol_id, commit_sha, phases)`.
This method looks up **usage occurrences** (where a known symbol is referenced),
not candidates by query text.

To support sparse candidate retrieval:
1. A new Tantivy schema would be required (fields: `qualified_name`,
   `module_name`, `kind`, `source_scope`, `group_id`)
2. Symbol population must write to this schema at ingest time
3. A new `TantivyBridge` search path needs `search_symbols_by_text(query)` →
   `[{qualified_name, score}]`
4. The dense + sparse merge step needs RRF or score normalization

None of steps 1–4 exist. Building them is PR-sized scope, not a config choice.

### Hybrid retrieval

Blocked on sparse. Not evaluated further.

---

## Dev-matrix comparison

A live embedding run against a real project is not required for this decision
because the sparse path **does not exist as an implementation**. There is no
code to compare against dense at query time.

The table below records what a future live matrix should measure if hybrid is
reconsidered:

| Query | Dense top-1 | Sparse top-1 | Hybrid top-1 | Dense latency (ms) | Hybrid latency (ms) |
|-------|-------------|--------------|--------------|-------------------|---------------------|
| "verify signature" | — | — | — | — | — |
| "parse transaction" | — | — | — | — | — |
| "wallet balance" | — | — | — | — | — |
| "block header hash" | — | — | — | — | — |

This table is intentionally empty in PR3a because sparse is absent. If a future
PR introduces Tantivy symbol-name search, populate this table from live runs
on `uw-ios-app` and one HorizontalSystems kit repo before committing to hybrid.

---

## Candidate pool: fixed and deterministic for PR3/PR6

Formula (unchanged, verified in `find_semantic.py:122`):

```python
def _candidate_limit(limit: int, scope_size: int) -> int:
    return min(max(limit * scope_size * 10, 50), 500)
```

Representative values:

| limit | scope_size (projects) | candidate_limit |
|-------|-----------------------|-----------------|
| 10 | 1 | 100 |
| 10 | 5 | 500 |
| 5 | 1 | 50 |
| 50 | 1 | 500 |

All values are deterministic from the two input parameters. PR3 and PR6 tests
may assert `candidate_limit` from the response payload without any code change.

---

## Query normalization (v1 baseline)

Implemented in `find_semantic.py:76`:

```python
def _normalize_query(value: str) -> str | None:
    normalized = value.strip()
    return normalized or None
```

- Leading/trailing whitespace stripped
- Case preserved (no lowercasing)
- No stemming, tokenization, or punctuation removal
- Empty-after-strip → `error_code="invalid_query"`

This is the PR3/PR6 test baseline. Any change to normalization must be
a deliberate PR3 commit, not a silent side-effect.

---

## Tokenizer and model identity (v1 baseline)

From GIM-915 arch note and `pyproject.toml`/embedding config:

| Component | Value |
|-----------|-------|
| Model | Qodo-Embed-1-1.5B |
| Vector dimensions | 1536 |
| Index | `symbol_embedding_idx` (Neo4j cosine) |
| Embedding call | `backend.embed_text(query)` — single string, no batching |

Changes to model or tokenizer invalidate the existing vector index and must
trigger a full re-embed before any quality comparison is valid.

---

## Candidate sort order (v1 baseline)

`_VECTOR_QUERY` ends with `ORDER BY score DESC LIMIT $limit`.

- Deterministic given fixed embedding input and unchanged Neo4j index
- No tie-breaking by `qualified_name` or `kind` in v1 — ties are Neo4j order

PR3 may add a secondary sort key; if so, it must be listed in `ScoreComponents`
and tested explicitly.

---

## Follow-up work

| Scope | Where | Conditions |
|-------|-------|------------|
| Wire `SemanticSearchRequest.effective_scopes()` into filtering | PR4 `find_semantic.py` | Prerequisite: PR3 ranking contract |
| Add `ScoreComponents` to response | PR3 `find_semantic.py` | Can include `lexical_match` via qualified_name substring boost — no Tantivy needed |
| Symbol-name Tantivy schema + population | Future (post-PR6) | Only if dense-only quality is demonstrably insufficient on live golden matrix |
| Hybrid RRF evaluation | Future (post Tantivy schema) | Populate dev-matrix table above before committing |

---

## Files in scope for PR3 (confirmed by this decision)

| File | Role |
|------|-------|
| `services/palace-mcp/src/palace_mcp/code/find_semantic.py` | Ranking/filtering changes land here |
| `services/palace-mcp/src/palace_mcp/code/semantic_contract.py` | `ScoreComponents` wiring, no new modules |
| `services/palace-mcp/tests/code/test_find_semantic.py` | Unit tests for ranking/normalization |
| `services/palace-mcp/tests/code/test_semantic_search_contract.py` | Contract type tests |
| `services/palace-mcp/tests/integration/test_find_semantic_search_tool.py` | MCP wire tests |

No new module in `code/semantic/` or `code/sparse/`. Sparse implementation, if
ever warranted, lands in `extractors/foundation/tantivy_bridge.py` (new method)
and is wired via `find_semantic.py`.
