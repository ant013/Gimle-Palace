---
slug: unstoppable-audit-teams-bootstrap
status: proposed (rev2)
branch: feature/unstoppable-audit-teams-bootstrap-spec
paperclip_issue: TBD
authoring_team: Board/Codex with voltAgents review
team: UnstoppableAudit
date: 2026-05-09
scope: docs-only spec gate
rev2_changes: |
  Addressed 4-agent review blockers before implementation approval:
  - added phased gates so live Paperclip mutations happen only after local
    repo/bootstrap/storage prerequisites pass;
  - added an execution-boundary matrix for clone/index/report/store/send work;
  - added an audit-only runtime profile and explicitly forbids carrying over
    the current CX hire profile with sandbox bypass;
  - split credentials into bootstrap-admin, deploy-update, runtime, Telegram,
    and future GitHub-signal classes;
  - changed Telegram delivery to a redacted delivery artifact, not the full
    internal report;
  - downgraded Neo4j/Palace writes to optional phase-1 structured storage unless
    a concrete writer/schema path exists before implementation;
  - added evidence manifest, report quality bar, one-issue handoff template,
    team-aware contamination validation, rollback/readback requirements, and
    manual PR rehearsal requirements.
---

# UnstoppableAudit Codex Teams Bootstrap

## 1. Goal

Create a safe, repeatable bootstrap path for two independent Codex audit teams:

- `UWI` for `unstoppable-wallet-ios`;
- `UWA` for `unstoppable-wallet-android`.

The first release is manual and audit-only. It must:

1. prepare local repository mirrors, ephemeral run workspaces, bootstrap
   prerequisites, and indexability checks before live Paperclip mutations;
2. create or configure Paperclip company/projects/agents from reviewable config,
   not by UI copy-paste;
3. deploy the teams from shared Gimle/CX instruction fragments plus
   Unstoppable-specific overrides;
4. create baseline knowledge for both repositories;
5. run a first shallow baseline audit for each repository;
6. store the full internal Markdown audit report in controlled local/Paperclip
   storage;
7. send only a redacted Markdown delivery artifact to a private Telegram
   destination through the Paperclip Telegram plugin file-send feature;
8. preserve an evidence manifest proving storage, redaction, and Telegram
   delivery.

GitHub automation is intentionally a later phase. The first release proves the
teams, local audit workflow, storage, and Telegram delivery by manually created
Paperclip issues.

## 2. Review Basis

This rev2 spec incorporates the original research plus four independent
voltAgents review tracks:

- architecture/feasibility review;
- security audit;
- DevOps/deployment review;
- QA/process review.

Reviewers agreed that the direction is sound, but rejected rev1 for
implementation approval because it left these contracts too soft:

- audit-only runtime enforcement;
- live hire/deploy dry-run, readback, and rollback behavior;
- credential boundaries;
- Telegram report redaction;
- storage evidence;
- one-issue handoff observability;
- manual PR rehearsal;
- phase ordering.

Confirmed local facts:

- The CX Codex bundle path already exists through
  `./paperclips/build.sh --target codex`.
- Codex bundle validation already exists through
  `./paperclips/validate-codex-target.sh`.
- Current Codex deploy and hire scripts are hardcoded to Gimle/CX names,
  agent-id files, workspace roots, and some model choices.
- Current `paperclips/hire-codex-agents.sh` sets
  `dangerouslyBypassApprovalsAndSandbox: true`; this profile is not acceptable
  for Unstoppable audit agents.
- Current GitHub signal code is not reusable for this feature as-is because it
  posts PR comments, keys off existing Paperclip branch conventions, asks for
  PR write permission, and checks out repository code before running a
  secret-bearing signal script.
- Current audit launcher tooling creates parent/child issues; UnstoppableAudit
  will not use that launcher for normal one-issue handoff.
- `codebase-memory` currently has an indexed iOS Unstoppable repository at
  `/Users/ant013/Ios/HorizontalSystems/unstoppable-wallet-ios`; Android was not
  visible in the current `codebase-memory` project list and must be treated as a
  bootstrap gap until verified.
- The local checkout used for spec authoring has uninitialized
  `paperclips/fragments/shared`; team bootstrap verification must explicitly
  initialize required submodules and install test dependencies.

## 3. Problem

We need a practical audit workflow for private Unstoppable Wallet review that:

- does not block GitHub PRs;
- does not publish sensitive audit detail in GitHub;
- does not expose full vulnerability reports to a low-trust chat channel;
- does not let audit agents mutate product repositories;
- can be repeated for iOS and Android without cross-team contamination.

