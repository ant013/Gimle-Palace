# Neo4j Vector Search Compatibility Migration Spec

Date: 2026-06-13
Branch: `fix/neo4j-search-vector-migration`
Base: `origin/develop` at `818ae53e`
Status: revised after audit

## Purpose

Make `palace.code.semantic_search` use Cypher 25 `SEARCH` on the MacBook native
Neo4j runtime, while preserving the existing `db.index.vector.queryNodes` path
for iMac Docker Neo4j 5.26.

This is not a SEARCH-only migration. The deployment reality is mixed:

- MacBook development/ingest runtime: native Neo4j 2026.x, SEARCH works and the
  old procedure emits a deprecation warning.
- iMac production/runtime path: Docker Neo4j 5.26-compatible. Native MPS runtime
  is not viable on the Intel iMac, and `SEARCH` is not available there.

Therefore the safe goal is:

- native MacBook: prefer `CYPHER 25 ... SEARCH ... SCORE AS score`;
- iMac Docker: fallback to `db.index.vector.queryNodes(...)`;
- no semantic response-shape, ranking, filtering, or over-fetch contract change.

## Runtime Facts

Repo evidence:

- `docker-compose.yml`: `neo4j:5.26.0`
- `docker-compose.server.yml`: `neo4j:5.26.0`
- `docs/runbooks/native-macos-palace-mcp.md` says native MPS deploy is for
  Apple Silicon dev hosts and explicitly says not to use it on Intel iMac.

Operator clarification on 2026-06-13:

- MacBook is native.
- iMac cannot use the native runtime path.

Spec consequence:

- A SEARCH-only patch is a ship-blocker because it would hard-fail on iMac
  Docker Neo4j 5.26.
- Fallback is required, not optional.

## Neo4j Docs

Official Neo4j documentation:

- `SEARCH` is a Cypher 25 feature introduced in Neo4j 2026.01:
  https://neo4j.com/docs/cypher-manual/current/clauses/search/
- Vector index docs mark `db.index.vector.queryNodes` and
  `db.index.vector.queryRelationships` deprecated as of Neo4j 2026.04 in favor
  of `SEARCH`:
  https://neo4j.com/docs/cypher-manual/current/indexes/semantic-indexes/vector-indexes/
- The deprecations page records the same replacement:
  https://neo4j.com/docs/cypher-manual/current/deprecations-additions-removals-compatibility/

Trusted-contract probe on MacBook native Neo4j confirmed:

```cypher
CYPHER 25
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
```

Result:

```text
{'rows': 1, 'first_has_score': True}
```

The probe also confirmed `SCORE AS score` is required; `score` is not defined
automatically by `SEARCH`.

## Parity Evidence

Native MacBook parity probe compared the same sampled `uw-ios-app` embedding via
legacy `queryNodes` and `CYPHER 25 ... SEARCH`, `k=10`:

```text
old_count=10
new_count=10
same_order=true
max_abs_score_delta=0.0
all_scores_in_0_1=true
```

EXPLAIN probe for the SEARCH query produced:

```text
NodeVectorIndexSearch@neo4j
SEARCH s IN (VECTOR INDEX symbol_embedding_idx FOR query_vector LIMIT $k) SCORE AS score
```

This is enough evidence to proceed with SEARCH on native MacBook, but not enough
to remove the legacy path required by iMac Docker.

## Current Implementation Boundary

Authoritative semantic-search implementation remains the boundary locked by
`docs/superpowers/specs/2026-05-27-GIM-915-semantic-search-arch-lock.md`.

Affected runtime file:

- `services/palace-mcp/src/palace_mcp/code/find_semantic.py`

Affected tests:

- `services/palace-mcp/tests/code/test_find_semantic.py`
- `services/palace-mcp/tests/code/test_semantic_filtering.py`
- `services/palace-mcp/tests/code/test_ranking_contract.py`
- `services/palace-mcp/tests/code/test_path_dual_read_queries.py`
- `services/palace-mcp/tests/integration/test_find_semantic_search_tool.py`

The foundation vector index stays unchanged:

```text
symbol_embedding_idx on :Symbol.embedding, cosine, 1536 dimensions
```

No schema/index DDL change is expected.

## Scope

In scope:

- Add a SEARCH query shape for Cypher 25 runtimes.
- Keep a legacy `queryNodes` query shape for Neo4j 5.26 compatibility.
- Use `CYPHER 25` prefix for the SEARCH query.
- Add runtime capability selection inside `_vector_search()`:
  - unknown capability: try SEARCH first;
  - SEARCH supported: cache and continue using SEARCH;
  - SEARCH syntax/client unsupported: cache and use legacy query;
  - fallback logs a one-time warning with sanitized runtime compatibility
    context;
  - unrelated errors must not be hidden by fallback.
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
- Update all query-dispatching test fakes that currently key on
  `queryNodes('symbol_embedding_idx'` or `"queryNodes"`.
- Add regression coverage for SEARCH path, fallback path, capability caching,
  and the literal index identifier.

Out of scope:

- Upgrading iMac/Docker Neo4j.
- Removing the legacy query while iMac remains on Neo4j 5.26.
- Hybrid dense/sparse retrieval.
- Ranking formula changes.
- New vector indexes.
- Changing embedding model or dimensions.
- Reworking deprecated Neo4j APIs outside semantic vector retrieval.

## Query Shapes

