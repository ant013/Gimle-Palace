# Spec — UW Agent Discovery Readiness Roadmap (rev2)

**Status:** Draft v2 (Board, 2026-05-19, post 3-subagent review)
**Author:** Anton (operator) + Board (Claude session)
**Pin:** develop tip `a65c448f fix(watchdog): emit shadow visibility logs in recovery_dry_run / baseline mode (#231)`
**Discovery contract inventory:** [`docs/runbooks/discovery-contract-inventory-2026-05-19.md`](../../runbooks/discovery-contract-inventory-2026-05-19.md) — rev2 minor fixes (M1, M2)
**Supersedes:** `2026-05-19-uw-discovery-readiness-roadmap.md` (rev1 on FB only, never merged)
**Retires (scope-qualified — see C2 / I6):** UW discovery portion of operator memory `project_gimle_palace_not_production_ready`. External-audit scope remains gated separately (M6, TBD).

## Changelog vs rev1

Rev2 addresses 15 review findings (5 critical, 6 important, 4 minor) from the 3-subagent code/architecture/PR-style review. Each fix is cited inline at affected milestone / slice.

| # | Tag | Reviewer's claim (summarized) | Resolution in rev2 |
|---|---|---|---|
| C1 | M3.D scope undersell | Existing rules syntactic; new 7 intents are behavioral/semantic — not <500 LOC in one PR | M3.D split into 4 slices: framework + seed → 2 intent batches → review-extend |
| C2 | M4.4 self-graded synthetic | Subagent grading subagent reproduces `project_uaudit_subagent_fp_systemic_pattern` | M4.4 split: M4.4a (CX synthetic, informational only) + M4.4b (operator hand-graded real ticket, the gate) |
| C3 | Wrong fragment path | Submodule has `fragments/pre-work-discovery.md`, not `fragments/pre-work/*.md` | M4.1 path corrected; framed as extension of existing fragment |
| C4 | M3.A fan-out semantics unspecified | Each of 6 tools has different bundle semantics | New M3.A.0 design-note slice before any M3.A.1-6 starts |
| C5 | Pin discipline gap | No policy for spec pin updates between milestones | New «Pin maintenance» subsection in Cross-cutting |
| I1 | M1.2 «≤30 min» wishful | Per-Kit SCIP fragile; loop on 42 Kits unmeasured | Acceptance: «runtime measured + committed in runbook» (not pre-merge gate) |
| I2 | M2.1 «reuse Swift script» wrong | scip-java needs gradle + AGP pinning, different toolchain | Renamed to «new `ingest_kotlin_module.sh`», effort <300 LOC |
| I3 | M3.B hidden dep on M3.D | `coding_convention` summary needs `:Convention` from M3.D | M3.B v1 ships without convention; convention added in M3.B-rev2 after M3.D lands |
| I4 | Gates weak on measurability | «non-empty», «≥10 OK» — no oracle | Each gate has committed JSON fixture OR explicit operator-graded spotcheck list |
| I5 | Medic coordination missing | `paperclip-shared-fragments` shared with Medic; M4.1 bumps pointer | M4.1 acceptance: Medic notify + `validate_instructions.py` against Medic dist |
| I6 | Retire-claim mismatches memory | Memory blocks «external audits»; M4 validates internal discovery | Retire qualified to «UW discovery only»; external-audit retirement deferred to M6 |
| M1 | `_slug_to_cm_project` mis-attributed | Lives in `code_composite.py:76`, not `code_router.py` | Inventory matrix corrected |
| M2 | `git.blame` arg shape | Actual: `project, path, ref=HEAD, line_start, line_end` (verified against `mcp_server.py`) | Final acceptance script updated |
| M3 | Status mismatch | «Awaiting PR» but already on FB | Updated wording |
| M4 | Plans-per-slice cost | `feedback_plan_first`: 3+ subtask → plan, else no | General Cross-cutting rule added; per-slice tagging avoided |

## Goal (unchanged)

Bring Gimle's palace.* MCP toolset to the level where an implementer agent (Claude or Codex) can discover and reuse existing UW iOS / Android codebase patterns **like a human engineer who knows the code**.

Concrete success: «implement cryptoPay (QR scan → URI parse → token selection → request → send)» — agent runs a discovery script of 15-18 `palace.*` calls **before** writing code, cites findings in PR body, reuses existing classes/patterns, matches module's idiomatic style.

## Non-goals (rev2 adds explicit M6 deferral)

