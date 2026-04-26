---
slug: GIM-94-ops-quality-round-2
status: draft (operator review pending)
branch: feature/GIM-94-ops-quality-round-2
paperclip_issue: 94
predecessor: 6fc1d1a (develop tip after GIM-81 merge)
date: 2026-04-26
---

# GIM-94 — Ops-quality round 2 (fragment compression + Phase 4.2 + .env.example)

## Goal

Fix three operational defects discovered in the 2026-04-25/26 N+1 + autonomous-chain session, while **net-reducing** the byte size of `paperclip-shared-fragments`. Today's GIM-82/90/91 added +184 lines (~5.5 KB ≈ 1500 tokens) of mostly postmortem narrative — that loads into every agent run. Compression must dominate the 3 new rules being added.

## Defects to fix

### D1 — Phase 4.2 role boundary not codified

GIM-81 (2026-04-25 19:09): CTO posted "I'll squash-merge once lint is green". PE pushed lint fix and immediately ran `gh pr merge --squash` themselves. Workflow violation, but `mergedBy: ant013` on GitHub gave no signal — all agents share the same token. GitHub-side enforcement cannot work (memory `feedback_single_token_review_gate.md`); discipline must live in fragments + role files.

### D2 — `PAPERCLIP_API_KEY` missing from `.env.example`

Live smoke 2026-04-26 03:55 UTC: `palace.ops.unstick_issue` returned 401 Unauthorized. Container env had `PAPERCLIP_API_KEY=""` because compose wires `${PAPERCLIP_API_KEY:-}` (empty default) and `.env` had no entry. QA Phase 4.1 PASS evidence falsely claimed "Blocker 1 401 FIXED" (tested with manual override or mock). Production deploys would hit the same 401 on first restart.

### D3 — Fragments edits bypass PR review

Audit 2026-04-26 04:00 UTC of `ant013/paperclip-shared-fragments`:
- GIM-82 → PR #7 ✅ (proper)
- GIM-90 commit `3d63d3f` — direct push to main, no PR
- GIM-91 commits `88a6803`, `14ce7d9` — direct push, no PR

Branch protection on fragments `main` is currently disabled. Risk: any agent run with operator's GH token can push broken rules with zero review trail.

### D4 — Fragment density bloat

Today's +184 lines breakdown:
- `worktree-discipline.md` +86 lines (mostly narrative GIM-75/76 incident text)
- `compliance-enforcement.md` +56 lines (verbose evidence-rigor + "how CR enforces" prose)
- `pre-work-discovery.md` +42 lines (long examples + practical-guidance sections)

Same rules can be expressed in ~30 lines total without semantic loss.

## Compression principle (applied to existing + future)

**One imperative line per rule + optional one-line "why" + optional one shell command.**

Forbidden in fragments:
- Multi-paragraph postmortem narratives → move to `docs/postmortems/`
- "How CR enforces" sections with bash → role-specific, move to `paperclips/roles/code-reviewer.md`
- "Practical guidance" with examples → cut; agents will reason

Soft cap per fragment file: **2 KB**. If exceeded, refactor or split.

## Tasks

| # | Task | Owner | Deps |
|---|---|---|---|
| 1 | Compress `fragments/worktree-discipline.md` (3.5 KB → ≤ 2.0 KB) | PE | — |
| 2 | Compress `fragments/compliance-enforcement.md` (4.0 KB → ≤ 2.0 KB) + add D1 rule + D3 rule | PE | — |
| 3 | Compress `fragments/pre-work-discovery.md` (2.3 KB → ≤ 1.5 KB) | PE | — |
| 4 | Add `PAPERCLIP_API_KEY` to `.env.example` + new `docs/runbooks/deploy-checklist.md` step | PE | — |
| 5 | New `fragments/fragment-density.md` (≤ 25 lines) — codify compression principle | PE | — |
| 6 | New `docs/postmortems/2026-04-26-fragment-extraction-postmortems.md` — narrative content moved here | PE | T1, T2, T3 |
| 7 | Setup branch protection on `paperclip-shared-fragments/main` via `gh api PUT` | Operator (Board) | — |
| 8 | Net-byte verification: fragments folder total bytes < pre-GIM-94 baseline | PE (CR verifies) | T1-T6 |