Preferred SEARCH query:

```cypher
CYPHER 25
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

Legacy fallback query:

```cypher
CALL db.index.vector.queryNodes('symbol_embedding_idx', $query_k, $embedding)
YIELD node, score
WITH node AS s, score
WHERE s:Symbol
  AND s.group_id IN $group_ids
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

Sibling-branch guard:

- If `fix/extractor-semantic-validity-audit` is merged/rebased first, preserve
  its dynamic optional property reads in both query shapes:

```cypher
properties(s)[$line_start_key] AS line_start,
properties(s)[$line_end_key] AS line_end
```

Do not paste the static `s.line_start` block over that fix.

## Compatibility Design

Recommended implementation:

- Introduce two constants:
  - `_VECTOR_SEARCH_QUERY`
  - `_VECTOR_LEGACY_QUERY`
- Keep `_vector_search()` as the only caller-facing helper.
- Add a module-level capability cache:
  - `None`: unknown, try SEARCH first.
  - `True`: use SEARCH directly.
  - `False`: use legacy `queryNodes` directly.
- On initial SEARCH failure, fallback only for Neo4j syntax/client errors that
  indicate unsupported `CYPHER 25`/`SEARCH`.
- Do not fallback for:
  - missing index;
  - missing parameters;
  - transaction timeout;
  - connection failures;
  - backend inconsistency;
  - data contract errors.
- Log one warning when falling back:
  - event: `semantic_search.vector_search.legacy_fallback`
  - include sanitized Neo4j error type/code;
  - do not log embeddings, secrets, or query text with vectors.

## Alternatives

1. Keep only `db.index.vector.queryNodes`.
   - Safe for iMac Docker 5.26, but leaves MacBook native smoke noisy.

2. SEARCH-only migration.
   - Rejected. It breaks iMac Docker Neo4j 5.26.

3. Capability-probe/fallback.
   - Accepted. It removes native deprecation noise where SEARCH exists and
     preserves production compatibility where it does not.

4. Upgrade iMac Docker Neo4j to 2026.x first.
   - Deferred. That is a separate runtime/store migration and should not be
     bundled into semantic-search query cleanup.

## Acceptance Criteria

- `palace.code.semantic_search` returns the same response shape as before.
- Native MacBook uses SEARCH and emits no `db.index.vector.queryNodes is
  deprecated` warning on the semantic path.
- iMac/Docker Neo4j 5.26 remains supported through legacy fallback.
- Unit tests cover:
  - SEARCH success path;
  - fallback on unsupported SEARCH/Cypher syntax;
  - no fallback for unrelated errors;
  - capability cache avoids retrying SEARCH after unsupported runtime is known;
  - literal `symbol_embedding_idx` is not caller-formatted.
- Query-shape tests prove:
  - SEARCH query uses `CYPHER 25`, `SEARCH s IN`,
    `VECTOR INDEX symbol_embedding_idx`, and `SCORE AS score`;
  - legacy query still contains `db.index.vector.queryNodes`;
  - there is no user-supplied vector index identifier.
- Native parity probe records:
  - top-K order comparison;
  - max score delta;
  - scores remain in `[0, 1]`.
- EXPLAIN/plan probe on native SEARCH contains `NodeVectorIndexSearch` or an
  equivalent vector-index-search operator for `symbol_embedding_idx`.
- Existing over-fetch behavior remains intact:
  - single-project candidate limit;
  - multi-project per-project fanout;
  - scope filtering after retrieval.
- If `fix/extractor-semantic-validity-audit` is merged/rebased into this branch,
  its optional-property warning fixes remain intact.

## Verification Plan

Targeted tests:

```bash
cd services/palace-mcp
uv run pytest tests/code/test_find_semantic.py \
  tests/code/test_semantic_filtering.py \
  tests/code/test_ranking_contract.py \
  tests/code/test_path_dual_read_queries.py \
  tests/integration/test_find_semantic_search_tool.py -q
```

Style/type/full gate:

```bash
cd services/palace-mcp
uv run ruff check
uv run ruff format --check
uv run mypy src/
uv run pytest
```

Native MacBook smoke:

```bash
cd services/palace-mcp
uv run python <temporary read-only smoke script>
```

Native smoke assertions:

- Neo4j connectivity succeeds through native `.env`.
- `semantic_search(project="uw-ios-app", query="swap view transaction confirmation balance", limit=3, include_context=False)` returns `ok=true`.
- `len(result) > 0`.
- Captured stderr/stdout contains no `db.index.vector.queryNodes is deprecated`.
- SEARCH-vs-legacy parity probe records top-K equality/score delta.
- EXPLAIN records a vector-index-search operator.

iMac/Docker compatibility:

- Preferred: run semantic smoke against actual iMac Docker Neo4j 5.26 and confirm
  legacy fallback returns results.
- If iMac smoke cannot be run in this turn, fallback behavior must still be
  covered by a unit test that simulates unsupported SEARCH syntax and verifies
  the legacy query returns results.

## Open Questions

- Should this branch wait for `fix/extractor-semantic-validity-audit` to merge,
  then rebase and preserve its dynamic optional-property reads? Recommended:
  yes, or explicitly port those reads into this branch before implementation
  review.
- Should historical docs that mention `queryNodes` be updated? Recommended:
  update only runtime/test docs touched by this migration; leave older historical
  specs unchanged unless a docs-cleanup task is opened.

