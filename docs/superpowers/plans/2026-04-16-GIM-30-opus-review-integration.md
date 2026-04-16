# GIM-30 — OpusArchitectReviewer PR Review Integration

> **For agentic workers:** steps use `- [ ]` checkboxes; TechnicalWriter executes the documentation steps, CodeReviewer gates plan + PR, OpusArchitectReviewer executes the dry-run. CTO orchestrates handoffs via Paperclip @-mentions.

**Goal:** Wire [OpusArchitectReviewer](/GIM/agents/opusarchitectreviewer) as a second-tier adversarial reviewer invoked **after** Sonnet [CodeReviewer](/GIM/agents/codereviewer) posts a mechanical-checklist APPROVE on feature PRs targeting `develop`. Advisory by default; CRITICAL Opus findings block merge.

**Architecture (MVP — manual handoff, no webhook automation yet):**

1. CodeReviewer runs CLAUDE.md mechanical checklist on the PR (GitHub + Paperclip issue).
2. On APPROVE, CodeReviewer's last Paperclip-issue comment ends with `@OpusArchitectReviewer architectural pass on PR #N please` — Paperclip wakes Opus automatically via the @-mention (no new routine/webhook needed).
3. Opus does docs-first review via `context7` (FastAPI, Pydantic, MCP SDK, Neo4j, Docker), checks SDK conformance + subtle-pattern deviations beyond the checklist, and posts findings (CRITICAL / WARNING / NOTE) on the Paperclip issue + cross-posts summary to the GitHub PR.
4. Merge rules: CRITICAL → block merge, require fix PR; WARNING / NOTE → advisory, captured for backlog.
5. Escalation: conflict between Sonnet and Opus verdicts → CTO adjudicates on the Paperclip issue.

**Why manual @-mention and not a GitHub→Paperclip routine webhook:** Paperclip already wakes agents on Paperclip-comment @-mentions. Wiring a GitHub Action → Paperclip routine webhook is out of scope for GIM-30 and can be filed as a follow-up if the manual flow proves friction-heavy after 5+ feature PRs.

**Tech stack / surfaces touched:** `paperclips/roles/*.md` (role contracts), `docs/review-flow.md` (new runbook), `docs/superpowers/plans/` (plan mirror), Paperclip agent config via API (no repo change needed — OpusArchitectReviewer already has `wakeOnDemand: true`, heartbeat disabled, budget 0 already correct).

---

## Phase 1 — Branch + Plan Mirror

### Step 1.1: Cut feature branch from `develop`
**Owner:** TechnicalWriter.  
**Deps:** none.  
**Files:** branch only.

- [ ] `git fetch origin && git checkout -b feature/GIM-30-opus-review-integration origin/develop`
- [ ] Confirm branch has no uncommitted state: `git status` → clean tree.

**Acceptance:** Branch `feature/GIM-30-opus-review-integration` exists locally, tracks `origin/develop`, working tree clean.

### Step 1.2: Mirror this plan to repo
**Owner:** TechnicalWriter.  
**Deps:** Step 1.1.  
**Files:** `docs/superpowers/plans/2026-04-16-GIM-30-opus-review-integration.md` (create).

- [ ] Copy this plan body verbatim (from issue document) to the repo file.
- [ ] Keep internal Paperclip links (`/GIM/...`) as-is for now — they resolve inside Paperclip UI.
- [ ] Commit: `docs(plans): add GIM-30 Opus review integration implementation plan` + `Co-Authored-By: Paperclip <noreply@paperclip.ing>`.

**Acceptance:** File exists on branch, contents match issue `plan` document, commit present.

### Step 1.3: CodeReviewer reviews plan
**Owner:** CodeReviewer.  
**Deps:** Step 1.2 committed and pushed.  
**Files:** N/A (review only).

- [ ] Read `docs/superpowers/plans/2026-04-16-GIM-30-opus-review-integration.md` on branch `feature/GIM-30-opus-review-integration`.
- [ ] Check plan-first compliance items from CodeReviewer's own checklist (`paperclips/roles/code-reviewer.md` → Plan-first discipline).
- [ ] Post verdict `APPROVE` or `REQUEST CHANGES` on [GIM-30](/GIM/issues/GIM-30).

**Acceptance:** Explicit APPROVE comment from CodeReviewer on GIM-30 before Phase 2 starts. If REQUEST CHANGES — CTO revises plan, loops back to 1.3.

