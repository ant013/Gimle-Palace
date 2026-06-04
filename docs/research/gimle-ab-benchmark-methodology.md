# Gimle A/B benchmark — methodology (v4, pilot-ready)

Tracking: paperclip GIM-1077.

Goal: empirically measure whether **gimle stack** (palace-mcp tools +
`analog-driven-development` skill) accelerates an LLM agent solving real
UW-iOS-app engineering tasks vs a **focused vanilla baseline** (small
curated superpowers + swift-domain skill set, NO palace tools).

> **v4 changes** address blockers from second-round voltAgent review of v3:
> custom subagent types with explicit `tools:` whitelists (real tool
> isolation), two git worktrees per code task, focused 5-skill control
> stack (vs v3's 13-skill kitchen sink), Workflow-tool harness (model-driven
> parallel) with token-attribution pilot, T10 staging spelled out,
> hypothesis honest about bundle vs ablation.

---

## Hypothesis (honest about scope)

We measure the **gimle bundle** (tools + workflow skill, jointly) vs a
**focused vanilla bundle** (general planning + TDD + Swift domain), not
ablated components. If gimle bundle wins, future ablation can split credit
between palace-mcp tools and analog-driven-development workflow skill.

Predicted: gimle bundle wins on architectural / cross-module / analog-style
tasks; loses on trivial lookup; uncertain on small code patches.

---

## Coverage scope (operator constraint, unchanged)

uw-ios-app + 8 standalone HS kits already in Neo4j; 30+ co-indexed dep
modules within uw-ios-app. No new ingest required for benchmark.

---

## Tool isolation — REAL, via custom subagent types

Two agent definitions at repo `.claude/agents/`:

### `.claude/agents/bench-gimle.md` (treatment)

```yaml
---
name: bench-gimle
description: Gimle-equipped subagent for A/B benchmark. Uses palace-mcp tools + analog-driven-development skill. Operates in /Users/ant013/Ios/bench-gimle worktree.
tools:
  - Read
  - Edit
  - Write
  - Grep
  - Glob
  - Bash
  - Skill
  - mcp__palace-memory__palace_code_semantic_search
  - mcp__palace-memory__palace_code_trace_call_path
  - mcp__palace-memory__palace_code_find_references
  - mcp__palace-memory__palace_code_find_idiom
  - mcp__palace-memory__palace_code_find_owners
  - mcp__palace-memory__palace_code_find_dead_code
  - mcp__palace-memory__palace_code_find_dead_symbols
  - mcp__palace-memory__palace_code_get_architecture
  - mcp__palace-memory__palace_code_list_functions
  - mcp__palace-memory__palace_code_get_code_snippet
  - mcp__palace-memory__palace_code_search_code
  - mcp__palace-memory__palace_code_find_cross_module_contracts
  - mcp__palace-memory__palace_code_find_public_api
  - mcp__palace-memory__palace_memory_lookup
  - mcp__palace-memory__palace_memory_decide
  - mcp__palace-memory__palace_health_status
---

[full body: see file]
```

### `.claude/agents/bench-vanilla.md` (control)

```yaml
---
name: bench-vanilla
description: Vanilla-equipped subagent for A/B benchmark. Uses focused superpowers + swift skills. Operates in /Users/ant013/Ios/bench-vanilla worktree. NO palace-mcp tools.
tools:
  - Read
  - Edit
  - Write
  - Grep
  - Glob
  - Bash
  - Skill
  - WebFetch
  - WebSearch
---

[full body: see file]
```

**No palace.* tools in vanilla's `tools:` list = subagent literally cannot
call them.** Replaces v3's honor-system "DO NOT call palace.*" instruction.

---

## Skill stack — focused on both sides (v4 fix)

### Treatment: gimle stack (3 skills)
- `analog-driven-development` (the 8-phase workflow — file at
  `/Users/ant013/Data/AI/gimle-skills/analog-driven-development/SKILL.md`,
  symlinked to `~/.claude/skills/analog-driven-development/`)
- `superpowers/test-driven-development` (TDD is universal)
- `superpowers/systematic-debugging` (debug is universal)

