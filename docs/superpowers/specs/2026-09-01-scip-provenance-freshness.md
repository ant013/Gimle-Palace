# Swift SCIP Provenance and Freshness

Date: 2026-09-01

Branch: `fix/scip-provenance-freshness`

Base: `origin/develop` at `25e531cd91e7b60375801583626b46357f032557`

Status: Ready for review, revision 3 after adversarial boundary and same-HEAD artifact-replacement review; no implementation changes are included in the spec commit.

## Goal

Prevent Palace from accepting an old Swift SCIP artifact as if it represented the repository's current `HEAD`, make `palace.memory.get_project_overview` and the native stale detector report that condition honestly, and preserve the existing incremental Swift update algorithm after provenance has been validated.

## Problem Statement and Reproduction

`ensure_swift_scip_artifact` already detects missing or mismatched metadata, including a `repo_head_sha` mismatch. It nevertheless returns a stale artifact when `--emit-scip=never` is selected, and also returns the stale artifact when automatic emission cannot run on the current host.

`SymbolIndexSwift.run` then parses that old artifact, reads the repository's current `HEAD`, hashes only paths present in the old SCIP document set, and persists a successful baseline stamped with the current commit. `_record_project_indexed_commit` copies that commit to `:Project`. This creates two false-current read paths:

- `get_project_overview` compares the falsely stamped `Project.indexed_commit` with the repository `HEAD` and reports current.
- `detect_project_stale_files` examines only `:File` rows produced from the old SCIP document set, so newly added files absent from that artifact are invisible.

The existing tests `test_ensure_swift_scip_artifact_never_succeeds_with_missing_metadata` and `test_ensure_swift_scip_artifact_never_succeeds_with_stale_sha` reproduce and currently approve the fail-open behavior.

A second failure exists during repair: regenerating SCIP at the same repository `HEAD` makes metadata current immediately, but the stored graph/Tantivy state still represents the old bytes. The durable Swift baseline already stores `scip_digest`, yet the current fast-skip decision compares only commit and source body-hash manifest. If paths and source bodies are unchanged, Palace can skip the replacement artifact and report current without ever consuming it.

## Assumptions

- Swift Palace artifacts use `scip/index.scip` with adjacent `scip/index.scip.meta.json`; an explicitly supplied alternative SCIP path uses the same `<artifact>.meta.json` convention.
- `repo_head_sha` in valid metadata is the commit represented by the complete SCIP artifact.
- Host and container repository paths may legitimately differ across a configured Docker or staged mount. Full path/host provenance is enforceable while preparing an artifact on the host; artifact consumption must instead bind the metadata slug and commit to the mounted project and its Git `HEAD`.
- Missing, invalid, or mismatched provenance is not safe for either full or incremental ingest.
- A failed provenance precondition may create/finalize an operational `IngestRun` error record, but must not mutate symbols, files, Tantivy documents, the valid extractor baseline, or `Project.indexed_commit`.
- Non-Swift profiles and non-Swift SCIP extractors are outside this change.
- The three affected repositories will be regenerated/re-ingested only after the fix is implemented, verified, and deployed; this change does not invent graph data for an old artifact.

## Scope

### In scope

1. Extract the existing Swift metadata load/validation primitives into a small shared provenance module usable by CLI, extractor, overview, and stale detection, with explicit preparation and consumption policies.
2. Resolve repository `HEAD` with `git rev-parse HEAD`, including linked Git worktrees where `.git` is a file.
3. Make CLI artifact preparation fail closed when a stale artifact cannot or must not be regenerated.
4. Add a defense-in-depth provenance gate to `SymbolIndexSwift.run` before SCIP parsing or product-state mutation.
5. Compose overview freshness with canonical Swift SCIP provenance so a falsely current graph baseline cannot report current.
6. Make the native stale detector set a project-level re-ingest reason for missing, invalid, or stale Swift SCIP provenance, independently of its existing per-file checks.
7. Require current artifact digest parity with the durable Swift baseline before fast-skip or a current read result; a replacement artifact at the same `HEAD` receives one safe full reprocess.
8. Update and extend unit/integration fixtures so current-artifact tests provide metadata for their actual Git commit.
9. Add regression coverage proving the validated path still performs incremental changed/added/removed processing, refreshes unchanged-symbol liveness, and retains existing full-mode fallbacks.

### Out of scope

- Rewriting the incremental planner, change-ratio threshold, body-hash algorithm, delta-resolution capture, pruning, or Tantivy/Neo4j write strategy. The only skip-planning delta is that changed SCIP bytes cannot be treated as an unchanged snapshot.
- A broad filesystem inventory in the stale detector.
- Changing provenance requirements for Java, Kotlin, TypeScript, Python, Solidity, or Clang indexes.
- Automatically deleting or regenerating repository artifacts during overview or stale-detector reads.
- Deploying or re-ingesting repositories in the spec-only phase.

