# GIM-225 — Foundation smoke regression — план реализации

## Цель

Закрыть foundation smoke regression после GIM-217: восстановить чистый startup `palace-mcp` при `ensure_schema()` и сделать host-side review smoke однозначно направленным в compose stack, а не в занятый host nginx на `localhost:8080`.

## Scope

**В scope:**
- Контрактный фикс между `ensure_schema()` и `UPSERT_PROJECT`.
- Аудит call-sites для `UPSERT_PROJECT`, `parent_mount`, `relative_path`.
- Review-profile host routing для `/healthz` и MCP smoke.
- Runtime QA на реальных compose services после Python и infra фиксов.

**Не в scope:**
- Новая модель `:Project`.
- Изменение семантики `parent_mount` / `relative_path` для уже зарегистрированных проектов.
- Новые MCP tools.
- Рефакторинг docker topology за пределами review/full smoke route.

## Phase 1.1 — CTO discovery gates

**Owner:** CXCTO  
**Status:** complete for plan handoff.

### Duplicate-work gate

- `git fetch origin --prune` выполнен 2026-05-07.
- `git log --all --grep="ensure_schema|UPSERT_PROJECT|review host port|host port|GIM-225" --oneline --extended-regexp` не нашёл готовый GIM-225 fix commit.
- `gh pr list --state all --search "GIM-225 OR ensure_schema OR UPSERT_PROJECT OR review host port"` нашёл PR #111 как источник follow-up, но не нашёл отдельный GIM-225 PR/fix.
- Serena/codebase-memory discovery подтвердил текущие символы:
  - `services/palace-mcp/src/palace_mcp/memory/constraints.py::ensure_schema`
  - `services/palace-mcp/src/palace_mcp/memory/project_tools.py::register_project`

### Observed drift

- `services/palace-mcp/src/palace_mcp/memory/cypher.py:130` `UPSERT_PROJECT` sets `p.parent_mount = $parent_mount` and `p.relative_path = $relative_path`.
- `services/palace-mcp/src/palace_mcp/memory/constraints.py:37` calls `UPSERT_PROJECT` without `parent_mount` and `relative_path`.
- `services/palace-mcp/src/palace_mcp/memory/project_tools.py::register_project` already accepts and forwards `parent_mount: str | None` and `relative_path: str | None`.
- `docker-compose.yml:50` maps host `8080` to container `8000`; issue evidence says host `localhost:8080` is occupied by nginx on the current machine.

## Phase 1.2 — Plan-first review

**Suggested owner:** CXCodeReviewer  
**Affected paths:** this plan only.  
**Dependencies:** Phase 1.1 complete.

**Acceptance criteria:**
- Reviewer confirms the decomposition keeps CTO out of code/test/compose implementation.
- Reviewer confirms Python step owns `ensure_schema` / `UPSERT_PROJECT` compatibility and not project-model redesign.
- Reviewer confirms infra step owns review-profile host routing and does not require changing MCP transport.
- Reviewer confirms QA step requires real runtime smoke, not `/healthz` only.
- Reviewer either APPROVES this plan and reassigns Phase 2.1, or REQUESTS CHANGES with exact plan edits.

## Phase 2.1 — Python contract fix

**Suggested owner:** CXPythonEngineer  
**Affected paths:**
- `services/palace-mcp/src/palace_mcp/memory/constraints.py`
- `services/palace-mcp/tests/memory/test_constraints.py`
- `services/palace-mcp/tests/integration/test_group_id_ingest.py`
- Any additional `UPSERT_PROJECT` tests under `services/palace-mcp/tests/memory/`

**Dependencies:** Phase 1.2 APPROVE.

**Required discovery before code:**
- Paste fresh output of `rg -n "UPSERT_PROJECT|parent_mount|relative_path" services/palace-mcp/src services/palace-mcp/tests`.
- List every `session.run(UPSERT_PROJECT, ...)` call-site and whether it intentionally passes `None` or concrete `parent_mount` / `relative_path`.

**Acceptance criteria:**
- `ensure_schema()` passes a complete parameter set accepted by current `UPSERT_PROJECT`.
- Default bootstrap project remains legacy-compatible: no `parent_mount` and no `relative_path` unless a fresh audit proves otherwise.
- Tests cover default project bootstrap after `UPSERT_PROJECT` gained `parent_mount` / `relative_path`.
- Startup failure mode is covered so missing Cypher parameters cannot silently regress.
- No semantic change to existing `:Project.name`, `:Project.parent_mount`, or `:Project.relative_path` fields.

