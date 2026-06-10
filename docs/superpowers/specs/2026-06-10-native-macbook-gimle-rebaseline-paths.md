# Native MacBook Gimle Rebaseline Paths

**Date:** 2026-06-10
**Base:** `develop` at `2bfaa2309af565613f491fcc0f9d1500e6cb8ded`
**Branch:** `docs/native-macbook-rebaseline-spec`

## Problem

The current operator surface still mixes three execution models:

- iMac/Docker Palace paths such as `/repos-hs` and `docker compose ... palace-mcp`.
- Old live working-copy paths such as `/Users/Shared/Ios/HorizontalSystems`.
- Native MacBook Palace paths using Homebrew Neo4j and `palace-mcp` on
  `http://127.0.0.1:8765/mcp`.

For the Gimle iOS rebaseline, the MacBook/native path must be authoritative:
native Neo4j, native `palace-mcp`, and dedicated source clones under
`/Users/Shared/Ios/Gimle-Repos/HorizontalSystems`. Extraction must not touch
live working repos under `/Users/Shared/Ios/HorizontalSystems`, and Android
repos are out of scope.

The required outcome is not documentation cleanup alone. The operator must be
able to perform a clean native rebaseline and prove it with real per-repository
and per-extractor counts from native Neo4j/Tantivy.

## Assumptions

- The iMac Docker path remains valid for iMac production/review deployment.
  This task must not remove Docker documentation globally.
- The MacBook rebaseline path must use native MCP calls and must not use scripts
  that implicitly run `docker compose up -d --force-recreate palace-mcp`.
- The dedicated iOS clone root is:
  `/Users/Shared/Ios/Gimle-Repos/HorizontalSystems`.
- The current iOS scope is limited to:
  `BitcoinCore.Swift`, `BitcoinKit.Swift`, `DashKit.Swift`, `EvmKit.Swift`,
  `component-kit-ios`, `hd-wallet-kit-ios`, and `unstoppable-wallet-ios`.
- Canonical project slugs for the seven-repo rebaseline are:
  `bitcoin-core`, `bitcoin-kit`, `dash-kit`, `evm-kit`, `component-kit`,
  `hd-wallet-kit`, and `uw-ios-app`.
- `embedding_symbol` should run through native `palace-mcp` because Docker CPU
  mode is memory-heavy and loses MPS acceleration.
- Rebaseline work must run sequentially: one repository/extractor step reaches a
  terminal state before the next step starts. No parallel extractor fan-out.

## Scope

Update operator-facing docs and scripts so MacBook/native rebaseline has a
single clear path:

- Document native MacBook rebaseline setup and verification.
- Add a native-only operator helper/runbook that calls MCP directly at
  `http://127.0.0.1:8765/mcp` instead of shelling through Docker compose.
- Add hard guardrails around old default paths so MacBook rebaseline commands
  fail before ingest if they resolve under `/Users/Shared/Ios/HorizontalSystems`
  or `/Users/ant013/Ios/uw-fresh-*`.
- Add target-scoped native cleanup for the seven iOS projects in native Neo4j
  and native Tantivy state, with before/after evidence.
- Preserve iMac Docker defaults where the script/runbook is explicitly iMac-only.
- Update smoke/rebaseline commands to use dedicated Gimle repos and native Neo4j.
- Produce a final native rebaseline report with real extractor, label, and
  occurrence-index counts.

## Out Of Scope

- Removing Docker support for iMac/review deployments.
- Extracting Android repos.
- Reworking extractor internals.
- Changing the Neo4j schema or deleting global volumes. Target-scoped cleanup
  for the seven rebaseline projects is in scope.
- Faking missing extractor inputs. Missing Periphery, `.swiftinterface`,
  `reactive_facts.json`, or profile inputs must remain visible in reports.
- Using `palace.memory.get_project_overview` as the proof source for rebaseline
  counts. Rebaseline proof must use direct native Neo4j/Tantivy evidence.

## Affected Areas

Likely affected files/areas:

- `docs/runbooks/native-macos-palace-mcp.md`
- `docs/runbooks/multi-repo-spm-ingest.md`
- `docs/runbooks/xcode-app-ingest.md`
- native startup docs/env references that determine
  `/Users/ant013/Android/Gimle-Palace-native/.env`
