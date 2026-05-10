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

## Non-Goals

- Rewriting Paperclip runtime behavior.
- Changing live agent records before the generated bundles validate.
- Removing existing safety rules to hit a size target.
- Replacing project technical instructions such as `AGENTS.md` or `CLAUDE.md`.
- Designing UAudit audit methodology in detail; UAudit-specific audit content
  belongs in the UAudit project overlay.

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

Owned by shared runtime definitions plus target-specific project choices.

Defines differences between target runtimes:

- Claude vs Codex instruction entry file;
- `CLAUDE.md` vs `AGENTS.md` wording;
- available tools, MCP servers, skills, and subagents;
- target-specific mention/agent naming conventions;
- target-specific deploy mode.

Target overlays must not contain product-specific repo paths, company IDs, or
issue prefixes. If a target needs a roster, it receives it from the project
manifest for that target.

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
  codex:
    instruction_entry_file: AGENTS.md
    deploy_mode: api

paths:
  primary_repo_root: /Users/Shared/Ios/Gimle-Palace
  project_rules_file: AGENTS.md

mcp:
  codebase_memory_projects:
    primary: repos-gimle

agents:
  - role_key: cto
    target: claude
    display_name: CTO
    agent_id: "..."
    icon: eye
    template: management/cto.md
    overlays:
      - delegation-map.md
      - verification-gates.md
  - role_key: cx-cto
    target: codex
    display_name: CXCTO
    agent_id: "..."
    icon: crown
    template: management/cto.md
    overlays:
      - delegation-map-codex.md
      - verification-gates.md
```

The manifest may include multiple repos and MCP indexes for projects such as
UAudit:

```yaml
paths:
  repos:
    ios: /Users/Shared/UnstoppableAudit/repos/ios/unstoppable-wallet-ios
    android: /Users/Shared/UnstoppableAudit/repos/android/unstoppable-wallet-android

mcp:
  codebase_memory_projects:
    ios: Users-Shared-UnstoppableAudit-repos-ios-unstoppable-wallet-ios
    android: Users-Shared-UnstoppableAudit-repos-android-unstoppable-wallet-android
