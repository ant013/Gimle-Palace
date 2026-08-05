# Native macOS palace-mcp deploy (MPS GPU)

Runbook for running palace-mcp natively on macOS (no Docker), using PyTorch MPS
for embedding extractor GPU acceleration.

**When to use:** dev-Mac / Apple Silicon host that owns the embedding workload.
Docker container loses MPS access; native delivers ~37× end-to-end speedup
(measured uw-ios-app, 47k vectors in 60min on M1 vs ~37h Docker CPU baseline).

**Don't use on iMac (Intel)** — no MPS; stay on Docker per
`docs/runbooks/imac-palace-mcp-docker-deploy.md`.

---

## Prerequisites

- Apple Silicon macOS (M1+)
- Homebrew + `brew install neo4j` (running on port 7687)
- `uv` or Python 3.12 + venv at `/Users/$USER/Android/Gimle-Palace-native/.venv`
- Source repo at `/Users/$USER/Android/Gimle-Palace` (current branch must include
  the `PALACE_REPOS_ROOT`-aware runner — see PR #357)
- HorizontalSystems kits under `/Users/$USER/Ios/HorizontalSystems/`
- SCIP indexes pre-built under each kit's `scip/index.scip`

---

## One-time setup

```bash
# 1. Native venv with editable palace-mcp install
cd /Users/$USER/Android/Gimle-Palace
python3.12 -m venv ../Gimle-Palace-native/.venv
source ../Gimle-Palace-native/.venv/bin/activate
pip install -e services/palace-mcp

# 2. Neo4j password (one-time, free port 7687 of any Docker neo4j first)
docker stop $(docker ps -q --filter publish=7687) 2>/dev/null || true
brew services start neo4j
sleep 5
cypher-shell -a bolt://localhost:7687 -u neo4j -p neo4j \
  "ALTER CURRENT USER SET PASSWORD FROM 'neo4j' TO '<NEW_PASSWORD>'"

# 3. Symlink HS parent_mount (no sudo — user-owned)
ln -s /Users/$USER/Ios/HorizontalSystems /Users/$USER/Ios-hs

# 4. .env file
cat > ../Gimle-Palace-native/.env <<'EOF'
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=<NEW_PASSWORD>
OPENAI_API_KEY=sk-dummy-not-used-for-qodo
PALACE_REPOS_ROOT=/Users/ant013/Ios
PALACE_HF_CACHE_DIR=/Users/ant013/.cache/palace-hf-cache
HF_HOME=/Users/ant013/.cache/palace-hf-cache
TRANSFORMERS_CACHE=/Users/ant013/.cache/palace-hf-cache
PALACE_TANTIVY_INDEX_PATH=/Users/ant013/.cache/palace-tantivy
PALACE_ADR_BASE_DIR=/Users/ant013/.cache/palace-adr
PALACE_EMBEDDING_LOCAL_ONLY=0
PALACE_EMBEDDING_MAX_SYMBOLS=50000
PALACE_GIT_SHA=native-dev
EOF

# 5. (Optional) launchd auto-start
cp services/palace-mcp/scripts/work.ant013.palace-mcp-native.plist \
   ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) \
  ~/Library/LaunchAgents/work.ant013.palace-mcp-native.plist
```

---

## Daily ops

```bash
# Start manually (foreground)
services/palace-mcp/scripts/launch_native_macos.sh

# Start daemonized (writes pidfile)
services/palace-mcp/scripts/launch_native_macos.sh --daemon

# Restart (launchd-managed)
launchctl kickstart -k gui/$(id -u)/work.ant013.palace-mcp-native

# Health check
curl -s http://localhost:8765/healthz   # expect 200

# Logs
tail -F ~/Library/Logs/palace-mcp-native/palace-mcp.log
```

---

## Project ingest (via direct MCP HTTP, bypassing Docker scripts)

The native deploy does **not** use `ingest_swift_kit.sh` / `ingest_xcode_app.sh`
because those scripts call `docker compose up -d --force-recreate palace-mcp`.
Instead, call MCP tools directly. Reference: `/tmp/native-mcp-call.py` helper
in PR #357 thread, or use any MCP client.

For incremental updates of already registered Gimle-Repos copies, follow
[the canonical Gimle-Repos replay preflight](gimle-repos-incremental-replay.md).
Do not treat a nullable `Project.indexed_commit` summary as permission to run a
full analysis: the extractor response is the authority for its durable
incremental checkpoint.

```python
# Register
palace.memory.register_project(
    slug="uw-ios-app",
    name="unstoppable-wallet-ios",
    parent_mount="hs",
    relative_path="unstoppable-wallet-ios",
    language="swift",
    framework="xcode",
)

# Extract symbols
palace.ingest.run_extractor(
    name="symbol_index_swift",
    project="uw-ios-app",
    scip_path="scip/index.scip",  # repo-relative
)

# Embed (MPS-accelerated, ~13/sec → 50k in ~64min)
palace.ingest.run_extractor(name="embedding_symbol", project="uw-ios-app")
```

---

## Known gaps / follow-ups

- **PALACE_EMBEDDING_MAX_SYMBOLS=50000 cap** — bucket policy may starve project
  methods when dependencies dominate; tracked as GIM-1075
- **embedding_symbol timeout 7200s** — 50k on MPS ≈ 64min; extractor is
  incremental + idempotent so retry is cheap
- **launchd plist not auto-installed** — operator must run `launchctl bootstrap`
  per setup step 5 above
- **Tunnel/remote access** — native palace-mcp binds 0.0.0.0:8765; expose via
  cloudflared as `gimle.ant013.work` if needed for MCP client from elsewhere
  (operator's MacBook session uses localhost:8765 directly when on dev-Mac)

---

## Measured baseline (M1 dev-Mac, 2026-05-30)

| Project | Symbols | scope_project | Embedded | symbol_index_swift | embedding_symbol |
| --- | --- | --- | --- | --- | --- |
| hs-extensions | 219 | 219 | 219 | 2.6s | 26.3s |
| uw-ios-app | 253,365 | 70,697 | 50,000 (cap) | 201.7s | ≈3850s |

Compared with iMac Docker CPU baseline (uw-ios-app): symbol_index_swift ≈ 200s
(parity), embedding_symbol ≈ 12 hours (37× slower).

Semantic search smoke (post-ingest): `query=MoneroAdapter project=uw-ios-app` →
`Unstoppable/Core/Adapters/MoneroAdapter.swift`, score 0.935, lexical 1.0.
