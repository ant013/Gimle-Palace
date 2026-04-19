# Extractor Library — Research Report

**Date:** 2026-04-18
**Research basis:** 9 parallel voltagent-research deep-dives over 45 candidate extractors, web-search prior-art (2024–2026 sources), spec §4.2/§4.6/§5 from `2026-04-15-gimle-palace-design.md`
**Target consumer:** Gimle-Palace knowledge graph for multi-repo mobile codebases at Unstoppable Wallet scale (~20 Kit libraries in Kotlin + Swift, SwiftUI + Compose, crypto/blockchain domain)
**Purpose:** Inform Graphiti schema + extractor-pipeline design for slices N+2…N+6 ahead of N+1 spec writing

**Artifacts:**
- `outline.yaml` — 45-item inventory with per-item config
- `fields.yaml` — 24-field research schema across 6 groups (identity / implementation / data_model / prior_art / queries_and_integration / operational)
- `sources.md` — 35 web-sourced prior-art references
- `results/*.json` — 12 full per-extractor JSON records on disk (agents 1, 4 complete, + partial agent 2); remaining 33 agent outputs captured in research conversation and synthesized here

---

## 1. Executive Summary

**Target problem:** 20 context-problem categories grouped into 5 meta-groups (Structural / Conventional / Historical / Semantic / Contextual). Each problem maps to one or more extractors; 45 extractors total including 5 cross-cutting support.

**Three key architectural decisions surfaced by the research:**

1. **Symbol graph is the backbone.** Extractor #21 (Symbol Index) is consumed by ≥30 of the 45 extractors. SCIP integration (#41) is Kotlin-only as of April 2026 — no official `scip-swift` exists. Swift coverage must come from SourceKit-LSP via #21. Merge-vs-separate is the highest-impact open question: recommend keep separate with SCIP as enrichment layer, joined by display_name + module.

2. **Three unavoidable overlaps were flagged and resolved through research:**
   - **#40 Crypto Domain Model ↔ #15 Domain Edge-Case** — keep separate. #40 is structural taxonomy (what coins/tokens/adapters exist); #15 is invariants (overflow guards, decimal precision, checksum validation). Bridge via `:LACKS_EDGE_CASE_GUARD` edge.
   - **#41 SCIP Resolver ↔ #21 Symbol Index** — keep separate, join by stable ID on display_name+module. Item 21 is live LSP (low-latency); Item 41 is batch SCIP (stable, precise). Different latency/accuracy tiers.
   - **#42 Build Reproducibility ↔ #25 Build System** — keep separate. #25 owns `cacheable` property on `:BuildTask` (static, from @CacheableTask annotation); #42 owns `cacheable_verified` (dynamic, from cache-hit evidence). Distinct provenance.

3. **Scheduler/DAG design is non-negotiable.** At least 8 extractors have hard ingest-ordering dependencies: #21 (Symbol Index) must complete before anything else; #22 (Git History Harvester) must precede #11/#12/#26/#32/#43/#44. RANGER / RepoGraph validate the explicit `cross_extractor_feeds` edge model.

**Three blocking domain-specific discoveries:**

