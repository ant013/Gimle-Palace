# Hot-Path Profiler Extractor (#17) — Specification

**Document date:** 2026-05-07
**Status:** Draft · awaiting CX-CTO formalisation (post-E6 close)
**Author:** Board+Claude session (operator + Claude Opus 4.7)
**Team:** Codex (CX-native: Instruments xctrace + Perfetto / simpleperf + xcodetracemcp MCP)
**Slice ID:** Phase 2 §2.5 #17 Hot-Path Profiler Extractor
**Companion plan:** `2026-05-07-hot-path-profiler-extractor_plan.md`
**Branch:** `feature/GIM-NN-hot-path-profiler-extractor`
**Blocker:** **E6 closure** (CX hire) + **profile-data fixtures** (see §8).

---

## 1. Goal

Ingest profiling-trace data (Instruments / Perfetto / simpleperf
captures) and connect hot-path samples to `:Symbol` / `:Function`
nodes so audit agents can answer:

- "What functions consume the most CPU / wall time on the launch path?"
- "Are crypto / signing functions on the hot path? (red flag if yes)"
- "Which UI thread blockers exist?"

Addresses target problem **#8 (perf bottlenecks visible in graph)**
in the original 45-extractor research inventory.

**Definition of Done:**

1. New extractor `hot_path_profiler` registered in `EXTRACTORS`.
2. `audit_contract()` returns hot-path summary as Pydantic model.
3. Writes `:HotPathSample` + `:HotPathSummary` nodes; enriches
   existing `:Function` with `cpu_share`, `wall_share`, `is_hot_path`
   properties.
4. `audit/templates/hot_path_profiler.md` ships.
5. Operator runbook `docs/runbooks/hot-path-profiler.md` documenting
   how to capture profile data (out-of-extractor — Mac dev workflow).
6. Smoke run on a fixture profile against `tronkit-swift` produces
   ≥3 hot-path entries with file/line back-refs to `:Function`.

## 2. Scope

