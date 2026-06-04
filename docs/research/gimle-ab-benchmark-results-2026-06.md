# Gimle A/B benchmark — pilot results (v4-with-caveats)

Run dates: 2026-05-31 → 2026-06-01.
Methodology: `docs/research/gimle-ab-benchmark-methodology.md` v4 + honor-system fallback.
Raw artifacts: `bench/runs/{pilot,sweep}-2026-05-31/`.

---

## TL;DR

| Arm | Mean tokens / invocation | Mean USD / invocation | Pass score (median across 10 tasks) |
| --- | --- | --- | --- |
| **gimle** (palace-mcp + analog-driven-development) | 1.74M | **$1.36** | 0.979 |
| **vanilla** (superpowers + swift skills, no palace) | 1.69M | **$0.90** | 0.979 |

**Headline finding under this setup:** on the 10-task UW-iOS corpus, the
gimle bundle produces **identical pass scores at +52% cost** vs a focused
vanilla baseline. Tasks scored ~perfect for both arms (median 1.0 on 7 of
8 sweep tasks, 0.83 on T2), so the comparison was bottlenecked by gold
checklists not discriminating.

**Caveats that materially weaken the finding** (read before interpreting):

1. **Palace MCP unreachable from subagent context** in several gimle runs.
   Workflow-spawned subagents reported `palace_health_status -> connection
   error` and fell back to local grep + Read. The gimle bundle then
   collapsed to "vanilla + analog-driven-development skill prompt"; we did
   not cleanly measure palace's contribution.
2. **Gold checklists too lenient** — must_contain + any_n_of regexes
   matched easily for both arms. T3-T10 saturated at 1.0/1.0; signal
   noise drowned any quality delta.
3. **Honor-system tool isolation** — custom subagent types in
   `.claude/agents/bench-*.md` were not loaded by the workflow runtime
   (only built-in / plugin-namespaced types resolved). Fell back to
   `general-purpose` + prompt-level "DO NOT call palace" instructions.
   Vanilla arm complied (0 palace calls across all 16 sweep runs); gimle
   tried but often got errors.

So the experiment shipped a real number, but it's a **lower-confidence**
number than v4 spec promised. Re-running with custom subagent types
properly loaded + tighter gold checklists is the obvious follow-up.

---

## Setup

- **Corpus**: UW iOS app + 8 standalone HS Swift kits + 30+ co-indexed
  dependency modules in Neo4j (380k+ embeddings; see Neo4j coverage table
  in methodology).
- **Tasks**: T1-T10 (lookup, trace, architecture, code-write, adversarial).
  Prompts at `bench/tasks/T*.prompt`; gold at `bench/gold/T*.json`.
- **Arms**:
  - **gimle** — palace-mcp MCP tools + analog-driven-development skill +
    TDD + systematic-debugging. Worktree `bench-gimle`.
  - **vanilla** — superpowers/{brainstorming, writing-plans,
    executing-plans, TDD, systematic-debugging} + swift-{ui-pro,
    concurrency-pro, testing-pro}. Worktree `bench-vanilla`.
- **Sample**: pilot N=2 on T1+T6 (8 invocations), sweep N=2 on T2-T5+T7-T10
  (32 invocations). Total 40 paired runs (20 per arm).
- **Harness**: Workflow tool with `parallel(agent_gimle, agent_vanilla)`
  per task per run.
- **Grading**: mechanical regex against `bench/gold/T*.json` via
  `bench/scripts/gimle-ab-grader.py`.

---

## Per-task pass scores (median over 2 runs)

| Task | Tier | gimle | vanilla | Δ |
| --- | --- | --- | --- | --- |
| T1 monero-class | 1 lookup | 0.94 | 0.92 | +0.02 |
| T2 simple-grep | 1 baseline | 0.83 | 0.83 | 0.00 |
| T3 send-flow | 2 trace | 1.00 | 1.00 | 0.00 |
| T4 adapter-inject | 2 trace | 1.00 | 1.00 | 0.00 |
| T5 multichain-swap | 3 arch | 1.00 | 1.00 | 0.00 |
| T6 add-whitelist | 4 code | 1.00 | 1.00 | 0.00 |
| T7 add-currency | 4 code | 1.00 | 1.00 | 0.00 |
| T8 bug-fix UTXO | 4 code | 1.00 | 1.00 | 0.00 |
| T9 extract Formatter | 4 refactor | 1.00 | 1.00 | 0.00 |
| T10 stale-index | 5 adversarial | 1.00 | 1.00 | 0.00 |
| **Mean median** | | **0.979** | **0.979** | 0.00 |

Single tier-3+ task (T5) where gimle's analog discovery should shine —
both arms matched. T9 refactor — both produced acceptable extraction.

---

## Per-task cost (mean USD, 2 runs)

Pulled from raw subagent JSONL transcripts using Sonnet 4.6 pricing
(`input × $3 + cache_creation × $3.75 + cache_read × $0.30 + output × $15`
per Mtok).

