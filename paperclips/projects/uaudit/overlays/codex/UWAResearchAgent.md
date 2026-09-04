---
target: codex
role_id: codex:uwa-research-agent
family: research
profiles: [research]
---

## Daily Version-Branch Research Stage (Android)

For `mode=daily_research`, set `HELPER={{paths.team_workspace_root}}/.uaudit-tools/uaudit_delivery_contract.py`; read `$RUN/run-context.json`, validated prior sidecars/markers and only references needed for open library, protocol, or platform questions. Do not redo prior audits.

Write cited human context to `$RUN/research-context.md`. Atomically publish `$RUN/research-context.findings.json` as the strict v1 envelope with exact copied `run_binding`, `stage="research_context"`, `source_agent="UWAResearchAgent"`, `audit_status=complete|partial|blocked`, structured findings, typed `{text,material}` limitations, and status-valid `block_reason`. Every finding has exactly `severity,file,line,area,title,evidence,impact,recommendation,needs_runtime_verification`; location is either relative file+positive line+null area or null file/line+nonempty area. Finding prose, limitation text and non-null blocked reason are Russian; complete/partial use null block reason. Do not count/deduplicate or add fields.

Severity is `Critical|Block|Important|Observation`. The helper canonicalizes known aliases with a Russian `material=false` warning. Fix a recoverable sidecar format/schema error without changing binding/evidence, then retry `validate-stage` exactly once. Never PATCH the issue to `blocked` or request Board approval for a recoverable output error.

Run `python3 "$HELPER" validate-stage --run-dir "$RUN" --sidecar "$RUN/research-context.findings.json"`; only it creates digest-bound `status/research_context.done.json`. Validation failure or `blocked` PATCHes issue blocked and stops without completion. Otherwise comment ready, PATCH `{{bindings.agents.UWAQAEngineer}}` with `mode=daily_qa_verify`, and stop. Never send Telegram or update state/cursors.
