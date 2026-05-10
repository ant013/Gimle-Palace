# Paperclip Generic Project + Team Bootstrap Spec

Date: 2026-05-10
Status: draft
Branch: feature/paperclip-generic-project-team-bootstrap-spec

## Problem

Gimle already has enough pieces to create Paperclip teams, provision Codex
runtime homes, register project knowledge, and wire Telegram notifications, but
the current process is still mostly project-specific. The UnstoppableAudit
bootstrap proved that copying a one-off flow creates repeated failures:

- Paperclip system notifications were routed through the Telegram plugin, not
  through agent runtime env vars.
- A new company Codex home can accidentally point at an API-key auth file while
  Gimle agents use a separate ChatGPT/OAuth auth file.
- Paperclip can convert an instructions bundle into `external` mode, but the
  bootstrapper did not automatically materialize each agent's workspace
  `AGENTS.md`.
- Agents can be hired with a generic/fallback workspace instead of the intended
  project/issue workspace if the bootstrapper does not bind `cwd`,
  `instructionsFilePath`, source roots, write roots, and source issue context as
  one atomic step.
- New agents need `--skip-git-repo-check` or a trusted/git workspace.
- Issue prefixes are live Paperclip company state (`GIM`, `UNS`, etc.), not
  something to infer from stale manifests.
- Codebase-memory, Serena, Neo4j, workspaces, artifacts, and Telegram routes
  must be namespaced so projects do not pollute each other.

We need one generic, reviewable bootstrap path where the operator gives a
project/team name, repositories, issue prefix, routing, and team template; the
tool then creates a working Paperclip company/project/team with verified runtime
credentials and isolated knowledge storage.

## Goals

- Define a generic declarative bootstrap contract for new Paperclip projects and
  teams.
- Replace one-off scripts such as `unstoppable_audit_*` with a reusable
  reconciler while preserving project-specific manifests.
- Make runtime credential validation explicit, especially Codex ChatGPT/OAuth
  vs API-key mode.
- Make Telegram routing a Paperclip plugin/company setting, not agent env.
- Ensure codebase-memory, Serena, Neo4j, workspaces, artifacts, and source roots
  are separated per project/company.
- Automatically create and bind every agent to the correct project workspace,
  instructions file, source roots, write roots, and bootstrap issue context.
- Produce enough preflight/postcheck evidence that a retry starts in the right
  chat, with the right model, credentials, instructions, and workspace.
- Use heartbeat diagnostics only as verification that automatic provisioning
  worked, not as a manual repair workflow.

## Non-Goals

- Do not expose raw OAuth tokens, API keys, Telegram bot tokens, or GitHub write
  credentials in manifests, logs, agent env, or AGENTS.md.
- Do not make Telegram system routing depend on agent environment variables.
- Do not force all projects into one company. Company-per-project is allowed and
  usually preferred for issue prefix, routing, permissions, and audit isolation.
- Do not require Neo4j writes in phase 1 if a project is only bootstrapping
  Paperclip agents; namespace reservation and validation are enough.
- Do not mutate existing Gimle agents or Telegram routes except through
  explicitly scoped reconciler operations.

## Inputs

The generic bootstrapper should accept one project package, either as a YAML
file or generated from an interactive wizard:

