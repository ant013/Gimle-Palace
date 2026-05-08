# CX Team Hire — BlockchainEng + SecAud + Python-Orch — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: `superpowers:writing-skills` (role files are skill-shaped). Atomic-handoff discipline mandatory.

**Slice:** E6 (Phase 6 meta — promoted to **prereq for 65% Codex swap**, 2026-05-07).
**Spec:** `docs/superpowers/specs/2026-05-07-cx-team-hire-blockchain-security-pyorch_spec.md`.
**Source branch:** `feature/GIM-229-cx-team-hire-three-agents` cut from `origin/develop`.
**Target branch:** `develop`. Squash-merge on APPROVE + smoke evidence.
**Team:** Board (governance + role-file authoring); CX team validates smoke. Phase chain compressed: Board → CR (plan-first) → Board (impl: file authoring + paperclip POST) → CR (mechanical) → QAEngineer (smoke) → CTO merge.

E6 is **not a typical engineering slice** — there's no Python code,
test suite, or extractor. It's a **provisioning + role-authoring**
slice. Adjustments to standard 7-phase chain:
- No PE / no MCPEngineer / no InfraEngineer step — Board does authoring.
- No OpusArchitectReviewer adversarial pass (no architectural surface
  to attack) — replaced by CX team smoke confirmation.

---

## Phase 0 — Prereqs + formalisation (CXCTO)

### Step 0.1: Resolve issue + branch

**Owner:** CXCTO.

- [x] Paperclip issue exists: `GIM-229`.
- [x] Body links spec + this plan.
- [x] Edit-pass replaces `GIM-NN` with `GIM-229` in the branch name.
- [x] Resolve E6-D1..D5 in spec §5.1.
- [ ] Reassign to CXCodeReviewer for plan-first review.

**Acceptance:** issue exists; CXCodeReviewer is assignee.

### Step 0.2: Pre-check existing agent inventory

**Owner:** CXCTO.

- [x] `curl -H "Authorization: Bearer $PAPERCLIP_API_KEY" "$PAPERCLIP_API_URL/api/companies/$PAPERCLIP_COMPANY_ID/agents"` checked on 2026-05-07.
- [x] Existing Claude-side names found: `BlockchainEngineer`,
      `SecurityAuditor`. Do not reuse these names.
- [x] Final CX names selected: `CXBlockchainEngineer`, `CXSecurityAuditor`
      (rev5 2026-05-08: `CXPythonEngineer2` removed — operator decision).
- [x] Paperclip agent records use `name` + generated `urlKey`; legacy
      `nameKey` payloads are stale for this slice.

**Acceptance:** no selected CX `name` collisions; clear naming decided.

---

## Phase 1 — Plan-first review (CodeReviewer)

### Step 1.1: Validate plan

**Owner:** CodeReviewer.

- [ ] Verify spec §3 In-scope items map 1-to-1 to Phase 2 steps below.
- [ ] Verify decision points D-1 through D-5 are resolved in spec §5.1.
- [ ] Verify smoke-probe acceptance is concrete (per-agent heartbeat
      within 2-3h on iMac runtime).
- [ ] APPROVE comment on paperclip + `gh pr review --approve` (PR
      doesn't exist yet — defer the GitHub APPROVE to Phase 3.1
      after PR is opened).
- [ ] Reassign to Board for implementation.

**Acceptance:** APPROVE comment posted; assignee = Board.

---

## Phase 2 — Authoring + provisioning (Board)

### Step 2.1: Apply formalised decisions

**Owner:** Board (operator session).

- [ ] Use spec §5.1 decisions without silent renaming:
      `CXBlockchainEngineer`, `CXSecurityAuditor` (rev5: `CXPythonEngineer2` dropped per operator 2026-05-08).
- [ ] Use CX workspace root
      `/Users/Shared/Ios/worktrees/cx/Gimle-Palace`.
- [ ] Use per-agent smoke probes with 2-3h heartbeat SLA.
- [ ] Capture any intentional deviation from §5.1 in PR body and
      re-request review before provisioning.

**Acceptance:** D-1..D-5 are reflected in PR body draft.

### Step 2.2: Author cx-blockchain-engineer.md

**Owner:** Board.
**Files:** `paperclips/roles-codex/cx-blockchain-engineer.md` (new).

- [ ] Start by reading `paperclips/roles/blockchain-engineer.md`
      (Claude-side baseline).
- [ ] Mirror to CX-side, replacing:
  - workspace path → `/Users/Shared/Ios/worktrees/cx/Gimle-Palace`
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

**Acceptance:** file exists, passes markdown-lint, `bash paperclips/build.sh --target codex` exits 0 and `bash paperclips/validate-codex-target.sh` exits 0 with no missing include, oversize, or forbidden-runtime-reference findings.

### Step 2.3: Author cx-security-auditor.md

**Owner:** Board.
**Files:** `paperclips/roles-codex/cx-security-auditor.md` (new).

- [ ] Same mirror process from `paperclips/roles/security-auditor.md`.
- [ ] Domain-knowledge anchor: OWASP top-10 mobile, Apple Secure
      Enclave, Android Keystore, common iOS/Android crypto missteps,
      taint-analysis methodology, supply-chain risk patterns.

**Acceptance:** as Step 2.2.

### ~~Step 2.4: Author cx-python-engineer-2.md~~ — **DROPPED in rev5 (2026-05-08)**

