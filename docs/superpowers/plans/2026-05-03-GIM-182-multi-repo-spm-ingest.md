# GIM-182 — Multi-repo SPM ingest — план реализации

> **Статус Phase 1.1:** план создан CTO. Перед Phase 1.2 review остаются формальные блокеры, перечисленные в разделе "Phase 1.1 gates".

## Цель

Сделать `uw-ios` виртуальным bundle-проектом, который агрегирует `uw-ios-app` и first-party HorizontalSystems Kits, чтобы MCP-запросы вроде `palace.code.find_references(..., project="uw-ios")` проходили по всем членам bundle без ручного перебора 41 репозитория.

## Scope

**В scope v1:**
- `:Bundle` и `:CONTAINS` в Neo4j с `group_id = "bundle/<name>"`.
- MCP tools для bundle CRUD/status и расширение `find_references`/`run_extractor`.
- Parent-mount параметры на `register_project`; отдельного `register_parent_mount` tool в v1 нет.
- Manifest-driven workflow для UW-iOS + HS Kits.
- 3-Kit fixture, CI drift-check, runbook и live QA smoke.

**Не в scope v1:**
- ThirdParty bundle, auto-discovery, ingest-side cache, concurrent ingest, webhook refresh, tier auto-derivation, first-class `register_parent_mount`, отдельная `:BundleIngestRun` entity.

## Phase 1.1 gates

1. **Branch ancestry gate — BLOCKED.**
   - Ожидание handoff: `feature/GIM-182-multi-repo-spm-ingest` должен descend from `f2f05c4`.
   - Факт проверки: `git merge-base --is-ancestor f2f05c4 HEAD` вернул `1`; `HEAD=706dc99`, `origin/develop=f2f05c4`.
   - Дополнительный риск: рабочее дерево помечает submodule `paperclips/fragments/shared` как modified (`74aa48c..f9c1852`), поэтому CTO не должен чистить/rebase-ить это состояние без Board/operator решения.

2. **External API truth gate — BLOCKED.**
   - В spec есть API-примеры `from pydantic import BaseModel, Field, field_validator`, `asyncio.create_task(...)`, `mcp.client.streamable_http.streamablehttp_client`.
   - Проверка `docs/research` не нашла `pydantic`/`asyncio`/`mcp client` spike/reference files.
   - По external library reference rule это должно быть закрыто live-verified spike/reference-файлами, датированными в пределах 30 дней, до APPROVE.

3. **Duplicate-work gate — OK.**
   - `git log --all --grep` нашел только spec commits GIM-182, без реализации.
   - `gh pr list --state all --search "GIM-182 multi-repo SPM ingest"` вернул `[]`.
   - Serena/codebase-memory поиск по `register_bundle|bundle_status|add_to_bundle|delete_bundle|query_failed_slugs|ingest_failed_slugs|never_ingested` не нашел существующей реализации в `services/palace-mcp/src`.

## Phase 1.2 — Plan-first review

**Suggested owner:** CXCodeReviewer  
**Affected paths:** этот план, `docs/superpowers/specs/2026-05-03-GIM-182-multi-repo-spm-ingest-design.md`  
**Dependencies:** Phase 1.1 gates закрыты.

**Acceptance criteria:**
- Reviewer явно подтверждает 5 invariant lines из spec §12:
  - smoke gate: `uw-ios-app` ok + >= 40/41 members ok;
  - `failed_slugs` разделен на query / ingest / never_ingested;
  - `register_parent_mount` не v1 tool, только параметры на `register_project`;
  - `:Bundle.group_id = "bundle/<name>"`;
  - bundle ingest async и сразу возвращает `run_id`.
- Reviewer проверяет, что file scope ниже совпадает со spec §4 и не пересекается с активным GIM-128.
- Reviewer либо APPROVE и передает Phase 2, либо REQUEST CHANGES с точными пунктами.

## Phase 2 — Implementation steps

### Step 1 — Bundle domain + schema

**Suggested owner:** CXPythonEngineer  
**Affected paths:** `services/palace-mcp/src/palace_mcp/memory/bundle.py`, memory schema/bootstrap modules, unit tests under `services/palace-mcp/tests/memory/`  
**Dependencies:** Phase 1.2 APPROVE.

**Acceptance criteria:**
- `:Bundle` constraint/index bootstrap is idempotent.
- `register_bundle`, `add_to_bundle`, `bundle_members`, `bundle_status`, `delete_bundle` have unit coverage.
- Namespace collision guards work both ways: project-vs-bundle and bundle-vs-project.
- `:Bundle.group_id = "bundle/<name>"` is written and tested.

### Step 2 — MCP tool surface

**Suggested owner:** CXPythonEngineer; CXMCPEngineer if available  
**Affected paths:** `services/palace-mcp/src/palace_mcp/mcp_server.py`, request/response schema files, MCP tests  
**Dependencies:** Step 1.

**Acceptance criteria:**
- 5 bundle memory tools are registered with stable response shapes.
- `palace.ingest.bundle_status(run_id)` is registered separately from memory bundle metadata status.
- No v1 `register_parent_mount` tool is exposed.
- Invalid bundle names return structured errors, not raw exceptions.

