## Telegram Report Delivery (UAudit)

Send Markdown reports with `POST /api/plugins/{{report_delivery.telegram_plugin_id}}/actions/send_to_telegram`
and body `{"params":{"companyId":"{{project.company_id}}","agentId":"$PAPERCLIP_AGENT_ID","issueIdentifier","markdownFileName","markdownContent"}}`.
Use `PAPERCLIP_API_KEY` and `PAPERCLIP_API_URL` from your runtime environment for this delivery call; do not read `.env` files.
`issueIdentifier` MUST be the current `{{report_delivery.issue_prefix}}-*`;
never pass `chatId`. Inline Markdown only: no `filePath`, URLs, binaries, bot
tokens, or direct `api.telegram.org`. On `Board access required`, save/comment
the artifact path, mark Telegram delivery permission-blocked, and stop retrying.
Lifecycle events are auto-routed via `opsRoutes`; do not emit them manually.

## UAudit Subagent Smoke Delivery

If the current issue says `UAudit subagent smoke`, do not run deployment work.
Read:

```bash
N=<issueNumber of this Paperclip issue>
RUN=/Users/Shared/UnstoppableAudit/runs/UNS-$N-audit
SUMMARY=$RUN/smoke/summary.json
```

Create `$RUN/smoke/telegram-report.md` from the smoke summary and subagent JSON
files. The Markdown must include:

- issue identifier and platform (`Android`);
- `expected_subagent_count` and `completed_subagent_count`;
- exact required subagent names;
- one short response/result line for each subagent;
- explicit PASS/FAIL verdict and blocker, if any.

Send that Markdown through the Telegram plugin using
`markdownFileName="uaudit-subagent-smoke-UNS-$N-android.md"`. Then comment the
artifact path and mark the issue `done`. If `summary.json` is missing, mark the
issue blocked and state the missing path.
