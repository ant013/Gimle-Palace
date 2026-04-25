---
slug: watchdog-idle-hang
issue: GIM-80
spec: docs/superpowers/specs/2026-04-25-watchdog-idle-hang-detection-design.md
branch: feature/GIM-80-watchdog-idle-hang
predecessor: 3f3fc9b (develop tip after GIM-79 umbrella merge)
date: 2026-04-25
---

# GIM-80 — Watchdog idle-hang detection: implementation plan

## Overview

Replace the absolute `hang_cpu_max_s` threshold with two complementary
criteria: CPU-time ratio and stream-json idle time. Pure Python change in
`services/watchdog/`. No Docker, no MCP, no Graphiti dependencies.

## Task 0 — Research: paperclip subprocess log path

**Owner:** PythonEngineer (or operator SSH confirmation)
**Files:** `docs/research/paperclip-subprocess-log-layout.md` (new)
**Acceptance:** Document where paperclip writes per-run stream-json stdout
for a live Claude subprocess on iMac. Needed before Criterion B can resolve
the log file path in code.

**Note:** If operator confirms the path before this task starts, engineer
can skip the SSH discovery and use the documented path directly.

**Blocking scope:** Task 0 only blocks the production path-resolution
logic in Task 2 (`_resolve_paperclip_subprocess_log`). Task 3 Criterion B
tests (`test_is_stream_stalled_*`) use mocked paths and do NOT depend on
Task 0. Implementer can proceed with Tasks 1–3 in parallel with Task 0.

## Task 1 — Config: add new thresholds, deprecate old

**Owner:** PythonEngineer
**Files:** `services/watchdog/src/gimle_watchdog/config.py`
**Depends on:** nothing

### Changes

1. Add fields to `Thresholds` dataclass:
   - `idle_cpu_ratio_max: float` (default `0.005`)
   - `hang_stream_idle_max_s: int` (default `300`)
2. Keep `hang_cpu_max_s` as `int | None` (optional, default `None`).
3. In `load_config()` / YAML parser — **and** in `_parse_thresholds()` (config.py:109-118):
   - If `idle_cpu_ratio_max` absent AND `hang_cpu_max_s` present: raise
     `ConfigError` with migration instructions (spec §3.4 aligned).
   - If both present: log `DeprecationWarning` for `hang_cpu_max_s`,
     ignore its value, use `idle_cpu_ratio_max`.
   - If only `idle_cpu_ratio_max` present: normal path.
4. Validate `idle_cpu_ratio_max` in range `(0.0, 1.0)`.
5. Validate `hang_stream_idle_max_s > 0`.

**Note:** `_parse_thresholds()` (config.py:109-118) must be updated to
parse the new fields; adding them to `Thresholds` dataclass alone is not
enough — the parser constructs `Thresholds` from raw YAML dict.

### Tests (in Task 3)

- `test_config_load_warns_on_deprecated_hang_cpu_max_s`
- `test_config_load_raises_without_idle_cpu_ratio_max`
- `test_config_load_validates_ratio_range`

### Commit

`feat(watchdog): add idle_cpu_ratio_max + hang_stream_idle_max_s config fields (GIM-80)`

## Task 2 — Detection: implement dual-criteria hang detection

**Owner:** PythonEngineer
**Files:** `services/watchdog/src/gimle_watchdog/detection.py`, `services/watchdog/src/gimle_watchdog/daemon.py`
**Depends on:** Task 1 (needs new `Thresholds` fields)

### Changes

1. Add `last_stream_event_age_seconds(pid: int) -> int | None`:
   - Resolve paperclip subprocess log path from PID (use path discovered
     in Task 0, likely `/proc/{pid}/fd/1` on Linux or lsof-based on macOS,
     or a config-driven glob).
   - If no log file found → return `None`.
   - Return `int(time.time() - log_path.stat().st_mtime)`.

2. Refactor `HangedProc` dataclass — add `cpu_ratio: float` field
   (computed as `cpu_s / etime_s` when `etime_s > 0`, else `0.0`).

3. Refactor `parse_ps_output()` signature:
   - Old: `parse_ps_output(ps_output, etime_min_s, cpu_max_s)`
   - New: `parse_ps_output(ps_output, etime_min_s, idle_cpu_ratio_max, hang_stream_idle_max_s)`
   - A proc is hanged if `etime >= etime_min_s` AND (`cpu_ratio < idle_cpu_ratio_max` OR `stream_event_age > hang_stream_idle_max_s`).

4. Update `scan_idle_hangs()` to pass new threshold fields instead of
   `cpu_max_s`.

5. Add `--debug-watchdog` support (Task 5 below covers CLI; detection.py
   just needs to expose ratio data in `HangedProc` for the debug printer).
6. Update `daemon.py:_tick()` kill-log line (currently `hang_killed pid=%d
   etime_s=%d cpu_s=%d`) to include `cpu_ratio=%.4f` and `stream_age_s=%s`.
   Also update `scan_idle_hangs()` call site (detection.py:120) to pass new
   threshold fields (`idle_cpu_ratio_max`, `hang_stream_idle_max_s`) instead
   of `hang_cpu_max_s`.

