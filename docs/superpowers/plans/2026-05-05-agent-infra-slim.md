---
title: Agent Infrastructure Slim — Plugin / Subagent / Skill Cleanup
date: 2026-05-05
status: draft
owner: operator (Anton)
branch: core/fix-agent-infra-slim
---

# Agent Infrastructure Slim

> **Goal:** Reduce eager-loaded token cost on every paperclip-agent wake AND operator session by removing unused plugin/subagent/skill definitions. Apply Variant A — keep only subagents with **confirmed runtime usage** (last 30 days, 464 sessions).

## Decision summary

- **Strategy:** Variant A — minimum viable subagent set per role. Curate to ≤5 subagents. Drop everything not invoked in 30-day window.
- **Token economics**: ~6,144 t voltagent dead weight × 464 wakes × 30d ≈ **2.85M tokens/month** wasted on unused agent definitions in paperclip runtime (≈$32/mo Opus, $8.50/mo Sonnet). Comparable saving on operator session.
- **Risk policy:** zero-risk drops first; aspirational/future-proofing items go to a separate "deferred" bucket with operator sign-off.

## Audit data (frozen 2026-05-05)

### Subagent invocations on paperclip iMac runtime — 464 sessions, last ~30 days

| Subagent | Calls | Invoked by |
|---|---:|---|
| `Explore` (built-in) | 24 | CTO, CR, PE, MCPE, ResearchAgent |
| `code-reviewer` (no prefix; origin TBD Phase 0) | 6 | CTO |
| `voltagent-qa-sec:code-reviewer` | 4 | CR (2), CTO (2) |
| `deep-research-agent` (origin TBD Phase 0) | 3 | CR |
| `voltagent-research:search-specialist` | 1 | ResearchAgent |
| `pr-review-toolkit:pr-test-analyzer` | 1 | CTO |
| `general-purpose` (built-in) | 1 | CR |
| **everything else** (≥85 voltagent + ≥5 pr-review-toolkit) | **0** | — |

### Skill invocations

| Skill | Calls |
|---|---:|
| `paperclip` | 449 (workflow orchestrator — must keep) |
| `superpowers:writing-plans` | 4 |
| `superpowers:executing-plans` | 4 |
| `superpowers:test-driven-development` | 3 |
| `superpowers:receiving-code-review` | 3 |
| `update-config` | 1 |
| **everything else** (~50 skills) | **0** |

### Per-role tool activity (last 30 days)

| Role | Sessions | Tools | Subagents called |
|---|---:|---:|---|
| CTO | 159 | 6,198 | Explore (7), code-reviewer (6), voltagent-qa-sec:code-reviewer (2), pr-review-toolkit:pr-test-analyzer (1) |
| CodeReviewer | 105 | 5,386 | Explore (5), deep-research-agent (3), voltagent-qa-sec:code-reviewer (2), general-purpose (1) |
| PythonEngineer | 68 | 4,346 | Explore (6) |
| QAEngineer | 42 | 2,704 | none |
| OpusArchitectReviewer | 29 | 1,110 | none |
| MCPEngineer | 26 | 1,300 | Explore (2) |
| ResearchAgent | 16 | 433 | Explore (4), voltagent-research:search-specialist (1) |
| TechnicalWriter | 8 | 98 | none |
| InfraEngineer | 5 | 190 | none |
| SecurityAuditor | 4 | 34 | none |
| BlockchainEngineer | 1 | 9 | none |
| codex-ArchitectReviewer | 1 | 22 | none |

### Plugin token cost (eager-loaded per wake, est. bytes/4)

| Plugin | Eager t | Used in runtime? |
|---|---:|---|
| voltagent-lang (29 agents) | 2,129 | ❌ 0 calls |
| voltagent-infra (16) | 1,195 | ❌ 0 calls |
| voltagent-qa-sec (14) | 921 | ⚠ 4 calls (only `code-reviewer`) |
| voltagent-core-dev (10) | 723 | ❌ 0 calls |
| voltagent-meta (10) | 630 | ❌ 0 calls |
| voltagent-research (7) | 546 | ⚠ 1 call (only `search-specialist`) |
| pr-review-toolkit (6) | 642 | ⚠ 1 call (only `pr-test-analyzer`) |
| frontend-design | 63 | ❌ 0 calls |

