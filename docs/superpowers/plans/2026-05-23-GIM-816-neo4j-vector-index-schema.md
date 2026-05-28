# GIM-816 Plan: Neo4j Vector Index Schema

## Goal

Add the `symbol_embedding_idx` Neo4j vector index declaration to the foundation schema path so later G0.5 embedding slices can persist and query `:Symbol.embedding` vectors.

## Assumptions

- This slice only adds schema representation and schema creation for the vector index.
- Existing schema creation remains idempotent with `IF NOT EXISTS`.
- The vector index uses `1536` dimensions and cosine similarity exactly as the roadmap states.
- Embedding population, semantic search MCP tools, cascade behavior, and validation-matrix work are out of scope.
- Existing unrelated worktree changes are not part of this slice and should not be reformatted or reverted.

## Acceptance Criteria

- `services/palace-mcp/src/palace_mcp/extractors/foundation/schema.py` represents `symbol_embedding_idx` for `:Symbol.embedding`.
- Generated Cypher creates a Neo4j vector index with `vector.dimensions: 1536` and `vector.similarity_function: 'cosine'`.
- The existing `ensure_custom_schema` / `_create_schema` path emits the vector-index creation statement.
- Focused tests prove schema declaration, generated Cypher, and schema creation behavior.
- Related UNIQUE/index setup stays limited to what this schema slice requires.

## Steps

1. Add focused schema tests first.
   - Owner: CXPythonEngineer
   - Paths:
     - `services/palace-mcp/tests/extractors/unit/test_schema.py`
   - Check: tests assert `EXPECTED_SCHEMA` includes `symbol_embedding_idx` on `Symbol.embedding`, generated Cypher contains `CREATE VECTOR INDEX`, `IF NOT EXISTS`, `vector.dimensions`, `1536`, `vector.similarity_function`, and `cosine`.

2. Add a creation-path test for vector indexes.
   - Owner: CXPythonEngineer
   - Paths:
     - `services/palace-mcp/tests/extractors/unit/test_schema.py`
   - Depends on: step 1
   - Check: a fake async session passed to `_create_schema` records the vector-index statement, proving the existing schema bootstrap path emits it.

3. Implement the smallest schema representation change.
   - Owner: CXPythonEngineer
   - Paths:
     - `services/palace-mcp/src/palace_mcp/extractors/foundation/schema.py`
   - Check: add only the minimal fields/helper needed to express a Neo4j vector index and generate the exact `symbol_embedding_idx` statement. Keep existing range indexes and fulltext indexes behavior unchanged.

4. Add the `symbol_embedding_idx` declaration.
   - Owner: CXPythonEngineer
   - Paths:
     - `services/palace-mcp/src/palace_mcp/extractors/foundation/schema.py`
   - Depends on: step 3
   - Check: declaration is scoped to label `Symbol`, property `embedding`, dimensions `1536`, and similarity `cosine`.

5. Run focused verification.
   - Owner: CXPythonEngineer
   - Depends on: steps 1-4
   - Commands:
     - `cd services/palace-mcp && uv run pytest tests/extractors/unit/test_schema.py`
     - `cd services/palace-mcp && uv run ruff check src/palace_mcp/extractors/foundation/schema.py tests/extractors/unit/test_schema.py`
   - Check: focused tests and lint pass. Run mypy only if the implementation changes typed public shapes enough to warrant it.

6. Open PR and hand off for mechanical review.
   - Owner: CXPythonEngineer -> CXCodeReviewer
   - Check: PR targets `develop`, references this plan, includes focused verification output, and states that later G0.5 rows remain untouched.

## Review Notes

- Prefer a tiny extension of the existing schema spec/emission flow over a general index framework.
- Do not add Neo4j driver calls outside the existing `_create_schema` loop.
- Do not implement embedding storage, backfill, semantic lookup, or validation matrix behavior in this slice.
- If the implementation adds a separate vector-index collection, reviewers should verify `SchemaDefinition.all_names()` and drift detection include the vector index name consistently.
