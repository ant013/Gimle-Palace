## Phase 3.1 — Mechanical Review: GIM-77 Bridge Extractor

**Branch:** `feature/GIM-77-bridge-extractor`
**Head commit:** `1626e93` — `feat(palace-mcp): GIM-77 bridge extractor — project CM facts into Graphiti`

### Tool output

```
$ uv run ruff check src/ tests/
All checks passed!

$ uv run mypy src/
Success: no issues found in 25 source files

$ uv run pytest tests/extractors/unit/ -q
49 passed in 2.14s

$ uv run pytest tests/extractors/integration/ --co -q
4 tests collected (not executed — requires Docker/Neo4j)
```

---

## Findings

### CRITICAL (blocks merge)

1. **`tests/extractors/integration/test_codebase_memory_bridge_integration.py:47` — `_fake_cm` signature mismatch.**
   The fake defines `async def _call(tool: str, **kwargs: Any)` but the real `_call_cm` signature is `(tool: str, arguments: dict | None = None)`. Bridge calls `_call_cm("search_graph", {"label": "File", ...})` with a positional `arguments` dict — but the fake captures it as `**kwargs`, so `kwargs = {"label": "File", ...}` instead of the expected `arguments={"label": ...}`. The fake's routing logic never sees the tool arguments — silently returns `{}` for all calls.
   **Should be:** `async def _call(tool: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:`
   **Rule:** CLAUDE.md Testing — testcontainers for Neo4j integration, no silent-failure patterns.

2. **`tests/extractors/integration/test_codebase_memory_bridge_integration.py:48-53` — tool names in fake don't match bridge's actual calls.**
   Fake routes on `"palace.code.get_nodes"`, `"palace.code.get_file_nodes"`, `"palace.code.get_edges"`, `"palace.code.get_architecture"`.
   Bridge actually calls: `"search_graph"`, `"query_graph"`, `"get_architecture"`.
   Only `"get_architecture"` accidentally matches. All other branches return `{}` silently — tests pass vacuously.
   **Should be:** Match against `"search_graph"`, `"query_graph"`, `"get_architecture"` as used in the bridge implementation.
   **Rule:** CLAUDE.md Testing — behavioral coverage > line coverage.

3. **Integration tests were never run.** PythonEngineer reported "skipped locally, Docker not running" — but even with Docker, both bugs above would cause all 4 tests to fail. These tests are untested tests.
   **Rule:** CLAUDE.md Testing — no silent-failure patterns in new code.

### WARNING

1. **`codebase_memory_bridge.py:208-212` — `_call_cm` returns `{}` silently on CM session=None and on error.**
   When `code_router._cm_session is None` returns `{}` without logging. When `result.isError` returns `{}` without logging. Caller cannot distinguish "CM returned empty" from "CM is down".
   **Should be:** At minimum `logger.warning(...)` on both paths.
   **Rule:** CLAUDE.md Python — custom exception hierarchy, no bare except without logger.

2. **`codebase_memory_bridge.py:312,629` — Cypher string interpolation instead of parameterized queries.**
   `f"MATCH (f:File) WHERE f.project = '{ctx.project_slug}'"` — `project_slug` is internal so injection risk is low, but parameterized queries (`$slug`) are the standard pattern.
   **Should be:** `"MATCH (f:File) WHERE f.project = $slug"` with `{"slug": ctx.project_slug}`.
   **Rule:** OWASP injection prevention; codebase convention.

3. **`codebase_memory_bridge.py:740` — private attribute access `graphiti.driver._async_driver.session()`.**
   Fragile — breaks on graphiti-core upgrades without notice.

4. **`codebase_memory_bridge.py:175-176` — `except (FileNotFoundError, json.JSONDecodeError, KeyError): pass`.**
   Corrupted state file resets to empty with no warning — could cause full re-sync flood without operator awareness.
   **Should be:** `logger.warning("bridge state file corrupt, resetting: %s", e)`.

5. **Missing planned integration tests.** Plan specified more tests; only 4 implemented. Missing: `test_cross_resolve_symbol_to_cm`, `test_file_modification_incremental_update`, `test_bridge_health_reporting`.
   **Rule:** Plan-first discipline — plan steps match reality.

