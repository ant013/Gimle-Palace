# S4.1 Smoke Run — tron-kit Audit Report

> **Issue**: GIM-277
> **Sprint**: S4.1 (E-smoke.md rev3)
> **Grounded on**: `origin/develop` at `4992cfa`
> **Parent spec**: `docs/superpowers/sprints/E-smoke.md` (rev3, 2026-05-07)
> **Audit-V1 overview**: `docs/superpowers/sprints/audit-v1-overview.md`

## Goal

First real audit report on a single Swift Kit (`tron-kit`). End-to-end
validation that v1 product works against real crypto-Kit source.

## Kit slug

Operational slug: **`tron-kit`** (per `uw-ios-bundle-manifest.json`).
Spec text says `tronkit-swift` — aspirational; `tron-kit` is what the
registry and bundle use.

## Pre-existing prerequisites (all merged)

| Sprint | Issue | Merge SHA |
|--------|-------|-----------|
| S0 | GIM-228 | `0a02ade` |
| S1 | GIM-233 | `c405082` |
| S2.1 | GIM-239 | `700a17a` |
| S2.2 | GIM-243 | `42e2894` |
| S2.3 | GIM-257 | `430f58e` |
| S3 | GIM-262 | `9dddb08` |
| code_ownership | GIM-216 | `2d6e6c1` |
| version-skew | GIM-218 | `603c840` |

19 extractors live in registry. `palace.audit.run` MCP tool at
`services/palace-mcp/src/palace_mcp/audit/run.py`.

## Acceptance criteria (from E-smoke.md rev3)

Every threshold below must pass before Phase 4.2 close:

| # | Criterion | Threshold |
|---|-----------|-----------|
| 1 | Sections populated | ≥7 of 10 sections contain findings or explicit "no findings" (not blank) |
| 2 | Non-informational findings | ≥3 findings with severity ≥ `low` |
| 3 | §1 Architecture content | Populated module DAG + ≥0 ArchViolation entries OR explicit "no violations — rules clean" with cited rule set |
| 4 | §4 Security error-handling content | Populated `:CatchSite` aggregate + ≥1 ErrorFinding OR explicit "no critical-path swallowed catches" with file count cited |
| 5 | False-positive rate | ≤2 of top-5 flagged items per section (§1, §4, §7) are false positives — manual review by operator + BlockchainEngineer |
| 6 | Blind spots declared | All missing extractors listed in §9 with rationale (#1, #7 NOT here in rev3) |
| 7 | Provenance complete | Every populated section traces to an `:IngestRun` with run_id |
| 8 | Executive summary | Present, ≤500 words, top-3 findings |

## MacBook gate — explicit pause (Phase 2 hard block)

iMac (Intel + macOS 13) CANNOT build modern iOS — no modern Xcode, no
`scip-emit-swift` capability. Real-source `.scip` for any HS Swift Kit
has never been generated on iMac.

**PythonEngineer Phase 2 sequence:**

1. iMac: `cd /Users/Shared/Ios/Gimle-Palace && docker compose --profile review up -d` — start palace-mcp + neo4j. Verify via `docker compose ps`.
2. iMac: `palace.memory.bundle_members(bundle="uw-ios")` — verify `tron-kit` is listed.
3. iMac: confirm `/Users/Shared/Ios/scip-inputs/tron-kit.scip` does NOT exist yet (or stale >24h).
4. **HARD BLOCK**: PATCH `status=blocked` + comment exactly:
   > **MacBook gate**: need real-source `.scip` for tron-kit. Operator: please run `bash paperclips/scripts/scip_emit_swift_kit.sh tron-kit` on a dev Mac with modern Xcode + cloned `tronkit-swift` repo, then `scp <output>.scip imac-ssh.ant013.work:/Users/Shared/Ios/scip-inputs/tron-kit.scip`. PATCH this issue back to me (PythonEngineer, `127068ee-b564-4b37-9370-616c81c63f35`) with `status=in_progress` once file is delivered.
5. Operator delivers file + reassigns. PE wakes up.
6. iMac: verify `/Users/Shared/Ios/scip-inputs/tron-kit.scip` exists and is recent (`stat -f "%m" <file>` within 24h).
7. iMac: `bash paperclips/scripts/ingest_swift_kit.sh tron-kit --bundle=uw-ios`. Read all extractor `:IngestRun` records; every relevant extractor must report `success`. Capture run_ids.
8. iMac: call `palace.audit.run(project="tron-kit")` via MCP. Capture full markdown report.
9. iMac: save markdown to `docs/audit-reports/2026-05-12-tron-kit.md` on feature branch.
10. iMac: ALSO run `bash paperclips/scripts/audit-workflow-launcher.sh tron-kit` — async multi-agent flavor. Capture child-issue identifiers + final reports.
11. Commit + open PR to develop.

## Audit-mode prompt validation (from E-smoke.md rev2)

During S4.1, verify that the 3 reused agents (with S0.3 audit-mode
prompts) can consume fetcher output and produce structured sub-reports:

- Each agent receives real fetcher data (not synthetic fixtures).
- Each agent produces a sub-report following the output format, cites
  only extractor data (no invented findings), uses severity grading rules.
- If an agent's output is unusable, flag the role prompt for revision
  before S4.2.

## Expected output

- `docs/audit-reports/2026-05-12-tron-kit.md` — sync report
- Async multi-agent report via `audit-workflow-launcher.sh`
- Retrospective deltas captured as v1.1 backlog items

## Implementer chain

7-phase standard Gimle: CTO → CR → PE → CR → Opus → QA → CTO merge.
Phase 3.2 (Opus adversarial review) reviews the audit REPORT quality,
not code — do NOT skip.

## Out of scope

- S4.2 bitcoin-core (separate issue after S4.1 closes)
- S4.3 bundle smoke (after S4.1 + S4.2)
- S4.4 retrospective + decision points D1-D4 (after S4.3)
- Track B operationalisation for OTHER Kits
