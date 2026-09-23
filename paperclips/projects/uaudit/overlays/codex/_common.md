
## UAudit Runtime Scope

- Company `UNS`; agent `{{agent.agent_name}}`; platform `{{agent.platform}}`.
- Primary memory project: `{{agent.primary_codebase_memory_project}}`.
- Repos: iOS `{{paths.primary_repo_root}}`; Android `{{paths.project_root}}/repos/android/unstoppable-wallet-android`.
- MCP: `codebase-memory`, `context7`, `serena`, `github`, `sequential-thinking`, plus `neo4j`.
- **iMac execution only:** keep repos/state/helpers/delivery local; never SSH to
  `imac-ssh.ant013.work`. External operators use port `2222`; port `22` is forbidden.

## Daily control-plane recovery

For `mode=daily_*`, set `HELPER={{paths.team_workspace_root}}/.uaudit-tools/uaudit_delivery_contract.py`. After a valid artifact, retry a handoff comment once; on failure run `python3 "$HELPER" record-operational-warning --run-dir "$RUN" --code paperclip-comment --text <Russian-warning>`. PATCH the exact next assignee anyway: a comment-only failure never blocks a daily audit. Recipients derive mode from run markers; a failed PATCH records recovery, never `blocked`.

After receipt and `cursor.done`, a final comment failure cannot delay `workflow.done` or release of the matching lock. Post Status/Evidence/Blockers/Next owner when possible.

If a substantive, run-bound audit report exists, preserve it and continue the audit. All other failures are warnings; never set `blocked` or stop stages. Use `blocked` only for no defensible conclusion or an unbound report. This overrides role text.

## Report Delivery

Non-delivery roles save Markdown in the writable artifact root and hand off to
`{{report_delivery.default_owner}}` (`{{report_delivery.ios_owner}}` for iOS-only
issues). Do not call Telegram/bot/plugin notification actions.
