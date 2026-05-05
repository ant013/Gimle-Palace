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

**Operator decision Q1 (CONFIRMED 2026-05-05):**
- `voltagent-lang:swift-expert` — **KEEP** for BlockchainEngineer (future iOS wallet review)
- `voltagent-lang:kotlin-specialist` — **KEEP** for BlockchainEngineer (future Android wallet review)
- All other 27 voltagent-lang agents — **DROP**

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

### Phase 0.5 — Per-role deep audit (READ-ONLY)

**Goal:** Replicate the depth of audit done for `claude:code-reviewer` for the remaining **19 roles**. Without this, Phase 4 cleanup is blind beyond CR.

**Background:** The CR audit (2026-05-05) found:
- 2 inline-vs-fragment **duplicates** (L84-88 plan-first → already in `plan-first-review.md`; L124-141 phase-3.1-file-structure → already in `phase-review-discipline.md`).
- **Coverage matrix gaps** in `claude:code-reviewer` (missing `karpathy-discipline.md` and `pre-work-discovery.md` per matrix).
- **Massive coverage gap** in `codex:cx-code-reviewer` (12 fragments missing).
- **18+ aspirational voltagent subagent references** in MCP/Subagents/Skills section (only 2 actually invoked).

These same patterns likely exist in other roles. Need systematic discovery.

**Tasks:**

- [ ] **Per-role inline duplication audit** (20 roles):
  - For each `paperclips/roles/*.md` and `paperclips/roles-codex/*.md`:
    - Read inline content
    - For each shared fragment listed in `<!-- @include -->` directives, diff inline content vs fragment content
    - Flag exact-duplication blocks (>5 lines redundant) for deletion in Phase 4
  - **Output:** `/tmp/role-inline-duplication-report.md` table with `role | inline-line-range | duplicates-fragment | tokens-savings`

