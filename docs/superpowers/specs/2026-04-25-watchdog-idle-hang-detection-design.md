---
slug: watchdog-idle-hang-detection
status: proposed
branch: feature/GIM-80-watchdog-idle-hang (cut from develop after GIM-78 umbrella lands)
paperclip_issue: 80
parent_umbrella: 79
predecessor: develop tip after umbrella merge
date: 2026-04-25
---

# GIM-79 — Watchdog idle-hang detection improvements

## 1. Context

Current watchdog config (`~/.paperclip/watchdog-config.yaml` rev1, set during GIM-63 deploy):

```yaml
companies:
  - id: 9d8f432c-ff7d-4e3a-bbe3-3cd355f73b64
    name: gimle
    thresholds:
      died_min: 3
      hang_etime_min: 60
      hang_cpu_max_s: 30   # ← problem
```

Logic: a Claude subprocess is classified as "hang" iff `etime > 60min AND cpu_time < 30s`. The `kill -KILL` action follows.

## 2. Problem

Confirmed 2026-04-25 from a real session:

- PID 32864 ran for **3h 53min** with 0.3% recent CPU.
- Cumulative CPU time was estimated at 30-60s — slightly **above** the 30s threshold.
- Watchdog's two-minute tick saw the process at every interval and never triggered (`actions=0` in log).
- Process was an `OpusArchitectReviewer` Phase 3.2 run that hit Anthropic token quota overnight; subprocess didn't exit, paperclip held the issue lock the whole time, the entire slice was blocked.
- Operator had to SSH in, manually `kill -TERM 32864`.

The threshold is too strict against an obvious idle hang. Symmetric mistake (raise to 300s) would let real long runs (e.g. CR adversarial reviews of large PRs) be killed early.

## 3. Solution — two complementary criteria

### 3.1 Criterion A — CPU-time ratio (replaces `hang_cpu_max_s`)

Replace absolute `hang_cpu_max_s` with a **ratio** `cpu_time / etime` measured in dimensionless units. A process that's been alive for an hour but only used 5 seconds of CPU has ratio 5/3600 ≈ 0.0014; an active LLM run typically sits at 0.05–0.20. Threshold suggestion: `idle_cpu_ratio_max: 0.005`.

```python
# detection.py — new shape
def is_idle_hang(proc, cfg):
    etime_s = proc.etime_seconds
    if etime_s < cfg.hang_etime_min * 60:
        return False                                  # too young to judge
    cpu_ratio = proc.cpu_time_s / etime_s
    return cpu_ratio < cfg.idle_cpu_ratio_max
```

Default `idle_cpu_ratio_max = 0.005` (0.5% over wall time). Tune after first month of live data.

### 3.2 Criterion B — Time since last stream-json event

Claude subprocesses paperclip spawns use `--output-format stream-json --verbose`. Each token batch / tool call / progress event emits a JSON line on stdout. If the subprocess has emitted nothing for >5 min, it's effectively dead even if accumulated CPU is high.

Implementation:

```python
# watchdog/detection.py — new helper
def last_stream_event_age_seconds(proc) -> int | None:
    """Tail the subprocess stdout (paperclip pipes it to a file) and
    return seconds since the last JSON line. None if no log file."""
    log_path = _resolve_paperclip_subprocess_log(proc.pid)
    if not log_path or not log_path.exists():
        return None
    last_mtime = log_path.stat().st_mtime
    return int(time.time() - last_mtime)

def is_stream_stalled(proc, cfg):
    age = last_stream_event_age_seconds(proc)
    if age is None:
        return False                                  # no log to judge
    return age > cfg.hang_stream_idle_max_s
```

Default `hang_stream_idle_max_s = 300` (5 min). Tune later.

**Discovery of paperclip subprocess log path:** paperclip writes per-task logs under `/var/folders/.../T/paperclip-skills-XXXXXX/agent-instructions.md` and (likely) a sibling `*.log` or stream output. We confirm in Task 0 by inspecting a live paperclip run on iMac.

### 3.3 Decision rule

A process is a hang if **either** Criterion A or Criterion B fires:

```python
def is_hang(proc, cfg):
    return is_idle_hang(proc, cfg) or is_stream_stalled(proc, cfg)
```

Conservative on purpose: if either signal triggers we kill, because the cost of killing a real long run (paperclip will respawn) is much smaller than letting an idle hang block a slice for hours.

### 3.4 Config schema migration

`~/.paperclip/watchdog-config.yaml` gains:

```yaml
companies:
  - id: ...
    thresholds:
      died_min: 3
      hang_etime_min: 60
      idle_cpu_ratio_max: 0.005      # NEW (replaces hang_cpu_max_s)
      hang_stream_idle_max_s: 300    # NEW
      hang_cpu_max_s: 30             # DEPRECATED — keep for one release with backward-compat read; warn in log
```

