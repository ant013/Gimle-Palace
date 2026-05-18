# Project Analyze Orchestrator

**Date:** 2026-05-14
**Status:** draft, amended after review
**Branch:** `feature/GIM-NN-project-analyze-orchestrator`
**Owner:** operator + Codex

## Problem

The current `tron-kit` smoke path is still too operator-shaped:

- Generate Swift SCIP with `paperclips/scripts/scip_emit_swift_kit.sh`.
- Ensure Docker mounts expose the repo and `scip/index.scip`.
- Register the project and bundle through MCP.
- Run a default extractor cascade through MCP.
- Run `palace.audit.run`.
- Manually inspect Memory Palace / audit output.

This proves the pieces, but not the product promise. The desired UX is:

> Give Gimle a repository path and project metadata; Gimle starts the local
> runtime, registers the project, runs analysis, writes Memory Palace facts,
> produces an audit report, and exposes the result through MCP.

## Assumptions

- V1 production smoke runs against the iMac Docker runtime. The primary repo
  path is `/Users/Shared/Ios/HorizontalSystems/TronKit.Swift` and the primary
  Gimle checkout is `/Users/Shared/Ios/Gimle-Palace`.
- V1 supports exactly one hybrid fallback: when iMac cannot emit Swift SCIP
  because Xcode/macOS is too old, a dev Mac/MacBook may emit SCIP and copy
  `scip/index.scip` plus `scip/index.scip.meta.json` to the iMac repo path
  before the iMac Docker analysis continues.
- Arbitrary remote orchestration is out of scope. V1 does not manage remote
  cloning, remote Docker over SSH, generic file sync, or multi-host lifecycle
  beyond the bounded MacBook SCIP emit -> iMac copy fallback.
- The host CLI talks to Docker-published MCP at `http://localhost:8080/mcp` by
  default. In-container port `8000` is not the host default.
- Swift SCIP is visible to the MCP container only after the host command updates
  `PALACE_SCIP_INDEX_PATHS` to include `{slug: container_scip_path}` and
  recreates `palace-mcp` when the env mapping changes.
- `language_profile` already exists as `:Project.language_profile`; this feature
  must use that field, not invent a parallel storage path.

## Goals

- Provide a single host-side command for local operator use:
  `palace project analyze --repo-path ... --slug ...`.
- Provide MCP-facing orchestration for already-mounted repositories through an
  `AnalysisRun` contract with progress/status/resume semantics.
- Reuse the existing MCP primitives instead of duplicating extractor logic:
  `palace.memory.register_project`, `palace.memory.register_bundle`,
  `palace.memory.add_to_bundle`, `palace.ingest.run_extractor`,
  `palace.audit.run`, `palace.memory.get_project_overview`.
- Make the command suitable for the full `tron-kit` smoke after GIM-283:
  default `swift_kit` extractor set, full audit, explicit status summary, and
  report output path.
- Keep Memory Palace access first-class: after the run, the user can query the
  same data through `palace.memory.*`, `palace.ingest.*`, and `palace.audit.*`
  from their MCP client.

## Non-goals

- Replacing individual extractor implementations.
- Hiding all platform prerequisites. For Swift SCIP generation, local Xcode and
  `xcrun swift` are still required.
- Running arbitrary host shell commands from the MCP server without an explicit
  host-side command. The MCP server may live inside Docker; it cannot bootstrap
  the container that hosts itself.
- Solving arbitrary remote orchestration. Only the MacBook SCIP emit -> iMac
  copy fallback is in scope.
- Keeping a single blocking MCP request open for the entire extractor cascade.

## Scope

This slice changes the production iMac analysis orchestration contract:

- Host CLI for iMac repo path analysis.
- Docker mount and `.env` SCIP visibility management needed by that CLI on
  iMac.
- Optional MacBook SCIP emit fallback that copies artifacts to the iMac repo
  path before iMac Docker analysis.
- MCP `AnalysisRun` start/status/resume surface.
- Ordered `swift_kit` profile source of truth.
- Tests, runbook, and `tron-kit` smoke verification.

It does not change extractor internals except where profile ordering or
orchestration glue requires small adapter changes.

## Architecture

### Host-side command

Add a CLI command under `services/palace-mcp/src/palace_mcp/cli.py`:

```bash
uv run --directory services/palace-mcp python -m palace_mcp.cli project analyze \
  --repo-path /Users/Shared/Ios/HorizontalSystems/TronKit.Swift \
  --slug tron-kit \
  --bundle uw-ios \
  --language-profile swift_kit \
  --emit-scip auto \
  --depth full \
  --url http://localhost:8080/mcp \
  --report-out docs/audit-reports/2026-05-14-tron-kit-rerun.md
```

Responsibilities:

1. Validate iMac repo path, slug, and iMac Docker execution model.
2. For SwiftPM repos, optionally generate `scip/index.scip` when missing or
   stale (`--emit-scip auto|always|never`) on iMac.
3. If iMac SCIP emit fails because the toolchain is unsupported, fail with a
   structured `SCIP_EMIT_TOOLCHAIN_UNSUPPORTED` result that includes the exact
   MacBook fallback command using `paperclips/scripts/scip_emit_swift_kit.sh`.
   The fallback command emits on MacBook and copies SCIP artifacts to
   `/Users/Shared/Ios/HorizontalSystems/<relative_path>/scip/` on iMac. After
   fallback succeeds, rerun the iMac command with `--emit-scip never` or
   `--emit-scip auto` so the iMac analysis consumes the copied SCIP.
4. Create or update a deterministic Docker Compose override that mounts the
   repo under a container-visible parent mount.
5. Compute the container SCIP path, normally
   `{container_repo_path}/scip/index.scip`.
6. Update `.env` `PALACE_SCIP_INDEX_PATHS` by merging the new
   `{slug: container_scip_path}` entry without deleting existing entries.
7. Start the iMac Gimle runtime with `docker compose --profile review up -d`;
   recreate `palace-mcp` when mount or env changes require it.
8. Wait for `/healthz`.
9. Compute a stable idempotency key from slug, language profile, repo HEAD SHA,
   depth, extractor list, and container repo path.
10. Start the MCP analysis run and poll status until terminal state. If the
   previous CLI process lost its response, a repeat invocation with the same
   inputs must recover the existing active run instead of starting a duplicate.
11. Save the report markdown and machine-readable summary.

The host default URL for this command is `http://localhost:8080/mcp`. Existing
subcommands may keep their current default only if tests make the distinction
explicit; the product smoke command must not silently target `localhost:8000`.

For `--emit-scip auto`, staleness is defined by
`scip/index.scip.meta.json`. The metadata must include repo HEAD SHA, emitter
name/version, generated timestamp, package path, generator host name, source
repo path, and destination iMac repo path.
`auto` regenerates SCIP when the index is missing, empty, unreadable, metadata
is missing/invalid, repo HEAD SHA changed, emitter version changed, package path
changed, source repo path changed, destination repo path changed, or generator
host changed. `always` ignores metadata and regenerates. `never` fails fast when
a usable SCIP index and metadata are absent.

### MCP orchestration tools

Add native MCP tools around an `AnalysisRun` model. Required parameters are
keyword-only to keep the Python signature valid:

```python
async def palace_project_analyze(
    *,
    slug: str,
    parent_mount: str,
    relative_path: str,
    language_profile: str,
    name: str | None = None,
    bundle: str | None = None,
    extractors: list[str] | None = None,
    depth: Literal["quick", "full"] = "full",
    continue_on_failure: bool = True,
    idempotency_key: str | None = None,
    force_new: bool = False,
) -> dict[str, Any]:
    ...

async def palace_project_analyze_status(
    *,
    run_id: str,
) -> dict[str, Any]:
    ...

async def palace_project_analyze_resume(
    *,
    run_id: str,
) -> dict[str, Any]:
    ...
```

`palace.project.analyze` starts or resumes an analysis run and returns quickly
with `run_id`, initial checkpoints, and the next polling hint. It must not hold
one MCP/HTTP request open while all extractors and audit run. The host CLI polls
`palace.project.analyze_status` and may call `palace.project.analyze_resume`
after interruption.

`AnalysisRun` state is durable in Neo4j. The implementation must create
`:AnalysisRun` nodes and per-extractor checkpoint data, either as
`:AnalysisCheckpoint` nodes or as structured checkpoint properties on the run.
The durable state must include `run_id`, `slug`, `language_profile`, `bundle`,
`extractors`, `depth`, `idempotency_key`, `status`, `created_at`, `updated_at`,
`started_at`, `finished_at`, `lease_owner`, `lease_expires_at`,
`last_completed_extractor`, checkpoint statuses, checkpoint `ingest_run_id`
values, and final audit/report payload references. Terminal runs are retained
for audit provenance in V1; automatic cleanup is out of scope.

Allowed run statuses:

- Active: `PENDING`, `RUNNING`, `RESUMABLE`.
- Terminal: `SUCCEEDED`, `SUCCEEDED_WITH_FAILURES`, `FAILED`, `CANCELED`.

Only one active `AnalysisRun` may exist per `(slug, language_profile)`.
Concurrent `palace.project.analyze` calls for the same pair must not start a
second extractor cascade. This requires an atomic Neo4j lock pattern, not a
read-then-create check. The implementation must acquire or create an
`:AnalysisLock {key: "<slug>|<language_profile>"}` in the same write
transaction that creates or reuses the `:AnalysisRun`. If the idempotency key
matches, return the existing active run with `active_run_reused=true`. If a
different active run exists, return an `ACTIVE_ANALYSIS_RUN_EXISTS` error with
the existing `run_id`. `force_new=true` may create a new run only after the
previous run is terminal; it must not override an active run.

After MCP process restart, `palace.project.analyze_status` must read Neo4j and
return the last durable checkpoint. If a run was `RUNNING` but its lease expired,
status becomes `RESUMABLE`. `palace.project.analyze_resume` reacquires the lease
and continues from the next uncompleted extractor. Re-running the host CLI after
a lost response should pass the same idempotency key and recover the existing
run instead of starting a duplicate.

Responsibilities:

1. Register/update `:Project` with `parent_mount`, `relative_path`, and existing
   `language_profile` property.
2. Register bundle and add membership when `bundle` is provided.
3. Resolve extractor defaults from `language_profile`.
4. For `swift_kit`, use a single ordered source of truth in Python, not a
   copied shell-list; every extractor must exist in `registry.EXTRACTORS`.
5. Run extractors serially in the required order.
6. Continue after extractor failure by default, recording `RUN_FAILED`,
   `FETCH_FAILED`, `NOT_ATTEMPTED`, or `OK` for each extractor.
7. Checkpoint after every extractor with run id, status, started/finished times,
   error code, `ingest_run_id`, and next action.
8. Run `palace.audit.run(project=slug, depth=depth)` after extractor attempts
   complete.
9. Pin final report provenance to this `AnalysisRun`'s checkpointed
   `ingest_run_id` values. The analysis report must not silently use latest-run
   data for an extractor that failed or was not attempted in the current run.
   Either the audit path must accept pinned run ids, or `project_analyze.py` must
   render pinned section status itself and mark any latest-run fallback as
   `STALE_EXTERNAL_RUN`.
10. Return terminal state with:
   - `ok`
   - `run_id`
   - `project`
   - `bundle`
   - `extractors`
   - `overview`
   - `audit`
   - `report_markdown`
   - `next_actions`

### Swift Kit profile source of truth

`services/palace-mcp/src/palace_mcp/extractors/foundation/profiles.py` must
expose an ordered `swift_kit` extractor list for orchestration. The audit
coverage set may remain a set internally, but the orchestrator needs stable
execution order.

The initial ordered `swift_kit` profile must match the current full smoke
surface, including the SCIP-backed symbol index step:

1. `symbol_index_swift`
2. `arch_layer`
3. `code_ownership`
4. `coding_convention`
5. `crypto_domain_model`
6. `cross_module_contract`
7. `cross_repo_version_skew`
8. `dead_symbol_binary_surface`
9. `dependency_surface`
10. `error_handling_policy`
11. `git_history`
12. `hot_path_profiler`
13. `hotspot`
14. `localization_accessibility`
15. `public_api_surface`
16. `reactive_dependency_tracer`
17. `testability_di`

If `paperclips/scripts/ingest_swift_kit.sh` remains as an operator helper, it
must consume or be tested against this source of truth so the shell script and
Python profile cannot drift silently.

The legacy shell path remains part of the production smoke fallback until the
new CLI replaces it. Add a drift test that compares
`paperclips/scripts/ingest_swift_kit.sh` `DEFAULT_EXTRACTORS` to the ordered
Python `swift_kit` profile, or change the script to read the Python profile
directly.

### Runtime boundary

The host CLI handles host-only concerns: Docker lifecycle, bind mounts, `.env`
updates, local repo paths, and Swift SCIP generation. The MCP tools handle
product concerns: Memory Palace registration, extractor orchestration, graph
writes, checkpoint status, and audit rendering.

