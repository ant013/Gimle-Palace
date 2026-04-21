# GIM-63 — Agent watchdog (respawn + idle-hang recovery)

**Date:** 2026-04-21
**Author:** Board (brainstorm with operator)
**Status:** REV2 — adversarial review incorporated.

**Rev2 change log:**
- §1 — honest LOC estimate (1000-1200 prod + 1000-1500 test); dropped "janitor" framing
- §4.2 — `hang_etime_min: 60` (was 30), `hang_cpu_max_s: 30` (was 60). Empirically calibrated against observed p99 of legitimate runs — see §4.2.1
- §4.5 — **major redesign**: POST `/api/agents/{id}/wake` returns 404 (verified 2026-04-21); `wakeAgentSchema` in paperclip source is internal-only. Primary path is now `POST /release → PATCH assigneeAgentId=same`. No `/wake` primary. No fallback logic needed.
- §4.5 kill — added PID-cmdline re-verification before `os.kill` to mitigate PID-reuse race
- §4.3 daemon — `_tick` wrapped in `asyncio.wait_for(..., timeout=60)` with `sys.exit(1)` on hang → launchd restarts
- §4.4 / §4.8 — `status` CLI now reports "paperclip-skills procs matched by filter today" (operator observability if command-line filter gets stale from Anthropic renames)
- §4.4 — permanent-escalation state (3 re-escalation cycles → no-auto-unescalate; requires explicit `unescalate --permanent=false`)
- §4.6 — state file version migration policy (unknown version → rename `.bak`, start empty, WARN)
- §4.7 — `install --discover-companies` errors by default if companies list non-empty; requires `--force`
- §6.1 — failure matrix: `fcntl LOCK_NB + 2 retries + fail-hard` (no infinite launchd-restart), HTTP 429 back-off
- §7.5 — coverage exclusions declared (subprocess calls to system-ctl, other-OS branches, CLI boilerplate)
- §8 — pre-merge check: PATCH assigneeAgentId with token returns 200 (was wake-check)
- §10 — escalation comment template explicit (referenced from §4.3), LOC estimate honest

