# Paperclip Layered Agent Assembly

## Status

Proposed.

## Context

Paperclip agent instructions now encode many lessons from real failures:
stale wakeups, ownerless handoffs, missing QA evidence, lock conflicts, merge
readiness mistakes, MCP/tool drift, and target-specific runtime differences.
Those rules are valuable and must not be weakened.

The current Gimle assembly path already has useful layers:

- source role files under `paperclips/roles/` and `paperclips/roles-codex/`;
- shared fragments under `paperclips/fragments/shared/`;
- Gimle local fragments under `paperclips/fragments/local/`;
- Codex target overrides under `paperclips/fragments/targets/codex/`;
- generated bundles under `paperclips/dist/` and `paperclips/dist/codex/`;
- deploy scripts that copy or upload `AGENTS.md` into Paperclip.

The problem is that these layers are not clean enough to support every project.
Gimle values still appear in places that should be generic, and deploy scripts
hard-code Gimle company and agent mappings. UAudit exposed the failure mode: a
manual runtime bootstrap produced live instructions that looked similar, but did
not inherit the exact handoff/assign discipline from the source-of-truth build.

This spec defines a layered assembly model where each level owns one concern,
project-specific values are supplied as parameters, and final generated bundles
remain no larger than current bundles.

Important current-state constraint: existing assembly metadata must be made
green before layered migration starts. At the time of this spec, a fresh worktree
without initialized submodules fails validation because
`paperclips/fragments/shared` is empty, and the current role/baseline/coverage
metadata has drift around `auditor` / `cx-auditor`. Layered assembly must not
hide or compound that drift.

## Assumptions

- `paperclip-shared-fragments` is the source of project-independent Paperclip
  lifecycle and role-prime logic.
- Project repositories such as Gimle, UAudit, and Medic own their project
  overlays, agent rosters, repo paths, issue prefixes, and verification gates.
- Generated `dist` files are build artifacts, not hand-authored source.
- Existing high-value behavioral rules should be preserved. Migration may move,
  parameterize, deduplicate, or shorten narrative text, but must not delete the
  mandatory logic expressed by current rules.
- Claude and Codex are targets of the same assembly system, not separate
  hand-maintained instruction systems.
- Live Paperclip agents should receive instructions only from generated bundles,
  not ad hoc edits to runtime workspace `AGENTS.md`.

## Goals

- Define a complete path from generic role/fragments to live Paperclip agent for
  each project.
- Isolate concerns by layer: shared logic, target runtime, project parameters,
  project overlay, agent binding, generated output, deploy.
- Keep generated role bundles at or below current size, with a preference for
  shrinking repeated text.
- Preserve the handoff, heartbeat, close, review, QA, merge, MCP, and
  delegation logic that currently prevents known Paperclip failures.
- Make project builders data-driven so Gimle, UAudit, and Medic can be assembled
  through the same mechanism with different manifests.
- Add validation that prevents unresolved variables, cross-project leakage, and
  logic loss during migration.
- Reconcile current builder, validator, baseline, role matrix, and deploy
  metadata before changing generated bundle semantics.

## Non-Goals

- Rewriting Paperclip runtime behavior.
- Changing live agent records before the generated bundles validate.
- Removing existing safety rules to hit a size target.
- Replacing project technical instructions such as `AGENTS.md` or `CLAUDE.md`.
- Designing UAudit audit methodology in detail; UAudit-specific audit content
  belongs in the UAudit project overlay.
- Migrating UAudit or Medic in the first implementation slice.
- Changing generated output paths for live deploy consumers in the first slice.
- Editing live Paperclip agent workspace `AGENTS.md` files by hand.

## First Shippable Slice

The first implementation slice is intentionally narrow:

```text
Project: Gimle only
Targets: existing Claude + Codex Gimle teams
Output paths: legacy paths retained
Deploy: no live deploy; project-aware dry-run and compare wrappers are allowed
Goal: manifest-driven build can regenerate current Gimle artifacts with current
      validator green and no bundle size growth
```

The first slice does not deploy UAudit or Medic and does not move live consumers
to a new output layout. UAudit and Medic are migration phases after the Gimle
manifest/builder path proves it can reproduce the current Gimle bundles.

