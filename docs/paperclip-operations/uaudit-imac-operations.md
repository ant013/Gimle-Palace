# UAudit — live operations on iMac

Use this runbook for a request about the current UAudit state, runs, logs, or
data. It is a read-only diagnostic procedure unless the user explicitly asks
for a Paperclip or runtime mutation.

The repository checkout on the MacBook is for development. It is not evidence
of the live UAudit service. Do not replace an unavailable iMac result with a
local search.

## Canonical target

| Item | Value |
| --- | --- |
| SSH target | `imac-ssh.ant013.work` |
| Expected remote host | `Antons-iMac.local` |
| UAudit path configuration | `/Users/anton/.paperclip/projects/uaudit/paths.yaml` |
| UAudit project root | `/Users/Shared/UnstoppableAudit` |
| UAudit run artifacts | `/Users/Shared/UnstoppableAudit/runs` |
| UAudit state and locks | `/Users/Shared/UnstoppableAudit/state` |
| Paperclip run logs | `/Users/anton/.paperclip/instances/default/data/run-logs` |

`paths.yaml` is the authority for the UAudit project root and workspace paths.
The literal values above were verified on 2026-08-18; read only the required
path keys again before relying on them, because an operator may move the
runtime.

## 1. iMac preflight

Use batch mode first. It prevents an unattended password prompt and proves
which host received the command.

```bash
ssh -o BatchMode=yes -o ConnectTimeout=10 imac-ssh.ant013.work \
  'hostname; date "+%Y-%m-%d %H:%M:%S %Z"'
```

Continue only when the hostname identifies the iMac. Report an SSH failure as
a blocker; do not search the local checkout instead.

Then read only the path keys needed for the query:

```bash
ssh -o BatchMode=yes imac-ssh.ant013.work '
  rg -n "^(project_root|team_workspace_root):" \
    /Users/anton/.paperclip/projects/uaudit/paths.yaml
'
```

## 2. Period and source selection

Unless the user supplies a calendar interval, “last two days” means the
preceding 48 hours, measured on the iMac (`-mmin -2880`). State that basis and
the iMac timezone in the result.

Use the smallest source that answers the request:

- A specific UAudit audit: its `runs/UNS-<N>-audit/` directory, including
  `run-context.json`, `status/`, `*.findings.json`, `delivery-summary.json`,
  and delivery markers when present.
- Daily UAudit health: `state/` cursors and locks, then the matching recent
  directories under `runs/`.
- Paperclip orchestration chronology: the Paperclip issue API described in
  [`API.md`](../../API.md), or the matching `.ndjson` file under
  `data/run-logs/` when its company, issue, and run identifiers are already
  known. Do not scan unrelated companies' logs.

The UAudit run directory is authoritative for audit artifacts. The Paperclip
run log is supplementary orchestration evidence and must be correlated by
identifier before it is attributed to UAudit.

## 3. Read-only inspection

Discover recent UAudit artifact names and timestamps without reading source
repositories or secrets:

```bash
ssh -o BatchMode=yes imac-ssh.ant013.work '
  root=/Users/Shared/UnstoppableAudit
  find "$root/runs" -type f -mmin -2880 \
    -exec stat -c "%y %n" {} + 2>/dev/null | sort -r
  find "$root/state" -maxdepth 3 -type f -print 2>/dev/null
'
```

For a known run, inspect only its state-bearing files. Prefer names, timestamps
and status fields; redact any accidental secret-bearing field rather than
returning it.

```bash
ssh -o BatchMode=yes imac-ssh.ant013.work '
  run=/Users/Shared/UnstoppableAudit/runs/UNS-<N>-audit
  find "$run" -maxdepth 2 -type f \
    \( -name "run-context.json" -o -name "*.findings.json" \
       -o -name "delivery-summary.json" -o -path "*/status/*" \) \
    -exec stat -c "%y %n" {} + 2>/dev/null | sort -r
'
```

For any state or JSON output, report only the fields needed for operational
status: issue/run identifier, timestamps, status, blockers, cursor position,
delivery result, and artifact paths. Do not paste entire raw logs or JSON
blobs.

## 4. Authentication failure

Do not copy or pre-load credentials before the batch-mode SSH preflight fails.
If it does fail, report the exact non-secret failure class first. The only
approved fallback locations are:

```text
/Users/ant013/Android/Gimle-Palace-native
/Users/ant013/Android/Gimle-Palace-native-dev
```

Inspect only the minimum credential material necessary to restore the requested
connection; never print it, add it to this repository, or leave a copied secret
in the worktree. If no safe, existing SSH configuration can be identified,
stop and ask the operator rather than guessing a password, host, or key.

For authenticated Paperclip API reads, first follow [`API.md`](../../API.md).
It defines the endpoint and secret-handling contract. API keys, JWTs and raw
env-file values must never be included in terminal output, documentation,
issues, or reports.

## 5. Reporting contract

Every live-status answer should state:

1. that the evidence came from iMac and the checked time window/timezone;
2. the exact run/state/log paths inspected;
3. completed, active, partial, blocked, missing, or stale status for each
   relevant artifact;
4. the concrete blocker when access or evidence is absent; and
5. whether the conclusion comes from UAudit artifacts, Paperclip orchestration
   logs, or both.

An empty 48-hour search means no matching files changed in that window; it does
not prove that no audit exists. Distinguish it from unavailable paths,
authentication failure, and malformed/blocked artifacts.