- [ ] **Per-role coverage gap audit** (20 roles):
  - Re-run `/tmp/bundle-audit.json` with deeper analysis: not only "extra/missing fragments" but also:
    - Fragment present but **not actually relevant** (e.g., `compliance-enforcement.md` in PE — review-frame doesn't fit implementer)
    - Inline rule that's NOT in any shared fragment but is **role-universal** → candidate to extract into new fragment
  - **Output:** updated `bundle-audit.json` with per-role gap classification

- [ ] **Per-role aspirational-subagent audit** (20 roles):
  - For each role's `## MCP / Subagents / Skills` section, list every subagent mention.
  - Cross-reference against actual invocation data (from `/tmp/agent-tool-audit.py` results).
  - Mark each as: **USED** (≥1 call), **REFERENCED-NEVER-CALLED** (in role file but 0 calls), **NEW-CANDIDATE** (in keep-list but not yet in role file).
  - **Output:** per-role keep/drop subagent matrix.

- [ ] **Cross-team consistency audit**: claude:CR vs codex:cx-CR pattern (12 fragments missing in cx-CR per earlier audit). Apply same comparison to all paired roles:
  - claude:CTO vs codex:cx-CTO
  - claude:PE vs codex:cx-PE
  - claude:MCPE vs codex:cx-MCPE
  - claude:Infra vs codex:cx-Infra
  - claude:QA vs codex:cx-QA
  - claude:TW vs codex:cx-TW
  - claude:Research vs codex:cx-Research
  - claude:Opus vs codex:codex-architect-reviewer
  - **Output:** cross-team coverage gap report — what codex variants need to add for parity.

**Acceptance:** 4 reports generated, reviewed by operator; concrete cleanup task list per role drafted; **bundle slim target re-estimated** with full data instead of CR-only extrapolation.

**Estimated work:** 1–2 sessions (read all 20 role files + cross-reference fragments).

**Why before Phase 4:** Phase 4 (role .md cleanup) needs concrete inline-duplication targets per role, not generic "trim subagents" guidance. Without this audit, Phase 4 either undershoots or breaks rules silently.

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

### Phase 3 — Curate kept plugins via Path-1 (file-level rm in plugin cache)

**Goal:** Four plugins (`voltagent-qa-sec`, `voltagent-research`, `pr-review-toolkit`, `voltagent-lang`) each contribute 1–2 used + many unused agents. Keep plugin enabled, delete unused .md files in plugin cache.

**Decision (CONFIRMED 2026-05-05):** Path-1 — `rm` unused .md files in plugin cache, preserving subagent name prefixes (no role-file changes needed). Catalog (`awesome-claude-code-subagents`) explicitly supports this via official Subagent Storage Locations table — `~/.claude/plugins/cache/<plugin>/<ver>/*.md` is the canonical delivery; per-file curation is the supported customization model.

**Risk mitigation:** `/plugins update voltagent-*` will restore deleted files. Mitigation: don't auto-update; document curate-script (`paperclips/scripts/curate-voltagent.sh`) for re-run after updates.

**Tasks:**

- [ ] **Write curate script** `paperclips/scripts/curate-voltagent.sh`:
  ```bash
  #!/usr/bin/env bash
  set -euo pipefail
  
  KEEP=(
    "voltagent-qa-sec/code-reviewer.md"
    "voltagent-research/search-specialist.md"
    "voltagent-lang/swift-expert.md"
    "voltagent-lang/kotlin-specialist.md"
  )
  
  CACHE_ROOT="${1:-$HOME/.claude/plugins/cache/voltagent-subagents}"
  
  for plugin_dir in "$CACHE_ROOT"/*/; do
    plugin_name=$(basename "$plugin_dir")
    for ver_dir in "$plugin_dir"*/; do
      [ -d "$ver_dir" ] || continue
      for md in "$ver_dir"*.md; do
        [ -e "$md" ] || continue
        agent=$(basename "$md" .md)
        rel="${plugin_name}/${agent}.md"
        if [ "$agent" = "README" ] || [ "$agent" = "LICENSE" ] || [ "$agent" = "CHANGELOG" ]; then continue; fi
        keep=0
        for k in "${KEEP[@]}"; do [ "$k" = "$rel" ] && keep=1 && break; done
        if [ "$keep" -eq 0 ]; then
          echo "rm $md"
          rm -- "$md"
        fi
      done
    done
  done
  ```

- [ ] **Curate pr-review-toolkit similarly** (separate plugin under `claude-plugins-official`):
  - Keep: `pr-test-analyzer.md`
  - rm: `silent-failure-hunter.md`, `type-design-analyzer.md`, `code-simplifier.md`, `code-reviewer.md`, `comment-analyzer.md`

- [ ] **Apply on operator session** (`~/.claude/plugins/cache/...`).
- [ ] **Apply on iMac paperclip runtime** via SSH (same paths under `/Users/anton/.claude/plugins/cache/...`).

**Per-role isolation (optional — strict Q1 reading):** if "только для тех ролей которые используют" means Blockchain-only access to swift/kotlin specialists, edit per-workspace `~/.paperclip/instances/default/workspaces/<role-uuid>/.claude/settings.json` to disable `voltagent-lang` for non-Blockchain roles. Default approach: keep simple — global cache curated to 2 lang agents, all roles see them in Agent docstring (~140t cost per wake for non-Blockchain — acceptable).

**Token saving (Path-1):**
- voltagent-qa-sec: 13 of 14 agents removed → −851 t per wake
- voltagent-research: 6 of 7 agents removed → −476 t per wake
- voltagent-lang: 27 of 29 agents removed → −1,985 t per wake
- pr-review-toolkit: 5 of 6 agents removed → −572 t per wake
- **Total Phase 3: −3,884 t per wake** (= ~1.8M tokens/month for paperclip runtime alone)

**Acceptance:** new session lists only kept subagents in Agent tool description; role files unchanged; smoke test on CR (calls `voltagent-qa-sec:code-reviewer`) succeeds.

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

### Phase 5 — Skill cleanup via `desiredSkills` API (corrected from earlier draft)

**Goal:** Per-agent skill curation using paperclip's official `POST /api/agents/:agentId/skills/sync` endpoint. Replaces earlier "file-level rm" approach.

**Background — verified in paperclip 2026.428 docs:**

| Mechanism | Available? | Notes |
|---|---|---|
| Per-agent skill assignment via `desiredSkills` | ✅ YES | Works for **company-imported** skills |
| Built-in `paperclip` skill exclusion per agent | ❌ NO | Auto-loaded by adapter; "Built-in Paperclip runtime skills are still added automatically when required by the adapter." |
| Skill auto-enable on @mention | ✅ YES | v2026.416: "Mentioned skills are automatically enabled for heartbeat runs" |
| User-level skills (`~/.claude/skills/`) precedence | ⚠ TBD | Need smoke test — see Phase 4.5 below |

**Tasks:**

- [ ] **Inventory company skill library**:
  ```bash
  TOKEN=$(cat ~/.paperclip-token)
  curl -sS -H "Authorization: Bearer $TOKEN" \
    "https://paperclip.ant013.work/api/companies/9d8f432c-ff7d-4e3a-bbe3-3cd355f73b64/skills"
  ```
  Outputs which skills are in company library (vs runtime auto-loaded).

- [ ] **Compare with audit data**: which company skills actually invoked per role? Build per-role skills matrix.

- [ ] **Per-role skills sync** (only company-imported skills affected):
  ```bash
  # For each agent:
  curl -sS -X POST -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"desiredSkills": ["paperclip", "<skill1>", "<skill2>"]}' \
    "$URL/api/agents/<agent-id>/skills/sync"
  ```

- [ ] **For built-in `paperclip` skill heartbeat-context concern**: see Phase 4.5/4.6 (terminology clarification + optional user-level override).

- [ ] **For non-company skills** (user-level `~/.claude/skills/` or plugin-installed):
  - On operator session: edit `~/.claude/settings.json` to disable unused plugin-skills (`code-review:code-review`, `frontend-design:frontend-design`, etc.).
  - On iMac: same.
  - These are NOT covered by `desiredSkills` API.

**Acceptance:** company-skills list per agent matches usage data; non-company skills disabled at session level.

---

### Phase 4.5 — Heartbeat terminology clarification (NEW)

**Goal:** Reduce agent confusion between paperclip's "heartbeat" framing and Gimle's actual event-only wake model.

**Background:** Two simultaneous truths in current setup:

1. **Paperclip framework terminology**: "heartbeat" = each wake-execution-window (regardless of trigger). Per `paperclip` skill SKILL.md: "You run in heartbeats". This applies to ALL wakes — scheduled, event, recovery.
2. **Gimle's actual config**: `runtimeConfig.heartbeat.enabled: false` for codex agents (and likely claude). All wakes are event-driven (mention, assignment, blocker-resolved, recovery via watchdog). No scheduled polling.

Agents see paperclip skill's "heartbeat" framing + our heartbeat-discipline.md, may infer "we run on schedule" → confused responses to operator (e.g., 2026-05-05 incident — agent quoted heartbeat language to operator who clarified "we use handoff").

**The accurate framing:**
- "Heartbeat" = wake-execution-window protocol (3-things-check + exit-if-idle).
- "Scheduled heartbeat polling" = **DISABLED** in our config.
- All Gimle wakes are event-triggered.
- The protocol (heartbeat-discipline.md) applies on every wake regardless of trigger.

**Tasks:**

- [ ] **Rename** `paperclips/fragments/shared/fragments/heartbeat-discipline.md` → `wake-discipline.md`. Update all 19 role file `<!-- @include -->` references atomically.
- [ ] **Edit content** to clarify:
  ```diff
  - ## Heartbeat discipline
  + ## Wake discipline (event-driven)
  
  - On every wake (heartbeat or event) check only **three** things:
  + Wakes are event-triggered (assignment, @mention, blocker-resolved, recovery).
  + No scheduled poll runs in this deployment (`runtimeConfig.heartbeat.enabled: false`).
  + On every wake, check only **three** things:
  
  - None of three → **exit immediately** with `No assignments, idle exit`. 
  - Each idle heartbeat must cost **<500 tokens**.
  + None of three → **exit immediately** with `No assignments, idle exit`. 
  + Each idle wake must cost **<500 tokens**.
  
  - Forbidden on idle heartbeat
  + Forbidden on idle wake
  ```
- [ ] **Add reconciliation note** at top of `wake-discipline.md`:
  ```markdown
  > **Note**: paperclip framework uses "heartbeat" generically for any
  > wake-execution-window. In Gimle deployment, scheduled heartbeats are
  > DISABLED — all wakes are event-triggered. When `paperclip` skill or
  > runtime references "heartbeat", interpret as "wake-window".
  ```

**Acceptance:** all 19 role bundles re-render with `wake-discipline.md` instead of `heartbeat-discipline.md`. No regression in `validate_instructions.py`. Smoke: agent in next wake doesn't reference "scheduled heartbeat" or "heartbeat polling" in comments.

**Token impact:** +50–80 t for the reconciliation note × 19 roles = ~1,000–1,500 t fleet cost increase. Acceptable trade-off for clarity.

---

### Phase 4.6 — Conditional: user-level override of `paperclip` skill (NEW, gated on smoke)

**Goal:** Replace upstream `paperclip` skill's "You run in heartbeats" framing with Gimle-specific event-only framing.

**Pre-requisite — smoke test (must pass before Phase 4.6 proper):**

```bash
# 1. Copy upstream paperclip skill to user-level
mkdir -p ~/.claude/skills/paperclip
cp /Users/anton/.npm/_npx/.../@paperclipai/server/skills/paperclip/SKILL.md \
   ~/.claude/skills/paperclip/SKILL.md

# 2. Edit user-level: add unique marker
echo "## Custom marker — user-level override active" >> ~/.claude/skills/paperclip/SKILL.md

# 3. New Claude Code session, load paperclip skill via Skill tool
# 4. Verify: marker appears in skill body
```

**If user-level overrides plugin-installed:** proceed with Phase 4.6 proper.
**If plugin always wins:** abandon Phase 4.6, rely on Phase 4.5 only.

**Tasks (proper, gated):**

- [ ] **Mirror upstream skill** to `paperclips/skills/paperclip/SKILL.md` in repo.
- [ ] **Edit content**: replace "heartbeat" → "wake" terminology consistently. Preserve all functional rules (auth, checkout, comment, handoff, etc.). Add note at top:
  ```markdown
  > **Gimle-customized version of paperclip skill** — replaces upstream
  > "heartbeat" terminology with explicit "event-driven wake" framing for
  > clarity in our deployment (no scheduled heartbeat enabled).
  ```
- [ ] **Symlink to user-level** on operator Mac: `~/.claude/skills/paperclip/ → /Users/ant013/Android/Gimle-Palace/paperclips/skills/paperclip/` (so updates ride through git).
- [ ] **Mirror on iMac**: rsync paperclips/skills/paperclip/ to iMac `~/.claude/skills/paperclip/`.
- [ ] **Smoke**: agent wake on iMac, verify session jsonl shows skill body with our wake-terminology, not upstream "heartbeats" — though this requires diffing skill body in session vs upstream.

**Risk:** upstream paperclip 2026.428+ may add features to skill that we miss. Mitigation: track upstream changes via `git log` on `paperclipai/paperclip` repo paths matching `server/skills/paperclip/**`. Cherry-pick / merge updates manually. Estimated upstream change frequency: 1–2 times per quarter based on v2026.318 → v2026.428 cadence.

**Acceptance:** new agent sessions load Gimle-customized paperclip skill instead of upstream version. Heartbeat-terminology incidents (like 2026-05-05) stop occurring in next 30 days.

---

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

## Token reduction estimate (cumulative, with all phases)

| Phase | Δ per wake | Δ per 30 days × 464 wakes |
|---|---:|---:|
| 1 (operator session disable) | ~−4,500 t | n/a (operator session) |
| 2 (iMac runtime disable: meta+infra+core-dev+frontend-design) | −2,748 t | −1.27M t |
| 3 (Path-1 — rm unused .md in qa-sec/research/lang/pr-review-toolkit caches) | −3,884 t | **−1.80M t** |
| 4 (role .md cleanup — driven by Phase 0.5 audit findings) | TBD (~−200 to −600 t/role avg) | −185K t conservative |
| 4.5 (rename + clarify heartbeat-discipline.md → wake-discipline.md) | **+50–80 t per role** (reconciliation note) | +1,400 t (cost) |
| 4.6 (gated — user-level paperclip skill override) | ~−500–1,000 t (replaced text shorter) | −230K t |
| 5 (skill cleanup via desiredSkills API + non-company plugin disable) | −500 t | −230K t |
| **Total (Phases 1+2+3+4+5+4.5, baseline)** | **~7,082 t per wake** | **~3.29M tokens / month** |
| **Total (+ Phase 4.6 if smoke passes)** | **~8,082 t per wake** | **~3.75M tokens / month** |

At Sonnet 4.6 input rate $0.003/1K: ≈ **$9.9–11.3/mo savings** (paperclip runtime).
At Opus 4.7 input rate $0.015/1K: ≈ **$49–56/mo savings** (paperclip runtime).

(Plus operator session — comparable savings, separate budget.)

**Note:** Phase 5 estimate revised down (from -1,000 to -500 t) because per-agent skill API only affects company-imported skills. Built-in `paperclip` skill remains.

(Plus operator session — comparable savings, separate budget.)

---

## Cross-references

- Audit script: `/tmp/agent-tool-audit.py` (read paperclip session jsonl, count subagent/skill calls per role).
- Bundle-size baseline: `paperclips/bundle-size-baseline.json`.
- Coverage matrix: `paperclips/instruction-coverage.matrix.yaml` (machine-readable rule-coverage spec).
- Related slices: GIM-189 (bundle-slim — split phase-handoff + compliance-enforcement); separate slice planned for codex:cx-code-reviewer coverage gap fix.

---

## Open questions for operator

1. ~~**iOS prep:** keep `voltagent-lang:swift-expert` + `voltagent-lang:kotlin-specialist`?~~ ✅ **RESOLVED 2026-05-05**: keep both, only for BlockchainEngineer per Q1 answer. Default approach: keep in plugin cache (140t/wake cost for non-Blockchain roles is acceptable). Strict per-workspace approach (workspace-level disable for non-Blockchain): noted as optional follow-up.
2. ~~**Phase 3 strategy:** option B vs C?~~ ✅ **RESOLVED 2026-05-05**: Path-1 (rm unused .md files in plugin cache, preserve subagent name prefix). No role file changes needed. Risk: `/plugins update` restores files; mitigation: documented curate script.
3. **Skill keep** (open): drop default = "if 0 calls in 30 days → drop". Operator can override per-skill (e.g. swiftui-pro / kmp / swift-* for future iOS work). **Pending operator review** before Phase 5 execution.
4. **Phase order** (open): ship Phase 1 first as smoke (faster operator-session verification), then Phase 2+. Phase 0.5 (per-role audit) runs in parallel — read-only. **Default: Phase 0 → Phase 1 → Phase 0.5 (parallel) → Phase 2 → Phase 3 → Phase 4 → Phase 5 → Phase 6.**

## Paperclip API verification (corrected from earlier draft)

**Verified in paperclip 2026.428 docs + v2026.416 release notes:**

| Operator's earlier overview (mis-attributed) | Reality in v2026.416/.428 |
|---|---|
| "Plugin Overrides (v2026.416)" — implied skill/subagent override | ❌ v2026.416 plugin overrides are about **adapters** (`claude_local`, `codex_local`, etc.) — third-party adapters can override built-in ones via `overriddenBuiltin` flag. NOT about skill/subagent overrides. |
| "Per-Agent Exclusions: restrict bundled skills... reducing heartbeat context for individual agents" | ❌ NOT documented in v2026.416 release notes or paperclip 2026.428 references. Likely AI-generated marketing text conflating multiple unrelated features. |
| "Runtime Skill Injection" | 🟡 Closest real feature: v2026.416 "Skill auto-enable — Mentioned skills are automatically enabled for heartbeat runs". Skills enable on @mention, not arbitrary runtime injection. |
| "Container Overrides `PAPERCLIP_HOST_FROM_CONTAINER`" | ✅ Real — env var for docker container host alias. Unrelated to skill control. |

**Real skill control mechanisms in 2026.428:**

- `POST /api/agents/:agentId/skills/sync` with `desiredSkills: [...]` — per-agent skill assignment for **company-imported** skills.
- `runtimeConfig.heartbeat.enabled: false` — disables scheduled wake (already used).
- Built-in `paperclip` skill — auto-loaded by adapter, **cannot be excluded** per agent. Modifications: direct edit (fragile) or user-level override (Phase 4.6, gated on smoke).

## Scope clarification — what was deeply audited vs not

- ✅ **Deep audit done**: `claude:code-reviewer` (inline duplication, fragment coverage gap, codex parity gap with 12 missing fragments). See findings inline in Phase 4 task list for CR.
- ✅ **Subagent invocation data**: ALL 20 roles (464 sessions / 30 days) — captured in `/tmp/agent-tool-audit.py` output above.
- ✅ **Fragment include matrix**: ALL 20 roles — captured in `/tmp/bundle-audit.json`.
- ❌ **Per-role inline duplication audit**: Only CR done. **Phase 0.5 task** (newly added) handles the remaining 19 roles.
- ❌ **Per-role aspirational subagent cleanup**: Only CR pattern identified. **Phase 0.5 task** maps cleanup targets per role.
- ❌ **Cross-team gap audit**: Only claude:CR vs codex:cx-CR done. **Phase 0.5 task** extends to all 8 paired roles.

---

_End of plan_
