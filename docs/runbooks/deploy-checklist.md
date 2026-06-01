# Deploy checklist

> See also: [Palace Operator Guide](operator-guide.md) for first-time
> setup, model cache, repo mounts, and cleanup policy.

Run before and after every `docker compose up` on the iMac deploy host.

## Pre-flight

1. Pull latest develop:
   ```bash
   git -C /Users/Shared/Ios/Gimle-Palace fetch origin && git -C /Users/Shared/Ios/Gimle-Palace checkout develop && git -C /Users/Shared/Ios/Gimle-Palace pull --ff-only
   ```

2. Verify required env vars are non-empty:
   ```bash
   grep -E "^(NEO4J_PASSWORD|OPENAI_API_KEY|PAPERCLIP_API_KEY)=." .env
   ```
   Expected: 3 lines. If fewer, populate `.env` from `.env.example` + `~/.paperclip/auth.json`.

3. **Phase 1 env vars** (optional; defaults shown — override only when needed):

   | Env var | Default | Purpose |
   |---|---|---|
   | `PALACE_AUDIT_SINK_PATH` | _(disabled)_ | Path for JSONL audit file (F4.0). Set to e.g. `/var/log/palace/audit.jsonl` to enable. |
   | `PALACE_TELEMETRY_ENABLED` | `true` | Master switch for MCP call telemetry (F4.0). Set `false` to suppress. |
   | `PALACE_QODO_PREWARM` | `true` | Pre-warm Qodo embedding model on startup (F4.1). Set `0` on memory-constrained hosts to skip. |
   | `PALACE_ANCHOR_SYMBOLS` | `{}` | JSON dict mapping `group_id → [qualified_names]` for S0 anchors. Example: `'{"project/gimle":["MyClass.method"]}'` |

   These do not block startup when absent — defaults are safe for production.

4. Bring up services:
   ```bash
   docker compose --profile review up -d --build --wait
   ```

5. Health check:
   ```bash
   curl -fsS http://localhost:8080/healthz
   ```
   Expected: `{"status":"ok"}`.

6. **Auth-path probe** (verifies `PAPERCLIP_API_KEY` reaches Paperclip server):
   ```bash
   docker compose exec -T palace-mcp python3 -c '
   import os, urllib.request
   url = os.environ["PAPERCLIP_API_URL"] + "/api/health"
   key = os.environ["PAPERCLIP_API_KEY"]
   req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}"})
   with urllib.request.urlopen(req, timeout=5) as r:
       assert r.status == 200, f"paperclip auth failed: {r.status}"
   print("OK")'
   ```
   Expected output: `OK`. Any non-200 or exception = deploy blocked; re-check `PAPERCLIP_API_KEY` in `.env`.

   Alternative probe (if `/api/health` rejects Authorization header):
   ```bash
   # Call unstick_issue with a known-done UUID and dry_run=True via MCP
   # Assert response contains "action": "noop" and no 401 error
   ```

7. **Infra delivery env**: after deploying project agents, verify every
   Telegram-delivery infra agent has `PAPERCLIP_API_KEY` and
   `PAPERCLIP_API_URL` in live `adapterConfig.env`. Host `.env` is not enough
   for Paperclip issue runs. If Telegram returns `Board access required`, follow
   `docs/paperclip-operations/telegram-report-delivery.md#infra-agent-runtime-env-repair`.

## Post-deploy verification

- `docker compose --profile review ps` — all containers healthy.
- `git -C /Users/Shared/Ios/Gimle-Palace branch --show-current` — outputs `develop`.

### F4.0 — telemetry / JSONL audit sink

If `PALACE_AUDIT_SINK_PATH` is set, verify the sink is writing:

```bash
SINK=$(docker compose exec -T palace-mcp sh -c 'echo $PALACE_AUDIT_SINK_PATH')
# Trigger one tool call, then:
docker compose exec -T palace-mcp tail -1 "$SINK"
# Expected: a single JSON line with keys: timestamp, tool_name, latency_ms
```

If `PALACE_AUDIT_SINK_PATH` is unset, telemetry is still active but written only
to structured logs:

```bash
docker compose --profile review logs palace-mcp --tail 20 | grep '"tool_name"'
# Expected: at least one JSON log line per MCP call made above
```

### F4.1 — Qodo embedding pre-warm

Verify cold-start is eliminated (warm latency should be < 2 s):

```bash
# First call after startup — should be warm if PALACE_QODO_PREWARM=true (default)
time curl -s -X POST \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"palace.code.semantic_search","arguments":{"query":"test","project":"project/gimle","limit":1}}}' \
  http://localhost:8080/mcp | python3 -m json.tool > /dev/null
# Expected: wall-clock < 2 s. A ~9 s first call means PALACE_QODO_PREWARM=false or prewarm failed.
```

Check startup logs to confirm prewarm completed:

```bash
docker compose --profile review logs palace-mcp | grep -i "prewarm\|embedding.*warm"
# Expected: a log line like "qodo prewarm complete" near startup
```

### F4.3 / F4.4 — runtime behavior notes (no action required)

These are internal improvements; no operator action is needed unless troubleshooting.

- **F4.3 hydration parallelization**: snippet and usage context are now fetched
  concurrently via `asyncio.gather` for each result hit. If you see unexpectedly
  low latency on `semantic_search` with `include_context=true`, this is expected.

- **F4.4 HNSW per-project budget**: for multi-project query scopes, each project
  receives its own HNSW query budget (`per_project_k`) rather than a single shared
  query. Results are merged and re-ranked by score. The `per_project_k` value is
  logged in the telemetry line (`candidate_limit` field) for debugging.
