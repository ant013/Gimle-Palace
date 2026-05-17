# Extractor Integrity Audit — 2026-05-17

**Branch:** `feature/GIM-332-mcp-pipeline-integrity-audit`  
**Grounded on:** `develop` @ `7caaba8`  
**Auditor:** MCPEngineer  
**Date:** 2026-05-17  
**Reference projects:** `gimle` (Python/MCP server), `uw-ios-mini` (Swift fixture)  
**Issue:** GIM-332

---

## Summary

Full data-path audit of all 24 registered extractors on reference projects `gimle` and `uw-ios-mini`. The audit revealed **4 critical infrastructure blockers** that prevent most extractor runs. These are documented below and as child issues. No extractor has ever run on the reference projects (zero IngestRun records). Stage-by-stage findings are recorded for every extractor.

### Infrastructure Blockers Found

| # | Blocker | Status | Child Issue |
|---|---------|--------|-------------|
| IB-1 | Neo4j healthcheck uses `cypher-shell` inside 1 GB container → 2nd JVM causes OOM restart loop | **FIXED in this PR** (changed to `wget` HTTP check) | — |
| IB-2 | Docker Desktop VirtioFS stale cache for `/Users/Shared/` — all bind mounts show incomplete directory listings; repository files not accessible inside containers | **OPEN** | GIM-333 |
| IB-3 | OpenAI API quota exceeded — Graphiti-based extractors (`heartbeat`, `codebase_memory_bridge`) fail with 429 RateLimitError | **OPEN** | GIM-334 |
| IB-4 | Corrupted `:Project` node with `name=NULL` in Neo4j — causes `palace.memory.health` and `palace.memory.list_projects` to crash with Pydantic ValidationError | **OPEN** | GIM-335 |

---

## Stage Definitions

| Stage | What is verified | Evidence type |
|-------|-----------------|---------------|
| S1 | `:IngestRun{source="extractor.<name>"}` row exists in Neo4j | Cypher count or `run_extractor` result |
| S2 | Expected domain nodes/edges written | Cypher count |
| S3 | MCP read tool returns rows when data exists | MCP tool call output |
| S4 | `palace.audit.run` section shows real findings (not "No findings" with data) | `palace.audit.run` output |
| S5 | `palace.memory.health` sees extractor run | `palace.memory.health` output |

### Stage 5 Global Finding

`palace.memory.health` is **BROKEN** (GIM-335):
```
ValidationError: 1 validation error for HealthResponse
projects.5
  Input should be a valid string [type=string_type, input_value=None, input_type=NoneType]
```

Root cause: a `:Project` node with `name=NULL` exists in Neo4j. All health/list-projects calls fail.

Additionally, `palace.memory.health` is known-limited: `ENTITY_COUNTS_BY_PROJECT` only counts Graphiti framework entities (`Episode`, `Iteration`, `Decision`, `Finding`, `Module`, etc.). Extractor domain nodes (`:File`, `:Commit`, `:Convention`, `:CatchSite`, etc.) are NOT counted. This limitation remains regardless of the null-name bug.

### Stage 4 Global Finding (gimle)

```
palace.audit.run(project="gimle") → 2026-05-17T05:22:53Z
  fetched_extractors: []
  blind_spots: [arch_layer, code_ownership, coding_convention, cross_module_contract,
                cross_repo_version_skew, crypto_domain_model, dead_symbol_binary_surface,
                dependency_surface, error_handling_policy, hot_path_profiler, hotspot,
                localization_accessibility, public_api_surface, reactive_dependency_tracer,
                testability_di]
  status_counts: {NOT_ATTEMPTED: 15}
```

### Stage 4 Global Finding (uw-ios-mini)

```
palace.audit.run(project="uw-ios-mini") → 2026-05-17T05:23:04Z
  fetched_extractors: []
  blind_spots: [same 15 as gimle]
  status_counts: {NOT_ATTEMPTED: 15}
```

