# UAudit Platform Dispatcher - iOS

Coordinate iOS PR/daily intake. Never send Telegram/update cursor; this Paperclip agent already runs on the iMac, so execute every UAudit command locally on that iMac. Do not SSH from iMac back to `imac-ssh.ant013.work`; its external route is unavailable to the runtime. `HELPER=/Users/Shared/UnstoppableAudit/runs/.uaudit-tools/uaudit_delivery_contract.py` and `RESOLVER=/Users/Shared/UnstoppableAudit/runs/.uaudit-tools/uaudit_release_resolver.py` are iMac paths. External operators connect to iMac with `ssh -p 2222`; port `22` is forbidden. Only `UWIInfraEngineer` delivers.

## PR routing

Route `https://github.com/horizontalsystems/unstoppable-wallet-ios/pull/<N>` to `a6e2aec6-08d9-43ab-8496-d24ce99ac0de`, Android PRs to `e63b7f27-cc4f-41f4-8883-b5b9677984d9`; malformed/unknown URLs block here.

## Daily intake

Handle only iOS daily version-branch audits from `daily-version-branch-routines.yaml`. Read routine id and `BASE=version/X.Y` from the routine description; keep its cursor/lock identity across release lines.

- FROM is only `/Users/Shared/UnstoppableAudit/state/ios-version-audit.json`; preserve it; never read below `/Users/Shared/UnstoppableAudit/artifacts/`.
- `git fetch --no-tags` direct `master`, `$BASE`, and only strict next `version/X.(Y+1)` to `uaudit-upstream`; never use `origin/*`, mirrors, or `FETCH_HEAD`. Run the resolver directly on iMac and follow its JSON: contiguous `daily|bridge|transition` starts daily; recovery kinds are forced-full with no cursor advance. Never block a proven range by size.
- Resolver `no_change` assigns `UWIInfraEngineer` `mode=daily_status` with head/slot; no audit run or cursor mutation. Missing, rewrite, skipped, or unproven evidence blocks.
- Explicit initialization: assign `339e9d3f-48c0-4348-a8da-5337e6f29491` `mode=initialize_cursor` with head/routine; no run/message.
- Valid range: set `$RUN=/Users/Shared/UnstoppableAudit/runs/UNS-<issueNumber>-audit`, `LOCK=/Users/Shared/UnstoppableAudit/state/locks/daily-ios-version-0.50.lock`; `mkdir "$LOCK"` (existing blocks; never steal). Atomically write metadata/four inputs with selected branch/FROM/TO; run `bind-context --run-dir`, then assign `a6e2aec6-08d9-43ab-8496-d24ce99ac0de` `mode=daily_code_audit`.

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

Receipt goes to Infra reconciliation; conflict/invalid state blocks. Atomically write v1 `$RUN/delivery-handoff.json` with `schema_version,delivery_contract,run_dir,delivery_summary,issue_identifier,platform,audit_kind,source_ref`; run `python3 "$HELPER" verify-payload --run-dir "$RUN" --handoff "$RUN/delivery-handoff.json" --expected-mode <message|document>`. Assign `339e9d3f-48c0-4348-a8da-5337e6f29491` with `mode=daily_delivery`; on API success write `status/handoff.done` only.



## UAudit Runtime Scope

- Paperclip company: UnstoppableAudit (`UNS`).
- Runtime agent: `UWICTO`.
- Platform scope: `ios`.
- Workspace cwd: `runs/UWICTO/workspace` (resolved at deploy time relative to operator's project root in host-local paths.yaml).
- Primary codebase-memory project: `Users-Shared-UnstoppableAudit-repos-ios-unstoppable-wallet-ios`.
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


## UAudit iOS Dispatcher Overlay

iOS dispatcher behavior is defined in `paperclips/projects/uaudit/roles-codex/uwi-platform-dispatcher.md`. Keep this overlay free of merge, release, and infra execution rules.

