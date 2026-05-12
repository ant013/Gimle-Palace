# UAudit Codex Subagents Smoke

## Rev2 Decision

This slice is UAudit-specific. Do not install or depend on a generic public
marketplace roster at runtime.

UAudit owns the subagent definitions it uses. The iMac global Codex home may
host them, but the source of truth must live in this repository, be installed
idempotently, and be verified before any Paperclip audit run depends on them.

## Context

UAudit PR audit is moving from a multi-Paperclip-agent fan-out to a smaller
coordinator model:

- `UWISwiftAuditor` coordinates iOS PR audits.
- `UWAKotlinAuditor` coordinates Android PR audits.
- Each coordinator explicitly invokes four UAudit-owned Codex subagents for
  parallel static review, then aggregates their reports into one English audit
  report under `/Users/Shared/UnstoppableAudit/runs/UNS-<N>-audit/`.
- Infra agents keep ownership of final report delivery, but the coordinator
  must preserve the observable handoff contract that Infra already reads.

Server inventory on `imac-ssh.ant013.work` shows global Codex agents already
installed in `/Users/anton/.codex/agents`:

- `swift-expert`
- `kotlin-specialist`
- `security-auditor`
- `blockchain-developer`
- `penetration-tester`
- `code-reviewer`
- several `voltagent-*` aliases

These are useful references only. For this UAudit organization, production
audit flow must use UAudit-owned `uaudit-*` agents, not mutable upstream
marketplace definitions.

## UAudit Runtime Constants

- UAudit company ID:
  `8f55e80b-0264-4ab6-9d56-8b2652f18005`
- UAudit production root:
  `/Users/Shared/UnstoppableAudit`
- iMac shared Codex home:
  `/Users/anton/.codex`
- UAudit managed Codex home:
  `/Users/anton/.paperclip/instances/default/companies/8f55e80b-0264-4ab6-9d56-8b2652f18005/codex-home`
- iOS coordinator:
  `UWISwiftAuditor` / `a6e2aec6-08d9-43ab-8496-d24ce99ac0de`
- Android coordinator:
  `UWAKotlinAuditor` / `18f0ee3e-0fd9-40e7-a3b4-99a4ad3ab400`
- iOS infra:
  `UWIInfraEngineer` / `339e9d3f-48c0-4348-a8da-5337e6f29491`
- Android infra:
  `UWAInfraEngineer` / `5f0709f8-0b05-43e7-8711-6df618b95f69`

Any command that syncs or deploys UAudit must set and print:

```bash
PAPERCLIP_COMPANY_ID=8f55e80b-0264-4ab6-9d56-8b2652f18005
```

The command must fail if the resolved managed Codex home is not under that
company ID.

## Assumptions

- Codex custom agents are loaded from `~/.codex/agents/*.toml` and are visible
  to Paperclip-managed Codex homes through
  `paperclips/sync-codex-runtime-home.sh`.
- Project-scoped `.codex/agents` are not required for UAudit because Paperclip
  runs use managed Codex homes on iMac.
- Subagents must be explicitly invoked by coordinator instructions; Codex does
  not auto-spawn them.
- Audit subagents must be `sandbox_mode = "read-only"`, but read-only is not
  treated as the full security boundary.
- Only the coordinator writes run files. Subagents return structured findings
  to the coordinator and must not write into the run directory.

## Scope

Implement the UAudit incremental PR-audit coordinator model:

1. Add repo-owned UAudit Codex custom agent definitions:
   - `uaudit-swift-audit-specialist`
   - `uaudit-kotlin-audit-specialist`
   - `uaudit-bug-hunter`
   - `uaudit-security-auditor`
   - `uaudit-blockchain-auditor`
2. Make every `uaudit-*` agent `sandbox_mode = "read-only"`.
3. Add a mandatory idempotent installer that copies those repo-owned `.toml`
   files into `/Users/anton/.codex/agents`, records backups before overwrite,
   verifies expected SHA-256 hashes, and can restore the previous files.
4. Update runtime sync/verification so UAudit-required agents are checked in
   both shared and managed Codex homes for the UAudit company ID.
5. Update UAudit Codex overlays:
   - `UWISwiftAuditor` becomes the iOS PR-audit coordinator.
   - `UWAKotlinAuditor` becomes the Android PR-audit coordinator.
   - `UWICTO` and `UWACTO` route PR issues to the language coordinator instead
     of coordinating the full phase fan-out themselves.
   - Infra handoff remains observable-compatible with existing infra agents,
     or infra overlays must be updated in the same slice.
