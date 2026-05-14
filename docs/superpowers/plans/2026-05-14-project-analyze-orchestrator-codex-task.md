# Codex CTO Task: Project Analyze Orchestrator

**Date:** 2026-05-14
**Implementation branch:** `feature/GIM-NN-project-analyze-orchestrator-impl`
**Approved spec:** `docs/superpowers/specs/2026-05-14-project-analyze-orchestrator.md`
**Base:** `origin/develop` plus approved spec commits
**Owner:** Codex CTO coordinator

## Mission

Implement the `project analyze` product path so an operator can give Gimle a
local repository path and receive a complete MCP-backed analysis, Memory Palace
state, and audit report without manually editing Docker mounts, `.env`, SCIP
paths, or extractor runs.

The first production smoke target is:

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

## Non-Negotiable Contracts

- Host CLI owns host-only work: Docker lifecycle, compose override, local path
  validation, `.env` `PALACE_SCIP_INDEX_PATHS`, and Swift SCIP generation.
- MCP owns product work: project/bundle registration, durable `AnalysisRun`,
  extractor orchestration, checkpoint status, resume, and audit report assembly.
- `AnalysisRun` state is durable in Neo4j, not in-memory only.
- Only one active `AnalysisRun` may exist for `(slug, language_profile)`.
- Repeated CLI invocation with the same idempotency key must recover the
  existing active run.
- `--emit-scip auto` uses `scip/index.scip.meta.json` and regenerates on stale
  repo SHA, emitter version, package path, host repo path, missing index, empty
  index, or invalid metadata.
- Host MCP URL default for this product command is `http://localhost:8080/mcp`.
- Compose override path is deterministic:
  `.gimle/runtime/project-analyze/docker-compose.project-analyze.yml`.
- Every agent must respect assigned write scope and must not revert unrelated
  dirty files.

## Current Dirty Files To Avoid

These existed before implementation work and must not be staged unless a later
task explicitly owns them:

- `paperclips/fragments/shared`
- `.serena/`
- `services/watchdog/.coverage`

## Agent Team Rules

- Agents are not alone in the codebase. Each package below has a write scope.
- If an agent needs to edit outside scope, it must stop and report the reason.
- Prefer tests before or alongside implementation for risky behavior.
- Keep commits small enough to review by package or wave.
- Every package must report changed files and verification command output.
- Do not run destructive git commands.

## Wave 0: Context And Branch Hygiene

### Task 0.1: Coordinator Branch Check

**Agent:** `coordinator`
**Write scope:** none

Confirm:

- Current branch is `feature/GIM-NN-project-analyze-orchestrator-impl`.
- Branch contains approved spec commits.
- `origin/develop` is an ancestor of the implementation branch.
- Dirty unrelated files are not staged.

Verification:

```bash
git status --short --branch
git merge-base --is-ancestor origin/develop HEAD
git log --oneline --max-count 5
```

### Task 0.2: Code Mapper

**Agent:** `code-mapper`
**Write scope:** none

Map exact implementation seams:

- `services/palace-mcp/src/palace_mcp/cli.py`
- `services/palace-mcp/src/palace_mcp/mcp_server.py`
- `services/palace-mcp/src/palace_mcp/memory/cypher.py`
- `services/palace-mcp/src/palace_mcp/extractors/foundation/profiles.py`
- extractor runner and `palace.ingest.run_extractor` call path
- audit runner and markdown return path

Output:

- Symbols/functions to edit.
- Existing tests to extend.
- Any hidden dependency that affects task ordering.

## Wave 1: Profile Contract

### Task 1.1: Ordered Profile Data

**Agent:** `profile-worker`
**Write scope:**

- `services/palace-mcp/src/palace_mcp/extractors/foundation/profiles.py`

Implement ordered `swift_kit` extractor sequence while preserving existing audit
coverage behavior and explicit `:Project.language_profile` lookup.

Acceptance:

- Ordered list exactly matches approved spec.
- Audit coverage set still works.
- No extractor implementation changes.

### Task 1.2: Profile Drift Tests

**Agent:** `profile-test-worker`
**Write scope:**