The dangerous failure modes are:

- UI-created agents drifting from team rules;
- current CX runtime defaults giving audit agents too much authority;
- cross-team contamination with Gimle/TG/CX names, UUIDs, paths, or handoff
  rules;
- audit artifacts living only in Telegram;
- GitHub Actions running untrusted PR code with Paperclip secrets;
- accidental PR comments or required checks that block merge flow;
- mutable branch refs being audited instead of immutable commits;
- silent local bootstrap failures producing low-signal audit reports.

## 4. Phase Gates

Implementation approval is split into gates. A later implementation plan must
preserve this ordering.

### Gate A - Local Prerequisites

No live Paperclip agent creation or bundle upload is allowed until Gate A
passes.

Gate A proves:

- target repository remotes are known;
- local stable mirrors exist or can be cloned;
- shared fragment submodules are initialized;
- required Python/test dependencies for instruction validation are available;
- iOS and Android indexability is known;
- Telegram destination and report retention policy are configured;
- Paperclip company/project model is decided;
- model matrix is decided.

### Gate B - Team Bootstrap Substrate

Gate B creates the reviewable team config, dry-run manifests, validation,
readback, and rollback behavior.

Gate B does not run a baseline audit.

### Gate C - Live Agent Creation And Bundle Deployment

Gate C may create/hire and deploy agents only after Gate A and Gate B pass.

Gate C must capture pre-change state for rollback before any live `PUT` or hire
request.

### Gate D - Baseline Audit Delivery

Gate D runs the first shallow baseline audits, stores full reports, emits
redacted Telegram delivery artifacts, and attaches evidence manifests.

### Gate E - Manual PR Audit Rehearsal

Gate E proves a manual PR audit against a harmless disposable PR/sample,
including one negative-path rehearsal.

### Gate F - Future GitHub Signal

Gate F is a separate future spec/plan. It is not part of this implementation
approval.

## 5. Assumptions And Preconditions

- The target Paperclip deployment is `https://paperclip.ant013.work`.
- Preferred Paperclip model: one dedicated company named `UnstoppableAudit`
  with two projects:
  - `UnstoppableWallet-iOS`;
  - `UnstoppableWallet-Android`.
- If Paperclip company creation or permissions make that impractical, the
  fallback is one existing company with the same two projects and strict
  `UWI`/`UWA` prefixes. The fallback must be documented before Gate C.
- Both audit teams use the Codex local adapter.
- Model selection must be configurable per team/role. The implementation must
  not hardcode unavailable models such as `gpt-5.5`; the initial default should
  be a currently usable Codex model such as `gpt-5.3-codex-spark`, unless the
  operator explicitly changes it.
- Agents are audit-only. They may read prepared workspaces, produce reports,
  assign Paperclip issues, and request Telegram delivery through the approved
  plugin path. They must not push to Unstoppable repositories, merge PRs, change
  product code, or receive admin credentials.
- Telegram is an operator-approved delivery channel, but it is not treated as
  end-to-end encrypted or durable storage.
- GitHub automation is not part of the first implementation slice.

The following values must be present in the team config before any live hire or
deploy command can run:

- Paperclip company ID or explicit company-creation plan;
- Paperclip project IDs or explicit project-creation plan;
- canonical iOS repository URL;
- canonical Android repository URL;
- Telegram destination for redacted audit reports;
- optional separate Telegram ops destination;
- model matrix;
- stable mirror root;
- ephemeral run workspace root;
- local report/artifact root;
- workspace retention TTL.

## 6. Scope

### In Scope

- A full spec and later implementation plan for the UnstoppableAudit bootstrap.
- A generic/team-aware Codex team deployment path derived from the Gimle/CX
  path, covering:
  - team configuration;
  - agent names/titles/capabilities;
  - reports-to relationships;
  - workspace roots;
  - model/reasoning configuration;
  - agent-id files;
  - dry-run manifest;
  - hire/apply;
  - live readback;
  - rollback manifest;
  - bundle build/deploy;
  - validation.
- Two independent Codex audit teams:
  - `UWI*` agents for iOS;
  - `UWA*` agents for Android.
- Team bundles assembled from shared fragments and Unstoppable-specific local
  fragments.
- Handoff rules that keep work inside one Paperclip issue unless a real blocker
  requires a child issue.
- Local repository bootstrap and indexing for both target repos.
- Phase-1 durable storage in local/Paperclip artifacts.
- Optional Palace/Neo4j structured storage only if a concrete writer/schema path
  is implemented or already exists before Gate D.