Compatibility rule: during the first slice, the canonical source becomes the
Gimle manifest plus overlays, but generated artifacts continue to be written to
the legacy locations:

```text
paperclips/dist/*.md
paperclips/dist/codex/*.md
paperclips/codex-agent-ids.env
```

Existing deploy scripts, watchdog consumers, validators, and workspace update
scripts must continue to work against those legacy paths until a separate
consumer-migration spec changes them.

Compatibility authority rule: the project manifest is the canonical logical
source for project facts, but Slice 1 may import existing compatibility inputs
such as `codex-agent-ids.env` and current deploy name mappings. Those files are
not a second source of truth; they are legacy inputs used to resolve the
manifest until a later slice generates them from the manifest.

## Source Of Truth

Ownership is fixed as follows:

- `paperclip-shared-fragments` owns generic schema definitions, generic
  validation rules, shared fragments, shared role templates, and sample
  manifests with placeholder values only.
- Each project repo owns real project manifests, real agent IDs, company IDs,
  repo paths, MCP/codebase-memory names, local overlays, generated bundles, and
  deploy binding metadata.
- Generated bundle metadata, hashes, size measurements, and compatibility output
  maps live in the project repo beside the generated bundles.

`paperclip-shared-fragments` must never contain real Gimle, UAudit, or Medic
company IDs, agent IDs, repo paths, or issue prefixes except inside historical
documentation that is not included into generated agent bundles.

## Layer Model

### L0: Shared Invariants

Owned by `paperclip-shared-fragments`.

Contains project-independent rules:

- heartbeat and idle behavior;
- explicit assignment and handoff discipline;
- close and blocked protocols;
- lock conflict handling;
- worktree and branch safety;
- review and QA evidence shapes;
- untrusted content policy;
- Karpathy-style verification discipline;
- role-prime behavior that is not tied to a product.

This layer may reference variables, but not concrete project values.

Allowed examples:

```text
{{ISSUE_PREFIX}}
{{CODEBASE_MEMORY_PROJECT}}
{{PROJECT_PLAN_PATH_PATTERN}}
{{QA_AGENT_NAME}}
{{CTO_AGENT_NAME}}
```

Forbidden examples:

```text
GIM-182
repos-gimle
/Users/Shared/Ios/Gimle-Palace
services/palace-mcp
Gimle-only agent UUIDs
```

Historical incident IDs may remain only when they are clearly marked as generic
lesson references or parameterized examples. If a bundle needs the rule but not
the story, keep the rule in the generated bundle and move the long story to a
lesson/runbook reference.

### L1: Shared Role Templates

Owned by `paperclip-shared-fragments`.

Contains role skeletons such as CTO, CodeReviewer, QAEngineer, ResearchAgent,
InfraEngineer, SecurityAuditor, and TechnicalWriter.

Templates define the role's generic responsibility and include L0 fragments.
They expose slots for project-owned content:

```text
{{PROJECT}}
{{DELEGATION_MAP}}
{{VERIFICATION_GATES}}
{{MCP_SUBAGENTS_SKILLS}}
{{RESPONSIBILITY_PATHS}}
{{COMPLIANCE_CHECKLIST}}
{{SMOKE_GATE}}
{{OUTPUT_CATALOGUE}}
```

Templates must stay small. Large project-specific tables belong to project
overlay files, not shared role templates.

### L2: Target Runtime Overlay

Owned by shared runtime definitions. Project-owned target values are supplied by
the project manifest.

Defines differences between target runtimes:

- Claude vs Codex instruction entry file;
- `CLAUDE.md` vs `AGENTS.md` wording;
- target capability contracts for tools, MCP servers, skills, and subagents;
- target-specific mention/agent naming conventions;
- target-specific deploy mode.

Target overlays must not contain product-specific repo paths, company IDs, or
issue prefixes. If a target needs a roster, it receives it from the project
manifest for that target.

The base MCP contract is project-independent and is declared once in the
project/target assembly metadata, not duplicated in every agent bundle:

```yaml
base_mcp_required:
  - codebase-memory
  - context7
  - serena
  - github
  - sequential-thinking
```

`codebase-memory` is common, but its project/index names are project-owned
values. Shared fragments may say "use codebase-memory first"; they must not
hard-code `repos-gimle`, UAudit repo names, or Medic repo names.

