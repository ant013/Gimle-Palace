export const meta = {
  name: 'gimle-ab-sweep-v5',
  description: 'A/B benchmark v5 — fresh ingest + real subagent types (bench-gimle/vanilla). 10 tasks × N=2 = 20 pairs.',
  phases: [{ title: 'Sweep' }],
}

const TASKS = [
  { id: 'T1',  file: 'T1.prompt',  desc: 'MoneroAdapter public API' },
  { id: 'T2',  file: 'T2.prompt',  desc: 'Foundation-not-UIKit grep' },
  { id: 'T3',  file: 'T3.prompt',  desc: 'send-flow trace ETH' },
  { id: 'T4',  file: 'T4.prompt',  desc: 'MoneroAdapter DI' },
  { id: 'T5',  file: 'T5.prompt',  desc: 'multichain-swap architecture' },
  { id: 'T6',  file: 'T6.prompt',  desc: 'add USDC ERC20 to whitelist' },
  { id: 'T7',  file: 'T7.prompt',  desc: 'add EUR currency' },
  { id: 'T8',  file: 'T8.prompt',  desc: 'fix silent Bitcoin UTXO failure' },
  { id: 'T9',  file: 'T9.prompt',  desc: 'extract MoneroAddressFormatter' },
  { id: 'T10', file: 'T10.prompt', desc: 'recordSwap thorough sweep', stages_file: true },
]

const REPO_ROOT = '/Users/ant013/Android/Gimle-Palace'
const STAGED_T10 = `${REPO_ROOT}/bench/staged/RecentSwaps.swift`
const N = 2

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
  },
}

function gimlePromptFor(task) {
  return `You are running as the GIMLE arm of an A/B benchmark.

Working directory: /Users/ant013/Ios/bench-gimle (do not leave it).
Task prompt file (Read it first): ${REPO_ROOT}/bench/tasks/${task.file}

Use palace-mcp tools aggressively where they help. Invoke
Skill('analog-driven-development') for code-change tasks. Skip
operator-approval gate (benchmark mode).

NEVER commit, NEVER push. Patches as plain text in artifact.

Return structured output per schema.`
}

function vanillaPromptFor(task) {
  return `You are running as the VANILLA arm of an A/B benchmark.

Working directory: /Users/ant013/Ios/bench-vanilla (do not leave it).
Task prompt file (Read it first): ${REPO_ROOT}/bench/tasks/${task.file}

You have NO palace-mcp tools (enforced by subagent type). Use Read, Edit,
Write, Grep, Glob, Bash. Invoke superpowers/brainstorming +
writing-plans + executing-plans + test-driven-development +
systematic-debugging. For Swift code (T6/T7/T8/T9) also invoke
swiftui-pro, swift-concurrency-pro, swift-testing-pro.

NEVER commit, NEVER push. Patches as plain text in artifact.

Return structured output per schema.`
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
      agent(gimlePromptFor(task), {
        agentType: 'bench-gimle',
        schema: TASK_OUTPUT_SCHEMA,
        label: `${task.id}-gimle-r${runIdx}`,
        phase: 'Sweep',
      }),
    () =>
      agent(vanillaPromptFor(task), {
        agentType: 'bench-vanilla',
        schema: TASK_OUTPUT_SCHEMA,
        label: `${task.id}-vanilla-r${runIdx}`,
        phase: 'Sweep',
      }),
  ])
}

phase('Sweep')
log(`v5 sweep: ${TASKS.length} tasks × N=${N} runs × 2 arms = ${TASKS.length * N * 2} subagent invocations.`)
log('Using REAL custom subagent types (bench-gimle / bench-vanilla) for runtime tool-isolation.')

const sweep = []
for (const task of TASKS) {
  await cleanWorktrees()
  if (task.stages_file) {
    await stageT10()
  }
  for (let n = 1; n <= N; n++) {
    log(`${task.id} (${task.desc}) — run ${n}/${N}`)
    const pair = await runPair(task, n)
    sweep.push({ task: task.id, run: n, gimle: pair[0], vanilla: pair[1] })
  }
}

log(`Sweep complete: ${sweep.length} pairs across ${TASKS.length} tasks.`)
return { sweep }
