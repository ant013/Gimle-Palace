## Heartbeat discipline

On every wake (heartbeat or event) check only **three** things:

1. **First Bash on wake:** `echo "TASK=$PAPERCLIP_TASK_ID WAKE=$PAPERCLIP_WAKE_REASON"`. If `TASK` non-empty → `GET /api/issues/$PAPERCLIP_TASK_ID` + work. **Do NOT exit** on `inbox-lite=[]` if `TASK` is set — paperclip always provides TASK_ID for mention-wakes.
2. `GET /api/agents/me` → any issue with `assigneeAgentId=me` and `in_progress`? → continue.
3. Comments / @mentions with `createdAt > last_heartbeat_at`? → reply.

None of three → **exit immediately** with `No assignments, idle exit`. Each idle heartbeat must cost **<500 tokens**.

### Cross-session memory — FORBIDDEN

If you "remember" past work at session start (*"let me continue where I left off"*) — that's session cache, not reality. Only source of truth is the Paperclip API:

- Issue exists, assigned to you now → work
- Issue deleted / cancelled / done → don't resurrect, don't reopen, don't write code "from memory"
- Don't remember the issue ID from the current prompt? It doesn't exist — query `GET /api/companies/{id}/issues?assigneeAgentId=me`.

Board cleans the queue regularly. If a resumed session "reminds" you of something — galaxy brain, ignore and wait for an explicit assignment.

### Forbidden on idle heartbeat

- Taking `todo` issues nobody assigned to you. Unassigned ≠ "I'll find work"
- Taking `todo` with `updatedAt > 24h` without fresh Board confirm (stale)
- Checking git / logs / dashboards "just in case"
- Self-checkout to an issue without an explicit assignment
- Creating new issues for "discovered problems" without Board request

### Source of truth

Work starts **only** from: (a) Board/CEO/manager created/assigned an issue this session, (b) someone @mentioned you with a concrete task, (c) `PAPERCLIP_TASK_ID` was passed at wake. Else — ignore.

### @-mentions: trailing space for plain mentions

Paperclip's parser captures trailing punctuation into the name (e.g. `@CTO:` becomes `CTO:`), the mention doesn't resolve, no wake is queued — **chain silently stalls**.

**Right:** `@CTO need a fix`, `@CodeReviewer, final review`
**Wrong:** `@CTO: need a fix`, `@iOSEngineer;`, `(@CodeReviewer)` — punctuation goes after the space.

### Handoff: always formally mention the next agent

End of phase → **always formal-mention** next agent in the comment, even if already assignee:

```
[@CXCodeReviewer](agent://<uuid>?i=<icon>) your turn
```

Use the local agent roster for UUID/icon. Plain `@Role` can wake ordinary comments, but phase handoff requires the formal form so the recovery path is explicit and machine-verifiable.

Endpoint difference:
- `POST /api/issues/{id}/comments` — wakes assignee (if not self-comment, issue not closed) + all @-mentioned.
- `PATCH /api/issues/{id}` with `comment` — wakes **ONLY** if assignee changed, moved out of backlog, or body has @-mentions. No-mention comment on PATCH **won't wake assignee** → silent stall.

**Rule:** handoff comment always includes a formal mention. Covers both paths and the retry/escalation rule in `phase-handoff.md`.

**Self-checkout on explicit handoff:** got an @-mention with explicit handoff phrase (`"your turn"`, `"pick it up"`, `"handing over"`) and sender already pushed → `POST /api/issues/{id}/checkout` yourself, don't wait for formal reassign.

Example:
```
POST /api/issues/{id}/comments
body: "[@CXCodeReviewer](agent://<uuid>?i=eye) fix ready ([GIM-29](/GIM/issues/GIM-29)), please re-review"
```

### HTTP 409 on close/update — execution lock conflict

`PATCH /api/issues/{id}` → **409** = another agent's execution lock. Holder is in `issues.execution_agent_name_key`. Typical: implementer tries to close, but CTO assigned and didn't release the lock → 409 → issue hangs.

**Do:**

1. `GET /api/issues/{id}` → read `executionAgentNameKey`.
2. Comment to holder: `"@CTO release execution lock on [GIM-5], I'm ready to close"`.
3. Alternative — if holder unavailable, `PATCH ... assigneeAgentId=<original-assignee>` → originator closes.
4. Don't retry close with the same JWT — without release, 409 keeps coming.

**Don't:**
- Direct SQL `UPDATE execution_run_id=NULL` — bypasses paperclip business logic (see §6.7 ops doc).
- Create a new issue copy — loses comment + review history.

Release (from holder):
```
POST /api/issues/{id}/release
# lock released, assignee can close via PATCH
```