## Final keep lists

### Subagent keep (operator + iMac runtime)

**Confirmed by usage:**
- `voltagent-qa-sec:code-reviewer` (4 calls)
- `voltagent-research:search-specialist` (1 call)
- `pr-review-toolkit:pr-test-analyzer` (1 call)

**Built-in / user-level (always available, no plugin disable affects):**
- `Explore`
- `general-purpose`
- `deep-research-agent` (origin TBD — Phase 0)
- `code-reviewer` (origin TBD — Phase 0; possibly `code-review:code-reviewer` plugin)

**Operator decision pending — future iOS/Android (currently 0 calls):**
- `voltagent-lang:swift-expert` (BlockchainEngineer aspirational)
- `voltagent-lang:kotlin-specialist` (BlockchainEngineer aspirational)

### Plugin keep / drop

| Plugin | Action | Notes |
|---|---|---|
| voltagent-lang | **DROP** (or keep if operator wants iOS prep) | 0 calls; aspirational refs only in BlockchainEngineer |
| voltagent-meta | **DROP** | 0 calls |
| voltagent-infra | **DROP** | 0 calls |
| voltagent-core-dev | **DROP** | 0 calls |
| voltagent-qa-sec | **KEEP plugin** but remove most agents | only `code-reviewer` used; alternative: extract to user-level + drop plugin |
| voltagent-research | **KEEP plugin** but remove most agents | only `search-specialist` used; alternative: extract |
| pr-review-toolkit | **KEEP plugin** but remove most agents | only `pr-test-analyzer` used |
| frontend-design | **DROP** | 0 calls |
| code-review | TBD — verify in Phase 0 | might be source of `code-reviewer` no-prefix |

### Skill keep

- `paperclip` (mandatory — workflow orchestrator)
- `superpowers:writing-plans`, `executing-plans`, `test-driven-development`, `receiving-code-review` (≥3 calls each)
- `update-config` (1 call — operator-only utility)

**Drop**: `kmp`, `swift-*`, `swiftui-*`, `swiftdata-*`, `swift-testing-pro`, `swift-concurrency-pro`, `research`, `research-deep`, `research-add-fields`, `research-add-items`, `research-report`, `codebase-memory`, `prime`, all other unused user-level skills.

### Per-role subagent matrix (target ≤5 subagents per role)

| Role | Keep list | Count |
|---|---|---:|
| **CTO** | Explore, code-reviewer (after Phase 0 resolves), voltagent-qa-sec:code-reviewer, pr-review-toolkit:pr-test-analyzer, general-purpose | 5 |
| **CodeReviewer** | Explore, deep-research-agent, voltagent-qa-sec:code-reviewer, general-purpose | 4 |
| **PythonEngineer** | Explore, general-purpose | 2 |
| **MCPEngineer** | Explore, general-purpose | 2 |
| **QAEngineer** | Explore | 1 |
| **OpusArchitectReviewer** | Explore, general-purpose | 2 |
| **ResearchAgent** | Explore, voltagent-research:search-specialist, deep-research-agent | 3 |
| **TechnicalWriter** | Explore | 1 |
| **InfraEngineer** | Explore | 1 |
| **SecurityAuditor** | Explore, voltagent-qa-sec:code-reviewer (for security PR review) | 2 |
| **BlockchainEngineer** | Explore (idle role; minimal viable) | 1 |
| **cx-CTO** | mirror claude:CTO | 5 |
| **cx-CodeReviewer** | mirror claude:CR (after coverage gap fix per separate slice) | 4 |
| **cx-PythonEngineer** | mirror claude:PE | 2 |
| **cx-MCPEngineer** | mirror claude:MCPE | 2 |
| **cx-QAEngineer** | mirror claude:QA | 1 |
| **cx-InfraEngineer** | mirror claude:Infra | 1 |
| **cx-TechnicalWriter** | mirror claude:TW | 1 |
| **cx-ResearchAgent** | mirror claude:Research | 3 |
| **codex-ArchitectReviewer** | Explore, general-purpose | 2 |

---

## Phase plan

Each phase is independent and reversible. Apply in order; gate next phase on previous phase smoke-passing.

