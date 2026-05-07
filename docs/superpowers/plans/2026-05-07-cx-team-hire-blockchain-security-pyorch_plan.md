# CX Team Hire — BlockchainEng + SecAud + Python-Orch — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: `superpowers:writing-skills` (role files are skill-shaped). Atomic-handoff discipline mandatory.

**Slice:** E6 (Phase 6 meta — promoted to **prereq for 65% Codex swap**, 2026-05-07).
**Spec:** `docs/superpowers/specs/2026-05-07-cx-team-hire-blockchain-security-pyorch_spec.md`.
**Source branch:** `feature/GIM-NN-cx-team-hire-three-agents` cut from `origin/develop`.
**Target branch:** `develop`. Squash-merge on APPROVE + smoke evidence.
**Team:** Board (governance + role-file authoring); CX team validates smoke. Phase chain compressed: Board → CR (plan-first) → Board (impl: file authoring + paperclip POST) → CR (mechanical) → QAEngineer (smoke) → CTO merge.

E6 is **not a typical engineering slice** — there's no Python code,
test suite, or extractor. It's a **provisioning + role-authoring**
slice. Adjustments to standard 7-phase chain:
- No PE / no MCPEngineer / no InfraEngineer step — Board does authoring.
- No OpusArchitectReviewer adversarial pass (no architectural surface
  to attack) — replaced by CX team smoke confirmation.

---

## Phase 0 — Prereqs (Board)

### Step 0.1: Resolve issue + branch

**Owner:** Board.

- [ ] Open paperclip issue `E6 — Hire BlockchainEng + SecAud + Python-Orch on CX team`.
- [ ] Body = link to spec + this plan; `GIM-NN` placeholders.
- [ ] Edit-pass replaces `GIM-NN` with assigned number.
- [ ] Reassign to CodeReviewer for plan-first review.

**Acceptance:** issue exists; CR is assignee.

### Step 0.2: Pre-check existing agent inventory

**Owner:** Board.

- [ ] `curl -H "Authorization: Bearer $PAPERCLIP_API_KEY" "$PAPERCLIP_API_URL/api/companies/$COMPANY_ID/agents"` and grep for any existing `name` collision (`BlockchainEngineer`, `SecurityAuditor`, candidate name from D-1). Note (rev4): paperclip agent records use `name` field, not `nameKey` — schema verified against develop.
- [ ] If collision: pause; revisit naming via D-1 with operator.

**Acceptance:** no `nameKey` collisions; clear naming decided.

---

## Phase 1 — Plan-first review (CodeReviewer)

### Step 1.1: Validate plan

**Owner:** CodeReviewer.

- [ ] Verify spec §3 In-scope items map 1-to-1 to Phase 2 steps below.
- [ ] Verify decision points D-1 through D-5 have a default chosen
      and operator's input on D-1 (naming) is captured.
- [ ] Verify smoke-probe acceptance is concrete (per-agent heartbeat
      within 1h on iMac runtime).
- [ ] APPROVE comment on paperclip + `gh pr review --approve` (PR
      doesn't exist yet — defer the GitHub APPROVE to Phase 3.1
      after PR is opened).
- [ ] Reassign to Board for impl.

**Acceptance:** APPROVE comment posted; assignee = Board.

---

## Phase 2 — Authoring + provisioning (Board)

### Step 2.1: Decision pre-impl with operator

**Owner:** Board (operator session).

- [ ] Confirm D-1 (third-agent naming) with operator. Default
      `cx-python-engineer-2` (kebab-case rev4). Capture decision in commit message.
- [ ] Confirm D-2 (shared vs per-role Python-orch fragment) — default
      shared, but if a domain-specific fragment makes sense, plan a
      stub now and defer authoring until first user.
- [ ] Confirm D-4 (per-agent smoke probe issues) — default yes; need
      3 smoke-probe issue numbers in Phase 4.

**Acceptance:** D-1..D-5 resolved; decisions noted in PR body draft.

### Step 2.2: Author cx-blockchain-engineer.md

**Owner:** Board.
**Files:** `paperclips/roles-codex/cx-blockchain-engineer.md` (new).

- [ ] Start by reading `paperclips/roles/blockchain-engineer.md`
      (Claude-side baseline).
- [ ] Mirror to CX-side, replacing:
  - workspace path → `/Users/ant013/Android/Gimle-Palace`
  - adapter spec → `codex_local`
  - any Claude-CLI-specific tool references → Codex-CLI equivalent
  - any reference to Claude team workspace structure → CX team
