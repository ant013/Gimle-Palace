## Telegram Report Delivery (UAudit)

Send Markdown reports with `POST /api/plugins/{{plugins.telegram.plugin_id}}/actions/send_to_telegram`
and body `{"params":{"companyId":"{{bindings.company_id}}","agentId":"$PAPERCLIP_AGENT_ID","issueIdentifier","markdownFileName","markdownContent"}}`.
Use `PAPERCLIP_API_KEY` and `PAPERCLIP_API_URL` from your runtime environment
for this delivery call; do not read `.env` files.
`issueIdentifier` MUST be the current `{{report_delivery.issue_prefix}}-*`;
never pass `chatId`. Inline Markdown only: no `filePath`, URLs, binaries, bot
tokens, or direct `api.telegram.org`. On `Board access required`, save/comment
the artifact path, mark Telegram delivery permission-blocked, and stop retrying.
Lifecycle events are auto-routed via `opsRoutes`; do not emit them manually.

## Daily Version-Branch Delta Audit (Android)

If the issue body contains `UAudit daily version-branch delta audit` and
`platform: android`, you own the full audit and delivery cycle in this same
issue. Do not hand off to `UWAKotlinAuditor`.

### Constants

```bash
N=<issueNumber of this Paperclip issue>
RUN={{paths.team_workspace_root}}/UNS-$N-audit
REPO={{paths.project_root}}/repos/android/unstoppable-wallet-android
BRANCH=version/0.49
CURSOR={{paths.project_root}}/state/android-version-audit.json
CODEBASE_MEMORY_PROJECT=Users-Shared-UnstoppableAudit-repos-android-unstoppable-wallet-android
```

Required subagents, all mandatory:

- `uaudit-kotlin-audit-specialist`
- `uaudit-bug-hunter`
- `uaudit-security-auditor`
- `uaudit-blockchain-auditor`

Use `spawn_agent` with explicit `agent_type` equal to the exact required name.
A call with omitted `agent_type`, `default`, or a generic role is a failed run.
Do not substitute a missing subagent.

### Cursor Rules

`$CURSOR` is the source of truth:

```json
{
  "platform": "android",
  "branch": "version/0.49",
  "last_successfully_audited_sha": "<sha>",
  "last_successful_issue": "UNS-<N>",
  "last_successful_at": "<UTC ISO-8601>"
}
```

Never advance the cursor before successful Telegram delivery. If delivery,
aggregation, subagents, checkout, or codebase-memory refresh fails, leave the
cursor unchanged.

If the cursor file is missing, create it with `last_successfully_audited_sha`
set to `origin/$BRANCH` and mark the issue `done` with an initialization
comment. Do not audit from repository root history on first run.

### Delta Intake

Create `$RUN/{status,subagents}`. Fetch remote branch data and resolve:

```bash
git -C "$REPO" fetch https://github.com/horizontalsystems/unstoppable-wallet-android.git "$BRANCH"
TO=$(git -C "$REPO" rev-parse FETCH_HEAD)
FROM=$(jq -r '.last_successfully_audited_sha' "$CURSOR")
```

If `FROM == TO`, write `$RUN/status/noop.done`, comment `No new commits for
Android $BRANCH`, and mark the issue `done`.

For non-empty deltas, write:

```bash
git -C "$REPO" log --format='%H%x09%an%x09%aI%x09%s' "$FROM..$TO" > "$RUN/commits.tsv.tmp"
git -C "$REPO" diff --name-status "$FROM..$TO" > "$RUN/files.tsv.tmp"
git -C "$REPO" diff "$FROM..$TO" > "$RUN/diff.patch.tmp"
```

Convert TSV files to JSON if convenient, then atomically move final artifacts to:

- `$RUN/commits.json`
- `$RUN/files.json`
- `$RUN/diff.patch`

Block instead of auditing if the delta is too large:

- more than 30 commits;
- more than 3000 changed diff lines.

For a blocked oversized delta, write `$RUN/status/blocked`, comment the exact
commit and line counts, and leave the cursor unchanged.

### Checkout And Memory Refresh

Checkout the audited code before subagent fanout:

```bash
git -C "$REPO" checkout --detach "$TO"
```

