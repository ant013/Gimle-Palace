# Codex Paperclip Team Builder

## Status

Proposed.

## Context

Gimle currently runs a working Paperclip agent team through `claude_local`.
Those agents can create additional agents through Paperclip's create-agent flow
and existing Claude-oriented instructions. That behavior must remain intact for
the Claude target.

The new goal is to create a duplicate Codex-capable team that can run through
Paperclip with `codex_local`, use Codex MCP/skills/agents, and still be able to
hire or configure new Paperclip agents through the same approval-safe lifecycle.

Live checks on 2026-05-02 confirmed:

- Paperclip exposes a loaded builtin `codex_local` adapter.
- `codex_local` supports instruction bundles, runtime skills, and local agent
  JWT.
- iMac has Codex CLI available in the Paperclip launchd PATH.
- iMac has Codex auth, MCP config, 138 Codex agents, and 58 Codex skills.
- The current Claude agents use `adapterType: "claude_local"` and
  `adapterConfig.model` for Claude model selection.

Evidence commands used for those claims:

```bash
curl -sS "$PAPERCLIP_API_URL/api/adapters" \
  -H "Authorization: Bearer $PAPERCLIP_API_KEY"

curl -sS "$PAPERCLIP_API_URL/llms/agent-configuration/codex_local.txt" \
  -H "Authorization: Bearer $PAPERCLIP_API_KEY"

curl -sS "$PAPERCLIP_API_URL/api/companies/$PAPERCLIP_COMPANY_ID/agent-configurations" \
  -H "Authorization: Bearer $PAPERCLIP_API_KEY"

ssh imac-ssh.ant013.work 'export PATH="$HOME/.local/bin:$HOME/.nvm/versions/node/v20.20.2/bin:/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin"; codex --version; find ~/.codex/agents -maxdepth 1 -name "*.toml" | wc -l; find ~/.codex/skills -name SKILL.md | wc -l'
```

The SSH command requires the same PATH that Paperclip launchd uses. A plain
non-login SSH shell may not find `codex`, while the Paperclip service PATH does.

## Assumptions

- `origin/develop` is the integration baseline for Gimle.
- Existing Claude agents and their managed `AGENTS.md` bundles are production
  state and must not be overwritten by Codex work.
- Codex agents should be added as new Paperclip agents, not by patching the
  current Claude agent records.
- New Paperclip agents are created through `agent-hires` and may require board
  approval before becoming runnable.
- Codex output may initially cover a pilot subset of roles before the full team
  is duplicated.

## Affected Areas

- `paperclips/build.sh`: currently builds only `paperclips/roles/*.md` into
  `paperclips/dist/*.md`.
- `paperclips/deploy-agents.sh`: currently uses one `DIST_DIR` and hard-coded
  Claude agent ids.
- `paperclips/dist/*.md`: current Claude production bundles.
- New Codex output path: `paperclips/dist/codex/*.md`.
- Shared fragments repository: target-specific runtime/create-agent fragments.
- Paperclip API: read-only discovery, `agent-hires`, approval follow-up, and
  `instructions-bundle/file` upload for new Codex agents only.

## Goals

- Keep the current Claude agent team behaviorally stable.
- Add a target-aware prompt/instruction build path for `claude` and `codex`.
- Let Codex agents create new Codex Paperclip agents through Paperclip API
  approval flow.
- Avoid leaking Claude-only runtime assumptions into Codex bundles.
- Make target choice explicit and repeatable from builder inputs rather than
  hand-editing each role.

## Non-Goals

- Do not convert existing Claude agents in place.
- Do not remove `superpowers:*` or Claude-only instructions from the Claude
  target.
- Do not bypass Paperclip approval flow by direct database writes.
- Do not auto-create production Codex agents before a pilot smoke run is
  reviewed.

## Target Model

Builder input should include:

- `target`: `claude` or `codex`
- `adapterType`: `claude_local` or `codex_local`
- `model`: provider model id
- `effort`: target-specific reasoning effort
- `projectRulesFile`: `CLAUDE.md` for Claude, `AGENTS.md` for Codex
- `skillsStrategy`: target-specific skill/subagent guidance
- `createAgentStrategy`: target-specific Paperclip hire instructions

Common role content should stay shared where it is platform-neutral. Runtime
behavior, CLI assumptions, skills/subagents, and self-hiring instructions should
be target-specific fragments.

## Claude Target

Claude remains the production baseline:

