# Gimle reliability report: paperclip-thorchain-codex56-20260717

- Task: paperclip-thorchain-team
- Workflow/phase: analog_change / awaiting_approval
- Trust: **RED**
- Repository: /Users/ant013/Android/Gimle-Palace-paperclip-thorchain
- Base HEAD: b56232d5b49183cfac04c9d403659a4a45cfcceb
- Final HEAD: n/a
- Gimle runtime: n/a
- Indexed commit: n/a

## Metrics

- Calls: 15 (success 11, warning 3, error 1, false-success 0)
- Useful-call rate: 93.3%
- Response-byte coverage: 1/15; total 93
- Duration coverage: 0/15; total n/a ms
- Gimle agreement: 80.0%
- Gimle contradiction: 20.0%
- Location validity: 80.0%; coverage 5/5
- Freshness coverage: 100.0%
- Replacement/fallback claims: 1
- Bugs: 6
- Analog slices/candidates: 4/14

### Calls by tool

| Tool | Success | Warning | Error | False-success |
|---|---:|---:|---:|---:|
| codebase-memory.get_architecture | 1 | 1 | 1 | 0 |
| codebase-memory.get_code_snippet | 4 | 0 | 0 | 0 |
| codebase-memory.index_status | 1 | 0 | 0 | 0 |
| codebase-memory.list_projects | 1 | 0 | 0 | 0 |
| codebase-memory.search_code | 4 | 1 | 0 | 0 |
| codebase-memory.search_graph | 0 | 1 | 0 | 0 |

Bug classes: {'caller_error': 2, 'stale_index': 1, 'coverage_gap': 3}
Bug severities: {'low': 3, 'high': 1, 'medium': 2}
Bug statuses: {'workaround': 5, 'fixed': 1}

## Gimle calls

| Event | Phase | Tool | Protocol | Outcome | Total/returned | Bytes | Duration | Used | Args hash | Warnings |
|---|---|---|---|---|---|---:|---:|:---:|---|---|
| E-0001 | preflight | codebase-memory.index_status | ok | success | n/a/1 | 93 | n/a | yes | 7f8b32ff65fe23ad | n/a |
| E-0002 | preflight | codebase-memory.search_code | ok | warning | 96/30 | n/a | n/a | yes | 5a5a36dacab2cd5c | Payload exceeded the response budget and was truncated; use narrower current-tree lanes before accepting candidates |
| E-0003 | preflight | codebase-memory.search_code | ok | success | 4/4 | n/a | n/a | yes | 277668d8b69d4e2b | n/a |
| E-0004 | evidence | codebase-memory.search_code | ok | success | 0/0 | n/a | n/a | yes | 10b64dcd7a5f2d1c | n/a |
| E-0005 | evidence | codebase-memory.list_projects | ok | success | 51/51 | n/a | n/a | yes | 44136fa355b3678a | n/a |
| E-0006 | evidence | codebase-memory.search_graph | ok | warning | 1253/30 | n/a | n/a | yes | ad0bd19475427992 | Graph payload returned only the first 30 of 1253 results; no candidate accepted without current-tree verification |
| E-0007 | evidence | codebase-memory.get_code_snippet | ok | success | n/a/1 | n/a | n/a | yes | d89b849f330006ae | n/a |
| E-0008 | evidence | codebase-memory.get_code_snippet | ok | success | n/a/1 | n/a | n/a | yes | 4a25a08858156969 | n/a |
| E-0009 | evidence | codebase-memory.get_code_snippet | ok | success | n/a/1 | n/a | n/a | yes | c5fd29349c71cd5e | n/a |
| E-0010 | evidence | codebase-memory.get_code_snippet | ok | success | n/a/1 | n/a | n/a | yes | 02a6df2308d4575f | n/a |
| E-0011 | evidence | codebase-memory.get_architecture | ok | error | n/a/0 | n/a | n/a | no | bc90784e79f7e4e4 | Caller used a hyphenated slug; indexed project uses EvmKit.Swift |
| E-0012 | evidence | codebase-memory.get_architecture | ok | warning | n/a/0 | n/a | n/a | yes | 82cf5575095950d3 | TronKit.Swift is not indexed; use exact local Serena and rg fallback |
| E-0013 | evidence | codebase-memory.get_architecture | ok | success | n/a/1 | n/a | n/a | yes | 58460a12b7844843 | n/a |
| E-0014 | evidence | codebase-memory.search_code | ok | success | 2/2 | n/a | n/a | yes | 54abe8e664ff30e3 | n/a |
| E-0015 | evidence | codebase-memory.search_code | ok | success | 2/2 | n/a | n/a | yes | 4689ce3fd99f80a8 | n/a |

