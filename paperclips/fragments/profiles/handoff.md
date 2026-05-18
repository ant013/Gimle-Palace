## Handoff discipline

When your phase is done, **explicitly transfer ownership**. Never leave an issue as "someone will pick it up". See `handoff/basics.md` for full procedure.

**Iron rule, restated:**
- ONE PATCH + ONE comment + STOP.
- Comment LAST sentence MUST end with `[@<Recipient>](agent://<uuid>?i=<icon>) your turn.` — **period. Nothing after.**
- If you don't know who's next → **handoff to your CTO** (`reportsTo` in manifest). Never drop the issue.

**Pre-handoff checklist (implementer side):**
- Feature branch pushed BEFORE the PATCH (`git push origin <branch>`)
- Evidence in comment body: commit SHA + branch link + concrete test/CI output
- `status=todo` between phases FORBIDDEN
- `status=done` without QA evidence comment FORBIDDEN

**Why so strict:** agents that keep writing past `your turn.` get SIGTERM'd mid-write (paperclip session limit), comment lost or partially saved, chain stalls. Multiple incidents codified this ({{evidence.handoff_flake_issue}} 8h stall).

Background lesson: `paperclips/fragments/lessons/phase-handoff.md`.
