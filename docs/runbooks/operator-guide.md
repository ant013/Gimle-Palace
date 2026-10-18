# Palace Operator Guide

> **Audience:** operator setting up or running Gimle Palace on the iMac deploy
> host. Covers the path from fresh clone to verified runtime smoke and semantic
> analysis. No chat history required.

---

## 1. Prerequisites

### Hardware

| Item | Minimum |
|---|---|
| macOS | 13+ (Ventura) |
| RAM | 32 GB (Neo4j alone reserves up to 16 GB) |
| Disk | 100 GB free (Neo4j data, model caches, repo clones) |
| Docker Desktop | running, 8 GB+ memory allocated |

### Software

Run each check. All must pass before proceeding.

```bash
sw_vers                          # macOS 13+
docker info --format '{{.ServerVersion}}'   # Docker running
docker compose version           # v2.x
python3 --version                # 3.11+
uv --version                     # uv installed
git --version                    # 2.x
```

### Optional (for Xcode workspace builds only)

Full Xcode is required only if you need to build SCIP indexes for Xcode
workspace projects (e.g. `uw-ios-app`). Server-only operators can skip this.

```bash
xcode-select -p                  # points at Xcode.app, not CommandLineTools
xcodebuild -version              # Xcode 15+
xcodebuild -checkFirstLaunchStatus   # license accepted
```

### Accounts & secrets

You need these values before starting. Never paste them into issues, Telegram,
or chat.

| Secret | Source | Used by |
|---|---|---|
| `NEO4J_PASSWORD` | generate: `openssl rand -base64 32` | Neo4j auth |
| `OPENAI_API_KEY` | OpenAI dashboard | embedder (text-embedding-3-small) |
| `PAPERCLIP_API_KEY` | Paperclip admin UI | `palace.ops.unstick_issue` |

---

## 2. Install & First Start

### 2.1 Clone the repo

```bash
cd /Users/Shared/Ios
git clone git@github.com:<org>/Gimle-Palace.git
cd Gimle-Palace
git checkout develop && git pull --ff-only
```

### 2.2 Create `.env`

```bash
cp .env.example .env
```

Edit `.env` and fill in real values for `NEO4J_PASSWORD`, `OPENAI_API_KEY`,
and `PAPERCLIP_API_KEY`. Leave other variables at their defaults unless you
know what you are changing.

**Never commit `.env`.** It is in `.gitignore`.

### 2.3 Start services

```bash
docker compose --profile review up -d --build --wait
```

Expected: `neo4j` and `palace-mcp` containers start. Neo4j takes ~60 seconds
to become healthy on first boot (data volume initialization).

### 2.4 Verify health

```bash
# Neo4j browser
curl -sf http://localhost:7474
# Expected: HTML page (Neo4j browser UI)

# Palace MCP healthz
curl -fsS http://localhost:8080/healthz
# Expected: {"status":"ok"}

# MCP tools list
curl -sf -X POST \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' \
  http://localhost:8080/mcp | python3 -m json.tool | head -20
# Expected: JSON with "result" containing tool definitions
```

