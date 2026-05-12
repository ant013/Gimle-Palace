# UAudit Codex Subagents Smoke

## Context

UAudit PR audit is moving from a multi-Paperclip-agent fan-out to a smaller
coordinator model:

- `UWISwiftAuditor` coordinates iOS PR audits.
- `UWAKotlinAuditor` coordinates Android PR audits.
- Each coordinator explicitly spawns four Codex subagents for parallel static
  review, then aggregates their reports into one English audit report under
  `/Users/Shared/UnstoppableAudit/runs/UNS-<N>-audit/`.
- Infra agents keep ownership of final report delivery.

Server inventory on `imac-ssh.ant013.work` shows global Codex agents already
installed in `/Users/anton/.codex/agents`:

- `swift-expert`
- `kotlin-specialist`
- `security-auditor`
- `blockchain-developer`
- `penetration-tester`
- `code-reviewer`
- several `voltagent-*` aliases

Gaps found:

- No generic `reviewer` agent is installed globally.
- Existing language and blockchain agents are `workspace-write`; for audit
  subagent work we need read-only UAudit-specific variants.
- UAudit CTO overlays currently fan out to Paperclip phase agents
  (`UWISwiftAuditor` plus `UWISecurityAuditor`, and Android equivalents), not
  to Codex subagents inside the language auditor coordinator.
- The Codex runtime sync script checks an older expected agent set and does not
  verify UAudit audit subagents.

## Assumptions

- Global Codex custom agents are loaded from `~/.codex/agents/*.toml` and are
  visible to Paperclip-managed Codex homes through
  `paperclips/sync-codex-runtime-home.sh`.
- Project-scoped `.codex/agents` are not required for UAudit because Paperclip
  runs use managed Codex homes on iMac.
- Subagents must be explicitly requested by the coordinator instructions; Codex
  does not auto-spawn them.
- Audit subagents must be read-only. Only the coordinator writes temporary
  report files.
- Runtime smoke can be done with a minimal prompt that asks
  `UWISwiftAuditor` and `UWAKotlinAuditor` to spawn their configured subagents
  and collect confirmation, without requiring a real GitHub PR audit.

## Scope

Implement the UAudit incremental PR-audit coordinator model:

1. Add or install global Codex custom agents on iMac:
   - `uaudit-swift-auditor`
   - `uaudit-kotlin-auditor`
   - `uaudit-bug-hunter`
   - `uaudit-security-auditor`
   - `uaudit-blockchain-auditor`
   - `reviewer` if the base generic PR reviewer remains useful as fallback
2. Make all UAudit audit subagents `sandbox_mode = "read-only"`.
3. Update runtime sync/verification so UAudit-required agents are checked in
   both shared and managed Codex homes.
4. Update UAudit Codex overlays:
   - `UWISwiftAuditor` becomes the iOS PR-audit coordinator.
   - `UWAKotlinAuditor` becomes the Android PR-audit coordinator.
   - `UWICTO` and `UWACTO` route PR issues to the language coordinator instead
     of coordinating the full phase fan-out themselves.
   - Infra handoff remains unchanged.
5. Update generated UAudit Codex bundles and deploy them to Paperclip.
6. Run a smoke test on iMac proving both language coordinators can access and
   invoke the expected Codex subagents.

## Out Of Scope

- Rewriting the full UAudit report-delivery flow.
- Restoring the previous full-repo audit/bughunt workflow.
- Adding QA/tester subagents; this workflow intentionally omits them.
- Running a full production PR audit as part of this slice.

## Affected Files And Areas

- `paperclips/sync-codex-runtime-home.sh`
- `paperclips/fragments/codex/skills-and-agents.md`
- `paperclips/projects/uaudit/overlays/codex/UWICTO.md`
- `paperclips/projects/uaudit/overlays/codex/UWACTO.md`
- new UAudit overlays for:
  - `paperclips/projects/uaudit/overlays/codex/UWISwiftAuditor.md`
  - `paperclips/projects/uaudit/overlays/codex/UWAKotlinAuditor.md`