## Selected Analog Family

### Provenance and honest freshness

The primary contract is the existing `swift_scip_metadata_needs_regeneration` behavior: provenance is current only when commit, emitter, package, destination, and local/remote origin rules match. `ensure_swift_scip_artifact` remains the preparation/composition point, but its stale reuse branches are rejected. `inspect_freshness` supplies the read-time fail-honest pattern: current requires positive evidence, while invalid or unavailable evidence never becomes current.

The rejected counterexample is the current `ensure_swift_scip_artifact` stale reuse path and the two tests that assert it succeeds.

### Incremental preservation

The primary implementation spine remains `SymbolIndexSwift.run`. Its current incremental gates—`force`, incremental setting, change ratio, durable previous baseline commit, Git diff, SCIP/body-hash agreement, and bounded fallback—remain unchanged after provenance succeeds. `_derive_incremental_graph_scope` supplies the changed/added/removed contract. The two-run integration test supplies the unchanged-symbol liveness and non-deprecation contract. The existing durable `scip_digest` field supplies the additional snapshot-identity invariant needed before fast-skip.

The negative control is the current change-threshold test: it must continue to select a full reprocess even when incremental mode is enabled.

## Proposed Design

### 1. Shared Swift SCIP provenance contract

Add a focused module under `palace_mcp` containing:

- the Swift emitter name/version constants currently private to `cli.py`;
- metadata path derivation and JSON loading;
- worktree-safe `git rev-parse HEAD` resolution;
- a typed immutable inspection result carrying `current`, `reason`, `repo_head_sha`, `artifact_commit_sha`, artifact digest, metadata path, and loaded metadata;
- a strict preparation policy retaining the existing local/`remote_copy`, source/destination path, and generator-host validation rules;
- a consumption policy requiring matching project slug, emitter/version, package kind, non-empty source/destination provenance, and artifact commit equal to the mounted repository `HEAD`, while allowing the configured host/container path translation;
- a helper that raises a caller-appropriate typed error only after inspection has produced a non-current result.

The policy choice is explicit at each call site; it is not inferred from an arbitrary path. The helper will not silently accept an explicit SCIP override, a test fixture, a metadata slug for another project, missing metadata, an unreadable Git `HEAD`, or an unknown emitter. Tests must construct valid provenance instead of bypassing the contract.

### 2. Fail-closed CLI preparation

Keep the current `always` behavior: emit and return a newly generated artifact.

For `never`, require both a non-empty artifact and current provenance. A missing/invalid/stale metadata result raises `ProjectAnalyzeCliError` with a stable machine-readable error code such as `stale_scip_artifact` and a message containing the inspection reason.

For `auto`, attempt emission when the artifact is unusable or provenance is not current. If emission is unavailable or fails, propagate the typed failure and fallback command; do not return the stale artifact. A current existing artifact remains reusable.

### 3. Extractor mutation boundary

After obtaining settings and resolving `scip_path`, `SymbolIndexSwift.run` applies the consumption policy against `ctx.project_slug` and `ctx.repo_path` before `ensure_custom_schema`, extractor-owned `create_ingest_run`, `parse_scip_file`, hash building, graph refresh, Tantivy writes, or valid-baseline persistence. The outer runner may still finalize its operational error record. A non-current result raises a structured extractor error with a distinct SCIP-provenance code and recovery guidance to regenerate the artifact, then retry.

The commit used for occurrences and the new baseline is the validated repository/artifact commit. Replace the direct `.git/HEAD` reader with the shared worktree-safe result. This prevents an old artifact from being stamped with a new repository commit.

Compute the current artifact digest once and pass it through baseline/skip decisions. Fast skip requires all three identities to match the durable baseline: commit, source body-hash manifest, and SCIP digest. When commit and source bodies match but SCIP digest differs, bypass the existing reconciliation/skip return and run a full symbol reprocess; no file delta can safely describe an opaque snapshot replacement. Persist the new digest only after that run succeeds. Conditions inside the existing changed/added/removed incremental planner do not change.

### 4. Honest overview for existing false baselines

For a registered `swift_kit` project with a resolved repository path, `get_project_overview` first computes its existing Git/index freshness, inspects canonical Swift SCIP provenance, and reads the durable Swift symbol baseline identity.

- If Git/index commit, artifact metadata commit, and durable baseline commit/digest all match the repository and current artifact, return the existing current result.
- If the artifact commit differs from repository `HEAD`, return `stale=true`, do not report `current_local_tree`, and expose a stable reason such as `scip_repo_head_sha_mismatch`.
- If metadata is current but the durable baseline is missing, invalid, or carries another SCIP digest, return stale/unknown with a stable baseline parity reason until a successful re-ingest consumes the artifact.
- If provenance cannot establish currency because metadata/Git/artifact is missing or invalid, return unknown rather than current, with the provenance reason.
- Preserve the graph's authoritative `indexed_commit` field for diagnosis; do not rewrite persistence during a read.

