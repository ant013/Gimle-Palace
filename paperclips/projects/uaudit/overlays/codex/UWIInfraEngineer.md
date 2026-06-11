## Telegram Report Delivery (UAudit)

The Telegram plugin action rejects agent-scoped runtime tokens with
`Board access required`. Read only `/Users/anton/.paperclip/auth.json` for this token; never `.env`,
bot tokens, or other secrets:

```bash
PAPERCLIP_DELIVERY_API_URL=http://localhost:3100
PAPERCLIP_DELIVERY_TOKEN=$(jq -r '.credentials["http://localhost:3100"].token // .credentials["https://paperclip.ant013.work"].token // empty' /Users/anton/.paperclip/auth.json)
test -n "$$PAPERCLIP_DELIVERY_TOKEN"
```

Send with `Authorization: Bearer $$PAPERCLIP_DELIVERY_TOKEN`:
`POST $$PAPERCLIP_DELIVERY_API_URL/api/plugins/{{plugins.telegram.plugin_id}}/actions/send_to_telegram`
body `{"params":{"companyId":"{{bindings.company_id}}","agentId":"$$PAPERCLIP_AGENT_ID","issueIdentifier","markdownFileName","markdownContent"}}`.
`issueIdentifier` MUST be `{{report_delivery.issue_prefix}}-*`; never pass
`chatId`. Inline Markdown only — no `filePath`, URLs, binaries, bot tokens, or
direct `api.telegram.org`. If `PAPERCLIP_DELIVERY_TOKEN` is empty or the plugin
still returns `Board access required`, save/comment the artifact path, mark
delivery permission-blocked, and stop retrying. Lifecycle events are auto-routed
via `opsRoutes`; do not emit them manually.

## Daily Version-Branch Staged Audit (iOS)

Run this path only after a UAudit daily handoff. You execute the staged
Paperclip-agent chain; never fan out to local `uaudit-*` Codex subagents for
daily real-delta audits.

Before repo work, delivery, or cursor writes, handle blocked resumes. If the
issue was blocked or `$RUN/status/blocked` exists, read the latest comments and
continue only when the newest Board/operator input explicitly says `unblocked`,
`resume approved`, `proceed`, or `partial audit approved`. `@Board blocked`,
watchdog escalation, or a repeated blocker summary is not unblock input. If no
explicit unblock exists, comment that the existing blocker still stands, PATCH
the issue back to `blocked`, leave the cursor unchanged, and stop.

### Constants

```bash
N=<issueNumber of this Paperclip issue>
RUN={{paths.team_workspace_root}}/UNS-$N-audit
REPO={{paths.primary_repo_root}}
BRANCH=version/0.49
CURSOR={{paths.project_root}}/state/ios-version-audit.json
CODEBASE_MEMORY_PROJECT=Users-Shared-UnstoppableAudit-repos-ios-unstoppable-wallet-ios
```

### Accepted Handoff Modes

`mode=initialize_cursor`: write the exact upstream head SHA supplied by `UWICTO` to `$CURSOR`, comment the initialized SHA and routine id, mark done, and stop. Do not create `$RUN`, do not audit, and do not send Telegram.

`mode=daily_infra_audit`: read `$RUN/{profile.json,commits.tsv,files.tsv,diff.patch,code.md,security.md,crypto.md}` for the supplied FROM..TO range. Write `$RUN/infra.md` with build, CI, dependency, delivery, repository, configuration, and operational findings plus limitations. Then write `$RUN/infra.done`. If Critical/Block findings or unresolved external questions require research, PATCH assignee to `{{bindings.agents.UWIResearchAgent}}` with `mode=daily_research`; otherwise PATCH assignee to `{{bindings.agents.UWIQAEngineer}}` with `mode=daily_qa_verify`. Stop after handoff.

`mode=daily_delivery`: read `$RUN/audit-final.md`, compute its SHA-256, and send it through Telegram as `markdownFileName="uaudit-ios-version-0.49-delta-UNS-$N.md"`. Verify `ok:true`, `routeSource:file_route`, `routeName:UAudit`, and `mode:document`.

Never advance the cursor before successful Telegram delivery. Only after successful delivery, atomically update `$CURSOR` with `<TO>`, `UNS-$N`, and current UTC ISO-8601 timestamp. Then comment the report path, delivered filename, message id, FROM..TO, and mark done.

## Prepared Audit Delivery (Backward Compatibility)

When a UAudit role PATCHes assignee onto you for a UNS-N PR-audit issue without the daily-delta marker, a prepared `audit.md` may be waiting at `{{paths.team_workspace_root}}/UNS-<N>-audit/audit.md`. You do not modify it. Compute its SHA-256, send it through the Telegram plugin using `issueIdentifier="UNS-$N"`, comment filename + `messageId` + SHA-256 digest, then mark the issue `done`.

## UAudit Subagent Smoke Delivery

If the current issue says `UAudit subagent smoke`, do not run deployment work or daily delta audit. Read `{{paths.team_workspace_root}}/UNS-$N-audit/smoke/summary.json`, create a short Telegram report from the smoke summary and subagent JSON files, send it through Telegram, comment the artifact path, and mark done. If the summary is missing, mark blocked and state the missing path.
