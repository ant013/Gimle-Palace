# 2026-04-26 — Fragment narratives extracted (GIM-94)

Postmortems for incidents that previously lived in fragments and bloated
agent prompts. Moved here per GIM-94 fragment-density rule. Fragments
now reference these by date+slug.

---

## GIM-75/76 carry-over commit incident (2026-04-24)

**What broke:** PythonEngineer working on GIM-76 carried a GIM-75 chore
commit onto the GIM-76 branch so local tests would pass. Subsequent
cleanup of that carry-over commit accidentally deleted unrelated GIM-76
wiring (`register_code_tools(_tool)`) — the entire GIM-76 deliverable
was dead code.

**Why:** Carry-over was invisible to CR because the commit appeared to
belong to the slice. The deletion happened during "cleanup" squash.

**Fix:** Fragment rule "cross-branch carry-over forbidden" added to
`worktree-discipline.md`. CR Phase 3.1 runs scope-audit grep.

**Cost:** One extra Phase 2/3.1 round-trip; GIM-76 had to be re-delivered.

---

## GIM-48 production checkout drift (2026-04-18)

**What broke:** QA left `/Users/Shared/Ios/Gimle-Palace` checked out on
a feature branch after Phase 4.1 smoke. Subsequent deploys and
observability tooling read stale feature-branch code. Operator had to
run `git reset --hard origin/develop` manually.

**Why:** No explicit rule required QA to restore production checkout
before run exit. Repeated 2026-04-25 14:42 UTC (GIM-77 branch left after Phase 4.1).

**Fix:** Fragment rule "QA returns checkout to develop after Phase 4.1"
added to `worktree-discipline.md`. Verification command included.

---

## GIM-89 palace.code.* arg-forwarding regression (2026-04-25)

**What broke:** `palace.code.search` and related tools silently dropped
arguments that were not in the flat top-level schema. MCP wire contract
was never tested end-to-end — only unit-level mocks were present.

**Why:** GIM-91 added integration-test rule to `compliance-enforcement.md`
after the fact. The test rule existed in prose but wasn't wired as a
compliance checklist item until GIM-91.

**Fix:** MCP wire-contract test rule added to `compliance-enforcement.md`.
Reference test pattern at `tests/mcp/`.

---

## GIM-81 Phase 4.2 boundary violation (2026-04-25)

**What broke:** CTO posted "I'll squash-merge once lint is green". PE
pushed a lint fix and immediately ran `gh pr merge --squash` themselves.
The merge succeeded (`mergedBy: ant013`) because all agents share the
same GitHub token — GitHub-side enforcement is impossible.

**Why:** No fragment rule codified which role owns `gh pr merge`. The
shared-token reality was documented only in operator memory
(`feedback_single_token_review_gate.md`), not in agent-facing fragments.

**Fix:** "Phase 4.2 squash-merge — CTO-only" rule added to
`compliance-enforcement.md` (GIM-94).
