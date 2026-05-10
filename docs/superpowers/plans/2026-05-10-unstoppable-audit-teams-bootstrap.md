---
slug: unstoppable-audit-teams-bootstrap-plan
status: proposed
date: 2026-05-10
branch: feature/unstoppable-audit-teams-bootstrap-plan
related_spec_branch: feature/unstoppable-audit-teams-bootstrap-spec
related_spec_commit: a07abe5
related_spec: docs/superpowers/specs/2026-05-09-unstoppable-audit-teams-bootstrap.md
scope: docs-only implementation plan for Gate A/B and controlled Gate C handoff
review_state: rev2 after architecture/security/devops/qa review
---

# UnstoppableAudit Teams Bootstrap - Implementation Plan

This plan operationalizes the rev2 UnstoppableAudit bootstrap spec. The first
implementation slice is intentionally conservative: prove local prerequisites,
team config, dry-run manifests, validation, rollback/readback contracts, and
only then allow a separate live apply gate for the full team.

## Rev2 Review Resolution

Four independent review tracks rejected the initial plan as too narrative for
Gate C/D. This rev2 converts the review findings into hard gates:

- Gate B is split into unauthenticated render and authenticated preflight.
- Gate A must capture exact repo SHAs and enforce owner-only artifact roots.
- Audit-only filesystem restrictions must be enforceable, not only policy text.
- Codex bundle generation must be team-scoped before `UWI`/`UWA` bundles exist.
- Telegram routing must be read back and smoke-tested before delivery gates.
- Live apply must stop on first failure and have tested partial rollback.
- Gate C smoke must prove behavior through Paperclip issues, not only prompt
  recall.
- Gate D must require schema validators for evidence manifests and reports.

## Current Decisions And Inputs

### Repository Inputs

- iOS repo: `https://github.com/horizontalsystems/unstoppable-wallet-ios`
- Android repo: `https://github.com/horizontalsystems/unstoppable-wallet-android`

### Paperclip Inputs

- Company: `UnstoppableAudit`
- Company ID: `8f55e80b-0264-4ab6-9d56-8b2652f18005`
- Current onboarding project ID: `64871690-2f2d-4fbd-a30d-975e6bbccec9`
- Current early CEO agent: `AUCEO`
- Current early CEO agent ID: `dcdd8871-5b44-4563-bb00-f8cca292a69e`
- Current early CEO adapter: `codex_local`
- Current early CEO status at discovery time: `paused`

The early `AUCEO` run produced a recovery issue. Treat that run as diagnostic
input only. The acceptance smoke happens after the full team is hired or
updated with the final UnstoppableAudit rules.

### Telegram Inputs

- Redacted report delivery group: `UAudit`
- Redacted report delivery chat ID: `-1003937871684`
- Ops group: `UAudit Ops`
- Ops chat ID: `-1003534905521`

Phase 1 uses Telegram only for redacted delivery artifacts and ops signals.
Telegram is not canonical storage.

The current Telegram plugin config still routes old Gimle/TelegramUpdate chats.
Gate A must update or create an audit-specific plugin route/profile, read it
back, restart the worker if required by plugin behavior, and prove the two chat
IDs above are explicitly allowlisted before any delivery smoke.

### Neo4j And Codebase-Memory Decision

Phase 1 does not use Neo4j as canonical audit finding storage.

- `codebase-memory` is used for per-repository code indexes and code search.
- Palace/Neo4j is allowed for existing code knowledge, extractor outputs, and
  project-scoped query context.
- Structured `AuditRun` / `AuditFinding` writes are skipped unless a concrete
  writer and schema exist before Gate D.
- Any Unstoppable Palace/Neo4j read/write path added in phase 1 must require an
  explicit `project` / `group_id`; defaulting to `project/gimle` is refused for
  UnstoppableAudit tools.
- Full internal reports, redacted artifacts, evidence manifests, and Paperclip
  issue comments are canonical phase-1 storage.
