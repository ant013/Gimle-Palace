# Paperclip Telegram Report Delivery Runbook

## Assumptions

- Telegram file/report delivery is handled by `paperclip-plugin-telegram`.
- UAudit report routing uses plugin `fileRoutes` and the current `UNS-*`
  `issueIdentifier`.
- Agent-scoped credentials may return `Board access required`; operator or
  Board-capable credentials are required for manual delivery.

## Scope

- Add an operator runbook for manual Markdown report delivery.
- Add a smoke checklist that verifies actual file delivery, not just ownership.
- Link the runbook from the existing Telegram operations page.

## Out Of Scope

- No AGENTS.md changes.
- No Telegram plugin code/config changes.
- No raw Telegram bot API usage.

## Affected Areas

- `docs/paperclip-operations/telegram-report-delivery.md`
- `docs/paperclip-operations/telegram-bot.md`

## Acceptance Criteria

- The runbook shows the supported `send_to_telegram` request shape.
- The runbook tells operators to use `issueIdentifier`, not `chatId`.
- The smoke checklist requires `ok:true`, `routeSource:file_route`, and
  `mode:document`.
- No agent bundle size changes.

## Verification Plan

- Review the Markdown for copy/paste correctness.
- Confirm no `paperclips/dist/` files changed.
- Run `git diff --check`.
