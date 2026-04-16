# MCP Engineer — Research Notes

**Research date:** 2026-04-16
**Purpose:** inform `paperclips/roles/mcp-engineer.md` for Gimle-Palace (Slice #9)
**Target:** owns palace-mcp service (FastAPI + streamable-HTTP MCP), tool catalogue, client distribution

## 1. Sources reviewed

| Source | Stars | Length | Signal |
|---|---|---|---|
| **anthropics/claude-plugins-official `mcp-server-dev`** | 17.1k | 208 lines + refs/ | **Official Anthropic-authored** — spec-current (2025-11-25), deployment matrix, references for tool-design + auth + elicitation + manifest |
| **VoltAgent `mcp-developer`** | ~17k | 275 lines | Full-lifecycle agent: JSON-RPC 2.0 checklist, server/client/protocol/SDK/integration/security/perf/test/deploy sections + multi-agent collaboration matrix |
| **VoltAgent codex `mcp-developer.toml`** | 4k | ~40 lines | **Engineering conservatism**: smallest safe change, compatibility-first, contract-safe errors, no protocol-breaking without migration |
| rohitg00 `mcp-developer` | 1.3k | ~120 lines | Transport (stdio/SSE/HTTP), Zod/JSON Schema, Inspector testing |
| anthropics official MCP docs (modelcontextprotocol.io) | — | — | Spec authority for streamable-HTTP / SSE deprecation / CIMD auth |
| wshobson/agents | 33.5k | — | **No MCP-specific agent** (gap) |
| garrytan/gstack | ~73k | — | **No MCP coverage** (gap) |
| addyosmani/agent-skills | — | — | devtools-mcp tooling, no agent role |

9 sources, only 4 directly applicable. wshobson + garrytan don't cover MCP at all — niche specialization.

## 2. Top-3 community recommendations (от research-specialist)

### 2.1 Anthropic mcp-server-dev as base
- Single source for current spec (streamable-HTTP default, SSE deprecated, CIMD OAuth in 2025-11-25 spec)
- references/ folder with `tool-design.md` + `auth.md` + `elicitation.md` — high-value secondary context
- Deployment decision matrix (remote / elicitation / MCP app / MCPB / stdio) directly applicable

### 2.2 Codex .toml for behavioral conservatism
- "Smallest safe change" + "compatibility impact on existing consumers" + "no protocol-breaking changes without migration guidance"
- Critical for Gimle: palace-mcp has live consumers (Serena, future Cursor/Claude Desktop)

### 2.3 VoltAgent for full-lifecycle scaffold
- 275 lines, structured by lifecycle phase (server dev / client / protocol / SDK / integration / security / perf / test / deploy)
- Use as section catalogue, not full prompt (too long, too generic for Gimle)

## 3. Gimle-specific gaps (NOT in any community prompt)

### 3.1 Pydantic v2 boundary validation policy
FastAPI + MCP = two validation layers. Community prompts assume one. For Gimle: explicit policy that EVERY MCP tool input goes through Pydantic model before business logic — this catches schema drift between FastAPI route and MCP tool definition.

### 3.2 Serena tool catalogue design
palace-mcp's primary value is semantic code analysis (Serena integration). Tool naming + idempotency + truncation policy specific to code-search domain. No community prompt addresses Serena-style tools.

### 3.3 Internal auth threat model
palace-mcp is internal (paperclip-agent-net), but exposable via cloudflared tunnel. Need explicit threat model doc + decision protocol for transport/exposure changes. Community prompts cover OAuth (external) or stdio (local), not internal-but-exposable.

### 3.4 Tool naming convention
`palace.<domain>.<verb>` — required for consistency across Cursor / Claude Desktop / programmatic clients. Anthropic mentions disambiguating descriptions but no naming convention.

## 4. Composite design

**Base:** behavioral conservatism (codex .toml) + Anthropic spec navigation (mcp-server-dev) + lifecycle structure (VoltAgent — sections only).

**Drop:**
- Full-lifecycle multi-agent collab matrix (VoltAgent) — Gimle has explicit role boundaries already
- MCPB packaging (Anthropic) — defer until external client demand
- Communication Protocol JSON block (VoltAgent) — pure noise for Claude Code
- stdio/SSE deep coverage (rohitg00) — locked transport for palace-mcp

**Add Gimle-specific:**
- Pydantic v2 boundary policy (4-line section)
- Serena tool catalogue rules (in tool design)
- Internal auth threat model (5-line section + reference to docs/mcp/auth-threat-model.md)
- Tool naming `palace.<domain>.<verb>` convention

## 5. Final template structure (95 lines role-specific)

1. Role + ownership boundaries (contrast with PythonEngineer/InfraEngineer/TechnicalWriter)
2. Зона ответственности table (5 rows + explicit "не зона")
3. Engineering conservatism principles (5 bullets)
4. Tool design rules (5 bullets — naming + count + schema + truncation + disambiguation)
5. Transport — locked: streamable-HTTP (justification)
6. Auth model (internal vs exposed, threat model reference)
7. Compliance checklist (8 items)
8. MCP/Subagents/Skills (Pydantic + Anthropic SDK + spec lookup)
9. Fragment includes (karpathy + escalation + heartbeat + git + worktree + language + pre-work)
