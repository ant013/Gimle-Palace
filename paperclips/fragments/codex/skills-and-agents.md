## Codex skills, agents, and MCP

Use installed Codex capabilities by task shape.

**Curated subagent set (per 30-day audit — keep only confirmed-invoked):**
- `voltagent-qa-sec:code-reviewer` (4 calls in audit window) — code review delegation
- `voltagent-research:search-specialist` (1 call) — landscape / CVE / docs search
- `pr-review-toolkit:pr-test-analyzer` (1 call) — test coverage audit
- `voltagent-lang:swift-expert`, `voltagent-lang:kotlin-specialist` — kept for future iOS/Android wallet review (BlockchainEngineer scope)
- Built-in: `Explore`, `general-purpose`
- User-level (iMac only): `code-reviewer`, `deep-research-agent`

When a named capability is missing at runtime, say so in the Paperclip comment
and continue with the best available fallback instead of inventing a tool.

**MCP context (use deliberately):**

- `codebase-memory`: architecture, indexed code search, snippets, impact.
- `serena`: project activation, symbols, references, diagnostics.
- `context7`: current library documentation.
- `playwright`: browser smoke checks and UI evidence.

MCP servers are shared runtime configuration. If they are missing in a Codex
Paperclip run, treat that as a runtime setup issue, not as a role-specific
instruction problem.
