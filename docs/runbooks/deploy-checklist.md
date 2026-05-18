# Deploy checklist

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

3. Bring up services:
   ```bash
   docker compose --profile review up -d --build --wait
   ```

4. Health check:
   ```bash
   curl -fsS http://localhost:8080/healthz
   ```
   Expected: `{"status":"ok"}`.

5. **Auth-path probe** (verifies `PAPERCLIP_API_KEY` reaches Paperclip server):
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

6. **Infra delivery env**: after deploying project agents, verify every
   Telegram-delivery infra agent has `PAPERCLIP_API_KEY` and
   `PAPERCLIP_API_URL` in live `adapterConfig.env`. Host `.env` is not enough
   for Paperclip issue runs. If Telegram returns `Board access required`, follow
   `docs/paperclip-operations/telegram-report-delivery.md#infra-agent-runtime-env-repair`.

## Post-deploy verification

- `docker compose --profile review ps` — all containers healthy.
- `git -C /Users/Shared/Ios/Gimle-Palace branch --show-current` — outputs `develop`.
