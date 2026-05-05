# Gimle-Palace Team Roadmap

**Last updated**: 2026-05-04
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
| C4 | Git History Harvester (Extractor #22) — Phase 2 prereq | 📋 spec+plan ready | GIM-186 | `services/palace-mcp/src/palace_mcp/extractors/git_history/`, `services/palace-mcp/tests/extractors/{unit,integration,fixtures}/`, runbook | Foundation for 6 historical extractors (#11/#12/#26/#32/#43/#44). Spec rev2 (1255 LOC) + plan (2430 LOC, 13 TDD tasks) committed on `feature/GIM-186-git-history-harvester`. **Awaiting Claude CTO availability after GIM-182 closes** — no team-chain trigger yet. |
| C5 | iMac post-merge auto-deploy | 📋 | TBD | `paperclips/scripts/imac-deploy-listener.{sh,plist}`, webhook handler | Removes manual `imac-deploy.sh` step after every merge |
| C6 | `palace.code.semantic_search` | 📋 | TBD | `services/palace-mcp/src/palace_mcp/code/semantic_search.py` | Deferred Slice 5 of original USE-BUILT; vector or hybrid search composite |

C2 (GIM-182) is now ✅. C3/C4/C5/C6 are independent and not launch-blocking. C4 (GIM-186) is fully spec'd + plan'd; ready for team-chain trigger when CTO frees for the historical-extractor lane.

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

## Phase 2 — Post-launch deep analysis

Reference: `docs/research/extractor-library/` (2026-04-18 brainstorm, 9 parallel research deep-dives over 45 candidate extractors).

**No Phase 2 slice starts until Phase 1 closes.** Order within each category is not strict — operator picks based on actual UW analysis needs that surface after launch.

**Cross-cutting prerequisites within Phase 2**:
- Item **#22 Git History Harvester** must merge before any historical extractor (#11/#12/#26/#32/#43/#44).
- All other items consume the Symbol Index (Phase 1 output) and may run in any order modulo team allocation rules in §6.

### 2.1 Structural (13 items)

| # | Name | Team | LLM | Tool stack | Status |
|---|------|------|:---:|------------|--------|
| 1 | Architecture Layer Extractor | Claude | — | tree-sitter + modules-graph-assert + ArchUnit + Package.swift | 📦 |
| 2 | Symbol Duplication Detector | Claude | — | jscpd + UniXcoder/CodeBERT embeddings + semhash | 📦 |
| 3 | Reactive Dependency Tracer | CX | — | swift-syntax + detekt AST + Compose Stability | 📦 |
| 4 | KMP Platform-Bridge Extractor | CX | — | tree-sitter-kotlin + SKIE + swift-syntax | 📦 (waits UW KMP adoption) |
| 5 | Dependency Surface Extractor | Claude | — | dep-analysis-gradle + spmgraph + Package.resolved parser | 📦 |
| 25 | Build System Extractor | CX | — | Gradle Tooling API + SwiftPM PackageDescription + Bazel aquery | 📦 |
| 27 | Public API Surface Extractor | CX | — | Kotlin BCV `.api` dumps + Swift `.swiftinterface` primary + optional `swift-api-digester` diagnostics + SKIE overlay | ✅ GIM-190 / PR #88 merged + iMac deployed at `2a96786`; `public_api_surface` registry verified |
| 31 | Cross-Module Contract Extractor | CX | — | Kotlin BCV + swift-public-api-diff + oasdiff | 📋 GIM-192 launched for CX spec formalization; consumes #27 PublicApiSurface/PublicApiSymbol |
| 33 | Dead Symbol & Binary Surface | CX | — | Periphery + Reaper SDK + CodeQL | 🚧 spec draft (`docs/superpowers/specs/2026-05-04-roadmap-33-dead-symbol-binary-surface.md`) |
| 36 | Network Schema & API Contract | Claude | — | oasdiff + Buf CLI + graphql-inspector | 📦 |
| 39 | Cross-Repo Version Skew | Claude | — | Gradle Tooling API + Renovate data + OWASP Dep-Check | 📦 (deps #5) |
| 41 | SCIP/LSIF Precise Symbol Resolver | CX | — | scip-* per-language | 🚧 = Phase 1 in disguise |
| 45 | Inter-Module Event Bus | CX | — | semgrep + tree-sitter + SourceKit-LSP | 📦 |

### 2.2 Conventional (9 items)

| # | Name | Team | LLM | Tool stack | Status |
|---|------|------|:---:|------------|--------|
| 6 | Coding Convention Extractor | CX | — | SwiftSyntax + Harmonize + Konsist + detekt + semgrep | 📦 |
| 7 | Error Handling Policy Extractor | Claude | — | semgrep + ast-grep + detekt | 📦 |
| 8 | Testability/DI Pattern Extractor | CX | — | Konsist + Harmonize + detekt + MockK/Mockito patterns | 📦 |
| 9 | Localization & Accessibility Extractor | CX | — | xcstrings parser + Android Lint + Google ATF | 📦 (overlaps Slice 2-lite — see B3) |
| 10 | Domain Naming & Glossary Extractor | Claude | ✅ | tree-sitter + Graphiti entity + sentence-transformers | 📦 |
| 28 | Coverage-Gap Extractor | CX | — | Kover + JaCoCo + Xcode llvm-cov + xcresult | 📦 |
| 29 | Resource/Asset Usage Extractor | CX | — | Android Lint UnusedResources + FengNiao + SwiftGen | 📦 |
| 37 | Documentation Coverage Extractor | CX | — | Dokka 2.2.0 + swift-doc-coverage + DocC | 📦 |
| 38 | Test Smell & Flaky Test Extractor | CX | — | tsDetect ports + FlakyLens + Develocity | 📦 |

### 2.3 Historical (6 items + #22 prereq)

| # | Name | Team | LLM | Tool stack | Status |
|---|------|------|:---:|------------|--------|
| 22 | Git History Harvester (**prereq**) | Claude | — | pygit2 | 📦 (must precede 11/12/26/32/43/44) |
| 11 | Decision History Extractor | Claude | ✅ | pygit2 + GitHub GraphQL + SZZ + ADR parser | 📦 |
| 12 | Migration Signal Extractor | CX | — | SwiftSyntax + detekt @Deprecated + semgrep + CodeQL | 📦 |
| 26 | Bug-Archaeology Extractor | Claude | ✅ | GitHub Issues + LLM4SZZ + pygit2 blame | 📦 |
| 32 | Code Ownership Extractor | Claude | — | pygit2 blame + code-maat + hercules | 📦 |
| 43 | PR Review Comment Knowledge Extractor | Claude | ✅ | GitHub GraphQL + LLM categorization | 📦 |
| 44 | Code Complexity × Churn Hotspot | Claude | — | radon + lizard + git churn | 📦 |

### 2.4 Semantic (6 items)

| # | Name | Team | LLM | Tool stack | Status |
|---|------|------|:---:|------------|--------|
| 13 | Invariant & Contract Extractor | Claude | — | tree-sitter + semgrep + Z3 (optional) | 📦 |
| 14 | Lifecycle & State Extractor | CX | — | swift-syntax + detekt + Compose state graph | 📦 |
| 15 | Domain Edge-Case Extractor | Claude | ✅ | semgrep + LLM | 📦 |
| 16 | Read/Write Path Asymmetry | Claude | — | tree-sitter + AST diff | 📦 |
| 34 | Code Smell Structural | Claude | — | radon + lizard + detekt CodeSmell | 📦 |
| 40 | Crypto Domain Model | Claude | — | semgrep custom rules (addresses/checksums/decimals) | 📦 |

### 2.5 Contextual (7 items)

| # | Name | Team | LLM | Tool stack | Status |
|---|------|------|:---:|------------|--------|
| 17 | Hot-Path Profiler | CX | — | Instruments + Perfetto + xctrace | 📦 |
| 18 | Concurrency Ownership Map | CX | — | swift-syntax actor + detekt coroutine scope | 📦 |
| 19 | Feature Flag & Config | Claude | — | semgrep + custom flag-detector | 📦 |
| 20 | Logging Policy | Claude | — | semgrep + AST | 📦 |
| 30 | Performance Pattern | Claude | — | tree-sitter | 📦 |
| 35 | Taint & PII Data-Flow | Claude | ✅ | CodeQL + semgrep | 📦 |
| 42 | Build Reproducibility | CX | — | Develocity build cache + cacheable_verified | 📦 |

### 2.6 Support / cross-cutting (5)

| # | Name | Team | LLM | Note |
|---|------|------|:---:|------|
| 21 | Symbol Index Extractor | CX | — | = Phase 1; partially done |
| 22 | Git History Harvester | Claude | — | listed in 2.3 |
| 23 | Test Harness Adapter | Claude | — | pytest/junit/xctest output normalizer |
| 24 | AST Pattern Matcher | Claude | — | semgrep wrapper + custom matchers |
| 41 | SCIP/LSIF Precise Resolver | CX | — | = Phase 1; partially done |

### 2.7 Tally

- **CX assignments**: 18 extractors (compiled-language native tooling-heavy)
- **Claude assignments**: 22 extractors (Python orchestration, LLM, embedding, git history)
- **Done or in-flight**: 5 (= Phase 1 work, all CX-style)

LLM-required: 7 (#10, #11, #15, #26, #35, #43 + #15 again — 6 unique). All Claude. Concentrates LLM cost on one team's infra.

---

## Phase 3 — Cross-language bridges (`:BRIDGES_TO`)

Per ADR D1 — bridges are extractors that build cross-language `:BRIDGES_TO` edges from existing per-language symbol graphs. **Phase 3 starts when both languages of a given bridge are complete in Phase 1 + Phase 2.**

| # | Bridge | Source ↔ Target | Source-of-truth artefact | Team | Deps |
|---|--------|----|------|------|------|
| C1 | SKIE Swift ↔ Kotlin (KMP) | UW-iOS ↔ UW-Android shared KMP modules | `*.kt` `expect`/`actual` + Swift extension declarations | CX | Phase 1 done + UW ships KMP shared modules |
| C2 | Solidity ABI ↔ TS/JS | dApp frontend ↔ smart contract calls | contract `*.abi.json` + TS `import` statements | Claude | Phase 1 done + GIM-104 + Solidity USE v2 |
| C3 | Anchor IDL ↔ TS/JS | Solana dApp ↔ Solana program | Anchor-generated IDL + TS `Program(idl)` references | Claude | Phase 1 done + GIM-104 + Anchor IDL extractor (B6) |
| C4 | EVM contract ↔ EVM contract (proxy/impl) | Inheritance + delegatecall analysis | Solidity AST + storage layout | Claude | Phase 1 done + Solidity USE v2 |

---

## Phase 4 — Beyond UW (low priority unless UW expands)

Operator-flagged secondary stack per `project_palace_purpose_unstoppable.md`. Schedule only when UW analysis surface stops generating slice candidates.

| # | Slice | Team | Tool stack | Trigger |
|---|-------|------|------------|---------|
| B1 | Solidity USE-occurrences v2 | Claude | extends `scip_emit/solidity/`, slither AST | Operator requests data-flow queries on EVM contracts |
| B2 | iOS Swift v2 (Storyboards/xib + Core Data .xcdatamodeld) | CX | XML parser + xcdatamodeld parser | UW uses Storyboards or Core Data and operator requests |
| B3 | Android Slice 2-lite (Manifest + strings) | CX | XML parser | Operator requests `R.string` cross-ref queries |
| B4 | Python extractor cross-module type-flow | Claude | mypy `dmypy` + tree-sitter | Internal palace-mcp need only |
| B5 | TS/JS — JSX/TSX prop usage tracking | Claude | tree-sitter-tsx | Frontend dApp analysis needed |
| B6 | Anchor IDL extractor (Solana) | Claude | custom IDL JSON parser | UW expands to Solana |
| B7 | FunC extractor (TON) | Claude | tree-sitter-func + custom emitter | UW expands to TON |
| B8 | Rust general extractor | CX | scip-rust / rust-analyzer SCIP | UW or operator needs systems-Rust analysis |

---

## Phase 5 — Non-extractor product slices

Product features and infra that are not extractors per se. Some launch-blocking, others post-launch.

| # | Slice | Team | Status | Trigger / Phase |
|---|-------|------|--------|-----------------|
| D1 | `palace.code.semantic_search` | Claude | 📋 (= C4 in §3) | Phase 1 parallel infra |
| D2 | `palace.code.test_impact` opt-in post-filter | Claude | 📦 | Phase 2; small followup to GIM-98 |
| D3 | Watchdog Phase 2 auto-repair | Claude | ⏸ | After GIM-181 + 7 days zero false-positive |
| D4 | Webhook async-signal v2 | Claude | 📦 | If GIM-48 pattern reproduces |
| D5 | `code_composite.py` → package refactor | Claude | ⏸ | After 2nd composite tool ships |
| D6 | Watchdog detector — missing QA evidence | Claude | 📦 | After GIM-127 fabrication pattern reproduces |
| D7 | Watchdog detector — missing branch-spec gate | Claude | 📦 | Sibling to D6 |
| D8 | iMac post-merge auto-deploy | Claude | 📋 (= C3 in §3) | Phase 1 parallel infra |

---

## Phase 6 — Meta / infrastructure

| # | Slice | Team | Status | Trigger |
|---|-------|------|--------|---------|
| E1 | iMac post-merge auto-deploy | Claude | 📋 | = D8 / C3 |
| E2 | iMac AGENTS.md auto-deploy on release-cut | Claude | 📦 | Symmetric to imac-agents-deploy.sh; auto-trigger |
| E3 | This roadmap file (`docs/roadmap.md`) | Board | ✅ | Always live; updated on every slice merge |
| E4 | Drift-detection weekly Action (GIM-181 role taxonomy) | Claude | 📦 | If hire frequency exceeds 1 / 2 weeks |
| E5 | `palace.code.manage_adr` writable v2 | Claude | 📦 | After Phase 1 |
| E6 | CX team — hire BlockchainEngineer + SecurityAuditor | Board | 📦 | Phase 4 (smart contract / Rust work needs them) |

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

- **Phase 1 real-query validation** — launch-critical implementation rows are merged; operator still decides when "launch" is real. Suggested gate: at least 3 useful queries on real UW codebase produce results matching expectations (≥1 each on iOS / Android / EVM contract).
- **Phase 2 ordering inside categories** — operator selected #27 Public API Surface Extractor for CX spec brainstorm on 2026-05-04; it closed as GIM-190. Next CX item is #31 Cross-Module Contract Extractor via GIM-192. Broader ordering remains demand-driven.
- **#22 Git History promotion** — triggered by first historical-extractor request. Currently 📦.
- **LLM infrastructure** — 6 Claude extractors require LLM. Ollama deploy + cost monitoring is a separate infra slice (not yet scheduled).
- **CX queue refresh** — completed 2026-05-04 after GIM-190 merged and iMac deploy verified; active CX docs lane is #31 Cross-Module Contract Extractor spec formalization (GIM-192).