### Control: focused vanilla stack (5 skills)
- `superpowers/brainstorming`
- `superpowers/writing-plans`
- `superpowers/executing-plans`
- `superpowers/test-driven-development`
- `superpowers/systematic-debugging`
- (swift-domain skills only loaded on swift code-writing tasks T6-T9:
  add `swiftui-pro` + `swift-concurrency-pro`)

Symmetric: both arms get TDD + systematic-debugging baseline. Treatment adds
1 skill (analog-driven-development). Control adds 3 (brainstorm + plans +
execute). Volume balanced, not skewed.

---

## Two-worktree setup (v4 fix — no parallel-write race)

```bash
# One-time setup
git -C /Users/ant013/Ios/HorizontalSystems/unstoppable-wallet-ios \
  worktree add /Users/ant013/Ios/bench-gimle   bench/sandbox-ab-gimle
git -C /Users/ant013/Ios/HorizontalSystems/unstoppable-wallet-ios \
  worktree add /Users/ant013/Ios/bench-vanilla bench/sandbox-ab-vanilla
```

Treatment subagent operates in `/Users/ant013/Ios/bench-gimle`.
Control subagent operates in `/Users/ant013/Ios/bench-vanilla`.

Per-task pre-cleanup (harness):
```bash
for wt in bench-gimle bench-vanilla; do
  git -C /Users/ant013/Ios/$wt reset --hard origin/master
  git -C /Users/ant013/Ios/$wt clean -fdx
done
```

Both worktrees never mutate the operator's primary checkout.

---

## Neutral parent context (v4 fix)

Benchmark **runs from `/tmp/gimle-bench-run-YYYYMMDD`** (NOT from
`/Users/ant013/Android/Gimle-Palace`), which has:
- No CLAUDE.md mentioning palace.*
- No MEMORY.md
- No `.claude/` settings inherited from Gimle-Palace
- Just the harness script + a `BENCH-INSTRUCTIONS.md` describing the run
  protocol neutrally

Eliminates parent-context priming of subagents. Subagents launched via
Workflow tool from this neutral parent.

---

## Harness — Workflow tool (v4 fix — model-driven parallel)

The `Workflow` tool natively supports `parallel(agent(...), agent(...))`
inside a script. Runs deterministically, captures `subagent_tokens` /
`duration_ms` / `tool_uses` per call, persists journal for resume.

Skeleton (`bench/workflows/gimle-ab-sweep.js`):

```javascript
export const meta = {
  name: 'gimle-ab-sweep',
  description: 'A/B benchmark: gimle vs vanilla on 10 UW iOS tasks, N=3',
  phases: [
    { title: 'Pilot', detail: 'T1+T6 N=2 token-attribution sanity' },
    { title: 'Sweep', detail: '10 tasks × 2 arms × 3 runs = 60 invocations' },
    { title: 'Grade', detail: 'mechanical regex against gold/*.json' },
  ],
}

const TASKS = [
  { id: 'T1', prompt: read('tasks/T1.prompt'), gold: 'gold/T1.json' },
  { id: 'T2', prompt: read('tasks/T2.prompt'), gold: 'gold/T2.json' },
  // ... T3..T10
]

const TASK_SCHEMA = { /* JSON schema for ARTIFACT + CHECKLIST + USAGE */ }

phase('Pilot')
const pilot = await pipeline(
  [TASKS[0], TASKS[5]], // T1 + T6
  task => parallel([
    () => agent(`${task.prompt}\n\nWORKTREE: /Users/ant013/Ios/bench-gimle`,
                 { agentType: 'bench-gimle', schema: TASK_SCHEMA, label: `${task.id}-gimle-pilot1` }),
    () => agent(`${task.prompt}\n\nWORKTREE: /Users/ant013/Ios/bench-vanilla`,
                 { agentType: 'bench-vanilla', schema: TASK_SCHEMA, label: `${task.id}-vanilla-pilot1` }),
  ])
)
// Operator inspects pilot results: are subagent_tokens credible?
// Are tool_uses counts what we expect? Are patches non-corrupted?

phase('Sweep')
const runs = await pipeline(
  TASKS,
  task => {
    const runs = []
    for (let n = 1; n <= 3; n++) {
      runs.push(parallel([
        () => agent(`${task.prompt}\n\nWORKTREE: /Users/ant013/Ios/bench-gimle`,
                     { agentType: 'bench-gimle', schema: TASK_SCHEMA, label: `${task.id}-gimle-r${n}` }),
        () => agent(`${task.prompt}\n\nWORKTREE: /Users/ant013/Ios/bench-vanilla`,
                     { agentType: 'bench-vanilla', schema: TASK_SCHEMA, label: `${task.id}-vanilla-r${n}` }),
      ]))
    }
    return Promise.all(runs)
  }
)

phase('Grade')
// gradeCSV(runs) — applies mechanical regex from gold/*.json per artifact
// outputs bench/results/<UTC>.csv
return { pilot, runs }
```

