# Gimle-Palace Team Roadmap

**Last updated**: 2026-05-06 (rev2: audit-v1 plan — 3-reviewer synthesis)
**Owner**: Board (operator + Board Claude session)
**Primary goal**: Index Unstoppable Wallet ecosystem live (Android + iOS + EVM
contracts). Phase 1 ends when palace-mcp produces useful queries against the
real UW codebase end-to-end.

This file is the **single source of truth** for slice ownership and ordering
across the two paperclip teams (Claude and CX/Codex). Update on every slice
merge or scope change.

---

## Status legend

| Icon | Meaning |
|------|---------|
| ✅ | Merged to develop |
| 🚧 | In flight (active phase chain) |
| 📋 | Queued — assigned, ready to start |
| ⏸ | Deferred — has explicit reactivation trigger |
| 📦 | Backlog — no team yet, no trigger |

## Team domains

| Team | Default scope | Adapter |
|------|--------------|---------|
| **Claude** | Python-orchestration extractors, LLM-using extractors, watchdog/observability, product-tool composites, Slice spec authoring, infrastructure, runbooks | `claude_local` |
| **CX/Codex** | Native-compiled language extractors, SCIP indexer integration, custom scip-emit binaries, native LSP work | `codex_local` |

Roles within each team follow the standard 7-phase chain: CTO → CR → PE/MCP/Infra → CR → Opus → QA → CTO merge. See `paperclips/fragments/profiles/handoff.md` for atomic-handoff discipline.

CX team currently lacks BlockchainEngineer and SecurityAuditor parity — see E6 in §5.

---

## Phase 1 — UW launch path (priority)

When all rows below are ✅, palace-mcp can index the entire UW production ecosystem live and the operator runs queries against real source instead of fixtures. **Phase 2 does not start until Phase 1 closes.**

### CX queue (sequential, launch-critical)

| Order | Slice | Status | Issue | Files | Notes |
|-------|-------|--------|-------|-------|-------|
| 1 | Symbol index Swift (UW-iOS, custom emitter Option C) | ✅ | GIM-128 | `services/palace-mcp/scip_emit_swift/`, `extractors/symbol_index_swift.py`, `tests/extractors/fixtures/uw-ios-mini-project/` | Merged `4ff2b2f`. Custom emitter; canonical Sourcegraph SCIP protobuf output. |
| 2 | Symbol index C/C++/Obj-C (UW-iOS Pods, scip-clang) | ✅ | GIM-184 | `extractors/symbol_index_clang.py`, fixtures, compose mounts | Merged `80b4f38`. Final v1 scope is C/C++; Objective-C is a documented follow-up after `scip-clang` smoke showed `.m` unsupported as first-class input. |

**Launch boundary**: reached when both CX queue items above AND Claude queue C2 (Multi-repo SPM ingest, GIM-182) are ✅. As of 2026-05-04, all launch-critical implementation rows are merged; the remaining launch close gate is operator validation that real UW queries return expected results end-to-end.

### Claude queue (parallel, infra + tooling + launch-critical C2)

