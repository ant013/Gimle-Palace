# Claude OAuth recovery on iMac

**Symptom**: Claude paperclip agents fail with `401 Invalid authentication credentials (adapter_failed)` (or yesterday's variant `claude_auth_required: Not logged in · Please run /login`). Run duration ≈ 5-10 seconds, exits 1, no useful work done. Multiple agents fail in lockstep — this is auth, not per-agent.

**Cause**: `~/.claude/.credentials.json` holds a Claude Max OAuth `accessToken` with `expiresAt` field. Token lives ~1.5-2 hours. Anthropic's CLI 2.x **does not auto-refresh** in non-interactive paperclip-driven runs. Once `expiresAt < now`, every Claude run dies. Paperclip's retry loop hammers the OAuth refresh endpoint until it 429-rate-limits, locking us out further.

## Quick recovery (operator + Board, ~10 min)

### 1. Kill the retry loop (Board, via SSH)

```bash
# Find any hung interactive `claude /login` (typical: hangs 16h+ on ttys)
ssh imac-ssh.ant013.work 'ps aux | grep "claude /login" | grep -v grep'
# Kill it if found:
ssh imac-ssh.ant013.work 'kill <PID>'

# Stop paperclip + workers (orphan npm processes don't always die from launchctl bootout — kill explicitly)
ssh imac-ssh.ant013.work 'launchctl bootout gui/$(id -u)/com.paperclip.server; sleep 2; pkill -f "paperclipai|claude"'

# Verify dead
ssh imac-ssh.ant013.work 'curl -sS -o /dev/null -w "%{http_code}\n" --max-time 3 http://localhost:3100/api/companies'
# Expect: 000 (connection refused = good, paperclip stopped)
```

### 2. Wait for OAuth rate-limit cooldown (5-10 min)

Anthropic's `console.anthropic.com/v1/oauth/token` returns `429 rate_limit_error` until cooldown. Just wait. Don't poke it.

### 3. Fresh OAuth login (operator, interactive on iMac)

```bash
# On iMac Terminal directly (NOT via SSH — needs browser)
claude /login
```

Anthropic OAuth flow opens browser, asks for Claude Max auth, returns paste-back code. Paste into Terminal. CLI writes new `~/.claude/.credentials.json` with fresh token pair (`expiresAt` ≈ 1h45m from now).

### 4. Verify token is fresh (Board)

```bash
ssh imac-ssh.ant013.work 'python3 -c "
import json, datetime
d = json.load(open(\"/Users/anton/.claude/.credentials.json\"))[\"claudeAiOauth\"]
exp = datetime.datetime.utcfromtimestamp(d[\"expiresAt\"]/1000)
now = datetime.datetime.utcnow()
print(f\"expiresAt: {exp.isoformat()}Z (in {(exp-now).total_seconds()/60:.0f} min)\")
"'
# Expect: ~100+ min in the future
```

### 5. Restart paperclip (Board, via SSH)

```bash
ssh imac-ssh.ant013.work 'launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.paperclip.server.plist'
sleep 5
ssh imac-ssh.ant013.work 'curl -sS -o /dev/null -w "%{http_code}\n" --max-time 3 http://localhost:3100/api/companies'
# Expect: 200 or 401 (server back; auth depends on token format)
```

### 6. Smoke probe one Claude agent

Pick any Claude agent (e.g., CTO `7fb0fdbb-...`), assign a trivial paperclip issue, wait 1-2 min for heartbeat. If heartbeat lands → recovery complete.

## Long-term fix candidates

OAuth Max tokens lasting only ~2 hours is fundamentally fragile for headless paperclip operation. Options:

- **Switch to API key flow** (`ANTHROPIC_API_KEY` env var via launchd plist). Pro: tokens don't expire. Con: billed per-token, may be more expensive than Claude Max subscription depending on usage.
- **Auto-refresh daemon**: separate process that watches `~/.claude/.credentials.json` `expiresAt` and POSTs to `console.anthropic.com/v1/oauth/token` with `refresh_token` before expiry. Pro: keeps Max subscription. Con: needs Anthropic OAuth client_id + may break when CLI auth schema changes.
- **CLI fix request**: file issue with Anthropic for CLI 2.x to auto-refresh in non-interactive mode.

Until one of these lands, expect to re-run this runbook every ~2h of paperclip uptime.

## History

- 2026-05-07 17:34Z: first occurrence — yesterday's token expired during S1 implementation; caught by watchdog as `claude_auth_required`. Operator did `claude /login` interactively → recovered for ~7h.
- 2026-05-08 ~05:07Z: token expired again; QA + GIM-238 + GIM-239 blocked. 16h hung `claude /login` discovered (PID 34179 from yesterday's session — never completed). 43 652 × 401 errors in paperclip server log = retry loop.
- Recovery this run: per steps 1-6 above. Document created so it's executable next time.