Operator decision: PE-2 is not needed. CXPythonEngineer alone is
sufficient for batch 1 of CX-native extractors (#6/#8/#9/#17). Revisit
hire only after empirical CXPythonEngineer overload evidence.

### Step 2.5: Submit agent hire requests to paperclip

**Owner:** Board.

For each of the **2** new agents (rev5 — was 3):

- [ ] Use `POST /api/companies/$PAPERCLIP_COMPANY_ID/agent-hires`,
      not the stale direct-create `nameKey` payload.
- [ ] Set `sourceIssueId=8ca15837-8dc4-4799-adfa-30d3e4486fee`.
- [ ] Set `reportsTo=da97dbd9-6627-48d0-b421-66af0750eacf`.
- [ ] Set `adapterType=codex_local`.
- [ ] Adapter config mirrors current CX agents:
      `cwd=/Users/Shared/Ios/worktrees/cx/Gimle-Palace`,
      managed `CODEX_HOME`, current CX `PATH`, `model=gpt-5.4`,
      `modelReasoningEffort=high`, `dangerouslyBypassApprovalsAndSandbox=true`.
- [ ] Set `runtimeConfig.heartbeat.enabled=false` and
      `wakeOnDemand=true`.
- [ ] Submit identity set:
      `CXBlockchainEngineer` (`role=engineer`, `icon=gem`),
      `CXSecurityAuditor` (`role=qa`, `icon=shield`).
      (rev5 dropped: ~~`CXPythonEngineer2`~~)
- [ ] Use top-level `instructionsBundle.files["AGENTS.md"]`; do not
      set `adapterConfig.promptTemplate` or `bootstrapPromptTemplate`.
- [ ] Instruction-source path to state in hire comment:
      adjacent-template from existing project role files:
      Claude `paperclips/roles/blockchain-engineer.md`,
      Claude `paperclips/roles/security-auditor.md`, and existing
      CX `paperclips/roles-codex/cx-python-engineer.md`.
- [ ] Capture returned UUID.
- [ ] Verify with GET that agent appears in company agent list.
- [ ] Update Board memory `reference_agent_ids.md` with the 3 new
      UUIDs (or repo-tracked agent table if exists — TBD).

**Acceptance:** 3 new agents listed in
`GET /api/companies/<id>/agents` with the chosen CX `name`s and
`status=idle` or `pending_approval` with linked hire approval.

### Step 2.6: Render + iMac deploy of role bundles

**Owner:** Board.

- [ ] Run `bash paperclips/build.sh --target codex`.
- [ ] Expected render outputs exist (rev5 — 2 files, was 3):
  - `paperclips/dist/codex/cx-blockchain-engineer.md`
  - `paperclips/dist/codex/cx-security-auditor.md`
- [ ] Run `bash paperclips/validate-codex-target.sh`; expected final line: `Codex target validation OK: <repo>/paperclips/dist/codex`.
- [ ] Verify rendered AGENTS.md for each new agent contains the
      expected sections.
- [ ] Commit role files + render artefacts.
- [ ] Push branch.
- [ ] Open PR titled `feat(GIM-229): hire 2 new CX agents — BlockchainEng + SecAud (rev5)`.
- [ ] PR body includes:
  - "Closes GIM-229"
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
- [ ] Wait for heartbeat (2-3h target).
- [ ] On heartbeat, verify:
  - workspace root = `/Users/Shared/Ios/worktrees/cx/Gimle-Palace`
    (CX root)
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
- [ ] Open or verify the next active Codex-queue issue for
      `Coding Convention Extractor (#6)` using
      `docs/superpowers/specs/2026-05-07-GIM-238-coding-convention-extractor_spec.md`
      and `docs/superpowers/plans/2026-05-07-GIM-238-coding-convention-extractor.md`;
      assign it to CXCTO for the normal Phase 1.1/1.2 chain or directly to
      CXCodeReviewer if the GIM-229 closure comment is the formal plan handoff.
- [ ] Create or verify parked downstream queue issues for:
  - `Testability/DI Pattern Extractor (#8)`
  - `Hot-Path Profiler Extractor (#17)`
  - `Localization & Accessibility Extractor (#9)`
- [ ] Park #8, #17, and #9 with explicit blocker/queue metadata rather than
      leaving them implicit in comments. If strict sequential Codex execution is
      required, set them `blocked` behind the #6 issue; #17 also keeps its
      real-trace fixture dependency noted from its plan.
- [ ] Final GIM-229 closure comment includes links/IDs for #6, #8, #17, and #9
      so the 35/65 swap cannot stall after E6.
- [ ] Close paperclip issue.
- [ ] **Unblock dependent slices**: post a comment on each blocked
      issue (Chain-Sol B1; #11/#26/#43; swapped extractors) noting
      "E6 closed — CX BlockchainEng + SecAud available (rev5: PE-2 dropped); this
      slice can now start when team-chain frees up."

**Acceptance:** E6 ✅; all 3 agents listed in iMac agent inventory; Board memory updated; #6 active issue exists; #8/#17/#9 parked with explicit blockers/queue metadata; downstream issues unblocked-via-comment.

---

## Definition-of-Done checklist

- [ ] **2** new role files committed (Codex side; rev5 was 3).
- [ ] **2** agent UUIDs registered on paperclip; listed in
      `reference_agent_ids.md`. (rev5: was 3; PE-2 dropped per operator
      decision 2026-05-08.)
- [ ] Smoke-probe heartbeat received from each new agent.
- [ ] PR squash-merged.
- [ ] Roadmap E6 ✅; memory entries updated.
- [ ] Next Codex queue issue #6 opened/verified and formally handed off.
- [ ] Downstream #8, #17, and #9 issues opened/verified and parked with explicit blocker/queue metadata.
- [ ] Downstream blocked issues notified.

---

## Risks (carried from spec §7)

- R1 — agent stuck in `status=error` after first run.
- R2 — `name` collision (mitigated in Step 0.2).
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