- New agent runtime
- Changes to extractor framework substrate (GIM-101a foundation)
- Free-text natural-language search (M5 optional)
- CM internal changes (out of Gimle scope)
- **External-audit scope** of `project_gimle_palace_not_production_ready` — deferred to M6, scope TBD

## Operator architectural decisions (2026-05-19, rev1 + rev2 review rounds)

| # | Decision |
|---|---|
| 1 | **Approach A**: explicit `bundle=` param per project-scoped native tool |
| 2 | **`palace.code.get_snippet_rich`** as native composite |
| 3 | **Hybrid idiom curation**: operator seeds 7 intents; team extends in batches per M3.D split |
| 4 | **IB-3 OpenAI quota** decision deferred to M5 entry |
| 5 | **CM-side bundle awareness**: watch metric M1; escalate to upstream if blocking |

## Milestones map (rev2)

| Milestone | Theme | Slice count | Teams | Gate exit oracle |
|---|---|---|---|---|
| **M0** | Prereqs + discovery contract pinned | 2 | Mixed | Inventory committed; GIM-355/356/357 closed |
| **M1** | UW iOS bundle query-ready | 4 | Mixed | Committed ≥10-symbol JSON oracle returns hits; per-member audit renders |
| **M2** | UW Android parity | 3 | Mixed | Committed 5-symbol oracle returns hits in both bundles |
| **M3** | Discovery primitives | 1 (design) + 6 (A) + 1 (B) + 1 (C) + 4 (D) = **13** | Mixed (M3.D 4-way split per C1) | Per-tool fixtures + golden JSON; operator-graded spotcheck for idioms |
| **M4** | Enforcement | 4 (M4.4 split per C2) | Mixed | M4.4b operator-signed real-ticket evidence |
| **M5** *(optional)* | Semantic unlock | 3 | Mixed | Operator-graded 3 sample queries |
| **M6** *(deferred)* | External-audit readiness | TBD | TBD | Closes remaining `project_gimle_palace_not_production_ready` scope |

---

## M0 — Prereqs + discovery contract

(Unchanged from rev1.)

| Slice | Team | Scope | Effort | Acceptance |
|---|---|---|---|---|
| **M0.1** This spec + inventory committed | Board | Both files merged on develop via this PR | <50 LOC | Spec + inventory merged; cited in subsequent slice plans |
| **M0.2** GIM-355/356/357 closure validation | Codex (CXCTO) | Re-run `ingest_swift_kit.sh bitcoin-core` post-fixes; document matrix | <100 LOC runbook | `docs/runbooks/bitcoin-core-post-fix-validation-2026-05-XX.md` shows ≥16/17 extractors `OK` + 1 expected `MISSING_INPUT` (`dead_symbol_binary_surface` per `periphery_fixtures_missing`) |

---

## M1 — UW iOS Bundle Query-Ready

| Slice | Team | Scope | Effort | Acceptance (oracle-grounded — I4) |
|---|---|---|---|---|
| **M1.1** Pre-flight regression baseline | Claude | Run `palace.audit.run(project="uw-ios-mini")` on fixture; commit baseline | <200 LOC | `docs/runbooks/uw-ios-mini-audit-baseline-2026-05-XX.json` committed; ≥10 extractors `OK` (vs explicit `RUN_FAILED` / `MISSING_INPUT` / `NOT_ATTEMPTED` taxonomy per `reference_palace_mcp_tool_schemas`) |
| **M1.2** Operator-side SCIP emit helper for UW iOS bundle | Codex (CXPyEng) | New `paperclips/scripts/scip_emit_xcode_bundle.sh` loops 41 Kits + main app, reuses per-Kit `scip_emit_swift_kit.sh`. **I1 fix:** acceptance is «runtime measured + committed in runbook» — NOT pre-merge ≤30-min gate | <250 LOC | Script runs end-to-end on operator dev Mac; produces 42 SCIP files at `/repos-hs/<Kit>/scip/index.scip`; **measured runtime committed to runbook**; per-Kit success/failure JSON aggregated; **≥35/42** successful (looser than rev1) |
| **M1.3** Bundle-mode ingest orchestration | Claude (PythonEng) | Extend `paperclips/scripts/ingest_swift_kit.sh` with `--bundle-all` mode | <250 LOC | One command ingests bundle; per-member status aggregated; ≥35 members succeed |
| **M1.4** Bundle smoke audit + symbol oracle | Codex (CXQAEngineer) | Run `palace.audit.run(bundle="uw-ios", depth="full")`; commit per-member reports + **fixed oracle JSON** of ≥10 specific UW symbols | <100 LOC | Audit `ok=true`; **all 10** oracle symbols return ≥1 ref via `find_references(bundle="uw-ios")` (not «non-empty» — per-symbol pass); `RUN_FAILED ≤ 5%` of (members × extractors) |

