---
status: proposed
slice: GIM-NN-watchdog-in-review-recovery
predecessor_sha: 5155ef7   # origin/develop tip at branch cut
related: GIM-79, GIM-80, GIM-181, GIM-183 (watchdog history); GIM-216 (live evidence)
paperclip_issue: GIM-NN
---

# Watchdog: recover lost handoffs to `in_review` assignees

## 1. Context

**Live incident, 2026-05-06 GIM-216:** PythonEngineer completed Phase 2, did
atomic `PATCH(assigneeAgentId=CR + status=in_review) + POST comment` handoff,
then SIGTERM'd on `claude_transient_upstream`. PATCH succeeded server-side
(assignee=CR, status=in_review). But CodeReviewer **never woke** — `lastHeartbeatAt`
stayed at 12:22:44 UTC for 40+ min after handoff at 12:42:58 UTC.

Manual recovery that works: `POST /api/issues/{id}/release` + `PATCH assigneeAgentId=<X>`
(empirically verified during incident — CR went `idle → running` within seconds).

Existing `actions.trigger_respawn` already implements this exact recipe (PATCH primary,
release+PATCH fallback). It works for `in_progress` issues — visible in `wake_result via=release_patch success=True` watchdog log on 2026-05-04T14:32:06Z.

**Why it didn't help GIM-216:** `detection.scan_died_mid_work` calls
`client.list_in_progress_issues(company.id)` (paperclip.py:157) which queries
`?status=in_progress` only. GIM-216 was in `in_review`. Detector never saw it.

## 2. Scope

### IN

- Switch `scan_died_mid_work` to use `list_active_issues` (already exists, queries `?status=todo,in_progress,in_review`) instead of `list_in_progress_issues`.
- Make `trigger_respawn` preserve `Issue.status` when fallback path executes — `POST /release` resets status to `todo` server-side; `PATCH` after release must restore the original status alongside `assigneeAgentId`.
- Update existing tests for `scan_died_mid_work` and `trigger_respawn` to cover the new behavior.
- Add focused tests:
  - `scan_died_mid_work` returns wake-action for `in_review` issue meeting all other criteria.
  - `trigger_respawn` fallback path PATCHes both `assigneeAgentId` and `status` (the saved original).
  - Status preservation does not affect primary PATCH path (where `release` was not called).
- Update `services/watchdog/README.md` to mention the broader scope.

### OUT (explicit followups, separate slices)

- **F1**: Per-status thresholds. v1 uses single `died_min: 3` for all statuses. If 3 min proves too aggressive for `in_review` (CR may legitimately take longer to spawn), introduce `died_in_review_min: 10` later — needs live data to tune.
- **F2**: New detector for the GIM-181 `comment_only_handoff` finding type — currently alert-only, could become auto-repair. Out of scope here; keeps this slice surgical.
- **F3**: Detect the inverse pattern: `in_review` issue assigned to **implementer**-class role (already covered by `ReviewOwnedByImplementer` finding, alert-only). Not extending that here.
- **F4**: `todo`-status recovery with stricter conditions (e.g., never-worked tasks may legitimately sit). v1 includes `todo` in the scan because `list_active_issues` returns it, but `died_min: 3` + `assigneeAgentId is not None` + `executionRunId is None` filter should be safe. Monitor for false positives.

## 3. Decisions

**R1 — Bug fix, not a new detector.** `trigger_respawn` already does the
right thing (PATCH primary → release+PATCH fallback). The gap is **detector
coverage**, not action capability. Adding a new detector would duplicate
logic and create maintenance debt. Single-line scope-extension is the right
fix.

**R2 — Status preservation done inside `trigger_respawn`, not detector.** The
detector hands off `Issue` (which carries `status`); `trigger_respawn` is the
only place that knows it called `release` and therefore needs to restore.
Pushing it into the detector would force every caller to reason about
release side-effects.

**R3 — Restore status with same PATCH that re-triggers wake.** Two options
considered:
  (a) `PATCH assigneeAgentId` then separate `PATCH status` — two roundtrips,
      two wake-events on the server, race-prone.
  (b) `PATCH {assigneeAgentId, status}` in one call — one roundtrip, atomic.