```yaml
slug: unstoppable-audit
name: UnstoppableAudit
issue_prefix: UNS

paperclip:
  company_mode: create-or-reconcile
  company_id: null
  project_id: null
  source_issue_title: UnstoppableAudit bootstrap

repositories:
  ios:
    url: https://github.com/horizontalsystems/unstoppable-wallet-ios
    stable_mirror_path: /Users/Shared/UnstoppableAudit/repos/ios/unstoppable-wallet-ios.git
    codebase_memory_project: unstoppable-wallet-ios
    serena_project: unstoppable-wallet-ios
  android:
    url: https://github.com/horizontalsystems/unstoppable-wallet-android
    stable_mirror_path: /Users/Shared/UnstoppableAudit/repos/android/unstoppable-wallet-android.git
    codebase_memory_project: unstoppable-wallet-android
    serena_project: unstoppable-wallet-android

runtime:
  run_root: /Users/Shared/UnstoppableAudit/runs
  artifact_root: /Users/Shared/UnstoppableAudit/artifacts
  codex_reference_home: /Users/anton/.paperclip/instances/default/companies/9d8f432c-ff7d-4e3a-bbe3-3cd355f73b64/codex-home
  codex_auth_mode_required: chatgpt
  codex_model_default: gpt-5.4
  codex_extra_args:
    - --skip-git-repo-check

telegram:
  route_mode: paperclip-plugin-company-routing
  ops_chat_id: -1003534905521
  reports_chat_id: -1003937871684
  system_events_to: ops
  report_events_to: reports

knowledge:
  neo4j_project_slug: unstoppable-audit
  group_id: project/unstoppable-audit
  codebase_memory_namespace: project

team_template: mobile-blockchain-audit
roster:
  - name: AUCEO
    role: ceo
    title: UnstoppableAudit CEO
    model: gpt-5.4
    reports_to: null
  - name: UWICTO
    role: cto
    title: iOS Audit CTO
    reports_to: AUCEO
```

## Desired Architecture

The implementation should be a reconciler, not a create-only script:

```text
project package
  -> validate schema
  -> resolve existing Paperclip company/project/issue/agents
  -> compute plan
  -> apply with explicit confirmation
  -> postcheck live Paperclip + filesystem + Codex + Telegram plugin config
```

The reconciler should produce manifests in the same style as the
UnstoppableAudit gates:

- `gate-a-prereq.json` - local paths, auth, plugin, repo, and namespace checks.
- `gate-b-dry-run.json` - desired company/project/team/runtime config.
- `gate-c-apply-plan.json` - Paperclip operations and rollback references.
- `gate-d-live-result.json` - live mutation result.
- `gate-e-postcheck.json` - live readback and smoke evidence.

## Bootstrap Flow

1. Validate project package.
2. Verify Paperclip API auth and operator permissions.
3. Resolve or create Paperclip company.
4. Verify live company `issuePrefix` matches requested prefix.
5. Resolve or create onboarding/source project and bootstrap issue.
6. Configure Telegram plugin routing by company or issue prefix.
7. Register or reserve knowledge namespace:
   - Neo4j `:Project {slug}` / `group_id = project/<slug>` when enabled.
   - codebase-memory project names are explicit and unique.
   - Serena project names are explicit and unique.
8. Prepare source mirrors as read-only source roots.
9. Prepare project-bound runtime layout:
   - per-agent workspace under `runtime.run_root/<agent>/workspace`.
   - per-agent scratch root under `runtime.run_root/<agent>/scratch`.
   - per-agent artifact root under `runtime.artifact_root/<agent>`.
   - source issue/project context recorded in Paperclip before the agent can
     run.
10. Prepare per-company Codex home.
11. Render instructions for every agent.
12. Hire or update agents with the final workspace, instructions, source roots,
    write roots, runtime env, model, and bootstrap issue context in one
    reconciler operation.
13. Patch runtime config and env if live state drifted.
14. Run postcheck and smoke.
15. Parse the smoke heartbeat transcript and fail on any unclassified runtime
    warning.

## Runtime Credential Rules

Codex runtime credential handling is a blocker because API-key mode and
ChatGPT/OAuth mode have different billing and quota behavior.

Preflight must check every new `CODEX_HOME` with:

```bash
CODEX_HOME="<company-codex-home>" codex login status
```

Acceptance:

- Output must say `Logged in using ChatGPT` when `codex_auth_mode_required` is
  `chatgpt`.
- `auth.json` must parse as JSON and contain `auth_mode = "chatgpt"`.
- `auth.json` must contain a token structure compatible with the current Codex
  CLI.