## Component analog family

| Slice | Risk | Required dimensions | Required roles | Waived roles | Primary | Supporting | Counterexamples |
|---|---|---|---|---|---|---|---|
| PC-S1 | critical | boundary, lifecycle, responsibility, state_errors, tests, trust | composition, contract, counterexample, implementation, lifecycle_error, test | n/a | C-PC-S1-PORTABILITY | C-PC-S1-NEW-TEAM-SMOKE | C-PC-S1-INCOMPLETE-ROLLBACK, C-PC-S1-STALE-BACKUP |
  - Conflict: UAA rollback does not invert all greenfield mutations; resolution: Add a transaction manifest that snapshots pre-state and records company, canonical bindings/paths, watchdog and every workspace path; verify rollback in dry-run before any old-state deletion
  - Conflict: Existing backup is older than database writes; resolution: Create and checksum a fresh SQL backup plus full portable company export immediately before mutation; deletion remains gated on count and restore validation
| PC-S2 | high | boundary, dependencies, lifecycle, responsibility, tests, trust | composition, contract, counterexample, implementation, test | n/a | C-PC-S2-TRADING-UAA | C-PC-S2-UNSTOPPABLE-SWIFT, C-PC-S2-CODEX56 | C-PC-S2-CEO-AS-CTO |
  - Conflict: Trading and preserved manifests derive live Paperclip role from capability profile, mapping CEO to CTO; resolution: Separate execution capability from live identity with validated paperclip_role and workflow_role fields; CEO is role ceo/outer_walker, CTO is role cto/inner_orchestrator
  - Conflict: Two agents may retain profile cto, causing canary and smoke to select CEO first; resolution: Select CTO by explicit paperclip_role/workflow_role, never by first profile cto; add regression tests
| PC-S3 | critical | boundary, dependencies, lifecycle, responsibility, state_errors, tests | composition, consumer, contract, counterexample, implementation, lifecycle_error, test | n/a | C-PC-S3-TRADING-WALKER | C-PC-S3-LIVE-UNSTOPPABLE | C-PC-S3-TRADING-ROLE-HANDOFF |
  - Conflict: Trading assigns both roadmap selection and child technical delivery to CTO; resolution: ThorChainCEO owns only the parent walker; ThorChainCTO owns phases 1, 3, and 7 of exactly one child
  - Conflict: Trading atomic handoff embeds the comment in the ownership PATCH; resolution: Require POST evidence comment, then PATCH assignee/status, exactly one read-only verification, then STOP
  - Conflict: The historical loop allowed premature merge, stale reopen, missing parent disposition, and invalid markers; resolution: Add permission boundaries, parent blockedBy invariant, same-PR marker lint, reviewed-head/QA merge gate, and stale-wake guards
| PC-S4 | high | boundary, dependencies, lifecycle, responsibility, tests | composition, consumer, contract, counterexample, implementation, test | n/a | C-PC-S4-TRONKIT-SCAFFOLD | C-PC-S4-EVMKIT-CONSUMER | C-PC-S4-LEGACY-SCAFFOLD |
  - Conflict: Existing kit analogs use legacy master and Swift tools 5.5; EvmKit lacks a test target; resolution: Use main for the new private repository; leave toolchain selection to the approved package-foundation slice and require tests plus iOS Example in that slice
  - Conflict: Creating package source now would pre-implement the first roadmap slice; resolution: Initial repository commit contains English governance/research/roadmap/report documentation and git hygiene only; no production Package.swift or Sources are claimed as delivered

### Analog candidates

