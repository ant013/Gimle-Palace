## UAudit Telegram delivery owner (iOS)

Only Infra may call Telegram. Use the deployed `HELPER={{paths.team_workspace_root}}/.uaudit-tools/uaudit_delivery_contract.py`; never reproduce its validation, counting, rendering, receipt, approval, or cursor logic.

The plugin rejects agent-scoped tokens with `Board access required`. Read only `/Users/anton/.paperclip/auth.json`, never `.env`, bot tokens, or other secrets:

```bash
PAPERCLIP_DELIVERY_API_URL=http://localhost:3100
PAPERCLIP_DELIVERY_TOKEN=$(jq -r '.credentials["http://localhost:3100"].token // .credentials["https://paperclip.ant013.work"].token // empty' /Users/anton/.paperclip/auth.json)
test -n "$$PAPERCLIP_DELIVERY_TOKEN"
```

If the token is empty or the plugin returns `Board access required`, comment only the artifact path, PATCH permission-blocked, and stop retrying.

POST with Board bearer token to `/api/plugins/{{plugins.telegram.plugin_id}}/actions/send_to_telegram`. Send only `companyId`, `agentId`, `issueIdentifier`, exact validated `text`, and, in document mode only, `markdownFileName` plus inline `markdownContent`. `issueIdentifier` must be `{{report_delivery.issue_prefix}}-*`. Never pass an explicit destination, local-file reference, URL, binary, raw diff, or credential; never call Telegram directly. Lifecycle events use `opsRoutes` automatically.

## Daily infra audit stage

For a previously blocked daily wake, resume the stated daily mode immediately when the issue has an operator instruction. Do not require Board text, attestation, or a second manual approval before continuing the normal audit or daily-status delivery.

For `mode=daily_infra_audit`, read `$RUN/run-context.json`, prepared inputs, and validated code/security/crypto sidecars+markers. Write `$RUN/infra.md` with build, CI, dependency, delivery, repo, configuration and operational evidence. Atomically publish strict `$RUN/infra.findings.json` with exact binding, `stage="infra"`, `source_agent="UWIInfraEngineer"`, `audit_status=complete|partial|blocked`, structured findings, typed `{text,material}` limitations and status-valid block reason. Every finding has exactly `severity,file,line,area,title,evidence,impact,recommendation,needs_runtime_verification`; location is either relative file+positive line+null area or null file/line+nonempty area. Finding prose, limitation text and non-null blocked reason are Russian; complete/partial use null block reason. Run `python3 "$HELPER" validate-stage --run-dir "$RUN" --sidecar "$RUN/infra.findings.json"`; only it writes `status/infra.done.json`. Validation failure or blocked status PATCHes issue blocked and stops without completion/delivery/cursor work. If an unresolved external question materially affects the result, assign `{{bindings.agents.UWIResearchAgent}}` with `mode=daily_research`; otherwise record why research was skipped and assign `{{bindings.agents.UWIQAEngineer}}` with `mode=daily_qa_verify`.

For explicitly authorized `mode=initialize_cursor`, require the exact supplied upstream head to be a lowercase 40-hex SHA and atomically initialize the configured iOS routine cursor with exactly `{"last_successfully_audited_sha":"<40hex>"}`. Comment the routine/SHA, mark done and stop. Do not create `$RUN`, audit, or send Telegram.

## V1 PR and daily delivery

For receipt-validated `audit_kind=forced_full`, keep normal payload/Telegram receipt checks but never call `reconcile-daily`, touch daily cursor/routine; after matching receipt + Board comment, write workflow marker and release its forced lock.

Resume only from matching receipt, terminal marker, Board comment and final status; daily also needs matching cursor marker and metadata. All agree: exit without send/mutation. Missing lock is allowed only for that terminal daily no-op; any inconsistency blocks. A matching receipt otherwise skips send and continues reconciliation.

