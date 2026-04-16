# GIM-28: FastMCP Best-Practices Refactor

**Date**: 2026-04-16  
**Branch**: `feature/GIM-28-fastmcp-refactor`  
**Source**: External FastMCP review (post-GIM-23), 3 surgical fixes.

---

## Findings → File Map

| Finding | Description | Files |
|---------|-------------|-------|
| F1 | Replace module-level `_driver` global + `set_driver()` with FastMCP `lifespan` + `Context` | `mcp_server.py`, `main.py` |
| F2 | Remove `[cli]` extra from `mcp` production dependency | `pyproject.toml`, `uv.lock` |
| F3 | `palace.health.status` must accept `ctx: Context` (natural from F1) | `mcp_server.py` |

Every line changed traces to one of F1/F2/F3. No new tools, no schema changes.

---

## Implementation Steps

### 1. F2 — `pyproject.toml`
- Change `mcp[cli]>=1.6` → `mcp>=1.6`
- Run `uv lock` to refresh lock file

### 2. F1 + F3 — `mcp_server.py`
- Add `PalaceContext` dataclass: `driver: AsyncDriver`
- Add `palace_lifespan(server: FastMCP) -> AsyncIterator[PalaceContext]` — creates/closes Neo4j driver
- Update `FastMCP(...)` call: add `lifespan=palace_lifespan`
- Remove `_driver: AsyncDriver | None` module global
- Remove `set_driver()` function
- Update `palace_health_status` signature: `(ctx: Context) -> HealthStatusResponse`
- Replace `if _driver is not None: ...` with `driver = ctx.request_context.lifespan_context.driver`

### 3. F1 — `main.py`
- Remove `set_driver` from import of `palace_mcp.mcp_server`
- Remove `set_driver(driver)` call in FastAPI lifespan
- FastAPI lifespan still creates its own driver for `/healthz` endpoint
- Comment: MCP sub-app owns its driver via `palace_lifespan`

### 4. Tests — `test_mcp_health_tool.py`
- Remove `reset_driver` fixture (no module global to reset)
- Remove `import palace_mcp.mcp_server as mcp_module` direct mutation
- Add `_make_ctx(driver)` helper: returns `MagicMock` with `ctx.request_context.lifespan_context = PalaceContext(driver=driver)`
- Update driver-dependent tests to call `palace_health_status(ctx)` directly
- `test_health_status_response_schema` — unchanged (Pydantic model)
- `test_tool_registered_in_mcp` — unchanged (`_mcp.list_tools()`)
- Drop `test_health_status_no_driver` — concept removed (driver always present from lifespan)

### 5. Verify
- `uv run pytest -q` — all tests pass
- `uv run ruff check src tests` — no lint errors
- `uv run mypy` — strict mode clean

---

## Convention: Every MCP Tool MUST
- Accept `ctx: Context` as the first parameter
- Access driver via `ctx.request_context.lifespan_context.driver`
- Use `ctx.info(...)` / `ctx.warning(...)` for structured MCP logging (where useful)

---

## Out of Scope
- New tools (separate product slice)
- Auth model for MCP exposure
- Performance / rate limiting