### Task 1 — worktree-discipline.md compression

Current additions to trim (86 lines):

- "Cross-branch carry-over forbidden" — 4-section rule with full GIM-75/76 narrative.
  Compress to:
  ```
  ## Cross-branch carry-over forbidden

  Never carry commits between parallel slice branches via cherry-pick or
  copy-paste. If Slice B's tests need Slice A, declare `depends_on: A`
  in spec and rebase on develop after A merges.

  Why: GIM-75/76 incident (2026-04-24) — see postmortem 2026-04-26.

  CR enforcement: every changed file must be in slice's declared scope.
  ```

- "QA returns production checkout" — 4-section rule with GIM-48 narrative.
  Compress to:
  ```
  ## QA returns checkout to develop after Phase 4.1

  Before run exit, QA on iMac:
      cd /Users/Shared/Ios/Gimle-Palace && git checkout develop && git pull --ff-only

  Verify: `git branch --show-current` outputs `develop`.

  Why: production checkout drives deploys/observability. Incident GIM-48 (2026-04-18).
  ```

Delete: detailed dirty-worktree handling examples, "Practical guidance" subsections. PE/QA agents are intelligent — minimum directive is enough.

### Task 2 — compliance-enforcement.md compression + 2 new rules

**Compress added today** (56 lines → ≤ 20 lines):

- Evidence rigor — keep the imperative + 1-line why. Drop the "Pattern" code blocks, drop "How CR enforces" subsection.
- Scope audit — keep imperative + bash command. Drop the wrap-around explanation.
- MCP wire-contract test rule (GIM-91) — keep imperative + reference test pattern path. Drop the "tests must do X, Y, Z" elaboration; the reference file shows it.

**Add D1 rule** (≤ 6 lines):

```
## Phase 4.2 squash-merge — CTO-only

Only CTO calls `gh pr merge`. Other roles stop after Phase 4.1 PASS:
they may comment, push final fixes, never merge.

Why: shared `ant013` GH token; branch protection cannot enforce actor.
See memory `feedback_single_token_review_gate`.
```

**Add D3 rule** (≤ 4 lines):

```
## Fragment edits go through PR

Never direct-push to `paperclip-shared-fragments/main`. Cut FB, open PR,
get CR APPROVE, squash-merge. Same flow as gimle-palace develop.
```

### Task 3 — pre-work-discovery.md compression

Same shape as T1: keep imperative + one-line why + optional command. Drop multi-paragraph examples and "How to verify" subsections.

### Task 4 — `.env.example` + deploy runbook

In `gimle-palace` (root):

```
# Paperclip API token — required by palace.ops.unstick_issue (GIM-81+)
# Source: ~/.paperclip/auth.json on the deploy host
# Format: pcp_board_<32 hex chars>
PAPERCLIP_API_KEY=
```

Create `docs/runbooks/deploy-checklist.md` (new file) with steps:
1. Pull latest develop
2. `grep -E "^(NEO4J_PASSWORD|OPENAI_API_KEY|PAPERCLIP_API_KEY)=." .env` returns 3 lines (non-empty values)
3. `docker compose --profile review up -d --build --wait`
4. `curl -fsS http://localhost:8080/healthz` returns `{status:ok}`

### Task 5 — `fragments/fragment-density.md` (NEW, ≤ 25 lines)

```
# Fragment density rule

Each fragment rule = imperative one-liner + (optional) one-line "why" +
(optional) one shell command if needed by an agent role.

Forbidden in fragments:
- Multi-paragraph postmortem narratives → `docs/postmortems/<date>-<slug>.md`
- Role-specific bash → `paperclips/roles/<role>.md`
- "Practical guidance" with examples → trust agent reasoning

Soft cap per file: 2 KB. If exceeded, refactor or split.

CR enforces: at Phase 1.2 plan-first review and Phase 3.1 mechanical review,
reject fragment-edit PRs that violate density rule.
```

Reference from `compliance-enforcement.md` (1 line link).

