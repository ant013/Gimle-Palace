# CX Team Hire — BlockchainEngineer + SecurityAuditor + Python-Orch Agent — Specification

**Document date:** 2026-05-07
**Status:** Formalised by CXCTO · awaiting CXCodeReviewer plan-first review
**Author:** Board+Claude session (operator + Claude Opus 4.7)
**Team:** Board (governance / role-file authoring); execution mostly mechanical
**Slice ID:** E6 (Phase 6 meta — promoted from "deferred" to **prereq for Codex 65% load swap**, 2026-05-07)
**Companion plan:** `2026-05-07-cx-team-hire-blockchain-security-pyorch_plan.md`
**Branch:** `feature/GIM-229-cx-team-hire-three-agents`

---

## 1. Goal

Bring CX team to feature parity with Claude team in three role
families so Codex can absorb ~65% of remaining roadmap work (per
operator decision 2026-05-07):

1. **BlockchainEngineer** (CX) — handles smart-contract / wallet-crypto
   slices: Solidity, Anchor, FunC, EVM, crypto-domain extractors.
2. **SecurityAuditor** (CX) — handles audit-Phase domain agent and any
   security-tagged extractors / slices.
3. **Python-orchestration engineer** (CX) — additional CXPythonEngineer-
   class agent for the swapped Claude-affinity work pool (LLM-required
   extractors, Python orchestration extractors, composite tools).

After E6 closes, the 35/65 (Claude/Codex) roadmap split is operationally
viable. Without E6 it is not — many "swapped" extractors require role
expertise CX team currently lacks.

**Definition of Done:**

1. Three new CX-prefixed agent UUIDs registered in Gimle company on
   paperclip instance, listed in `reference_agent_ids.md`.
2. Three role files authored under `paperclips/roles-codex/` (rev4 —
   kebab-case naming, matching existing `cx-code-reviewer.md` pattern;
   plus `<!-- @include fragments/local/audit-mode.md -->` marker
   pre-wired in security + blockchain files at creation time, since
   S0.3 deferred CX-side audit-mode wiring to E6 file creation):
   - `paperclips/roles-codex/cx-blockchain-engineer.md` (with audit-mode include)
   - `paperclips/roles-codex/cx-security-auditor.md` (with audit-mode include)
   - `paperclips/roles-codex/cx-python-engineer-2.md`
3. Role files include all standard fragments (handoff,
   atomic-handoff, audit-mode prompts post-S0.3, QA-evidence,
   wire-contract rules) per
   `feedback_slim_both_claude_codex.md`.
4. CX-side counterparts for `BlockchainEngineer`/`SecurityAuditor`
   added to **`paperclips-shared-fragments` submodule** if any
   blockchain-/security-specific fragments emerge during authoring;
   otherwise role files can stay self-contained.
5. Agents pass first smoke: each reassigned a trivial probe issue and
   posts a heartbeat comment within 2-3h on iMac runtime.
6. `roadmap.md` E6 row updated 📦 → ✅ with merge SHA.
7. `feedback_slim_both_claude_codex.md` updated to acknowledge CX team
   now has full audit-Phase domain coverage.
8. `project_dual_team_architecture.md` memory updated to note CX is at
   parity (was "9 roles, no blockchain/security yet").

## 2. Why now / why this scope

Operator decision 2026-05-07 (this session) flipped the team load to
35/65 in favour of Codex on the basis that:

- Codex tokens are cheaper per equivalent unit of work.
- Claude resources (engineers / context budgets) are scarce relative
  to roadmap size (~50 NOT-DONE units).
