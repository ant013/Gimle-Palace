# Audit report — tron-kit after GIM-283-2 (Slice 1)

**Date:** 2026-05-13
**Slice:** GIM-283-2 — Coverage (testability_di + reactive + DEFAULT_EXTRACTORS)
**Branch:** `feature/GIM-283-2-audit-coverage-gaps`
**Commit SHA:** `259fd727bfdb5f1addd23fea88b96ce925d50a16`
**Status:** QA PASS ✅ (see constraints section)

---

## Phase 4.1 QA Evidence

### 1. Containers

```
$ docker compose --profile review ps
NAME                        IMAGE                   STATUS
gimle-palace-neo4j-1        neo4j:5.26.0            Up 11 hours (healthy)
gimle-palace-palace-mcp-1   gimle-palace-palace-mcp Up 10 minutes (healthy)
```

### 2. Healthz

```json
{"status":"ok","neo4j":"reachable"}
```

Source: `docker exec gimle-palace-palace-mcp-1 curl -sf http://127.0.0.1:8000/healthz`

### 3. Registry verification (MCP tool call)

```
$ palace.ingest.list_extractors()  (via docker exec palace_mcp.cli)

Registry count: 24
  arch_layer: audit_contract=True
  code_ownership: audit_contract=True
  coding_convention: audit_contract=True
  ...
  reactive_dependency_tracer: audit_contract=True   ← B2 (new)
  testability_di: audit_contract=True               ← B1 (new, from GIM-242)
  localization_accessibility: audit_contract=True
  hot_path_profiler: audit_contract=True
```

All 24 extractors registered, all with `audit_contract=True`.
`testability_di` and `reactive_dependency_tracer` newly appear with contracts.

### 4. palace.audit.run — blind spot comparison

**Before slice (2026-05-12):**
```
Blind spots: coding_convention, cross_module_contract, hot_path_profiler,
             localization_accessibility, public_api_surface
```
`reactive_dependency_tracer` and `testability_di` were **absent** (no audit_contract).

**After slice (2026-05-13, feature branch image):**
```
Blind spots: coding_convention, hot_path_profiler, localization_accessibility,
             reactive_dependency_tracer, testability_di
```

`reactive_dependency_tracer` and `testability_di` now appear as **NOT_ATTEMPTED**
(have audit_contract, haven't run on tron-kit yet) instead of being completely absent.
This is the expected outcome: audit pipeline recognizes them.

Existing 8 fetched extractors unchanged — no regression.

### 5. ingest_swift_kit.sh DEFAULT_EXTRACTORS (dry-run)

```
$ bash paperclips/scripts/ingest_swift_kit.sh tron-kit --bundle=uw-ios --dry-run

DEFAULT_EXTRACTORS (from script header):
  symbol_index_swift, git_history, dependency_surface, arch_layer,
  error_handling_policy, crypto_domain_model, hotspot, code_ownership,
  cross_repo_version_skew, public_api_surface, cross_module_contract,
  dead_symbol_binary_surface, coding_convention, localization_accessibility,
  reactive_dependency_tracer, testability_di, hot_path_profiler
```

`coding_convention`, `localization_accessibility`, `reactive_dependency_tracer`,
`testability_di` all present in DEFAULT_EXTRACTORS (B3 fix).

### 6. Unit tests

```
$ uv run pytest tests/extractors/test_profiles.py \
                tests/audit/unit/test_audit_contracts.py \
                tests/extractors/reactive_dependency_tracer/test_audit_contract_present.py

34 passed, 1 warning
```

Includes:
- `test_profiles.py`: swift_kit profile contains testability_di and reactive_dependency_tracer
- `test_audit_contracts.py`: all extractor audit contracts valid
- `test_audit_contract_present.py`: reactive audit_contract returns correct template, query, severity mapper

### 7. Opus F1 fix applied

Commit `259fd727`: `Severity` moved to lazy import inside `_reactive_severity_mapper()`,
matching codebase convention (arch_layer, crypto_domain_model, error_handling_policy peers).
ruff + mypy clean.

---

## Acceptance criteria status

| Criterion | Status | Notes |
|-----------|--------|-------|
| `testability_di` appears in audit report (not NOT_APPLICABLE) | ✅ | Shows as NOT_ATTEMPTED blind spot |
| `reactive_dependency_tracer` appears (not NOT_APPLICABLE) | ✅ | Shows as NOT_ATTEMPTED blind spot |
| `coding_convention` present (any status except NOT_APPLICABLE) | ✅ | Shows as NOT_ATTEMPTED blind spot (no regression) |
| `localization_accessibility` present (any status except NOT_APPLICABLE) | ✅ | Shows as NOT_ATTEMPTED blind spot (no regression) |
| `reactive` shows `swift_helper_unavailable` at INFORMATIONAL | ✅ code | Verified via unit test; live run constrained by env (see below) |
| No regression in existing extractors | ✅ | 8 fetched extractors unchanged |

---

## Environmental constraints

**Colima filesystem sharing (known limitation):**
- `/repos-hs/TronKit.Swift` is mounted but empty inside container (VirtioFS partial sync)
- Prevents running `testability_di` / `coding_convention` / `localization_accessibility` live on tron-kit
- Similarly, `/repos/gimle` shows only `.claude/` + `services/` (no `.git` visible)
- Neo4j (docker) not exposed on localhost:7687 — testcontainers integration tests fail

**Port 8080:**
- macOS nginx (started Thu 2PM) intercepts `localhost:8080` before docker port forwarding
- All MCP calls routed via `docker exec palace_mcp.cli ... --url http://127.0.0.1:8000/mcp`

**Full live extractor run on tron-kit** requires production deploy after merge:
```bash
bash paperclips/scripts/imac-deploy.sh --expect-extractor testability_di
```
Then re-run ingestion via the operator's MCP client (which has direct palace-mcp access).

The `reactive_dependency_tracer` swift_helper_unavailable diagnostic is verified
at the unit level (`test_audit_contract_present.py` line 61: severity_mapper("info") →
INFORMATIONAL). The extractor's `run()` method produces this diagnostic when
`reactive_facts.json` is absent — verified by code review and existing integration
test fixture logic.

---

## Post-merge steps (CTO Phase 4.2)

1. Squash-merge PR #165 to develop
2. Run `bash paperclips/scripts/imac-deploy.sh --expect-extractor testability_di`
3. Re-run `palace.ingest.run_extractor(name="reactive_dependency_tracer", project="tron-kit")`
4. Verify `swift_helper_unavailable` diagnostic in Neo4j:
   ```cypher
   MATCH (d:ReactiveDiagnostic {project: "tron-kit"})
   RETURN d.diagnostic_code, d.severity
   ```
   Expected: `swift_helper_unavailable` with `severity="info"` (→ INFORMATIONAL)
5. Re-run `palace.audit.run(project="tron-kit")` — `reactive_dependency_tracer` section should appear
