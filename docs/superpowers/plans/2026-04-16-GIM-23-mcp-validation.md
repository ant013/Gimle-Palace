# GIM-23: MCP Validation — First Real Tool with Client Connect

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Read only your assigned step — the full issue body is not needed.**

**Goal:** Prove end-to-end that palace-mcp serves a real MCP client by implementing and validating the `palace.health.status` tool via streamable-HTTP transport.

**Architecture:** FastMCP (`mcp[cli]>=1.6`) is mounted as a Starlette sub-app at `/mcp` inside the existing FastAPI service on port 8080 (host) → 8000 (container). A shared module-level Neo4j driver (set during FastAPI lifespan) gives the MCP tool access to connectivity state. Pydantic v2 validates the response boundary.

**Tech Stack:** Python 3.12, FastAPI, FastMCP (streamable-HTTP), Pydantic v2, Neo4j async driver, uv, pytest-asyncio, mypy --strict, Docker Compose (profile: review)

---

## File Map

| File | Role | Status |
|------|------|--------|
| `services/palace-mcp/src/palace_mcp/mcp_server.py` | MCP server: tool definition, `HealthStatusResponse` schema, driver injection | ✅ Done |
| `services/palace-mcp/src/palace_mcp/main.py` | FastAPI app: lifespan, driver sharing, `/mcp` mount | ✅ Done |
| `services/palace-mcp/tests/test_mcp_health_tool.py` | Unit tests: tool invocation, driver states, schema validation | ✅ Done |
| `docs/clients/claude-desktop.json` | Claude Desktop MCP config pointing to `http://localhost:8080/mcp` | ✅ Done |
| `docs/clients/cursor.json` | Cursor MCP config | ✅ Done |
| `docs/clients/README.md` | How to apply client configs | ✅ Done |

---

## Step 1 — MCP server layer (MCPEngineer)

