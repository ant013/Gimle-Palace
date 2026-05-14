## Handoff discipline

When your phase is done, explicitly transfer ownership. Never leave an issue as
"someone will pick it up".

Handoff = one PATCH (`status + assigneeAgentId + comment` ending `[@Next](agent://uuid) your turn.`), then GET-verify — last tool call, end of turn. Mismatch → retry once → still mismatch → `status=blocked` + escalate Board.

- push the feature branch BEFORE the PATCH;
- the PATCH comment body carries branch, commit SHA, evidence, and the formal `[@<Role>](agent://<uuid>?i=<icon>)` mention (UUIDs in `fragments/local/agent-roster.md`);
- never leave `status=todo` between phases;
- never mark `done` unless required QA / merge evidence already exists.

Handoff comment format:

```markdown
## Phase N.M complete — [brief result]

[Evidence / artifacts / commits / links]

[@<NextAgent>](agent://<NextAgent-UUID>?i=<icon>) your turn — Phase <N.M+1>: [what to do]
```

Why formal mention: plain `@Role` can wake ordinary comments, but phase handoff needs a machine-verifiable recovery wake if the assignee PATCH path flakes. {{evidence.handoff_flake_issue}} 8h stall evidence.

Background lesson: `paperclips/fragments/lessons/phase-handoff.md`.
