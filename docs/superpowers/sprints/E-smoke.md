# Sprint S4 (E) — Smoke run on tronKit-swift + bitcoinKit-swift

**Goal**: validate end-to-end that v1 product works on real crypto-Kit
source. Two Kits: tronKit-swift (first — simpler), bitcoinKit-swift
(second — generalisation check).

**Wall-time**: ~1 week calendar (no new code; runbook execution +
report critique).

**Driver**: this is THE moment the "first product release" exists.
Everything before is plumbing; this is the first audit report a real
human can read and act on.

**Definition of Done**:
1. `palace.audit.run(project="tronkit-swift")` produces a complete
   markdown audit report.
2. Report passes operator review: findings are credible, severity
   ranks make sense, sections cover all expected domains, blind
   spots disclosed honestly.
3. Same for `bitcoinkit-swift`.
4. Operator-facing demo doc: `docs/audit-reports/2026-MM-DD-tronkit-swift.md`
   and `docs/audit-reports/2026-MM-DD-bitcoinkit-swift.md` (the
   actual audit reports become artifacts).
5. List of v1 product gaps captured per the report's blind-spots
   section, prioritised for S6+ intake.

**Dependencies**:
- S1 (D) merged: workflow + agents + composite tool live on iMac.
- S2 (B-min) merged: `crypto_domain_model` extractor in registry.
- S3 (C) merged: ingestion automation works.
- GIM-216 + GIM-218 merged: ownership + skew sections populated.

---

## Slices

### S4.1 — tronKit-swift first audit

1. Dev Mac: `bash scip_emit_swift_kit.sh tronkit-swift`.
2. iMac: `bash ingest_swift_kit.sh tronkit-swift --bundle=uw-ios`.
   Verify all extractor `:IngestRun` records show `success`.
3. iMac: `palace.audit.run(project="tronkit-swift")` — produces
   markdown report.
4. Operator reviews markdown:
   - Are top-N hotspots actually hot? (manually correlate with git
     log).
   - Are dead symbols actually dead? (spot-check 2-3).
   - Are crypto-domain findings legitimate? (BlockchainEngineer
     review of each high-severity item).
   - Are ownership claims accurate? (sanity-check vs git blame on
     1 file).
   - Does the report have ALL expected sections per `D-audit-orchestration.md`
     §S1.1 deliverable spec?
5. Capture deltas: false-positives, missed findings, format issues.
6. File these as v1 product backlog (small followup PRs, not v2
   blockers).

### S4.2 — bitcoinKit-swift second audit

Same flow as S4.1. The point is to verify v1 generalises beyond
the first Kit. Differences expected (different package layout,
different Swift version target, different crypto patterns) — they
should NOT require workflow changes; they may surface
extractor-side gaps.

### S4.3 — Bundle smoke

After both Kit audits succeed individually:

1. iMac: `palace.audit.run(bundle="uw-ios", depth="full")`.
2. Verify cross-Kit sections appear:
   - Cross-repo version skew (from GIM-218).
   - Cross-module contract drift (from GIM-192).
   - Bundle-wide ownership concentration.
3. Operator review.

If `uw-ios` bundle has only 2 members at this point (tronKit +
bitcoinKit), cross-Kit signal will be sparse. Smoke validates the
SHAPE of the cross-Kit report; the quality signal comes after S5
when the full 41-Kit bundle is populated.

### S4.4 — Smoke retrospective + gap-list

**Files**:
- `docs/superpowers/sprints/E-smoke-retrospective.md` (output of
  this slice)

**Scope**: write a retrospective document covering:
- What worked.
- What broke.
- What's the v1.1 backlog (small fixes).
- What's the v2 backlog (bigger gaps — extractor adds, role
  splits, etc).
- Should `Auditor` (single multi-domain role) split into
  Quality/Dependency/Historical? Operator decides per smoke
  evidence.
- Is `crypto_domain_model` rule set sufficient, or are there
  obvious gaps that need rule additions?

This retrospective drives S6+ slice prioritisation.

---

## Decision points (post-smoke)

| ID | Question | Default outcome |
|----|----------|------------------|
| AV1-S4-D1 | Auditor role — keep single multi-domain or split? | Decided after smoke evidence; default keep single |
| AV1-S4-D2 | crypto_domain_model rule expansion priority | Decided per smoke false-negatives; default add 5 more rules in v1.1 |
| AV1-S4-D3 | Extractor backlog priority (#1 vs #34 vs #7 vs LLM infra)? | Decided per smoke blind-spot complaints; default operator picks one |

## Cross-references

- Overview: `audit-v1-overview.md`
- Sprint dependencies: `D-audit-orchestration.md`, `B-audit-extractors.md`, `C-ingestion-automation.md`
- Scale-out: `F-scale.md`
