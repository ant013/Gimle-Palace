
## UAudit Runtime Scope

- Paperclip company: UnstoppableAudit (`UNS`).
- Runtime agent: `{{agent.agent_name}}`.
- Platform scope: `{{agent.platform}}`.
- Workspace cwd: `runs/{{agent.agent_name}}/workspace` (resolved at deploy time relative to operator's project root in host-local paths.yaml).
- Primary codebase-memory project: `{{agent.primary_codebase_memory_project}}`.
- iOS repo: `{{paths.primary_repo_root}}` (operator's host-local path; example `/opt/uaa-example/uaudit/repos/ios/unstoppable-wallet-ios`).
- Android repo: `{{paths.project_root}}/repos/android/unstoppable-wallet-android`.
- Required base MCP: `codebase-memory`, `context7`, `serena`, `github`, `sequential-thinking`.
- UAudit project MCP addition: `neo4j`.

Before ending a Paperclip issue, post Status/Evidence/Blockers/Next owner and
use the exact UAudit agent name from the roster. `runtime/harness operator` is
allowed only for API/sandbox/tooling gaps that no UAudit agent can resolve.

## Report Delivery

Non-delivery roles: save final/user-requested Markdown reports in the writable
artifact root, comment the absolute path, and hand off delivery to
`{{report_delivery.default_owner}}` by default (`{{report_delivery.ios_owner}}`
only for explicitly iOS-only issues). Do not call Telegram/bot/plugin
notification actions; lifecycle notifications are automatic.
