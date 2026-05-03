## Creating Paperclip agents from Codex

Use the Paperclip approval flow. Never patch an existing agent into a different
runtime, and never write agent rows directly to the database.

Preflight:

```bash
curl -sS "$PAPERCLIP_API_URL/api/agents/me" \
  -H "Authorization: Bearer $PAPERCLIP_API_KEY"

curl -sS "$PAPERCLIP_API_URL/api/companies/$PAPERCLIP_COMPANY_ID/agent-configurations" \
  -H "Authorization: Bearer $PAPERCLIP_API_KEY"

curl -sS "$PAPERCLIP_API_URL/llms/agent-configuration/codex_local.txt" \
  -H "Authorization: Bearer $PAPERCLIP_API_KEY"
```

If `PAPERCLIP_AGENT_ID` is available, also verify runtime skills:

```bash
curl -sS "$PAPERCLIP_API_URL/api/agents/$PAPERCLIP_AGENT_ID/skills" \
  -H "Authorization: Bearer $PAPERCLIP_API_KEY"
```

Codex hire payload shape:

```json
{
  "name": "CodexCodeReviewer",
  "role": "engineer",
  "title": "Codex Code Reviewer",
  "icon": "eye",
  "reportsTo": "<cto-or-ceo-agent-id>",
  "capabilities": "Reviews implementation changes using Codex runtime, repository context MCP, and Paperclip issue workflow.",
  "adapterType": "codex_local",
  "adapterConfig": {
    "cwd": "/Users/Shared/Ios/worktrees/cx/Gimle-Palace",
    "model": "gpt-5.5",
    "modelReasoningEffort": "high",
    "instructionsFilePath": "AGENTS.md",
    "instructionsBundleMode": "managed",
    "maxTurnsPerRun": 200,
    "timeoutSec": 0,
    "graceSec": 15,
    "env": {
      "CODEX_HOME": "/Users/anton/.paperclip/instances/default/companies/9d8f432c-ff7d-4e3a-bbe3-3cd355f73b64/codex-home",
      "PATH": "/Users/anton/.local/bin:/Users/anton/.nvm/versions/node/v20.20.2/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
    }
  },
  "runtimeConfig": {
    "heartbeat": {
      "enabled": false,
      "intervalSec": 14400,
      "wakeOnDemand": true,
      "maxConcurrentRuns": 1,
      "cooldownSec": 10
    }
  },
  "budgetMonthlyCents": 0,
  "sourceIssueId": "<originating-issue-uuid>"
}
```

Procedure:

1. Submit `POST /api/companies/:companyId/agent-hires`.
2. If the response is `pending_approval`, stop and report the approval id.
3. After approval, upload the generated `AGENTS.md` with
   `PUT /api/agents/:id/instructions-bundle/file`.
4. Before upload, fetch the target agent config and require
   `adapterType: "codex_local"`.
5. Verify the company Codex home exposes common MCP, agents, and skills.
6. Run a narrow smoke task before assigning implementation work.
