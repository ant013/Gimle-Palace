# Hot-Path Profiler Extractor (#17) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: `superpowers:test-driven-development`. Atomic-handoff discipline mandatory.

**Slice:** Phase 2 §2.5 #17 Hot-Path Profiler Extractor.
**Spec:** `docs/superpowers/specs/2026-05-07-hot-path-profiler-extractor_spec.md`.
**Source branch:** `feature/GIM-NN-hot-path-profiler-extractor` cut from `origin/develop` **after E6 closes**.
**Target branch:** `develop`. Squash-merge on APPROVE.
**Team:** Codex. Phase chain: CXCTO → CXCodeReviewer (plan-first) → CXPythonEngineer (or PE-2) → CXCodeReviewer (mechanical) → OpusArchitectReviewer (adversarial) → CXQAEngineer → CXCTO merge.

> **Blocked-on-E6** (CX hire) **+ profile-data fixtures**: this slice
> needs at least one Instruments `.json` + one Perfetto `.pftrace`
> fixture committed before integration tests can pass. Capture is a
> Mac/Android dev workflow; document it in the runbook (Phase 2.5).

---

## Phase 0 — Prereqs (Board)

### Step 0.1: E6 gate

- [ ] Verify E6 ✅. If not, queue with `blockedByIssueIds=[<E6 id>]`.

### Step 0.2: Capture fixture profiles (out-of-extractor manual step)

**Owner:** Board (operator + Mac dev).

- [ ] On a Mac with Xcode: capture an Instruments Time Profiler trace
      of `tronkit-swift` unit tests; export as JSON via
      `xctrace export --input <trace> --xpath ...`.
- [ ] On an Android dev box: capture a Perfetto trace of UW-Android
      app cold start.
- [ ] Trim each trace to ~1MB if possible (anonymise / sub-sample).
- [ ] Commit under
      `services/palace-mcp/tests/extractors/fixtures/hot-path-fixture/profiles/`.
- [ ] Document the exact `xctrace` / `traceconv` invocations in
      `docs/runbooks/hot-path-profiler.md` (authored in Phase 2.5).

**Acceptance:** at least 1 `.json` (Instruments) + 1 `.pftrace`
(Perfetto) committed; sizes documented.

### Step 0.3: Issue + branch

- [ ] Open paperclip issue `Hot-Path Profiler Extractor (#17)`.
- [ ] Body = link to spec + plan; `GIM-NN` placeholder.
- [ ] Reassign CXCTO.

---

## Phase 1 — CXCTO formalisation + plan-first review

### Step 1.1 (CXCTO)

- [ ] Verify spec §3 trace formats match captured fixtures.
- [ ] Resolve HP-D1..HP-D5 (defaults from spec).
- [ ] Reassign CXCodeReviewer.

### Step 1.2 (CXCodeReviewer plan-first)

- [ ] Verify each parser has test+impl+commit.
- [ ] Verify symbol resolution path uses Phase 1 symbol-index
      `:Function` nodes (no parallel symbol scheme).
- [ ] APPROVE → CXPythonEngineer.

---

## Phase 2 — Implementation

### Phase 2.1 — Scaffolding

- [ ] Failing test: `HotPathProfilerExtractor` class exists, registered.
- [ ] Implement under
      `extractors/hot_path_profiler/{__init__,extractor}.py`.
- [ ] Add to `EXTRACTORS` registry.
- [ ] Tests GREEN.
- [ ] Commit: `feat(GIM-NN): hot_path_profiler scaffolding`.

### Phase 2.2 — Instruments JSON parser (Mac side)

- [ ] Failing test: synthetic Instruments JSON → expected
      `:HotPathSample` rows.
- [ ] Implement parser under
      `extractors/hot_path_profiler/parsers/instruments.py`.
- [ ] Tests GREEN.
- [ ] Commit: `feat(GIM-NN): Instruments xctrace JSON parser`.

