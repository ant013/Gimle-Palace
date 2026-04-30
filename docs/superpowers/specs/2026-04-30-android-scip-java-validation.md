# Slice 1 — Android scip-java AGP validation

**Status:** Board draft (rev1, 2026-04-30)
**GIM-NN:** placeholder — CTO swaps in Phase 1.1
**Predecessor merge:** `d6e6d35` (GIM-124 Solidity extractor merged 2026-04-29)
**Related:** GIM-104 (TS extractor), GIM-111 (Java/Kotlin extractor on JVM-mini synthetic fixture), GIM-105 rev2 (Q1 FQN cross-language decision)
**Roadmap context:** First of 4-5 slices for full operator-stack language coverage. Sequence: Slice 1 (this) → Slice 2 (Android resources) → Slice 3 (iOS Swift+C+++Obj-C, possibly split) → Slice 4 (KMP bridge).

## Goal

Prove that the existing `symbol_index_java` extractor — built on the 101a foundation and validated on the synthetic `jvm-mini-project` fixture (GIM-111) — handles **real-world Android projects** end-to-end without code changes. Validation surface includes Jetpack Compose, multi-module Gradle, modern Kotlin idioms (StateFlow, sealed interfaces, suspend), and KSP-generated source (Room DAO `*_Impl` classes).

The slice ships a **vendored multi-module Android fixture** (`uw-android-mini-project`, derived from `unstoppable-wallet-android` MIT-licensed source), oracle-backed test class with cross-module reference assertions, integration test, docker-compose bind-mounts, and a real-project live-smoke target on iMac. **No new extractor code is written.** If `symbol_index_java` cannot reach this scope, the slice surfaces gaps as named follow-ups.

This is the smallest slice in the post-Solidity language sequence — explicitly designed to prove existing infrastructure works on Android before investing in resource extraction (Slice 2) or KMP cross-target resolution (Slice 4).

## Sequence

```
Slice 1 (this) → Slice 2 (Android resources) → Slice 3 (iOS native) → Slice 4 (KMP bridge)
   ↓
deliverables:
   - vendored fixture compiles + scip-java emits valid index
   - oracle-backed assertions on def/use/cross-module/KSP-generated symbols
   - real Android project (UW-android) registered + live-smoke
   - parallel ops setup for UW-ios (mount + register, no extractor yet)
```

**Per-slice "максимум эффективности" mandate:** each language slice ships full DEF + USE coverage from day 1. No Solidity-style v1-stub-then-followup pattern.

## Hard dependencies

| Dependency | State |
|---|---|
| `symbol_index_java` extractor (GIM-111) | Merged on develop, JVM-mini fixture validated. **Reused without modification.** |
| 101a foundation substrate (TantivyBridge, BoundedInDegreeCounter, ensure_custom_schema, …) | Stable, all extractors build on it. |
| `scip_parser.py` lang-agnostic parser (GIM-104) | Handles `KOTLIN`/`JAVA` per-document detection. |
| Q1 FQN cross-language Variant B (GIM-105 rev2) | Locks qualified_name format. |
| `scip-java` upstream (Sourcegraph) | External CLI; pin version in `regen.sh`. Slice does NOT vendor or fork scip-java. |
| iMac docker-compose state | Operator extends `volumes` for new bind-mounts; restart palace-mcp via `imac-deploy.sh`. |

## Architecture

### What's reused (no code changes)

| Component | Reuse status |
|---|---|
| `symbol_index_java` extractor | **Unchanged** — already handles `.kt`/`.kts`/`.java` via per-document language auto-detection. |
| `scip_parser.iter_scip_occurrences()` | Unchanged. |
| Foundation substrate (101a: schema bootstrap, TantivyBridge, eviction, circuit breaker, checkpoints) | Unchanged. |
| 3-phase bootstrap (defs+decls → user_uses → vendor_uses) | Unchanged. |
| `palace.code.find_references()` MCP tool | Unchanged. |
| Existing tests for jvm-mini fixture | Unchanged — coexist with new uw-android-mini tests. |

### What's new

