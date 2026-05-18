# Hot-Path Profiler Extractor (#17) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: `superpowers:test-driven-development`. Atomic-handoff discipline mandatory.

**Slice:** Phase 2 §2.5 #17 Hot-Path Profiler Extractor.
**Spec:** `docs/superpowers/specs/2026-05-07-hot-path-profiler-extractor_spec.md`.
**Source branch:** `feature/GIM-276-hot-path-profiler-extractor` cut from `origin/develop` **after E6 closes**.
**Target branch:** `develop`. Squash-merge on APPROVE.
**Team:** Codex. Phase chain: CXCTO → CXCodeReviewer (plan-first) → CXPythonEngineer (`e010d305-22f7-4f5c-9462-e6526b195b19`) → CXCodeReviewer (mechanical) → CodexArchitectReviewer (adversarial) → CXQAEngineer → CXCTO merge.

> **Track A / Track B rule (CR-rev1):** Track A is a committed,
> pre-recorded xctrace-derived JSON fixture and is the merge gate.
> Track B is optional live `xctrace` capture on a dev Mac and is
> deferred follow-up evidence. CI and merge review must not depend on
> local Instruments availability.

---

## Phase 0 — Prereqs (Board)

### Step 0.1: E6 gate

- [ ] Verify E6 ✅. If not, queue with `blockedByIssueIds=[<E6 id>]`.

### Step 0.2: Fixture profiles (CR-rev1 Track A/B split)

> **CR-rev1:** Track A is mandatory and merge-blocking. Track B is
> deferred.

#### Step 0.2a — Synthetic stubs for parser unit tests

**Owner:** CXPythonEngineer (during Phase 2.2 / 2.3).
**Files:** `services/palace-mcp/tests/extractors/fixtures/hot-path-fixture/synthetic/{instruments-stub.json,perfetto-stub.pftrace}`.

- [ ] Author minimal synthetic Instruments JSON (~10 sample frames,
      hand-crafted — does NOT need real Mac capture).
- [ ] Author minimal synthetic Perfetto trace (~10 events; can be
      generated with Perfetto trace-builder tooling or hand-rolled as
      a minimal protobuf for maximum determinism).
- [ ] These stubs feed **Phase 2.2** (Instruments parser unit tests)
      and **Phase 2.3** (Perfetto parser unit tests). Phase 2 work
      proceeds without waiting for real trace capture.

**Acceptance:** synthetic stubs committed; Phase 2.2 + 2.3 unit tests
runnable + GREEN against stubs.

#### Step 0.2b — Track A fixture (merge gate)

**Owner:** CXPythonEngineer, with Operator providing source trace if
needed.
**Files:**
- `services/palace-mcp/tests/extractors/fixtures/hot-path-fixture/profiles/track-a-instruments-time-profile.json`
- `services/palace-mcp/tests/extractors/fixtures/hot-path-fixture/profiles/track-a-instruments-time-profile.metadata.json`

- [ ] On a Mac with Xcode: capture an Instruments Time Profiler trace
      of `tronkit-swift` or `uw-ios-mini` execution; export the Time
      Profiler table via `xctrace export --input <trace> --xpath ...`.
- [ ] Normalize the exported table into the JSON parser input fixture
      above. Metadata file records Xcode version, source table XPath,
      source workload, anonymization/sub-sampling notes, and source
      command.
- [ ] Keep each committed fixture file ≤ 1MB.
- [ ] Add an integration test that fails if the Track A fixture is
      missing, empty, malformed, or produces zero `:HotPathSample`
      rows.

**Acceptance:** Track A fixture + metadata committed; Phase 2.4
integration test uses this fixture and is GREEN. Merge is blocked if
Track A fixture or test evidence is absent.

#### Step 0.2c — Track B live capture (deferred follow-up)

**Owner:** Operator / CXQAEngineer after implementation is reviewable.

- [ ] Run live `xctrace` capture on a dev Mac and compare top hot paths
      against Track A fixture behavior.