Role-owned skills and subagents remain in role templates or shared role
fragments when they are genuinely role semantics, for example CTO review
delegation or QA test-audit delegation. Project manifests may append
project/runtime-specific capabilities; they must not silently remove role
capabilities. Shared/common capability lists are validated from the resolved
manifest so they do not inflate every generated agent.

### L3: Project Manifest

Owned by each project repository.

The project manifest is the only file the project-specific builder needs to know
about for project facts. It supplies values for template variables and points to
overlay fragments.

Proposed path:

```text
paperclips/projects/<project-key>/paperclip-agent-assembly.yaml
```

Required fields:

```yaml
project:
  key: gimle
  display_name: Gimle
  issue_prefix: GIM
  company_id: "..."
  integration_branch: develop
  specs_dir: docs/superpowers/specs
  plans_dir: docs/superpowers/plans

targets:
  claude:
    instruction_entry_file: AGENTS.md
    deploy_mode: local-or-api
    adapter_type: claude_local
    instructions_bundle_mode: external-or-managed
  codex:
    instruction_entry_file: AGENTS.md
    deploy_mode: api
    adapter_type: codex_local
    instructions_bundle_mode: managed

paths:
  project_root: /Users/Shared/Ios/Gimle-Palace
  primary_repo_root: /Users/Shared/Ios/Gimle-Palace
  shared_fragments_root: paperclips/fragments/shared
  overlay_root: paperclips/projects/gimle/overlays
  project_rules_file: AGENTS.md

mcp:
  base_required:
    - codebase-memory
    - context7
    - serena
    - github
    - sequential-thinking
  codebase_memory_projects:
    primary: repos-gimle
  additions:
    project: []
    by_role:
      security-auditor: []

agents:
  - role_key: cto
    target: claude
    display_name: CTO
    agent_id: "..."
    adapter_type: claude_local
    instructions_bundle_mode: external-or-managed
    workspace_cwd: /Users/Shared/Ios/worktrees/claude/Gimle-Palace
    output_path: paperclips/dist/cto.md
    icon: eye
    template: management/cto.md
    overlays:
      - delegation-map.md
      - verification-gates.md
    capability_additions:
      mcp: []
      skills: []
      subagents: []
  - role_key: cx-cto
    target: codex
    display_name: CXCTO
    agent_id: "..."
    adapter_type: codex_local
    instructions_bundle_mode: managed
    workspace_cwd: /Users/Shared/Ios/worktrees/cx/Gimle-Palace
    output_path: paperclips/dist/codex/cx-cto.md
    icon: crown
    template: management/cto.md
    overlays:
      - delegation-map-codex.md
      - verification-gates.md
    capability_additions:
      mcp: []
      skills: []
      subagents: []
```

The manifest may include multiple repos and MCP indexes for projects such as
UAudit:

```yaml
paths:
  repos:
    ios: /Users/Shared/UnstoppableAudit/repos/ios/unstoppable-wallet-ios
    android: /Users/Shared/UnstoppableAudit/repos/android/unstoppable-wallet-android

mcp:
  base_required:
    - codebase-memory
    - context7
    - serena
    - github
    - sequential-thinking
  codebase_memory_projects:
    ios: Users-Shared-UnstoppableAudit-repos-ios-unstoppable-wallet-ios
    android: Users-Shared-UnstoppableAudit-repos-android-unstoppable-wallet-android
  additions:
    project:
      - neo4j
    by_role:
      auditor:
        - neo4j
```

Manifest schema rules:

- `adapter_type` is required for every target and every agent. Deploy refuses a
  live agent whose adapter type differs.
- `instructions_bundle_mode` is required so managed Codex bundles and external
  workspace files are not confused.
- `workspace_cwd` is required for any script that patches or verifies agent
  workspaces.
- `output_path` is required during compatibility mode and must point to the
  legacy generated file consumed by current deploy scripts.
- Overlay resolution order is fixed:
  `shared template -> shared include -> target overlay -> project overlay ->
  agent overlay`.
- Capability resolution order is additive:
  `base required MCP -> target capability contract -> role skills/subagents ->
  project additions -> agent additions`. Project additions append entries such
  as UAudit `neo4j` MCP; they do not replace the common MCP set or role-owned
  skills/subagents.