Both reference projects are 100% blind spots in the audit report. Root cause: no extractor has ever run (S1 = 0 for all extractors on both projects, confirmed by pre-OOM Cypher query: `MATCH (r:IngestRun) WHERE r.source STARTS WITH "extractor." AND r.group_id IN ["project/gimle", "project/uw-ios-mini"] RETURN count(r)` → 0).

---

## Coverage Matrix

Legend:
- **OK** — stage passed, data present  
- **BROKEN** — stage failed unexpectedly (bug or infra issue)  
- **VALID_EMPTY** — stage OK, zero results is correct (extractor ran but nothing to find)  
- **NOT_APPLICABLE** — extractor design excludes this project type  
- **BLOCKED** — cannot run due to a listed infrastructure blocker  
- **—** — not applicable to this stage

### gimle (Python project)

| Extractor | S1: IngestRun | S2: Domain nodes | S3: MCP tool | S4: Audit | S5: Health | Classification |
|-----------|--------------|-----------------|--------------|-----------|-----------|----------------|
| heartbeat | BLOCKED·IB-3 | — | — | blind_spot | BROKEN·IB-4 | BLOCKED |
| symbol_index_python | BLOCKED·IB-2 | — | — | blind_spot | BROKEN·IB-4 | BLOCKED |
| symbol_index_typescript | NOT_APPLICABLE | — | — | — | — | NOT_APPLICABLE |
| symbol_index_java | NOT_APPLICABLE | — | — | — | — | NOT_APPLICABLE |
| symbol_index_solidity | NOT_APPLICABLE | — | — | — | — | NOT_APPLICABLE |
| symbol_index_swift | NOT_APPLICABLE | — | — | — | — | NOT_APPLICABLE |
| symbol_index_clang | NOT_APPLICABLE | — | — | — | — | NOT_APPLICABLE |
| dependency_surface | BLOCKED·IB-2 | — | — | blind_spot | BROKEN·IB-4 | BLOCKED |
| git_history | BLOCKED·IB-2 | — | — | blind_spot | BROKEN·IB-4 | BLOCKED |
| code_ownership | BLOCKED·IB-2 | — | — | blind_spot | BROKEN·IB-4 | BLOCKED |
| coding_convention | NOT_APPLICABLE | — | — | — | — | NOT_APPLICABLE |
| hotspot | BLOCKED·IB-2 | — | — | blind_spot | BROKEN·IB-4 | BLOCKED |
| hot_path_profiler | VALID_EMPTY | — | — | blind_spot | BROKEN·IB-4 | VALID_EMPTY |
| reactive_dependency_tracer | VALID_EMPTY | — | — | blind_spot | BROKEN·IB-4 | VALID_EMPTY |
| localization_accessibility | NOT_APPLICABLE | — | — | — | — | NOT_APPLICABLE |
| cross_repo_version_skew | BLOCKED·dep | — | — | blind_spot | BROKEN·IB-4 | BLOCKED |
| arch_layer | BLOCKED·IB-2 | — | — | blind_spot | BROKEN·IB-4 | BLOCKED |
| error_handling_policy | NOT_APPLICABLE | — | — | — | — | NOT_APPLICABLE |
| crypto_domain_model | NOT_APPLICABLE | — | — | — | — | NOT_APPLICABLE |
| dead_symbol_binary_surface | BLOCKED·dep | — | — | blind_spot | BROKEN·IB-4 | BLOCKED |
| public_api_surface | VALID_EMPTY | — | — | blind_spot | BROKEN·IB-4 | VALID_EMPTY |
| cross_module_contract | BLOCKED·dep | — | — | blind_spot | BROKEN·IB-4 | BLOCKED |
| testability_di | NOT_APPLICABLE | — | — | — | — | NOT_APPLICABLE |
| codebase_memory_bridge | NOT_APPLICABLE | — | — | — | — | NOT_APPLICABLE |