---

## Phase 2 — Documentation Deliverables (parallel once Phase 1 approved)

### Step 2.1: Create `paperclips/roles/opus-architect-reviewer.md`
**Owner:** TechnicalWriter.  
**Deps:** Step 1.3 APPROVE.  
**Files:** `paperclips/roles/opus-architect-reviewer.md` (create).

File MUST contain these sections (style must match existing `code-reviewer.md` format, use `<!-- @include fragments/shared/fragments/*.md -->` for shared fragments):

- **Header:** `# OpusArchitectReviewer — Gimle (Second-Tier Adversarial Review)` + role summary tied to CLAUDE.md.
- **Role:** Explicit statement that Opus is **second-tier**, never a substitute for Sonnet CodeReviewer. Reports to CTO but escalates to Board on CTO-authored plans (red-team independence).
- **Invocation contract:**
  - Fires on explicit `@OpusArchitectReviewer` mention in a Paperclip issue comment from CodeReviewer (APPROVE handoff) or CTO (retroactive / conflict adjudication request).
  - Never self-assigns unassigned PRs.
  - Wake-on-demand only; heartbeat disabled; monthly budget 0 — every run must be justified.
- **Review methodology:**
  - **Docs-first**: BEFORE reading PR code, pull current docs for every non-trivial library used in the diff via `context7` (FastAPI, Pydantic v2, MCP Python SDK, Neo4j driver, Docker Compose schema). Training-data drift assumption is hard rule — no recall-only claims.
  - **SDK conformance scan:** Does the code use the SDK's intended primitives (e.g. FastMCP `lifespan` vs module globals, `Depends()` DI vs singletons, Pydantic `model_validate` vs raw dict construction)?
  - **Subtle-pattern detection:** issues Sonnet's mechanical checklist misses — eventual-consistency mistakes, missing capability use, dep-graph smell, silent behavioural coupling, API contract drift.
  - **Independent of Sonnet's verdict:** even if Sonnet APPROVEd, Opus can flag CRITICAL and block merge.
- **Output format:** identical structure to CodeReviewer's review format (Summary / Findings CRITICAL/WARNING/NOTE with `file:line` + doc-link citation / Compliance-style section / Verdict `APPROVE | REQUEST CHANGES | REJECT`). Each finding must cite an **official doc URL** (from `context7`) — not just training-data prose.
- **Blocker rules:**
  - CRITICAL findings = merge blocked until fix PR lands and both Sonnet + Opus re-APPROVE.
  - WARNING findings = advisory; CTO decides whether to file follow-up issue before merge.
  - NOTE findings = captured in backlog, never blocker.
- **MCP / subagents / skills:**
  - MCP primary: `context7` (docs, required before any finding), `serena` (symbol navigation in large diffs), `github` (PR diff + CI status), `sequential-thinking` (cross-component architectural reasoning).
  - Subagents: `voltagent-qa-sec:architect-reviewer`, `voltagent-qa-sec:code-reviewer` (for checks Sonnet tier skipped), `pr-review-toolkit:type-design-analyzer`, `pr-review-toolkit:silent-failure-hunter`.
  - Skills: `pr-review-toolkit:review-pr`, `superpowers:verification-before-completion`.
- **Escalation:** If CTO authored the plan Opus is reviewing → escalate disagreement directly to Board (bypass CTO). Never suppress CRITICAL finding under deadline pressure.
- **Included fragments (required):** `escalation-blocked.md`, `git-workflow.md`, `worktree-discipline.md`, `heartbeat-discipline.md`, `language.md` — match CodeReviewer layout.

**Acceptance:** File exists, lints clean against project markdown style, all required sections present, fragments included.

### Step 2.2: Create `docs/review-flow.md`
**Owner:** TechnicalWriter.  
**Deps:** Step 1.3 APPROVE.  
**Files:** `docs/review-flow.md` (create).

Sections:

- **Scope:** applies to feature PRs targeting `develop`; release PRs `develop → main` follow a separate (existing) flow.
- **Lifecycle diagram:** `feature/GIM-N` cut from `develop` → engineer commits + pushes → PR opens against `develop` → Sonnet CodeReviewer mechanical pass → Sonnet APPROVE + `@OpusArchitectReviewer` handoff comment on Paperclip issue → Opus architectural pass → merge-gate evaluation → merge to `develop`.
- **Handoff contract (copy-pasteable template):**
  ```
  ## CodeReviewer verdict: APPROVE
  [summary + checklist link]
  @OpusArchitectReviewer architectural pass on PR #<N> please. Context: <one-line scope>.
  ```
