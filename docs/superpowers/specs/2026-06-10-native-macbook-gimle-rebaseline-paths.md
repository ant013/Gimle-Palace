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

## Assumptions

- The iMac Docker path remains valid for iMac production/review deployment.
  This task must not remove Docker documentation globally.
- The MacBook rebaseline path must prefer native MCP calls over scripts that
  implicitly run `docker compose up -d --force-recreate palace-mcp`.
- The dedicated iOS clone root is:
  `/Users/Shared/Ios/Gimle-Repos/HorizontalSystems`.
- The current iOS scope is limited to:
  `BitcoinCore.Swift`, `BitcoinKit.Swift`, `DashKit.Swift`, `EvmKit.Swift`,
  `component-kit-ios`, `hd-wallet-kit-ios`, and `unstoppable-wallet-ios`.
- `embedding_symbol` should run through native `palace-mcp` because Docker CPU
  mode is memory-heavy and loses MPS acceleration.

## Scope

Update operator-facing docs and scripts so MacBook/native rebaseline has a
single clear path:

- Document native MacBook rebaseline setup and verification.
- Add or update native-safe operator scripts/helpers that call MCP directly at
  `http://127.0.0.1:8765/mcp` instead of shelling through Docker compose.
- Add guardrails around old default paths so MacBook rebaseline commands do not
  silently use `/Users/Shared/Ios/HorizontalSystems` or
  `/Users/ant013/Ios/uw-fresh-*`.
- Preserve iMac Docker defaults where the script/runbook is explicitly iMac-only.
- Update smoke/rebaseline commands to use dedicated Gimle repos and native Neo4j.

## Out Of Scope

- Removing Docker support for iMac/review deployments.
- Extracting Android repos.
- Reworking extractor internals.
- Changing the Neo4j schema or deleting global volumes.
- Faking missing extractor inputs. Missing Periphery, `.swiftinterface`,
  `reactive_facts.json`, or profile inputs must remain visible in reports.

## Affected Areas

Likely affected files/areas:

- `docs/runbooks/native-macos-palace-mcp.md`
- `docs/runbooks/multi-repo-spm-ingest.md`
- `docs/runbooks/xcode-app-ingest.md`
- `services/palace-mcp/scripts/regen-uw-ios-scip.sh`
- `services/palace-mcp/scripts/smoke_uw_ios_bundle.py`
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
   - Parent mount compatibility: `/Users/ant013/Ios-hs` must point at the
     dedicated root when `PALACE_REPOS_ROOT=/Users/ant013/Ios`.

2. Keep Docker scripts iMac-safe, but prevent accidental MacBook misuse.
   - Existing Docker-oriented scripts should state they are iMac/Docker scripts.
   - Native docs should not instruct operators to call scripts that recreate
     Docker `palace-mcp`.
   - If a script supports both modes, make mode explicit and default conservatively.

3. Make old path usage visible.
   - Update default path text away from `/Users/Shared/Ios/HorizontalSystems`
     for MacBook/native rebaseline.
   - Add checks or runbook verification that active env does not contain
     `/Users/Shared/Ios/HorizontalSystems` or `/Users/ant013/Ios/uw-fresh-*`
     for the target slugs.

4. Preserve factual reporting.
   - Reports must include per-extractor `IngestRun` success, `nodes_written`,
     `edges_written`, and label counts from native Neo4j.
   - Extractors with missing real inputs must be reported as failed or
     zero-output with the concrete reason, not hidden.

## Acceptance Criteria

- A MacBook operator can follow one native rebaseline runbook without running
  `docker compose` for ingest.
- Native env verification proves:
  - `palace-mcp` health at `http://127.0.0.1:8765/healthz`.
  - Neo4j reachable at `bolt://localhost:7687`.
  - `PALACE_SCIP_INDEX_PATHS` for target slugs points only under
    `/Users/Shared/Ios/Gimle-Repos/HorizontalSystems`.
  - `/Users/ant013/Ios-hs` points to
    `/Users/Shared/Ios/Gimle-Repos/HorizontalSystems`.
- No MacBook/native instruction defaults to
  `/Users/Shared/Ios/HorizontalSystems` or `/Users/ant013/Ios/uw-fresh-*`.
- Docker/iMac runbooks remain explicitly labeled and not broken by the native
  updates.
- Relevant script tests or shell syntax checks pass.

## Verification Plan

- `rg` checks:
  - verify MacBook/native docs do not use old live repo paths;
  - verify Docker commands remain only in Docker/iMac sections;
  - verify no native rebaseline command invokes `docker compose`.
- Script checks:
  - `bash -n` for changed shell scripts.
  - Existing targeted tests under `services/palace-mcp/tests/scripts/`.
- Native smoke:
  - `curl -s http://127.0.0.1:8765/healthz`.
  - `palace.ingest.list_extractors` through `http://127.0.0.1:8765/mcp`.
  - Direct MCP registration/run for one small target after approval.

## Open Questions

- Should the native helper be a new script, or should existing ingest scripts gain
  an explicit `--native` mode?
- Should the checked-in docs mention the operator-specific symlink
  `/Users/ant013/Ios-hs`, or should this be generalized via env examples?
- Should `PALACE_EMBEDDING_MAX_SYMBOLS` remain uncapped for final native
  embedding, or should reports explicitly use a bounded cap for repeatability?
