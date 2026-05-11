
## UAudit Runtime Scope

- Paperclip company: UnstoppableAudit (`UNS`).
- Runtime agent: `{{agent.agent_name}}`.
- Platform scope: `{{agent.platform}}`.
- Workspace cwd: `{{agent.workspace_cwd}}`.
- Primary codebase-memory project: `{{agent.primary_codebase_memory_project}}`.
- iOS repo: `/Users/Shared/UnstoppableAudit/repos/ios/unstoppable-wallet-ios`.
- Android repo: `/Users/Shared/UnstoppableAudit/repos/android/unstoppable-wallet-android`.
- Required base MCP: `codebase-memory`, `context7`, `serena`, `github`, `sequential-thinking`.
- UAudit project MCP addition: `neo4j`.

Before ending a Paperclip issue, post Status/Evidence/Blockers/Next owner and
use the exact UAudit agent name from the roster. `runtime/harness operator` is
allowed only for API/sandbox/tooling gaps that no UAudit agent can resolve.
