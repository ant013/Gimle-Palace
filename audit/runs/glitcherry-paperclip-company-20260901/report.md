# Gimle reliability report: glitcherry-paperclip-company-20260901

- Task: GLITCHERRY-PAPERCLIP-COMPANY
- Workflow/phase: analog_change / awaiting_approval
- Trust: **YELLOW**
- Repository: /Users/ant013/Data/AI/audit/worktrees/gimle-palace-glitcherry-company
- Base HEAD: 25e531cd91e7b60375801583626b46357f032557
- Final HEAD: n/a
- Gimle runtime: n/a
- Indexed commit: n/a

## Metrics

- Calls: 1 (success 0, warning 0, error 1, false-success 0)
- Useful-call rate: 0.0%
- Response-byte coverage: 0/1; total n/a
- Duration coverage: 0/1; total n/a ms
- Gimle agreement: n/a
- Gimle contradiction: n/a
- Location validity: n/a; coverage 0/0
- Freshness coverage: n/a
- Replacement/fallback claims: 0
- Bugs: 2
- Analog slices/candidates: 3/10

### Calls by tool

| Tool | Success | Warning | Error | False-success |
|---|---:|---:|---:|---:|
| palace.health.status | 0 | 0 | 1 | 0 |

Bug classes: {'environment_drift': 1, 'stale_index': 1}
Bug severities: {'medium': 1, 'high': 1}
Bug statuses: {'workaround': 2}

## Gimle calls

| Event | Phase | Tool | Protocol | Outcome | Total/returned | Bytes | Duration | Used | Args hash | Warnings |
|---|---|---|---|---|---|---:|---:|:---:|---|---|
| E-0001 | evidence | palace.health.status | unavailable | error | n/a/n/a | n/a | n/a | no | 44136fa355b3678a | No Gimle or Palace MCP tools are exposed in this session; no call could be issued. |

## Component analog family

| Slice | Risk | Required dimensions | Required roles | Waived roles | Primary | Supporting | Counterexamples |
|---|---|---|---|---|---|---|---|
| S-WALKER-PROFILE | high | boundary, dependencies, lifecycle, responsibility, state_errors, tests, trust | composition, consumer, contract, counterexample, implementation, lifecycle_error, test | n/a | C-WALKER-REVIEWER-BASE | C-WALKER-BOOTSTRAP-SMOKE | C-WALKER-CTO-RELEASE |
  - Conflict: The cto profile contains the desired merge/plan/orchestration features but also release-cut and lacks explicit commit/push authority needed for spec/plan branches.; resolution: Create a separate walker profile extending reviewer, add commit-and-push/worktree/merge/orchestration/plan fragments, exclude release-cut, and test both positive and negative authority.
| S-PROJECT-BUNDLE | high | boundary, dependencies, lifecycle, responsibility, state_errors, tests, trust | composition, consumer, contract, counterexample, implementation, lifecycle_error, test | n/a | C-BUNDLE-THORCHAIN | C-BUNDLE-FULLAUDIT | C-BUNDLE-LEGACY |
  - Conflict: ThorChain assigns the outer Walker to CEO and uses profile cto for both CEO and CTO, while Glitcherry explicitly assigns roadmap walking to CTO and forbids CEO technical execution.; resolution: Reuse ThorChain bundle shape, atomic handoffs, dormancy and exact tests; set CEO to minimal/governance and CTO to the new walker profile, with Glitcherry-specific role crafts and seven-role roster.
| S-BOOTSTRAP-CANARY | high | boundary, dependencies, lifecycle, responsibility, state_errors, tests, trust | composition, consumer, contract, counterexample, implementation, lifecycle_error, test | n/a | C-BOOTSTRAP-JOURNALED | C-BOOTSTRAP-SMOKE, C-BOOTSTRAP-DORMANT | C-BOOTSTRAP-DIRTY-LIVE |
  - Conflict: The live iMac lacks both product source clones and its shared Gimle checkout is dirty, so in-place deploy/bootstrap is unsafe.; resolution: After approval, clone both private repos into dedicated /Users/anton/Android sources, deploy from a fresh Gimle worktree, run bootstrap without autonomous roadmap activation, then disposable smoke/canary and leave no feature issue.

### Analog candidates

