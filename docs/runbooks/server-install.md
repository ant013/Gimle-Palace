# Palace Server Install — Operator Runbook

**Audience:** operator deploying palace-mcp + Neo4j on a Linux server.
**Scope:** CPU-first server profile (no Xcode, no GPU required for baseline).
**Companion:** `docs/runbooks/productized-runtime-smoke.md` covers MacBook Xcode smoke.

---

## 1. Server Requirements

| Resource | Minimum | Recommended |
|---|---|---|
| CPU | 4 cores | 8+ cores |
| RAM | 16 GB | 32–64 GB |
| Disk | 50 GB SSD | 200 GB NVMe (Neo4j + model cache + repos) |
| Linux kernel | 5.4 (Docker 20.10+) | 5.15+ |
| Docker Engine | 20.10+ | 24+ |
| Docker Compose | v2.5+ | v2.20+ |
| Internet (first run) | Required for model download | — |

**GPU:** Not required. Qodo-Embed-1-1.5B runs on CPU. A GPU (CUDA 12+) speeds up embedding ~10×; add `runtime: nvidia` to palace-mcp in a compose override if a GPU is present.

Check Docker version:
```bash
docker --version
docker compose version
```

---

## 2. Initial Setup

### 2.1 Clone the repository

```bash
git clone git@github.com:ant013/Gimle-Palace.git /srv/palace/gimle
cd /srv/palace/gimle
```

### 2.2 Create directories and set permissions

palace-mcp runs as UID 1000 (`appuser`). Create host dirs owned by UID 1000:

```bash
# Model cache (~3 GB after first warm-up)
sudo mkdir -p /data/palace-model-cache
sudo chown -R 1000:1000 /data/palace-model-cache

# Tantivy FTS index
sudo mkdir -p /data/palace-tantivy
sudo chown -R 1000:1000 /data/palace-tantivy

# Repo parent (all repos live here as subdirs)
sudo mkdir -p /srv/repos
# Repos themselves must be readable by UID 1000:
# Option A — world-readable: chmod -R o+rX /srv/repos/<repo>
# Option B — chown: sudo chown -R 1000:1000 /srv/repos/<repo>
```

### 2.3 Clone repos under the repo parent

```bash
# Example: Gimle-Palace
git clone git@github.com:ant013/Gimle-Palace.git /srv/repos/gimle
# Example: unstoppable-wallet-ios
git clone git@github.com:horizontalsystems/unstoppable-wallet-ios.git /srv/repos/uw-ios
# Example: unstoppable-wallet-android
git clone git@github.com:horizontalsystems/unstoppable-wallet-android.git /srv/repos/uw-android
```

Ensure UID 1000 can read each repo:
```bash
sudo chown -R 1000:1000 /srv/repos/gimle /srv/repos/uw-ios /srv/repos/uw-android
```

### 2.4 Create `.env`

```bash
cp .env.server.example .env
```

Edit `.env` — required fields:

```bash
# Generate a strong password:
NEO4J_PASSWORD=$(openssl rand -base64 32)
echo "NEO4J_PASSWORD=$NEO4J_PASSWORD" >> .env  # or edit the placeholder

# Set your OpenAI key:
OPENAI_API_KEY=sk-...

# Set the repo parent:
PALACE_REPO_PARENT=/srv/repos
```

Tune Neo4j memory to your host RAM (rule of thumb: heap = RAM/4, pagecache = RAM/4):

| Host RAM | NEO4J_HEAP_MAX | NEO4J_PAGECACHE |
|---|---|---|
| 16 GB | 4G | 4G |
| 32 GB | 8G | 8G |
| 64 GB | 16G | 16G |

---

## 3. Build the Image

```bash
PALACE_GIT_SHA=$(git rev-parse HEAD)
docker compose -f docker-compose.server.yml build --build-arg GIT_SHA="$PALACE_GIT_SHA"
```

First build downloads ~430–530 MB of ML packages (torch). Allow 5–15 minutes on a clean host. Subsequent builds use the Docker layer cache.

---

## 4. Pre-warm the Model Cache

Download Qodo-Embed-1-1.5B (~3 GB) into the persistent cache volume before starting the service. This only runs once (or after `--level=reclaim` cleanup).

```bash
docker compose -f docker-compose.server.yml --profile cache-warm run --rm cache-warm
```

Expected output:
```
[cache-preflight] model=Qodo/Qodo-Embed-1-1.5B status=present ...
cache-warm: model cache ready
```

After success, set in `.env`:
```
PALACE_EMBEDDING_LOCAL_ONLY=1
```

This makes palace-mcp fail fast if the cache is missing or stale on subsequent starts.

---

## 5. Start the Stack

```bash
docker compose -f docker-compose.server.yml --profile server up -d
```

Verify both services are healthy:
```bash
docker compose -f docker-compose.server.yml ps
```

Expected:
```
NAME           STATUS          PORTS
gimle-neo4j-1           running (healthy)   ...
gimle-palace-mcp-1      running (healthy)   127.0.0.1:8080->8000/tcp
```

---

## 6. Health Checks

```bash
# Neo4j HTTP admin (internal bridge only — use docker exec):
docker exec -it $(docker compose -f docker-compose.server.yml ps -q neo4j) \
  wget -qO- http://localhost:7474

# palace-mcp healthz:
curl -fsS http://localhost:8080/healthz

# MCP tools list:
curl -fsS -X POST \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' \
  http://localhost:8080/mcp | python3 -m json.tool | head -20
```