- `auth_mode = "apikey"` is a hard blocker for OAuth-based agents.

Rules:

- Do not symlink a new company `auth.json` to `/Users/anton/.codex/auth.json`
  unless that file itself has been verified as `auth_mode = "chatgpt"`.
- Prefer copying from a known-good company Codex home, such as Gimle's
  `codex-home/auth.json`, when that file is verified as ChatGPT/OAuth.
- Copy credentials with mode `0600`.
- Never write raw credential contents into repo manifests.
- Keep agents/skills as links or copied folders according to existing
  `sync-codex-runtime-home.sh`, but include `auth.json` and `config.toml` in the
  validation surface.

## Codex Adapter Rules

For every `codex_local` agent:

- `adapterConfig.cwd` must be the generated project-bound agent workspace, not
  a Paperclip fallback workspace.
- `adapterConfig.env.CODEX_HOME` must point at the verified company Codex home.
- `adapterConfig.env.PATH` must include the Codex binary path used by Paperclip.
- `adapterConfig.extraArgs` must include `--skip-git-repo-check`, unless the
  workspace is known trusted and git-initialized.
- `adapterConfig.model` must match the project package. Drift from `gpt-5.4` to
  `gpt-5.5` should be detected and patched only when requested by package.
- `adapterConfig.dangerouslyBypassApprovalsAndSandbox` should be explicit.
- `sourceRootsReadOnly` must contain product repositories.
- `writableRoots` must contain only per-agent artifact and scratch roots.
- The source issue/project context used for the first run must be assigned as
  part of agent creation or reconciliation. The bootstrapper must not rely on a
  later manual move/retry to attach the agent to the right issue.

## Agent Workspace Provisioning Rules

Agent creation is not complete until filesystem layout and Paperclip live
config agree. The bootstrapper must create or reconcile this state before any
agent can run:

- `runtime.run_root/<agent>/workspace` exists.
- `runtime.run_root/<agent>/scratch` exists.
- `runtime.artifact_root/<agent>` exists.
- `adapterConfig.cwd` points to the workspace above.
- `adapterConfig.instructionsFilePath`, when external, points to
  `<workspace>/AGENTS.md`.
- `writableRoots` includes only the agent scratch and artifact roots.
- `sourceRootsReadOnly` includes the project source mirrors.
- The Paperclip agent is attached to the intended company, project/bootstrap
  issue, source roots, and issue prefix.

The reconciler must treat these as desired state. If a newly hired agent points
at a fallback workspace, missing workspace, missing `AGENTS.md`, wrong
instructions path, wrong roots, or no source issue context, apply must fail or
patch the agent automatically before the first heartbeat.

Manual copying of `AGENTS.md` or moving agents between fallback and project
workspaces is a bug in the bootstrapper, not an operator step.

## Instructions Bundle Rules

Paperclip has two relevant modes:

- `managed`: Paperclip stores agent instructions under the company/agent
  instructions directory.
- `external`: Paperclip expects the file at `adapterConfig.instructionsFilePath`
  to exist on disk.

Postcheck must verify:

- If `instructionsBundleMode = "managed"`, Paperclip readback points to the
  managed company/agent instructions path.
- If `instructionsBundleMode = "external"`, every workspace contains
  `AGENTS.md`.
- If `instructionsBundleMode = "external"`, the exact
  `adapterConfig.instructionsFilePath` exists before any heartbeat or smoke run
  is started.
- If `instructionsBundleMode = "external"`, the bootstrapper renders or copies
  `AGENTS.md` into every agent workspace during apply. Operators should never
  need to materialize this file manually after a failed run.
- Rendered `AGENTS.md` contains project slug, source roots, write roots, role,
  reporting line, and credential constraints.
- No AGENTS.md contains raw secrets or bootstrap admin credentials.

## Provisioning Smoke Rules

The first heartbeat is a verification of automatic provisioning, not a manual
repair workflow. The bootstrapper must capture stdout/stderr/transcript lines
and use them to prove that the agent was created in the right place.