| Order | Slice | Status | Issue | Files | Notes |
|-------|-------|--------|-------|-------|-------|
| C1 | Watchdog handoff detector (Phase 1 alert-only) | ✅ | GIM-181 | `services/watchdog/*` | Detective half of atomic-handoff strategy; merged `f2f05c4` |
| C2 | Multi-repo SPM ingest (full slice — Claude end-to-end) | ✅ | GIM-182 | `services/palace-mcp/src/palace_mcp/{memory/bundle.py,code/find_references.py,ingest/runner.py,git/path_resolver.py}`, `services/palace-mcp/scripts/`, `docs/runbooks/multi-repo-spm-ingest.md` | Merged `f2696fa`. Originally split (Claude=spec, CX=impl); operator decision 2026-05-03 reassigned to Claude end-to-end. |
| C3 | Watchdog handoff detector — Opus nudge follow-up | ✅ | GIM-183 | `services/watchdog/*` | 3 follow-ups merged `365c9c4` (PR #81): server-Date anchoring, 4 missing JSONL events emitted, e2e lifecycle test. |
| C4 | Git History Harvester (Extractor #22) — Phase 2 prereq | ✅ | GIM-186 | `services/palace-mcp/src/palace_mcp/extractors/git_history/`, `services/palace-mcp/tests/extractors/{unit,integration,fixtures}/`, runbook | Merged `b0dd44d`. Foundation for 6 historical extractors (#11/#12/#26/#32/#43/#44) — all now unblocked. |
| C5 | iMac post-merge auto-deploy | 📋 | TBD | `paperclips/scripts/imac-deploy-listener.{sh,plist}`, webhook handler | Removes manual `imac-deploy.sh` step after every merge |
| C6 | `palace.code.semantic_search` | ✅ | GIM-837 / G0.5.5 | `services/palace-mcp/src/palace_mcp/code/find_semantic.py`, `services/palace-mcp/src/palace_mcp/code/semantic_contract.py` | Superseded by G0.5.5. Product-quality ranking/filtering/snippet/matrix hardening continues in G0.6 PR3-PR6. |

C2 (GIM-182), C4 (GIM-186), and C6 are now ✅. C3/C5 are independent and not launch-blocking.

### Already merged (Phase 1 foundation)

| Slice | Issue | Note |
|-------|-------|------|
| Symbol index Python | GIM-102 | Foundation dogfood; first content extractor on 101a substrate |
| Symbol index TS/JS | GIM-104 | Lang-agnostic `scip_parser` extracted |
| Symbol index Java/Kotlin | GIM-111 + GIM-127 | UW-Android validated, fixture pinned to UW@c0489d5a3 (pre-AGP-9) |
| Symbol index Solidity v1 | GIM-124 | DEFs only; USE-occurrences deferred to Phase 2 |
| Watchdog mechanical | GIM-67/69/79/80 | `scan_died_mid_work` + `scan_idle_hangs` |
| Atomic-handoff fragment | PR #77 (`9262aca`) | Preventive companion to GIM-181 |
| Watchdog handoff detector (alert-only) | GIM-181 (`f2f05c4`) | Detective half of atomic-handoff strategy; 3 Opus nudge follow-ups closed in GIM-183 |
| Watchdog handoff detector — Opus nudge follow-ups | GIM-183 (`365c9c4`) | Server-Date anchoring + 4 JSONL events + e2e lifecycle test |
| Symbol index Swift (UW-iOS) | GIM-128 (`4ff2b2f`) | First-party HS Kits indexed via custom emitter; CX queue item 1 closed |
| Symbol index C/C++ (UW-iOS native) | GIM-184 (`80b4f38`) | `scip-clang` C/C++ extractor merged; Objective-C follow-up documented out of v1 |
| Multi-repo SPM ingest | GIM-182 (`f2696fa`) | First-party HS Kits resolved via bundle; UW iOS multi-repo path unblocked |
| Paperclip team workspace isolation | PR #76 | Two team roots under `/Users/Shared/Ios/worktrees/{claude,cx}/` |
| Paperclip shared CM discipline | PR #75 | Both teams share `repos-gimle` CM project + `palace.memory.decide` writes |
| Codex/CX team build target | PR #73-74 | Codex team operational with 9 roles |

---

## Audit-V1 — first product release (current focus)

**Goal**: ship a working audit pipeline end-to-end — pick `tronKit-swift`,
get a complete audit report from a paperclip agent team, MCP fully
populated. After v1 ships, every additional extractor is a tiny isolated
slice that just enriches MCP without touching workflow.

**Definition of Done for v1 (rev3):**
1. `palace.audit.run(project="tronkit-swift")` returns a structured
   markdown report (synchronous data+render, no agent involvement).
2. `audit-workflow-launcher.sh tronkit-swift` triggers a multi-agent
   audit via Paperclip child issues; final report posted to parent.
3. The same commands work on `bitcoinkit-swift` and any other Swift Kit.
4. After v1, adding extractor X = (a) implement `audit_contract()` on
   extractor class, (b) add template file, (c) re-run — no orchestrator
   or agent changes needed (enforced by `BaseExtractor.audit_contract()`
   pattern).
5. Audit report ships **with populated** Architecture Layering (extractor
   #1) and Error Handling Policy (extractor #7) sections — these are
   NOT blind spots in v1 (rev3, AV1-D7 flipped from "yes/blind-spot" to
   "no/included"; +6w to envelope).

### Sprint sequence (rev3 — #1 + #7 included; 18w envelope)

| ID | Sprint | Detail file | Wall-time | Depends on | Team |
|----|--------|-------------|-----------|------------|------|
| **S0** ✅ | Foundation prerequisites (IngestRun unify, composite tools, audit-mode prompts) | [`D-audit-orchestration.md` §S0](superpowers/sprints/D-audit-orchestration.md) | ~1 week | nothing | PE (S0.1+S0.2) ‖ any (S0.3) | `0a02ade` |
| **S1 (D)** | Audit Orchestration — workflow + agents + report format + tool | [`D-audit-orchestration.md`](superpowers/sprints/D-audit-orchestration.md) | ~3-4 weeks | S0 | PE |
| **S2.1 (B-min)** | Audit-critical extractor: `crypto_domain_model` (#40) | [`B-audit-extractors.md`](superpowers/sprints/B-audit-extractors.md) | ~2 weeks | S1.6 frees PE + semgrep spike | Claude PE |
| **S2.2 (B+1)** | Architecture Layer extractor (#1) | [`B-audit-extractors.md`](superpowers/sprints/B-audit-extractors.md) | ~3 weeks | S2.1 frees PE | Claude PE |
| **S2.3 (B+7)** | Error Handling Policy extractor (#7) | [`B-audit-extractors.md`](superpowers/sprints/B-audit-extractors.md) | ~3 weeks | S2.2 frees PE (or ‖ if a 2nd Claude engineer is free) | Claude PE |
| **S3 (C)** | Per-Kit ingestion automation | [`C-ingestion-automation.md`](superpowers/sprints/C-ingestion-automation.md) | ~1 week | S1.9 (palace_mcp.cli) | Infra (‖ S1) |
| **S4 (E)** | Smoke on tronKit-swift + bitcoinKit-swift | [`E-smoke.md`](superpowers/sprints/E-smoke.md) | ~1 week | S0 + S1 + S2.1 + S2.2 + S2.3 + S3 (GIM-216 ✅ merged `2d6e6c1`; GIM-218 ✅ merged `603c840`) | QA + operator |
| **S5 (F)** | Scale to 41 HS Kits + uw-ios-app | [`F-scale.md`](superpowers/sprints/F-scale.md) | ~3 weeks | S4 | operator + Infra |
| **S6+** | Iterative extractor backlog (#2, #34, etc — #1/#7 NOT here in rev3) | TBD per slice | ongoing | post-v1 | per slice |

**Rev3 critical path** (sequential, single Claude PE): S0 (1w) → S1 (3-4w, PE-bound) →
S2.1 (2w PE) → S2.2 (3w PE, #1 Arch Layer) → S2.3 (3w PE, #7 Error Handling) →
S4 (1w) → S5 (3w) = **~17-18 weeks**.
S3 runs ‖ S1 (different engineer).
GIM-218 contingency closed: extractor merged `603c840` 2026-05-07.
**Parallel S2.2 ‖ S2.3 option**: if a second Claude engineer becomes available
after S2.1 (different files: arch_layer/* vs error_handling/*), max(3w, 3w) = 3w
collapses to **~14-15 weeks** total. Operator-chosen 18w envelope tolerates the
sequential path with ~0-1w margin; parallelisation is upside, not gating.

### Path justification (rev2 — incorporates team allocation)

- **S0 first**: prerequisite foundation fixes (IngestRun schema unification,
  missing composite tools, audit-mode agent prompts). Without S0, S1.4
  discovery misses half the extractors (OPUS-CRITICAL-1) and S1.5 fetcher
  has no tools to call (CR-CRITICAL-3).
- **S1 after S0**: defines the product surface. PythonEngineer-bound.
- **S2.1 after S1.6** (rev2 change): S2.1 also needs PE. Rev1 claimed S1‖S2
  parallel — impossible with one PE (CTO-MEDIUM-1). S2.1 starts when S1.6
  (`audit_contract()` implementations) frees PE. Requires completed semgrep
  spike (S2-prereq). S2.1 = `crypto_domain_model` (#40).
- **S2.2 after S2.1** (rev3): Architecture Layer extractor (#1). Reuses
  the semgrep / tree-sitter substrate from S2.1 prereq spike. Deterministic
  (no LLM); writes `:Module/:Layer/:ArchViolation`. Critical for
  blockchain-audit "wallet-core must not import UI", "Kit X must not
  depend on Kit Y" findings.
- **S2.3 after S2.2** (rev3): Error Handling Policy extractor (#7). Heuristic
  (semgrep + ast-grep + detekt rules). Writes `:CatchSite/:ErrorPolicy`.
  Critical for crypto-Kits — swallowed errors in signing/balance paths
  → potential lost funds.
- **S3 ‖ S1**: InfraEngineer domain, no file overlap. Ingestion automation
  shrinks per-Kit setup from ~30 min to ~3 min. Needs `palace_mcp.cli`
  from S1.9 (or `curl` shim until then).
- **S4 after S0+S1+S2.{1,2,3}+S3**: real smoke on tronKit-swift +
  bitcoinKit-swift. Measurable acceptance criteria (rev2, CR-MED-4)
  + per-extractor sections required for #1 + #7 (rev3, AV1-D7 flip).
- **S5 last**: scaling to 41 Kits. 3 weeks (rev2, padded from 2 — OPUS-MEDIUM-1).
- **S6+ post-v1**: each new extractor plugs in via `audit_contract()` —
  no orchestrator/agent changes.

### Critical decision points (rev2 — pre-S0 start)

| ID | Question | Default | Impact of non-default | When |
|----|----------|---------|----------------------|------|
| AV1-D1 | Report format: markdown only, or also JSON? | markdown only | JSON adds ~1 slice to S1.3 | S1.1 brainstorm |
| AV1-D2 | Agent set: reuse 3 + 1 new Auditor, NO Synthesizer? (rev2) | reuse 3 + Auditor, no Synth | Adding Synth = +1 agent role + token cost per audit | S1 brainstorm |
| AV1-D3 | Trigger: manual only for v1? | manual; cron/CI in S6+ | Cron adds ~2 slices | S1 brainstorm |
| AV1-D4 | LLM extractors deferred to post-v1? | yes | If no → +12 weeks for Ollama infra | After S4 |
| AV1-D5 | SCIP emit Track A/B preserved? | yes | Single-machine = simpler but slower | S3 brainstorm |
| AV1-D6 | Max tokens per agent per audit run? (rev2) | 50K in / 10K out | Higher = richer sub-reports but more cost | S1.1 brainstorm; measured in S4 |
| AV1-D7 | Blind spots #1 (Arch Layer) + #7 (Error Handling) acceptable for v1? (**rev3 — flipped**) | **NO — both extractors INCLUDED in v1; envelope expanded 12w → 18w** | If yes (revert to rev2) → 12w envelope, sections shipped as blind spots in §9 | Resolved pre-rev3 (operator decision 2026-05-07) |

### In-flight slices feeding v1

- **GIM-216** code_ownership — ✅ merged `2d6e6c1` 2026-05-06. Feeds Ownership report section in S4. `palace.code.find_owners` registered at `mcp_server.py:850`.
- **GIM-218** cross_repo_version_skew — ✅ merged `603c840` 2026-05-07. Feeds Dependencies §5 of audit report. `palace.code.find_version_skew` registered via `register_version_skew_tools()` at `mcp_server.py:790`. **Rev2 contingency closed** — extractor landed before contingency trigger fired; no blind-spot fallback needed.

### Post-v1 slice intake protocol (rev2 — `audit_contract()` paved path)

After v1 ships, adding extractor X follows the **paved path**:

1. Board+Claude session: brainstorm + spec rev1 + 4-agent audit + spec rev2.
2. Paperclip team: standard 7-phase chain.
3. Implementer adds `audit_contract()` method to extractor class + template file.
4. iMac deploy: `bash paperclips/scripts/imac-deploy.sh`.
5. Per-existing-Kit re-ingest: `bash scripts/ingest_swift_kit.sh <slug> --extractors=X`.
6. Re-run `palace.audit.run(project=<slug>)` — report includes new section
   automatically because the generic fetcher discovers it via `:IngestRun`
   and calls `audit_contract()` for query + template.

The pipeline is **extractor-name-agnostic** — discovery enumerates from the
graph, fetcher dispatches via `audit_contract()`, renderer loads the template.
No hardcoded lists anywhere in the orchestrator (rev2 fix for CTO-CRITICAL-1,
OPUS-CRITICAL-2).

---

## UW iOS Dev-Mirror Product (GIM-987 — rev2 spec)

**Goal**: 13 UW iOS kits (8 already in graph + 5 to add) with every
language-applicable extractor green, MacBook docker-compose on port
8765 + cloudflared `gimle.ant013.work`, WRITE tools bearer-gated.
**Dev-mirror for agent coding assistance**, not a production-audit
substrate ([[project_gimle_palace_not_production_ready]] still
applies). Spec:
[`docs/superpowers/specs/2026-05-29-uw-ios-full-product-rev2.md`](superpowers/specs/2026-05-29-uw-ios-full-product-rev2.md).
Walker plan:
[`docs/superpowers/plans/2026-05-29-GIM-987-uw-ios-dev-mirror-product.md`](superpowers/plans/2026-05-29-GIM-987-uw-ios-dev-mirror-product.md).

**Wall-time**: 17–23 working days focused / 5–7 calendar weeks.
**Phase**: parallel to Audit-V1 and Phase 2 — different track
(agent-assist), different file footprint, no overlap with Audit-V1
agent orchestration or Phase 2 middleware.

### CX queue (most of the slice work — 66% split)

Issue numbers `GIM-987-cN` are placeholders; CEO assigns real issue
numbers when spawning per the walker plan's phased dispatch.

| Order | Slice | Status | Walker child | Files | Notes |
|-------|-------|--------|--------------|-------|-------|
| 1 | A1 Toolchain auto-detect from `.swift-version` | 📋 | GIM-987-c1 | `paperclips/scripts/scip_emit_swift_kit.sh` | Hard-fail on missing toolchain. Unblocks B-series. |
| 2 | A2 Per-kit cleanup in `palace_ingest.sh` | 📋 | GIM-987-c2 | `paperclips/scripts/palace_ingest.sh` | Removes `.palace-scip-{build,derived-data}` post-success. |
| 3 | A5 iMac palace-mcp rebuild | 📋 | GIM-987-c5 | iMac ops | Applies PR #341 hf-cache fix permanently. Hard-gate before D3. |
| 4 | C2 `PALACE_SCIP_INDEX_PATHS` dedup | 📋 | GIM-987-c6 | `paperclips/scripts/ingest_swift_kit.sh` | Bounded env var growth. |
| 5 | A6a Extractor coverage discovery sweep | 📋 | GIM-987-c7 | new `paperclips/scripts/palace_extractor_coverage_2026-05-29.csv` + baseline list | Depends on A1. |
| 6 | B1 hs-extensions verify | 📋 | GIM-987-c8 | n/a (ingest only) | Closes #345 E2E. Depends on A1. |
| 7 | B2 MarketKit ingest | 📋 | GIM-987-c9 | `Package.swift` override if needed | Depends on A1; fallback GRDB pin. |
| 8 | B3 BitcoinCashKit ingest | 📋 | GIM-987-c10 | `Package.swift` override if needed | Depends on A1; fallback HsCryptoKit pin. |
| 9 | C1 `palace_cleanup.sh` | 📋 | GIM-987-c11 | new `paperclips/scripts/palace_cleanup.sh` | dual-host scan, 90 s ceiling. |
| 10 | C4 Graph orphan cleanup | 📋 | GIM-987-c12 | extends c11 | Soft-delete stale `:Project`. |
| 11 | B4a Cocoapods spike | 📋 | GIM-987-c13 | new `docs/research/2026-05-29-cocoapods-scip-spike.md` | 0.5 day. Depends on B2 (so SwiftPM path proven first). |
| 12 | B4b Cocoapods pipeline | 📋 | GIM-987-c14 | new `paperclips/scripts/scip_emit_cocoapods_kit.sh` + edits to `palace_ingest.sh` | Depends on B4a. |
| 13 | B5 component-kit ingest | 📋 | GIM-987-c15 | n/a | Depends on B4b. |
| 14 | B6 hd-wallet-kit-ios ingest | 📋 | GIM-987-c16 | n/a | Depends on B4b. Distinct from SwiftPM `hd-wallet-kit`. |
| 15 | D1 `docker-compose.dev-mac.yml` | 📋 | GIM-987-c17 | new `docker-compose.dev-mac.yml` | Port 8765, own neo4j volume, no `cpus` cap. |
| 16 | D2 macbook bootstrap runbook | 📋 | GIM-987-c18 | new `docs/runbooks/macbook-gimle-bootstrap.md` | 30–60 min walkthrough. |
| 17 | D4c GDPR email-hash env | 📋 | GIM-987-c20 | edit `docker-compose.dev-mac.yml` + `code_ownership` extractor | `PALACE_OWNERS_HASH_EMAILS=1`. |
| 18 | D4b Cloudflared tunnel | 📋 | GIM-987-c21 | new `services/cloudflared/dev-mac/` | Hard-gate after D4a (Claude queue). |
| 19 | D3 Fresh ingest of 13 kits on macbook | 📋 | GIM-987-c22 | n/a | Hard-gate after A5; depends on A1+A2+A3+D1. |
| 20 | F-A Smoke A per-extractor | 📋 | GIM-987-c23 | new `paperclips/scripts/palace_extractor_smoke.sh` | Per-language extractor coverage. |
| 21 | F-B Smoke B per-tool with seed oracle | 📋 | GIM-987-c24 | new `paperclips/scripts/palace_tool_smoke.sh` + `palace_smoke_seeds.json` | Real assertions, no tautology. |

### Claude queue (Python in palace-mcp + design — 33% split)

| Order | Slice | Status | Walker child | Files | Notes |
|-------|-------|--------|--------------|-------|-------|
| C1 | A3 `:Symbol` soft-delete + unique constraint + dedup migration | 📋 | GIM-987-c3 | `services/palace-mcp/src/palace_mcp/extractors/foundation/symbol_node_writer.py` + new `services/palace-mcp/scripts/migrate_symbol_constraint.py` | Coexists with existing `eviction.py` on `:SymbolOccurrenceShadow`. |
| C2 | A4 GIM-950 kit embedding `repo_not_mounted` fix | 📋 | GIM-987-c4 | `services/palace-mcp/src/palace_mcp/extractors/embedding_symbol.py` + any mount-path resolver | Hard cap 3 days. |
| C3 | D4a Bearer middleware on WRITE tools | 📋 | GIM-987-c19 | new `services/palace-mcp/src/palace_mcp/auth.py` + edits to `mcp_server.py` | `PALACE_WRITE_TOKEN` env. Hard-gate before D4b. |
| C4 | E1 Scheduled-updates design doc | 📋 | GIM-987-c25 | new `docs/superpowers/specs/2026-05-29-palace-scheduled-updates.md` | Design only this milestone. |

### Walker dispatch phases

Per the walker plan, CEO opens children in phased batches — does NOT
bulk-POST all 25 upfront. Phased dispatch:

1. **Phase 1** (parallel-safe, no deps): c1, c2, c3, c4, c5, c6.
2. **Phase 2** (after c1 closes): c7, c8.
3. **Phase 3** (after c7+c8 close): c9, c10, c11, c12.
4. **Phase 4** (after c9 closes): c13, c14, c15, c16.
5. **Phase 5** (after c1+c2+c3+c5 close, can overlap Phase 4): c17, c18, c19, c20, c21, c22.
6. **Phase 6** (after all prior close): c23, c24, c25.

### Acceptance — walker DONE when

- 13 `:Project {language: "swift"}` in graph; coverage CSV documents extractor status per (kit, ext).
- F-A and F-B smokes green on all 13 kits + `uw-ios-app` from both iMac and MacBook MCP.
- `curl https://gimle.ant013.work/mcp/` returns 406 from any network; write call without bearer returns 401.
- `:Author` nodes carry `email_hash` not raw `email`.
- Re-ingesting any kit does not double `count(:Symbol {group_id})`.

---

## Phase 2 — Project-Specialist Agent (post Audit-V1)

**Goal**: Make Gimle's 7 capabilities (6 named + new semantic search) **enforced by middleware** so agents reliably consult the graph before writing code. **Productization-grade design from day one** — sellable to any team beyond ourselves. iOS pilot first (UW HS Kits substrate ready), language-agnostic infrastructure supports Kotlin / Solidity / JS / Python recipes from G4 onwards.

**Why this is a separate phase**: A 2026-05-21 capability audit revealed Phase 1 closed at code-merge level but **operationally fragmented** — extractors merged but (a) live ingest only partially run, (b) 11/14 extractors write nodes without `group_id` linking so per-project queries return empty, (c) 4 extractors silently skip on missing input artefacts that no upstream pipeline produces, (d) dead-code detection was shallow single-symbol Periphery wrap (operator's UW iOS has 5-15-class dead clusters needing transitive analysis), (e) productization decision (G-D3) requires multi-tenant + security work not present today. Phase 2 G0 closes substrate gaps; G0f closes security gap for external pilot.

**Driver**: when `project-specialist` agent is asked to add a new module to ANY project, the resulting PR cites existing patterns, follows conventions, avoids dead clusters, introduces no duplicates, merges with ≤1 review round. Measurable via gaming-resistant metrics (G3).

**Wall-time**:

| Path | Optimistic | Conservative |
|---|---|---|
| **Internal** (G0 → G0.5 → G1 → G2 → G2.5 → G4; G3 ‖) | 9 weeks | 13 weeks |
| **External pilot** (+ G0f 2 weeks, can run ‖ G4) | 11 weeks | 15 weeks |

### Sprint sequence (rev3.2)

| ID | Sprint | Detail file | Wall-time | Depends on | Team | Status |
|----|--------|-------------|-----------|------------|------|--------|
| **G0** | Substrate readiness — 5 sub-sprints (G0a-e: ingest activation + schema linking fix + missing artefacts pipeline + **deep dead-code extractor** + verification matrix) | [`G-project-specialist-agent.md` §G0](superpowers/sprints/G-project-specialist-agent.md) | ~2-3 weeks | nothing | Board + Infra + Claude PE | ✅ G0b/c/d/e closed 2026-05-23 (UW iOS app 17/17 verified). G0a re-cascade for 4 kits deferred — bundled with G0.5 final validation cascade. |
| **G0.5** | Semantic embeddings layer (Neo4j vector + **Qodo-Embed-1-1.5B self-hosted**) — broken into 7 sequential slices, see [§G0.5 slice list](#g05-mega-sprint-detail--codex-team) | [`G-project-specialist-agent.md` §G0.5](superpowers/sprints/G-project-specialist-agent.md) | ~5-6 days | G0b/c/d/e ✅ | **Codex team** (CX CTO drives walker, CX PE implements, CX QA validates) | 🚧 Walker ready 2026-05-23 |
| **G1** | Capability audit + **4-column** comparative baseline (Gimle / SymDex / **Sourcegraph Amp** / grep) | [§G1](superpowers/sprints/G-project-specialist-agent.md) | ~1 week | G0.5 | Board + Claude | 📋 |
| **G2** | Recipe pilot — **Phase 1 synthetic + Phase 2 real PR corpus**, 3-arm A/B with N≥20 paired runs | [§G2](superpowers/sprints/G-project-specialist-agent.md) | ~2-3 weeks | G1 | Board + Claude | 📋 |
| **G2.5** | Domain-preflight middleware enforcement (AgentSpec-style runtime gate) | [§G2.5](superpowers/sprints/G-project-specialist-agent.md) | ~1-2 weeks | G2 | Claude PE | 📋 |
| **G3** | Measurement loop — gaming-resistant metrics, language-agnostic | [§G3](superpowers/sprints/G-project-specialist-agent.md) | ~1 week | G1 | Claude PE (‖ G2/G2.5) | 📋 |
| **G4** | Roll-out to 4 more recipe types (each includes `find_dead_code` pre-check) | [§G4](superpowers/sprints/G-project-specialist-agent.md) | ~2-3 weeks | G2.5 + G3 | Claude + CX | 📋 |
| **G0f** | **Security foundation** — multi-tenant auth + isolation + secret scrubbing + build sandbox + audit log (**gates external pilots only**, not internal use) | [§G0f](superpowers/sprints/G-project-specialist-agent.md) | ~2 weeks | G3 (can run ‖ G4) | Claude PE + security review | 📋 |
| **G5** | Optional extractors — scaffolding, test pattern, diagram, route discovery | [§G5](superpowers/sprints/G-project-specialist-agent.md) | ~2-3 weeks | G4 (on metric trigger) | per slice | 📦 |

**Parallelisation**: G3 ‖ G2/G2.5 (independent metrics infra vs recipe + middleware). G0f can run ‖ G4 if external pilot timing demands. G0 is critical-path mega-sprint; G0.5+ depend on it.

**Gating**:
- G0.5 starts only when G0e verification matrix passes: ≥13/15 testable extractors return reasonable project-linked node counts, AND both input-conditional extractors emit no errors when input absent
- G2 starts only if G1 audit shows ≥4/7 capabilities scoring `acceptable`
- **External pilot starts only after G0f closes** (internal use does not wait)

### G0 mega-sprint detail (= internal product readiness gate)

| Sub-sprint | What | Wall-time | Owner | Status |
|---|---|---|---|---|
| G0a | Activate ingest for remaining HS Kits + uw-ios-app | 1 day | Board | ⏸ deferred — re-cascade all 4 kits bundled with G0.5.6 final validation (uw-ios-app done 2026-05-23, 17/17 verified) |
| G0b | Schema linking fix — defense-in-depth: Python `ScopeTaggedWriter` (Layer 1) + Neo4j APOC trigger (Layer 2) | 7-8 days | Claude PE | ✅ done 2026-05-22 (PR #271 APOC + earlier ScopeTaggedWriter) |
| G0c | Missing artefacts pipeline — `prepare_swift_kit_artifacts.sh` runs Periphery + swiftinterface gen | 3-5 days | Claude PE | ✅ done 2026-05-22 (PR #294/#295 prepare scripts + iMac smoke 2026-05-23 with Periphery 2282 findings + 5 swiftinterface) |
| G0d | Deep dead-code extractor — transitive cluster + extension chain + SCC analysis + dynamic-dispatch root set extractor + fixture tests | 7-9 days | Claude PE | ✅ done 2026-05-23 (PR #286 G0d code + #287 idempotent finding_id + #288/#289 Symbol INDEX + #290/#291/#292 Neo4j 16g + #293 timeout 3600; UW dead_code = 5926 findings, 5926 edges) |
| G0e | Verification matrix — per-extractor sample queries (15 testable + 2 input-conditional) + cross-extractor coherence + multi-tenant isolation test | 2-3 days | Board + Claude | ✅ done 2026-05-23 (UW iOS app honest 17/17: all extractors return success=true with ok/missing_input outcome; see [[project_extractor_baseline_2026-05-22]]) |

**G0d is a genuine moat**: ranks dead findings by severity (critical = dead module / high = dead SCC ≥3 classes / medium = dead extension chain / low = single dead symbol), enriched with git_history-based safe_to_delete_score. No commercial competitor (Cursor / Sourcegraph / Cody / SymDex) does SCC-level dead detection at graph level for Swift today.

### G0 closed 2026-05-23

G0b/c/d/e closed. G0a deferred (bundled with G0.5 final cascade). All G0d future enhancements (symbol-level refactoring analyzer) captured in spec §G0d "Future enhancements" — separate post-G0d sprint.

### G0.5 mega-sprint detail — codex team

**Owner**: Codex team (CX CTO walker drives, CX PE implements, CX QA validates). Walker pattern per [[feedback_walker_sprint_protocol]] — one walker reads roadmap, spawns ONE child slice at a time via `parentId`, advances when child closes.

**Walker prompt**: scan §G0.5 slice list below top-to-bottom for first `Status: 📋`. Spawn child issue with `parentId = walker.id`, assignee CX CTO. Wait. On child close → mark slice `✅` in this roadmap + advance to next.

#### G0.5 slice list (sequential)

| Slice | What | Wall-time | Status | Acceptance |
|---|---|---|---|---|
| G0.5.1 | `EmbeddingBackend` abstraction — Python protocol class + dispatcher | 0.5 day | ✅ (2026-05-23) | `services/palace-mcp/src/palace_mcp/embeddings/backend.py` exports `EmbeddingBackend` Protocol with `embed_text(text: str) -> list[float]` + `embed_batch(texts) -> list[list[float]]`. Pluggable for Qodo/OpenAI/etc. Unit test for protocol contract. |
| G0.5.2 | Qodo-Embed-1-1.5B self-hosted runner | 1 day | ✅ (2026-05-23) | New service or in-process worker that loads HF model `Qodo/Qodo-Embed-1-1.5B` (1.5B params, Apache 2.0). HTTP endpoint OR direct Python embed. Latency budget ≤500ms per 200-token batch on M-series Mac. Implements `EmbeddingBackend`. |
| G0.5.3 | Neo4j vector index schema + UNIQUE setup | 0.5 day | ✅ (2026-05-23) | `CREATE VECTOR INDEX symbol_embedding_idx FOR (s:Symbol) ON (s.embedding) OPTIONS {indexConfig: {`vector.dimensions`: 1536, `vector.similarity_function`: 'cosine'}}`. Added to `extractors/foundation/schema.py` ConstraintSpec/IndexSpec. Tests assert index created. |
| G0.5.4 | Embedding population extractor — new `:Symbol` embedding writer | 1.5 day | ✅ (2026-05-23, 4d3b2f5) | New extractor `embedding_symbol` reads all `:Symbol` nodes for a project, batches by 64, calls `EmbeddingBackend.embed_batch`, writes vector to `s.embedding`. Idempotent (skip if hash matches). Registered in `extractors/registry.py`. `palace.ingest.run_extractor(name='embedding_symbol', project=...)` works. |
| G0.5.5 | MCP tool `palace.code.semantic_search` | 1 day | ✅ (2026-05-24, 467943f) | New MCP tool `palace.code.semantic_search(query: str, project: str, limit: int = 10)`. Generates query embedding → Neo4j `CALL db.index.vector.queryNodes('symbol_embedding_idx', limit, $query_vec)` → returns top-N symbols with cosine score + qname + file_path. Schema in `code/find_semantic.py` mirrors find_references pattern. |
| G0.5.6 | G0a closure: cascade all 5 projects with embedding_symbol | 0.5 day | 📋 | Re-run ingest on bitcoin-core, evm-kit, bitcoin-kit, dash-kit, uw-ios-app. Each gets symbol_index_swift + dead_code + embedding_symbol. Verify `MATCH (s:Symbol {group_id:"project/<slug>"}) WHERE s.embedding IS NOT NULL RETURN count(s)` > 100 per project (small kits may be 10-100, app 100K+). |
| G0.5.7 | Validation matrix + acceptance criteria | 1 day | 📋 | `palace.code.semantic_search(query="signature verification", project="uw-ios-app")` returns relevant symbols (manual top-3 review by operator). `semantic_search` returns < 1s on populated index. Doc in `docs/runbooks/semantic-search.md`. Final matrix posted in walker. |

**Walker advance protocol**: when child issue X closes (status=done):
1. Walker is woken via paperclip's parent-id mechanism (child has `parentId = walker.id`)
2. Walker edits this roadmap section: changes child's slice row Status `📋` → `✅` with merge commit ref
3. Walker scans next `📋` row → spawns new child with `parentId = walker.id`
4. Walker waits again
5. When all 7 slices `✅` → walker marks itself done + closes

Total wall-time per slice estimate: 5-6 days (matches sprint envelope).

### G0.6 product readiness hardening — clean runtime, semantic quality, server install

**Spec**:
`docs/superpowers/specs/2026-05-27-GIM-product-readiness-roadmap_spec.md`

**Owner model**: CEO/walker dispatches one slice per child issue. Each child
uses the normal Paperclip plan-first flow before implementation. The umbrella
spec is the routing contract; per-slice TDD/implementation plans are authored
inside child issues.

**Goal**: turn current GIM runtime smoke and semantic search into an installable,
repeatable product path:

- clean Docker/image reproducibility with no runtime source copy or manual pip
  patching;
- persistent Qodo/HF/uv/Neo4j cache strategy with safe cleanup defaults;
- semantic search quality: backend decision, deterministic ranking, filtering,
  snippet/context provider, and executable golden matrix;
- runtime golden smoke matrix across MacBook/Xcode and server-safe rows;
- powerful-server install/config profile and copy-paste-safe runbook.

#### G0.6 slice list

| Slice | What | Status | Depends On | Notes |
|---|---|---|---|---|
| PR0 | Product readiness contract lock | 📋 | none | Create Paperclip child DAG and close only by merged-to-`develop` SHA. |
| PR0a | Semantic-search architecture lock | 🚧 | PR0 | GIM-915. Lock current `find_semantic.py` / `semantic_contract.py` boundary; arch note at `docs/superpowers/specs/2026-05-27-GIM-915-semantic-search-arch-lock.md`. |
| PR1 | Clean Docker image reproducibility | 📋 | GIM-856, PR0 | Digest/pinned build, frozen deps, fresh-host scratch rebuild, no manual runtime patching. |
| PR2 | Persistent ML dependency and model cache strategy | 📋 | PR1 | Qodo/HF/uv/Neo4j cache env contract, local-only fail-fast, cleanup retention levels. |
| PR3a | Semantic candidate backend decision | 📋 | PR0a | Dense vs sparse vs hybrid candidate retrieval decision with dev-matrix evidence. |
| PR3 | Semantic ranking contract | 📋 | PR3a | Deterministic score formula, metrics, rank explanations, stable ordering tests. |
| PR4 | Semantic filtering contract | 📋 | PR3 | Default first-party filtering plus explicit expert cross-project/scope search. |
| PR5 | Snippet/context provider hardening | 📋 | PR0a, PR3 | Commit-scoped bounded snippets using safe path resolution. |
| PR6 | Machine-readable golden matrix | 📋 | PR0a, PR3, PR4, PR5 | Mandatory/advisory/no-answer rows, metrics, holdout split, nonzero exit on failures. |
| PR7 | Runtime golden smoke matrix | 📋 | GIM-856, PR1, PR2 | UW app + Swift kit + bounded embedding rows with JSON/markdown evidence. |
| PR8 | Server install/config profile | 📋 | PR1, PR2 | Linux/Docker/Neo4j/cache/repo-mount profiles, secure defaults, no broad secret mounts. |
| PR9 | Stable operator runbook | 📋 | PR6, PR7, PR8 | Install/start/cache/repo/smoke/semantic/debug/cleanup path without chat history. |
| PR10 | End-to-end product readiness gate | 📋 | PR6, PR7, PR8, PR9 | Redacted final evidence bundle and go/no-go report. |

**Parallelism rule**: runtime image/config slices PR1/PR2/PR8 share files and
need one writer at a time. Semantic behavior slices PR0a/PR3a/PR3/PR4/PR5 share
`find_semantic.py`/contracts and stay on one Python owner lane. PR6, PR7, and
PR9 can run when their dependencies are closed.

### G0 starts immediately (does not wait for Audit-V1 close)

G0 is independent of Audit-V1 — it fixes infrastructure already merged. G0a executes today via Board. G0.5 onwards waits for Audit-V1 to free Claude PE capacity (~July 2026 at S2.3 close).

### Decisions captured 2026-05-21 (rev3.2: 13 decisions, all closed)

| ID | Decision | Operator answer |
|---|---|---|
| G-D1 | Recipe hard-coded per role or dynamic? | hard-coded for v1 |
| G-D2 | Pilot task fake or real? | Phase 1 synthetic + Phase 2 real PR corpus |
| G-D3 | Productization explicit goal? | YES — generic from day one |
| G-D4 | Middleware enforcement? | YES — G2.5 strict gate |
| G-D5 | Full breadth or narrow to 3 moats? | FULL BREADTH |
| G-D6 | SymDex companion or build own semantic? | BUILD OWN |
| G-D7 | G0 size — single sprint or full substrate? | FULL SUBSTRATE (5 sub-sprints) |
| G-D8 | Deep dead-code algorithm | TRANSITIVE + extension chain + SCC + dynamic-dispatch root set |
| G-D9 | **Embedding model** | **Qodo-Embed-1-1.5B self-hosted (Apache 2.0)** |
| G-D10 | **GDS licensing for productization** | **Use GDS Community now; swap to own Johnson's SCC before first paying client** |
| G-D11 | **G0d split for non-Xcode clients** | **No split — Periphery mandatory** (Swift project ⇒ macOS guaranteed) |
| G-D12 | **G0b enforcement layer** | **Defense-in-depth: Python wrapper + Neo4j APOC trigger** |
| G-D13 | **Security timing** | **G0f gates external pilots only; internal use unblocked** |

### Industry references (selected — full list in sprint detail)

- Recipe enforcement: [AgentSpec — arxiv 2503.18666](https://arxiv.org/abs/2503.18666); [Cursor rules](https://cursor.com/docs/rules)
- Symbol-precise retrieval: [Sourcegraph Cody](https://sourcegraph.com/blog/anatomy-of-a-coding-assistant); [Aider repo-map](https://aider.chat/docs/repomap.html)
- Code embedding: [Qodo-Embed-1-1.5B (Apache 2.0)](https://huggingface.co/Qodo/Qodo-Embed-1-1.5B); [Neo4j vector search](https://neo4j.com/developer/genai-ecosystem/vector-search/)
- Dead-code baseline: [Periphery](https://github.com/peripheryapp/periphery); [Neo4j GDS — SCC](https://neo4j.com/docs/graph-data-science/current/algorithms/strongly-connected-components/); [Meta SCARF — FSE 2023](https://dl.acm.org/doi/10.1145/3611643.3613871)
- Comparable product: [SymDex](https://github.com/husnainpk/SymDex) — patterns adopted + anti-patterns avoided; [Sourcegraph Amp](https://amplifilabs.com/post/sourcegraph-amp-agent-accelerating-code-intelligence-for-ai-driven-development) — closest productized comparable
- Structured navigation: [SWE-agent NeurIPS 2024](https://proceedings.neurips.cc/paper_files/paper/2024/file/5a7c947568c1b1328ccc5230172e1e7c-Paper-Conference.pdf)

---

### Archived Phase 2-6 backlog

Moved to [`docs/roadmap-archive.md`](roadmap-archive.md) in rev2
(OPUS-LOW-1: HTML comments are invisible to search/grep/agent tools).
Re-activate individual rows via S6+ intake protocol.

<!-- rev3 (2026-05-07): inline HTML-commented duplicate of Phase 2-6
     fully removed; canonical content lives in docs/roadmap-archive.md.
     This closes OPUS-LOW-1 — search/grep/agent tools no longer need
     to peek inside HTML comments to see archived rows. -->


---

## Parallelization rules

Per `feedback_parallel_team_protocol.md` (operator-codified 2026-05-03).

1. **No file overlap** between active parallel slices on the same shared file.
2. **One issue = one team end-to-end.** Don't mix Claude and CX agents within a single slice's phase chain.
3. **Smoke-first** before introducing new parallel patterns.
4. **Forbidden if both touch any of**:
   - same extractor under `services/palace-mcp/extractors/*`
   - same fixture under `services/palace-mcp/tests/extractors/fixtures/*`
   - `docker-compose.yml`, `.env.example`, `CLAUDE.md`
   - same spec file or plan file under `docs/superpowers/specs|plans/`
5. **Additive shared-file edits** (registry registration line, compose mount line, env-var line) are tolerated when both teams promise additive-only changes; merge-order conflicts resolve trivially.

## Atomic-handoff discipline

Per `paperclips/fragments/profiles/handoff.md` (PR #77, `9262aca`):

> ALWAYS hand off by PATCHing `status + assigneeAgentId + comment` in one API call, then GET-verify the assignee; @mention-only handoff is invalid.

Watchdog Phase 1 (GIM-181, merged `f2f05c4`) landed the **detective** half — alerts when an agent fails this rule. Three Opus nudge follow-ups tracked as GIM-183.

---

## Update protocol

When a slice merges to `develop`:

1. Move the row from 🚧 / 📋 to ✅.
2. If a dependent unblocks → annotate that row.
3. Promote next CX or next Claude item one position up if its predecessor closed.
4. Commit roadmap update on a small `docs(roadmap):` PR or alongside the merging slice's spec/plan PR.

Avoid editing during active phase chains — wait for the slice merge so the file matches the latest develop tip.

---

## Open questions

- **Audit-V1 decision points** — see `Audit-V1 — first product release` section above for AV1-D1..AV1-D7 (rev2 adds D6 token budget + D7 blind spot acceptance). Resolve pre-S0 start.
- **Phase 1 real-query validation** — launch-critical rows are merged; S4 smoke is the de facto launch validation.
- **LLM infrastructure** — 6 extractors require LLM. Decision per AV1-D4: post-v1.
- **Archived Phase 2-6 backlog** — moved to `docs/roadmap-archive.md` (rev2). Re-activate via S6+ intake protocol.
- ~~GIM-218 contingency~~ (rev2) — **closed in rev4**: GIM-218 merged `603c840` 2026-05-07; version-skew shipped, no blind-spot fallback needed.