| Candidate | Slice | Disposition | Fact | Roles | Dimensions | Freshness | Path |
|---|---|---|---|---|---|---|---|
| C-PC-S1-PORTABILITY | PC-S1 | kept | F-PC-007 | composition, contract, implementation, lifecycle_error | boundary, lifecycle, responsibility, state_errors, trust | known_current | /Users/ant013/.npm/_npx/43414d9b790239bb/node_modules/paperclipai/dist/index.js |
| C-PC-S1-NEW-TEAM-SMOKE | PC-S1 | supporting | F-PC-005 | test | lifecycle, tests, trust | known_current | paperclips/scripts/bootstrap-project.sh |
| C-PC-S1-INCOMPLETE-ROLLBACK | PC-S1 | rejected | F-PC-006 | counterexample | lifecycle, state_errors, trust | known_current | paperclips/scripts/rollback.sh |
| C-PC-S1-STALE-BACKUP | PC-S1 | quarantined | F-PC-011 | counterexample | lifecycle, state_errors, trust | known_current | /Users/ant013/Data/AI/paperclip/instances/default/data/backups/paperclip-20260618-202325.sql.gz |
| C-PC-S2-TRADING-UAA | PC-S2 | kept | F-PC-003 | composition, contract, implementation, test | boundary, dependencies, lifecycle, responsibility, tests | known_current | paperclips/projects/trading/paperclip-agent-assembly.yaml |
| C-PC-S2-UNSTOPPABLE-SWIFT | PC-S2 | supporting | F-PC-008 | implementation | dependencies, responsibility | known_current | /Users/ant013/Data/AI/paperclip/backups/unstoppable-codex-2026-06-13/cx-swift-engineer.md |
| C-PC-S2-CODEX56 | PC-S2 | supporting | F-PC-009 | composition | lifecycle, trust | known_current | /Users/ant013/.codex/config.toml |
| C-PC-S2-CEO-AS-CTO | PC-S2 | rejected | F-PC-008 | counterexample | boundary, dependencies, responsibility | known_current | /Users/ant013/Data/AI/paperclip/backups/unstoppable-codex-2026-06-13/manifest.codex.yaml |
| C-PC-S3-TRADING-WALKER | PC-S3 | kept | F-PC-004 | composition, contract, implementation | boundary, dependencies, lifecycle, responsibility, state_errors | known_current | paperclips/projects/trading/WORKFLOW.md |
| C-PC-S3-LIVE-UNSTOPPABLE | PC-S3 | supporting | F-PC-010 | consumer, lifecycle_error, test | lifecycle, state_errors, tests | known_current | /Users/ant013/Data/AI/paperclip/instances/default/data/run-logs/dfc662ee-513f-42f7-9f46-23f07e0a98d0 |
| C-PC-S3-TRADING-ROLE-HANDOFF | PC-S3 | rejected | F-PC-013 | counterexample | boundary, lifecycle, responsibility, state_errors | known_current | paperclips/projects/trading/WORKFLOW.md |
| C-PC-S4-TRONKIT-SCAFFOLD | PC-S4 | kept | F-PC-014 | composition, contract, implementation, test | boundary, dependencies, lifecycle, responsibility, tests | known_current | /Users/ant013/Ios/HorizontalSystems/TronKit.Swift/Package.swift |
| C-PC-S4-EVMKIT-CONSUMER | PC-S4 | supporting | F-PC-015 | consumer | boundary, lifecycle | known_current | /Users/ant013/Ios/HorizontalSystems/EvmKit.Swift/README.md |
| C-PC-S4-LEGACY-SCAFFOLD | PC-S4 | rejected | F-PC-015 | counterexample | dependencies, lifecycle, tests | known_current | /Users/ant013/Ios/HorizontalSystems/EvmKit.Swift/Package.swift |

## Evidence claims

| Fact | Rev | Load-bearing | Verdict | Accepted | Basis | Events | Location | Freshness | Claim |
|---|---:|:---:|---|:---:|---|---|---|---|---|
| F-PC-001 | 1 | yes | MATCH | yes | rg | n/a | valid | known_current | The clean origin/develop worktree has no paperclips/projects/unstoppable project assembly |
  - Serena: n/a
  - rg: find and sed both report paperclips/projects/unstoppable absent; current project directories are enumerated under paperclips/projects
  - Anchors: paperclips/projects
| F-PC-002 | 1 | yes | CONTRADICTED | no | rg | E-0003 | invalid | known_stale | Indexed paperclips/projects/unstoppable files are current candidates for the new ThorChain team assembly |
  - Serena: n/a
  - rg: Current b56232d worktree has no paperclips/projects/unstoppable directory
  - Anchors: paperclips/projects/unstoppable
| F-PC-003 | 1 | yes | MATCH | yes | serena+rg | E-0007 | valid | known_current | The current Trading project is a schema-v2 five-agent UAA family with host-local bindings and paths, topological reportsTo composition, generated managed bundles, and migration ... |
  - Serena: Current-tree symbol and file navigation confirmed the Trading manifest, builder, resolver, deployer, and migration tests at b56232d
  - rg: Targeted rg confirmed schemaVersion 2, five agents, reportsTo, codex_local target, host-local boundary comments, and Phase B/D/E test anchors
  - Anchors: paperclips/projects/trading/paperclip-agent-assembly.yaml, paperclips/scripts/build_project_compat.py, paperclips/scripts/resolve_bindings.py, paperclips/tests/test_phase_e_trading_migration.py