- First shallow baseline audit for each repo.
- Manual PR audit rehearsal for later operator-created Paperclip issues.
- Security requirements for checkout, redaction, credentials, agent runtime, and
  future GitHub signal automation.

### Out Of Scope

- Implementing GitHub automation in the first slice.
- Adding required GitHub checks or blocking PR merges.
- Posting audit reports or summaries as GitHub PR comments.
- Reusing the current GitHub `paperclip-signal` workflow for Unstoppable.
- Reusing `paperclips/scripts/audit-workflow-launcher.sh` for normal
  Unstoppable handoff.
- Running full app builds, tests, or product code unless explicitly approved per
  audit issue.
- Writing code changes to `unstoppable-wallet-ios` or
  `unstoppable-wallet-android`.
- Creating automated remediation PRs.
- Treating Telegram as canonical audit storage.
- Building a general marketplace product for arbitrary companies in this first
  slice. The implementation should be generic enough to reuse, but acceptance is
  based on `UWI` and `UWA`.

## 7. Team Model

Each platform gets a separate team with the same role pattern and independent
handoff chain.

### iOS Team

- `UWICTO`: owns issue decomposition, scope, review gates, final decision, and
  Telegram delivery approval.
- `UWISwiftAuditor`: owns Swift/iOS code review and architecture risk analysis.
- `UWISecurityAuditor`: owns secrets, auth, network, privacy, and abuse-path
  review.
- `UWICryptoAuditor`: owns wallet, transaction, key-management, signature, and
  blockchain-domain review.
- `UWIInfraEngineer`: owns local checkout/indexing/tooling readiness, not app
  infrastructure changes.
- `UWIResearchAgent`: owns cited research and repo/domain context summaries.
- `UWIQAEngineer`: owns verification of the audit process, report evidence,
  redaction, and delivery smoke checks.
- `UWITechnicalWriter`: assembles final Markdown audit reports from reviewed
  inputs.

### Android Team

- `UWACTO`: owns issue decomposition, scope, review gates, final decision, and
  Telegram delivery approval.
- `UWAKotlinAuditor`: owns Kotlin/Android code review and architecture risk
  analysis.
- `UWASecurityAuditor`: owns secrets, auth, network, privacy, and abuse-path
  review.
- `UWACryptoAuditor`: owns wallet, transaction, key-management, signature, and
  blockchain-domain review.
- `UWAInfraEngineer`: owns local checkout/indexing/tooling readiness, not app
  infrastructure changes.
- `UWAResearchAgent`: owns cited research and repo/domain context summaries.
- `UWAQAEngineer`: owns verification of the audit process, report evidence,
  redaction, and delivery smoke checks.
- `UWATechnicalWriter`: assembles final Markdown audit reports from reviewed
  inputs.

### Agent Policy

- Only team CTOs may create new agents, and only after explicit operator
  approval.
- Agents may assign the same issue to the next team member when done.
- Agents must not create child issues for normal handoff. Child issues are
  allowed only for a real blocker, for example missing credentials, missing repo
  access, missing tool installation, or a decision that blocks the audit.
- Completion handoff fallback is the owning team CTO.
- Cross-team handoff is not allowed by default. iOS and Android teams may share
  summarized findings through the CTOs only.
- Every final report must include exact repo, commit SHA, audit type, date,
  authoring team, provenance, blind spots, and evidence limitations.

## 8. One-Issue Handoff Contract

UnstoppableAudit uses one issue per baseline audit or PR audit. Normal role
handoff must happen by comments and reassignment inside that issue.

The issue body must include this checklist before work starts:

```markdown
## Audit Issue Control

- Team: UWI | UWA
- Repo:
- Audit type: baseline | manual-pr
- Base SHA:
- Head SHA:
- Full internal report path:
- Redacted Telegram artifact path:
- Evidence manifest path:

## Handoff Plan

- [ ] 1. CTO scope approval -> Infra
- [ ] 2. Infra bootstrap/index evidence -> Research
- [ ] 3. Research repo/domain memo -> PlatformAuditor
- [ ] 4. Platform audit subreport -> SecurityAuditor
- [ ] 5. Security audit subreport -> CryptoAuditor
- [ ] 6. Crypto audit subreport -> TechnicalWriter
- [ ] 7. TechnicalWriter full/redacted reports -> QA
- [ ] 8. QA evidence/redaction/delivery verification -> CTO
- [ ] 9. CTO final approval, storage, Telegram delivery, close

## Child Issue Policy

No child issues unless blocker rule triggers.
```

Every handoff comment must include:

