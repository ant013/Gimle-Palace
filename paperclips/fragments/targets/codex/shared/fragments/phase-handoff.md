## Phase handoff discipline (iron rule)

Between plan phases, **explicit reassign** to next-phase agent. Never leave "someone will pick up".

Before exit: `status=done` OR `assigneeAgentId` set to next agent / your CXCTO. Mandatory. PATCH `status + assigneeAgentId + comment` in one call → GET-verify; mismatch → retry once → still mismatch → `status=blocked` + escalate Board.

### Handoff matrix

| Phase done | Next | Required handoff |
|---|---|---|
| 1.1 Formalization (CTO) | 1.2 Plan-first | `git mv`/rename/`GIM-N` swap on FB directly (no sub-issue) → push → `assignee=CXCodeReviewer` + formal mention |
| 1.2 Plan-first (CR) | 2.x Implementation | `assignee=<implementer>` + formal mention |
| 2 Implementation | 3.1 Mechanical CR | `assignee=CXCodeReviewer` + push done + formal mention |
| 3.1 CR APPROVE | 3.2 Codex | `assignee=CodexArchitectReviewer` + formal mention |
| 3.2 Architect APPROVE | 4.1 QA | `assignee=CXQAEngineer` + formal mention |
| 4.1 QA PASS | 4.2 Merge | `assignee=<merger>` (usually CXCTO) + formal mention |

Sub-issues for Phase 1.1 mechanical work are anti-pattern per `cto-no-code-ban.md` narrowed scope.

### NEVER

- `status=todo` between phases (= unassigned, free to claim).
- `release` lock without simultaneous `PATCH assignee=<next>` — issue hangs ownerless.
- Keep `assignee=me, status=in_progress` after my phase ends — reassign before handoff comment.
- `status=done` without Phase 4.1 evidence comment authored by **CXQAEngineer** (`authorAgentId`).

### Handoff comment format

```
## Phase N.M complete — [brief result]

[Evidence / artifacts / commits / links]

[@<NextAgent>](agent://<NextAgent-UUID>?i=<icon>) your turn — Phase <N.M+1>: [what to do]
```

Formal mention `[@](agent://uuid)` only — not plain `@Role`. Plain works for comments, but handoff needs the formal recovery-wake form. Codex UUIDs in `fragments/local/agent-roster.md`.

### Pre-handoff checklist (implementer → reviewer)

- [ ] `git push origin <feature-branch>` done — commits live on origin
- [ ] Local green (lint + typecheck + test, language-appropriate)
- [ ] CI running on FB (or auto-triggered by push)
- [ ] Handoff comment includes commit SHA + branch link

### Exit Protocol — after handoff PATCH succeeds

After the handoff PATCH returns 200 and GET-verify confirms `assigneeAgentId == <next>`:

- **Stop tool use immediately.** The handoff PATCH is your last tool call. No more bash, curl, serena, gh, or any other tool — even read-only ones.
- Output your final summary as plain assistant text, then end the turn.
- Do **not** re-fetch the issue, do **not** post a second confirmation comment, do **not** check git status. Your phase is closed.

Why: between the PATCH (which changes assignee away from you) and your subprocess exit, paperclip's run-supervisor sees the issue is no longer yours and SIGTERMs the process. Any tool call in that window dies mid-flight, the run is marked `claude_transient_upstream` (Exit 143), and a retry is queued — only to be cancelled with `issue_reassigned` once the next agent picks up.

Evidence: GIM-216 — 11 successful handoffs misclassified as failures because agents kept making tool calls after the PATCH. Pre-slim baseline GIM-193 had zero such failures.

If post-handoff cleanup is genuinely needed (e.g. local worktree state), do it BEFORE the handoff PATCH, not after.

### Pre-close checklist (CXCTO → status=done)

- [ ] Phase 4.2 merged (squash on develop)
- [ ] Phase 4.1 evidence comment exists + `authorAgentId == CXQAEngineer`
- [ ] Evidence: commit SHA + runtime smoke + plan-specific invariant
- [ ] CI green on merge commit (or admin override documented in merge message)
- [ ] Production deploy completed (merge ≠ auto-deploy on most setups)

### Autonomous queue propagation (post-merge)

CXCTO after squash-merge: `PATCH status=done, assignee=null` (per top rule) + POST new issue for next queue position if body lists one. Skip = chain dies.

Any missing → don't close, escalate Board.

### Phase 4.1 QA-evidence comment format

```
## Phase 4.1 — QA PASS ✅

### Evidence
1. Commit SHA: `<git rev-parse HEAD on FB>`
2. `docker compose --profile <x> ps` — containers healthy
3. `/healthz` — `{"status":"ok",...}` (or service equivalent)
4. Real MCP tool call — `palace.<tool>()` + output (not just healthz)
5. Ingest CLI / runtime smoke — command output
6. Plan-specific invariant — e.g. `MATCH (n) RETURN DISTINCT n.group_id`, expected 1 row
7. Production checkout restored to expected branch (per project's checkout-discipline)

[@<merger>](agent://<merger-UUID>?i=<icon>) Phase 4.1 green → Phase 4.2 squash-merge to develop.
```

`/healthz`-only or mocked-DB pytest = insufficient; real runtime smoke required.

### Lock stale edge case

If `POST /release` returns 200 but `executionAgentNameKey` doesn't reset (GIM-52, reported by CodexArchitectReviewer) — try `PATCH assignee=me` → `POST /release` → `PATCH assignee=<next>`. Fails twice → escalate Board with issue id, run id, attempt sequence.

### Self-check before handoff

- Formal mention written (not plain `@`)?
- Current assignee = next agent (GET-verified)?
- Push visible in `git ls-remote origin <branch>` (implementer only)?
- Evidence in my comment is mine, not retold (QA only)?

GET-verify fails after retry → `status=blocked` + `@Board handoff PATCH ok but GET shows actual=<x>, expected=<y>` + stop. Don't exit silently.
