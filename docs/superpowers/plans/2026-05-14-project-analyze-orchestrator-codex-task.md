# Paperclip Codex CTO Task: Project Analyze Orchestrator

**Date:** 2026-05-14
**Implementation branch:** `feature/GIM-NN-project-analyze-orchestrator-impl`
**Approved spec:** `docs/superpowers/specs/2026-05-14-project-analyze-orchestrator.md`
**Project assembly:** `paperclips/projects/gimle/paperclip-agent-assembly.yaml`
**Resolved assembly:** `paperclips/dist/gimle.resolved-assembly.json`
**Codex team root:** `/Users/Shared/Ios/worktrees/cx/Gimle-Palace`
**Owner:** `CXCTO` / `codex:cx-cto`

## Mission For CXCTO

Own delivery of the `project analyze` product path for Gimle. The result must
let an operator provide a local repository path and receive a complete
MCP-backed analysis, Memory Palace state, and audit report without manually
editing Docker mounts, `.env`, SCIP paths, or extractor runs.

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

## Paperclip Team Context

This task belongs to the Gimle Paperclip Codex team, not local ad-hoc Codex
subagents. CXCTO delegates through Paperclip to the existing Codex agents:

| Responsibility | Paperclip agent | Agent id |
| --- | --- | --- |
| Technical owner, decomposition, gates | `cx-cto` | `da97dbd9-6627-48d0-b421-66af0750eacf` |
| MCP protocol and tool surface | `cx-mcp-engineer` | `9a5d7bef-9b6a-4e74-be1d-e01999820804` |
| Python services and Neo4j implementation | `cx-python-engineer` | `e010d305-22f7-4f5c-9462-e6526b195b19` |
| Docker Compose, host CLI runtime boundary | `cx-infra-engineer` | `21981be0-8c51-4e57-8a0a-ca8f95f4b8d9` |
| Test strategy, integration, smoke evidence | `cx-qa-engineer` | `99d5f8f8-822f-4ddb-baaa-0bdaec6f9399` |
| Runbook and operator docs | `cx-technical-writer` | `1b9fc009-4b02-4560-b7f5-2b241b5897d9` |
| Final adversarial architecture review | `codex-architect-reviewer` | `fec71dea-7dba-4947-ad1f-668920a02cb6` |

Supporting files:

- `paperclips/codex-agent-ids.env`
- `paperclips/deploy-codex-agents.sh`
- `paperclips/scripts/deploy_project_agents.py`
- `paperclips/update-agent-workspaces.sh`
- `paperclips/dist/codex/cx-cto.md`

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
- Work must happen in the Gimle Paperclip Codex workspace unless CXCTO records a
  specific reason to use another checkout.

## Current Dirty Files To Avoid

These existed before implementation planning in the local operator checkout and
must not be staged by this task unless CXCTO explicitly takes ownership:

- `paperclips/fragments/shared`
- `.serena/`
- `services/watchdog/.coverage`

## CXCTO Operating Rules

- CXCTO owns the plan, dependency ordering, branch discipline, and merge gate.
- CXCTO must delegate implementation to the named Paperclip Codex team roles,
  not to local internal Codex subagents.
- Each assignee receives a bounded work package with write scope, expected
  output, and verification command.
- If a role needs to edit outside scope, it reports back to CXCTO before making
  the edit.
- Each role reports changed files and command evidence.
- CXCTO keeps unrelated dirty files out of commits.
- Final merge requires `cx-qa-engineer` verification and
  `codex-architect-reviewer` review.

## Wave 0: CTO Intake And Assignment

### Task 0.1: CXCTO Intake

**Assignee:** `cx-cto`
**Write scope:** none

Confirm in the Paperclip Codex workspace:

- Current checkout is the Gimle project.
- Branch is `feature/GIM-NN-project-analyze-orchestrator-impl` or a CXCTO-named
  child branch created from it.
- Branch contains approved spec commits:
  - `76f61ed docs(spec): project analyze orchestrator`
  - `05b7fde docs(spec): tighten project analyze contract`
  - `0246f8b docs(spec): pin analysis run durability`
- `origin/develop` is an ancestor.
- No unrelated files are staged.

Verification:

```bash
git status --short --branch
git merge-base --is-ancestor origin/develop HEAD
git log --oneline --max-count 8
```

### Task 0.2: CXCTO Codebase-Memory Read

**Assignee:** `cx-cto`
**Write scope:** none

Read codebase-memory before delegating:

- Paperclip Gimle assembly and Codex team root.
- Existing MCP server and CLI structure.
- Existing profile resolver and extractor registry.
- Existing Neo4j memory/cypher patterns.
- Existing test locations.

Output:

- Final delegation order.
- Any changed role assignment.
- Any blocker before Wave 1.

## Wave 1: Profile Contract

### Task 1.1: Ordered Profile Data

**Assignee:** `cx-python-engineer`
**Review:** `cx-mcp-engineer`
**Write scope:**

- `services/palace-mcp/src/palace_mcp/extractors/foundation/profiles.py`

Implement ordered `swift_kit` extractor sequence while preserving existing audit
coverage behavior and explicit `:Project.language_profile` lookup.

Acceptance:

- Ordered list exactly matches approved spec.
- Audit coverage set still works.
- No extractor implementation changes.

### Task 1.2: Profile Drift Tests

**Assignee:** `cx-qa-engineer`
**Support:** `cx-python-engineer`
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

**Assignee:** `cx-python-engineer`
**Review:** `cx-mcp-engineer`
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

**Assignee:** `cx-python-engineer`
**Review:** `cx-qa-engineer`
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

**Assignee:** `cx-python-engineer`
**Review:** `cx-qa-engineer`
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

**Assignee:** `cx-python-engineer`
**Review:** `cx-mcp-engineer`
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

**Assignee:** `cx-mcp-engineer`
**Support:** `cx-python-engineer`
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

**Assignee:** `cx-qa-engineer`
**Support:** `cx-mcp-engineer`
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

## Wave 4: Host CLI And Docker Boundary

### Task 4.1: CLI Parser

**Assignee:** `cx-mcp-engineer`
**Review:** `cx-infra-engineer`
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

**Assignee:** `cx-infra-engineer`
**Support:** `cx-mcp-engineer`
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

**Assignee:** `cx-infra-engineer`
**Review:** `cx-qa-engineer`
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

**Assignee:** `cx-mcp-engineer`
**Support:** `cx-python-engineer`
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

**Assignee:** `cx-technical-writer`
**Review:** `cx-infra-engineer`
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

**Assignee:** `cx-qa-engineer`
**Support:** `cx-infra-engineer`
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

### Task 5.3: Final Paperclip Review

**Assignee:** `codex-architect-reviewer`
**Support:** `cx-code-reviewer`
**Write scope:** none unless CXCTO assigns follow-up fixes

Review stance:

- Findings first.
- Include file/line refs.
- Prioritize correctness, durability, concurrency, and missing tests.
- Confirm no unrelated dirty files are staged.
- Confirm the implementation matches the approved spec and this Paperclip team
  assignment.

Required checks:

```bash
git status --short
git diff --stat
git diff --cached --stat
```

## Definition Of Done

- CXCTO accepts the implementation plan and delegation evidence.
- Spec contracts are implemented.
- Unit/integration checks pass or failures are explicitly explained.
- Full `tron-kit` smoke produces report markdown and machine-readable summary.
- Memory Palace can answer project overview for `tron-kit`.
- Audit output includes profile coverage and per-extractor statuses.
- CXQAEngineer signs off on verification evidence.
- CodexArchitectReviewer signs off on architecture and concurrency/durability.
- No unrelated local artifacts are committed.