- `Handoff-Step: <number>`;
- `Completed-By: <agent>`;
- `Next-Assignee: <agent>`;
- `Artifacts: <paths/ids>`;
- `Blocker: none` or a concrete blocker reason.

Acceptance must verify that no child issues were created unless the issue
contains a blocker comment with the reason and child issue link.

## 9. Audit-Only Runtime Profile

The current CX hire/runtime profile must not be reused unchanged.

Every UnstoppableAudit agent must be created with a distinct audit runtime
profile:

- `adapterType`: `codex_local`;
- `instructionsBundleMode`: `managed`;
- sandbox/approvals: enabled unless a specific operator-approved exception is
  documented;
- `dangerouslyBypassApprovalsAndSandbox`: false for normal audit agents;
- no GitHub write token in normal runtime environment;
- no Paperclip bootstrap-admin or deploy-update credential in normal runtime
  environment;
- writable roots limited to:
  - the issue-specific report/artifact directory;
  - optional temporary scratch under the issue run directory;
  - no product repository root as a writable root;
- repository roots are read-only from the agent perspective;
- network/tool access is limited to the tools needed for Paperclip issue work,
  MCP/codebase-memory/Serena, local file reads, and Telegram plugin delivery
  request;
- shell commands that can mutate source repositories, push, merge, or modify
  remotes are out of policy for audit agents.

Live verification must read back each agent configuration and fail if:

- sandbox bypass is enabled without explicit exception;
- workspace points at a mutable product checkout as the primary writable root;
- admin credentials appear in runtime env;
- model differs from team config;
- instructions bundle path is not `AGENTS.md`;
- adapter is not `codex_local`.

## 10. Credential Model

Credentials must be separated by class.

| Credential class | Used by | Scope | Runtime exposure |
| --- | --- | --- | --- |
| `bootstrap-admin` | operator only | company/project creation and initial hires | never exposed to agents |
| `deploy-update` | operator deploy script | bundle upload/readback for listed agent IDs | never exposed to agents |
| `runtime-issue-docs` | audit agents | assign/comment/read needed Paperclip issues/docs only | allowed only if least-privilege |
| `telegram-delivery` | Telegram plugin/server | send redacted delivery artifacts to configured destination | not exposed to agents as raw token |
| `future-github-signal` | future GitHub workflow/gateway | metadata-only issue upsert/wake | not part of phase 1 |

The implementation plan must define storage location, rotation notes, and
operator setup steps for each credential class. Scripts must avoid printing
tokens, auth headers, full payloads, or raw reports.

## 11. Deployment Design

The implementation should extend existing Gimle/CX mechanics instead of
copy-pasting agent configuration in the UI.

Required team config:

- `paperclips/teams/unstoppable-audit.yaml` or equivalent;
- company/project IDs or creation plan;
- `UWI` and `UWA` prefixes;
- roles and display names;
- model defaults and per-role overrides;
- runtime control profile fields;
- workspace roots;
- reports-to relationships;
- Telegram delivery policy;
- repository URLs and local clone paths;
- credential class names, not raw secret values;
- rollback/readback output paths.

Required dry-run manifest:

- every planned agent name;
- role/title/capabilities;
- reports-to target;
- adapter type;
- model and reasoning effort;
- workspace path;
- writable roots;
- sandbox/approval posture;
- runtime env variable names;
- source issue ID if used;
- target team-scoped agent-id file;
- planned API operation: create, update, skip, or refuse.

Live apply must:

- refuse to run if dry-run manifest is absent or stale;
- capture pre-change state for every existing agent before update;
- write a rollback manifest before any live mutation;
- submit hires/updates through Paperclip API;
- read back live config after each mutation;
- fail if readback does not match the manifest;
- write a team-scoped agent-id file;
- refuse to overwrite Gimle/CX/TG agent IDs.

Bundle deploy must:

- build bundles for the selected team;
- validate bundles;
- preflight that live agents use `codex_local`;
- upload only selected team bundles;
- read back the uploaded bundle metadata/content hash when the API supports it;
- preserve previous bundle content for rollback.

Validation must be team-aware. It must fail if generated `UWI`/`UWA` bundles
contain:

- Gimle project names as active scope;
- TG plugin project names as active scope;
- CX agent rosters as the current team;
- agent IDs from another team;
- stale `UWI` references in `UWA` bundles or stale `UWA` references in `UWI`
  bundles;
- Claude/Opus-only runtime instructions.

Generated bundles must mention:

- `AGENTS.md`;
- `codex_local`;
- codebase-memory;
- Serena;
- Paperclip one-issue handoff;
- audit-only runtime policy;
- Telegram redacted artifact delivery rules.

