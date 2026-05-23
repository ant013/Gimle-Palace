# GIM-813 Plan: Qodo Embed Self-Hosted Runner

## Goal

Add a concrete self-hosted `EmbeddingBackend` for `Qodo/Qodo-Embed-1-1.5B` without starting later G0.5 semantic-search work.

## Assumptions

- GIM-799 is the foundation for this slice: `EmbeddingBackend` and `EmbeddingBackendDispatcher` already exist in `services/palace-mcp/src/palace_mcp/embeddings/backend.py`.
- The implementation can use an in-process Python backend or a tiny local HTTP wrapper, but the Python abstraction must expose the same synchronous `embed_text` and `embed_batch` contract.
- Unit tests must not download or load the full Hugging Face model by default.
- Any heavyweight model dependency is acceptable only if it is required to load the local Qodo backend cleanly and is imported lazily by the backend path.
- Neo4j vector schema, population extractors, semantic MCP tools, cascade behavior, and validation-matrix work are out of scope.

## Acceptance Criteria

- `services/palace-mcp/src/palace_mcp/embeddings/` exports a concrete Qodo backend that satisfies `EmbeddingBackend`.
- `embed_text(text: str) -> list[float]` returns the single embedding for one input.
- `embed_batch(texts: list[str]) -> list[list[float]]` returns one embedding per input in input order.
- Dispatcher behavior can select the Qodo backend by name without special-casing Qodo in caller code.
- Focused tests cover backend contract and dispatcher registration/dispatch behavior without requiring model download in CI.
- A smallest-practical local smoke documents measured latency or an explicit skip path for environments without the model/dependency cache.

## Steps

1. Add Qodo backend contract tests first.
   - Owner: CXPythonEngineer
   - Paths:
     - `services/palace-mcp/tests/embeddings/test_qodo_backend.py`
   - Check: tests use an injected fake encoder/model object to prove `embed_text`, `embed_batch`, ordering, and float-list conversion without network access or model download.

2. Implement the smallest concrete backend.
   - Owner: CXPythonEngineer
   - Paths:
     - `services/palace-mcp/src/palace_mcp/embeddings/qodo.py`
     - `services/palace-mcp/src/palace_mcp/embeddings/__init__.py`
     - dependency/config files only if required for local model loading
   - Check: implementation remains a thin `EmbeddingBackend` adapter around the local model runner. Lazy-load optional model libraries inside the backend path. Do not add async workers, Neo4j calls, embedding persistence, or future provider registry scaffolding.

3. Wire Qodo through existing dispatch behavior.
   - Owner: CXPythonEngineer
   - Paths:
     - `services/palace-mcp/tests/embeddings/test_qodo_backend.py`
     - `services/palace-mcp/src/palace_mcp/embeddings/qodo.py`
   - Depends on: step 2
   - Check: a focused test creates an `EmbeddingBackendDispatcher` with `{"qodo": qodo_backend}` and verifies selected/default dispatch calls the Qodo backend through the existing abstraction.

4. Add local latency smoke with a CI-safe skip.
   - Owner: CXPythonEngineer
   - Paths:
     - `services/palace-mcp/tests/embeddings/test_qodo_backend_smoke.py` or a narrowly scoped script under `services/palace-mcp/scripts/`
   - Depends on: step 2
   - Check: smoke only runs when explicitly enabled by an environment variable and skips with a clear reason otherwise. When enabled on an M-series Mac with local model availability, it embeds a roughly 200-token batch and records whether latency is `<=500ms`.

5. Run focused verification and open PR.
   - Owner: CXPythonEngineer
   - Depends on: steps 1-4
   - Commands:
     - `cd services/palace-mcp && uv run pytest tests/embeddings/test_backend.py tests/embeddings/test_qodo_backend.py`
     - optional local smoke command from step 4, with output pasted or skip reason documented
   - Check: PR targets `develop`, references this plan, includes focused pytest output and smoke evidence/skip reason, and states that later G0.5 rows remain untouched.

## Review Notes

- Prefer an injected encoder/model seam over mocking global imports; this keeps tests small and avoids model downloads.
- Do not modify the existing `EmbeddingBackend` protocol unless implementation proves the Qodo model cannot satisfy it.
- Do not make the dispatcher responsible for constructing model dependencies unless a current call site already needs that factory.
- If a new dependency is required, reviewers should verify it is justified by the Qodo backend and is not imported during unrelated package import or unit tests.