- [ ] Post evidence in the issue/PR if available.

**Acceptance:** optional only. Track B absence is not a merge blocker
once Track A fixture evidence is present.

### Step 0.3: Issue + branch

- [ ] Open paperclip issue `Hot-Path Profiler Extractor (#17)`.
- [ ] Body = link to spec + plan; `GIM-276` placeholder resolved.
- [ ] Reassign CXCTO.

---

## Phase 1 — CXCTO formalisation + plan-first review

### Step 1.1 (CXCTO)

- [ ] Verify spec §3 trace formats match captured fixtures.
- [ ] Resolve HP-D1..HP-D5 (defaults from spec).
- [ ] Verify API truth file exists:
      `docs/superpowers/specs/reference_xctrace_perfetto_traceconv_simpleperf_api_truth.md`.
- [ ] Reassign CXCodeReviewer.

### Step 1.2 (CXCodeReviewer plan-first)

- [ ] Verify each parser has test+impl+commit.
- [ ] Verify symbol resolution path uses Phase 1 symbol-index
      `:Function` nodes (no parallel symbol scheme).
- [ ] Verify Track A fixture path and Track B deferral are explicit.
- [ ] Verify implementation write scope and validation commands are
      concrete enough for Phase 3.1 comparison.
- [ ] APPROVE → CXPythonEngineer.

---

## Phase 2 — Implementation

### Phase 2.1 — Scaffolding

- [ ] Failing test: `HotPathProfilerExtractor` class exists, registered.
- [ ] Implement under
      `services/palace-mcp/src/palace_mcp/extractors/hot_path_profiler/{__init__.py,extractor.py,models.py}`.
- [ ] Add to `EXTRACTORS` registry in
      `services/palace-mcp/src/palace_mcp/extractors/registry.py`.
- [ ] Tests GREEN:
      `cd services/palace-mcp && uv run pytest tests/extractors/unit/test_hot_path_profiler_scaffold.py tests/extractors/unit/test_registry.py -k hot_path_profiler`.
- [ ] Commit: `feat(GIM-276): hot_path_profiler scaffolding`.

### Phase 2.2 — Instruments JSON parser (Mac side)

- [ ] Failing test: synthetic Instruments JSON → expected
      `:HotPathSample` rows.
- [ ] Implement parser under
      `services/palace-mcp/src/palace_mcp/extractors/hot_path_profiler/parsers/instruments.py`.
- [ ] Tests GREEN:
      `cd services/palace-mcp && uv run pytest tests/extractors/unit/test_hot_path_profiler_parser_instruments.py`.
- [ ] Commit: `feat(GIM-276): Instruments xctrace JSON parser`.

### Phase 2.3 — Perfetto pftrace parser (Android side)

- [ ] Failing test: synthetic Perfetto trace → expected rows.
- [ ] Add `perfetto` runtime dependency in
      `services/palace-mcp/pyproject.toml` and refresh
      `services/palace-mcp/uv.lock`.
- [ ] Implement parser under
      `services/palace-mcp/src/palace_mcp/extractors/hot_path_profiler/parsers/perfetto.py` using `perfetto.trace_processor.TraceProcessor`.
- [ ] Keep `traceconv` in fixture/runbook tooling unless the
      implementer pins a deterministic binary path.
- [ ] Dependency import validation:
      `cd services/palace-mcp && uv run python -c "from perfetto.trace_processor import TraceProcessor"`.
- [ ] Tests GREEN:
      `cd services/palace-mcp && uv run pytest tests/extractors/unit/test_hot_path_profiler_parser_perfetto.py`.
- [ ] Commit: `feat(GIM-276): Perfetto pftrace parser`.

### Phase 2.4 — Symbol resolution + Neo4j writer

#### Step 2.4.1: Failing integration test

- [ ] testcontainers Neo4j + pre-seeded `:Function` nodes (mock Phase 1
      symbol index output).