## 12. Execution Boundary Matrix

| Activity | Owner | Runtime | Credentials | Writable roots | Sandbox bypass |
| --- | --- | --- | --- | --- | --- |
| Resolve team config | operator script | local shell | none or bootstrap-admin for readback | spec/config repo only | no |
| Clone/update stable mirrors | operator script | local shell | repo read credential if needed | stable mirror root | no |
| Create ephemeral run worktree | operator script or Infra under policy | local shell | repo read credential if needed | issue run root | no |
| Initialize submodules/test deps | operator script | local shell | none unless dependency fetch required | CX repo workspace | no |
| Build/validate bundles | operator script | local shell | none | CX repo dist paths | no |
| Hire/create agents | operator script | local shell | bootstrap-admin | team agent-id/manifest files | no |
| Deploy bundles | operator script | local shell | deploy-update | rollback/deploy manifests | no |
| Read source code for audit | agents | codex_local | runtime-issue-docs if needed | issue report/scratch only | no |
| Write full internal report | TechnicalWriter | codex_local | runtime-issue-docs if needed | issue artifact root | no |
| Redaction review | QA, CTO | codex_local | runtime-issue-docs if needed | issue artifact root | no |
| Send Telegram artifact | CTO via plugin path | Paperclip/plugin | telegram-delivery held by plugin/server | none for agent token | no |
| Write Paperclip docs/memories | CTO or TechnicalWriter | codex_local/API | runtime-issue-docs | Paperclip controlled store | no |
| Write Neo4j structured run | optional operator/service path | approved service | graph credential | graph only | no |
| Future GitHub signal | future workflow/gateway | GitHub or gateway | future-github-signal | none | no |

No activity in phase 1 may require product repository write access.

## 13. Workspace And Repository Bootstrap

Use stable mirrors plus ephemeral per-run workspaces.

Recommended roots:

- stable mirrors:
  - `/Users/Shared/UnstoppableAudit/repos/ios/unstoppable-wallet-ios.git`
  - `/Users/Shared/UnstoppableAudit/repos/android/unstoppable-wallet-android.git`
- ephemeral run workspaces:
  - `/Users/Shared/UnstoppableAudit/runs/<issue-id>/ios`
  - `/Users/Shared/UnstoppableAudit/runs/<issue-id>/android`
- report/artifact root:
  - `/Users/Shared/UnstoppableAudit/artifacts/<issue-id>/`

Stable mirrors are fetch-only. Audits do not run directly in the stable mirror.

Both baseline and PR audits must run from ephemeral worktrees or clones created
from the stable mirror and pinned to an immutable SHA.

Checkout requirements:

- no `git pull` inside an active audit run;
- fetch exact refs/SHAs through an operator-controlled script;
- detached HEAD for audit workspaces;
- Git hooks disabled;
- credential helpers disabled for run workspaces unless explicitly approved;
- submodule recursion disabled by default;
- LFS smudge disabled by default;
- `file://` protocol disabled unless explicitly approved;
- owner-only filesystem permissions for report and run directories;
- cleanup or archive according to configured TTL.

Baseline bootstrap:

1. clone/fetch each stable mirror;
2. record remote URL, default branch, and baseline commit SHA;
3. create issue-specific ephemeral workspace at that SHA;
4. index each repository in `codebase-memory`;
5. activate or create Serena project context for each repository if supported;
6. write a short repo map into Paperclip docs/memories;
7. create a phase-1 evidence manifest before audit starts.

If a repo cannot be indexed, the team may continue only with a degraded-scope
waiver in the issue and report. The waiver must identify the missing tool,
impact, and compensating manual review.

## 14. Knowledge Storage

Use a hybrid model, but phase 1 must stay implementable.

### Phase-1 Required Storage

Phase 1 requires:

- full internal Markdown report in a controlled local/Paperclip artifact;
- redacted Telegram Markdown artifact;
- evidence manifest;
- Paperclip issue comments recording handoff and storage paths/IDs;
- repo map and baseline SHA record.

### Optional Structured Storage

Palace/Neo4j structured audit storage is allowed in phase 1 only if a concrete
writer/schema path exists before Gate D.

If no writer/schema path exists, the implementation must:

- mark Neo4j structured storage as skipped in the evidence manifest;
- keep full report and evidence manifest as the phase-1 durable store;
- not claim that `AuditRun` or `AuditFinding` graph records were persisted.

Minimum future structured record shape:

- `AuditProject`
  - `project_key`;
  - `platform`;
  - `repo_url`;
  - `default_branch`;
  - `paperclip_project_id`.