- Sensitive audit findings must not be written to shared/global graph nodes.

Evidence manifests should record:

```json
{
  "neo4j_audit_run_id": "skipped",
  "neo4j_storage_reason": "structured AuditRun/AuditFinding writer not implemented in phase 1"
}
```

## Scope

### In Scope For This Plan

- Gate A prerequisite verifier.
- Gate A credential inventory and Telegram route readiness.
- Gate B team config and dry-run manifest.
- Gate B authenticated Paperclip readback before live apply.
- Team-scoped Codex bundle substrate decision.
- Team-aware validation for `UWI`, `UWA`, and umbrella `UA` roles.
- Rollback/readback manifest design.
- Audit-only Codex runtime profile.
- OS-enforced read-only source workspace layout or an approved equivalent.
- Full-team hire/update sequencing before smoke.
- Gate C handoff criteria for live apply.

### Out Of Scope For This Plan

- GitHub automation.
- Automated PR comments or required checks.
- Product repository writes.
- Full baseline audits.
- Telegram delivery implementation.
- Structured Neo4j audit finding persistence.

## Phase 0 - Review Gate

Owner: Board/operator + Codex.

1. Review this plan against rev2 spec commit `a07abe5`.
2. Confirm phase-1 Neo4j audit storage is skipped by default.
3. Confirm existing `AUCEO` is either updated in place or replaced by manifest
   policy during Gate C.
4. Confirm `UAudit` and `UAudit Ops` Telegram chat IDs above.
5. Confirm no live Paperclip mutation starts until Gate A and Gate B pass.
6. Confirm the team-bundle substrate choice:
   - preferred: parameterized renderer with team-scoped output directories; or
   - fallback: separate Unstoppable role tree with isolated roster fragments.
7. Confirm the audit-only filesystem enforcement layer:
   - preferred: OS-level read-only source workspace plus separate writable
     artifact/scratch path; or
   - fallback: documented Paperclip adapter writable-root enforcement if the
     live adapter schema supports it.

Acceptance:

- This docs-only plan is approved or amended.
- No code or live Paperclip config has changed from this branch.

## Phase 1 - Gate A Local Prerequisites

Owner: operator script plus infra role after team bootstrap.

Affected paths:

- `paperclips/teams/unstoppable-audit.yaml`
- `paperclips/scripts/unstoppable-audit-prereq.sh`
- `docs/superpowers/plans/2026-05-10-unstoppable-audit-teams-bootstrap.md`

Implementation tasks:

1. Add a team config skeleton with non-secret values:
   - company ID;
   - onboarding/project IDs;
   - repo URLs;
   - Telegram chat IDs;
   - model matrix;
   - stable mirror root;
   - ephemeral run root;
   - artifact root;
   - retention TTL;
   - codebase-memory indexing root policy.
2. Add a prereq script that validates local-only state without API mutation:
   - required directories exist or can be created;
   - stable mirror root is writable by operator;
   - artifact root is owner-only or the gate hard-fails unless an explicit
     waiver file is attached;
   - `paperclips/fragments/shared` is initialized;
   - `./paperclips/build.sh --target codex` is runnable;
   - `./paperclips/validate-codex-target.sh` is runnable;
   - `codebase-memory` has iOS index or returns a clear missing-index result;
   - Android indexability is checked and recorded as pass or blocker;
   - exact iOS and Android baseline SHAs are fetched and recorded;
   - ephemeral audit workspaces can be created from those exact SHAs;
   - product source paths are read-only from the audit-agent perspective;
   - writable artifact/scratch paths are separate from source paths.
3. Record Gate A outputs in a local manifest:
   - `paperclips/manifests/unstoppable-audit/gate-a-prereq.json`
   - no raw tokens;
   - no full report text.
4. Add a credential inventory manifest:
   - credential class;
   - owner;
   - storage backend or secret reference;
   - allowed consumers;
   - rotation trigger;
   - runtime exposure policy.
