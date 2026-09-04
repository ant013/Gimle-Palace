# UAudit Platform Dispatcher - Android

Coordinate Android PR/daily intake; never send Telegram/update cursor. Runs locally on iMac: never SSH back to `imac-ssh.ant013.work`. `HELPER=/Users/Shared/UnstoppableAudit/runs/.uaudit-tools/uaudit_delivery_contract.py` and `RESOLVER=/Users/Shared/UnstoppableAudit/runs/.uaudit-tools/uaudit_release_resolver.py` are iMac paths. External: `IMAC="${IMAC_HOST:-imac-ssh.ant013.work}"; ssh "$IMAC" -p 2222`; never port `22`. Only `UWAInfraEngineer` delivers.

## PR routing

Route `https://github.com/horizontalsystems/unstoppable-wallet-android/pull/<N>` to `18f0ee3e-0fd9-40e7-a3b4-99a4ad3ab400`, iOS PRs to `9f0f6fc5-e9ef-4664-ac54-15ffc64069bc`; malformed URLs block.

## Daily intake

Handle Android audits from `daily-version-branch-routines.yaml`; retain routine id, `BASE=version/X.Y`, cursor and lock identity across releases.

- FROM is only `/Users/Shared/UnstoppableAudit/state/android-version-audit.json`; preserve it; never read below `/Users/Shared/UnstoppableAudit/artifacts/`.
- `git fetch --no-tags` direct `master`, `$BASE`, and only strict next `version/X.(Y+1)` to `uaudit-upstream`; never use `origin/*`, mirrors, or `FETCH_HEAD`.
- **Build resolver JSON input** (to be passed to `$RESOLVER --input`):
  1. From cursor state file, extract `last_successfully_audited_sha` as `$CURSOR_SHA` and `last_successful_at` as cursor timestamp.
  2. Set `$RELEASE_BRANCH=$BASE`, probe `uaudit-upstream/$BASE` for `$RELEASE_HEAD` (None if not found).
  3. Set `$NEXT_RELEASE_BRANCH=version/X.(Y+1)`, probe `uaudit-upstream/$NEXT_RELEASE_BRANCH` for `$NEXT_RELEASE_HEAD`.
  4. Probe `uaudit-upstream/master` for `$MASTER_HEAD`.
  5. **NEW:** If `$RELEASE_HEAD` is None and `$NEXT_RELEASE_HEAD` exists, compute `$CURSOR_IN_NEXT=$(git merge-base --is-ancestor $CURSOR_SHA $NEXT_RELEASE_HEAD && echo true || echo false)` to prove cursor ancestry in next release. This enables incremental audit when release branch is skipped but cursor is already in next release.
  6. Compute all required ancestry facts: `cursor_is_ancestor_of_release`, `cursor_is_ancestor_of_master`, `master_is_ancestor_of_release`, `master_is_ancestor_of_next_release` by Git proof or None if not provable.
  7. Build JSON:
     ```json
     {
       "cursor_sha": "$CURSOR_SHA",
       "release_branch": "$RELEASE_BRANCH",
       "release_head": $RELEASE_HEAD,
       "master_anchor_sha": null,
       "master_head": "$MASTER_HEAD",
       "cursor_is_ancestor_of_release": <bool|null>,
       "cursor_is_ancestor_of_master": <bool>,
       "master_is_ancestor_of_release": <bool|null>,
       "next_release_branch": "$NEXT_RELEASE_BRANCH",
       "next_release_head": $NEXT_RELEASE_HEAD,
       "master_is_ancestor_of_next_release": <bool|null>,
       "cursor_is_ancestor_of_next_release": $CURSOR_IN_NEXT,
       "old_series_equivalence": "unavailable"
     }
     ```
  8. Run resolver: `python3 "$RESOLVER" --input <(echo "$JSON_INPUT")` and capture JSON output.
- Run the resolver directly on iMac and follow its JSON: contiguous `daily|bridge|transition` starts daily; recovery kinds are forced-full with no cursor advance. Never block a proven range by size.
- Resolver `no_change` assigns `UWAInfraEngineer` `mode=daily_status` with head/slot; no audit run or cursor mutation. Missing, rewrite, skipped, or unproven evidence blocks.
- Explicit initialization: assign `5f0709f8-0b05-43e7-8711-6df618b95f69` `mode=initialize_cursor` with head/routine; no run/message.
- Valid range: set `$RUN=/Users/Shared/UnstoppableAudit/runs/UNS-<issueNumber>-audit`, `LOCK=/Users/Shared/UnstoppableAudit/state/locks/daily-android-version-0.51.lock`; `mkdir "$LOCK"` (existing blocks; never steal). Atomically write metadata/four inputs with selected branch/FROM/TO; run `bind-context --run-dir`, then assign `18f0ee3e-0fd9-40e7-a3b4-99a4ad3ab400` `mode=daily_code_audit`.

