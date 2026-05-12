# Telegram Report Delivery

Use this runbook when a Paperclip agent saved a Markdown report but could not
deliver it because Telegram delivery is Board-gated.

This is an operator path. Do not add this full procedure to agent instructions.

## UAudit Current Values

| Field | Value |
|---|---|
| Company ID | `8f55e80b-0264-4ab6-9d56-8b2652f18005` |
| Telegram plugin ID | `60023916-4b6c-40f5-829f-bc8b98abc4ed` |
| Issue identifier prefix | `UNS-*` |
| Default delivery owner | `UWAInfraEngineer` |
| iOS-only delivery owner | `UWIInfraEngineer` |

The Telegram chat is selected by plugin `fileRoutes`. Do not pass `chatId`.

## Daily UAudit Delta Delivery

UAudit daily version-branch audits are owned end-to-end by infra agents:

- iOS: `UWIInfraEngineer`
- Android: `UWAInfraEngineer`

Their scheduled issues contain `UAudit daily version-branch delta audit`.
Infra fetches the version branch, compares the branch head with the platform
cursor, refreshes codebase-memory, runs the UAudit subagents, writes
`audit.md`, sends the report through this Telegram plugin, and only then
advances the cursor.

Cursor files:

- `/Users/Shared/UnstoppableAudit/state/ios-version-audit.json`
- `/Users/Shared/UnstoppableAudit/state/android-version-audit.json`

Do not manually advance a cursor after a failed or permission-blocked delivery.
The cursor represents `last_successfully_audited_sha`, not merely the local
checkout state.

## Infra Agent Runtime Env Repair

Use this when an infra agent builds the correct Telegram plugin payload but the
plugin returns `{"error":"Board access required"}`.

Cause: the infra agent runtime does not have a Board-scoped
`PAPERCLIP_API_KEY`. Host `.env` may be correct, but Paperclip issue runs only
see values present in the live agent `adapterConfig.env`.

Fix the live infra agent configuration, not the report payload:

- Add `PAPERCLIP_API_KEY` to the infra agent `adapterConfig.env` from the
  operator Board token.
- Add `PAPERCLIP_API_URL` to the same `adapterConfig.env`.
- Preserve the existing `adapterConfig` fields, especially `cwd`,
  `CODEX_HOME`, `PATH`, model, sandbox, and extra args.
- Keep agent instructions short: tell infra to use `PAPERCLIP_API_KEY` and
  `PAPERCLIP_API_URL` from runtime env for delivery, and not to read `.env`.
- Redeploy or save that agent configuration, then retry only the blocked
  delivery issue.

Do not "fix" this by passing `chatId`, raw Telegram bot tokens, direct
`api.telegram.org` calls, `filePath`, URLs, or by teaching runtime agents to
read operator `.env`/`auth.json` files. Those paths bypass the file-route
contract and are the source of recurring drift.

Post-fix proof is a plugin response containing `ok:true`,
`routeSource:"file_route"`, `routeName` for the project, `mode:"document"`, and
a `messageId`.

## Manual Markdown Delivery

Run from the iMac host where `.env` contains a Board-capable
`PAPERCLIP_API_KEY`.

```bash
cd /Users/Shared/Ios/Gimle-Palace

REPORT_PATH="/absolute/path/to/report.md" \
ISSUE_IDENTIFIER="UNS-10" \
MARKDOWN_FILE_NAME="UNS-10-report.md" \
AGENT_ID="5f0709f8-0b05-43e7-8711-6df618b95f69" \
python3 - <<'PY'
import json
import os
import pathlib
import urllib.error
import urllib.request

env = {}
for line in pathlib.Path(".env").read_text().splitlines():
    if line and not line.startswith("#") and "=" in line:
        key, value = line.split("=", 1)
        env[key] = value

api = env.get("PAPERCLIP_API_URL", "http://localhost:3100").rstrip("/")
api_key = env["PAPERCLIP_API_KEY"]
plugin_id = "60023916-4b6c-40f5-829f-bc8b98abc4ed"
company_id = "8f55e80b-0264-4ab6-9d56-8b2652f18005"

report_path = pathlib.Path(os.environ["REPORT_PATH"])
payload = {
    "params": {
        "companyId": company_id,
        "agentId": os.environ["AGENT_ID"],
        "issueIdentifier": os.environ["ISSUE_IDENTIFIER"],
        "markdownFileName": os.environ["MARKDOWN_FILE_NAME"],
        "markdownContent": report_path.read_text(),
    }
}

request = urllib.request.Request(
    f"{api}/api/plugins/{plugin_id}/actions/send_to_telegram",
    data=json.dumps(payload).encode(),
    headers={
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    },
    method="POST",
)

try:
    with urllib.request.urlopen(request, timeout=30) as response:
        print(response.status)
        print(response.read().decode("utf-8", "replace"))
except urllib.error.HTTPError as error:
    print(error.code)
    print(error.read().decode("utf-8", "replace"))
    raise
PY
```

Expected successful response includes:

- `ok: true`
- `mode: "document"`
- `routeSource: "file_route"`
- `routeName: "UAudit"`
- `issueIdentifier: "UNS-..."`

If the response is `Board access required`, stop. Save or comment the artifact
path on the issue and rerun only with Board-capable credentials. Do not retry
with `chatId`, raw bot tokens, direct `api.telegram.org`, URLs, or `filePath`.

## Smoke Checklist

For any report-delivery smoke, verify all of these before closing the parent
issue:

- The Markdown artifact exists at the path reported by the agent.
- The delivery call used `issueIdentifier`, not `chatId`.
- The plugin response returned `ok:true`.
- The plugin response used `routeSource:file_route`.
- The plugin response used `mode:document`.
- The parent issue comment includes the delivered file name and plugin
  `messageId`.

Ownership-only confirmation is not enough; the smoke is complete only after the
file delivery path has been exercised or explicitly marked permission-blocked.