- Builders must emit a resolved capability manifest next to generated bundles.
  Validation checks the resolved manifest for common MCP and project additions.
  Agent bundles only receive capability text when a role-specific instruction
  actually needs it.
- Paths are normalized relative to the project repo unless an absolute runtime
  path is explicitly required for Paperclip adapter configuration.
- Agent IDs may come from the manifest or from a declared env/env-file source,
  but the resolved build manifest must contain the selected agent's concrete ID
  before deploy. Missing IDs remain visible as `PENDING` and are not silently
  skipped.
- Resolved manifests fingerprint declared compatibility inputs so ID mapping
  drift is detected when legacy env or deploy mapping files change without a
  rebuild.

### L4: Project Overlay Fragments

Owned by each project repository.

Contains project-specific content referenced by the manifest:

- agent roster and UUIDs;
- delegation map;
- verification gates;
- repo map;
- issue prefix and path conventions;
- project-specific MCP/codebase-memory names;
- role-specific project responsibilities;
- project-specific bans and smoke commands.

Proposed path:

```text
paperclips/projects/<project-key>/overlays/
```

Project overlays may be verbose if needed, but generated bundles must still
meet size budgets. If an overlay table is too large, split it into:

- mandatory short rule in the bundle;
- referenced runbook/spec for background detail.

### L5: Generated Bundle

Owned by the build output.

Generated files are final instructions for one concrete agent.

Target layout after all consumers migrate:

```text
paperclips/dist/<project-key>/<target>/<agent>.md
```

Compatibility layout for the first shippable slice:

```text
paperclips/dist/*.md
paperclips/dist/codex/*.md
```

The first slice must emit the compatibility layout. The new layout is a future
consumer-migration step and must not be required by the initial builder,
validator, or deploy changes.

Generated bundles must contain:

- no unresolved `{{VARIABLE}}`;
- no unresolved `@include`;
- no wrong project literals;
- no source frontmatter;
- all mandatory logic markers required by the role profile;
- target-correct instruction naming and tool language.

Generated bundles may contain concrete project values because they are the final
agent artifact.

### L6: Deploy Binding

Owned by project deploy config plus generic deploy tooling.

Future deploy tooling should not hard-code Gimle, Medic, or UAudit. It should
read the project manifest and upload/copy each generated bundle to the matching
agent.

Future deploy behaviors:

- refuse upload to an agent whose live adapter type does not match the target;
- deploy only generated bundle content;
- verify at least one stable marker per target agent after deploy;
- support dry-run and single-agent deploy by project, target, and agent;
- write a deploy summary with project key, target, agent count, source SHA, and
  generated bundle hashes;
- never mutate another project's agents.

## Size Discipline

Migration must not increase generated bundle size.

Before changing assembly, capture a baseline:

```text
agent, target, bytes, lines, words, mandatory_marker_count
```

Acceptance rule:

- Phase 0 keeps the current validator policy while making metadata green;
- migrated layered bundles use stricter policy: effective
  `maxGrowthPercent: 0`;
- each migrated generated bundle must be `<=` its baseline byte count unless a
  reviewer explicitly approves a documented allowlist exception;
- total generated size per project and target must be `<=` baseline;
- preferred outcome is smaller generated output by removing duplication and
  moving background narratives behind references.

Current compatibility note: `bundle-size-baseline.json` currently supports
`policy.maxGrowthPercent`, and Gimle's baseline is set to `10`. Layered
migration must either set the effective policy to zero for migrated roles or
require an explicit `bundle-size-allowlist.json` entry with owner, reason, and
review date for any growth. Silent growth through the old default is not
allowed for migrated bundles.

This is a size rule, not a safety-removal rule. If a rule is mandatory and
large, first deduplicate or parameterize it. Do not delete it.

## Logic Preservation

Every current safety rule must get a stable marker before migration.

Examples:

```text
paperclip:heartbeat:idle-exit
paperclip:handoff:patch-status-assignee-comment
paperclip:handoff:get-verify
paperclip:handoff:formal-mention
paperclip:close:qa-evidence-required
paperclip:lock:409-release-path
paperclip:review:no-rubber-stamp
paperclip:merge:cto-only
paperclip:mcp:tool-contract-test
```

