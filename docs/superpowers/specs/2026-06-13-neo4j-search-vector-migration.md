# Neo4j SEARCH Vector Migration Spec

Date: 2026-06-13
Branch: `fix/neo4j-search-vector-migration`
Base: `origin/develop` at `818ae53e`

## Purpose

Migrate `palace.code.semantic_search` candidate retrieval away from the
deprecated Neo4j vector procedure:

```cypher
CALL db.index.vector.queryNodes('symbol_embedding_idx', $query_k, $embedding)
YIELD node, score
```

to Cypher 25 `SEARCH`:

```cypher
MATCH (s:Symbol)
  SEARCH s IN (
    VECTOR INDEX symbol_embedding_idx
    FOR $embedding
    LIMIT $query_k
  ) SCORE AS score
```

This removes the live Neo4j deprecation warning observed during the native
semantic smoke and keeps the semantic tool aligned with the current Neo4j vector
index API.

## Background

Official Neo4j documentation states:

- `SEARCH` is a Cypher 25 feature introduced in Neo4j 2026.01:
  https://neo4j.com/docs/cypher-manual/current/clauses/search/
- Vector index docs mark `db.index.vector.queryNodes` and
  `db.index.vector.queryRelationships` deprecated as of Neo4j 2026.04 in favor
  of `SEARCH`:
  https://neo4j.com/docs/cypher-manual/current/indexes/semantic-indexes/vector-indexes/
- The deprecations page records the same replacement:
  https://neo4j.com/docs/cypher-manual/current/deprecations-additions-removals-compatibility/

Native read-only probe against `/Users/ant013/Android/Gimle-Palace-native/.env`
confirmed the current local Neo4j accepts the intended syntax:

```text
MATCH (sample:Symbol)
WHERE sample.embedding IS NOT NULL
WITH sample.embedding AS query_vector
LIMIT 1
MATCH (s:Symbol)
  SEARCH s IN (
    VECTOR INDEX symbol_embedding_idx
    FOR query_vector
    LIMIT 1
  ) SCORE AS score
RETURN s.qualified_name AS qualified_name, score AS score

=> {'rows': 1, 'first_has_score': True}
```

The probe also confirmed `SCORE AS score` is required; `score` is not defined
automatically by the `SEARCH` subclause.

## Current Implementation

Authoritative semantic-search implementation remains the boundary locked by
`docs/superpowers/specs/2026-05-27-GIM-915-semantic-search-arch-lock.md`:

- `services/palace-mcp/src/palace_mcp/code/find_semantic.py`
  - `_VECTOR_QUERY`
  - `_vector_search()`
  - `semantic_search()`
- `services/palace-mcp/tests/code/test_find_semantic.py`
- `services/palace-mcp/tests/code/test_semantic_filtering.py`
- `services/palace-mcp/tests/code/test_path_dual_read_queries.py`
- `services/palace-mcp/tests/integration/test_find_semantic_search_tool.py`

The foundation vector index remains:

```text
symbol_embedding_idx on :Symbol.embedding, cosine, 1536 dimensions
```

No schema/index DDL change is expected.

## Assumptions

- Runtime native Neo4j is Cypher 25 / Neo4j 2026.01+ capable. The native probe
  above confirms this for the current local database.
- MCP deployment targets use the same native Neo4j generation. This migration
  intentionally does not add an older-Neo4j fallback unless implementation
  testing proves iMac/runtime Neo4j is older than local native Neo4j.
- `symbol_embedding_idx` remains a fixed trusted index identifier. Neo4j
  `VECTOR INDEX index_name` syntax expects an index identifier, not a runtime
  parameter, so no user-supplied index name is introduced.
- Existing semantic ranking, filtering, over-fetch, per-project fanout, context
  hydration, and result contract should remain unchanged.

## Scope

In scope:

- Replace `_VECTOR_QUERY` procedure call with `MATCH ... SEARCH ... SCORE AS`.
- Preserve parameters:
  - `$embedding`
  - `$query_k`
  - `$group_ids`
  - `$include_deprecated`
- Preserve result fields:
  - `group_id`
  - `qualified_name`
  - `kind`
  - `file_path`
  - `line_start`
  - `line_end`
  - `module_name`
  - `source_scope`
  - `embedding_input_hash`
  - `commit_sha`
  - `score`
- Update unit-test fakes that currently detect `"queryNodes('symbol_embedding_idx'"`.
- Add a query-shape regression test asserting:
  - `SEARCH s IN` is present.
  - `VECTOR INDEX symbol_embedding_idx` is present.
  - `SCORE AS score` is present.
  - `db.index.vector.queryNodes` is absent.