| Artefact | Description |
|---|---|
| `tests/extractors/fixtures/uw-android-mini-project/` | Vendored multi-module Android fixture, ~28-32 files. |
| `tests/extractors/fixtures/uw-android-mini-project/REGEN.md` | Vendor source pin (UW commit SHA captured at fixture creation, upstream branch = `master`), regen script doc, manual oracle table. |
| `tests/extractors/fixtures/uw-android-mini-project/regen.sh` | `./gradlew compileDebugKotlin` (all 4 modules) + `npx @sourcegraph/scip-java index --output ./scip/index.scip`. |
| `tests/extractors/fixtures/uw-android-mini-project/scip/index.scip` | Pre-generated scip-java output, committed binary (~80-200 KB). |
| `tests/extractors/fixtures/uw-android-mini-project/LICENSE` | MIT, copy from upstream UW. |
| `TestUwAndroidMiniProjectFixture` class in `tests/extractors/unit/test_real_scip_fixtures.py` | ~12 oracle-backed assertions (def counts, KSP-generated symbol present, cross-module USE pairs, qualified_name format). Skipped via `requires_scip_uw_android` marker if `index.scip` missing. |
| `tests/extractors/integration/test_symbol_index_java_uw_integration.py` | Integration test running `symbol_index_java` against the new fixture; asserts IngestRun success + checkpoints in Neo4j + Tantivy doc count. |
| `docker-compose.yml` additions | 2 bind-mounts: `/Users/Shared/Android/unstoppable-wallet-android:/repos/uw-android:ro` and `/Users/Shared/Ios/unstoppable-wallet-ios:/repos/uw-ios:ro`. |
| `.env.example` annotation | Document `PALACE_SCIP_INDEX_PATHS` extension for Android slug. |
| `CLAUDE.md` updates | New "Operator workflow: Android symbol index" subsection in §Extractors; project mount table extended with `uw-android` + `uw-ios` rows. |

### Fixture layout

```
uw-android-mini-project/
├── REGEN.md
├── regen.sh
├── LICENSE                                  # MIT, vendor copy
├── settings.gradle.kts                      # 4 modules included
├── build.gradle.kts                         # root buildscript
├── gradle.properties                        # android.useAndroidX=true, etc.
├── gradle/
│   ├── libs.versions.toml                   # version catalog (Kotlin/AGP/Compose/Room)
│   └── wrapper/
│       └── gradle-wrapper.properties        # gradle distribution URL pinned
├── scip/
│   └── index.scip                           # committed binary
│
├── app-mini/
│   ├── build.gradle.kts                     # com.android.application + deps on 3 siblings
│   ├── src/main/AndroidManifest.xml         # Application + MainActivity
│   └── src/main/kotlin/io/horizontalsystems/uwmini/app/
│       ├── MyApp.kt                         # Application class (manual DI)
│       ├── MainActivity.kt                  # ComponentActivity, setContent { MainScreen() }
│       ├── MainScreen.kt                    # @Composable, uses WalletIcons + ChartView
│       ├── MainViewModel.kt                 # ViewModel + StateFlow
│       └── UiState.kt                       # sealed interface
│
├── core-mini/                               # KSP exercise via Room
│   ├── build.gradle.kts                     # com.android.library + ksp + room.compiler
│   ├── src/main/AndroidManifest.xml
│   └── src/main/kotlin/io/horizontalsystems/uwmini/core/
│       ├── db/
│       │   ├── WalletEntity.kt              # @Entity
│       │   ├── WalletDao.kt                 # @Dao with suspend + Flow
│       │   └── AppDatabase.kt               # @Database
│       ├── model/Wallet.kt                  # domain class
│       └── repository/WalletRepository.kt
│
├── components/
│   ├── icons-mini/                          # vendored verbatim from UW :components:icons
│   │   ├── build.gradle.kts                 # com.android.library + compose
│   │   ├── src/main/AndroidManifest.xml
│   │   └── src/main/kotlin/.../WalletIcons.kt
│   │
│   └── chartview-mini/                      # vendored adapted from UW :components:chartview
│       ├── build.gradle.kts
│       ├── src/main/AndroidManifest.xml
│       └── src/main/kotlin/.../ChartView.kt + ChartData.kt
```

