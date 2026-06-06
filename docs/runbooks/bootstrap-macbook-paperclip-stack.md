# Bootstrap MacBook — Paperclip Stack Parity with iMac

**Audience**: operator setting up a fresh MacBook (or any second-host macOS) to mirror the iMac production Paperclip stack — server fork, telegram plugin fork, watchdog daemon, heartbeats disabled, with Gimle/Trading/UAudit company support.

**Companion**: [docs/superpowers/specs/2026-05-10-paperclip-generic-project-team-bootstrap.md](../superpowers/specs/2026-05-10-paperclip-generic-project-team-bootstrap.md) defines the declarative bootstrap *contract*. This runbook is the *procedural* "do this on macOS" guide.

**Reference deployment**: `/Users/anton/` on iMac (`imac-ssh.ant013.work`). Paths in this runbook assume `/Users/<operator>/` — substitute your username.

---

## 0. Target architecture

After successful bootstrap, the host runs:

```
┌─ launchd (com.paperclip.server) ─────────────────┐
│   /Users/<op>/paperclip/start-paperclip.sh        │
│   → npx paperclipai run                           │
│      ↓ port 3100                                  │
│      ├── Telegram plugin (ant013 fork, per-route  │
│      │   `sendImportant`)                         │
│      ├── Companies: Gimle, Trading, UAudit, …     │
│      └── Adapters: codex_local, claude_local      │
└──────────────────────────────────────────────────┘

┌─ launchd (work.<op>.gimle-watchdog) ─────────────┐
│   Python daemon at services/watchdog/             │
│   poll_interval 120s, recovery_dry_run=false,     │
│   READ-ONLY (heartbeats off per project memory)   │
└──────────────────────────────────────────────────┘

┌─ Native Neo4j (Homebrew) ────────────────────────┐
│   bolt://localhost:7687, port 7474 HTTP           │
└──────────────────────────────────────────────────┘

┌─ Native palace-mcp uvicorn ──────────────────────┐
│   localhost:8765, MCP HTTP, code-graph reachable  │
└──────────────────────────────────────────────────┘

~/.paperclip/                                       
├── auth.json                  (Board token)        
├── settings.json              (heartbeat off)      
├── watchdog-config.yaml       (3-company tracker)  
├── watchdog.token             (read-only token)    
├── instances/default/companies/                    
│   ├── 9d8f432c-…-Gimle/                           
│   │   ├── agents/                                 
│   │   ├── codex-home/        (CODEX_HOME isolated)
│   │   └── claude-prompt-cache/                    
│   └── 09edf17a-…-Trading/                         
├── journal/                   (bootstrap audit)    
└── plugins/                   (npm-installed)      
```

---

## 1. Prerequisites

Run each check. All must pass before proceeding.

| Item | Minimum | Check |
|---|---|---|
| macOS | 13+ (Ventura) | `sw_vers` |
| Xcode (optional, Swift kits only) | 15+ | `xcodebuild -version` |
| Homebrew | latest | `brew --version` |
| Node | 20.x (via nvm) | `node -v` (must be on 20-track for paperclipai) |
| Python | 3.11+ via uv | `python3 --version && uv --version` |
| Git | 2.x | `git --version` |
| Docker Desktop | optional (legacy only) | `docker info` |

**Install missing pieces**:

```bash
# Homebrew (if missing)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# nvm + Node 20
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/master/install.sh | bash
exec $SHELL
nvm install 20
nvm alias default 20

# uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Native Neo4j (no Docker)
brew install --cask neo4j-community-edition
brew services start neo4j

# OR Neo4j as Homebrew formula:
brew install neo4j
brew services start neo4j
```

Verify Neo4j is up:

```bash
curl -sf http://localhost:7474 && echo " ✓ neo4j http"
cypher-shell -u neo4j -p '<initial password>' 'RETURN 1' && echo " ✓ neo4j bolt"
```

