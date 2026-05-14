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

- V1 is local-host only: the host CLI runs on the same machine that owns the
  repository path and runs Docker Compose.
- Remote dev Mac to iMac SCIP generation/copy is out of scope for V1. A later
  slice may add explicit `--remote-host` and `--remote-base` flags.
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
- Solving remote SCIP generation/copy in this slice.
- Keeping a single blocking MCP request open for the entire extractor cascade.

## Scope

This slice changes the local analysis orchestration contract only:

- Host CLI for local repo path analysis.
- Docker mount and `.env` SCIP visibility management needed by that CLI.
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
  --repo-path /Users/ant013/Ios/HorizontalSystems/TronKit.Swift \
  --slug tron-kit \
  --bundle uw-ios \
  --language-profile swift_kit \
  --emit-scip auto \
  --depth full \
  --url http://localhost:8080/mcp \
  --report-out docs/audit-reports/2026-05-14-tron-kit-rerun.md
```

Responsibilities:

1. Validate local repo path, slug, and local-host execution model.
2. For SwiftPM repos, optionally generate `scip/index.scip` when missing or
   stale (`--emit-scip auto|always|never`) on the same host that runs Docker.
3. Create or update a deterministic Docker Compose override that mounts the
   repo under a container-visible parent mount.
4. Compute the container SCIP path, normally
   `{container_repo_path}/scip/index.scip`.
5. Update `.env` `PALACE_SCIP_INDEX_PATHS` by merging the new
   `{slug: container_scip_path}` entry without deleting existing entries.
6. Start the local Gimle runtime with `docker compose --profile review up -d`;
   recreate `palace-mcp` when mount or env changes require it.
7. Wait for `/healthz`.
8. Start the MCP analysis run and poll status until terminal state.
9. Save the report markdown and machine-readable summary.

The host default URL for this command is `http://localhost:8080/mcp`. Existing
subcommands may keep their current default only if tests make the distinction
explicit; the product smoke command must not silently target `localhost:8000`.

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
   error code, and next action.
8. Run `palace.audit.run(project=slug, depth=depth)` after extractor attempts
   complete.
9. Return terminal state with:
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

### Runtime boundary

The host CLI handles host-only concerns: Docker lifecycle, bind mounts, `.env`
updates, local repo paths, and Swift SCIP generation. The MCP tools handle
product concerns: Memory Palace registration, extractor orchestration, graph
writes, checkpoint status, and audit rendering.

For V1, all paths are local to the Docker host. A command that points at
`/Users/ant013/Ios/HorizontalSystems/TronKit.Swift` must either mount that exact
path into Docker or stage it into the existing runtime mount pattern before
starting analysis. The generated SCIP path passed through
`PALACE_SCIP_INDEX_PATHS` must be the container-visible path, not the host path.

## Affected Files

Expected implementation areas:

- `services/palace-mcp/src/palace_mcp/cli.py`
- `services/palace-mcp/src/palace_mcp/mcp_server.py`
- `services/palace-mcp/src/palace_mcp/project_analyze.py` (new)
- `services/palace-mcp/src/palace_mcp/extractors/foundation/profiles.py`
- `services/palace-mcp/tests/test_project_analyze.py` (new)
- `services/palace-mcp/tests/test_mcp_server_project_analyze.py` (new)
- `services/palace-mcp/tests/test_project_analyze_cli.py` (new)
- `docs/runbooks/project-analyze.md` (new)
- `docs/audit-reports/` only for smoke evidence, not unit tests

Existing scripts may be reused or wrapped:

- `paperclips/scripts/scip_emit_swift_kit.sh`
- `paperclips/scripts/ingest_swift_kit.sh`

## Agent Execution Plan

The implementation must be split into small Codex-agent work packages. Agents
are not alone in the codebase: each package has an explicit write scope, and no
agent should revert edits outside its assigned files.

### Wave 0: Prep

1. Agent `coordinator`: create implementation branch from current approved spec.
   - Write scope: none except git metadata.
   - Output: branch name, clean status, base commit.
   - Verification: `git status --short --branch`.