- `services/palace-mcp/tests/extractors/test_profiles.py`

Add tests proving:

- Exact 17-extractor order.
- Every extractor exists in `registry.EXTRACTORS`.
- Existing profile inference behavior still passes.

Verification:

```bash
cd services/palace-mcp && uv run pytest tests/extractors/test_profiles.py
```

## Wave 2: Durable AnalysisRun Core

### Task 2.1: Neo4j AnalysisRun Model

**Agent:** `analysis-model-worker`
**Write scope:**

- `services/palace-mcp/src/palace_mcp/project_analyze.py`
- `services/palace-mcp/src/palace_mcp/memory/cypher.py`
- `services/palace-mcp/tests/test_project_analyze.py`

Implement durable `:AnalysisRun` and checkpoint persistence helpers.

Required fields:

- `run_id`
- `slug`
- `language_profile`
- `bundle`
- `extractors`
- `depth`
- `idempotency_key`
- `status`
- `created_at`
- `updated_at`
- `started_at`
- `finished_at`
- `lease_owner`
- `lease_expires_at`
- `last_completed_extractor`
- checkpoint statuses
- checkpoint `ingest_run_id`
- final audit/report payload references

Acceptance:

- One active run per `(slug, language_profile)`.
- Existing idempotency key reuses active run.
- Different active run returns `ACTIVE_ANALYSIS_RUN_EXISTS`.

### Task 2.2: Resume And Lease Semantics

**Agent:** `analysis-state-worker`
**Write scope:**

- `services/palace-mcp/src/palace_mcp/project_analyze.py`
- `services/palace-mcp/tests/test_project_analyze.py`

Implement:

- Active statuses: `PENDING`, `RUNNING`, `RESUMABLE`.
- Terminal statuses: `SUCCEEDED`, `SUCCEEDED_WITH_FAILURES`, `FAILED`,
  `CANCELED`.
- Expired `RUNNING` lease becomes `RESUMABLE`.
- Resume continues after `last_completed_extractor`.

Acceptance:

- Unit test simulates process restart by recreating service object and reading
  Neo4j-backed state.

### Task 2.3: Extractor Orchestration

**Agent:** `analysis-runner-worker`
**Write scope:**

- `services/palace-mcp/src/palace_mcp/project_analyze.py`
- `services/palace-mcp/tests/test_project_analyze.py`

Implement serial extractor execution from ordered profile or explicit list.

Acceptance:

- Continue on failure by default.
- Checkpoint after every extractor.
- Statuses include `OK`, `RUN_FAILED`, `FETCH_FAILED`, `NOT_ATTEMPTED`.
- Every completed checkpoint pins `ingest_run_id`.

### Task 2.4: Audit Finalization

**Agent:** `analysis-audit-worker`
**Write scope:**

- `services/palace-mcp/src/palace_mcp/project_analyze.py`
- `services/palace-mcp/tests/test_project_analyze.py`

Implement final audit/report assembly.

Acceptance:

- Audit runs only after extractor attempts finish.
- Report includes pinned per-extractor run ids.
- Provenance mismatch with latest-run discovery is visible, not hidden.

## Wave 3: MCP Surface

### Task 3.1: MCP Tool Registration

**Agent:** `mcp-tool-worker`
**Write scope:**

- `services/palace-mcp/src/palace_mcp/mcp_server.py`

Add keyword-only MCP tools:

- `palace.project.analyze`
- `palace.project.analyze_status`
- `palace.project.analyze_resume`

Acceptance:

- `palace.project.analyze` returns quickly with `run_id`.
- Status reads durable Neo4j state.
- Resume reacquires lease.

### Task 3.2: MCP Tests

**Agent:** `mcp-test-worker`
**Write scope:**

- `services/palace-mcp/tests/test_mcp_server_project_analyze.py`

Add tests for:

- Required args.
- Quick `run_id` return.
- Status lookup.
- Resume.
- Idempotency behavior.
- Existing `language_profile` storage and resolution.

Verification:

```bash
cd services/palace-mcp && uv run pytest tests/test_mcp_server_project_analyze.py
```

## Wave 4: Host CLI

### Task 4.1: CLI Parser

