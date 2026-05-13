# Runbook: Watchdog Handoff Alert Detection (GIM-181)

Watchdog's semantic handoff detector identifies issues where an agent failed to
properly hand off work. It runs as Phase 3 inside every tick, after the
respawn pass. All findings are **alert-only** — watchdog posts a comment and
logs a JSONL event; it performs no automatic repair.

## Enabling

In `~/.paperclip/watchdog-config.yaml`, add:

```yaml
handoff:
  handoff_alert_enabled: true          # required — disabled by default
  handoff_alert_cooldown_min: 30       # min between re-alerts for the same issue (default 30)
  handoff_comment_lookback_min: 5      # how old the @-mention must be (default 5)
  handoff_wrong_assignee_min: 3        # min before wrong-assignee alert (default 3)
  handoff_review_owner_min: 5          # min before review-owned-by-implementer alert (default 5)
  handoff_comments_per_issue: 5        # comments fetched per issue (default 5)
  handoff_max_issues_per_tick: 30      # issues scanned per company per tick (default 30)
```

Restart the daemon after editing:

```bash
gimle-watchdog restart    # or: launchctl unload/load on macOS
```

## Finding types

| Type | Condition |
|------|-----------|
| `comment_only_handoff` | Current assignee @-mentioned another agent ≥ `handoff_comment_lookback_min` min ago, but `assigneeAgentId` was never updated |
| `wrong_assignee` | `assigneeAgentId` is not a known hired agent UUID and issue is not closed |
| `review_owned_by_implementer` | Issue in `in_review` but assigned to an implementer-class agent (not a reviewer) |

## Inspecting alerts

```bash
# Last 20 handoff alert events
cat ~/.paperclip/watchdog.log | jq -c 'select(.event=="handoff_alert_posted")' | tail -20

# Pass summaries
cat ~/.paperclip/watchdog.log | jq -c 'select(.event=="handoff_pass_complete")' | tail -10

# Failed alert posts
cat ~/.paperclip/watchdog.log | jq -c 'select(.event=="handoff_alert_failed")'
```

## Silencing an alert

Watchdog re-alerts only when the issue snapshot changes (e.g., new @-mention, different
assignee) AND the cooldown has elapsed. To stop repeated alerts:

- **Fix the underlying issue**: reassign to correct agent or update `assigneeAgentId`.
- **Increase cooldown** temporarily in `watchdog-config.yaml`.
- **Disable handoff detection** entirely (`handoff_alert_enabled: false`).

Watchdog automatically clears its internal alert entry when the issue no longer
triggers a finding (i.e., the inconsistency was resolved).

## Cooldown and snapshot semantics

State is keyed on `{issue_id}:{finding_type}`. For each key, watchdog stores:

- `alerted_at` — UTC ISO timestamp of last alert post
- `snapshot` — the issue fields relevant to the finding at alert time

An alert is suppressed when both conditions hold:
1. `snapshot` is unchanged (same assignee, status, and mention target)
2. OR cooldown has not elapsed since `alerted_at`

On finding resolution (no finding for issue in this tick), all three keys for
that `issue_id` are cleared from state.

## Troubleshooting

**No alerts firing despite obvious inconsistencies.**

1. Verify `handoff_alert_enabled: true` in the live config: `gimle-watchdog status`.
2. Check `handoff_max_issues_per_tick` — issues beyond the limit are skipped.
3. Check logs for `handoff_pass_company_failed` — API errors abort the company pass.
4. Check `handoff_comment_lookback_min` — @-mention may be too recent.

**Alerts fire for a closed issue.**

The detector skips `done`, `cancelled`, and other non-active statuses. If an
issue appears closed but still triggers an alert, verify the API response status
via `gimle-watchdog tail` showing `handoff_pass_complete`.

**`handoff_alert_failed` in logs.**

Comment posting to paperclip failed (network, 5xx). Watchdog logs the error but
does **not** record the alert in state, so it will retry next tick if the finding
still exists. Check `error` field in the JSONL event for the cause.

## GIM-255 — безопасное повторное включение после hardening

Этот раздел добавлен после GIM-255 и описывает, как безопасно вернуть handoff detectors в rollout без повторения spam-инцидента на stale issues.

### Safe Re-enable Checklist

1. Начать не с production, а с local/staging smoke.
2. Включать ровно один detector flag за раз:
   - `handoff_cross_team_enabled`
   - `handoff_ownerless_enabled`
   - `handoff_infra_block_enabled`
   - `handoff_stale_bundle_enabled`
3. Оставлять `handoff_auto_repair_enabled: false`.
4. После каждого включения перезапускать watchdog и сразу проверять логи.
5. Подтверждать, что `tier_alert_posted` появляется только для заранее подготовленного fresh control case.
6. Подтверждать, что на 32 issues из incident cohort GIM-255 не появилось ни одного нового handoff alert comment и нет unexpected `tier_alert_posted` / `handoff_alert_posted`.
7. Только после чистого smoke для одного flag включать следующий.
8. В production повторять ту же последовательность: один flag, restart, log check, known-issue check, потом следующий flag.

### Что проверять в логах

- Для tier detectors success path логируется как `tier_alert_posted issue=<id> ftype=<type> comment=<comment-id>`.
- Для legacy handoff detectors success path логируется как `handoff_alert_posted`.
- Если `tier_alert_posted` или `handoff_alert_posted` появляются без подготовленного fresh control case, rollout нужно остановить.
- Если на known-spammed issues появились новые alert comments или новые state entries, rollout нужно остановить.

### Smoke Procedure

1. Подготовить один fresh control case для текущего detector flag.
2. Включить один flag в конфиге watchdog.
3. Перезапустить watchdog.
4. Проверить, что fresh control case дал ровно один bounded alert.
5. Проверить, что stale issues из incident cohort GIM-255 не дали alert comments и не получили повторный wake.
6. Сохранить evidence: включённый flag, relevant log lines, результат проверки incident cohort.

### Production Rollout

1. `handoff_alert_enabled` и tier flags включать по одному, а не пачкой.
2. После каждого шага фиксировать:
   - какой flag включён;
   - время restart watchdog;
   - наличие или отсутствие `tier_alert_posted`;
   - отсутствие новых alerts на 32 issues из GIM-255 incident cohort.
3. Если хотя бы один шаг даёт неожиданный alert volume, rollout останавливается до нового fix.

### Rollback

1. Вернуть все `handoff_*_enabled: false`.
2. Убедиться, что `handoff_auto_repair_enabled` остаётся `false`.
3. Перезапустить watchdog.
4. Проверить, что новые `tier_alert_posted` / `handoff_alert_posted` больше не появляются.

### Policy Note

`handoff_auto_repair_enabled` не включается в production в рамках GIM-255. Любое включение auto-repair требует отдельного решения Board и отдельного rollout slice с новой проверкой рисков.
