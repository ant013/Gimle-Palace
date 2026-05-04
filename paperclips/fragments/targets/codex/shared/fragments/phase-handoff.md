## Phase handoff discipline (iron rule)

Between plan phases (§8), always **explicit reassign** to the next-phase agent. Never leave "someone will pick up".

ALWAYS hand off by PATCHing `status + assigneeAgentId + comment` in one API call, then GET-verify the assignee. If verification mismatches, retry once with the same payload; if it still mismatches, mark `status=blocked` and escalate to Board with `assigneeAgentId.actual` != `expected`. Do not silently exit (work pushed to git but handoff dropped = 8h stall, GIM-182 evidence). @mention-only handoff is invalid.

GIM-48 evidence: CR set `status=todo` after approve instead of `assignee=CXQAEngineer`; CTO closed without QA evidence; merged code crashed on iMac. QA was skipped **because ownership was not transferred**.

### Handoff matrix

| Phase done | Next phase | Required handoff |
|---|---|---|
| 1.1 Formalization (CTO) | 1.2 Plan-first review | CTO does `git mv` / rename / `GIM-57` swap **on the feature branch directly** (no sub-issue), pushes, then `assignee=CXCodeReviewer` + formal mention. Sub-issues for Phase 1.1 mechanical work are anti-pattern per the narrowed `cto-no-code-ban.md` scope. |
| 1.2 Plan-first (CR) | 2.x Implementation | `assignee=<implementer>` + formal mention |
| 2 Implementation | 3.1 Mechanical review | `assignee=CXCodeReviewer` + formal mention + **git push done** |
| 3.1 CR APPROVE | 3.2 Codex adversarial | `assignee=CodexArchitectReviewer` + formal mention |
| 3.2 Architect APPROVE | 4.1 QA live smoke | `assignee=CXQAEngineer` + formal mention |
| 4.1 QA PASS | 4.2 Merge | `assignee=<merger>` (usually CXCTO) + formal mention |

### NEVER

- `status=todo` between phases. `todo` = "unassigned, free to claim" — phases require **explicit assignee**.
- `release` execution lock without simultaneous `PATCH assignee=<next-phase-agent>` — issue hangs ownerless.
- Keeping `assignee=me, status=in_progress` after my phase ends. Reassign before writing the handoff comment.
- `status=done` without verifying Phase 4.1 evidence-comment exists **from the right agent** (QAEngineer, not implementer or CR).

### Handoff comment format

```
## Phase N.M complete — [brief result]

[Evidence / artifacts / commits / links]

[@<NextAgent>](agent://<NextAgent-UUID>?i=<icon>) your turn — Phase <N.M+1>: [what to do]
```

Use formal mention `[@<Role>](agent://<uuid>?i=<icon>)`, not plain `@<Role>`. Plain mentions are OK for comments, but not handoff evidence: formal form is the recovery wake when assignee PATCH flakes.

See `fragments/local/agent-roster.md` for Codex UUIDs. Paperclip UI `@` auto-formats.

### Pre-handoff checklist (implementer → reviewer)

Before writing "Phase 2 complete — [@CXCodeReviewer](agent://<uuid>?i=<icon>)":

- [ ] `git push origin <feature-branch>` done — commits live on origin
- [ ] Local green: `uv run ruff check && uv run mypy src/ && uv run pytest` (or language equivalent)
- [ ] CI on feature branch running (or auto-triggered by push)
- [ ] PR open, or will open at Phase 4.2 (per plan §8)
- [ ] Handoff comment includes **commit SHA** and branch link, not just "done"

Skip any → CR gets "done" on code not on origin → dead end.

### Pre-close checklist (CTO → status=done)

- [ ] Phase 4.2 merge done (squash commit on develop / main)
- [ ] Phase 4.1 evidence-comment **exists** and is authored by **CXQAEngineer** (`authorAgentId`)
- [ ] Evidence contains: commit SHA, runtime smoke (healthcheck / tool call), plan-specific invariant check (e.g. `MATCH ... RETURN DISTINCT n.group_id`)
- [ ] CI green on merge commit (or admin override documented in merge message with reason)
- [ ] Production deploy completed post-merge (merge ≠ auto-deploy on most setups — follow the project's deploy playbook)

Any item missing → **don't close**. Escalate to Board (`@Board evidence missing on Phase 4.1 before close`).

### Phase 4.1 QA-evidence comment format

Reference:

```
## Phase 4.1 — QA PASS ✅

### Evidence

1. Commit SHA tested: `<git rev-parse HEAD on feature branch>`
2. `docker compose --profile <x> ps` — [containers healthy]
3. `/healthz` — `{"status":"ok","neo4j":"reachable"}` (or service equivalent)
4. MCP tool: `palace.memory.<tool>()` → [output] (real MCP call, not just healthz)
5. Ingest CLI / runtime smoke — [command output]
6. Direct invariant check (plan-specific) — e.g. `MATCH (n) RETURN DISTINCT n.group_id`, expected 1 row
7. After QA — restore the production checkout to the expected branch (follow the project's checkout-discipline rule)

[@<merger>](agent://<merger-UUID>?i=<icon>) Phase 4.1 green, handing to Phase 4.2 — squash-merge to develop.
```

`/healthz`-only evidence is insufficient; it can be green while functionality is broken. Mocked-DB pytest output does NOT count — real runtime smoke required.

### Lock stale edge case

If `POST /release` returns 200 but `executionAgentNameKey` doesn't reset (GIM-52 Phase 4.1, reported by CodexArchitectReviewer) — **don't ignore**.

Observed workaround (GIM-52, GIM-53): `PATCH assignee=me` → `POST /release` → `PATCH assignee=<next>` clears it. Try this first.

If the workaround fails twice — escalate to Board with details (issue id, run id, attempt sequence). Either paperclip bug or endpoint rename — Board decides.

### Self-check before handoff

- "Did I write `[@NextAgent](agent://<uuid>?i=<icon>)` in formal form, not plain `@NextAgent`?" — must be formal
- "Is current assignee the next agent or still me?" — must be next
- "Did GET-verify after the PATCH return `assigneeAgentId == <next-agent-UUID>`?" — must be yes
- "Is my push visible in `git ls-remote origin <branch>`?" — must be yes for implementer handoff
- "Is the evidence in my comment mine, or did I retell someone else's work?" — for QA, only own evidence counts

If GET-verify fails after retry, **do not exit silently**. Mark `status=blocked`, post `@Board handoff PATCH succeeded but GET shows assigneeAgentId=<actual>, expected=<next>`, and stop.
