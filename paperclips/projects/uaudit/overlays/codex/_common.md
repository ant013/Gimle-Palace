
## UAudit Runtime Scope

- Paperclip company: UnstoppableAudit (`UNS`).
- Runtime agent: `{{agent.agent_name}}`.
- Platform scope: `{{agent.platform}}`.
- Primary codebase-memory project: `{{agent.primary_codebase_memory_project}}`.
- iOS repo: `{{paths.primary_repo_root}}`.
- Android repo: `{{paths.project_root}}/repos/android/unstoppable-wallet-android`.
- Required base MCP: `codebase-memory`, `context7`, `serena`, `github`, `sequential-thinking`.
- UAudit project MCP addition: `neo4j`.
- **Execution host is iMac only.** Run repos, cursors, locks, helpers and delivery
  locally; never SSH back to `imac-ssh.ant013.work`. External operators use
  `ssh -p 2222 "${IMAC_HOST:-imac-ssh.ant013.work}"`; port `22` is forbidden.

## Daily control-plane recovery

For `mode=daily_*`, set `HELPER={{paths.team_workspace_root}}/.uaudit-tools/uaudit_delivery_contract.py`. Once its durable artifact is valid, retry a failed handoff comment once and run `python3 "$HELPER" record-operational-warning --run-dir "$RUN" --code paperclip-comment --text <Russian-warning>`. Then PATCH the exact next assignee anyway; a comment-only failure never blocks a daily audit, requests Board, or reruns a valid stage. Without a comment, the recipient derives the sole next mode from run markers. Retry a failed PATCH once; only failed ownership transfer may block.

After a verified receipt and `cursor.done`, the same warning rule means a final comment failure cannot delay `workflow.done` or release of the matching lock. Post Status/Evidence/Blockers/Next owner when possible.

## Report Delivery

Non-delivery roles save Markdown in the writable artifact root and hand off to
`{{report_delivery.default_owner}}` (`{{report_delivery.ios_owner}}` for iOS-only
issues). Do not call Telegram/bot/plugin notification actions.