- `AuditRun`
  - `run_id`;
  - `project_key`;
  - `audit_type`: `baseline` or `pr`;
  - `base_sha`;
  - `head_sha`;
  - `started_at`;
  - `finished_at`;
  - `paperclip_issue_id`;
  - `report_artifact_path`;
  - `telegram_message_id` when available.
- `AuditFinding`
  - deterministic finding ID;
  - severity;
  - category;
  - status;
  - evidence refs;
  - affected files/symbols;
  - first_seen_run_id;
  - last_seen_run_id.
- `PRAuditScope`
  - PR URL;
  - PR number;
  - base branch;
  - head branch;
  - base SHA;
  - head SHA;
  - changed paths;
  - dependency-impact notes.

## 15. Evidence Manifest

Every delivered report must have a machine-readable evidence manifest stored
outside Telegram.

Recommended filename:

- `UWI-baseline-audit-<short_sha>.evidence.json`
- `UWA-baseline-audit-<short_sha>.evidence.json`
- `UWI-pr-<pr_number>-<short_sha>.evidence.json`
- `UWA-pr-<pr_number>-<short_sha>.evidence.json`

Required fields:

```json
{
  "team": "UWI",
  "repo_url": "https://github.com/...",
  "audit_type": "baseline",
  "paperclip_issue_id": "...",
  "base_sha": "...",
  "head_sha": "...",
  "worktree_path": "...",
  "worktree_cleanup_policy": "...",
  "full_report_path": "...",
  "full_report_sha256": "...",
  "redacted_report_path": "...",
  "redacted_report_sha256": "...",
  "paperclip_doc_id": "... or skipped",
  "neo4j_audit_run_id": "... or skipped",
  "telegram_chat_id": "...",
  "telegram_message_id": "... or fallback-proof",
  "sender_agent": "UWICTO",
  "approver_agent": "UWICTO",
  "qa_agent": "UWIQAEngineer",
  "redaction_check": "passed",
  "provenance": ["..."],
  "blind_spots": ["..."],
  "created_at": "ISO-8601"
}
```

The manifest may store hashes and IDs instead of raw sensitive report text.

## 16. Telegram Delivery

Telegram is delivery-only and low-trust compared to controlled local/Paperclip
storage.

The full internal audit report must not be sent to Telegram by default.

Telegram receives a redacted delivery artifact that:

- removes secrets, tokens, auth headers, private keys, seed phrases, local
  absolute paths, raw exploit payloads, full stack traces, and full diff excerpts;
- summarizes sensitive findings without operational exploit detail;
- includes severity counts, finding IDs, affected areas, and next actions;
- includes a pointer to the controlled internal artifact ID/path, not the raw
  full report body;
- includes the report SHA256 from the evidence manifest when useful.

Redaction must be reviewed by QA and approved by CTO before send.

Telegram delivery proof must include:

- destination chat/channel ID;
- Telegram message ID when available;
- timestamp;
- artifact filename;
- artifact SHA256;
- sender;
- fallback screenshot/log only if the plugin/API cannot return message ID.

If Telegram delivery fails, the issue must stay open or blocked. The full
internal report and evidence manifest remain canonical.

## 17. Audit Workflows

### Baseline Audit

For each platform team:

1. CTO creates or accepts one baseline audit issue with the required handoff
   template.
2. Infra verifies stable mirror, ephemeral workspace, commit SHA, tools, MCP
   access, and `codebase-memory`/Serena status.
3. Research writes a repo/domain context memo with citations and blind spots.
4. Platform auditor reviews code structure, architecture boundaries, and risky
   areas visible from baseline analysis.
5. Security auditor reviews auth, secrets, privacy, network, storage, and
   abuse-path risks.
6. Crypto auditor reviews wallet, key, transaction, signing, address, chain,
   and fee-related areas.
7. TechnicalWriter assembles the full internal Markdown report and redacted
   Telegram artifact.
8. QA verifies evidence, provenance, blind spots, degraded-scope waivers,
   redaction, reproducibility, and Telegram file-send smoke.
9. CTO approves final artifacts, stores them, sends the redacted Markdown file
   to Telegram through the plugin, and attaches the evidence manifest.
10. CTO closes the issue only after storage and Telegram delivery evidence
    exist.

### Manual PR Audit Rehearsal

Until GitHub automation exists:

1. operator creates one Paperclip issue per PR audit;
2. issue title includes team prefix, repo, PR number, and short subject;
3. issue body includes PR URL, target branch, base SHA, head SHA, requested
   depth, and handoff template;
4. team fetches exact commits and audits the diff plus relevant dependency
   impact;
