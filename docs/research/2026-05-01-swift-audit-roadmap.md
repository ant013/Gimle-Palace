# Swift / iOS Audit Roadmap — UW-iOS Ecosystem Coverage

**Date:** 2026-05-01
**Status:** Strategic reference — informs Slice 4+ planning
**Author:** Board (operator-driven analysis session)
**Predecessor:** `docs/research/extractor-library/report.md` (2026-04-18) — 45-extractor research backlog
**Target:** Full audit + analysis capability for unstoppable-wallet-ios + ~15-20 Swift Kit dependencies (BitcoinKit-iOS, EvmKit.Swift, Eip20Kit.Swift, OneInchKit.Swift, UniswapKit.Swift, HsToolKit, MarketKit, HdWalletKit, WalletConnect, aa-swift, etc.)

---

## 1. Current State

5 extractors live in production palace-mcp as of merge of GIM-124:

| # | Extractor | Status | Swift coverage |
|---|---|---|---|
| (diag) | heartbeat | ✅ live | n/a |
| 21 | symbol_index_python | ✅ live (GIM-104 predecessor) | — |
| 21 | symbol_index_typescript | ✅ live (GIM-104) | — |
| 21 | symbol_index_java (Java + Kotlin) | ✅ live (GIM-127) | — |
| (gap) | symbol_index_solidity | ⚠ live, DEFs only — no USE occurrences | — |
| 21 | **symbol_index_swift** | 🟡 GIM-128 in progress | ✅ pending |

After GIM-128 merge, Swift coverage is **1 extractor of ~38 Swift-relevant**.

## 2. Filter — 45 Backlog → Swift Relevance

Of the 45 extractors in `report.md`, ~38 apply to a Swift-only audit. Excluded:

- **#4 KMP Platform-Bridge** — UW-iOS is pure Swift; no shared KMP code with UW-android. (Slice 4 KMP Bridge is a separate Android-side concern, not in this Swift roadmap.)
- **#41 SCIP/LSIF Resolver** — `scip-swift` does not exist as of April 2026 (verified in research). For Swift, the only path to a SCIP-format index is the community SwiftSCIPIndex tool (IndexStoreDB → SCIP), which we use directly via #21 — not as a separate enrichment layer.

### Tier A — Foundational (must-have for any audit; 12 extractors)

These unlock structural navigability. After Tier A, palace-mcp can answer: "what calls X?", "where is X defined?", "what depends on Kit Y?", "what's the architecture?", "where are hotspots?".

| # | Extractor | Why for UW-iOS |
|---|---|---|
| 21 | Symbol Index Swift | Backbone — FQN, refs, defs/decls (GIM-128) |
| 22 | Git History Harvester | Foundation for historical cluster |
| 24 | AST Pattern Matcher | Shared AST infra (semgrep + tree-sitter + ast-grep); feeds 10+ |
| 5 | Dependency Surface (SPM) | Package.swift / Package.resolved → SPM dependency graph |
| 25 | Build System (SPM/Xcode) | SwiftPM PackageDescription parser, target/product graph |
| 1 | Architecture Layer | Module structure, public/internal/fileprivate visibility |
| 27 | Public API Surface (Swift) | swift-api-digester — what each Kit exposes |
| 31 | Cross-Module Contract | API drift between Kits and UW-iOS app |
| 33 | Dead Symbol (Swift) | Periphery — unused code in UW-iOS |
| 44 | Complexity × Churn Hotspot | Where to focus refactor effort |
| 32 | Code Ownership | Bus-factor + ownership distribution |
| 34 | Code Smell Structural (Swift) | SwiftLint-driven smell inventory |

### Tier B — Quality signals (10 extractors)

Adds: "what's the code style?", "where's flaky tests?", "where's missing coverage?", "concurrency hazards?".

| # | Extractor | Why for UW-iOS |
|---|---|---|
| 6 | Coding Convention | SwiftLint + Harmonize-Swift — naming, style |
| 7 | Error Handling Policy (Swift) | try/throws/Result patterns; swallow-catch |
| 8 | Testability / DI (Swift) | protocol-DI, Swinject patterns, mock surfaces |
| 18 | Concurrency Ownership Map | @MainActor / actor / async patterns; Swift 6 sendability |
| 14 | Lifecycle & State | SwiftUI @State / @Observable / property wrappers |
| 30 | Performance Pattern | Main-thread sync, N+1, copy-on-write misses |
| 20 | Logging Policy | os.log, Logger, OSLog Privacy specifiers |
| 38 | Test Smell & Flaky Test | XCTest patterns; FlakyLens-style detection |
| 28 | Coverage-Gap | xccov / xcresult — uncovered paths |
| 9 | Localization & Accessibility | .strings, .xcstrings, VoiceOver readiness |

