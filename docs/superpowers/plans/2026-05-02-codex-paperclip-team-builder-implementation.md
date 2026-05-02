# Codex Paperclip Team Builder Implementation Plan

## Objective

Implement the remaining safe path for running a duplicate Codex Paperclip team
without changing the existing Claude team. The work proceeds from build-time
separation to deploy guardrails, then to one approved pilot Codex agent.

## Guardrails

- Start every implementation branch from `origin/develop`.
- Do not patch existing Claude agent records into Codex records.
- Do not overwrite existing Claude managed bundles.
- Do not remove Claude-only `superpowers:*` or Claude subagent instructions from
  the Claude target.
- Do not direct-write Paperclip database rows for agent creation.
- Use `POST /api/companies/:companyId/agent-hires` for new agents.

## Dependencies

- Codex runtime map source:
  `/Users/ant013/Android/paperclip-shared-fragments/targets/codex/runtime-map.json`.
- Current shared-fragments branch:
  `feature/codex-global-spec-gate`.
- Gimle must consume the shared-fragments runtime map either by merging/bumping
  the shared fragments dependency or by copying a reviewed snapshot into the
  Gimle implementation branch.
- If the runtime map is not yet merged, Phase 3 may proceed only with an
  explicit pinned commit hash recorded in the implementation PR.

## Write Scopes

| Phase | Repo | Allowed writes | Forbidden writes |
|---|---|---|---|
| 1 | Gimle + shared fragments | Docs/notes only | Prompt output, live bundles, API writes |
| 2 | Gimle | `paperclips/build.sh` or new builder script, build docs | Existing live agent ids, existing deploy API behavior |
| 3 | shared fragments first, Gimle integration second | Target-specific fragments, runtime map references | Claude-only fragment semantics |
| 4 | Gimle | Validation scripts/docs if needed | Live Paperclip state |
| 5 | Gimle | New Codex deploy script or target-aware deploy mode | Uploading to current Claude ids |
| 6 | Paperclip API | `agent-hires` for one approved pilot only | Patching existing agents, direct DB writes |
| 7 | Paperclip API | One read-only smoke issue/comment flow | Broad team rollout |
| 8 | Gimle + Paperclip API | Additional Codex hires after pilot approval | Claude team conversion |
 
The first implementation PR should keep Phase 6+ live API writes out of scope
unless the PR explicitly requests pilot approval.

## Phase 1: Builder Discovery

1. Inspect current Gimle prompt build flow:
   - `paperclips/build.sh`
   - `paperclips/roles/*.md`
   - `paperclips/fragments/**`
   - `paperclips/dist/*.md`
2. Inspect shared fragment source and current include semantics.
3. Record which files are consumer-owned in Gimle and which are shared-fragment
   owned.
4. Decide exact implementation location for target-aware build logic.

Exit criteria:

- We know whether the first implementation belongs in Gimle only, shared
  fragments only, or both.
- Existing Claude build behavior is documented before changes.

## Phase 2: Target-Aware Build

Implementation choice:

- Keep the current `paperclips/build.sh` legacy behavior as the Claude default.
- Add a small target-aware wrapper or builder rather than replacing the current
  awk expander in-place.
- Do not rely on broad global string replacement. Target-specific content should
  come from explicit target fragments or explicit token values.
- The first acceptable mechanism is:
  - legacy command: `./paperclips/build.sh` builds Claude output exactly as
    today;
  - new command: `./paperclips/build.sh --target codex` or
    `./paperclips/build-target.sh codex` writes `paperclips/dist/codex/*.md`;
  - token values are supplied by a small target map:
    `PROJECT_RULES_FILE`, `RUNTIME_FRAGMENT`, `CREATE_AGENT_FRAGMENT`.

Steps:

1. Add target parameters:
   - `target=claude|codex`
   - `projectRulesFile=CLAUDE.md|AGENTS.md`
   - `runtimeFragment=claude|codex`
   - `createAgentFragment=claude|codex`
2. Keep Claude output at `paperclips/dist/*.md`.
3. Add Codex output at `paperclips/dist/codex/*.md`.
4. Ensure a Codex build cannot overwrite top-level `paperclips/dist/*.md`.
5. Preserve current Claude build as the default command.

Exit criteria:

- Running the legacy build still produces the same Claude output path.
- Running the Codex build produces only `paperclips/dist/codex/*.md`.

## Phase 3: Codex Runtime Fragments

1. Add Codex runtime instructions:
   - use `AGENTS.md` for project rules;
   - load context with `codebase-memory` and `serena`;
   - use installed Codex agents and skills;
   - apply Karpathy discipline.