Set Neo4j password (first time only):

```bash
# Web UI: http://localhost:7474 → set password
# OR via cypher-shell with default neo4j/neo4j:
cypher-shell -u neo4j -p neo4j "ALTER CURRENT USER SET PASSWORD FROM 'neo4j' TO '<your-32-char-password>'"
```

Save password to `~/.paperclip/secrets/neo4j-password` (mode 600).

---

## 2. Install paperclipai server (npm canary fork)

iMac runs `paperclipai@2026.508.0-canary.0`. The canary track has our patches before they roll into stable.

```bash
nvm use 20
npm install -g paperclipai@2026.508.0-canary.0
which paperclipai     # expect ~/.nvm/versions/node/v20.x/bin/paperclipai
paperclipai --version
```

Create the runtime home:

```bash
mkdir -p ~/paperclip/logs
mkdir -p ~/.paperclip/{instances/default/companies,journal,backups,plugins,projects}
```

---

## 3. Install forked telegram plugin

```bash
cd ~/paperclip
git clone https://github.com/ant013/paperclip-plugin-telegram.git
cd paperclip-plugin-telegram
git checkout feat/per-route-send-important   # current production branch on iMac
npm install
npm run build
```

Register the plugin path with Paperclip:

```bash
mkdir -p ~/.paperclip/plugins
cd ~/.paperclip/plugins
# Symlink or npm install local checkout
npm install ~/paperclip/paperclip-plugin-telegram
```

Telegram bot token + chat IDs must be configured **after** company creation (Section 8). Save your bot token to `~/.paperclip/secrets/telegram-bot-token` (mode 600) for now.

---

## 4. Install watchdog daemon

The watchdog is part of the Gimle-Palace repo (`services/watchdog/`). It's **read-only** in Gimle (no auto-wake; per `reference_gimle_no_autowake.md`) but still useful for monitoring + Telegram alerts.

```bash
# Clone Gimle-Palace if not already
cd ~/Android
git clone https://github.com/ant013/Gimle-Palace.git
cd Gimle-Palace

# Install watchdog via uv
cd services/watchdog
uv sync
```

Create watchdog config from iMac's:

```bash
mkdir -p ~/.paperclip
cat > ~/.paperclip/watchdog-config.yaml <<'YAML'
version: 1
paperclip:
  base_url: http://localhost:3100
  api_key_source: file:~/.paperclip/watchdog.token
companies:
  # Replace IDs after Section 8 creates them
  - id: <gimle-uuid>
    name: gimle
    thresholds:
      died_min: 3
      hang_etime_min: 60
      idle_cpu_ratio_max: 0.005
      hang_stream_idle_max_s: 300
  - id: <trading-uuid>
    name: trading
    thresholds:
      died_min: 3
      hang_etime_min: 60
      idle_cpu_ratio_max: 0.005
      hang_stream_idle_max_s: 300
daemon:
  poll_interval_seconds: 120
  recovery_enabled: true
  recovery_dry_run: false      # set true to test without action
  max_actions_per_tick: 1
cooldowns:
  per_issue_seconds: 300
  per_agent_cap: 3
  per_agent_window_seconds: 900
logging:
  path: ~/.paperclip/watchdog.log
  level: INFO
  rotate_max_bytes: 10485760
  rotate_backup_count: 5
escalation:
  post_comment_on_issue: true
handoff:
  # all auto-handoff features off (matches iMac for Gimle)
  handoff_alert_enabled: false
  handoff_cross_team_enabled: false
  handoff_ownerless_enabled: false
  handoff_infra_block_enabled: false
  handoff_stale_bundle_enabled: false
  handoff_auto_repair_enabled: false
YAML
```

Generate a read-only watchdog token (after step 8 — board token can mint this):

```bash
# Placeholder for now; populate after Section 8
echo "<watchdog-readonly-token>" > ~/.paperclip/watchdog.token
chmod 600 ~/.paperclip/watchdog.token
```