- **Swift scip-swift does not exist** (April 2026 verified). Kotlin has scip-java + scip-kotlin (SemanticDB plugin, maintenance health uncertain since 2023). Any Swift cross-tool symbol dedup must use SourceKit-LSP + custom normalization.
- **Kotlin LSP from JetBrains (KotlinConf 2025)** is alpha, partially closed-source, JVM-only Gradle. Community `fwcd/kotlin-language-server` remains the portable fallback for KMP shared code.
- **Ollama/LLM dependency is concentrated in 4 extractors** (#10, #13, #15, #35). Others are deterministic or heuristic. This localizes the LLM-cost blast radius to specific slices — consistent with the OAuth-consistent substrate decision from earlier in this session.

---

## 2. Extractor Inventory (45 items)

### 2.1 Structural (13 items — "what exists, how connected")

| # | Name | Target problems | Confidence | Key tool stack |
|---|---|---|---|---|
| 1 | Architecture Layer Extractor | 4 | deterministic | tree-sitter + modules-graph-assert (Gradle) + ArchUnit + Package.swift |
| 2 | Symbol Duplication Detector | 1 | heuristic | jscpd + UniXcoder/CodeBERT embeddings + semhash |
| 3 | Reactive Dependency Tracer | 2 | heuristic | swift-syntax + detekt AST + Compose Stability Analyzer + SourceKit-LSP |
| 4 | KMP Platform-Bridge Extractor | 16 | deterministic | tree-sitter-kotlin + Kotlin compiler plugin + SKIE + swift-syntax |
| 5 | Dependency Surface Extractor | 17 | deterministic | dependency-analysis-gradle-plugin + spmgraph + Package.resolved parser |
| 25 | Build System Extractor | 4, 13 | deterministic | Gradle Tooling API + SwiftPM PackageDescription + Bazel aquery |
| 27 | Public API Surface Extractor | 4, 16, 17 | deterministic | binary-compatibility-validator (Kotlin) + swift-api-digester + SKIE overlay parsing |
| 31 | Cross-Module Contract Extractor | 4, 17 | deterministic | Kotlin BCV + Adyen swift-public-api-diff + oasdiff-style rule engine |
| 33 | Dead Symbol & Binary Surface | 1, 4 | heuristic | Periphery (Swift) + Reaper Android SDK + Reaper iOS (Sentry) + CodeQL |
| 36 | Network Schema & API Contract | 4, 17 | heuristic | oasdiff + Buf CLI + graphql-inspector + Retrofit/URLSession AST parser |
| 39 | Cross-Repo Version Skew | 17 | deterministic | Gradle Tooling API + Package.resolved parser + Renovate data + OWASP Dep-Check |
| 41 | SCIP/LSIF Precise Resolver | 1, 2, 4, 16, 18 | deterministic | scip-java + scip-kotlin (SemanticDB plugin) + SCIP CLI. **Kotlin-only; no scip-swift** |
| 45 | Inter-Module Event Bus | 2, 4, 9 | heuristic | semgrep + tree-sitter + SourceKit-LSP/kotlin-lsp + CodeQL |

### 2.2 Conventional (9 items — "how it's done here")

| # | Name | Target problems | Confidence | Key tool stack |
|---|---|---|---|---|
| 6 | Coding Convention Extractor | 3 | heuristic | SwiftSyntax + Harmonize + Konsist + detekt + semgrep |
| 7 | Error Handling Policy Extractor | 10 | heuristic | SwiftSyntax + semgrep + ast-grep + detekt (EmptyCatchBlock etc.) + SourceKit-LSP |
| 8 | Testability/DI Pattern Extractor | 11 | heuristic | Konsist + Harmonize + detekt (Hilt/Koin) + semgrep (MockK/Mockito) |
| 9 | Localization & Accessibility Extractor | 12 | heuristic | SwiftSyntax + xcstrings parser + Android Lint + Google ATF + detekt |
| 10 | Domain Naming & Glossary Extractor | 18 | **LLM-required** | tree-sitter + semgrep + Graphiti entity extraction + sentence-transformers embedding |
| 28 | Coverage-Gap Extractor | 11 | deterministic | Kover 0.9.8 + JaCoCo + Xcode llvm-cov/xcresult + DataDog swift-code-coverage |
| 29 | Resource/Asset Usage Extractor | 12 | heuristic | Android Lint UnusedResources + FengNiao + SwiftGen/R.swift + semgrep |
| 37 | Documentation Coverage Extractor | 3, 18 | deterministic | Dokka 2.2.0 reportUndocumented + swift-doc-coverage + DocC coverage flag |
| 38 | Test Smell & Flaky Test Extractor | 11 | heuristic | tsDetect ruleset ports (Kotlin/Swift) + FlakyLens (OOPSLA 2025) + Develocity |

### 2.3 Historical (6 items — "why so, not otherwise")

| # | Name | Target problems | Confidence | Key tool stack |
|---|---|---|---|---|
| 11 | Decision History Extractor | 5 | heuristic | pygit2 + GitHub GraphQL (associatedPullRequests) + SZZ + ADR parser + LLM |
| 12 | Migration Signal Extractor | 15 | heuristic | SwiftSyntax (@available) + detekt (@Deprecated) + semgrep coexistence + CodeQL |
| 26 | Bug-Archaeology Extractor | 5 | heuristic | GitHub Issues API + LLM4SZZ-style classifier + pygit2 blame + LLM category |
| 32 | Code Ownership Extractor | 5 | deterministic | pygit2 blame + code-maat (CST) + hercules (RIG) + custom Gini/HHI aggregator |
| 43 | PR Review Comment Extractor | 3, 5, 10 | heuristic | GitHub GraphQL reviewThreads + semgrep classifier + LLM intent classifier |
| 44 | Complexity × Churn Hotspot | 5, 8 | deterministic | detekt + SwiftLint + code-maat/pygit2 + Tornhill crime-scene formula |

### 2.4 Semantic (6 items — "invariants and implicit contracts")

| # | Name | Target problems | Confidence | Key tool stack |
|---|---|---|---|---|
| 13 | Invariant & Contract Extractor | 6 | **LLM-required** | semgrep + tree-sitter + ast-grep + detekt + Kotlin contracts API + LLM for test-spec inference |
| 14 | Lifecycle & State Extractor | 7 | heuristic | tree-sitter-swift + swift-syntax (+ macro expansion) + compose-stability-analyzer + Compose compiler metrics |
| 15 | Domain Edge-Case Extractor | 14 | **LLM-required** | semgrep (BigDecimal/overflow/address patterns) + ast-grep + domain-specific rules + LLM for test-cases |
| 16 | Read/Write Path Asymmetry | 19 | heuristic | semgrep + tree-sitter (Repository/Cache naming) + CodeQL dataflow |
| 34 | Code Smell Structural | 6, 11 | deterministic | detekt (LargeClass, LongMethod) + SwiftLint + tree-sitter (Feature Envy via call-graph) |
| 40 | Crypto Domain Model | 14, 18 | heuristic | tree-sitter (sealed class extraction) + semgrep + SLIP-0044 registry lookup + LLM |

### 2.5 Contextual (6 items — "where in lifecycle we are")

| # | Name | Target problems | Confidence | Key tool stack |
|---|---|---|---|---|
| 17 | Hot-Path Profiler Extractor | 8 | heuristic | xctrace + Perfetto PerfettoSQL + simpleperf + xcodetracemcp MCP |
| 18 | Concurrency Ownership Map | 9 | heuristic | SwiftSyntax (@MainActor, nonisolated, Swift 6.2 @concurrent) + SourceKit-LSP cursor-info + detekt coroutines |
| 19 | Feature Flag & Config Extractor | 13 | heuristic | semgrep + tree-sitter + Gradle DSL parser + xcconfig parser + BuildKonfig |
| 20 | Logging Policy Extractor | 20 | heuristic | semgrep (Timber/Log.*/os.log/Logger) + tree-sitter + os.log privacy API parser |
| 30 | Performance Pattern Extractor | 8 | heuristic | semgrep (main-thread sync, N+1) + detekt (ForbiddenMethodCall) + SwiftLint + CodeQL (deep N+1) |
| 35 | Taint & PII Data-Flow | 20 | **LLM-required** | semgrep taint-mode (intrafile) + CodeQL (cross-file) + iHunter-style methodology (not OSS) |
| 42 | Build Reproducibility | 13 | heuristic | Bazel BEP + Gradle Build Scan + diffoscope + reprotest + SOURCE_DATE_EPOCH checks |

### 2.6 Cross-cutting support (5 items)

| # | Name | Role |
|---|---|---|
| 21 | Symbol Index Extractor | **Backbone.** SourceKit-LSP + kotlin-lsp (or fwcd) + palace-serena MCP. Feeds ≥30 extractors. |
| 22 | Git History Harvester | Raw commits + PRs + blame via pygit2 + GitHub GraphQL. Feeds historical extractors. |
| 23 | Test Harness Adapter | xcresultparser v1.7 (Xcode 16+) + JaCoCo/Kover XML + JUnit XML normalization. |
| 24 | AST Pattern Matcher | semgrep + ast-grep + tree-sitter unified rule engine. Feeds 10+ extractors. |
| 41 | SCIP/LSIF Precise Resolver | (also in Structural) — batch stable-ID layer for cross-tool dedup. |

---

## 3. Meta-Category Coverage Verification

All 20 problems mapped to at least one extractor; no gaps. See `outline.yaml` for exact problem-to-extractor mapping. Minor overlap cluster noted around problem 11 (testability): four extractors contribute (#8 DI, #28 coverage, #38 test smells, #23 harness) — intentional redundancy since each attacks a distinct dimension.

**Confidence-tier distribution:**
- Deterministic (15 items) — highest-confidence automation targets, low maintenance burden
- Heuristic (26 items) — require per-project calibration; approximate 80-95% precision depending on tool
- LLM-required (4 items: #10, #13, #15, #35) — concentrated LLM cost surface; these are the extractors where the OAuth-boundary decision from earlier in the session matters most

---

## 4. Shared Tool Infrastructure

Distinct tools reused across ≥3 extractors (argues for shared implementation rather than per-extractor duplication):

| Tool | Used by extractors | Recommended ownership |
|---|---|---|
| **tree-sitter** (+ kotlin, swift, java grammars) | 1, 2, 3, 4, 6, 7, 10, 12, 14, 15, 16, 18, 25, 40, 45 | #24 AST Pattern Matcher as shared execution layer |
| **semgrep** (+ taint mode) | 3, 6, 7, 8, 10, 12, 13, 14, 15, 16, 18, 19, 20, 30, 33, 35, 38, 45 | #24 AST Pattern Matcher |
| **ast-grep** | 6, 7, 10, 13, 15, 16, 38 | #24 AST Pattern Matcher |
| **detekt** (+ custom rulesets) | 3, 6, 7, 8, 12, 13, 14, 18, 30, 34, 38, 44 | dedicated detekt runner in #24 |
| **SwiftSyntax / SourceKit-LSP** | 1, 3, 4, 6, 7, 13, 14, 17, 18, 19, 20, 27, 33, 34, 38 | #21 Symbol Index as shared LSP client |
| **Kotlin LSP / compiler plugins** | 1, 3, 4, 5, 6, 7, 8, 13, 14, 18, 21, 27, 33, 34, 38 | #21 Symbol Index |
| **pygit2 / libgit2** | 11, 12, 22, 26, 32, 43, 44 | #22 Git History Harvester as shared git interface |
| **GitHub GraphQL API** | 11, 22, 26, 43 | #22 Git History Harvester |
| **CodeQL 2.18.1+** (Kotlin/Swift GA July 2024) | 7, 16, 30, 33, 35, 45 | optional high-accuracy pass; CI-integrated separately from real-time extractors |
| **Graphiti entity extraction** | 10, 15, 35, 40 | Graphiti-core library direct integration |
| **LLM (Claude/GPT-4o/etc.)** | 10, 11, 13, 15, 16, 26, 35, 40, 43 | centralized LLM router with OAuth-consistent default (Ollama/local-embed-only per earlier decision) |

**Implication for N+1 spec:** the Graphiti compose service should be sized to run alongside shared infrastructure (palace-serena, shared AST engine, git harvester). Ollama may be activated only when one of the 4 LLM-required extractors is in scope for a slice.

---

## 5. Ingest Dependency DAG (derived from `cross_extractor_feeds`)

```
 Layer 0 (roots): #22 Git History Harvester, #23 Test Harness Adapter, #24 AST Pattern Matcher

 Layer 1 (consume layer 0): #21 Symbol Index (consumes nothing; backbone)

 Layer 2 (consume L0/L1):
   Structural: #1, #2, #3, #4, #5, #25, #33
   Conventional: #6, #9, #10, #29, #37
   Historical: #11, #12, #26, #32, #44
   Semantic: #13, #14, #16, #34
   Contextual: #17, #18, #19, #20, #42
   Support: #41 (SCIP — independent of L1)

 Layer 3 (consume L2):
   Structural: #27 (needs #1, #4), #31 (needs #1, #4, #5, #21, #27), #36 (needs #25, #27), #39 (needs #25), #45 (needs #21)
   Conventional: #7 (needs #6), #8 (needs #6), #28 (needs #23), #38 (needs #23, #24)
   Semantic: #15 (needs #13, #21, #23), #40 (needs #15, #21)
   Contextual: #30 (needs #16, #17, #21, #24), #35 (needs #20, #21, #24)
   Historical: #43 (needs #11, #22)

 Layer 4: #42 (Build Reproducibility — annotates #25 nodes; on-demand trigger, off the critical path)
```

**Scheduling observation:** a 5-level DAG means a full ingest can parallelize Layer 0–2 extensively; Layer 3 gates on Layer 2 completion. The most critical single-point bottleneck is **#21 Symbol Index** — any outage of this extractor blocks 30+ downstream. Spec should mandate #21 health-check before scheduling downstream.

---

## 6. Overlap Resolutions (from research evidence)

### 6.1 #40 Crypto Domain Model ↔ #15 Domain Edge-Case → KEEP SEPARATE

**Rationale (from agent 8 analysis):** Item 40 extracts the domain ontology — what coins/tokens/adapters exist, their SLIP-0044 coin_type, UTXO vs account-model classification. Item 15 extracts defensive guards — overflow checks, decimal precision, checksum validation.

- 40 is stable domain taxonomy (low churn)
- 15 is volatile defensive-code inventory (high churn; each bug fix adds new guards)

Merging would conflate temporal validity semantics. Bridge via `:GUARDS_DOMAIN` or `:LACKS_EDGE_CASE_GUARD` edge from #15 → #40 entities.

### 6.2 #41 SCIP Resolver ↔ #21 Symbol Index → KEEP SEPARATE, ENRICH

**Rationale (from agent 2 analysis):**
- Item 21 is live LSP queries (SourceKit-LSP + kotlin-lsp) — low-latency, real-time, handles Swift
- Item 41 is batch SCIP indexes (scip-java, scip-kotlin) — Kotlin-only, compiler-verified stable IDs

**Critical finding:** no official `scip-swift` exists as of April 2026 — SCIP coverage is Kotlin-only. This means #41 is **supplementary enrichment**, not a #21 replacement. Join key: `display_name + module` on Kotlin symbols for stable-ID annotation.

### 6.3 #42 Build Reproducibility ↔ #25 Build System → KEEP SEPARATE, DISTINCT PROPERTIES

**Rationale (from agent 3 analysis):**
- Item 25 sets `cacheable: bool` from `@CacheableTask` static annotation
- Item 42 sets `cacheable_verified: bool` from Bazel BEP / Develocity cache-hit evidence

Both properties live on shared `:BuildTask` nodes. Item 25 owns node creation; Item 42 annotates existing nodes with operational evidence. Non-conflicting provenance.

---

## 7. Top Open Questions Blocking Implementation

Distilled from per-extractor `open_questions` fields; ordered by blast radius.

### 7.1 Schema-level (block any extractor slice)

1. **FQN format unification Kotlin ↔ Swift** (#21, #41, #31). Different name-mangling rules mean cross-language dedup requires a normalization layer. Options: (a) SCIP string format for Kotlin, custom canonicalized form for Swift; (b) separate namespaces. Recommend (a) with documented Swift → SCIP-like mapping.
2. **:SymbolOccurrence storage scale** (#21). 20-Kit repo generates 5–10M occurrences. Options: (a) store all in Graphiti (scale risk); (b) sidecar inverted index (Tantivy/Lucene) with references only in graph. Recommend (b) — separates dense reference data from the structural graph.
3. **Shared `:ExternalDependency` node ownership** (#5, #39). Two extractors produce overlapping nodes. Mandate: Item 25/5 creates; Item 39 enriches with version-matrix properties. Ingest order: 25 → 5 → 39.

### 7.2 Scheduling-level (block multi-slice rollout)

4. **Recency decay constant λ for #32 Code Ownership** (RIG paper proposes 3–6 month half-life; mobile Kit commit cadence differs). Configurable per-Kit with sensible default; decision before implementation.
5. **CodeQL as optional enrichment** (#7, #30, #33, #35, #45). CodeQL database build adds 20–40 min per full ingest. Recommend nightly CodeQL pass for high-accuracy confirmation; per-commit runs remain semgrep/tree-sitter-only.
6. **Profiling scenario ownership** (#17, #23). Who defines and executes scenarios — Test Harness Adapter or Hot-Path Profiler? Recommend #23 executes, #17 ingests artifacts.

### 7.3 Domain-specific (block crypto-relevant extractors)

7. **Ethereum JSON-RPC schema type** (#36). Not REST/GraphQL/protobuf. Recommend adding `jsonrpc` schema type with hardcoded EVM method registry. Future slice decision.
8. **Token list dynamic loading** (#40). CoinGecko/CMC JSON lists produce thousands of `:TokenContract` nodes. Policy: ingest only statically declared contracts; remote lists are out of scope.
9. **iHunter binary taint is not OSS** (#35). Options: (a) reproduce via Ghidra/Binary Ninja scripting; (b) CodeQL on LLVM bitcode via `swift -emit-bc`; (c) source-level taint only, document gap. Recommend (c) for N+2–N+6, revisit iHunter approach in later slice.

### 7.4 Toolchain-risk (block at any moment)

10. **SKIE vs Swift Export migration** (#4). SKIE does not support Swift Export (Kotlin 2.1+ experimental, stable target 2026). Schema design today may require revision in 2026. Recommend dual-path model in schema with explicit `bridgeType` enum.
11. **Dokka coverage percentage** (#37). Issue #398 open since Dec 2018; no native coverage API. Requires custom text-output parser that may break on Dokka version updates.
12. **xcresultparser Xcode 16 API break** (#23). Major rewrite required for Xcode 16. Version pinning is critical; CI must flag Xcode version mismatch.

---

## 8. Roadmap Recommendation (for N+2…N+6 slices)

**N+2 (first code extractor slice):**
- **#21 Symbol Index** (mandatory — blocks all downstream)
- **#22 Git History Harvester** (mandatory — blocks historical cluster)
- **#1 Architecture Layer** (deterministic, low risk, high value for module queries)
- **#25 Build System** (deterministic, foundational for #39/#42)

→ Unlocks: architecture query tool surface + foundational DAG.

**N+3 (first reviewer-useful slice):**
- **#24 AST Pattern Matcher** (shared infra for 10+ extractors)
- **#44 Complexity × Churn Hotspot** (deterministic; combines #22 + #34 metrics; immediate value for refactor prioritization)
- **#32 Code Ownership** (deterministic; bus-factor risk surface)

→ Unlocks partial version of user's target task: "analyze code, report hotspots."

**N+4 (structural + conventional):**
- **#27 Public API Surface** + **#31 Cross-Module Contract** (deterministic pair; BCV + swift-api-digester)
- **#5 Dependency Surface** + **#39 Cross-Repo Version Skew** (dedup via shared `:ExternalDependency` node)
- **#6 Coding Convention** + **#7 Error Handling Policy** + **#8 Testability/DI** (Konsist/Harmonize/semgrep cluster)

→ Unlocks convention queries for agents: "what pattern does this project use?"

**N+5 (semantic + runtime):**
- **#34 Code Smell Structural** + **#28 Coverage-Gap** + **#38 Test Smell** (quality-signal cluster)
- **#17 Hot-Path Profiler** + **#30 Performance Pattern** (static + runtime performance)
- **#18 Concurrency Ownership Map**

→ Unlocks full version of user's target task: "find bugs / duplication / performance issues."

**N+6 (crypto-domain + deep):**
- **#13 Invariant & Contract** + **#15 Domain Edge-Case** + **#40 Crypto Domain Model** (LLM-required cluster; activate OAuth-friendly LLM path)
- **#35 Taint & PII Data-Flow** (security-critical; CodeQL-backed)
- **#20 Logging Policy** (PII leakage detection)

→ Crypto-wallet-specific value unlocked.

**Deferred beyond N+6:** #42 Build Reproducibility, #43 PR Review Comment, #26 Bug Archaeology, #29 Resource/Asset Usage, #33 Dead Symbol, #36 Network Schema, #37 Documentation Coverage, #11 Decision History, #12 Migration Signal, #19 Feature Flag, #45 Inter-Module Event Bus — valuable but not on the critical path to the user's stated task. Each can be a 2-3 day slice once infrastructure is in place.

---

## 9. Implications for N+1 Spec (current slice)

N+1 is substrate only — it does NOT implement any extractor. But this research informs N+1 specifically in these ways:

1. **Graphiti schema must accommodate `cross_extractor_feeds` as a first-class concept.** Inter-extractor edges are load-bearing (RANGER/RepoGraph precedent).
2. **Bi-temporal support required day-one** — at least 6 extractors use edge `end_time` semantically (migration completion, smell resolution, violation remediation, cache invalidation breakage).
3. **Faceted classification §5.4 must include `capability` axis** — research confirms capability tags are heavily used (`:Audits`, `:Observes`, `:Resolves`, `:DetectsStaleness`, etc.).
4. **Namespace model (`group_id` per project) is confirmed correct.** All extractors scope outputs per-repo; a single namespace would collide fatally at 20-Kit scale.
5. **SCIP alignment is already non-negotiable.** Designing `:Symbol` nodes without SCIP stable-ID field will require retroactive schema migration in N+2.
6. **Shared infrastructure (palace-serena, AST engine, git harvester) belongs in substrate, not per-extractor containers.** Compose services in N+1 spec should reflect this.

---

## 10. Source Material

All 45 extractor JSON records (12 on disk at `results/*.json`, 33 captured in research-deep agent conversation archived at `/private/tmp/claude-501/-Users-ant013-Android-Gimle-Palace/…/tasks/a*.output`). Prior-art references in `sources.md` (35 links spanning SCIP, Glean, Stack Graphs, CodeQL, Periphery/Reaper, SmellyCode++, Flakify/FlakyLens, oasdiff, Buf, Kover, Dokka, SwiftSyntax, RepoGraph, RANGER, KGCompass, LLM4SZZ, Graphiti, Zep, and others).

**Headline papers this research relied on:**
- RepoGraph (arXiv 2410.14684) — repo-level KG design
- RANGER (arXiv 2509.25257) — explicit inter-extractor edges
- KGCompass (arXiv 2503.21710) — issue-PR-code triple, 91% file-level recall
- LLM4SZZ (arXiv 2504.01404) — bug-introducing commit +16% F1
- FlakyLens (OOPSLA 2025) — 65.79% F1 flaky detection
- SmellyCode++ (Scientific Data 2025) — 94-96% F1 smell detection without LLM
- iHunter (USENIX Security 2024) — iOS binary PII taint
- Zep / Graphiti (arXiv 2501.13956) — temporal KG for agent memory