| Candidate | Slice | Disposition | Fact | Roles | Dimensions | Freshness | Path |
|---|---|---|---|---|---|---|---|
| C-WALKER-REVIEWER-BASE | S-WALKER-PROFILE | kept | F-REVIEWER-BASE | contract, implementation | boundary, dependencies, responsibility | known_current | paperclips/fragments/profiles/reviewer.yaml |
| C-WALKER-BOOTSTRAP-SMOKE | S-WALKER-PROFILE | supporting | F-BOOTSTRAP-IDENTITY-SMOKE | composition, consumer, lifecycle_error, test | lifecycle, state_errors, tests, trust | known_current | paperclips/scripts/bootstrap-project.sh |
| C-WALKER-CTO-RELEASE | S-WALKER-PROFILE | rejected | F-CTO-RELEASE-CONFLICT | counterexample | boundary, lifecycle | known_current | paperclips/fragments/profiles/cto.yaml |
| C-BUNDLE-THORCHAIN | S-PROJECT-BUNDLE | kept | F-THORCHAIN-BUNDLE | composition, contract, implementation | boundary, dependencies, lifecycle, responsibility | known_current | paperclips/projects/thorchain |
| C-BUNDLE-FULLAUDIT | S-PROJECT-BUNDLE | supporting | F-FULLAUDIT-SANDBOX | consumer, lifecycle_error, test | state_errors, tests, trust | known_current | paperclips/projects/fullaudit |
| C-BUNDLE-LEGACY | S-PROJECT-BUNDLE | rejected | F-LEGACY-COUNTEREXAMPLES | counterexample | boundary, lifecycle | known_current | paperclips/projects/trading/WORKFLOW.md |
| C-BOOTSTRAP-JOURNALED | S-BOOTSTRAP-CANARY | kept | F-BOOTSTRAP-LIFECYCLE | composition, contract, implementation | dependencies, lifecycle, responsibility | known_current | paperclips/scripts/bootstrap-project.sh |
| C-BOOTSTRAP-SMOKE | S-BOOTSTRAP-CANARY | supporting | F-SMOKE-ROLLBACK | consumer, lifecycle_error, test | state_errors, tests, trust | known_current | paperclips/scripts/smoke-test.sh |
| C-BOOTSTRAP-DORMANT | S-BOOTSTRAP-CANARY | supporting | F-THORCHAIN-BUNDLE | consumer, contract | boundary | known_current | paperclips/projects/thorchain/WORKFLOW.md |
| C-BOOTSTRAP-DIRTY-LIVE | S-BOOTSTRAP-CANARY | quarantined | F-LIVE-BOOTSTRAP-PREFLIGHT | counterexample | lifecycle, state_errors | known_current | /Users/Shared/Ios/Gimle-Palace |

## Evidence claims

| Fact | Rev | Load-bearing | Verdict | Accepted | Basis | Events | Location | Freshness | Claim |
|---|---:|:---:|---|:---:|---|---|---|---|---|
| F-REVIEWER-BASE | 1 | yes | MATCH | yes | serena+rg | n/a | valid | known_current | The reviewer profile is the closest non-release capability base: universal safety, codebase discovery, merge-readiness, plan review, approval, and atomic handoff, but no commit/... |
  - Serena: Fresh Serena target inspection found reviewer.yaml extends no profile and includes merge-readiness, merge-state, approve, plan review, and handoff.
  - rg: Fresh rg/sed at HEAD 25e531cd confirms reviewer.yaml lines 1-13 and profile tests; description explicitly excludes commit-and-push and release-cut.
  - Anchors: paperclips/fragments/profiles/reviewer.yaml:1, paperclips/tests/test_phase_b_profiles.py:83
| F-BOOTSTRAP-IDENTITY-SMOKE | 1 | yes | MATCH | yes | rg | n/a | valid | known_current | Bootstrap accepts explicit Paperclip role/icon independently from prompt profile, routes workflow identity separately, and smoke probes Git authority by profile and orchestratio... |
  - Serena: n/a
  - rg: bootstrap-project.sh:595-609 applies paperclip_role/paperclip_icon overrides; smoke-test.sh:145-159 passes profile and workflow_role separately; _smoke_probes.sh:131-203 separates Git and phase checks.
  - Anchors: paperclips/scripts/bootstrap-project.sh:595, paperclips/scripts/lib/_smoke_probes.sh:131, paperclips/scripts/smoke-test.sh:145
| F-CTO-RELEASE-CONFLICT | 1 | yes | MATCH | yes | serena+rg | n/a | valid | known_current | The current cto profile is unsafe for Glitcherry Walker authority because it inherits reviewer and unconditionally includes release-cut in addition to merge and plan/orchestrati... |
  - Serena: Fresh Serena inspection found cto.yaml extends reviewer and includes universal/cto-merge-authority.md, git/release-cut.md, handoff/phase-orchestration.md, and plan/producer.md.
  - rg: Fresh sed confirms cto.yaml lines 1-12; _smoke_probes.sh:23 requires merge and release-cut for profile cto.
  - Anchors: paperclips/fragments/profiles/cto.yaml:1, paperclips/scripts/lib/_smoke_probes.sh:23