Required signals:

- Codex must reach initialization, for example `initmodel codex` or equivalent
  session-start evidence.
- The run must use the intended `CODEX_HOME`; `codex login status` for that home
  must already be verified as ChatGPT/OAuth when required.
- The agent instructions path must be readable before launch. A line like
  `could not read agent instructions file ... AGENTS.md` is a failed
  instructions postcheck.
- The run workspace must be the project/issue workspace created by the
  bootstrapper. A line like `No project or prior session workspace was
  available. Using fallback workspace ...` means provisioning failed. It is not
  an acceptable post-bootstrap state.
- A line like `write_stdin failed: stdin is closed for this session` is a
  tool-session failure. If Codex initialized and instructions/workspace checks
  passed, classify it separately and inspect which command/session attempted the
  write instead of treating it as quota or credential failure.

Postcheck output must include:

- credential result: `chatgpt`, `apikey`, missing, malformed, or unknown.
- instructions result: managed path or external `AGENTS.md` existence.
- workspace result: assigned project/issue workspace, prior session workspace,
  or fallback workspace marked as provisioning failure.
- tool-session result: no router errors, or the exact router error class.

Known UnstoppableAudit lesson:

- AUCEO reached Codex initialization after the company `CODEX_HOME` was copied
  from Gimle's ChatGPT/OAuth home, but the heartbeat still warned about missing
  `/Users/Shared/UnstoppableAudit/runs/AUCEO/workspace/AGENTS.md` and fallback
  workspace selection. The generic bootstrapper must prevent this by creating
  the workspace, rendering `AGENTS.md`, and binding the Paperclip agent to the
  project/bootstrap issue before the first AUCEO run.

## Telegram Routing Rules

Paperclip system notifications are plugin-level behavior. Agent env vars such
as `TELEGRAM_OPS_CHAT_ID` do not route `agent.started`, `run.failed`, quota, or
adapter errors.

The generic bootstrapper must configure the Paperclip Telegram plugin routing
for the new company or issue prefix:

- system events: ops chat.
- adapter failures and quota failures: ops chat.
- human escalation: ops chat unless package overrides.
- redacted reports and audit artifacts: reports chat.

Postcheck must prove route isolation:

- Gimle `GIM-*` events still route to Gimle chats.
- New project prefix events, such as `UNS-*`, route to the configured project
  chats.
- Plugin worker restart or reload is performed when the plugin requires it.

## Knowledge Isolation Rules

The project package must declare all knowledge namespaces explicitly:

- Paperclip company ID and issue prefix.
- Neo4j project slug and group ID.
- codebase-memory project names.
- Serena project names.
- source mirror roots.
- artifact and run roots.

No namespace should be inferred from stale manifests. The bootstrapper should
fail if a requested namespace is already bound to another active project unless
the package says `mode: reconcile`.

## Required Postcheck

The postcheck must produce one manifest with:

- Paperclip company ID, project ID, issue prefix, and bootstrap issue key.
- Live Telegram routing summary without bot tokens.
- Per-agent live config summary:
  - name, agent ID, model, status.
  - `CODEX_HOME`, auth mode, and login status.
  - `cwd`, `extraArgs`, source roots, writable roots.
  - source issue/project binding used by the first run.
  - instructions mode and file existence.
- Filesystem summary:
  - workspaces exist.
  - scratch/artifact roots exist.
  - source roots exist and are read-only to agents.
- Knowledge summary:
  - Neo4j project namespace exists or is explicitly skipped.
  - codebase-memory project names are indexed or explicitly pending.
  - Serena project names are resolvable or explicitly pending.
- Smoke result:
  - at least one low-cost agent run starts in the correct Telegram chat.
  - the run does not fail for trusted-directory, missing AGENTS.md, or API-key
    quota reasons.
  - heartbeat transcript is classified into credential, instructions,
    workspace-context, and tool-session results.
  - no fallback workspace is used after project/team bootstrap.