6. **`health.py` imports private `_load_state` from bridge extractor.** Cross-module import of private function. Should be public or expose a health accessor.

### NOTE

1. **Co-Authored-By** in commit `1626e93`: `Claude Sonnet 4.6 <noreply@anthropic.com>` — should be `Paperclip <noreply@paperclip.ing>`.

2. **4 deleted spec files** (`docs/superpowers/specs/2026-04-19-*`) are from GIM-79 merge landing on develop after the feature branch was cut. Branch divergence artifact, not scope creep. No action needed.

---

## Compliance checklist

### Python / FastAPI
- [x] Type hints on all functions — mypy --strict passes (0 errors, 25 source files)
- [x] Async everywhere I/O happens — all CM calls, Neo4j writes are async
- [x] httpx.AsyncClient reused via DI — N/A, CM calls via MCP session not HTTP
- [N/A] asyncio.create_task stored in set — no fire-and-forget tasks
- [x] Pydantic v2 BaseModel — BridgeHealthInfo in schema.py:70, ConfigDict(extra="forbid")
- [x] BaseSettings for config — no new config keys
- [x] DI via FastAPI Depends() — extractor in registry.py, no global singletons added
- [ ] Custom exception hierarchy, no bare except without logger — BLOCKER: _call_cm:208-212 returns {} silently; _load_state:175 swallows exceptions with pass
- [x] uv.lock committed — no deps changed
- [x] ruff check + ruff format pass — All checks passed!

### Docker / Compose
- [N/A] All items — no Docker/Compose changes in this PR

### MCP protocol
- [x] Tool inputs validated by Pydantic v2 — BridgeHealthInfo validates health output
- [x] Error responses via MCP error envelope — ExtractorStats with success=False
- [N/A] Tool names unique — no new MCP tools; bridge is internal extractor
- [N/A] Long-running streaming — bridge is synchronous within tool call

### Testing
- [N/A] Bug-case failing test — new feature, not a fix
- [x] pytest-asyncio for async tests — @pytest.mark.asyncio on all, asyncio_mode="auto"
- [ ] testcontainers for Neo4j integration — BLOCKER: 4 integration tests exist but are broken (signature + tool name mismatch) and never executed
- [ ] No silent-failure patterns — BLOCKER: _call_cm returns {} silently; _fake_cm masks failures
- [x] Behavioral coverage > line coverage — 20 unit tests cover all 10 projection rules, incremental skip, derived layer, health

### Code discipline (Karpathy)
- [x] No scope creep — all changes trace to GIM-77 tasks
- [x] No speculative features — implements exactly the spec projection rules
- [x] No drive-by improvements — no unrelated changes
- [x] Success criteria defined — in issue body acceptance section and plan file

### Plan-first discipline
- [x] Plan file exists — docs/superpowers/plans/2026-04-25-GIM-77-bridge-extractor.md
- [x] PR description references plan — PR not yet open, will verify at Phase 4.2
- [ ] Plan steps marked done — plan checkboxes not updated to reflect completion
- [N/A] Plan changed mid-flight — no scope change evidence

### Git workflow
- [x] Feature branch from develop — feature/GIM-77-bridge-extractor
- [x] Conventional commit — feat(palace-mcp): GIM-77 bridge extractor
- [ ] Co-Authored-By Paperclip — commit uses Claude Sonnet 4.6 instead
- [x] No force push on develop/main — clean history

---

## Verdict: REQUEST CHANGES

**3 CRITICAL findings block merge.** All relate to integration tests that are broken and were never verified:

1. Fix `_fake_cm` signature: `(tool, **kwargs)` -> `(tool, arguments=None)`
2. Fix tool names in fake: `palace.code.get_nodes` -> `search_graph`, etc.
3. Run integration tests against real Neo4j (Docker) and confirm they pass.

**6 WARNINGs** should be addressed in the same fix round:
- Add logging to `_call_cm` silent-failure paths
- Use parameterized Cypher queries instead of f-string interpolation
- Fix `_load_state` silent exception swallowing
- Make `_load_state`/`_BridgeState` public or expose a health accessor
- Add missing planned integration tests
- Fix Co-Authored-By trailer

@PythonEngineer please fix the CRITICAL and WARNING findings. Integration tests must actually pass against real Neo4j before re-submitting for review.
