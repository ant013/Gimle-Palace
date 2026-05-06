# Sprint S3 (C) — Per-Kit ingestion automation

**Goal**: shrink per-Kit setup from ~30 min manual (10 steps) to
~3 min `bash ingest_swift_kit.sh <kit-slug>`. Required for S5
(scaling to 41 Kits + wallet-ios) — 41 × 30 min = 20 hours of
manual work is un-shippable.

**Wall-time**: ~1 week calendar (one Board+Claude session +
InfraEngineer + QA chain).

**Driver**: parallelisable with S1+S2 (this sprint touches only
shell scripts + docker-compose generators; no overlap with extractor
or workflow code).

**Definition of Done**:
1. `paperclips/scripts/ingest_swift_kit.sh <slug>` orchestrator on
   iMac performs all 10 manual steps idempotently.
2. `paperclips/scripts/scip_emit_swift_kit.sh <slug>` on dev Mac
   builds + emits SCIP + scp's to iMac mount point.
3. Per-Kit health-check post-ingest:
   `palace.memory.health(project=<slug>)` returns `success` for
   all expected extractors.
4. Operator runbook: `docs/runbooks/ingest-swift-kit.md`.
5. Smoke: full ingestion of one HS Kit
   (e.g., `marketkit-swift` — small, well-understood) end-to-end.

**Explicitly NOT in this sprint**:
- iMac ↔ dev Mac trust automation (rsync key exchange) — operator
  provisions manually, script reads pre-configured ssh.
- Multi-Kit batch mode (`ingest_all_uw_ios_kits.sh`) — handled in
  S5 after this script proves on a single Kit.
- Auto-detection of extractor changes — explicit `--extractors=...`
  flag for v1.

---

## Slices

### S3.1 — `scip_emit_swift_kit.sh` (dev Mac side)

**Files**:
- `paperclips/scripts/scip_emit_swift_kit.sh`

**Scope**: take `<slug>` arg, locate or clone repo, build, emit SCIP
via `scip_emit_swift` package (already in repo from GIM-128), scp
to iMac at `/repos/<slug>/scip/index.scip`.

**Dependencies**: dev Mac has Xcode + Swift 5.9+ (real-source
ingestion needs modern toolchain per `reference_imac_toolchain_limits.md`).

**Idempotency**: re-run with same `<slug>` re-builds and overwrites.

**Decision points**:
- D3-1: branch / commit pinning per Kit. Default: latest `main`
  / `master`. Operator can override via `--ref=<sha-or-tag>`.
- D3-2: build flavour (Debug / Release). Default: Debug (faster
  index emit; no production codegen needed for static analysis).

---

### S3.2 — `ingest_swift_kit.sh` (iMac orchestrator)

**Files**:
- `paperclips/scripts/ingest_swift_kit.sh`
- `paperclips/scripts/lib/ingest_helpers.sh` — shared helpers if any

**Scope**: 10-step orchestration:

1. Validate `<slug>` regex.
2. Verify `/repos/<slug>` mount exists (or `/repos-hs/<rel-path>` if
   bundled HS Kit). If not mounted, edit
   `docker-compose.override.yml` to add the bind-mount; restart
   `palace-mcp`.
3. Verify `/repos/<slug>/scip/index.scip` exists. If absent,
   abort with operator-facing error: "run `scip_emit_swift_kit.sh
   <slug>` on dev Mac first; expected at <path>".
4. Update `.env`: `PALACE_SCIP_INDEX_PATHS` JSON to include
   `<slug>: /repos/<slug>/scip/index.scip`. Idempotent edit (read,
   parse, merge, write).
5. `docker compose up -d --force-recreate palace-mcp` (re-read .env).
6. `palace.memory.register_project(slug=<slug>, parent_mount=<...>,
   relative_path=<...>)` — idempotent.
7. `palace.memory.add_to_bundle(bundle="uw-ios", project=<slug>,
   tier=<...>)` if `<slug>` is a UW iOS Kit. Idempotent.
8. Run extractor cascade in fixed order (per audit-v1 v1
   extractor set):
   - `symbol_index_swift`
   - `git_history`
   - `dependency_surface`
   - `public_api_surface`
   - `dead_symbol_binary_surface`
   - `hotspot`
   - `code_ownership` (post-GIM-216 merge)
   - `cross_repo_version_skew` (post-GIM-218 merge)
   - `cross_module_contract`
   - `crypto_domain_model` (post-S2 merge)
9. After each, verify `palace.memory.health(project=<slug>)` returns
   `success` for that extractor; abort on failure.
10. Final report to stdout: list of `:IngestRun.run_id` per
    extractor with status.

**Error recovery**: if step N fails, script exits with a clear
"to retry, run `ingest_swift_kit.sh <slug> --resume-from=N`".
Stretch goal — defer to S6+ if too complex for v1.

**Decision points**:
- D3-3: extractor cascade order — fixed list vs `--extractors=...`
  override? Default: fixed list (simpler; operator overrides via
  flag per slice).
- D3-4: bundle membership policy — auto-detect HS Kit by slug
  prefix vs `--bundle=<name>` flag? Default: `--bundle=<name>`
  explicit (avoid surprises).

---

### S3.3 — Health-check + idempotency tests

**Files**:
- `paperclips/scripts/tests/test_ingest_idempotency.sh`
- (optional) Python unit tests for `.env` JSON merge logic if
  extracted to a helper.

**Scope**: integration test that runs `ingest_swift_kit.sh` against
a known fixture (gimle itself or oz-v5-mini), verifies all 9
extractors report success, then re-runs and verifies idempotency
(no duplicate `:Project` / `:HAS_MEMBER`, no fresh `:IngestRun`
unless target HEAD changed).

---

### S3.4 — Operator runbook

**Files**:
- `docs/runbooks/ingest-swift-kit.md`

**Scope**: end-to-end operator instructions, including:
- Pre-flight: dev Mac toolchain check, iMac ssh access, .env
  template.
- Happy path: 3 commands (dev Mac scip-emit → iMac ingest → verify).
- Troubleshooting per-step.
- Per-Kit cookbook entries for known UW iOS Kits (marketkit,
  evmkit, bitcoinkit, tronkit, etc — at least 5 entries with any
  Kit-specific quirks discovered during S4 smoke).

---

## Risks

| Risk | Mitigation |
|------|------------|
| dev Mac build fails on a specific Kit (toolchain, dependency, etc) | S4 smoke catches per-Kit issues; runbook accumulates per-Kit notes; broken Kits flagged with `--skip` until fixed |
| iMac mount drift — operator manually edits docker-compose.yml between runs | Script reads docker-compose ONCE on first ingest; subsequent runs assume mount stable; mismatch triggers fail-fast with diff |
| `.env` JSON parse fails on malformed input | Use `jq` or Python `json.tool` for read-merge-write; reject non-JSON input with explicit error |
| Extractor cascade order matters (e.g., dependency_surface before cross_repo_version_skew) | Fixed order documented in spec; future changes require explicit slice update |

## Cross-references

- Overview: `audit-v1-overview.md`
- Workflow: `D-audit-orchestration.md`
- Smoke that uses this script: `E-smoke.md`
- Existing single-Kit runbook precedent: `docs/runbooks/multi-repo-spm-ingest.md`
