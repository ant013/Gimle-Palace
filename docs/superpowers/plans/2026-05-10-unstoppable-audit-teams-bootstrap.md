---
slug: unstoppable-audit-teams-bootstrap-plan
status: proposed
date: 2026-05-10
branch: feature/unstoppable-audit-teams-bootstrap-plan
related_spec_branch: feature/unstoppable-audit-teams-bootstrap-spec
related_spec_commit: a07abe5
related_spec: docs/superpowers/specs/2026-05-09-unstoppable-audit-teams-bootstrap.md
scope: docs-only implementation plan for Gate A/B and controlled Gate C handoff
---

# UnstoppableAudit Teams Bootstrap - Implementation Plan

This plan operationalizes the rev2 UnstoppableAudit bootstrap spec. The first
implementation slice is intentionally conservative: prove local prerequisites,
team config, dry-run manifests, validation, rollback/readback contracts, and
only then allow a separate live apply gate for the full team.

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

### Neo4j And Codebase-Memory Decision

Phase 1 does not use Neo4j as canonical audit finding storage.

- `codebase-memory` is used for per-repository code indexes and code search.
- Palace/Neo4j is allowed for existing code knowledge, extractor outputs, and
  project-scoped query context.
- Structured `AuditRun` / `AuditFinding` writes are skipped unless a concrete
  writer and schema exist before Gate D.
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
- Gate B team config and dry-run manifest.
- Team-aware validation for `UWI`, `UWA`, and umbrella `UA` roles.
- Rollback/readback manifest design.
- Audit-only Codex runtime profile.
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
   - retention TTL.
2. Add a prereq script that validates local-only state without API mutation:
   - required directories exist or can be created;
   - stable mirror root is writable by operator;
   - artifact root is owner-only or warns if not;
   - `paperclips/fragments/shared` is initialized;
   - `./paperclips/build.sh --target codex` is runnable;
   - `./paperclips/validate-codex-target.sh` is runnable;
   - `codebase-memory` has iOS index or returns a clear missing-index result;
   - Android indexability is checked and recorded as pass or bootstrap gap.
3. Record Gate A outputs in a local manifest:
   - `paperclips/manifests/unstoppable-audit/gate-a-prereq.json`
   - no raw tokens;
   - no full report text.

Acceptance:

- Gate A manifest exists.
- Missing Android index is represented as a known gap, not hidden.
- No Paperclip hire/update/bundle upload has occurred.

## Phase 2 - Gate B Team Config And Dry-Run Manifest

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
2. Define the audit-only runtime profile:
   - `adapterType = codex_local`;
   - `instructionsBundleMode = managed`;
   - `instructionsFilePath = AGENTS.md`;
   - sandbox bypass false by default;
   - no GitHub write token;
   - no bootstrap-admin or deploy-update credential in agent env;
   - writable roots limited to issue artifact/scratch roots;
   - product repo roots read-only by policy.
3. Render a dry-run manifest for every planned agent:
   - name/title/role;
   - reports-to;
   - model and reasoning effort;
   - runtime env variable names only;
   - workspace path;
   - writable roots;
   - source issue if used;
   - target agent-id file;
   - planned API operation: `create`, `update`, `skip`, or `refuse`.
4. Treat existing `AUCEO` as a manifest-managed object:
   - if readback matches target config, mark `skip`;
   - if safe to update, mark `update`;
   - if conflicting and unsafe, mark `refuse`.

Acceptance:

- Dry-run is deterministic.
- Dry-run can run without `PAPERCLIP_API_KEY`, but live readback fields are
  marked unchecked.
- With API key, dry-run includes current `AUCEO` readback.
- No live mutation happens in dry-run mode.

## Phase 3 - Validation And Contamination Checks

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

Acceptance:

- Validator fails on known-bad fixture config.
- Validator passes the intended team config.
- Existing Gimle/CX deploy scripts are not used with hidden defaults.

## Phase 4 - Rollback And Readback Contract

Owner: deployment tooling owner.

Affected paths:

- `paperclips/scripts/unstoppable-audit-apply.py`
- `paperclips/manifests/unstoppable-audit/rollback-*.json`
- `paperclips/manifests/unstoppable-audit/readback-*.json`

Implementation tasks:

1. Implement pre-change capture for existing agents before any live `POST` or
   `PUT`.
2. Write rollback manifest before live mutation.
3. After each create/update, read back:
   - adapter type;
   - model;
   - reasoning effort;
   - instructions bundle mode/path;
   - sandbox bypass;
   - runtime env key names;
   - workspace and writable roots.
4. Fail if readback diverges from manifest.
5. Write team-scoped agent ID files only after readback passes.

Acceptance:

- Apply refuses to run without a fresh dry-run manifest.
- Apply refuses to overwrite Gimle/CX/TG agent ID files.
- Rollback manifest exists before the first live mutation.

## Phase 5 - Gate C Full-Team Live Apply

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
5. Smoke must prove each tested agent can state:
   - its team and role;
   - one-issue handoff rules;
   - audit-only restrictions;
   - codebase-memory/Serena usage;
   - Telegram redacted-file delivery policy.

Acceptance:

- No final acceptance is based on the earlier failed `AUCEO` run.
- Every live agent readback matches manifest.
- Team smoke passes only after full-team bootstrap.

## Phase 6 - Gate D Handoff Stub

Owner: future baseline audit operator/team.

This plan does not execute baseline audits. It defines the handoff inputs:

- iOS and Android stable mirror SHAs;
- indexability evidence;
- full internal report path pattern;
- redacted Telegram artifact path pattern;
- evidence manifest path pattern;
- degraded-scope waiver format;
- Telegram delivery proof fields.

Acceptance:

- Gate D cannot start until Gate C smoke passes.
- Neo4j audit finding storage is either skipped with reason or implemented by a
  separate approved writer/schema slice.

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
```

Future operator/API checks:

```bash
paperclips/scripts/unstoppable-audit-prereq.sh
paperclips/scripts/unstoppable-audit-team.py dry-run --team all
paperclips/scripts/validate_unstoppable_audit.py --manifest <dry-run.json>
paperclips/scripts/unstoppable-audit-apply.py apply --manifest <dry-run.json>
```

## Open Risks

- Android repository is not currently visible as a separate `codebase-memory`
  project in the known index list.
- The rev2 spec is on a separate branch at the time this plan is written; merge
  order should preserve the spec before or alongside this plan.
- Telegram plugin currently allows only previous Gimle/TelegramUpdate chat IDs;
  Gate A must update plugin config or prove the delivery path can target
  `UAudit` and `UAudit Ops`.
- Existing `AUCEO` is paused and had an early failed run; Gate C must update or
  recreate it under the final manifest rather than treating it as accepted.
