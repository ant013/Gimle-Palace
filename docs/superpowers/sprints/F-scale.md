# Sprint S5 (F) — Scale to all 41 HS Kits + uw-ios-app

> **Rev2** (2026-05-06): padded wall-time to 3 weeks (OPUS-MEDIUM-1).
> Deferred uw-ios-app deep-dive to concrete sub-slices after S4
> retrospective (CR-MED-5). Added 1-week per-Kit debugging budget.

**Goal**: take the v1 product proven on 2 Kits (S4) and run it across
the full UW iOS bundle (41 first-party HS Kits + uw-ios-app main
app). Result: 42 audit reports, one bundle-wide audit, and an
operator-ready demo of "we audit the whole UW iOS ecosystem
end-to-end".

**Wall-time**: ~3 weeks calendar (rev2 — padded from ~2 weeks).
Breakdown:
- Week 1: batch ingest infrastructure + first 20 Kits.
- Week 2: remaining 21 Kits + triage failures + re-runs.
- Week 3: uw-ios-app + bundle audit + per-Kit debugging buffer.

**Why 3 weeks, not 2** (OPUS-MEDIUM-1): Even with automation (S3), each Kit
needs ~30 min pipeline time (sequential extractors on single Neo4j).
Real throughput ≈ 8-10 Kits/day. 42 Kits = 4-5 business days execution alone.
GIM-182 precedent: multi-repo SPM ingest surfaced per-Kit quirks taking 1-2
days each to resolve. 1 week debugging buffer is mandatory.

**Driver**: only this sprint converts v1 from "works on 2 Kits" to
"covers the product target". Operator's stated goal includes
"остальные либы + wallet-ios" — this sprint delivers that.

**Definition of Done**:
1. All 41 HS Kits + uw-ios-app have successful `:IngestRun`
   records for all v1 extractors (≥95% success rate = 40/42 minimum).
2. `palace.code.find_version_skew(bundle="uw-ios")` returns
   meaningful cross-Kit drift.
3. `palace.code.find_owners(file_path=...)` works for any file in
   any of the 42 projects.
4. `palace.audit.run(bundle="uw-ios")` produces a bundle-wide audit.
5. Operator demo: pick 5 Kits at random, present their reports + bundle.
6. Inventory: `docs/audit-reports/uw-ios-bundle-2026-MM-DD.md`.

---

## Slices

### S5.1 — Batch ingest infrastructure

**Files**:
- `paperclips/scripts/ingest_all_uw_ios_kits.sh`
- `paperclips/scripts/scip_emit_all_uw_ios_kits.sh`

**Scope**: wrapper around `ingest_swift_kit.sh` that reads the canonical
member list from `uw-ios-bundle-manifest.json` (exists per GIM-182).

**Resilience**: failure of one Kit does NOT abort the batch. Failed
Kits → `~/.palace/audit-v1/failed-kits.json` for operator triage.

**Decision points**:
- D5-1: parallel vs sequential ingest. Default: sequential
  (avoids overwhelming Neo4j). Parallel is stretch goal.
- D5-2: dev Mac SCIP emit batch too? Default: yes.

**Size**: ~2-3 hours.

---

### S5.2 — Run the batch ingest

1. Dev Mac: `bash scip_emit_all_uw_ios_kits.sh`. Capture failures.
2. iMac: `bash ingest_all_uw_ios_kits.sh`. Capture failures.
3. Triage failures one-by-one. Expected failure categories:
   - Unusual SwiftPM layout → fix scip_emit script.
   - Obj-C headers → skip or defer.
   - Malformed `Package.resolved` → fix parser.
4. Re-run until ≥95% success (40/42 minimum).

**Size**: ~3-5 days (mostly wall-time waiting + triage).

---

### S5.3 — Bundle-wide audit

1. `palace.audit.run(bundle="uw-ios", depth="full")`.
2. Verify cross-Kit sections: version skew, contract drift,
   ownership concentration.
3. Aggregate findings: top-10 hotspots, top-10 ownership
   concentrations, top-10 supply-chain issues across all 42 projects.
4. Operator review.

**Size**: ~1 day.

---

### S5.4 — uw-ios-app analysis (rev2: concrete scope, not open-ended)

**Rev2 change** (CR-MED-5): Original was "open-ended depending on what we hit."
Now scoped to concrete steps:

1. Run `ingest_swift_kit.sh uw-ios-app` — if all extractors succeed, done.
2. If hotspot/public_api_surface timeout on the larger graph:
   - Tune `PALACE_*_TIMEOUT` env vars.
   - If structural, add `--depth=quick` mode that caps per-extractor scan
     to first N files.
3. If still failing after timeout tuning, defer uw-ios-app full audit to
   v1.1. Ship S5 with 41 Kits only.

**Size**: ~1-2 days.
**Success criteria**: uw-ios-app audit report exists OR explicit deferral
with documented blockers.

---

### S5.5 — Operator demo + handoff

**Files**:
- `docs/audit-reports/uw-ios-bundle-2026-MM-DD.md`

**Scope**: operator-facing documentation: reports, how to re-run,
post-v1 backlog.

This artifact closes audit-v1 and opens "post-v1 intake protocol".

**Size**: ~0.5 day.

---

## Risks

| Risk | Mitigation |
|------|------------|
| Kit fails ingest requiring extractor surgery | S4 smoke catches early; week 3 buffer for patches |
| uw-ios-app graph overwhelms Neo4j | Timeout tuning; defer to v1.1 if structural |
| Systematic false-positives in crypto rules | Iterate YAML rules in S5; cheap to refine |
| Bundle `find_version_skew` noise | Tune `min_severity` default; `top_n` clamping |
| More than 2 Kits fail permanently | Accept 95% threshold; document failures for v1.1 |

## Cross-references

- Overview: `audit-v1-overview.md`
- All preceding sprints
- Post-v1 intake: `docs/roadmap.md` §"Post-v1 slice intake protocol"
