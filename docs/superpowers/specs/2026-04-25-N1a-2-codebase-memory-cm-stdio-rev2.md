---
slug: N1a-2-codebase-memory-cm-stdio-rev2
status: post-hoc-canonical (matches commit de3f30c on feature/GIM-76)
branch: feature/GIM-76-codebase-memory-sidecar
paperclip_issue: 76 (9917ad4d-102f-4c81-afcd-22a9a6c71881)
parent_umbrella: 74
predecessor: 766629d (develop tip)
date: 2026-04-25
supersedes: 2026-04-24-N1a-2-codebase-memory-sidecar-design.md
---

# N+1a.2 rev2 — Codebase-Memory in-process subprocess (stdio)

## 1. Why a rev2

Rev1 assumed `codebase-memory-mcp` v0.6.0 exposed an HTTP/JSON-RPC endpoint and
ran as a separate compose service that palace-mcp called over the network.
Phase 4.1 live smoke (commit `18def9c`) found:

```
$ codebase-memory-mcp --help
codebase-memory-mcp    Run MCP server on stdio
```

The binary is **stdio-only** — no HTTP server, no listening port, exits with
status 0 when stdin is closed. The rev1 transport assumption was never
verified in the rev1 spike (root cause: spike read the README's "MCP server"
language and assumed transport without running `--help`). PE pre-emptively
shipped the corrected architecture in commit `de3f30c` between 19:49 UTC (QA
FAIL) and 20:03 UTC; this rev2 is the post-hoc canonicalization of what was
actually built.

Rev1 file is kept with a SUPERSEDED banner — do not edit further.

## 2. Architecture (current)

```
docker compose --profile review up -d
└── palace-mcp container (single)
    ├── codebase-memory-mcp binary copied into image at /usr/local/bin
    ├── /repos/<slug>:ro bind-mounts (host repos)
    ├── codebase-memory-cache named volume → SQLite + indices
    └── on FastAPI startup, code_router.start_cm_subprocess():
        ├── spawns codebase-memory-mcp via mcp.client.stdio.stdio_client
        ├── wraps the (read, write) streams in mcp.ClientSession
        ├── awaits session.initialize() (MCP handshake)
        └── stores session in module-global _cm_session for tool handlers
```

There is **no separate codebase-memory-mcp service** in `docker-compose.yml`.
The `code-graph` profile is retained as a no-op alias (compose service list is
unchanged from `review`). All networking between palace-mcp and CM happens
in-process over stdio pipes — zero network surface, no port collisions.

## 3. Solution shape

### 3.1 Dockerfile multi-stage

`services/palace-mcp/Dockerfile`:
- Stage `cm-fetch` (debian-slim, SHA-pinned) downloads
  `codebase-memory-mcp-linux-${ARCH}-portable.tar.gz` from GitHub releases
  for `CM_VERSION`, verifies SHA-256, untars to `/tmp/codebase-memory-mcp`.
- Final stage `COPY --from=cm-fetch` puts the binary at
  `/usr/local/bin/codebase-memory-mcp` with mode 0755.

Net image size impact: ~25–30 MB (one static binary).

### 3.2 Compose integration

