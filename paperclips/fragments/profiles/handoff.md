## Handoff discipline

When your phase is done, explicitly transfer ownership. Never leave an issue as
"someone will pick it up".

Required handoff:

- ALWAYS hand off by PATCHing `status + assigneeAgentId + comment` in one API call, then GET-verify the assignee; @mention-only handoff is invalid.
- push the feature branch before handoff;
- set the next-phase assignee explicitly;
- @mention the next agent in the handoff comment;
- include branch, commit SHA, evidence, and the exact next requested action;
- never leave `status=todo` between phases;
- never mark `done` unless required QA / merge evidence already exists.

Handoff comment format:

```markdown
## Phase N.M complete — [brief result]

[Evidence / artifacts / commits / links]

@<NextAgent> your turn — Phase <N.M+1>: [what to do]
```

Background lesson: `paperclips/fragments/lessons/phase-handoff.md`.