---

## 5. Configure secrets (.env, auth.json)

```bash
mkdir -p ~/.paperclip/secrets
chmod 700 ~/.paperclip/secrets

# 5.1 paperclipai server auth (Board token from prod paperclip UI sign-in)
cat > ~/.paperclip/auth.json <<JSON
{
  "version": 1,
  "credentials": {
    "https://paperclip.<your-domain>": {
      "apiBase": "https://paperclip.<your-domain>",
      "token": "pcp_board_<…>",
      "createdAt": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
      "updatedAt": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    }
  }
}
JSON
chmod 600 ~/.paperclip/auth.json

# 5.2 GitHub token for paperclipai runtime
echo "ghp_<…>" > ~/.paperclip/secrets/github-token
chmod 600 ~/.paperclip/secrets/github-token

# 5.3 Optional legacy OpenAI key
# Only needed if you intentionally switch PALACE_MEMORY_EMBEDDER=openai.
echo "sk-proj-<…>" > ~/.paperclip/secrets/openai-api-key
chmod 600 ~/.paperclip/secrets/openai-api-key
```

If running palace-mcp natively too (see Section 14), also put an env file at `Gimle-Palace/.env`:

```bash
cat > ~/Android/Gimle-Palace/.env <<ENV
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=$(cat ~/.paperclip/secrets/neo4j-password)
PALACE_MEMORY_EMBEDDER=qodo
PALACE_HF_CACHE_DIR=$HOME/.cache/palace-hf-cache
PALACE_EMBEDDING_LOCAL_ONLY=0
PALACE_EMBEDDING_MAX_SYMBOLS=100000
PALACE_TANTIVY_INDEX_PATH=$HOME/.cache/palace-tantivy
HF_HOME=$HOME/.cache/palace-hf-cache
PALACE_ADR_BASE_DIR=$HOME/.cache/palace-adr
PALACE_GIT_SHA=native-dev
PALACE_REPOS_ROOT=$HOME/Ios
CODEBASE_MEMORY_MCP_BINARY=$HOME/.local/bin/codebase-memory-mcp
PAPERCLIP_API_KEY=$(cat ~/.paperclip/auth.json | python3 -c "import json,sys; print(json.load(sys.stdin)['credentials'][list(json.load(open('/dev/stdin'))['credentials'])[0]]['token'])")
ENV
chmod 600 ~/Android/Gimle-Palace/.env
```

If you explicitly need the legacy OpenAI Graphiti embedder, append:

```bash
cat >> ~/Android/Gimle-Palace/.env <<ENV
PALACE_MEMORY_EMBEDDER=openai
OPENAI_API_KEY=$(cat ~/.paperclip/secrets/openai-api-key)
ENV
```

---

## 6. Bootstrap launchd autostart

### 6.1 paperclipai server

Create `start-paperclip.sh`:

```bash
cat > ~/paperclip/start-paperclip.sh <<'SH'
#!/bin/zsh
set -eu

LOG_DIR="$HOME/paperclip/logs"
OUT_LOG="$LOG_DIR/paperclip.log"
ERR_LOG="$LOG_DIR/paperclip.error.log"
START_LOG="$LOG_DIR/paperclip.autostart.log"
NODE_BIN="$HOME/.nvm/versions/node/v20.20.2/bin"
PAPERCLIP_BIN="$NODE_BIN/paperclipai"

mkdir -p "$LOG_DIR"
{
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] autostart invoked"
  /bin/sleep "${PAPERCLIP_START_DELAY_SECONDS:-20}"

  if /usr/sbin/lsof -nP -iTCP:3100 -sTCP:LISTEN >/dev/null 2>&1; then
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] port 3100 already listening; exit"
    exit 0
  fi
  if /usr/bin/pgrep -f "paperclipai run" >/dev/null 2>&1; then
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] paperclipai run already present; exit"
    exit 0
  fi
  if [ ! -x "$PAPERCLIP_BIN" ]; then
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] missing executable: $PAPERCLIP_BIN" >&2
    exit 1
  fi

  exec "$PAPERCLIP_BIN" run >>"$OUT_LOG" 2>>"$ERR_LOG"
} >>"$START_LOG" 2>&1
SH
chmod +x ~/paperclip/start-paperclip.sh
```