### Step 3 — Parent mount path resolver

**Suggested owner:** CXPythonEngineer  
**Affected paths:** `services/palace-mcp/src/palace_mcp/git/path_resolver.py`, `memory/projects` registration path, git/path tests  
**Dependencies:** Step 1.

**Acceptance criteria:**
- `register_project(slug, parent_mount?, relative_path?)` stays backward-compatible for legacy `/repos/<slug>` projects.
- Relative paths cannot escape the configured parent mount.
- Existing `palace.git.*` tests remain covered for legacy slug resolution.

### Step 4 — Bundle-aware `find_references`

**Suggested owner:** CXPythonEngineer  
**Affected paths:** `services/palace-mcp/src/palace_mcp/code/find_references.py` or current composite code path, unit/integration tests  
**Dependencies:** Steps 1-2.

**Acceptance criteria:**
- `project="uw-ios"` expands through bundle membership and merges per-member results.
- Health output exposes `query_failed_slugs`, `ingest_failed_slugs`, `never_ingested_slugs`.
- Query-time member failures are logged and returned without hiding successful members.

### Step 5 — Async bundle ingest runner

**Suggested owner:** CXPythonEngineer  
**Affected paths:** `services/palace-mcp/src/palace_mcp/extractors/runner.py`, new bundle state/registry module, runner tests  
**Dependencies:** Steps 1-2.

**Acceptance criteria:**
- `run_extractor(bundle=...)` returns `run_id` within 100 ms in test harness.
- Heavy per-member ingest runs in a tracked background `asyncio.Task`.
- `bundle_status(run_id)` reports progress, terminal state, and failure taxonomy.
- Other MCP tools remain responsive while bundle ingest is running.

### Step 6 — Operator scripts and manifest drift

**Suggested owner:** CXPythonEngineer for scripts; CXInfraEngineer for compose once hired  
**Affected paths:** `services/palace-mcp/scripts/uw-ios-bundle-manifest.json`, `register-uw-ios-bundle.sh`, `regen-uw-ios-scip.sh`, manifest drift check, `docker-compose.yml`  
**Dependencies:** Steps 1-5.

**Acceptance criteria:**
- Manifest contains `uw-ios-app` plus HS Kit members with tier metadata.
- Register script is idempotent and skip-if-exists.
- Regen script includes mtime guard, sha256 verification, rsync failure handling, disk preflight.
- CI drift check compares manifest to UW-IOS `Package.resolved`.
- Compose includes `/Users/Shared/Ios/HorizontalSystems:/repos-hs:ro` without breaking non-iMac overrides.

### Step 7 — 3-Kit fixture and regression coverage

**Suggested owner:** CXPythonEngineer  
**Affected paths:** `services/palace-mcp/tests/extractors/fixtures/uw-ios-bundle-mini-project/`, unit/integration tests  
**Dependencies:** Steps 1-6; GIM-128 fixture layout awareness.

**Acceptance criteria:**
- Fixture covers `uw-ios-mini`, `EvmKit-mini`, `Eip20Kit-mini`.
- Tests prove cross-repo reference lookup for a symbol like `EvmKit.Address`.
- Tests prove `uw-ios-app` slug is distinct from `uw-ios` bundle.
- Fixture paths do not overlap GIM-128 declared write scope.

### Step 8 — Runbook

**Suggested owner:** CXTechnicalWriter once hired; otherwise CXPythonEngineer for first draft  
**Affected paths:** `docs/runbooks/multi-repo-spm-ingest.md`  
**Dependencies:** Steps 1-7.

**Acceptance criteria:**
- Runbook covers one-time setup, manifest registration, SCIP regeneration, smoke, troubleshooting, cleanup.
- Runbook documents `uw-ios-app` mandatory success and >= 40/41 bundle success gate.
- Runbook includes operator-safe remediation for failed member ingest and path/mount errors.

### Step 9 — Phase 3 review gates

**Suggested owner:** CXCodeReviewer then CodexArchitectReviewer  
**Affected paths:** PR diff and plan/spec artifacts  
**Dependencies:** Phase 2 pushed.

**Acceptance criteria:**
- CR pastes `git diff --name-only origin/develop...HEAD | sort -u` and verifies scope.
- CR verifies the 5 invariant lines from Phase 1.2 still match implementation.
- Architect review checks async lifecycle, path traversal hardening, bundle/project namespace semantics, and smoke gate enforceability.

### Step 10 — Phase 4 QA and merge

**Suggested owner:** CXQAEngineer for Phase 4.1; CXCTO for Phase 4.2  
**Affected paths:** runtime evidence comment, PR, develop merge  
**Dependencies:** Phase 3 approvals.

**Acceptance criteria:**
- QA evidence is from real runtime, not mocked DB only.
- Evidence includes tested commit SHA, docker health, real MCP bundle registration/query/status calls, and direct Neo4j invariant check for `Bundle.group_id`.
- Smoke passes: `uw-ios-app` ok and >= 40/41 members ok.
- Before any merge blocker escalation, CXCTO pastes `gh pr view --json mergeStateStatus,mergeable,statusCheckRollup,reviewDecision,headRefOid` and required follow-up evidence.
