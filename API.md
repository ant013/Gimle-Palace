# Gimle API Access Runbook

This is the first document to read before using Paperclip, watchdog, or
related operator APIs. Do not rediscover endpoints by grepping old specs
unless this file is missing the needed contract.

Secrets stay in `.env`. Never paste real API keys, JWT secrets, bearer
tokens, or private keys into issues, docs, logs, or PR comments.

## Environment

Load local operator credentials from the repo `.env`:

```bash
source /Users/ant013/Android/Gimle-Palace-claude/.env
```

Expected variables:

```bash
PAPERCLIP_API_URL=https://paperclip.ant013.work
PAPERCLIP_API_KEY=<from .env>
PAPERCLIP_COMPANY_ID=<company uuid, when present>
```

For Gimle, the company id currently used by Paperclip issues is:

```text
9d8f432c-ff7d-4e3a-bbe3-3cd355f73b64
```

Use the public URL for Board/operator actions unless you are explicitly
debugging a local server. Containers may use different internal URLs such
as `http://host.docker.internal:3100`; do not assume those are valid from
the host shell.

## Authentication

Preferred operator auth is a persistent Paperclip API key:

```bash
curl -s \
  -H "Authorization: Bearer $PAPERCLIP_API_KEY" \
  "$PAPERCLIP_API_URL/api/issues/<issue-id>"
```

JWT auth exists for internal agent/runtime flows, but most operator work
should not hand-roll JWTs. If a JWT is required, generate it from secrets
already present in `.env` or the runtime environment and keep the token
out of logs. Prefer existing project helpers over copying crypto snippets.

## Paperclip Issues API

Known working endpoints:

| Action | Method + path |
| --- | --- |
| List/find issues | `GET /api/companies/:companyId/issues?issueNumber=<N>` |
| Read issue | `GET /api/issues/:id` |
| Update issue | `PATCH /api/issues/:id` |
| Create issue | `POST /api/companies/:companyId/issues` |
| Add comment | `POST /api/issues/:id/comments` |
| Read comments | `GET /api/issues/:id/comments?limit=<N>` |
| Checkout issue | `POST /api/issues/:id/checkout` |
| Release issue | `POST /api/issues/:id/release` |

Important gotcha: company-scoped list/create routes are authoritative in
the current deployment. `GET /api/issues?companyId=...` returns a 400
asking for `/api/companies/{companyId}/issues`, and `POST /api/issues`
is not a create endpoint.

## Common Commands

Read an issue:

```bash
curl -s \
  -H "Authorization: Bearer $PAPERCLIP_API_KEY" \
  "$PAPERCLIP_API_URL/api/issues/<issue-id>"
```

Find an issue by number:

```bash
curl -s \
  -H "Authorization: Bearer $PAPERCLIP_API_KEY" \
  "$PAPERCLIP_API_URL/api/companies/$PAPERCLIP_COMPANY_ID/issues?issueNumber=<number>"
```

Create an issue:

```bash
curl -s -X POST \
  -H "Authorization: Bearer $PAPERCLIP_API_KEY" \
  -H "Content-Type: application/json" \
  --data @issue.json \
  "$PAPERCLIP_API_URL/api/companies/$PAPERCLIP_COMPANY_ID/issues"
```

Minimal create payload:

```json
{
  "title": "GIM-NNN follow-up - short title",
  "description": "Goal, evidence, required work, acceptance criteria.",
  "parentId": "<parent-issue-id>",
  "status": "todo",
  "priority": "high",
  "assigneeAgentId": "<agent-uuid>"
}
```

Block one issue on another:

```bash
curl -s -X PATCH \
  -H "Authorization: Bearer $PAPERCLIP_API_KEY" \
  -H "Content-Type: application/json" \
  --data '{"status":"blocked","blockedByIssueIds":["<blocker-issue-id>"]}' \
  "$PAPERCLIP_API_URL/api/issues/<blocked-issue-id>"
```

Wake an assignee with a comment:

```bash
curl -s -X POST \
  -H "Authorization: Bearer $PAPERCLIP_API_KEY" \
  -H "Content-Type: application/json" \
  --data '{"body":"[@AgentName](agent://<agent-id>?i=bug) your turn - clear instruction."}' \
  "$PAPERCLIP_API_URL/api/issues/<issue-id>/comments"
```

Reassign an issue:

```bash
curl -s -X PATCH \
  -H "Authorization: Bearer $PAPERCLIP_API_KEY" \
  -H "Content-Type: application/json" \
  --data '{"assigneeAgentId":"<agent-uuid>"}' \
  "$PAPERCLIP_API_URL/api/issues/<issue-id>"
```

## Wake-Up Rules

Use `POST /api/issues/:id/comments` when you need to wake the assignee or
mentioned agents.

Do not rely on `PATCH /api/issues/:id` with a `comment` field for wake-up.
Patch comments wake only in specific cases such as assignee change,
moving out of backlog, or explicit mentions. A no-mention patch comment
can silently stall.

For handoff, do both when appropriate:

1. `PATCH /api/issues/:id` with `assigneeAgentId`.
2. `POST /api/issues/:id/comments` with a direct mention and exact next
   action.

## Execution Locks

If `PATCH /api/issues/:id` returns conflict, read the issue and inspect:

```text
executionRunId
executionAgentNameKey
executionLockedAt
```

Try normal release first:

```bash
curl -s -X POST \
  -H "Authorization: Bearer $PAPERCLIP_API_KEY" \
  "$PAPERCLIP_API_URL/api/issues/<issue-id>/release"
```

Then reassign if needed. Do not kill agent processes or clear locks unless
you have confirmed the process is stale and the operator explicitly wants
that recovery path.

## Watchdog

Watchdog uses the same Paperclip API contract. The normal recovery shape is:

1. Read issue state with `GET /api/issues/:id`.
2. Release stale lock with `POST /api/issues/:id/release`.
3. Reassign with `PATCH /api/issues/:id`.
4. Wake with `POST /api/issues/:id/comments`.

The watchdog code path lives under:

```text
services/watchdog/src/gimle_watchdog/paperclip.py
```

Use watchdog behavior as the reference for recovery flow, not old ad hoc
commands in issue comments.

## Palace MCP Health

Production iMac `palace-mcp` is normally published on host port `8080`:

```bash
curl -s http://localhost:8080/healthz
```

Expected healthy response:

```json
{"status":"ok","neo4j":"reachable"}
```

Isolated smoke runs may publish MCP on another host port such as `18080`
when production already occupies `8080`. Always report the compose project
name and host port used in QA evidence.

## Known Gotchas

- `POST /api/issues` returns route-not-found; create via
  `POST /api/companies/:companyId/issues`.
- `GET /api/issues?companyId=...` returns 400; list/find via
  `GET /api/companies/:companyId/issues`.
- Comment creation wakes agents; patch comments can stall.
- `blockedByIssueIds` should be set when a blocked issue has a concrete
  follow-up. Do not leave `status=blocked` with empty `blockedBy` unless
  the blocker is outside Paperclip.
- Do not reuse or delete default `gimle-palace_*` Docker volumes during
  isolated smoke verification.
- Do not paste secrets from `.env`. Refer to variable names only.
- When an endpoint is uncertain, check `OPTIONS` first before trying
  mutating calls:

```bash
curl -s -i -X OPTIONS \
  -H "Authorization: Bearer $PAPERCLIP_API_KEY" \
  "$PAPERCLIP_API_URL/api/companies/$PAPERCLIP_COMPANY_ID/issues"
```