**Gate exit oracle:** committed `docs/runbooks/uw-ios-symbol-oracle-2026-05-XX.json` of ≥10 specific UW iOS symbols; **every** oracle symbol returns ≥1 ref.

Memory checkpoint: operator writes `project_uw_ios_indexed.md`.

---

## M2 — UW Android Parity

| Slice | Team | Scope | Effort | Acceptance |
|---|---|---|---|---|
| **M2.1** scip-java pinning + **new** `ingest_kotlin_module.sh` | Codex (CXPyEng) | **I2 fix:** new script (NOT «reuse Swift pattern»). gradle compileKotlin + scip-java + AGP pinning per `project_scip_java_strategy_2026-04-30` (UW@`c0489d5a3`, pre-AGP-9). Ingest `uw-android` | **<300 LOC** | `palace.audit.run(project="uw-android")` `ok=true`; ≥10 extractors `OK` (taxonomy explicit); committed runtime + per-extractor count |
| **M2.2** Cross-platform diff report | Claude (PythonEng) | Side-by-side `uw-ios` vs `uw-android` per-extractor findings | <200 LOC | `docs/runbooks/uw-cross-platform-diff-2026-05-XX.md` committed with row-by-row diff |
| **M2.3** Cross-platform smoke + symbol oracle | Codex (CXQAEngineer) | Committed list of **5** common-name symbols (`Wallet`, `Address`, `Balance`, `Transaction`, `Network`) | <100 LOC | Each of 5 returns ≥1 ref in **both** bundles via wire test `tests/extractors/integration/test_uw_cross_platform_symbols.py` |

Memory checkpoint: operator updates `project_uw_indexed_both_platforms.md`.

---

## M3 — Discovery Primitives

### M3.A — bundle parameter extension to 6 project-only tools (Approach A)

**C4 fix:** new pre-slice M3.A.0 design-note before M3.A.1.

| Slice | Team | Scope | Effort | Acceptance |
|---|---|---|---|---|
| **M3.A.0** Per-tool bundle-semantics design note | Claude (Board + CTO) | 1-pager per tool defining bundle behavior. Specifically resolves: `find_hotspots top_n` cut strategy (global vs per-Kit quota); `find_dead_symbols` cross-Kit reachability (bundle dead ≠ union per-project dead); `find_public_api` scope (app + Kits vs app-only); `find_owners` / `list_functions` / `find_cross_module_contracts` per-tool merge rules | <300 LOC doc | `docs/runbooks/m3-bundle-semantics-design.md` committed; CR Phase 1.2 + **operator explicitly approve** before M3.A.1 starts |
| **M3.A.1** `find_hotspots bundle=` param | Codex (CXPyEng) | Per M3.A.0 | <150 LOC + tests | Per-design-note acceptance; committed fixture + golden JSON |
| **M3.A.2** `list_functions bundle=` param | Codex (CXPyEng) | Per M3.A.0 | <100 LOC + tests | Same |
| **M3.A.3** `find_owners bundle=` param | Codex (CXPyEng) | Per M3.A.0 | <150 LOC + tests | Same |
| **M3.A.4** `find_dead_symbols bundle=` param | Codex (CXPyEng) | Per M3.A.0 **(highest cross-Kit reachability complexity)**. If M3.A.0 escalates as too-complex-for-1-slice, ship per-project union v1 + follow-up issue | <250 LOC + tests | Per-design-note; v1 acceptance documented per M3.A.0 outcome |
| **M3.A.5** `find_public_api bundle=` param | Codex (CXPyEng) | Per M3.A.0 | <100 LOC + tests | Same |
| **M3.A.6** `find_cross_module_contracts bundle=` param | Codex (CXPyEng) | Per M3.A.0 | <150 LOC + tests | Same |

### M3.B — `get_snippet_rich` composite (I3 fix: convention deferred)

