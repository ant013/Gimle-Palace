# GIM-81 Implementation Plan — `palace.ops.unstick_issue` MCP tool

**Spec:** `docs/superpowers/specs/2026-04-25-palace-ops-unstick-issue-design.md`
**Branch:** `feature/GIM-81-palace-ops-unstick` (rebase onto `origin/develop` before Phase 2)
**Dependency:** GIM-75 (Graphiti foundation) — merged ✅ (`cf2fd0f`)

**Rev 2 (2026-04-25):** Addresses CodeReviewer Phase 1.2 findings — 3 CRITICALs + 5 WARNINGs resolved. See spec amendments in same commit.

## Problem

Paperclip execution locks get stuck (release endpoint returns 200 but doesn't clear `executionRunId`). Manual workaround: SSH to iMac, `ps | grep`, `kill -TERM`, wait for paperclip to detect exit. Happened 4+ times in 2 weeks. This tool codifies the operator playbook as an MCP tool.

## Blocker: Task 0 — operator iMac spike

Task 0 requires physical SSH access to iMac to inspect live paperclip processes. **This is operator (Board) work** — agents cannot SSH to production hosts. Results needed before Phase 2 implementation:

- (a) Is there a deterministic link between `executionRunId` from API and `paperclip-skills-XXXXXX` temp dir in `ps` output?
- (b) Does iMac SSH require `cloudflared access ssh` ProxyCommand or direct OpenSSH?
- (c) Does palace-mcp container need `cloudflared` binary?

**Output:** `docs/research/paperclip-run-id-pid-correlation.md`

## Tasks

### Task 0 — iMac spike (BLOCKED — operator work)

**Owner:** Board / Operator
**What:** SSH to iMac, inspect live paperclip run, document findings per spec §4 Task 0 (a)(b)(c).
**Output:** `docs/research/paperclip-run-id-pid-correlation.md`
**Acceptance:** File committed to feature branch with answers to all 3 questions.

### Task 1 — Extend Dockerfile

**Owner:** PythonEngineer
**Depends on:** Task 0 (need to know if cloudflared required)
**Files:** `services/palace-mcp/Dockerfile`
**What:** Add `openssh-client` (and `cloudflared` if Task 0(c) says yes) to apt-get install.
**Acceptance:** `docker compose build palace-mcp` succeeds. `ssh -V` works inside container.

### Task 2 — Extend docker-compose.yml

**Owner:** PythonEngineer
**Files:** `docker-compose.yml`
**What:** Add read-only SSH key mounts (to `/home/appuser/.ssh/`, NOT `/root/.ssh/` — container runs as `appuser`), `PALACE_OPS_HOST` / `PALACE_OPS_SSH_KEY` env vars, `PAPERCLIP_API_URL` env var, and `extra_hosts: ["host.docker.internal:host-gateway"]` to palace-mcp service per spec §3.3.
**Acceptance:** Container starts with SSH material mounted and readable by `appuser`. Paperclip API reachable from inside container via `host.docker.internal:3100`. `.env.example` updated with all new vars.

### Task 3 — Config settings

**Owner:** PythonEngineer
**Files:** `services/palace-mcp/src/palace_mcp/config.py`, `.env.example`
**What:** Add `palace_ops_host`, `palace_ops_ssh_key` (default `/home/appuser/.ssh/id_ed25519`), and `paperclip_api_url` (default `http://host.docker.internal:3100`) to Settings.
**Acceptance:** Settings load from env vars with documented defaults. `paperclip_api_url` is used by unstick tool for all API calls (no hardcoded localhost).

### Task 4 — Core implementation

**Owner:** PythonEngineer
**Depends on:** Task 0 (heuristic choice), Tasks 1-3
**Files:** `services/palace-mcp/src/palace_mcp/ops/__init__.py` (new), `services/palace-mcp/src/palace_mcp/ops/unstick.py` (new)
**What:** Implement unstick algorithm per spec §3.1-3.4:
- Read issue state from paperclip API
- Discover candidate PIDs via SSH (strict + permissive heuristic)
- Send SIGTERM
- Poll for lock clearing
- Safety guards (dry_run, `force: bool = False` parameter for >5 PID override, 5-PID cap)
- All subprocess calls via `asyncio.create_subprocess_exec` (never `subprocess.run`)
**Acceptance:** Function returns correct response shapes for noop/killed/lock_not_released cases. No blocking subprocess calls.

### Task 5 — MCP tool registration

**Owner:** PythonEngineer
**Depends on:** Task 4
**Files:** `services/palace-mcp/src/palace_mcp/mcp_server.py`
**What:** Register `palace.ops.unstick_issue` via `_tool()` wrapper (Pattern #21 at mcp_server.py:120-123).
**Acceptance:** Tool appears in `palace.ops.*` namespace. Schema matches spec §3.1 signature.

### Task 6 — Audit episode write

**Owner:** PythonEngineer
**Depends on:** Task 4, GIM-75 merged ✅
**Files:** `services/palace-mcp/src/palace_mcp/ops/unstick.py`
**What:** Write `:Episode{kind="ops.unstick_issue"}` to Graphiti after kill. Wrap in try/except — kill must succeed even if Neo4j is down.
**Acceptance:** Audit episode created on success. Graceful degradation on Graphiti failure.

### Task 7 — Unit tests

**Owner:** PythonEngineer
**Depends on:** Tasks 4-6
**Files:** `services/palace-mcp/tests/ops/__init__.py` (new), `services/palace-mcp/tests/ops/test_unstick.py` (new)
**What:** 8 unit tests per spec §5.1 (noop, dry_run, strict heuristic, permissive fallback, 5-cap, audit episode, timeout) + 1 additional test for `PALACE_OPS_HOST=local` mode (direct exec path without SSH).
**Acceptance:** All tests pass. Coverage for all response shapes including local-mode path.

### Task 8 — Integration tests

**Owner:** PythonEngineer
**Depends on:** Task 7
**Files:** `services/palace-mcp/tests/ops/test_unstick_integration.py` (new)
**What:** 2 integration tests per spec §5.2 (full flow kill+clear, respawn detection). Mock SSH + paperclip API.
**Acceptance:** Both tests pass.

### Task 9 — PR + CI

**Owner:** PythonEngineer
**What:** Push branch, open PR into develop, ensure CI green.
**Acceptance:** PR open, lint+typecheck+test+docker-build all pass.

## Phase sequence

| Phase | Agent | What |
|---|---|---|
| 1.1 Formalize | CTO | This plan (done) |
| 1.2 Plan-first review | CodeReviewer | Validate plan |
| **BLOCKED** | Board/Operator | Task 0 — iMac spike |
| 2 Implementation | PythonEngineer | Tasks 1–9 (after Task 0 results) |
| 3.1 Mechanical review | CodeReviewer | Code review |
| 3.2 Adversarial review | OpusArchitectReviewer | Security (SSH key handling, kill safety) |
| 4.1 QA live smoke | QAEngineer | Live smoke per spec §5.3 on iMac |
| 4.2 Merge | CTO | Squash-merge to develop. Chain END — post summary. |

## Notes

- Task 0 is the critical-path blocker. Without it, we don't know the SSH access mode or PID heuristic validity.
- Implementation Tasks 1-3 (Dockerfile, compose, config) could proceed in parallel with Task 0 if Board provides a partial answer on question (b) — SSH mode.
- The audit episode (Task 6) depends on GIM-75 which is already merged.
- Security concern: SSH keys mounted read-only inside container. OpusArchitectReviewer should scrutinize this in Phase 3.2.
- This is the last issue in the GIM-91→GIM-90→GIM-81 chain. No further chain trigger after merge.

## Rev 2 changes (CR Phase 1.2 response)

**CRITICALs resolved:**
1. SSH mount path → `/home/appuser/.ssh/` (not `/root/.ssh/`). Spec §3.3 + plan Task 2 updated. Default `PALACE_OPS_SSH_KEY=/home/appuser/.ssh/id_ed25519`.
2. `force: bool = False` added to tool signature in spec §3.1. Plan Task 4 acceptance updated.
3. Paperclip API access: `extra_hosts: ["host.docker.internal:host-gateway"]` + `PAPERCLIP_API_URL` env var added to spec §3.3 + plan Tasks 2-3. Tool reads `paperclip_api_url` from config.

**WARNINGs resolved:**
1. Async subprocess discipline: spec §3.3 now mandates `asyncio.create_subprocess_exec`. Plan Task 4 acceptance updated.
2. Local-mode test: added 1 unit test for `PALACE_OPS_HOST=local` path to Task 7.
3. `__init__.py` files: added to Task 4 (`ops/__init__.py`) and Task 7 (`tests/ops/__init__.py`).
4. Branch rebase: plan header updated — rebase onto `origin/develop` before Phase 2.
5. Audit episode queryability: noted for QA Phase 4.1 live smoke (spec §5.3 step 4 already covers lookup).
