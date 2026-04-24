---
slug: N1a-2-codebase-memory-sidecar
status: proposed
branch: feature/GIM-76-codebase-memory-sidecar (to be cut from develop once umbrella lands)
paperclip_issue: 76 (9917ad4d-102f-4c81-afcd-22a9a6c71881)
parent_umbrella: 74
predecessor: 67d42dc (develop tip)
date: 2026-04-24
---

# N+1a.2 — Codebase-Memory sidecar and `palace.code.*` pass-through

## 1. Context and scope boundary

This slice stands up `codebase-memory-mcp` (MIT, DeusData, arXiv 2603.27277) as a sidecar process via docker-compose, and exposes its 14-tool surface through `palace-mcp` as `palace.code.*` MCP tools. It is independent of the Graphiti foundation (GIM-75) — those two slices can merge in either order.

**In scope:**
- New docker-compose profile `code-graph`.
- Sidecar service `codebase-memory-mcp` with health probe, read-only repo mounts, persistent SQLite volume.
- `palace-mcp` router module that forwards specific MCP calls to the sidecar.
- 7 `palace.code.*` tools enabled via pass-through.
- 1 CM tool explicitly **disabled** in router (`manage_adr`).
- Docs + README update.
- Integration tests + iMac live smoke.

**Out of scope:**
- Graphiti foundation — **GIM-75**.
- Bridge extractor (projection of CM facts into Graphiti) — **GIM-77**.
- `semantic_search` — later followup.
- Auto-indexing on MCP session start (CM's `auto_index` feature) — later followup (enable via `config set` after observation period).

## 2. Problem

Palace-mcp currently has no structural code understanding. Agents working on a target project must rely on file-level `grep` + `read` via MCP, which is slow and token-heavy. We need a production-quality code-structural graph (call chains, imports, impact analysis, routes, Louvain communities) without investing months to build it in-house.

Codebase-Memory MCP provides all of this out of the box: 66 languages, sub-millisecond queries, zero LLM, SLSA 3 + 2586 tests, MIT license. Embedding it as a sidecar is the cheapest path to giving agents real code understanding.

## 3. Solution — sidecar + router

### 3.1 Docker-compose profile `code-graph`

Add to `docker-compose.yml`:

```yaml
services:
  codebase-memory-mcp:
    image: ghcr.io/deusdata/codebase-memory-mcp:v1.x   # pin exact tag on merge
    profiles: [code-graph]
    # Alternative if no published image: vendor tarball + entrypoint
    volumes:
      - codebase-memory-cache:/home/cmm/.cache/codebase-memory-mcp
      - /Users/Shared/Ios/Gimle-Palace:/repos/gimle:ro
      # Add additional target-project mounts as needed (Medic etc.)
    networks:
      - paperclip-agent-net
    ports:
      # Only expose via internal network; DO NOT bind to host in MVP.
      # For debugging, operator can uncomment: - "127.0.0.1:8765:8765"
    healthcheck:
      test: ["CMD", "codebase-memory-mcp", "--health"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 20s
    restart: unless-stopped

  palace-mcp:
    # ... existing config ...
    profiles: [review, analyze, full, code-graph]   # add code-graph
    environment:
      # ... existing ...
      CODEBASE_MEMORY_MCP_URL: http://codebase-memory-mcp:8765/mcp

volumes:
  codebase-memory-cache:
```

**Pinning policy:** exact image tag (not `latest`). If DeusData does not publish a container image, vendor the release tarball under `vendor/codebase-memory-mcp/<version>/` and build a local image in the palace-mcp repo. Checksum the tarball and verify SHA-256 in CI.

**Mounts:** target repos bind-mounted read-only, same pattern as `palace.git.*` mounts in GIM-54. Write-protection is defence-in-depth; CM's own security posture says it never writes to mounted repos.

### 3.2 Router module

`services/palace-mcp/src/palace_mcp/code_router.py`:

```python
from fastmcp import FastMCP
import httpx
from pydantic import BaseModel

CM_URL = settings.codebase_memory_mcp_url

# Tools enabled as pass-through:
_ENABLED_CM_TOOLS = [
    "search_graph",
    "trace_call_path",
    "query_graph",
    "detect_changes",
    "get_architecture",
    "get_code_snippet",
    "search_code",
]

# Tools explicitly disabled:
_DISABLED_CM_TOOLS = {
    "manage_adr": (
        "palace.code.manage_adr is disabled: :Decision in palace.memory is the "
        "authoritative ADR store. Use palace.memory.lookup Decision {...} to read "
        "and a future palace.memory.decide(...) to write."
    ),
}

def register_code_tools(mcp: FastMCP) -> None:
    for tool_name in _ENABLED_CM_TOOLS:
        _register_passthrough(mcp, tool_name)
    for disabled, message in _DISABLED_CM_TOOLS.items():
        _register_disabled_tool(mcp, disabled, message)

def _register_passthrough(mcp: FastMCP, tool_name: str) -> None:
    """Expose `palace.code.<tool_name>` that forwards the call to CM."""
    @mcp.tool(name=f"palace.code.{tool_name}")
    async def _forward(**kwargs) -> dict:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                CM_URL,
                json={
                    "jsonrpc": "2.0",
                    "method": f"tools/call",
                    "params": {"name": tool_name, "arguments": kwargs},
                    "id": 1,
                },
            )
            response.raise_for_status()
            return response.json()["result"]

def _register_disabled_tool(mcp: FastMCP, tool_name: str, message: str) -> None:
    @mcp.tool(name=f"palace.code.{tool_name}")
    async def _blocked(**kwargs) -> dict:
        return {"error": message, "hint": "See spec §3.2 of N+1a.2 for rationale."}
```

**Rationale for not `mcp.mount(other_server)`:** FastMCP supports server composition, but we want explicit per-tool allow-list (for `manage_adr` denial and future per-tool rate limiting / auditing). A router with explicit tool registration is clearer to audit.

### 3.3 Connectivity

- Palace-mcp resolves CM sidecar by Docker DNS name (`codebase-memory-mcp`).
- CM's MCP endpoint runs on port 8765 inside the container (default).
- Palace-mcp health check verifies CM reachability on startup; surfaces in `palace.memory.health()` as `code_graph_reachable: bool`.

### 3.4 What we deliberately do NOT do in this slice

- **No auto-indexing on session start.** CM's `auto_index=true` feature is deferred; the operator runs `index_repository` manually in GIM-77 testing, and auto-index gets enabled in a later ops slice after we understand its performance on our target repos.
- **No projection of CM facts into Graphiti.** That is GIM-77.
- **No cross-service HTTP linking tests on our sandbox repo.** Nice-to-have but not on the acceptance path for this slice.
- **No palace-mcp UI for the CM graph.** The CM `--ui` variant (port 9749) is not deployed here; operator can run it ad-hoc if needed.

## 4. Tasks

0. **Verify CM MCP tool schemas** — before writing router code, run `codebase-memory-mcp cli get_graph_schema` and `codebase-memory-mcp --help` against the pinned image in a throwaway container. Record actual parameter names (critically `index_repository: repo_path` — **NOT** `path`). Update `docs/research/codebase-memory-0-28-spike.md` if drift from the pre-design spike is found.
1. Decide image source — published tag or vendored tarball — in operator discussion before Phase 2.
2. Add `codebase-memory-mcp` service to `docker-compose.yml` under `code-graph` profile.
3. Add `CODEBASE_MEMORY_MCP_URL` env var to palace-mcp service.
4. Create `services/palace-mcp/src/palace_mcp/code_router.py` with `register_code_tools()` + 7 pass-through + 1 disabled. Use parameter names from Task 0.
5. Wire `register_code_tools()` into palace-mcp's MCP registration.
6. Add `code_graph_reachable` health probe to `palace.memory.health`.
7. Update `services/palace-mcp/README.md` with architecture note + list of `palace.code.*` tools + note on disabled `manage_adr`.
8. Unit tests per §6.1.
9. Integration tests per §6.2.
10. Live smoke per §6.3 on iMac.

## 5. API shape after this slice

New MCP tools (all read-only pass-through to CM):

- `palace.code.search_graph(name_pattern?, label?, qn_pattern?, ...)`
- `palace.code.trace_call_path(function_name, direction, depth)`
- `palace.code.query_graph(cypher)`
- `palace.code.detect_changes()`
- `palace.code.get_architecture()`
- `palace.code.get_code_snippet(qualified_name)`
- `palace.code.search_code(pattern)`

Disabled (returns directive error):

- `palace.code.manage_adr(...)`

## 6. Tests

### 6.1 Unit tests

- `test_router_registers_seven_enabled_tools` — after `register_code_tools(mcp)`, the `mcp` instance has exactly the 7 listed `palace.code.*` tools.
- `test_router_registers_manage_adr_as_disabled` — `palace.code.manage_adr` exists and returns the directive error with `hint` pointing at spec §3.2.
- `test_passthrough_serialization_shape` — monkeypatched CM endpoint; verify JSON-RPC envelope (method, params, id) is formed correctly and response is unwrapped to `result`.
- `test_passthrough_timeout_surfaces` — monkeypatched CM returns after 45s; client timeout is 30s → tool returns a structured timeout error, not a hang.

### 6.2 Integration tests

Fixture: spawn `codebase-memory-mcp` binary as subprocess on an ephemeral port; bind-mount `tests/fixtures/sandbox-repo/` (3 Python files + 1 Go file + 1 Dockerfile).

- `test_end_to_end_get_architecture` — `palace.code.get_architecture` returns a dict with expected keys (`languages`, `packages`, `entry_points`, `routes`, ...).
- `test_end_to_end_search_graph` — `palace.code.search_graph(name_pattern="main")` returns at least one node.
- `test_end_to_end_trace_call_path` — for a known Python call in the sandbox repo, `palace.code.trace_call_path` returns the expected chain.
- `test_end_to_end_get_code_snippet` — for a known symbol, `get_code_snippet` returns source body matching the on-disk file.
- `test_end_to_end_manage_adr_blocked` — attempting `palace.code.manage_adr` returns the directive error.

### 6.3 Live smoke on iMac

1. `docker compose --profile code-graph up -d` → `palace-mcp` + `neo4j` + `codebase-memory-mcp` all healthy (healthchecks green within 60s).
2. Index the Gimle repo via the operator shell attached to the CM container: `codebase-memory-mcp cli index_repository '{"repo_path": "/repos/gimle"}'` — non-zero node/edge counts. (Parameter name is `repo_path`, not `path` — verified 2026-04-24, see `docs/research/codebase-memory-0-28-spike.md`.)
3. `palace.code.get_architecture` via an MCP client returns languages=["Python"], non-zero packages.
4. `palace.code.trace_call_path(function_name="build_graphiti")` returns at least an empty-array result (function does not exist yet in GIM-76 alone; non-error response is the assertion).
5. `palace.code.manage_adr(...)` returns the directive error.
6. Claude Code (on operator's laptop) connected to palace-mcp via existing SSH tunnel lists both `palace.memory.*` and `palace.code.*` tools.
7. Watchdog (`~/.paperclip/watchdog.err`) stays empty for the duration.

All seven must pass before Phase 4.2 merge. QA Phase 4.1 evidence comment includes tool-call paste + docker compose logs tail.

## 7. Risks

| Risk | Mitigation |
|---|---|
| Codebase-Memory has no published container image; vendoring tarball adds maintenance | Operator decides at Phase 2 kickoff; if no image, CI builds local image from pinned tarball checksum, pushes to private registry. |
| CM sidecar eats memory/disk and destabilizes the paperclip-agent-net | Memory: CM releases RAM after indexing (RAM-first pipeline). Disk: SQLite volume `codebase-memory-cache` sized per expected repo total. Healthcheck + restart policy recovers from crashes. Can be `docker compose --profile code-graph stop codebase-memory-mcp` at any time with zero data loss (SQLite persists). |
| Pass-through router becomes a bottleneck on high-QPS agent traffic | Monitor p50/p99 via existing palace-mcp request logs. If a problem materializes, switch from HTTP-JSON-RPC to direct Python-lib invocation (CM ships a Python binding too). |
| CM's 14 tools expand; we silently miss new capabilities | Operator scans CM releases quarterly; adds to router allow-list explicitly. New tools are not auto-enabled — no implicit trust. |
| `manage_adr` deny-list feels like lock-in; some agent actually wants CM's ADR store | Document in README that CM's ADR store is authoritative in CM's ecosystem but not in ours. If a real need arises, a sync slice adds CM→Graphiti one-way mirroring. Revisit no earlier than N+2. |
| Read-only mounts still allow CM to write SQLite cache to its volume | Expected and intended. The `:ro` is on target repo mounts only, not on the CM cache volume. |

## 8. References

- Codebase-Memory paper: arXiv:2603.27277 (Vogel et al., March 2026).
- Codebase-Memory repo: https://github.com/DeusData/codebase-memory-mcp (MIT, 1809 stars).
- Pre-design tool-schema spike (verified 2026-04-24): `docs/research/codebase-memory-0-28-spike.md`.
- Umbrella decomposition: `docs/superpowers/specs/2026-04-24-N1-decomposition-design.md`.
- GIM-75 Graphiti foundation spec (independent): `docs/superpowers/specs/2026-04-24-N1a-1-graphiti-foundation-design.md`.
- GIM-77 bridge extractor spec (depends on this + GIM-75): `docs/superpowers/specs/2026-04-24-N1a-3-bridge-extractor-design.md`.
- Historical combined spec (deprecated): `docs/superpowers/specs/2026-04-24-N1a-graphiti-codebase-memory-foundation-design.md`.