| Slice | Team | Scope | Effort | Acceptance |
|---|---|---|---|---|
| **M3.B** `palace.code.get_snippet_rich` v1 (no convention) | Claude (MCPEng) | Composite: CM `get_code_snippet` + Palace `find_owners` + `find_hotspots` + recent commits. **I3 fix:** convention summary EXCLUDED from v1; added in M3.B-rev2 after M3.D lands | <250 LOC | Returns `{snippet, definition_location, usages, owners, hotspot_score, recent_commits}` — NO `conventions` field in v1; integration test |

### M3.C — `find_idiom` MCP tool

| Slice | Team | Scope | Effort | Acceptance |
|---|---|---|---|---|
| **M3.C** `palace.code.find_idiom` MCP tool | Claude (MCPEng) | Reads `:Convention` + `:ConventionViolation` from `coding_convention` extractor (queries existing schema — does not write) | <200 LOC | Returns structured response with `dominant`, `samples`, `outliers`; integration test |

### M3.D — Idiom curation **(C1 fix: 4-slice split)**

Rev1 lumped framework + 7 intents + per-module validation into one <500 LOC slice — reviewer correctly flagged as unrealistic. Existing `coding_convention/` is a 4-file monolith (571 LOC) with **syntactic** regex rules (`naming.type_class`, `structural.adt_pattern`, `idiom.collection_init`). New 7 intents (`async_cancel`, `error_propagation`, etc.) are **behavioral/semantic** — require semgrep + tree-sitter on Swift+Kotlin, OR data-flow on SCIP, OR separate analyzer. None fit in regex.

| Slice | Team | Scope | Effort | Acceptance |
|---|---|---|---|---|
| **M3.D.0** plugin/rules/ framework + seed intent (async_cancel) | Codex (CXPyEng) | Refactor `coding_convention/` from monolith to `extractor.py` + `rules/__init__.py` + `rules/_base.py` + `rules/async_cancel.py`. Implementation approach (semgrep+tree-sitter vs SCIP-data-flow) decided in plan-first review | ~400 LOC | `:Convention` nodes for `async_cancel` intent appear in Neo4j on `uw-ios` after re-ingest; ≥3 modules have dominant computed; **operator-graded spotcheck** — operator picks 5 specific modules and confirms dominant matches reality (per C2: NOT subagent-graded) |
| **M3.D.1** +2 intents (error_propagation, networking_client) | Codex (CXPyEng) | 2 new rule files using M3.D.0 framework | ~400 LOC | Same per-intent acceptance (operator-graded 5 modules per intent) |
| **M3.D.2** +3 intents (persistence, di_injection, navigation) | Codex (CXPyEng) | 3 more rule files | ~500 LOC | Same |
| **M3.D.3** Final seed (logging) + review-and-extend | Codex (CXPyEng) | Add `logging` intent + team mines UW codebase via PR-comment-driven extension (target: 12-15 total intents shipped) | ~300 LOC | All 7 seed intents work; ≥5 additional team-extended intents in `rules/`; documented in `docs/runbooks/api-idiom-rules.md` |

**Sequencing within M3:**

1. **M3.A.0 first** (Board+Claude+CR+operator approve) → blocks M3.A.1-6
2. M3.A.1-6 serialize on Codex (one slice per CXCTO at a time) — 6 PRs in sequence
3. M3.B + M3.C serialize on Claude (single CTO/MCPEng) — 2 PRs
4. **M3.D.0-3 serialize on Codex strictly** (4 PRs in sequence) — depends on framework in M3.D.0
5. M3.A (Codex) and M3.B+C (Claude) can run in parallel across teams
6. M3.D follows M3.A on Codex (cannot parallel within team)
7. **I3 explicit dep arc:** M3.B-rev2 (with convention) **requires M3.D.0 landed first**

**Gate exit oracle:**
- All M3.A.* tools return non-empty + golden-JSON-match for committed bundle test fixture
- M3.D: **operator-graded spotcheck list** (5 modules per seed intent) confirms dominant matches reality — gates **per intent**, not per slice

Memory checkpoint: operator updates `project_palace_discovery_primitives_ready.md`.

---

## M4 — Discovery Enforcement

