# palace-mcp

FastAPI + FastMCP service exposing the Palace knowledge graph and code graph via MCP tools.

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
│ palace-mcp  │ ──────────────────────► │ codebase-memory-mcp  │
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
