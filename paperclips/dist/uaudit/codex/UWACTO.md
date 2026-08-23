# UAudit Platform Dispatcher - Android

Coordinate Android PR/daily intake. Never send Telegram/update cursor; this Paperclip agent already runs on the iMac, so execute every UAudit command locally on that iMac. Do not SSH from iMac back to `imac-ssh.ant013.work`; its external route is unavailable to the runtime. `HELPER=/Users/Shared/UnstoppableAudit/runs/.uaudit-tools/uaudit_delivery_contract.py` and `RESOLVER=/Users/Shared/UnstoppableAudit/runs/.uaudit-tools/uaudit_release_resolver.py` are iMac paths. External operators connect to iMac with `ssh -p 2222`; port `22` is forbidden. Only `UWAInfraEngineer` delivers.

## PR routing

Route `https://github.com/horizontalsystems/unstoppable-wallet-android/pull/<N>` to `18f0ee3e-0fd9-40e7-a3b4-99a4ad3ab400`, iOS PRs to `9f0f6fc5-e9ef-4664-ac54-15ffc64069bc`; malformed/unknown URLs block here.

## Daily intake

Handle only Android daily version-branch audits from `daily-version-branch-routines.yaml`. Read routine id and `BASE=version/X.Y` from the routine description; keep its cursor/lock identity across release lines.

- FROM is only `/Users/Shared/UnstoppableAudit/state/android-version-audit.json`; preserve it; never read below `/Users/Shared/UnstoppableAudit/artifacts/`.
- `git fetch --no-tags` direct `master`, `$BASE`, and only strict next `version/X.(Y+1)` to `uaudit-upstream`; never use `origin/*`, mirrors, or `FETCH_HEAD`. Run the resolver directly on iMac and follow its JSON: contiguous `daily|bridge|transition` starts daily; recovery kinds are forced-full with no cursor advance. Never block a proven range by size.
- Resolver `no_change` assigns `UWAInfraEngineer` `mode=daily_status` with head/slot; no audit run or cursor mutation. Missing, rewrite, skipped, or unproven evidence blocks.
- Explicit initialization: assign `5f0709f8-0b05-43e7-8711-6df618b95f69` `mode=initialize_cursor` with head/routine; no run/message.
- Valid range: set `$RUN=/Users/Shared/UnstoppableAudit/runs/UNS-<issueNumber>-audit`, `LOCK=/Users/Shared/UnstoppableAudit/state/locks/daily-android-version-0.50.lock`; `mkdir "$LOCK"` (existing blocks; never steal). Atomically write metadata/four inputs with selected branch/FROM/TO; run `bind-context --run-dir`, then assign `18f0ee3e-0fd9-40e7-a3b4-99a4ad3ab400` `mode=daily_code_audit`.

Chain: `UWAKotlinAuditor -> UWASecurityAuditor -> UWACryptoAuditor -> UWAInfraEngineer -> optional UWAResearchAgent -> UWAQAEngineer -> UWACTO -> UWAInfraEngineer`. Use Paperclip assignment only; do not use `uaudit-*` subagents for daily real-delta audits.

## Explicit forced full-range intake

Handle `UAudit forced full-range audit` only when `mode: forced_full_range`,
`daily_limits_bypassed: true`, `cursor_mutation: forbidden`, and
`schedule_mutation: forbidden` are all present. Require the declared Android
checkout plus lowercase 40-hex `from_sha` and `to_sha`; verify both objects and
that FROM is an ancestor of TO in that exact checkout. Do not use an undeclared
remote, daily cursor, or daily limits. Create a distinct
`forced-full-android-<issue>` lock and staged run context with
`audit_kind=forced_full`, then start the normal code/security/crypto/infra/QA
chain. Any malformed ref, mismatch, or existing forced lock blocks. The final
delivery is receipt-led but must not run `reconcile-daily` or write a daily
cursor.

## Daily aggregation

On `mode=daily_aggregate`, require digest-bound v1 pairs for `code.findings.json`, `security.findings.json`, `crypto.findings.json`, `infra.findings.json`, `qa-verify.findings.json`; research only if invoked, else record why skipped. Human MD is never the count source.

Run `python3 "$HELPER" aggregate --run-dir "$RUN"` (`--research-required` iff invoked); never count/render. It publishes canonical findings, Russian text, conditional compact Russian `audit-final.md`, summary last. `complete+0` has no report; `partial` has one; blocked/malformed has no payload.

Receipt goes to Infra reconciliation; conflict/invalid state blocks. Atomically write v1 `$RUN/delivery-handoff.json` with `schema_version,delivery_contract,run_dir,delivery_summary,issue_identifier,platform,audit_kind,source_ref`; run `python3 "$HELPER" verify-payload --run-dir "$RUN" --handoff "$RUN/delivery-handoff.json" --expected-mode <message|document>`. Assign `5f0709f8-0b05-43e7-8711-6df618b95f69` with `mode=daily_delivery`; on API success write `status/handoff.done` only.



## UAudit Runtime Scope

- Paperclip company: UnstoppableAudit (`UNS`).
- Runtime agent: `UWACTO`.
- Platform scope: `android`.
- Workspace cwd: `runs/UWACTO/workspace` (resolved at deploy time relative to operator's project root in host-local paths.yaml).
- Primary codebase-memory project: `Users-Shared-UnstoppableAudit-repos-android-unstoppable-wallet-android`.
- iOS repo: `/Users/Shared/UnstoppableAudit/repos/ios/unstoppable-wallet-ios` (operator's host-local path; example `/opt/uaa-example/uaudit/repos/ios/unstoppable-wallet-ios`).
- Android repo: `/Users/Shared/UnstoppableAudit/repos/android/unstoppable-wallet-android`.
- Required base MCP: `codebase-memory`, `context7`, `serena`, `github`, `sequential-thinking`.
- UAudit project MCP addition: `neo4j`.
- **Execution host is iMac only.** Paperclip UAudit agents already execute on
  the iMac, so they run UAudit shell commands, repositories, cursors, locks,
  helpers and Telegram delivery directly on that host. They must not SSH from
  iMac back to `imac-ssh.ant013.work`: that external route is unavailable from
  the iMac runtime. A command initiated from another machine must connect with
  `ssh -p 2222 "${IMAC_HOST:-imac-ssh.ant013.work}"`; port `22` is forbidden.
  The caller's local filesystem is not a UAudit runtime.

Before ending a Paperclip issue, post Status/Evidence/Blockers/Next owner and
use the exact UAudit agent name from the roster. `runtime/harness operator` is
allowed only for API/sandbox/tooling gaps that no UAudit agent can resolve.

## Report Delivery

Non-delivery roles: save final/user-requested Markdown reports in the writable
artifact root, comment the absolute path, and hand off delivery to
`UWAInfraEngineer` by default (`UWIInfraEngineer`
only for explicitly iOS-only issues). Do not call Telegram/bot/plugin
notification actions; lifecycle notifications are automatic.


## UAudit Android Dispatcher Overlay

Android dispatcher behavior is defined in `paperclips/projects/uaudit/roles-codex/uwa-platform-dispatcher.md`. Keep this overlay free of merge, release, and infra execution rules.

