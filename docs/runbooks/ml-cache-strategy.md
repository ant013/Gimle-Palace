# ML Model Cache Strategy

**Issue:** GIM-917  
**Status:** Production runbook

## Overview

Qodo-Embed-1-1.5B (~3 GB) and its HuggingFace dependencies are large. This runbook defines:
- Where caches live and how they are mounted
- Environment variable precedence
- Cleanup levels (safe, reclaim, destructive)
- Preflight cache status and what each status means

## Cache Directories

| Cache | Env var | Container path | Compose default |
|---|---|---|---|
| HuggingFace/Qodo models | `PALACE_HF_CACHE_DIR` | `/data/hf-cache` | named volume `palace-hf-cache` |
| Qodo-specific (alias) | `PALACE_QODO_CACHE_DIR` | same as HF | — |
| uv wheel cache | `UV_CACHE_DIR` | build-time only | build cache mount |
| Neo4j data | — | `/data` | named volume `neo4j_data` |
| Tantivy FTS | — | `/var/lib/palace/tantivy` | named volume `palace-tantivy-data` |

### Env var precedence (HF cache root)

Inside the container, the effective cache root is resolved in this order:

1. `HF_HOME` (set by compose from `PALACE_HF_CACHE_DIR`)
2. `TRANSFORMERS_CACHE` (also set by compose as fallback)
3. `~/.cache/huggingface` (library default)

The preflight module (`cache_preflight.py`) uses the same precedence.

## Volume Mount Contract

Default (named volume, data-local to Docker):

```yaml
volumes:
  - palace-hf-cache:/data/hf-cache
```

Override to a host bind-mount in `docker-compose.override.yml` to share the
cache between projects or persist across host migrations:

```yaml
services:
  palace-mcp:
    volumes:
      - /data/palace-model-cache:/data/hf-cache
```

Set the override path in `.env`:

```
PALACE_HF_CACHE_DIR=/data/hf-cache
```

## Cache Status

The preflight module reports one of four statuses for each model:

| Status | Meaning | Local-only behaviour |
|---|---|---|
| `present` | Cache root exists, model snapshot dirs found, provenance file present | Proceed normally |
| `stale` | Cache root exists but snapshot dir or provenance file is missing (partial download) | **Fail fast** — fix or re-download |
| `absent` | Cache root does not exist | **Fail fast** — first-time download needed |
| `readonly` | Cache root exists but not writeable, world-writable, or mixed-owner | **Fail fast** — fix permissions |

### Local-only mode

Set `PALACE_EMBEDDING_LOCAL_ONLY=1` to enforce that **no network download occurs**.
The container will fail fast (before model load) if the cache is `absent`, `stale`, or `readonly`.

```bash
# Verify smoke uses cached model without network access:
docker exec -e PALACE_EMBEDDING_LOCAL_ONLY=1 palace-mcp python /app/scripts/smoke_image.py
```

## Provenance Record

After a successful cache download, the preflight module writes:

```
/data/hf-cache/palace_cache_provenance.json
```

Contents (no secrets):

```json
{
  "model_id": "Qodo/Qodo-Embed-1-1.5B",
  "source": "huggingface",
  "revision": "main",
  "cache_root": "/data/hf-cache",
  "recorded_at": "2026-01-01T00:00:00Z",
  "version_marker": "Qodo/Qodo-Embed-1-1.5B@main"
}
```

## Cleanup Levels

**Never run `docker volume prune`** — it will remove the model cache.  
Use `scripts/palace-cleanup.sh` instead:

| Level | What it removes | Removes model cache? |
|---|---|---|
| `safe` | Docker builder cache (keeps last 1 GB) + `.tmp/` workdirs | No |
| `reclaim` | `safe` + stopped containers + dangling images | No |
| `destructive` | `reclaim` + ALL named volumes (models, Neo4j, Tantivy) | **Yes** |

### Dry-run (default)

```bash
./scripts/palace-cleanup.sh --level=safe
./scripts/palace-cleanup.sh --level=reclaim
./scripts/palace-cleanup.sh --level=destructive
```

### Execute

```bash
./scripts/palace-cleanup.sh --level=safe --execute
./scripts/palace-cleanup.sh --level=reclaim --execute
# Destructive requires y/yes confirmation:
./scripts/palace-cleanup.sh --level=destructive --execute
```

### Safety guards

The cleanup script:
- Refuses to operate on `/` or `$HOME`
- Refuses paths outside `REPO_ROOT`, `/tmp`, `/var`, `/data`
- Uses `realpath` to resolve symlinks before path checks
- Requires `--execute` flag for any real action
- Requires interactive `yes` confirmation for destructive level

## First-time Model Download

On a fresh host (cache absent), start without `PALACE_EMBEDDING_LOCAL_ONLY`:

```bash
PALACE_EMBEDDING_LOCAL_ONLY=0 docker compose --profile full up -d
# Model downloads on first embedding request (5-15 min).
# Then write provenance and switch to local-only for smoke re-runs:
docker exec palace-mcp python -c "
from palace_mcp.embeddings.cache_preflight import record_cache_provenance
record_cache_provenance('Qodo/Qodo-Embed-1-1.5B', source='huggingface', revision='main')
"
```

After provenance is written, set `PALACE_EMBEDDING_LOCAL_ONLY=1` in `.env` for
subsequent operator runs.

## Smoke Re-run with Existing Cache

```bash
# Verify cache is present and model loads without network:
docker exec -e PALACE_EMBEDDING_LOCAL_ONLY=1 <container> python /app/scripts/smoke_image.py
```

Expected output includes:
```
[cache-preflight] model=Qodo/Qodo-Embed-1-1.5B status=present ...
[PASS] QodoEmbeddingBackend initialised (model cached)
```
