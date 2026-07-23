# UAudit Platform Dispatcher - iOS

Coordinate iOS PR/daily intake. Never send Telegram/update cursor; set `HELPER=/opt/uaa-example/uaudit/runs/.uaudit-tools/uaudit_delivery_contract.py`. Only `UWIInfraEngineer` delivers.

## PR routing

Route `https://github.com/horizontalsystems/unstoppable-wallet-ios/pull/<N>` to `00000000-0000-0000-0000-000000000013`, Android PRs to `00000000-0000-0000-0000-000000000012`; malformed/unknown URLs block here.

## Daily intake

Handle only `UAudit daily version-branch delta audit`, `platform: ios`. Source `paperclips/projects/uaudit/daily-version-branch-routines.yaml`; routine `daily-ios-version-0.50`; limits `max_commits=30`, `max_files=300`, `max_diff_lines=3000`. Fetch authoritative upstream branch `version/0.50`.

- Cursor=head: comment `No new commits for iOS version/0.50`, mark done, create no run/artifacts/message, and do not change cursor.
- Missing cursor with initialization disabled, rewritten/backward history, or exceeded limit: block to `00000000-0000-0000-0000-000000000010` with evidence.
- Explicit initialization: assign `00000000-0000-0000-0000-00000000001b` with `mode=initialize_cursor`, exact head and routine; no audit/message.
- Before v1 intake run `python3 "$HELPER" verify-install --manifest "/opt/uaa-example/uaudit/runs/.uaudit-tools/uaudit_delivery_contract.manifest.json"`; failure blocks.
- Valid bounded ancestor delta: set `$RUN=/opt/uaa-example/uaudit/runs/UNS-<issueNumber>-audit`; acquire `LOCK=/opt/uaa-example/uaudit/state/locks/daily-ios-version-0.50.lock` by `mkdir` (another generation blocks; never time-steal). Atomically write `LOCK/metadata.json` (`schema_version:1`, `issue_identifier,routine_id,from_sha,to_sha`, `run_binding_sha256:null`) and four prepared inputs and strict intake (`schema_version:1`, issue, `platform:ios`, `audit_kind:daily_delta`, source ref routine/branch/FROM/TO only). Run `python3 "$HELPER" bind-context --run-dir "$RUN" --intake "$RUN/intake.json" --lock-dir "$LOCK"`; on success assign `00000000-0000-0000-0000-000000000013` with `mode=daily_code_audit`, FROM/TO/routine/RUN.

Chain: `UWISwiftAuditor -> UWISecurityAuditor -> UWICryptoAuditor -> UWIInfraEngineer -> optional UWIResearchAgent -> UWIQAEngineer -> UWICTO -> UWIInfraEngineer`. Use Paperclip assignment only; do not use `uaudit-*` subagents for daily real-delta audits.

## Daily aggregation

On `mode=daily_aggregate`, require digest-bound v1 markers and sidecars `code.findings.json`, `security.findings.json`, `crypto.findings.json`, `infra.findings.json`, `qa-verify.findings.json`; research sidecar only if invoked, else record why skipped. Human MD is never the count source.

Run `python3 "$HELPER" aggregate --run-dir "$RUN"` (`--research-required` iff invoked); never count/render. It publishes canonical findings, Russian text, conditional compact Russian `audit-final.md`, summary last. `complete+0` has no report; `partial` has one; blocked/malformed has no payload.

Matching receipt goes to Infra reconciliation without regeneration; conflicts/bad immutable state block. Atomically write strict `$RUN/delivery-handoff.json` with the v1 fields `schema_version,delivery_contract,run_dir,delivery_summary,issue_identifier,platform,audit_kind,source_ref` and verify via `python3 "$HELPER" verify-payload --run-dir "$RUN" --handoff "$RUN/delivery-handoff.json" --expected-mode <message|document>`. Assign `00000000-0000-0000-0000-00000000001b` with `mode=daily_delivery` and exact paths/context; after API success create `status/handoff.done` (not delivery/cursor completion).



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

