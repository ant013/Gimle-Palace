# Runbook: UW Android Ingest — 2026-05-20

## Scope

This runbook records the `GIM-379` operator path for ingesting the pinned
`uw-android` repo with the new
[`paperclips/scripts/ingest_kotlin_module.sh`](../../paperclips/scripts/ingest_kotlin_module.sh).

- Repo: `/Users/Shared/Android/unstoppable-wallet-android`
- Required pin: `c0489d5a33f5da441f07b1f685d42b25b805ffd1`
- MCP URL used for verification: `http://localhost:18080/mcp`
- Compose project used for verification: `gimle-palace-gim379`

Verification used an isolated compose project on `:18080` so the ingest could be
validated without relying on the shared `:8080` operator stack.

## Commands

```bash
cd /Users/Shared/Ios/worktrees/cx/Gimle-Palace-GIM-379

# One-off isolated verification stack
sed 's/"8080:8000"/"18080:8000"/' docker-compose.yml > docker-compose.gim379.yml
docker compose -p gimle-palace-gim379 \
  --env-file .env \
  -f docker-compose.gim379.yml \
  up -d neo4j palace-mcp

# Live ingest
paperclips/scripts/ingest_kotlin_module.sh \
  --env-file .env \
  --compose-project-name gimle-palace-gim379 \
  --compose-file ./docker-compose.gim379.yml \
  --mcp-url http://localhost:18080/mcp

# Audit verification
uv run --directory services/palace-mcp python -m palace_mcp.cli tool call \
  palace.audit.run \
  --url http://localhost:18080/mcp \
  --json '{"project":"uw-android"}'
```

## Runtime Summary

| Metric | Value |
|---|---:|
| Total script runtime | `148s` |
| Gradle task | `compileDebugKotlin` |
| SemanticDB files | `36` |
| `scip/index.scip` size | `815,994 bytes` |
| Repo pin verified | `c0489d5a33f5da441f07b1f685d42b25b805ffd1` |

## Extractor Results

Default bounded extractor set: `symbol_index_java`, `arch_layer`,
`git_history`, `code_ownership`, `dependency_surface`, `hotspot`,
`coding_convention`, `cross_repo_version_skew`, `public_api_surface`,
`cross_module_contract`, `hot_path_profiler`, `testability_di`.

`localization_accessibility` was left out of the default bounded path because it
showed unbounded live-runtime behavior on the full repo and is not required to
clear the `GIM-379` acceptance bar.

| Extractor | Status | Duration ms | Nodes written | Outcome |
|---|---|---:|---:|---|
| `symbol_index_java` | `OK` | `8979` | `6287` | `ok` |
| `arch_layer` | `OK` | `8871` | `8` | `ok` |
| `git_history` | `OK` | `671` | `0` | `ok` |
| `code_ownership` | `OK` | `407` | `1` | `ok` |
| `dependency_surface` | `OK` | `2848` | `0` | `ok` |
| `hotspot` | `OK` | `56671` | `5685` | `ok` |
| `coding_convention` | `OK` | `17440` | `516` | `ok` |
| `cross_repo_version_skew` | `OK` | `25` | `1` | `ok` |
| `public_api_surface` | `OK` | `2` | `0` | `missing_input` |
| `cross_module_contract` | `OK` | `15` | `0` | `skipped` |
| `hot_path_profiler` | `OK` | `1` | `0` | `missing_input` |
| `testability_di` | `OK` | `3727` | `30` | `ok` |

Status totals from the ingest summary:

| Status | Count |
|---|---:|
| `OK` | `12` |
| `RUN_FAILED` | `0` |
| `NOT_REGISTERED` | `0` |

## Audit Verification

`palace.audit.run(project="uw-android")` returned `ok=true`.

Audit result snapshot:

| Field | Value |
|---|---|
| `ok` | `true` |
| `status_counts.OK` | `4` |
| `status_counts.NOT_APPLICABLE` | `11` |
| `blind_spots` | `[]` |
| `fetched_extractors` | `arch_layer`, `code_ownership`, `dependency_surface`, `hotspot` |

The audit profile remains `android_kit`, so audit coverage is intentionally
limited to the four audit-contract extractors for that profile. The ingest
script runs a broader 12-extractor set to satisfy the operator readiness goal
for `uw-android`.