2. Agent `code-mapper`: confirm current extractor/profile/CLI/MCP seams.
   - Write scope: none.
   - Output: short map of relevant symbols and tests.
   - Verification: cite exact files/functions to edit.

### Wave 1: Profile Contract

3. Agent `profile-worker`: add ordered profile data.
   - Write scope:
     `services/palace-mcp/src/palace_mcp/extractors/foundation/profiles.py`.
   - Change: expose ordered `swift_kit` extractor sequence while preserving
     existing audit coverage behavior and `:Project.language_profile` lookup.
   - Verification: targeted unit tests added in the next package must pass.

4. Agent `profile-test-worker`: add drift tests for profile ordering.
   - Write scope: `services/palace-mcp/tests/unit/test_profiles.py`.
   - Change: assert exact 17-extractor order and membership in
     `registry.EXTRACTORS`.
   - Verification:
     `cd services/palace-mcp && uv run pytest tests/unit/test_profiles.py`.

### Wave 2: AnalysisRun Core

5. Agent `analysis-model-worker`: add `AnalysisRun` data model.
   - Write scope: `services/palace-mcp/src/palace_mcp/project_analyze.py`.
   - Change: define run status, checkpoint schema, terminal states, and report
     summary structures.
   - Verification: model-only tests compile and serialize.

6. Agent `analysis-state-worker`: add run persistence/resume adapter.
   - Write scope: `services/palace-mcp/src/palace_mcp/project_analyze.py`.
   - Change: persist enough state to resume from the last completed checkpoint.
   - Verification: unit test proves an interrupted run reloads checkpoint state.

7. Agent `analysis-runner-worker`: add extractor orchestration.
   - Write scope: `services/palace-mcp/src/palace_mcp/project_analyze.py`.
   - Change: run ordered extractors serially, continue on failure, record
     `OK`, `RUN_FAILED`, `FETCH_FAILED`, or `NOT_ATTEMPTED`.
   - Verification: unit test with fake extractor runner covers success, failure,
     and continue-on-failure.

8. Agent `analysis-audit-worker`: add audit/report finalization.
   - Write scope: `services/palace-mcp/src/palace_mcp/project_analyze.py`.
   - Change: call audit after extractor attempts and assemble
     `report_markdown`, `overview`, `audit`, and `next_actions`.
   - Verification: unit test with fake audit client verifies terminal payload.

### Wave 3: MCP Surface

9. Agent `mcp-tool-worker`: register project analysis MCP tools.
   - Write scope: `services/palace-mcp/src/palace_mcp/mcp_server.py`.
   - Change: add keyword-only `palace.project.analyze`,
     `palace.project.analyze_status`, and `palace.project.analyze_resume`.
   - Verification:
     `cd services/palace-mcp && uv run pytest tests/test_mcp_server_project_analyze.py`.

10. Agent `mcp-test-worker`: add MCP tool tests.
    - Write scope: `services/palace-mcp/tests/test_mcp_server_project_analyze.py`.
    - Change: prove required args, quick `run_id` return, status lookup, resume,
      and existing `language_profile` storage behavior.
    - Verification:
      `cd services/palace-mcp && uv run pytest tests/test_mcp_server_project_analyze.py`.

### Wave 4: Host CLI

11. Agent `cli-parser-worker`: add `project analyze` parser.
    - Write scope: `services/palace-mcp/src/palace_mcp/cli.py`.
    - Change: add command args, validate local path/slug, and set product-smoke
      URL default to `http://localhost:8080/mcp`.
    - Verification: parser unit tests pass.

12. Agent `cli-scip-worker`: add SCIP generation/env mapping helpers.
    - Write scope: `services/palace-mcp/src/palace_mcp/cli.py`.
    - Change: implement `--emit-scip`, compute container SCIP path, merge
      `.env` `PALACE_SCIP_INDEX_PATHS`, preserve existing JSON entries.
    - Verification: tests cover missing env, existing env, invalid JSON, and
      container path vs host path.

13. Agent `cli-docker-worker`: add Docker lifecycle helpers.
    - Write scope: `services/palace-mcp/src/palace_mcp/cli.py`.
    - Change: create/update compose override, start review profile, recreate
      `palace-mcp` only when env or mount changes, wait for health.
    - Verification: command-construction tests use fakes, not real Docker.

