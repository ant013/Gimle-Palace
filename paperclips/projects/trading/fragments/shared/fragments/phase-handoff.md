<!-- derived-from: paperclips/fragments/shared/fragments/phase-handoff.md @ shared-submodule 285bf36 -->
<!-- on shared advance, manually diff and re-derive -->

<!-- paperclip:handoff-contract:v2 -->
## Phase handoff discipline (iron rule)

<!-- paperclip:team-local-roster:v1 -->
> **Naming**: role names in this fragment (`CTO`, `CodeReviewer`, `PythonEngineer`, `QAEngineer`, `CEO`) refer to **Trading** roles directly — no `CX*` / `TRD*` prefix is used. Trading roster lives in `paperclips/projects/trading/overlays/{claude,codex}/_common.md` and the assembly YAML. Always resolve concrete UUIDs via `fragments/local/agent-roster.md` for your team — that's the authoritative mapping.

Between plan phases, **explicit reassign** to next-phase agent. Never leave "someone will pick up".

<!-- paperclip:handoff-exit-shapes:v1 -->
<!-- paperclip:handoff-verify-status-assignee:v1 -->
Before exit: `status=done` OR atomic handoff to next agent (or your CTO) — one PATCH (`status + assigneeAgentId + comment` ending `[@Next](agent://uuid) your turn.`), then GET-verify. Stop. No more output.

Mismatch on verify → retry once; still mismatch → `status=blocked` + escalate Board.

### Handoff matrix

| Phase done | Next | Required handoff |
|---|---|---|
| 1 Spec (CTO) | 2 Spec review (CR) | push spec branch → `assignee=CodeReviewer` + formal mention |
| 2 Spec review (CR) | 3 Plan (CTO) | comment with severity tally (`<N> blockers, <M> major, <K> minor`) → `assignee=CTO` + formal mention |
| 3 Plan (CTO) | 4 Impl (PE) | comment "plan ready" → `assignee=PythonEngineer` + formal mention |
| 4 Impl (PE) | 5 Code review (CR) | **all four required**: `git push origin <feature-branch>` + `gh pr create --base main` + atomic PATCH `status=in_progress + assigneeAgentId=<CR-UUID> + comment="impl ready, PR #N at commit <SHA>"` + formal mention `[@CodeReviewer](agent://<CR-UUID>?i=eye)` |
| 5 Code review (CR) | 6 Smoke (QA) | paste `uv run ruff/mypy/pytest/coverage` output → `assignee=QAEngineer` + formal mention |
| 6 Smoke (QA) | 7 Merge (CTO) | paste live smoke evidence (command output, not just PASS) → `assignee=CTO` + formal mention |

### NEVER

- `status=todo` between phases (= unassigned, free to claim).
- `release` lock without simultaneous `PATCH assignee=<next>` — issue hangs ownerless.
- Keep `assignee=me, status=in_progress` after my phase ends — reassign before handoff comment.
- `status=done` without Phase 6 evidence comment authored by **QAEngineer** (`authorAgentId`).

### Handoff comment format

```
## Phase N complete — [brief result]

[Evidence / artifacts / commits / links]

[@<NextAgent>](agent://<NextAgent-UUID>?i=<icon>) your turn — Phase <N+1>: [what to do]
```

Formal mention `[@](agent://uuid)` only — not plain `@Role`. Plain works for comments, but handoff needs the formal recovery-wake form. UUIDs in `fragments/local/agent-roster.md`.

### Pre-handoff checklist (implementer → reviewer)

- [ ] `git push origin <feature-branch>` done — commits live on origin
- [ ] Local green (lint + typecheck + test, language-appropriate)
- [ ] CI running on FB (or auto-triggered by push)
- [ ] Handoff comment includes commit SHA + branch link

### Pre-close checklist (CTO → status=done)

- [ ] Phase 7 merged (squash on `main`)
- [ ] Phase 6 evidence comment exists + `authorAgentId == QAEngineer`
- [ ] Evidence: commit SHA + runtime smoke + plan-specific invariant
- [ ] CI green on merge commit (or admin override documented in merge message)
- [ ] ROADMAP.md status line `**Status:** ✅ Implemented — PR #<N> (...)` added under the relevant `### X.Yz` heading on the feature branch (lands on `main` via squash)

Any missing → don't close, escalate Board.

### Autonomous queue propagation (post-merge)

CTO after squash-merge: `PATCH status=done, assignee=null` (per top rule) + advance parent `roadmap walker` issue (post comment naming the next sub-section, spawn next child issue). Skip = chain dies.

### Phase 6 QA-evidence comment format

```
## Phase 6 — QA PASS ✅

### Evidence
1. Commit SHA: `<git rev-parse HEAD on FB>`
2. `uv run pytest -q` — pass count + duration
3. Real CLI/runtime smoke — command output (not just "ran")
4. Plan-specific invariant — e.g. validator output, replay manifest hash, fixture parity
5. Production checkout restored to `main` (per project's checkout-discipline)

[@CTO](agent://<CTO-UUID>?i=shield) Phase 6 green → Phase 7 squash-merge to main.
```

`/healthz`-only or mocked-DB pytest = insufficient; real runtime smoke required.

### Lock stale edge case

If `POST /release` returns 200 but `executionAgentNameKey` doesn't reset ({{evidence.release_reset_issue}}) — try `PATCH assignee=me` → `POST /release` → `PATCH assignee=<next>`. Fails twice → escalate Board with issue id, run id, attempt sequence.

### Self-check before handoff

- Formal mention written (not plain `@`)?
- Current assignee = next agent (GET-verified)?
- Push visible in `git ls-remote origin <branch>` (implementer only)?
- Evidence in my comment is mine, not retold (QA only)?

GET-verify fails after retry → `status=blocked` + `@Board handoff PATCH ok but GET shows actual=<x>, expected=<y>` + stop. Don't exit silently.

### Comment ≠ handoff (iron rule)

Writing "Reassigning…" or "handing off…" in a comment body **does not execute** handoff. Only `PATCH /api/issues/{id}` with `assigneeAgentId` triggers the next agent's wake. Without PATCH, issue stalls with previous assignee indefinitely. Precedents: {{evidence.qa_to_cto_stall_issue}}, {{evidence.cr_to_pe_stall_issue}}.