## Affected Files / Areas

Expected future implementation areas:

- `paperclips/scripts/paperclip_project_team_bootstrap.py` - generic
  reconciler.
- `paperclips/schemas/project-team-bootstrap.schema.json` - package schema.
- `paperclips/templates/team/*.yaml` - reusable team templates.
- `paperclips/templates/project/*.yaml` - project package examples.
- `paperclips/sync-codex-runtime-home.sh` - include auth/config validation or
  split into a reusable Codex home preparation command.
- `paperclips/tests/` - unit tests for planning, credential validation,
  Telegram routing diff, and instructions mode handling.
- `docs/paperclip-operations/telegram-bot.md` - update with multi-company
  routing, not only a global default chat.

## Acceptance Criteria

- A single command can dry-run a new Paperclip project/team from a package file.
- Dry-run output lists all Paperclip, filesystem, Telegram, Codex, and knowledge
  changes before mutation.
- Live apply is guarded by an explicit confirmation token.
- A new company can be created with the correct issue prefix.
- Agent roster is hired or reconciled idempotently.
- Agent creation automatically provisions the correct per-agent workspace,
  scratch root, artifact root, instructions file, source roots, write roots,
  runtime env, and source issue/project binding.
- Codex agents use verified ChatGPT/OAuth credentials, not API-key mode, when
  requested.
- Paperclip Telegram plugin routes project events to project chats without
  changing Gimle routing.
- Every `codex_local` agent has a valid project-bound workspace, instructions
  file or managed bundle, `--skip-git-repo-check`, and scoped write roots before
  its first run.
- Heartbeat postcheck proves that the agent initializes Codex with the intended
  company `CODEX_HOME`, can read instructions, and starts from the intended
  project/issue workspace.
- No successful bootstrap requires manually moving agents or copying
  `AGENTS.md` into run workspaces after hiring.
- Re-running the bootstrapper makes no changes when live state already matches
  the package.
- A failed preflight explains the exact blocker and does not partially mutate
  Paperclip or local runtime state.

## Verification Plan

- Unit tests:
  - schema validation for project package.
  - desired-state rendering from package.
  - diff planning for create, update, and no-op.
  - Codex auth parser detects `chatgpt`, `apikey`, missing, and malformed auth.
  - instructions mode postcheck for managed vs external.
  - Telegram routing diff never writes raw bot token to manifest.
- Integration tests with mocked Paperclip API:
  - create company/project/agents.
  - reconcile existing agents.
  - detect duplicate agents.
  - rollback manifest generation.
- Live dry-run on current Gimle and UnstoppableAudit:
  - Gimle reports no drift unless package requests it.
  - UnstoppableAudit reports known drift only.
- Live smoke after approval:
  - one agent starts and reaches Codex initialization using ChatGPT/OAuth.
  - Telegram start/fail event lands in the configured project ops chat.
  - no `Not inside a trusted directory` failure.
  - no missing `AGENTS.md` warning when mode is external.
  - no fallback workspace warning.
  - any `stdin is closed` / router error is reported as a tool-session issue,
    not as OAuth or quota failure.

## Open Questions

- Should generic bootstrap create one Paperclip company per product, or support
  multiple projects inside one company by default?
- Should issue prefix be immutable once a company is created, or can the
  reconciler patch it if no issues exist yet?
- What is the exact Paperclip Telegram plugin API for company/issue-prefix
  routing, and does it require worker restart after every route change?
- Should Codex OAuth credentials be copied per company or linked to a single
  known-good OAuth home? Copying is safer for drift; linking is simpler.
- Should `instructionsBundleMode` be forced to `managed` for all new projects,
  or should external workspace `AGENTS.md` remain supported?
- Should codebase-memory indexes be created by bootstrapper, or only validated
  as prerequisites?
- Should Neo4j `:Project` registration be phase 1 for every new Paperclip
  project, or optional until first ingest?
