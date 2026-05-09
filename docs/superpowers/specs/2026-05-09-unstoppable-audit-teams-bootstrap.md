---
slug: unstoppable-audit-teams-bootstrap
status: proposed
branch: feature/unstoppable-audit-teams-bootstrap-spec
paperclip_issue: TBD
authoring_team: Board/Codex with voltAgents research
team: UnstoppableAudit
date: 2026-05-09
scope: docs-only spec gate
---

# UnstoppableAudit Codex Teams Bootstrap

## 1. Goal

Create a safe, repeatable bootstrap path for two independent Codex audit teams:

- `UWI` for `unstoppable-wallet-ios`;
- `UWA` for `unstoppable-wallet-android`.

The first release is manual and audit-only:

1. create the Paperclip company/projects/agents;
2. deploy the teams from shared Gimle/CX instruction fragments, not by UI copy-paste;
3. clone and index both repositories locally;
4. create baseline knowledge for both repositories;
5. run a first shallow baseline audit for each repository;
6. send final Markdown audit files to a private Telegram group through the
   Paperclip Telegram plugin file-send feature;
7. store the audit knowledge in local durable stores so Telegram is delivery
   only, not the archive.

GitHub automation is intentionally a later phase. The first phase proves the
teams, storage, and Telegram delivery by manually created Paperclip issues.

## 2. Research Basis

This spec incorporates four independent review tracks:

- deploy/team-factory analysis of `paperclips/build.sh`,
  `paperclips/deploy-codex-agents.sh`, `paperclips/hire-codex-agents.sh`,
  `paperclips/validate-codex-target.sh`, and team workspace scripts;
- GitHub signal analysis of `.github/workflows/paperclip-signal.yml`,
  `.github/scripts/paperclip_signal.py`, `.github/paperclip-signals.yml`, and
  existing Paperclip issue creation scripts;
- security analysis of GitHub signal, local checkout, Paperclip API,
  Telegram delivery, and audit artifact handling;
- knowledge/storage analysis of `codebase-memory`, Serena, Palace/Neo4j,
  Paperclip docs/memories, and Telegram.

Confirmed local facts:

- The CX Codex bundle path already exists through
  `./paperclips/build.sh --target codex`.
- Codex bundle validation already exists through
  `./paperclips/validate-codex-target.sh`.
- Current Codex deploy and hire scripts are hardcoded to Gimle/CX names,
  agent-id files, workspace roots, and some model choices.
- Current GitHub signal code is not suitable for this feature as-is because it
  posts PR comments, keys off existing Paperclip branch conventions, and checks
  out repository code before running a secret-bearing signal script.
- `codebase-memory` currently has an indexed iOS Unstoppable repository at
  `/Users/ant013/Ios/HorizontalSystems/unstoppable-wallet-ios`; Android was not
  visible in the current `codebase-memory` project list and must be treated as a
  bootstrap gap until verified.

## 3. Problem

We need a practical audit workflow for private Unstoppable Wallet review that
does not block GitHub PRs and does not publish sensitive audit detail in GitHub.

The operator wants:

- two separate Codex teams so iOS and Android audits do not block each other;
- the same instruction quality as Gimle/CX agents: shared fragments, handoff
  rules, Karpathy discipline, MCP awareness, skills/plugin rules, and team
  rosters;
- audit reports delivered as `.md` files to Telegram;
- local baseline knowledge that later PR audits can reuse;
- a future path where GitHub PRs targeting `version/**` only signal Paperclip
  to start an audit.

The dangerous failure modes are:

- UI-created agents drifting from team rules;
- cross-team contamination with Gimle/TG names, UUIDs, project paths, or
  handoff rules;
- audit artifacts living only in Telegram;
- GitHub Actions running untrusted PR code with Paperclip secrets;
- accidental PR comments or required checks that block merge flow;
- mutable branch refs being audited instead of immutable commits.

## 4. Assumptions

- The target Paperclip deployment is `https://paperclip.ant013.work`.
- The preferred Paperclip organization model is one dedicated company named
  `UnstoppableAudit` with two projects:
  - `UnstoppableWallet-iOS`;
  - `UnstoppableWallet-Android`.
- If Paperclip company creation or permissions make that impractical, the
  fallback is one existing company with the same two projects and strict
  `UWI`/`UWA` prefixes. The fallback must be documented before use.
- Both audit teams use the Codex local adapter.
- Model selection must be configurable per team/role. The implementation must
  not hardcode unavailable models such as `gpt-5.5`; the initial default should
  be a currently usable Codex model such as `gpt-5.3-codex-spark`, unless the
  operator explicitly changes it.