### Vendoring strategy

| File / module | Source | Strategy |
|---|---|---|
| `LICENSE` | UW root | Literal copy |
| `gradle/libs.versions.toml` | UW root | Literal, trim blockchain-SDK entries |
| Root `settings.gradle.kts` + `build.gradle.kts` | UW root | Adapted — only 4 mini modules |
| `:components:icons-mini/WalletIcons.kt` | UW `:components:icons` | **Literal vendoring** — primary "real-world Compose" proof |
| `:components:chartview-mini/*.kt` | UW `:components:chartview` | Literal or pruned subset (if upstream >300 LOC) |
| `:core-mini/db/*` | UW `:core` Room files | Literal + strip blockchain-SDK imports |
| `:core-mini/repository/WalletRepository.kt` | UW patterns | Adapted — Room-only, no networking |
| `:app-mini/Main*.kt` | UW patterns | **Synthesized** in UW style — UW `:app` is too dependency-heavy to vendor verbatim |

**Pin policy:** REGEN.md captures UW commit SHA at fixture creation for reproducibility. Upstream tracking branch = `master` — future regens may roll forward. Oracle counts are re-verified on every regen.

## Architecture decisions

### From GIM-105 rev2 §Per-language action map — Kotlin (locked)

| Field | Kotlin |
|---|---|
| Manager token | `maven` (scip-java symbol scheme) |
| Package format | `<groupId>:<artifactId>` |
| Version token | `.` placeholder (Variant B strip) |
| Descriptor chain | Class `#`, method `().`, field `.`, package `/` |
| Generics policy | `keep_brackets` |
| Qualified_name | `<package>:<descriptor-chain>` after Variant B strip |
| Local symbols | Skip function-body locals; store class members globally |

### Decisions resolved in rev1 of this spec

| Decision | Resolution |
|---|---|
| Fixture source | Vendored from `unstoppable-wallet-android` (MIT, public, modern Compose+Room+multi-module). Operator's primary Android dev project (Medic) is private — cannot vendor. |
| Vendor pin policy | Track upstream `master`. SHA captured per-regen in REGEN.md for reproducibility, no fixed tag. |
| Module count | **4 modules** — `:app-mini`, `:core-mini`, `:components:icons-mini`, `:components:chartview-mini`. Mirrors UW topology. Single-module fixture (1) too weak for cross-module proof. |
| KSP exercise | **Room** (`@Entity`/`@Dao`/`@Database`). Matches UW's actual KSP usage (UW does NOT use Hilt). Generates `WalletDao_Impl` whose presence is AC#4. |
| Compose `@Composable` | Emitted by scip-java as standard METHOD. Specialized `SymbolKind.COMPOSABLE` is **out of scope** v1. |
| Fixture wrapper jar | **Not committed.** Text-only fixture, operator runs system Gradle. |
| `index.scip` binary | **Committed.** Existing pattern across all 4 prior language fixtures. |
| Test marker | `requires_scip_uw_android` — symmetric with `requires_scip_solidity`/`_python`/`_typescript`/`_java`. |
| Live-smoke target | UW-android (public). Medic deferred — would be private-only iMac demo without public artefact. |
| iOS pre-registration | UW-ios bind-mount + `register_project` lands in Slice 1. Extractor execution happens in Slice 3. |

## Non-goals (explicitly defer)

- **Android XML resources** — `AndroidManifest.xml` (activities/services/receivers/permissions/intent-filters), `res/layout/*.xml`, `res/values/*.xml` (strings/colors/dimens), R-class generated symbols → **Slice 2** (custom Android resource extractor).
- **DataBinding/ViewBinding generated classes** — also XML-related → Slice 2.
- **Compose `@Composable` as specialized SymbolKind** — semantic distinction (vs regular METHOD) not surfaced. Followup if Compose-specific queries become valuable.
- **KMP source-sets** (`commonMain`/`androidMain`/`iosMain`) + `expect`/`actual` resolution → **Slice 4** (after iOS).
- **Gradle dependency graph indexing** (modules, transitive deps, version conflicts) — out of scope, not a code-symbol concern.
- **ProGuard/R8 rules indexing** — low value, out of scope.
- **Hilt/Koin DI** — UW does not use either; nothing to exercise in fixture.
- **`uw-ios` extractor execution** — pre-mounted in this slice but extractor work is Slice 3.

