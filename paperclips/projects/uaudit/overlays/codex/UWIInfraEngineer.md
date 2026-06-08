## Telegram Report Delivery (UAudit)

The Telegram plugin action rejects agent-scoped runtime tokens with
`Board access required`. Read only `/Users/anton/.paperclip/auth.json` for this token; never `.env`,
bot tokens, or other secrets:

```bash
PAPERCLIP_DELIVERY_API_URL=http://localhost:3100
PAPERCLIP_DELIVERY_TOKEN=$(jq -r '.credentials["http://localhost:3100"].token // .credentials["https://paperclip.ant013.work"].token // empty' /Users/anton/.paperclip/auth.json)
test -n "$$PAPERCLIP_DELIVERY_TOKEN"
```

Send with `Authorization: Bearer $$PAPERCLIP_DELIVERY_TOKEN`:
`POST $$PAPERCLIP_DELIVERY_API_URL/api/plugins/{{plugins.telegram.plugin_id}}/actions/send_to_telegram`
body `{"params":{"companyId":"{{bindings.company_id}}","agentId":"$$PAPERCLIP_AGENT_ID","issueIdentifier","markdownFileName","markdownContent"}}`.
`issueIdentifier` MUST be `{{report_delivery.issue_prefix}}-*`; never pass
`chatId`. Inline Markdown only — no `filePath`, URLs, binaries, bot tokens, or
direct `api.telegram.org`. If `PAPERCLIP_DELIVERY_TOKEN` is empty or the plugin
still returns `Board access required`, save/comment the artifact path, mark
delivery permission-blocked, and stop retrying. Lifecycle events are auto-routed
via `opsRoutes`; do not emit them manually.

## Daily Version-Branch Delta Audit Executor (iOS)

Run this path only after `UWICTO` PATCHes this issue to you with a daily audit handoff. You execute the decision that `UWICTO` already made. Do not decide no-op, rollback, history rewrite, missing-cursor, or oversized-delta cases yourself.

### Constants

```bash
N=<issueNumber of this Paperclip issue>
RUN={{paths.team_workspace_root}}/UNS-$N-audit
REPO={{paths.primary_repo_root}}
BRANCH=version/0.49
CURSOR={{paths.project_root}}/state/ios-version-audit.json
CODEBASE_MEMORY_PROJECT=Users-Shared-UnstoppableAudit-repos-ios-unstoppable-wallet-ios
```

Required subagents for `mode=audit_delta`, all mandatory:

- `uaudit-swift-audit-specialist`
- `uaudit-bug-hunter`
- `uaudit-security-auditor`
- `uaudit-blockchain-auditor`

Use `spawn_agent` with explicit `agent_type` equal to the exact required name. A call with omitted `agent_type`, `default`, or a generic role is a failed run. Do not substitute a missing subagent.

### Accepted Handoff Modes

`mode=initialize_cursor`: write the exact upstream head SHA supplied by `UWICTO` to `$CURSOR`, comment the initialized SHA and routine id, mark done, and stop. Do not create `$RUN`, do not audit, and do not send Telegram.

`mode=audit_delta`: create `$RUN/{status,subagents}` and audit only the supplied FROM..TO range. Verify the handoff includes FROM, TO, routine id, required subagent roster, and limits. If any handoff value is missing or the roster differs from `paperclips/projects/uaudit/daily-version-branch-routines.yaml`, write `$RUN/status/blocked`, comment the mismatch, and leave the cursor unchanged.

### Delta Materialization

Fetch remote branch data and verify the supplied TO matches authoritative upstream:

```bash
git -C "$REPO" fetch https://github.com/horizontalsystems/unstoppable-wallet-ios.git "$BRANCH"
UPSTREAM_TO=$(git -C "$REPO" rev-parse FETCH_HEAD)
test "$UPSTREAM_TO" = "<handoff TO>"
```

Write artifacts for the supplied range only:

```bash
git -C "$REPO" log --format='%H%x09%an%x09%aI%x09%s' "<FROM>..<TO>" > "$RUN/commits.tsv.tmp"
git -C "$REPO" diff --name-status "<FROM>..<TO>" > "$RUN/files.tsv.tmp"
git -C "$REPO" diff "<FROM>..<TO>" > "$RUN/diff.patch.tmp"
```

Atomically move final artifacts to `$RUN/commits.json`, `$RUN/files.json`, and `$RUN/diff.patch`. Block instead of auditing if the realized delta exceeds the handed-off limits: more than 30 commits, more than 300 files, or more than 3000 changed diff lines.

### Checkout And Memory Refresh

Checkout the audited code before subagent fanout:

```bash
git -C "$REPO" checkout --detach "<TO>"
```

Refresh/enrich codebase-memory for `$REPO` after checkout and before spawning subagents. Use the `codebase-memory` MCP indexer for `$CODEBASE_MEMORY_PROJECT` when available; if unavailable, write `$RUN/status/blocked` and stop. Do not audit stale branch context.

### Subagent Fanout

Start the four required subagents in parallel immediately after memory refresh. Give each subagent only `$RUN/diff.patch`, `$RUN/commits.json`, `$RUN/files.json`, `$REPO`, and `$CODEBASE_MEMORY_PROJECT`.

Subagents are read-only reviewers. They must not write files, post comments, deploy, send Telegram, or read secrets. Require JSON with agent name, reviewed scope, findings, no-finding areas, and limitations. Wrong agent name, malformed JSON, timeout after one retry, or generic fallback blocks the run and leaves the cursor unchanged.

Persist each completed subagent JSON immediately; keep statuses in `$RUN/subagents/status.json`.
On timeout, write `$RUN/recovery.json`; resume by spawning only missing reviewers.

### Aggregate, Deliver, And Commit Cursor

Write `$RUN/audit.md` in English with issue id, branch, FROM, TO, counts, roster, verdict, findings grouped by severity, disagreements, no-finding areas, limitations, and methodology.

Send `$RUN/audit.md` through Telegram as `markdownFileName="uaudit-ios-version-0.49-delta-UNS-$N.md"`. Verify `ok:true`, `routeSource:file_route`, `routeName:UAudit`, and `mode:document`.

Never advance the cursor before successful Telegram delivery. Only after successful delivery, atomically update `$CURSOR` with `<TO>`, `UNS-$N`, and current UTC ISO-8601 timestamp. Then comment the report path, delivered filename, message id, FROM..TO, and mark done.

## Prepared Audit Delivery (Backward Compatibility)

When a UAudit role PATCHes assignee onto you for a UNS-N PR-audit issue without the daily-delta marker, a prepared `audit.md` may be waiting at `{{paths.team_workspace_root}}/UNS-<N>-audit/audit.md`. You do not modify it. Compute its SHA-256, send it through the Telegram plugin using `issueIdentifier="UNS-$N"`, comment filename + `messageId` + SHA-256 digest, then mark the issue `done`.

## UAudit Subagent Smoke Delivery

If the current issue says `UAudit subagent smoke`, do not run deployment work or daily delta audit. Read `{{paths.team_workspace_root}}/UNS-$N-audit/smoke/summary.json`, create a short Telegram report from the smoke summary and subagent JSON files, send it through Telegram, comment the artifact path, and mark done. If the summary is missing, mark blocked and state the missing path.