- `services/palace-mcp/scripts/launch_native_macos.sh`
- a new native-only rebaseline helper/script under `services/palace-mcp/scripts/`
- `services/palace-mcp/scripts/regen-uw-ios-scip.sh`
- `services/palace-mcp/scripts/smoke_uw_ios_bundle.py`
- `services/palace-mcp/scripts/_mcp_client.py` or replacement native MCP caller
- `paperclips/scripts/prepare_repo.sh`
- `paperclips/scripts/palace_ingest.sh`
- `paperclips/scripts/ingest_swift_kit.sh`
- `paperclips/scripts/ingest_xcode_app.sh`
- tests under `services/palace-mcp/tests/scripts/` if script defaults or mode
  selection changes.

## Design

1. Introduce an explicit MacBook/native profile in docs and scripts.
   - Native MCP URL: `http://127.0.0.1:8765/mcp`.
   - Native Neo4j: `bolt://localhost:7687`.
   - Dedicated repo root: `/Users/Shared/Ios/Gimle-Repos/HorizontalSystems`.
   - Canonical native env file:
     `/Users/ant013/Android/Gimle-Palace-native/.env`.
   - Parent mount compatibility: `/Users/ant013/Ios-hs` may point at the
     dedicated root when `PALACE_REPOS_ROOT=/Users/ant013/Ios`, but the
     authoritative source root remains
     `/Users/Shared/Ios/Gimle-Repos/HorizontalSystems`.

2. Use a native-only helper for the MacBook rebaseline.
   - Do not make existing Docker-first ingest scripts the default native path.
   - Existing Docker-oriented scripts should remain iMac/Docker scripts and be
     labeled as such.
   - The native helper must call MCP at `http://127.0.0.1:8765/mcp`, must not
     require `docker`, and must not run `docker compose`.
   - If a shared script gains native support later, native mode must be explicit
     and must hard-fail before any Docker action.

3. Keep Docker scripts iMac-safe, but prevent accidental MacBook misuse.
   - Existing Docker-oriented scripts should state they are iMac/Docker scripts.
   - Native docs should not instruct operators to call scripts that recreate
     Docker `palace-mcp`.
   - If a script supports both modes, make mode explicit and default conservatively.

4. Make old path usage impossible in native mode.
   - Update MacBook/native default path text away from
     `/Users/Shared/Ios/HorizontalSystems`.
   - Native helper must resolve all repo, symlink, and SCIP paths with
     `realpath`.
   - Native helper must abort if any target repo, symlink target, SCIP path, or
     env path resolves under `/Users/Shared/Ios/HorizontalSystems` or
     `/Users/ant013/Ios/uw-fresh-*`.

5. Define the exact seven-project native ingest surface.
   - Add a native project manifest/profile mapping:
     - `bitcoin-core` -> `BitcoinCore.Swift`
     - `bitcoin-kit` -> `BitcoinKit.Swift`
     - `dash-kit` -> `DashKit.Swift`
     - `evm-kit` -> `EvmKit.Swift`
     - `component-kit` -> `component-kit-ios`
     - `hd-wallet-kit` -> `hd-wallet-kit-ios`
     - `uw-ios-app` -> `unstoppable-wallet-ios`
   - The native profile must contain exactly these seven slugs.
   - Android slugs and Android repo roots must be rejected for this rebaseline.
   - Existing 41-member `uw-ios` bundle smoke can remain iMac/bundle-specific,
     but it must not be the native seven-repo acceptance gate.

6. Prove clone freshness and SCIP provenance before ingest.
   - Each dedicated clone must be fetched from origin and fast-forwarded or
     reported as unable to update.
   - Each clone must have a recorded branch, HEAD SHA, and working-tree status.
   - Each `scip/index.scip` must exist and be non-empty.
   - If an `index.scip.meta.json` or equivalent metadata file exists, its
     `repo_head_sha` must match the clone HEAD. If metadata is absent, the
     final report must state that provenance could not be verified.

7. Clean native target state before ingest.
   - Target-scoped native Neo4j cleanup must remove prior graph state for the
     seven project `group_id`s without deleting unrelated projects or global
     volumes.
   - Native Tantivy state for the target runs/projects must be empty or
     target-purged before ingest.
   - Cleanup must emit before/after counts for each target project.

8. Run extractors sequentially.
   - For each project, run the registered extractor cascade one extractor at a
     time.
   - Do not start the next extractor until the current extractor has a terminal
     result.
   - Do not start the next project until the current project has completed its
     planned extractor cascade.

