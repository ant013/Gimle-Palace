---
issue: GIM-77
title: "N+1a.3 Bridge extractor — project CM facts into Graphiti"
status: ready-for-review
branch: feature/GIM-77-bridge-extractor
predecessor: 804e897 (develop tip at branch creation, 2026-04-25)
spec: docs/superpowers/specs/2026-04-24-N1a-3-bridge-extractor-design.md
depends_on:
  - GIM-75 (Graphiti foundation) — merged cf2fd0f
  - GIM-76 (CM sidecar) — merged 804e897
date: 2026-04-25
---

# Plan — GIM-77: Bridge extractor

## Overview

New extractor `codebase_memory_bridge` reads selected facts from Codebase-Memory
(via `palace.code.*`) and writes them as Graphiti `EntityNode`/`EntityEdge` with
metadata envelope. Manual trigger via `palace.ingest.run_extractor`.

## Tasks

### Task 1 — Extractor skeleton + registry

**Owner:** PythonEngineer
**Files:**
- `services/palace-mcp/src/palace_mcp/extractors/codebase_memory_bridge.py` (new)
- `services/palace-mcp/src/palace_mcp/extractors/registry.py` (edit — add import + register)

**Acceptance:**
- Class `CodebaseMemoryBridgeExtractor` inherits `BaseExtractor`.
- `name = "codebase_memory_bridge"`, `version = "0.1"`.
- Registered in `EXTRACTORS` dict.
- `palace.ingest.list_extractors()` returns `codebase_memory_bridge`.
- `ruff check` + `mypy` pass.

**Test:**
- Unit: `test_extractor_registered` — `EXTRACTORS["codebase_memory_bridge"]` is an instance of `CodebaseMemoryBridgeExtractor`.

**Commit:** `feat(gim77): scaffold codebase_memory_bridge extractor`

---

### Task 2 — Projection rules: asserted nodes (Project, File, Module, Symbol, APIEndpoint)

**Owner:** PythonEngineer
**Depends on:** Task 1
**Files:**
- `codebase_memory_bridge.py` (extend `run()`)

**Acceptance:**
- Bridge reads CM via `palace.code.search_graph` / `palace.code.query_graph`.
- Maps CM `:Project`/`:File`/`:Module` → Graphiti same-named EntityNode.
- Maps CM `:Function`/`:Method`/`:Class`/`:Interface`/`:Enum`/`:Type` → Graphiti `:Symbol{kind=...}`.
- Maps CM `:Route` → Graphiti `:APIEndpoint`.
- Every node carries `attributes`: `cm_id`, `qualified_name`, `confidence=1.0`, `provenance="asserted"`, `extractor="codebase_memory_bridge@0.1"`, `extractor_version="0.1"`, `evidence_ref=["cm:<cm_id>"]`, `observed_at=<iso>`.

**Test:**
- Unit: `test_projection_rules_coverage` — every CM type in `_CM_TO_GRAPHITI_MAP` has target + provenance + confidence.
- Unit: `test_metadata_envelope_on_every_projection` — all 6 metadata fields populated on every projected entity.
- Unit: `test_cm_id_present_on_every_projected_node`.
- Unit: `test_qualified_name_populated_on_symbol_file_module`.

**Commit:** `feat(gim77): projection rules for asserted nodes`

---

### Task 3 — Projection rules: asserted edges (CONTAINS, DEFINES, CALLS, IMPORTS, HANDLES)

**Owner:** PythonEngineer
**Depends on:** Task 2
**Files:**
- `codebase_memory_bridge.py` (extend)

**Acceptance:**
- CM `CONTAINS_*` → Graphiti `CONTAINS`, `provenance="asserted"`, `confidence=1.0`.
- CM `DEFINES`/`CALLS`/`IMPORTS` → same name, same provenance.
- CM `HANDLES` → `HANDLES` with CM's own `confidence` attr.
- Every edge has `valid_at = now`, `cm_edge_id` in attributes.

**Test:**
- Unit: `test_skipped_edges_not_projected` — CM edges in skip-list produce zero Graphiti edges.

**Commit:** `feat(gim77): projection rules for asserted edges`

---

### Task 4 — Derived layer: ArchitectureCommunity + Hotspot

**Owner:** PythonEngineer
**Depends on:** Task 2
**Files:**
- `codebase_memory_bridge.py` (extend)

**Acceptance:**
- CM Louvain community nodes → Graphiti `:EntityNode` with `labels=["ArchitectureCommunity"]`, `provenance="derived"`, `confidence=<modularity_score>`.
- Community `MEMBER_OF` edges projected.
- CM `FILE_CHANGES_WITH` top-5% → Graphiti `:EntityNode` with `labels=["Hotspot"]`, `provenance="derived"`, `confidence=<normalized_cochange_rank>`.
- Hotspot `LOCATES_IN` edges to `:File` projected.

**Test:**
- Unit: mock CM Louvain output → verify ArchitectureCommunity nodes + MEMBER_OF edges created.
- Unit: mock CM co-change data → verify only top-5% become Hotspots.

**Commit:** `feat(gim77): derived layer — ArchitectureCommunity + Hotspot`