**Predecessor SHAs this spec is grounded in:**
- `develop` tip: `068014f` (GIM-62 async-signal dispatcher merged 2026-04-21T01:07:48Z)
- `paperclips/fragments/shared` submodule: `6374423` (upstream PR #6 async-signal-wait)

**Related memory (must read before implementation):**
- `reference_claude_process_idle_hang.md` — empirical findings that motivated this slice
- `reference_paperclip_rest_endpoints.md` — verified API paths
- `reference_paperclip_token_locations.md` — where `PAPERCLIP_API_KEY` lives

---

## 1. Goal

Close the pipeline-recovery gap discovered during GIM-62: paperclip does **not** auto-respawn agents when their Claude subprocess dies mid-work, and it does **not** auto-kill Claude subprocesses that hang after completion. Both are observed failure modes. Heartbeat is globally disabled by design (event-driven handoff); without it, stuck issues wait forever for operator intervention.

Build a host-native watchdog daemon (~1000-1200 LOC prod + 1000-1500 LOC test, measured for honesty — this is not a small utility), part of the Gimle stack's one-command install, that:

1. Polls paperclip API every 2 minutes for issues stuck in `assignee-set + no-run` state older than a threshold, and wakes the assignee via `POST /wake` (with `PATCH` fallback).
2. Polls the iMac process table for `claude --print` subprocesses with long wall-time and negligible CPU-time, and kills them — next tick resurrects via (1).
3. Protects itself against loop-forever scenarios with per-issue cooldowns, per-agent caps, and escalation comments on paperclip issues when operator intervention is genuinely needed.
4. Supports multi-company configs (one daemon, multiple paperclip companies — Gimle + Medic in one install).
5. Self-installs as platform-native service (launchd on macOS, systemd user-unit on Linux, cron fallback) via `python -m watchdog install`.

This compensates for paperclip's intentionally-disabled heartbeat — the operator chose event-driven handoff architecture, but the exception path (process death without phase-done event) needs external recovery. GIM-63 provides that.

## 2. Motivation

### Observed incident (GIM-62 CTO hang, 2026-04-20)

- CTO agent completed Phase 1.1 work in ~4 minutes (`terminal_reason: "completed"`, comment posted, `assigneeAgentId` PATCHed to CR)
- Claude subprocess did NOT exit — lived for 62 more minutes with ~0 CPU (likely MCP-child-process keeping node event loop alive)
- Paperclip waited on `child.on('close')` — `executionRunId` stayed non-null → CR never spawned → pipeline stuck
- Operator manually killed PID; CR woke on next paperclip poll (actually on the reassign-refresh we'd already done)

### Empirical verification (2026-04-20)

Test: created disposable issue assigned to ResearchAgent with a 3-minute task. While agent was running, killed the subprocess with `pkill`. Watched `/api/issues/{id}/runs` for 60 seconds.

Result: **zero auto-respawn**. Run marked `failed`, `executionRunId` cleared, `assigneeAgentId` still pointing at ResearchAgent — but no new run was spawned. Pipeline stuck until manual intervention.

Proves two gaps in current state:
1. **Mid-work process death**: paperclip does NOT fire an "assignment" or "on_demand" wake on unexpected child-process exit. Only `timer` (disabled) would cover this, and we don't want to enable it.
2. **Idle-hang subprocess**: paperclip cannot detect OS-level hang without a timeout (`adapterConfig.timeoutSec`), and timeout is risky (kills mid-work runs if set too low — see §10).

### Cost of not solving

- Every stuck issue requires manual operator SSH + `kill` + re-trigger
- Defeats the autonomy premise of the Gimle stack
- Observed ~1-in-10 rate of CTO idle-hangs in GIM-62 session — unacceptable at scale

### Non-goals

- NOT replacing paperclip's built-in heartbeat (operator disabled it deliberately)
- NOT building an orchestrator — this is a janitor process that recovers from exceptional states
- NOT covering paperclip-daemon-level failures (paperclipai node process crash) — that's systemd/launchd's job on the paperclip service itself
- NOT a full telemetry/stats service (§4.8 of GIM-15 is a future component)

## 3. High-level architecture

```
┌─────────────────────────────────────────────────────────────┐
│ iMac host (macOS) OR Linux server                           │
│                                                             │
│   ┌──────────────────────────────────────────────────────┐  │
│   │ gimle-watchdog daemon (long-running, launchd/systemd)│  │
│   │                                                      │  │
│   │  every 2 min:                                        │  │
│   │    1. scan_idle_hangs() → `ps -ao`, filter by        │  │
│   │       etime_s > 30min AND cpu_s < 60s                │  │
│   │    2. kill any hanged PIDs (SIGTERM, SIGKILL after)  │  │
│   │    3. sleep 10s                                      │  │
│   │    4. for each company in config:                    │  │
│   │       scan_died_mid_work():                          │  │
│   │         GET /api/companies/{id}/issues?status=in_progress │
│   │         filter: assigneeAgentId != null AND          │  │
│   │                 executionRunId == null AND           │  │
│   │                 updatedAt > 3 min ago                │  │
│   │         for each candidate:                          │  │
│   │           if cooldown/cap not exceeded → wake()      │  │
│   │           else record_escalation() + post comment    │  │
│   │    5. persist state, emit log events                 │  │
│   └──────────────────────────────────────────────────────┘  │
│                                                             │
│   Files:                                                    │
│     ~/.paperclip/watchdog-config.yaml    (input)            │
│     ~/.paperclip/watchdog-state.json     (persistent state) │
│     ~/.paperclip/watchdog.log            (jsonl, rotated)   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
                               │
                               ▼
         ┌──────────────────────────────────────────┐
         │ paperclip.ant013.work (OR localhost:3100)│
         │   GET /api/companies/{id}/issues         │
         │   POST /api/agents/{id}/wake             │
         │   PATCH /api/issues/{id}                 │
         │   POST /api/issues/{id}/comments         │
         └──────────────────────────────────────────┘
```

## 4. Components

### 4.1 Package layout

`services/watchdog/` — standalone Python 3.12 package, isolated `uv` venv, independent of `palace-mcp`.

```
services/watchdog/
├── pyproject.toml
├── README.md                        # install/troubleshoot/live-smoke
├── src/watchdog/
│   ├── __init__.py
│   ├── __main__.py                  # CLI entry: install/uninstall/run/tick/status/unescalate
│   ├── config.py                    # YAML parser + dataclasses + schema validation
│   ├── paperclip.py                 # httpx.AsyncClient wrapper
│   ├── detection.py                 # scan_died_mid_work + scan_idle_hangs + ps parsers
│   ├── actions.py                   # wake_with_fallback + kill_hanged_proc
│   ├── state.py                     # ~/.paperclip/watchdog-state.json
│   ├── service.py                   # render_plist / render_systemd_unit / render_cron
│   ├── logger.py                    # JSON-lines + rotation
│   └── daemon.py                    # main loop for `run` mode
└── tests/
    ├── conftest.py
    ├── fixtures/
    │   ├── ps_output_macos.txt
    │   ├── ps_output_linux.txt
    │   ├── issues_response.json
    │   └── plist_expected.xml
    ├── test_config.py
    ├── test_detection.py
    ├── test_paperclip.py            # httpx MockTransport
    ├── test_state.py
    ├── test_actions.py
    ├── test_service.py              # render-only tests, no system calls
    └── test_integration.py          # FastAPI mock paperclip end-to-end
```

### 4.2 Config file — `~/.paperclip/watchdog-config.yaml`

```yaml
version: 1

# Shared paperclip API — single endpoint for all companies
paperclip:
  base_url: http://localhost:3100
  api_key_source: env:PAPERCLIP_API_KEY    # or file:/path, or inline (warn)

# Multi-company: daemon polls all listed
companies:
  - id: 9d8f432c-ff7d-4e3a-bbe3-3cd355f73b64
    name: gimle
    thresholds:
      died_min: 3                    # updatedAt > N min → "stuck"
      hang_etime_min: 60             # ps etime > N min (empirically calibrated, §4.2.1)
      hang_cpu_max_s: 30             # AND ps cpu_time < N s

  - id: 1593f659-a6d7-4c7e-9cd7-8b87027f278e
    name: medic
    thresholds:
      died_min: 3
      hang_etime_min: 60
      hang_cpu_max_s: 30

daemon:
  poll_interval_seconds: 120

cooldowns:
  per_issue_seconds: 300              # min 5 min between wakes of same issue
  per_agent_cap: 3                    # max 3 wakes per agent per window
  per_agent_window_seconds: 900       # window = 15 min

logging:
  path: ~/.paperclip/watchdog.log
  level: INFO
  rotate_max_bytes: 10485760          # 10 MB
  rotate_backup_count: 5

escalation:
  post_comment_on_issue: true
  comment_marker: "<!-- watchdog-escalation -->"
```

### 4.2.1 Threshold calibration — empirical methodology

**Data** (sampled 2026-04-21 from GIM-62 issue — 19 completed runs across CTO, CR, PE, QA, Opus, CEO agents):

| Stat | `duration_ms` (wall-time of completed run) |
|---|---|
| Min | 34,411 ms (~34s, CTO quick formalize) |
| P50 | ~170 s |
| P75 | ~260 s |
| P90 | ~410 s |
| **Max legitimate run** | **2,125,525 ms (~35.4 min, PE Phase 2 implementation)** |

**Key insight:** Claude CLI runs are **API-bound** (>95% of `duration_ms` is spent in `api_duration_ms` — `cache_read_input_tokens > 1M` for CTO run observed). Legitimate long work has **low CPU** by construction — the opposite of a "busy process".

**Threshold derivation:**

- `hang_etime_min: 60` = 1.7× observed max legitimate run (35 min × 1.7 ≈ 60 min). Covers the long-tail PE/MCPE coding sessions with comfortable safety margin. CTO idle-hang incident was 66 min → still detected.
- `hang_cpu_max_s: 30` = conservative. Legit API-bound runs accrue CPU on MCP tool calls / context processing. A 60-min run normally accumulates 1-5 min CPU on serena/palace MCP invocations. Truly idle-hang process: ~0-10s CPU over hours (what GIM-62 CTO showed).

**Re-calibration triggered by:**
- New false-positive kill observed in production → widen thresholds
- Long-tail run extends beyond 35 min (e.g., heavy MCPE multi-hour coding) → widen further  
- Anthropic releases changes Claude-CLI behavior → sample fresh data

**Open calibration improvement (out-of-scope for MVP):** collect ps snapshots every 30s for first week post-deploy, compute rolling p99 (etime, cpu), auto-tune thresholds. Tracked as followup slice GIM-6X.

**Schema validation** (enforced by `config.py`):
- `version == 1` required (reject unknown versions)
- `companies` non-empty list, each `id` is UUID
- `thresholds.*_min` and `*_max_s` are positive integers
- `cooldowns.per_agent_cap >= 1`
- `paperclip.api_key_source` matches `env:<VAR>` | `file:<path>` | `inline:<string>` patterns

### 4.3 Daemon main loop

```python
# services/watchdog/src/watchdog/daemon.py (pseudocode)
async def run(config: Config, state: State, client: PaperclipClient) -> None:
    """Persistent loop for launchd/systemd KeepAlive mode."""
    while True:
        tick_started = datetime.utcnow()
        try:
            # Self-liveness: if _tick itself hangs (httpx deadlock, zombie
            # subprocess, PATCH stuck in paperclip), we sys.exit(1) and
            # let launchd/systemd respawn us. Without this, a hung daemon
            # is exactly the silent-failure it's meant to prevent.
            await asyncio.wait_for(
                _tick(config, state, client),
                timeout=60,  # 2× normal tick budget — generous but bounded
            )
        except asyncio.TimeoutError:
            log.error("tick_timeout_self_exit", timeout_s=60)
            sys.exit(1)  # launchd KeepAlive restarts us after ~10s
        except Exception as e:
            log.exception("tick_failed", error=str(e))
        # Sleep until next interval, accounting for tick duration
        elapsed = (datetime.utcnow() - tick_started).total_seconds()
        await asyncio.sleep(max(0, config.daemon.poll_interval_seconds - elapsed))


async def _tick(config: Config, state: State, client: PaperclipClient) -> TickResult:
    log.info("tick_start", companies=len(config.companies))

    # Phase 1: kill host-level idle hangs (frees executionRunId)
    hanged = detection.scan_idle_hangs(config)
    for proc in hanged:
        result = actions.kill_hanged_proc(proc)
        log.warn("hang_killed", pid=proc.pid, etime_s=proc.etime_s,
                 cpu_s=proc.cpu_s, kill_result=result.status)

    if hanged:
        await asyncio.sleep(10)  # give paperclip time to register process exit

    # Phase 2: wake stuck assignees (per company)
    total_actions = 0
    for company in config.companies:
        died = await detection.scan_died_mid_work(company, client, state, config)
        for action in died:
            if action.kind == "wake":
                result = await actions.wake_with_fallback(client, action.issue, action.agent_id)
                state.record_wake(action.issue.id, action.agent_id)
                log.info("wake_result", via=result.via, success=result.success,
                         issue=action.issue.id)
            elif action.kind == "escalate":
                state.record_escalation(action.issue.id, action.reason)
                if config.escalation.post_comment_on_issue:
                    # Template: see §6.3 for full example. Build function renders
                    # marker + escalation context (agent name, wake count, timeline,
                    # suggested operator actions) into a single markdown comment.
                    await client.post_issue_comment(action.issue.id,
                                                    build_escalation_body(action, state))
                log.warn("escalation", issue=action.issue.id, reason=action.reason,
                         escalation_count=state.escalation_count(action.issue.id))
            total_actions += 1

    state.save()
    log.info("tick_end", actions=total_actions)
```

For cron-mode (no launchd/systemd), entry is `watchdog tick` instead of `run` — runs one `_tick` then exits. Same `_tick` function, different wrapper.

### 4.4 Detection primitives

**`scan_died_mid_work`** — async, per-company.

```python
async def scan_died_mid_work(company: CompanyConfig, client: PaperclipClient,
                              state: State, config: Config) -> list[Action]:
    """Find issues stuck in assignee-set + no-run state."""
    now = datetime.utcnow()
    threshold = now - timedelta(minutes=company.thresholds.died_min)
    issues = await client.list_in_progress_issues(company.id)
    actions: list[Action] = []

    for issue in issues:
        if issue.assignee_agent_id is None:
            continue
        if issue.execution_run_id is not None:
            continue
        if issue.updated_at > threshold:
            continue
        if state.is_escalated(issue.id):
            # Permanent-escalation cuts off auto-unescalate after M re-escalation cycles.
            # Scenario this prevents: broken agent → 3 wakes → escalate → operator
            # comments "looking" → auto-unescalate → 3 wakes again → escalate → ...
            # After 3 such full cycles, require explicit `unescalate` CLI invocation.
            if state.is_permanently_escalated(issue.id):
                continue
            # Auto-unescalate if operator touched issue after escalation
            if issue.updated_at > state.escalated_issues[issue.id]["escalated_at"]:
                state.clear_escalation(issue.id)
            else:
                continue

        if state.is_issue_in_cooldown(issue.id, config.cooldowns.per_issue_seconds):
            actions.append(Action(kind="skip", issue=issue, reason="per_issue_cooldown"))
            continue
        if state.agent_cap_exceeded(issue.assignee_agent_id, config.cooldowns):
            actions.append(Action(kind="escalate", issue=issue,
                                  agent_id=issue.assignee_agent_id,
                                  reason="per_agent_cap"))
            continue

        actions.append(Action(kind="wake", issue=issue,
                              agent_id=issue.assignee_agent_id))

    return actions
```

**`scan_idle_hangs`** — sync, host-wide.

```python
def scan_idle_hangs(config: Config) -> list[HangedProc]:
    """Find claude subprocesses exceeding hang thresholds (union of per-company thresholds)."""
    # Use minimum etime + max cpu across companies (strictest filter)
    etime_min = min(c.thresholds.hang_etime_min for c in config.companies) * 60
    cpu_max = max(c.thresholds.hang_cpu_max_s for c in config.companies)

    result = subprocess.run(
        ["ps", "-ao", "pid,etime,time,command"],
        capture_output=True, text=True, check=True,
    )
    return parse_ps_output(result.stdout, etime_min, cpu_max)


def parse_ps_output(ps_output: str, etime_min: int, cpu_max: int) -> list[HangedProc]:
    hanged = []
    for line in ps_output.splitlines()[1:]:  # skip header
        fields = line.split(None, 3)
        if len(fields) < 4:
            continue
        if "append-system-prompt-file" not in fields[3] or "paperclip-skills" not in fields[3]:
            continue
        pid = int(fields[0])
        etime_s = _parse_etime(fields[1])  # "1:06:07" or "DD-HH:MM:SS"
        cpu_s = _parse_time(fields[2])      # "0:35.61" (macOS) or "00:00:35" (Linux)
        if etime_s >= etime_min and cpu_s <= cpu_max:
            hanged.append(HangedProc(pid=pid, etime_s=etime_s, cpu_s=cpu_s))
    return hanged
```

**Platform notes for `_parse_time`:**
- macOS: `MM:SS.hundredths` (e.g. `0:35.61` = 35.61s)
- Linux: `HH:MM:SS` or `D-HH:MM:SS` for days (e.g. `00:00:35` = 35s)

Detection via `sys.platform` at module load; pick parser.

### 4.5 Action primitives

**`trigger_respawn`** — PATCH-based primary, with POST `/release` pre-step for stale-lock cases.

**Endpoint verification (2026-04-21):**
- `POST /api/agents/{id}/wake` → **HTTP 404 not found.** `wakeAgentSchema` in paperclip source (`paperclipai/dist/index.js:1527`) is an internal Zod schema for validation, NOT exposed as REST route.
- `PATCH /api/issues/{id}` with `{assigneeAgentId: same}` → **works** (GIM-62 proven; triggers `assignment` wake event).
- `POST /api/issues/{id}/release` → **works** (GIM-62 proven; clears assignee + potentially clears stale `executionRunId`).

**Revised logic** (no `/wake`, no fallback branching):

```python
async def trigger_respawn(client: PaperclipClient, issue: Issue,
                           assignee_id: str) -> RespawnResult:
    """PATCH assigneeAgentId=same to trigger paperclip 'assignment' wake event.
    
    If PATCH alone doesn't trigger a new run within 30s (possible if
    paperclip has a stale lock referring to the dead run), retry with
    POST /release + PATCH sequence — the proven GIM-52/53 workaround.
    """
    # Primary: single PATCH (fast path, most cases work)
    await client.patch_issue(issue.id, {"assigneeAgentId": assignee_id})
    for _ in range(6):
        await asyncio.sleep(5)
        refreshed = await client.get_issue(issue.id)
        if refreshed.execution_run_id is not None:
            return RespawnResult(via="patch", success=True,
                                 run_id=refreshed.execution_run_id)

    # Fallback: POST /release clears stale lock, then PATCH re-triggers
    log.info("respawn_fallback_release_patch", issue=issue.id)
    try:
        await client.post_release(issue.id)
    except PaperclipError as e:
        log.warning("release_failed", issue=issue.id, error=str(e))
    await client.patch_issue(issue.id, {"assigneeAgentId": assignee_id})
    for _ in range(6):
        await asyncio.sleep(5)
        refreshed = await client.get_issue(issue.id)
        if refreshed.execution_run_id is not None:
            return RespawnResult(via="release_patch", success=True,
                                 run_id=refreshed.execution_run_id)

    return RespawnResult(via="none", success=False, run_id=None)
```

**`kill_hanged_proc`** — with PID-cmdline re-verification to mitigate PID-reuse race.

```python
def kill_hanged_proc(proc: HangedProc) -> KillResult:
    """SIGTERM, wait 3s, SIGKILL if still alive.

    Re-verifies PID-cmdline match before sending signal. On macOS, PID max
    is 99999 and reuse can happen on long-running systems; between the
    scan and the kill, the original process could have exited and its PID
    could have been reassigned to an unrelated process (or critical OS
    service). This check catches that rare race.
    """
    # Re-verify: same PID, same command, etime roughly matches
    current = _read_proc_cmdline(proc.pid)
    if current is None:
        return KillResult(pid=proc.pid, status="already_dead")
    if "append-system-prompt-file" not in current or "paperclip-skills" not in current:
        log.warning("pid_reused", pid=proc.pid, old_cmd_prefix=proc.command[:60],
                    new_cmd_prefix=current[:60])
        return KillResult(pid=proc.pid, status="pid_reused_skip")

    try:
        os.kill(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        return KillResult(pid=proc.pid, status="already_dead")

    time.sleep(3)
    try:
        os.kill(proc.pid, 0)  # check
        os.kill(proc.pid, signal.SIGKILL)
        return KillResult(pid=proc.pid, status="forced")
    except ProcessLookupError:
        return KillResult(pid=proc.pid, status="clean")


def _read_proc_cmdline(pid: int) -> str | None:
    """Return current process cmdline, or None if process is gone."""
    result = subprocess.run(
        ["ps", "-p", str(pid), "-o", "command="],
        capture_output=True, text=True,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return None
    return result.stdout.strip()
```

### 4.6 State file

**`~/.paperclip/watchdog-state.json`** shape:

```json
{
  "version": 1,
  "last_updated": "2026-04-21T02:14:00Z",
  "issue_cooldowns": {
    "<issue-uuid>": {"last_wake_at": "2026-04-21T02:10:30Z"}
  },
  "agent_wakes": {
    "<agent-uuid>": ["2026-04-21T01:55:00Z", "..."]
  },
  "escalated_issues": {
    "<issue-uuid>": {
      "escalated_at": "2026-04-21T01:45:00Z",
      "reason": "per_agent_cap_exceeded",
      "escalation_count": 1,
      "permanent": false
    }
  }
}
```

**Fields explained:**
- `escalation_count`: incremented each time we re-escalate the same issue (including after auto-unescalate + re-trigger cycle)
- `permanent`: set to `true` when `escalation_count >= 3`. Auto-unescalate is skipped while `permanent=true`. Only `gimle-watchdog unescalate --issue <uuid>` clears it.

**Version migration policy** (for future schema changes):
- Unknown `version` → rename current file to `watchdog-state.json.bak-<timestamp>`, start with empty state, log `WARN state_version_unknown`.
- Missing `version` (very old corrupted file) → same recovery path.
- This avoids blocking daemon startup on a single bad field while preserving forensic data.

**Atomic writes:** write to `<path>.tmp` then `os.replace()` (POSIX-atomic).
**Corrupt-file recovery:** read errors → log WARN + start with empty state (don't crash daemon).
**Pruning:** `record_wake` drops `agent_wakes` entries older than 1h to bound state size.

### 4.7 Platform service installers

`service.py` exposes three pure-render functions (no system calls — testable via fixture comparison):

- `render_plist(config: Config, venv_path: Path, config_path: Path) -> str`
- `render_systemd_unit(config, venv_path, config_path) -> str`
- `render_cron_entry(config, venv_path, config_path) -> str`

`__main__.py install` glues them together:

```python
def cmd_install(args):
    platform = detect_platform()
    config_path = args.config_path or DEFAULT_CONFIG_PATH
    venv_path = find_venv_for_script()  # services/watchdog/.venv/bin/python

    if args.dry_run:
        print(render_for_platform(platform, ...))
        return

    if platform == "macos":
        plist = render_plist(config, venv_path, config_path)
        plist_path = Path("~/Library/LaunchAgents/work.ant013.gimle-watchdog.plist").expanduser()
        plist_path.write_text(plist)
        subprocess.run(["launchctl", "load", "-w", str(plist_path)], check=True)
        _verify_running("work.ant013.gimle-watchdog")

    elif platform == "linux" and _has_systemd():
        unit = render_systemd_unit(config, venv_path, config_path)
        unit_path = Path("~/.config/systemd/user/gimle-watchdog.service").expanduser()
        unit_path.parent.mkdir(parents=True, exist_ok=True)
        unit_path.write_text(unit)
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
        subprocess.run(["systemctl", "--user", "enable", "--now", "gimle-watchdog.service"], check=True)
        _verify_running_systemd("gimle-watchdog.service")

    else:
        # Fallback: crontab
        entry = render_cron_entry(config, venv_path, config_path)
        _append_crontab_entry(entry, marker="# gimle-watchdog")
```

**`--discover-companies` flag** — overwrite semantics:
- On first install (config missing OR `companies: []` empty): runs `GET /api/companies`, auto-populates with non-archived entries. No prompt.
- On re-install with existing non-empty `companies:` list: **errors out** with clear message:
  ```
  Config at ~/.paperclip/watchdog-config.yaml already has 2 companies configured.
  --discover-companies will OVERWRITE your edits (thresholds, names).
  Re-run with --force to overwrite, or edit the file manually.
  ```
- `--force` overrides the error (operator consent-required).

This prevents silent loss of operator-tuned thresholds when running install a second time.

**`--dry-run`:** print would-write content without actually writing.

### 4.7.1 State file locking

Single-writer guarantee via `fcntl.flock(fd, LOCK_EX | LOCK_NB)` on the state file. If another daemon instance holds the lock:

```python
for attempt in range(3):
    try:
        fcntl.flock(state_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        break
    except BlockingIOError:
        log.warn("state_locked_retry", attempt=attempt)
        time.sleep(2)
else:
    log.error("state_locked_fatal_another_daemon_present")
    sys.exit(2)  # hard fail — launchd will not restart-loop because
                 # exit code 2 can be configured as "do not restart"
                 # (in plist ExitTimeOut + SuccessfulExit behavior)
```

`exit(2)` signals to `launchd`/`systemd` that this is a permanent setup error, not a transient fault — avoids the 10-second restart loop that `exit(1)` would trigger.

### 4.8 CLI surface

```
gimle-watchdog install [--config PATH] [--dry-run] [--discover-companies] [--force]
gimle-watchdog uninstall [--purge]                     # --purge also deletes state + log
gimle-watchdog run                                     # long-running loop (launchd/systemd)
gimle-watchdog tick                                    # one-shot scan + exit (cron)
gimle-watchdog status                                  # service state + filter-match count + cooldowns
gimle-watchdog tail [-n N] [-f] [--level L]
gimle-watchdog unescalate --issue <uuid>               # clear escalation (including permanent flag)
gimle-watchdog escalate --issue <uuid> --permanent     # manually mark issue as permanently escalated
```

All commands read `--config PATH` or default `~/.paperclip/watchdog-config.yaml`.

### 4.8.1 `status` health-check — filter-drift detection

The `status` CLI reports a count of `ps` processes matching our `append-system-prompt-file.*paperclip-skills` filter, **across any etime** (not just idle-hangs):

```
$ gimle-watchdog status
Service: gimle-watchdog (launchd)           active (running) since 2026-04-21 10:00:00
Current tick: 2026-04-21T15:14:00Z          no hangs detected
Filter health:
  paperclip-skills procs seen today: 47     ← if 0 for 24h+, filter may be stale
  (This catches upstream Anthropic renaming of --append-system-prompt-file, etc.)
Cooldowns active:                            2
Escalations (auto):                          0
Escalations (permanent):                     1 (use `unescalate --issue <uuid>` to clear)
```

If `procs seen today: 0` across multiple hours while paperclip agent activity is non-zero (cross-check via `GET /api/issues?status=in_progress`), the filter has probably drifted — Anthropic renamed a flag, or paperclip changed its subprocess invocation. Operator action: update filter pattern in `detection.py` and re-deploy.

**Daily process-match counter persistence:** state file gets a new field:
```json
"daily_filter_stats": {
  "2026-04-21": {"procs_seen": 47, "kills": 0}
}
```
Older dates pruned (keep 30 days).

## 5. Scope boundaries

### 5.1 In scope

- Python package `services/watchdog/` with modules above
- Config YAML with multi-company support
- Detection for mid-work-died + idle-hang
- Wake with POST /wake primary + PATCH fallback
- Per-issue cooldown + per-agent cap + escalation
- State file with atomic writes
- Platform-native installers: macOS launchd, Linux systemd, crontab fallback
- Local JSON-lines log with rotation
- Escalation comments on paperclip issues (dedup via state file)
- Full test suite: unit (config/state/detection/actions/paperclip) + integration (FastAPI mock paperclip)
- Install-script integration (edit existing `install.sh` / `just install`)
- README.md with install, troubleshoot, live smoke sections

### 5.2 Out of scope (deferred)

- **Paperclip plugin rewrite** — future GIM-6X. Cron is MVP; plugin event-driven architecture is cleaner but heavier.
- **`/stats` HTTP endpoint** — §4.8 GIM-15 telemetry service pattern. Watchdog's daemon could expose one, but MVP = log-only.
- **Multi-paperclip-instance support** — current config assumes single paperclip URL, multiple companies. If user has two separate paperclipai servers, need two watchdog daemons (or config `paperclip_instances: []` extension — not designed).
- **Windows platform support** — not a target.
- **Test-coverage for actual launchctl/systemctl invocation** — renderers tested via fixtures; live install tested manually per §7.3.

### 5.3 Non-goals

- Watchdog does NOT manage paperclipai itself (node daemon) — assume it's running. If paperclipai dies, recovery is outside watchdog's scope.
- Watchdog does NOT attempt to restart paperclip services (`docker compose up`). If `GET /api/companies` 5xx's, log and skip this tick.
- Watchdog does NOT rewrite broken role prompts or agent configs. Escalation comment flags the problem; human fixes the root cause.

## 6. Failure modes + observability

### 6.1 Failure matrix

| Situation | Detection | Response |
|---|---|---|
| Paperclip API 5xx (transient) | httpx exception | log WARN, skip this tick, retry next tick |
| Paperclip API 429 (rate limit) | status check | exponential back-off: next tick waits 2×, 4×, 8× normal interval, max 30 min. Resets on first 2xx. |
| Paperclip API 401/403 | status check | log ERROR, keep running (operator must fix token) |
| PATCH primary respawn trigger fails (no new run in 30s) | verify loop | fall to release+PATCH path (§4.5). If still fails, count as wake attempt, log ERROR |
| `ps` command fails (permissions) | subprocess error | log ERROR, skip scenario (b) for this tick, still run (a) |
| `kill` permission denied | OSError | log ERROR, move on, next tick retries |
| PID reused between scan and kill | cmdline re-check (§4.5) | log WARN `pid_reused`, skip kill, next tick will re-scan |
| `_tick` itself hangs > 60s | `asyncio.wait_for` timeout | log ERROR, `sys.exit(1)`, launchd KeepAlive restarts |
| Config YAML malformed | parse error | daemon fails to start with `sys.exit(2)`, clear error message |
| State file corrupted | json.JSONDecodeError | log WARN, start with empty state, continue |
| State file unknown version | version mismatch | rename to `.bak-<ts>`, start empty, log WARN |
| State file locked by another daemon | `fcntl.LOCK_NB` BlockingIOError | retry 2× with 2s sleep, then `sys.exit(2)` (do-not-respawn) |
| Escalation comment post fails | paperclip API error | log ERROR, escalation still recorded in state (not retried) |
| Daily filter-match count = 0 for 24h+ | status health-check | log WARN `filter_drift_suspected`, operator notified via `status` output |

### 6.2 Security model

- **Token exposure**: daemon reads `PAPERCLIP_API_KEY` from env (launchd/systemd propagate via `EnvironmentFile`/`EnvironmentVariables`). File-based `api_key_source: file:<path>` supported for paranoid setups — file mode 600 check enforced on read.
- **No external ports**: daemon doesn't listen on any port (MVP). No network exposure beyond outbound to paperclip API.
- **Host-process kill authority**: daemon runs as user `anton` (same UID as paperclipai). Can only kill processes it owns. Won't accidentally kill root processes or other users.
- **State file permissions**: written with mode 600.
- **Log file permissions**: mode 644 (operator convenience — log lines don't contain tokens or PII).

### 6.3 Observability layers

1. **Local JSON-lines log** — `~/.paperclip/watchdog.log`, rotated. `gimle-watchdog tail` convenience reader.
2. **State file** — human-readable JSON at `~/.paperclip/watchdog-state.json`. Shows current cooldowns + escalations.
3. **Paperclip issue comments** — only on escalation, marker-deduped (`<!-- watchdog-escalation -->`).
4. **`gimle-watchdog status`** — one-command summary combining above.
5. **launchd/systemd status** — standard platform tools: `launchctl list | grep watchdog`, `systemctl --user status gimle-watchdog`.

Metrics/dashboard deferred.

## 7. Testing plan

### 7.1 Unit tests (pytest, in-process)

**`test_config.py`:**

| Test | Verifies |
|---|---|
| `test_valid_config_parses` | Full YAML → Config object |
| `test_unknown_version_raises` | `version: 999` → ConfigError |
| `test_empty_companies_raises` | `companies: []` → ConfigError |
| `test_invalid_uuid_raises` | malformed company id → ConfigError |
| `test_api_key_env_resolution` | `env:FOO` → reads `os.environ["FOO"]` |
| `test_api_key_missing_env_warns` | `env:NONEXISTENT` → None + log WARN |
| `test_api_key_file_resolution` | `file:/path` → reads file content |
| `test_negative_threshold_raises` | `died_min: -1` → ConfigError |

**`test_detection.py`:**

| Test | Verifies |
|---|---|
| `test_parse_etime_macos_mm_ss` | `"5:30"` → 330 |
| `test_parse_etime_macos_hh_mm_ss` | `"1:06:07"` → 3967 |
| `test_parse_etime_linux_days` | `"1-02:00:00"` → 93600 |
| `test_parse_time_macos_decimal` | `"0:35.61"` → 36 |
| `test_parse_time_linux_hms` | `"00:00:35"` → 35 |
| `test_parse_ps_filters_non_paperclip` | ps lines without `paperclip-skills` → skipped |
| `test_parse_ps_finds_hang` | hanged proc fixture → returned |
| `test_parse_ps_skips_active` | fresh proc (etime 5min) → skipped |
| `test_scan_died_skips_null_assignee` | issue with no assignee → not actioned |
| `test_scan_died_skips_active_run` | `executionRunId` non-null → not actioned |
| `test_scan_died_skips_recent_update` | `updatedAt` 1min ago → not actioned |
| `test_scan_died_wakes_stuck` | stuck issue → Action(kind=wake) |
| `test_scan_died_respects_cooldown` | issue in cooldown → Action(kind=skip) |
| `test_scan_died_escalates_at_cap` | agent exceeded cap → Action(kind=escalate) |
| `test_scan_died_auto_unescalates_on_touch` | escalated issue with newer updatedAt → cleared + actioned |

**`test_state.py`:**

| Test | Verifies |
|---|---|
| `test_state_roundtrip` | write + read identical |
| `test_corrupt_state_returns_empty` | broken JSON → empty state + WARN |
| `test_is_issue_in_cooldown_within` | record + check within cooldown window → True |
| `test_is_issue_in_cooldown_after` | check after cooldown expired → False |
| `test_agent_cap_exceeded_within_window` | 3 wakes in 15min → True |
| `test_agent_cap_not_exceeded_outside_window` | 3 wakes but 2 > 15min old → False |
| `test_record_wake_prunes_old` | after `record_wake`, state has entries < 1h only |
| `test_atomic_write` | `os.replace` used (mock or check tempfile) |

**`test_paperclip.py`** (httpx MockTransport):

| Test | Verifies |
|---|---|
| `test_list_in_progress_issues` | parses response into Issue list |
| `test_wake_agent_posts_correct_body` | body matches `wakeAgentSchema` |
| `test_patch_issue_assignee` | correct endpoint + body |
| `test_get_issue_returns_issue` | fields mapped |
| `test_retry_5xx` | 503 → 503 → 200 (3 attempts) |
| `test_409_idempotency_not_error` | 409 treated as no-op success |
| `test_401_terminal` | 401 → PaperclipError, no retry |

**`test_actions.py`:**

| Test | Verifies |
|---|---|
| `test_wake_with_fallback_via_wake` | /wake → verify poll finds run_id → via="wake" |
| `test_wake_with_fallback_via_patch` | /wake posts but no run → PATCH → success → via="patch" |
| `test_wake_with_fallback_total_failure` | both fail → success=False |
| `test_kill_hanged_proc_clean_exit` | SIGTERM, process gone at check → status="clean" |
| `test_kill_hanged_proc_forced` | SIGTERM, still alive → SIGKILL → status="forced" |
| `test_kill_hanged_proc_already_dead` | process missing → status="already_dead" |

**`test_service.py`:**

| Test | Verifies |
|---|---|
| `test_render_plist_matches_fixture` | `render_plist(test_config)` == `fixtures/plist_expected.xml` |
| `test_render_systemd_matches_fixture` | same pattern |
| `test_render_cron_matches_fixture` | same pattern |
| `test_render_plist_escapes_paths_with_spaces` | path with space → XML-valid |

### 7.2 Integration test (FastAPI mock paperclip)

**`test_integration.py`:** spins up FastAPI in-process mock exposing:
- `GET /api/companies/{id}/issues` → returns configurable list
- `POST /api/agents/{id}/wake` → mutates mock state (sets new `executionRunId`)
- `PATCH /api/issues/{id}` → stores change
- `POST /api/issues/{id}/comments` → records

Scenarios:

| Scenario | Setup | Assert |
|---|---|---|
| `test_tick_wakes_stuck_issue` | mock issue stuck 5min | after tick: wake call made, state.record_wake invoked |
| `test_tick_respects_cooldown` | state has recent wake for issue | after tick: NO wake call |
| `test_tick_escalates_at_cap` | state has 3 recent wakes for agent | after tick: escalation comment posted, no new wake |
| `test_tick_auto_unescalates` | escalated issue with new updatedAt | after tick: escalation cleared, wake attempted |

### 7.3 Platform install tests

Renderers are unit-tested (§7.1). Actual `launchctl`/`systemctl` invocation is NOT unit-tested — tested via `--dry-run` manual flow documented in README:

```bash
cd services/watchdog
uv run python -m watchdog install --dry-run   # prints plist/unit/cron without writing
uv run python -m watchdog install              # real install
uv run python -m watchdog status               # verify running
uv run python -m watchdog uninstall            # clean removal
```

### 7.4 Live smoke test (post-deploy, manual)

Documented in `services/watchdog/README.md`:

1. **Mid-work-died test**: create disposable paperclip issue assigned to idle agent. PATCH status=in_progress. Wait for Claude process spawn. `pkill` that process. Within 2-4 minutes, log should show `died_detected` + `wake_attempt` + `wake_success`.

2. **Idle-hang test**: hard to reproduce deterministically (depends on MCP-child timing). Alternative: `kill -STOP` a running Claude process to simulate hang. Watchdog should detect after `hang_etime_min` threshold and kill.

3. **Escalation test**: spawn disposable issue with broken role instructions (role that loops without reassign). After 3 wakes, verify escalation comment appears on issue with proper marker.

### 7.5 Test-design-discipline compliance (GIM-61)

- ✅ `httpx.MockTransport` not `MagicMock(httpx.AsyncClient)` — real httpx, fake network
- ✅ `subprocess.run` not mocked; `parse_ps_output(ps_str)` takes injected string
- ✅ `os.kill` tests use real signals on a real spawned `sleep 300` child process (not mocked)
- ✅ Integration test = real FastAPI app in-process — behaves like real paperclip (incl. HTTP error shapes)

Coverage goal: **85%+ of instrumented code**, declared excludes in `.coveragerc`:

```ini
[run]
omit =
  # Platform-specific branches — tested on live OS only, not by opposite-OS CI
  */service.py:detect_platform

[report]
exclude_lines =
  # CLI entrypoint boilerplate (tested by integration, not unit)
  if __name__ == .__main__.:
  # Subprocess calls to system tools (launchctl/systemctl) — real execution is live-smoke
  subprocess.run\(\[.launchctl.
  subprocess.run\(\[.systemctl.
  # Defensive branches for conditions that require OS support we can't fake
  if sys.platform == .win32.:
  pragma: no cover
```

Measured via `pytest --cov=watchdog --cov-config=.coveragerc`. CI reports `coverage xml` artifact for PR review.

## 8. Rollout order

1. **Write code on `feature/GIM-63-agent-watchdog`** (already created off `068014f`). All tests pass locally.
2. **Pre-merge operator tasks**:
   - Ensure `.env` has `PAPERCLIP_API_KEY` (already present from GIM-62)
   - No new secrets needed — daemon reads existing token
   - **Token scope pre-check** — verify the existing Board-level token can perform the PATCH that drives respawn. On iMac (or any machine with `$PAPERCLIP_API_KEY`):
     ```bash
     curl -sS -w "HTTP %{http_code}\n" -X PATCH \
       -H "Authorization: Bearer $PAPERCLIP_API_KEY" \
       -H "Content-Type: application/json" \
       -d '{"assigneeAgentId":"<CTO-uuid>"}' \
       "$PAPERCLIP_BASE/api/issues/<any-cto-assigned-issue>"
     # Expected: HTTP 200 (verified in GIM-62, but re-check in case scope changed)
     ```
     If 403 → obtain higher-scope token before merge. (Existing `pcp_board_*` token verified 2026-04-21 to work for PATCH.)
3. **Merge to develop** — CI green (new `watchdog-tests` CI job added, mirrors `github-scripts-tests`).
4. **Install on iMac** — manual SSH + `cd /Users/Shared/Ios/Gimle-Palace && git pull && cd services/watchdog && uv sync && uv run python -m watchdog install --discover-companies`.
5. **Verify** via `gimle-watchdog status` + checking iMac log file.
6. **Live smoke** (§7.4) — run tests 1-3 against production watchdog.
7. **Update install.sh** — in a followup micro-slice (or inline in this slice if trivial).

## 9. Success criteria

This slice is successful when:

- New paperclip issues stuck in `assignee+no-run+stale` state are auto-resurrected within 3-5 minutes without operator action
- Claude subprocesses hanging idle are auto-killed within `hang_etime_min` + 2 minutes
- Same issue getting wake-spammed is prevented by per-issue cooldown
- Rogue agent (persistently failing) is escalated via paperclip comment after 3 wakes in 15 min
- Escalation can be cleared either automatically (on operator touch) or manually (`unescalate` CLI)
- Watchdog itself does NOT crash, even under paperclip downtime or network flakes (continues trying next tick)
- All tests pass in CI (new `watchdog-tests` job)
- Live smoke tests 1-3 pass on iMac post-install

## 10. Open questions / trade-offs

- **Honest scope assessment**: this is the largest slice among GIM-59/61/62/63 — ~1000-1200 LOC prod + ~1000-1500 LOC test, 3 days of engineer-time, not an afternoon janitor script. The "janitor" framing in earlier drafts understated complexity; §1 now reflects reality.

- **Coarse cap vs per-(agent,issue) cap**: chosen per-agent cap. Consequence: if agent X legitimately has 3 stuck issues in parallel (shouldn't happen in Gimle — each agent handles one phase at a time), all 3 escalate after 3 total wakes of agent X. Acceptable given current usage pattern. Revisit if pattern changes.

- **Kill authority on host**: daemon runs as `anton` user. Can kill own processes. If paperclipai runs as different user (it doesn't currently — same user), watchdog can't `kill` its children. Document this assumption; if it changes, need `sudo` or polkit rule.

- **Idempotency vs retry interaction**: `idempotency_key` on `/wake` contains minute-bucketed timestamp. Same issue woken in back-to-back ticks (<1min) produces same key → paperclip may 409 (documented as "already woken"). Treat as success; no retry. This is correct behavior — we don't want two wakes in <60s window anyway.

- **launchd `KeepAlive=true` vs throttling**: if daemon crashes repeatedly, launchd restarts it every 10s (system default `ThrottleInterval`). We rely on this; worst case = noisy log but no cascade failure.

- **State file growth**: `agent_wakes` pruned to 1h window. `escalated_issues` never pruned (grows monotonically). Annual size estimate at current rates: <100KB. Acceptable; revisit if 1M+ escalations happen.

- **Windows (future)**: `service.py` has no Windows renderer. Out of scope for GIM-63. If needed later: Task Scheduler XML + `schtasks`.

- **Test for actual sleep/wake timing**: `_tick` sleeps 10s between scenario (b) and (a). In unit tests we stub the sleep. Integration test runs a real async sleep but shortened via `freezegun`. Acceptable.

---

**Predecessor context cited:**
- GIM-62 introduced paperclip-signal dispatcher; during its CTO hang we empirically discovered auto-respawn gap.
- GIM-61 test-design-discipline fragment shapes how watchdog tests are written.
- GIM-15 §4.8 telemetry pattern informs future `/stats` endpoint extension (deferred).