If any check fails, see [Common Failures](#9-common-failures--troubleshooting).

### 2.5 Deploy APOC trigger (first time only)

The `require_group_id` trigger prevents nodes without `group_id` from being
created. Run once after the first Neo4j start:

```bash
PW=$(grep ^NEO4J_PASSWORD= .env | cut -d= -f2)

docker exec gimle-palace-neo4j-1 cypher-shell -u neo4j -p "$PW" "
CALL apoc.trigger.add('require_group_id',
  'UNWIND \$createdNodes AS n
   WITH n WHERE NOT (n:Bundle OR n:Project OR n:IngestRun OR n:IngestCheckpoint)
   CALL apoc.util.validate(
     n.group_id IS NULL,
     \"node label=%s cm_id=%s missing required group_id\",
     [labels(n)[0], coalesce(n.cm_id, \"<none>\")]
   ) YIELD value
   RETURN value',
  {phase:'before'}
)"
```

Verify:

```bash
docker exec gimle-palace-neo4j-1 cypher-shell -u neo4j -p "$PW" \
  "CALL apoc.trigger.show('neo4j') YIELD name, paused RETURN name, paused"
# Expected: require_group_id | false
```

---

## 3. Model Cache Setup

### Qodo model cache

The `embedding_symbol` extractor uses a local Qodo model for code embeddings
when `PALACE_EMBEDDING_LOCAL_ONLY` is set.

```bash
# Default cache location (adjustable in runtime binding)
mkdir -p /Users/Shared/models/qodo
```

If you use an existing HuggingFace cache, symlink it:

```bash
ln -sf ~/.cache/huggingface /Users/Shared/models/huggingface
```

### Local-only mode

To avoid API calls for embeddings, set in `.env`:

```
PALACE_EMBEDDING_LOCAL_ONLY=1
```

When set, the extractor uses only the local Qodo model. If the model cache
is empty or missing, the extractor will fail — see
[Local-only model cache failure](#local-only-model-cache-failure).

### Embedding limits

To cap the number of symbols embedded per run (useful for initial testing):

```
PALACE_EMBEDDING_LIMIT=500
```

Remove or leave unset for unlimited.

---

## 4. Repo Mounts

Palace-mcp accesses analyzed repos via Docker bind mounts. The `docker-compose.yml`
defines the iMac convention. Non-iMac operators override in
`docker-compose.override.yml`.

### iMac mount convention

| Host path | Container path | Purpose |
|---|---|---|
| `/Users/Shared/Ios/Gimle-Palace` | `/repos/gimle` | This repo |
| `/Users/Shared/Ios/unstoppable-wallet-ios` | `/repos/uw-ios` | UW iOS (standalone) |
| `/Users/Shared/Ios/HorizontalSystems/unstoppable-wallet-ios` | `/repos/uw-ios-app` | UW iOS app (workspace) |
| `/Users/Shared/Ios/HorizontalSystems` | `/repos-hs` | Parent mount for all HS Swift kits |
| `/Users/Shared/Android/unstoppable-wallet-android` | `/repos/uw-android` | UW Android |

### Adding a new repo mount

1. Add a volume entry to `docker-compose.override.yml` (never edit `docker-compose.yml`
   for local paths):

```yaml
services:
  palace-mcp:
    volumes:
      - /path/to/repo:/repos/my-project:ro
      - /path/to/repo/.git:/repos/my-project/.git:ro
```

2. Restart palace-mcp:

```bash
docker compose --profile review up -d palace-mcp
```

3. Verify the mount is visible inside the container:

```bash
docker compose exec palace-mcp ls /repos/my-project/
```

> **Note:** The explicit `.git` mount works around a Docker Desktop VirtioFS
> stale directory cache issue (GIM-332).

### Non-iMac setup

Create `docker-compose.override.yml` at the repo root and remap all
`/Users/Shared/...` paths to your local checkout locations. The override
file is in `.gitignore`.

---

## 5. Running Runtime Smoke

The smoke system validates that extractors run correctly on a project. It
uses **recipes** (committed, portable) and **runtime bindings** (local, never
committed).

### 5.1 Recipes

Recipes are YAML files in the repo. Two built-in examples:

| Recipe | Build system | Location |
|---|---|---|
| `bitcoin-kit` | `swift_package` | See `productized-runtime-smoke.md` §3 |
| `uw-ios-app` | `xcode_workspace` | See `productized-runtime-smoke.md` §3 |

### 5.2 Runtime binding

Create a binding for your machine. Example for the iMac:

```python
from pathlib import Path
from palace_mcp.smoke.runtime_binding import RuntimeBinding

binding = RuntimeBinding(
    repo_path=Path("/Users/Shared/Ios/HorizontalSystems/unstoppable-wallet-ios"),
    parent_mount=Path("/Users/Shared/Ios"),
    mount_name="ios",
    mcp_mount_name="ios",
    mcp_url="http://localhost:8731/mcp",
    qodo_cache_path=Path("/Users/Shared/models/qodo"),
)
```

`mcp_mount_name` must match `^[a-z][a-z0-9-]{0,15}$`.

### 5.3 Dry-run first

Always dry-run before a live smoke. Dry-run validates recipe and binding
without building SCIP, registering projects, or running extractors.

```python
from palace_mcp.smoke.runner import SmokeRunner
from palace_mcp.smoke.recipe import load_recipe_yaml

recipe = load_recipe_yaml(Path("path/to/recipe.yaml"))
runner = SmokeRunner(recipe, binding, dry_run=True)
report = asyncio.run(runner.run_smoke())

for stage in report.stages:
    print(f"  {stage.stage}: {stage.status.value}")
```

### 5.4 Live smoke

```python
runner = SmokeRunner(recipe, binding)
report = asyncio.run(runner.run_smoke())

print("PASSED" if report.passed else "FAILED")
for stage in report.stages:
    print(f"  {stage.stage}: {stage.status.value} ({stage.duration_ms}ms)")
```

### 5.5 Smoke pipeline stages

| # | Stage | What it does | Dry-run |
|---|---|---|---|
| 1 | `preflight` | Environment checks (15 validators) | runs |
| 2 | `prepare` | Copy config templates, resolve packages | runs |
| 3 | `build_scip` | Build project and emit SCIP index | skipped |
| 4 | `register_project` | Register project in palace-mcp | skipped |
| 5 | `run_extractors` | Run each extractor in recipe order | skipped |
| 6 | `report` | Emit structured JSON report | runs |

Failure in any stage skips all subsequent stages.

### 5.6 Preflight standalone

Run preflight independently to diagnose environment issues:

```python
from palace_mcp.smoke.preflight import run_preflight

report = asyncio.run(run_preflight(recipe, binding))
for check in report.checks:
    status = "PASS" if check.passed else "FAIL"
    print(f"  [{status}] {check.name}: {check.message or 'ok'}")
```

For details on all 15 preflight checks, see
[productized-runtime-smoke.md](productized-runtime-smoke.md) §7.

---

## 6. Running Semantic Analysis (`project analyze`)

This guide owns the legacy iMac Docker runtime on port `8080`. The CLI now
defaults to the native macOS runtime on port `8765` and does not manage Docker
unless explicitly requested. Therefore every Docker-starting command in this
section must pass both `--manage-runtime` and the Docker MCP URL.

### 6.1 Verify CLI entrypoint

```bash
cd services/palace-mcp
uv run python -m palace_mcp.cli project analyze --help
# Expected: help with flags --repo-path, --slug, --language-profile, etc.
```

### 6.2 Dry-run

```bash
uv run python -m palace_mcp.cli project analyze \
  --repo-path /Users/Shared/Ios/HorizontalSystems/unstoppable-wallet-ios \
  --slug uw-ios-app \
  --language-profile swift \
  --dry-run
```

### 6.3 Live run

```bash
uv run python -m palace_mcp.cli project analyze \
  --repo-path /Users/Shared/Ios/HorizontalSystems/unstoppable-wallet-ios \
  --slug uw-ios-app \
  --language-profile swift \
  --manage-runtime \
  --url http://localhost:8080/mcp \
  --report-out .gimle/runtime/project-analyze/uw-ios-app-analysis-report.md \
  --summary-out .gimle/runtime/project-analyze/uw-ios-app-analysis-summary.json
```

`--manage-runtime` allows the CLI to write the compose override and
start/recreate the legacy runtime. `--url` is required because Docker publishes
host port `8080`, while the CLI default is the already-running native service
on `8765`.

Expected output files:
- `.gimle/runtime/project-analyze/<slug>-analysis-report.md`
- `.gimle/runtime/project-analyze/<slug>-analysis-summary.json`

For per-kit Swift ingestion, see [ingest-swift-kit.md](ingest-swift-kit.md).
For Xcode app ingestion, see [xcode-app-ingest.md](xcode-app-ingest.md).

---

## 7. Do-Not-Delete List

These directories and data stores must not be deleted during routine
maintenance. Losing them costs hours to days to rebuild.

| Path / store | Why | Rebuild cost |
|---|---|---|
| `/Users/Shared/models/qodo/` | Qodo model cache | Hours (re-download + warm-up) |
| `~/.cache/huggingface/` | HuggingFace model cache | Hours (large model downloads) |
| Repo clones under `/Users/Shared/Ios/`, `/Users/Shared/Android/` | Source repos with local SCIP indexes | Minutes–hours (re-clone + re-emit SCIP) |
| Neo4j data volume (`neo4j_data`) | Knowledge graph (all extracted entities, edges, decisions) | Hours–days (full re-ingest from scratch) |
| `.gimle/runtime/project-analyze/` reports | Analysis evidence linked from issues | Cannot regenerate after source changes |
| `codebase-memory-cache` Docker volume | Code graph SQLite databases | Minutes (re-index, but loses incremental state) |
| `<repo>/scip/index.scip` files | Pre-built SCIP indexes | Minutes–hours per repo (requires Xcode build) |

**Rule:** if you are unsure whether something is safe to delete, check this
list first. When in doubt, do not delete.

---

## 8. Cleanup Policy

All cleanup commands default to **dry-run**. Destructive operations require
an explicit `--force` flag and operator confirmation.

### Safe (read-only, always okay to run)

```bash
# Check Docker disk usage
docker system df

# List dangling images
docker images -f dangling=true

# List stopped containers
docker ps -a --filter status=exited

# Check Neo4j data volume size
docker volume inspect neo4j_data --format '{{.Mountpoint}}'
du -sh "$(docker volume inspect neo4j_data --format '{{.Mountpoint}}')" 2>/dev/null \
  || echo "volume backed by Docker VM — check Docker Desktop dashboard"
```

### Reclaim (low risk, recoverable)

```bash
# Remove dangling images (not tagged, not used by any container)
docker image prune
# Prompts Y/n. Safe — only removes unreferenced layers.

# Remove build cache older than 7 days
docker builder prune --filter until=168h
# Prompts Y/n.

# Remove stopped containers (not running services)
docker container prune
# Prompts Y/n.

# Clean Python bytecode caches
find services/palace-mcp -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null
```

### Destructive (requires explicit confirmation)

> **WARNING:** These commands delete data that takes hours to rebuild.
> Triple-check before running. Never run in automated scripts without
> operator review.

```bash
# Reset Neo4j to empty (DESTROYS ALL GRAPH DATA)
# Only run if you intend a full re-ingest from scratch.
docker compose --profile review down
docker volume rm gimle-palace_neo4j_data
# Then restart: docker compose --profile review up -d --build --wait
# Then re-deploy APOC trigger (see §2.5)

# Remove all Palace SCIP indexes (forces rebuild for every repo)
find /Users/Shared/Ios -path '*/scip/index.scip' -delete

# Remove codebase-memory cache (forces full re-index)
docker volume rm gimle-palace_codebase-memory-cache

# Full Docker system prune (removes ALL unused images, containers, volumes, networks)
docker system prune --all --volumes
# DANGER: this removes neo4j_data and codebase-memory-cache too.
# Only use on a machine you are fully rebuilding.
```

---

## 9. Common Failures & Troubleshooting

### Docker rebuild hangs on ML dependencies

**Symptom:** `docker compose up --build` stalls during `pip install` of
ML packages (torch, transformers, sentence-transformers).

**Cause:** Large wheel downloads on slow connections, or pip resolver
conflicts.

**Fix:**
```bash
# Check which layer is building
docker compose --profile review logs palace-mcp --tail 30

# If truly stuck (>20 min on a single pip install):
# Ctrl+C, then rebuild with no cache
docker compose --profile review build --no-cache palace-mcp
docker compose --profile review up -d --wait
```

If the build fails on a specific package, check that your Docker Desktop
has sufficient memory (8 GB+) and that the network is not blocking PyPI.

### Neo4j auth / volume mismatch

**Symptom:** Neo4j container restarts in a loop. Logs show:
`Invalid username or password` or `Auth file mismatch`.

**Cause:** The `NEO4J_PASSWORD` in `.env` does not match the password
stored in the Neo4j data volume (set on first boot).

**Fix:**
```bash
# Option 1: Reset to match your .env password (destroys data)
docker compose --profile review down
docker volume rm gimle-palace_neo4j_data
docker compose --profile review up -d --wait
# Re-deploy APOC trigger (§2.5)

# Option 2: Change .env to match the volume's password
# (only if you remember the original password)
```

### Missing Xcode vs. server-only operation

**Symptom:** Preflight fails on `xcode_select`, `xcodebuild_version`,
or `ios_sdk_runtime` checks.

**Cause:** Full Xcode is not installed, or `xcode-select` points at
CommandLineTools instead of Xcode.app.

**Fix (if you need Xcode builds):**
```bash
xcode-select -s /Applications/Xcode.app/Contents/Developer
sudo xcodebuild -license accept
```

**Fix (server-only, no Xcode workspace builds):**
Skip Xcode-dependent recipes. Use only `swift_package` recipes that
build with `swift build` (does not require full Xcode). Set
`build_system: swift_package` in your recipe.

### Missing SCIP path

**Symptom:** `build_scip` stage fails with "SCIP output parent is not
a writable directory" or the register stage finds no SCIP index.

**Cause:** The SCIP file was not built or not copied to the expected
location.

**Fix:**
```bash
# Check if SCIP exists
ls -la /path/to/repo/scip/index.scip

# If missing, emit it:
# For Swift kits:
bash paperclips/scripts/scip_emit_swift_kit.sh <slug> \
  --repo-root /path/to/repos \
  --remote-host imac-ssh.ant013.work \
  --remote-base /Users/Shared/Ios/HorizontalSystems

# For Xcode apps:
bash paperclips/scripts/scip_emit_xcode_app.sh \
  --repo-path /path/to/repo \
  --scheme <scheme> \
  --slug <slug> \
  --relative-path <relative-path>
```

See [xcode-app-scip-emit.md](xcode-app-scip-emit.md) and
[ingest-swift-kit.md](ingest-swift-kit.md) for full details.

### Local-only model cache failure

**Symptom:** `embedding_symbol` extractor fails with model-not-found
or cache miss errors when `PALACE_EMBEDDING_LOCAL_ONLY=1`.

**Cause:** The local Qodo model cache directory is empty or does not
exist.

**Fix:**
```bash
# Verify cache exists and has content
ls -la /Users/Shared/models/qodo/

# If empty, run one embedding with local-only disabled first
# to populate the cache, then re-enable:
# 1. Unset PALACE_EMBEDDING_LOCAL_ONLY in .env
# 2. Run a small smoke (PALACE_EMBEDDING_LIMIT=10)
# 3. Re-set PALACE_EMBEDDING_LOCAL_ONLY=1 in .env
```

### Semantic matrix underfill

**Symptom:** Analysis report shows low coverage — many symbols have
no embeddings or the embedding matrix is sparse.

**Cause:** `PALACE_EMBEDDING_LIMIT` is too low, or the extractor
skipped symbols due to errors.

**Fix:**
```bash
# Check current limit
grep PALACE_EMBEDDING_LIMIT .env

# Remove or increase the limit
# Then re-run the smoke or project analyze for the affected slug

# Check extractor results in the JSON report
python3 -c "
import json, sys
r = json.load(open('.gimle/runtime/project-analyze/<slug>-analysis-summary.json'))
for e in r.get('extractors', []):
    print(f\"{e['name']}: ok={e['ok']}, symbols={e.get('symbol_count', '?')}\")
"
```

### MCP connection failures

**Symptom:** `mcp_tools_list` preflight check fails, or `register_project`
stage fails with connection errors.

**Fix:**
```bash
# Verify palace-mcp is running
curl -sf -X POST \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' \
  http://localhost:8080/mcp

# If no response, check containers
docker compose --profile review ps
docker compose --profile review logs palace-mcp --tail 30

# Restart if needed
docker compose --profile review restart palace-mcp
```

### Neo4j out of memory

**Symptom:** Neo4j container killed by OOM or becomes unresponsive
during large ingest runs.

**Fix:**
- Ensure Docker Desktop has 16 GB+ memory allocated
- The compose file sets `mem_limit: 16g` for Neo4j with heap up to 8 GB
  and page cache at 4 GB — these are tuned for the iMac; reduce if your
  machine has less RAM
- Check current usage: `docker stats gimle-palace-neo4j-1`

---

## 10. Quick Reference Card

```
# Start services
docker compose --profile review up -d --build --wait

# Health check
curl -fsS http://localhost:8080/healthz

# View logs
docker compose --profile review logs -f --tail 50

# Stop services (keeps data)
docker compose --profile review down

# Restart a single service
docker compose --profile review restart palace-mcp

# Neo4j browser
open http://localhost:7474

# MCP tool list
curl -sf -X POST -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' \
  http://localhost:8080/mcp | python3 -m json.tool | head -20
```

---

## 11. Phase 1 Features (shipped 2026-06)

The following features shipped in Phase 1 (PRs #361-#367). They are active on
`develop` as of 2026-06-01. No action is required unless you need to configure
non-default behaviour.

### S0 — Anchor symbols

Anchor symbols are high-priority qualified names pinned per project. They are
always included in semantic search candidates regardless of embedding score.

Configure via `.env`:

```
PALACE_ANCHOR_SYMBOLS='{"project/gimle":["MyModule.BalanceData","WalletKit.Transaction"]}'
```

The value is a JSON object: keys are `group_id` strings (same format as the
`project` field in MCP tool calls), values are lists of fully-qualified symbol
names. Defaults to `{}` (no anchors).

### F4.0 — Telemetry + JSONL audit sink

Every MCP tool call appends a structured record to the audit sink (if configured)
and to the service structured log. Each record includes: `timestamp`,
`tool_name`, `request_args`, `response_summary`, `latency_ms`, `error`.

Relevant `.env` keys:

| Key | Default | Notes |
|---|---|---|
| `PALACE_TELEMETRY_ENABLED` | `true` | Set `false` to suppress all audit records |
| `PALACE_AUDIT_SINK_PATH` | _(disabled)_ | Absolute path for the JSONL file; directory must exist and be writable by the container |

To write to a host path, bind-mount it or use a directory already mounted
(e.g. `/var/lib/palace/`). See [deploy-checklist.md](deploy-checklist.md) §Post-deploy
for the verification step.

### F4.1 — Qodo embedding pre-warm

Palace-mcp pre-warms the Qodo embedding model during the FastAPI lifespan startup,
eliminating the ~9 s cold-start on the first `semantic_search` call.

Relevant `.env` key:

| Key | Default | Notes |
|---|---|---|
| `PALACE_QODO_PREWARM` | `true` | Set `0` to skip pre-warm on memory-constrained hosts |

If pre-warm fails (e.g. model cache missing), startup completes with a warning
rather than crashing — the first live call incurs the cold-start penalty instead.
See [deploy-checklist.md](deploy-checklist.md) §F4.1 for the verification step.

### F4.3 — Hydration parallelization

Snippet and usage-context hydration for each `semantic_search` result hit now
runs concurrently via `asyncio.gather`. This reduces wall-clock latency for
`semantic_search` calls with `include_context=true` when there are multiple hits.
No configuration required.

### F4.4 — HNSW per-project query budget

For `semantic_search` calls that span multiple projects (multi-project `scope`),
each project now gets its own HNSW query with an individual result budget
(`per_project_k = candidate_limit(limit, 1)`). Results from all projects are
merged and re-ranked by score before the final limit is applied.

This prevents high-symbol-count projects from crowding out results from smaller
projects in multi-project scopes. No configuration required. The `per_project_k`
value is visible in telemetry logs for debugging.

---

## Related Runbooks

These runbooks cover specific workflows in detail. The guide above covers
the common path; refer to these for edge cases.

- [ingest-swift-kit.md](ingest-swift-kit.md) — per-kit Swift ingestion
  (SCIP emit on dev Mac + iMac registration)
- [xcode-app-ingest.md](xcode-app-ingest.md) — Xcode app ingestion
  (workspace builds, not SwiftPM)
- [xcode-app-scip-emit.md](xcode-app-scip-emit.md) — SCIP emit for
  Xcode app targets
- [swift-kit-prepare.md](swift-kit-prepare.md) — artefact preparation
  (Periphery, swiftinterface)
- [productized-runtime-smoke.md](productized-runtime-smoke.md) — full
  smoke system reference (recipe schema, binding schema, all 15 preflight checks)
- [neo4j-apoc-trigger-deploy.md](neo4j-apoc-trigger-deploy.md) — APOC
  trigger deployment details
- [deploy-checklist.md](deploy-checklist.md) — pre/post deploy checklist
- [uaa-live-deploy.md](uaa-live-deploy.md) — Paperclip agent deploy
  across trading/uaudit/gimle
