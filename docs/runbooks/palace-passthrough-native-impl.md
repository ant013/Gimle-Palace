# Palace Native Passthrough Runbook

Grounded in `origin/develop` commit `24bfdb31` on 2026-06-08. This is the merged
Phase 1.0-1.7 behavior that Phase 1.8 documents.

## Current split

Inspect the current router split first:

```bash
uv run --directory services/palace-mcp python -m palace_mcp.cli tool call \
  palace.code.list_passthrough_projects \
  --url http://localhost:8080/mcp \
  --json '{}'
```

Expected on `24bfdb31`:

```json
{
  "native": [
    "palace.code.search_graph",
    "palace.code.trace_call_path",
    "palace.code.query_graph",
    "palace.code.detect_changes",
    "palace.code.get_architecture",
    "palace.code.get_code_snippet"
  ],
  "cm_only": [
    "palace.code.search_code"
  ]
}
```

## Routing decisions

```text
project omitted
  -> CM if CODEBASE_MEMORY_MCP_BINARY is configured
  -> cm_fallback_unavailable if CM is not running

project resolves to a Palace slug
  -> native for: query_graph, get_code_snippet, detect_changes,
     trace_call_path(mode="calls"), search_graph(pattern mode), get_architecture
  -> CM for: search_code when CM is available
  -> phase2_required for native Phase 2 gaps
  -> native_error for terminal native validation/runtime envelopes

project does not resolve
  -> project_not_found (response points operators at palace.memory.list_projects)
```

`search_graph` and `get_code_snippet` default `include_deprecated=false` at the
router boundary. Pass `include_deprecated=true` explicitly when needed.

## Manual operator calls

Use `uw-ios-baseline` for the Phase 1 acceptance checks.

`query_graph`:

```bash
uv run --directory services/palace-mcp python -m palace_mcp.cli tool call \
  palace.code.query_graph \
  --url http://localhost:8080/mcp \
  --json '{"project":"uw-ios-baseline","query":"MATCH (s:Symbol) WHERE s.group_id = $group_id RETURN s.qualified_name AS qualified_name ORDER BY qualified_name LIMIT 10"}'
```

`get_code_snippet`:

```bash
uv run --directory services/palace-mcp python -m palace_mcp.cli tool call \
  palace.code.get_code_snippet \
  --url http://localhost:8080/mcp \
  --json '{"project":"uw-ios-baseline","qualified_name":"<qualified-name-from-query_graph>"}'
```

`detect_changes`:

```bash
uv run --directory services/palace-mcp python -m palace_mcp.cli tool call \
  palace.code.detect_changes \
  --url http://localhost:8080/mcp \
  --json '{"project":"uw-ios-baseline"}'
```

`trace_call_path`:

```bash
uv run --directory services/palace-mcp python -m palace_mcp.cli tool call \
  palace.code.trace_call_path \
  --url http://localhost:8080/mcp \
  --json '{"project":"uw-ios-baseline","function_name":"<qualified-name-from-query_graph>","mode":"calls","direction":"outbound","depth":3}'
```

`search_graph`:

```bash
uv run --directory services/palace-mcp python -m palace_mcp.cli tool call \
  palace.code.search_graph \
  --url http://localhost:8080/mcp \
  --json '{"project":"uw-ios-baseline","label":"Symbol","name_pattern":"^HD.*"}'
```

`get_architecture`:

```bash
uv run --directory services/palace-mcp python -m palace_mcp.cli tool call \
  palace.code.get_architecture \
  --url http://localhost:8080/mcp \
  --json '{"project":"uw-ios-baseline"}'
```

`search_code` remains CM-only:

```bash
uv run --directory services/palace-mcp python -m palace_mcp.cli tool call \
  palace.code.search_code \
  --url http://localhost:8080/mcp \
  --json '{"project":"uw-ios-baseline","pattern":"HD"}'
```

Expected behavior:
- With `CODEBASE_MEMORY_MCP_BINARY` configured and the CM subprocess up, the
  call is served by CM.
- Without CM but with a Palace-known project slug, the response is
  `{ok: false, error_code: "phase2_required"}`.

## Phase 2 gaps

These are the Phase 1 native deferrals that operators will actually see:

`search_graph` full-text/BM25 mode is deferred:

```bash
uv run --directory services/palace-mcp python -m palace_mcp.cli tool call \
  palace.code.search_graph \
  --url http://localhost:8080/mcp \
  --json '{"project":"uw-ios-baseline","query":"HD wallet"}'
```

Expected: `{ok: false, error_code: "phase2_required"}`.

`trace_call_path` non-call modes are deferred:

```bash
uv run --directory services/palace-mcp python -m palace_mcp.cli tool call \
  palace.code.trace_call_path \
  --url http://localhost:8080/mcp \
  --json '{"project":"uw-ios-baseline","function_name":"<qualified-name-from-query_graph>","mode":"data_flow"}'
```

Expected: `{ok: false, error_code: "phase2_required", mode: "data_flow"}`.

## Log inspection

The router emits one structured INFO event per call with message
`passthrough.dispatch`.

```bash
docker compose logs palace-mcp --tail 200 | \
  jq -c 'select(.message=="passthrough.dispatch") | {tool, decision, project, duration_ms}'
```

Actual `decision` values in the merged code:
- `native`
- `native_error`
- `cm`
- `project_not_found`
- `phase2_required`
- `cm_fallback_unavailable`

Notes:
- CM fallback that succeeds is logged as `cm`, not a separate `fallback_to_cm`
  value.
- `project` is the resolved slug when namespace resolution succeeds; otherwise
  it is the raw input value or `null`.

## Common envelopes

- `project_not_found`: the slug or CM namespace is unknown to Palace. Use
  `palace.memory.list_projects` to inspect registered slugs and mappings.
- `cm_fallback_unavailable`: the request needs CM and the subprocess was not
  started. Configure `CODEBASE_MEMORY_MCP_BINARY`.
- `phase2_required`: the tool is intentionally deferred in this slice.

## No global all-CM toggle

The merged Phase 1 code does not expose a dedicated env flag that disables
native routing for Palace-known projects. `CODEBASE_MEMORY_MCP_BINARY` only
controls whether CM fallback is available. If you need all-CM behavior for a
Palace-known slug, call the CM server directly; Palace will still prefer the
native handlers above.