### Tier C — Crypto-specific (5 extractors; 4 LLM-required)

The audit value-multiplier for a wallet codebase. PII leak detection (#35) is **security-critical**.

| # | Extractor | Why for UW-iOS |
|---|---|---|
| 40 | Crypto Domain Model | Adapters, coin_type, SLIP-0044, UTXO vs Account taxonomy |
| 15 | Domain Edge-Case (LLM) | Overflow, decimal precision, address checksum, BigDecimal-equivalents |
| 13 | Invariant & Contract (LLM) | Preconditions, assertions, custom contracts |
| 35 | Taint & PII Data-Flow (LLM) | Where mnemonic/seed/private-key flows; **wallet must-have** |
| 36 | Network Schema | URLSession + JSON-RPC EVM contracts + REST APIs |

### Tier D — Surrounding (11 extractors)

Valuable for completeness but not on critical path.

| # | Extractor | Why |
|---|---|---|
| 17 | Hot-Path Profiler | xctrace runtime hot paths |
| 19 | Feature Flag | xcconfig, #if DEBUG, BuildKonfig-equivalent |
| 37 | Documentation Coverage | DocC, swift-doc-coverage |
| 45 | Inter-Module Event Bus | Notification / Combine publisher graph |
| 39 | Cross-Repo Version Skew | Package.resolved diff between Kits |
| 3 | Reactive Dependency Tracer | Combine / SwiftUI publisher graph |
| 11 | Decision History | ADR + PR linkage |
| 26 | Bug Archaeology | issue→fix-commit patterns |
| 43 | PR Review Comment | Patterns from review feedback |
| 29 | Resource/Asset (lite) | xcassets / SwiftGen — UW has live UIKit screens |
| 42 | Build Reproducibility | Xcode build determinism (far goal) |
| 12 | Migration Signal | @available coexistence |
| 2 | Symbol Duplication | Dupe detection across Kits via embeddings |

**Total Swift-relevant: 38 extractors.**

## 3. UW-iOS Ecosystem Inventory

The audit target is multi-repo, similar to UW-android. Estimated 15-20 SPM-style repositories. Operator MUST verify exact list against current `Package.resolved` of unstoppable-wallet-ios before Slice 4 starts.

**Core utilities (operator-internal HS-prefixed):**
- HsToolKit.Swift — networking, reachability, crypto
- HsExtensions, HsCryptoKit.Swift, HsCryptoKit.Native
- ObjectMapper-Swift fork

**Blockchain Kits — UTXO chains:**
- BitcoinKit.Swift, BitcoinCashKit-iOS, DashKit-iOS, LitecoinKit-iOS
- ECashKit-iOS, ZCashKit-iOS

**Blockchain Kits — EVM:**
- EvmKit.Swift, Eip20Kit.Swift
- OneInchKit.Swift, UniswapKit.Swift

**Blockchain Kits — non-EVM:**
- TonKit.Swift, TronKit.Swift
- SolanaSwift / Solana.Swift fork
- StellarKit.Swift

**Wallet/Identity:**
- HdWalletKit.Swift
- WalletConnectKit (or community WalletConnect-Swift)
- aa-swift (Account Abstraction)

**Market/data:**
- MarketKit.Swift
- ChartView.Swift

Each is a separate `.scip` index, separate registration in palace-mcp, separate read-only mount. `palace-mcp/docker-compose.yml` will need to grow ~15-20 entries under `palace-mcp.volumes`.

## 4. Prioritized Roadmap

Slices ordered by `cost × dependency-blocking × audit-value`. Each slice produces working, independently-mergeable software.

### Phase I — Swift foundation (after GIM-128)

| Slice | Scope | Tier | Notes |
|---|---|---|---|
| **GIM-128** (in progress) | symbol_index_swift (#21) | A | Track A/B fixture pattern from `reference_imac_toolchain_limits.md` |
| **Slice 4** | Multi-repo SPM ingest pipeline | A | Operational track — regen procedure for each Kit, scp to iMac, batch-ingest. No new code, just process + scripts. Unblocks all Swift work. |
| **Slice 5** | Dependency Surface SPM (#5) + Build System SPM (#25) — paired | A | Deterministic. SPM Package.swift + Package.resolved parser. After this: "what does Kit X depend on?" |
| **Slice 6** | Architecture Layer (#1) | A | Deterministic. Module/target structure, visibility map. Pairs with #5. |

→ After Phase I: Swift navigability. Can answer module-level audit queries.

### Phase II — Quality signals

| Slice | Scope | Tier | Notes |
|---|---|---|---|
| **Slice 7** | Git History (#22) + Hotspots (#44) + Code Ownership (#32) | A/B | Triple slice — all deterministic, all git-based. Massive immediate value. |
| **Slice 8** | Code Smell Structural (#34) — SwiftLint integration | A | `:CodeSmell` nodes from SwiftLint. |
| **Slice 9** | Dead Symbol (#33) — Periphery integration | A | `:DeadSymbol` nodes. Track B only (Periphery requires full Xcode build). |
| **Slice 10** | Public API Surface (#27) + Cross-Module Contract (#31) | A | swift-api-digester. **Highest value for multi-repo audit** — API drift detection. |

→ After Phase II: MVP audit. Can detect problems.

### Phase III — Deep audit

| Slice | Scope | Tier |
|---|---|---|
| **Slice 11** | Concurrency Map (#18) | B |
| **Slice 12** | Convention (#6) + Error Handling (#7) + DI (#8) — paired | B |
| **Slice 13** | Coverage Gap (#28) + Test Smell (#38) + Test Harness (#23) | B |
| **Slice 14** | AST Pattern Matcher infra (#24) — shared layer for remaining semantic | A (cross-cutting) |

### Phase IV — Crypto-specific (LLM-touched)

These activate the LLM cost-surface. The OAuth-friendly LLM path **must be decided before Slice 15**. Concentrated in 4 extractors per research §4.

| Slice | Scope | Tier |
|---|---|---|
| **Slice 15** | Crypto Domain Model (#40) | C |
| **Slice 16** | Domain Edge-Case (#15, LLM) | C |
| **Slice 17** | Taint & PII (#35, LLM) — **wallet security must-have** | C |
| **Slice 18** | Logging Policy (#20) — pairs with #35 (PII leak detection) | B |

### Phase V — Extensions

| Slice | Scope | Tier |
|---|---|---|
| **Slice 19** | Performance Pattern (#30) + Hot-Path (#17) | B/D |
| **Slice 20** | Lifecycle / State (#14) | B |
| **Slice 21** | Network Schema (#36) | C |
| **Slice 22** | Localization & Accessibility (#9) | B |
| **Slice 23** | Documentation Coverage (#37) | D |
| **Slice 24** | Feature Flag (#19) | D |
| **Slice 25** | Reactive Dependency (#3) | D |
| **Slice 26** | Migration (#12) + Decision History (#11) + Bug Archaeology (#26) + PR Reviews (#43) | D |
| **Slice 27** | Inter-Module Event Bus (#45) | D |
| **Slice 28** | Symbol Duplication (#2) + Cross-Repo Version Skew (#39) | D |
| **Slice 29** | Build Reproducibility (#42) | D |

**Total: ~27 slices for full Swift audit ecosystem coverage** (ex-GIM-128 already in flight).

## 5. Android Twin Carry-over Analysis

Operator question 2026-05-01: "After completing all Swift work, will Android audit be ready?"

**Honest answer: NO.** Of ~38 Swift-relevant extractors, only **~7 are language-agnostic at the data layer** and reuse directly for Android. The other ~31 require Android-twin implementations because tooling and language patterns differ.

### Reused as-is (~7 extractors)

| # | Extractor | Why language-agnostic |
|---|---|---|
| 22 | Git History Harvester | pygit2 + GitHub GraphQL — same for any repo |
| 32 | Code Ownership | git blame + code-maat — language-agnostic |
| 11 | Decision History | ADR + PR linkage — generic |
| 26 | Bug Archaeology | Issues → fix-commits — generic |
| 43 | PR Review Comment | GitHub GraphQL reviewThreads — generic |
| 42 | Build Reproducibility | Bazel BEP — same for both |
| 44 | Complexity × Churn (git half) | git churn part is generic; complexity part is language-specific |

For these, ingest pipeline written once works on UW-iOS, UW-android, and any future project.

### Need separate Android-twin (~31 extractors)

Each requires Android-twin implementation due to different tooling:

| Category | Swift-side tool | Android-side tool |
|---|---|---|
| #21 Symbol Index | SwiftSCIPIndex + IndexStoreDB | scip-java + semanticdb-kotlinc (✅ already done in GIM-127) |
| #5 Dependency Surface | SwiftPM PackageDescription | Gradle Tooling API + dependency-analysis-gradle-plugin |
| #25 Build System | SwiftPM | Gradle + AGP + KSP |
| #1 Architecture Layer | Package.swift parser | modules-graph-assert + ArchUnit |
| #27 Public API Surface | swift-api-digester | binary-compatibility-validator (BCV) |
| #33 Dead Symbol | Periphery | Reaper-Android SDK |
| #34 Code Smell | SwiftLint | detekt |
| #28 Coverage Gap | xccov / xcresult | Kover / JaCoCo |
| #38 Test Smell | tsDetect-Swift port | tsDetect-Kotlin port |
| #18 Concurrency | @MainActor / actor / async | coroutines / Flow / Channel — **different model entirely** |
| #14 Lifecycle | SwiftUI @State / @Observable | Compose @Composable / State |
| #7 Error Handling | throws / Result | Result / Either / runCatching |
| #8 Testability/DI | protocol-DI / Swinject | Hilt / Koin / Dagger |
| #20 Logging | os.log / Logger | Timber / Log.* |
| #36 Network | URLSession / Alamofire / JSON-RPC | Retrofit / OkHttp |
| #9/#29 Resources | xcassets / .strings / SwiftGen | strings.xml / R.swift |
| #6 Convention | SwiftLint + Harmonize | detekt + Konsist + Harmonize-Android |
| #19 Feature Flag | xcconfig + #if DEBUG | Gradle BuildConfig + BuildKonfig |
| #37 Documentation | DocC + swift-doc-coverage | Dokka 2.2 reportUndocumented |
| #45 Event Bus | Combine / NotificationCenter | Flow / SharedFlow / Channel |
| #3 Reactive | Combine + SwiftUI | Flow + Compose |
| #39 Version Skew | Package.resolved diff | Gradle deps diff |
| #17 Hot-Path | xctrace | simpleperf / Perfetto |
| #30 Performance | SwiftLint forbidden + semgrep-swift | detekt ForbiddenMethodCall + semgrep-kotlin |
| #13 Invariant (LLM) | semgrep-swift rules | Kotlin contracts API + semgrep-kotlin |
| #15 Edge-Case (LLM) | semgrep-swift rules | semgrep-kotlin rules |
| #35 Taint (LLM) | semgrep-swift / CodeQL-Swift | semgrep-kotlin / CodeQL-Kotlin |
| #40 Crypto Domain | Swift adapter parsing | Kotlin adapter parsing |
| #2 Symbol Duplication | UniXcoder Swift tokens | UniXcoder Kotlin tokens |
| #12 Migration Signal | @available coexistence | @Deprecated coexistence |
| #41 SCIP Resolver | **N/A — no scip-swift** | scip-java / scip-kotlin (Android-only enrichment) |

### Twin cost reduction

Each Android-twin slice costs **~40-50% of the original Swift-side slice** because:

1. **Substrate already built** — 101a foundation (Tantivy bridge, IngestRun lifecycle, BoundedInDegreeCounter, schema management) is shared.
2. **Schema decisions already made** — `:Symbol`, `:CodeSmell`, `:DeadSymbol`, `:BuildTask` node types and their edges are designed once.
3. **Patterns already debugged** — TDD approach, Phase 4.1 evidence discipline, fixture-based testing — knowledge transfers 1:1.
4. **Cross-language FQN** already resolved (GIM-105 rev2 Variant B strip).

### Realistic full-coverage estimate

| Side | Slices | Cost |
|---|---|---|
| Swift roadmap (this doc) | ~27 slices | 100% |
| Android-twin slices | ~22-25 slices | ~40-50% per slice |
| Generic git-level slices | ~5-7 slices | shared, done **once** |

So the schema "do Swift → Android is free" does NOT hold. But the schema "do Swift → Android is ~2× cheaper and faster" does hold.

## 6. Slicing Strategy Options

Three orderings are plausible. Decision pending operator.

### Plan A: Swift-first complete
All ~27 Swift slices → then ~22-25 Android-twin slices.

- **Pros:** Single tooling context (Swift), no language switching, deep momentum on iOS audit
- **Cons:** ~6 months Android-side stagnates; UW-iOS and UW-android diverge in audit capability

### Plan B: Per-tier alternation **(recommended)**
Swift Tier A → Android-twin Tier A → Swift Tier B → Android-twin Tier B → …

- **Pros:** Both platforms develop in parallel; cross-platform queries (#31 Cross-Module Contract) can flag iOS↔Android API drift sooner; balanced velocity
- **Cons:** Double context-switching between Swift and Kotlin tooling per phase

### Plan C: Generic-first
Generic git-level cluster (#22/#32/#11/#26/#43/#42/#44-git) for both platforms simultaneously → then Android Tier A (since #21 already exists) → then Swift Tier A.

- **Pros:** Maximum-speed coverage of UW-android (where #21 backbone is done already)
- **Cons:** UW-iOS audit deferred 5-7 slices; operator's stated priority was UW-iOS

**Recommendation: Plan B.** Best balance of audit-product velocity for both platforms and immediate value from cross-platform contract drift detection.

## 7. Blockers & Open Questions

| # | Blocker | Impact | Mitigation |
|---|---|---|---|
| 1 | iMac is Intel + macOS 13 + Swift ≤5.8 | No live Swift build on iMac (SourceKit-LSP, swift-syntax, Periphery, swift-api-digester all unavailable) | Track A (fixture, merge gate) / Track B (dev Mac, deferred). Codified in `reference_imac_toolchain_limits.md` and applied per slice for any Swift tooling. |
| 2 | scip-swift does not exist | Only path to Swift symbol graph is community SwiftSCIPIndex (IndexStoreDB → SCIP) | GIM-128 spec rev2 Phase 1.0 spike validates SwiftSCIPIndex output suitability before Phase 2 implementation |
| 3 | swift-api-digester binary | Requires Xcode 15+ — unavailable on iMac | Track B for #27 / #31 (Slice 10) |
| 4 | Periphery requires full project build | Full xcodebuild needed — impossible on iMac | Track B for #33 (Slice 9) |
| 5 | Multi-repo coordination | 15-20 Kit-repos, each separate registration + .scip | Slice 4 — centralized regen + scp batch script |
| 6 | CodeQL-Swift GA July 2024 | Build cost 20-40 min per repo for full ingest | Nightly only (not per-commit). See research §7.2.5 |
| 7 | iHunter binary taint not OSS | Source-level taint only for #35 | Accept gap. Document in Slice 17 spec. See research §7.3.9 |
| 8 | LLM-OAuth boundary | 4 extractors require LLM (#10/#13/#15/#35) | Decision required before Slice 15 |
| 9 | FQN cross-language Swift ↔ Kotlin | Mangling rules differ | GIM-105 rev2 Variant B strip resolved this for current languages; verify Swift conforms in GIM-128 Phase 1.0 |
| 10 | `.scip` storage scale at 15-20 Kits | Estimated 5-10M occurrences (research §7.1.2) | Tantivy already in place; verify capacity in Slice 4 ops procedure |
| 11 | Sourcegraph upstream — scip-java AGP9 incompatibility | If Sourcegraph fixes by 2026-05-07, can re-enable AGP9 path on Android-twin work | Per `project_scip_java_strategy_2026-04-30.md` — check upstream 2026-05-07 |

## 8. Decision Points (Pending Operator Input)

1. **Slicing strategy** — Plan A / B / C? *Recommendation: B (alternation).*
2. **First Android-twin slice** — when in the schedule? *Recommendation: after Slice 5 (SPM Dependency), do Android-twin "Slice 5b Gradle Dependency Surface" before moving to Slice 6 Swift Architecture Layer.*
3. **LLM/OAuth path** — needs concrete decision before Slice 15.
4. **Slice 4 scope cap** — operational-only (procedure + scripts), or expand to include first 3-4 Kit ingestions? *Recommendation: scripts-only; let Slice 5 ingest Kits as needed.*
5. **Periphery / swift-api-digester** — accept Track B-only (deferred-not-blocked) per `reference_imac_toolchain_limits.md`? *Recommendation: yes — already established pattern.*

## 9. Companion References

- `docs/research/extractor-library/report.md` — original 45-item research backlog (2026-04-18)
- `docs/research/extractor-library/outline.yaml` — per-extractor metadata
- `docs/research/extractor-library/fields.yaml` — research field schema
- `docs/research/extractor-library/sources.md` — 35 prior-art links
- `docs/superpowers/specs/2026-04-30-ios-swift-extractor.md` — GIM-128 Slice 3 spec rev2
- `docs/superpowers/plans/2026-04-30-GIM-128-ios-swift-extractor.md` — GIM-128 Slice 3 plan rev1
- `docs/superpowers/specs/2026-04-30-android-scip-java-validation.md` — GIM-127 Slice 1 spec (predecessor)

Memory references (operator's auto-memory):
- `reference_imac_toolchain_limits.md` — Track A/B split rationale
- `project_palace_purpose_unstoppable.md` — palace-mcp primary purpose = UW ecosystem
- `project_scip_java_strategy_2026-04-30.md` — scip-java upstream deadline
- `project_extractor_roadmap_post_solidity.md` — sequence Kotlin → iOS roadmap origin
- `project_solidity_use_occurrences_gap.md` — Solidity v1 gap context

---

**Status:** Reference document. Updates allowed via FB+PR per CLAUDE.md iron rules. Next revision trigger: Slice 4 spec writing or operator-driven slicing-strategy decision.