- `adapterType: "claude_local"`
- Existing Claude model ids remain valid.
- Existing Claude skills, subagents, and `superpowers:*` references stay in
  Claude output.
- Existing Paperclip create-agent instructions remain available to Claude
  agents.
- Generated Claude output must remain close to the current `paperclips/dist`
  files unless a separate reviewed change intentionally updates behavior.

## Codex Target

Codex output should use:

- `adapterType: "codex_local"`
- Default model: `gpt-5.5`
- Default reasoning: `modelReasoningEffort: "high"`
- `instructionsBundleMode: "managed"`
- `instructionsFilePath: "AGENTS.md"` in the hire request; Paperclip may expand
  it to an absolute managed bundle path after creation.
- Codex MCP context loading through `codebase-memory` and `serena`
- Codex skills from `~/.codex/skills`
- Codex agents from `~/.codex/agents`
- Paperclip runtime skills materialized by Paperclip into the effective
  Codex home.

Codex bundles must not depend on:

- `superpowers:*` skill names unless a real Codex equivalent exists.
- Claude Code-only subagent names.
- `claude` CLI cache/session assumptions.
- `CLAUDE.md` as the project rules file.

## Build And Deploy Layout

The first implementation slice should make the layout explicit:

- Claude output remains `paperclips/dist/*.md`.
- Codex output goes to `paperclips/dist/codex/*.md`.
- Claude deploy continues to read only `paperclips/dist/*.md`.
- Codex deploy must read only `paperclips/dist/codex/*.md`.
- Codex deploy must require a separate Codex agent id map.
- Codex deploy must fail closed if a target agent's live `adapterType` is not
  `codex_local`.
- Claude deploy must fail closed if a target agent's live `adapterType` is not
  `claude_local`.

`paperclips/deploy-agents.sh` currently contains hard-coded Claude agent ids.
The Codex path must not reuse that map. The safe implementation shape is either
a new `paperclips/deploy-codex-agents.sh` or a `--target codex` mode with a
separate id map and explicit adapter preflight.

## Codex Create-Agent Flow

Codex agents must be able to create new Paperclip agents by following an
explicit target-aware procedure:

1. Verify local identity and permissions:

```bash
curl -sS "$PAPERCLIP_API_URL/api/agents/me" \
  -H "Authorization: Bearer $PAPERCLIP_API_KEY"
```

The response must identify the current agent/company and confirm the needed
permission for creating agents. If the credential is a board/user credential
rather than an agent credential, the flow must use the documented board hire
approval path and must not assume agent-local permissions.

2. Discover company agents and configs:

```bash
curl -sS "$PAPERCLIP_API_URL/api/companies/$PAPERCLIP_COMPANY_ID/agent-configurations" \
  -H "Authorization: Bearer $PAPERCLIP_API_KEY"
```

3. Verify adapter docs:

```bash
curl -sS "$PAPERCLIP_API_URL/llms/agent-configuration/codex_local.txt" \
  -H "Authorization: Bearer $PAPERCLIP_API_KEY"
```

4. Verify runtime skills for the creating agent where applicable:

```bash
curl -sS "$PAPERCLIP_API_URL/api/agents/$PAPERCLIP_AGENT_ID/skills" \
  -H "Authorization: Bearer $PAPERCLIP_API_KEY"
```

The expected state is `supported: true` with Paperclip required skills
configured for the adapter.

5. Choose `name`, `role`, `title`, `icon`, `reportsTo`, `capabilities`, and
   `sourceIssueId`.
6. Choose target runtime.
7. For Codex hires, submit a complete hire request:

```json
{
  "name": "CodexCodeReviewer",
  "role": "engineer",
  "title": "Codex Code Reviewer",
  "icon": "eye",
  "reportsTo": "<cto-or-ceo-agent-id>",
  "capabilities": "Reviews implementation changes using Codex runtime, repository context MCP, and Paperclip issue workflow.",
  "adapterType": "codex_local",
  "adapterConfig": {
    "cwd": "/Users/Shared/Ios/Gimle-Palace",
    "model": "gpt-5.5",
    "modelReasoningEffort": "high",
    "instructionsFilePath": "AGENTS.md",
    "instructionsBundleMode": "managed",
    "maxTurnsPerRun": 200,
    "timeoutSec": 0,
    "graceSec": 15
  },
  "runtimeConfig": {
    "heartbeat": {
      "enabled": false,
      "intervalSec": 14400,
      "wakeOnDemand": true,
      "maxConcurrentRuns": 1,
      "cooldownSec": 10
    }
  },
  "budgetMonthlyCents": 0,
  "sourceIssueId": "<originating-issue-uuid>"
}
```