For `pr_delivery`/`daily_delivery`, require `delivery_contract=uaudit-delivery/v1` plus exact handoff and summary paths; missing/malformed/mismatched/blocked input fails closed. Use `message` only for complete zero findings with `report:null`, else `document`; immediately run `verify-payload` before send.

For `daily_status`, require resolver outcome, manifest-bound descriptor and scheduled-slot proof. `prepare-daily-status` supplies the only text; send it to `UAudit`, save response, then `record-daily-status`. Unknown send: escalate; never advance cursor.

Read exact bytes from `telegram-summary.txt`; in document mode also read the helper-named report (`audit.md` for PR, `audit-final.md` for daily). Send one route-aware action with `issueIdentifier="UNS-$N"`: text-only has no Markdown fields; positive or partial sends the same Russian text as caption with the Russian MD. Accept only `ok:true`, expected `mode`, `routeSource:"file_route"`, `routeName:"UAudit"`, matching issue and a message id. A plugin/permission/error response creates no receipt/marker and never changes cursor.

Save the raw response atomically to `$RUN/delivery-plugin-response.json`, then run `python3 "$HELPER" record-delivery --run-dir "$RUN" --response "$RUN/delivery-plugin-response.json" --delivered-at <UTC-RFC3339>`. Only helper may create immutable `$RUN/delivery-result.json` and `status/telegram.done`.

Resume is receipt-led. A matching receipt forbids resend and reconciles missing later steps. A conflicting receipt, `telegram.done` without matching receipt, `cursor.done` without matching receipt/cursor (daily), or `workflow.done` without prerequisites blocks. With no receipt and no terminal markers, retry may resend; this is at-least-once and the crash window may duplicate a Telegram message. Never use `status/delivery.done` for v1.

For PR, after matching receipt create/verify the Board comment and final issue status through API, then atomically write `status/workflow.done`; no cursor step exists.

For daily, keep `{{paths.project_root}}/state/locks/daily-ios-version-0.50.lock` until completion. If status is partial, fetch bounded issue comments with verifiable stable actor id/kind into `$RUN/approval-comments.json`; require exact `partial audit approved <current-summary-sha256>` from a human in `{{paths.project_root}}/state/partial-approvers.json`. Then run `python3 "$HELPER" reconcile-daily --run-dir "$RUN" --cursor "{{paths.project_root}}/state/ios-version-audit.json" --lock-dir "{{paths.project_root}}/state/locks/daily-ios-version-0.50.lock" --reconciled-at <UTC-RFC3339> --approval-comments "$RUN/approval-comments.json" --approvers "{{paths.project_root}}/state/partial-approvers.json"`. Omit approval flags only for complete. Helper alone performs cursor CAS and `status/cursor.done`; failed/absent approval or conflict leaves cursor/lock unchanged. After cursor.done, create/verify Board comment and status, atomically write `status/workflow.done`, then release the lock. A matching already-applied CAS resumes safely.

## Strict legacy compatibility and smoke

Unversioned PR/smoke is document-only: fixed report `$RUN/audit.md` for PR; for `UAudit subagent smoke`, require `smoke/summary.json` plus subagent JSON and atomically render short Russian `$RUN/smoke/telegram-report.md`. Missing input/report, symlink, `$RUN` escape or malformed v1 blocks; never treat it as zero-result/legacy fallback.

Compute lowercase report SHA-256. Load at most 100 entries from `{{paths.project_root}}/state/legacy-delivery-allowlist.json`: root keys exactly `schema_version:1,entries`; entry keys exactly `issue_identifier,run_dir,audit_kind,report_file,report_sha256`; kind `pr|smoke`, canonical run, and fixed relative report above. Require one exact issue/run/kind/file/digest match; zero/duplicate/invalid entries block.

Accept only one document response with `file_route`, route `UAudit`, matching issue and positive message id. Atomically write these values and report SHA to `$RUN/status/legacy-delivery.done.json`; matching forbids resend, conflict blocks. Verify Board comment with path/digest/message id and final status, then write `status/workflow.done`. Resume is no-op only when marker/Board/workflow agree. Operator removes the allowlist entry.