6. Update generated UAudit Codex bundles and deploy them through the
   project-aware UAudit deploy path.
7. Run positive and negative smoke tests on iMac proving both coordinators can
   invoke the required UAudit subagents and fail closed when a required subagent
   is missing or malformed.

## Out Of Scope

- Rewriting the full UAudit report-delivery flow.
- Restoring the previous full-repo audit/bughunt workflow.
- Adding QA/tester subagents; this workflow intentionally omits them.
- Running a full production PR audit as part of this slice.
- Depending on generic `reviewer` or mutable marketplace names in production
  UAudit smoke criteria.

## Affected Files And Areas

- new repo-owned UAudit subagent source directory, for example:
  `paperclips/projects/uaudit/codex-agents/*.toml`
- new mandatory installer/smoke helper under `paperclips/scripts/`
- `paperclips/sync-codex-runtime-home.sh`
- `paperclips/fragments/codex/skills-and-agents.md`
- `paperclips/projects/uaudit/paperclip-agent-assembly.yaml`
- `paperclips/projects/uaudit/compat/codex-agent-ids.env`
- `paperclips/projects/uaudit/overlays/codex/UWICTO.md`
- `paperclips/projects/uaudit/overlays/codex/UWACTO.md`
- new UAudit coordinator overlays:
  - `paperclips/projects/uaudit/overlays/codex/UWISwiftAuditor.md`
  - `paperclips/projects/uaudit/overlays/codex/UWAKotlinAuditor.md`
- existing infra overlays only if the coordinator cannot preserve current
  handoff semantics:
  - `paperclips/projects/uaudit/overlays/codex/UWIInfraEngineer.md`
  - `paperclips/projects/uaudit/overlays/codex/UWAInfraEngineer.md`
- generated bundles under `paperclips/dist/uaudit/codex/`

## Security Boundary

For UAudit subagents, `read-only` is necessary but insufficient. The
coordinator instructions and subagent `.toml` files must also enforce:

- allowed tools: static code reading, MCP code search, symbol lookup, and
  local file reads under the PR repository and prepared run artifacts only;
- forbidden reads:
  - `~/.paperclip/**`
  - `~/.codex/auth.json`
  - `~/.codex/sessions/**`
  - `~/.codex/history.jsonl`
  - `~/.ssh/**`
  - `.env`
  - any file named `auth.json`, `token`, `credentials`, or `secrets`;
- forbidden behavior:
  - reading or printing `PAPERCLIP_API_KEY`;
  - using deploy credentials;
  - writing files;
  - posting Paperclip comments;
  - sending full PR diffs to external network tools;
  - falling back to non-UAudit agents when a required `uaudit-*` agent is
    missing.

The smoke must include negative checks proving a `uaudit-*` subagent cannot
write, does not read forbidden secret paths, and reports blocked when a required
agent is unavailable.

## Coordinator Boundary

The Paperclip language auditors are coordinators, not language specialists:

| Coordinator | Owns | Does not own |
| --- | --- | --- |
| `UWISwiftAuditor` | iOS PR intake, run-state files, subagent invocation, aggregation, infra handoff | Deep Swift review as a solo reviewer |
| `UWAKotlinAuditor` | Android PR intake, run-state files, subagent invocation, aggregation, infra handoff | Deep Kotlin review as a solo reviewer |

Specialist subagents:

| Subagent | Responsibility | Non-goals |
| --- | --- | --- |
| `uaudit-swift-audit-specialist` | Swift/iOS correctness, concurrency, UIKit/SwiftUI lifecycle, memory, error handling | Security-only review, blockchain protocol semantics, writing files |
| `uaudit-kotlin-audit-specialist` | Kotlin/Android correctness, coroutines, Compose/lifecycle, nullability, variant-sensitive behavior | Security-only review, blockchain protocol semantics, writing files |
| `uaudit-bug-hunter` | Regression paths, crashes, state loss, edge cases, data corruption, user-visible broken flows | Style-only review, broad architecture essays |
| `uaudit-security-auditor` | Secrets, storage, auth, TLS, deeplinks/intents, WebView/WC/Web3 abuse, logging PII | Generic correctness unless security-relevant |
| `uaudit-blockchain-auditor` | Signing, transaction lifecycle, chain switching, approvals, nonce/replay, fees, confirmations | Generic mobile UI review |

