## Codex skills, agents, and MCP

Use installed Codex capabilities by task shape:

- Planning: `create-plan` skill for explicit plan requests.
- Code review: `code-reviewer`, `reviewer`, `architect-reviewer`.
- Python/backend work: `python-pro`, `backend-developer`, `debugger`.
- QA/testing: `qa-expert`, `test-automator`, `error-detective`.
- Security: `security-auditor`, `security-engineer`, `penetration-tester`.
- MCP/API work: `mcp-developer`, `api-designer`.
- Swift/mobile work: `swift-pro`, `swift-expert`, `mobile-developer`.
- Frontend/UX work: `frontend-design`, `ui-designer`, `ux-researcher`.

Use MCP context deliberately:

- `codebase-memory`: architecture, indexed code search, snippets, impact.
- `serena`: project activation, symbols, references, diagnostics.
- `context7`: current library documentation.
- `playwright`: browser smoke checks and UI evidence.

When a named capability is missing at runtime, say so in the Paperclip comment
and continue with the best available fallback instead of inventing a tool.