### Phase 0 — Verify subagent origins (READ-ONLY, no changes)

**Goal:** Identify which plugin (or user-level) provides `code-reviewer` (no prefix) and `deep-research-agent`. Without this, we cannot decide whether keeping these subagents requires a specific plugin to stay enabled.

**Tasks:**
- [ ] Inspect `~/.claude/plugins/cache/code-review/...` — does it provide a `code-reviewer` agent? Same prefix or different?
- [ ] Inspect `~/.claude/agents/` and `~/.paperclip/.../agents/` — any user-level `code-reviewer.md` or `deep-research-agent.md`?
- [ ] On iMac: same checks at `/Users/anton/.claude/plugins/cache/` and `/Users/anton/.claude/agents/`.
- [ ] Pick a sample session jsonl from CTO that called `code-reviewer` — inspect the system prompt's Agent tool description to see what plugin/source resolved that name.

**Acceptance:** clear mapping `code-reviewer` → `<plugin>:<name>` or `user-level:<path>`. Same for `deep-research-agent`.

**Output:** updated "Subagent keep" section above with resolved origins.

---

### Phase 1 — Plugin disable on operator session (zero risk, fast iteration)

**Goal:** Remove eager-loaded weight of unused plugins from operator's `~/.claude/settings.json`. Operator never invokes voltagent subagents directly, so 0 functional impact.

**Tasks:**
- [ ] **Backup:** copy `~/.claude/settings.json` → `~/.claude/settings.json.bak.2026-05-05` (manual restore on regression).
- [ ] **Edit settings.json** to disable plugins via `disabledPlugins` (or use `enabledPlugins` allowlist):
  ```json
  {
    "disabledPlugins": [
      "voltagent-lang@voltagent-subagents",
      "voltagent-meta@voltagent-subagents",
      "voltagent-infra@voltagent-subagents",
      "voltagent-core-dev@voltagent-subagents",
      "frontend-design@claude-plugins-official"
    ]
  }
  ```
  (Exact key name depends on Claude Code version — verify via `update-config` skill or docs.)
- [ ] **Smoke:** new operator session, verify Agent tool docstring no longer lists voltagent-lang/meta/infra/core-dev/frontend-design agents.
- [ ] **Measure:** count tokens of new `Agent` tool description vs baseline. Target: ≥4,500 t reduction.

**Acceptance:** new operator session loads with ≥4,500 t fewer eager tokens. No functional regression (Explore + built-ins still work).

**Rollback:** restore settings.json from `.bak.2026-05-05`.

---

### Phase 2 — Plugin disable on iMac paperclip runtime (zero-risk subset)

**Goal:** Same as Phase 1 but for paperclip-agent runtime on iMac.

**Tasks:**
- [ ] **Backup** iMac `/Users/anton/.claude/settings.json` (and any per-instance settings under `/Users/anton/.paperclip/.../`).
- [ ] **Edit** iMac settings.json mirroring Phase 1.
- [ ] **Restart paperclip launchd** to ensure agents reload settings on next wake (if needed; new sessions pick up new settings on cold start by default).
- [ ] **Smoke:** wake one active role (e.g., PythonEngineer via test issue assign + immediate cancel) — verify session loads, Bash/Read/Edit work.
- [ ] **Measure:** sample new paperclip session jsonl — count Agent tool description size, compare baseline.

**Acceptance:** active paperclip role wakes successfully with smaller bundle. Bundle size baseline (`paperclips/bundle-size-baseline.json`) re-measured shows reduction.

**Rollback:** restore iMac settings.json + restart launchd.

---

### Phase 3 — Curate kept plugins (medium risk, single-subagent retention)

**Goal:** Three plugins (`voltagent-qa-sec`, `voltagent-research`, `pr-review-toolkit`) each contribute 1 used + many unused agents. Keep plugin enabled but trim agent count.

**Approach options (evaluate per plugin):**

A) **Plugin-internal trim** (delete unused .md files): risky — plugin auto-update overwrites.
B) **Extract to user-level** + disable plugin: clean, but renames subagent (`voltagent-qa-sec:code-reviewer` → `code-reviewer-qa-sec`); breaks role-file references.
C) **Accept overhead** (keep entire plugin): simplest; ~921 + 546 + 642 = ~2,109 t residual cost per wake.

