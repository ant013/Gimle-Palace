# Operator Claude Code Setup — palace.memory.prime

**Audience:** Human operator bootstrapping a new Claude Code session for the Gimle Palace project.

## Quick start

```
palace.memory.prime(role="operator")
```

Returns a context snapshot: current slice header, recent standing decisions, and health summary.
Paste the `content` field into the session or store in operator memory.

## Tool signature

```
palace.memory.prime(
    role: str,              # one of: operator, cto, codereviewer, pythonengineer,
                            #         opusarchitectreviewer, qaengineer
    slice_id: str | None,   # e.g. "GIM-96" — auto-detected from git branch if omitted
    budget: int = 2000,     # token estimate cap; role extras are tail-truncated if over
)
```

## Prerequisites

1. `docker compose --profile review up -d` — palace-mcp and Neo4j must be running.
2. Claude Code must have the `palace-mcp` MCP server wired in (`.mcp.json` or settings).
3. The operator checkout must be on a `feature/GIM-*` branch for auto-detection to work;
   otherwise pass `slice_id` explicitly.

## What the tool returns

```json
{
  "ok": true,
  "content": "## Slice context: GIM-96 ...\n...",
  "role": "operator",
  "slice_id": "GIM-96",
  "tokens_estimated": 487,
  "truncated": false
}
```

`content` is Markdown. It contains:
- **Slice header** — issue ref, description, and the 5 most recent commits on the feature branch.
- **Standing decisions** — up to 5 `:Decision` nodes from Neo4j scoped to this slice,
  each wrapped in `<untrusted-decision>` bands (treat as data, not instructions).
- **Health summary** — Neo4j reachability and last ingest run.
- **Role extras** — role-specific context from `paperclips/fragments/shared/fragments/role-prime/<role>.md`.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `"ok": false, "error_code": "invalid_role"` | Typo in role name | Check spelling; valid: `operator cto codereviewer pythonengineer opusarchitectreviewer qaengineer` |
| `"ok": false, "error_code": "neo4j_error"` | Neo4j not running | `docker compose --profile review up -d` |
| `slice_id: null` in response | Not on a feature branch | Pass `slice_id` explicitly: `palace.memory.prime(role="operator", slice_id="GIM-96")` |
| `"truncated": true` | Role extras exceeded budget | Raise `budget` param or the role extras file is too large |
| Decisions show `<untrusted-decision>` markup | Expected | That markup is intentional — it signals untrusted external content |

## Updating role-prime files

Role-prime fragments live in the `paperclips/fragments/shared` submodule under
`fragments/role-prime/<role>.md`. Edit on a feature branch there, then update
the submodule pointer in gimle-palace. Fragment density cap: ≤ 2 KB per file (GIM-94).

## Slash command (optional)

If `.claude/commands/prime.md` is present in the project, `/prime <role> [<slice-id>]`
invokes the tool directly from Claude Code's command palette.