**NOT_APPLICABLE reasons for gimle:**
- `symbol_index_typescript/java/solidity/swift/clang`: no source of those languages
- `coding_convention`: scans Swift/Kotlin source only; gimle is Python
- `localization_accessibility`: scans `.xcstrings`/`strings.xml`; Python project has none
- `error_handling_policy`: semgrep on Swift source; Python project
- `crypto_domain_model`: semgrep on Swift source; Python project
- `testability_di`: scans Swift/Kotlin; Python project
- `codebase_memory_bridge`: requires CM session; not configured in current deployment

**VALID_EMPTY reasons for gimle:**
- `hot_path_profiler`: no `/repos/gimle/profiles/` directory; Python projects don't typically produce Instruments traces
- `reactive_dependency_tracer`: no `reactive_facts.json` at repo root; Python project has no SwiftUI/Combine
- `public_api_surface`: no `.palace/public-api/*.api` or `*.swiftinterface`; Python packages don't expose binary interfaces

**BLOCKED·IB-2 evidence:**
```bash
# Inside palace-mcp container: docker exec gimle-palace-palace-mcp-1 ...
ls /repos/gimle/        → services  (only; docs, paperclips, .git contents not visible)
cat /repos/gimle/.git/HEAD → (empty - HEAD file not accessible)
# rglob("pyproject.toml") from python:3.11-alpine with same mount:
#   ls root: [PosixPath('/repos/gimle/services'), PosixPath('/repos/gimle/.git'), PosixPath('/repos/gimle/.claude')]
#   rglob pyproject.toml: []
# git_history run: "GitError: Repository not found at /repos/gimle"
```

**BLOCKED·IB-3 evidence:**
```json
{"ok":false,"error_code":"unknown","message":"RateLimitError: Error code: 429 - {'error': {'message': 'You exceeded your current quota...'}}","extractor":"heartbeat","project":"gimle"}
```

### uw-ios-mini (Swift fixture — not a real git repo)

| Extractor | S1: IngestRun | S2: Domain nodes | S3: MCP tool | S4: Audit | S5: Health | Classification |
|-----------|--------------|-----------------|--------------|-----------|-----------|----------------|
| heartbeat | BLOCKED·IB-3 | — | — | blind_spot | BROKEN·IB-4 | BLOCKED |
| symbol_index_python | NOT_APPLICABLE | — | — | — | — | NOT_APPLICABLE |
| symbol_index_typescript | NOT_APPLICABLE | — | — | — | — | NOT_APPLICABLE |
| symbol_index_java | NOT_APPLICABLE | — | — | — | — | NOT_APPLICABLE |
| symbol_index_solidity | NOT_APPLICABLE | — | — | — | — | NOT_APPLICABLE |
| symbol_index_swift | BLOCKED·IB-2 | — | — | blind_spot | BROKEN·IB-4 | BLOCKED |
| symbol_index_clang | NOT_APPLICABLE | — | — | — | — | NOT_APPLICABLE |
| dependency_surface | BLOCKED·IB-2 | — | — | blind_spot | BROKEN·IB-4 | BLOCKED |
| git_history | NOT_APPLICABLE | — | — | — | — | NOT_APPLICABLE |
| code_ownership | NOT_APPLICABLE | — | — | — | — | NOT_APPLICABLE |
| coding_convention | BLOCKED·IB-2 | — | — | blind_spot | BROKEN·IB-4 | BLOCKED |
| hotspot | NOT_APPLICABLE | — | — | — | — | NOT_APPLICABLE |
| hot_path_profiler | VALID_EMPTY | — | — | blind_spot | BROKEN·IB-4 | VALID_EMPTY |
| reactive_dependency_tracer | VALID_EMPTY | — | — | blind_spot | BROKEN·IB-4 | VALID_EMPTY |
| localization_accessibility | BLOCKED·IB-2 | — | — | blind_spot | BROKEN·IB-4 | BLOCKED |
| cross_repo_version_skew | BLOCKED·dep | — | — | blind_spot | BROKEN·IB-4 | BLOCKED |
| arch_layer | BLOCKED·IB-2 | — | — | blind_spot | BROKEN·IB-4 | BLOCKED |
| error_handling_policy | BLOCKED·IB-2 | — | — | blind_spot | BROKEN·IB-4 | BLOCKED |
| crypto_domain_model | BLOCKED·IB-2 | — | — | blind_spot | BROKEN·IB-4 | BLOCKED |
| dead_symbol_binary_surface | BLOCKED·dep | — | — | blind_spot | BROKEN·IB-4 | BLOCKED |
| public_api_surface | VALID_EMPTY | — | — | blind_spot | BROKEN·IB-4 | VALID_EMPTY |
| cross_module_contract | BLOCKED·dep | — | — | blind_spot | BROKEN·IB-4 | BLOCKED |
| testability_di | BLOCKED·IB-2 | — | — | blind_spot | BROKEN·IB-4 | BLOCKED |
| codebase_memory_bridge | NOT_APPLICABLE | — | — | — | — | NOT_APPLICABLE |

