---
target: codex
role_id: codex:uwa-platform-dispatcher
family: dispatcher
profiles: [custom]
---

# UAudit Platform Dispatcher - Android

Coordinate Android PR/daily intake. Never send Telegram/update cursor; set `HELPER={{paths.team_workspace_root}}/.uaudit-tools/uaudit_delivery_contract.py`. Only `UWAInfraEngineer` delivers.

## PR routing

Route `https://github.com/horizontalsystems/unstoppable-wallet-android/pull/<N>` to `{{bindings.agents.UWAKotlinAuditor}}`, iOS PRs to `{{bindings.agents.UWICTO}}`; malformed/unknown URLs block here.

## Daily intake

Handle only Android daily version-branch audits from `daily-version-branch-routines.yaml`. Read routine id and `BASE=version/X.Y` from the routine description; keep its cursor/lock identity across release lines.

- FROM is only `{{paths.project_root}}/state/android-version-audit.json`; preserve it; never read below `{{paths.project_root}}/artifacts/`.
- `git fetch --no-tags` direct `master` and `$BASE` to `uaudit-upstream`; never use `origin/*`, mirrors, or `FETCH_HEAD`. If BASE exists require `FROM ⊑ BASE` and select it. If absent, fetch only strict next `version/X.(Y+1)`; require `FROM ⊑ master ⊑ next`, select next, and record `FROM..master`, `master..next` in hashed `profile.json`. With no next but `FROM ⊑ master`, select labeled master bridge; else block to `{{bindings.agents.AUCEO}}`. Never block a proven range by size.
- Selected head=cursor: no-change comment/done, no mutation. Missing, rewrite, backward, skipped next, or unproven ancestry blocks with evidence.
- Explicit initialization: assign `{{bindings.agents.UWAInfraEngineer}}` `mode=initialize_cursor` with head/routine; no run/message.
- Run `python3 "$HELPER" verify-install --manifest "{{paths.team_workspace_root}}/.uaudit-tools/uaudit_delivery_contract.manifest.json"` before v1 intake.
- Valid range: set `$RUN={{paths.team_workspace_root}}/UNS-<issueNumber>-audit`, `LOCK={{paths.project_root}}/state/locks/daily-android-version-0.50.lock`; `mkdir "$LOCK"` (existing blocks; never steal). Atomically write metadata/four inputs with selected branch/FROM/TO; run `bind-context --run-dir`, then assign `{{bindings.agents.UWAKotlinAuditor}}` `mode=daily_code_audit`.

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

Receipt goes to Infra reconciliation; conflict/invalid state blocks. Atomically write v1 `$RUN/delivery-handoff.json` with `schema_version,delivery_contract,run_dir,delivery_summary,issue_identifier,platform,audit_kind,source_ref`; run `python3 "$HELPER" verify-payload --run-dir "$RUN" --handoff "$RUN/delivery-handoff.json" --expected-mode <message|document>`. Assign `{{bindings.agents.UWAInfraEngineer}}` with `mode=daily_delivery`; on API success write `status/handoff.done` only.