## Test strategy

| Test layer | File | Purpose |
|---|---|---|
| Unit (parser-level) | `tests/extractors/unit/test_real_scip_fixtures.py` :: `TestUwAndroidMiniProjectFixture` | Parse committed `index.scip`, assert oracle counts + named symbols + cross-module USE pairs + qualified_name format. ~12 assertions. Skipped via `requires_scip_uw_android` marker. |
| Integration (extractor end-to-end) | `tests/extractors/integration/test_symbol_index_java_uw_integration.py` | Real Neo4j (testcontainers/compose-reuse) + Tantivy. Run `symbol_index_java` against the new fixture; assert IngestRun success, phase1+phase2 checkpoints, Tantivy doc count matches oracle. |
| Live-smoke (Phase 4.1, QAEngineer on iMac) | Manual MCP tool calls + Cypher | After deploy: `palace.ingest.run_extractor name=symbol_index_java project=uw-android` → verify `ok:true` + `nodes_written` > 5000; `palace.code.find_references qualified_name=WalletDao project=uw-android` → returns multi-occurrence result. |

Drift-check: regen UW → `index.scip` differs → oracle counts must update. Pattern symmetric to oz-v5-mini.

## Acceptance criteria

| AC# | Condition | Verification |
|---|---|---|
| AC#1 | Vendored fixture compiles standalone | `./gradlew :app-mini:compileDebugKotlin :core-mini:compileDebugKotlin :components:icons-mini:compileDebugKotlin :components:chartview-mini:compileDebugKotlin` exit 0 |
| AC#2 | scip-java emits valid `index.scip` | `npx @sourcegraph/scip-java index` exit 0; file parses via `parse_scip_file()` without exception |
| AC#3 | Oracle counts match (locked Phase 1.0) | All assertions in `TestUwAndroidMiniProjectFixture` pass |
| **AC#4** | **KSP-generated `WalletDao_Impl` present as DEF** | Test: `assert any("WalletDao_Impl" in n for n in def_qnames)` — primary KSP proof |
| AC#5 | Cross-module USE resolves | 5 USE-pair tests: app→repo, app→icons, app→chart, repo→dao, dao_impl→dao |
| AC#6 | `@Composable` qualified_names well-formed | `MainScreen` + `ChartView` both Composable; qualified_name has no scheme prefix; language detected `KOTLIN` |
| AC#7 | Integration test green | `test_symbol_index_java_uw_integration.py` passes locally + on iMac |
| AC#8 | Docker-compose bind-mounts added | 2 entries in `docker-compose.yml` (uw-android + uw-ios) |
| AC#9 | `PALACE_SCIP_INDEX_PATHS` documented | `.env.example` shows Android slug example |
| AC#10 | CLAUDE.md updated | New "Operator workflow: Android symbol index" subsection + 2 new project mount rows |

### Phase 4.1 live-smoke evidence (QAEngineer)

```
[1] palace.ingest.list_extractors → returns existing list (no new extractor expected)
[2] palace.memory.register_project slug=uw-android → ok:true
[3] On iMac: cd /Users/Shared/Android/unstoppable-wallet-android
            ./gradlew compileDebugKotlin
            npx @sourcegraph/scip-java index --output ./scip/index.scip
[4] Update .env: PALACE_SCIP_INDEX_PATHS={..., "uw-android":"/repos/uw-android/scip/index.scip"}
[5] Restart palace-mcp container
[6] palace.ingest.run_extractor name=symbol_index_java project=uw-android
    → ok:true, nodes_written > 5000 (full UW codebase)
[7] palace.code.find_references qualified_name=WalletDao project=uw-android
    → returns DEFs + USEs across UW codebase
[8] palace.memory.lookup entity_type=IngestRun filters={"source":"extractor.symbol_index_java"}
    → confirms run record persisted
```

## Risks