---

### Task 5 — Incremental sync via XXH3 hash compare

**Owner:** PythonEngineer
**Depends on:** Tasks 2, 3
**Files:**
- `codebase_memory_bridge.py` (extend)

**Acceptance:**
- Bridge state file `~/.paperclip/codebase-memory-bridge-state.json` tracks `{project_slug, last_run_at, file_hashes: {cm_id: xxh3}}`.
- Unchanged files (same xxh3) → no writes.
- Changed files → re-project affected symbols + edges with fresh `valid_at`.
- Removed CM files → Graphiti edges get `invalid_at = now`.
- State file rewritten after successful run.
- Does NOT use `palace.code.detect_changes` (that's uncommitted diff only).

**Test:**
- Unit: `test_incremental_skips_unchanged_files` — second run on identical CM state writes 0 nodes/edges.
- Unit: `test_incremental_invalidates_removed_edges` — file dropped → edge `invalid_at` set.
- Unit: `test_incremental_uses_hash_compare_not_detect_changes` — mock `detect_changes` to raise; bridge syncs fine.

**Commit:** `feat(gim77): incremental sync via XXH3 hash compare`

---

### Task 6 — Health reporting extension

**Owner:** PythonEngineer
**Depends on:** Task 1
**Files:**
- `services/palace-mcp/src/palace_mcp/memory/health.py` (edit)

**Acceptance:**
- `palace.memory.health()` returns `bridge` section: `last_run_at`, `last_run_duration_ms`, `nodes_written_by_type`, `edges_written_by_type`, `cm_index_freshness_sec`, `staleness_warning`.
- `staleness_warning = true` if `now - last_run_at > 2 * expected_interval`.

**Test:**
- Unit: `test_health_bridge_section_present` after one mock bridge run.

**Commit:** `feat(gim77): extend health reporting with bridge stats`

---

### Task 7 — Integration tests

**Owner:** PythonEngineer
**Depends on:** Tasks 1-6
**Files:**
- `tests/extractors/integration/test_codebase_memory_bridge_integration.py` (new)

**Acceptance:**
- Uses testcontainers-neo4j + CM subprocess + `tests/fixtures/sandbox-repo/`.
- `test_bridge_full_run` — non-zero Symbol/File results with `cm_id`; ArchitectureCommunity ≥1; Hotspot ≤5% of files; `provenance` always `asserted` or `derived`.
- `test_cross_resolve_symbol_to_cm` — pick Symbol, use `qualified_name` → `palace.code.get_code_snippet()` returns matching source body.
- `test_incremental_rerun_no_op` — second run: `nodes_written=0, edges_written=0`.
- `test_file_modification_incremental_update` — edit one fixture file, re-run → only affected symbols updated.
- `test_bridge_health_reporting` — `health()['bridge']` populated after one run.

**Commit:** `test(gim77): integration tests for codebase_memory_bridge`

---

### Task 8 — Unit tests (collected)

**Owner:** PythonEngineer
**Depends on:** Tasks 1-6 (written alongside each task)
**Files:**
- `tests/extractors/unit/test_codebase_memory_bridge.py` (new)

**Acceptance:**
- All unit tests from Tasks 1-6 collected in one file.
- `uv run pytest tests/extractors/unit/test_codebase_memory_bridge.py` green.

**Commit:** `test(gim77): unit tests for codebase_memory_bridge`

---

### Task 9 — README update

**Owner:** PythonEngineer
**Depends on:** Tasks 1-6
**Files:**
- `services/palace-mcp/README.md` (edit)

**Acceptance:**
- Bridge extractor documented with usage example and cross-resolve example.

**Commit:** `docs(gim77): document bridge extractor in README`

---

### Task 10 — Live smoke on iMac (Phase 4.1)

**Owner:** QAEngineer
**Depends on:** Tasks 1-9 merged, CI green
**Steps:** per spec §6.3 (9-point checklist).

## Dependency graph

```
Task 1 (skeleton)
├── Task 2 (asserted nodes)  ─┬── Task 3 (asserted edges) ─┬── Task 5 (incremental)
│                              │                             │
│                              └── Task 4 (derived layer) ───┘
├── Task 6 (health)
└── Task 8 (unit tests, alongside 1-6)

Tasks 1-6 ──► Task 7 (integration tests)
Tasks 1-6 ──► Task 9 (README)
Tasks 1-9 ──► Task 10 (live smoke, QAEngineer)
```

## Phase sequence

| Phase | Agent | Scope |
|-------|-------|-------|
| 1.1 Formalize | CTO | This plan. Branch creation. |
| 1.2 Plan-first review | CodeReviewer | Validate tasks have concrete test+impl+commit. |
| 2 Implement | PythonEngineer | Tasks 1-9 (TDD). |
| 3.1 Mechanical review | CodeReviewer | `ruff check && mypy src/ && pytest` output. |
| 3.2 Adversarial review | OpusArchitectReviewer | Poke holes. |
| 4.1 Live smoke | QAEngineer | Task 10 on iMac. |
| 4.2 Merge | CTO | Squash-merge to develop. |