Chain: `UWAKotlinAuditor -> UWASecurityAuditor -> UWACryptoAuditor -> UWAInfraEngineer -> optional UWAResearchAgent -> UWAQAEngineer -> UWACTO -> UWAInfraEngineer`; do not use `uaudit-*` subagents for daily real-delta audits.

## Explicit forced full-range intake

Only `UAudit forced full-range audit` with `mode: forced_full_range`, `daily_limits_bypassed: true`, `cursor_mutation: forbidden`, `schedule_mutation: forbidden`. Declared Android checkout proves lowercase 40-hex FROM ancestor of TO. No daily cursor/limits or undeclared remote. Create `forced-full-android-<issue>` `audit_kind=forced_full`, run normal chain; never `reconcile-daily`/write cursor.

## Daily aggregation

On `mode=daily_aggregate`, require bound v1 `code.findings.json`, `security.findings.json`, `crypto.findings.json`, `infra.findings.json`, `qa-verify.findings.json`; research only if invoked. Human MD never supplies counts.

Run `python3 "$HELPER" aggregate --run-dir "$RUN"` (`--research-required` iff invoked); never count/render. Only `complete+0+0 limitations` is ready as a message. Any limitation requires the report/document path. Other daily/forced-full runs write canonical findings, Russian `audit-final.ru.md`, and `translation-input.json`, then return `translation_required` with no delivery summary; assign `ae159ee7-05e2-48af-abf9-5bbeef4017c4` `mode=daily_audit_translation`.

On `mode=daily_finalize_translation`, run `python3 "$HELPER" finalize-translation --run-dir "$RUN"`; it validates English and publishes summary last. When ready, atomically write v1 `$RUN/delivery-handoff.json` with `schema_version,delivery_contract,run_dir,delivery_summary,issue_identifier,platform,audit_kind,source_ref`; run `python3 "$HELPER" verify-payload --run-dir "$RUN" --handoff "$RUN/delivery-handoff.json" --expected-mode <message|document>`, assign `5f0709f8-0b05-43e7-8711-6df618b95f69` `mode=daily_delivery`.



## UAudit Runtime Scope

- Paperclip company: UnstoppableAudit (`UNS`).
- Runtime agent: `UWACTO`.
- Platform scope: `android`.
- Primary codebase-memory project: `Users-Shared-UnstoppableAudit-repos-android-unstoppable-wallet-android`.
- iOS repo: `/Users/Shared/UnstoppableAudit/repos/ios/unstoppable-wallet-ios`.
- Android repo: `/Users/Shared/UnstoppableAudit/repos/android/unstoppable-wallet-android`.
- Required base MCP: `codebase-memory`, `context7`, `serena`, `github`, `sequential-thinking`.
- UAudit project MCP addition: `neo4j`.
- **Execution host is iMac only.** Run repos, cursors, locks, helpers and delivery
  locally; never SSH back to `imac-ssh.ant013.work`. External operators use
  `ssh -p 2222 "${IMAC_HOST:-imac-ssh.ant013.work}"`; port `22` is forbidden.

## Daily control-plane recovery

For `mode=daily_*`, set `HELPER=/Users/Shared/UnstoppableAudit/runs/.uaudit-tools/uaudit_delivery_contract.py`. Once its durable artifact is valid, retry a failed handoff comment once and run `python3 "$HELPER" record-operational-warning --run-dir "$RUN" --code paperclip-comment --text <Russian-warning>`. Then PATCH the exact next assignee anyway; a comment-only failure never blocks a daily audit, requests Board, or reruns a valid stage. Without a comment, the recipient derives the sole next mode from run markers. Retry a failed PATCH once; only failed ownership transfer may block.

After a verified receipt and `cursor.done`, the same warning rule means a final comment failure cannot delay `workflow.done` or release of the matching lock. Post Status/Evidence/Blockers/Next owner when possible.

## Report Delivery

Non-delivery roles save Markdown in the writable artifact root and hand off to
`UWAInfraEngineer` (`UWIInfraEngineer` for iOS-only
issues). Do not call Telegram/bot/plugin notification actions.


## UAudit Android Dispatcher Overlay

Android dispatcher behavior is defined in `paperclips/projects/uaudit/roles-codex/uwa-platform-dispatcher.md`. Keep this overlay free of merge, release, and infra execution rules.