Create the launchd plist `~/Library/LaunchAgents/com.paperclip.server.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>EnvironmentVariables</key>
    <dict>
        <key>HOME</key>
        <string>/Users/OPERATOR</string>
        <key>NVM_DIR</key>
        <string>/Users/OPERATOR/.nvm</string>
        <key>PATH</key>
        <string>/Users/OPERATOR/.local/bin:/Users/OPERATOR/.nvm/versions/node/v20.20.2/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
    </dict>
    <key>KeepAlive</key>
    <true/>
    <key>Label</key>
    <string>com.paperclip.server</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/OPERATOR/paperclip/start-paperclip.sh</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>StandardErrorPath</key>
    <string>/Users/OPERATOR/paperclip/logs/paperclip.error.log</string>
    <key>StandardOutPath</key>
    <string>/Users/OPERATOR/paperclip/logs/paperclip.log</string>
    <key>WorkingDirectory</key>
    <string>/Users/OPERATOR/paperclip</string>
</dict>
</plist>
```

Replace `OPERATOR` with your username (`whoami`), then:

```bash
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.paperclip.server.plist
launchctl print gui/$(id -u)/com.paperclip.server | grep state
# Verify listening
sleep 30
lsof -nP -iTCP:3100 -sTCP:LISTEN
curl -sf http://localhost:3100/healthz
```

### 6.2 watchdog daemon

Create `~/Library/LaunchAgents/work.OPERATOR.gimle-watchdog.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>EnvironmentVariables</key>
    <dict>
        <key>HOME</key>
        <string>/Users/OPERATOR</string>
        <key>PATH</key>
        <string>/Users/OPERATOR/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
    </dict>
    <key>KeepAlive</key>
    <true/>
    <key>Label</key>
    <string>work.OPERATOR.gimle-watchdog</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/OPERATOR/Android/Gimle-Palace/services/watchdog/.venv/bin/python</string>
        <string>-m</string>
        <string>gimle_watchdog.daemon</string>
        <string>--config</string>
        <string>/Users/OPERATOR/.paperclip/watchdog-config.yaml</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>StandardErrorPath</key>
    <string>/Users/OPERATOR/.paperclip/watchdog.error.log</string>
    <key>StandardOutPath</key>
    <string>/Users/OPERATOR/.paperclip/watchdog.log</string>
</dict>
</plist>
```

Bootstrap (after Section 8 fills in `companies:` UUIDs):

```bash
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/work.$(whoami).gimle-watchdog.plist
```

---

## 7. Disable heartbeats for company agents

**Why**: Gimle agents do NOT auto-wake. Operator manually triggers via `paperclipai heartbeat run --agent-id <id>` per `reference_gimle_no_autowake.md`. Trading and UAudit use heartbeats normally.

**Where**: per-agent `heartbeatPolicy` in the Paperclip agent record, OR company-level default.

After Section 8 creates the Gimle company, set its heartbeat default:

```bash
# Get Gimle company config
CO=<gimle-uuid>
TOKEN=$(jq -r '.credentials | to_entries[0].value.token' ~/.paperclip/auth.json)

curl -s -X PATCH "http://localhost:3100/api/companies/$CO" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"defaultHeartbeatPolicy": "off"}'
```

Per-agent override (if needed):

```bash
AGENT_ID=<agent-uuid>
curl -s -X PATCH "http://localhost:3100/api/agents/$AGENT_ID" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"heartbeatPolicy": "off"}'
```

