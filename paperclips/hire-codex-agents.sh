#!/usr/bin/env bash
# Submit Paperclip hire requests for the Codex/CX Gimle team.
# This creates approval requests only; it does not approve them.
set -euo pipefail

COMPANY_ID="${PAPERCLIP_COMPANY_ID:-9d8f432c-ff7d-4e3a-bbe3-3cd355f73b64}"
API_BASE="${PAPERCLIP_API_URL:-https://paperclip.ant013.work}"
SOURCE_ISSUE_ID="${PAPERCLIP_SOURCE_ISSUE_ID:-e7795ef5-a2df-4302-947b-6d8da7598bce}"
CODEX_HOME="${PAPERCLIP_CODEX_HOME:-/Users/anton/.paperclip/instances/default/companies/$COMPANY_ID/codex-home}"
CODEX_PATH="${PAPERCLIP_CODEX_PATH:-/Users/anton/.local/bin:/Users/anton/.nvm/versions/node/v20.20.2/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin}"
WORKSPACE="${PAPERCLIP_WORKSPACE:-/Users/Shared/Ios/Gimle-Palace}"

CEO_ID="${PAPERCLIP_CEO_ID:-10a4968e-ff2c-471a-a5a8-98026aeead1b}"
CTO_ID="${PAPERCLIP_CTO_ID:-7fb0fdbb-e17f-4487-a4da-16993a907bec}"

if [ -z "${PAPERCLIP_API_KEY:-}" ]; then
  echo "ERROR: PAPERCLIP_API_KEY is required" >&2
  exit 1
fi

post_hire() {
  local name="$1"
  local role="$2"
  local title="$3"
  local icon="$4"
  local reports_to="$5"
  local capabilities="$6"
  local model="$7"
  local effort="$8"

  local payload
  payload=$(
    jq -n \
      --arg name "$name" \
      --arg role "$role" \
      --arg title "$title" \
      --arg icon "$icon" \
      --arg reportsTo "$reports_to" \
      --arg capabilities "$capabilities" \
      --arg cwd "$WORKSPACE" \
      --arg model "$model" \
      --arg effort "$effort" \
      --arg codexHome "$CODEX_HOME" \
      --arg codexPath "$CODEX_PATH" \
      --arg sourceIssueId "$SOURCE_ISSUE_ID" \
      '{
        name: $name,
        role: $role,
        title: $title,
        icon: $icon,
        reportsTo: $reportsTo,
        capabilities: $capabilities,
        adapterType: "codex_local",
        adapterConfig: {
          cwd: $cwd,
          model: $model,
          modelReasoningEffort: $effort,
          instructionsFilePath: "AGENTS.md",
          instructionsEntryFile: "AGENTS.md",
          instructionsBundleMode: "managed",
          maxTurnsPerRun: 200,
          timeoutSec: 0,
          graceSec: 15,
          dangerouslyBypassApprovalsAndSandbox: true,
          env: {
            CODEX_HOME: $codexHome,
            PATH: $codexPath
          }
        },
        runtimeConfig: {
          heartbeat: {
            enabled: false,
            intervalSec: 14400,
            wakeOnDemand: true,
            maxConcurrentRuns: 1,
            cooldownSec: 10
          }
        },
        budgetMonthlyCents: 0,
        sourceIssueId: $sourceIssueId
      }'
  )

  echo "Submitting $name ($model/$effort)"
  curl -sS -X POST "$API_BASE/api/companies/$COMPANY_ID/agent-hires" \
    -H "Authorization: Bearer $PAPERCLIP_API_KEY" \
    -H "Content-Type: application/json" \
    --data-binary "$payload" \
    | jq -c '{
        name: .agent.name,
        agentId: .agent.id,
        status: .agent.status,
        approvalId: (.approval.id // null),
        approvalStatus: (.approval.status // null)
      }'
}

post_hire \
  "CXCTO" \
  "cto" \
  "CX Chief Technology Officer — Gimle" \
  "crown" \
  "$CEO_ID" \
  "Codex duplicate of CTO. Owns technical strategy, architecture, decomposition, review gates, and delegation to the CX agent team. Does not write code." \
  "gpt-5.5" \
  "high"

post_hire \
  "CXPythonEngineer" \
  "engineer" \
  "CX Python services engineer (FastAPI, asyncio, Neo4j, pytest)" \
  "code" \
  "$CEO_ID" \
  "Codex duplicate of PythonEngineer. Owns Python backend services: FastAPI async, Pydantic v2, pytest-asyncio, Neo4j driver, structlog and OTEL." \
  "gpt-5.4" \
  "high"

post_hire \
  "CXInfraEngineer" \
  "devops" \
  "CX Infrastructure engineer — Docker Compose, Justfile, installer, networking, backup" \
  "wrench" \
  "$CTO_ID" \
  "Codex duplicate of InfraEngineer. Owns Docker Compose stack, Dockerfiles, Justfile, paperclip-agent-net, cloudflared, sops secrets, healthchecks, and single-node backup/restore." \
  "gpt-5.4" \
  "high"

post_hire \
  "CXMCPEngineer" \
  "engineer" \
  "CX MCP Engineer — palace-mcp protocol and tool catalogue" \
  "circuit-board" \
  "$CTO_ID" \
  "Codex duplicate of MCPEngineer. Owns palace-mcp protocol implementation, streamable-HTTP transport, Pydantic schemas, tool catalogue design, client artifacts, and MCP compatibility." \
  "gpt-5.4" \
  "high"

post_hire \
  "CodexArchitectReviewer" \
  "qa" \
  "Codex Architectural Reviewer — second-tier adversarial review" \
  "crown" \
  "$CTO_ID" \
  "Codex duplicate of OpusArchitectReviewer. Performs docs-first architectural review after CXCodeReviewer mechanical pass, focusing on SDK conformance, idiomatic patterns, and subtle design risks." \
  "gpt-5.5" \
  "high"

post_hire \
  "CXQAEngineer" \
  "qa" \
  "CX QA Engineer — testing, smoke, integration" \
  "bug" \
  "$CTO_ID" \
  "Codex duplicate of QAEngineer. Owns pytest-asyncio unit tests, testcontainers Neo4j integration, docker compose smoke automation, regression reproduction, and evidence capture." \
  "gpt-5.4" \
  "high"

post_hire \
  "CXResearchAgent" \
  "researcher" \
  "CX Research Analyst — Gimle" \
  "search" \
  "$CTO_ID" \
  "Codex duplicate of ResearchAgent. Produces cited technology landscape research for Graphiti, MCP, Neo4j, memory frameworks, and code analysis tooling. Does not code." \
  "gpt-5.5" \
  "high"

post_hire \
  "CXTechnicalWriter" \
  "general" \
  "CX Technical Writer — operational docs" \
  "file-code" \
  "$CTO_ID" \
  "Codex duplicate of TechnicalWriter. Owns operational docs, install guides, runbooks, MCP protocol docs, demo scripts, and verified copy-paste-safe command evidence." \
  "gpt-5.4" \
  "medium"
