## Handoff discipline

When your phase is done, explicitly transfer ownership. Never leave an issue as
"someone will pick it up".

Handoff:

- ALWAYS hand off by PATCHing `status + assigneeAgentId + comment` in one API call, then GET-verify the assignee; on mismatch retry once with the same payload, then mark `status=blocked` and escalate to Board with `assigneeAgentId.actual` != `expected`. @mention-only handoff is invalid.
- push the feature branch before handoff;
- set the next-phase assignee explicitly;
- @mention the next agent **in formal markdown form** `[@<Role>](agent://<uuid>?i=<icon>)`, not plain `@<Role>` — see `fragments/local/agent-roster.md` for UUIDs;
- include branch, commit SHA, evidence, and the exact next requested action;
- never leave `status=todo` between phases;
- never mark `done` unless required QA / merge evidence already exists.

Handoff comment format:

```markdown
## Phase N.M complete — [brief result]

[Evidence / artifacts / commits / links]

[@<NextAgent>](agent://<NextAgent-UUID>?i=<icon>) your turn — Phase <N.M+1>: [what to do]
```

Why formal mention: plain `@Role` can wake ordinary comments, but phase handoff needs a machine-verifiable recovery wake if the assignee PATCH path flakes. GIM-182 8h stall evidence.

Background lesson: `paperclips/fragments/lessons/phase-handoff.md`.
