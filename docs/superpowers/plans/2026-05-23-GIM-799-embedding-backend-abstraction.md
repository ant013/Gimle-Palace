# GIM-799 Plan: EmbeddingBackend Abstraction

## Goal

Add the minimal embedding backend interface and dispatcher foundation for later G0.5 semantic embedding slices.

## Assumptions

- This slice implements only the interface/dispatcher foundation.
- Qodo model loading, OpenAI/Voyage adapters, Neo4j vector indexes, embedding population, and semantic MCP tools are out of scope.
- Existing unrelated worktree changes are not part of this slice and should not be reformatted or reverted.

## Acceptance Criteria

- `services/palace-mcp/src/palace_mcp/embeddings/backend.py` exports an `EmbeddingBackend` protocol with:
  - `embed_text(text: str) -> list[float]`
  - `embed_batch(texts: list[str]) -> list[list[float]]`
- Backend selection is pluggable by name without hard-coding model infrastructure into this slice.
- A focused unit test covers protocol conformance and dispatcher selection behavior.

## Steps

1. Add focused tests first.
   - Owner: CXPythonEngineer
   - Paths: `services/palace-mcp/tests/embeddings/test_backend.py`
   - Check: test defines two fake backends, verifies `EmbeddingBackend` runtime conformance, verifies selected backend is used for `embed_text` and `embed_batch`, and verifies no concrete Qodo/OpenAI model code is required.

2. Implement the minimal package surface.
   - Owner: CXPythonEngineer
   - Paths:
     - `services/palace-mcp/src/palace_mcp/embeddings/backend.py`
     - `services/palace-mcp/src/palace_mcp/embeddings/__init__.py`
   - Check: implementation stays limited to the protocol and a small dispatcher helper, for example a name-to-backend mapping resolver. Do not add model dependencies, Neo4j calls, config loading, async machinery, or future adapter scaffolding.

3. Run focused verification.
   - Owner: CXPythonEngineer
   - Command: `cd services/palace-mcp && uv run pytest tests/embeddings/test_backend.py`
   - Check: focused pytest passes.

4. Handoff for review.
   - Owner: CXPythonEngineer -> CXCodeReviewer
   - Check: PR targets `develop`, references this plan, includes focused pytest output, and notes that later G0.5 slices remain untouched.

## Review Notes

- Prefer a small function or tiny dispatcher type over a registry framework.
- Do not broaden the protocol to roadmap-level `dim`, `embed_query`, or `embed_documents`; GIM-799 acceptance explicitly names `embed_text` and `embed_batch`.
- Do not import optional embedding libraries in this slice.
