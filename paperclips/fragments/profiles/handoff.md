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

### Exit Protocol — after handoff PATCH succeeds

After the handoff PATCH returns 200 and GET-verify confirms `assigneeAgentId == <next>`:

- **Stop tool use immediately.** The handoff PATCH is your last tool call. No more bash, curl, serena, gh, or any other tool — even read-only ones.
- Output your final summary as plain assistant text, then end the turn.
- Do **not** re-fetch the issue, do **not** post a second confirmation comment, do **not** check git status. Your phase is closed.

Why: between the PATCH (which changes assignee away from you) and your subprocess exit, paperclip's run-supervisor sees the issue is no longer yours and SIGTERMs the process. Any tool call in that window dies mid-flight, the run is marked `claude_transient_upstream` (Exit 143), and a retry is queued — only to be cancelled with `issue_reassigned` once the next agent picks up.

Evidence: GIM-216 — 11 successful handoffs misclassified as failures because agents kept making tool calls after the PATCH. Pre-slim baseline GIM-193 had zero such failures.

If post-handoff cleanup is genuinely needed (e.g. local worktree state), do it BEFORE the handoff PATCH, not after.

Background lesson: `paperclips/fragments/lessons/phase-handoff.md`.