Non-Swift projects retain the existing behavior.

### 5. Project-level stale detection

For a `swift_kit` project, `detect_project_stale_files` inspects canonical Swift SCIP provenance and durable baseline digest parity after repository resolution. A non-current or not-yet-consumed artifact sets `requires_reingest=true` and a project-level reason, even when all existing indexed files have unchanged bodies. Existing per-file stale, metadata-only, ignored, and error classification remains intact.

This intentionally does not enumerate repository files: the missing-new-file bug is detected through the artifact's stale commit contract, which is cheaper and matches the actual source of truth.

## Delta Matrix

| Area | Preserved invariant | Required delta | Failure mode prevented | Verification |
|---|---|---|---|---|
| Shared provenance | Existing emitter/path/local/remote metadata rules | Make validation reusable with explicit preparation and mount-aware consumption policies | Divergent validation or rejection of valid host/container path translation | Shared-helper unit tests for current, missing, malformed, wrong slug/commit/path/host, remote copy, linked worktree, and translated mount paths |
| CLI `never` | A usable artifact is required | Also require current provenance; raise typed error otherwise | Explicit reuse of stale bytes | Invert the two current fail-open tests and assert no analyze request |
| CLI `auto` | Regenerate missing/stale artifacts | Propagate emission/toolchain failure instead of stale reuse | Fallback silently corrupts baseline | Unit test stale artifact plus unsupported toolchain |
| Swift extractor | Existing structured error handling | Validate before extractor-owned lifecycle/schema/product writes and use validated commit | Old SCIP stamped with current `HEAD` through direct MCP/extractor entry | Unit test asserts schema, parse, writers, and baseline are untouched on mismatch while the outer runner reports the error |
| Fast skip / repair | Commit and body-hash parity identify unchanged source | Also require stored/current SCIP digest parity; full reprocess opaque replacement bytes | Regenerated same-HEAD artifact is never consumed | Unit/integration test replaces SCIP only, observes full processing, then observes a subsequent true skip |
| Overview | Git/index equality is required for current | Conjoin equality with Swift artifact provenance and durable baseline digest parity | False `current_local_tree` before or after artifact regeneration | Overview tests with `Project.indexed_commit == HEAD` plus old metadata, then current metadata/new digest with old baseline |
| Stale detector | Existing indexed-file body checks | Add project-level Swift provenance/baseline parity reason | New source absent from old SCIP or unconsumed replacement remains invisible | Detector tests with unchanged indexed row plus old metadata and with current metadata/new digest plus old baseline |
| Incremental changed/added/removed | Git/SCIP/body-hash agreement controls scoped writes | No planner change; supply matching metadata in fixtures | Provenance fix accidentally disables or broadens incremental updates | Unit scope tests and two-commit integration test |
| Unchanged symbols | Liveness refresh prevents accidental deprecation | No behavioral change | Incremental run deprecates or rewrites unchanged symbols | Existing integration assertions remain green |
| Safety fallback | Threshold/mismatch/truncation force full mode | No behavioral change | Provenance gate forces incremental or removes fallback | Existing threshold and mismatch tests remain green |

## Affected Files and Areas

Expected production areas:

- `services/palace-mcp/src/palace_mcp/cli.py`
- `services/palace-mcp/src/palace_mcp/extractors/symbol_index_swift.py`
- `services/palace-mcp/src/palace_mcp/extractors/foundation/errors.py`
- `services/palace-mcp/src/palace_mcp/memory/project_tools.py`
- `services/palace-mcp/src/palace_mcp/ops/detect_stale_files.py`
- one new focused shared Swift SCIP provenance module under `services/palace-mcp/src/palace_mcp/`

Expected test areas:

- `services/palace-mcp/tests/test_project_analyze_cli.py`
- `services/palace-mcp/tests/extractors/unit/test_symbol_index_swift.py`
- `services/palace-mcp/tests/extractors/integration/test_symbol_index_swift_integration.py`
- `services/palace-mcp/tests/memory/test_project_tools.py`
- `services/palace-mcp/tests/ops/test_detect_stale_files.py`
- a focused unit test file for the shared provenance module if that keeps cases smaller than the existing CLI test file

No implementation file outside these areas should change unless a failing relevant test exposes a direct dependency; any expansion requires a spec revision before implementation.

## Acceptance Criteria

