# Roadmap Archive — Phase 2-6

**Extracted**: 2026-05-06 (rev2 of audit-v1 plan, OPUS-LOW-1).
**Reason**: HTML comments in `roadmap.md` were invisible to grep/search/agent tools.
**Reactivation**: per S6+ intake protocol in `roadmap.md`.

Superseded 2026-05-06 by Audit-V1 plan. Slices not yet started are paused;
in-flight slices (GIM-216 #32, GIM-218 #39) continue and fold into v1 as
data-providers.

---

## Phase 2 — Post-launch deep analysis

Reference: `docs/research/extractor-library/` (2026-04-18 brainstorm, 9 parallel research deep-dives over 45 candidate extractors).

**No Phase 2 slice starts until Phase 1 closes.** Order within each category is not strict — operator picks based on actual UW analysis needs that surface after launch.

**Cross-cutting prerequisites within Phase 2**:
- Item **#22 Git History Harvester** must merge before any historical extractor (#11/#12/#26/#32/#43/#44).
- All other items consume the Symbol Index (Phase 1 output) and may run in any order modulo team allocation rules.

### 2.1 Structural (13 items)

| # | Name | Team | LLM | Tool stack | Status |
|---|------|------|:---:|------------|--------|
| 1 | Architecture Layer Extractor | Claude | — | tree-sitter + modules-graph-assert + ArchUnit + Package.swift | deferred |
| 2 | Symbol Duplication Detector | Claude | — | jscpd + UniXcoder/CodeBERT embeddings + semhash | deferred |
| 3 | Reactive Dependency Tracer | CX | — | swift-syntax + detekt AST + Compose Stability | deferred |
| 4 | KMP Platform-Bridge Extractor | CX | — | tree-sitter-kotlin + SKIE + swift-syntax | deferred (waits UW KMP adoption) |
| 5 | Dependency Surface Extractor | Claude | — | dep-analysis-gradle + spmgraph + Package.resolved parser | merged (GIM-191) |
| 25 | Build System Extractor | CX | — | Gradle Tooling API + SwiftPM PackageDescription + Bazel aquery | deferred |
| 27 | Public API Surface Extractor | CX | — | Kotlin BCV + Swift .swiftinterface | merged (GIM-190) |
| 31 | Cross-Module Contract Extractor | CX | — | Kotlin BCV + swift-public-api-diff + oasdiff | merged (GIM-192) |
| 33 | Dead Symbol & Binary Surface | CX | — | Periphery + Reaper SDK + CodeQL | merged (GIM-193) |
| 36 | Network Schema & API Contract | Claude | — | oasdiff + Buf CLI + graphql-inspector | deferred |
| 39 | Cross-Repo Version Skew | Claude | — | Gradle Tooling API + Renovate data + OWASP Dep-Check | GIM-218 (pending) |
| 41 | SCIP/LSIF Precise Symbol Resolver | CX | — | scip-* per-language | = Phase 1 |
| 45 | Inter-Module Event Bus | CX | — | semgrep + tree-sitter + SourceKit-LSP | deferred |

### 2.2 Conventional (9 items)

| # | Name | Team | LLM | Tool stack | Status |
|---|------|------|:---:|------------|--------|
| 6 | Coding Convention Extractor | CX | — | SwiftSyntax + Harmonize + Konsist + detekt + semgrep | deferred |
| 7 | Error Handling Policy Extractor | Claude | — | semgrep + ast-grep + detekt | deferred |
| 8 | Testability/DI Pattern Extractor | CX | — | Konsist + Harmonize + detekt + MockK/Mockito patterns | deferred |
| 9 | Localization & Accessibility Extractor | CX | — | xcstrings parser + Android Lint + Google ATF | deferred |
| 10 | Domain Naming & Glossary Extractor | Claude | LLM | tree-sitter + Graphiti entity + sentence-transformers | deferred |
| 28 | Coverage-Gap Extractor | CX | — | Kover + JaCoCo + Xcode llvm-cov + xcresult | deferred |
| 29 | Resource/Asset Usage Extractor | CX | — | Android Lint UnusedResources + FengNiao + SwiftGen | deferred |
| 37 | Documentation Coverage Extractor | CX | — | Dokka 2.2.0 + swift-doc-coverage + DocC | deferred |
| 38 | Test Smell & Flaky Test Extractor | CX | — | tsDetect ports + FlakyLens + Develocity | deferred |

### 2.3 Historical (6 items + #22 prereq)

| # | Name | Team | LLM | Tool stack | Status |
|---|------|------|:---:|------------|--------|
| 22 | Git History Harvester (prereq) | Claude | — | pygit2 | GIM-186 spec ready |
| 11 | Decision History Extractor | Claude | LLM | pygit2 + GitHub GraphQL + SZZ + ADR parser | deferred |
| 12 | Migration Signal Extractor | CX | — | SwiftSyntax + detekt @Deprecated + semgrep + CodeQL | deferred |
| 26 | Bug-Archaeology Extractor | Claude | LLM | GitHub Issues + LLM4SZZ + pygit2 blame | deferred |
| 32 | Code Ownership Extractor | Claude | — | pygit2 blame + code-maat + hercules | GIM-216 (in progress) |
| 43 | PR Review Comment Knowledge Extractor | Claude | LLM | GitHub GraphQL + LLM categorization | deferred |
| 44 | Code Complexity x Churn Hotspot | Claude | — | radon + lizard + git churn | merged (GIM-195) |

### 2.4 Semantic (6 items)

| # | Name | Team | LLM | Tool stack | Status |
|---|------|------|:---:|------------|--------|
| 13 | Invariant & Contract Extractor | Claude | — | tree-sitter + semgrep + Z3 (optional) | deferred |
| 14 | Lifecycle & State Extractor | CX | — | swift-syntax + detekt + Compose state graph | deferred |
| 15 | Domain Edge-Case Extractor | Claude | LLM | semgrep + LLM | deferred |
| 16 | Read/Write Path Asymmetry | Claude | — | tree-sitter + AST diff | deferred |
| 34 | Code Smell Structural | Claude | — | radon + lizard + detekt CodeSmell | deferred |
| 40 | Crypto Domain Model | Claude | — | semgrep custom rules | S2 v1 (audit-v1) |

### 2.5 Contextual (7 items)

| # | Name | Team | LLM | Tool stack | Status |
|---|------|------|:---:|------------|--------|
| 17 | Hot-Path Profiler | CX | — | Instruments + Perfetto + xctrace | deferred |
| 18 | Concurrency Ownership Map | CX | — | swift-syntax actor + detekt coroutine scope | deferred |
| 19 | Feature Flag & Config | Claude | — | semgrep + custom flag-detector | deferred |
| 20 | Logging Policy | Claude | — | semgrep + AST | deferred |
| 30 | Performance Pattern | Claude | — | tree-sitter | deferred |
| 35 | Taint & PII Data-Flow | Claude | LLM | CodeQL + semgrep | deferred |
| 42 | Build Reproducibility | CX | — | Develocity build cache + cacheable_verified | deferred |

### Tally

- **CX**: 18 extractors. **Claude**: 22 extractors.
- **LLM-required**: 6 unique (#10, #11, #15, #26, #35, #43). All Claude.

---

## Phase 3 — Cross-language bridges

| # | Bridge | Team | Deps |
|---|--------|------|------|
| C1 | SKIE Swift-Kotlin (KMP) | CX | Phase 1 + UW KMP |
| C2 | Solidity ABI-TS/JS | Claude | Phase 1 + Solidity USE v2 |
| C3 | Anchor IDL-TS/JS | Claude | Phase 1 + Anchor extractor |
| C4 | EVM contract-contract | Claude | Phase 1 + Solidity USE v2 |

## Phase 4 — Beyond UW

| # | Slice | Team | Trigger |
|---|-------|------|---------|
| B1 | Solidity USE v2 | Claude | EVM data-flow queries needed |
| B2 | iOS Swift v2 (Storyboards/Core Data) | CX | UW uses them |
| B3 | Android Slice 2-lite | CX | R.string cross-ref needed |
| B4-B8 | Python/TS/Anchor/FunC/Rust | varies | ecosystem expansion |

## Phase 5 — Non-extractor product slices

| # | Slice | Team | Status |
|---|-------|------|--------|
| D1 | `palace.code.semantic_search` | Claude | queued |
| D2 | `test_impact` opt-in filter | Claude | backlog |
| D3 | Watchdog Phase 2 auto-repair | Claude | deferred |
| D4-D8 | Various infra | Claude | backlog |

## Phase 6 — Meta / infrastructure

| # | Slice | Team | Status |
|---|-------|------|--------|
| E1-E2 | Auto-deploy (merge + release-cut) | Claude | queued |
| E3 | Roadmap file | Board | live |
| E4-E6 | Various meta | varies | backlog |
