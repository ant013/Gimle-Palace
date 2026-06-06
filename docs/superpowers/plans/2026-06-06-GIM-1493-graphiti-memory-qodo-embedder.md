# GIM-1493 Plan: Switch Graphiti Memory Embedder to Local Qodo

## Grounding

- Repository state: `feature/GIM-1497-symbol-index-swift-last-seen` at `33417c3ae349197a36c04392ca039ae69113c20d` on 2026-06-06.
- Verified live Neo4j data via in-container `cypher-shell` on 2026-06-06:
  - `(:Decision:Entity)` count = `15`, `name_embedding` dim = `1024`
  - `(:Episode:Entity)` count = `3`, `name_embedding` dim = `1024`
  - `fact_embedding` count = `0` for those labels
- Verified local code/tests on 2026-06-06:
  - `tests/memory/test_decide.py` expects `name_embedding_dim == 1024`
  - Graphiti `EmbedderClient` default `EMBEDDING_DIM` is `1024`
  - Existing Neo4j vector index in this checkout is only `symbol_embedding_idx` on `:Symbol.embedding` with `1536` dimensions

## Goal

Replace Graphiti memory writes from the OpenAI embedder path with a local Qodo-backed adapter, reusing the existing palace embedder singleton and preserving `noop` and `openai` selectors as explicit fallbacks.

## Assumptions

- The wake payload's `2048`-dimension note does not match the current checkout or live data; this slice should follow the verified local `1024`-dimension contract unless a reviewer points to newer contradictory evidence.
- This slice covers Graphiti memory writes only. `embedding_symbol` and the existing `:Symbol.embedding` schema stay unchanged.
- No separate memory vector index migration is required in this checkout because the current memory labels already store `1024`-dim embeddings and there is no dedicated Graphiti memory vector index to split.
- Sharing the existing Qodo backend instance through `palace_mcp.embeddings` is preferable to constructing a second `QodoEmbeddingBackend()` inside `graphiti_runtime`.
- `OPENAI_API_KEY` remains required today because Graphiti still needs an `OpenAIClient` stub at construction time; this slice only removes the embedding dependency from the hot write path.

## Acceptance Criteria

- `services/palace-mcp/src/palace_mcp/graphiti_runtime.py` exposes a Graphiti-compatible Qodo adapter implementing async `create(...)` and `create_batch(...)`.
- `build_graphiti(settings)` selects the embedder by setting, defaulting to `qodo`, while preserving `noop` and `openai`.
- The Qodo Graphiti adapter reuses the existing palace embedding dispatcher/backend cache instead of loading a second model instance.
- Focused tests cover:
  - adapter `create`/`create_batch` behavior
  - `build_graphiti` selector wiring
  - `palace.memory.decide` write path returning a non-zero embedding dimension through the local embedder path without an OpenAI embedding call
- Focused verification passes:
  - `cd services/palace-mcp && uv run pytest tests/test_graphiti_runtime*.py tests/memory/test_*decide* -v`

## Steps

1. Add the smallest config/runtime test coverage first.
   - Paths:
     - `services/palace-mcp/tests/test_gim75_unit.py` or new focused `tests/test_graphiti_runtime*.py`
   - Check: tests prove `build_graphiti()` defaults to `qodo`, still accepts explicit `openai` / `noop`, and passes the expected embedder instance into `Graphiti(...)`.

2. Implement a Graphiti-compatible Qodo adapter that reuses the existing singleton.
   - Paths:
     - `services/palace-mcp/src/palace_mcp/graphiti_runtime.py`
     - `services/palace-mcp/src/palace_mcp/embeddings/__init__.py` only if a tiny accessor is needed
   - Check: adapter stays thin, converts Graphiti async calls into the existing synchronous backend contract, and does not duplicate model-loading logic.

3. Add the minimal setting surface for embedder selection.
   - Paths:
     - `services/palace-mcp/src/palace_mcp/config.py`
     - focused tests for settings/runtime wiring
   - Check: `palace_memory_embedder` defaults to `qodo`; accepted values are limited to the requested selectors.

4. Cover the decide write path end to end with the local embedder.
   - Paths:
     - `services/palace-mcp/tests/memory/test_decide.py`
     - a new focused integration/unit test near existing Graphiti runtime tests if needed
   - Check: the test exercises the real save helper path far enough to prove the local embedder is used and returns `name_embedding_dim == 1024` without invoking OpenAI embedding APIs.

5. Run focused verification.
   - Commands:
     - `cd services/palace-mcp && uv run pytest tests/test_graphiti_runtime*.py tests/memory/test_*decide* -v`
     - `cd services/palace-mcp && uv run ruff check src/palace_mcp/graphiti_runtime.py src/palace_mcp/config.py tests/test_graphiti_runtime*.py tests/memory/test_*decide*`
   - Check: focused tests and lint pass; expand to mypy only if the adapter/settings change adds public typing surface that needs it.

## Review Notes

- Keep the change surgical: no semantic lookup redesign, no symbol-index schema migration, no Graphiti schema refactor.
- If the adapter needs a new accessor in `palace_mcp.embeddings`, prefer a one-line cache getter over a new registry abstraction.
- If reviewer evidence shows a newer live environment where Qodo truly returns `2048`, stop and reopen the migration question before changing vector schema in this slice.