---

## Sample size & statistics (v4 fix — pilot first)

- **Pilot**: T1 + T6, N=2 each, parallel. Total 8 invocations. Validates:
  - Subagent token counters credible (reconcile against parent's billed)?
  - Tool whitelists work (vanilla subagent confirms palace.* unavailable)?
  - Worktrees properly isolated (concurrent patches don't collide)?
  - Skill invocation actually triggers workflow (logs show phase markers)?
- **If pilot passes**: full sweep N=3 per (task, arm) = 60 invocations
- **Statistical claims**: with N=3, report **median + IQR + Cliff's delta
  (effect size)**. Skip Wilcoxon — N too small for meaningful p-values.
- If any task shows huge variance in pilot → extend to N=5 just for that
  task.

---

## Cost estimate (v4 fix — realistic)

Per invocation realistic envelope:
- Gimle arm: 30-100k tokens (palace JSON blobs returned as tool_result enter
  next turn's input)
- Vanilla arm: 20-80k tokens (many Bash/Read calls, smaller results)
- Mixed in/out ~70/30 effective after cache
- Sonnet pricing: `$3 in + $15 out` per Mtok → ~$0.50-3.00 per invocation

**Pilot: 8 invocations × $1.50 avg ≈ $12.**
**Full sweep: 60 invocations × $1.50 avg ≈ $90. Worst case $200.**
Wall-clock: 2-3 hours (parallel pairs).

---

## Task corpus (v4 — unchanged from v3 except T10 staging)

T1 monero-class, T2 simple-grep (anti-palace), T3 send-flow, T4
adapter-injection, T5 multichain-swap, T6 add-whitelist, T7 add-currency,
T8 bug-fix, T9 small-refactor, T10 stale-index.

### T10 staging (explicit, v4 fix)

Before launching the T10 parallel agent calls, harness `Bash` step:

```bash
# Copy a pre-prepared file into both worktrees — palace index does NOT see it
for wt in bench-gimle bench-vanilla; do
  cp /Users/ant013/Android/Gimle-Palace/bench/staged/RecentSwaps.swift \
     /Users/ant013/Ios/$wt/Source/
done
# Verify both worktrees have it, palace index DOES NOT
stat /Users/ant013/Ios/bench-gimle/Source/RecentSwaps.swift  # exists
stat /Users/ant013/Ios/bench-vanilla/Source/RecentSwaps.swift  # exists
# (Palace would need explicit re-ingest to know about this file)
```

T10 then asks both arms: "Find every method named `recordSwap`." Treatment
arm uses palace (stale — misses new file) + may or may not cross-verify via
Grep. Control arm uses Grep + finds all instances naturally. **Headline T10
metric: did treatment-arm cross-verify or trust stale index?** Not pass/fail.

---

## Metrics captured per invocation (Workflow / Agent tool natively)

From `agent(...)` return + Agent tool's `<usage>`:
- `subagent_tokens` (total)
- `tool_uses` (count)
- `duration_ms`
- final structured output (ARTIFACT, CHECKLIST_FACTS, *_USAGE)

Per-task derived:
- `pass_score` = fraction of gold-checklist items matched (mechanical regex)
- `cost_usd` (estimate using Sonnet pricing assuming 70/30 in/out split)
- `efficiency` = pass_score / cost_usd
- `efficiency_per_minute` = pass_score / duration_ms × 60000

Headline:
- Per-task: median (gimle / vanilla) ratios for tokens, time, cost, pass_score
- Per-tier: weighted median
- Per-arm overall: pass-rate, total cost, total tokens
- T10 sanity: cross-verification rate of gimle arm

---

## Pilot acceptance criteria

Before greenlighting full sweep:
1. Pilot completes without harness crashes
2. Token attribution sane: `Σ subagent_tokens ≈ parent's billed (tool_result accumulation)` within ±20%
3. Vanilla subagent attempted zero palace.* calls (confirmed by transcript scan; if non-zero → bug in subagent definition, fix and re-pilot)
4. Treatment subagent successfully read and followed at least Phase A of `analog-driven-development` skill (presence of "brainstorm" / "delta matrix" in artifact)
5. Both worktrees end pilot in clean state (no merge conflicts, no cross-contamination)
6. Mechanical grader runs without errors on pilot outputs

Failed any → fix harness/spec, re-pilot. Don't burn $80 on flawed setup.

---

## Threats to validity (v4 final)

| Threat | Status |
| --- | --- |
| Cache pollution | non-issue (parallel subagents, fresh contexts) |
| Tool isolation | SOLVED via explicit `tools:` whitelist in agent definition |
| Worktree write race | SOLVED via two worktrees |
| Parent context leakage | SOLVED via neutral `/tmp/gimle-bench-run-*` parent |
| Skill volume asymmetry | SOLVED via focused 3+2 vs 5 stack |
| Honor-system | ELIMINATED (no instructions about avoidance — capability gap is structural) |
| Subagent token misattribution | TESTED in pilot before full sweep |
| Hypothesis bundle vs ablation | DOCUMENTED honestly: "measures bundle" |
| Model variance | N=3 → IQR; extend on high-variance tasks |
| Generalization (single repo) | DOCUMENTED limitation |
| T10 fairness | DOCUMENTED as qualitative probe, not scored A/B |

Residuals:
- N=3 statistical power weak — pilot study, not paper-grade
- One Sonnet version only — pin and re-run if model upgrades
- All tasks Swift / iOS-domain — gimle may shine differently on Android

---

## Run protocol

**Today (2026-05-31)**:
- Finalize v4 spec ✓
- Install `analog-driven-development` skill via symlink to `~/.claude/skills/`
- Write `.claude/agents/bench-{gimle,vanilla}.md` definitions
- Write 10 task prompts + 10 gold/*.json checklists
- Set up bench worktrees + neutral `/tmp/gimle-bench-run-*` parent
- Write Workflow script

**Tomorrow (2026-06-01)**:
- Run pilot (T1 + T6, N=2)
- Operator reviews pilot results
- If pilot passes → full sweep (N=3, ~3h, ~$90)
- Day-of analysis + first results draft

**Day after**:
- Final report at `docs/research/gimle-ab-benchmark-results-2026-06.md`
- Recommendations on whether to make gimle skill the default for UW work

---

## Open items requiring operator confirmation

1. **Worktrees in operator's UW iOS checkout** — `git worktree add` creates
   sibling dirs `/Users/ant013/Ios/bench-{gimle,vanilla}`. Operator OK?
2. **Symlink gimle skill into `~/.claude/skills/`** — required for Skill tool
   to find it. OK?
3. **Code-writing tasks T6-T9 produce patches but never commit/push.** OK?
4. **Pilot first** ($12, 30min) before authorizing $90 sweep. Default yes.

---

## Decision log

- **2026-05-30 v1** — initial draft.
- **2026-05-31 v2** — addressed 4 blockers from 3 voltAgent reviewers (T10
  tautology, N=1, cache contamination, no pass/fail).
- **2026-05-31 v3** — adopted parallel-subagent design (operator suggestion).
- **2026-05-31 v4** — addressed 3 blockers + 3 should-fix from second-round
  v3 review by 2 voltAgents (architect-reviewer, research-analyst): real
  tool isolation via custom subagent types, two worktrees, focused skill
  stacks, Workflow-tool harness with pilot gate, T10 staging spelled out,
  hypothesis honest about bundle measurement.