| # | Risk | Mitigation |
|---|---|---|
| **R1** | scip-java may NOT pick up KSP-generated source (`WalletDao_Impl` in `build/generated/ksp/.../sources/`) | **Phase 1.0 prerequisite:** end-to-end `regen.sh` + `grep WalletDao_Impl scip/index.scip`. If 0 → add explicit `sourceSets["main"].kotlin.srcDir(...)` for KSP outputs in `:core-mini/build.gradle.kts`. If still 0 → escalate to spec rev2 with workaround OR scip-java patch as separate followup. |
| R2 | scip-java may emit per-module `.scip` instead of one merged file | Phase 1.0 verify: `len(index.documents)` after parse. If per-module → adapt `regen.sh` to aggregator pattern (Solidity precedent). |
| R3 | AGP/Kotlin/Compose Compiler version drift | `REGEN.md` pins UW SHA + scip-java version. If versions conflict, fixture pins AGP **older** than upstream UW (documented divergence). |
| R4 | UW transitive deps pull blockchain SDKs into fixture | Vendor `:core` only as Room-related kernel; synthesize `:app-mini` rather than copying real UW `:app`. Documented in REGEN.md "Vendoring strategy" section. |
| R5 | `@Composable` indistinguishable from regular METHOD in index | **Accept as v1 limitation.** Document in Non-goals. Followup if Compose-specific queries needed. |
| R6 | iMac live-smoke needs operator manual ops (clone, mount, rebuild) | Documented in CLAUDE.md (existing pattern). QAEngineer Phase 4.1 owns deployment. |
| R7 | `index.scip` binary creates noisy diffs on regen | Existing pattern across 4 fixtures. Acceptable. |
| R8 | Effort underestimation if R1/R2/R3 surface | Plan includes Phase 1.0 prerequisite **before** PE Phase 2. Spec rev2 if early-discover blocks plan. **Buffer:** 5d PE + 2d = 7d. |

## Effort estimate

**PE Phase 2: 4-5 days. Total wall-clock with phase ritual + buffer: ~7-9 days.**

Phase breakdown (informational):
- Phase 1.0 Board oracle gate: 0.5d — regen end-to-end, fill manual oracle table
- Phase 1.1 CTO formalize: 0.25d
- Phase 1.2 CR plan-first review: 0.25d
- **Phase 2 PE TDD implement: 4-5d** — vendoring + tests + integration + CLAUDE.md (largest unit)
- Phase 3.1 CR mechanical review: 0.25d
- Phase 3.2 Opus adversarial review: 0.25d
- Phase 4.1 QA live-smoke: 0.5d
- Phase 4.2 CTO merge: 0.1d
- Buffer: 1-2d for R1/R2/R3 surprises (KSP source visibility, multi-module aggregation, AGP version conflicts)

## iMac ops setup (parallel to slice — not blocking PR merge)

1. `git clone https://github.com/horizontalsystems/unstoppable-wallet-android.git /Users/Shared/Android/unstoppable-wallet-android`
2. `git clone https://github.com/horizontalsystems/unstoppable-wallet-ios.git /Users/Shared/Ios/unstoppable-wallet-ios`
3. Edit `docker-compose.yml` on iMac checkout: add 2 bind-mounts under `palace-mcp.volumes`.
4. `bash paperclips/scripts/imac-deploy.sh --target <merge-sha>` — restart palace-mcp with new mounts.
5. Via MCP: `palace.memory.register_project slug=uw-android` + `slug=uw-ios`.
6. (For Phase 4.1 live-smoke) — `./gradlew compileDebugKotlin` + `scip-java index` on UW-android, set `PALACE_SCIP_INDEX_PATHS`, restart, run `symbol_index_java`.

## Operator review verification (rev1)

| Operator question | Resolution |
|---|---|
| 1. Vendor pin policy | `master` (rolling), SHA captured per-regen in REGEN.md. |
| 2. UW-android + UW-ios placement on iMac | Both downloaded + bind-mounted in this slice. Android under `/Users/Shared/Android/`, iOS under `/Users/Shared/Ios/` (existing convention). |
| 3. Live-smoke target | UW-android (public). Medic deferred (private). |
| 4. Other open questions (Q4-Q8 from spec §4) | All accepted with brainstorm-recommended defaults. |