| Slice | Team | Scope | Effort | Acceptance |
|---|---|---|---|---|
| **M4.1** Extend existing `pre-work-discovery.md` fragment **(C3 path fix + I5 Medic)** | Claude (TechnicalWriter) | **Real path: `paperclips/fragments/shared/fragments/pre-work-discovery.md`** (NO `pre-work/` subdir). Frame as **extension** of existing fragment with concrete `palace.code.*` discovery script template + required PR-body sections («Reuse findings», «Style match», «Open questions»). Bump submodule pointer. **I5 fix:** acceptance includes Medic coordination | <150 LOC | Fragment updated in submodule; pointer bumped; rendered into ≥1 Claude bundle + ≥1 Codex bundle; `validate_instructions.py` green; **Medic team notified before pointer bump** (paperclip API → Medic CTO) AND `validate_instructions.py --repo-root <medic-path>` green OR follow-up issue filed if Medic-side regression |
| **M4.2** CR enforcement compliance check | Codex (CXCodeReviewer) | Extend Phase 3.1 to require «Reuse findings» section in PR body OR explicit «no-match» note | <100 LOC role-file change | Synthetic PR test — body without section → CR returns request-changes |
| **M4.3** Wire fragment into 10 implementer role AGENTS.md | Claude (TechnicalWriter) | 5 Claude + 5 Codex implementer roles | <50 LOC fragment refs | All 10 role files reference fragment; `validate_instructions.py` green |
| **M4.4a** *(informational)* CX synthetic e2e | Codex (CXQAEngineer) | Synthetic task «add TRC20 token display row in WalletList». Drive CXPyEng; capture discovery calls + reuse evidence | <50 LOC runbook | Evidence committed at `docs/runbooks/m4-cx-synthetic-validation-2026-05-XX.md` — **informational only, NOT the gate** |
| **M4.4b** **(THE gate)** Operator hand-graded real-ticket validation **(C2 fix)** | Board / operator | Operator picks a real upcoming UW iOS feature ticket. Implementer (Claude or Codex) executes. **Operator hand-grades**: did agent run ≥5 discovery calls? Did PR body cite ≥3 findings? Did agent reuse ≥2 existing patterns? Did style match conventions? — **operator decides per criterion**, NO subagent involvement (per `project_uaudit_subagent_fp_systemic_pattern`) | <50 LOC runbook | Operator-signed evidence at `docs/runbooks/m4-operator-validation-<ticket>-2026-05-XX.md` with explicit operator signoff line |

**Gate exit:** M4.4b operator-signed evidence committed.

Memory checkpoint: operator **partially retires** `project_gimle_palace_not_production_ready` — adds qualifier «UW discovery scope unblocked after M4; **external audits remain gated** until M6 (TBD)» AND writes `project_palace_agent_discovery_ready.md` with M4.4b evidence path. **I6 fix.**

---

## M5 — Semantic Search (optional)

| Slice | Team | Scope | Effort | Acceptance |
|---|---|---|---|---|
| **M5.1** IB-3 OpenAI quota analysis + path decision | Codex (CXResearchAgent) | Report: cost top-up vs local embedder vs hybrid | <100 LOC analysis | `docs/research/2026-05-XX-embedding-cost-analysis.md`; operator decides path |
| **M5.2** Embedding backend per M5.1 | Claude (MCPEng) | Per-decision implementation | <300 LOC | `palace.memory.health()` shows embedder operational |
| **M5.3** `palace.code.semantic_query` MCP tool + UW iOS embedding | Codex (CXMCPEng) | New tool wrapping Graphiti similarity + ingest UW iOS bundle | <250 LOC + ingest runtime | **Operator-graded** 3 sample queries selected by operator return sensible results |

---

## M6 *(deferred, scope TBD)* — External-audit readiness

**I6 placeholder.** Closes the «external audits» portion of `project_gimle_palace_not_production_ready` that M4 explicitly did NOT cover.

