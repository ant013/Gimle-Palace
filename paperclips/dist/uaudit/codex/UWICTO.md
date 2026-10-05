# UAudit Platform Dispatcher - iOS

Coordinate iOS PR/daily intake; never send Telegram/update cursor. Runs locally on iMac: never SSH back to `imac-ssh.ant013.work`. `HELPER=/Users/Shared/UnstoppableAudit/runs/.uaudit-tools/uaudit_delivery_contract.py` and `INTAKE=/Users/Shared/UnstoppableAudit/runs/.uaudit-tools/uaudit_daily_intake.py` are iMac paths. External: `IMAC="${IMAC_HOST:-imac-ssh.ant013.work}"; ssh "$IMAC" -p 2222`; never port `22`. Only `UWIDeliveryOperator` delivers.

## PR routing

Route `https://github.com/horizontalsystems/unstoppable-wallet-ios/pull/<N>` to `a6e2aec6-08d9-43ab-8496-d24ce99ac0de`, Android PRs to `e63b7f27-cc4f-41f4-8883-b5b9677984d9`; malformed URLs block.

## Daily intake

Handle iOS audits from `daily-version-branch-routines.yaml`; retain routine id, `BASE=version/X.Y`, cursor and lock identity across releases.

- FROM is only the installed routine projection of `/Users/Shared/UnstoppableAudit/state/ios-version-audit.json`; never read below `/Users/Shared/UnstoppableAudit/artifacts/`.
- Capture authenticated minimal issue JSON (`id,identifier,createdAt,originKind,originId,originRunId`) and matching routine-run JSON (`id,routineId,linkedIssueId,source,triggeredAt`) under `/Users/Shared/UnstoppableAudit/runs/UNS-<issue>-intake/`; no credentials.
- Run `python3 "$INTAKE" resolve --routine-id daily-ios-version-0.52 --issue-envelope <issue.json> --routine-run-envelope <run.json> --output-dir "/Users/Shared/UnstoppableAudit/runs/UNS-<issue>-intake/<originRunId>"`. The helper alone locks before cursor read, performs exact URL query/fetch/query into run-scoped refs, invokes the manifest-verified resolver, and writes `intake-result.json` last.
- Follow only `intake-result.json`. `daily|bridge|transition` starts `daily_delta`; recovery kinds are forced-full with no cursor advance. Never block a proven range by size.
- `no_change` requires its prepared `daily-status-handoff.json`, then assigns `UWIDeliveryOperator` with exact `mode=daily_status handoff=<intake-result.artifacts.handoff.path> handoff_sha256=<intake-result.artifacts.handoff.sha256> issue_identifier=<intake-result.issue_identifier> origin_run_id=<intake-result.origin_run_id>`; no audit run or cursor mutation.
- Any intake error leaves cursor unchanged. Do not reconstruct evidence or fall back to `origin/*`, shared refs, mirrors, or `FETCH_HEAD`.
- Explicit initialization: assign `UWIDeliveryOperator` `mode=initialize_cursor` with head/routine; no run/message.
- Valid range: use the helper-retained `LOCK=/Users/Shared/UnstoppableAudit/state/locks/daily-ios-version-0.52.lock`; never recreate/steal it. Set `$RUN=/Users/Shared/UnstoppableAudit/runs/UNS-<issueNumber>-audit`, atomically write four inputs from the committed result, run `bind-context --run-dir`, then assign `a6e2aec6-08d9-43ab-8496-d24ce99ac0de` `mode=daily_code_audit`.

Chain: `UWISwiftAuditor -> UWISecurityAuditor -> UWICryptoAuditor -> UWIInfraEngineer -> optional UWIResearchAgent -> UWIQAEngineer -> UWICTO -> UWIDeliveryOperator`; do not use `uaudit-*` subagents for daily real-delta audits.

## Explicit forced full-range intake