Picked (b). Matches the shared-fragment handoff discipline ("ONE API call
PATCHing all fields together").

**R4 — Primary-path PATCH stays single-field.** When `release` was not
called (primary path succeeds), status was not modified. Adding `status` to
the primary PATCH would be a no-op that pollutes the diff. Keep primary
minimal.

**R5 — No new config knobs.** Reuses `died_min` (already defaults 3, already
deployed). Avoids another iMac yaml-migration incident (cf. GIM-80
deprecated-key bug, 2026-05-04).

**R6 — Existing cooldown applies as-is.** `per_issue_seconds: 300` (5 min)
prevents respawn-storms. `per_agent_cap: 3` per `per_agent_window_seconds: 900`
caps total wake attempts. Both adequate for the broader scope.

## 4. Implementation

### 4.1 `detection.py`

Single line change in `scan_died_mid_work` (line 220):

```python
- issues = await client.list_in_progress_issues(company.id)
+ issues = await client.list_active_issues(company.id)
```

The `_IssueLister` Protocol (line 43-44) needs to advertise `list_active_issues`
instead of (or in addition to) `list_in_progress_issues`. Pick: replace the
single method on the protocol — mocks already exist for both.

### 4.2 `actions.py`

`trigger_respawn` accepts `Issue` directly (already does). Use `issue.status`
in the fallback PATCH:

```python
async def trigger_respawn(client, issue, assignee_id) -> RespawnResult:
    # Primary
    await client.patch_issue(issue.id, {"assigneeAgentId": assignee_id})
    run_id = await _wait_for_respawn(client, issue.id)
    if run_id is not None:
        return RespawnResult(via="patch", success=True, run_id=run_id)

    # Fallback — release resets status to "todo"; restore in same PATCH
    log.info("respawn_fallback_release_patch issue=%s preserving_status=%s", issue.id, issue.status)
    try:
        await client.post_release(issue.id)
    except PaperclipError as e:
        log.warning("release_failed issue=%s error=%s", issue.id, e)
    await client.patch_issue(
        issue.id,
        {"assigneeAgentId": assignee_id, "status": issue.status},
    )
    run_id = await _wait_for_respawn(client, issue.id)
    ...
```

`Issue` already carries `status` (paperclip.py:34) so no signature change.

### 4.3 `paperclip.py`

No change. `list_active_issues` already exists (line 164-173).

### 4.4 `daemon.py`

No change. Already passes `action.issue` to `trigger_respawn`.

## 5. Test plan

### 5.1 Unit — `tests/test_detection.py`

- **NEW** `test_scan_died_mid_work_includes_in_review_issues`: feed lister
  with one `in_review` issue meeting all death criteria → expect one
  `Action(kind="wake")`.
- **UPDATE** existing `test_scan_died_mid_work_*` tests that mock
  `list_in_progress_issues` → switch mock to `list_active_issues`.

### 5.2 Unit — `tests/test_actions.py`

- **UPDATE** `test_trigger_respawn_patch_fails_release_patch_succeeds`:
  assert second PATCH carries **both** `assigneeAgentId` AND `status` (the
  status from the input `Issue` fixture).
- **NEW** `test_trigger_respawn_release_path_preserves_in_review_status`:
  Issue with `status="in_review"`, primary PATCH fails to wake → fallback
  release+PATCH must include `"status": "in_review"` in the fallback PATCH
  body. Verify via `assert_awaited_with`.
- **NEW** `test_trigger_respawn_primary_patch_omits_status_field`:
  primary PATCH (no release) must be `{"assigneeAgentId": ...}` only — no
  `status` key. Avoids accidental status writes on the happy path.

### 5.3 Integration — `tests/test_integration.py` or `test_daemon.py`

- **NEW** `test_daemon_recovers_in_review_handoff_loss`: end-to-end with
  fake paperclip client returning one `in_review` issue with stale
  updatedAt + null executionRunId. Tick should call `trigger_respawn`,
  fallback path runs (mock primary as no-spawn), assert final state has
  status=in_review preserved.

### 5.4 Coverage gate

Current watchdog coverage is **90.5%** (per GIM-80 commit message). Must
not regress. Run `uv run pytest --cov=gimle_watchdog --cov-fail-under=90`.

### 5.5 Lint / type

`uv run ruff check src/ tests/ && uv run mypy --strict src/`. Both must
pass. No new env vars to validate.

### 5.6 Live smoke (deferred to QA / iMac)

After deploy:
1. Disposable issue assigned to a known idle agent, `status=in_review`,
   updatedAt set 5 min in the past, executionRunId=null.
2. Wait for next watchdog tick (~2 min).
3. Verify `~/.paperclip/watchdog.log` shows
   `wake_result issue=<id> via=release_patch success=True`.
4. Verify issue status is still `in_review` after the wake (NOT `todo`).
5. Verify assignee got a new heartbeat run.

## 6. Acceptance criteria

1. `scan_died_mid_work` returns wake-actions for `in_review` issues meeting
   the (assignee + null-runId + stale-updatedAt) gates.
2. `trigger_respawn` fallback PATCH includes `status` field populated from
   the input `Issue.status`.
3. `trigger_respawn` primary PATCH does NOT include `status` field
   (assignee-only).
4. After `release+repatch`, the issue's `status` is the original status
   (verified post-PATCH GET in integration test).
5. Existing tests for `in_progress` recovery still pass.
6. No new config knobs in `~/.paperclip/watchdog-config.yaml`.
7. Live smoke evidence shows recovery for `in_review` issue with status
   preserved.

## 7. Edge cases

- **Status was already `todo`**: `release` resets it to `todo`, fallback
  PATCH writes `status=todo` — net no-op. Safe.
- **`Issue.status` is empty string** (paperclip API edge): `_issue_from_json`
  defaults to `""`. Fallback PATCH would send `status=""`, which paperclip
  may reject. Mitigation: in fallback, if `issue.status == ""`, omit the
  status field from PATCH (let server-side keep current state). Test for
  this.
- **Issue already in `done`/`cancelled`**: `list_active_issues` doesn't
  return these. Detector won't see them. No regression.
- **Concurrent operator action**: operator changes status between detector
  decision and our PATCH. Worst case our PATCH overwrites operator's
  change. Mitigation: small window (<10s), per_issue_cooldown 300s prevents
  oscillation. Accept as v1 risk; document.

## 8. Out-of-scope cleanups

None. Spec deliberately surgical.

## 9. Risks

- **R1**: Broader detector scope = higher false-positive risk for `in_review`
  issues that legitimately sit (CR taking long to spawn). Mitigated by
  existing 5-min per-issue cooldown + 3-per-15-min per-agent cap.
  Monitoring: track `wake_result via=*` counts post-deploy; alert if
  `release_patch` becomes >50% of wakes (signals systemic issue, not
  one-off recovery).
- **R2**: Status preservation logic adds branching; small risk of new bug
  if fallback path called with malformed Issue. Tests cover empty-status
  case explicitly.
- **R3**: This fix addresses the observed symptom (lost wake) but NOT the
  underlying paperclip wake-event-mechanism behavior that lost it. Real
  root cause likely `createdByRunId` of the failed PE-run suppressing
  subsequent events. That's a paperclipai upstream fix (out of scope).
  This slice is defensive recovery, not prevention.

## 10. Deploy

Standard:
1. Merge PR to develop.
2. SSH iMac.
3. `cd /Users/Shared/Ios/Gimle-Palace && git fetch && git checkout origin/develop`
4. `cd services/watchdog && uv sync --all-extras`
5. `launchctl kickstart -k gui/$(id -u)/work.ant013.gimle-watchdog`
6. Verify within 3 min: fresh `tick_start` in `~/.paperclip/watchdog.log`,
   no new ConfigError in `~/.paperclip/watchdog.err`.

No yaml migration needed.