5. full report and redacted delivery artifact are stored and delivered;
6. no GitHub comments or status checks are created.

Gate E must include:

- one successful rehearsal against a disposable harmless sample;
- one negative-path rehearsal, such as stale head SHA, missing issue field, or
  force-pushed PR;
- proof of base/head SHA capture;
- exact fetched commit;
- chosen diff basis;
- worktree path;
- cleanup/archive result;
- proof that GitHub received no comments or status checks.

## 18. Report Format And Quality Bar

Baseline reports should be named:

- `UWI-baseline-audit-<short_sha>.internal.md`
- `UWA-baseline-audit-<short_sha>.internal.md`
- `UWI-baseline-audit-<short_sha>.telegram.md`
- `UWA-baseline-audit-<short_sha>.telegram.md`

Manual PR reports should be named:

- `UWI-pr-<pr_number>-<short_sha>.internal.md`
- `UWA-pr-<pr_number>-<short_sha>.internal.md`
- `UWI-pr-<pr_number>-<short_sha>.telegram.md`
- `UWA-pr-<pr_number>-<short_sha>.telegram.md`

Minimum internal report sections:

- title;
- repo and exact commit(s);
- audit type and scope;
- executive summary;
- repo map;
- tool/indexing status;
- provenance;
- blind spots;
- degraded-scope waivers;
- severity summary;
- critical/high/medium/low findings;
- evidence and file references;
- limitations;
- follow-up recommendations;
- storage and Telegram delivery evidence.

Each finding must include:

- deterministic finding ID;
- severity;
- affected file/symbol when known;
- concrete evidence;
- impact;
- recommendation;
- confidence;
- whether it is new, known, or needs manual confirmation.

A report with no provenance and no blind spots cannot pass QA.

## 19. Security Requirements

- Audit teams are read-only for Unstoppable repositories.
- Normal audit agents must not run with sandbox bypass.
- GitHub Actions must be metadata/signal-only when automation is added.
- No GitHub Action may checkout untrusted PR code while Paperclip secrets are
  available.
- Local audits must fetch immutable commit SHAs, not mutable branch refs.
- Git hooks must not run during audit checkout.
- Submodules and LFS smudge must be disabled by default unless explicitly
  needed and approved for a specific repo.
- Audit workspaces must be isolated per run and cleaned up or retained under a
  documented retention policy.
- Audit logs must not print raw reports, secrets, tokens, auth headers, or full
  payloads.
- Telegram artifacts must be redacted and approved before send.
- Bootstrap-admin, deploy-update, runtime, Telegram, and future GitHub signal
  credentials must be separated.
- The Telegram bot token and Paperclip signal key must be separate secrets.
- Failure to deliver to Telegram must not lose the report; the stored full
  report and evidence manifest are canonical.

## 20. Acceptance Criteria

### Gate A - Local Prerequisites

- Required submodules are initialized.
- Required test dependencies are installed or a pinned setup command exists.
- iOS and Android repo remotes are configured.
- Stable mirror root and ephemeral run root exist.
- iOS and Android indexability is known.
- Telegram destination is configured.
- Company/project model is decided.
- Model matrix is decided.
- Retention TTL is decided.

### Gate B - Team Bootstrap Substrate

- A repeatable team config exists for `UWI` and `UWA`.
- Team creation can render a complete dry-run manifest before API execution.
- Dry-run manifest includes sandbox/approval posture and credential classes.
- Validation is team-aware and rejects cross-team contamination.
- Rollback manifest format exists.
- Current CX/Gimle scripts are not used with hidden defaults for live
  Unstoppable creation.

### Gate C - Live Agent Creation And Bundle Deployment

- Agents are deployed through scripts/API, not hand-edited in UI.
- Live config readback matches the dry-run manifest.
- Every live audit agent uses `codex_local`.
- Every live audit agent has sandbox bypass disabled unless explicitly approved.
- No admin credential is present in agent runtime env.
- Generated bundles pass Codex validation.
- Bundle validation rejects stale Gimle/TG/CX active-scope contamination.
- Smoke coverage includes CTO plus at least one specialist role per team.
- Agents can report their team, project, handoff rules, MCP access, runtime
  restrictions, and Telegram redacted-file protocol.

### Gate D - Baseline Audit Delivery

- iOS and Android repositories have separate stable mirrors and ephemeral run
  workspaces.
- Both repositories have recorded baseline SHAs.
- Both repositories are indexed or have explicit structured skip/degraded-scope
  reasons.
