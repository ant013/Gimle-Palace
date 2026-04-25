# Task 0 — paperclip run-ID ↔ PID correlation spike

**Issue:** GIM-81 — `palace.ops.unstick_issue` MCP tool
**Operator:** Anton (Board)
**Date:** 2026-04-25
**Setting:** iMac production host (Antons-iMac.local, OSX 14, Docker Desktop 24.0.2)

## Question (a) — RunId ↔ tmpdir correlation

**Question:** Given an `executionRunId` from paperclip API, can we deterministically find the corresponding `claude --print` PID on the host?

### Findings

**No deterministic API mapping.** The `paperclip-skills-XXXXXX` tmpdir is RANDOM (mkstemp suffix). Process args contain only:

```
claude --print - --output-format stream-json --verbose ... \
  --append-system-prompt-file /var/folders/.../paperclip-skills-jaFEDY/agent-instructions.md \
  --add-dir /var/folders/.../paperclip-skills-jaFEDY
```

Nothing in the process args ties back to `executionRunId`. The tmpdir content is the agent role file (`agent-instructions.md`) and a `.claude/` subdirectory — neither references the runId.

**`GET /api/runs/{runId}` does NOT return PID** (verified via API response inspection during GIM-77 session — schema is `{runId, status, agentId, startedAt, finishedAt, usageJson, resultJson}`).

### Implication for unstick algorithm

Use **timing + heuristic** approach, not exact runId-PID match:

1. **Strict heuristic:** for stuck issue with `executionRunId=X` and `executionLockedAt=T`, find claude --print proc whose ETIME approximately matches `now - T` (within tolerance, e.g. ±60s).

2. **Permissive fallback:** if ambiguous (multiple candidates), apply CPU-ratio idle test: kill any `claude --print` proc whose `cpu_time/etime < 0.005` AND `etime > 5min` (consistent with GIM-80 watchdog idle-hang detection).

3. **5-PID safety cap:** if more than 5 candidates after both heuristics, abort with `force=False` and require operator override (`force=True` parameter).

This matches operator's manual workflow: "find the obviously-idle claude --print proc and kill it, but don't sweep them all".

## Question (b) — SSH from container: cloudflared ProxyCommand or direct OpenSSH?

**Direct OpenSSH.** Verified:

- iMac's `cloudflared tunnel run` daemon (PID 53222, started 14 Apr) registers SSH service so `imac-ssh.ant013.work` resolves and accepts standard SSH protocol from anywhere with internet. Operator's MacBook reaches it via `ssh anton@imac-ssh.ant013.work` directly — NO `cloudflared access ssh` ProxyCommand needed.
- iMac LAN IP `192.168.5.111` accepts SSH on port 22 (verified `nc -zv 127.0.0.1 22` succeeded).
- Mac Remote Login service active (`com.openssh.ssh-agent` in launchctl).

**For palace-mcp container:** simplest path is `host.docker.internal:22` (Docker for Mac built-in DNS for host). No tunneling needed.

```bash
# inside container
ssh -i /home/appuser/.ssh/palace_ops_id_ed25519 \
    -o StrictHostKeyChecking=no \
    anton@host.docker.internal \
    "kill -TERM <PID>"
```

**Fallback option** for non-Docker-Desktop deployments: `imac-ssh.ant013.work` (transparent cloudflared tunnel; works from anywhere). Spec config should accept either via env var:

```
PALACE_OPS_HOST=host.docker.internal  # default for Docker for Mac
PALACE_OPS_HOST=imac-ssh.ant013.work  # for remote-deployment scenarios
PALACE_OPS_HOST=local                 # short-circuit: skip SSH, use direct subprocess (for in-container testing)
```

## Question (c) — Does palace-mcp container need `cloudflared` binary?

**No.** Reasoning per (b):

- `host.docker.internal` is built into Docker for Mac (no client tooling required).
- For the cloudflared tunnel path (`imac-ssh.ant013.work`), the iMac side runs the tunnel daemon. Container side just needs DNS resolution (works through container network) + standard SSH client.

Container must have:
- ✅ `openssh-client` (Task 1 of plan)
- ❌ `cloudflared` binary — not needed

## Operator-completed setup (Task 0 deliverables)

### SSH key generation

```bash
ssh-keygen -t ed25519 -N "" -C "palace-ops@gimle-palace (2026-04-25)" \
  -f ~/.ssh/palace_ops_id_ed25519
```

Files produced on iMac:
- `/Users/anton/.ssh/palace_ops_id_ed25519` — private key (mode 0600, 432 bytes)
- `/Users/anton/.ssh/palace_ops_id_ed25519.pub` — public key (mode 0644, 118 bytes)

### Authorized_keys

Public key appended to `/Users/anton/.ssh/authorized_keys` (mode 0600).

### Self-SSH verification

```
$ ssh -i ~/.ssh/palace_ops_id_ed25519 anton@localhost "echo OK; uname -n"
Warning: Permanently added 'localhost' (ED25519) to the list of known hosts.
OK
Antons-iMac.local
```

✅ Key works.

## Recommended container mount (for Task 2)

In `docker-compose.yml`, palace-mcp service:

```yaml
volumes:
  - /Users/anton/.ssh/palace_ops_id_ed25519:/home/appuser/.ssh/palace_ops_id_ed25519:ro
  - /Users/anton/.ssh/palace_ops_id_ed25519.pub:/home/appuser/.ssh/palace_ops_id_ed25519.pub:ro
extra_hosts:
  - "host.docker.internal:host-gateway"
environment:
  PALACE_OPS_HOST: "host.docker.internal"
  PALACE_OPS_SSH_KEY: "/home/appuser/.ssh/palace_ops_id_ed25519"
```

⚠ **Permission gotcha:** the mounted private key file owner inside container will be `appuser:appuser` only if the host file's UID matches. On macOS Docker Desktop, file mounts inherit host UID/GID via the VM. SSH client requires the private key to be mode 0600 and owned by the user. PE may need `chown` step in entrypoint OR rely on Docker for Mac's userns mapping.

PE: verify in Task 2 via `docker compose exec -T palace-mcp ls -la /home/appuser/.ssh/palace_ops_id_ed25519` after compose up.

## Security notes

- The dedicated key is single-purpose (palace-ops kill operations). Compromise scope: SSH-as-anton on iMac, can run any command. Mitigation deferred to follow-up: lock down with `command="..."` in `authorized_keys` to allow only `kill -TERM <PID>` after `pgrep claude --print` validation.
- 5-PID safety cap in algorithm is the primary safeguard against runaway kill.
- Audit episode in Graphiti (Task 6) gives forensic trail.

## Authorization

Operator (Anton, Board) authorizes Task 0 as complete and grants chain authorization for PE Phase 2 to resume. Acknowledged at: 2026-04-25 ~17:45 UTC.