- generated bundles under `paperclips/dist/uaudit/codex/`
- optional installer/smoke helper under `paperclips/scripts/` if needed to make
  the global subagent setup repeatable.

## Coordinator Contract

Each coordinator receives a PR URL or prepared PR metadata/diff, then spawns
four read-only subagents:

For iOS:

- `uaudit-swift-auditor`
- `uaudit-bug-hunter`
- `uaudit-security-auditor`
- `uaudit-blockchain-auditor`

For Android:

- `uaudit-kotlin-auditor`
- `uaudit-bug-hunter`
- `uaudit-security-auditor`
- `uaudit-blockchain-auditor`

Each subagent returns:

```json
{
  "agent": "uaudit-swift-auditor | uaudit-kotlin-auditor | uaudit-bug-hunter | uaudit-security-auditor | uaudit-blockchain-auditor",
  "scope": "files and PR areas reviewed",
  "findings": [
    {
      "severity": "Critical | Block | Important | Observation",
      "confidence": "High | Medium | Low",
      "file": "path",
      "line": 123,
      "title": "one sentence",
      "evidence": "code-grounded evidence",
      "impact": "wallet/user/security impact",
      "recommendation": "minimal actionable fix",
      "false_positive_risk": "Low | Medium | High",
      "needs_runtime_verification": true
    }
  ],
  "no_finding_areas": ["areas explicitly checked with no issue"],
  "limitations": ["what static review could not verify"]
}
```

The coordinator deduplicates findings, ranks by severity and confidence, writes
the final English report to `$RUN/audit.md`, and hands off to the platform infra
agent for delivery.

## Acceptance Criteria

- iMac global Codex home contains all UAudit-required `.toml` agents.
- Paperclip-managed Codex home resolves those same agents through the runtime
  sync path.
- `paperclips/sync-codex-runtime-home.sh` reports no missing UAudit-required
  agents after sync.
- `paperclips/build.sh --target codex` renders UAudit bundles successfully.
- `paperclips/deploy-codex-agents.sh --api` uploads the updated UAudit bundles
  to Codex-local Paperclip agents.
- `UWISwiftAuditor` smoke confirms it can spawn or request all four iOS
  subagents and aggregate their confirmations.
- `UWAKotlinAuditor` smoke confirms it can spawn or request all four Android
  subagents and aggregate their confirmations.
- Smoke evidence includes:
  - timestamp
  - iMac host
  - Codex home path
  - available agent list
  - coordinator output showing subagent confirmations

## Verification Plan

1. Local repo checks:
   - `bash paperclips/build.sh --target codex`
   - any existing Paperclip validation command that covers UAudit generated
     bundles.
2. iMac runtime checks:
   - inspect `/Users/anton/.codex/agents`
   - run `paperclips/sync-codex-runtime-home.sh` for the UAudit company
   - inspect managed Codex home agent symlink/list
3. Deploy:
   - run UAudit Codex deploy through the existing API deploy path with
     `PAPERCLIP_API_KEY` set from the iMac environment.
4. Smoke:
   - assign or invoke `UWISwiftAuditor` with a smoke-only prompt requesting
     confirmation from the four iOS subagents.
   - assign or invoke `UWAKotlinAuditor` with the same Android-specific smoke.
   - save smoke transcripts under `/private/tmp` or the UAudit run directory
     and summarize the result back to the operator.

## Open Questions

- Should the global agent names be UAudit-specific only (`uaudit-*`), or should
  we also install the generic VoltAgent `reviewer` as a fallback?
- Should `blockchain-developer` remain installed as workspace-write globally,
  or should UAudit instructions always require the read-only
  `uaudit-blockchain-auditor` variant?
- Should CTO PR routing assign directly to `UWISwiftAuditor`/`UWAKotlinAuditor`,
  or should CTO perform a minimal intake before handoff?