- Run native smoke to confirm no `db.index.vector.queryNodes` deprecation warning
  remains in the semantic path.

Out of scope:

- Hybrid dense/sparse retrieval.
- Ranking formula changes.
- New vector indexes.
- Changing embedding model or dimensions.
- Reworking deprecated Neo4j APIs outside semantic vector retrieval.
- Merging the separate smoke-followup branch. If that branch lands first, this
  branch should rebase and keep its migration limited to the vector query shape.

## Proposed Query Shape

Target `_VECTOR_QUERY`:

```cypher
MATCH (s:Symbol)
  SEARCH s IN (
    VECTOR INDEX symbol_embedding_idx
    FOR $embedding
    LIMIT $query_k
  ) SCORE AS score
WHERE s.group_id IN $group_ids
  AND ($include_deprecated OR NOT s:Deprecated)
RETURN
  s.group_id AS group_id,
  s.qualified_name AS qualified_name,
  s.kind AS kind,
  s.file_path AS file_path,
  s.line_start AS line_start,
  s.line_end AS line_end,
  s.module_name AS module_name,
  s.source_scope AS source_scope,
  s.embedding_input_hash AS embedding_input_hash,
  s.commit_sha AS commit_sha,
  score AS score
ORDER BY score DESC
```

Implementation note: if this branch is rebased after
`fix/extractor-semantic-validity-audit`, preserve that branch's dynamic optional
property reads for `line_start` and `line_end`.

## Alternatives Considered

1. Keep `db.index.vector.queryNodes` until removal.
   - Rejected: live smoke already emits deprecation warnings, making semantic
     smoke noisy and hiding real schema problems.

2. Add runtime fallback: try `SEARCH`, then retry `queryNodes`.
   - Not preferred initially: fallback doubles query surface and can hide a
     stale deployment. Add only if iMac/native runtime verification proves a
     supported target lacks Cypher 25 `SEARCH`.

3. Rewrite retrieval into a new semantic module.
   - Rejected by the GIM-915 architecture lock. Candidate retrieval stays in
     `find_semantic.py`.

## Acceptance Criteria

- `palace.code.semantic_search` returns the same response shape as before.
- Unit tests no longer rely on `queryNodes('symbol_embedding_idx'`.
- Query-shape tests prove `SEARCH` is used and `db.index.vector.queryNodes` is
  not present in `_VECTOR_QUERY`.
- Native semantic smoke against `/Users/ant013/Android/Gimle-Palace-native/.env`
  returns non-empty results for `uw-ios-app` or another embedded project.
- The semantic native smoke output contains no Neo4j deprecation warning for
  `db.index.vector.queryNodes`.
- Existing over-fetch behavior remains intact:
  - single-project candidate limit
  - multi-project per-project fanout
  - scope filtering after retrieval
- Full `services/palace-mcp` checks pass or any environment-gated skips are
  explained.

## Verification Plan

Local targeted:

```bash
cd services/palace-mcp
uv run pytest tests/code/test_find_semantic.py \
  tests/code/test_semantic_filtering.py \
  tests/code/test_path_dual_read_queries.py \
  tests/integration/test_find_semantic_search_tool.py -q
uv run ruff check src/palace_mcp/code/find_semantic.py \
  tests/code/test_find_semantic.py \
  tests/code/test_semantic_filtering.py \
  tests/code/test_path_dual_read_queries.py
uv run ruff format --check src/palace_mcp/code/find_semantic.py \
  tests/code/test_find_semantic.py \
  tests/code/test_semantic_filtering.py \
  tests/code/test_path_dual_read_queries.py
```

Full service gate:

```bash
cd services/palace-mcp
uv run ruff check
uv run ruff format --check
uv run mypy src/
uv run pytest
```

Native smoke:

```bash
cd services/palace-mcp
uv run python <temporary read-only smoke script>
```

Smoke assertions:

- Neo4j connectivity succeeds through native `.env`.
- `semantic_search(project="uw-ios-app", query="swap view transaction confirmation balance", limit=3, include_context=False)` returns `ok=true`.
- `len(result) > 0`.
- Captured stderr/stdout contains no `db.index.vector.queryNodes is deprecated`.

## Open Questions

- Does the iMac runtime Neo4j version match local native Neo4j closely enough
  for `SEARCH`? If not, implementation must add an explicit compatibility
  decision before shipping.
- Should the project keep old documentation examples that mention
  `queryNodes`, or update only runtime/test code in this migration? Recommended:
  update only runtime/test docs directly touched by the migration, leave older
  historical specs unchanged.

