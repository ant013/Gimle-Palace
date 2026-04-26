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

## palace.ingest — Extractor Framework

Palace-mcp ships a pluggable extractor framework. Extractors read from external
sources and write `EntityNode` / `EntityEdge` rows to Graphiti (Neo4j).

### Registered extractors

| Name | Description |
|---|---|
| `heartbeat` | Diagnostic probe. Writes one `:Episode` node per run. Use to verify the pipeline is alive. |
| `codebase_memory_bridge` | Projects selected CM facts into Graphiti with metadata envelope (`cm_id`, `confidence`, `provenance`, `observed_at`). Supports incremental sync via per-file XXH3 hashing. |

### Running an extractor

```
palace.ingest.list_extractors()
palace.ingest.run_extractor(name="codebase_memory_bridge", project="gimle")
```

Success response:
```json
{
  "ok": true,
  "run_id": "<uuid>",
  "extractor": "codebase_memory_bridge",
  "project": "gimle",
  "duration_ms": 1420,
  "nodes_written": 34,
  "edges_written": 12,
  "success": true
}
```

### codebase_memory_bridge — projection rules

| CM label | Graphiti type | Confidence | Provenance |
|---|---|---|---|
| `Project` | `:Project` | 1.0 | asserted |
| `File` | `:File` | 1.0 | asserted |
| `Module` | `:Module` | 1.0 | asserted |
| `Function` / `Method` / `Class` / … | `:Symbol{kind=...}` | 1.0 | asserted |
| `Route` | `:APIEndpoint` | 1.0 | asserted |
| Louvain cluster | `:ArchitectureCommunity` | modularity score | derived |
| Top-5% co-change files | `:Hotspot` | normalized rank | derived |

Skipped CM edges: `THROWS`, `READS`, `WRITES`, `HTTP_CALLS`, `ASYNC_CALLS`,
`USES_TYPE`, `IMPLEMENTS`, `INHERITS`, `USAGE`, `TESTS`, `FILE_CHANGES_WITH`.

### Cross-resolve: CM node ↔ Graphiti node

Every projected node carries `cm_id = "<project_slug>:<cm_uuid>"`. To find
the Graphiti EntityNode matching a CM symbol:

```cypher
MATCH (n {cm_id: "gimle:some-cm-uuid", group_id: "project/gimle"})
RETURN n
```

### Incremental sync

State is persisted to `~/.paperclip/codebase-memory-bridge-state.json`.
Between runs, only files whose `xxh3` hash changed are re-projected.
Stale edges for removed files are marked `invalid_at`.

### Health

`palace.memory.health()` returns a `bridge` section when the extractor has
run at least once:

```json
{
  "bridge": {
    "last_run_at": "2026-04-25T10:00:00+00:00",
    "last_run_duration_ms": 1420,
    "nodes_written_by_type": {"File": 12, "Symbol": 22},
    "edges_written_by_type": {"CONTAINS": 12},
    "cm_index_freshness_sec": 42.3,
    "staleness_warning": false
  }
}
```

`staleness_warning` is `true` when `cm_index_freshness_sec > 600` (2× the 5-min MVP interval).

## palace.memory.decide — Write-side :Decision tool

Records a `:Decision` node in Graphiti. Use after a verdict, design call, review APPROVE/REJECT, or any committed-to choice that future agents should see.

### Example

```python
palace.memory.decide(
  title="Adopt edge-based supersession model",
  body="Decision nodes use (:Decision)-[:SUPERSEDES]->(:Decision) edges instead of a supersedes attribute list. Separate slice for proper edge-based supersession.",
  slice_ref="GIM-96",
  decision_maker_claimed="cto",
  decision_kind="design",
  tags=["architecture", "graphiti"],
  confidence=0.9,
)
```

Success response:
```json
{
  "ok": true,
  "uuid": "<uuid>",
  "name": "Adopt edge-based supersession model",
  "slice_ref": "GIM-96",
  "decision_maker_claimed": "cto",
  "decided_at": "2026-04-26T07:30:00+00:00",
  "name_embedding_dim": 1536
}
```

### Read back via lookup

```python
palace.memory.lookup(entity_type="Decision", filters={"slice_ref": "GIM-96"})
```

### Validation

| Field | Rules |
|---|---|
| `title` | 1–200 chars |
| `body` | 1–2000 chars |
| `slice_ref` | `GIM-<n>`, `N+<n>[a-z][.<n>]`, or `operator-decision-<YYYYMMDD>` |
| `decision_maker_claimed` | One of: `cto`, `codereviewer`, `pythonengineer`, `opusarchitectreviewer`, `qaengineer`, `operator`, `board` |
| `confidence` | 0.0–1.0 (default 1.0) |
| `tags` | ≤ 16 items |
| `evidence_ref` | ≤ 32 items |
| `decision_kind` | Optional free-form string, ≤ 80 chars |

Validation errors return `{"ok": false, "error_code": "validation_error", "message": "..."}` (not FastMCP `isError`). Infrastructure errors (Neo4j/embedder down) raise via `handle_tool_error` → FastMCP `isError=true`.
