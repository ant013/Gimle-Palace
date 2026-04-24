# Codebase-Memory MCP tool schema — verified 2026-04-24

Captured via README-scrape of `DeusData/codebase-memory-mcp` main branch (v1.x tag at time of spike). Complements `graphiti-core-0-28-spike/README.md`.

**Before starting GIM-76 implementation, re-verify by running `codebase-memory-mcp --help` or `palace.code.get_graph_schema` on a live sidecar to confirm nothing has drifted.**

## Tool signatures (from CLI and README examples)

### Indexing

| Tool | Arguments | Notes |
|---|---|---|
| `index_repository` | `repo_path: str` (absolute) | **Parameter is `repo_path`, NOT `path`.** |
| `index_status` | `project?: str` | Optional project filter. |
| `list_projects` | — | No arguments. |
| `delete_project` | `project: str` | Required slug. |

### Query

| Tool | Arguments | Notes |
|---|---|---|
| `search_graph` | `name_pattern?: str` (regex), `label?: str`, `file_pattern?: str`, `degree?: int`, `limit?: int`, `offset?: int`, `project?: str` | All optional, combinable. |
| `trace_call_path` | `function_name: str`, `direction: "inbound" \| "outbound" \| "both"`, `depth: 1..5` | Depth bounded. |
| `query_graph` | `query: str` | Cypher-like subset. |
| `detect_changes` | **(no arguments)** | Returns git working-tree diff mapped to symbols. **Does not accept a timestamp or "since" filter.** Cannot be used for incremental sync of arbitrary change windows — only current uncommitted state. |
| `get_architecture` | — | Returns `{languages, packages, entry_points, routes, hotspots, clusters, ADR}`. |
| `get_code_snippet` | `qualified_name: str` | **Format: `<project>.<path_parts_dotted>.<name>`** — deterministic if bridge populates this field directly. |
| `search_code` | (grep-like; exact args not in README) | |
| `get_graph_schema` | — | Returns node/edge counts + relationship patterns. |

### Extras

| Tool | Status in GIM-76 |
|---|---|
| `manage_adr` | **DISABLED in router** — `:Decision` in Graphiti is authoritative. |
| `ingest_traces` | Not enabled in GIM-76 MVP (defer). |

## Implications for GIM-76 and GIM-77

### GIM-76

- Live-smoke script uses `repo_path` (fixed from earlier draft).
- Re-verify `search_code` and `manage_adr` schema at implementation time via `get_graph_schema` or `--help`.

### GIM-77 incremental sync

- **`detect_changes` is not a change-feed.** It reports the current uncommitted git working tree diff. It tells you "what's different from HEAD right now", not "what changed since time T".
- **Correct incremental primitive for bridge:** per-file XXH3 hash comparison via `query_graph`:

  ```cypher
  MATCH (f:File)
  RETURN f.uuid AS cm_id, f.path, f.xxh3_hash, f.project
  ```

  Bridge maintains state file `{cm_id: last_seen_xxh3}` and compares. Files with changed hash → re-project; files missing from CM response → mark Graphiti edges `invalid_at = now`.

- **`detect_changes` stays useful for:** agents asking "what's uncommitted right now and which symbols does it touch" — an on-demand `palace.code.*` query, not a bridge synchronization primitive.

### GIM-77 cross-resolve

- `get_code_snippet(qualified_name)` is **deterministic** given qualified_name is stored.
- Bridge **must store** `qualified_name` as a first-class attribute on every projected `:Symbol`, `:File`, `:Module`. Read it from CM's `search_graph` response (CM stores it natively).
- Cross-resolve becomes: `palace.code.get_code_snippet(qualified_name=node.attributes['qualified_name'])`.

## Source

README of `DeusData/codebase-memory-mcp` fetched via web at 2026-04-24. Full paper: arXiv:2603.27277.