| F-PC-004 | 1 | yes | MATCH | yes | serena+rg | E-0004 | valid | known_current | The current Trading workflow implements a two-loop roadmap walker, a seven-phase child delivery loop, an integration-branch status marker, and atomic handoff semantics |
  - Serena: Serena confirmed outer loop, inner loop, Phase 1-7 table, QA routing, and atomic handoff sections in current Trading WORKFLOW and Codex overlay
  - rg: Targeted rg/read confirmed the same sections and exact status-marker and PATCH contract at b56232d
  - Anchors: paperclips/projects/trading/WORKFLOW.md, paperclips/projects/trading/overlays/codex/_common.md
| F-PC-005 | 1 | yes | MATCH | yes | serena+rg | E-0008, E-0009, E-0010 | valid | known_current | Current UAA bootstrap and deploy code accepts per-agent model and reasoning effort, hires in reportsTo order, deploys managed bundles, writes per-agent workspaces, and protects ... |
  - Serena: Serena confirmed current bootstrap and deploy symbol boundaries and callers
  - rg: Targeted rg/read confirmed model, modelReasoningEffort, adapterType, topological hire, workspace copy, SHA verification, safe backup, and restore branches
  - Anchors: paperclips/scripts/bootstrap-project.sh, paperclips/scripts/deploy_project_agents.py, paperclips/scripts/rollback.sh
| F-PC-006 | 1 | yes | MATCH | yes | serena+rg | n/a | valid | known_current | The current UAA rollback journal does not cover newly created companies, host-local bindings and paths, created workspace directories, or watchdog state |
  - Serena: Serena inspection found journal handlers only for agent instructions, plugin config, version bumps, and agent hires
  - rg: Targeted read of bootstrap-project.sh and rollback.sh confirmed company and filesystem creation without corresponding inverse journal kinds
  - Anchors: paperclips/scripts/bootstrap-project.sh, paperclips/scripts/rollback.sh
| F-PC-007 | 1 | yes | MATCH | yes | rg | n/a | valid | known_current | Installed local Paperclip 2026.618.0 supports explicit database backup, portable company export including company agents projects issues tasks and skills, portable import, and c... |
  - Serena: n/a
  - rg: Cached installed package source confirms version 2026.618.0, db:backup options, company export/import include sets, and CLI company delete confirmation contract
  - Anchors: /Users/ant013/.npm/_npx/43414d9b790239bb/node_modules/paperclipai/package.json, /Users/ant013/.npm/_npx/43414d9b790239bb/node_modules/paperclipai/dist/index.js
| F-PC-008 | 1 | yes | MATCH | yes | rg | n/a | valid | known_current | The preserved Unstoppable team is a five-agent codex_local Swift delivery topology with a true live CEO role, but its committed manifest maps CEO through the CTO profile and rol... |
  - Serena: n/a
  - rg: Five preserved agent JSON files show CEO/CTO/engineer/engineer/qa and codex_local; the preserved manifest and Swift craft show the five-agent Swift topology and CEO profile drift
  - Anchors: /Users/ant013/Data/AI/paperclip/backups/unstoppable-codex-2026-06-13/manifest.codex.yaml, /Users/ant013/Data/AI/paperclip/backups/unstoppable-codex-2026-06-13/cx-swift-engineer.md, /Users/ant013/Data/AI/paperclip/backups/unstoppable-codex-2026-06-13/CEO.agent.json
| F-PC-009 | 1 | yes | MATCH | yes | serena+rg | n/a | valid | known_current | The local Codex runtime is configured and running with model gpt-5.6-sol at xhigh reasoning, and Paperclip codex_local passes arbitrary manifest model IDs through to the adapter |
  - Serena: Serena confirmed bootstrap passes manifest model and reasoning effort into codex_local adapterConfig
  - rg: Local Codex config declares gpt-5.6-sol/xhigh; codex-cli reports 0.144.5; current bootstrap forwards model fields
  - Anchors: /Users/ant013/.codex/config.toml, paperclips/scripts/bootstrap-project.sh