- Blocking the 65% swap is the absence of three role families on CX:
  - Smart-contract / blockchain-domain (#40, B1, C2, C4).
  - Security audit / taint-analysis / PII (#35, audit-Phase domain).
  - Sufficient Python-orchestration bandwidth for swapped extractors.

E6 was previously listed in `roadmap.md` Phase 6 with status `📦` and
trigger "Phase 4 (smart contract / Rust work needs them)". Rev3 of
the audit-v1 plan plus operator's 2026-05-07 swap-decision **promote
E6 from deferred to a prereq for the entire 65% swap**.

E6 cannot be parallelised with the swap-receiving slices — those slices
need the new agents to exist. So E6 is **dependency-zero, must finish
first**, even though it doesn't ship product feature.

## 3. Scope

### 3.1 In scope

- Three new agent identities in paperclip company `9d8f432c-...`.
  Each agent gets:
  - UUID, `name`, display title, generated `urlKey`.
  - Adapter set to `codex_local` (CX team standard).
  - Initial `status = idle`.
  - Workspace root pinned to CX worktree per
    `feedback_team_workspace_dirs_persistent.md`
    (`/Users/Shared/Ios/worktrees/cx/Gimle-Palace`, live-verified
    from existing CX agent configs on 2026-05-07).
- Three role files under `paperclips/roles-codex/` (kebab-case per
  rev4 — matching existing `cx-code-reviewer.md` / `cx-cto.md`):
  - `cx-blockchain-engineer.md`
  - `cx-security-auditor.md`
  - `cx-python-engineer-2.md`
- Each role file contains:
  - Standard role-fragment includes (handoff, plan-first, qa-evidence,
    wire-contract, atomic-handoff, slim-discipline).
  - Role-specific responsibilities section.
  - Audit-mode prompt section (post-S0.3 fragment).
  - Domain-knowledge anchors (e.g., for BlockchainEngineer:
    "knows EVM call semantics, Solidity ABI, Anchor IDL, FunC
    cell layouts, SLIP-0044 registry").
- AGENTS.md re-render on iMac via existing `imac-agents-deploy.sh`
  pipeline.
- Smoke-probe issue per new agent: trivial paperclip issue assigned to
  the new agent with "post a heartbeat comment confirming you're alive
  and your workspace is on CX team root
  `/Users/Shared/Ios/worktrees/cx/Gimle-Palace`".

### 3.2 Out of scope

- New shared fragments — only added if authoring surfaces a need.
- Cross-team workflow / handoff changes (existing rules apply).
- Rebalancing existing assignments — that's the swap-receiver slices.
- Auditor role agent (a Phase 2 Audit agent in S1.7, distinct from
  SecurityAuditor; handled in S1).

## 4. Files in scope

| File | Action | Why |
|---|---|---|
| `paperclips/roles-codex/cx-blockchain-engineer.md` | new | Role file for new agent (kebab-case rev4) |
| `paperclips/roles-codex/cx-security-auditor.md` | new | Role file for new agent (kebab-case rev4) |
| `paperclips/roles-codex/cx-python-engineer-2.md` | new | Role file for new agent (D-1 may rename) |
| `paperclips/scripts/curate-claude-plugins.sh` | maybe touch | If parity wiring needs sibling update |
| `paperclips/agents/agent-id-table.md` (if exists) or Board memory `reference_agent_ids.md` | update | Registry of agent UUIDs |
| `docs/roadmap.md` E6 row | update | Status transition 📦 → ✅ |

NOT in scope (do not touch unless authoring surfaces a need):
- Existing CX role files.
- Claude-side role files.
- `paperclip-shared-fragments` submodule (touch only if a generalisable
  fragment emerges; otherwise role files self-contain).

## 5. Decision points

| ID | Question | Default | Impact of non-default |
|----|----------|---------|----------------------|
| **E6-D1** | Name of the third agent — `cx-python-engineer-2` (parallels existing `cx-python-engineer`) or `cx-claude-affinity-engineer` (signals "absorbs swapped Claude work") or domain-specific (`cx-llm-orchestrator` if mostly LLM extractors)? | `cx-python-engineer-2` (least ambiguous, matches kebab-case CX naming per rev4) | non-default name forces re-check of role-file fragment includes |
| **E6-D2** | All three agents share a single Python-orch fragment, or each role-specific? | shared (per slim-discipline; reduce drift) | role-specific = more drift risk over time |
| **E6-D3** | Do new agents inherit existing CX team workspace root, or get a sub-root? | inherit (same root, different branches) | sub-roots break the persistent-workspace rule from `feedback_team_workspace_dirs_persistent.md` |
| **E6-D4** | Smoke probe issue per agent or one combined "introduce yourselves" issue? | per-agent (cleaner audit trail) | combined risks paperclip's "one assignee" rule |
| **E6-D5** | Existing CX agents (CXCTO, CXCodeReviewer, etc) — do their role files need any update because of the new arrivals? | review pass only; no automatic edits | a sweep edit risks drift in unrelated rules |

### 5.1 CXCTO formalisation decisions (2026-05-07)

Решения ниже закрывают E6-D1..D5 для plan-first review и последующей
Board-реализации:

- **E6-D1:** выбран третий агент `CXPythonEngineer2`, role file
  `paperclips/roles-codex/cx-python-engineer-2.md`. Не использовать
  `cx-claude-affinity-engineer` или доменное имя: текущая цель —
  второй CXPythonEngineer-class исполнитель, а не новая специализация.
- **E6-D2:** новых shared-фрагментов в E6 не заводить по умолчанию.
  Все три роли должны использовать существующий стандартный набор
  фрагментов; role-specific секции остаются в role files. Если Board
  при авторинге найдёт реально переиспользуемый fragment need, это
  отдельное замечание в PR body, не silent scope growth.
- **E6-D3:** все три агента наследуют live CX root
  `/Users/Shared/Ios/worktrees/cx/Gimle-Palace`. Иной root из раннего
  draft считается устаревшим.
- **E6-D4:** smoke-probe issues создаются отдельно для каждого агента.
  SLA heartbeat: 2-3h, не 1h.
- **E6-D5:** существующие CX role files не менять автоматически.
  Допускается только review pass; любые правки существующих ролей
  должны быть явно обоснованы как необходимые для E6.

Live pre-check 2026-05-07:

- В компании уже существуют Claude-side `BlockchainEngineer`
  (`9874ad7a-dfbc-49b0-b3ed-d0efda6453bb`) и `SecurityAuditor`
  (`a56f9e4a-ef9c-46d4-a736-1db5e19bbde4`). Новые Codex агенты
  MUST использовать CX-prefixed names: `CXBlockchainEngineer`,
  `CXSecurityAuditor`, `CXPythonEngineer2`.
- Hire path MUST use `POST /api/companies/:companyId/agent-hires`
  with `sourceIssueId=8ca15837-8dc4-4799-adfa-30d3e4486fee`.
  Direct create payloads using legacy `nameKey` are stale for this
  slice.
- Reporting line for all three: CXCTO
  `da97dbd9-6627-48d0-b421-66af0750eacf`.
- Icons: `gem` for `CXBlockchainEngineer`, `shield` for
  `CXSecurityAuditor`, `code` for `CXPythonEngineer2`.
- Runtime heartbeat remains disabled with `wakeOnDemand=true`, matching
  current CX team convention.

## 6. Test plan summary

E6 is a **role-authoring + provisioning** slice — there's no Python
unit testing in the conventional sense. Validation is operational:

- **Static**: each new role file passes markdown-lint, `bash paperclips/build.sh --target codex` exits 0, and `bash paperclips/validate-codex-target.sh` exits 0 with no missing include, oversize, or forbidden-runtime-reference findings.
- **Operational**: each new agent is reassigned a smoke-probe issue
  on iMac runtime; agent must:
  - Post heartbeat comment within 2-3h (rev4 — was 1h; CTO-E6-M1 found
    1h optimistic given known SIGTERM trap from `feedback_max_turns_per_run.md`,
    first-run workspace setup, role-file render time).
  - Reference its workspace root in the comment.
  - Confirm role-fragment-includes are in its rendered AGENTS.md.
- **Cross-language consistency**: rendered AGENTS.md for each new
  agent contains the standard set of sections (Goal, Responsibilities,
  Audit mode, Handoff, QA evidence, Wire contract). Verified by
  text-grep against template.

## 7. Risks

- **R1**: a new agent has a stale `status=error` after first run,
  blocking the swap. Mitigation: smoke-probe step explicitly tests
  status transition `idle → in_progress → idle`.
- **R2**: agent identity duplication — paperclip rejects or confuses
  provisioning if `name` collides with an existing one. Mitigation:
  pre-check via GET `/api/companies/{id}/agents` listing and
  CX-prefixed names.
- **R3**: role-fragment drift between Claude- and Codex-side BlockchainEng
  / SecurityAud (since Claude side already has them). Mitigation: 
  start by copying Claude-side as base, then strip Claude-only references
  (workspace path, bash worker dirs).
- **R4**: workspace conflict if new agents pick the wrong root and try
  to write to Claude tree. Mitigation: explicit CX workspace root
  `/Users/Shared/Ios/worktrees/cx/Gimle-Palace` in role-file
  front-matter and adapter config.

## 8. Dependencies

**Hard dependencies**: none. E6 can start day-0 in parallel with S0
(Audit-V1 prereqs) — different file trees, no overlap.

**E6 unblocks**: every "swapped to Codex" slice that needs blockchain /
security / Python-orch domain expertise. Specifically:
- All Indep Claude-affinity SWAPPED extractors (#2 #10 #13 #15 #16 #19
  #20 #30 #34 #35 #36) — 11 slices.
- Chain-Sol (B1 → C2/C4) — 3 slices.
- Chain-Hist after Claude finishes #22 (#11 #26 #43) — 3 slices.
- Phase 4 ecosystem expansion B1/B4-B8 — partial.

**Post-E6 queue handoff:** before GIM-229 is closed, CXCTO MUST open or
verify the next active Codex-queue issue for Coding Convention Extractor (#6)
and create/park downstream queue issues for Testability/DI (#8), Hot-Path
Profiler (#17), and Localization & Accessibility (#9). The closure comment
MUST link those issue IDs; #8/#17/#9 must have explicit blocker/queue
metadata instead of relying on roadmap memory.

## 9. Cross-references

- Operator decision 2026-05-07 (this session): "Просто наймем
  BlockchainEngineer + SecurityAuditor для CX команды. И добавим
  навыков Python orchestration ... И просто swap работ".
- `roadmap.md` row E6 (Phase 6 meta).
- `project_dual_team_architecture.md` memory (CX team currently
  9 roles, no Blockchain/Security parity).
- `feedback_slim_both_claude_codex.md` (every role/fragment touch
  must hit BOTH team trees).
- `feedback_team_workspace_dirs_persistent.md` (workspace dirs are
  persistent — new agents inherit, don't carve sub-roots).
- Companion: `2026-05-07-cx-team-hire-blockchain-security-pyorch_plan.md`.