For V1, all paths are local to the Docker host. A command that points at
`/Users/Shared/Ios/HorizontalSystems/TronKit.Swift` must either mount that exact
path into Docker or stage it into the existing runtime mount pattern before
starting analysis. The generated SCIP path passed through
`PALACE_SCIP_INDEX_PATHS` must be the container-visible path, not the host path.
When SCIP is generated on MacBook, the iMac-side path remains authoritative for
Docker and `PALACE_SCIP_INDEX_PATHS`; the MacBook source path is metadata only.

Compose override strategy is deterministic:

- Generate the override under a Gimle-controlled runtime directory, not inside
  the target repo. Default path:
  `.gimle/runtime/project-analyze/docker-compose.project-analyze.yml`.
- Write a companion `.gimle/runtime/project-analyze/compose.env` or reuse the
  repo `.env` explicitly; every Docker Compose invocation from the CLI must pass
  the same `--env-file` and the same ordered `-f docker-compose.yml -f
  <generated-override>` arguments.
- The override is reused across runs for the same slug and rewritten
  deterministically when repo path, staged path, or container mount changes.
- The CLI must record the compose files and env file in the machine-readable
  summary so a later operator or agent can reproduce the exact runtime.
- Cleanup is explicit only; V1 must not silently remove generated overrides or
  staged repos after a run because they are part of the resumable runtime
  contract.
- `.gimle/runtime/` is expected local runtime state and must be ignored by git.
  The implementation must add or verify a `.gitignore` rule before smoke.

## Affected Files

Expected implementation areas:

- `services/palace-mcp/src/palace_mcp/cli.py`
- `services/palace-mcp/src/palace_mcp/mcp_server.py`
- `services/palace-mcp/src/palace_mcp/project_analyze.py` (new)
- `services/palace-mcp/src/palace_mcp/memory/cypher.py`
- `services/palace-mcp/src/palace_mcp/extractors/foundation/profiles.py`
- `services/palace-mcp/tests/test_project_analyze.py` (new)
- `services/palace-mcp/tests/test_mcp_server_project_analyze.py` (new)
- `services/palace-mcp/tests/test_project_analyze_cli.py` (new)
- `paperclips/scripts/scip_emit_swift_kit.sh`
- `paperclips/scripts/ingest_swift_kit.sh`
- `paperclips/scripts/tests/test_ingest_idempotency.sh`
- `.gitignore`
- `docs/runbooks/project-analyze.md` (new)
- `docs/audit-reports/` only for smoke evidence, not unit tests

Existing scripts may be reused or wrapped:

- `paperclips/scripts/scip_emit_swift_kit.sh`
- `paperclips/scripts/ingest_swift_kit.sh`

## Paperclip Execution Plan

The implementation plan lives in
`docs/superpowers/plans/2026-05-14-project-analyze-orchestrator-codex-task.md`.
That plan is authoritative for team execution and assigns work to the real
Gimle Paperclip Codex team (`cx-cto`, `cx-python-engineer`, `cx-mcp-engineer`,
`cx-infra-engineer`, `cx-qa-engineer`, `cx-technical-writer`, and
`codex-architect-reviewer`). Do not execute this work with local ad-hoc Codex
subagents.

## Acceptance Criteria

1. A single host command can analyze `tron-kit` from the iMac repo path and
   write a full audit report.
2. The command starts the Docker runtime when it is not already running.
3. The command does not require the operator to manually edit `.env` for
   `PALACE_SCIP_INDEX_PATHS`; it merges `{slug: container_scip_path}` itself and
   preserves existing mappings.
4. When the env mapping or repo mount changes, the command recreates
   `palace-mcp` before running the SCIP-backed extractor.
5. The product smoke command defaults to or explicitly uses
   `http://localhost:8080/mcp`.
6. `palace.project.analyze` starts an `AnalysisRun` and returns `run_id` without
   waiting for the full 17-extractor cascade.
7. `palace.project.analyze_status` exposes per-extractor checkpoint status.
8. `AnalysisRun` and checkpoints are durable in Neo4j and survive a real
   `palace-mcp` process restart or container recreate verified by smoke.
9. Only one active `AnalysisRun` can exist per `(slug, language_profile)`;
   duplicate starts are protected by an atomic Neo4j lock transaction and reuse
   the same idempotent run or return `ACTIVE_ANALYSIS_RUN_EXISTS`.
10. Interrupted runs can be resumed after process restart from the last
    completed checkpoint.
11. `--emit-scip auto` regenerates when `scip/index.scip.meta.json` is missing
    or mismatches repo HEAD SHA, emitter version, package path, generator host,
    source repo path, or destination iMac repo path.
