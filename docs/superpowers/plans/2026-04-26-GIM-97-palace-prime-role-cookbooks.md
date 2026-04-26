# GIM-97 — palace.memory.prime 5 role cookbooks

**Spec:** `docs/superpowers/specs/2026-04-26-GIM-95b-palace-prime-role-cookbooks.md` (rev2)
**Branch:** `feature/GIM-95b-palace-prime-role-cookbooks`
**Predecessor:** `77b58f5` (GIM-96 squash-merge)
**Scope:** Markdown-only. Zero code changes. 5 role-prime fragments + submodule update.

## Steps

### Step 1 — Write 5 role cookbook fragments (PythonEngineer)

Replace stub content in each file with the full cookbook from the spec (§ Cookbook content per role).

| File | Role | Key content |
|---|---|---|
| `paperclips/fragments/shared/fragments/role-prime/cto.md` | CTO | Phase 1.1 + 4.2 guards, lookup/decide tools |
| `paperclips/fragments/shared/fragments/role-prime/codereviewer.md` | CodeReviewer | Phase 1.2 + 3.1 guards, search_graph/decide tools |
| `paperclips/fragments/shared/fragments/role-prime/pythonengineer.md` | PythonEngineer | Phase 2 guards, code tools, decide |
| `paperclips/fragments/shared/fragments/role-prime/opusarchitectreviewer.md` | OpusArchitectReviewer | Phase 3.2 guards, query_graph/search_code, decide |
| `paperclips/fragments/shared/fragments/role-prime/qaengineer.md` | QAEngineer | Phase 4.1 guards, health/lookup, decide |

**Acceptance:**
- Each file ≤ 1400 tokens (universal core takes ≤ 600 of 2000 budget)
- Phase guards inline per Q7 verdict (explicit "If at Phase X, do Y")
- Tool ordering follows phase-progression per Q8 verdict
- Each cookbook references `palace.memory.lookup` with `decision_maker_claimed` filter
- Each cookbook references `palace.memory.decide` with role-appropriate `decision_kind`
- Fragment density matches GIM-94 rule (imperative one-liners + minimal context)

**Affected files:** `paperclips/fragments/shared/fragments/role-prime/{cto,codereviewer,pythonengineer,opusarchitectreviewer,qaengineer}.md`
**Dependencies:** GIM-95a merged (provides loader/dispatcher)
**Owner:** PythonEngineer

### Step 2 — Submodule update (PythonEngineer)

Commit the 5 changed files in `paperclips/fragments/shared`, push to `paperclip-shared-fragments/main` per GIM-94 D3 rule. Then bump the submodule pointer in `gimle-palace` feature branch.

**Acceptance:**
- `git submodule status` shows updated SHA
- `git diff --cached -- paperclips/fragments/shared` confirms pointer advance

**Affected files:** `paperclip-shared-fragments` (submodule pointer)
**Dependencies:** Step 1
**Owner:** PythonEngineer

### Step 3 — Token budget + per-role acceptance smoke (QAEngineer)

On iMac with `--profile review`:
- Run `/prime <role>` for all 6 roles (5 new + operator baseline)
- Verify each returns role-specific section (not stub text)
- Verify token estimate ≤ 2000 per role
- Verify `palace.code.query_graph` example invocations reference real symbols
- Verify each cookbook recommends `palace.memory.decide` with appropriate `decision_kind`

**Acceptance:** Per spec § Acceptance items 1-6
**Dependencies:** Step 2
**Owner:** QAEngineer

## Phase sequence

| Phase | Agent | What |
|---|---|---|
| 1.1 Formalize | CTO | Verify spec, create plan, push — **this phase** |
| 1.2 Plan-first review | CodeReviewer | Validate plan tasks have concrete acceptance |
| 2 Implementation | PythonEngineer | Steps 1-2 |
| 3.1 Mechanical review | CodeReviewer | Scope audit (markdown-only, no code drift) |
| 3.2 Adversarial review | OpusArchitectReviewer | Content quality, tool reference accuracy |
| 4.1 Live smoke | QAEngineer | Step 3 |
| 4.2 Merge | CTO | Squash-merge to develop, chain-end summary |
