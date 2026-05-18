# TDD Plan — Watchdog `in_review` recovery (GIM-NN)

**Spec:** `docs/superpowers/specs/2026-05-06-GIM-NN-watchdog-in-review-recovery.md`
**Branch:** `feature/GIM-NN-watchdog-in-review-recovery` (cut from `5155ef7` origin/develop)
**Estimated diff:** ~50 LOC src + ~120 LOC tests + ~30 LOC docs

---

## Task list (8 tasks, 3 atomic commits)

### T1 — Detector: extend Protocol + fake mock to use `list_active_issues`

**Test (write first, must fail):**
- `tests/test_detection.py::test_scan_died_mid_work_includes_in_review_issues`
  - Build `_FakeClient` with one `Issue(status="in_review", assignee_agent_id="cr-1", execution_run_id=None, updated_at=10:00)` at frozen time `10:05`.
  - Call `scan_died_mid_work(cfg, client, state, config)`.
  - Assert returned `actions == [Action(kind="wake", issue=...)]`.

**Impl:**
- `services/watchdog/src/gimle_watchdog/detection.py:43-44`: change `_IssueLister` Protocol method from `list_in_progress_issues` to `list_active_issues`.
- `services/watchdog/src/gimle_watchdog/detection.py:220`: change call site from `list_in_progress_issues` to `list_active_issues`.
- `services/watchdog/tests/test_detection.py:289`: rename `_FakeClient.list_in_progress_issues` to `list_active_issues`.

**Verify:**
- `uv run pytest tests/test_detection.py -v` — all existing in_progress tests still pass + new in_review test passes.
- `uv run ruff check src/ tests/`
- `uv run mypy --strict src/`

**Commit:** `feat(watchdog): scan in_review issues for lost-handoff recovery (GIM-NN)`

---

### T2 — Action: preserve status across release+repatch fallback

**Tests (write first, must fail):**
- `tests/test_actions.py::test_trigger_respawn_release_path_preserves_in_review_status`
  - Build `Issue(status="in_review", ...)`, primary `get_issue` returns `run_id=None` (no spawn), then after release+repatch returns `run_id="run-new"`.
  - Assert `client.patch_issue.await_args_list[1].args == ("issue-1", {"assigneeAgentId": "agent-1", "status": "in_review"})`.
- `tests/test_actions.py::test_trigger_respawn_primary_patch_omits_status_field`
  - Primary path succeeds (first poll returns spawned `run_id`).
  - Assert `client.patch_issue.await_args_list == [call("issue-1", {"assigneeAgentId": "agent-1"})]` — no `status` key.
- `tests/test_actions.py::test_trigger_respawn_release_path_skips_status_when_empty`
  - Build `Issue(status="", ...)`. Fallback PATCH must be `{"assigneeAgentId": "agent-1"}` only — no `status` key (avoid sending empty string to server).
- **Update** `test_trigger_respawn_patch_fails_release_patch_succeeds`: change expected fallback PATCH body to include `"status": "in_progress"` (the existing `_issue()` helper has `status="in_progress"`).

**Impl:**
- `services/watchdog/src/gimle_watchdog/actions.py:58-77`: in `trigger_respawn` fallback path, build PATCH body `{"assigneeAgentId": assignee_id}` then conditionally add `"status": issue.status` if `issue.status` is truthy.
- Add log breadcrumb `respawn_fallback_release_patch issue=%s preserving_status=%s` for observability.

**Verify:**
- `uv run pytest tests/test_actions.py -v`
- `uv run ruff check src/ tests/`
- `uv run mypy --strict src/`

**Commit:** `fix(watchdog): preserve issue.status across release+repatch fallback (GIM-NN)`

---

### T3 — Integration test (daemon-level, fakes only — no real paperclip)