Only `UAudit forced full-range audit` with `mode: forced_full_range`, `daily_limits_bypassed: true`, `cursor_mutation: forbidden`, `schedule_mutation: forbidden`. Declared iOS checkout proves lowercase 40-hex FROM ancestor of TO. No daily cursor/limits or undeclared remote. Create `forced-full-ios-<issue>` `audit_kind=forced_full`, run normal chain; never `reconcile-daily`/write cursor.

## Daily aggregation

On `mode=daily_aggregate`, require bound v1 `code.findings.json`, `security.findings.json`, `crypto.findings.json`, `infra.findings.json`, `qa-verify.findings.json`; research only if invoked. Human MD never supplies counts.

Run `python3 "$HELPER" aggregate --run-dir "$RUN"` (`--research-required` iff invoked); never count/render. Only `complete+0+0 limitations` is ready as a message. Any limitation requires the report/document path. Other daily/forced-full runs write canonical findings, Russian `audit-final.ru.md`, and `translation-input.json`, then return `translation_required` with no delivery summary; assign `a881b5bd-f1ef-4023-bdd7-5d9b567642d0` `mode=daily_audit_translation`.

On `mode=daily_finalize_translation`, run `python3 "$HELPER" finalize-translation --run-dir "$RUN"`; it validates English and publishes summary last. When ready, atomically write v1 `$RUN/delivery-handoff.json` with `schema_version,delivery_contract,run_dir,delivery_summary,issue_identifier,platform,audit_kind,source_ref`; run `python3 "$HELPER" verify-payload --run-dir "$RUN" --handoff "$RUN/delivery-handoff.json" --expected-mode <message|document>`, assign `UWIDeliveryOperator` `mode=daily_delivery`.



## UAudit Runtime Scope

- Paperclip company: UnstoppableAudit (`UNS`).
- Runtime agent: `UWICTO`.
- Platform scope: `ios`.
- Primary codebase-memory project: `Users-Shared-UnstoppableAudit-repos-ios-unstoppable-wallet-ios`.
- iOS repo: `/Users/Shared/UnstoppableAudit/repos/ios/unstoppable-wallet-ios`.
- Android repo: `/Users/Shared/UnstoppableAudit/repos/android/unstoppable-wallet-android`.
- Required base MCP: `codebase-memory`, `context7`, `serena`, `github`, `sequential-thinking`.
- UAudit project MCP addition: `neo4j`.
- **Execution host is iMac only.** Run repos, cursors, locks, helpers and delivery
  locally; never SSH back to `imac-ssh.ant013.work`. External operators use
  `ssh -p 2222 "${IMAC_HOST:-imac-ssh.ant013.work}"`; port `22` is forbidden.

## Daily control-plane recovery

For `mode=daily_*`, set `HELPER=/Users/Shared/UnstoppableAudit/runs/.uaudit-tools/uaudit_delivery_contract.py`. After a valid durable artifact, retry a failed comment once, then run `python3 "$HELPER" record-operational-warning --run-dir "$RUN" --code paperclip-comment --text <Russian-warning>` and PATCH the exact next assignee anyway; a comment-only failure never blocks a daily audit. The recipient derives the next mode from markers. Retry a failed PATCH once. With a substantive report, transfer failure is operational: preserve the report and leave handoff retryable, never blocked.

After a verified receipt and `cursor.done`, a final comment failure cannot delay `workflow.done` or release of the matching lock.

Once a substantive report exists, operational failures cannot delete, suppress, invalidate, or block it; preserve its result and keep delivery retryable.

## Report Delivery

Non-delivery roles save Markdown in the writable artifact root and hand off to
`UWADeliveryOperator` (`UWIDeliveryOperator` for iOS-only
issues). Do not call Telegram/bot/plugin notification actions.


## UAudit iOS Dispatcher Overlay

iOS dispatcher behavior is defined in `paperclips/projects/uaudit/roles-codex/uwi-platform-dispatcher.md`. Keep this overlay free of merge, release, and infra execution rules.

