---
slug: palace-ops-unstick-issue
status: proposed
branch: feature/GIM-81-palace-ops-unstick (cut from develop after umbrella lands)
paperclip_issue: 81
parent_umbrella: 79
depends_on:
  - 75 — Graphiti foundation (audit `:Episode` write requires `save_entity_node` from `graphiti_runtime.py`). If GIM-75 hasn't merged, this slice cannot finish Phase 2.
predecessor: develop tip after umbrella + GIM-75 merge
date: 2026-04-25
---

# GIM-81 — `palace.ops.unstick_issue` MCP tool

## 1. Context

Memory `reference_paperclip_stale_execution_lock.md` (updated 2026-04-25) documents the paperclip platform bug: `POST /api/issues/{id}/release` returns HTTP 200 with the full issue body but **does not clear** `executionRunId` / `executionAgentNameKey`. All probed cancel/unlock REST endpoints return 404. The only mechanism that actually frees the lock is killing the underlying `claude --print …` subprocess on the host, after which paperclip eventually (10–60 sec) detects exit and clears the row.

This workaround has been performed by hand at least 4 times in the past two weeks (GIM-52, 53, 69, 75/76). It involves SSH, ps grep, kill, and a follow-up state check. Codifying it as an MCP tool removes operator toil, lowers MTTR on stale-lock incidents, and gives downstream agents (e.g., a future "ops orchestrator" agent) a programmable hook.

## 2. Problem

Operator playbook today:

```
ssh imac
ps -A -o pid,etime,%cpu,command | grep "claude.*--print" | grep -v grep
# eyeball which etime is dead (idle hours)
kill -TERM <pid>
# wait
# from laptop:
curl ... /api/issues/<id>      # check executionRunId cleared
# if not, retry kill or retry reassign cycle
```

This is ~2 minutes per incident, error-prone (which PID matches which issue lock is heuristic), and disruptive to the operator's flow.

## 3. Solution — single MCP tool encapsulating the workaround

### 3.1 Tool signature

```python
@mcp.tool(name="palace.ops.unstick_issue")
async def unstick_issue(
    issue_id: str,
    *,
    dry_run: bool = False,
    force: bool = False,
    timeout_sec: int = 90,
) -> dict:
    """Force-release a paperclip issue stuck on a stale executionRunId.

    Workflow:
      1. Read issue state. If executionRunId is None → return {ok: True, action: "noop"}.
      2. Discover candidate Claude PIDs on the host that match this issue's run.
      3. Send SIGTERM to each candidate.
      4. Poll paperclip API for executionRunId clearing (every 5s, up to timeout_sec).
      5. If cleared → return {ok: True, action: "killed", killed_pids: [...]}.
         If not cleared → return {ok: False, error: "lock_not_released", ...}.
    """
```

### 3.2 Candidate-PID discovery

Two heuristics, applied in order:

1. **Strict match on run-id** — paperclip writes `--add-dir /var/folders/.../T/paperclip-skills-XXXXXX/` with the temp path containing a token. We don't yet know if that token correlates to `executionRunId` directly; **Task 0 of the slice** is verifying the link. If yes, we filter `ps` output for the matching path.
2. **Permissive fallback** — when strict match yields no candidates, list all `claude --print` PIDs that have `etime > 30 min` AND `cpu_ratio < 0.005` (mirrors GIM-79 idle-hang heuristic). Return them as candidates with `confidence: "permissive"`.

In either case, the response carries the full PID list + which heuristic matched, so the caller can audit.

### 3.3 Host access — runtime contract

Tool runs **inside `palace-mcp` container**. Current Dockerfile installs only `curl` + `git`; `docker-compose.yml` mounts no SSH material. **This slice must extend both** to enable host SSH:

