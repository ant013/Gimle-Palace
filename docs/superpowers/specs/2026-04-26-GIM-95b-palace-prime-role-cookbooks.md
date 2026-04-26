---
slug: GIM-95b-palace-prime-role-cookbooks
status: draft (operator review pending)
branch: feature/GIM-95b-palace-prime-role-cookbooks
paperclip_issue: TBD
predecessor: TBD (post-GIM-95a merge SHA)
date: 2026-04-26
parent_initiative: N+2 Category 1 (USE-BUILT)
sequence_position: 3 of 4 — role cookbooks (markdown only, zero code change)
related: GIM-95a (foundation), GIM-96 (write-side)
depends_on: GIM-95a (must merge first)
---

# GIM-95b — `palace.memory.prime` role cookbooks (5 markdown fragments)

## Goal

Replace the 5 stub `role-prime/{cto,codereviewer,pythonengineer,opusarchitectreviewer,qaengineer}.md` fragments shipped in GIM-95a with their full role-specific content. After this slice, all 6 roles supported by `palace.memory.prime` return rich per-role priming snapshots within the ≤ 2000 token budget.

This is **mechanical work** — zero code, zero new module. Just markdown content authoring + submodule update + bundle re-build verification.

## Sequence

Slice 3 of 4 in N+2 Category 1 (USE-BUILT). **Hard dependency on GIM-95a merge** — GIM-95a establishes the architecture (loader, dispatcher, budget enforcement, untrusted-decision rendering policy); this slice fills in 5 markdown fragments using that loader.

## Decisions recorded

Per operator verdict during GIM-95 review:
- All architectural decisions live in GIM-95a (rev2 spec). This slice inherits them.
- Cookbook content respects GIM-94 fragment-density rule (imperative one-liners + minimal context).
- Each role markdown fragment ≤ 1400 tokens (universal core takes ≤ 600 of the 2000 budget).
- No phase auto-detection in v1 — agent reads role-extras and infers their phase from issue context.

## Cookbook content per role

### CTO — `paperclip-shared-fragments/fragments/role-prime/cto.md`

CTO active in Phase 1.1 (Formalize) and Phase 4.2 (Merge). Role context:

```markdown
## CTO role context

Phase 1.1 Formalize:
- Verify spec exists at `docs/superpowers/specs/<date>-<slug>-design.md`
- Cut clean FB from current develop tip; verify `git log HEAD ^origin/develop` is empty
- Verify `depends_on:` in spec frontmatter — all listed slices merged on develop
- Write plan at `docs/superpowers/plans/<date>-GIM-N-<slug>.md`
- Reassign to CodeReviewer for Phase 1.2

Phase 4.2 Merge (CTO-ONLY per compliance-enforcement.md):
- Verify CI green: `gh pr view <PR> --json statusCheckRollup`
- Verify QA Phase 4.1 evidence comment present
- Verify Phase 3.2 Opus APPROVE present
- `gh pr merge <N> --squash --delete-branch`

Useful tools:
- palace.memory.lookup(entity_type="Decision", filters={"decision_maker_claimed": "cto"}, limit=5) — past CTO decisions
- palace.memory.health() — verify before merge
- palace.memory.decide(...) — record after merge: decision_kind="board-ratification" or "spec-revision"
```

### CodeReviewer — `paperclip-shared-fragments/fragments/role-prime/codereviewer.md`

CR active in Phase 1.2 (plan-first), 3.1 (mechanical), 3.2 (adversarial substitution). Role context:

```markdown
## CodeReviewer role context

Phase 1.2 Plan-first review:
- Read `docs/superpowers/plans/<slice>.md`
- Verify each task: test+impl+commit pattern, concrete acceptance, dependency closure
- REQUEST CHANGES if vague or missing CR/PE/Opus/QA assignments

Phase 3.1 Mechanical:
- Run: `cd services/palace-mcp && uv run ruff check && uv run ruff format --check && uv run mypy src/ && uv run pytest`
- Paste full output in APPROVE comment (anti-rubber-stamp rule, compliance-enforcement.md)
- Scope audit: `git log origin/develop..HEAD --name-only | sort -u` — every file in slice's declared scope

Useful tools:
- palace.code.search_graph(qn_pattern="<scope>", project="repos-gimle") — what's in scope
- palace.code.query_graph(query="MATCH (s:Symbol) WHERE s.qualified_name CONTAINS '<scope>' RETURN count(s)", project="repos-gimle") — scope sizing
- palace.memory.lookup(entity_type="Decision", filters={"decision_maker_claimed": "codereviewer"}, limit=5) — past reviews
- palace.memory.decide(...) — record APPROVE/REJECT: decision_kind="review-approve" or "scope-change"
```

### PythonEngineer — `paperclip-shared-fragments/fragments/role-prime/pythonengineer.md`

PE active in Phase 2 (Implementation). Role context:

```markdown
## PythonEngineer role context

Phase 2 Implementation:
- Read plan tasks from `docs/superpowers/plans/<slice>.md`
- Discipline reminders (compliance-enforcement.md):
  - Phase 4.2 squash-merge — CTO-only. Push final fix and stop.
  - MCP wire-contract test rule (GIM-91) — any new @mcp.tool needs streamablehttp_client integration test
  - Use `gh pr create --body-file` (NOT inline `--body`)

Useful tools:
- palace.code.get_code_snippet(qualified_name="...", project="repos-gimle") — read existing code before editing
- palace.code.search_graph(name_pattern="...", project="repos-gimle") — find similar implementations
- palace.code.trace_call_path(function_name="...", project="repos-gimle", mode="callees") — what would my edit affect
- palace.memory.lookup(entity_type="Decision", filters={"decision_maker_claimed": "pythonengineer"}, limit=3) — past similar work
- palace.memory.decide(...) — record at end of Phase 2: decision_kind="design"
```

### OpusArchitectReviewer — `paperclip-shared-fragments/fragments/role-prime/opusarchitectreviewer.md`

Opus active in Phase 3.2 (adversarial). Role context:

```markdown
## OpusArchitectReviewer role context

Phase 3.2 Adversarial review:
- Read PR diff: `gh pr view <N> --json additions,deletions,files`
- Categories to check (anti-rubber-stamp, compliance-enforcement.md):
  - Security: input validation, secrets, SSH key safety
  - Error handling: silent failures, fallback paths
  - API stability: external library version pin, deprecated methods
  - Test coverage: real MCP integration test (GIM-91 rule), no mock-substrate happy-path
  - Spec drift: any plan task missing from commits = red flag

Useful tools:
- palace.code.query_graph(query="MATCH (n:Function) WHERE n.qualified_name CONTAINS '<changed file>' RETURN n.name, n.in_degree, n.out_degree", project="repos-gimle") — coupling = risk
- palace.code.search_code(pattern="except:|except Exception", project="repos-gimle") — bare except hunt
- palace.memory.lookup(entity_type="Decision", filters={"decision_maker_claimed": "opusarchitectreviewer"}, limit=5) — past adversarial findings
- palace.memory.decide(...) — record verdict: decision_kind="review-approve" with confidence rubric
```

### QAEngineer — `paperclip-shared-fragments/fragments/role-prime/qaengineer.md`

QA active in Phase 4.1 (Live smoke). Role context:

```markdown
## QAEngineer role context

Phase 4.1 Live smoke:
- Spec acceptance section in `docs/superpowers/specs/<slice>-design.md`
- Pre-flight: `docker compose --profile review up -d --build --wait` (deploy-checklist.md GIM-94)
- Auth-path probe per GIM-94 deploy-checklist Step 5

Discipline (post-Phase 4.1):
- Restore production checkout to develop:
    cd /Users/Shared/Ios/Gimle-Palace && git checkout develop && git pull --ff-only
- Verify: `git branch --show-current` outputs `develop`
- Per worktree-discipline.md (GIM-90)

Useful tools:
- palace.memory.health() — pre-smoke + post-smoke comparison
- palace.code.search_graph(label="Function", name_pattern="<smoke target>", project="repos-gimle") — verify symbol exists in CM after rebuild
- palace.memory.lookup(entity_type="Symbol", filters={"qualified_name_contains": "<target>"}, limit=2) — verify bridge wrote target
- palace.memory.decide(...) — record post-smoke verdict: decision_kind="review-approve" with evidence_ref of PR URL
```