- [ ] Run extractor on Track A fixture
      `services/palace-mcp/tests/extractors/fixtures/hot-path-fixture/profiles/track-a-instruments-time-profile.json` → expect:
  - `:HotPathSample` rows linked by `qualified_name` to `:Function`.
  - `:Function` enriched with `cpu_share`, `wall_share`,
    `is_hot_path` properties.
  - `:HotPathSummary` row matches input trace metadata.
- [ ] Tests GREEN:
      `cd services/palace-mcp && uv run pytest tests/extractors/integration/test_hot_path_profiler_integration.py`.

#### Step 2.4.2: Implement symbol resolver + writer

- [ ] `services/palace-mcp/src/palace_mcp/extractors/hot_path_profiler/symbol_resolver.py` — match
      Instruments / Perfetto symbol names to SCIP qualified names;
      log unresolved as `:HotPathSampleUnresolved`.
- [ ] `services/palace-mcp/src/palace_mcp/extractors/hot_path_profiler/neo4j_writer.py` — batch writes;
      use S0.1 unified `:IngestRun` schema and canonical `project_id`.
- [ ] Tests GREEN:
      `cd services/palace-mcp && uv run pytest tests/extractors/unit/test_hot_path_profiler_symbol_resolver.py tests/extractors/unit/test_hot_path_profiler_neo4j_writer.py tests/extractors/integration/test_hot_path_profiler_integration.py`.
- [ ] Commit: `feat(GIM-276): hot_path_profiler symbol resolver + writer`.

### Phase 2.5 — extract() orchestration + runbook

#### Step 2.5.1: extract()

- [ ] Wire scaffolding to call parsers + resolver + writer.
- [ ] Configure trace-file discovery: read trace files from
      `/repos/<slug>/profiles/*.{json,pftrace}` in the mounted repo.
- [ ] Tests GREEN:
      `cd services/palace-mcp && uv run pytest tests/extractors/unit/test_hot_path_profiler_extractor.py tests/extractors/integration/test_hot_path_profiler_integration.py`.

#### Step 2.5.2: Author runbook

**Files:** `docs/runbooks/hot-path-profiler.md` (new).

- [ ] Document:
  - How to capture Instruments trace on a Mac (xctrace export
    command with concrete flags).
  - How to capture Perfetto trace on Android (steps, config).
  - Where to commit Track A fixtures in
    `services/palace-mcp/tests/extractors/fixtures/hot-path-fixture/profiles/`.
  - Expected fixture-file format / size.
  - How to run extractor: `palace.ingest.run_extractor(name="hot_path_profiler", project="<slug>")`.
  - Troubleshooting symbol resolution mismatches.

#### Step 2.5.3: Commit

- [ ] Commit: `feat(GIM-276): hot_path_profiler extract() + runbook`.

### Phase 2.6 — `audit_contract()` + template

- [ ] Failing test: `audit_contract()` returns expected.
- [ ] Failing test: template renders synthetic data.
- [ ] Implement per spec §5.
- [ ] Author
      `services/palace-mcp/src/palace_mcp/audit/templates/hot_path_profiler.md`.
- [ ] Add `HotPathAuditList` Pydantic model.
- [ ] Tests GREEN:
      `cd services/palace-mcp && uv run pytest tests/audit/unit/test_audit_contracts.py tests/audit/unit/test_templates.py -k hot_path_profiler`.
- [ ] Commit: `feat(GIM-276): hot_path_profiler audit_contract + template`.

### Phase 2.7 — CLAUDE.md catalogue

- [ ] Add `hot_path_profiler` row to `CLAUDE.md` §"Registered
      extractors" with team affinity (Codex), trace-file dependency
      note, and runbook reference.
- [ ] Push branch.
- [ ] Open PR `feat(GIM-276): hot_path_profiler extractor (#17)`.
- [ ] Reassign CXCodeReviewer.

---

