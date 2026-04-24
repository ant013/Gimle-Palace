# Gimle Agent Watchdog (GIM-63)

Host-native daemon that recovers paperclip agents from:
1. **Mid-work process death** — Claude subprocess dies unexpectedly; paperclip doesn't auto-respawn because heartbeat is disabled. Watchdog PATCHes assigneeAgentId=same to trigger paperclip's "assignment" wake event.
2. **Idle-hang** — Claude subprocess stays alive with near-zero CPU after completing its work (known upstream issue with MCP child processes keeping the node event loop alive). Watchdog kills it; next tick respawns.

## Install

Manual:
```bash
cd services/watchdog
uv sync --all-extras
uv run python -m gimle_watchdog install --discover-companies
```

On macOS → launchd plist at `~/Library/LaunchAgents/work.ant013.gimle-watchdog.plist`.
On Linux → systemd user unit at `~/.config/systemd/user/gimle-watchdog.service`.

## Configuration

Edit `~/.paperclip/watchdog-config.yaml`. See spec §4.2 for full schema.

## Operational commands

```bash
gimle-watchdog status                     # service state + filter health
gimle-watchdog tail -n 100                # last 100 log lines
gimle-watchdog unescalate --issue <uuid>  # clear escalation
gimle-watchdog escalate --issue <uuid>    # manually permanent-escalate
gimle-watchdog uninstall                  # remove service
```

## Troubleshooting

**Daemon doesn't start.** Check log: `~/.paperclip/watchdog.err`.

**Agent not waking.** Verify token: `curl -H "Authorization: Bearer $PAPERCLIP_API_KEY" http://localhost:3100/api/companies/<CO>/issues`.

**Filter drift.** If `status` shows `procs matching filter: 0` across multiple days while agents are active, Anthropic may have renamed `--append-system-prompt-file`. Update `PS_FILTER_TOKENS` in `src/gimle_watchdog/detection.py`.

## Live smoke tests

1. **Mid-work-died test**: create disposable paperclip issue assigned to idle agent. PATCH status=in_progress. Wait for Claude process spawn. `pkill -TERM` that process. Within 3-5 minutes, log should show `wake_result via=patch`.
2. **Idle-hang test**: `kill -STOP <pid>` on a running Claude subprocess to simulate hang. Within `hang_etime_min + 2 min` tick window, log should show `hang_killed status=forced` then `wake_result` on next tick.
3. **Escalation test**: create issue with broken role that immediately crashes. After 3 wake cycles in 15 min, verify escalation comment appears on issue + `escalated` field in state.