**Decision criteria per plugin:**
- voltagent-qa-sec: 14 agents @ 921t → 1 used → keep but accept 13 dead refs (~850t overhead) **OR** extract to user-level (best for slim).
- voltagent-research: 7 agents @ 546t → 1 used → same logic (~470t overhead).
- pr-review-toolkit: 6 agents @ 642t → 1 used → same (~530t overhead).

**Tasks (assume option C — accept overhead — for first iteration):**
- [ ] No action; revisit in Phase 6 if combined overhead (~2,109t) needs further trim.

**Tasks (option B — extract — if Phase 1+2 results undershoot target):**
- [ ] Copy `<plugin>/<used-agent>.md` → `~/.claude/agents/<used-agent>.md` (user-level).
- [ ] Update all role files referencing the original prefix to the new prefix-less name.
- [ ] Disable plugin.
- [ ] Smoke each role that references the agent.

**Acceptance:** decision documented; if option B chosen, all role-file references updated atomically.

---

### Phase 4 — Role .md cleanup (per-role subagent matrix application)

**Goal:** Apply per-role subagent matrix from "Final keep lists" section. Each of 20 role .md files has its `## MCP / Subagents / Skills` section reduced to the keep-list for that role.

**Tasks (one task per role family):**
- [ ] **claude:CTO** — `paperclips/roles/cto.md` MCP/Subagents/Skills section: replace with:
  ```markdown
  ## Subagents
  - `Explore` (codebase exploration)
  - `code-reviewer` (delegate code review)
  - `voltagent-qa-sec:code-reviewer` (deep review)
  - `pr-review-toolkit:pr-test-analyzer` (test coverage audit)
  - `general-purpose` (fallback)
  ```
- [ ] **claude:CodeReviewer** — `paperclips/roles/code-reviewer.md`: keep Explore, deep-research-agent, voltagent-qa-sec:code-reviewer, general-purpose.
- [ ] **claude:PythonEngineer** — `paperclips/roles/python-engineer.md`: keep Explore, general-purpose.
- [ ] **claude:MCPEngineer** — `paperclips/roles/mcp-engineer.md`: keep Explore, general-purpose.
- [ ] **claude:QAEngineer** — keep Explore.
- [ ] **claude:OpusArchitectReviewer** — keep Explore, general-purpose. **Drop** all aspirational voltagent-qa-sec/voltagent-research lists.
- [ ] **claude:ResearchAgent** — keep Explore, voltagent-research:search-specialist, deep-research-agent.
- [ ] **claude:TechnicalWriter** — keep Explore. Drop voltagent-meta:knowledge-synthesizer ref.
- [ ] **claude:InfraEngineer** — keep Explore. Drop entire voltagent-infra delegation matrix.
- [ ] **claude:SecurityAuditor** — keep Explore, voltagent-qa-sec:code-reviewer. Drop massive voltagent delegation tree.
- [ ] **claude:BlockchainEngineer** — keep Explore. Drop voltagent-lang aspirational table.
- [ ] **codex variants** (9 roles) — mirror claude variants per matrix.

**Acceptance:** every role .md has ≤5 subagents listed in MCP/Subagents/Skills section. Removed text doesn't appear in any subsequent rendered bundle.

**Side benefit:** removed text = removed eager bundle weight. Estimated: 200–600 t saved per role × 20 roles = 4,000–12,000 t total fleet impact reduction (one-time, persistent).

---

### Phase 5 — Skill cleanup (user-level + plugin-level)

**Goal:** Disable / uninstall skills with 0 invocations in 30-day audit window.

**Tasks:**
- [ ] **Audit user-level skills** (`~/.claude/skills/`): keep only those operator wants. Candidates to keep: `update-config`, `prime`, `init`, `review`, `security-review` (utility skills); `swiftui-pro`, `swift-testing-pro`, `swiftdata-pro`, `swift-concurrency-pro`, `kmp`, `swiftui-development`, `swiftui-patterns` — operator decision (iOS roadmap relevance).
- [ ] **Audit plugin skills**: `superpowers:*` — keep only invoked ones (writing-plans, executing-plans, test-driven-development, receiving-code-review) and frequently-needed planning skills (brainstorming, verification-before-completion). Drop `code-review:*`, `pr-review-toolkit:review-pr` etc. unless verified.
- [ ] **Mirror to iMac** runtime.

