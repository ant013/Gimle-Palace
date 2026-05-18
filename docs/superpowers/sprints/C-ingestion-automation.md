# Sprint S3 (C) — Per-Kit ingestion automation

> **Rev2** (2026-05-06): fixes MCP-from-bash invocation mechanism
> (CTO-HIGH-6, CR-HIGH-4). Corrects extractor cascade — 7/10 exist
> (CR-CRITICAL-1 was factually wrong). Confirms bundle tools exist
> (CR-CRITICAL-2 was factually wrong). Defines `palace_mcp.cli` as
> invocation mechanism.

**Goal**: shrink per-Kit setup from ~30 min manual (10 steps) to
~3 min `bash ingest_swift_kit.sh <kit-slug>`. Required for S5
(scaling to 41 Kits + wallet-ios) — 41 × 30 min = 20 hours of
manual work is un-shippable.

**Wall-time**: ~1 week calendar (one Board+Claude session +
InfraEngineer + QA chain).

**Driver**: parallelisable with S1 (this sprint is InfraEngineer
domain; S1 needs PythonEngineer). No file overlap.

**Definition of Done**:
1. `paperclips/scripts/ingest_swift_kit.sh <slug>` orchestrator on
   iMac performs all 10 manual steps idempotently.
2. `paperclips/scripts/scip_emit_swift_kit.sh <slug>` on dev Mac
   builds + emits SCIP + scp's to iMac mount point.
3. Per-Kit health-check post-ingest:
   `palace.memory.health(project=<slug>)` returns `success` for
   all expected extractors.
4. Operator runbook: `docs/runbooks/ingest-swift-kit.md`.
5. Smoke: full ingestion of one HS Kit end-to-end.

**Explicitly NOT in this sprint**:
- iMac ↔ dev Mac trust automation — operator provisions ssh manually.
- Multi-Kit batch mode — handled in S5.
- Auto-detection of extractor changes — explicit `--extractors=...` flag.

---

## MCP tool invocation from scripts (rev2 — CTO-HIGH-6, CR-HIGH-4)

**Problem**: The scripts call MCP tools (`palace.memory.register_project`,
`palace.ingest.run_extractor`, `palace.memory.add_to_bundle`) but MCP
requires a client connection. A bare bash script can't call them directly.

**Solution**: `python3 -m palace_mcp.cli <tool> [--arg=value]` — a thin
one-shot CLI module that connects to palace-mcp's streamable HTTP endpoint
(already exposed) and executes a single MCP tool call. Returns JSON to stdout.

