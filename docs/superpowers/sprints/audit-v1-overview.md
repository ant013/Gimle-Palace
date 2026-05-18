# Audit-V1 — first product release: overview

**Status**: pre-S1 (rev3 — operator flipped AV1-D7 → #1 + #7 included, envelope expanded 12w → 18w).
**Driver**: operator goal — first complete audit run on `tronkit-swift`,
then `bitcoinkit-swift`, then remaining HS Kits + `wallet-ios`. After
v1, every additional extractor is a tiny isolated slice that just
enriches MCP without touching the audit workflow.

This file is the rendered version of the strategic report from the
Board+Claude session. The roadmap (`docs/roadmap.md`) carries the
sprint table and decision points; this file carries the *justification*
and *tradeoff log* so future readers understand the why.

---

> ### Rev3 changelog (2026-05-07)
>
> Operator decision applied to GIM-219 after rev2 review:
>
> 1. **AV1-D7 flipped from "yes/blind-spot" to "no/included"** — Architecture
>    Layer Extractor (#1) and Error Handling Policy Extractor (#7) are now
>    in v1 scope, not deferred to S6+.
> 2. **Wall-time envelope expanded 12w → 18w** to absorb +6w (~3w each for #1
>    and #7, sequential on single Claude PE). Parallel S2.2 ‖ S2.3 collapses
>    back to ~14-15w if a 2nd Claude engineer is available.
> 3. **S2 split into S2.1 (#40), S2.2 (#1), S2.3 (#7)** — each its own
>    paperclip slice, all on Claude team per `roadmap.md` §2.1/§2.2 team
>    allocation.
> 4. **S4 acceptance criteria** extended: §1 Architecture and §4 Security
>    sections now require populated content from #1 / #7 (not "blind spot —
>    pending"). See `E-smoke.md` rev3.
> 5. **OPUS-LOW-1 closed entirely** — `roadmap.md` HTML-commented Phase 2-6
>    duplicate removed; canonical archive in `docs/roadmap-archive.md` only.
>
> Rationale: for a blockchain/security audit of WalletKit's, layer-violation
> detection (#1) and swallowed-error detection (#7) are foundational —
> swallowed crypto errors → potential lost funds; cross-module boundary
> breaks → security boundary breaches. Operator weighed +6w cost vs. these
> sections shipping as §9 disclaimers and chose full coverage.
>
> ### Rev2 changelog (2026-05-06)
>
> Synthesised from 3-reviewer audit of rev1 (`4deb538`):
> CTO (3C/6H/3M/1L), CodeReviewer (3C/6H/5M/2L), OpusArchitectReviewer (2C/3H/2M/1L).
>
> **CR factual corrections applied first:**
> - CR-CRITICAL-1 wrong: 7/10 cascade extractors exist in registry (not 0/10).
> - CR-CRITICAL-2 wrong: Bundle infra fully implemented in GIM-182 (`memory/bundle.py`, 5 MCP tools).
> - CR-HIGH-6 wrong: `symbol_index_swift` is registered as `SymbolIndexSwift()`.
> - CTO-HIGH-5 wrong: `palace.memory.add_to_bundle` exists at `mcp_server.py:465`.
>
> **Structural changes in rev2:**
> 1. Added **S0 — Foundation prerequisites** sprint (IngestRun schema unification, missing composite tools, audit-mode agent prompts, templates directory).
> 2. Removed **AuditSynthesizer** agent role — replaced with Python renderer function (saves tokens, prevents hallucination).
> 3. Rewrote **§4 paved-path** around `BaseExtractor.audit_contract()` — real plug-and-play, not aspirational.
> 4. Split **`palace.audit.run`** into sync data-tool + async workflow launcher (CTO-CRITICAL-2).
> 5. Redesigned **S1.9** to use Paperclip child issues for parallel agent dispatch (OPUS-HIGH-1).
> 6. Added **mandatory semgrep-Swift spike** as S2 prerequisite (OPUS-HIGH-3).
> 7. Added **token budget** decision point AV1-D6 (CTO-HIGH-1).
> 8. Added **blind-spot acceptance** decision point AV1-D7 (CTO-HIGH-2).
> 9. Honest **slice sizing** throughout — dropped "≤30 min" claims where unrealistic.
> 10. Added **S4 measurable acceptance criteria** (CR-MED-4).
> 11. Padded **S5 to 3 weeks** with 1 week per-Kit debugging budget (OPUS-MEDIUM-1).
> 12. Moved **roadmap archive** from HTML comments to `docs/roadmap-archive.md` (OPUS-LOW-1).
> 13. Templates in `audit/templates/<extractor>.md`, not `extractors/<name>/` (avoids flat-to-dir refactor, CTO-LOW-1).
> 14. GIM-218 contingency: explicit demotion to "nice-to-have" for S4 if not started within 1 week.

---

## 1. What we ship in v1

Two tools, two purposes:

**`palace.audit.run(project, depth="full") → AuditReport`** — synchronous MCP tool.
Fetches data from graph, renders markdown report from extractor outputs. No agent involvement.
Returns immediately. Used for smoke testing, ad-hoc checks, operator review.

**`audit-workflow-launcher.sh <slug>`** — async multi-agent workflow.
Creates a parent Paperclip issue + 3 child issues (one per domain agent). Each agent queries
palace MCP tools, produces a structured sub-report. Parent collects results via
`issue_children_completed` wake, then calls `palace.audit.render()` to produce the final report.
Used for production audit runs where agent reasoning adds value.

`AuditReport` is a structured markdown document with these sections:

1. **Executive summary** — top-N findings, severity-graded, ≤500 words.
2. **Architecture** — layer model + module boundaries + violations
   (S2.2 #1, rev3), public API surface, cross-module contract drift
   (from GIM-190/192).
3. **Quality** — hotspots (GIM-195), dead symbols (GIM-193), code-smell
   counters (Phase B if/when added; for v1 marked "blind spot — pending
   #34").
4. **Security** — error-handling policy + swallowed-catch findings
   (S2.3 #7, rev3), crypto-domain findings (S2.1 #40), known taint
   patterns (LLM blind spot — pending #35).
5. **Dependencies** — external surface (GIM-191), version skew
   (GIM-218 if merged; otherwise marked "blind spot — GIM-218 pending"),
   single-source picks.
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

Per AV1-D2 (rev2: reuse 3 + 1 new Auditor; NO AuditSynthesizer):

| Agent | Role | Audit-mode additions | What it queries |
|-------|------|---------------------|------------------|
| **OpusArchitectReviewer** | Architecture findings | Audit-mode prompt section: input format (fetcher JSON), output format (sub-report markdown), severity grading from extractor metrics | `palace.code.find_references`, public API surface, cross-module contract |
| **SecurityAuditor** | Security findings | Audit-mode prompt section: same contract | `palace.code.find_owners`, error-handling counters, crypto-domain output (S2) |
| **BlockchainEngineer** | Crypto-Kit specifics | Audit-mode prompt section: same contract | `palace.code.find_owners`, crypto-domain output (S2), purl scopes |
| **Auditor** (NEW role, S1) | Quality + Dependencies + Historical | Full audit role prompt from scratch | `palace.code.find_hotspots`, `palace.code.find_owners`, `palace.code.find_version_skew`, `:IngestRun` provenance |

**AuditSynthesizer removed** (rev2, OPUS-HIGH-2): the renderer is pure Python
(`audit/renderer.py`). LLM reasoning is unnecessary for template rendering and
risks hallucinating/modifying findings — which §4 explicitly prohibits. The
workflow launcher calls `palace.audit.render(sub_reports)` directly.

Three reuses (with audit-mode prompt additions) + 1 new role. One new role
file to author: `paperclips/roles/auditor.md`. Three existing role files
need an `## Audit mode` section appended.

## 3. Why this scope is the fastest viable v1

We rejected three larger v1 scopes:

### Rejected — "full audit team with 7 specialised roles"
Adds 5 new role files, 5 new agent UUIDs, 5 sets of role-specific
prompts. Doubles the synthesis surface. Operator can split the single
`Auditor` role into Quality / Dependency / Historical / etc later if
S4 smoke surfaces real differentiation pressure. Until then YAGNI.

### Partially accepted — Phase B subset for v1 (rev3)
Original Phase B candidates: #1 Arch Layer + #2 Symbol Dup + #34
Code Smell + #7 Error Handling (~3 weeks each). Rev2 shipped only
#40 to fit a 12-week envelope. **Rev3 (operator decision 2026-05-07)
expands envelope to 18 weeks and adds #1 + #7** — both deemed
foundational for blockchain audit (layer violations + swallowed
errors are unacceptable §9 blind spots for a Wallet Kit audit).
**Still rejected for v1**: #2 Symbol Duplication (needs embeddings
infra) and #34 Code Smell Structural (overlaps Hotspot/CCN —
post-smoke decision). Both remain S6+.

### Rejected — "wait for LLM infra before v1"
LLM-blocked extractors (#11 Decision History, #26 Bug-Archaeology,
#35 Taint, #43 PR Review) are valuable but require Ollama
deployment + cost monitoring + agent-llm cost budgeting — that's
a separate slice not yet specced. Decision AV1-D4: defer. v1 ships
with the LLM-blocked sections explicitly noted as blind spots.

## 4. The "post-v1 paved path" promise (rev2 — `audit_contract()`)

The crucial design constraint: **after v1 lands, adding extractor X
requires implementing ONE method on the extractor class — no
orchestrator, renderer, or agent changes.**

This is enforced by the **`BaseExtractor.audit_contract()`** pattern
(rev2, OPUS-CRITICAL-2):

```python
class BaseExtractor:
    def audit_contract(self) -> AuditContract | None:
        """Return None if this extractor has no audit section."""
        return None

@dataclass
class AuditContract:
    query: str           # Cypher query that fetches audit-relevant data
    response_model: type # Pydantic model for the query result
    template_path: Path  # Path to Jinja template for the audit section
    severity_mapper: Callable[[Any], str]  # Maps findings → severity
```

The discovery→fetch→render pipeline is fully generic:
1. **Discovery** (`audit/discovery.py`): queries `:IngestRun` for latest
   successful runs per extractor — schema unified in S0.
2. **Fetch**: for each discovered extractor, calls
   `extractor.audit_contract().query` — no per-extractor `fetch_X()` functions.
3. **Render** (`audit/renderer.py`): loads `audit_contract().template_path`,
   renders with fetched data — no per-extractor renderer logic.

The only thing a new extractor must provide:
- `audit_contract()` returning its query, model, and template
- The template file at `audit/templates/<name>.md`

**No orchestrator changes. No new composite tools. No agent changes.**

If a future extractor needs a new agent role (e.g., LLM-bearing
agent for #26 Bug-Archaeology that needs reasoning over commit
messages), that's a v2 extension. v1's promise stops at "non-LLM
extractors plug in unchanged via `audit_contract()`".

## 5. Pre-S1 checklist

Before starting S1 brainstorm, operator should confirm:

- [ ] AV1-D1 — markdown only? (default yes)
- [ ] AV1-D2 — reuse 3 + 1 new Auditor, NO Synthesizer agent? (rev2 default yes)
- [ ] AV1-D3 — manual trigger only for v1? (default yes)
- [ ] AV1-D4 — LLM-blocked extractors deferred to S6+? (default yes)
- [ ] AV1-D5 — Track A/B SCIP emit pattern preserved? (default yes)
- [ ] AV1-D6 — Max token budget per agent per audit run? (rev2, CTO-HIGH-1.
  Default: 50K input / 10K output per domain agent. Measured after S4 dry run.)
- [x] AV1-D7 — Blind spots #1 (Architecture Layer) and #7 (Error Handling)
  acceptable for v1 blockchain audit quality bar? **NO (rev3 flip).** Both
  extractors included as S2.2 + S2.3; envelope expanded 12w → 18w to
  absorb +6w sequential. Operator confirmed 2026-05-07 (GIM-219).
- [ ] **S0 prerequisite sprint** approved (rev2 addition — IngestRun unification + composite tools).
- [ ] **GIM-218** status check: if still zero progress within 1 week of
  rev2 approval, demote version-skew to blind spot for S4 and descope
  from v1 critical path. GIM-216 is on track (PR #105, Phase 3 in progress).

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
- S0 (Foundation prerequisites) detail: `D-audit-orchestration.md` §S0
- S1 (Audit Orchestration) detail: `D-audit-orchestration.md`
- S2 (Crypto Domain Extractor) detail: `B-audit-extractors.md`
- S3 (Ingestion Automation) detail: `C-ingestion-automation.md`
- S4 (Smoke) detail: `E-smoke.md`
- S5 (Scale) detail: `F-scale.md`
- Archived Phase 2-6 backlog: `docs/roadmap-archive.md`
- Memory queue updated: `project_next_claude_extractor_queue.md`
- Existing in-flight: GIM-216 (`feature/GIM-NN-code-ownership-extractor`),
  GIM-218 (`feature/GIM-NN-cross-repo-version-skew`)