2. Add Codex skills/agents mapping using the pinned runtime map dependency.
3. Add Codex create-agent instructions:
   - verify identity and permissions;
   - verify company and adapter docs;
   - verify runtime skills;
   - submit `codex_local` hire request;
   - wait for approval;
   - upload Codex `AGENTS.md`;
   - smoke test before real work.
4. Keep Claude runtime/create-agent fragments unchanged except for target
   parameter wiring.

Exit criteria:

- Codex output contains Codex runtime instructions.
- Claude output still contains current Claude runtime instructions.

## Phase 4: Leakage And Parity Validation

1. Run Claude build and compare generated Claude bundles against the current
   tracked `paperclips/dist/*.md`.
2. Run Codex build.
3. Check Codex output denylist:

```bash
rg -n "superpowers:|Claude Code|Claude CLI|claude CLI|claude-api|CLAUDE\\.md|pr-review-toolkit:|OpusArchitectReviewer" paperclips/dist/codex
```

4. Check Claude output denylist for accidental Codex leakage:

```bash
rg -n "codex_local|gpt-5\\.5|modelReasoningEffort|CODEX_HOME" paperclips/dist/*.md
```

5. Validate Codex runtime availability locally and on iMac.

Exit criteria:

- No forbidden Codex leakage remains in generated Codex runtime bundles.
- No accidental Codex runtime content appears in Claude bundles.
- Runtime map validation passes.

## Phase 5: Deploy Guardrails

Policy for the first Codex pilot:

- Prefer API deploy for Codex bundles.
- Do not allow Codex `--local` copy in the first implementation slice.
- If local mode is later added, it must first read the target agent config and
  prove `adapterType: "codex_local"` before copying to a managed bundle path.
- Existing Claude local deploy may remain unchanged, but adding an adapter
  preflight there is allowed if it does not change successful behavior.

Steps:

1. Add Codex deploy path:
   - preferred: `paperclips/deploy-codex-agents.sh`;
   - acceptable alternative: `paperclips/deploy-agents.sh --target codex`.
2. Use a separate Codex agent id map.
3. Before upload, fetch each live agent config.
4. Refuse upload unless live `adapterType` matches target:
   - Claude deploy requires `claude_local`;
   - Codex deploy requires `codex_local`.
5. In dry-run mode, print planned uploads without writing bundles.

Exit criteria:

- Codex deploy cannot target current Claude ids.
- Claude deploy cannot target future Codex ids.
- Dry-run shows exact agent id, adapter type, and bundle path.

## Phase 6: Pilot Agent Creation

1. Choose first pilot role.
   Recommended first pilot: `CodexCodeReviewer`.
   Rationale: Paperclip has no `reviewer` role enum, and the existing Medic
   `CodeReviewer` uses `role: "engineer"`. A reviewer pilot is low-risk because
   the first smoke task can be read-only and does not require write access to
   production code.
2. Submit a new hire request through Paperclip API:

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

Before submitting the first hire, re-read:

```bash
curl -sS "$PAPERCLIP_API_URL/llms/agent-configuration/codex_local.txt" \
  -H "Authorization: Bearer $PAPERCLIP_API_KEY"
```

Confirm that:

- `timeoutSec` is accepted and `0` means no timeout for the current adapter
  version, or replace it with the documented safe value.
- `maxTurnsPerRun` is accepted by `codex_local`.
- `modelReasoningEffort: "high"` is accepted for the selected model.

3. Wait for board approval if Paperclip returns `pending_approval`.
4. Upload only the pilot Codex bundle.
5. Confirm live agent config shows `adapterType: "codex_local"`.

Exit criteria:

- One pilot Codex agent exists as a separate Paperclip agent.
- Existing Claude agents remain unchanged.

## Phase 7: Smoke Test

1. Assign a narrow read-only issue to the pilot Codex agent.
2. Expected behavior:
   - agent starts through `codex_local`;
   - reads `AGENTS.md` bundle;
   - can use Paperclip issue workflow;
   - can use Codex runtime context guidance;
   - leaves a clear comment/result.
3. Compare pilot output with the equivalent Claude role.
4. Record failures before expanding the team.

Exit criteria:

- Pilot agent completes a read-only smoke task.
- Any missing tool/MCP/skill gaps are documented.
- No Claude agent behavior regresses.

## Phase 8: Team Expansion

1. Map remaining Gimle roles to Codex equivalents.
2. Create Codex hires one role at a time or in small batches.
3. Upload generated Codex bundles only after approval.
4. Run role-specific smoke checks.
5. Keep Claude team as fallback until Codex parity is demonstrated.

Exit criteria:

- Codex duplicate team exists beside Claude team.
- Claude remains operational.
- Rollback remains pause/stop assigning/terminate Codex agents only.
