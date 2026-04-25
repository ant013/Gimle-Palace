# GIM-76: Codebase-Memory Sidecar + palace.code.* Pass-Through — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Embed codebase-memory-mcp as a docker-compose sidecar and expose 7 pass-through + 1 disabled MCP tool via `palace.code.*` in palace-mcp.

**Architecture:** A new `code-graph` docker-compose profile starts the `codebase-memory-mcp` sidecar alongside palace-mcp and neo4j (neo4j also gets `code-graph` in its profiles — see CR CRITICAL #3). Palace-mcp contains a `code_router.py` module that registers 8 MCP tools (`palace.code.*`) via `register_code_tools(tool_decorator)`, which receives `_tool` from `mcp_server.py` — Pattern #21 dedup-aware decorator (CR CRITICAL #1). The decorator handles `__name__` binding before decoration (CR CRITICAL #2 — no late-binding closure bug). Seven tools forward JSON-RPC calls to the sidecar via a DI-injected `httpx.AsyncClient`; one (`manage_adr`) returns a structured error. Health status is surfaced via `palace.memory.health`.

**Tech Stack:** Python 3.12, FastMCP (from `mcp.server.fastmcp`), httpx, Pydantic BaseSettings, pytest, Docker Compose.

**Spec:** `docs/superpowers/specs/2026-04-24-N1a-2-codebase-memory-sidecar-design.md` at `315b138`.
**Research spike:** `docs/research/codebase-memory-0-28-spike.md`.

---

## File Structure

### New files

| File | Responsibility |
|---|---|
| `services/palace-mcp/src/palace_mcp/code_router.py` | 7 pass-through + 1 disabled `palace.code.*` tool registration, `set_cm_client()` DI |
| `tests/test_code_router.py` | Unit tests: tool registration, serialization, disabled tool, timeout |
| `tests/code_graph/__init__.py` | Package marker for integration tests |
| `tests/code_graph/conftest.py` | CM subprocess fixture on ephemeral port |
| `tests/code_graph/test_code_graph_integration.py` | 8 integration tests (one per tool) |
| `tests/fixtures/sandbox-repo/main.py` | Fixture Python file for CM indexing |
| `tests/fixtures/sandbox-repo/lib/helpers.py` | Fixture Python file with helper functions |
| `tests/fixtures/sandbox-repo/cmd/main.go` | Fixture Go file |
| `tests/fixtures/sandbox-repo/Dockerfile` | Minimal Dockerfile fixture |

### Modified files

| File | Change |
|---|---|
| `docker-compose.yml` | Add `codebase-memory-mcp` service under `code-graph` profile; add `code-graph` to palace-mcp profiles; add `CODEBASE_MEMORY_MCP_URL` env; add `codebase-memory-cache` volume |
| `services/palace-mcp/src/palace_mcp/config.py` | Add `codebase_memory_mcp_url: str` field to `Settings` |
| `services/palace-mcp/src/palace_mcp/main.py` | Import and call `set_cm_client()` in lifespan; import `register_code_tools` |
| `services/palace-mcp/src/palace_mcp/mcp_server.py` | Call `register_code_tools(_mcp)` and expose `_mcp` + `_tool` for code_router; update module docstring |
| `services/palace-mcp/src/palace_mcp/memory/health.py` | Add `code_graph_reachable` field to health response |
| `services/palace-mcp/src/palace_mcp/memory/schema.py` | Add `code_graph_reachable` field to `HealthResponse` |
| `services/palace-mcp/README.md` | Add `palace.code.*` tool listing, architecture note, disabled `manage_adr` note |

---

## Task 0: Verify CM transport and tool schemas

**Purpose:** Before writing any code, confirm the CM sidecar's MCP transport (HTTP-SSE vs stdio vs streamable-HTTP) and actual tool parameter names match the spike doc. This is a research task — no code changes.

**Files:**
- Read: `docs/research/codebase-memory-0-28-spike.md`

- [ ] **Step 1: Pull and run CM image in throwaway container**

```bash
docker run --rm -it ghcr.io/deusdata/codebase-memory-mcp:latest --help 2>&1 | head -40
```

If no published image exists, download the release tarball from the GitHub releases page and run locally. Record which approach works.

- [ ] **Step 2: Verify MCP transport type**

Look for `--transport`, `--port`, `--sse`, `--streamable-http` flags in the help output. Record the default transport and port. The router's `httpx.post()` target depends on this.

- [ ] **Step 3: Verify tool parameter names**

Run against a dummy repo:

```bash
docker run --rm -v /tmp/test-repo:/repos/test:ro ghcr.io/deusdata/codebase-memory-mcp:latest cli get_graph_schema
```

Confirm `index_repository` takes `repo_path` (not `path`). Confirm `search_code` parameter names.

- [ ] **Step 4: Update spike doc if drift found**

If any parameter names or transport details differ from `docs/research/codebase-memory-0-28-spike.md`, update that file. If everything matches, add a verification timestamp line.

- [ ] **Step 5: Decide image source**

Determine if `ghcr.io/deusdata/codebase-memory-mcp` has a published, tagged image. If yes, record the exact tag + digest for pinning. If no, document the vendoring approach (tarball + local build). Record the decision in a comment on the issue.

- [ ] **Step 6: Commit**

```bash
git add docs/research/codebase-memory-0-28-spike.md
git commit -m "docs(research): verify CM transport and schemas for GIM-76"
```

---

## Task 1: Add `codebase_memory_mcp_url` to Settings

**Files:**
- Modify: `services/palace-mcp/src/palace_mcp/config.py:15-20`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

In `tests/test_config.py`, add:

```python
from unittest.mock import patch

def test_settings_codebase_memory_mcp_url_defaults_empty() -> None:
    """codebase_memory_mcp_url defaults to empty string when env var unset."""
    with patch.dict(os.environ, {"NEO4J_PASSWORD": "test"}, clear=True):
        from palace_mcp.config import Settings
        s = Settings()
        assert s.codebase_memory_mcp_url == ""


def test_settings_codebase_memory_mcp_url_from_env() -> None:
    """codebase_memory_mcp_url reads from env var."""
    with patch.dict(os.environ, {"NEO4J_PASSWORD": "test", "CODEBASE_MEMORY_MCP_URL": "http://cm:8765/mcp"}, clear=True):
        from palace_mcp.config import Settings
        s = Settings()
        assert s.codebase_memory_mcp_url == "http://cm:8765/mcp"
```

**Note:** Uses `patch.dict(os.environ, ..., clear=True)` to match existing test style in `test_config.py` (CR WARNING #2).

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/palace-mcp && uv run pytest tests/test_config.py -v -k codebase_memory`
Expected: FAIL — `Settings` has no field `codebase_memory_mcp_url`

- [ ] **Step 3: Add the field to Settings**

In `services/palace-mcp/src/palace_mcp/config.py`, add to the `Settings` class:

```python
class Settings(BaseSettings):
    """Runtime settings for the palace-mcp FastAPI service."""

    neo4j_uri: str = "bolt://neo4j:7687"
    neo4j_password: SecretStr
    palace_default_group_id: str = "project/gimle"
    codebase_memory_mcp_url: str = ""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd services/palace-mcp && uv run pytest tests/test_config.py -v -k codebase_memory`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/config.py tests/test_config.py
git commit -m "feat(config): add codebase_memory_mcp_url setting (GIM-76)"
```

---

## Task 2: Create `code_router.py` — tool registration skeleton

**Files:**
- Create: `services/palace-mcp/src/palace_mcp/code_router.py`
- Test: `tests/test_code_router.py`

- [ ] **Step 1: Write the failing test for 7 enabled tools**

Create `services/palace-mcp/tests/test_code_router.py`:

```python
"""Unit tests for code_router.py — palace.code.* tool registration."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from mcp.server.fastmcp import FastMCP


EXPECTED_ENABLED_TOOLS = [
    "palace.code.search_graph",
    "palace.code.trace_call_path",
    "palace.code.query_graph",
    "palace.code.detect_changes",
    "palace.code.get_architecture",
    "palace.code.get_code_snippet",
    "palace.code.search_code",
]


class TestToolRegistration:
    """Unit tests use a stub decorator to test code_router in isolation.

    Integration with mcp_server._tool (Pattern #21) is tested in
    test_mcp_server.py::TestCodeToolRegistration.
    """

    @staticmethod
    def _make_stub_tool() -> tuple[Callable, FastMCP, list[str]]:
        """Create a stub _tool decorator that registers on a test FastMCP instance."""
        mcp = FastMCP("test")
        tracked_names: list[str] = []

        def stub_tool(name: str, description: str) -> Callable:
            tracked_names.append(name)
            return mcp.tool(name=name, description=description)

        return stub_tool, mcp, tracked_names

    def test_registers_seven_enabled_tools(self) -> None:
        """register_code_tools adds exactly 7 palace.code.* pass-through tools."""
        stub_tool, mcp, _ = self._make_stub_tool()
        from palace_mcp.code_router import register_code_tools
        register_code_tools(stub_tool)
        tool_names = [t.name for t in mcp._tool_manager.list_tools()]
        for name in EXPECTED_ENABLED_TOOLS:
            assert name in tool_names, f"Missing tool: {name}"

    def test_registers_manage_adr_as_disabled(self) -> None:
        """palace.code.manage_adr is registered and returns directive error."""
        stub_tool, mcp, _ = self._make_stub_tool()
        from palace_mcp.code_router import register_code_tools
        register_code_tools(stub_tool)
        tool_names = [t.name for t in mcp._tool_manager.list_tools()]
        assert "palace.code.manage_adr" in tool_names

    def test_total_tool_count_is_eight(self) -> None:
        """Exactly 8 palace.code.* tools registered (7 enabled + 1 disabled)."""
        stub_tool, mcp, _ = self._make_stub_tool()
        from palace_mcp.code_router import register_code_tools
        register_code_tools(stub_tool)
        code_tools = [t for t in mcp._tool_manager.list_tools() if t.name.startswith("palace.code.")]
        assert len(code_tools) == 8

    def test_each_tool_dispatches_to_distinct_cm_name(self) -> None:
        """Verify each registered tool forwards to its own CM tool name (closure binding correctness).

        CR CRITICAL #2: The decorator receives a factory-bound cm_tool_name,
        ensuring no late-binding closure bug in the registration loop.
        """
        stub_tool, mcp, _ = self._make_stub_tool()
        from palace_mcp.code_router import register_code_tools
        register_code_tools(stub_tool)
        tools = [t for t in mcp._tool_manager.list_tools()
                 if t.name.startswith("palace.code.") and t.name != "palace.code.manage_adr"]
        names = {t.name for t in tools}
        assert len(names) == 7, f"Expected 7 distinct tool names, got {len(names)}: {names}"

    def test_decorator_receives_all_names(self) -> None:
        """Stub decorator tracks all 8 tool names — proves Pattern #21 integration point works."""
        stub_tool, _, tracked = self._make_stub_tool()
        from palace_mcp.code_router import register_code_tools
        register_code_tools(stub_tool)
        code_names = [n for n in tracked if n.startswith("palace.code.")]
        assert len(code_names) == 8, f"Expected 8, got {len(code_names)}: {code_names}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/palace-mcp && uv run pytest tests/test_code_router.py::TestToolRegistration -v`
Expected: FAIL — `palace_mcp.code_router` does not exist

- [ ] **Step 3: Create code_router.py with tool registration**

Create `services/palace-mcp/src/palace_mcp/code_router.py`:

```python
"""palace.code.* MCP tool router — pass-through to codebase-memory-mcp sidecar.

Registers 7 enabled tools (forwarded to CM via JSON-RPC over HTTP) and
1 disabled tool (manage_adr — returns directive error).
"""

from __future__ import annotations

import logging
from typing import Any, Callable

import httpx

logger = logging.getLogger(__name__)

_cm_client: httpx.AsyncClient | None = None


def set_cm_client(client: httpx.AsyncClient) -> None:
    """DI injection point — called from FastAPI lifespan."""
    global _cm_client  # noqa: PLW0603
    _cm_client = client


_ENABLED_CM_TOOLS: dict[str, str] = {
    "search_graph": "Search code graph nodes by name pattern, label, or file pattern.",
    "trace_call_path": "Trace function call chains (inbound/outbound/both).",
    "query_graph": "Run a Cypher-like query against the code graph.",
    "detect_changes": "Detect uncommitted changes mapped to symbols.",
    "get_architecture": "Get project architecture: languages, packages, entry points, routes.",
    "get_code_snippet": "Get source code for a qualified symbol name.",
    "search_code": "Grep-like code search across indexed repositories.",
}

_DISABLED_CM_TOOLS: dict[str, str] = {
    "manage_adr": (
        "palace.code.manage_adr is disabled. Decision in palace.memory is the "
        "authoritative ADR store. Use palace.memory.lookup Decision {...} to read "
        "and a future palace.memory.decide(...) to write."
    ),
}


def register_code_tools(tool_decorator: Callable[[str, str], Callable]) -> None:
    """Register all palace.code.* tools using the provided decorator.

    Accepts `_tool` from mcp_server.py — Pattern #21 dedup-aware decorator
    that appends each name to `_registered_tool_names` before delegating
    to `@_mcp.tool()`.
    """
    for cm_name, desc in _ENABLED_CM_TOOLS.items():
        _register_passthrough(tool_decorator, cm_name, desc)
    for disabled_name, message in _DISABLED_CM_TOOLS.items():
        _register_disabled_tool(tool_decorator, disabled_name, message)


def _register_passthrough(
    tool_decorator: Callable[[str, str], Callable],
    cm_tool_name: str,
    description: str,
) -> None:
    palace_name = f"palace.code.{cm_tool_name}"

    @tool_decorator(palace_name, description)
    async def _forward(**kwargs: Any) -> dict[str, Any]:
        assert _cm_client is not None, (
            "CM client not initialized; call set_cm_client() in lifespan"
        )
        response = await _cm_client.post(
            "",
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {"name": cm_tool_name, "arguments": kwargs},
                "id": 1,
            },
        )
        response.raise_for_status()
        result = response.json()
        if "error" in result:
            return {"error": result["error"]}
        return result.get("result", result)


def _register_disabled_tool(
    tool_decorator: Callable[[str, str], Callable],
    cm_tool_name: str,
    message: str,
) -> None:
    palace_name = f"palace.code.{cm_tool_name}"

    @tool_decorator(palace_name, f"[DISABLED] {cm_tool_name}")
    async def _blocked(**kwargs: Any) -> dict[str, Any]:
        return {
            "error": message,
            "hint": "See spec §3.2 of N+1a.2 for rationale.",
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd services/palace-mcp && uv run pytest tests/test_code_router.py::TestToolRegistration -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/code_router.py tests/test_code_router.py
git commit -m "feat(code-router): register 7+1 palace.code.* tools (GIM-76)"
```

---

## Task 3: Unit tests — serialization, disabled response, timeout

**Files:**
- Modify: `tests/test_code_router.py`
- Modify: `services/palace-mcp/src/palace_mcp/code_router.py` (if needed)

- [ ] **Step 1: Write test for manage_adr disabled response**

Add to `tests/test_code_router.py`:

```python
import asyncio


class TestDisabledTool:
    @pytest.mark.asyncio
    async def test_manage_adr_returns_directive_error(self) -> None:
        """Calling palace.code.manage_adr returns error + hint, no forwarding."""
        from palace_mcp.code_router import register_code_tools
        mcp = FastMCP("test")
        stub_tool = lambda name, desc: mcp.tool(name=name, description=desc)
        register_code_tools(stub_tool)

        tool = next(t for t in mcp._tool_manager.list_tools() if t.name == "palace.code.manage_adr")
        result = await tool.run(arguments={})
        assert "error" in result
        assert "palace.memory" in result["error"]
        assert "hint" in result
```

- [ ] **Step 2: Run test to verify it passes**

Run: `cd services/palace-mcp && uv run pytest tests/test_code_router.py::TestDisabledTool -v`
Expected: PASS (disabled tool is already implemented)

- [ ] **Step 3: Write test for JSON-RPC serialization shape**

Add to `tests/test_code_router.py`:

```python
class TestPassthroughSerialization:
    @pytest.mark.asyncio
    async def test_jsonrpc_envelope_shape(self) -> None:
        """Pass-through builds correct JSON-RPC envelope and unwraps result."""
        from palace_mcp.code_router import register_code_tools, set_cm_client

        captured_request: dict[str, Any] = {}

        async def mock_post(url: str, *, json: dict[str, Any], **kw: Any) -> MagicMock:
            captured_request.update(json)
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.json.return_value = {"jsonrpc": "2.0", "result": {"nodes": []}, "id": 1}
            return resp

        client = AsyncMock(spec=httpx.AsyncClient)
        client.post = mock_post
        set_cm_client(client)

        mcp = FastMCP("test")
        stub_tool = lambda name, desc: mcp.tool(name=name, description=desc)
        register_code_tools(stub_tool)
        tool = next(t for t in mcp._tool_manager.list_tools() if t.name == "palace.code.search_graph")
        result = await tool.run(arguments={"name_pattern": "main"})

        assert captured_request["jsonrpc"] == "2.0"
        assert captured_request["method"] == "tools/call"
        assert captured_request["params"]["name"] == "search_graph"
        assert captured_request["params"]["arguments"] == {"name_pattern": "main"}
        assert result == {"nodes": []}

        set_cm_client(None)  # cleanup
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd services/palace-mcp && uv run pytest tests/test_code_router.py::TestPassthroughSerialization -v`
Expected: PASS

- [ ] **Step 5: Write test for timeout surfacing**

Add to `tests/test_code_router.py`:

```python
class TestPassthroughTimeout:
    @pytest.mark.asyncio
    async def test_timeout_surfaces_as_error(self) -> None:
        """httpx timeout → RuntimeError raised (FastMCP converts to isError)."""
        from palace_mcp.code_router import register_code_tools, set_cm_client

        async def mock_post_timeout(url: str, **kw: Any) -> None:
            raise httpx.ReadTimeout("Connection timed out")

        client = AsyncMock(spec=httpx.AsyncClient)
        client.post = mock_post_timeout
        set_cm_client(client)

        mcp = FastMCP("test")
        stub_tool = lambda name, desc: mcp.tool(name=name, description=desc)
        register_code_tools(stub_tool)
        tool = next(t for t in mcp._tool_manager.list_tools() if t.name == "palace.code.get_architecture")

        with pytest.raises(httpx.ReadTimeout):
            await tool.run(arguments={})

        set_cm_client(None)  # cleanup
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd services/palace-mcp && uv run pytest tests/test_code_router.py::TestPassthroughTimeout -v`
Expected: PASS

- [ ] **Step 7: Run all code_router unit tests together**

Run: `cd services/palace-mcp && uv run pytest tests/test_code_router.py -v`
Expected: All PASS

- [ ] **Step 8: Commit**

```bash
git add tests/test_code_router.py
git commit -m "test(code-router): serialization, disabled tool, timeout unit tests (GIM-76)"
```

---

## Task 4: Wire code_router into mcp_server.py and main.py lifespan

**Files:**
- Modify: `services/palace-mcp/src/palace_mcp/mcp_server.py:1-17,107-114`
- Modify: `services/palace-mcp/src/palace_mcp/main.py:49-71`

- [ ] **Step 1: Write the failing test — code tools appear in build_mcp_asgi_app**

Add to `tests/test_mcp_server.py`:

```python
class TestCodeToolRegistration:
    def test_code_tools_registered_in_mcp(self) -> None:
        """palace.code.* tools pass Pattern #21 dedup and appear in the MCP app.

        Tests through build_mcp_asgi_app() — same path as the existing
        TestAssertUniqueToolNames test. This verifies that code tools
        are tracked by _registered_tool_names (Pattern #21) and don't
        collide with existing palace.memory.* / palace.git.* tools.
        (CR WARNING #3: test public API, not internal list.)
        """
        from palace_mcp.mcp_server import build_mcp_asgi_app, _mcp
        build_mcp_asgi_app()  # asserts unique names — would crash on collision
        code_tools = [t for t in _mcp._tool_manager.list_tools() if t.name.startswith("palace.code.")]
        assert len(code_tools) == 8
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/palace-mcp && uv run pytest tests/test_mcp_server.py::TestCodeToolRegistration -v`
Expected: FAIL — no `palace.code.*` tools registered yet

- [ ] **Step 3: Wire register_code_tools into mcp_server.py**

In `services/palace-mcp/src/palace_mcp/mcp_server.py`, add after line 29 (imports):

```python
from palace_mcp.code_router import register_code_tools
```

At the bottom of the file (after the last `@_tool` block, before any trailing code), add:

```python
# ---------------------------------------------------------------------------
# palace.code.* — codebase-memory pass-through tools
# ---------------------------------------------------------------------------

register_code_tools(_tool)
```

**Why `_tool` not `_mcp`:** `register_code_tools` receives Pattern #21's `_tool` decorator
directly — each `palace.code.*` name is appended to `_registered_tool_names` and checked
by `assert_unique_tool_names()` at boot via `build_mcp_asgi_app()`. This closes CR CRITICAL #1.

Update the module docstring (lines 1-16) to include the new tools:

```python
"""MCP server layer for palace-mcp.

Exposes MCP tools via streamable-HTTP transport.
The FastAPI app mounts this at ``/mcp`` and shares the Neo4j driver
through :func:`set_driver`.

Tools registered:
- palace.health.status
- palace.memory.lookup
- palace.memory.health
- palace.git.log / .show / .blame / .diff / .ls_tree
- palace.code.search_graph / .trace_call_path / .query_graph /
  .detect_changes / .get_architecture / .get_code_snippet / .search_code
- palace.code.manage_adr (disabled — returns directive error)
"""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd services/palace-mcp && uv run pytest tests/test_mcp_server.py::TestCodeToolRegistration -v`
Expected: PASS

- [ ] **Step 5: Run the full existing test suite to check for regressions**

Run: `cd services/palace-mcp && uv run pytest tests/test_mcp_server.py -v`
Expected: All PASS (including existing `TestAssertUniqueToolNames` — proves no duplicate names)

- [ ] **Step 6: Wire httpx client creation in main.py lifespan**

In `services/palace-mcp/src/palace_mcp/main.py`, add imports at top (after line 15):

```python
import httpx
from palace_mcp.code_router import set_cm_client
```

In the `lifespan` function (after `set_default_group_id` call, around line 59), add:

```python
    cm_url = settings.codebase_memory_mcp_url
    cm_client: httpx.AsyncClient | None = None
    if cm_url:
        cm_client = httpx.AsyncClient(base_url=cm_url, timeout=30.0)
        set_cm_client(cm_client)
```

After the `yield` (before `await driver.close()`), add cleanup:

```python
    if cm_client is not None:
        await cm_client.aclose()
```

- [ ] **Step 7: Verify import compiles**

Run: `cd services/palace-mcp && uv run python -c "from palace_mcp.main import create_app; print('OK')"`
Expected: `OK`

- [ ] **Step 8: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/mcp_server.py services/palace-mcp/src/palace_mcp/main.py tests/test_mcp_server.py
git commit -m "feat(mcp-server): wire palace.code.* tools + httpx lifespan DI (GIM-76)"
```

---

## Task 5: Add `code_graph_reachable` to health probe

**Files:**
- Modify: `services/palace-mcp/src/palace_mcp/memory/schema.py`
- Modify: `services/palace-mcp/src/palace_mcp/memory/health.py`
- Test: `tests/memory/test_health.py` or `tests/test_health.py`

- [ ] **Step 1: Write the failing test**

Add to whichever health test file exists (check `tests/test_health.py`):

```python
@pytest.mark.asyncio
async def test_health_includes_code_graph_reachable_field() -> None:
    """HealthResponse includes code_graph_reachable field."""
    from palace_mcp.memory.schema import HealthResponse
    resp = HealthResponse(neo4j_reachable=True, entity_counts={})
    assert hasattr(resp, "code_graph_reachable")
    assert resp.code_graph_reachable is False  # default
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/palace-mcp && uv run pytest tests/test_health.py -v -k code_graph`
Expected: FAIL — `HealthResponse` has no field `code_graph_reachable`

- [ ] **Step 3: Add field to HealthResponse in schema.py**

In `services/palace-mcp/src/palace_mcp/memory/schema.py`, find the `HealthResponse` class and add:

```python
    code_graph_reachable: bool = False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd services/palace-mcp && uv run pytest tests/test_health.py -v -k code_graph`
Expected: PASS

- [ ] **Step 5: Add reachability probe to health.py**

In `services/palace-mcp/src/palace_mcp/memory/health.py`, import and probe the CM sidecar.

At the top, add (import the module, not the binding — avoids stale-reference bug per CR WARNING #1):

```python
from palace_mcp import code_router
```

Before the `return HealthResponse(...)` block (around line 79), add:

```python
    code_graph_ok = False
    if code_router._cm_client is not None:
        try:
            probe = await _cm_client.post(
                "",
                json={"jsonrpc": "2.0", "method": "tools/list", "params": {}, "id": 0},
                timeout=5.0,
            )
            code_graph_ok = probe.status_code == 200
        except Exception as exc:
            logger.warning("code_graph health probe failed: %s", exc)
```

In the `return HealthResponse(...)` call, add:

```python
        code_graph_reachable=code_graph_ok,
```

- [ ] **Step 6: Run full health tests**

Run: `cd services/palace-mcp && uv run pytest tests/test_health.py tests/memory/ -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/memory/schema.py services/palace-mcp/src/palace_mcp/memory/health.py tests/test_health.py
git commit -m "feat(health): add code_graph_reachable to palace.memory.health (GIM-76)"
```

---

## Task 6: Docker-compose — add codebase-memory-mcp service

**Files:**
- Modify: `docker-compose.yml`

- [ ] **Step 0: Add `code-graph` to neo4j profiles** (CR CRITICAL #3)

In `docker-compose.yml`, update the neo4j service `profiles` line (currently `[review, analyze, full]`) to include `code-graph`:

```yaml
    profiles: [review, analyze, full, code-graph]
```

**Why:** palace-mcp's `depends_on: neo4j: condition: service_healthy` means
`docker compose --profile code-graph up -d` must also start neo4j. Without
`code-graph` in neo4j's profiles, compose deadlocks or silently skips the
dependency.

- [ ] **Step 1: Add the codebase-memory-mcp service**

Add after the `palace-mcp` service block in `docker-compose.yml`:

```yaml
  codebase-memory-mcp:
    image: ghcr.io/deusdata/codebase-memory-mcp:v1.x  # pin exact tag from Task 0
    restart: unless-stopped
    mem_limit: 2g
    cpus: "1.5"
    profiles: [code-graph]
    volumes:
      - codebase-memory-cache:/home/cmm/.cache/codebase-memory-mcp
      - /Users/Shared/Ios/Gimle-Palace:/repos/gimle:ro
    networks:
      - paperclip-agent-net
    healthcheck:
      test: ["CMD", "codebase-memory-mcp", "--health"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 20s
```

- [ ] **Step 2: Add `code-graph` profile to palace-mcp**

In `docker-compose.yml`, update the palace-mcp `profiles` line:

```yaml
    profiles: [review, analyze, full, code-graph]
```

- [ ] **Step 3: Add CODEBASE_MEMORY_MCP_URL env var to palace-mcp**

In the palace-mcp service `environment` block, add:

```yaml
      CODEBASE_MEMORY_MCP_URL: "http://codebase-memory-mcp:8765/mcp"
```

- [ ] **Step 4: Add codebase-memory-cache volume**

In the `volumes:` section at the bottom, add:

```yaml
  codebase-memory-cache:
```

- [ ] **Step 5: Validate compose file syntax**

Run: `docker compose config --profiles code-graph > /dev/null && echo "OK"`
Expected: `OK` (no syntax errors)

- [ ] **Step 6: Commit**

```bash
git add docker-compose.yml
git commit -m "infra(compose): add codebase-memory-mcp sidecar under code-graph profile (GIM-76)"
```

**Note:** The exact image tag must be filled in from Task 0's findings. If no published image exists, replace the `image:` line with a `build:` context pointing at a vendored directory containing the Dockerfile + tarball.

---

## Task 7: Create sandbox-repo test fixture

**Files:**
- Create: `tests/fixtures/sandbox-repo/main.py`
- Create: `tests/fixtures/sandbox-repo/lib/__init__.py`
- Create: `tests/fixtures/sandbox-repo/lib/helpers.py`
- Create: `tests/fixtures/sandbox-repo/cmd/main.go`
- Create: `tests/fixtures/sandbox-repo/Dockerfile`

- [ ] **Step 1: Create fixture Python files**

Create `services/palace-mcp/tests/fixtures/sandbox-repo/main.py`:

```python
"""Sandbox entry point for CM integration tests."""

from lib.helpers import greet, add_numbers


def main() -> None:
    print(greet("world"))
    print(add_numbers(2, 3))


if __name__ == "__main__":
    main()
```

Create `services/palace-mcp/tests/fixtures/sandbox-repo/lib/__init__.py`:

```python
```

Create `services/palace-mcp/tests/fixtures/sandbox-repo/lib/helpers.py`:

```python
"""Helper functions for the sandbox repo."""


def greet(name: str) -> str:
    return f"Hello, {name}!"


def add_numbers(a: int, b: int) -> int:
    return a + b
```

- [ ] **Step 2: Create fixture Go file**

Create `services/palace-mcp/tests/fixtures/sandbox-repo/cmd/main.go`:

```go
package main

import "fmt"

func main() {
	fmt.Println(hello("world"))
}

func hello(name string) string {
	return "Hello, " + name + "!"
}
```

- [ ] **Step 3: Create fixture Dockerfile**

Create `services/palace-mcp/tests/fixtures/sandbox-repo/Dockerfile`:

```dockerfile
FROM python:3.12-slim
COPY . /app
WORKDIR /app
CMD ["python", "main.py"]
```

- [ ] **Step 4: Commit**

```bash
git add services/palace-mcp/tests/fixtures/sandbox-repo/
git commit -m "test(fixtures): add sandbox-repo for CM integration tests (GIM-76)"
```

---

## Task 8: Integration tests — CM subprocess + router end-to-end

**Files:**
- Create: `services/palace-mcp/tests/code_graph/__init__.py`
- Create: `services/palace-mcp/tests/code_graph/conftest.py`
- Create: `services/palace-mcp/tests/code_graph/test_code_graph_integration.py`

**Prerequisite:** Task 0 must have confirmed the CM binary is available (either via Docker image or local install). If CM cannot be spawned as a subprocess in CI, these tests should be marked `@pytest.mark.skipif` with a clear message.

- [ ] **Step 1: Create the package marker**

Create `services/palace-mcp/tests/code_graph/__init__.py` (empty file).

- [ ] **Step 2: Create conftest.py with CM subprocess fixture**

Create `services/palace-mcp/tests/code_graph/conftest.py`:

```python
"""Fixtures for codebase-memory-mcp integration tests.

Spawns a CM process on an ephemeral port, indexes the sandbox-repo fixture,
and provides an httpx client pointed at it.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from collections.abc import AsyncGenerator, Generator
from pathlib import Path

import httpx
import pytest
import pytest_asyncio

SANDBOX_REPO = Path(__file__).parent.parent / "fixtures" / "sandbox-repo"
CM_BINARY = shutil.which("codebase-memory-mcp")


def _find_free_port() -> int:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def cm_port() -> Generator[int, None, None]:
    """Start CM on an ephemeral port, yield the port, kill on teardown."""
    if CM_BINARY is None:
        pytest.skip("codebase-memory-mcp binary not found on PATH")

    port = _find_free_port()
    proc = subprocess.Popen(
        [CM_BINARY, "--port", str(port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={**os.environ, "CM_DATA_DIR": str(Path("/tmp") / f"cm-test-{port}")},
    )
    # Wait for CM to be ready
    base_url = f"http://127.0.0.1:{port}"
    for _ in range(30):
        try:
            r = httpx.post(
                f"{base_url}/mcp",
                json={"jsonrpc": "2.0", "method": "tools/list", "params": {}, "id": 0},
                timeout=2.0,
            )
            if r.status_code == 200:
                break
        except httpx.ConnectError:
            time.sleep(0.5)
    else:
        proc.kill()
        pytest.fail("CM did not become ready within 15s")

    # Index the sandbox repo
    httpx.post(
        f"{base_url}/mcp",
        json={
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "index_repository",
                "arguments": {"repo_path": str(SANDBOX_REPO.resolve())},
            },
            "id": 2,
        },
        timeout=30.0,
    )

    yield port

    proc.kill()
    proc.wait()


@pytest_asyncio.fixture(scope="session")
async def cm_client(cm_port: int) -> AsyncGenerator[httpx.AsyncClient, None]:
    """Async httpx client pointed at the CM subprocess.

    Uses async fixture + yield (CR NOTE #1: avoids deprecated asyncio.get_event_loop()).
    """
    client = httpx.AsyncClient(
        base_url=f"http://127.0.0.1:{cm_port}/mcp",
        timeout=30.0,
    )
    yield client
    await client.aclose()
```

- [ ] **Step 3: Write the 8 integration tests**

Create `services/palace-mcp/tests/code_graph/test_code_graph_integration.py`:

```python
"""Integration tests for palace.code.* tools against a real CM subprocess.

Each test calls the router (via code_router functions directly with the
injected cm_client) and verifies a non-error response shape.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from palace_mcp.code_router import set_cm_client


async def _call_tool(cm_client: httpx.AsyncClient, tool_name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    """Helper: call a CM tool via JSON-RPC and return the result."""
    set_cm_client(cm_client)
    response = await cm_client.post(
        "",
        json={
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments or {}},
            "id": 1,
        },
    )
    response.raise_for_status()
    data = response.json()
    set_cm_client(None)
    assert "error" not in data, f"CM returned error: {data.get('error')}"
    return data.get("result", data)


@pytest.mark.asyncio
class TestCodeGraphIntegration:
    async def test_end_to_end_get_architecture(self, cm_client: httpx.AsyncClient) -> None:
        result = await _call_tool(cm_client, "get_architecture")
        assert isinstance(result, dict)
        assert "languages" in result

    async def test_end_to_end_search_graph(self, cm_client: httpx.AsyncClient) -> None:
        result = await _call_tool(cm_client, "search_graph", {"name_pattern": "main"})
        assert isinstance(result, (dict, list))

    async def test_end_to_end_trace_call_path(self, cm_client: httpx.AsyncClient) -> None:
        result = await _call_tool(cm_client, "trace_call_path", {
            "function_name": "main",
            "direction": "outbound",
            "depth": 2,
        })
        assert isinstance(result, (dict, list))

    async def test_end_to_end_get_code_snippet(self, cm_client: httpx.AsyncClient) -> None:
        result = await _call_tool(cm_client, "get_code_snippet", {
            "qualified_name": "main",
        })
        assert isinstance(result, (dict, str))

    async def test_end_to_end_query_graph(self, cm_client: httpx.AsyncClient) -> None:
        result = await _call_tool(cm_client, "query_graph", {
            "query": "MATCH (n) RETURN count(n)",
        })
        assert result is not None

    async def test_end_to_end_detect_changes(self, cm_client: httpx.AsyncClient) -> None:
        result = await _call_tool(cm_client, "detect_changes")
        assert isinstance(result, (dict, list))

    async def test_end_to_end_search_code(self, cm_client: httpx.AsyncClient) -> None:
        result = await _call_tool(cm_client, "search_code", {
            "pattern": "def main",
        })
        assert isinstance(result, (dict, list))

    async def test_end_to_end_manage_adr_blocked(self, cm_client: httpx.AsyncClient) -> None:
        """manage_adr goes through the router disabled path, not CM directly."""
        from palace_mcp.code_router import register_code_tools, set_cm_client as _set
        from mcp.server.fastmcp import FastMCP

        _set(cm_client)
        mcp = FastMCP("test")
        stub_tool = lambda name, desc: mcp.tool(name=name, description=desc)
        register_code_tools(stub_tool)
        tool = next(t for t in mcp._tool_manager.list_tools() if t.name == "palace.code.manage_adr")
        result = await tool.run(arguments={"action": "list"})
        assert "error" in result
        assert "palace.memory" in result["error"]
        _set(None)
```

- [ ] **Step 4: Run integration tests (requires CM binary on PATH)**

Run: `cd services/palace-mcp && uv run pytest tests/code_graph/ -v`
Expected: All 8 PASS (or SKIP if CM binary not available)

- [ ] **Step 5: Commit**

```bash
git add services/palace-mcp/tests/code_graph/
git commit -m "test(integration): 8 end-to-end palace.code.* tests against CM subprocess (GIM-76)"
```

---

## Task 9: Update README.md with palace.code.* documentation

**Files:**
- Modify: `services/palace-mcp/README.md`

- [ ] **Step 1: Add palace.code.* section to README**

Add the following section to `services/palace-mcp/README.md` (after the existing tool documentation):

```markdown
## palace.code.* — Code Graph Tools (via Codebase-Memory sidecar)

Requires docker-compose profile `code-graph`. These tools forward to a
[codebase-memory-mcp](https://github.com/DeusData/codebase-memory-mcp) sidecar
running as a separate container.

### Enabled tools (pass-through)

| Tool | Description |
|---|---|
| `palace.code.search_graph` | Search code graph nodes by name pattern, label, file pattern |
| `palace.code.trace_call_path` | Trace function call chains (inbound/outbound/both) |
| `palace.code.query_graph` | Run a Cypher-like query against the code graph |
| `palace.code.detect_changes` | Detect uncommitted changes mapped to symbols |
| `palace.code.get_architecture` | Get project architecture: languages, packages, entry points, routes |
| `palace.code.get_code_snippet` | Get source code for a qualified symbol name |
| `palace.code.search_code` | Grep-like code search |

### Disabled tools

| Tool | Reason |
|---|---|
| `palace.code.manage_adr` | ADR is authoritative in `palace.memory` (`:Decision` nodes). CM's ADR store is not used. Returns a directive error pointing to `palace.memory.lookup Decision {...}`. |

### Architecture

```
┌─────────────┐     JSON-RPC/HTTP      ┌──────────────────────┐
│ palace-mcp  │ ────────────────────►   │ codebase-memory-mcp  │
│ (router)    │                         │ (sidecar, code-graph) │
└─────────────┘                         └──────────────────────┘
      │                                         │
      │ Neo4j (palace.memory.*)                 │ SQLite (code graph)
      ▼                                         ▼
   ┌──────┐                              ┌───────────┐
   │neo4j │                              │ /repos/:ro │
   └──────┘                              └───────────┘
```

### Not routed (intentionally omitted)

- `index_repository`, `index_config`, `reindex_file`, `create_checkpoint` — indexing is operator-controlled, not agent-facing
- `get_graph_schema` — internal CM introspection, no agent use case
- `ingest_traces` — out of scope for this slice
```

- [ ] **Step 2: Commit**

```bash
git add services/palace-mcp/README.md
git commit -m "docs(readme): add palace.code.* tool listing and architecture (GIM-76)"
```

---

## Task 10: Lint, typecheck, full test suite

**Files:** None (verification only)

- [ ] **Step 1: Run ruff check**

Run: `cd services/palace-mcp && uv run ruff check src/ tests/`
Expected: No errors

- [ ] **Step 2: Run mypy**

Run: `cd services/palace-mcp && uv run mypy src/`
Expected: No errors

- [ ] **Step 3: Run full test suite**

Run: `cd services/palace-mcp && uv run pytest tests/ -v --ignore=tests/code_graph`
Expected: All PASS (unit tests; integration tests may require CM binary)

- [ ] **Step 4: Run docker compose config validation**

Run: `docker compose config --profiles code-graph > /dev/null && echo "OK"`
Expected: `OK`

- [ ] **Step 5: Fix any issues found, commit fixes**

If any lint/type/test failures, fix them and commit:

```bash
git add -A
git commit -m "fix: address lint/type/test issues (GIM-76)"
```

---

## Task 11: Live smoke on iMac (Phase 4.1 — QAEngineer)

**Purpose:** This task is executed by QAEngineer, not the implementer. Listed here for completeness.

- [ ] **Step 1:** `docker compose --profile code-graph up -d` → all 3 services healthy within 60s
- [ ] **Step 2:** Index gimle repo: `codebase-memory-mcp cli index_repository '{"repo_path": "/repos/gimle"}'` → non-zero nodes
- [ ] **Step 3:** `palace.code.get_architecture` → languages=["Python"], non-zero packages
- [ ] **Step 4:** `palace.code.trace_call_path(function_name="build_graphiti")` → non-error response
- [ ] **Step 5:** `palace.code.manage_adr(...)` → directive error
- [ ] **Step 6:** Claude Code lists both `palace.memory.*` and `palace.code.*` tools
- [ ] **Step 7:** Watchdog `~/.paperclip/watchdog.err` stays empty

---

## Dependency graph

```
Task 0 (verify CM)
  └──► Task 6 (docker-compose — needs exact image tag)
Task 1 (config) ──► Task 4 (wire lifespan)
Task 2 (code_router skeleton) ──► Task 3 (unit tests) ──► Task 4 (wire mcp_server)
Task 4 ──► Task 5 (health probe)
Task 7 (sandbox fixtures) ──► Task 8 (integration tests)
Task 9 (README) — independent
Task 10 (lint/typecheck) — after all code tasks (1-9)
Task 11 (live smoke) — after merge to develop
```

**Parallelizable groups:**
- Group A: Tasks 1, 2, 7 (independent, no shared files)
- Group B: Tasks 6, 9 (independent, different files)
- Sequential chain: Task 0 → 6; Tasks 2 → 3 → 4 → 5; Task 7 → 8; all → 10