**Test (write first):**
- `tests/test_daemon.py::test_tick_recovers_in_review_handoff_loss`
  - Fake `PaperclipClient`:
    - `list_active_issues` returns `[Issue(status="in_review", assignee_agent_id="cr-1", execution_run_id=None, updated_at=now-5min)]`.
    - `get_issue` (called by `_wait_for_respawn`) initially returns same issue with `run_id=None`, after fallback PATCH returns `run_id="run-new"`.
    - `patch_issue` and `post_release` are AsyncMocks.
  - Run one `_tick`.
  - Assert `client.post_release.await_args_list == [call("issue-1")]`.
  - Assert second `patch_issue` call body contains `"status": "in_review"`.
  - Assert state has wake recorded for issue.

**Impl:**
- No source change — this test exercises T1+T2 wired together via `_tick`.

**Verify:**
- `uv run pytest tests/test_daemon.py -v`

**Commit:** *(combined with T4 docs commit below)*

---

### T4 — Docs: update README + add inline comment in `trigger_respawn`

**Edit:**
- `services/watchdog/README.md`: under "What it does", note that recovery now covers `in_review` (not only `in_progress`). Add one sentence under "Known fragility" referencing GIM-216 incident.
- Inline comment on `actions.py` fallback PATCH: `# release resets status to "todo"; restore original status in the same PATCH (GIM-NN, GIM-216 incident)`.

**Commit:** `docs(watchdog): document in_review recovery + status-preservation rationale (GIM-NN)`

(T3 + T4 ship in this single commit since T3 has no source changes.)

---

### T5 — Coverage gate

**Run:**
- `uv run pytest --cov=gimle_watchdog --cov-report=term-missing --cov-fail-under=90`

**Acceptance:**
- Total coverage ≥ 90% (current is 90.5% per GIM-80).
- New code (detection change + actions change) has 100% line coverage.

**Action if fails:** add tests for any uncovered branch in T2 fallback logic (likely the empty-status branch).

---

### T6 — Push + open PR

**Branch:**
- `feature/GIM-NN-watchdog-in-review-recovery` (already cut)
- Three commits: T1, T2, T3+T4

**Push:**
- `git push -u origin feature/GIM-NN-watchdog-in-review-recovery`

**PR:**
- Title: `feat(watchdog): recover in_review handoffs + preserve status (GIM-NN)`
- Body sections: Summary / Why / Changes / Test Plan / **QA Evidence** (with deferred-to-iMac note + the live smoke procedure from spec §5.6).

---

### T7 — Live smoke (deferred to QA on iMac, post-merge)

Spec §5.6:
1. Disposable issue assigned to known idle agent, `status=in_review`, updatedAt 5 min in past, executionRunId=null.
2. Wait for next tick (~2 min).
3. Verify `wake_result issue=<id> via=release_patch success=True` in `~/.paperclip/watchdog.log`.
4. Verify issue `status` is still `in_review` (not `todo`) post-recovery.
5. Verify assignee got new heartbeat run.

---

### T8 — iMac deploy (operator, post-merge)

```bash
ssh anton@imac-ssh.ant013.work
cd /Users/Shared/Ios/Gimle-Palace
git fetch origin && git checkout origin/develop -B develop
cd services/watchdog && uv sync --all-extras
launchctl kickstart -k gui/$(id -u)/work.ant013.gimle-watchdog
sleep 30
tail -10 ~/.paperclip/watchdog.log    # expect fresh tick_start, no err
```

No yaml migration needed.

---

## Coverage matrix (acceptance ↔ task)

| Acceptance criterion (spec §6) | Task |
|---|---|
| 1. `scan_died_mid_work` covers `in_review` | T1 |
| 2. Fallback PATCH includes `status` from `Issue` | T2 |
| 3. Primary PATCH excludes `status` field | T2 |
| 4. Post-recovery status equals original | T3 (integration) |
| 5. Existing `in_progress` recovery tests still pass | T1 (regression) |
| 6. No new config knobs | T1, T2 (no `Thresholds` change) |
| 7. Live smoke evidence | T7 (deferred) |

## Risk register (spec §9 → mitigation in plan)

- **R1 broader scope FP**: monitored via wake-result distribution log. No code-side mitigation in v1.
- **R2 status-preservation bug**: covered by 4 tests in T2 (success path, primary-only, empty-status, regression).
- **R3 doesn't fix paperclip wake-event root cause**: explicit followup E (out of scope).