Coordinator may override, merge, or downgrade a subagent finding only when it
keeps the original source attribution and records the reason.

## State Model

For issue `UNS-<N>`:

```text
/Users/Shared/UnstoppableAudit/runs/UNS-<N>-audit/
  pr.json
  pr.diff
  coordinator.md
  subagents/
    uaudit-swift-audit-specialist.json
    uaudit-kotlin-audit-specialist.json
    uaudit-bug-hunter.json
    uaudit-security-auditor.json
    uaudit-blockchain-auditor.json
  status/
    intake.done
    subagents.started
    subagents.done
    aggregate.done
    handoff.done
    blocked
  audit.md
  smoke/
    positive.json
    negative-missing-agent.json
    negative-malformed-output.json
    negative-readonly.json
```

Only the coordinator writes these files. Writes must be atomic:

- write to `*.tmp`;
- validate content;
- rename into place.

Duplicate wakes:

- if `status/aggregate.done` exists, the coordinator exits without changing
  files;
- if `status/subagents.started` exists but expected subagent output is missing,
  the coordinator resumes or marks blocked according to the retry policy.

Retry policy:

- one retry per subagent for transient invocation failure;
- malformed JSON or missing required fields after retry marks the run blocked;
- missing required subagent marks the run blocked, not degraded;
- a blocked run writes `status/blocked` with a one-line reason and comments a
  short blocked message without embedding audit content.

## PR Input Envelope

The coordinator may pass subagents only:

- the prepared `pr.diff` path;
- the prepared `pr.json` path;
- the relevant repository root;
- a narrow instruction prompt for that subagent role.

The coordinator must not pass:

- full Paperclip issue threads;
- API tokens or environment dumps;
- deploy logs;
- auth files;
- unrelated run directories;
- raw report content in Paperclip comments.

Smoke transcripts must not include full PR diff lines. They may include file
names, SHA values, agent names, status markers, and short synthetic snippets.

## Subagent Output Contract

Each subagent returns JSON:

```json
{
  "agent": "uaudit-swift-audit-specialist | uaudit-kotlin-audit-specialist | uaudit-bug-hunter | uaudit-security-auditor | uaudit-blockchain-auditor",
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

Aggregation rules:

- exact duplicate finding keys are `(file, line, title)`;
- duplicate findings keep all source-agent names;
- highest severity wins unless the coordinator downgrades with an explicit
  reason;
- conflicting findings are preserved as a conflict section rather than silently
  collapsed;
- final report keeps source attribution per finding.

The coordinator writes `$RUN/audit.md` and then hands off to the platform infra
agent for delivery.

## Handoff Contract

The coordinator must preserve Infra's current observable contract:

1. final report exists at `$RUN/audit.md`;
2. no audit bytes are posted into Paperclip comments;
3. coordinator posts a short handoff comment with issue number, platform, and
   path convention only;
4. coordinator PATCHes `assigneeAgentId` to:
   - iOS: `339e9d3f-48c0-4348-a8da-5337e6f29491`
   - Android: `5f0709f8-0b05-43e7-8711-6df618b95f69`
5. Infra computes its own hash and delivery payload.

If current infra overlays require CTO-originated wording or a different state
marker, this slice must update infra overlays rather than relying on implicit
compatibility.

## Build And Deploy Commands

Local/project build:

```bash
bash paperclips/build.sh --project uaudit --target codex
```

Project-aware dry run:

```bash
python3 paperclips/scripts/deploy_project_agents.py \
  --project uaudit \
  --target codex \
  --agent UWISwiftAuditor \
  --dry-run

python3 paperclips/scripts/deploy_project_agents.py \
  --project uaudit \
  --target codex \
  --agent UWAKotlinAuditor \
  --dry-run
