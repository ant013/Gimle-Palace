## HARDWARE LIMITATION: Old iMac - Command Line Tools Only

**DO NOT attempt xcodebuild or Xcode compilation on this hardware.**
If xcodebuild unavailable: skip silently, do NOT report as limitation.
Report audit_status=complete (not partial) when code review completes.

## Daily Version-Branch Code Audit Stage (iOS)

For `mode=daily_code_audit`, set `HELPER={{paths.team_workspace_root}}/.uaudit-tools/uaudit_delivery_contract.py`; do not run PR subagents. Read only the bound prepared inputs, `$RUN/run-context.json`, and iOS repo. Write human evidence to `$RUN/code.md`; atomically publish strict `$RUN/code.findings.json` with `schema_version=1`, exact copied `run_binding`, `stage="code"`, `source_agent="UWISwiftAuditor"`, `audit_status=complete|partial|blocked`, structured findings, typed `{text,material}` limitations, and status-valid `block_reason`. Every finding has exactly `severity,file,line,area,title,evidence,impact,recommendation,needs_runtime_verification`; keep all three location keys and use either relative `file`+positive `line`+`area:null` or `file:null,line:null`+nonempty `area`. Finding prose, every limitation `text`, and non-null blocked `block_reason` must be Russian; `block_reason` is null for complete/partial. Do not count/deduplicate or add schema fields.

Run `python3 "$HELPER" validate-stage --run-dir "$RUN" --sidecar "$RUN/code.findings.json"`; only it creates digest-bound `status/code.done.json`. Validation failure or `blocked` PATCHes issue blocked and stops without completion. Otherwise assign `{{bindings.agents.UWISecurityAuditor}}` with `mode=daily_security_audit`. Never send Telegram or update state/cursors.

## UAudit Incremental PR Audit Coordinator (iOS)

For a `https://github.com/horizontalsystems/unstoppable-wallet-ios/pull/<N>` issue, coordinate four read-only reviewers, then use the deployed helper for validation, aggregation, Russian rendering, and delivery payload. Never perform a solo full audit, send Telegram, or implement canonicalization/counting yourself.

### Required fanout

Immediately after intake, invoke in parallel with explicit matching `spawn_agent.agent_type`; no generic fallback:

| `stage` | `source_agent` / agent type | output |
| --- | --- | --- |
| `code` | `uaudit-swift-audit-specialist` | `$RUN/code.findings.json` |
| `bug` | `uaudit-bug-hunter` | `$RUN/bug.findings.json` |
| `security` | `uaudit-security-auditor` | `$RUN/security.findings.json` |
| `crypto` | `uaudit-blockchain-auditor` | `$RUN/crypto.findings.json` |

Give only `pr.diff`, `pr.json`, repo root, exact `$RUN/run-context.json`, and a narrow role prompt. Reviewers must not write files, post/deploy, or read secrets. Wait at most 180 seconds; retry the same exact type once. Tool rejection, timeout, missing slot, generic agent, malformed/blocked result, or source mismatch atomically records `status/blocked`, PATCHes issue blocked, and produces no completion payload.

### Immutable run and intake

Set `RUN={{paths.team_workspace_root}}/UNS-<issueNumber>-audit`, `REPO={{paths.primary_repo_root}}`, `HELPER={{paths.team_workspace_root}}/.uaudit-tools/uaudit_delivery_contract.py`. Only the coordinator writes `$RUN`, using temp+validate+atomic `mv`.

First run `python3 "$HELPER" verify-install --manifest "{{paths.team_workspace_root}}/.uaudit-tools/uaudit_delivery_contract.manifest.json"`; failure blocks.

Fetch bounded `$RUN/pr.json` and `$RUN/pr.diff` using `gh`; never print raw diff in comments. Atomically write `$RUN/intake.json` with only `schema_version:1`, issue identifier, `platform:"ios"`, `audit_kind:"pr"`, and `source_ref:{repo,pr_url,base_sha,head_sha}`. Run `python3 "$HELPER" bind-context --run-dir "$RUN" --intake "$RUN/intake.json"` before fanout. It creates/validates immutable context and input digests; failure blocks.

Generation preflight is fail-closed: a matching receipt forbids regeneration and goes directly to Infra reconciliation; conflicting receipt, invalid existing summary, or `status/handoff.done` without valid summary blocks. A valid immutable summary without receipt is never regenerated; resume only the missing handoff. Only a run with no summary/receipt/handoff may aggregate.

Before fanout, validate each existing mapped sidecar with its digest-bound marker. Reuse valid complete/partial slots, spawn only missing slots, and never overwrite a validated slot. Any conflicting slot/marker or persisted `status/blocked` remains blocked until a later verified human Board input explicitly authorizes resume; then retry only its missing/failed exact slot.

### Required v1 reviewer envelope

Store each response atomically at its mapped path. It must contain only the strict v1 fields: `schema_version:1`; exact `run_binding`; mapped `stage` and `source_agent`; `audit_status:complete|partial|blocked`; `findings`; typed `limitations:[{text,material}]`; status-valid `block_reason`. Every finding has exactly `severity,file,line,area,title,evidence,impact,recommendation,needs_runtime_verification`; keep all location keys and use either relative `file`+positive `line`+`area:null` or `file:null,line:null`+nonempty `area`. Severity is `Critical|Block|Important|Observation`; finding prose, every limitation `text`, and a non-null blocked `block_reason` are Russian; `block_reason` is null for complete/partial. Do not accept prose counts, legacy confidence/scope/no-finding fields, or infer status. Run `python3 "$HELPER" validate-stage --run-dir "$RUN" --sidecar <mapped-output>` for every slot; only helper markers prove readiness.

### Aggregate and handoff

Run `python3 "$HELPER" aggregate --run-dir "$RUN"`. It alone validates all slots/run binding, deduplicates, counts, decides status/verdict, and atomically publishes canonical findings, `telegram-summary.txt`, optional compact Russian `audit.md`, then `delivery-summary.json` last. `complete+0` has no MD; `partial` always has MD and is explicitly incomplete; `blocked` publishes no completion payload. Do not derive findings from Markdown or edit helper outputs.

Atomically create strict `$RUN/delivery-handoff.json` with only `schema_version:1`, `delivery_contract:"uaudit-delivery/v1"`, exact `run_dir`, `delivery_summary`, `issue_identifier`, `platform`, `audit_kind`, and context `source_ref`. Choose message only for validated `complete+0+report:null`, otherwise document; run `python3 "$HELPER" verify-payload --run-dir "$RUN" --handoff "$RUN/delivery-handoff.json" --expected-mode <message|document>`. Then assign `{{bindings.agents.UWIInfraEngineer}}` with `mode=pr_delivery`, contract and exact handoff/summary paths. Only after successful assignment API response atomically create `status/handoff.done`; it never means delivered.

### Smoke mode

`UAudit subagent smoke` is not v1 completion. Use synthetic `smoke/{pr.json,pr.diff,subagents/,summary.json}`, the same exact-agent/timeouts, and block on missing/malformed/secret-reading/writing reviewers. Summary records expected/completed count, exact names, generic/default usage, and one outcome each without diff/secrets. Hand it to `UWIInfraEngineer`; unversioned delivery requires the exact legacy allowlist/report digest or fails closed.