Neo4j bolt port is **not exposed to the host** by default (internal bridge only). To allow loopback-only admin access, add to `docker-compose.override.yml`:

```yaml
services:
  neo4j:
    ports:
      - "127.0.0.1:7474:7474"  # HTTP admin (loopback-only)
      - "127.0.0.1:7687:7687"  # Bolt (loopback-only)
```

---

## 7. Compose Override Examples

### Model cache on host bind-mount (recommended for multi-service hosts)

`docker-compose.override.yml`:
```yaml
services:
  palace-mcp:
    volumes:
      - /data/palace-model-cache:/data/hf-cache
```

`.env`:
```
PALACE_HF_CACHE_DIR=/data/hf-cache
```

### Repo parent bind-mount (different parent path)

`.env`:
```
PALACE_REPO_PARENT=/data/repos
```

### Increase Neo4j memory for 64 GB host

`.env`:
```
NEO4J_HEAP_INITIAL=8G
NEO4J_HEAP_MAX=16G
NEO4J_PAGECACHE=16G
NEO4J_MEM_LIMIT=32g
```

### palace-mcp on different port

`.env`:
```
PALACE_MCP_PORT=9090
```

### Enable palace-mcp on all interfaces (behind a reverse proxy)

`.env`:
```
PALACE_MCP_HOST=0.0.0.0
```

Only do this if a reverse proxy (nginx, Caddy) handles TLS and access control.

### Local-only embeddings (no network after first warm-up)

`.env`:
```
PALACE_EMBEDDING_LOCAL_ONLY=1
```

---

## 8. Backup and Restore

### Neo4j data

Neo4j stores graph data in the `neo4j_data` named volume.

**Backup:**
```bash
docker compose -f docker-compose.server.yml stop neo4j
docker run --rm \
  -v $(basename $(pwd))_neo4j_data:/data \
  -v /backup:/backup \
  neo4j:5.26.0 \
  neo4j-admin database dump neo4j --to-path=/backup/
docker compose -f docker-compose.server.yml start neo4j
```

**Restore:**
```bash
docker compose -f docker-compose.server.yml stop neo4j
docker run --rm \
  -v $(basename $(pwd))_neo4j_data:/data \
  -v /backup:/backup \
  neo4j:5.26.0 \
  neo4j-admin database load neo4j --from-path=/backup/ --overwrite-destination=true
docker compose -f docker-compose.server.yml start neo4j
```

### Model cache

The HF/Qodo model cache is stored in the `palace-hf-cache` named volume (or a host bind-mount if overridden). It can be re-warmed at any time — it is not primary data.

**Backup (optional):**
```bash
docker run --rm \
  -v $(basename $(pwd))_palace-hf-cache:/src:ro \
  -v /backup:/backup \
  busybox \
  tar czf /backup/palace-hf-cache-$(date +%Y%m%d).tar.gz -C /src .
```

**Restore (alternative to re-warm):**
```bash
docker run --rm \
  -v $(basename $(pwd))_palace-hf-cache:/dst \
  -v /backup:/backup \
  busybox \
  tar xzf /backup/palace-hf-cache-<date>.tar.gz -C /dst
```

### What NOT to back up

- `palace-tantivy-data` — Tantivy FTS index is rebuilt automatically from Neo4j.
- `codebase-memory-cache` — Codebase-memory cache is rebuilt from source repos.

---

## 9. Preflight Checks (startup)

The `entrypoint.sh` runs before the MCP server starts and exits non-zero on:

| Check | Fail condition |
|---|---|
| Tantivy dir | Not mounted or not writable by UID 1000 |
| NEO4J_PASSWORD | Empty or equals "changeme" |
| HF cache | Directory absent AND `PALACE_EMBEDDING_LOCAL_ONLY=1` |

It prints (without revealing secret values):
- `[preflight] neo4j-uri=<uri> auth=configured bolt-host-exposed=no`
- `[preflight] hf-cache=<path> local-only=<0|1>`
- `[preflight] repo=<path> status=mounted|absent`

View preflight output:
```bash
docker compose -f docker-compose.server.yml logs palace-mcp | grep preflight
```

---

## 10. MacBook Xcode Smoke vs. Server Indexing

| Concern | MacBook (`docker-compose.yml`) | Server (`docker-compose.server.yml`) |
|---|---|---|
| SCIP index generation | Xcode build on Mac host | Not supported (no Xcode) |
| Repo mounts | Absolute Mac paths (`/Users/Shared/...`) | `PALACE_REPO_PARENT` env var |
| SSH key mounts | `~/.ssh/id_ed25519`, palace_ops keys | None (use `PALACE_OPS_HOST=local`) |
| Model cache | Named volume or Mac bind-mount | Host bind-mount (`/data/palace-model-cache`) |
| Neo4j bolt | Exposed to host via `docker-compose.override.yml` | Internal bridge only |
| palace-mcp port | `8080` | `127.0.0.1:8080` (loopback-only) |

**Xcode smoke** (SCIP generation, iOS build) must run on a MacBook. The server only handles indexing and MCP queries against pre-generated SCIP indexes.

---

## 11. Stopping and Cleanup

```bash
# Stop stack:
docker compose -f docker-compose.server.yml --profile server down

# Stop and remove volumes (DESTRUCTIVE — deletes Neo4j data and model cache):
docker compose -f docker-compose.server.yml --profile server down -v

# Selective cleanup — see scripts/palace-cleanup.sh for fine-grained control:
bash scripts/palace-cleanup.sh --help
```