- **Opus output expectation:** findings with doc-citations, final verdict, cross-post summary to GitHub PR thread.
- **Merge-gate table:**
  | Sonnet | Opus | Action |
  |---|---|---|
  | APPROVE | APPROVE | merge allowed |
  | APPROVE | REQUEST CHANGES (CRITICAL) | block until fix PR + re-review |
  | APPROVE | REQUEST CHANGES (WARNING only) | CTO files follow-up issue, merge allowed |
  | REQUEST CHANGES | — | Opus not yet invoked; fix Sonnet findings first |
  | APPROVE (Sonnet) | REJECT (Opus) | escalation to Board, merge blocked |
- **Conflict adjudication:** Sonnet vs Opus disagreement on same finding → CTO adjudicates on the Paperclip issue; if CTO is plan author, Board adjudicates.
- **Opt-out conditions:** doc-only PRs (no `src/`, no `tests/`, no `compose.yaml`) may merge with Sonnet-only review; Opus invocation optional.
- **Release flow pointer:** `develop → main` release PR still follows existing CTO-approval rule (link to CLAUDE.md branch-flow section).
- **Retroactive reviews:** CTO may `@OpusArchitectReviewer` on any merged PR's Paperclip issue to get a post-hoc architectural review; findings feed backlog issues.

**Acceptance:** File exists, merge-gate table rendered, all sections present, linked from `paperclips/roles/opus-architect-reviewer.md` and CLAUDE.md Branch Flow section (or at minimum — from a new pointer line in CLAUDE.md).

### Step 2.3: Update `paperclips/roles/code-reviewer.md` with handoff step
**Owner:** TechnicalWriter.  
**Deps:** Step 1.3 APPROVE.  
**Files:** `paperclips/roles/code-reviewer.md` (modify).

- [ ] Add new subsection under existing `## Формат ревью` (or as a new top-level `## Handoff to OpusArchitectReviewer`) with:
  - Trigger condition: verdict `APPROVE` on feature PR targeting `develop` and diff contains code / infra (not doc-only).
  - Required last line of APPROVE comment on Paperclip issue: `@OpusArchitectReviewer architectural pass on PR #<N> please. Context: <scope>.`
  - Explicit exception: doc-only PRs skip the handoff.
  - Pointer to `docs/review-flow.md` merge-gate table.
- [ ] Do NOT change existing compliance checklist entries — only add the new handoff section.

**Acceptance:** New handoff section present, trigger / format / exception spelled out, no regressions to existing checklist.

### Step 2.4: Add pointer in CLAUDE.md
**Owner:** TechnicalWriter.  
**Deps:** Step 2.2.  
**Files:** `CLAUDE.md` (modify).

- [ ] Under existing `## Branch Flow` section, append a short bullet: `Review pipeline — see docs/review-flow.md (Sonnet mechanical pass → Opus architectural pass on feature→develop PRs).`
- [ ] No other CLAUDE.md changes.

**Acceptance:** Pointer bullet present, one line only, no other churn.

---

## Phase 3 — Validation via PR dry-run

### Step 3.1: Open PR against `develop`
**Owner:** TechnicalWriter.  
**Deps:** Steps 2.1–2.4 committed.  
**Files:** PR metadata.

- [ ] Push branch.
- [ ] Open PR with title `docs(review): integrate OpusArchitectReviewer into PR review flow (GIM-30)` targeting `develop`.
- [ ] PR body references [GIM-30](/GIM/issues/GIM-30) and links to `docs/superpowers/plans/2026-04-16-GIM-30-opus-review-integration.md`.

**Acceptance:** PR URL posted on GIM-30.

### Step 3.2: CodeReviewer mechanical pass on this PR
**Owner:** CodeReviewer.  
**Deps:** Step 3.1.  
**Files:** N/A (review).

- [ ] Run CodeReviewer checklist on this PR. This is a doc-only PR per Step 2.2 opt-out rule, so `APPROVE` should not trigger an Opus mention. **HOWEVER**, to exercise the flow, CodeReviewer MUST mention `@OpusArchitectReviewer` explicitly for this first-run validation — overriding the opt-out for dry-run purposes. Note in the handoff comment that this is a dry-run override.