### In scope
- **Trace formats**: Instruments `.trace` exported via xctrace
  (Time Profiler instrument), Perfetto / simpleperf `.pftrace`
  (Android), iOS DTPS `.signpost`. Optionally
  [xcodetracemcp](https://github.com/Sourceful-AI/xcodetracemcp) MCP
  for Mac-side capture-as-MCP-tool.
- **Sample aggregation**: per-function CPU-share and wall-time-share
  across the trace.
- **Symbol resolution**: link samples to `:Function` nodes via
  `qualified_name` (post-Phase 1 symbol-index).
- **Hot-path classification**: heuristic threshold (e.g., CPU
  share ≥ 5% within trace) marks function as hot.

### Out of scope
- Capturing profile data inside the extractor (capture is a Mac /
  Android dev-side workflow; extractor only ingests files).
- Cross-language CPU attribution (samples that hit Swift / C++ /
  Obj-C bridges keep their native attribution; multi-frame
  attribution deferred).
- Battery / energy profiling.
- Network / disk I/O profiling — that's #30 Performance Pattern's
  remit.

## 3. Detection / ingest strategy

| Surface | Source | Method |
|---|---|---|
| iOS Time Profiler | xctrace export `.json` | parse via Sourcegraph xctrace JSON schema |
| Android CPU profile | Perfetto trace | parse via Perfetto SDK / `traceconv` |
| Android sampling | simpleperf `.data` | parse via simpleperf `report-sample --proto` |
| Symbol resolution | Phase 1 symbol-index `:Function` nodes | match `qualified_name` (post-symbol-index merge of trace samples) |

### Confidence
`heuristic` per research inventory — sample-based attribution
inherits sampling noise. Per-finding `confidence` field with
`certain` for samples ≥1000, `heuristic` for fewer.

## 4. Schema impact

```cypher
(:HotPathSample {
  project_id, run_id,
  trace_id: string,           // identifies the input trace file
  qualified_name: string,     // matches :Function/:Symbol
  cpu_samples: int,
  wall_ms: int,
  total_samples_in_trace: int,
  source_format: string       // "instruments" | "perfetto" | "simpleperf"
})

(:HotPathSummary {
  project_id, run_id, trace_id,
  total_cpu_samples: int,
  total_wall_ms: int,
  hot_function_count: int,    // count of :HotPathSample with cpu_share >= threshold
  threshold_cpu_share: float  // configurable, default 0.05
})

// Enrich existing :Function nodes (idempotent)
SET f.cpu_share = sample_cpu / total_cpu,
    f.wall_share = sample_wall / total_wall,
    f.is_hot_path = (cpu_share >= threshold)
```

Indices:
- `INDEX :HotPathSample(project_id, qualified_name)`.
- `INDEX :HotPathSummary(project_id, trace_id)`.

## 5. `audit_contract()`

```python
def audit_contract(self) -> AuditContract:
    return AuditContract(
        query="""
            MATCH (s:HotPathSample {project: $project})
            WHERE s.cpu_samples * 1.0 / s.total_samples_in_trace >= 0.05
            RETURN s ORDER BY s.cpu_samples DESC LIMIT 25
        """,
        response_model=HotPathAuditList,
        template_path=Path("audit/templates/hot_path_profiler.md"),
        severity_mapper=lambda s: "high" if s.cpu_share >= 0.20 else "medium" if s.cpu_share >= 0.10 else "low",
    )
```

## 6. Initial rule set / detector list (≤4 rules)

1. **`hot.cpu_share`** — function contributes ≥ threshold (default 5%)
   of CPU samples in the trace.
2. **`hot.wall_block`** — function blocks the main / UI thread for
   ≥ N ms (default 100ms; flagged "high" if on UI thread).
3. **`hot.crypto_in_critical_path`** — `:Function` whose
   `qualified_name` matches `*Crypto*|*Sign*|*Decrypt*|*Address*` AND
   `is_hot_path=true` — heuristic flag indicating crypto on UI/launch
   path (anti-pattern for some apps; informational for others).
4. **`hot.boot_path_amplifier`** — function called during app-launch
   trace contributing ≥ 2% of cold-start time.

## 7. Decision points

| ID | Question | Default | Impact |
|----|----------|---------|--------|
| **HP-D1** | Mac-only first (Instruments only) or Mac+Android Day-1? | both Day-1 | Mac-only halves smoke + skips UW-Android |
| **HP-D2** | Hot-path threshold default | 5% CPU share | lower = more findings (noisier); higher = miss medium hot spots |
| **HP-D3** | Trace input format — file path or content blob? | file path under `/repos/<slug>/profiles/<trace>` | content blob = self-contained but fat MCP payload |
| **HP-D4** | Trigger inside extractor or external profile-capture step? | external (Mac/Android dev runs Instruments / Perfetto, commits trace under `profiles/`) | inside-extractor = brittle (needs UI bring-up) |
| **HP-D5** | xcodetracemcp MCP integration v1 or follow-up? | follow-up (own slice if needed) | v1 = adds external MCP dep, complicates Docker setup |

## 8. Test plan

- **Unit per parser**: synthetic small trace files (Instruments JSON,
  Perfetto pftrace) → assert `:HotPathSample` rows match expected.
- **Integration**: testcontainers Neo4j + small fixture trace +
  pre-seeded `:Function` nodes → assert `:HotPathSample` rows
  reference `:Function` correctly + `:Function` properties enriched.
- **Smoke**: a real Instruments-captured trace from `tronkit-swift`
  unit-test run → operator + BlockchainEngineer review top-5 hot
  paths for plausibility.

### Profile-data fixtures (extractor blocker)

Before merge, the team needs **at least one Instruments + one
Perfetto fixture** committed under
`tests/extractors/fixtures/hot-path-fixture/profiles/`. Generating
fixtures requires a Mac (Xcode Instruments) + Android dev box
(Perfetto / simpleperf). This is an out-of-extractor manual step
documented in the runbook.

## 9. Risks

- **R1**: trace formats evolve / version-skew. Mitigation: pin
  parser libs in `pyproject.toml`; version-check fixture per CI run.
- **R2**: symbol-name mismatch — Instruments mangled names vs SCIP
  qualified names. Mitigation: per-format demangler step before
  match; log mismatches as `:HotPathSampleUnresolved`.
- **R3**: trace files are huge (100MB+). Mitigation: stream-parse;
  per-batch insert; abort if > 500MB.
- **R4**: capture variability — same workload runs different times
  produce different hot paths. Mitigation: average across N runs
  (out-of-extractor); each `:HotPathSample` cites its `trace_id`.
- **R5**: xctrace export schema is undocumented in places.
  Mitigation: smoke-test against multiple Xcode versions; pin
  Xcode-tested set in runbook.

## 10. Out of scope

- Auto-fix / refactor suggestions.
- Live profiling daemon (extractor is batch-only).
- Battery / power profiling.
- Network I/O profiling (#30).

## 11. Cross-references

- Original research: `docs/research/extractor-library/report.md` §2.5
  row #17.
- Roadmap: `docs/roadmap-archive.md` §2.5 #17.
- E6 prereq: `2026-05-07-cx-team-hire-blockchain-security-pyorch_*.md`.
- Audit-V1 integration: feeds §3 Quality of report.
- xcodetracemcp follow-up: HP-D5; tracked as separate slice if pursued.
- Companion: `2026-05-07-hot-path-profiler-extractor_plan.md`.