Backward-compat: if `hang_cpu_max_s` present in config, log a deprecation warning and ignore it (don't auto-translate — operator should explicitly choose ratio).

## 4. Tasks

0. Confirm paperclip subprocess stdout log path on iMac. SSH, find a live paperclip run, locate where its stream-json output is being written. Document in `docs/research/paperclip-subprocess-log-layout.md`.
1. Update `services/watchdog/src/gimle_watchdog/config.py` — add `idle_cpu_ratio_max: float`, `hang_stream_idle_max_s: int`, deprecate `hang_cpu_max_s` with warning.
2. Update `services/watchdog/src/gimle_watchdog/detection.py` — implement `is_idle_hang`, `last_stream_event_age_seconds`, `is_stream_stalled`, `is_hang`. Replace single-criterion check.
3. Unit tests per §6.1.
4. Integration test (sandbox-process simulator) per §6.2.
5. Update `~/.paperclip/watchdog-config.yaml` on iMac via SSH (operator step) with new fields; preserve old as deprecated.
6. Live smoke per §6.3.

## 5. API / config impact

Configuration only. No new MCP tools. No Graphiti or Codebase-Memory dependencies. Watchdog binary version bump.

## 6. Tests

### 6.1 Unit tests

- `test_is_idle_hang_under_threshold_skips_young_proc` — etime < hang_etime_min returns False regardless of ratio.
- `test_is_idle_hang_high_etime_low_ratio_kills` — etime=14000s, cpu_time=40s → ratio 0.0028 < 0.005 → True.
- `test_is_idle_hang_high_etime_high_ratio_keeps` — etime=14000s, cpu_time=200s → ratio 0.014 > 0.005 → False.
- `test_is_stream_stalled_no_log_returns_false` — proc whose log file is missing → False.
- `test_is_stream_stalled_recent_event_returns_false` — log mtime 60s ago, threshold 300 → False.
- `test_is_stream_stalled_old_event_returns_true` — log mtime 600s ago, threshold 300 → True.
- `test_is_hang_either_criterion_triggers` — only one of the two True → result True.
- `test_config_load_warns_on_deprecated_hang_cpu_max_s` — config with `hang_cpu_max_s` and no `idle_cpu_ratio_max` raises ConfigError; with `idle_cpu_ratio_max` set logs deprecation but loads.

### 6.2 Integration tests

Spawn synthetic subprocesses with controlled CPU usage via `python -c "import time; time.sleep(...)"` plus controlled stdout-emission timing.

- `test_real_idle_proc_classified_as_hang` — sleep proc with no output → idle ratio kicks in past hang_etime_min.
- `test_real_active_proc_not_classified` — busy-loop proc with frequent output → both criteria say not-hang.
- `test_stream_stall_killed_via_kickstart` — proc with high CPU but stalled output → killed via Criterion B.

### 6.3 Live smoke on iMac

1. SSH to iMac, ensure watchdog running new version (after merge + manual install).
2. `tail -f ~/.paperclip/watchdog.log` in one window.
3. Trigger a fake hang: `ssh imac "sleep 3700 &"` (etime > hang_etime_min, zero CPU).
4. Within next 1 watchdog tick (max 2 min after threshold) — log line `hang_killed pid=...`. Sleep proc exits.
5. Trigger a fake stalled-stream: long-running script with high CPU, stop emitting stdout via `kill -STOP`. Within hang_stream_idle_max_s + 1 tick — `hang_killed`.
6. `~/.paperclip/watchdog.err` stays empty for the duration of the smoke.

## 7. Risks

| Risk | Mitigation |
|---|---|
| Stream-stall criterion has false positives — Claude can be silent for several minutes during long tool calls (e.g. WebFetch with large response) | Default 300s is generous; tune after observation. If false-positives appear, raise threshold or add per-tool exemption. |
| Paperclip subprocess log location changes between paperclip versions | Task 0 documents where they live now; future paperclip update may need a config knob `paperclip_subprocess_log_glob`. |
| Backward-compat `hang_cpu_max_s` gets ignored silently | Log warning at every startup until operator removes the deprecated key. After 2 versions, remove the parser branch entirely. |

## 8. References

- Memory `reference_claude_process_idle_hang.md` (motivation).
- 2026-04-25 incident: PID 32864 idle 3h53min, accumulated CPU above 30s, watchdog never triggered.
- GIM-63 spec (original watchdog design): `docs/superpowers/specs/2026-04-21-GIM-63-agent-watchdog-design.md` §4.2.1.
