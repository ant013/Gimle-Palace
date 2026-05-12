
## Trading Runtime Scope

This bundle inherits the proven Gimle/CX role text above. The base text was authored for Gimle-Palace; for **Trading** the substitutions below take precedence over any conflicting reference up there.

- **Paperclip company**: Trading (`TRD`).
- **Runtime agent**: `{{agent.agent_name}}`.
- **Workspace cwd**: `{{agent.workspace_cwd}}`.
- **Primary codebase-memory project**: `{{agent.primary_codebase_memory_project}}`.
- **Source repo**: `https://github.com/ant013/trading-agents` (private), mirrored read/write at `/Users/Shared/Trading/repo`.
- **Project domain**: trading platform — data ingestion (news, OHLC candles, exchange feeds) → strategy synthesis → AI-agent execution.
- **Issue prefix**: `TRD-N` (e.g., `TRD-1`).
- **Branch model**: `feature/TRD-N-<slug>` cut from `develop`, squash-merge via PR.
- **Required base MCP set**: `codebase-memory`, `context7`, `serena`, `github`, `sequential-thinking`. No Trading-specific MCPs in v1.

### Substitution table (read base role with these in mind)

| Base text reference (Gimle/UW) | Trading equivalent |
|---|---|
| `services/palace-mcp/` or `palace.*` MCP namespace | No MCP service in Trading v1; use base MCPs. |
| Graphiti / Neo4j extractor work | Not applicable to Trading v1 — skip. |
| Unstoppable Wallet (UW) / `unstoppable-wallet-*` as test target | `trading-agents` repo; no UW dependency. |
| `/Users/Shared/Ios/Gimle-Palace` production checkout | `/Users/Shared/Trading/repo`. |
| `docs/superpowers/specs/plans` in Gimle-Palace repo | `docs/superpowers/specs/plans` IN `trading-agents` repo. |
| `paperclips/fragments/shared/...` (Gimle's submodule) | Not used by Trading v1. |

### Workflow chain (5-phase, lean version)

CTO formalize → CR plan-first review → PE implement → CR mechanical review → QA smoke → CTO merge.

Trading roster has no OpusArchitectReviewer; Phase 3.2 adversarial is **skipped**. Trading roster has no InfraEngineer/MCPEngineer/Researcher/Writer; multi-role concerns collapse into the present 5 roles. Reassign with `PATCH status + assigneeAgentId + comment` atomically; `@mention` is decoration on the happy path.

### Telegram routing

Lifecycle events (`issue.created`, `issue.assigned`, `agent.run.started`, `agent.run.finished`, `agent.error`) are **auto-routed** by `paperclip-plugin-telegram` to the configured Trading chats:

- Ops chat (system events): `-1003956778910`
- Reports chat (file/markdown deliveries): `-1003907417326`

Agents do NOT call Telegram actions manually for lifecycle events; the plugin handles them.

### Report delivery

Trading v1 has no Infra-equivalent agent designated as report owner. Final markdown reports go to the writable artifact root `/Users/Shared/Trading/artifacts/{{agent.agent_name}}/`. Operator picks up delivery to the Reports chat until a delivery owner is designated for the project.

### Operator memory location

Operator's auto-memory for Trading lives at `~/.claude/projects/-Users-Shared-Trading/memory/` (separate namespace from Gimle/UAudit). Do not write Gimle memory paths.