5. Add Telegram plugin readiness:
   - route/profile contains `UAudit` and `UAudit Ops`;
   - destination chat IDs are allowlisted;
   - inbound commands are disabled unless explicitly approved;
   - every send requires an explicit destination, not an implicit global
     default;
   - config readback and restart evidence are recorded;
   - previous plugin config is captured for rollback.

Acceptance:

- Gate A manifest exists.
- iOS and Android baseline SHAs are recorded, or Android is explicitly blocked
  before any Android role smoke.
- Missing Android index blocks Android Gate C unless a written degraded-scope
  waiver narrows the smoke/audit to iOS only.
- Artifact roots are owner-only or the gate fails.
- Telegram route readiness is proved or Gate D remains blocked.
- Credential inventory exists and contains no raw secret values.
- No Paperclip hire/update/bundle upload has occurred.

## Phase 2 - Gate B1 Team Config And Unauthenticated Render

Owner: Codex/Python or shell tooling owner.

Affected paths:

- `paperclips/teams/unstoppable-audit.yaml`
- `paperclips/scripts/unstoppable-audit-team.py` or equivalent shell entrypoint
- `paperclips/manifests/unstoppable-audit/*.json`
- `paperclips/tests/test_unstoppable_audit_team.py`

Implementation tasks:

1. Define a complete team roster:
   - `AUCEO` umbrella coordination role;
   - `UWICTO`, `UWISwiftAuditor`, `UWISecurityAuditor`,
     `UWICryptoAuditor`, `UWIInfraEngineer`, `UWIResearchAgent`,
     `UWIQAEngineer`, `UWITechnicalWriter`;
   - `UWACTO`, `UWAKotlinAuditor`, `UWASecurityAuditor`,
     `UWACryptoAuditor`, `UWAInfraEngineer`, `UWAResearchAgent`,
     `UWAQAEngineer`, `UWATechnicalWriter`.
2. Decide and implement the team-bundle substrate:
   - parameterized renderer with team-scoped output directories; or
   - separate Unstoppable role tree with isolated roster fragments.
3. Define the audit-only runtime profile:
   - `adapterType = codex_local`;
   - `instructionsBundleMode = managed`;
   - `instructionsFilePath = AGENTS.md`;
   - sandbox bypass false by default;
   - no GitHub write token;
   - no bootstrap-admin or deploy-update credential in agent env;
   - writable roots limited to issue artifact/scratch roots;
   - product repo roots read-only by policy.
4. Render an unauthenticated dry-run manifest for every planned agent:
   - name/title/role;
   - reports-to;
   - model and reasoning effort;
   - runtime env variable names only;
   - workspace path;
   - writable roots;
   - source issue if used;
   - target agent-id file;
   - planned API operation: `create`, `update`, `skip`, or `refuse`.
5. Default Unstoppable live apply to `create-only` until authenticated preflight
   proves an existing agent is safe to update.

Acceptance:

- Dry-run is deterministic.
- Dry-run can run without `PAPERCLIP_API_KEY`, but live readback fields are
  marked unchecked.
- No live mutation happens in dry-run mode.
- Generated bundles/configs are team-scoped and do not depend on CX/Gimle
  roster fragments as active team state.

## Phase 3 - Gate B2 Authenticated Preflight

Owner: operator plus deployment tooling owner.

Affected paths:

- `paperclips/scripts/unstoppable-audit-team.py`
- `paperclips/manifests/unstoppable-audit/preflight-*.json`
- `paperclips/tests/test_unstoppable_audit_team.py`

Implementation tasks:

1. Read back the live Paperclip state for every target agent name and ID.
2. Treat existing `AUCEO` as a manifest-managed object only after readback:
   - mark `skip` only on exact config hash match;
   - mark `update` only on exact `(company_id, project_id, agent_name,
     source_issue_id, config hash lineage)` match and with rollback snapshot;
   - mark `refuse` for conflicting, paused, failed, or unknown state unless
     operator explicitly chooses recreate.
