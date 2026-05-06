# Audit-V1 — first product release: overview

**Status**: pre-S1 (Board+Claude session 2026-05-06 produced this plan).
**Driver**: operator goal — first complete audit run on `tronkit-swift`,
then `bitcoinkit-swift`, then remaining HS Kits + `wallet-ios`. After
v1, every additional extractor is a tiny isolated slice that just
enriches MCP without touching the audit workflow.

This file is the rendered version of the strategic report from the
Board+Claude session. The roadmap (`docs/roadmap.md`) carries the
sprint table and decision points; this file carries the *justification*
and *tradeoff log* so future readers understand the why.

---

## 1. What we ship in v1

A single MCP composite tool: `palace.audit.run(project: str | None = None, bundle: str | None = None, depth: str = "full") → AuditReport`.

`AuditReport` is a structured markdown document with these sections:

1. **Executive summary** — top-N findings, severity-graded, ≤500 words.
2. **Architecture** — layer model, module boundaries, public API surface,
   cross-module contract drift (from GIM-190/192).
3. **Quality** — hotspots (GIM-195), dead symbols (GIM-193), code-smell
   counters (Phase B if/when added; for v1 marked "blind spot — pending
   #34").
4. **Security** — error-handling smells (Phase B blind spot — pending
   #7), crypto-domain findings (S2 #40), known taint patterns (LLM
   blind spot — pending #35).
5. **Dependencies** — external surface (GIM-191), version skew
   (GIM-218), single-source picks.
6. **Ownership** — file-level owners (GIM-216), bus-factor=1 files,
   recently-active vs. dormant authors.
7. **Crypto-domain (Kits with `pkg:github/horizontalsystems/*` Swift
   crypto-related deps)** — address validation, decimal handling,
   checksum invariants (S2 #40).
8. **Cross-Kit (bundle mode)** — version skew, public-API contract
   drift, ownership concentration across the bundle.
9. **Blind spots** — explicit list of "we did NOT analyse X because
   extractor Y is not yet merged". Honest gap-list.
10. **Provenance** — list of `:IngestRun` records that fed this report,
    with timestamps and `extractor_name` per run.

The format is markdown so operators can paste into PR descriptions,
runbooks, audit logs. JSON export is post-v1 (AV1-D1).

## 2. The team that produces it

Per AV1-D2 (default = "reuse + 1 new + Synthesizer"):

| Agent | Role | What it queries / contributes |
|-------|------|--------------------------------|
| **OpusArchitectReviewer** | Architecture findings | `palace.code.find_references`, public API surface, cross-module contract |
| **SecurityAuditor** | Security findings | `palace.code.find_owners`, error-handling counters, crypto-domain output (S2) |
| **BlockchainEngineer** | Crypto-Kit specifics | `palace.code.find_owners`, crypto-domain output (S2), purl scopes |
| **Auditor** (NEW role, S1) | Quality + Dependencies + Historical synthesised view | `palace.code.find_hotspots`, `palace.code.find_owners`, `palace.code.find_version_skew`, `:IngestRun` provenance |
| **AuditSynthesizer** (NEW role, S1) | Final markdown report | Reads all 4 agents' outputs, applies template, renders markdown |

Three reuses + 1 new role + 1 synthesizer. No specialised
Quality/Dependency/Historical roles for v1 (operator can split the
single `Auditor` later if needed). Two new role files to author:
`paperclips/roles/auditor.md` + `paperclips/roles/audit-synthesizer.md`.

## 3. Why this scope is the fastest viable v1

We rejected three larger v1 scopes:

### Rejected — "full audit team with 7 specialised roles"
Adds 5 new role files, 5 new agent UUIDs, 5 sets of role-specific
prompts. Doubles the synthesis surface. Operator can split the single
`Auditor` role into Quality / Dependency / Historical / etc later if
S4 smoke surfaces real differentiation pressure. Until then YAGNI.

### Rejected — "full Phase B extractor backlog before v1"
Phase B (#1 Architecture Layer + #2 Symbol Duplication + #34 Code
Smell + #7 Error Handling) is ~3 weeks of Board+paperclip work each.
Total: ~12 weeks for v1 — unacceptable. v1 ships with #40 only
(crypto-Kit relevance is highest among the 5). Other 4 explicitly
listed as "blind spot" in the report; operator sees the gap and
prioritises them in S6+ based on what S4 smoke surfaced.

### Rejected — "wait for LLM infra before v1"
LLM-blocked extractors (#11 Decision History, #26 Bug-Archaeology,
#35 Taint, #43 PR Review) are valuable but require Ollama
deployment + cost monitoring + agent-llm cost budgeting — that's
a separate slice not yet specced. Decision AV1-D4: defer. v1 ships
with the LLM-blocked sections explicitly noted as blind spots.

## 4. The "post-v1 paved path" promise

The crucial design constraint: **after v1 lands, adding extractor X
must NOT require any change to the audit workflow, agents, or report
template**.

This is enforced by:

- **Synthesizer template enumerates extractor outputs from the graph**,
  not from a hardcoded list. New `:IngestRun{extractor_name='X'}`
  appears → synthesizer adds a section to the report automatically.
- **Section template per extractor lives WITH the extractor** in
  `extractors/<name>/audit_section_template.md`. The synthesizer
  reads it. New extractor = new template file.
- **Per-domain agents query MCP via composite tools** (`palace.code.*`),
  not via raw Cypher. New extractor that adds a new entity type ships
  with a matching composite tool; agents pick it up via tool
  introspection.
- **Audit report severity ranks come from extractor output**, not
  from agent judgment. Each extractor labels its own findings
  (`hotspot` already does this via score; `crypto_domain_model` will
  too). Synthesizer aggregates without re-judging.

If a future extractor needs a new agent role (e.g., LLM-bearing
agent for #26 Bug-Archaeology that needs reasoning over commit
messages), that's a v2 extension. v1's promise stops at "non-LLM
extractors plug in unchanged".

## 5. Pre-S1 checklist

Before starting S1 brainstorm, operator should confirm:

- [ ] AV1-D1 — markdown only? (default yes)
- [ ] AV1-D2 — reuse + 1 new Auditor + Synthesizer? (default yes)
- [ ] AV1-D3 — manual trigger only for v1? (default yes)
- [ ] AV1-D4 — LLM-blocked extractors deferred to S6+? (default yes)
- [ ] AV1-D5 — Track A/B SCIP emit pattern preserved? (default yes)
- [ ] **GIM-216** + **GIM-218** kept on track to land before S4 (smoke).
  These two are not blocking S1/S2/S3 starts but are blocking the
  smoke (S4) success criteria for "Ownership" and "Dependencies"
  report sections.

## 6. What this overview is NOT

- Not a TDD plan — plans live in
  `docs/superpowers/plans/<YYYY-MM-DD>-<sprint-id>-<slug>.md` per
  slice within each sprint.
- Not a spec — specs live in
  `docs/superpowers/specs/<YYYY-MM-DD>-GIM-NN-<slug>.md` per slice
  within each sprint.
- Not the trigger for any paperclip work — it's the agreement document
  the operator reads before approving the Audit-V1 plan.

## 7. Cross-references

- High-level table + decision points: `docs/roadmap.md` §"Audit-V1"
- S1 (Audit Orchestration) detail: `D-audit-orchestration.md`
- S2 (Crypto Domain Extractor) detail: `B-audit-extractors.md`
- S3 (Ingestion Automation) detail: `C-ingestion-automation.md`
- S4 (Smoke) detail: `E-smoke.md`
- S5 (Scale) detail: `F-scale.md`
- Memory queue updated: `project_next_claude_extractor_queue.md`
- Existing in-flight: GIM-216 (`feature/GIM-NN-code-ownership-extractor`),
  GIM-218 (`feature/GIM-NN-cross-repo-version-skew`)