The migration validator must compare required markers per role/profile before
and after assembly. A bundle can shrink only if the mandatory marker remains and
the rule is still operationally clear.

## Build Flow

0. Verify preconditions:
   - submodules initialized;
   - current build passes;
   - current `validate_instructions.py` passes;
   - role sources, coverage matrix, baseline, and generated dist agree.
1. Read project manifest.
2. Resolve target and role list.
3. Load shared role template.
4. Expand shared includes.
5. Apply target overlay.
6. Apply project variable substitution.
7. Insert project overlay fragments.
8. Strip source-only metadata.
9. Emit generated bundle to compatibility output path for Slice 1.
10. Validate unresolved variables/includes.
11. Validate project leakage rules.
12. Validate mandatory logic markers.
13. Validate generated size budget.
14. Emit bundle manifest with hashes.

## Migration Plan

### Phase 0: Current Assembly Reconciliation

Before any layered builder implementation:

- Add an explicit submodule initialization requirement to build/validator docs:
  `git submodule update --init --recursive`.
- Make validator failure for an empty `paperclips/fragments/shared` actionable,
  not a long list of missing fragment errors.
- Reconcile `paperclips/roles/`, `paperclips/roles-codex/`,
  `paperclips/dist/`, `paperclips/dist/codex/`,
  `paperclips/instruction-coverage.matrix.yaml`, and
  `paperclips/bundle-size-baseline.json`.
- Resolve the current auditor drift: `claude:auditor` and
  `codex:cx-auditor` are real deployable Audit-V1 agents and must be present in
  coverage, baseline, generated output, deploy bindings, and resolved assembly
  metadata.
- Reconcile current Codex runtime validation conflicts without rewriting role
  semantics. Existing `superpowers:*` and `pr-review-toolkit:*` references must
  be classified as direct runtime capability, mapped equivalent, or explicit
  gap in the runtime capability map before any validator blocks or permits them.
- Run `python3 paperclips/scripts/validate_instructions.py --repo-root .` green
  before changing build semantics.
- Record the green baseline commit and generated bundle sizes.
- Add a live/generated comparison gate that can read current Paperclip
  `AGENTS.md` through the API, save it as a snapshot, and compare it with the
  generated bundle. Before deploy this is a reviewed old-live vs new-generated
  diff; after deploy it must be an exact live vs generated match.
- Add a Paperclip assembly CI job after instruction validation and
  capability-aware target validation are green:
  - `git submodule update --init --recursive`;
  - `python3 paperclips/scripts/build_project_compat.py --project gimle --inventory skip`;
  - `python3 paperclips/scripts/validate_instructions.py --repo-root .`;
  - `python3 paperclips/scripts/generate_assembly_inventory.py --check`;
  - `bash paperclips/validate-codex-target.sh`;
  - `python3 -m pytest paperclips/tests/test_validate_instructions.py`.

### Phase 1: Inventory And Marker Extraction

- List all Gimle role bundles first; UAudit and Medic inventories are later
  phases after Gimle compatibility is proven.
- Capture current generated size baselines.
- Extract mandatory safety rules into marker inventory.
- Identify project literals in shared fragments and role-prime files.
- Classify each literal as shared, target, or project-owned.
- Inventory existing shared-fragment project literals without requiring cleanup
  in this slice.
- Commit `paperclips/assembly-inventory.json` as generated metadata and enforce
  freshness with `paperclips/scripts/generate_assembly_inventory.py --check`.

### Phase 2: Parameter Schema

- Add manifest schema and sample manifests with placeholder values in
  `paperclip-shared-fragments`.
- Add project-local template files that show how to repeat a build for a new
  project without copying shared capability text into every generated agent.
- Add real Gimle manifest in the Gimle repo.
- Define standard variables for issue prefix, paths, required MCP set,
  codebase-memory projects, project capability additions, roles, and target
  names.
- Add validation for missing variables and unused variables.
- Define compatibility import rules for `codex-agent-ids.env` and current
  deploy name mappings.

### Phase 3: Builder Compatibility Mode