- Agents are audit-only. They may read repositories, produce reports, assign
  Paperclip issues, and send Telegram files through the plugin. They must not
  push to Unstoppable repositories, merge PRs, or change product code.
- Telegram is an operator-approved delivery channel, but it is not treated as
  end-to-end encrypted or durable storage.
- GitHub automation is not part of the first implementation slice.

## 5. Scope

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
- Hybrid audit knowledge storage:
  - `codebase-memory` and Serena for live source navigation;
  - Palace/Neo4j for structured audit facts and run provenance;
  - Paperclip docs/memories for human-readable reports and operator decisions;
  - Telegram for final delivery only.
- First shallow baseline audit for each repo.
- Manual PR audit workflow for later operator-created Paperclip issues.
- Security requirements for local checkout, report redaction, and future GitHub
  signal automation.

### Out Of Scope

- Implementing GitHub automation in the first slice.
- Adding required GitHub checks or blocking PR merges.
- Posting audit reports or summaries as GitHub PR comments.
- Running full app builds, tests, or product code unless explicitly approved per
  audit issue.
- Writing code changes to `unstoppable-wallet-ios` or
  `unstoppable-wallet-android`.
- Creating automated remediation PRs.
- Treating Telegram as canonical audit storage.
- Building a general marketplace product for arbitrary companies in this first
  slice. The implementation should be generic enough to reuse, but acceptance is
  based on `UWI` and `UWA`.

## 6. Team Model

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
- `UWIQAEngineer`: owns verification of the audit process, report evidence, and
  delivery smoke checks.
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
- `UWAQAEngineer`: owns verification of the audit process, report evidence, and
  delivery smoke checks.
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
- Every final report must include the exact repo, commit SHA, audit type, date,
  authoring team, and evidence limitations.

## 7. Deployment Design

The implementation should extend existing Gimle/CX mechanics instead of
copy-pasting agent configuration in the UI.

Required changes for the later implementation plan:

- Introduce a team config file, for example
  `paperclips/teams/unstoppable-audit.yaml`, describing:
  - company/project names or IDs;
  - `UWI` and `UWA` prefixes;
  - roles and display names;
  - model defaults and per-role overrides;
  - workspace roots;
  - reports-to relationships;
  - Telegram delivery policy;
  - repository URLs and local clone paths.
- Add or extend a team factory script that can:
  - dry-run the planned hires;
  - submit hire requests through the Paperclip API;
  - write a team-scoped agent-id file;
  - refuse to overwrite Gimle/CX/TG agent IDs.
- Add or extend a Codex deploy script that can:
  - build bundles for a named team;
  - validate bundles;
  - deploy only the selected team;
  - preflight that live agents use `codex_local`;
  - use a team-scoped agent-id file.
- Keep `./paperclips/build.sh --target codex` as the base build path unless a
  team-aware target extension is explicitly approved.
- Validation must fail if generated `UWI`/`UWA` bundles contain stale
  references to:
  - Gimle project names as active scope;
  - TG plugin project names as active scope;
  - CX agent rosters as the current team;
  - old agent UUIDs;
  - Claude/Opus-only runtime instructions.
- Generated bundles must mention `AGENTS.md`, `codex_local`, `codebase-memory`,
  Serena, Paperclip handoff, and Telegram file delivery rules.

## 8. Workspace And Repository Bootstrap

Use stable source checkouts per repository plus ephemeral per-audit workspaces.

Recommended stable roots:

- `/Users/Shared/Ios/worktrees/unstoppable-audit/ios/unstoppable-wallet-ios`
- `/Users/Shared/Ios/worktrees/unstoppable-audit/android/unstoppable-wallet-android`

The exact paths may change during implementation, but the accepted design must
preserve:

- separate iOS and Android roots;
- no shared mutable checkout between teams;
- no product-code push permissions required for audit agents;
- no `git pull` inside an active audit run;
- immutable commit SHA recorded for every baseline or PR audit.

Baseline bootstrap:

1. clone or refresh each repository in its stable root;
2. fetch the default branch;
3. record remote URL, default branch, and baseline commit SHA;
4. index each repository in `codebase-memory`;
5. activate or create Serena project context for each repository if supported;
6. write a short repo map into Paperclip docs/memories;
7. create a Palace/Neo4j audit project record if the graph schema is available.

PR audit bootstrap, later manual path:

