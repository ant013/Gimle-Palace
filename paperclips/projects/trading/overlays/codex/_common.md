
## Trading Runtime Scope

This bundle inherits the proven Gimle/CX role text above. The base text was authored for Gimle-Palace; for **Trading** the substitutions below take precedence over any conflicting reference up there.

- **Paperclip company**: Trading (`TRD`).
- **Runtime agent**: `{{agent.agent_name}}`.
- **Workspace cwd**: `{{agent.workspace_cwd}}`.
- **Primary codebase-memory project**: `{{agent.primary_codebase_memory_project}}`.
- **Source repo**: `https://github.com/ant013/trading-agents` (private), mirrored read/write at `/Users/Shared/Trading/repo`.
- **Project domain**: trading platform — data ingestion (news, OHLC candles, exchange feeds) → strategy synthesis → AI-agent execution.
- **Issue prefix**: `TRD-N`.
- **Branch model**: `feature/TRD-N-<slug>` from `develop`, squash-merge via PR.
- **Required base MCP set**: `codebase-memory`, `context7`, `serena`, `github`, `sequential-thinking`. No Trading-specific MCPs in v1.

### Substitution table

| Base text reference (Gimle/UW) | Trading equivalent |
|---|---|
| `services/palace-mcp/` or `palace.*` MCP namespace | No MCP service in Trading v1. Use base MCPs. |
| Graphiti / Neo4j extractor work | Not applicable — skip. |
| Unstoppable Wallet (UW) / `unstoppable-wallet-*` as test target | `trading-agents` repo. |
| `/Users/Shared/Ios/Gimle-Palace` production checkout | `/Users/Shared/Trading/repo`. |
| `docs/superpowers/specs/plans` in Gimle-Palace repo | `docs/specs` + `docs/plans` IN `trading-agents` repo. |
| `paperclips/fragments/shared/...` Gimle submodule | Not used by Trading v1. |
| Gimle 7-phase workflow (CTO → CR → PE → CR → Opus → QA → CTO) | **Trading 7-phase, different ordering** — see WORKFLOW below. |

### Workflow chain (authoritative ref: `paperclips/projects/trading/WORKFLOW.md`)

Trading runs **two loops**:

- **Outer loop** — parent `roadmap walker` issue. CTO reads `roadmap.md` at repo root, spawns one child issue per `- [ ]` row top-to-bottom, waits, then advances.
- **Inner loop** (per child) — 7 transitions:

  1. **CTO** drafts spec → 2. **CR** reviews spec via 3 voltAgent subagents (arch / security / cost) → 3. **CTO** writes plan addressing CR blockers → 4. **PE** implements → 5. **CR** reviews code (mechanical + quality, paste `ruff/mypy/pytest/coverage` output) → 6. **QA** smoke with pinned routing criteria → 7. **CTO** merges PR + closes child + advances roadmap.

  Key difference from Gimle: CR sees **spec first** (Phase 2), not plan. Plan written by CTO post-review.

  QA routing is **not judgmental** — see WORKFLOW.md "QA criteria" table.

### Telegram routing

Lifecycle events auto-routed by `paperclip-plugin-telegram`:
- Ops chat (system events): `-1003956778910`
- Reports chat (file/markdown deliveries): `-1003907417326`

Agents do NOT call Telegram actions manually for lifecycle events.

### Report delivery

Trading v1 has no Infra-equivalent agent. Final markdown reports go to `/Users/Shared/Trading/artifacts/{{agent.agent_name}}/`. Operator handles delivery until a delivery owner is designated.

### Operator memory location

Trading auto-memory: `~/.claude/projects/-Users-Shared-Trading/memory/`. Do not write Gimle memory paths.
