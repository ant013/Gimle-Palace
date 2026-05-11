## Telegram Report Delivery (UAudit)

Send Markdown reports with `POST /api/plugins/{{report_delivery.telegram_plugin_id}}/actions/send_to_telegram`
and body `{"params":{"companyId":"{{project.company_id}}","agentId":"$PAPERCLIP_AGENT_ID","issueIdentifier","markdownFileName","markdownContent"}}`.
`issueIdentifier` MUST be the current `{{report_delivery.issue_prefix}}-*`;
never pass `chatId`. Inline Markdown only: no `filePath`, URLs, binaries, bot
tokens, or direct `api.telegram.org`. On `Board access required`, save/comment
the artifact path, mark Telegram delivery permission-blocked, and stop retrying.
Lifecycle events are auto-routed via `opsRoutes`; do not emit them manually.