1. operator creates a Paperclip issue with repo, PR URL, base SHA, and head SHA;
2. team fetches the exact head SHA into an ephemeral worktree;
3. team optionally computes a merge-base or pinned merge commit if the audit
   scope requires merged-result semantics;
4. team audits only the intended diff plus dependency impact;
5. team deletes or archives the ephemeral worktree according to retention policy.

## 9. Knowledge Storage

Use a hybrid model.

### Live Code Intelligence

`codebase-memory` and Serena are the live analysis substrate. They are allowed
to be rebuilt and should not be the only durable audit history.

Required project keys:

- `uw-ios` or a clear equivalent for `unstoppable-wallet-ios`;
- `uw-android` or a clear equivalent for `unstoppable-wallet-android`.

### Structured Audit Knowledge

Palace/Neo4j is the canonical structured audit store when available.

Minimum record shape:

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

### Narrative Audit Artifacts

Paperclip docs/memories are the durable human-readable layer:

- baseline audit report markdown;
- PR audit report markdown;
- operator decisions;
- accepted-risk notes;
- audit limitations;
- handoff summaries.

### Telegram

Telegram is delivery-only:

- send final `.md` files to the configured private audit chat/group;
- do not rely on Telegram as the only retained copy;
- do not put raw secrets, tokens, exploit payloads, or full sensitive stack
  traces into Telegram reports.

## 10. Audit Workflows

### Baseline Audit

For each platform team:

1. CTO creates or accepts one baseline audit issue.
2. Infra engineer verifies repo checkout, commit SHA, tools, MCP access, and
   `codebase-memory`/Serena status.
3. Research agent writes a concise repo/domain context memo.
4. Platform auditor reviews code structure, architecture boundaries, and risky
   changed/hot areas visible from baseline analysis.
5. Security auditor reviews auth, secrets, privacy, network, storage, and
   abuse-path risks.
6. Crypto auditor reviews wallet, key, transaction, signing, address, chain,
   and fee-related areas.
7. Technical writer assembles a Markdown report from reviewed subreports.
8. QA engineer verifies report evidence, redaction, reproducibility, and
   Telegram delivery on a harmless test file before final send.
9. CTO approves final report, stores it in Paperclip/Neo4j as applicable, and
   sends the Markdown file to Telegram through the plugin.
10. CTO closes the issue only after storage and Telegram delivery evidence are
    attached to the issue.

### Manual PR Audit

Until GitHub automation exists:

1. operator creates one Paperclip issue per PR audit;
2. issue title includes team prefix, repo, PR number, and short subject;
3. issue body includes PR URL, target branch, base SHA, head SHA, and requested
   depth;
4. team fetches exact commits and audits the diff plus relevant dependency
   impact;
5. final report is stored and delivered as Markdown;
6. no GitHub comments or status checks are created.

### Future GitHub Signal

The future automation should only create or update Paperclip audit issues. It
must not run the audit inside GitHub Actions.

Required signal design:

- trigger on PR lifecycle events targeting `version/**`;
- prefer a direct `pull_request_target` workflow restricted to `version/**`,
  with no checkout of PR head or merge refs;
- if `pull_request_target` is rejected, use an unprivileged `pull_request`
  workflow only for internal PRs and document fork limitations;
- use minimal `GITHUB_TOKEN` permissions;
- use a dedicated Paperclip signal key with least privilege;
- send only metadata: repo, PR number, base branch, base SHA, head SHA, title,
  author, and event type;
- deduplicate on the Paperclip side by a stable PR key;
- do not post PR comments;
- do not add required checks;
- confirm live branch protection for `version/**` before enabling.

## 11. Security Requirements

- Audit teams are read-only for Unstoppable repositories.
- GitHub Actions must be metadata/signal-only when automation is added.
- No GitHub Action may checkout untrusted PR code while Paperclip secrets are
  available.
- Local audits must fetch immutable commit SHAs, not mutable branch refs.
- Git hooks must not run during audit checkout.
- Submodules and LFS smudge should be disabled by default unless explicitly
  needed and approved for a specific repo.
- Audit workspaces should be isolated per run and cleaned up or retained under a
  documented retention policy.
- Audit logs must not print raw reports, secrets, tokens, auth headers, or full
  payloads.
- Telegram reports must be redacted for secrets and high-risk exploit detail.
- The Paperclip API key used by future GitHub signals must not have broad admin
  scope.
- The Telegram bot token and Paperclip signal key must be separate secrets.
- Failure to deliver to Telegram must not lose the report; the stored report is
  canonical.