| F-PC-010 | 1 | yes | MATCH | yes | rg | n/a | valid | known_current | The preserved Unstoppable execution history proves the outer blocker-based walker and seven-phase child loop, while also exposing four premature or incomplete delivery paths and... |
  - Serena: n/a
  - rg: 194 preserved NDJSON runs, materialized role bundles, ROADMAP/Git/PR evidence, and the durable analysis account for 12 roadmap children: 8 complete seven-phase cycles and 4 violations
  - Anchors: /Users/ant013/Data/AI/paperclip/instances/default/data/run-logs/dfc662ee-513f-42f7-9f46-23f07e0a98d0, /Users/ant013/Data/AI/thorchain/docs/research/paperclip-unstoppable-roadmap-walker-analysis.md
| F-PC-011 | 1 | yes | MATCH | yes | rg | n/a | valid | known_current | The newest existing SQL backup predates later database-directory writes and therefore cannot authorize deletion without a fresh pre-mutation backup |
  - Serena: n/a
  - rg: Newest backup paperclip-20260618-202325.sql.gz is 4366506 bytes at 20:23:27 +0600 with SHA-256 df229f..., while the database directory mtime is 21:03:46 +0600
  - Anchors: /Users/ant013/Data/AI/paperclip/instances/default/data/backups/paperclip-20260618-202325.sql.gz, /Users/ant013/Data/AI/paperclip/instances/default/db
| F-PC-012 | 1 | no | MATCH | yes | rg | n/a | valid | known_current | GitHub authentication has private-repository scope and ant013/ThorChainKit.Swift does not currently exist |
  - Serena: n/a
  - rg: gh auth status confirms account ant013 with repo scope; gh repo view returns repository not found
  - Anchors: ant013/ThorChainKit.Swift
| F-PC-013 | 1 | yes | MATCH | yes | serena+rg | n/a | valid | known_current | The current Trading walker assigns the outer roadmap loop to CTO and its atomic-handoff prose collapses evidence comment and reassignment into one PATCH, which conflicts with th... |
  - Serena: Serena confirmed CTO ownership in current outer-loop and Codex overlay sections and the single-PATCH atomic handoff section
  - rg: Targeted read confirmed Trading CTO outer ownership and PATCH-with-comment contract; preserved Unstoppable live history shows separate CEO and safer comment-before-transfer order
  - Anchors: paperclips/projects/trading/WORKFLOW.md, paperclips/projects/trading/overlays/codex/_common.md, /Users/ant013/Data/AI/thorchain/docs/research/paperclip-unstoppable-roadmap-walker-analysis.md
| F-PC-014 | 1 | yes | MATCH | yes | serena+rg | n/a | valid | known_current | TronKit.Swift is the closest repository scaffold analog: a Swift Package library with a test target and an iOS Example project, on a single integration branch |
  - Serena: Exact local Serena activation confirmed Package.swift library and test targets and README iOS Example contract
  - rg: Exact local git and filesystem checks confirmed master integration, Sources/TronKit, Tests/TronKitTests, and iOS Example project/workspace
  - Anchors: /Users/ant013/Ios/HorizontalSystems/TronKit.Swift/Package.swift, /Users/ant013/Ios/HorizontalSystems/TronKit.Swift/README.md, /Users/ant013/Ios/HorizontalSystems/TronKit.Swift/iOS Example
| F-PC-015 | 1 | yes | MATCH | yes | combined | E-0013, E-0014, E-0015 | valid | known_current | EvmKit.Swift independently confirms the Swift Package plus iOS Example convention, but its current Package.swift has no test target and both kit analogs use the legacy master br... |
  - Serena: n/a
  - rg: Exact local read confirmed library target and iOS Example, no testTarget, master default branch, and swift-tools-version 5.5
  - Anchors: /Users/ant013/Ios/HorizontalSystems/EvmKit.Swift/Package.swift, /Users/ant013/Ios/HorizontalSystems/EvmKit.Swift/README.md, /Users/ant013/Ios/HorizontalSystems/EvmKit.Swift/iOS Example

## Adversarial decisions

- D-PC-001@3 ACCEPT: Quiescence barrier remains accepted on normalized spec hash
- D-PC-002@3 ACCEPT: Model and bounded-worker proof remains accepted on normalized spec hash
- D-PC-003@3 ACCEPT: Source documentation preservation remains accepted on normalized spec hash
- D-PC-004@2 ACCEPT: Freshness and identity gates remain accepted on normalized spec hash
- D-PC-005@2 ACCEPT: Primary analog coherence remains accepted on normalized spec hash
- D-PC-006@2 ACCEPT: Inherited-defect guards remain accepted on normalized spec hash
- D-PC-007@2 ACCEPT: Bounded scope remains accepted on normalized spec hash
- D-PC-008@2 ACCEPT: Recovery and confidentiality remain accepted on normalized spec hash
- D-PC-009@2 ACCEPT: Test validity and minimality remain accepted on normalized spec hash