3. Fail authenticated preflight if any readback field is unchecked:
   - adapter;
   - model and reasoning effort;
   - instructions path and bundle mode;
   - sandbox bypass;
   - env key names;
   - workspace path;
   - source read-only and artifact writable-root contract.
4. Add negative tests for:
   - stale dry-run manifest;
   - readback divergence;
   - unsafe `AUCEO` update;
   - runtime env containing bootstrap-admin or deploy-update credentials;
   - foreign Gimle/CX/TG agent ID overwrite.

Acceptance:

- Gate C is blocked until authenticated preflight passes.
- `AUCEO` has an evidence-backed `create`, `update`, `skip`, or `refuse`
  decision.
- No auto-detected local/API mutation mode is allowed for Unstoppable scripts.

## Phase 4 - Validation And Contamination Checks

Owner: QA/tooling owner.

Affected paths:

- `paperclips/scripts/validate_unstoppable_audit.py`
- `paperclips/tests/test_validate_unstoppable_audit.py`

Implementation tasks:

1. Reject unsafe runtime settings:
   - sandbox bypass true without explicit exception;
   - adapter not `codex_local`;
   - model not matching config;
   - mutable product repo as writable root;
   - admin/deploy credentials in runtime env;
   - instructions path not `AGENTS.md`.
2. Reject cross-team contamination:
   - active Gimle/CX/TG project scope;
   - CX/TG agent rosters as current team;
   - stale UUIDs from unrelated teams;
   - `UWI` references inside `UWA` role bundles except allowed comparison text;
   - `UWA` references inside `UWI` role bundles except allowed comparison text.
3. Require generated bundles to mention:
   - `codebase-memory`;
   - Serena;
   - Paperclip one-issue handoff;
   - audit-only runtime policy;
   - Telegram redacted artifact rules.
4. Add redaction lint for Telegram artifacts:
   - reject secrets, tokens, auth headers, private keys, seed phrases, local
     absolute paths, raw exploit payloads, full stack traces, and long diff
     excerpts;
   - fail closed before delivery.

Acceptance:

- Validator fails on known-bad fixture config.
- Validator passes the intended team config.
- Existing Gimle/CX deploy scripts are not used with hidden defaults.

## Phase 5 - Rollback And Readback Contract

Owner: deployment tooling owner.

Affected paths:

- `paperclips/scripts/unstoppable-audit-apply.py`
- `paperclips/manifests/unstoppable-audit/rollback-*.json`
- `paperclips/manifests/unstoppable-audit/readback-*.json`

Implementation tasks:

1. Implement pre-change capture for existing agents before any live `POST` or
   `PUT`.
2. Write rollback manifest before live mutation.
3. Apply must stop on the first mutation or readback error.
4. On partial failure, emit a machine-readable partial-state marker listing:
   - agents already mutated;
   - agents untouched;
   - rollback manifest ID;
   - failed operation and response summary.
5. Implement and test `rollback --manifest <id>`:
   - restores only mutated agents;
   - runs before any bundle deploy;
   - runs before team-scoped agent ID files are written.
6. After each create/update, read back:
   - adapter type;
   - model;
   - reasoning effort;
   - instructions bundle mode/path;
   - sandbox bypass;
   - runtime env key names;
   - workspace and writable roots.
7. Fail if readback diverges from manifest.
8. Write team-scoped agent ID files only after readback passes.

Acceptance:

- Apply refuses to run without a fresh dry-run manifest.
- Apply refuses to overwrite Gimle/CX/TG agent ID files.
- Rollback manifest exists before the first live mutation.
- Bundle upload is globally blocked until all agent config readbacks pass.

## Phase 6 - Gate C Full-Team Live Apply

Owner: operator with Board approval.

This phase is a handoff gate, not automatically approved by this plan.

Implementation tasks:

1. Hire or update the full team from the approved manifest.
2. Include `AUCEO` in the same manifest-managed process.
3. Deploy managed bundles only after all live agent configs pass readback.
4. Run smoke after the full team exists:
   - `AUCEO`;
   - `UWICTO`;
   - `UWACTO`;
   - at least one iOS specialist;
   - at least one Android specialist.
