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

### Composite tools

| Tool | Description |
|---|---|
| `palace.code.test_impact` | Given a Function's `qualified_name`, return all tests exercising it. Default: `:TESTS` edge (exact, hop=1, homonym-immune). Opt-in: `include_indirect=True` — multi-hop `trace_call_path` (homonym caveat). |

#### `palace.code.test_impact` usage

```jsonc
// Default path — exact, homonym-immune (uses :TESTS edge)
{
  "qualified_name": "palace_mcp.code_router.register_code_tools",
  "project": "repos-gimle"          // optional; default from PALACE_CM_DEFAULT_PROJECT
}

// Opt-in indirect path — multi-hop via trace_call_path (homonym risk)
{
  "qualified_name": "palace_mcp.code_router.register_code_tools",
  "include_indirect": true,
  "max_hops": 3,                    // 1-5, default 3
  "max_results": 50                 // 1-200, default 50
}
```

Response shape (success):
```json
{
  "ok": true,
  "requested_qualified_name": "register_code_tools",
  "qualified_name": "palace_mcp.code_router.register_code_tools",
  "project": "repos-gimle",
  "method": "tests_edge",
  "tests": [
    {"name": "test_register_code_tools", "qualified_name": "tests.test_code_router.test_register_code_tools", "hop": 1}
  ],
  "total_found": 1,
  "max_hops_used": null,
  "truncated": false
}
```

Error envelopes:
- `symbol_not_found` — no Function node matches the `qualified_name` suffix
- `ambiguous_qualified_name` — pattern matched multiple symbols; `matches` lists candidates
- `validation_error` — invalid argument (e.g. special characters in `qualified_name`)

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

---

## Production deploy on iMac

> Extracted from former root `CLAUDE.md` during UAA Phase H1 CLAUDE.md
> decompose (2026-05-17).

After a PR squash-merges to `develop`, rebuild and restart `palace-mcp` with:

```bash
bash paperclips/scripts/imac-deploy.sh
```

The script must run **on the iMac** (SSH in first, then invoke locally).

- Pinned deploy: `bash paperclips/scripts/imac-deploy.sh --target <sha>`
- Assert extractor: `bash paperclips/scripts/imac-deploy.sh --expect-extractor symbol_index_typescript`
- Rollback: see `paperclips/scripts/imac-deploy.README.md` — tag `prev_image`
  from `imac-deploy.log` and `docker compose up -d --no-build palace-mcp`

Prerequisites and all five deploy gotchas are documented in
`paperclips/scripts/imac-deploy.README.md`.

## AGENTS.md deploy on iMac

After a release-cut merges to `main`, update live agent role files with:

```bash
bash paperclips/scripts/imac-agents-deploy.sh
```

The script must run **on the iMac** (SSH in first, then invoke locally).

- Pinned deploy: `bash paperclips/scripts/imac-agents-deploy.sh --target-sha <sha>`
- Rollback: see `paperclips/scripts/imac-agents-deploy.README.md`

No Docker needed — the script copies rendered AGENTS.md files from a
temporary `origin/main` worktree to live agent bundle directories.
Paperclip reads AGENTS.md fresh on each agent run, so no restart is required.

## Docker Compose Profiles

Services use explicit profile opt-in:

```bash
docker compose --profile review up -d    # palace-mcp + neo4j
docker compose --profile analyze up -d   # analyze mode
docker compose --profile full up -d      # full mode
```

No profile → no services start (intentional — forces explicit opt-in).

## Environment

Copy `.env.example` to `.env` and fill real values before starting
compose. Required at minimum: `NEO4J_PASSWORD`.

`PALACE_DEFAULT_GROUP_ID` (default `project/gimle`) namespaces all
Issue/Comment/Agent/IngestRun nodes. Do **not** change casually — it
determines which rows ingest writes against and GC scopes on.

## Mounting project repos for palace.git.*

`palace-mcp` exposes 5 read-only git tools (`palace.git.log`, `.show`,
`.blame`, `.diff`, `.ls_tree`). Each tool takes a `project` slug that
must correspond to a directory bind-mounted at `/repos/<slug>` inside
the container.

**Currently mounted projects (docker-compose.yml):**

| Slug         | Host path                                                                           | Mount                    |
|--------------|-------------------------------------------------------------------------------------|--------------------------|
| `gimle`      | `/Users/Shared/Ios/Gimle-Palace`                                                    | `/repos/gimle:ro`        |
| `oz-v5-mini` | `services/palace-mcp/tests/extractors/fixtures/oz-v5-mini-project` (repo-relative) | `/repos/oz-v5-mini:ro`   |
| `uw-android` | `/Users/Shared/Android/unstoppable-wallet-android`                                  | `/repos/uw-android:ro`   |
| `uw-ios-mini`| `services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project` (repo-relative) | `/repos/uw-ios-mini:ro` |
| `uw-ios`     | `/Users/Shared/Ios/unstoppable-wallet-ios`                                          | `/repos/uw-ios:ro`       |
| HS Kits (parent) | `/Users/Shared/Ios/HorizontalSystems` (41 repos; GIM-182 `uw-ios` bundle)   | `/repos-hs:ro`           |

### Non-iMac contributors

Real-project bind-mounts (`gimle`, `uw-android`, `uw-ios`) use absolute Mac paths
(`/Users/Shared/...`) for operator-iMac convention. Non-iMac contributors
should:

- Create `docker-compose.override.yml` redirecting these paths to local clones, OR
- Run `docker compose --profile review up` excluding affected services and use only
  fixture-based mounts (paths under `./services/palace-mcp/tests/extractors/fixtures/`)
  which work cross-platform.

The HS parent mount (`/repos-hs`) serves all 41 UW-iOS bundle members via
`parent_mount="hs"` + `relative_path` parameters in `register_project`. Each Kit
resolves to `/repos-hs/<relative_path>` inside the container. Non-iMac contributors
should override the host path in `docker-compose.override.yml`.

**To add a new project:**
1. Add a bind-mount entry to `docker-compose.yml` under `palace-mcp.volumes`:
   ```yaml
   - /path/to/your/repo:/repos/your-slug:ro
   ```
2. Restart the `palace-mcp` container (`docker compose --profile review up -d --force-recreate palace-mcp`).
3. Optionally register the project in Neo4j via `palace.memory.register_project` so
   it appears in `palace.memory.health` without the `git_repos_unregistered` warning.

**Security notes:**
- All bind-mounts are read-only (`:ro`).
- `git` commands run with a sanitized environment (`GIT_CONFIG_NOSYSTEM=1`,
  `PATH=/usr/bin:/bin`, no `HOME` git config) — the container cannot write
  to or exfiltrate credentials from mounted repos.
- Only whitelisted git verbs (`log`, `show`, `blame`, `diff`, `ls-tree`,
  `cat-file`) are executed; write verbs are blocked at the subprocess layer.