Refresh/enrich codebase-memory for `$REPO` after checkout and before spawning
subagents. Use the `codebase-memory` MCP indexer for
`$CODEBASE_MEMORY_PROJECT` when available; if the MCP/indexer is unavailable,
write `$RUN/status/blocked` and stop. Do not audit stale branch context.

### Subagent Fanout

Start the four required subagents in parallel immediately after memory refresh.
Give each subagent only:

- `$RUN/diff.patch`
- `$RUN/commits.json`
- `$RUN/files.json`
- `$REPO`
- `$CODEBASE_MEMORY_PROJECT`

Subagents are read-only reviewers. They must not write files, post comments,
deploy, send Telegram, or read secrets. Require JSON with this shape:

```json
{
  "agent": "required exact agent name",
  "scope": "files and commit areas reviewed",
  "findings": [
    {
      "severity": "Critical | Block | Important | Observation",
      "confidence": "High | Medium | Low",
      "file": "path",
      "line": 123,
      "title": "one sentence",
      "evidence": "code-grounded evidence",
      "impact": "wallet/user/security impact",
      "recommendation": "minimal actionable fix",
      "false_positive_risk": "Low | Medium | High",
      "needs_runtime_verification": true
    }
  ],
  "no_finding_areas": ["areas explicitly checked with no issue"],
  "limitations": ["what static review could not verify"]
}
```

Wait up to 180 seconds per slot; retry each exact missing agent once. Malformed
JSON, wrong `"agent"`, missing required fields, timeout after retry, or generic
fallback blocks the run and leaves the cursor unchanged.

After validation, write the final JSON outputs under:

```text
$RUN/subagents/
  uaudit-kotlin-audit-specialist.json
  uaudit-bug-hunter.json
  uaudit-security-auditor.json
  uaudit-blockchain-auditor.json
```

### Aggregate, Deliver, And Commit Cursor

Write `$RUN/audit.md` in English. Include:

- title: `# Daily Android Version Delta Audit - version/0.49`
- issue identifier, branch, `FROM`, `TO`, commit count, file count;
- subagent roster;
- executive verdict: `approve`, `request changes`, or `block`;
- findings grouped by severity with source-agent attribution;
- conflicts/disagreements between subagents;
- no-finding areas and limitations;
- methodology: `git diff`, `codebase-memory`, `serena`, Codex subagents.

Send `$RUN/audit.md` through the Telegram plugin with
`markdownFileName="uaudit-android-version-0.49-delta-UNS-$N.md"`. Verify
`ok:true`, `routeSource:file_route`, `routeName:UAudit`, and `mode:document`.

Only after successful delivery, atomically update `$CURSOR`:

```json
{
  "platform": "android",
  "branch": "version/0.49",
  "last_successfully_audited_sha": "<TO>",
  "last_successful_issue": "UNS-<N>",
  "last_successful_at": "<UTC ISO-8601>"
}
```

Then comment the report path, delivered filename, message id, `FROM..TO`, and
mark the issue `done`.

## Prepared Audit Delivery (Backward Compatibility)

When UWACTO or another UAudit role PATCHes assignee onto you for a UNS-N
PR-audit issue without the daily-delta marker, a prepared `audit.md` may be
waiting at `{{paths.team_workspace_root}}/UNS-<N>-audit/audit.md`. You do
not modify it. Compute its SHA-256, send it through the Telegram plugin using
`issueIdentifier="UNS-$N"`, comment filename + `messageId` + SHA-256 digest,
then mark the issue `done`.

## UAudit Subagent Smoke Delivery

If the current issue says `UAudit subagent smoke`, do not run deployment work or
daily delta audit. Read:

```bash
N=<issueNumber of this Paperclip issue>
RUN={{paths.team_workspace_root}}/UNS-$N-audit
SUMMARY=$RUN/smoke/summary.json
```

Create `$RUN/smoke/telegram-report.md` from the smoke summary and subagent JSON
files. The Markdown must include:

- issue identifier and platform (`Android`);
- `expected_subagent_count` and `completed_subagent_count`;
- exact required subagent names;
- one short response/result line for each subagent;
- explicit PASS/FAIL verdict and blocker, if any.

Send that Markdown through the Telegram plugin using
`markdownFileName="uaudit-subagent-smoke-UNS-$N-android.md"`. Then comment the
artifact path and mark the issue `done`. If `summary.json` is missing, mark the
issue blocked and state the missing path.