**Acceptance:** Sonnet APPROVE + explicit dry-run handoff comment posted on GIM-30.

### Step 3.3: Opus dry-run on PR
**Owner:** OpusArchitectReviewer.  
**Deps:** Step 3.2.  
**Files:** N/A (review).

- [ ] Opus follows `paperclips/roles/opus-architect-reviewer.md` methodology against the PR diff.
- [ ] Uses `context7` to verify doc-writing conventions (even for docs PR, check terminology matches official FastMCP / Pydantic wording where cited).
- [ ] Posts findings + verdict on GIM-30. Validates that the runbook is accurate, that role-doc invocation contract is internally consistent, and that merge-gate table is implementable.

**Acceptance:** Opus review comment posted, contains at least 1 structured finding (even NOTE-level) with a `context7` doc citation, final verdict present.

### Step 3.4: Merge to `develop`
**Owner:** CTO (merge) after Sonnet + Opus both APPROVE (or Opus WARNING-only with CTO ack).  
**Deps:** Step 3.3 + any fix loops.  
**Files:** N/A.

- [ ] Merge PR with squash commit.
- [ ] Mark GIM-30 `done` only after Phase 4 completes.

**Acceptance:** PR merged; GIM-30 still `in_progress` pending Phase 4.

---

## Phase 4 — Retroactive dry-run on [GIM-23](/GIM/issues/GIM-23) MCP health tool

### Step 4.1: CTO triggers Opus retroactive review on GIM-23
**Owner:** CTO (triggering), OpusArchitectReviewer (executing).  
**Deps:** Phase 3 merged.  
**Files:** N/A.

- [ ] CTO posts on [GIM-23](/GIM/issues/GIM-23) a comment: `@OpusArchitectReviewer retroactive architectural pass on the merged MCP health tool (PR link). Context: GIM-23 Phase 4 validation for GIM-30.`
- [ ] Opus runs full methodology against the merged `feature/GIM-23-mcp-health-tool` diff (already merged into `develop`) — docs-first via `context7` for FastMCP + streamable-HTTP + lifespan patterns.
- [ ] Opus posts findings on GIM-23. Any CRITICAL finding → new fix issue filed (child of GIM-23 or fresh feature issue, CTO decides).

**Acceptance:** Opus retroactive review comment on GIM-23 with docs-cited findings, even if verdict is APPROVE (validates the tool setup works on real code, not just docs PR).

### Step 4.2: Close GIM-30
**Owner:** CTO.  
**Deps:** Step 4.1.  
**Files:** N/A.

- [ ] Summary comment on GIM-30 linking: plan doc, merged PR, GIM-23 retroactive review, any follow-up issues created.
- [ ] PATCH GIM-30 status `done`.

**Acceptance:** GIM-30 done with summary comment. If blockers surfaced → status `blocked` + escalation to Board instead.

---

## Out of scope (explicit non-goals)

- GitHub Action → Paperclip webhook routine automation (can be filed as follow-up if manual flow has friction after 5+ PRs).
- Changing OpusArchitectReviewer's Paperclip config beyond what was set at hire time ([GIM-29](/GIM/issues/GIM-29)) — `wakeOnDemand: true`, heartbeat disabled, budget 0 already correct.
- Cross-posting automation GitHub ↔ Paperclip (Opus cross-posts summary manually as part of its review output).

## Risks

- **Risk:** Sonnet forgets to @-mention Opus on APPROVE → Opus never runs. **Mitigation:** Step 2.3 adds explicit handoff step to CodeReviewer role doc; CTO spot-checks first 3 feature→develop PRs post-rollout.
- **Risk:** Opus budget (0) means it never fires. **Mitigation:** Paperclip `wakeOnDemand: true` + budget 0 allows manual wake (per hire-time config); if platform blocks runs at budget 0, escalate to Board for budget allocation — file as blocker, do not silently fail.
- **Risk:** Opus and Sonnet produce conflicting verdicts and CTO becomes bottleneck. **Mitigation:** Merge-gate table in `docs/review-flow.md` covers main conflict cases; only REJECT-vs-APPROVE escalates to Board.

## Success metrics (review after 5 feature→develop PRs post-rollout)

- ≥ 90% of feature PRs get Opus pass (handoff didn't drop).
- Opus surfaces ≥ 1 WARNING-or-higher finding Sonnet missed on at least 2 of 5 PRs.
- Zero CRITICAL findings on merged code within 30 days of merge (proves gate works).
