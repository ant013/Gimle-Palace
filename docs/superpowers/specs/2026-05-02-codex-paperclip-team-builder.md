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
- `instructionsFilePath` managed by Paperclip
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

## Codex Create-Agent Flow

Codex agents must be able to create new Paperclip agents by following an
explicit target-aware procedure:

1. Discover company and existing agents with Paperclip API.
2. Choose `name`, `role`, `title`, `icon`, `reportsTo`, and `capabilities`.
3. Choose target runtime.
4. For Codex hires, submit:

```json
{
  "adapterType": "codex_local",
  "adapterConfig": {
    "model": "gpt-5.5",
    "modelReasoningEffort": "high",
    "instructionsBundleMode": "managed"
  }
}
```

5. Use `POST /api/companies/:companyId/agent-hires`.
6. Respect approval state and do not continue as if the agent is active while
   approval is pending.
7. After approval, upload the generated `AGENTS.md` with
   `PUT /api/agents/:id/instructions-bundle/file`.
8. Run a minimal smoke verification before assigning real work.

The same procedure should support Claude hires by selecting the Claude target
and preserving Claude adapter config.

## Proposed Files

Likely shared-fragment changes:

- `fragments/platform/claude/*.md`
- `fragments/platform/codex/*.md`
- `targets/codex/runtime-map.json`
- `scripts/validate-codex-runtime-map.sh`
- builder script or config that accepts `--target claude|codex`

Likely Gimle integration changes:

- `paperclips/dist/codex/*.md` or an equivalent separate Codex output path
- deploy/dry-run command that can upload Codex bundles only to Codex agents
- docs describing pilot creation and rollback

## Validation Plan

1. Build Claude target for representative roles and diff against current
   `paperclips/dist/*.md`.
2. Build Codex target for representative roles.
3. Grep Codex output for Claude leakage:

```bash
rg -n "superpowers:|Claude Code|claude CLI|CLAUDE\\.md" paperclips/dist/codex
```

4. Validate Codex runtime map against the actual iMac/local Codex runtime.
5. Read-only check Paperclip `/api/adapters` confirms `codex_local` is loaded.
6. Create one pilot Codex agent through `agent-hires` only after review.
7. Upload only that pilot's Codex `AGENTS.md`.
8. Assign a narrow read-only smoke issue.
9. Compare result quality and tool availability against the matching Claude
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
