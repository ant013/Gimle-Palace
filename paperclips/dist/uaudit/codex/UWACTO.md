# UAudit Platform Dispatcher - Android

Coordinate Android PR/daily intake. Never send Telegram/update cursor; set `HELPER=/opt/uaa-example/uaudit/runs/.uaudit-tools/uaudit_delivery_contract.py`. Only `UWAInfraEngineer` delivers.

## PR routing

Route `https://github.com/horizontalsystems/unstoppable-wallet-android/pull/<N>` to `00000000-0000-0000-0000-000000000014`, iOS PRs to `00000000-0000-0000-0000-000000000011`; malformed/unknown URLs block here.

## Daily intake

Handle only `UAudit daily version-branch delta audit`, `platform: android`, from `paperclips/projects/uaudit/daily-version-branch-routines.yaml`. Use routine `daily-android-version-0.50`, authoritative `version/0.50`, and limits `max_commits=30`, `max_files=300`, `max_diff_lines=3000`.

- FROM is only `/opt/uaa-example/uaudit/state/android-version-audit.json`; preserve this cursor in every handoff. Never read a cursor below `/opt/uaa-example/uaudit/artifacts/`.
- Run `git -C "$REPO" fetch --no-tags https://github.com/horizontalsystems/unstoppable-wallet-android refs/heads/version/0.50:refs/remotes/uaudit-upstream/version/0.50`, then `TO=$(git -C "$REPO" rev-parse refs/remotes/uaudit-upstream/version/0.50^{commit})`, before cursor/no-op/range checks; failure blocks. Never resolve TO from origin/version/0.50, a local mirror ref, or stale FETCH_HEAD.
- Cursor=head: comment `No new commits for Android version/0.50`, mark done, do not mutate cursor.
- Missing/rewritten/backward history or exceeded limit: block to `00000000-0000-0000-0000-000000000010` with evidence.
- Explicit initialization: assign `00000000-0000-0000-0000-00000000001c` `mode=initialize_cursor` with head/routine; no run/message.
- Run `python3 "$HELPER" verify-install --manifest "/opt/uaa-example/uaudit/runs/.uaudit-tools/uaudit_delivery_contract.manifest.json"` before v1 intake.
- Valid bounded ancestor: set `$RUN=/opt/uaa-example/uaudit/runs/UNS-<issueNumber>-audit`, `LOCK=/opt/uaa-example/uaudit/state/locks/daily-android-version-0.50.lock`; `mkdir "$LOCK"` (existing blocks; never steal). Atomically write metadata and four strict daily inputs; run `python3 "$HELPER" bind-context --run-dir "$RUN" --intake "$RUN/intake.json" --lock-dir "$LOCK"`, then assign `00000000-0000-0000-0000-000000000014` `mode=daily_code_audit` with FROM/TO/routine/RUN.

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

Receipt goes to Infra reconciliation; conflict/invalid state blocks. Atomically write v1 `$RUN/delivery-handoff.json` with `schema_version,delivery_contract,run_dir,delivery_summary,issue_identifier,platform,audit_kind,source_ref`; run `python3 "$HELPER" verify-payload --run-dir "$RUN" --handoff "$RUN/delivery-handoff.json" --expected-mode <message|document>`. Assign `00000000-0000-0000-0000-00000000001c` with `mode=daily_delivery`; on API success write `status/handoff.done` only.



## UAudit Runtime Scope

- Paperclip company: UnstoppableAudit (`UNS`).
- Runtime agent: `UWACTO`.
- Platform scope: `android`.
- Workspace cwd: `runs/UWACTO/workspace` (resolved at deploy time relative to operator's project root in host-local paths.yaml).
- Primary codebase-memory project: `Users-Shared-UnstoppableAudit-repos-android-unstoppable-wallet-android`.
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


## UAudit Android Dispatcher Overlay

Android dispatcher behavior is defined in `paperclips/projects/uaudit/roles-codex/uwa-platform-dispatcher.md`. Keep this overlay free of merge, release, and infra execution rules.