- [ ] Verify standard fragment includes: handoff, plan-first,
      qa-evidence, atomic-handoff, slim-discipline, audit-mode
      (post-S0.3 — if S0.3 hasn't merged yet, leave a TODO marker
      and note in PR body that audit-mode include lands in a follow-up
      after S0.3 merges).
- [ ] Add domain-knowledge anchor section: EVM call semantics +
      Solidity ABI + Anchor IDL + FunC cell layouts + SLIP-0044 +
      common wallet-cryptography pitfalls.

**Acceptance:** file exists, passes markdown-lint, fragment-include
validator (`paperclips/scripts/curate-script.sh`) returns clean.

### Step 2.3: Author cx-security-auditor.md

**Owner:** Board.
**Files:** `paperclips/roles-codex/cx-security-auditor.md` (new).

- [ ] Same mirror process from `paperclips/roles/security-auditor.md`.
- [ ] Domain-knowledge anchor: OWASP top-10 mobile, Apple Secure
      Enclave, Android Keystore, common iOS/Android crypto missteps,
      taint-analysis methodology, supply-chain risk patterns.

**Acceptance:** as Step 2.2.

### Step 2.4: Author cx-python-engineer-2.md (or D-1 alternative name)

**Owner:** Board.
**Files:** `paperclips/roles-codex/cx-python-engineer-2.md` (new).

- [ ] Mirror from `paperclips/roles-codex/cx-python-engineer.md`
      (existing CX PE).
- [ ] Adjust scope blurb: "second Python engineer on CX team —
      handles swapped Claude-affinity extractor work + LLM-bearing
      extractors + audit composite tools".
- [ ] Add a note at the top: "Coordinates with CXPythonEngineer (#1)
      via plan-first phase to avoid file overlap on the same extractor."

**Acceptance:** as Step 2.2.

### Step 2.5: POST agent identities to paperclip

**Owner:** Board.

For each of the 3 new agents:

- [ ] `curl -X POST -H "Authorization: Bearer $PAPERCLIP_API_KEY" -H "Content-Type: application/json" -d '{"companyId":"<id>","nameKey":"<key>","name":"<display>","adapter":"codex_local","status":"idle"}' "$PAPERCLIP_API_URL/api/companies/<id>/agents"`.
- [ ] Capture returned UUID.
- [ ] Verify with GET that agent appears in company agent list.
- [ ] Update Board memory `reference_agent_ids.md` with the 3 new
      UUIDs (or repo-tracked agent table if exists — TBD).

**Acceptance:** 3 new agents listed in
`GET /api/companies/<id>/agents` with the chosen `nameKey`s and
`status=idle`.

### Step 2.6: Render + iMac deploy of role bundles

**Owner:** Board.

- [ ] Run paperclip role-bundle render command (project standard).
- [ ] Verify rendered AGENTS.md for each new agent contains the
      expected sections.
- [ ] Commit role files + render artefacts.
- [ ] Push branch.
- [ ] Open PR titled `feat(GIM-NN): hire 3 new CX agents — BlockchainEng + SecAud + PE-2`.
- [ ] PR body includes:
  - "Closes GIM-NN"
  - List of 3 new agent UUIDs.
  - Decision-points D-1..D-5 outcomes.
  - QA Evidence section deferred to Phase 4.
- [ ] Reassign issue to CodeReviewer for Phase 3.

**Acceptance:** branch pushed; PR open; CI runs.

---

## Phase 3 — Mechanical review (CodeReviewer)

**Owner:** CodeReviewer.

- [ ] Paste `gh pr checks <PR>` — required CI green
      (lint, docker-build, qa-evidence-present + any role-file
      validator).
- [ ] Diff each new role file against its Claude-side counterpart;
      flag any unexpected divergence beyond the documented mirror
      changes.
- [ ] Verify the 3 agent UUIDs returned from POST are referenced in
      `reference_agent_ids.md` update.
- [ ] APPROVE on paperclip + `gh pr review --approve`.
- [ ] Reassign to QAEngineer for smoke (no Opus adversarial pass —
      no architectural surface).

**Acceptance:** APPROVE on paperclip + GitHub.

---

## Phase 4 — Smoke (QAEngineer on iMac)

### Step 4.1: Deploy role bundles + restart paperclip if needed