`docker-compose.yml`:
- `palace-mcp` service gains:
  - `CODEBASE_MEMORY_MCP_BINARY: "${CODEBASE_MEMORY_MCP_BINARY:-}"` env (path to binary inside container; default empty disables CM).
  - `/repos/gimle:ro` bind-mount (was previously on the sidecar service).
  - `codebase-memory-cache` named volume mounted at `/home/appuser/.cache/codebase-memory-mcp` (CM's SQLite + index storage).
- The standalone `codebase-memory-mcp` service is removed.
- `depends_on` between palace-mcp and a CM service is removed (no longer applicable).
- `neo4j` service unchanged.

### 3.3 Router (`code_router.py`)

- Module-globals `_cm_session: ClientSession | None`, `_cm_exit_stack: AsyncExitStack | None`.
- `start_cm_subprocess(binary: str)`:
  - `StdioServerParameters(command=binary, args=[])`
  - `stdio_client(params)` → (read, write) pair
  - `ClientSession(read, write)` entered into AsyncExitStack
  - `await session.initialize()`
- `stop_cm_subprocess()`: `await stack.aclose()`, clears globals.
- `register_code_tools(tool_decorator)` — same Pattern #21 dedup-aware
  registration as rev1; takes `_tool` from `mcp_server.py`.
- `_register_passthrough(tool_decorator, cm_name, desc)` per enabled tool:
  forwards `arguments: dict | None` via `_cm_session.call_tool(cm_name, args)`.
  Returns parsed JSON when CM emits `TextContent` with valid JSON, otherwise
  `{"text": ...}`. `result.isError` → `{"error": [...]}`.
- 7 enabled tools (unchanged from rev1): `search_graph`, `trace_call_path`,
  `query_graph`, `detect_changes`, `get_architecture`, `get_code_snippet`,
  `search_code`.
- 1 disabled tool (unchanged from rev1): `manage_adr` returns directive
  error pointing at `palace.memory.lookup Decision`.

### 3.4 Lifespan wiring (`main.py`)

In FastAPI lifespan, after Graphiti is up and before yield:

```python
if settings.codebase_memory_mcp_binary:
    await start_cm_subprocess(settings.codebase_memory_mcp_binary)
```

After yield, parallel `await stop_cm_subprocess()`. CM is **opt-in** —
empty `CODEBASE_MEMORY_MCP_BINARY` disables it without breaking startup;
`palace.code.*` tools remain registered but raise the "subprocess not started"
assertion if invoked.

### 3.5 Health surface

`palace.memory.health` returns a `code_graph_reachable` boolean derived from
`_cm_session is not None` (presence check, not liveness — connectivity probe
is a follow-up, see Risks §6).

## 4. What we deliberately do NOT do in this slice

- No CM ADR usage (`manage_adr` disabled — Decision authoritative in palace.memory).
- No `auto_index` enable on session start (CM has this option but we leave it off until observation period passes; revisit in followup).
- No semantic_search exposure (deferred to followup slice).
- No bridge extractor — that's GIM-77.
- No liveness probe of the CM subprocess (presence-only; if subprocess crashes,
  next tool call raises and operator sees error). Liveness probe + auto-restart
  is a Risks §6 followup.

## 5. Acceptance

- `docker compose --profile review up -d --build --wait` → both containers healthy.
- `palace.code.search_graph(name_pattern="palace.memory.lookup")` → returns CM
  result row (proves: subprocess up, MCP handshake done, tool forwarded,
  result parsed). This is the GO/NO-GO check, not `/healthz`.
- `palace.code.manage_adr(...)` → directive error response (disabled tool).
- `palace.memory.health` → `code_graph_reachable: true`.
- All unit tests + integration tests green in CI (mocking `ClientSession`,
  not `httpx`).

## 6. Risks

| Risk | Mitigation |
|---|---|
| CM subprocess crashes mid-session | Next tool call raises `assert _cm_session` → tool error to caller. Operator sees error. **Followup:** liveness probe + auto-restart in lifespan. |
| Binary update breaks tool schema | SHA-pinned in Dockerfile; bump is explicit. PR review catches schema drift. |
| Stdio backpressure / deadlock | MCP SDK handles framing; we don't write to stdin during tool calls (only via call_tool). Low risk. |
| CM index corruption | Persistent named volume `codebase-memory-cache`; `docker volume rm` resets. CM is read-mostly (only `index_repository` writes). |
| Cold start latency | One-time cost on container start (subprocess fork + MCP handshake, <1s on iMac). Acceptable. |

## 7. Test coverage

- `tests/test_code_router.py` — unit, mocks `ClientSession.call_tool`. 7 enabled tools forwarded, 1 disabled tool returns directive error, error envelope shape, JSON-parsing fallback to `{"text": ...}`.
- `tests/code_graph/conftest.py` + `tests/code_graph/test_code_graph_integration.py` — integration, runs CM subprocess against `tests/fixtures/sandbox-repo/` and asserts real tool responses.
- `tests/memory/test_health.py` — `code_graph_reachable` reflects session presence.

## 8. Tasks (already done in `de3f30c`)

This is the post-hoc canonical spec; the implementation already exists. No new
PE tasks. The remaining workflow tasks are:

1. **CR Phase 3.1 mechanical re-review** of `de3f30c` (rev2 architecture).
2. **Opus Phase 3.2 adversarial re-review** of `de3f30c`.
3. **QA Phase 4.1 re-smoke** on iMac with `--profile review` (no longer `--profile code-graph`).
4. PR open + merge to develop.

## 9. References

- `docs/superpowers/specs/2026-04-24-N1a-2-codebase-memory-sidecar-design.md` — superseded rev1 (HTTP).
- `services/palace-mcp/src/palace_mcp/code_router.py` (commit `de3f30c`).
- `services/palace-mcp/src/palace_mcp/main.py:13,68,77`.
- `services/palace-mcp/Dockerfile` — cm-fetch multi-stage.
- MCP Python SDK — `mcp.client.stdio.stdio_client`, `mcp.ClientSession`.
- `reference_graphiti_core_0_28_api_truth.md` — sister verified-API memory; this rev2 is a parallel API-truth correction for codebase-memory-mcp.
