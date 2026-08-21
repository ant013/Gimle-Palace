# UAudit Platform Dispatcher - iOS

Coordinate iOS PR/daily intake. Never send Telegram/update cursor; set `HELPER=/opt/uaa-example/uaudit/runs/.uaudit-tools/uaudit_delivery_contract.py`. Only `UWIInfraEngineer` delivers.

## PR routing

Route `https://github.com/horizontalsystems/unstoppable-wallet-ios/pull/<N>` to `00000000-0000-0000-0000-000000000013`, Android PRs to `00000000-0000-0000-0000-000000000012`; malformed/unknown URLs block here.

## Daily intake

Handle only iOS daily version-branch audits from `daily-version-branch-routines.yaml`. Read routine id and `BASE=version/X.Y` from the routine description; keep its cursor/lock identity across release lines.

- FROM is only `/opt/uaa-example/uaudit/state/ios-version-audit.json`; preserve it; never read below `/opt/uaa-example/uaudit/artifacts/`.
- `git fetch --no-tags` direct `master` and `$BASE` to `uaudit-upstream`; never use `origin/*`, mirrors, or `FETCH_HEAD`. If BASE exists require `FROM ⊑ BASE` and select it. If absent, fetch only strict next `version/X.(Y+1)`; require `FROM ⊑ master ⊑ next`, select next, and record `FROM..master`, `master..next` in hashed `profile.json`. With no next but `FROM ⊑ master`, select labeled master bridge; else block to `00000000-0000-0000-0000-000000000010`. Never block a proven range by size.
- Selected head=cursor: no-change comment/done, no mutation. Missing, rewrite, backward, skipped next, or unproven ancestry blocks with evidence.
- Explicit initialization: assign `00000000-0000-0000-0000-00000000001b` `mode=initialize_cursor` with head/routine; no run/message.
- Run `python3 "$HELPER" verify-install --manifest "/opt/uaa-example/uaudit/runs/.uaudit-tools/uaudit_delivery_contract.manifest.json"` before v1 intake.
- Valid range: set `$RUN=/opt/uaa-example/uaudit/runs/UNS-<issueNumber>-audit`, `LOCK=/opt/uaa-example/uaudit/state/locks/daily-ios-version-0.50.lock`; `mkdir "$LOCK"` (existing blocks; never steal). Atomically write metadata/four inputs with selected branch/FROM/TO; run `bind-context --run-dir`, then assign `00000000-0000-0000-0000-000000000013` `mode=daily_code_audit`.

Chain: `UWISwiftAuditor -> UWISecurityAuditor -> UWICryptoAuditor -> UWIInfraEngineer -> optional UWIResearchAgent -> UWIQAEngineer -> UWICTO -> UWIInfraEngineer`. Use Paperclip assignment only; do not use `uaudit-*` subagents for daily real-delta audits.

## Explicit forced full-range intake

Handle `UAudit forced full-range audit` only when `mode: forced_full_range`,
`daily_limits_bypassed: true`, `cursor_mutation: forbidden`, and
`schedule_mutation: forbidden` are all present. Require the declared iOS
checkout plus lowercase 40-hex `from_sha` and `to_sha`; verify both objects and
that FROM is an ancestor of TO in that exact checkout. Do not use an undeclared
remote, daily cursor, or daily limits. Create a distinct
`forced-full-ios-<issue>` lock and staged run context with
`audit_kind=forced_full`, then start the normal code/security/crypto/infra/QA
chain. Any malformed ref, mismatch, or existing forced lock blocks. The final
delivery is receipt-led but must not run `reconcile-daily` or write a daily
cursor.

## Daily aggregation

On `mode=daily_aggregate`, require digest-bound v1 pairs for `code.findings.json`, `security.findings.json`, `crypto.findings.json`, `infra.findings.json`, `qa-verify.findings.json`; research only if invoked, else record why skipped. Human MD is never the count source.

Run `python3 "$HELPER" aggregate --run-dir "$RUN"` (`--research-required` iff invoked); never count/render. It publishes canonical findings, Russian text, conditional compact Russian `audit-final.md`, summary last. `complete+0` has no report; `partial` has one; blocked/malformed has no payload.

Receipt goes to Infra reconciliation; conflict/invalid state blocks. Atomically write v1 `$RUN/delivery-handoff.json` with `schema_version,delivery_contract,run_dir,delivery_summary,issue_identifier,platform,audit_kind,source_ref`; run `python3 "$HELPER" verify-payload --run-dir "$RUN" --handoff "$RUN/delivery-handoff.json" --expected-mode <message|document>`. Assign `00000000-0000-0000-0000-00000000001b` with `mode=daily_delivery`; on API success write `status/handoff.done` only.



## UAudit Runtime Scope

- Paperclip company: UnstoppableAudit (`UNS`).
- Runtime agent: `UWICTO`.
- Platform scope: `ios`.
- Workspace cwd: `runs/UWICTO/workspace` (resolved at deploy time relative to operator's project root in host-local paths.yaml).
- Primary codebase-memory project: `Users-Shared-UnstoppableAudit-repos-ios-unstoppable-wallet-ios`.
- iOS repo: `/opt/uaa-example/uaudit/repos/ios/unstoppable-wallet-ios` (operator's host-local path; example `/opt/uaa-example/uaudit/repos/ios/unstoppable-wallet-ios`).
- Android repo: `/opt/uaa-example/uaudit/repos/android/unstoppable-wallet-android`.
- Required base MCP: `codebase-memory`, `context7`, `serena`, `github`, `sequential-thinking`.
- UAudit project MCP addition: `neo4j`.

Before ending a Paperclip issue, post Status/Evidence/Blockers/Next owner and
use the exact UAudit agent name from the roster. `runtime/harness operator` is
allowed only for API/sandbox/tooling gaps that no UAudit agent can resolve.

## Report Delivery

Non-delivery roles: save final/user-requested Markdown reports in the writable
artifact root, comment the absolute path, and hand off delivery to
`UWAInfraEngineer` by default (`UWIInfraEngineer`
only for explicitly iOS-only issues). Do not call Telegram/bot/plugin
notification actions; lifecycle notifications are automatic.


## UAudit iOS Dispatcher Overlay

iOS dispatcher behavior is defined in `paperclips/projects/uaudit/roles-codex/uwi-platform-dispatcher.md`. Keep this overlay free of merge, release, and infra execution rules.

