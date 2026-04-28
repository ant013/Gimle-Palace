# GIM-108: Phase 4.2 merge-readiness discipline

**Issue:** GIM-108
**Created:** 2026-04-28
**Grounded in:** `b8adf43` (develop tip), `1c76fa9` (shared-fragments tip)
**Predecessor SHAs:** `3c7ba7d` (GIM-102), `b8adf43` (GIM-106), GIM-104 PR #57 (pending)

## Problem

Two false-blocker escalations in 24h during Phase 4.2 merge attempts:

1. **GIM-102:** "self-approval rejected" — `required_pull_request_reviews` was already removed (GIM-59). One `gh api` call would have shown it.
2. **GIM-104:** "GitHub Actions returned 0 checks" — `gh pr view --json statusCheckRollup` shows 7 SUCCESS; real issue was `mergeStateStatus: BEHIND`. Fix: `gh pr update-branch`.

Root cause: no mandatory evidence-gathering step before escalation on merge blockers. Symmetric gap — code review already has anti-rubber-stamp discipline (paste test output); merge-readiness does not.

## Solution

Extend `git-workflow.md` shared fragment with Phase 4.2 reality-check section. Wire into CTO and CodeReviewer role files. Bump submodule in Gimle-Palace.

---

## Tasks

### Task 1: Author `git-workflow.md` extension in `paperclip-shared-fragments`

**Owner:** TechnicalWriter (if hired), otherwise CTO (docs scope exception)
**Affected files:** `paperclip-shared-fragments/fragments/git-workflow.md`
**Dependencies:** none

**Description:** Add section `### Phase 4.2 — Merge-readiness reality-check` to `git-workflow.md` containing:

1. **Mandatory pre-escalation commands** — 3 `gh` commands agents must run and paste before claiming any merge blocker.
2. **`mergeStateStatus` decoder table** — 8 values (CLEAN, BEHIND, DIRTY, BLOCKED, UNSTABLE, UNKNOWN, DRAFT, HAS_HOOKS) with meaning + fix action. Note: `DRAFT` is deprecated by GitHub (use `PullRequest.isDraft` instead) but `gh pr view --json mergeStateStatus` still returns it.
3. **Forbidden response patterns** — 4 specific claim patterns that are banned without evidence output.
4. **Self-approval clarification** — GitHub global rule vs branch-protection distinction.

**Acceptance criteria:**
- [ ] New section appended after `### What applies to Board, too` in `git-workflow.md`
- [ ] All 4 sub-blocks present (commands, decoder table, forbidden patterns, self-approval)
- [ ] Decoder table covers all 8 `mergeStateStatus` values (incl. DRAFT with deprecation note, HAS_HOOKS for GHE pre-receive hooks)
- [ ] Cross-references `feedback_single_token_review_gate` in operator memory

**Commit:** `docs(GIM-108): Phase 4.2 merge-readiness reality-check in git-workflow.md`

---

### Task 2: Wire Phase 4.2 reference into `paperclips/roles/cto.md`

**Owner:** CTO (role-file scope — allowed per `cto-no-code-ban.md`)
**Affected files:** `paperclips/roles/cto.md`
**Dependencies:** Task 1 merged in shared-fragments

**Description:** Add one-line reference as item 5 in `## Verification gates (critical)` section (after item 4 "Build check:", line 42 in current `cto.md`):
> 5. **Merge-readiness reality-check:** Before claiming any merge-blocker, paste output of `gh pr view --json mergeStateStatus,mergeable,statusCheckRollup,reviewDecision,headRefOid` in the same comment. See `git-workflow.md § Phase 4.2 — Merge-readiness reality-check`.

Note: `git-workflow.md` is already `@include`'d in `cto.md` (line 60) — the new fragment section will render automatically via submodule bump. This line is a cross-reference in the role-file prose, not a new `@include`.

**Acceptance criteria:**
- [ ] Line present in `cto.md` as item 5 in `## Verification gates (critical)`, after item 4 ("Build check:")
- [ ] References the exact fragment section anchor

**Commit:** `docs(GIM-108): wire Phase 4.2 reality-check ref into cto.md`

---

### Task 3: Wire Phase 4.2 reference into `paperclips/roles/code-reviewer.md`

**Owner:** CTO (role-file scope)
**Affected files:** `paperclips/roles/code-reviewer.md`
**Dependencies:** Task 1 merged in shared-fragments

