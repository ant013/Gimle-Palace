## Agent UUID roster — Trading

Use `[@<Role>](agent://<uuid>?i=<icon>)` in phase handoffs.
Source: `paperclips/projects/trading/paperclip-agent-assembly.yaml` (canonical agent records on iMac).

**Cross-team handoff rule**: handoffs must go to a Trading agent (listed below).
Other paperclip companies (Gimle, UAudit, etc.) have their own UUIDs; PATCH or
POST targeting a non-Trading UUID returns **404 from paperclip**. Use ONLY the
table below; do not copy UUIDs from any other roster file you may have seen.

This file covers both claude and codex bundle targets (single roster — Trading
uses bare role names without any `TRD*` / `CX*` prefix).

| Role | UUID | Icon | Adapter |
|---|---|---|---|
| CEO | `3649a8df-94ed-4025-a998-fb8be40975af` | `crown` | codex |
| CTO | `4289e2d6-990b-4c53-b879-2a1dc90fe72b` | `shield` | claude |
| CodeReviewer | `8eeda1b1-704f-4b97-839f-e050f9f765d2` | `eye` | codex |
| PythonEngineer | `2705af9c-7dda-464c-9f6c-8d0deb38816a` | `code` | codex |
| QAEngineer | `fbd3d0e4-6abb-4797-83d2-e4dc99dbed44` | `bug` | codex |

`@Board` stays plain (operator-side, not an agent).

### Routing rule (per Trading 7-step workflow)

| Phase | Owner | Formal mention |
|---|---|---|
| 1 Spec | CTO | `[@CTO](agent://4289e2d6-990b-4c53-b879-2a1dc90fe72b?i=shield)` |
| 2 Spec review | CodeReviewer | `[@CodeReviewer](agent://8eeda1b1-704f-4b97-839f-e050f9f765d2?i=eye)` |
| 3 Plan | CTO | `[@CTO](agent://4289e2d6-990b-4c53-b879-2a1dc90fe72b?i=shield)` |
| 4 Impl | PythonEngineer | `[@PythonEngineer](agent://2705af9c-7dda-464c-9f6c-8d0deb38816a?i=code)` |
| 5 Code review | CodeReviewer | `[@CodeReviewer](agent://8eeda1b1-704f-4b97-839f-e050f9f765d2?i=eye)` |
| 6 Smoke | QAEngineer | `[@QAEngineer](agent://fbd3d0e4-6abb-4797-83d2-e4dc99dbed44?i=bug)` |
| 7 Merge | CTO | `[@CTO](agent://4289e2d6-990b-4c53-b879-2a1dc90fe72b?i=shield)` |

CEO (`3649a8df`) is operator-facing only — agents do not hand off to CEO from
within the inner-loop chain.

### Common mistake (cross-company UUID leak)

If a UUID you are about to use does NOT appear in the table above — STOP. It
belongs to a different paperclip company; the PATCH/POST will return 404.
Recover by consulting the table.

Evidence: see `docs/BUGS.md` (Bug 1) for the TRD-4 trace where wrong-roster
UUID caused 404.