```

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

Generated files are final instructions for one concrete agent:

```text
paperclips/dist/<project-key>/<target>/<agent>.md
```

Temporary compatibility paths may remain during migration:

```text
paperclips/dist/*.md
paperclips/dist/codex/*.md
```

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

Deploy tooling should not hard-code Gimle, Medic, or UAudit. It should read the
project manifest and upload/copy each generated bundle to the matching agent.

Required deploy behaviors:

- refuse upload to an agent whose live adapter type does not match the target;
- deploy only generated bundle content;
- verify at least one stable marker per target agent after deploy;
- support dry-run and single-agent deploy;
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

- each migrated generated bundle must be `<=` its baseline byte count unless a
  reviewer explicitly approves a documented exception;
- total generated size per project and target must be `<=` baseline;
- preferred outcome is smaller generated output by removing duplication and
  moving background narratives behind references.

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

1. Read project manifest.
2. Resolve target and role list.
3. Load shared role template.
4. Expand shared includes.
5. Apply target overlay.
6. Apply project variable substitution.
7. Insert project overlay fragments.
8. Strip source-only metadata.
9. Emit generated bundle.
10. Validate unresolved variables/includes.
11. Validate project leakage rules.
12. Validate mandatory logic markers.
13. Validate generated size budget.
14. Emit bundle manifest with hashes.

## Migration Plan

### Phase 1: Inventory

- List all Gimle, UAudit, and Medic role bundles.
- Capture current generated size baselines.
- Extract mandatory safety rules into marker inventory.
- Identify project literals in shared fragments and role-prime files.
- Classify each literal as shared, target, or project-owned.

### Phase 2: Parameter Schema

- Add manifest schema and examples for Gimle, UAudit, and Medic.
- Define standard variables for issue prefix, paths, MCP projects, roles, and
  target names.
- Add validation for missing variables and unused variables.

### Phase 3: Shared Cleanup

- Replace project literals in `paperclip-shared-fragments` with variables or
  move them to project overlays.
- Keep rule text intact unless replaced by an equivalent marked rule plus
  background reference.
- Add a check that `paperclip-shared-fragments` has no forbidden project
  literals.

### Phase 4: Builder

- Extend or replace current include-only builder with layered assembly.
- Preserve existing `paperclips/build.sh` behavior during compatibility mode.
- Add project/target output paths.
- Generate a bundle manifest with hashes and size stats.

### Phase 5: Gimle Migration

- Express current Gimle Claude and Codex teams through a Gimle manifest.
- Generate bundles equivalent to current outputs.
- Prove no generated bundle grew.
- Prove mandatory markers are present.
- Switch Gimle deploy scripts to manifest-driven deploy.

### Phase 6: UAudit Migration

- Add UAudit manifest and overlays.
- Generate AUCEO, CTO, Swift/Kotlin/Crypto/Security/Infra/QA/Research/Writer
  bundles from the same layered system.
- Verify UAudit bundles include the same handoff/assign/close rules as Gimle.
- Deploy only after generated bundles pass validation.

### Phase 7: Medic Migration

- Add Medic manifest and overlays.
- Generate Medic bundles from the same layered system.
- Verify Medic-specific MCP/tool gaps are represented as project overlay
  content, not shared literals.

## Affected Areas

- `paperclips/build.sh`
- `paperclips/deploy-agents.sh`
- `paperclips/deploy-codex-agents.sh`
- `paperclips/scripts/imac-agents-deploy.sh`
- `paperclips/fragments/shared/`
- `paperclips/fragments/local/`
- `paperclips/fragments/targets/`
- `paperclips/roles/`
- `paperclips/roles-codex/`
- proposed `paperclips/projects/`
- validation scripts under `paperclips/scripts/`
- `paperclip-shared-fragments` repository

## Acceptance Criteria

- A documented layer model exists and is reflected in build inputs.
- Project-specific literals are not present in shared fragments except in
  documented historical references or parameter examples.
- Gimle, UAudit, and Medic can each declare a project manifest.
- Generated bundles contain no unresolved variables or includes.
- Generated bundles contain all required safety markers for their profiles.
- Generated bundle size does not increase per agent or per project target.
- Deploy tooling can dry-run by project, target, and agent.
- Deploy tooling refuses to deploy to agents outside the selected project.
- UAudit generated bundles use the same shared lifecycle logic as Gimle with
  only UAudit project values substituted.
- Existing live bundles are not modified until generated outputs are reviewed.

## Verification Plan

- Run existing build for baseline and record size stats.
- Run layered build for Gimle in dry-run mode.
- Diff generated Gimle bundles against current bundles by section and marker.
- Run validator:
  - unresolved variables/includes;
  - forbidden shared literals;
  - required marker presence;
  - role/profile coverage;
  - size budget;
  - manifest agent IDs and target adapter expectations.
- Run deploy dry-run for Gimle.
- Run deploy dry-run for UAudit.
- Review generated AUCEO/CTO/Infra bundles specifically for handoff, assign,
  blocked, and close behavior.

## Open Questions

- Should generated output keep compatibility paths under `paperclips/dist/` and
  `paperclips/dist/codex/`, or move immediately to
  `paperclips/dist/<project>/<target>/`?
- Should historical incident IDs such as `GIM-182` be parameterized, moved to
  lessons, or kept only in Gimle overlays?
- Is `palace.memory` a generic Paperclip MCP namespace or a Gimle product
  namespace that must be renamed/parameterized?
- Should project manifests live only in each product repo, or should
  `paperclip-shared-fragments` also carry schema and sample manifests?
- What is the exact exception process if one bundle must grow to preserve a
  safety rule?