1. A Swift SCIP artifact with missing, malformed, or mismatched metadata cannot reach symbol parsing or product-state mutation through project-analyze, direct extractor invocation, or an explicit SCIP path.
2. `--emit-scip=never` returns a typed failure for stale provenance; `auto` never reuses stale bytes after an emitter/toolchain failure.
3. A valid local artifact and a valid `remote_copy` artifact at current `HEAD` remain accepted.
4. Git `HEAD` resolution works in a normal checkout and a linked worktree; a valid configured host/container path translation does not cause a false rejection.
5. A provenance failure does not run extractor schema setup, advance the valid Swift extractor baseline or `Project.indexed_commit`, or mutate Neo4j/Tantivy product data; the outer runner still returns a structured failure.
6. Overview cannot report `current_local_tree` when canonical Swift SCIP metadata represents another commit; unavailable provenance is unknown, not current.
7. Overview remains non-current after same-HEAD artifact regeneration until the valid durable baseline stores the current artifact digest.
8. The stale detector returns `requires_reingest=true` with a stable project-level reason for stale provenance or artifact/baseline digest mismatch even when all indexed file rows are unchanged.
9. Replacing SCIP bytes at the same `HEAD` with unchanged source bodies performs one full reprocess, updates the baseline digest only after success, and permits a later identical run to fast-skip.
10. Non-Swift overview and stale-detector behavior is unchanged.
11. With valid metadata and matching prior artifact lineage, a small two-commit Swift change still uses incremental mode: changed and added files are rewritten, removed files are removed, and unchanged symbols are retained, marked live in the new run, and not deprecated.
12. Existing full-mode fallbacks for threshold exceedance, truncated Git diff, missing baseline, SCIP path mismatch, and body-hash mismatch remain intact.
13. No test-only or explicit-path bypass exists in production provenance validation.

## Verification Plan

### Focused red/green tests

- Reproduce the current CLI fail-open cases, invert them to typed failures, and verify the analyze call does not start.
- Add shared provenance cases for valid/missing/malformed/stale metadata, wrong project slug, local/remote origin, destination mismatch, Git failure, linked-worktree `HEAD`, and valid configured mount translation.
- Add an extractor test proving stale provenance fails before schema setup, extractor-owned ingest creation, `parse_scip_file`, Tantivy calls, graph refresh, or baseline persistence, while runner error finalization remains observable.
- Add a same-HEAD replacement test: start from a baseline whose source-body digest matches but SCIP digest differs, assert a full graph/Tantivy reprocess and successful digest update, then assert the next identical run can skip.
- Add overview and detector regression tests for a falsely current Project baseline paired with old SCIP metadata and for current metadata/new artifact bytes paired with the old baseline digest.

### Incremental regression matrix

- Run the existing changed-only unit test with valid metadata and assert only the changed path is replaced.
- Retain/add direct scope assertions for changed, added, and removed paths.
- Run the two-commit integration test with metadata rewritten for each commit; retain assertions for two second-run writes, unchanged symbol liveness, and non-deprecation.
- Run the threshold, truncation, SCIP mismatch, body-hash mismatch, and missing-baseline full-fallback tests.

### Repository checks

From `services/palace-mcp`:

```bash
uv run --isolated --python 3.12 --frozen ruff check src tests
uv run --isolated --python 3.12 --frozen ruff format --check src tests
uv run --isolated --python 3.12 --frozen mypy src/
uv run --isolated --python 3.12 --frozen pytest -q
```

Because the change touches shared extractor and freshness infrastructure, the full Palace MCP test suite is required before deployment. Native runtime deployment and the three repository re-ingests happen only after tests pass.

### Post-deployment observation

1. Before re-ingest, verify overview and stale detection report the three affected Swift repositories as stale/unknown for the provenance reason rather than current.
2. Regenerate SCIP artifacts at each repository's current `HEAD`.
3. Verify overview and stale detection remain non-current when the regenerated artifact digest does not yet match the durable baseline.
4. Run repository analysis normally. A same-HEAD repaired artifact may intentionally use one full reprocess for `scip_digest_mismatch`; otherwise confirm the response mode remains `incremental` when each safe delta is below the existing threshold and accept full mode only for an existing documented fallback reason.
5. Confirm overview reports current only after the successful validated ingest and stale detection no longer requires re-ingest.

## Rollback

Rollback the Palace code deployment without deleting repository SCIP files or extractor baselines. The change does not migrate schema or rewrite stored data during reads. If deployment verification fails, keep the affected repositories marked for re-ingest and do not run a stale artifact through the old fail-open path.

## Open Questions

None. The design deliberately chooses strict provenance for production and tests, canonical read-time inspection plus durable artifact/baseline parity for Swift projects, one safe full reprocess for opaque same-HEAD artifact replacement, and no changes inside the changed/added/removed incremental planner.