- Extend or replace current include-only builder with layered assembly.
- Preserve existing `paperclips/build.sh` behavior during compatibility mode.
- Add a manifest-driven compatibility builder that reads the Gimle project
  manifest, renders role sources directly, resolves target-specific fragments,
  substitutes manifest variables, and emits the same legacy output paths.
- Emit legacy paths for Gimle Slice 1.
- Add project/target output paths only behind an explicit future compatibility
  flag.
- Generate a bundle manifest with hashes and size stats.
- Do not change live deploy consumers in this phase.

### Phase 4: Gimle-Only Manifest Compatibility Slice

- Express current Gimle Claude and Codex teams through a Gimle manifest.
- Generate bundles equivalent to current outputs.
- Prove no generated bundle grew.
- Prove mandatory markers are present.
- Keep legacy output paths:
  - `paperclips/dist/*.md`;
  - `paperclips/dist/codex/*.md`.
- Keep current deploy mappings and deploy modes compatible.
- Do not deploy live agents in this slice.

### Phase 5: Deploy Dry-Run Compatibility Wrapper

- Add or adapt a deploy wrapper that supports:
  - `--dry-run`;
  - `--project <key>`;
  - `--target claude|codex`;
  - optional `--agent <role-key>`.
- Wrapper reads the resolved project manifest, including resolved role
  `agentName` and `agentId` fields.
- Claude dry-run must not copy files.
- Codex dry-run must not upload bundles.
- Existing deploy scripts remain available until consumer migration is complete.

### Phase 6: Gimle Deploy Migration

- Switch Gimle deploy scripts to manifest-driven deploy.
- Deploy only after generated output and dry-run behavior are reviewed.

### Phase 7: Shared Cleanup

- Replace project literals in `paperclip-shared-fragments` with variables or
  move them to project overlays.
- Keep rule text intact unless replaced by an equivalent marked rule plus
  background reference.
- Add a check that `paperclip-shared-fragments` has no forbidden project
  literals in generated-bundle inputs.

### Phase 8: UAudit Migration

- Add UAudit manifest and overlays.
- Generate AUCEO, CTO, Swift/Kotlin/Crypto/Security/Infra/QA/Research/Writer
  bundles from the same layered system.
- Verify UAudit bundles include the same handoff/assign/close rules as Gimle.
- Deploy only after generated bundles pass validation.

### Phase 9: Medic Migration

- Add Medic manifest and overlays.
- Generate Medic bundles from the same layered system.
- Verify Medic-specific MCP/tool gaps are represented as project overlay
  content, not shared literals.

## Affected Areas

- `paperclips/build.sh`
- `paperclips/deploy-agents.sh`
- `paperclips/deploy-codex-agents.sh`
- `paperclips/hire-codex-agents.sh`
- `paperclips/update-agent-workspaces.sh`
- `paperclips/validate-codex-target.sh`
- `paperclips/scripts/imac-agents-deploy.sh`
- `paperclips/scripts/generate_assembly_inventory.py`
- `paperclips/scripts/validate_instructions.py`
- `paperclips/tests/test_validate_instructions.py`
- `paperclips/assembly-inventory.json`
- `paperclips/scripts/audit-workflow-launcher.sh`
- `paperclips/fragments/shared/`
- `paperclips/fragments/local/`
- `paperclips/fragments/targets/`
- `paperclips/fragments/shared/targets/*/runtime-map.json`
- `paperclips/roles/`
- `paperclips/roles-codex/`
- `paperclips/instruction-coverage.matrix.yaml`
- `paperclips/bundle-size-baseline.json`
- `paperclips/bundle-size-allowlist.json`
- `paperclips/codex-agent-ids.env`
- watchdog and handoff detector consumers that assume role IDs, issue prefixes,
  output paths, or agent names
- proposed `paperclips/projects/`
- `paperclips/projects/README.md`
- `paperclips/projects/_template/paperclip-agent-assembly.yaml`
- validation scripts under `paperclips/scripts/`
- `paperclip-shared-fragments` repository

## Acceptance Criteria

### Phase 0 Acceptance

- Phase 0 reconciles current role, matrix, baseline, generated output, and
  submodule preconditions.
- Current `validate_instructions.py` is green before layered migration changes
  build semantics.
- Current Codex target validation is not made green by deleting or renaming real
  skills/subagents/plugins from role text. It must use a runtime capability map
  or remain a documented blocker until that map exists.
