# Sprint S5 (F) — Scale to all 41 HS Kits + uw-ios-app

**Goal**: take the v1 product proven on 2 Kits (S4) and run it across
the full UW iOS bundle (41 first-party HS Kits + uw-ios-app main
app). Result: 42 audit reports, one bundle-wide audit, and an
operator-ready demo of "we audit the whole UW iOS ecosystem
end-to-end".

**Wall-time**: ~2 weeks calendar (mostly operator-driven manual
ingest cycles + per-Kit triage; small Kits go fast, the main app
will need its own analysis pass).

**Driver**: only this sprint converts v1 from "works on 2 Kits" to
"covers the product target". Operator's stated goal includes
"остальные либы + wallet-ios" — this sprint delivers that.

**Definition of Done**:
1. All 41 HS Kits + uw-ios-app have successful `:IngestRun`
   records for all v1 extractors.
2. `palace.code.find_version_skew(bundle="uw-ios")` returns
   meaningful cross-Kit drift.
3. `palace.code.find_owners(file_path=...)` works for any file in
   any of the 42 projects.
4. `palace.audit.run(bundle="uw-ios")` produces a bundle-wide
   audit report.
5. Operator demo: pick 5 Kits at random, present their reports +
   the bundle report.
6. Inventory document: `docs/audit-reports/uw-ios-bundle-2026-MM-DD.md`
   (master list of all 42 reports + bundle summary).

---

## Slices

### S5.1 — Batch ingest infrastructure

**Files**:
- `paperclips/scripts/ingest_all_uw_ios_kits.sh`

**Scope**: wrapper around `ingest_swift_kit.sh` that reads the canonical
member list from
`services/palace-mcp/scripts/uw-ios-bundle-manifest.json` (already
exists per GIM-182), iterates each, calls the per-Kit script,
aggregates a final summary.

**Resilience**: failure of one Kit does NOT abort the batch. Failed
Kits go into `~/.palace/audit-v1/failed-kits.json` with the error
message; operator triages individually.

**Decision points**:
- D5-1: parallel vs sequential ingest. Default: sequential
  (avoids overwhelming Neo4j / palace-mcp event loop). Parallel
  is a stretch goal if sequential is too slow.
- D5-2: dev Mac SCIP emit batch — `scip_emit_all_uw_ios_kits.sh`
  on the dev Mac too? Default: yes — same wrapper pattern.

---

### S5.2 — Run the batch ingest

1. Dev Mac: `bash scip_emit_all_uw_ios_kits.sh`. Wait. Capture failures.
2. iMac: `bash ingest_all_uw_ios_kits.sh`. Wait. Capture failures.
3. Triage failures one-by-one. Common expected failures:
   - Kit uses unusual SwiftPM layout — fix scip_emit script.
   - Kit has Obj-C headers not handled by current extractor —
     defer to followup.
   - Kit's `Package.resolved` is malformed — fix
     `dependency_surface` parser.
4. Re-run failed Kits until success rate ≥95% (40/42 at minimum).

---

### S5.3 — Bundle-wide audit

1. `palace.audit.run(bundle="uw-ios", depth="full")`.
2. Operator review. Cross-Kit version skew is the highlight:
   does it surface real drift?
3. Cross-module contract drift: do public API changes between
   Kit versions surface?
4. Aggregate findings: top-10 hotspots across all 42 projects;
   top-10 ownership concentrations; top-10 supply-chain issues.

---

### S5.4 — uw-ios-app deep-dive

The main wallet app is the largest project (orders of magnitude
more symbols than any single Kit). Likely needs its own perf-tuning
pass:
- Hotspot ingest may take longer (more files, more functions).
- Public API surface is huge.
- Code ownership graph is dense.

**Slices** (open-ended depending on what we hit):
- Tune extractor batch sizes if needed.
- Validate Cypher query plans on the bigger graph.
- Possibly add `uw-ios-app`-specific runbook quirks.

---

### S5.5 — Operator demo + handoff

**Files**:
- `docs/audit-reports/uw-ios-bundle-2026-MM-DD.md` — landing page
- 42 individual reports (or trimmed to 5 representative for the
  demo doc; full set available via `palace.audit.run` on demand).

**Scope**: operator-facing documentation that says
"audit-v1 works, here are the reports, here's how to re-run, here's
the post-v1 backlog of extractors / agent splits / format
improvements".

This is the artifact that closes audit-v1 and opens "post-v1
intake protocol" for ongoing work.

---

## Risks

| Risk | Mitigation |
|------|------------|
| Some Kit fails ingest in a way that requires extractor surgery | S4 smoke catches early; S5 budget allows for 1-2 extractor patches mid-flight |
| uw-ios-app graph overwhelms Neo4j (memory / query timeout) | Tune `PALACE_*_TIMEOUT` env vars; if structural, defer uw-ios-app to v1.1 with smaller-scope audit |
| Operator review reveals systematic false-positives in `crypto_domain_model` rules | Iterate rules in S5; rule pack is YAML; cheap to refine |
| Bundle-mode `find_version_skew` returns unmanageable noise | Tune `min_severity` default in operator's runbook commands; consider `top_n` clamping per ecosystem |

## Cross-references

- Overview: `audit-v1-overview.md`
- All preceding sprints
- Post-v1 intake protocol: `docs/roadmap.md` §"Post-v1 slice intake protocol"
