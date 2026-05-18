# Sprint S4 (E) — Smoke run on tronKit-swift + bitcoinKit-swift

> **Rev3** (2026-05-07): acceptance criteria extended to require populated
> Architecture Layer (#1) and Error Handling (#7) sections — no longer §9
> blind spots. AV1-D7 flipped per operator decision GIM-219.
>
> **Rev2** (2026-05-06): adds measurable acceptance criteria (CR-MED-4).
> Adds GIM-218 contingency plan. Adds audit-mode prompt validation step.

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
2. Report passes acceptance criteria (see below).
3. Same for `bitcoinkit-swift`.
4. Operator-facing artifacts: `docs/audit-reports/2026-MM-DD-tronkit-swift.md`
   and `docs/audit-reports/2026-MM-DD-bitcoinkit-swift.md`.
5. Gap-list for S6+ captured in retrospective.

**Dependencies**:
- S0 (Foundation prerequisites) merged.
- S1 (D) merged: workflow + agents + composite tool live on iMac.
- **S2.1 (B-min) merged**: `crypto_domain_model` extractor in registry.
- **S2.2 (B+1) merged**: `arch_layer` extractor in registry (rev3).
- **S2.3 (B+7) merged**: `error_handling_policy` extractor in registry (rev3).
- S3 (C) merged: ingestion automation works.
- GIM-216 merged (PR #105, expected ~1 week).
- GIM-218: see contingency below.

---

## GIM-218 contingency (rev2, CTO-CRITICAL-3)

GIM-218 (cross_repo_version_skew) has zero progress — no branch, no spec,
no assignee. Realistic minimum: 2-3 weeks from first touch to merge.

**Decision (per rev2 checklist AV1-D7)**: If GIM-218 is not started within
1 week of rev2 approval:
- **Demote** version-skew from S4 required section to S4 blind spot.
- S4 acceptance criteria below adjust: "Dependencies" section ships without
  version skew; report explicitly states "blind spot — GIM-218 pending".
- S5 bundle-mode cross-Kit skew also degrades to blind spot.
- GIM-218 becomes a post-v1 S6+ slice.

This avoids blocking the entire v1 on a single unstarted dependency.

---

## Acceptance criteria (rev2 — CR-MED-4)

S4 is not "run it and see". Each audit report must pass these **measurable
thresholds** to be accepted:

### Per-Kit report acceptance

| Criterion | Threshold | How to measure |
|-----------|-----------|----------------|
| Sections populated | ≥7 of 10 sections contain findings or explicit "no findings" (not blank) — rev3 raised from ≥5 because §1 Arch and §4 Security are now required | Count non-empty sections |
| Non-informational findings | ≥3 findings with severity ≥ `low` | Count findings in report |
| **§1 Architecture content (rev3)** | Populated module DAG + ≥0 ArchViolation entries OR explicit "no violations — rules clean" with cited rule set | Verify `:ArchViolation` query + `:Module` count > 1 |
| **§4 Security error-handling content (rev3)** | Populated `:CatchSite` aggregate + ≥1 ErrorFinding OR explicit "no critical-path swallowed catches" with file count cited | Verify `:CatchSite` count > 0 + ErrorFinding query |
| False-positive rate (top-5 across §1, §4, §7) | ≤2 of top-5 flagged items per section are false-positives | Manual review by operator + BlockchainEngineer |
| Blind spots declared | All missing extractors listed in §9 with rationale (#1, #7 NOT here in rev3) | Verify against registry diff |
| Provenance complete | Every populated section traces to an `:IngestRun` with run_id | Verify run_ids exist in Neo4j |
| Executive summary | Present, ≤500 words, covers top-3 findings | Word count + content check |

### Bundle report acceptance (S4.3)

| Criterion | Threshold |
|-----------|-----------|
| Cross-Kit sections present | At least 1 of: version skew, contract drift, ownership concentration |
| Bundle members listed | Both Kits appear in report header |

### Audit-mode prompt validation (rev2)

During S4.1, verify that the 3 reused agents (with S0.3 audit-mode prompts)
can consume fetcher output and produce structured sub-reports:
- Each agent receives real fetcher data (not synthetic fixtures).
- Each agent produces a sub-report that: follows the output format, cites
  only extractor data (no invented findings), uses severity grading rules.
- If an agent's output is unusable, flag the role prompt for revision before
  S4.2.

---

## Slices

### S4.1 — tronKit-swift first audit

1. Dev Mac: `bash scip_emit_swift_kit.sh tronkit-swift`.
2. iMac: `bash ingest_swift_kit.sh tronkit-swift --bundle=uw-ios`.
   Verify all extractor `:IngestRun` records show `success`.
3. iMac: `palace.audit.run(project="tronkit-swift")` — sync report.
4. iMac: `bash audit-workflow-launcher.sh tronkit-swift` — async
   multi-agent report (validates child-issue dispatch).
5. Operator reviews both reports against acceptance criteria above.
6. Validate audit-mode prompts: review each agent's sub-report
   for format compliance and finding accuracy.
7. Capture deltas: false-positives, missed findings, format issues.
8. File small followups as v1.1 backlog.

### S4.2 — bitcoinKit-swift second audit

Same flow as S4.1. Validates v1 generalises beyond first Kit.
Differences expected — should NOT require workflow changes.

### S4.3 — Bundle smoke

After both Kit audits succeed individually:

1. `palace.audit.run(bundle="uw-ios", depth="full")`.
2. Verify cross-Kit sections appear (per bundle acceptance criteria).
3. Operator review.

With only 2 members, cross-Kit signal will be sparse. Validates the
SHAPE of the cross-Kit report; quality signal comes after S5.

### S4.4 — Smoke retrospective + gap-list

**Files**:
- `docs/superpowers/sprints/E-smoke-retrospective.md`

**Scope**:
- What worked / what broke.
- v1.1 backlog (small fixes).
- v2 backlog (bigger gaps).
- Auditor role split decision (AV1-S4-D1).
- Crypto-domain rule expansion assessment (AV1-S4-D2).
- Token budget measurement: actual tokens consumed per agent per
  Kit audit vs. AV1-D6 budget. Adjust if over.

---

## Decision points (post-smoke)

| ID | Question | Default outcome |
|----|----------|------------------|
| AV1-S4-D1 | Auditor role — keep single or split? | Decided after smoke evidence |
| AV1-S4-D2 | crypto_domain_model rule expansion | Decided per false-negatives |
| AV1-S4-D3 | Extractor backlog priority | Decided per blind-spot complaints |
| AV1-S4-D4 | Token budget revision (rev2) | Measured vs. AV1-D6 target |

## Cross-references

- Overview: `audit-v1-overview.md`
- Sprint dependencies: `D-audit-orchestration.md`, `B-audit-extractors.md`, `C-ingestion-automation.md`
- Scale-out: `F-scale.md`