## Tasks

| # | Task | Owner | Deps |
|---|---|---|---|
| 1 | Replace `paperclip-shared-fragments/fragments/role-prime/cto.md` stub with full content above | PE | GIM-95a merged |
| 2 | Replace `role-prime/codereviewer.md` stub | PE | GIM-95a merged |
| 3 | Replace `role-prime/pythonengineer.md` stub | PE | GIM-95a merged |
| 4 | Replace `role-prime/opusarchitectreviewer.md` stub | PE | GIM-95a merged |
| 5 | Replace `role-prime/qaengineer.md` stub | PE | GIM-95a merged |
| 6 | Submodule update PR + merge to `paperclip-shared-fragments/main` (per GIM-94 D3 rule) | PE | T1-T5 |
| 7 | Bump submodule pointer in `gimle-palace` feature branch | PE | T6 |
| 8 | Token budget verification — `/prime <each role>` returns ≤ 2000 estimated tokens | QA | T7 |
| 9 | Per-role acceptance — operator runs `/prime cto`, `/prime codereviewer`, etc. and verifies role-specific bullet appears (e.g. "Phase 4.2 squash-merge — CTO-only" in `/prime cto` output) | QA | T7 |

## Acceptance

1. All 5 role markdown fragments contain full content (NOT stub messages mentioning GIM-95b)
2. `/prime cto`, `/prime codereviewer`, `/prime pythonengineer`, `/prime opusarchitectreviewer`, `/prime qaengineer` each return their role-specific section
3. Token budget: each role's prime output `estimate_tokens(content) ≤ 2000`
4. `palace.code.query_graph` example invocations in cookbooks reference real symbols/queries — not placeholder text
5. Each cookbook references at least one `palace.memory.lookup` filter using new `decision_maker_claimed` whitelist entry (validates GIM-96 + 95a + 95b round-trip)
6. Each cookbook recommends `palace.memory.decide` with appropriate `decision_kind` for that role's typical Phase

## Out of scope

- New code — this slice is markdown-only
- New `palace.memory.*` or `palace.code.*` tools — all consumed are pre-existing
- Phase-aware sub-priming (e.g. `/prime cr 1.2` vs `/prime cr 3.1`) — separate refinement slice
- Cookbook content tuning post-observation — separate slice after we see how agents use them

## Open questions for operator review

1. **Cookbook content granularity** — current cookbooks have ~15-20 lines each. Is this the right depth, or should they be tighter (~10 lines, fragment-density rule pressure) or richer (~30 lines, fully phase-detailed)?

2. **Phase-detection placeholder** — cookbooks above implicitly assume one phase per role (e.g., CTO at 1.1+4.2 covered in same cookbook). Should we add explicit phase guards (e.g., "If you are at Phase 1.1, use these tools; if 4.2, use those") or let agent reason?

3. **`Useful tools` ordering** — currently each cookbook lists ~5-7 tools in arbitrary order. Should we rank by frequency-of-use (most-used first) or by phase-progression (sequenced as agent would invoke)?

## References

- GIM-95a — foundation slice (this slice depends on it)
- GIM-96 — write-side `:Decision` (consumed by all 5 cookbooks via `decide(...)` recommendations)
- GIM-94 — fragment density rule (this slice's cookbooks respect it)
- GIM-91 — MCP wire-contract test rule (referenced in PE/Opus/QA cookbooks)
- `paperclip-shared-fragments/fragments/compliance-enforcement.md` — discipline reminders
- `paperclip-shared-fragments/fragments/worktree-discipline.md` — QA cleanup rule