**Owner:** QAEngineer.

- [ ] SSH iMac.
- [ ] FF-pull develop.
- [ ] `bash paperclips/scripts/imac-agents-deploy.sh` — copies
      rendered AGENTS.md into agent bundle directories.
- [ ] No paperclip restart needed (paperclip reads AGENTS.md fresh
      per-run per CLAUDE.md).

### Step 4.2: Per-agent smoke probe

**Owner:** QAEngineer.

For each of the 3 new agents:

- [ ] Open a smoke-probe paperclip issue titled
      `[smoke] Introduce yourself — <agent name>`.
- [ ] Body: "Confirm you're alive: post a heartbeat comment that
      includes (a) your workspace root, (b) the date you read AGENTS.md,
      (c) the list of fragment-includes you see in your bundle."
- [ ] Reassign to the new agent. Verify atomic-handoff via PATCH
      assignee.
- [ ] Wait for heartbeat (≤1h target).
- [ ] On heartbeat, verify:
  - workspace root = `/Users/ant013/Android/Gimle-Palace` (CX root)
  - fragment list includes the standard set (handoff, atomic-handoff,
    qa-evidence, plan-first, slim-discipline)
  - status transitions `idle → in_progress → idle`
  - paperclip executionRunId clears (no stale-lock per
    `reference_paperclip_stale_execution_lock.md`).
- [ ] Close smoke-probe issue.

**Acceptance:** 3 heartbeat comments posted with all expected fields.

### Step 4.3: Author QA Evidence comment

**Owner:** QAEngineer.

- [ ] Edit PR body to add `## QA Evidence` section. Cite:
  - Branch SHA used for render.
  - 3 agent UUIDs.
  - 3 smoke-probe issue numbers.
  - Heartbeat comment IDs (or excerpts).
  - Affirmation per `feedback_pe_qa_evidence_fabrication.md`:
    "All 3 agents posted live heartbeats; not fabricated."
- [ ] Reassign to CTO.

**Acceptance:** QA Evidence satisfies `qa-evidence-present` CI check.

---

## Phase 5 — Merge (CTO)

**Owner:** CTO.

- [ ] Verify required CI green.
- [ ] Verify CR APPROVE + QA Evidence present.
- [ ] Squash-merge.
- [ ] Update `docs/roadmap.md` E6 row 📦 → ✅ + merge SHA.
- [ ] Update Board memory `project_dual_team_architecture.md` —
      remove "(no blockchain/security yet)" caveat; add E6 closure date.
- [ ] Update Board memory `reference_agent_ids.md` with 3 new IDs
      (already done in Step 2.5; double-check).
- [ ] Close paperclip issue.
- [ ] **Unblock dependent slices**: post a comment on each blocked
      issue (Chain-Sol B1; #11/#26/#43; swapped extractors) noting
      "E6 closed — CX BlockchainEng / SecAud / PE-2 available; this
      slice can now start when team-chain frees up."

**Acceptance:** E6 ✅; all 3 agents listed in iMac agent inventory;
Board memory updated; downstream issues unblocked-via-comment.

---

## Definition-of-Done checklist

- [ ] 3 new role files committed (Codex side).
- [ ] 3 agent UUIDs registered on paperclip; listed in
      `reference_agent_ids.md`.
- [ ] Smoke-probe heartbeat received from each new agent.
- [ ] PR squash-merged.
- [ ] Roadmap E6 ✅; memory entries updated.
- [ ] Downstream blocked issues notified.

---

## Risks (carried from spec §7)

- R1 — agent stuck in `status=error` after first run.
- R2 — `nameKey` collision (mitigated in Step 0.2).
- R3 — Claude/Codex role-file drift (mitigated in Step 2.{2,3,4}).
- R4 — workspace path misconfiguration.

---

## Cross-references

- Spec: `2026-05-07-cx-team-hire-blockchain-security-pyorch_spec.md`
- Roadmap: `docs/roadmap.md` E6 row
- Operator decision (this session, 2026-05-07).
- Memory (Board): `project_dual_team_architecture.md`,
  `reference_agent_ids.md`, `feedback_slim_both_claude_codex.md`,
  `feedback_team_workspace_dirs_persistent.md`,
  `reference_paperclip_stale_execution_lock.md`.
- iMac deploy: `paperclips/scripts/imac-agents-deploy.sh` +
  `paperclips/scripts/imac-agents-deploy.README.md`.