The CLI is built in S1.9 (it's a shared prerequisite). S3 scripts use it:

```bash
python3 -m palace_mcp.cli memory.register_project --slug="$SLUG" --parent_mount="/repos/$SLUG"
python3 -m palace_mcp.cli memory.add_to_bundle --bundle="$BUNDLE" --project="$SLUG"
python3 -m palace_mcp.cli ingest.run_extractor --name="$EXTRACTOR" --project="$SLUG"
```

**Prerequisite**: S1.9 delivers `palace_mcp.cli`. If S3 starts before S1.9
merges, the script can use `curl` against the HTTP endpoint as a temporary
shim (palace-mcp exposes `POST /mcp` with JSON-RPC).

---

## Extractor cascade status (rev2 — correcting CR-CRITICAL-1)

**CR claimed 0/10 cascade extractors exist. This is wrong.** Verified against
develop HEAD `registry.py` (14 extractors registered):

| S3.2 cascade extractor | Status | Notes |
|---|---|---|
| `symbol_index_swift` | **exists** | `SymbolIndexSwift()` — GIM-128 |
| `git_history` | **exists** | `GitHistoryExtractor()` — GIM-186 |
| `dependency_surface` | **exists** | `DependencySurfaceExtractor()` — GIM-191 |
| `public_api_surface` | **exists** | `PublicApiSurfaceExtractor()` — GIM-190 |
| `dead_symbol_binary_surface` | **exists** | `DeadSymbolBinarySurfaceExtractor()` — GIM-193 |
| `hotspot` | **exists** | `HotspotExtractor()` — GIM-195 |
| `cross_module_contract` | **exists** | `CrossModuleContractExtractor()` — GIM-192 |
| `code_ownership` | **pending** | GIM-216 — PR #105 in Phase 3 |
| `cross_repo_version_skew` | **pending** | GIM-218 — not started |
| `crypto_domain_model` | **pending** | S2 deliverable |

**7/10 exist today. 3 pending** (ownership, skew, crypto).
The cascade script skips missing extractors with a warning.

## Bundle tools status (rev2 — correcting CR-CRITICAL-2)

**CR claimed bundle concept is completely absent. This is wrong.**
`memory/bundle.py` (309 lines, GIM-182) implements full CRUD:
- `palace.memory.register_bundle`
- `palace.memory.add_to_bundle`
- `palace.memory.bundle_members`
- `palace.memory.bundle_status`
- `palace.memory.delete_bundle`

All registered in `mcp_server.py`. S3.2 step 7 works as-written.

---

## Slices

### S3.1 — `scip_emit_swift_kit.sh` (dev Mac side)

**Files**:
- `paperclips/scripts/scip_emit_swift_kit.sh`

**Scope**: take `<slug>` arg, locate or clone repo, build, emit SCIP
via `scip_emit_swift` package (GIM-128), scp to iMac at
`/repos/<slug>/scip/index.scip`.

**Idempotency**: re-run with same `<slug>` re-builds and overwrites.

**Decision points**:
- D3-1: branch/commit pinning. Default: latest `main`/`master`.
- D3-2: build flavour. Default: Debug (faster).

**Size**: ~1-2 hours.

---

### S3.2 — `ingest_swift_kit.sh` (iMac orchestrator)

**Files**:
- `paperclips/scripts/ingest_swift_kit.sh`

**Scope**: 10-step orchestration:

1. Validate `<slug>` regex.
2. Verify `/repos/<slug>` mount exists. If not, edit
   `docker-compose.override.yml` to add bind-mount; restart palace-mcp.
3. Verify `/repos/<slug>/scip/index.scip` exists. If absent, abort.
4. Update `.env`: `PALACE_SCIP_INDEX_PATHS` JSON merge. Uses `jq`
   for safe JSON read-merge-write.
5. `docker compose up -d --force-recreate palace-mcp`.
6. `python3 -m palace_mcp.cli memory.register_project --slug=<slug> ...`
7. `python3 -m palace_mcp.cli memory.add_to_bundle --bundle=<bundle> --project=<slug>`
   (if `--bundle` flag provided).
8. Run extractor cascade (skip missing with warning):
   - `symbol_index_swift`
   - `git_history`
   - `dependency_surface`
   - `public_api_surface`
   - `dead_symbol_binary_surface`
   - `hotspot`
   - `cross_module_contract`
   - `code_ownership` (skip if not registered)
   - `cross_repo_version_skew` (skip if not registered)
   - `crypto_domain_model` (skip if not registered)
9. After each, verify health; log failure but continue.
10. Final summary to stdout.

**Error recovery**: if step N fails, script reports the step and
continues to next extractor. `--resume-from=N` is deferred to S6+.

**Decision points**:
- D3-3: fixed list vs `--extractors=...` override? Default: fixed with skip.
- D3-4: bundle membership — `--bundle=<name>` explicit flag.

**Size**: ~2-3 hours.

---

### S3.3 — Health-check + idempotency tests

**Files**:
- `paperclips/scripts/tests/test_ingest_idempotency.sh`

**Scope**: integration test against a known fixture (oz-v5-mini),
verifies extractors report success, re-runs to verify idempotency.

**Size**: ~1-2 hours.

---

### S3.4 — Operator runbook

**Files**:
- `docs/runbooks/ingest-swift-kit.md`

**Scope**: end-to-end instructions + troubleshooting + per-Kit cookbook.

**Size**: ~1 hour.

---

## Risks

| Risk | Mitigation |
|------|------------|
| dev Mac build fails on a Kit | S4 smoke catches; runbook accumulates per-Kit notes |
| iMac mount drift | Script reads compose once; mismatch = fail-fast |
| `.env` JSON parse fails | `jq` for safe merge; reject non-JSON input |
| Cascade order matters | Fixed order in spec; explicit slice for changes |
| `palace_mcp.cli` not ready when S3 starts | Temporary `curl` shim against HTTP endpoint |

## Cross-references

- Overview: `audit-v1-overview.md`
- Workflow: `D-audit-orchestration.md`
- Smoke that uses this script: `E-smoke.md`
- Existing runbook precedent: `docs/runbooks/multi-repo-spm-ingest.md`