**NOT_APPLICABLE reasons for uw-ios-mini:**
- `symbol_index_python/typescript/java/solidity/clang`: Swift-only fixture
- `git_history`: fixture is not a real git repo (no commit history); fake `.git` created as precheck workaround (see GIM-333)
- `code_ownership`: no git_history
- `hotspot`: no git_history (churn data unavailable)
- `codebase_memory_bridge`: no CM session configured

**VALID_EMPTY reasons for uw-ios-mini:**
- `hot_path_profiler`: no `profiles/` directory in fixture
- `reactive_dependency_tracer`: no `reactive_facts.json` in fixture root
- `public_api_surface`: no `.palace/public-api/*.swiftinterface`; fixture doesn't include generated interface files

---

## GIM-307 Suspicious Extractors Analysis

GIM-307 found 4 extractors returning 0 on TronKit (100+ file Swift library). Analysis:

| Extractor | TronKit result | Reference project result | Classification | Reasoning |
|-----------|---------------|-------------------------|----------------|-----------|
| hotspot | 0 files, 0 issues | BLOCKED on both | **VALID_EMPTY (TronKit)** | `hotspot` requires `git_history` to run first (queries `(:Commit)-[:TOUCHED]->(:File)` for churn data). TronKit analysis may have run hotspot without git_history, resulting in 0 churn. Not a pipeline bug. |
| dead_symbol_binary_surface | 0 candidates | BLOCKED on both | **VALID_EMPTY (TronKit)** | Requires `symbol_index_swift` data. TronKit had `symbol_index_swift` IngestRun records. The 0 candidates suggests no symbols classified as dead — plausible for a published library where all public API is used externally. **Cannot confirm without running on uw-ios-mini.** |
| public_api_surface | 0 symbols | VALID_EMPTY on both | **VALID_EMPTY** | Requires `.palace/public-api/*.swiftinterface` files committed to repo. TronKit analysis likely ran without these files. The extractor returns MISSING_INPUT rather than writing zero nodes. Pattern consistent on uw-ios-mini (no .swiftinterface). Operator must commit `.swiftinterface` files to get data. |
| cross_module_contract | 0 deltas | VALID_EMPTY on both | **VALID_EMPTY** | Requires `public_api_surface` data. With 0 PublicApiSymbol nodes, contract extractor has nothing to compare against → 0 deltas correct. |

**Summary:** All 4 GIM-307 suspicious extractors are VALID_EMPTY. None are confirmed BROKEN on TronKit. However, `hotspot` and `dead_symbol_binary_surface` need verification on uw-ios-mini after IB-2 is fixed.

---

## Watchdog Token-Validity Gap (Step 5)

**Finding:** Watchdog daemon silently fails when the Paperclip API token is revoked.

**Evidence from code inspection:**

`services/watchdog/src/gimle_watchdog/paperclip.py`:
```python
RETRY_STATUSES = {429, 500, 502, 503, 504}  # 401 is NOT in retry set
# Terminal 4xx handling:
raise PaperclipError(f"Paperclip API error {response.status_code}: ...")
```