## Phase 3 — Review

### Phase 3.1 — Mechanical (CXCodeReviewer)

- [ ] `gh pr checks` green; pytest output for the exact Phase 2
      commands above.
- [ ] Verify changed files are within approved scope:
  - `services/palace-mcp/src/palace_mcp/extractors/hot_path_profiler/**`
  - `services/palace-mcp/src/palace_mcp/extractors/registry.py`
  - `services/palace-mcp/src/palace_mcp/audit/templates/hot_path_profiler.md`
  - `services/palace-mcp/pyproject.toml`
  - `services/palace-mcp/uv.lock`
  - `services/palace-mcp/tests/extractors/unit/test_hot_path_profiler_*.py`
  - `services/palace-mcp/tests/extractors/integration/test_hot_path_profiler_integration.py`
  - `services/palace-mcp/tests/extractors/fixtures/hot-path-fixture/**`
  - `services/palace-mcp/tests/audit/unit/*` only for hot_path_profiler cases
  - `docs/runbooks/hot-path-profiler.md`
  - `CLAUDE.md`
- [ ] Verify Track A fixture files are committed and ≤ 1MB each.
- [ ] If Perfetto support remains in v1, verify `services/palace-mcp/pyproject.toml` and `services/palace-mcp/uv.lock` contain the pinned `perfetto` dependency and import validation output is present.
- [ ] APPROVE → CodexArchitectReviewer.

### Phase 3.2 — Adversarial

- [ ] Probe: Instruments XML vs JSON variant — which Xcode versions
      does parser handle?
- [ ] Probe: Perfetto trace with non-Linux thread states — graceful
      degradation?
- [ ] Probe: trace with 100K samples — does parser stream or load
      whole thing?
- [ ] Probe: HP-D2 threshold (5% CPU share) — sane on a quiet trace
      vs a busy trace? Configurable per-run?
- [ ] Probe: symbol mismatch fallback — does extractor abort or
      proceed with `:HotPathSampleUnresolved` markers?

---

## Phase 4 — QA evidence (CXQAEngineer on iMac)

- [ ] iMac live: bring up palace-mcp + Neo4j with fixture profiles
      mounted under `/repos/<slug>/profiles/`.
- [ ] Live MCP call: `palace.ingest.run_extractor(name="hot_path_profiler", project="<slug>")`.
- [ ] Cypher: `MATCH (s:HotPathSample) RETURN count(s)` > 0.
- [ ] Cypher: `MATCH (f:Function {is_hot_path: true}) RETURN f.qualified_name LIMIT 5` returns expected.
- [ ] QA Evidence in PR body.

---

## Phase 5 — Merge (CXCTO)

- [ ] CI green; CXCodeReviewer + CodexArchitectReviewer APPROVE; QA Evidence.
- [ ] Squash-merge.
- [ ] Update `docs/roadmap-archive.md` §2.5 #17 row → ✅ + SHA.
- [ ] iMac deploy.

---

## DoD checklist

- [ ] Scaffolding + Instruments parser + Perfetto parser + symbol
      resolver + writer + extract + runbook + audit_contract +
      template + CLAUDE.md update — merged.
- [ ] Smoke runs on fixture profile produce ≥3 hot-path entries.
- [ ] Roadmap updated.
- [ ] Track A xctrace-derived JSON fixture + metadata committed
      (Step 0.2b outputs).
- [ ] Track B live capture is either posted as optional evidence or
      explicitly deferred in the issue/PR.

---

## Risks (from spec §9)

R1 trace-format drift · R2 symbol-name mismatch · R3 huge trace files
· R4 capture variability · R5 xctrace schema undocumented.

---

## Cross-references

- Spec: `2026-05-07-hot-path-profiler-extractor_spec.md`.
- Predecessor: E6.
- Roadmap: `docs/roadmap-archive.md` §2.5 #17.
- xcodetracemcp follow-up: HP-D5 (separate slice if pursued).
