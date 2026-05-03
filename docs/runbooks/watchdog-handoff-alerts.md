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
