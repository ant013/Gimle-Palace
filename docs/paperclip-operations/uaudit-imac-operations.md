# UAudit — live operations on iMac

Use this runbook for the current UAudit state, daily routines, issues, runs, or
logs. It is read-only unless the user explicitly requests a Paperclip or
runtime mutation.

## Fast path: Paperclip access

For Paperclip control-plane access, load the persistent Codex environment:

```bash
set -a
source /Users/ant013/.codex/.env
set +a
curl -fsS --max-time 30 --connect-timeout 10 -H "Authorization: Bearer $PAPERCLIP_API_KEY" "$PAPERCLIP_API_URL/api/cli-auth/me" | jq '{source, companyIds}'
```

The expected result has `source: "board_key"`. Never print the environment,
the bearer token, or a raw request header. `/Users/ant013/.codex/.env` is a
local link to the approved operator environment at
`/Users/ant013/Android/Gimle-Palace-claude/.env`; it is deliberately outside
the repository and must not be committed or copied into a worktree.

Use the authenticated company list to locate `UnstoppableAudit`, then inspect
only the daily-routine state needed for the request:

```bash
uaudit_company_id=$(for id in $(curl -fsS -H "Authorization: Bearer $PAPERCLIP_API_KEY" "$PAPERCLIP_API_URL/api/cli-auth/me" | jq -r '.companyIds[]'); do curl -fsS -H "Authorization: Bearer $PAPERCLIP_API_KEY" "$PAPERCLIP_API_URL/api/companies/$id"; done | jq -r 'select(.name == "UnstoppableAudit") | .id')
curl -fsS -H "Authorization: Bearer $PAPERCLIP_API_KEY" "$PAPERCLIP_API_URL/api/companies/$uaudit_company_id/routines" | jq '.[] | select(.title | test("UAudit daily (Android|iOS)")) | {title, status, lastTriggeredAt, triggers, lastRun, activeIssue}'
```

For an individual issue, use the ID returned by the routine or issue list:

```bash
curl -fsS -H "Authorization: Bearer $PAPERCLIP_API_KEY" "$PAPERCLIP_API_URL/api/issues/<issue-id>" | jq '{identifier, title, status, updatedAt, executionRunId, executionAgentNameKey, executionLockedAt}'
```

Follow [`API.md`](../../API.md) for the authoritative endpoint, authentication,
and mutation contract. Do not use these read-only commands to release locks,
advance cursors, approve audits, or modify schedules.

## iMac artifact inspection

Paperclip state explains orchestration, but iMac artifacts remain authoritative
for cursors, lock metadata, run artifacts, and delivery receipts. Use the
smallest source that answers the question.

| Item | Value |
| --- | --- |
| SSH target | `imac-ssh.ant013.work` |
| Expected remote host | `Antons-iMac.local` |
| UAudit project root | `/Users/Shared/UnstoppableAudit` |
| Run artifacts | `/Users/Shared/UnstoppableAudit/runs` |
| State and locks | `/Users/Shared/UnstoppableAudit/state` |
| Paperclip run logs | `/Users/anton/.paperclip/instances/default/data/run-logs` |

First attempt a non-interactive SSH preflight:

```bash
ssh -o BatchMode=yes -o ConnectTimeout=10 imac-ssh.ant013.work 'hostname; date "+%Y-%m-%d %H:%M:%S %Z"'
```

When SSH succeeds, use it for filesystem evidence. For example, inspect recent
daily-audit state without reading source repositories or secrets:

```bash
ssh -o BatchMode=yes imac-ssh.ant013.work 'root=/Users/Shared/UnstoppableAudit; find "$root/runs" -type f -mmin -2880 -exec stat -f "%Sm %N" {} + 2>/dev/null | sort -r; find "$root/state" -maxdepth 3 -type f -print 2>/dev/null'
```

When SSH authentication fails, report the non-secret failure class. Do not
guess a password, host, or key; continue with the Paperclip fast path only for
control-plane evidence. The API cannot prove the exact cursor, lock metadata,
run artifact, or delivery receipt.

## Reporting contract

State whether each conclusion is based on iMac artifacts, Paperclip API
control-plane evidence, or both. Include the time window/timezone, the exact
paths or API resources inspected, each routine or issue status, and any
concrete blocker. An empty artifact search is not proof that no audit exists.