- `auditor` / `cx-auditor` are treated as deployable agents and reflected
  consistently in source roles, generated dist, coverage matrix, baseline, and
  deploy bindings.
- Paperclip assembly CI runs build, Codex build, instruction validation, Codex
  target validation, and validator tests.
- A local runtime comparison tool can compare generated bundles with deployed
  Paperclip `AGENTS.md` files without editing live agents.

### Slice 1 Acceptance

- A documented layer model exists and is reflected in Gimle build inputs.
- First implementation slice is Gimle-only and retains legacy output paths:
  `paperclips/dist/*.md` and `paperclips/dist/codex/*.md`.
- Gimle can declare a real project manifest in Slice 1.
- A reusable template manifest and README document the repeatable build cycle
  for Gimle, UAudit, Medic, and future projects.
- The repeatable build docs include a post-deploy generated-vs-runtime
  comparison step.
- The compare tooling reads role bindings from the resolved manifest and
  reports missing role IDs as `PENDING` instead of silently omitting them.
- The resolved Gimle capability manifest contains the common MCP contract:
  `codebase-memory`, `context7`, `serena`, `github`, and
  `sequential-thinking`.
- Project capability additions are additive in the resolved manifest; an empty
  Gimle additions list is valid, and later UAudit can add `neo4j` without
  changing shared role templates or every generated bundle.
- Generated bundles contain no unresolved variables or includes.
- Generated bundles contain all required safety markers for their profiles.
- Generated bundle size does not increase per agent or per project target.
- Existing shared-fragment project literals are inventoried; Slice 1 does not
  need to remove all of them.
- New manifest/overlay inputs do not introduce new shared-fragment project
  literals.
- `codex-agent-ids.env` and current deploy mappings are either imported as
  compatibility inputs or generated from the manifest; they are not independent
  authoritative sources.
- Resolved role entries include `agentName` and `agentId`; validators check the
  name/path relationship and UUID shape while allowing undeployed roles to stay
  pending.
- Validators reject stale resolved manifests when declared compatibility inputs
  such as `codex-agent-ids.env` or `deploy-agents.sh` change without rebuilding.
- No live deploy occurs in Slice 1.

### Future Acceptance

- Deploy tooling can dry-run by project, target, and agent.
- Deploy tooling refuses to deploy to agents outside the selected project.
- Project-specific literals are not present in shared generated-bundle inputs
  except in documented historical references or parameter examples.
- UAudit and Medic can each declare project manifests.
- Future UAudit generated bundles must use the same shared lifecycle logic as
  Gimle with only UAudit project values substituted.
- Existing live bundles are not modified until generated outputs are reviewed.

## Verification Plan

- Run `git submodule update --init --recursive` before validation in fresh
  worktrees.
- Run existing build for baseline and record size stats.
- Run current validator green before layered migration:
  `python3 paperclips/scripts/validate_instructions.py --repo-root .`.
- Verify assembly inventory freshness:
  `python3 paperclips/scripts/generate_assembly_inventory.py --check`.
- Verify auditor/cx-auditor role-set decision is reflected consistently in
  source roles, generated dist, coverage matrix, and baseline.
- Run layered build for Gimle in dry-run mode.
- Diff generated Gimle bundles against current bundles by section and marker.
- Run validator:
  - unresolved variables/includes;
  - forbidden shared literals;
  - required marker presence;
  - role/profile coverage;
  - size budget;
  - manifest agent IDs and target adapter expectations.
- Do not run deploy dry-run until the deploy wrapper phase.
- Do not run UAudit or Medic deploy in Slice 1.
- In later UAudit phase, review generated AUCEO/CTO/Infra bundles specifically
  for handoff, assign, blocked, and close behavior.

## Open Questions

- Should historical incident IDs such as `GIM-182` be parameterized, moved to
  lessons, or kept only in Gimle overlays?
- Is `palace.memory` a generic Paperclip MCP namespace or a Gimle product
  namespace that must be renamed/parameterized?
- Should the first layered builder be an extension of `paperclips/build.sh` or a
  new script called by `build.sh` in compatibility mode?
- What is the exact owner/review cadence for bundle-size allowlist exceptions?