- A shallow baseline internal audit report exists for iOS.
- A shallow baseline internal audit report exists for Android.
- Both internal reports include provenance and blind spots.
- Both redacted Telegram artifacts exist.
- Both evidence manifests exist.
- Both baseline reports are stored outside Telegram.
- Both redacted artifacts are delivered to the configured private Telegram
  destination as Markdown files.

### Gate E - Manual PR Rehearsal

- Manual PR audit instructions are documented.
- One successful harmless sample PR audit rehearsal passes.
- One negative-path rehearsal rejects stale/missing PR metadata before audit.
- Rehearsal proves exact SHA checkout and worktree cleanup/archive.
- Rehearsal proves no GitHub PR comments, required checks, or merge-blocking
  behavior are added.

## 21. Verification Plan

Spec verification:

- `git diff --check`
- confirm only docs/spec files changed in the spec commit.

Implementation verification:

- initialize required submodules;
- install or verify required test dependencies;
- run instruction validation tests after prerequisites are present;
- `./paperclips/build.sh --target codex`
- `./paperclips/validate-codex-target.sh`
- team factory dry-run for `UWI`;
- team factory dry-run for `UWA`;
- inspect dry-run manifests;
- repo mirror/bootstrap preflight for iOS;
- repo mirror/bootstrap preflight for Android;
- `codebase-memory` index status for iOS;
- `codebase-memory` index status for Android;
- Serena activation check for iOS;
- Serena activation check for Android;
- deploy dry-run for `UWI`;
- deploy dry-run for `UWA`;
- live API readback after any create/update;
- smoke issue for `UWICTO`;
- smoke issue for `UWACTO`;
- smoke issue for at least one specialist role per team;
- grep generated bundles for stale active-scope references:
  - `Gimle`;
  - `Telegram Plugin Fork`;
  - `TGCTO`;
  - `CXCTO`;
  - old UUIDs from unrelated teams;
- harmless Telegram file-send smoke with a non-sensitive redacted Markdown file;
- baseline audit delivery proof for both teams;
- evidence manifest verification for both teams;
- manual PR positive rehearsal;
- manual PR negative rehearsal.

## 22. Future GitHub Signal Contract

Future GitHub signal automation is a separate gate and must not be implemented
under this spec.

Required future design:

- direct `pull_request_target` workflow restricted to PRs targeting
  `version/**`, unless a later spec rejects this with reasons;
- no `actions/checkout`;
- no repo-sourced dependency install;
- no PR comments;
- no required status check;
- minimal permissions, ideally `contents: read` plus no write scopes unless a
  later spec proves need;
- metadata-only payload:
  - repo;
  - PR number;
  - base branch;
  - base SHA;
  - head SHA;
  - title;
  - author;
  - event type;
- dedicated future GitHub signal key;
- Paperclip-side idempotency/upsert key:
  `audit:<repo_full_name>:pr:<number>`;
- live branch-protection check for `version/**` before enabling.

The current `.github/workflows/paperclip-signal.yml` and
`.github/scripts/paperclip_signal.py` are explicitly non-reusable for
Unstoppable without a separate redesign.

## 23. Implementation Sequence

This is not implementation approval; it is the expected plan shape after rev2
review.

1. Write the implementation plan with explicit phase gates and one-issue
   handoff order.
2. Resolve Gate A config values.
3. Prepare local bootstrap prerequisites: submodules, deps, stable mirrors,
   artifact roots, and indexability checks.
4. Add the team config and dry-run manifest generator.
5. Add team-aware validation and contamination checks.
6. Add safe hire/deploy apply path with readback and rollback manifest.
7. Add Unstoppable-specific Codex role bundles/fragments.
8. Build and validate bundles.
9. Create/hire agents through Paperclip API only after Gate A/B pass.
10. Deploy bundles through API with readback.
11. Run agent smoke tests.
12. Create baseline issue for iOS and execute one-issue handoff.
13. Create baseline issue for Android and execute one-issue handoff.
14. Store full internal reports, redacted artifacts, and evidence manifests.
15. Deliver redacted Markdown files through Telegram.
16. Run QA verification.
17. Run manual PR positive and negative rehearsals.
18. CTO closes issues only after storage, evidence, and Telegram delivery proof
    exist.

## 24. Remaining Operator Inputs Before Live Work

These are not design blockers, but they are preconditions for Gate C:

- exact iOS repo remote URL;
- exact Android repo remote URL;
- Paperclip company/project IDs or approval to create them;
- Telegram redacted-report destination ID;
- optional Telegram ops destination ID;
- final model matrix;
- workspace retention TTL;
- whether phase-1 Neo4j structured writes are required or explicitly skipped.