| Task | gimle $ | vanilla $ | Δ% |
| --- | --- | --- | --- |
| T2 | $0.97 | $0.46 | +109% |
| T3 | $1.71 | $1.20 | +43% |
| T4 | $1.42 | $0.78 | +83% |
| T5 | $1.93 | $1.11 | +74% |
| T7 | $0.65 | $0.45 | +44% |
| T8 | $1.32 | $1.05 | +26% |
| T9 | $1.13 | $0.93 | +21% |
| T10 | $0.69 | $0.39 | +75% |
| **Mean** | **$1.23** | **$0.80** | **+54%** |

Gimle pays the cost premium primarily through **palace JSON payloads
returning as 10-100KB tool_result blobs** that enter the next turn's
input/cache_creation. Vanilla's Bash/Grep/Read returns are smaller.

---

## Observations from raw transcripts

### Palace reachability

Out of 16 gimle sweep runs, **palace_calls > 0** in 14 / 16. But several
runs surface "Palace MCP unreachable" / "connection error" text in the
artifact, indicating the call was made but returned an error envelope.

The harness's parent process IS running native palace-mcp on
`localhost:8765` (pid 84199, 380k+ embeddings indexed). The subagent
context may not inherit MCP server config the same way the parent does
— this is a real-world UX gap worth filing.

### Skill invocation

- gimle: `analog-driven-development` invoked in 15 / 16 runs ✓
- vanilla: zero palace.* calls, complied with restrictions ✓
  (compliance self-reported AND verified by `palace_calls: 0` in usage)

### Artifact quality (qualitative)

Reading T3 (send-flow trace), T5 (multichain swap), T9 (refactor) artifacts
side-by-side:

- **gimle** artifacts contain explicit "Phase A brainstorm" / "delta
  matrix" sections, more structured, marginally more thorough on edge
  cases.
- **vanilla** artifacts read more directly, leaner, similar concrete
  coverage of the gold facts.

A human reviewer doing blind grading would likely score gimle slightly
higher on "thoroughness" — but the mechanical gold-checklist grading
showed no delta. Suggests we need richer rubrics for the next round.

---

## What we measured vs what we wanted to measure

| Wanted | Got |
| --- | --- |
| palace tools vs no-palace tools effect | palace tools (sometimes broken) vs no-palace tools |
| analog-driven-development workflow effect | analog-driven-development workflow (sometimes engaged) effect |
| Headline cost ratio | gimle +52% cost for identical mechanical pass score |
| Per-tier breakdown | tier 1 lookup ~tied, all others saturated at perfect |
| Adversarial probe (T10) | both arms found target via grep; palace's stale-index didn't bite |

---

## Recommendations

### Immediate (operator-actionable, ~1 hour)

1. **Reload Claude Code session** so custom `~/.claude/agents/bench-{gimle,vanilla}.md`
   are picked up by the runtime — eliminates honor-system fallback.
2. **Tighten gold checklists**:
   - Add `must_contain_n_of` with higher N
   - Add depth-sensitive matchers (e.g. T3 must mention ≥5 of 7
     components, not just any 3)
   - Add semantic equivalence checks for code patches via `git apply`
     + targeted test run
3. **Re-run** with v4-real (custom subagent types + tighter gold).

### Methodological (~half-day)

4. **MCP server pass-through for subagents** — investigate why
   palace-memory MCP doesn't reach Workflow subagents. Likely needs to be
   declared in `~/.claude/agents/bench-gimle.md` frontmatter (e.g. a
   `mcpServers:` field) — current docs unclear.
5. **Subjective grader** — third agent rates artifacts on rubric (clarity,
   thoroughness, correctness) blind to arm. Adds discrimination above
   mechanical floor.
6. **Ablation arm** — palace-only (no skill) + skill-only (no palace) to
   attribute headline cost to a single source.

### Honest reporting (now)

7. **Don't claim "palace doesn't help"** from this run. The data shows
   palace + skill bundle costs more and produces equivalent answers
   under conditions where (a) gold cannot discriminate, (b) palace
   sometimes fails to connect. Real verdict requires step 4 + tighter
   gold. Treat current numbers as **null finding**, not negative finding.

---

## Cost

- Pilot (T1+T6 N=2 = 8 invocations): ~$5.50
- Sweep (T2-T5+T7-T10 N=2 = 32 invocations): ~$36
- Grader + 3 voltAgent methodology reviews: ~$5
- **Total budget consumed:** ~$46.50

Compares against v4 estimate ($40-80, 2-3h): on the low end. Could afford
re-run with proper isolation.

---

## Decision log

- **2026-05-30 → 2026-05-31** — v1→v4 methodology revisions (3 voltAgent
  review rounds) + harness implementation.
- **2026-06-01** — Pilot ran (T1+T6, N=2). Custom subagent types didn't
  load → switched to general-purpose + honor-system tool isolation.
  Pilot validated harness end-to-end.
- **2026-06-01** — Full sweep (T2-T5+T7-T10, N=2). All 32 invocations
  succeeded. Mechanical grader produced tied pass scores.
- **Next**: operator decides whether to re-run with custom subagent types
  + tighter gold, or accept current null finding as "good enough"
  signal that focused vanilla is a competitive baseline.