## Verification and acceptance


## Bugs and limitations

### GIMLE-PC-001: Initial Paperclip runbook query was broader than the response budget

- Class/severity/confidence/status: caller_error / low / confirmed / workaround
- Tool/events/claims: codebase-memory.search_code / E-0002 / n/a
- Reproduction: Search four broad adapter/deploy terms across paperclips and docs with limit 30
- Expected: Bounded compact candidate list
- Actual: 96 deduplicated results and output truncation
- Impact: No candidate may be accepted from the truncated tail
- Workaround: Use narrow path-specific current-tree searches and reads
- Anchors: paperclips/

### GIMLE-PC-002: Indexed Unstoppable assembly paths are absent from origin/develop

- Class/severity/confidence/status: stale_index / high / confirmed / workaround
- Tool/events/claims: codebase-memory.search_code / E-0003 / F-PC-001
- Reproduction: Search Unstoppable role names in indexed Users-ant013-Android-Gimle-Palace, then inspect paperclips/projects/unstoppable in clean b56232d worktree
- Expected: Indexed file candidates exist at the reported paths in the current repository tree or carry explicit stale metadata
- Actual: Index reports four paperclips/projects/unstoppable files; the directory does not exist at current origin/develop
- Impact: Using indexed candidates would place the ThorChain assembly on a nonexistent/stale project structure
- Workaround: Reject these paths; locate source through current git history, submodules, and server runbooks
- Anchors: paperclips/projects

### GIMLE-PC-003: Indexed search underfills current Trading assembly documentation

- Class/severity/confidence/status: coverage_gap / medium / confirmed / workaround
- Tool/events/claims: codebase-memory.search_code / E-0004 / n/a
- Reproduction: Search the indexed project for roadmap walker, two-loop, Phase 1, paperclip-agent-assembly, or bindings under ^paperclips/projects/trading/
- Expected: Matches from current Trading WORKFLOW, assembly, overlays, and binding examples
- Actual: Zero indexed matches while Serena and targeted rg find the files and matching text at current origin/develop
- Impact: A search-only workflow would miss the clean primary analog and could incorrectly conclude greenfield
- Workaround: Use Serena and targeted rg/current-tree reads for the Trading family
- Anchors: paperclips/projects/trading

### GIMLE-PC-004: Paperclip compatibility graph query exceeded bounded response

- Class/severity/confidence/status: coverage_gap / low / confirmed / workaround
- Tool/events/claims: codebase-memory.search_graph / E-0006 / n/a
- Reproduction: Search graph for build project compatibility resolve bindings deploy project agents at limit 30
- Expected: Bounded relation set sufficient for candidate evaluation
- Actual: 30 of 1253 rows returned with has_more/truncation
- Impact: Tail results cannot authorize analog selection
- Workaround: Use exact symbol snippets plus Serena and targeted current-tree reads
- Anchors: paperclips/scripts

### GIMLE-PC-005: Initial EvmKit project slug used the wrong punctuation

- Class/severity/confidence/status: caller_error / low / confirmed / fixed
- Tool/events/claims: codebase-memory.get_architecture / E-0011 / n/a
- Reproduction: Request Users-ant013-Ios-HorizontalSystems-EvmKit-Swift
- Expected: Use indexed slug Users-ant013-Ios-HorizontalSystems-EvmKit.Swift
- Actual: Project not found and available-project list returned
- Impact: No evidence from this failed call was used
- Workaround: Retry with exact indexed project name
- Anchors: /Users/ant013/Ios/HorizontalSystems/EvmKit.Swift

### GIMLE-PC-006: Local TronKit.Swift repository is not indexed

- Class/severity/confidence/status: coverage_gap / medium / confirmed / workaround
- Tool/events/claims: codebase-memory.get_architecture / E-0012 / F-PC-014
- Reproduction: Request architecture for the exact local TronKit repository
- Expected: Indexed architecture for a load-bearing kit scaffold analog
- Actual: No TronKit project exists among 51 indexed projects
- Impact: Gimle cannot provide freshness or graph evidence for the closest kit scaffold analog
- Workaround: Activate the exact local repository with Serena and cross-check with git and targeted rg
- Anchors: /Users/ant013/Ios/HorizontalSystems/TronKit.Swift

## Interpretation

Contradicted or unverifiable Gimle evidence was not accepted as repository truth. A verified fallback does not erase the defect.