### Phase 2.3 — Perfetto pftrace parser (Android side)

- [ ] Failing test: synthetic Perfetto trace → expected rows.
- [ ] Implement parser under
      `extractors/hot_path_profiler/parsers/perfetto.py` using Perfetto
      SDK or subprocess `traceconv`.
- [ ] Tests GREEN.
- [ ] Commit: `feat(GIM-NN): Perfetto pftrace parser`.

### Phase 2.4 — Symbol resolution + Neo4j writer

#### Step 2.4.1: Failing integration test

- [ ] testcontainers Neo4j + pre-seeded `:Function` nodes (mock Phase 1
      symbol index output).
- [ ] Run extractor on fixture profile → expect:
  - `:HotPathSample` rows linked by `qualified_name` to `:Function`.
  - `:Function` enriched with `cpu_share`, `wall_share`,
    `is_hot_path` properties.
  - `:HotPathSummary` row matches input trace metadata.

#### Step 2.4.2: Implement symbol resolver + writer

- [ ] `extractors/hot_path_profiler/symbol_resolver.py` — match
      Instruments / Perfetto symbol names to SCIP qualified names;
      log unresolved as `:HotPathSampleUnresolved`.
- [ ] `extractors/hot_path_profiler/neo4j_writer.py` — batch writes;
      use S0.1 unified `:IngestRun` schema.
- [ ] Tests GREEN.
- [ ] Commit: `feat(GIM-NN): hot_path_profiler symbol resolver + writer`.

### Phase 2.5 — extract() orchestration + runbook

#### Step 2.5.1: extract()

- [ ] Wire scaffolding to call parsers + resolver + writer.
- [ ] Configure trace-file discovery: read trace files from
      `/repos/<slug>/profiles/*.{json,pftrace}` in the mounted repo.
- [ ] Tests GREEN.

#### Step 2.5.2: Author runbook

**Files:** `docs/runbooks/hot-path-profiler.md` (new).

- [ ] Document:
  - How to capture Instruments trace on a Mac (xctrace export
    command with concrete flags).
  - How to capture Perfetto trace on Android (steps, config).
  - Where to commit traces in the project (`profiles/` directory in
    the target repo).
  - Expected fixture-file format / size.
  - How to run extractor: `palace.ingest.run_extractor(name="hot_path_profiler", project="<slug>")`.
  - Troubleshooting symbol resolution mismatches.

#### Step 2.5.3: Commit

- [ ] Commit: `feat(GIM-NN): hot_path_profiler extract() + runbook`.

### Phase 2.6 — `audit_contract()` + template

- [ ] Failing test: `audit_contract()` returns expected.
- [ ] Failing test: template renders synthetic data.
- [ ] Implement per spec §5.
- [ ] Author `audit/templates/hot_path_profiler.md`.
- [ ] Add `HotPathAuditList` Pydantic model.
- [ ] Tests GREEN.
- [ ] Commit: `feat(GIM-NN): hot_path_profiler audit_contract + template`.

### Phase 2.7 — CLAUDE.md catalogue

- [ ] Add `hot_path_profiler` row to `CLAUDE.md` §"Registered
      extractors" with team affinity (Codex), trace-file dependency
      note, and runbook reference.
- [ ] Push branch.
- [ ] Open PR `feat(GIM-NN): hot_path_profiler extractor (#17)`.
- [ ] Reassign CXCodeReviewer.

---

## Phase 3 — Review

### Phase 3.1 — Mechanical (CXCodeReviewer)

- [ ] `gh pr checks` green; pytest output for new tests.
- [ ] Verify trace-file fixture sizes ≤ 1MB each (per Step 0.2).
- [ ] APPROVE → OpusArchitectReviewer.

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

- [ ] CI green; CR + Opus APPROVE; QA Evidence.
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
- [ ] Profile fixtures committed (Step 0.2 outputs).

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