## 12. Report Format

Baseline reports should be Markdown files named:

- `UWI-baseline-audit-<short_sha>.md`
- `UWA-baseline-audit-<short_sha>.md`

Manual PR reports should be named:

- `UWI-pr-<pr_number>-<short_sha>.md`
- `UWA-pr-<pr_number>-<short_sha>.md`

Minimum report sections:

- title;
- repo and exact commit(s);
- audit type and scope;
- executive summary;
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

## 13. Acceptance Criteria

- A reviewed implementation plan exists after this spec is approved.
- No implementation code is changed in the spec-only commit.
- A repeatable team config exists for `UWI` and `UWA`.
- Team creation can be dry-run before API execution.
- Team deployment can be dry-run before API execution.
- Generated bundles pass Codex validation.
- Bundle validation rejects stale Gimle/TG/CX active-scope contamination.
- Agents are deployed through scripts/API, not hand-edited in UI.
- Agents can report their team, project, handoff rules, MCP access, and
  Telegram file-delivery protocol in a smoke task.
- iOS and Android repositories have separate local roots.
- Both repositories have recorded baseline SHAs.
- Both repositories are indexed or have explicit structured skip reasons.
- A shallow baseline audit report exists for iOS.
- A shallow baseline audit report exists for Android.
- Both baseline reports are stored outside Telegram.
- Both baseline reports are delivered to the configured private Telegram
  destination as Markdown files.
- Manual PR audit instructions are documented and tested with a dry-run or
  harmless sample issue.
- No GitHub PR comments, required checks, or merge-blocking behavior are added.

## 14. Verification Plan

Spec verification:

- `git diff --check`
- confirm only docs/spec files changed in the spec commit.

Later implementation verification:

- `./paperclips/build.sh --target codex`
- `./paperclips/validate-codex-target.sh`
- team factory dry-run for `UWI`;
- team factory dry-run for `UWA`;
- deploy dry-run for `UWI`;
- deploy dry-run for `UWA`;
- API preflight that every live agent adapter is `codex_local`;
- smoke issue for `UWICTO`;
- smoke issue for `UWACTO`;
- grep generated bundles for stale active-scope references:
  - `Gimle`;
  - `Telegram Plugin Fork`;
  - `TGCTO`;
  - `CXCTO`;
  - old UUIDs from unrelated teams;
- `codebase-memory` index status for iOS;
- `codebase-memory` index status for Android;
- Serena activation check for iOS;
- Serena activation check for Android;
- harmless Telegram file-send smoke with a non-sensitive Markdown file;
- baseline audit delivery proof for both teams.

Future GitHub signal verification:

- unit tests for `version/**` base-branch filtering;
- unit tests proving no PR comments are posted;
- unit tests for deterministic PR-to-Paperclip issue upsert;
- test that fork PRs do not expose secrets if supported;
- live check that `version/**` branch protection does not require the signal
  workflow.

## 15. Open Questions

- What are the exact canonical GitHub remote URLs for iOS and Android?
- Should `UnstoppableAudit` be a separate Paperclip company or two projects
  inside an existing company?
- What Telegram chat/channel ID should receive final audit files?
- Should ops notifications for audit agent start/finish go to a separate ops
  chat from final audit reports?
- What is the exact model matrix for CTO/security/crypto roles versus writer and
  QA roles?
- Should baseline audit include a combined cross-platform report after the two
  per-platform reports?
- Should accepted-risk decisions be mirrored into Neo4j as first-class nodes, or
  kept only in Paperclip docs/memories for the first release?
- What retention period should apply to ephemeral PR audit workspaces and local
  report files?

## 16. Proposed Implementation Sequence

This is not implementation approval; it is the expected plan shape after spec
review.

1. Write the implementation plan with explicit one-issue handoff order.
2. Add the team config and generic/team-aware hire/deploy dry-run path.
3. Add Unstoppable-specific Codex role bundles/fragments.
4. Build and validate bundles.
5. Create/hire agents through Paperclip API.
6. Deploy bundles through API.
7. Run agent smoke tests.
8. Prepare iOS and Android local repo roots.
9. Index both repos with `codebase-memory` and verify Serena access.
10. Create baseline knowledge records and repo maps.
11. Run first shallow baseline audit for iOS.
12. Run first shallow baseline audit for Android.
13. Store reports and deliver Markdown files through Telegram.
14. Run QA verification.
15. CTO closes the issue only after both storage and Telegram evidence exist.