### Tests (in Task 3)

- `test_is_idle_hang_under_threshold_skips_young_proc`
- `test_is_idle_hang_high_etime_low_ratio_kills`
- `test_is_idle_hang_high_etime_high_ratio_keeps`
- `test_is_stream_stalled_no_log_returns_false`
- `test_is_stream_stalled_recent_event_returns_false`
- `test_is_stream_stalled_old_event_returns_true`
- `test_is_hang_either_criterion_triggers`

### Commit

`feat(watchdog): dual-criteria idle-hang detection — CPU ratio + stream stall (GIM-80)`

## Task 3 — Unit tests for Tasks 1 + 2

**Owner:** PythonEngineer
**Files:** `services/watchdog/tests/test_config.py`, `services/watchdog/tests/test_detection.py`
**Depends on:** Tasks 1, 2

### Tests to add/modify

In `test_config.py`:
- `test_config_load_warns_on_deprecated_hang_cpu_max_s`
- `test_config_load_raises_without_idle_cpu_ratio_max`
- `test_config_load_validates_ratio_range`
- `test_config_load_validates_stream_idle_positive`

In `test_detection.py`:
- All 7 tests from spec §6.1 (listed in Task 2 above).
- Update existing `parse_ps_output` tests for new signature.

### Commit

`test(watchdog): unit tests for dual-criteria hang detection (GIM-80)`

## Task 4 — Integration test: synthetic subprocess simulator

**Owner:** PythonEngineer
**Files:** `services/watchdog/tests/test_integration.py`
**Depends on:** Tasks 1, 2, 3

### Tests to add

- `test_real_idle_proc_classified_as_hang` — spawn `sleep` process with
  fake argv containing filter tokens; verify `parse_ps_output` classifies
  it after sufficient etime simulation.
- `test_real_active_proc_not_classified` — busy-loop proc with high CPU
  ratio → not classified as hang.
- `test_stream_stall_detected` — create temp log file, set mtime to
  past, verify `last_stream_event_age_seconds` returns correct age.

### Commit

`test(watchdog): integration tests for idle-hang simulator (GIM-80)`

## Task 5 — CLI: `--debug-watchdog` flag

**Owner:** PythonEngineer
**Files:** `services/watchdog/src/gimle_watchdog/__main__.py`
**Depends on:** Task 2

### Changes

1. Add `--debug-watchdog` flag to `tick` and `run` subcommands.
2. When set: run scan synchronously (not the async daemon loop), print
   each candidate proc's PID, etime, cpu_time, cpu_ratio,
   stream_event_age, and whether each criterion would fire in a table
   format — then return immediately. No kill, no Phase 2 respawn.
3. Useful for operator to inspect ratios on live iMac before trusting
   the new thresholds.
4. Behavior: `scan → print table → exit(0)`. Does not enter the daemon
   tick loop. Does not modify any process state.

### Commit

`feat(watchdog): add --debug-watchdog dry-run inspection flag (GIM-80)`

## Task 6 — Lint + typecheck green

**Owner:** PythonEngineer
**Files:** all touched files
**Depends on:** Tasks 1–5

### Gate

```bash
cd services/watchdog
uv run ruff check src/ tests/
uv run mypy src/
uv run pytest
```

All green before handoff to CodeReviewer.

### Commit

Fix-up commit if needed: `chore(watchdog): lint/type fixes (GIM-80)`

## Phase sequence

| Phase | Agent | What |
|-------|-------|------|
| 1.1 Formalize | CTO | This plan. Branch cut. ✅ |
| 1.2 Plan-first review | CodeReviewer | Review this plan for gaps. |
| 2 Implement | PythonEngineer | Tasks 0–6 on `feature/GIM-80-watchdog-idle-hang`. |
| 3.1 Mechanical review | CodeReviewer | `ruff + mypy + pytest` output in APPROVE. |
| 3.2 Adversarial review | OpusArchitectReviewer | Poke holes. |
| 4.1 Live smoke | QAEngineer | Synthetic emulator (spec §6.3b) on iMac. |
| 4.2 Merge | CTO | Squash-merge to develop after CI green. |

## Pre-implementation note

Working directory may contain uncommitted palace-mcp files from a prior
branch. Implementer must `git checkout -- services/palace-mcp/` and
`git clean -fd services/palace-mcp/` before starting to ensure a clean
GIM-80-only diff.

## Risks

| Risk | Mitigation |
|------|-----------|
| Log path discovery (Task 0) blocks Task 2 Criterion B | Task 2 can implement Criterion A first; Criterion B returns `None` (no-op) until path is confirmed. Two separate commits OK. |
| Existing tests break due to `parse_ps_output` signature change | Task 3 explicitly updates all callers. TDD: write failing tests first. |
| `--debug-watchdog` flag name conflicts with existing args | Checked `__main__.py` — no conflicts. |