**Verification**: agent's `heartbeatPolicy` field returns `"off"` in `GET /api/agents/me`.

---

## 8. Create company via API

Use the bootstrap contract from [`docs/superpowers/specs/2026-05-10-paperclip-generic-project-team-bootstrap.md`](../superpowers/specs/2026-05-10-paperclip-generic-project-team-bootstrap.md) — preferred — or follow this minimal example:

```bash
TOKEN=$(jq -r '.credentials | to_entries[0].value.token' ~/.paperclip/auth.json)

curl -s -X POST "http://localhost:3100/api/companies" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Gimle",
    "issuePrefix": "GIM",
    "description": "Gimle Palace — palace-mcp + UW iOS ecosystem"
  }' | jq -r '.id'
```

Save the returned company UUID and use it for all subsequent `agents`, `projects`, and `routines` API calls.

Bootstrap journal: every `bootstrap-<slug>.json` write goes to `~/.paperclip/journal/` automatically. Use the iMac journals as templates: copy `bootstrap-trading.json` from iMac (`scp anton@imac-ssh.ant013.work:~/.paperclip/journal/20260520T035017Z-bootstrap-trading.json ~/.paperclip/journal/`) to see the full schema.

---

## 9. Hire agents per company

Per [`paperclips/fragments/codex/create-agent.md`](../../paperclips/fragments/codex/create-agent.md) — use the Paperclip approval flow. Never patch agent rows directly to DB.