9. Preserve factual reporting.
   - Reports must include per-extractor `IngestRun` success, `nodes_written`,
     `edges_written`, outcome/status, message/reason, and label counts from
     native Neo4j.
   - Reports must include occurrence-index/Tantivy counts where extractors write
     occurrence documents.
   - Extractors with missing real inputs must be reported as failed or
     zero-output with the concrete reason, not hidden.
   - `embedding_symbol` coverage must be explicit: report total eligible
     symbols, embedded symbols, and whether `PALACE_EMBEDDING_MAX_SYMBOLS` or
     another cap made the run incomplete.

## Acceptance Criteria

- A MacBook operator can follow one native rebaseline runbook without running
  `docker compose` for ingest.
- The native rebaseline path is a native-only helper/runbook, not the existing
  Docker-first ingest scripts as the default path.
- Native env verification proves:
  - `palace-mcp` health at `http://127.0.0.1:8765/healthz`.
  - Neo4j reachable at `bolt://localhost:7687`.
  - The loaded native env file is
    `/Users/ant013/Android/Gimle-Palace-native/.env`, not repo-local `.env`.
  - `PALACE_SCIP_INDEX_PATHS` for target slugs points only under
    `/Users/Shared/Ios/Gimle-Repos/HorizontalSystems`.
  - `/Users/ant013/Ios-hs` points to
    `/Users/Shared/Ios/Gimle-Repos/HorizontalSystems`.
- No MacBook/native instruction defaults to
  `/Users/Shared/Ios/HorizontalSystems` or `/Users/ant013/Ios/uw-fresh-*`.
- A negative guardrail check proves native mode aborts before ingest when a
  target path resolves under `/Users/Shared/Ios/HorizontalSystems`.
- The native project manifest/profile contains exactly seven iOS slugs:
  `bitcoin-core`, `bitcoin-kit`, `dash-kit`, `evm-kit`, `component-kit`,
  `hd-wallet-kit`, and `uw-ios-app`; it contains no Android slugs.
- Dedicated clones are current enough for ingest: each target has branch, HEAD
  SHA, origin URL, working-tree status, and SCIP provenance recorded.
- Native cleanup emits before/after Neo4j and Tantivy evidence for the seven
  target projects before ingest starts.
- Extractor execution is sequential, and the report records start/end time for
  each extractor step.
- Final report includes direct native Neo4j `IngestRun` evidence and label
  counts per project/extractor, plus occurrence-index counts where applicable.
- Missing inputs and capped/incomplete embeddings are visible and fail the full
  rebaseline gate unless explicitly classified as optional in the report.
- Docker/iMac runbooks remain explicitly labeled and not broken by the native
  updates.
- Relevant script tests or shell syntax checks pass.

## Verification Plan

- `rg` checks:
  - verify MacBook/native docs do not use old live repo paths;
  - verify Docker commands remain only in Docker/iMac sections;
  - verify no native rebaseline command invokes `docker compose`.
- Path guard checks:
  - `realpath` every target repo and SCIP path and confirm it is under
    `/Users/Shared/Ios/Gimle-Repos/HorizontalSystems`;
  - run one negative check where native mode is pointed at
    `/Users/Shared/Ios/HorizontalSystems` and verify it aborts before MCP calls.
- Script checks:
  - `bash -n` for changed shell scripts.
  - Existing targeted tests under `services/palace-mcp/tests/scripts/`.
- Native smoke:
  - `curl -s http://127.0.0.1:8765/healthz`.
  - `palace.ingest.list_extractors` through `http://127.0.0.1:8765/mcp`.
  - Native Neo4j `RETURN 1` through `bolt://localhost:7687`.
- Rebaseline proof:
  - cleanup before/after counts for each of the seven target `group_id`s;
  - exact seven-slug manifest check and no Android slug check;
  - clone freshness/provenance table;
  - sequential extractor run log;
  - direct Neo4j queries for `IngestRun` and label counts;
  - direct Tantivy/occurrence-index count evidence for occurrence-writing
    extractors.

## Resolved Review Decisions

- Use a new native-only rebaseline helper/runbook for the MacBook path. Do not
  make Docker-first ingest scripts the native default.
- Keep `/Users/ant013/Ios-hs` documented only as compatibility for current
  `PALACE_REPOS_ROOT=/Users/ant013/Ios` resolution. The authoritative clone root
  remains `/Users/Shared/Ios/Gimle-Repos/HorizontalSystems`.
- Full rebaseline evidence must state whether embeddings are capped. A capped
  `embedding_symbol` run is acceptable only as an explicitly incomplete run; a
  complete rebaseline requires embedded coverage for all eligible target symbols
  or a concrete failure reason.
