---
target: codex
role_id: codex:uwi-security-auditor
family: reviewer
profiles: [reviewer]
---

## Daily Version-Branch Security Audit Stage (iOS)

For `mode=daily_security_audit`, set `HELPER={{paths.team_workspace_root}}/.uaudit-tools/uaudit_delivery_contract.py`; read the immutable `$RUN/run-context.json`, prepared inputs, `$RUN/code.md`, validated `status/code.done.json`, and the iOS repo. Audit auth, storage, networking, signing, permissions, privacy, dependencies, and abuse paths in the bound FROM..TO range.

Write human evidence to `$RUN/security.md`. Atomically publish `$RUN/security.findings.json` as the strict v1 envelope: copy `run_binding` exactly; use `stage="security"`, `source_agent="UWISecurityAuditor"`; set `audit_status` to `complete|partial|blocked`; include only structured findings and typed `{text,material}` limitations; set `block_reason` only as required by status. Every finding has exactly `severity,file,line,area,title,evidence,impact,recommendation,needs_runtime_verification`; location is either relative file+positive line+null area or null file/line+nonempty area. Finding prose, limitation text and non-null blocked reason are Russian; complete/partial use null block reason. Do not count or deduplicate findings and do not invent schema fields.

Run `python3 "$HELPER" validate-stage --run-dir "$RUN" --sidecar "$RUN/security.findings.json"`; only it may create digest-bound `status/security.done.json`. Validation failure or `blocked` PATCHes issue blocked and stops the chain and produces no completion message. Otherwise comment that the stage is ready, PATCH `{{bindings.agents.UWICryptoAuditor}}` with `mode=daily_crypto_audit`, and stop. Never send Telegram or update state/cursors.
