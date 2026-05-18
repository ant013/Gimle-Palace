# Audit Orchestration — Runbook

**Slice:** GIM-233 (Audit-V1 S1)
**Status:** v1 — synchronous audit only; async workflow launcher (S1.9) added

---

## Overview

Palace Audit-V1 has two modes:

| Mode | Command | Output | When to use |
|------|---------|--------|-------------|
| **Synchronous** | `palace.audit.run` MCP tool or `cli.py audit run` | Markdown inline | Quick audit; CI; operator one-shot |
| **Async workflow** | `audit-workflow-launcher.sh` or `cli.py audit launch` | Paperclip issues + sub-reports | Full async multi-agent audit with domain sub-reports |

---

## Synchronous audit (single MCP call)

### Via MCP tool (from Claude Code or any MCP client)

```
palace.audit.run(project="gimle")
# or
palace.audit.run(bundle="uw-ios", depth="quick")
```

**Response fields:**

| Field | Description |
|-------|-------------|
| `ok` | `true` on success |
| `report_markdown` | Full markdown audit report |
| `fetched_extractors` | List of extractor names that contributed data |
| `blind_spots` | List of extractors that have contracts but no successful IngestRun |
| `provenance` | `{project, generated_at, depth, run_ids}` |

### Via CLI (from iMac terminal)

```bash
cd /Users/Shared/Ios/Gimle-Palace/services/palace-mcp
# Run and print to terminal
uv run python -m palace_mcp.cli audit run --project=gimle

# Write to file
uv run python -m palace_mcp.cli audit run --project=gimle > /tmp/audit-report.md

# Quick depth (only first 3 extractors)
uv run python -m palace_mcp.cli audit run --project=gimle --depth=quick

# Custom MCP URL (default: http://localhost:8000/mcp)
uv run python -m palace_mcp.cli audit run --project=gimle --url=http://localhost:8000/mcp
```

**Expected latency:** 1–5 s for an empty graph; 10–60 s for a fully-seeded project
(depends on number of extractors with data and Neo4j query time).

---

## Async workflow launcher

Launches a Paperclip issue-based audit workflow:

```
Parent issue: "audit: <slug>"        ← Auditor agent
├── Child: "audit-domain: <slug>/audit-arch"   ← OpusArchitectReviewer
├── Child: "audit-domain: <slug>/audit-sec"    ← SecurityAuditor
└── Child: "audit-domain: <slug>/audit-crypto" ← BlockchainEngineer
```

Domain agents read fetcher data from `palace.audit.run`, post sub-report
comments to their child issues, then close them `done`. When all 3 children
close, the Auditor assembles the final report and closes the parent.

### Prerequisites

1. Auditor agent must be registered in Paperclip — capture its UUID.
2. `dependency_surface`, `hotspot`, `code_ownership` etc. must have run for
   the target project (otherwise the audit will have many blind spots).
3. `audit-mode.md` fragment must be deployed via `imac-agents-deploy.sh`
   so domain agents receive audit-mode instructions (S0.3).

### Dry-run (CI / preview)

```bash
# Python CLI
uv run python -m palace_mcp.cli audit launch \
  --project=gimle \
  --auditor-id=<uuid> \
  --dry-run

# Bash script
bash paperclips/scripts/audit-workflow-launcher.sh \
  --project=gimle \
  --auditor-id=<uuid> \
  --dry-run
```

Prints all 4 JSON issue payloads to stdout without calling the Paperclip API.
Use this in CI to verify payload structure.

### Live run (iMac)

```bash
export PAPERCLIP_API_KEY="<token>"   # optional for local dev
export PAPERCLIP_COMPANY_ID="9d8f432c-ff7d-4e3a-bbe3-3cd355f73b64"

bash paperclips/scripts/audit-workflow-launcher.sh \
  --project=gimle \
  --auditor-id=<auditor-uuid>
```

Or via Python CLI:

```bash
uv run python -m palace_mcp.cli audit launch \
  --project=gimle \
  --auditor-id=<auditor-uuid> \
  --api-key="$PAPERCLIP_API_KEY"
```

**Expected latency:** < 2 s to create 4 issues; agent wakes are async.

---

## Failure modes and remediation

### Failure 1: Many blind spots in report

**Symptom:** `blind_spots` in the response contains most extractor names.

**Cause:** Required extractors have not run for the project.

**Fix:**
```
palace.ingest.run_extractor(name="hotspot", project="<slug>")
palace.ingest.run_extractor(name="dependency_surface", project="<slug>")
palace.ingest.run_extractor(name="code_ownership", project="<slug>")
# … repeat for each extractor in blind_spots
```
Then re-run `palace.audit.run`.

### Failure 2: Async workflow stalls — child issue not progressing

**Symptom:** Child issue stuck in `in_progress` or `todo` for > 30 min.

**Diagnosis:**
```
# Check child issue state
GET /api/issues/<child-issue-id>

# Check agent is assigned and responsive
GET /api/agents/<domain-agent-id>
```

**Fix:**
- If agent timed out: re-assign the child issue to the same agent via
  `PATCH /api/issues/<id>` with `assigneeAgentId=<uuid>`.
- If domain agent lacks audit-mode instructions: deploy S0.3 fragment via
  `bash paperclips/scripts/imac-agents-deploy.sh` then re-assign.

### Failure 3: MCP tool returns `driver_unavailable`

**Cause:** palace-mcp container not running or Neo4j unreachable.

**Fix:**
```bash
# On iMac
docker compose --profile review ps         # check container status
bash paperclips/scripts/imac-deploy.sh     # redeploy if needed
```

### Failure 4: CLI exits 1 with "MCP call failed"

**Cause:** palace-mcp is not running at the target URL.

**Fix:** Verify the MCP URL with:
```bash
curl -s http://localhost:8000/healthz | python3 -m json.tool
```
Default port is 8000. Check `docker compose --profile review ps` for the
actual mapped port.

---

## Extractor prerequisites per audit section

| Audit section | Required extractor | Run command |
|---|---|---|
| Hotspots | `hotspot` (needs `git_history` first) | `palace.ingest.run_extractor(name="hotspot", project=...)` |
| Dead symbols | `dead_symbol_binary_surface` | `palace.ingest.run_extractor(name="dead_symbol_binary_surface", project=...)` |
| Dependencies | `dependency_surface` | `palace.ingest.run_extractor(name="dependency_surface", project=...)` |
| Code ownership | `code_ownership` (needs `git_history` first) | `palace.ingest.run_extractor(name="code_ownership", project=...)` |
| Version skew | `cross_repo_version_skew` (needs `dependency_surface` first) | `palace.ingest.run_extractor(name="cross_repo_version_skew", project=...)` |
| Public API | `public_api_surface` | `palace.ingest.run_extractor(name="public_api_surface", project=...)` |
| Cross-module contracts | `cross_module_contract` | `palace.ingest.run_extractor(name="cross_module_contract", project=...)` |
