# Slice 1 — Android scip-java AGP validation

**Status:** Board draft (rev3, 2026-04-30) — paperclip-issue [GIM-127](https://paperclip.ant013.work/issues/60cb7d81-22ec-4261-8150-14b147f7f64e); rev3 surfaces UW-upstream reality discovered in Phase 1.0 trial; needs CR re-review before PE Phase 2 begins.
**Revision history:**
- rev1 (2026-04-30) — initial draft from operator brainstorm Q1-Q5
- rev2 (2026-04-30) — operator review surfaced 9 issues; fixes: paths qualified `services/palace-mcp/`-rooted, `gradle` (system) replaces `./gradlew`, AC#4 conditional on Phase 1.0 KSP-source-visibility gate, AC#7 `find_references` removed (latent bug `code_composite.py:449` hardcoded `symbol_index_python` — separate followup), `requires_scip_uw_android` marker as explicit pyproject.toml deliverable, integration test pattern flagged as NEW (real fixture vs existing synthetic), iOS `uw-ios` bind-mount/register decoupled from Slice 1 ACs (now optional ops-prep), non-iMac contributor override note added, "максимум эффективности" mandate scoped to scip-java-visible sources
- rev3 (2026-04-30) — Phase 1.0 trial on UW master `f830bb52` revealed two spec-assumption mistakes: (1) `:components:icons` upstream is **resources-only** (XML drawables, no Kotlin), not a Compose icons object — `:components:icons-mini/WalletIcons.kt` switches from "literal vendoring" to **synthesized in UW style** (~30-50 LOC); (2) Room (`@Entity`/`@Dao`/`@Database`) lives in UW `:app/src/main/java/.../core/storage/` (20+ DAOs), not `:core` — `:core-mini/db/*` switches from "literal vendor" to **synthesized mirroring UW DAO patterns**, placed in `:core-mini` to preserve multi-module proof structure. Net: 1 of 4 modules truly vendored verbatim (`:components:chartview-mini`), 3 of 4 synthesized. Slice goal unchanged; module count unchanged; ACs unchanged.
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
   - oracle-backed assertions on def/use/cross-module/KSP-generated (KSP cond on Phase 1.0)
   - real Android project (UW-android) registered + live-smoke
   - UW-ios clone is OPTIONAL ops-prep, not Slice 1 deliverable
```

**Per-slice "максимум эффективности" mandate:** each language slice ships **full Java/Kotlin source DEF+USE coverage for scip-java-visible sources** from day 1. Resource-layer coverage (XML/Manifest/R-class/ViewBinding) is deferred to Slice 2; KMP cross-target resolution is deferred to Slice 4. No Solidity-style v1-stub-then-followup pattern *within the declared scope*.

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
| `palace.code.find_references()` MCP tool | Unchanged in Slice 1. **Known broken for non-Python extractors** — see Non-goals; separate followup (proposed GIM-126). |
| Existing tests for jvm-mini fixture | Unchanged — coexist with new uw-android-mini tests. |

### What's new

| Artefact | Description |
|---|---|
| `services/palace-mcp/tests/extractors/fixtures/uw-android-mini-project/` | Vendored multi-module Android fixture, ~28-32 files. |
| `services/palace-mcp/tests/extractors/fixtures/uw-android-mini-project/REGEN.md` | Vendor source pin (UW commit SHA captured at fixture creation, upstream branch = `master`), regen script doc, manual oracle table. |
| `services/palace-mcp/tests/extractors/fixtures/uw-android-mini-project/regen.sh` | `gradle compileDebugKotlin` (all 4 modules) + `npx @sourcegraph/scip-java index --output ./scip/index.scip`. |
| `services/palace-mcp/tests/extractors/fixtures/uw-android-mini-project/scip/index.scip` | Pre-generated scip-java output, committed binary (~80-200 KB). |
| `services/palace-mcp/tests/extractors/fixtures/uw-android-mini-project/LICENSE` | MIT, copy from upstream UW. |
| `TestUwAndroidMiniProjectFixture` class in `services/palace-mcp/tests/extractors/unit/test_real_scip_fixtures.py` | ~12 oracle-backed assertions (def counts, KSP-generated symbol present, cross-module USE pairs, qualified_name format). Skipped via `requires_scip_uw_android` marker if `index.scip` missing. |
| `services/palace-mcp/tests/extractors/integration/test_symbol_index_java_uw_integration.py` | **NEW INTEGRATION-TEST PATTERN** — distinct from existing `test_symbol_index_java_integration.py` which uses synthetic `build_jvm_scip_index()` factory + `MagicMock` settings. New test reads committed fixture `index.scip` from disk + uses real Neo4j (compose-reuse) + asserts Tantivy doc count against oracle. Sets precedent for future fixture-based integration tests. |
| `services/palace-mcp/pyproject.toml` `[tool.pytest.ini_options].markers` | **Add `requires_scip_uw_android` marker** — explicit one-line edit, symmetric with existing `requires_scip_typescript/python/java/solidity`. |
| `docker-compose.yml` additions | **1 bind-mount** added: `/Users/Shared/Android/unstoppable-wallet-android:/repos/uw-android:ro`. iOS mount (`uw-ios`) is **NOT** in this slice — see §"iMac ops setup" optional ops-prep. |
| `.env.example` annotation | Document `PALACE_SCIP_INDEX_PATHS` extension for Android slug. |
| `CLAUDE.md` updates | New "Operator workflow: Android symbol index" subsection in §Extractors; project mount table extended with `uw-android` row; explicit note that real-project bind-mounts (`gimle`, `uw-android`) are operator-iMac-specific paths and non-iMac contributors should use `docker-compose.override.yml` to redirect. |

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
│   └── libs.versions.toml                   # version catalog (Kotlin/AGP/Compose/Room)
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

### Vendoring strategy (rev3 — corrected against UW reality discovered in Phase 1.0 trial 2026-04-30)

| File / module | Source | Strategy |
|---|---|---|
| `LICENSE` | UW root | Literal copy |
| `gradle/libs.versions.toml` | UW root | Literal, trim blockchain-SDK entries (web3j, bitcoin/ethereum/solana/tron/ton kits, etc.) |
| Root `settings.gradle.kts` + `build.gradle.kts` + `gradle.properties` | UW root | Adapted — only 4 mini modules |
| **`:components:chartview-mini/*.kt`** | UW `:components:chartview` | **LITERAL VENDORING** — only true verbatim vendor in fixture; primary "real-world Compose" proof. Pick 2-4 source files (e.g., `ChartView.kt`, `ChartData.kt`) + minimum dependencies. View-binding-using files OK — proves scip-java handles non-Compose Kotlin too. |
| `:components:icons-mini/WalletIcons.kt` | **No upstream** — UW `:components:icons` is **resources-only** (XML drawables, 0 Kotlin) | **SYNTHESIZED** in UW style — `object WalletIcons { val Send: ImageVector = ...; val Receive = ...; val Swap = ... }` (~30-50 LOC). Provides "Compose-only module without KSP/DB" multi-module proof. Could not be vendored as originally planned. |
| `:core-mini/db/*` (Room entities, DAOs, Database) | **No upstream in `:core`** — UW Room lives in `:app/src/main/java/.../core/storage/` (20+ DAOs + AppDatabase). Strategy: **MIRROR** UW patterns (snake-case table names, suspend + Flow, `@Insert`/`@Update`/`@Delete`/`@Query` mix) but place in our `:core-mini`. | **SYNTHESIZED** following UW DAO conventions. Justification: vendoring full UW `:app` storage is infeasible (transitive deps explode); placing Room in `:core-mini` (not `:app-mini`) keeps multi-module proof structure clean. |
| `:core-mini/repository/WalletRepository.kt` | UW DAO usage patterns | **SYNTHESIZED** — Room-only, no networking |
| `:app-mini/Main*.kt` | UW Activity/Compose patterns | **SYNTHESIZED** in UW style — UW `:app` is too dependency-heavy to vendor verbatim |

**Net vendoring count:** 1 of 4 modules truly vendored verbatim (`:components:chartview-mini`); 3 of 4 synthesized. Original spec rev1/rev2 wording "vendored 4 modules" was over-stated — corrected here. Slice 1 still proves "scip-java handles real Android" because (a) chartview vendor IS real UW Kotlin code, (b) all dependencies pinned to UW's `libs.versions.toml` (Kotlin 2.3.10, AGP equivalent, Compose 1.10.2, Room 2.8.1, KSP 2.3.2 — modern), (c) `:app-mini` synthesis uses real UW Compose+Hilt-free patterns.

**Pin policy:** REGEN.md captures UW commit SHA `f830bb528998855dcfe276c1e4ff927a1e2cd9a1` (Phase 1.0 trial 2026-04-30) for reproducibility. Upstream tracking branch = `master` — future regens may roll forward. Oracle counts are re-verified on every regen.

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

### Decisions resolved (rev1 + rev2 + rev3)

| Decision | Resolution |
|---|---|
| Fixture source | Vendored from `unstoppable-wallet-android` (MIT, public, modern Compose+Room+multi-module). Operator's primary Android dev project (Medic) is private — cannot vendor. |
| Vendor pin policy | Track upstream `master`. SHA captured per-regen in REGEN.md for reproducibility, no fixed tag. |
| Module count | **4 modules** — `:app-mini`, `:core-mini`, `:components:icons-mini`, `:components:chartview-mini`. Mirrors UW topology. Single-module fixture (1) too weak for cross-module proof. |
| KSP exercise | **Room** (`@Entity`/`@Dao`/`@Database`). Matches UW's actual KSP usage (UW does NOT use Hilt). |
| KSP source visibility (rev2) | **Conditional on Phase 1.0 gate** — see AC#4. Branch A: scip-java sees KSP source by default. Branch B: workaround in `:core-mini/build.gradle.kts` OR followup-issue replaces AC#4. PE Phase 2 blocked until branch locked. |
| Compose `@Composable` | Emitted by scip-java as standard METHOD. Specialized `SymbolKind.COMPOSABLE` is **out of scope** v1. |
| Gradle invocation (rev2) | **System `gradle` (≥8.x)**, no wrapper jar/script in fixture. Symmetric with `jvm-mini-project` precedent. |
| `index.scip` binary | **Committed.** Existing pattern across all 4 prior language fixtures. |
| Test marker | `requires_scip_uw_android` — explicit one-line addition to `services/palace-mcp/pyproject.toml` `[tool.pytest.ini_options].markers` (NOT pre-existing). |
| Integration test pattern (rev2) | **NEW pattern** — distinct from existing `test_symbol_index_java_integration.py` (which uses synthetic SCIP factory + MagicMock). New pattern: real fixture `.scip` from disk + real Neo4j (compose-reuse) + Tantivy doc count oracle. Sets precedent for future fixture-based integration tests across all languages. |
| Live-smoke target | UW-android (public). Medic deferred — would be private-only iMac demo without public artefact. |
| `find_references` proof (rev2) | **Removed from AC#7** — `code_composite.py:449` has latent bug hardcoding `symbol_index_python` for IngestRun lookup (affects all 4 language extractors). **Separate followup-issue** (proposed GIM-126). Slice 1 live-smoke proves via `palace.memory.lookup` instead. |
| iOS pre-registration (rev2) | **Decoupled from Slice 1 ACs.** UW-ios clone is OPTIONAL ops-prep with no Slice 1 deliverable; `docker-compose.yml` adds ONLY `uw-android` mount. iOS-related compose changes land in Slice 3. |
| Non-iMac contributors (rev2) | `docker-compose.yml` real-project mounts use absolute Mac paths (operator iMac convention). Contributors on other platforms use `docker-compose.override.yml`. Documented in CLAUDE.md per AC#10. |
| **UW upstream reality (rev3)** | Phase 1.0 trial on UW master `f830bb52` revealed: `:components:icons` = XML resources only (no Kotlin); `:core` = generic utils (Room actually in `:app/.../storage/`). Spec rev1/rev2 wrongly assumed icons had a `WalletIcons.kt` Kotlin object and core had Room. **Resolution**: `:components:icons-mini` and `:core-mini` switch from "literal vendor" to "synthesized in UW style" — same module structure, same ACs, same KSP exercise via Room. Only `:components:chartview-mini` remains literal vendor (UW source confirmed Kotlin Compose + view-binding). |
| **Synthesis vs vendoring trade-off (rev3)** | Spec rev1 oversold "vendored from UW" — actual ratio is 1:3 (vendored:synthesized). This DOES NOT weaken the slice because: (a) Compose vendor IS real (chartview); (b) all version pins (Kotlin 2.3.10, Compose 1.10.2, Room 2.8.1, KSP 2.3.2, AGP) come from UW's `libs.versions.toml` literal; (c) synthesized code FOLLOWS UW patterns (same Compose state-hoisting, same Room DAO conventions). Operator's "максимум эффективности" mandate satisfied — fixture exercises real-world AGP+Compose+KSP toolchain even when source is partially synthesized. |

## Non-goals (explicitly defer)

- **Android XML resources** — `AndroidManifest.xml` (activities/services/receivers/permissions/intent-filters), `res/layout/*.xml`, `res/values/*.xml` (strings/colors/dimens), R-class generated symbols → **Slice 2** (custom Android resource extractor).
- **DataBinding/ViewBinding generated classes** — also XML-related → Slice 2.
- **Compose `@Composable` as specialized SymbolKind** — semantic distinction (vs regular METHOD) not surfaced. Followup if Compose-specific queries become valuable.
- **KMP source-sets** (`commonMain`/`androidMain`/`iosMain`) + `expect`/`actual` resolution → **Slice 4** (after iOS).
- **Gradle dependency graph indexing** (modules, transitive deps, version conflicts) — out of scope, not a code-symbol concern.
- **ProGuard/R8 rules indexing** — low value, out of scope.
- **Hilt/Koin DI** — UW does not use either; nothing to exercise in fixture.
- **`uw-ios` ALL** — clone+mount+register+extractor — **all** iOS-related work is Slice 3. UW-ios clone is a discretionary ops-prep convenience here, NOT a deliverable.
- **`palace.code.find_references` lang-agnostic fix** — `code_composite.py:449` hardcodes `symbol_index_python` for IngestRun lookup, breaking `find_references` for Java/TS/Solidity ingest projects. **Tracked as separate followup** (proposed GIM-126). Affects ALL prior language extractors, not Android-specific.

## Test strategy

| Test layer | File | Purpose |
|---|---|---|
| Unit (parser-level) | `services/palace-mcp/tests/extractors/unit/test_real_scip_fixtures.py` :: `TestUwAndroidMiniProjectFixture` | Parse committed `index.scip`, assert oracle counts + named symbols + cross-module USE pairs + qualified_name format. ~12 assertions. Skipped via `requires_scip_uw_android` marker. |
| Integration (extractor end-to-end) | `services/palace-mcp/tests/extractors/integration/test_symbol_index_java_uw_integration.py` | Real Neo4j (testcontainers/compose-reuse) + Tantivy. Run `symbol_index_java` against the new fixture; assert IngestRun success, phase1+phase2 checkpoints, Tantivy doc count matches oracle. |
| Live-smoke (Phase 4.1, QAEngineer on iMac) | Manual MCP tool calls + Cypher | After deploy: `palace.ingest.run_extractor name=symbol_index_java project=uw-android` → verify `ok:true` + `nodes_written` > 5000; `palace.memory.lookup entity_type=IngestRun filters={"source":"extractor.symbol_index_java"}` → confirms run record. **Note:** `palace.code.find_references` is NOT used as proof — see "Known limitations" below. |

Drift-check: regen UW → `index.scip` differs → oracle counts must update. Pattern symmetric to oz-v5-mini.

## Acceptance criteria

| AC# | Condition | Verification |
|---|---|---|
| AC#1 | Vendored fixture compiles standalone | `gradle :app-mini:compileDebugKotlin :core-mini:compileDebugKotlin :components:icons-mini:compileDebugKotlin :components:chartview-mini:compileDebugKotlin` exit 0 (system Gradle ≥8.x; no wrapper jar in fixture — symmetric with `jvm-mini-project`) |
| AC#2 | scip-java emits valid `index.scip` | `npx @sourcegraph/scip-java index` exit 0; file parses via `parse_scip_file()` without exception |
| AC#3 | Oracle counts match (locked Phase 1.0) | All assertions in `TestUwAndroidMiniProjectFixture` pass |
| **AC#4 (CONDITIONAL — Phase 1.0 gate)** | KSP-generated `WalletDao_Impl` resolution status fixed BEFORE Phase 2 starts. **Branch A** (default expected): `regen.sh` end-to-end produces `index.scip` with `WalletDao_Impl` as DEF — AC#4 hard, test `assert any("WalletDao_Impl" in n for n in def_qnames)`. **Branch B**: Phase 1.0 confirms scip-java does NOT see KSP source — spec **enters rev2** before PE Phase 2 starts; either (B-1) workaround `sourceSets["main"].kotlin.srcDir("build/generated/ksp/.../sources/...")` in `:core-mini/build.gradle.kts` makes `WalletDao_Impl` visible, OR (B-2) AC#4 is replaced by "scip-java handles non-KSP Kotlin only" + explicit followup-issue for KSP support. PE Phase 2 does NOT start until branch is locked. |
| AC#5 | Cross-module USE resolves | 5 USE-pair tests: app→repo, app→icons, app→chart, repo→dao, dao_impl→dao (last pair conditional on AC#4 Branch A) |
| AC#6 | `@Composable` qualified_names well-formed | `MainScreen` + `ChartView` both Composable; qualified_name has no scheme prefix; language detected `KOTLIN` |
| AC#7 | Integration test green | `test_symbol_index_java_uw_integration.py` passes locally + on iMac |
| AC#8 | Docker-compose bind-mount added | **1 entry** in `docker-compose.yml` (`uw-android`) — see "Known limitations" for `uw-ios` deferral |
| AC#9 | `PALACE_SCIP_INDEX_PATHS` documented | `.env.example` shows Android slug example |
| AC#10 | CLAUDE.md updated | New "Operator workflow: Android symbol index" subsection + 1 new project mount row (`uw-android`) + non-iMac contributor override note |

### Phase 4.1 live-smoke evidence (QAEngineer)

```
[1] palace.ingest.list_extractors → returns existing list (no new extractor expected)
[2] palace.memory.register_project slug=uw-android → ok:true
[3] On iMac: cd /Users/Shared/Android/unstoppable-wallet-android
            gradle compileDebugKotlin
            npx @sourcegraph/scip-java index --output ./scip/index.scip
[4] Update .env: PALACE_SCIP_INDEX_PATHS={..., "uw-android":"/repos/uw-android/scip/index.scip"}
[5] Restart palace-mcp container
[6] palace.ingest.run_extractor name=symbol_index_java project=uw-android
    → ok:true, nodes_written > 5000 (full UW codebase)
[7] palace.memory.lookup entity_type=IngestRun filters={"source":"extractor.symbol_index_java"}
    → confirms run record persisted with success=true + matching project
```

### Known limitations (this slice)

- **`palace.code.find_references` is NOT exercised as Slice 1 proof.** `code_composite.py:449` hard-codes the IngestRun extractor-name lookup to `symbol_index_python`, so calling `find_references` after a successful `symbol_index_java` ingest returns `project_not_indexed` even though Tantivy contains the data. **Out of scope for Slice 1; tracked as separate followup** (proposed: GIM-126 — make `_query_ingest_run_for_project` lang-agnostic OR check ANY successful IngestRun regardless of extractor). Affects all four current language extractors (TS/Python/Java/Solidity), not specific to Android — discovery surfaced during Slice 1 brainstorm 2026-04-30.
- **`@Composable` indistinguishable from regular METHOD** in index — scip-java emits both with same SymbolKind. No Compose-specific queries possible via `palace.code.*` v1.
- **iOS bind-mount + register (`uw-ios`)** deferred to Slice 3. See "iMac ops setup" optional ops-prep — operator MAY clone+mount in this window but it is NOT a Slice 1 deliverable nor merge gate.

## Risks

| # | Risk | Mitigation |
|---|---|---|
| **R1** | scip-java may NOT pick up KSP-generated source (`WalletDao_Impl` in `build/generated/ksp/.../sources/`) | **Encoded as AC#4 conditional Phase 1.0 gate.** Phase 1.0 = end-to-end `regen.sh` + `grep WalletDao_Impl scip/index.scip`. If 0 → Branch B-1 workaround `sourceSets["main"].kotlin.srcDir(...)` in `:core-mini/build.gradle.kts`. If still 0 → Branch B-2: AC#4 replaced + spec rev3 + followup-issue for scip-java KSP support. PE Phase 2 blocked until branch locked. |
| R2 | scip-java may emit per-module `.scip` instead of one merged file | Phase 1.0 verify: `len(index.documents)` after parse. If per-module → adapt `regen.sh` to aggregator pattern (Solidity precedent). |
| R3 | AGP/Kotlin/Compose Compiler version drift | `REGEN.md` pins UW SHA + scip-java version. If versions conflict, fixture pins AGP **older** than upstream UW (documented divergence). |
| R4 | UW transitive deps pull blockchain SDKs into fixture | Vendor `:core` only as Room-related kernel; synthesize `:app-mini` rather than copying real UW `:app`. Documented in REGEN.md "Vendoring strategy" section. |
| R5 | `@Composable` indistinguishable from regular METHOD in index | **Accept as v1 limitation.** Document in Non-goals. Followup if Compose-specific queries needed. |
| R6 | iMac live-smoke needs operator manual ops (clone, mount, rebuild) | Documented in CLAUDE.md (existing pattern). QAEngineer Phase 4.1 owns deployment. |
| R7 | `index.scip` binary creates noisy diffs on regen | Existing pattern across 4 fixtures. Acceptable. |
| R8 | Effort underestimation if R1/R2/R3 surface | Plan includes Phase 1.0 prerequisite **before** PE Phase 2. Spec rev3 if early-discover blocks plan. **Buffer:** PE 4-5d + ritual + 1-2d buffer = ~7-9d wall-clock. |

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

## iMac ops setup

### Required for Slice 1 (gates AC#7-AC#10 — operator-iMac-specific paths)

1. `git clone https://github.com/horizontalsystems/unstoppable-wallet-android.git /Users/Shared/Android/unstoppable-wallet-android`
2. Edit `docker-compose.yml` (committed via this slice's PR): adds **1 bind-mount** under `palace-mcp.volumes` for `uw-android`.
3. `bash paperclips/scripts/imac-deploy.sh --target <merge-sha>` — restart palace-mcp with the new mount.
4. Via MCP: `palace.memory.register_project slug=uw-android`.
5. For Phase 4.1 live-smoke: `gradle compileDebugKotlin` + `scip-java index` on UW-android, set `PALACE_SCIP_INDEX_PATHS`, restart, run `symbol_index_java`.

### Optional ops-prep (NOT a Slice 1 gate — operator-discretion, supports future Slice 3)

While you're at it on iMac, you MAY also (entirely optional, no AC depends on these):
- `git clone https://github.com/horizontalsystems/unstoppable-wallet-ios.git /Users/Shared/Ios/unstoppable-wallet-ios` — saves time during Slice 3 setup.
- This slice does NOT add a `uw-ios` bind-mount to `docker-compose.yml`. iOS-related compose changes land in Slice 3 alongside iOS extractor work.

### Non-iMac contributors

`docker-compose.yml` real-project mounts (`gimle`, `uw-android`) use absolute Mac paths (`/Users/Shared/...`) for operator-iMac convenience. Non-iMac contributors should:
- Either create `docker-compose.override.yml` redirecting these paths to local clones
- Or run `docker compose --profile review up` excluding the affected service and use the fixture-only path (`./services/palace-mcp/tests/extractors/fixtures/...` mounts work cross-platform)
- This is documented in CLAUDE.md as part of AC#10.

## Operator review verification

### rev1 (initial brainstorm Q1-Q5)

| Operator question | Resolution |
|---|---|
| 1. Vendor pin policy | `master` (rolling), SHA captured per-regen in REGEN.md. |
| 2. UW-android + UW-ios placement on iMac | Android under `/Users/Shared/Android/`, iOS under `/Users/Shared/Ios/` (existing convention). **rev2 update:** iOS decoupled from Slice 1 ACs. |
| 3. Live-smoke target | UW-android (public). Medic deferred (private). |
| 4. Other open questions (Q4-Q8 from spec §4) | All accepted with brainstorm-recommended defaults. |

### rev3 (Phase 1.0 trial on dev Mac, 2026-04-30)

| # | Phase 1.0 finding | Resolution in rev3 |
|---|---|---|
| Reality 1 | `:components:icons` upstream — resources-only (XML drawables, 0 Kotlin) | `:components:icons-mini/WalletIcons.kt` SYNTHESIZED in UW style (`object WalletIcons { val Send/Receive/Swap: ImageVector }`). Module preserved for multi-module proof. |
| Reality 2 | Room (`@Entity`/`@Dao`/`@Database`) lives in UW `:app/.../storage/`, not `:core` | `:core-mini/db/*` SYNTHESIZED following UW DAO patterns (snake-case tables, suspend + Flow, mixed Insert/Update/Delete/Query). Placed in `:core-mini` (not `:app-mini`) to preserve multi-module structure + Room/KSP exercise. |
| Reality 3 | UW master pin captured | SHA `f830bb528998855dcfe276c1e4ff927a1e2cd9a1` (REGEN.md will document). |
| Toolchain | Dev Mac has Java 21 LTS, Gradle 9.3.1, Node 23, npx 11.6 | Gradle 9 may need AGP compat workaround; surface in REGEN.md if encountered. |
| Vendoring honesty | rev1/rev2 implied "4 modules vendored from UW" | rev3 corrects: 1 truly vendored (chartview), 3 synthesized in UW style with all version pins from UW `libs.versions.toml`. |

### rev2 (operator review of rev1 spec)

| # | Operator finding | Resolution in rev2 |
|---|---|---|
| Critical 1 | `find_references` hardcoded to `symbol_index_python` (`code_composite.py:449`) | Operator chose option (b): remove from AC#7, open separate followup-issue (proposed GIM-126). Live-smoke uses `palace.memory.lookup` instead. |
| Critical 2 | Path references missing `services/palace-mcp/` prefix | Fixed throughout — all paths now repo-rooted. |
| Critical 3 | `./gradlew` vs system `gradle` conflict | Use system `gradle` (≥8.x). No wrapper in fixture. Symmetric with `jvm-mini-project`. |
| Critical 4 | AC#4 phrased as guarantee, but R1 acknowledges KSP-source-visibility risk | AC#4 → **conditional Phase 1.0 gate**. Branch A (default), Branch B (workaround), B-2 (followup-issue). PE Phase 2 blocked until branch locked. |
| Medium 5 | `requires_scip_uw_android` marker doesn't exist yet | Explicit deliverable in "What's new" — `pyproject.toml` edit. |
| Medium 6 | New integration test pattern (real fixture + Neo4j) is stronger, not symmetric | Flagged as **NEW PATTERN** in "What's new" + Decisions table. Sets precedent for future fixtures. |
| Medium 7 | "Full DEF + USE coverage from day 1" wider than declared scope | Qualified to "**scip-java-visible Kotlin/Java sources** from day 1; resource layer → Slice 2; KMP → Slice 4". |
| Medium 8 | docker-compose.yml Mac-specific mounts may break non-iMac contributors | Existing precedent (gimle line 53), but rev2 adds explicit override note in CLAUDE.md (per AC#10). |
| Medium 9 | iOS scope creep without immediate validation | Operator chose option (b): UW-ios is OPTIONAL ops-prep, NOT a Slice 1 deliverable nor merge gate. AC#8 reduced from "2 mounts" to "1 mount" (uw-android only). |