14. Agent `cli-poll-worker`: add AnalysisRun polling/report output.
    - Write scope: `services/palace-mcp/src/palace_mcp/cli.py`.
    - Change: call analyze, poll status, handle terminal states, write markdown
      and JSON summary.
    - Verification: fake MCP client test covers successful and failed terminal
      states.

15. Agent `cli-test-worker`: add CLI integration tests.
    - Write scope: `services/palace-mcp/tests/test_project_analyze_cli.py`.
    - Change: cover URL default, env update, restart decision, status polling,
      and report output path.
    - Verification:
      `cd services/palace-mcp && uv run pytest tests/test_project_analyze_cli.py`.

### Wave 5: Docs And Smoke

16. Agent `docs-worker`: add runbook.
    - Write scope: `docs/runbooks/project-analyze.md`.
    - Change: document local prerequisites, host port 8080, SCIP env update,
      Docker recreate behavior, and Memory Palace follow-up queries.
    - Verification: runbook commands match CLI help.

17. Agent `verification-worker`: run full local validation.
    - Write scope: `docs/audit-reports/` only if smoke evidence is generated.
    - Change: no source edits unless a prior agent is reassigned.
    - Verification: run the unit/integration commands and then the full
      `tron-kit` product smoke.

18. Agent `reviewer`: final review before merge.
    - Write scope: none unless explicitly assigned follow-up fixes.
    - Output: findings first, with file/line refs; confirm no unrelated files
      such as `.serena/`, `.coverage`, or submodule dirt are staged.
    - Verification: `git diff --stat`, `git status --short`, and test summary.

## Acceptance Criteria

1. A single host command can analyze `tron-kit` from a local repo path and write
   a full audit report.
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
8. Interrupted runs can be resumed or safely reported as resumable with the last
   completed checkpoint.
9. `palace.memory.list_projects` includes `tron-kit` after the run.
10. `palace.memory.get_project_overview(slug="tron-kit")` returns non-empty
    ingest metadata.
11. `palace.ingest.list_extractors` exposes all default `swift_kit` extractors.
12. `palace.audit.run(project="tron-kit", depth="full")` returns markdown with:
    - Profile Coverage appendix
    - per-extractor status summary
    - run ids for populated sections
    - explicit `RUN_FAILED`, `FETCH_FAILED`, or `NOT_ATTEMPTED` entries when
      applicable
13. The smoke output records whether `reactive_dependency_tracer` failed because
    `reactive_facts.json` is absent; that is an expected diagnostic, not a
    hidden blind spot.
14. `swift_kit` profile tests prove the ordered list exactly matches the
    expected 17-extractor sequence and each extractor exists in
    `registry.EXTRACTORS`.
15. Registration tests prove `language_profile` is stored in existing
    `:Project.language_profile` and consumed by profile resolution.
16. No unrelated local artifacts such as `.coverage` or `.serena/` are
    committed.

## Verification Plan

Unit / integration:

```bash
cd services/palace-mcp && uv run pytest tests/test_project_analyze.py
cd services/palace-mcp && uv run pytest tests/test_mcp_server_project_analyze.py
cd services/palace-mcp && uv run pytest tests/test_project_analyze_cli.py
cd services/palace-mcp && uv run pytest tests/unit/test_profiles.py
cd services/palace-mcp && uv run ruff check src tests
cd services/palace-mcp && uv run mypy
```

Product smoke:

```bash
uv run --directory services/palace-mcp python -m palace_mcp.cli project analyze \
  --repo-path /Users/ant013/Ios/HorizontalSystems/TronKit.Swift \
  --slug tron-kit \
  --bundle uw-ios \
  --language-profile swift_kit \
  --emit-scip auto \
  --depth full \
  --url http://localhost:8080/mcp \
  --report-out docs/audit-reports/2026-05-14-tron-kit-rerun.md
```

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
- Should `AnalysisRun` be persisted as `:AnalysisRun` nodes in Neo4j, local JSON
  state under the service data directory, or both?
- Should the command support `--repo-url` cloning in this slice, or only local
  `--repo-path`?
- Should reports be committed automatically, or only written to disk and left
  for operator review?
