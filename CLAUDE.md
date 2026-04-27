# Gimle Palace — Developer Guide

## Branch Flow

Single mainline: `develop`. Feature branches cut from develop, PR'd back.
`main` is an optional release-stable reference.

```
feature/GIM-N-<slug>    (all work: code, spec, plan, research, docs)
      │
      ▼  PR → squash-merge (CI green + CR paperclip APPROVE + CR GitHub review + QA evidence present)
develop                   (integration tip; iMac deploys from here)
      │
      ▼  .github/workflows/release-cut.yml (label `release-cut` on a merged PR, or workflow_dispatch)
main                      (stable release ref — tags live here)
```

**Iron rules:**
- Every change — product code, spec, plan, research, postmortem, role-file, CLAUDE.md itself — goes through a feature branch + PR. Zero direct human commits to `develop` or `main`.
- Force push forbidden on `develop` / `main`; on feature branches only `--force-with-lease` AND only when you are the sole writer of the current phase (see `git-workflow.md` fragment).
- Branch protection on develop + main: admin-bypass disabled. All required checks must pass for PR merge. `main` accepts push only from `github-actions[bot]` via `release-cut.yml`.
- Feature branches live in paperclip-managed worktrees; primary repo stays on `develop`.
- **Operator/Board checkout location:** a separate clone, typically `~/<project>-board/` or `~/Android/<project>/`. Never use the production deploy checkout (`/Users/Shared/Ios/<project>/`) for spec/plan writing.

**Spec + plan location:** `docs/superpowers/specs/` and `docs/superpowers/plans/` on the feature branch. After squash-merge they land on develop. Main gets them only when `release-cut.yml` Action runs.

**Required status checks on develop:**
- `lint`
- `typecheck`
- `test`
- `docker-build`
- `qa-evidence-present` (verifies PR body has `## QA Evidence` with SHA, unless `micro-slice` label)