**Acceptance:** skill list in system reminder ≤15 skills. New session loads ≥1,000 t fewer eager tokens vs Phase 0 baseline.

---

### Phase 6 — Validation + measurement

**Goal:** Confirm slim achieved, no functional regressions.

**Tasks:**
- [ ] **Re-render bundles**: `bash paperclips/build.sh --target claude && bash paperclips/build.sh --target codex`.
- [ ] **Re-run** `python3 paperclips/scripts/validate_instructions.py` — confirm no rule coverage regression (markers from `instruction-coverage.matrix.yaml` still match).
- [ ] **Re-measure** `paperclips/bundle-size-baseline.json` — capture per-role byte/token reduction.
- [ ] **Smoke matrix** — for each of 12 active roles (CTO down to BlockchainEngineer): assign a benign test issue, verify wake + idle-exit (don't actually do work). Confirm:
  - Bundle loads
  - No "subagent not found" errors in session jsonl
  - paperclip skill invokes successfully
- [ ] **Re-run audit script** (`/tmp/agent-tool-audit.py`) on next 7-day window post-deploy. Confirm no functional regression (no agent silently failing because subagent missing).

**Acceptance:** 
- All 12 active roles wake and idle-exit cleanly (12/12 smoke pass).
- Median claude bundle ≤5,000 t (target — cf. GIM-189 acceptance criteria of ≤25 KB ≈ ≤6,250 t).
- No `validate_instructions.py` failures.
- 7-day post-deploy: no agent stuck or escalation due to missing subagent.

**Rollback (per phase, independently):** each phase has its own backup + restore step.

---

## Token reduction estimate (cumulative)

| Phase | Δ per wake | Δ per 30 days × 464 wakes |
|---|---:|---:|
| 1 (operator session disable) | −4,677 t | n/a (operator session, not paperclip) |
| 2 (iMac runtime disable: lang+meta+infra+core-dev+frontend-design) | −4,740 t | **−2.20M t** |
| 3 (option B extract — optional, +1,860 t) | −1,860 t | −0.86M t |
| 4 (role .md cleanup — 200–600 t/role × 20 roles, fleet-fraction wakes) | −400 t avg | −185K t (paperclip share) |
| 5 (skill cleanup) | −1,000 t | −464K t |
| **Total (Phases 1+2+4+5, conservative)** | **~6,140 t per wake** | **~2.85M tokens / month** |
| **Total (+ Phase 3 option B)** | **~8,000 t per wake** | **~3.71M tokens / month** |

At Sonnet 4.6 input rate $0.003/1K: ≈ $8.50/mo savings.
At Opus 4.7 input rate $0.015/1K: ≈ $42/mo savings.

(Plus operator session — comparable savings, separate budget.)

---

## Cross-references

- Audit script: `/tmp/agent-tool-audit.py` (read paperclip session jsonl, count subagent/skill calls per role).
- Bundle-size baseline: `paperclips/bundle-size-baseline.json`.
- Coverage matrix: `paperclips/instruction-coverage.matrix.yaml` (machine-readable rule-coverage spec).
- Related slices: GIM-189 (bundle-slim — split phase-handoff + compliance-enforcement); separate slice planned for codex:cx-code-reviewer coverage gap fix.

---

## Open questions for operator

1. **iOS prep:** keep `voltagent-lang:swift-expert` + `voltagent-lang:kotlin-specialist` for future iOS/Android wallet work? (Cost: ~150t per wake to keep both. Drop saves another ~150t.)
2. **Phase 3 strategy:** option C (accept ~2,100t plugin overhead) for simplicity, or option B (extract subagents to user-level, lose role-file dispatch names) for maximum slim?
3. **Skill keep**: any user-level skill (kmp, swiftui-*, etc.) operator anticipates needing in next 90 days even if 0 calls in past 30?
4. **Phase order**: ship Phase 1 (operator session, fastest verification) first, then Phase 2+, OR all at once via paperclip slice?

---

_End of plan_