| F-THORCHAIN-BUNDLE | 1 | yes | MATCH | yes | serena+rg | n/a | valid | known_current | ThorChain is the strongest project-bundle analog: custom role crafts, explicit Paperclip/workflow identities, exact-roster tests, a dormant bootstrap boundary, one active child,... |
  - Serena: Fresh Serena inspection found explicit CEO/CTO/reviewer/implementer/QA identities in the assembly, exactly-one-child orchestration in CTO craft, and the atomic workflow handoff.
  - rg: ThorChain WORKFLOW.md:14-17,45-49; assembly:90-136; test_phase_f_thorchain_assembly.py asserts exact roster/files/dormancy markers/rendered templates.
  - Anchors: paperclips/projects/thorchain/WORKFLOW.md:14, paperclips/projects/thorchain/paperclip-agent-assembly.yaml:86, paperclips/tests/test_phase_f_thorchain_assembly.py:18
| F-FULLAUDIT-SANDBOX | 1 | yes | MATCH | yes | serena+rg | n/a | valid | known_current | fullAudit is the strongest sandbox/composition analog: constrained per-agent Git workspaces cloned from a host-local source, loopback-only Paperclip URL, minimal writable roots,... |
  - Serena: Fresh Serena inspection found explicit identities plus constrained writable paths in the fullAudit assembly.
  - rg: fullAudit assembly:44-48,115-117,173-177; bootstrap-project.sh:630-707; test_fullaudit_assembly.py:17-149 asserts constrained roots, clone isolation, loopback env and exact roster.
  - Anchors: paperclips/projects/fullaudit/paperclip-agent-assembly.yaml:44, paperclips/tests/test_fullaudit_assembly.py:17
| F-LEGACY-COUNTEREXAMPLES | 1 | yes | MATCH | yes | rg | n/a | valid | known_current | Trading and Wallet Radar are useful negative examples for Glitcherry authority and handoff: both bind CEO-like roles to the cto profile, and their older workflows use a single P... |
  - Serena: n/a
  - rg: trading assembly:84-90 and wallet-radar assembly:76-84 use cto roles/profiles; trading WORKFLOW.md:186-197 and wallet-radar WORKFLOW.md:116-126 describe legacy single-PATCH/decorative mention semantics.
  - Anchors: paperclips/projects/trading/paperclip-agent-assembly.yaml:84, paperclips/projects/wallet-radar/WORKFLOW.md:116
| F-BOOTSTRAP-LIFECYCLE | 1 | yes | MATCH | yes | rg | n/a | valid | known_current | The current bootstrap is journaled and idempotent: it validates manifest/host roots/prefix, creates or reuses company and agents, reconciles managed config, clones isolated work... |
  - Serena: n/a
  - rg: bootstrap-project.sh:337-408 validates and journals paths; 410 onward create-or-reuse; 630-707 constrains workspaces/env; 879 selects inner_orchestrator; 901-944 deploys per-agent workspace instructions.
  - Anchors: paperclips/scripts/bootstrap-project.sh:337, paperclips/scripts/bootstrap-project.sh:879, paperclips/scripts/bootstrap-project.sh:901
| F-SMOKE-ROLLBACK | 1 | yes | MATCH | yes | rg | n/a | valid | known_current | Runtime smoke covers identity/config, workspace, profile Git boundaries, workflow responsibility and cross-agent handoff using disposable issues, while rollback tracks and compe... |
  - Serena: n/a
  - rg: smoke-test.sh:76-191 and _smoke_probes.sh:44-224 create tracked disposable issues, check profiles/workflow and perform handoff; rollback.sh records/deletes exact resources with path and UUID guards.
  - Anchors: paperclips/scripts/smoke-test.sh:76, paperclips/scripts/lib/_smoke_probes.sh:44, paperclips/scripts/rollback.sh:84