12. The generated compose override path, env file, and exact `docker compose`
    file list are deterministic and recorded in the summary output.
13. If iMac cannot emit SCIP due unsupported Xcode/macOS, the CLI returns a
    structured fallback command for MacBook SCIP emit and iMac copy; the iMac
    Docker analysis can then resume using the copied SCIP artifact.
14. `.gimle/runtime/` is ignored by git and does not appear as an untracked
    source artifact after smoke.
15. Pinned audit provenance prevents stale latest-run sections from being hidden;
    any latest-run fallback is marked `STALE_EXTERNAL_RUN`.
16. `paperclips/scripts/ingest_swift_kit.sh` cannot drift silently from the
    ordered Python `swift_kit` profile.
17. `palace.memory.list_projects` includes `tron-kit` after the run.
18. `palace.memory.get_project_overview(slug="tron-kit")` returns non-empty
    ingest metadata.
19. `palace.ingest.list_extractors` exposes all default `swift_kit` extractors.
20. `palace.audit.run(project="tron-kit", depth="full")` returns markdown with:
    - Profile Coverage appendix
    - per-extractor status summary
    - run ids for populated sections
    - explicit `RUN_FAILED`, `FETCH_FAILED`, or `NOT_ATTEMPTED` entries when
      applicable
21. The smoke output records whether `reactive_dependency_tracer` failed because
    `reactive_facts.json` is absent; that is an expected diagnostic, not a
    hidden blind spot.
22. `swift_kit` profile tests prove the ordered list exactly matches the
    expected 17-extractor sequence and each extractor exists in
    `registry.EXTRACTORS`.
23. Registration tests prove `language_profile` is stored in existing
    `:Project.language_profile` and consumed by profile resolution.
24. No unrelated local artifacts such as `.coverage` or `.serena/` are
    committed.

## Verification Plan

Unit / integration:

```bash
cd services/palace-mcp && uv run pytest tests/test_project_analyze.py
cd services/palace-mcp && uv run pytest tests/test_mcp_server_project_analyze.py
cd services/palace-mcp && uv run pytest tests/test_project_analyze_cli.py
cd services/palace-mcp && uv run pytest tests/extractors/test_profiles.py
cd services/palace-mcp && uv run ruff check src tests
cd services/palace-mcp && uv run mypy
```

Product smoke:

```bash
uv run --directory services/palace-mcp python -m palace_mcp.cli project analyze \
  --repo-path /Users/Shared/Ios/HorizontalSystems/TronKit.Swift \
  --slug tron-kit \
  --bundle uw-ios \
  --language-profile swift_kit \
  --emit-scip auto \
  --depth full \
  --url http://localhost:8080/mcp \
  --report-out docs/audit-reports/2026-05-14-tron-kit-rerun.md
```

If iMac SCIP emit fails with `SCIP_EMIT_TOOLCHAIN_UNSUPPORTED`, run the emitted
MacBook fallback command, equivalent to:

```bash
bash paperclips/scripts/scip_emit_swift_kit.sh tron-kit \
  --repo-path /Users/ant013/Ios/HorizontalSystems/TronKit.Swift \
  --remote-host imac-ssh.ant013.work \
  --remote-base /Users/Shared/Ios/HorizontalSystems \
  --remote-relative-path TronKit.Swift
```

Then rerun the iMac product smoke with `--emit-scip auto` or
`--emit-scip never` so Docker consumes the copied iMac SCIP artifact.

Post-smoke MCP checks:

```bash
uv run --directory services/palace-mcp python -m palace_mcp.cli tool call \
  palace.memory.health --url http://localhost:8080/mcp --json '{}'

uv run --directory services/palace-mcp python -m palace_mcp.cli tool call \
  palace.memory.get_project_overview --url http://localhost:8080/mcp \
  --json '{"slug":"tron-kit"}'

uv run --directory services/palace-mcp python -m palace_mcp.cli tool call \
  palace.project.analyze_status --url http://localhost:8080/mcp \
  --json '{"run_id":"<run_id-from-smoke>"}'

uv run --directory services/palace-mcp python -m palace_mcp.cli audit run \
  --project tron-kit --depth full --url http://localhost:8080/mcp
```

## Open Questions

- Should the host command live only in `palace_mcp.cli`, or should we keep a
  thin shell wrapper for operator ergonomics?
- Should the command support `--repo-url` cloning in this slice, or only local
  `--repo-path`?
- Should reports be committed automatically, or only written to disk and left
  for operator review?