### Task 6 — `docs/postmortems/2026-04-26-fragment-extraction-postmortems.md` (NEW)

Move all narrative content extracted from fragments here. Format:

```
# 2026-04-26 — Fragment narratives extracted (GIM-94)

Postmortems for incidents that previously lived in fragments and bloated
agent prompts. Moved here per GIM-94 fragment-density rule. Fragments
now reference these by date+slug.

## GIM-75/76 carry-over commit incident (2026-04-24)
[narrative from worktree-discipline.md]

## GIM-48 production checkout drift (2026-04-18)
[narrative from worktree-discipline.md]

## GIM-89 palace.code.* arg-forwarding regression (2026-04-25)
[narrative — pertains to GIM-91 fragment]

## GIM-81 Phase 4.2 boundary violation (2026-04-25)
[narrative — pertains to D1 above]
```

### Task 7 — Branch protection on fragments main

```bash
gh api -X PUT /repos/ant013/paperclip-shared-fragments/branches/main/protection \
  --input - <<'JSON'
{
  "required_status_checks": null,
  "enforce_admins": false,
  "required_pull_request_reviews": null,
  "restrictions": null,
  "allow_force_pushes": false,
  "allow_deletions": false
}
JSON
```

Note: `required_pull_request_reviews: null` is intentional — single-token reality (per memory) means no agent can self-approve. Direct-push block is the protection we want; the discipline rule (T2 D3) provides the PR requirement at the workflow layer.

### Task 8 — Net-byte verification

```bash
cd paperclip-shared-fragments
PRE_GIM_94=<HEAD before this PR's submodule pointer bump>
git diff $PRE_GIM_94..HEAD --stat fragments/
# total deletions > total insertions, even after 3 new rules added
```

If insertions > deletions, fail Phase 3.1 review and iterate compression.

## Phase sequence (standard)

| Phase | Agent | Notes |
|---|---|---|
| 1.1 Formalize | CTO | This plan exists; CTO verifies and pushes branch |
| 1.2 Plan-first review | CR | Review this plan for completeness, scope |
| 2 Implement | PE | Tasks 1–6 + 8 (T7 is operator) |
| 3.1 Mechanical | CR | Verify fragment sizes, run net-byte check |
| 3.2 Adversarial | Opus | Verify no semantic loss in compression |
| 4.1 QA | QA | Spawn one fresh agent run, confirm role files load < 32 KB total |
| 4.2 Merge | **CTO ONLY** | Per the new D1 rule landing in this PR |

No chain trigger to next slice — this is end of ops-quality cleanup queue.

## Acceptance summary

1. ✅ All 4 defects (D1-D4) addressed with concrete, enforceable artifacts
2. ✅ Net byte delta on `fragments/` is **negative** vs. pre-GIM-94 baseline
3. ✅ All previously-codified rules from GIM-82/90/91 still expressible (semantic preservation)
4. ✅ Postmortem doc exists with extracted narratives, fragments reference it by date
5. ✅ `PAPERCLIP_API_KEY` documented in `.env.example` + verified in deploy-checklist
6. ✅ Branch protection on fragments main blocks direct-push
7. ✅ New `fragment-density.md` enforced by CR going forward

## Out of scope (defer to N+2 candidates)

- Per-role fragment loading (PE.md grams only PE-relevant rules; CR.md only CR-relevant) — large architectural refactor, file as N+2
- Automated token-budget alarm in `paperclips/build.sh` — defer until compression discipline holds over multiple slices
- Migrating other historical narratives from fragments to memory/postmortems — this slice covers what GIM-82/90/91 added; older narratives left for a later cleanup pass

## Open questions for operator review

1. **Net-byte target tightness:** "≤ pre-GIM-94 baseline" or "≤ pre-GIM-82 baseline (more aggressive)"?
2. **Postmortem doc structure:** one file with 4 sections (current plan) or 4 separate files?
3. **D1 rule placement:** only in `compliance-enforcement.md`, or duplicated in `paperclips/roles/python-engineer.md` so PE sees it without cross-fragment lookup?
4. **`required_pull_request_reviews: null` confirm:** keep null forever, or revisit when separate bot identity is provisioned (separate slice)?