| F-GLITCHERRY-CONTROL-CONTRACT | 1 | yes | MATCH | yes | rg | n/a | valid | known_current | The current Glitcherry control repo assigns roadmap authorship and releases to the Human Engineering Lead, CEO to governance only, CTO to the single Walker, and requires separat... |
  - Serena: n/a
  - rg: Glitcherry at f3e4943: human-engineering-lead.md:3-18, walker-lifecycle.md:1-52, two-repository-git-workflow.md:1-66, and ROADMAP.md:1-57 define these boundaries.
  - Anchors: /Users/ant013/Data/AI/Glitcherry/docs/runbooks/human-engineering-lead.md:3, /Users/ant013/Data/AI/Glitcherry/docs/runbooks/walker-lifecycle.md:1
| F-LIVE-BOOTSTRAP-PREFLIGHT | 1 | yes | MATCH | yes | rg | n/a | valid | known_current | Live Paperclip has no Glitcherry company and no GLA prefix allocation; the iMac has neither Glitcherry repo clone at the proposed Android paths, while the shared Gimle checkout ... |
  - Serena: n/a
  - rg: Authenticated API check on 2026-09-01 listed prefixes STA,TRD,FUL,TEL,WR,MED,GIM,UNS only. SSH path check found proposed Glitcherry paths absent and /Users/Shared/Ios/Gimle-Palace at 6d736a4e develop with 15 dirty entries.
  - Anchors: Paperclip GET /api/companies 2026-09-01, iMac SSH path audit 2026-09-01

## Adversarial decisions

- ADR-ROSTER-7@2 ACCEPT: Keep seven permanent agents, including a dedicated Media Pipeline Engineer.
- ADR-CEO-MINIMAL@2 ACCEPT: Use profile minimal plus explicit Paperclip CEO identity and a custom governance role craft.
- ADR-WALKER-PROFILE@2 ACCEPT: Add a reusable walker profile rather than reuse cto.
- ADR-NO-CUSTOM-INCLUDES@2 ACCEPT: Use a tested global profile instead of a project manifest custom include list.
- ADR-CTO-NO-SELF-REVIEW@2 ACCEPT: Allow reviewer mechanics in Walker profile but prohibit CTO self-approval by workflow and exact-owner tests.
- ADR-ONE-WRITER@2 ACCEPT: Retain two specialized implementers with exactly one primary writer per slice.
- ADR-QA-PROFILE@2 ACCEPT: Use established qa profile with a custom no-fix role boundary.
- ADR-TWO-REPO-WORKSPACE@2 ACCEPT: Use Android as the generated cwd and a CTO-only sibling control clone inside the writable workspace.
- ADR-MODEL-EFFORT@2 ACCEPT: Use gpt-5.6-sol xhigh for judgment-heavy roles and high for bounded CEO/platform/QA roles.
- ADR-DORMANT@2 ACCEPT: Bootstrap and canary leave the company dormant with no product/root issue.
- ADR-CONSTRAINED@2 ACCEPT: Start with constrained sandbox and false bypass; treat missing capability as a failed canary.

## Verification and acceptance


## Bugs and limitations

### GIMLE-ENV-001: Gimle/Palace MCP unavailable in current session

- Class/severity/confidence/status: environment_drift / medium / confirmed / workaround
- Tool/events/claims: palace.health.status / E-0001 / n/a
- Reproduction: Inspect enabled MCP tool catalog for palace or gimle namespaces.
- Expected: A read-only health endpoint and project-discovery tools are callable.
- Actual: No palace/gimle tool is registered.
- Impact: Semantic Gimle discovery and freshness metadata cannot contribute to analog selection.
- Workaround: Use codebase-memory only for candidate discovery, then rely exclusively on Serena and targeted rg in the fresh worktree.
- Anchors: tool catalog 2026-09-01

### CBM-MAP-001: Indexed Gimle-Palace checkout does not match target worktree

- Class/severity/confidence/status: stale_index / high / confirmed / workaround
- Tool/events/claims: codebase-memory / n/a / n/a
- Reproduction: Compare codebase-memory project root Users-ant013-Android-Gimle-Palace and its Git HEAD with the task worktree HEAD.
- Expected: Indexed checkout maps to the current origin/develop ancestry and contains current ThorChain/fullAudit project sources.
- Actual: Index root HEAD c62cef3 is on another branch, is not an ancestor of target 25e531cd, and bounded searches missed current ThorChain/fullAudit files.
- Impact: Indexed locations and absence results cannot be load-bearing for this design.
- Workaround: Use codebase-memory only as a hint; verify every kept analog with Serena and rg at 25e531cd.
- Anchors: paperclips/projects/thorchain; paperclips/scripts/bootstrap-project.sh

## Interpretation

Contradicted or unverifiable Gimle evidence was not accepted as repository truth. A verified fallback does not erase the defect.