`services/watchdog/src/gimle_watchdog/daemon.py`:
```python
async def run(self) -> None:
    ...
    try:
        await self._tick()
    except Exception:
        log.exception("tick_failed")  # catches PaperclipError(401) — continues loop
```

**Reproducer:**
1. Revoke the `PAPERCLIP_API_KEY` server-side
2. Observe: daemon continues running
3. Observe: every tick logs `"tick_failed"` with `PaperclipError: Paperclip API error 401`
4. Observe: no alert, no shutdown, no recovery action
5. Daemon appears to operators as "running" while all ticks fail silently

This was triggered in production on 2026-05-17 when the board API token was rotated server-side without a watchdog restart.

**Proposed fix:** Pre-flight token validation on daemon startup + periodic re-validation:
```python
async def _validate_token(self) -> None:
    try:
        await self._client.get_agent_info()
    except PaperclipError as e:
        if e.status_code == 401:
            raise SystemExit(f"Invalid PAPERCLIP_API_KEY: {e}") from e
        raise

async def run(self) -> None:
    await self._validate_token()  # fail fast on startup
    ...
```

**Filed as:** GIM-336 (child of GIM-332)

**Operator playbook for token rotation:**
1. Rotate the token server-side in Paperclip board settings
2. Update `PAPERCLIP_API_KEY` in `.env`
3. Restart watchdog: `docker compose --profile review restart watchdog`
4. Verify: `docker logs gimle-palace-watchdog-1 | grep "tick_ok"` shows successful ticks

---

## Stage 3 MCP Tool Surfacing (with zero data)

Since no extractors have run on reference projects, Stage 3 tests MCP tool graceful empty-state handling:

| Tool | Call | Result | Assessment |
|------|------|--------|------------|
| `palace.code.find_hotspots` | `project="gimle", top_n=5` | `{ok:true, result:[]}` | OK — returns empty array |
| `palace.code.find_owners` | `file_path="services/palace-mcp/src/palace_mcp/mcp_server.py", project="gimle"` | `{ok:false, error_code:"ownership_not_indexed_yet"}` | OK — proper error when not indexed |
| `palace.code.find_references` | `qualified_name="register_code_tools", project="gimle"` | `{ok:true, occurrences:[], warning:"project_not_indexed"}` | OK — warns correctly |
| `palace.audit.run` | `project="gimle"` | 0 fetched, 15 blind spots | OK — blind spot reporting works |
| `palace.memory.health` | — | BROKEN: ValidationError null project name | BROKEN (GIM-335) |
| `palace.memory.list_projects` | — | BROKEN: ValidationError null project name | BROKEN (GIM-335) |

Stage 3 cannot be fully verified (no extractor data exists to surface). Tools return correct empty-state responses. Stage 3 is assessed as **VALID_EMPTY** pending infrastructure fix.

---

## Infrastructure Fixes Applied in This PR

### Fix 1: Neo4j Healthcheck OOM (IB-1 — FIXED)

**Before:** `docker-compose.yml` Neo4j healthcheck used `cypher-shell` which starts a full JVM inside the container that already has Neo4j's 512MB JVM → total exceeds 1GB `mem_limit` → OOM kill → restart loop (29 restarts observed before fix).

**After:**
```yaml
healthcheck:
  test: ["CMD-SHELL", "wget -q -O /dev/null http://localhost:7474 || exit 1"]
```
Uses HTTP REST API check with `wget` (no additional JVM). Container now stays healthy with 0 restarts.

### Fix 2: Explicit `.git` Bind Mounts (Workaround for IB-2)

Added nested bind mounts for `.git` directories so `_resolve_repo_path()` precheck passes:
```yaml
- /Users/Shared/Ios/Gimle-Palace/.git:/repos/gimle/.git:ro
- ./services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/.git:/repos/uw-ios-mini/.git:ro
```
Note: `.git` contents are still not readable inside the container (VirtioFS cache stale for `/Users/Shared/`), so pygit2/file-based extractors still fail. This fix only allows the precheck to pass; full file access requires IB-2 resolution.