**Dockerfile change (`services/palace-mcp/Dockerfile`):**

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl git \
    openssh-client \
    && rm -rf /var/lib/apt/lists/*
```

**docker-compose change (`docker-compose.yml` palace-mcp service):**

```yaml
palace-mcp:
  # ... existing ...
  extra_hosts:
    - "host.docker.internal:host-gateway"   # enables container → host API access
  volumes:
    # ... existing ...
    - "${HOME}/.ssh/id_ed25519:/home/appuser/.ssh/id_ed25519:ro"
    - "${HOME}/.ssh/known_hosts:/home/appuser/.ssh/known_hosts:ro"
    - "${HOME}/.ssh/config:/home/appuser/.ssh/config:ro"   # only if cloudflared ProxyCommand entry needs to be visible
  environment:
    # ... existing ...
    PALACE_OPS_HOST: "${PALACE_OPS_HOST:-imac-ssh.ant013.work}"
    PAPERCLIP_API_URL: "${PAPERCLIP_API_URL:-http://host.docker.internal:3100}"
```

**Notes:**
- Mount is **read-only** (`:ro`) — defense in depth.
- The SSH key file path is parameterized via env var (e.g. `PALACE_OPS_SSH_KEY=/home/appuser/.ssh/id_ed25519`).
- For deployments where the host runs **on the same machine** as palace-mcp (no SSH needed), `PALACE_OPS_HOST=local` short-circuits SSH and execs `ps` / `kill` directly. Decide between these two modes via `PALACE_OPS_HOST` value at config-load time.
- `cloudflared access ssh` is invoked via `ProxyCommand` declared in mounted `~/.ssh/config`. Verify cloudflared binary is reachable inside container — if not, add `cloudflared` to the Dockerfile too. **Task 0 verifies which mode (cloudflared vs direct) the production iMac uses.**

For non-iMac deployments — same contract, just different `PALACE_OPS_HOST`.

**Paperclip API access from container:** The tool reads issue state and polls for lock clearing via the paperclip API. Since palace-mcp runs on the Docker bridge network, `127.0.0.1:3100` (host-local paperclip) is unreachable. Use `extra_hosts: ["host.docker.internal:host-gateway"]` in compose and `PAPERCLIP_API_URL=http://host.docker.internal:3100` env var. The tool must read `PAPERCLIP_API_URL` from config, not hardcode localhost.

**Async subprocess discipline:** All SSH/ps/kill subprocess calls must use `asyncio.create_subprocess_exec`, not `subprocess.run` — the tool runs inside an async MCP handler and blocking the event loop would stall all concurrent MCP operations.

### 3.4 Safety guards

- `dry_run=True` returns the candidate PID list without sending kills.
- Hard cap on candidates: refuse to kill more than 5 PIDs in one call (unless `force: true` is explicitly passed).
- Audit log entry to `palace.memory` as `:Episode{kind="ops.unstick_issue", target_issue, killed_pids, outcome}` — agent intervention is auditable as a first-class event.

### 3.5 Out of scope

- Bulk unstick across multiple issues in one call (would invite mass-kill scenarios).
- Auto-trigger from watchdog (could be added later — this slice is operator/agent-callable only).
- Modifying paperclip source / submitting upstream patch.

## 4. Tasks

0. **Spike on iMac** — (a) SSH from operator laptop, inspect a live paperclip run; correlate `executionRunId` from API with `paperclip-skills-XXXXXX` temp dir suffix in `ps` output. Document the link in `docs/research/paperclip-run-id-pid-correlation.md`. If no deterministic correlation found — drop strict heuristic, document as such. (b) Verify whether the iMac SSH endpoint requires `cloudflared access ssh` ProxyCommand, or accepts direct OpenSSH. Document in same spike file. (c) Decide whether `palace-mcp` container needs `cloudflared` binary installed alongside `openssh-client` — record verdict.
1. **Extend `services/palace-mcp/Dockerfile`** to install `openssh-client` (and `cloudflared` if Task 0(c) says so).
2. **Extend `docker-compose.yml`** palace-mcp service: read-only mounts of `${HOME}/.ssh/id_ed25519`, `${HOME}/.ssh/known_hosts`, `${HOME}/.ssh/config`; new env vars `PALACE_OPS_HOST` and `PALACE_OPS_SSH_KEY`.
3. **Add to `config.py`** `Settings`: `palace_ops_host: str = "imac-ssh.ant013.work"`, `palace_ops_ssh_key: str = "/home/appuser/.ssh/id_ed25519"`, `paperclip_api_url: str = "http://host.docker.internal:3100"`. Add `.env.example` lines.
4. Create `services/palace-mcp/src/palace_mcp/ops/unstick.py` with the algorithm.
5. Register MCP tool `palace.ops.unstick_issue` via `_tool()` wrapper (per `mcp_server.py:120-123` Pattern #21).
6. Audit-log episode write — depends on GIM-75 helpers `save_entity_node` from `graphiti_runtime.py`. **Wrap in try/except**: if Graphiti is unreachable (Neo4j down) the kill must still proceed; log a stderr warning instead of failing the tool.
7. Unit tests per §6.1.
8. Integration test (mocks SSH + paperclip API) per §6.2.
9. Live smoke on iMac per §6.3.

## 5. Tests

### 5.1 Unit tests

- `test_unstick_noop_when_no_lock` — issue with executionRunId=null returns `{ok: True, action: "noop"}`.
- `test_unstick_dry_run_returns_candidates_no_kill` — mocked SSH; assert no `kill` invoked, candidate list returned.
- `test_unstick_strict_heuristic_matches_run_id` — fixture `ps` output containing matching paperclip-skills temp dir.
- `test_unstick_permissive_fallback_when_strict_empty` — strict match empty → permissive returns idle candidates with `confidence: "permissive"`.
- `test_unstick_refuses_more_than_five_candidates_without_force` — 6 candidates → returns error unless `force=True`.
- `test_unstick_local_mode_no_ssh` — `PALACE_OPS_HOST=local` → uses direct `asyncio.create_subprocess_exec` for `ps`/`kill` without SSH wrapper.
- `test_unstick_writes_audit_episode` — graphiti mock captures `:Episode{kind="ops.unstick_issue"}` with metadata envelope.
- `test_unstick_returns_lock_not_released_when_timeout` — paperclip API returns same executionRunId for entire poll window → `{ok: False, error: "lock_not_released"}`.

### 5.2 Integration tests

Mock-based (no real SSH or live paperclip); patches `subprocess.run` for SSH/ps/kill and patches `httpx.AsyncClient.get/patch` for paperclip API.

- `test_unstick_full_flow_kill_then_clear` — paperclip first call returns stale lock; after mocked kill, second poll returns lock cleared. Assert SSH command sequence + audit entry.
- `test_unstick_paperclip_respawns_within_poll_window` — after kill, paperclip starts a new run on same issue (new executionRunId observed). Tool should report `{ok: True, action: "killed_then_respawned", new_run_id: ...}`.

### 5.3 Live smoke on iMac

1. Manually create a stale lock (PATCH assigneeAgentId, kill subprocess, observe lingering executionRunId).
2. From operator MCP client: `palace.ops.unstick_issue(issue_id="<the-stuck-id>", dry_run=true)` — returns candidate list, no kills happen.
3. `palace.ops.unstick_issue(issue_id="<the-stuck-id>")` — returns `{ok: True, action: "killed", killed_pids: [...]}`.
4. Verify via `palace.memory.lookup Episode {kind: "ops.unstick_issue"}` that an audit event landed in Graphiti.
5. Verify `~/.paperclip/watchdog.err` empty (we did not crash watchdog).

## 6. Risks

| Risk | Mitigation |
|---|---|
| Strict run-id heuristic fails (no deterministic link from executionRunId to ps tmpdir) | Task 0 verifies; if no link, ship permissive only with stronger UX warnings. |
| Tool kills wrong PID (wrong issue, but matching paperclip-skills suffix) | Hard cap 5 + dry_run. Audit log. Operator review of audit episodes catches drift. |
| SSH from container to host fails (key revoked, cloudflared down) | Tool returns `{ok: False, error: "ssh_unreachable", details: ...}` — diagnostic only. |
| Tool becomes the default escape hatch for normal handoff issues | Documentation + `palace.memory.health` flag if `:Episode{kind:"ops.unstick_issue"}` count exceeds N/day. Not in this slice. |

## 7. References

- Memory `reference_paperclip_stale_execution_lock.md` (the bug, the workaround, the 2026-04-25 confirmation).
- `mcp_server.py:120-123` (Pattern #21 `_tool()` wrapper for MCP tool registration).
- GIM-80 (parallel slice) for `idle_cpu_ratio_max` heuristic which the permissive fallback reuses.
- 2026-04-25 incident timeline: GIM-75/76 stale-lock occurrences during overnight token-quota stalls.