**Roster for Gimle** (matches iMac's 25-agent setup):

| Role | Adapter | Owner |
|---|---|---|
| CEO | claude_local | Anton (operator) |
| CTO | claude_local | engineering hierarchy root |
| CodeReviewer | claude_local | review chain |
| PythonEngineer | claude_local | implementation |
| MCPEngineer | claude_local | palace-mcp impl |
| InfraEngineer | claude_local | bench scripts, deploy |
| BlockchainEngineer | claude_local | crypto-domain analysis |
| OpusArchitectReviewer | claude_local | adversarial review |
| SecurityAuditor | claude_local | sec review |
| ResearchAgent | claude_local | spec research |
| QAEngineer | claude_local | smoke / live test |
| TechnicalWriter | claude_local | docs |
| Auditor | claude_local | UAudit-shaped |
| CXCTO | codex_local | Codex team root |
| CXPythonEngineer | codex_local | Codex impl |
| CXInfraEngineer | codex_local | Codex infra |
| CXQAEngineer | codex_local | Codex QA |
| CXCodeReviewer | codex_local | Codex review |
| CXMCPEngineer | codex_local | Codex MCP |
| CXBlockchainEngineer | codex_local | Codex crypto |
| CXSecurityAuditor | codex_local | Codex sec |
| CXAuditor | codex_local | Codex audit |
| CXTechnicalWriter | codex_local | Codex docs |
| CXResearchAgent | codex_local | Codex research |
| CodexArchitectReviewer | codex_local | Codex adversarial |

**Hire flow** (per agent; cross-reference `paperclips/fragments/codex/create-agent.md` for full payload):

```bash
TOKEN=$(jq -r '.credentials | to_entries[0].value.token' ~/.paperclip/auth.json)
CO=<gimle-uuid>
OPERATOR=$(whoami)
COMPANY_HOME=$HOME/.paperclip/instances/default/companies/$CO

# CEO (claude adapter)
curl -s -X POST "http://localhost:3100/api/companies/$CO/agents" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "CEO",
    "role": "ceo",
    "title": "Chief Executive Officer",
    "icon": "crown",
    "reportsTo": null,
    "adapterType": "claude_local",
    "adapterConfig": {
      "cwd": "'$HOME'/Android/Gimle-Palace-claude",
      "model": "claude-opus-4-7",
      "instructionsFilePath": "AGENTS.md",
      "instructionsBundleMode": "managed",
      "maxTurnsPerRun": 400,
      "env": {
        "PATH": "'$HOME'/.local/bin:'$HOME'/.nvm/versions/node/v20.20.2/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
      }
    },
    "heartbeatPolicy": "off"
  }'
```

**CXCTO** (codex adapter, ChatGPT/OAuth mode — different `CODEX_HOME` per company):

```bash
mkdir -p "$COMPANY_HOME/codex-home"
# Copy oauth-token from iMac (or run codex login on this MacBook first):
scp anton@imac-ssh.ant013.work:"~/.paperclip/instances/default/companies/$CO/codex-home/auth.json" \
    "$COMPANY_HOME/codex-home/auth.json"
chmod 600 "$COMPANY_HOME/codex-home/auth.json"

curl -s -X POST "http://localhost:3100/api/companies/$CO/agents" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "CXCTO",
    "role": "engineer",
    "title": "Codex Chief Technology Officer",
    "icon": "cog",
    "reportsTo": "<ceo-agent-id>",
    "adapterType": "codex_local",
    "adapterConfig": {
      "cwd": "'$HOME'/Android/Gimle-Palace-cx",
      "model": "gpt-5.5",
      "modelReasoningEffort": "high",
      "instructionsFilePath": "AGENTS.md",
      "instructionsBundleMode": "managed",
      "maxTurnsPerRun": 600,
      "timeoutSec": 0,
      "graceSec": 15,
      "env": {
        "CODEX_HOME": "'$COMPANY_HOME'/codex-home",
        "PATH": "'$HOME'/.local/bin:'$HOME'/.nvm/versions/node/v20.20.2/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
      }
    },
    "heartbeatPolicy": "off"
  }'
```

Repeat for every role per the roster. Cross-reference iMac via:

```bash
# Pull full Gimle roster from iMac as JSON
ssh anton@imac-ssh.ant013.work \
  'curl -s -H "Authorization: Bearer $(jq -r .credentials.\"https://paperclip.ant013.work\".token ~/.paperclip/auth.json)" \
   "https://paperclip.ant013.work/api/companies/9d8f432c-ff7d-4e3a-bbe3-3cd355f73b64/agents"' \
  | jq '[.[] | {name, role, adapterType, adapterConfig: {model: .adapterConfig.model, maxTurnsPerRun: .adapterConfig.maxTurnsPerRun}}]'
```

Adjust `cwd`/`CODEX_HOME` paths per your MacBook layout.

---

## 10. Per-company workspace isolation

Each company gets its own:

- `~/.paperclip/instances/default/companies/<uuid>/agents/<agent-uuid>/` — agent workspace
- `~/.paperclip/instances/default/companies/<uuid>/codex-home/` — isolated `CODEX_HOME` (Codex auth + cache)
- `~/.paperclip/instances/default/companies/<uuid>/claude-prompt-cache/` — Claude prompt cache

Source code lives outside `.paperclip`:

- `~/Android/Gimle-Palace-claude/` — Board + Claude team worktree
- `~/Android/Gimle-Palace-cx/` — Codex team worktree
- `~/Android/Gimle-Palace/` — operator's primary worktree

**Create the worktrees**:

```bash
cd ~/Android/Gimle-Palace
git worktree add ~/Android/Gimle-Palace-claude develop
git worktree add ~/Android/Gimle-Palace-cx develop
```

`AGENTS.md` files are generated by Paperclip when `instructionsBundleMode: managed`. Verify on first heartbeat that each agent's `cwd` has a fresh `AGENTS.md`.

---

## 11. Configure Telegram routing

After companies + agents exist:

```bash
TOKEN=$(jq -r '.credentials | to_entries[0].value.token' ~/.paperclip/auth.json)
CO=<gimle-uuid>
BOT_TOKEN=$(cat ~/.paperclip/secrets/telegram-bot-token)
GIMLE_FILES_CHAT_ID=<chat-id>
GIMLE_OPS_CHAT_ID=<ops-chat-id>

# Configure plugin per-company
curl -s -X POST "http://localhost:3100/api/plugins/telegram/config" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "companyId": "'$CO'",
    "botToken": "'$BOT_TOKEN'",
    "fileRoutes": [
      {"chatId": "'$GIMLE_FILES_CHAT_ID'", "sendImportant": false}
    ],
    "opsRoutes": [
      {"chatId": "'$GIMLE_OPS_CHAT_ID'", "sendImportant": true}
    ]
  }'
```

**Important gotcha** (per `reference_paperclip_plugin_config_endpoint.md`): POST **replaces** config — always GET current snapshot first if reconfiguring.

```bash
curl -s "http://localhost:3100/api/plugins/telegram/config?companyId=$CO" \
  -H "Authorization: Bearer $TOKEN" | tee ~/.paperclip/backups/telegram-config-$(date -u +%Y%m%dT%H%M%SZ).json
```

---

## 12. Smoke verification

```bash
TOKEN=$(jq -r '.credentials | to_entries[0].value.token' ~/.paperclip/auth.json)

# 12.1 paperclipai server
curl -sf http://localhost:3100/healthz && echo " ✓ paperclip /healthz"
curl -s "http://localhost:3100/api/companies" -H "Authorization: Bearer $TOKEN" | jq '.[].name'

# 12.2 watchdog
launchctl print gui/$(id -u)/work.$(whoami).gimle-watchdog | grep state
tail -5 ~/.paperclip/watchdog.log

# 12.3 agents responding
curl -s "http://localhost:3100/api/companies/<gimle-uuid>/agents" \
  -H "Authorization: Bearer $TOKEN" \
  | jq '[.[] | {name, status, heartbeatPolicy}]'

# 12.4 manual heartbeat (since auto-wake off)
CEO_ID=<ceo-uuid>
paperclipai heartbeat run --agent-id $CEO_ID

# Watch logs as it runs:
tail -f ~/.paperclip/instances/default/companies/<gimle-uuid>/agents/$CEO_ID/runs/*.log
```

---

## 13. Daily ops

### Wake an agent (no auto-heartbeat)

```bash
paperclipai heartbeat run --agent-id <agent-uuid>
```

### Watchdog status

```bash
launchctl list | grep paperclip
launchctl list | grep watchdog
tail -50 ~/.paperclip/watchdog.log
```

### Restart paperclip server

```bash
launchctl bootout gui/$(id -u)/com.paperclip.server
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.paperclip.server.plist
```

### Kill hung Codex / Claude process

```bash
pgrep -laf "codex|claude" | head
kill <pid>     # or kill -9 if hung at 0% CPU > 10 min
```

(Per `reference_claude_process_idle_hang.md` — known issue, manual kill required.)

### Token revoked silently

Symptoms: 401/403 on `/api/companies` while `auth.json` looks correct. Fix:

```bash
paperclipai auth login        # interactive — paste fresh token via approval URL
```

Per `reference_paperclip_token_revoke_recovery.md`.

---

## 14. Optional: native palace-mcp on this MacBook

For semantic search / call hierarchy on UW iOS, you'll also want palace-mcp + native Neo4j:

```bash
cd ~/Android/Gimle-Palace/services/palace-mcp
uv sync
mkdir -p ~/.cache/{palace-hf-cache,palace-tantivy,palace-adr}

# Start palace-mcp uvicorn (foreground, then `&` for background)
set -a; source ~/Android/Gimle-Palace/.env; set +a
~/.venv/bin/uvicorn palace_mcp.main:app --host 127.0.0.1 --port 8765
```

Then add to `~/.claude.json`:

```json
{
  "mcpServers": {
    "palace-memory": {
      "type": "http",
      "url": "http://localhost:8765/mcp"
    }
  }
}
```

For full ingest pipeline see `bench/ingest-fresh-{build,replay}.sh` documented in `docs/superpowers/specs/2026-06-05-incremental-ingest-design.md`.

---

## 15. iMac parity checklist

Run this on iMac to dump current config, then mirror on MacBook:

```bash
ssh anton@imac-ssh.ant013.work bash <<'REMOTE'
echo "=== paperclipai version ==="
paperclipai --version 2>/dev/null || npx paperclipai --version

echo "=== companies ==="
curl -s -H "Authorization: Bearer $(jq -r .credentials.\"https://paperclip.ant013.work\".token ~/.paperclip/auth.json)" \
  "https://paperclip.ant013.work/api/companies" | jq '[.[] | {id, name}]'

echo "=== launchd plists ==="
ls ~/Library/LaunchAgents/ | grep -iE "paperclip|watchdog"

echo "=== plugins ==="
ls ~/.paperclip/plugins/node_modules/

echo "=== watchdog config (companies tracked) ==="
yq '.companies[] | {id, name}' ~/.paperclip/watchdog-config.yaml

echo "=== telegram plugin git ==="
git -C ~/paperclip/paperclip-plugin-telegram remote -v
git -C ~/paperclip/paperclip-plugin-telegram branch --show-current
REMOTE
```

Diff the output against your MacBook setup — anything missing on MacBook must be replicated.

---

## 16. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `paperclipai run` exits with `EADDRINUSE` | Port 3100 already in use (orphan node) | `lsof -i :3100`; `kill <pid>` |
| Telegram plugin not picked up | Plugin not in `~/.paperclip/plugins/node_modules/` | `cd ~/.paperclip/plugins && npm install ~/paperclip/paperclip-plugin-telegram` then restart paperclipai |
| Agent stuck `status=error` | Failed run left state | `PATCH /api/agents/{id}` with `{"status": "idle"}` |
| Watchdog logs `401 Unauthorized` | Token expired / revoked | Regenerate via `paperclipai auth token --readonly --output ~/.paperclip/watchdog.token` |
| Codex agent uses wrong OAuth | `CODEX_HOME` not set in adapter env | `PATCH /api/agents/{id}` updating `adapterConfig.env.CODEX_HOME` |
| AGENTS.md missing in agent workspace | First heartbeat hasn't run | Trigger heartbeat once: `paperclipai heartbeat run --agent-id <uuid>` |
| Neo4j connection refused | Service not running | `brew services restart neo4j` |
| Heartbeat fires when shouldn't | `heartbeatPolicy` not set on agent | `PATCH /api/agents/{id} {"heartbeatPolicy": "off"}` |

---

## Appendix A: File ownership cheat sheet

| Path | Mode | Owner |
|---|---|---|
| `~/.paperclip/auth.json` | 600 | operator |
| `~/.paperclip/watchdog.token` | 600 | operator |
| `~/.paperclip/secrets/*` | 600 | operator |
| `~/.paperclip/instances/default/companies/<uuid>/codex-home/auth.json` | 600 | operator |
| `~/Library/LaunchAgents/com.paperclip.server.plist` | 644 | operator |
| `~/paperclip/start-paperclip.sh` | 755 | operator |
| `~/Android/Gimle-Palace/.env` | 600 | operator |

Never commit any of the above. Run `git diff --cached` before every commit to verify.

---

## Appendix B: Related runbooks

- [`operator-claude-code-setup.md`](operator-claude-code-setup.md) — palace.memory.prime quick start
- [`productized-runtime-smoke.md`](productized-runtime-smoke.md) — MacBook palace-mcp smoke
- [`operator-guide.md`](operator-guide.md) — iMac operator guide
- [`server-install.md`](server-install.md) — Linux server profile
- `docs/superpowers/specs/2026-05-10-paperclip-generic-project-team-bootstrap.md` — declarative bootstrap contract (the *what*)
- `paperclips/fragments/codex/create-agent.md` — Codex hire payload reference