Likely requires:
- Distinct validation against a non-UW project (external HS contributor's repo or unrelated open-source Swift kit)
- Different acceptance shape (external-audit-shaped, not internal-discovery-shaped)

Not detailed in v2 spec body. Roadmap entry only.

---

## Cross-cutting rules (rev2 updates)

- **Slice size**: 1 PR, ≤300 LOC ideal, single concern, independent CI green.
- **Slice ordering**: 1 active issue per team. Cross-team parallel only when file scopes don't overlap. Within team — strict sequential (per `feedback_sequential_assign_when_tree_overlap`).
- **Failure handling**: missed AC → sub-issue, not bundle into next slice.
- **Plans-per-slice (M4 fix)**: per `feedback_plan_first` memory — slice ≤150 LOC + 1 PR → no separate plan doc; otherwise plan required. CR Phase 1.2 enforces per slice.
- **Pin maintenance (C5 fix)**:
  - At each milestone start, the milestone-opening slice (M1.1 / M2.1 / M3.A.0 / M4.1 / M5.1) updates this spec's top-level Pin line with current develop SHA via spec rev (`rev3-pin-bump`).
  - Breaking refactors in `services/palace-mcp/src/palace_mcp/code_router.py`, `code_composite.py`, `mcp_server.py`, `audit/run.py`, `audit/discovery.py`, OR any file under `extractors/foundation/`, OR submodule pointer for `paperclip-shared-fragments` — **trigger CTO-level spec review** (re-validate inventory matrix; bump spec rev if matrix changed).
- **Spec revisions**: `-rev3`, `-rev4` suffix per `docs/contributing/docs-layout.md`.
- **Memory updates**: each milestone exit triggers memory checkpoint (operator-side).
- **Slice-internal sub-issues**: not counted against team concurrency limit (continuation of parent slice).

## Final acceptance (whole roadmap, oracle-grounded — I4)

Operator runs this discovery script against UW iOS bundle, every call returns non-empty + actionable AND matches committed golden-JSON fixtures from M1-M3:

```
# Sanity (oracle: bundle freshness fixture)
palace.memory.get_project_overview(slug="uw-ios-app")
palace.memory.bundle_status(bundle="uw-ios")

# Exact-name discovery (oracle: ≥10 UW symbol list from M1.4)
palace.code.find_references("scanQR", bundle="uw-ios")
palace.code.find_references("addressFromMnemonic", bundle="uw-ios")

# Semantic / pattern (CM passthrough)
palace.code.search_code(pattern="bech32", lang="swift", project=...)
palace.code.search_graph(name_pattern="*Parser*", project=...)

# Snippet retrieval — enriched composite (M3.B v1 — no convention)
palace.code.get_snippet_rich(qualified_name="UriParser.parse", project="uw-ios-app")

# Idiomatic patterns (oracle: M3.D operator-graded spotcheck)
palace.code.find_idiom(intent="async_cancel", project="uw-ios-app", module="Send")
palace.code.find_idiom(intent="error_propagation", project="uw-ios-app")

# Ownership / risk (M3.A bundle param)
palace.code.find_owners(file_path="Modules/Send/SendController.swift", bundle="uw-ios")
palace.code.find_hotspots(bundle="uw-ios", path_prefix="Modules/Send")

# History (M2 fix: verified arg signature)
palace.git.log(project="uw-ios-app", path="Modules/Send/SendController.swift", limit=10)
palace.git.blame(project="uw-ios-app", path="Modules/Send/SendController.swift", ref="HEAD", line_start=42, line_end=42)

# Cross-cutting (M3.A bundle param)
palace.code.find_version_skew(bundle="uw-ios", min_severity="minor")
palace.code.find_dead_symbols(bundle="uw-ios")
palace.code.find_public_api(bundle="uw-ios")

# Optional M5 (operator-graded)
palace.code.semantic_query("how does the app cancel async tasks", bundle="uw-ios")
```

Each tool's return matches its committed golden JSON fixture.

## Open questions for operator (rev2 round)

1. **M3.D split execution order.** Strict sequential on Codex (4 PRs), or parallelize via different CXPyEng agents on independent rule files? Latter only safe if file scopes don't overlap — rules/ slices may touch shared `rules/__init__.py`.
2. **M3.D.0 implementation approach.** Plan-first decides: semgrep + tree-sitter (new dep) OR data-flow on SCIP (no new dep but harder for behavioral intents)?
3. **M4.4b real ticket choice.** Operator selects which upcoming UW feature ticket — needs to be representative (not just CSS-tweak). Suggest «add new TRC20-style integration».
4. **M3.A.4 dead-symbol reachability.** If M3.A.0 escalates as too complex for one slice, ship M3.A.4 with per-project union v1 + follow-up issue?
5. **M6 scoping kickoff.** Draft external-audit M6 scope before or after M4 completes?

## Reviewer-disagreed positions (transparency)

In two places rev2 resolves slightly differently from reviewer's framing — disclosed explicitly:

- **C5 pin maintenance**: reviewer rated Critical; rev2 resolves as Cross-cutting rule (process detail). If reviewer disagrees, willing to upgrade to its own slice (M0.3).
- **I4 oracle for M3.D**: reviewer suggested «manual spotcheck list». Rev2 makes it **operator-graded** explicitly (per C2: subagent grading insufficient). This creates compounding manual operator burden — tradeoff flagged.

— Board (Anton), draft v2 2026-05-19, develop tip `a65c448f`