## Phase 2.2 — Review host routing fix

**Suggested owner:** CXInfraEngineer  
**Affected paths:**
- `docker-compose.yml`
- `docs/runbooks/deploy-checklist.md`
- `docs/clients/README.md` only if operator-facing endpoint text changes
- Optional: `docs/runbooks/revert-broken-merge.md` if smoke command needs correction

**Dependencies:** Phase 1.2 APPROVE.

**Required discovery before code/docs:**
- Paste host evidence proving what owns `localhost:8080` on the target machine.
- Paste compose evidence showing the intended reachable host endpoint for `palace-mcp` review/full profile.
- If changing Docker Compose syntax, add or cite a live-verified Docker Compose reference under `docs/research/` dated within 30 days.

**Acceptance criteria:**
- Host-side `/healthz` smoke cannot accidentally hit host nginx when the review stack is intended.
- Compose container healthcheck remains container-local and continues to target `http://localhost:8000/healthz`.
- Operator docs distinguish the container healthcheck from host-side review smoke.
- Existing client docs keep `localhost:8080/mcp` only if it is still the canonical operator endpoint; otherwise they point to the new reviewed endpoint.
- Infra change does not alter Neo4j profile ownership or service dependencies.

## Phase 3.1 — Mechanical code review

**Suggested owner:** CXCodeReviewer  
**Affected paths:** all files changed by Phase 2.1 and Phase 2.2.  
**Dependencies:** Phase 2.1 and Phase 2.2 pushed.

**Acceptance criteria:**
- Confirms `UPSERT_PROJECT` call-sites are all audited and tests fail on missing parameters.
- Confirms infra route targets the compose stack and does not mask service startup failures.
- Confirms changed files stay inside GIM-225 declared scope.
- Requests changes if `/healthz` is used as the only proof of service correctness.

## Phase 3.2 — Architect review

**Suggested owner:** CodexArchitectReviewer  
**Affected paths:** all files changed by Phase 2.1 and Phase 2.2.  
**Dependencies:** Phase 3.1 APPROVE.

**Acceptance criteria:**
- Confirms no architecture drift in project registration semantics.
- Confirms review routing is an operational correction, not a new deployment topology.
- Confirms QA can prove default `gimle` project registration through a real MCP/runtime path.

## Phase 4.1 — Runtime QA

**Suggested owner:** CXQAEngineer  
**Affected paths:** QA evidence comment only unless QA finds defects.  
**Dependencies:** Phase 3.2 APPROVE.

**Acceptance criteria:**
- `uv run ruff check` green for `services/palace-mcp`.
- `uv run mypy src/` green from `services/palace-mcp`.
- `uv run pytest` green for `services/palace-mcp`.
- `docker compose build` green.
- `docker compose --profile full up` healthchecks green.
- Host-side smoke hits the intended compose endpoint, not host nginx.
- Real MCP tool call succeeds after startup.
- Neo4j invariant proves default `gimle` project registration exists and has expected legacy path fields:
  - `slug = "gimle"`
  - `group_id = "project/gimle"`
  - `parent_mount IS NULL`
  - `relative_path IS NULL`

## Phase 4.2 — Merge

**Suggested owner:** CXCTO  
**Affected paths:** PR metadata and issue status only.  
**Dependencies:** Phase 4.1 QA PASS evidence authored by CXQAEngineer.

**Acceptance criteria:**
- Paste `gh pr view --json mergeStateStatus,mergeable,statusCheckRollup,reviewDecision,headRefOid`.
- Paste check-runs and `develop` branch protection evidence before claiming any merge blocker.
- Squash-merge to `develop` only after review and QA gates pass.
- Close GIM-225 only after merge commit, QA evidence, and production deploy evidence are present.

## Handoff order

1. CXCodeReviewer reviews this plan.
2. CXPythonEngineer implements Phase 2.1.
3. CXInfraEngineer implements Phase 2.2 after or in parallel with Phase 2.1 if reviewer explicitly allows parallel child issues.
4. CXCodeReviewer performs Phase 3.1.
5. CodexArchitectReviewer performs Phase 3.2.
6. CXQAEngineer performs Phase 4.1.
7. CXCTO performs Phase 4.2 merge/close discipline.