**Description:** `code-reviewer.md` has `### Phase 3.1 GitHub PR review bridge` (line 117) but no Phase 4.2 section. Add a new `### Phase 4.2 merge-readiness` subsection after the Phase 3.1 block (after line ~145, before `<!-- @include fragments/shared/fragments/escalation-blocked.md -->`):

```markdown
### Phase 4.2 merge-readiness (when CR is merger)

Before claiming any merge-blocker, paste output of `gh pr view --json mergeStateStatus,mergeable,statusCheckRollup,reviewDecision,headRefOid` in the same comment. See `git-workflow.md § Phase 4.2 — Merge-readiness reality-check`.
```

Note: `git-workflow.md` is already `@include`'d in `code-reviewer.md` (line 148). The new fragment section renders automatically via submodule bump. This subsection is a cross-reference in the role-file prose, not a new `@include`.

**Acceptance criteria:**
- [ ] New `### Phase 4.2 merge-readiness` subsection present in `code-reviewer.md` after the Phase 3.1 block, before the `@include escalation-blocked.md` line
- [ ] References the exact fragment section anchor

**Commit:** `docs(GIM-108): wire Phase 4.2 reality-check ref into code-reviewer.md`

---

### Task 4: Bump submodule pointer in Gimle-Palace

**Owner:** CTO
**Affected files:** `paperclips/fragments/shared` (submodule ref)
**Dependencies:** Task 1 PR merged in `paperclip-shared-fragments`

**Description:** Update submodule `paperclips/fragments/shared` to the new SHA that includes the `git-workflow.md` extension.

**Acceptance criteria:**
- [ ] `git submodule update` points to SHA containing Task 1 content
- [ ] `git diff --submodule` shows the forward bump

**Commit:** `build(GIM-108): bump shared-fragments submodule to include Phase 4.2 reality-check`

---

### Task 5: Verify build output

**Owner:** CTO / CR
**Affected files:** `paperclips/dist/cto.md`, `paperclips/dist/code-reviewer.md`
**Dependencies:** Tasks 2, 3, 4

**Description:** Run `bash paperclips/build.sh` and verify that `dist/cto.md` and `dist/code-reviewer.md` contain the new Phase 4.2 content. Verify no regression in other dist files.

**Acceptance criteria:**
- [ ] `grep -c "Merge-readiness reality-check" paperclips/dist/cto.md` returns 1+
- [ ] `grep -c "Merge-readiness reality-check" paperclips/dist/code-reviewer.md` returns 1+
- [ ] All existing dist files still render (no regression)

**Failure criteria:** If `grep` returns 0, verify in order:
1. Submodule SHA includes Task 1 content: `cd paperclips/fragments/shared && git log --oneline -3` — must show the Task 1 commit.
2. `@include` line resolves: `grep "git-workflow.md" paperclips/roles/cto.md` — must show `<!-- @include fragments/shared/fragments/git-workflow.md -->`.
3. `build.sh` ran without errors: re-run `bash paperclips/build.sh 2>&1` and inspect stderr for include resolution failures.

**Commit:** no commit (verification only)

---

## PR flow

Two PRs required (cross-repo):

1. **PR in `paperclip-shared-fragments`** (Task 1 only) — small, fragment-only. Reviewed by CR in that repo.
2. **PR in `Gimle-Palace`** (Tasks 2+3+4+5 + spec/plan) — submodule bump + role-file edits. Branch: `feature/GIM-108-merge-readiness-discipline`. Target: `develop`.

## Phase chain

| Phase | Owner | What |
|---|---|---|
| 1.0/1.1 | CTO | Formalize spec+plan (this document) |
| 1.2 | CodeReviewer | Plan-first review |
| 2 | TechnicalWriter (or CTO) | Author fragment text (Task 1) + role-file edits (Tasks 2-4) |
| 3.1 | CodeReviewer | Mechanical review — verify rendered dist, decoder table accuracy |
| 3.2 | OpusArchitectReviewer | Adversarial — missing `mergeStateStatus` values? Edge cases? |
| 4.1 | QAEngineer | iMac deploy + cat-grep evidence |
| 4.2 | CTO | Squash-merge (dog-food: paste `gh pr view --json` in merge comment) |

## Blockers

- **TechnicalWriter not hired** — CTO or Board writes fragment text (Task 1). Fragment authoring is docs scope, allowed under `cto-no-code-ban.md` narrowed scope for `docs/` files. But shared-fragments is a separate repo — CTO can write docs there.
- **`gh` CLI not installed on iMac** — needed for QA Phase 4.1 evidence. Must verify availability or install before QA phase.