**Agent:** `cli-parser-worker`
**Write scope:**

- `services/palace-mcp/src/palace_mcp/cli.py`
- `services/palace-mcp/tests/test_project_analyze_cli.py`

Add `project analyze` command parser.

Acceptance:

- Validates local repo path and slug.
- Defaults product command URL to `http://localhost:8080/mcp`.
- Accepts `--emit-scip auto|always|never`, `--bundle`, `--language-profile`,
  `--depth`, `--report-out`.

### Task 4.2: SCIP Metadata And Env Mapping

**Agent:** `cli-scip-worker`
**Write scope:**

- `services/palace-mcp/src/palace_mcp/cli.py`
- `services/palace-mcp/tests/test_project_analyze_cli.py`

Implement:

- `scip/index.scip.meta.json` read/write.
- `--emit-scip auto` stale detection.
- container SCIP path computation.
- `.env` `PALACE_SCIP_INDEX_PATHS` JSON merge preserving existing entries.

Acceptance:

- Missing/empty index regenerates.
- Missing/invalid metadata regenerates.
- SHA/version/path mismatch regenerates.
- Invalid existing env JSON fails clearly.

### Task 4.3: Compose And Docker Lifecycle

**Agent:** `cli-docker-worker`
**Write scope:**

- `services/palace-mcp/src/palace_mcp/cli.py`
- `services/palace-mcp/tests/test_project_analyze_cli.py`

Implement:

- deterministic override at
  `.gimle/runtime/project-analyze/docker-compose.project-analyze.yml`
- pinned `--env-file`
- ordered `-f docker-compose.yml -f <generated-override>`
- start review profile
- recreate `palace-mcp` only when env or mount changes
- health wait

Acceptance:

- Tests use fakes, not real Docker.
- Summary records compose files and env file.

### Task 4.4: CLI Polling And Outputs

**Agent:** `cli-poll-worker`
**Write scope:**

- `services/palace-mcp/src/palace_mcp/cli.py`
- `services/palace-mcp/tests/test_project_analyze_cli.py`

Implement:

- stable idempotency key from slug, language profile, repo HEAD SHA, depth,
  extractor list, and container repo path
- start analyze
- poll status until terminal
- write markdown report
- write machine-readable summary

Acceptance:

- Repeat CLI invocation with same inputs recovers active run.
- Failed terminal states produce non-zero exit and useful summary.

## Wave 5: Docs, Verification, Review

### Task 5.1: Runbook

**Agent:** `docs-worker`
**Write scope:**

- `docs/runbooks/project-analyze.md`

Document:

- local prerequisites
- Docker host port 8080
- SCIP metadata behavior
- `.env` mapping behavior
- compose override path
- Memory Palace follow-up queries
- resume behavior

### Task 5.2: Full Verification

**Agent:** `verification-worker`
**Write scope:**

- `docs/audit-reports/` only if smoke evidence is generated

Run:

```bash
cd services/palace-mcp && uv run pytest tests/extractors/test_profiles.py
cd services/palace-mcp && uv run pytest tests/test_project_analyze.py
cd services/palace-mcp && uv run pytest tests/test_mcp_server_project_analyze.py
cd services/palace-mcp && uv run pytest tests/test_project_analyze_cli.py
cd services/palace-mcp && uv run ruff check src tests
cd services/palace-mcp && uv run mypy
```

Then run the full `tron-kit` smoke command from this task.

### Task 5.3: Final Review

**Agent:** `reviewer`
**Write scope:** none unless assigned follow-up fixes

Review stance:

- Findings first.
- Include file/line refs.
- Prioritize correctness, durability, concurrency, and missing tests.
- Confirm no unrelated dirty files are staged.

Required checks:

```bash
git status --short
git diff --stat
git diff --cached --stat
```

## Definition Of Done

- Spec contracts are implemented.
- Unit/integration checks pass or failures are explicitly explained.
- Full `tron-kit` smoke produces report markdown and machine-readable summary.
- Memory Palace can answer project overview for `tron-kit`.
- Audit output includes profile coverage and per-extractor statuses.
- No unrelated local artifacts are committed.