```

Live deploy must use the project-aware UAudit path, not
`paperclips/deploy-codex-agents.sh`. The live command must set
`PAPERCLIP_COMPANY_ID=8f55e80b-0264-4ab6-9d56-8b2652f18005` and verify every
target agent has `adapterType = codex_local` before upload.

Rollout order:

1. install UAudit `uaudit-*` agent `.toml` files with backup;
2. sync UAudit managed Codex home and verify the expected roster;
3. build UAudit Codex bundles;
4. deploy only `UWISwiftAuditor` and `UWAKotlinAuditor`;
5. smoke both coordinators;
6. deploy CTO rerouting overlays;
7. smoke routing from CTO to coordinator;
8. leave Infra unchanged only if the handoff contract is verified.

Rollback:

- restore previous `~/.codex/agents/uaudit-*.toml` backups;
- restore previous deployed `UWISwiftAuditor` and `UWAKotlinAuditor` bundles;
- if CTO rerouting was deployed, restore previous `UWICTO` and `UWACTO`
  bundles;
- rerun project-aware compare/snapshot and stop.

## Acceptance Criteria

- Repo contains authoritative UAudit `uaudit-*` `.toml` definitions.
- Installer is idempotent and records/uses backups for rollback.
- Every `uaudit-*` agent is verified as `sandbox_mode = "read-only"`.
- iMac global Codex home contains exactly the expected UAudit agent roster.
- UAudit managed Codex home resolves that same roster under company
  `8f55e80b-0264-4ab6-9d56-8b2652f18005`.
- Runtime sync fails closed if the resolved company ID or managed Codex home is
  not UAudit.
- `bash paperclips/build.sh --project uaudit --target codex` renders UAudit
  bundles successfully.
- Project-aware dry run resolves `UWISwiftAuditor` and `UWAKotlinAuditor` to
  UAudit agent IDs and `paperclips/dist/uaudit/codex/*.md`.
- Live deploy uploads only after adapter preflight confirms `codex_local`.
- Post-deploy compare/snapshot shows generated SHA equals deployed SHA for the
  two coordinators before CTO rerouting is enabled.
- Positive iOS smoke proves `UWISwiftAuditor` invoked:
  - `uaudit-swift-audit-specialist`
  - `uaudit-bug-hunter`
  - `uaudit-security-auditor`
  - `uaudit-blockchain-auditor`
- Positive Android smoke proves `UWAKotlinAuditor` invoked:
  - `uaudit-kotlin-audit-specialist`
  - `uaudit-bug-hunter`
  - `uaudit-security-auditor`
  - `uaudit-blockchain-auditor`
- Negative smoke proves:
  - missing required subagent blocks the run;
  - malformed subagent JSON blocks the run;
  - `uaudit-*` subagents are read-only and do not read forbidden secret paths;
  - coordinator does not fall back to generic agents.
- Smoke evidence includes timestamp, host, company ID, Codex home path, agent
  roster, invoked agent names, coordinator status markers, and transcript
  excerpts without raw PR diff content or secrets.

## Verification Plan

1. Local repo checks:
   - `bash paperclips/build.sh --project uaudit --target codex`
   - project-aware dry run for both coordinators
   - UAudit-aware compare/snapshot if available, or add one in this slice
2. iMac runtime checks:
   - inspect `/Users/anton/.codex/agents`
   - install UAudit-owned `uaudit-*` agents with backup
   - run `paperclips/sync-codex-runtime-home.sh` with
     `PAPERCLIP_COMPANY_ID=8f55e80b-0264-4ab6-9d56-8b2652f18005`
   - inspect the UAudit managed Codex home agent symlink/list
3. Deploy:
   - run the project-aware UAudit deploy path for coordinators only
   - compare generated and deployed bundles
4. Smoke:
   - invoke `UWISwiftAuditor` with smoke-only synthetic PR metadata/diff
   - invoke `UWAKotlinAuditor` with smoke-only synthetic PR metadata/diff
   - run negative missing-agent, malformed-output, and read-only/secret-path
     checks
   - save smoke summaries under the UAudit run directory without full diff
     content or secrets
5. Enable routing:
   - deploy `UWICTO`/`UWACTO` rerouting only after coordinator smoke passes
   - smoke a CTO-to-coordinator handoff

## Open Questions

- Does `deploy_project_agents.py` already support API live deploy for UAudit
  Codex targets in the exact mode we need, or does this slice need to extend it?
- Does current Codex runtime expose enough structured evidence to prove exact
  subagent invocation names, or do coordinator prompts need to require explicit
  signed/structured confirmation from each subagent?
- Can secret-path negative checks be enforced by Codex sandbox configuration,
  or are they instruction-level checks only in the current runtime?