**CR approval path:** CR posts full compliance comment on paperclip issue AND `gh pr review --approve` on the GitHub PR (the GitHub review satisfies branch-protection's "Require PR reviews" rule).

**Release-cut procedure:** to update `main`:
1. Add label `release-cut` to a merged develop PR, OR
2. Run `gh workflow run release-cut.yml`.

The Action opens a PR `develop → main`, enables auto-merge with rebase
strategy, and (after merge) pushes an annotated tag `release-<date>-<sha>`.
Uses only the workflow's `GITHUB_TOKEN` — no PAT or App needed. No human
pushes `main`, ever.

See also:
- `paperclips/fragments/shared/fragments/git-workflow.md` — per-agent rules.
- `docs/runbooks/2026-04-19-meta-workflow-migration-rollback.md` — if branch protection or the new workflows cause a block and need to be reverted.

## Production deploy on iMac

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

## Docs layout

- `docs/superpowers/specs/YYYY-MM-DD-<slug>.md` — design specs (Board
  output). Revisions keep the old file with a deprecation banner at
  the top; new revisions add `-rev3` suffix.
- `docs/superpowers/plans/YYYY-MM-DD-GIM-<N>-<slug>.md` — TDD
  implementation plans, one per issue. `GIM-NN` placeholder is
  swapped for the real issue number when CTO formalizes in Phase 1.1.
- `docs/postmortems/YYYY-MM-DD-<incident>.md` — one file per incident
  in the three-gate analysis format established by GIM-48.
- `docs/research/` — external library verification, competitive
  analysis, extractor inventory, etc. Treat older research docs as
  historical; verify library APIs against the installed version
  before reusing any claim.

## Paperclip team workflow

Product slices of meaningful size (>200 LOC or cross-cutting) go
through the paperclip agent team rather than being implemented
inline. Canonical phase sequence:

- **1.1 Formalize** (CTO) — verify Board's spec+plan paths, swap the
  `GIM-NN` placeholder, reassign to CodeReviewer.
- **1.2 Plan-first review** (CodeReviewer) — validate every task has
  concrete test+impl+commit; flag gaps; APPROVE → reassign to
  implementer.
- **2 Implement** (MCPEngineer / PythonEngineer / …) — TDD through
  plan tasks on `feature/GIM-<N>-<slug>`; push frequently.
- **3.1 Mechanical review** (CodeReviewer) — paste
  `uv run ruff check && uv run mypy src/ && uv run pytest` output in
  APPROVE; no "LGTM" rubber-stamps.
- **3.2 Adversarial review** (OpusArchitectReviewer) — poke holes;
  findings addressed before Phase 4.
- **4.1 Live smoke** (QAEngineer) — on iMac; real MCP tool call + CLI
  + direct Cypher invariant. Evidence comment authored by
  QAEngineer.
- **4.2 Merge** — squash-merge to develop after CI green. No admin
  override.

Phase-handoff discipline is encoded in the shared-fragment
`phase-handoff.md` (submodule `paperclip-shared-fragments`, wired
into every role's `AGENTS.md`). Reassign explicitly between phases —
`status=todo` between phases is forbidden.

## Operator auto-memory

The operator's Claude Code session maintains an auto-memory store
alongside this repo. A fresh session should look there for current
slice status, paperclip API tokens, known library pitfalls, incident
lessons, and deploy notes. The repo itself assumes operator memory
exists but does not reference any single memory file by path.

## Mounting project repos for palace.git.*

`palace-mcp` exposes 5 read-only git tools (`palace.git.log`, `.show`,
`.blame`, `.diff`, `.ls_tree`). Each tool takes a `project` slug that
must correspond to a directory bind-mounted at `/repos/<slug>` inside
the container.

**Currently mounted projects (docker-compose.yml):**

| Slug    | Host path                     | Mount                    |
|---------|-------------------------------|--------------------------|
| `gimle` | `/Users/Shared/Ios/Gimle-Palace` | `/repos/gimle:ro`     |

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

## Pinning

When editing specs or plans, always reference the commit SHA or
branch state the artefact is grounded in — do not assume "current
develop" still means what it meant when a future reader lands here.
Cite a predecessor slice's merge SHA in spec headers.

## Extractors

Palace-mcp ships a pluggable extractor framework under
`services/palace-mcp/src/palace_mcp/extractors/`. Each extractor writes
domain nodes/edges to Neo4j scoped by `group_id = "project/<slug>"` and is
invoked via MCP tool `palace.ingest.run_extractor(name, project)`.

### Registered extractors

- `heartbeat` — diagnostic probe. Writes one `:ExtractorHeartbeat` node per
  run. Use to verify the pipeline is alive before running heavy extractors.
- `symbol_index_python` — Python symbol indexer. Reads a pre-generated `.scip`
  file (produced by `npx @sourcegraph/scip-python` outside the container).
  Writes occurrences into Tantivy (full-text) and `:IngestRun` + checkpoints
  into Neo4j. 3-phase bootstrap: defs/decls → user uses → vendor uses.
  Query via `palace.code.find_references(qualified_name, project)`.

### Operator workflow: Python symbol index

1. Generate `.scip` file outside the container:
   ```bash
   cd /repos/gimle
   npx @sourcegraph/scip-python index --output ./scip/index.scip
   ```

2. Set env var for palace-mcp container in `.env`:
   ```
   PALACE_SCIP_INDEX_PATHS={"gimle":"/repos/gimle/scip/index.scip"}
   ```

3. Run the extractor:
   ```
   palace.ingest.run_extractor(name="symbol_index_python", project="gimle")
   ```

4. Query references:
   ```
   palace.code.find_references(qualified_name="register_code_tools", project="gimle")
   ```

### Running an extractor

From Claude Code (or any MCP client connected to palace-mcp):

```
palace.ingest.list_extractors()
palace.ingest.run_extractor(name="heartbeat", project="gimle")
```

Response shape (success):
```json
{"ok": true, "run_id": "<uuid>", "extractor": "heartbeat",
 "project": "gimle", "duration_ms": 42,
 "nodes_written": 1, "edges_written": 0, "success": true}
```

Error envelope on failure:
```json
{"ok": false, "error_code": "invalid_slug | unknown_extractor |
 project_not_registered | repo_not_mounted | extractor_config_error |
 extractor_runtime_error | unknown", "message": "<short>",
 "extractor": "...", "project": "...", "run_id": "..."}
```

### Adding a new extractor

1. Create `src/palace_mcp/extractors/<name>.py` with a class inheriting
   `BaseExtractor`. Declare `name`, `description`, `constraints`, `indexes`
   class attributes. Implement `async def extract(self, ctx) -> ExtractorStats`.
2. Import and register in `registry.py`:
   ```python
   from palace_mcp.extractors.<name> import <ClassName>
   EXTRACTORS["<name>"] = <ClassName>()
   ```
3. Unit test in `tests/extractors/unit/test_<name>.py` (mock driver).
4. Integration test in `tests/extractors/integration/test_<name>_integration.py`
   (real Neo4j via testcontainers or compose reuse).

### Extractor foundation substrate (GIM-101a)

All production extractors build on `extractors/foundation/`:

| Module | Purpose |
|--------|---------|
| `models.py` | Pydantic v2 schemas: `SymbolOccurrence`, `IngestCheckpoint`, `EvictionRecord`, … |
| `errors.py` | `ExtractorErrorCode` (18 codes) + `ExtractorError(Exception)` dataclass |
| `identifiers.py` | `symbol_id_for(qname)` — signed-i64 blake2b hash (overflow-safe) |
| `importance.py` | `BoundedInDegreeCounter` + `importance_score()` 5-component formula |
| `tantivy_bridge.py` | `TantivyBridge` async context manager wrapping tantivy-py |
| `schema.py` | `ensure_custom_schema()` — idempotent Neo4j schema with drift detection |
| `checkpoint.py` | `write_checkpoint`, `reconcile_checkpoint`, `create_ingest_run` |
| `eviction.py` | 3-round eviction (`run_eviction`) — never deletes def/decl |
| `circuit_breaker.py` | `check_phase_budget`, `check_resume_budget` — hard caps |
| `synthetic_harness.py` | Deterministic 70M-occurrence stress generator |

**Phase bootstrap order (per phase start):**
1. `check_resume_budget(previous_error_code)` — block budget-exceeded restarts
2. `ensure_custom_schema(driver)` — idempotent schema bootstrap
3. `check_phase_budget(nodes_written_so_far, ...)` — hard cap pre-flight
4. Process occurrences → `tantivy_bridge.add_or_replace_async()`
5. `write_checkpoint(driver, ...)` — after Tantivy commit
6. On restart: `reconcile_checkpoint(checkpoint, actual_doc_count)` — verify integrity

**Tantivy volume** (docker-compose): named volume `palace-tantivy-data` at
`/var/lib/palace/tantivy` inside container. Service runs as uid 1000 (non-root).
`entrypoint.sh` checks write access and fails fast on ownership mismatch.

**GDS plugin caveat**: eviction rounds 1-3 use standard Cypher (`DETACH DELETE`),
not GDS algorithms. GDS is optional — eviction works without it.

### Extractor env vars (GIM-101a)

All vars in `PalaceSettings` (config.py), prefix `PALACE_`:

| Variable | Default | Description |
|----------|---------|-------------|
| `PALACE_MAX_OCCURRENCES_TOTAL` | 50 000 000 | Global hard cap across all projects |
| `PALACE_MAX_OCCURRENCES_PER_PROJECT` | 10 000 000 | Per-project hard cap |
| `PALACE_IMPORTANCE_THRESHOLD_USE` | 0.05 | Round-1 eviction floor for `use` nodes |
| `PALACE_MAX_OCCURRENCES_PER_SYMBOL` | 5 000 | Round-2 per-symbol cap |
| `PALACE_RECENCY_DECAY_DAYS` | 30.0 | Half-life for recency_decay() |
| `PALACE_TANTIVY_INDEX_PATH` | (required) | Host path for Tantivy index |
| `PALACE_TANTIVY_HEAP_MB` | 100 | Tantivy writer heap in MB |
| `PALACE_SCIP_INDEX_PATHS` | `{}` | JSON map `{slug: path}` for SCIP extractors |

### Known limitations

- **`palace.memory.health()` shows only paperclip ingest runs**, not
  extractor runs (`memory/health.py:46` hardcodes `source="paperclip"`).
  Query extractor runs via `palace.memory.lookup(entity_type="IngestRun",
  filters={"source": "extractor.<name>"})`. UI-friendly health grouping
  is a followup.
- **No scheduler** — extractor runs are manual via MCP tool. Cron trigger
  is a followup.
- **No concurrent runs** — palace-mcp's event loop serializes MCP tool
  calls. A heavy extractor blocks other tools during its run.