5. Prompt-recall smoke must prove each tested agent can state:
   - its team and role;
   - one-issue handoff rules;
   - audit-only restrictions;
   - codebase-memory/Serena usage;
   - Telegram redacted-file delivery policy.
6. Behavioral smoke must run through Paperclip issues:
   - one positive one-issue handoff smoke with reassignment and required
     handoff comment fields;
   - one blocker-path smoke proving child issue creation happens only with a
     concrete blocker reason and link;
   - zero child issues in the positive handoff smoke.
7. Filesystem smoke must prove:
   - reading source works;
   - writing to artifact/scratch root works;
   - attempted write to product source fails or is blocked by policy with
     recorded evidence.

Acceptance:

- No final acceptance is based on the earlier failed `AUCEO` run.
- Every live agent readback matches manifest.
- Team smoke passes only after full-team bootstrap.
- Gate C does not pass on prompt recall alone.
- If Android index/readiness is waived, Gate C scope is explicitly iOS-only and
  Android roles are not accepted as production-ready.

## Phase 7 - Gate D Baseline Delivery Readiness

Owner: future baseline audit operator/team.

This plan does not execute baseline audits. It defines the readiness checks that
must exist before baseline audits can be accepted:

- iOS and Android stable mirror SHAs;
- indexability evidence;
- full internal report path pattern;
- redacted Telegram artifact path pattern;
- evidence manifest path pattern;
- degraded-scope waiver format;
- Telegram delivery proof fields.
- evidence manifest schema validator;
- internal report quality validator;
- redacted artifact lint;
- Telegram delivery proof validator;
- one-issue handoff audit checker.

Acceptance:

- Gate D cannot start until Gate C smoke passes.
- Neo4j audit finding storage is either skipped with reason or implemented by a
  separate approved writer/schema slice.
- Gate D cannot pass until both iOS and Android reports, or an explicitly
  narrowed scope waiver, pass validators for:
  - report hashes;
  - provenance;
  - blind spots;
  - degraded-scope waivers;
  - storage outside Telegram;
  - Telegram message ID or fallback proof;
  - QA and approver identities.

## Verification Commands

Docs/plan branch:

```bash
git diff --check
git diff --name-only origin/develop...
```

Future implementation branch:

```bash
./paperclips/build.sh --target codex
./paperclips/validate-codex-target.sh
python -m pytest paperclips/tests/test_unstoppable_audit_team.py -v
python -m pytest paperclips/tests/test_validate_unstoppable_audit.py -v
python -m pytest paperclips/tests/test_unstoppable_audit_apply.py -v
python -m pytest paperclips/tests/test_unstoppable_audit_evidence.py -v
```

Future operator/API checks:

```bash
paperclips/scripts/unstoppable-audit-prereq.sh
paperclips/scripts/unstoppable-audit-team.py dry-run --team all
paperclips/scripts/unstoppable-audit-team.py preflight --team all
paperclips/scripts/validate_unstoppable_audit.py --manifest <dry-run.json>
paperclips/scripts/unstoppable-audit-apply.py apply --manifest <dry-run.json>
paperclips/scripts/unstoppable-audit-apply.py rollback --manifest <rollback.json>
```

## Open Risks

- The rev2 spec is on a separate branch at the time this plan is written; merge
  order should preserve the spec before or alongside this plan.
- Android repository is not currently visible as a separate `codebase-memory`
  project in the known index list. This is now a Gate C scope blocker, not only
  an informational risk.
- Telegram plugin currently allows only previous Gimle/TelegramUpdate chat IDs.
  This is now a Gate A dependency.
- Existing `AUCEO` is paused and had an early failed run. This is now handled by
  authenticated preflight and create-only/update rules.
- Paperclip Codex adapter writable-root support has not been verified. Gate A/B
  must either prove adapter support or use OS-level read-only source layout.
