## Agent UUID roster — Gimle Claude

Use `[@<Role>](agent://<uuid>?i=<icon>)` in phase handoffs.
Source: `paperclips/deploy-agents.sh`.

**Cross-team handoff rule** (applies to ALL agents, both teams): handoffs
must go to an agent on YOUR OWN team. Claude-side roles handoff to
Claude-side agents (bare names, no prefix); CX-side roles handoff to
CX-side agents (CX prefix). The two teams are isolated by design (per
`feedback_parallel_team_protocol.md`). When you say "next CTO" — that's
the CTO of your team. NEVER address an agent on the other team in a
phase handoff. The build pipeline ships **target-specific** rosters:
Claude target gets THIS file (Claude UUIDs); Codex target gets the
override at `paperclips/fragments/targets/codex/local/agent-roster.md`
(CX UUIDs).

| Role | UUID | Icon |
|---|---|---|
| CTO | `7fb0fdbb-e17f-4487-a4da-16993a907bec` | `eye` |
| CodeReviewer | `bd2d7e20-7ed8-474c-91fc-353d610f4c52` | `eye` |
| MCPEngineer | `274a0b0c-ebe8-4613-ad0e-3e745c817a97` | `circuit-board` |
| PythonEngineer | `127068ee-b564-4b37-9370-616c81c63f35` | `code` |
| QAEngineer | `58b68640-1e83-4d5d-978b-51a5ca9080e0` | `bug` |
| OpusArchitectReviewer | `8d6649e2-2df6-412a-a6bc-2d94bab3b73f` | `eye` |
| InfraEngineer | `89f8f76b-844b-4d1f-b614-edbe72a91d4b` | `server` |
| TechnicalWriter | `0e8222fd-88b9-4593-98f6-847a448b0aab` | `book` |
| ResearchAgent | `bbcef02c-b755-4624-bba6-84f01e5d49c8` | `magnifying-glass` |
| BlockchainEngineer | `9874ad7a-dfbc-49b0-b3ed-d0efda6453bb` | `link` |
| SecurityAuditor | `a56f9e4a-ef9c-46d4-a736-1db5e19bbde4` | `shield` |

`@Board` stays plain (operator-side, not an agent).