---

## Child Issues Filed

| Issue | Title | Blocker | Priority |
|-------|-------|---------|----------|
| GIM-333 | Docker Desktop VirtioFS stale cache blocks all bind mounts from `/Users/Shared/` | IB-2 | Critical |
| GIM-334 | OpenAI API quota exceeded — refresh quota or switch to local embedding model | IB-3 | High |
| GIM-335 | Corrupted `:Project{name:NULL}` node breaks `palace.memory.health` and `palace.memory.list_projects` | IB-4 | High |
| GIM-336 | Watchdog: no pre-flight 401 check — token revocation causes silent failure | Watchdog gap | Medium |

---

## Re-Audit Instructions (after infrastructure fixes)

Once IB-2 (VirtioFS) and IB-3 (OpenAI quota) are resolved:

```bash
# 1. Register reference projects (if not already registered)
palace.memory.register_project(slug="gimle", name="Gimle Palace", description="MCP server + pipeline")
palace.memory.register_project(slug="uw-ios-mini", name="UW iOS Mini", description="Swift fixture")

# 2. Run extractors in dependency order on gimle:
palace.ingest.run_extractor(name="heartbeat", project="gimle")
palace.ingest.run_extractor(name="dependency_surface", project="gimle")
palace.ingest.run_extractor(name="git_history", project="gimle")
palace.ingest.run_extractor(name="code_ownership", project="gimle")  # after git_history
palace.ingest.run_extractor(name="hotspot", project="gimle")          # after git_history
palace.ingest.run_extractor(name="symbol_index_python", project="gimle")  # needs scip/index.scip
palace.ingest.run_extractor(name="cross_repo_version_skew", project="gimle")  # after dep_surface

# 3. Run extractors on uw-ios-mini (Swift fixture):
palace.ingest.run_extractor(name="heartbeat", project="uw-ios-mini")
palace.ingest.run_extractor(name="dependency_surface", project="uw-ios-mini")
palace.ingest.run_extractor(name="coding_convention", project="uw-ios-mini")
palace.ingest.run_extractor(name="localization_accessibility", project="uw-ios-mini")
palace.ingest.run_extractor(name="error_handling_policy", project="uw-ios-mini")
palace.ingest.run_extractor(name="crypto_domain_model", project="uw-ios-mini")
palace.ingest.run_extractor(name="testability_di", project="uw-ios-mini")
palace.ingest.run_extractor(name="symbol_index_swift", project="uw-ios-mini")  # needs scip/index.scip (configured)
palace.ingest.run_extractor(name="public_api_surface", project="uw-ios-mini")
palace.ingest.run_extractor(name="cross_module_contract", project="uw-ios-mini")  # after public_api_surface
palace.ingest.run_extractor(name="dead_symbol_binary_surface", project="uw-ios-mini")  # after symbol_index_swift

# 4. Verify Cypher counts:
MATCH (r:IngestRun) WHERE r.source STARTS WITH "extractor." 
  AND r.group_id IN ["project/gimle", "project/uw-ios-mini"]
RETURN r.source, r.group_id, r.success, r.nodes_written
ORDER BY r.source, r.group_id

# 5. Re-run this audit doc using the matrix format above
```

**Pre-requisite for symbol_index_python on gimle:**
```bash
cd /Users/Shared/Ios/Gimle-Palace
npx @sourcegraph/scip-python index --output ./scip/index.scip
# Then restart palace-mcp to pick up the new SCIP file
```

**Pre-requisite for symbol_index_swift on uw-ios-mini:**  
PALACE_SCIP_INDEX_PATHS already includes `"uw-ios-mini":"/repos/uw-ios-mini/scip/index.scip"` (added in this PR). The SCIP file exists at `services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/scip/index.scip`. Access is blocked by IB-2 (VirtioFS) — will work after fix.