**Owner:** MCPEngineer  
**Status:** ✅ Done (committed in `feature/GIM-23-mcp-health-tool`, PR #6)

**What was done:**
- Added `services/palace-mcp/src/palace_mcp/mcp_server.py`:
  - `FastMCP("palace")` instance with `streamable_http_app()` export
  - `HealthStatusResponse(BaseModel)` with `neo4j: Literal["reachable","unreachable"]`, `git_sha: str`, `uptime_seconds: int`
  - `@_mcp.tool(name="palace.health.status")` async tool wrapping Neo4j connectivity check
  - `set_driver(driver)` / `_driver` module-level injection pattern
- Updated `main.py`: `set_driver(driver)` in lifespan, `app.mount("/mcp", build_mcp_asgi_app())`
- Added `services/palace-mcp/tests/test_mcp_health_tool.py`: 7 unit tests covering reachable/unreachable/None driver, verbose flag, git_sha default, schema validation, tool registration

**Acceptance criteria:** ✅
- `palace.health.status` registered in FastMCP tool manager
- Unit tests pass: `cd services/palace-mcp && uv run pytest tests/test_mcp_health_tool.py -v`
- mypy --strict passes: `uv run mypy src`

---

## Step 2 — Client config docs (TechnicalWriter)

**Owner:** TechnicalWriter  
**Status:** ✅ Done (committed in same branch, GIM-24)

**What was done:**
- `docs/clients/claude-desktop.json`: `{"mcpServers": {"palace": {"url": "http://localhost:8080/mcp"}}}`
- `docs/clients/cursor.json`: equivalent Cursor config
- `docs/clients/README.md`: instructions for applying configs

**Acceptance criteria:** ✅
- Both JSON files are valid and reference `http://localhost:8080/mcp`
- README explains where to paste each config

---

## Step 3 — Compose port verification (InfraEngineer)

**Owner:** InfraEngineer  
**Status:** ✅ Done (no changes needed — port mapping already correct)

**What was verified:**
- `docker-compose.yml` already maps `8080:8000` for palace-mcp
- `/healthz` accessible at `http://localhost:8080/healthz`
- `/mcp` endpoint will be accessible at `http://localhost:8080/mcp` after step 1 is merged

**Acceptance criteria:** ✅
- No compose changes required
- Port 8080 maps to container port 8000

---

## Step 4 — PR review (CodeReviewer)

**Owner:** CodeReviewer  
**Status:** 🔲 TODO — PR #6 on branch `feature/GIM-23-mcp-health-tool` awaits review

**What to do:**

Review PR #6: https://github.com/ant013/Gimle-Palace/pull/6

**Files to review:**
- `services/palace-mcp/src/palace_mcp/mcp_server.py` — MCP protocol compliance, Pydantic v2 usage, tool naming convention
- `services/palace-mcp/src/palace_mcp/main.py` — lifespan driver sharing, ASGI mount
- `services/palace-mcp/tests/test_mcp_health_tool.py` — test quality, async fixture cleanup
- `docs/clients/claude-desktop.json` + `docs/clients/cursor.json` — valid JSON, correct URL

**Compliance table to include in PR review comment:**

| Check | Status | Evidence |
|-------|--------|----------|
| Tool name follows `palace.<domain>.<verb>` | [ ] | `palace.health.status` in mcp_server.py |
| Pydantic v2 `BaseModel` used for response schema | [ ] | `HealthStatusResponse(BaseModel)` |
| `verbose` param accepted without breaking (reserved) | [ ] | ARG001 noqa on unused param |
| Driver None case handled (returns "unreachable") | [ ] | `if _driver is not None:` guard |
| Unit tests cover: reachable, unreachable, None driver | [ ] | test_mcp_health_tool.py:7 tests |
| mypy --strict passes | [ ] | CI check |
| CI green (docker-build + lint + tests) | [ ] | GitHub Actions on PR |
| No scope creep (only health tool, no other tools) | [ ] | Single tool definition |

**Anti-rubber-stamp reminder:** APPROVE only after CI is green. Do NOT approve if `docker-build` job is failing. Check GitHub Actions status on PR before submitting review.

**Verdict must be:**
- `REQUEST CHANGES` with specific list if any compliance item fails
- `APPROVE` with completed compliance table if all items pass

**After review:**
- If REQUEST CHANGES: post comment in GIM-23 `@PythonEngineer @InfraEngineer` with list of fixes needed
- If APPROVE: post comment in GIM-23 `@MCPEngineer` step 4 complete, step 5 (smoke test) in progress

- [ ] Read PR #6 diff
- [ ] Fill in compliance table
- [ ] Check GitHub Actions CI status on PR
- [ ] Submit APPROVE or REQUEST CHANGES
- [ ] Comment in GIM-23 with outcome

---

## Step 5 — Live MCP client smoke test (QAEngineer)

**Owner:** QAEngineer  
**Status:** 🔄 In Progress (GIM-27 assigned to QAEngineer)

**Prerequisites:**
- PR #6 merged to `develop` (or test against feature branch with `docker build`)
- `.env` file has `NEO4J_PASSWORD` set
- Docker running

**What to do:**

```bash
# 1. Start compose with review profile
cd /path/to/Gimle-Palace
docker compose --profile review up -d

# 2. Wait for healthchecks to go green
docker compose ps  # both should show "healthy"

# 3. Verify MCP endpoint responds
curl -s http://localhost:8080/health | python3 -m json.tool
# Expected: {"status": "ok"}
```

**Option C (programmatic Python client — recommended for automation):**

```python
# smoke_test.py
import asyncio
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

async def smoke():
    async with streamablehttp_client("http://localhost:8080/mcp") as (r, w, _):
        async with ClientSession(r, w) as session:
            await session.initialize()
            tools = await session.list_tools()
            tool_names = [t.name for t in tools.tools]
            print("Tools:", tool_names)
            assert "palace.health.status" in tool_names, f"Missing tool, got: {tool_names}"

            result = await session.call_tool("palace.health.status", {})
            print("Result:", result)
            # Verify response fields exist
            content_text = result.content[0].text if result.content else ""
            assert "neo4j" in content_text, "Missing neo4j field"
            assert "git_sha" in content_text, "Missing git_sha field"
            assert "uptime_seconds" in content_text, "Missing uptime_seconds field"
            print("SMOKE TEST PASSED")

asyncio.run(smoke())
```

Run: `pip install mcp && python3 smoke_test.py`

**Expected output:**
```
Tools: ['palace.health.status']
Result: <CallToolResult with neo4j, git_sha, uptime_seconds>
SMOKE TEST PASSED
```

**Evidence required:** Paste the full terminal output into a PR comment on PR #6. Screenshot of client listing `palace.health.status` also acceptable if programmatic client fails.

**Acceptance criteria:**
- [ ] `palace.health.status` appears in `list_tools()` response
- [ ] Tool invocation returns response with `neo4j`, `git_sha`, `uptime_seconds` fields
- [ ] Evidence (output or screenshot) posted to PR #6 comment
- [ ] Comment in GIM-23 linking to PR comment with evidence

**After smoke test:**
- Post evidence as PR #6 comment
- Comment in GIM-23: step 5 complete, link to evidence, @CodeReviewer for final merge

- [ ] Start compose with review profile
- [ ] Run programmatic smoke test (or Option A/B)
- [ ] Post evidence to PR #6
- [ ] Comment in GIM-23 with link to evidence

---

## Step 6 — Merge + post-merge compose smoke (MCPEngineer or InfraEngineer)

**Owner:** MCPEngineer  
**Status:** 🔲 TODO — blocked on Step 4 (APPROVE) + Step 5 (evidence posted)

**Prerequisites:**
- CodeReviewer APPROVE on PR #6
- QAEngineer evidence posted to PR comment
- CI green on PR #6

**What to do:**

```bash
# 1. Merge PR #6 via GitHub (squash merge into develop)
# Use GitHub UI: https://github.com/ant013/Gimle-Palace/pull/6

# 2. Pull develop locally
git checkout develop && git pull origin develop

# 3. Run compose smoke test from merged develop
cd /path/to/Gimle-Palace
docker compose --profile review up -d --build

# 4. Verify both services healthy
docker compose ps
# Expected: neo4j (healthy), palace-mcp (healthy)

# 5. Verify MCP endpoint
curl -s http://localhost:8080/health
# Expected: {"status":"ok"}

curl -s -X POST http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
# Expected: list with palace.health.status
```

**Acceptance criteria:**
- [ ] PR #6 merged to `develop`
- [ ] `docker compose --profile review up -d --build` succeeds
- [ ] Both `neo4j` and `palace-mcp` show `(healthy)` in `docker compose ps`
- [ ] `palace.health.status` reachable via MCP endpoint after merge
- [ ] GIM-23 marked `done` with final comment linking to merged PR

**After merge:**
- Mark GIM-23 as `done`
- Comment in GIM-23 with merge commit SHA and evidence that compose is green

- [ ] Merge PR #6 after APPROVE + evidence
- [ ] Pull develop, rebuild compose
- [ ] Verify healthchecks green
- [ ] Mark GIM-23 done with final evidence

---

## Progress Tracker

| Step | Owner | Status |
|------|-------|--------|
| 1. MCP server layer | MCPEngineer | ✅ Done |
| 2. Client config docs | TechnicalWriter | ✅ Done |
| 3. Compose port verify | InfraEngineer | ✅ Done |
| 4. PR review | CodeReviewer | 🔲 TODO |
| 5. Live smoke test | QAEngineer | 🔄 In Progress (GIM-27) |
| 6. Merge + post-merge smoke | MCPEngineer | 🔲 TODO |

---

*Plan created: 2026-04-16 by MCPEngineer for GIM-23.*
*Source of truth for all handoffs. Update checkboxes as steps complete.*
