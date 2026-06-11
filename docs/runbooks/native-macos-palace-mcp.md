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

## Gimle iOS seven-repo native rebaseline

Use this path for the MacBook Gimle iOS rebaseline. It is native-only and does
not call Docker compose.

Canonical inputs:

- Native MCP: `http://127.0.0.1:8765/mcp`
- Native Neo4j: `bolt://localhost:7687`
- Native env: `/Users/ant013/Android/Gimle-Palace-native/.env`
- Dedicated clone root: `/Users/Shared/Ios/Gimle-Repos/HorizontalSystems`
- Manifest:
  `services/palace-mcp/scripts/native-ios-rebaseline-manifest.json`

Preflight only:

```bash
cd /Users/Shared/Ios/Gimle-Palace/services/palace-mcp
uv run python scripts/native_ios_rebaseline.py \
  --report /tmp/native-ios-rebaseline-dry-run.json
```

Apply cleanup and ingest sequentially:

```bash
cd /Users/Shared/Ios/Gimle-Palace/services/palace-mcp
uv run python scripts/native_ios_rebaseline.py \
  --apply \
  --report /tmp/native-ios-rebaseline-apply.json
```

The helper hard-fails before ingest if a target path resolves under
`/Users/Shared/Ios/HorizontalSystems` or `/Users/ant013/Ios/uw-fresh-*`.
It cleans only the seven target project group ids, then runs each extractor
sequentially. The final JSON report includes clone state, SCIP state,
cleanup before/after counts, per-extractor MCP responses, direct Neo4j
`IngestRun` evidence, label counts, and Tantivy phase counts where applicable.

---

## Known gaps / follow-ups

- **PALACE_EMBEDDING_MAX_SYMBOLS=300000 for the seven iOS rebaseline** - this
  covers the largest current iOS project (`uw-ios-app`, 254,764 symbols). Keep
  this value above the largest expected project until the bucket policy work
  tracked as GIM-1075 lands.
- **embedding_symbol timeout 7200s** - large projects can still need multiple
  incremental passes. `uw-ios-app` reached full coverage through idempotent
  retries: 100,000 symbols, one timed-out pass that still persisted progress,
  then 59,148 symbols in the final successful pass.
- **launchd plist not auto-installed** — operator must run `launchctl bootstrap`
  per setup step 5 above
- **Tunnel/remote access** — native palace-mcp binds 0.0.0.0:8765; expose via
  cloudflared as `gimle.ant013.work` if needed for MCP client from elsewhere
  (operator's MacBook session uses localhost:8765 directly when on dev-Mac)

---

## Measured baseline (native MacBook, 2026-06-11)

| Project | Symbols | scope_project | Embedded | symbol_index_swift | embedding_symbol |
| --- | --- | --- | --- | --- | --- |
| bitcoin-core | 48,166 | 7,154 | 48,166 | 101.1s | 4,690.2s |
| bitcoin-kit | 48,490 | 219 | 48,490 | 117.4s | 3,627.5s |
| dash-kit | 49,788 | 1,596 | 49,788 | 110.5s | 3,611.4s |
| evm-kit | 44,661 | 3,181 | 44,661 | 98.6s | 3,134.6s |
| component-kit | 11,836 | 0 | 11,836 | 19.5s | 758.5s |
| hd-wallet-kit | 226 | 0 | 226 | 2.3s | 17.7s |
| uw-ios-app | 254,764 | 69,987 | 254,764 | 2,746.3s | 7,086.8s + 4,922.4s final successful pass |

Compared with the old Docker CPU baseline, the native path is the required
MacBook path for this rebaseline and uses dedicated clones under
`/Users/Shared/Ios/Gimle-Repos/HorizontalSystems`.

Semantic search smoke (post-ingest): `query=MoneroAdapter project=uw-ios-app` →
`packages/WalletCore/Sources/WalletCore/Modules/Wallet/WalletAdapterService.swift`,
backend `qodo`, `embedded_symbol_count=254764`, `eligible_symbols=254764`.