8. Use `POST /api/companies/:companyId/agent-hires`.
9. Respect approval state and do not continue as if the agent is active while
   approval is pending.
10. After approval, upload the generated `AGENTS.md` with
   `PUT /api/agents/:id/instructions-bundle/file`.
11. Run a minimal smoke verification before assigning real work.

The same procedure should support Claude hires by selecting the Claude target
and preserving Claude adapter config.

Codex create-agent instructions must explicitly tell the agent not to create a
direct DB row, not to patch a Claude agent into Codex, and not to upload Codex
instructions into any live agent whose adapter type is not `codex_local`.

## Proposed Files

Likely shared-fragment changes:

- `fragments/platform/claude/*.md`
- `fragments/platform/codex/*.md`
- `targets/codex/runtime-map.json`
- `scripts/validate-codex-runtime-map.sh`
- builder script or config that accepts `--target claude|codex`

Likely Gimle integration changes:

- `paperclips/dist/codex/*.md`
- deploy/dry-run command that can upload Codex bundles only to Codex agents
- docs describing pilot creation and rollback

## Acceptance Criteria

- Claude production bundles are not changed by the Codex implementation unless a
  later reviewed spec explicitly allows it.
- A Claude build still produces `paperclips/dist/*.md` for the existing deploy
  script.
- A Codex build produces `paperclips/dist/codex/*.md` and never overwrites
  `paperclips/dist/*.md`.
- Codex output contains `AGENTS.md` as the project rules reference and does not
  contain `CLAUDE.md`.
- Codex output contains Codex MCP/skills/agents guidance and does not rely on
  Claude-only `superpowers:*` or Claude Code subagent names.
- Deploy tooling cannot upload Codex output to current Claude agent ids.
- Deploy tooling checks live `adapterType` before upload and refuses mismatches.
- New Codex agents are created only through `POST /api/companies/:companyId/agent-hires`.
- Create-agent preflight verifies identity, company, adapter docs, runtime
  skills, and create-agent permission or board approval path before submitting a
  hire.
- A pending approval stops the create-agent flow until approval is granted.
- Pilot Codex agent creation includes `cwd`, `instructionsFilePath`,
  `instructionsBundleMode`, `runtimeConfig`, `budgetMonthlyCents`, and
  `sourceIssueId`.
- First smoke task is read-only or otherwise explicitly approved before real
  implementation work is assigned.

## Validation Plan

1. Build Claude target for representative roles and diff against current
   `paperclips/dist/*.md`.
2. Build Codex target for representative roles.
3. Grep Codex output for Claude leakage:

```bash
rg -n "superpowers:|Claude Code|Claude CLI|claude CLI|claude-api|CLAUDE\\.md|pr-review-toolkit:|OpusArchitectReviewer" paperclips/dist/codex
```

Allowed mentions are only explanatory text in specs/docs, not generated
runtime bundles.

4. Grep Claude output for accidental Codex leakage:

```bash
rg -n "codex_local|gpt-5\\.5|modelReasoningEffort|CODEX_HOME" paperclips/dist/*.md
```

5. Validate Codex runtime map against the actual iMac/local Codex runtime.
6. Read-only check Paperclip `/api/adapters` confirms `codex_local` is loaded.
7. Read-only check candidate target agents' live adapter type before any upload.
8. Create one pilot Codex agent through `agent-hires` only after review.
9. Upload only that pilot's Codex `AGENTS.md`.
10. Assign a narrow read-only smoke issue.
11. Compare result quality and tool availability against the matching Claude
   role.

## Rollback

Rollback is simple because the existing Claude agents are untouched:

- Stop assigning issues to Codex pilot agents.
- Pause or terminate Codex pilot agents through Paperclip.
- Keep Claude agents and their managed bundles unchanged.

## Open Questions

- First pilot role: `CodeReviewer`, `ResearchAgent`, or a new
  `CodexCodeReviewer`.
- Codex output path: separate `paperclips/dist/codex/` or separate managed
  target directory outside current `dist`.
- Whether all Opus-equivalent roles should start on `gpt-5.5 high`, or whether
  low-risk roles should use cheaper models after the first smoke run.
