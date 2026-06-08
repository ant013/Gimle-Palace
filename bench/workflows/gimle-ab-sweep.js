export const meta = {
  name: 'gimle-ab-sweep',
  description: 'A/B benchmark FULL SWEEP: T2-T5 + T7-T10, N=2 each, parallel pairs.',
  whenToUse: 'After pilot (T1+T6) validated harness.',
  phases: [{ title: 'Sweep', detail: 'T2-T5 + T7-T10, N=2 each' }],
}

const TASKS = [
  { id: 'T2', file: 'T2.prompt', desc: 'simple-grep (anti-palace)' },
  { id: 'T3', file: 'T3.prompt', desc: 'send-flow trace' },
  { id: 'T4', file: 'T4.prompt', desc: 'adapter-injection' },
  { id: 'T5', file: 'T5.prompt', desc: 'multichain-swap architecture' },
  { id: 'T7', file: 'T7.prompt', desc: 'add EUR currency' },
  { id: 'T8', file: 'T8.prompt', desc: 'fix silent Bitcoin UTXO' },
  { id: 'T9', file: 'T9.prompt', desc: 'extract MoneroAddressFormatter' },
  { id: 'T10', file: 'T10.prompt', desc: 'stale-index adversarial', stages_file: true },
]

const REPO_ROOT = '/Users/ant013/Android/Gimle-Palace'
const STAGED_T10 = `${REPO_ROOT}/bench/staged/RecentSwaps.swift`

const TASK_OUTPUT_SCHEMA = {
  type: 'object',
  required: ['artifact', 'checklist_facts'],
  additionalProperties: false,
  properties: {
    artifact: { type: 'string' },
    checklist_facts: {
      type: 'array',
      items: {
        type: 'object',
        required: ['item', 'covered'],
        properties: {
          item: { type: 'string' },
          covered: { type: 'boolean' },
        },
      },
    },
    usage_summary: {
      type: 'object',
      properties: {
        palace_calls: { type: 'integer' },
        bash_calls: { type: 'integer' },
        read_calls: { type: 'integer' },
        grep_calls: { type: 'integer' },
        skills_invoked: { type: 'array', items: { type: 'string' } },
      },
    },
    arm_compliance: {
      type: 'object',
      properties: {
        arm: { type: 'string' },
        followed_restrictions: { type: 'boolean' },
        violations: { type: 'array', items: { type: 'string' } },
      },
    },
  },
}

function gimlePrompt(task) {
  return `You are running as the **GIMLE arm** of an A/B benchmark.

Your toolset INCLUDES palace-mcp tools (mcp__palace-memory__palace_code_*,
palace_memory_*, palace_health_*). Use them. Also invoke
Skill('analog-driven-development') for the 8-phase workflow.
Skip operator-approval gate (benchmark = autonomous).

Working directory: /Users/ant013/Ios/bench-gimle. Operate ONLY there.
NEVER commit, NEVER push.

Task prompt file: ${REPO_ROOT}/bench/tasks/${task.file}

Return structured output. Be efficient.`
}

function vanillaPrompt(task) {
  return `You are running as the **VANILLA arm** of an A/B benchmark.

STRICT: DO NOT call any palace.* / mcp__palace-memory__ tool — IGNORE them.
DO NOT invoke Skill('analog-driven-development').
DO invoke: superpowers/brainstorming, writing-plans, executing-plans,
test-driven-development, systematic-debugging (skip approval gates).
For Swift code tasks also: swiftui-pro, swift-concurrency-pro,
swift-testing-pro.
Use only: Read, Edit, Write, Grep, Glob, Bash, WebFetch, WebSearch.

Working directory: /Users/ant013/Ios/bench-vanilla. Operate ONLY there.
NEVER commit, NEVER push.

Task prompt file: ${REPO_ROOT}/bench/tasks/${task.file}

Return structured output. Be efficient.`
}

async function cleanWorktrees() {
  return agent(
    `Bash: for wt in /Users/ant013/Ios/bench-gimle /Users/ant013/Ios/bench-vanilla; do cd "$wt" && git reset --hard 94258fd49 2>&1 | tail -1 && git clean -fdx -e .build -e SourcePackages 2>&1 | tail -1; done; echo done`,
    { label: 'pre-clean', phase: 'Sweep', agentType: 'general-purpose' }
  )
}

async function stageT10() {
  return agent(
    `Bash: for wt in /Users/ant013/Ios/bench-gimle /Users/ant013/Ios/bench-vanilla; do mkdir -p "$wt/Source" && cp ${STAGED_T10} "$wt/Source/RecentSwaps.swift" && stat -f%z "$wt/Source/RecentSwaps.swift"; done`,
    { label: 'stage-T10', phase: 'Sweep', agentType: 'general-purpose' }
  )
}

async function runPair(task, runIdx) {
  return parallel([
    () =>
      agent(gimlePrompt(task), {
        agentType: 'general-purpose',
        schema: TASK_OUTPUT_SCHEMA,
        label: `${task.id}-gimle-r${runIdx}`,
        phase: 'Sweep',
      }),
    () =>
      agent(vanillaPrompt(task), {
        agentType: 'general-purpose',
        schema: TASK_OUTPUT_SCHEMA,
        label: `${task.id}-vanilla-r${runIdx}`,
        phase: 'Sweep',
      }),
  ])
}

phase('Sweep')
log('FULL SWEEP: T2-T5 + T7-T10, N=2 each, 16 pairs.')

const sweep = []
for (const task of TASKS) {
  await cleanWorktrees()
  if (task.stages_file) {
    await stageT10()
  }
  for (let n = 1; n <= 2; n++) {
    log(`${task.id} (${task.desc}) run ${n}/2...`)
    const pair = await runPair(task, n)
    sweep.push({ task: task.id, run: n, gimle: pair[0], vanilla: pair[1] })
  }
}

log(`Sweep complete: ${sweep.length} pairs.`)
return { sweep }
