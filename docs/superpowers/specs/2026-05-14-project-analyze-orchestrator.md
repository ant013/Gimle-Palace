# Project Analyze Orchestrator

**Date:** 2026-05-14
**Status:** draft
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

## Goals

- Provide a single host-side command for local operator use:
  `palace project analyze --repo-path ... --slug ...`.
- Provide a matching MCP-facing orchestration surface for already-mounted
  repositories: `palace.project.analyze`.
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
- Solving async Paperclip multi-agent audit workflow in this slice. This slice
  focuses on deterministic local analysis + synchronous audit output.

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
  --report-out docs/audit-reports/2026-05-14-tron-kit-rerun.md
```

Responsibilities:

1. Validate local repo path and slug.
2. For SwiftPM repos, optionally generate `scip/index.scip` when missing or
   stale (`--emit-scip auto|always|never`).
3. Create or update a deterministic Docker Compose override that mounts the
   repo under a container-visible parent mount.
4. Start or restart the local Gimle runtime with `docker compose --profile review`.
5. Wait for `/healthz`.
6. Call the MCP orchestrator (`palace.project.analyze`) with container-visible
   metadata.
7. Save the report markdown and machine-readable summary.

### MCP tool

Add native MCP tool:

```python
palace.project.analyze(
    slug: str,
    name: str | None = None,
    bundle: str | None = None,
    parent_mount: str,
    relative_path: str,
    language_profile: str,
    extractors: list[str] | None = None,
    depth: Literal["quick", "full"] = "full",
)
```

Responsibilities:

1. Register/update `:Project` with `parent_mount`, `relative_path`, and
   `language_profile`.
2. Register bundle and add membership when `bundle` is provided.
3. Resolve extractor defaults from `language_profile`; for `swift_kit`, use the
   current 17-extractor set from `ingest_swift_kit.sh`.
4. Run extractors serially in the required order.
5. Collect per-extractor result status, run ids, and errors.
6. Run `palace.audit.run(project=slug, depth=depth)`.
7. Return:
   - `ok`
   - `project`
   - `bundle`
   - `extractors`
   - `overview`
   - `audit`
   - `report_markdown`
   - `next_actions`

### Why both layers are needed

The host CLI handles host-only concerns: Docker lifecycle, bind mounts, local
repo paths, and Swift SCIP generation. The MCP tool handles product concerns:
Memory Palace registration, extractor orchestration, graph writes, and audit
rendering. This keeps MCP safe and lets external clients read/query the result
without needing direct host filesystem access.

## Affected Files

Expected implementation areas:

- `services/palace-mcp/src/palace_mcp/cli.py`
- `services/palace-mcp/src/palace_mcp/mcp_server.py`
- `services/palace-mcp/src/palace_mcp/project_analyze.py` (new)
- `services/palace-mcp/src/palace_mcp/extractors/foundation/profiles.py`
- `services/palace-mcp/tests/test_project_analyze.py` (new)
- `services/palace-mcp/tests/test_mcp_server_project_analyze.py` (new)
- `docs/runbooks/project-analyze.md` (new)
- `docs/audit-reports/` only for smoke evidence, not unit tests

Existing scripts may be reused or wrapped:

- `paperclips/scripts/scip_emit_swift_kit.sh`
- `paperclips/scripts/ingest_swift_kit.sh`

## Acceptance Criteria

1. A single host command can analyze `tron-kit` from a local repo path and write
   a full audit report.
2. The command starts the Docker runtime when it is not already running.
3. The command does not require the operator to manually edit `.env` for
   `PALACE_SCIP_INDEX_PATHS`.
4. `palace.project.analyze` works when the repo is already mounted and visible
   to the container.
5. `palace.memory.list_projects` includes `tron-kit` after the run.
6. `palace.memory.get_project_overview(slug="tron-kit")` returns non-empty
   ingest metadata.
7. `palace.ingest.list_extractors` exposes all default `swift_kit` extractors.
8. `palace.audit.run(project="tron-kit", depth="full")` returns markdown with:
   - Profile Coverage appendix
   - per-extractor status summary
   - run ids for populated sections
   - explicit `RUN_FAILED`, `FETCH_FAILED`, or `NOT_ATTEMPTED` entries when
     applicable
9. The smoke output records whether `reactive_dependency_tracer` failed because
   `reactive_facts.json` is absent; that is an expected diagnostic, not a hidden
   blind spot.
10. No unrelated local artifacts such as `.coverage` or `.serena/` are committed.

## Verification Plan

Unit / integration:

- `cd services/palace-mcp && uv run pytest tests/test_project_analyze.py`
- `cd services/palace-mcp && uv run pytest tests/test_mcp_server_project_analyze.py`
- `cd services/palace-mcp && uv run ruff check src tests`
- `cd services/palace-mcp && uv run mypy`

Product smoke:

```bash
uv run --directory services/palace-mcp python -m palace_mcp.cli project analyze \
  --repo-path /Users/ant013/Ios/HorizontalSystems/TronKit.Swift \
  --slug tron-kit \
  --bundle uw-ios \
  --language-profile swift_kit \
  --emit-scip auto \
  --depth full \
  --report-out docs/audit-reports/2026-05-14-tron-kit-rerun.md
```

Post-smoke MCP checks:

```bash
uv run --directory services/palace-mcp python -m palace_mcp.cli tool call \
  palace.memory.health --url http://localhost:8080/mcp --json '{}'

uv run --directory services/palace-mcp python -m palace_mcp.cli tool call \
  palace.memory.get_project_overview --url http://localhost:8080/mcp \
  --json '{"slug":"tron-kit"}'

uv run --directory services/palace-mcp python -m palace_mcp.cli audit run \
  --project tron-kit --depth full --url http://localhost:8080/mcp
```

## Open Questions

- Should the host command live only in `palace_mcp.cli`, or should we keep a
  thin shell wrapper for operator ergonomics?
- Should `palace.project.analyze` persist an `:AnalysisRun` node distinct from
  per-extractor `:IngestRun` nodes?
- Should the command support `--repo-url` cloning in this slice, or only local
  `--repo-path`?
- Should reports be committed automatically, or only written to disk and left
  for operator review?
