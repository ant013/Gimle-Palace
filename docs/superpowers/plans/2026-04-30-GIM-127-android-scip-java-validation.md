# Slice 1 — Android scip-java AGP validation Implementation Plan (rev3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Revision history:**
- rev1 (2026-04-30) — initial plan, 14 tasks
- rev2 (2026-04-30) — Phase 1.2 CodeReviewer review (paperclip GIM-127 comment 2026-04-30T07:34Z) returned REQUEST CHANGES: CRITICAL #1 (AC#5 only 1 of 5 USE-pair tests in Task 9), WARNING #1 (Task 10 missing Tantivy doc count assertion despite description claim), WARNING #2 (Composable tests missing explicit `language == Language.KOTLIN` per AC#6). All three fixed in rev2.
- rev3 (2026-04-30) — Spec rev3 landed (commit `b0e4607`) reflecting Phase 1.0 trial finding: UW upstream `:components:icons` is XML-resources-only (no Kotlin) and Room lives in `:app/.../storage/` not `:core`. Plan adapts: Tasks 3 + 5 switch from "verify vendored" to "verify Phase 1.0 SYNTHESIZED outputs". Task 4 (`:components:chartview-mini`) stays "verify vendored verbatim" — only true vendor in fixture. Module count + ACs unchanged.

**Goal:** Validate that the existing `symbol_index_java` extractor (GIM-111) handles real-world Android projects (Compose + multi-module + KSP via Room) end-to-end without code changes. Ship vendored fixture from `unstoppable-wallet-android`, oracle-backed unit + integration tests, docker-compose bind-mount, and CLAUDE.md operator workflow doc.

**Architecture:** Pure fixture + tests + config + docs slice. **No new extractor code.** Re-uses `symbol_index_java`, `scip_parser`, 101a foundation substrate. New deliverables: vendored multi-module fixture (`uw-android-mini-project`), **17 oracle-backed unit assertions** (rev2; was 13 — added 4 cross-module USE pairs per CR CRITICAL #1), NEW integration-test pattern (real fixture `.scip` from disk + real Neo4j compose-reuse — distinct from existing synthetic `build_jvm_scip_index()` pattern in `test_symbol_index_java_integration.py`) **with Tantivy doc count oracle assertion** (rev2; CR WARNING #1), 1 docker-compose bind-mount, pyproject.toml marker, CLAUDE.md updates.

**Tech Stack:** Python 3.12, palace-mcp extractor framework (101a substrate, lang-agnostic since GIM-104), Kotlin 1.9+, AGP 8.x, Jetpack Compose, Room (KSP), system Gradle ≥8.x, scip-java upstream (Sourcegraph), pytest, testcontainers/compose-reuse Neo4j, Tantivy.

**Predecessor SHA:** `d6e6d35` (GIM-124 Solidity merged 2026-04-29).
**Spec:** `docs/superpowers/specs/2026-04-30-android-scip-java-validation.md` (rev2).
**Companion (NOT a blocker):** GIM-126 (`palace.code.find_references` lang-agnostic IngestRun gate fix) lands separately on `feature/GIM-126-find-references-lang-agnostic`. Slice 1 lives without it; once GIM-126 merges, Slice 1 spec rev3 can restore `find_references` step in Phase 4.1 evidence.

---

## Phase 1.0: Oracle gate (Board completes BEFORE PE Phase 2 starts)

> **Plan-first / GIM-114 discipline gate.** Plan acceptance criterion AC#3 requires concrete oracle counts in `TestUwAndroidMiniProjectFixture`. Board (or operator-acting-as-Board) performs trial vendoring + regen + count BEFORE PythonEngineer starts Phase 2. Without locked oracle, Phase 3.1 mechanical review cannot detect silent scope reduction.
>
> Phase 1.0 also locks AC#4 conditional branch (Branch A: scip-java sees KSP source by default; Branch B-1: workaround in `:core-mini/build.gradle.kts` sourceSets; Branch B-2: AC#4 replaced + spec rev3 + scip-java KSP followup-issue). PE Phase 2 does NOT start until branch locked.

### Task 0a — Vendor preliminary files + trial regen + lock AC#4 branch

Board (operator or designated agent) executes outside the feature branch (e.g., in a scratch worktree):

1. Pin upstream UW SHA: `git ls-remote https://github.com/horizontalsystems/unstoppable-wallet-android.git refs/heads/master | awk '{print $1}'` → record in REGEN.md.
2. Clone UW to scratch dir, identify exact files for vendoring per spec §"Fixture layout" + §"Vendoring strategy":
   - Root: `LICENSE`, `gradle/libs.versions.toml`, `settings.gradle.kts`, `build.gradle.kts` (root), `gradle.properties`
   - `:components:icons` source — vendor `WalletIcons.kt` (or whatever the icons object file is called) verbatim
   - `:components:chartview` source — vendor 1-2 Compose files verbatim (or pruned subset if upstream >300 LOC each)
   - `:core` Room files — vendor entity/DAO/database/repository (or closest approximations) + strip blockchain-SDK imports
   - `:app` — DO NOT vendor verbatim (too dep-heavy); synthesize in PE Phase 2 Task 6
3. Trim `gradle/libs.versions.toml` to remove blockchain-SDK entries (web3j, bitcoin-kit, ethereum-kit, solana-kit, tron-kit, ton-kit etc.) — keep Kotlin/AGP/Compose/Room/Coroutines/AndroidX core.
4. Build a self-contained 4-module fixture in scratch dir following spec §"Fixture layout".
5. Synthesize `:app-mini` Kt files (Activity + ViewModel + Screen + UiState + Application) — full code in Task 6.
6. Run `regen.sh` (Task 7 content). Verify exit 0.
7. **AC#4 KSP-source-visibility check:** `python3 -c "from palace_mcp.extractors.scip_parser import parse_scip_file; idx=parse_scip_file('scip/index.scip'); names=[s.symbol for d in idx.documents for s in d.symbols]; ksp_hit=[n for n in names if 'WalletDao_Impl' in n]; print(f'KSP-generated DAO_Impl present: {bool(ksp_hit)}'); print(ksp_hit[:3] if ksp_hit else 'NONE — Branch B required')"`.
   - If `True` → **Lock Branch A**. AC#4 stands as written. Note in REGEN.md: "AC#4 Branch A locked 2026-04-30 — scip-java sees KSP source out of the box."
   - If `False` → try **Branch B-1**: add `kotlin.sourceSets["main"].kotlin.srcDir(file("build/generated/ksp/debug/kotlin"))` to `:core-mini/build.gradle.kts`; re-run regen; re-check.
     - If now `True` → **Lock Branch B-1**. Note workaround in REGEN.md.
     - If still `False` → **Branch B-2**: AC#4 is replaced. Open spec rev3 + open new GIM-N issue for "scip-java KSP-generated source support". PE Phase 2 still starts; AC#4 is dropped from oracle assertions; cross-module USE in Task 9 drops `dao_impl→dao` pair.
8. **R2 Multi-module aggregation check:** `python3 -c "from palace_mcp.extractors.scip_parser import parse_scip_file; idx=parse_scip_file('scip/index.scip'); print(f'Documents: {len(idx.documents)}'); print(f'Modules covered: {set(d.relative_path.split(\"/\")[0] for d in idx.documents)}')"`.
   - Expected: 4 distinct module roots (`app-mini`, `core-mini`, `components`, etc).
   - If scip-java emits per-module `.scip` instead of one merged → adapt `regen.sh` to aggregator pattern (Solidity precedent in `services/palace-mcp/src/palace_mcp/scip_emit/solidity.py:_make_aggregator`).
9. **Count and fill oracle table** in `services/palace-mcp/tests/extractors/fixtures/uw-android-mini-project/REGEN.md`:

```
| Metric | Value | Notes |
|---|---|---|
| N_MODULES | 4 | :app-mini, :core-mini, :components:icons-mini, :components:chartview-mini |
| N_DOCUMENTS_TOTAL | <count> | len(index.documents) |
| N_DEFS_TOTAL | <count> | source-defined symbols (kind == DEF) |
| N_DECLS_TOTAL | <count> | ForwardDef (kind == DECL); 0 for Android typically |
| N_USES_TOTAL | <count> | use occurrences in function bodies |
| N_OCCURRENCES_TOTAL | <count> | defs + decls + uses |
| N_DEFS_KSP_GENERATED | <count> | conditional on AC#4 Branch — 0 if B-2 |
| AC#4 Branch | A / B-1 / B-2 | locked outcome |
```

10. Commit Phase 1.0 outputs to FB `feature/GIM-127-android-scip-java-validation`:
    - REGEN.md with filled oracle table + AC#4 branch decision
    - All vendored files (so PE doesn't redo vendoring; Phase 2 Tasks 2-6 become "verify present" rather than "create")
    - `regen.sh`
    - `index.scip` binary
    - LICENSE
    - Note: gradle.properties, settings.gradle.kts, etc. all included

**Phase 1.0 deliverable:** PE picks up FB with fixture already vendored + index.scip committed + REGEN.md oracle filled + AC#4 branch locked. PE's Phase 2 Tasks 2-6 collapse to a single "verify Phase 1.0 outputs present" step (Task 1).

---

## Phase 2: PE TDD implementation

### Task 1: Pre-flight verify Phase 1.0 outputs

**Files:**
- Read: `services/palace-mcp/tests/extractors/fixtures/uw-android-mini-project/REGEN.md`
- Read: `services/palace-mcp/tests/extractors/fixtures/uw-android-mini-project/scip/index.scip` (binary present)

- [ ] **Step 1: Confirm Phase 1.0 artefacts exist on FB**

Run:
```bash
cd services/palace-mcp/tests/extractors/fixtures/uw-android-mini-project
test -f REGEN.md && test -f LICENSE && test -f settings.gradle.kts && test -f build.gradle.kts && test -f gradle.properties && test -f gradle/libs.versions.toml && test -f scip/index.scip && test -f regen.sh && echo "OK: Phase 1.0 fixture base present"
```

Expected: `OK: Phase 1.0 fixture base present`. If missing files → **STOP**, escalate to CTO; Phase 1.0 incomplete.

- [ ] **Step 2: Verify oracle table is filled (no `<count>` placeholders)**

Run:
```bash
grep -c "<count>" services/palace-mcp/tests/extractors/fixtures/uw-android-mini-project/REGEN.md
```

Expected: `0`. If non-zero → **STOP**, oracle gate not closed.

- [ ] **Step 3: Verify AC#4 branch locked**

Run:
```bash
grep -E "AC#4 Branch[: ]+(A|B-1|B-2)" services/palace-mcp/tests/extractors/fixtures/uw-android-mini-project/REGEN.md
```

Expected: one match with concrete branch (A, B-1, or B-2). If empty or `<branch>` placeholder → **STOP**.

- [ ] **Step 4: Note locked branch — drives Task 9 oracle assertions**

Capture: `LOCKED_BRANCH=$(grep -oE 'AC#4 Branch[: ]+[AB]-?[12]?' REGEN.md | grep -oE '[AB]-?[12]?')`. Mentally note: if `B-2`, Task 9 drops the KSP-related assertions and `dao_impl→dao` USE pair from Task 9 cross-module checks.

- [ ] **Step 5: No commit — pre-flight only.**

---

### Task 2: Verify all 4 module directories present

> **Note:** This task assumes Phase 1.0 vendored modules. If Phase 1.0 only vendored root config, PE creates module directories here. Adjust based on Phase 1.0 actual scope (REGEN.md should document).

**Files:**
- Verify: `services/palace-mcp/tests/extractors/fixtures/uw-android-mini-project/{app-mini,core-mini,components/icons-mini,components/chartview-mini}/`

- [ ] **Step 1: Confirm 4 module roots**

Run:
```bash
cd services/palace-mcp/tests/extractors/fixtures/uw-android-mini-project
for m in app-mini core-mini components/icons-mini components/chartview-mini; do
  test -d "$m" && echo "OK: $m" || echo "MISSING: $m"
done
```

Expected: 4 `OK:` lines. If `MISSING:` for any → return to Task 6 (synthesize :app-mini) or report Phase 1.0 incomplete.

- [ ] **Step 2: Confirm each module has build.gradle.kts + AndroidManifest.xml**

Run:
```bash
for m in app-mini core-mini components/icons-mini components/chartview-mini; do
  test -f "$m/build.gradle.kts" && test -f "$m/src/main/AndroidManifest.xml" && echo "OK: $m" || echo "MISSING: $m gradle/manifest"
done
```

Expected: 4 `OK:` lines.

- [ ] **Step 3: No commit — verification only.**

---

### Task 3: Verify `:components:icons-mini` module (SYNTHESIZED — rev3)

> **rev3 change:** UW upstream `:components:icons` is XML-resources-only (no Kotlin source). Phase 1.0 synthesizes `WalletIcons.kt` (~30-50 LOC, `object WalletIcons { val Send/Receive/Swap/...: ImageVector }`) in UW style. Module preserved for "Compose-only without DB/KSP" multi-module proof.

**Files:**
- Verify: `services/palace-mcp/tests/extractors/fixtures/uw-android-mini-project/components/icons-mini/src/main/kotlin/.../WalletIcons.kt`

- [ ] **Step 1: Confirm vendored Compose icons file exists**

Run:
```bash
find services/palace-mcp/tests/extractors/fixtures/uw-android-mini-project/components/icons-mini -name "*.kt" -type f
```

Expected: at least one `.kt` file (typically `WalletIcons.kt` or similar).

- [ ] **Step 2: Verify file content has `object` with `ImageVector` constants (verbatim Compose pattern)**

Run:
```bash
KT=$(find services/palace-mcp/tests/extractors/fixtures/uw-android-mini-project/components/icons-mini -name "*.kt" | head -1)
grep -E "^object|ImageVector|Icons\." "$KT" | head -5
```

Expected: matches showing `object WalletIcons` (or similar) + `ImageVector` references.

- [ ] **Step 3: Verify build.gradle.kts has `compose = true` and proper plugin block**

Run:
```bash
grep -E "compose = true|com\.android\.library|kotlin.android" services/palace-mcp/tests/extractors/fixtures/uw-android-mini-project/components/icons-mini/build.gradle.kts
```

Expected: at least 2 matches. If `compose = true` missing → fixture won't compile.

- [ ] **Step 4: No commit — verification only.**

---

### Task 4: Verify `:components:chartview-mini` module (VENDORED VERBATIM from UW)

> **rev3 emphasis:** This is the **only** module truly vendored from UW (`components/chartview/src/main/java/io/horizontalsystems/chartview/`). Phase 1.0 picks 2-4 source files (e.g., `ChartView.kt`, `ChartData.kt`) + minimum dependencies. UW upstream uses `viewBinding = true` + `compose.runtime` (mixed View+Compose); our vendor preserves this — proves scip-java handles non-pure-Compose Kotlin too.

**Files:**
- Verify: `services/palace-mcp/tests/extractors/fixtures/uw-android-mini-project/components/chartview-mini/src/main/kotlin/.../*.kt`

- [ ] **Step 1: Confirm 1-2 vendored Compose chart files**

Run:
```bash
find services/palace-mcp/tests/extractors/fixtures/uw-android-mini-project/components/chartview-mini -name "*.kt" -type f
```

Expected: 1-2 `.kt` files (`ChartView.kt`, optionally `ChartData.kt`).

- [ ] **Step 2: Verify uses `Canvas` / `drawBehind` / `Path` (advanced Compose APIs)**

Run:
```bash
KT=$(find services/palace-mcp/tests/extractors/fixtures/uw-android-mini-project/components/chartview-mini -name "ChartView.kt")
grep -cE "Canvas|drawBehind|Path|Modifier" "$KT"
```

Expected: ≥3 matches. (If 0 → wrong file vendored.)

- [ ] **Step 3: Verify @Composable annotation present**

Run:
```bash
grep -c "@Composable" services/palace-mcp/tests/extractors/fixtures/uw-android-mini-project/components/chartview-mini/src/main/kotlin/*/ChartView.kt 2>/dev/null || \
  find services/palace-mcp/tests/extractors/fixtures/uw-android-mini-project/components/chartview-mini -name "ChartView.kt" -exec grep -c "@Composable" {} \;
```

Expected: ≥1.

- [ ] **Step 4: No commit — verification only.**

---

### Task 5: Verify `:core-mini` module (SYNTHESIZED Room — rev3)

> **rev3 change:** UW Room (`@Entity`/`@Dao`/`@Database`) lives in `:app/src/main/java/io/horizontalsystems/bankwallet/core/storage/` (20+ DAOs + `AppDatabase.kt`), NOT in `:core`. UW `:core` is generic utilities (Extensions, helpers). Phase 1.0 synthesizes `:core-mini/db/*` (`WalletEntity.kt`, `WalletDao.kt`, `AppDatabase.kt`) following UW patterns (snake-case tables, suspend + Flow, mixed `@Insert`/`@Update`/`@Delete`/`@Query`). Module placed in `:core-mini` (not `:app-mini`) to preserve multi-module proof + KSP-via-Room exercise.

**Files:**
- Verify: `services/palace-mcp/tests/extractors/fixtures/uw-android-mini-project/core-mini/src/main/kotlin/.../db/{WalletEntity,WalletDao,AppDatabase}.kt`
- Verify: `services/palace-mcp/tests/extractors/fixtures/uw-android-mini-project/core-mini/src/main/kotlin/.../repository/WalletRepository.kt`
- Verify: `services/palace-mcp/tests/extractors/fixtures/uw-android-mini-project/core-mini/build.gradle.kts` (KSP plugin + room.compiler ksp dep)

- [ ] **Step 1: Confirm Room DSL files present**

Run:
```bash
find services/palace-mcp/tests/extractors/fixtures/uw-android-mini-project/core-mini -name "*.kt" -type f | sort
```

Expected: at minimum `WalletEntity.kt`, `WalletDao.kt`, `AppDatabase.kt`, `WalletRepository.kt` (4+ files).

- [ ] **Step 2: Verify Room annotations present**

Run:
```bash
grep -lE "@Entity|@Dao|@Database" services/palace-mcp/tests/extractors/fixtures/uw-android-mini-project/core-mini/src/main/kotlin/**/*.kt 2>/dev/null
```

Expected: 3 distinct files (entity, dao, database).

- [ ] **Step 3: Verify build.gradle.kts wires KSP + Room compiler**

Run:
```bash
grep -E "ksp|room.compiler|com.google.devtools.ksp" services/palace-mcp/tests/extractors/fixtures/uw-android-mini-project/core-mini/build.gradle.kts
```

Expected: ≥2 matches (plugin + dependency).

- [ ] **Step 4: AC#4 Branch B-1 specific — verify sourceSets workaround if branch locked B-1**

If REGEN.md says `AC#4 Branch B-1`:
```bash
grep -E "kotlin.srcDir.*generated/ksp" services/palace-mcp/tests/extractors/fixtures/uw-android-mini-project/core-mini/build.gradle.kts
```
Expected: 1 match. If 0 → workaround missing despite branch lock; **STOP** and report.

If REGEN.md says Branch A or B-2 → skip this step.

- [ ] **Step 5: No commit — verification only.**

---

### Task 6: Synthesize `:app-mini` module (if Phase 1.0 left placeholder)

> **Conditional:** if Phase 1.0 already synthesized `:app-mini`, this task collapses to verification (run grep checks like Tasks 3-5). The full code below applies if Phase 1.0 left it as PE responsibility (per spec §Vendoring strategy: ":app-mini synthesized in UW style").

**Files:**
- Create: `services/palace-mcp/tests/extractors/fixtures/uw-android-mini-project/app-mini/build.gradle.kts`
- Create: `services/palace-mcp/tests/extractors/fixtures/uw-android-mini-project/app-mini/src/main/AndroidManifest.xml`
- Create: `services/palace-mcp/tests/extractors/fixtures/uw-android-mini-project/app-mini/src/main/kotlin/io/horizontalsystems/uwmini/app/MyApp.kt`
- Create: `services/palace-mcp/tests/extractors/fixtures/uw-android-mini-project/app-mini/src/main/kotlin/io/horizontalsystems/uwmini/app/MainActivity.kt`
- Create: `services/palace-mcp/tests/extractors/fixtures/uw-android-mini-project/app-mini/src/main/kotlin/io/horizontalsystems/uwmini/app/MainScreen.kt`
- Create: `services/palace-mcp/tests/extractors/fixtures/uw-android-mini-project/app-mini/src/main/kotlin/io/horizontalsystems/uwmini/app/MainViewModel.kt`
- Create: `services/palace-mcp/tests/extractors/fixtures/uw-android-mini-project/app-mini/src/main/kotlin/io/horizontalsystems/uwmini/app/UiState.kt`

- [ ] **Step 1: app-mini/build.gradle.kts**

```kotlin
plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.compose)
}

android {
    namespace = "io.horizontalsystems.uwmini.app"
    compileSdk = libs.versions.compileSdk.get().toInt()

    defaultConfig {
        applicationId = "io.horizontalsystems.uwmini"
        minSdk = libs.versions.minSdk.get().toInt()
        targetSdk = libs.versions.compileSdk.get().toInt()
        versionCode = 1
        versionName = "0.1"
    }

    buildFeatures { compose = true }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}

dependencies {
    implementation(project(":core-mini"))
    implementation(project(":components:icons-mini"))
    implementation(project(":components:chartview-mini"))
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.compose.material3)
    implementation(libs.androidx.compose.ui)
    implementation(libs.androidx.lifecycle.viewmodel.compose)
    implementation(libs.kotlinx.coroutines.android)
}
```

- [ ] **Step 2: app-mini/src/main/AndroidManifest.xml**

```xml
<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android">
    <application
        android:name=".MyApp"
        android:label="UW Mini">
        <activity
            android:name=".MainActivity"
            android:exported="true">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LAUNCHER" />
            </intent-filter>
        </activity>
    </application>
</manifest>
```

- [ ] **Step 3: MyApp.kt**

```kotlin
package io.horizontalsystems.uwmini.app

import android.app.Application
import io.horizontalsystems.uwmini.core.db.AppDatabase
import io.horizontalsystems.uwmini.core.repository.WalletRepository

class MyApp : Application() {
    lateinit var walletRepository: WalletRepository
        private set

    override fun onCreate() {
        super.onCreate()
        val db = AppDatabase.create(this)
        walletRepository = WalletRepository(db.walletDao())
    }
}
```

- [ ] **Step 4: MainActivity.kt**

```kotlin
package io.horizontalsystems.uwmini.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.viewModels
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface

class MainActivity : ComponentActivity() {
    private val viewModel: MainViewModel by viewModels {
        MainViewModel.Factory((application as MyApp).walletRepository)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme {
                Surface {
                    MainScreen(viewModel = viewModel)
                }
            }
        }
    }
}
```

- [ ] **Step 5: MainScreen.kt**

```kotlin
package io.horizontalsystems.uwmini.app

import androidx.compose.foundation.layout.Column
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import io.horizontalsystems.uwmini.chart.ChartView
import io.horizontalsystems.uwmini.icons.WalletIcons

@Composable
fun MainScreen(viewModel: MainViewModel, modifier: Modifier = Modifier) {
    val state by viewModel.uiState.collectAsState()
    Column(modifier = modifier) {
        when (val s = state) {
            is UiState.Loading -> Text("Loading wallets...")
            is UiState.Success -> {
                Text("Wallets: ${s.wallets.size}")
                ChartView(values = s.wallets.map { it.balance.toFloat() })
            }
            is UiState.Error -> Text("Error: ${s.message}")
        }
    }
}
```

- [ ] **Step 6: MainViewModel.kt**

```kotlin
package io.horizontalsystems.uwmini.app

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import io.horizontalsystems.uwmini.core.repository.WalletRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

class MainViewModel(private val repository: WalletRepository) : ViewModel() {
    private val _uiState = MutableStateFlow<UiState>(UiState.Loading)
    val uiState: StateFlow<UiState> = _uiState.asStateFlow()

    init {
        viewModelScope.launch {
            repository.allWallets().collect { wallets ->
                _uiState.value = UiState.Success(wallets)
            }
        }
    }

    class Factory(private val repository: WalletRepository) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T =
            MainViewModel(repository) as T
    }
}
```

- [ ] **Step 7: UiState.kt**

```kotlin
package io.horizontalsystems.uwmini.app

import io.horizontalsystems.uwmini.core.model.Wallet

sealed interface UiState {
    object Loading : UiState
    data class Success(val wallets: List<Wallet>) : UiState
    data class Error(val message: String) : UiState
}
```

- [ ] **Step 8: Verify all 5 .kt + manifest + gradle present**

Run:
```bash
ls services/palace-mcp/tests/extractors/fixtures/uw-android-mini-project/app-mini/src/main/kotlin/io/horizontalsystems/uwmini/app/*.kt | wc -l
```

Expected: `5`.

- [ ] **Step 9: Commit `:app-mini` synthesis**

```bash
git add services/palace-mcp/tests/extractors/fixtures/uw-android-mini-project/app-mini/
git commit -m "feat(GIM-127): synthesize :app-mini module (Activity + Compose + ViewModel + StateFlow + sealed UiState)"
```

---

### Task 7: Run regen.sh end-to-end + commit `index.scip`

> **Conditional:** if Phase 1.0 already committed `index.scip`, this task is verification-only. Re-run regen if `:app-mini` synthesis (Task 6) changed source set.

**Files:**
- Modify (regenerate): `services/palace-mcp/tests/extractors/fixtures/uw-android-mini-project/scip/index.scip`

- [ ] **Step 1: Verify regen.sh contents**

Run:
```bash
cat services/palace-mcp/tests/extractors/fixtures/uw-android-mini-project/regen.sh
```

Expected: shell script that runs `gradle compileDebugKotlin` (across modules) + `npx @sourcegraph/scip-java index --output ./scip/index.scip` (or equivalent).

- [ ] **Step 2: Run regen end-to-end**

Run:
```bash
cd services/palace-mcp/tests/extractors/fixtures/uw-android-mini-project
bash regen.sh 2>&1 | tail -20
```

Expected: gradle build success + scip-java success messages, exit 0.

- [ ] **Step 3: Verify `index.scip` is non-trivial**

Run:
```bash
test -s scip/index.scip && wc -c scip/index.scip
```

Expected: non-empty file, typically 80-300 KB.

- [ ] **Step 4: Re-verify oracle counts unchanged from Phase 1.0**

Run:
```bash
python3 -c "
from palace_mcp.extractors.scip_parser import parse_scip_file, iter_scip_occurrences
idx = parse_scip_file('services/palace-mcp/tests/extractors/fixtures/uw-android-mini-project/scip/index.scip')
occs = list(iter_scip_occurrences(idx, commit_sha='regen-check'))
defs = [o for o in occs if o.kind.name == 'DEF']
uses = [o for o in occs if o.kind.name == 'USE']
print(f'Documents: {len(idx.documents)}, DEFs: {len(defs)}, USEs: {len(uses)}, Total: {len(occs)}')
"
```

Expected: counts within ±5% of REGEN.md oracle values (small drift OK, large drift → investigate before commit).

- [ ] **Step 5: Commit regenerated index.scip if drifted**

```bash
git add services/palace-mcp/tests/extractors/fixtures/uw-android-mini-project/scip/index.scip
git diff --cached --stat services/palace-mcp/tests/extractors/fixtures/uw-android-mini-project/scip/index.scip
```

If diff non-empty:
```bash
git commit -m "chore(GIM-127): regen index.scip after :app-mini synthesis"
```

If diff empty (Phase 1.0 already final): no commit, move on.

---

### Task 8: Add `requires_scip_uw_android` marker to pyproject.toml

**Files:**
- Modify: `services/palace-mcp/pyproject.toml` (line ~50, in `[tool.pytest.ini_options].markers` block)

- [ ] **Step 1: Verify current markers list**

Run:
```bash
grep -A 10 "^markers = \[" services/palace-mcp/pyproject.toml
```

Expected: list with `integration`, `slow`, `wire`, `requires_scip_typescript/python/java/solidity`, `requires_slither`. Note: `requires_scip_uw_android` is NOT present.

- [ ] **Step 2: Add new marker**

Edit `services/palace-mcp/pyproject.toml`. After the line:
```
    "requires_scip_solidity: tests requiring oz-v5-mini/index.scip fixture",
```
Insert new line:
```
    "requires_scip_uw_android: tests requiring uw-android-mini-project/index.scip fixture (real Android: Compose + Room/KSP + multi-module)",
```

- [ ] **Step 3: Verify marker is registered**

Run:
```bash
cd services/palace-mcp && uv run pytest --markers 2>&1 | grep "requires_scip_uw_android"
```

Expected: line `@pytest.mark.requires_scip_uw_android: tests requiring uw-android-mini-project/index.scip fixture (real Android: Compose + Room/KSP + multi-module)`.

- [ ] **Step 4: Commit**

```bash
git add services/palace-mcp/pyproject.toml
git commit -m "test(GIM-127): register requires_scip_uw_android pytest marker"
```

---

### Task 9: `TestUwAndroidMiniProjectFixture` — unit-level oracle assertions

> **TDD:** Write all 17 assertions (rev2 — 13 + 4 cross-module USE pairs from CR CRITICAL #1 fix) referencing oracle values from REGEN.md FIRST. Run — assertions checking concrete numbers will pass (index already committed); structural assertions will fail if module names mismatch — adjust as needed. Then commit.

**Files:**
- Modify: `services/palace-mcp/tests/extractors/unit/test_real_scip_fixtures.py` (append new test class at end of file)

- [ ] **Step 1: Read existing test file structure**

Run:
```bash
grep -nE "^class Test|^@requires_scip" services/palace-mcp/tests/extractors/unit/test_real_scip_fixtures.py
```

Expected: existing classes for TS/Python/JVM/Sol fixtures, each prefixed with `@requires_scip_*` marker.

- [ ] **Step 2: Add fixture path constant + marker at top of file**

Find the FIXTURE path constants near the top (around line 20-30). After `SOL_SCIP = FIXTURES / "oz-v5-mini-project" / "index.scip"`:
```python
UW_ANDROID_SCIP = FIXTURES / "uw-android-mini-project" / "scip" / "index.scip"
```

After `requires_scip_solidity = pytest.mark.skipif(...)`:
```python
requires_scip_uw_android = pytest.mark.skipif(
    not UW_ANDROID_SCIP.exists(), reason="uw-android-mini-project/scip/index.scip not present"
)
```

- [ ] **Step 3: Add oracle constants near the existing `_SOL_N_*` block**

After the `_SOL_N_*` block:
```python
# uw-android-mini oracle (locked Phase 1.0 — REGEN.md authoritative)
_UW_N_OCCURRENCES_TOTAL = <FROM_REGEN_MD>  # fill from REGEN.md
_UW_N_DEFS = <FROM_REGEN_MD>
_UW_N_USES = <FROM_REGEN_MD>
_UW_N_DOCUMENTS = <FROM_REGEN_MD>
_UW_AC4_BRANCH = "<A | B-1 | B-2>"  # from REGEN.md
```

> **Replace `<FROM_REGEN_MD>` with the locked numbers from `REGEN.md` oracle table.** No `<>` placeholders may remain.

- [ ] **Step 4: Add `TestUwAndroidMiniProjectFixture` class at end of file**

```python
@requires_scip_uw_android
class TestUwAndroidMiniProjectFixture:
    """Oracle assertions for uw-android-mini-project fixture.

    Locked Phase 1.0 oracle in services/palace-mcp/tests/extractors/fixtures/uw-android-mini-project/REGEN.md.
    AC#4 (KSP-generated WalletDao_Impl) conditional — see _UW_AC4_BRANCH.
    """

    def test_parses_without_error(self) -> None:
        index = parse_scip_file(UW_ANDROID_SCIP)
        assert index is not None

    def test_yields_kotlin_occurrences(self) -> None:
        index = parse_scip_file(UW_ANDROID_SCIP)
        occs = list(iter_scip_occurrences(index, commit_sha="test"))
        kt_occs = [o for o in occs if o.language == Language.KOTLIN]
        assert len(kt_occs) > 0, "Expected at least one Kotlin occurrence"

    def test_occurrence_total_matches_oracle(self) -> None:
        index = parse_scip_file(UW_ANDROID_SCIP)
        occs = list(iter_scip_occurrences(index, commit_sha="test"))
        # Allow ±2% drift since regen may produce slightly different USE counts across scip-java versions
        lo, hi = int(_UW_N_OCCURRENCES_TOTAL * 0.98), int(_UW_N_OCCURRENCES_TOTAL * 1.02)
        assert lo <= len(occs) <= hi, f"Oracle: {_UW_N_OCCURRENCES_TOTAL}±2%, got {len(occs)}"

    def test_def_count_matches_oracle(self) -> None:
        index = parse_scip_file(UW_ANDROID_SCIP)
        occs = list(iter_scip_occurrences(index, commit_sha="test"))
        defs = [o for o in occs if o.kind == SymbolKind.DEF]
        lo, hi = int(_UW_N_DEFS * 0.98), int(_UW_N_DEFS * 1.02)
        assert lo <= len(defs) <= hi, f"Oracle: {_UW_N_DEFS}±2% DEF, got {len(defs)}"

    def test_documents_count_matches_oracle(self) -> None:
        index = parse_scip_file(UW_ANDROID_SCIP)
        assert len(index.documents) == _UW_N_DOCUMENTS, (
            f"Oracle: {_UW_N_DOCUMENTS} docs, got {len(index.documents)}"
        )

    def test_main_activity_def_present(self) -> None:
        index = parse_scip_file(UW_ANDROID_SCIP)
        occs = list(iter_scip_occurrences(index, commit_sha="test"))
        names = {o.symbol_qualified_name for o in occs if o.kind == SymbolKind.DEF}
        assert any("MainActivity" in n for n in names), \
            f"Expected MainActivity DEF, sample: {sorted(names)[:5]}"

    def test_main_screen_composable_present(self) -> None:
        # @Composable MainScreen() in app-mini/MainScreen.kt
        # AC#6: language detected KOTLIN (CR WARNING #2 fix — explicit per-DEF check)
        index = parse_scip_file(UW_ANDROID_SCIP)
        occs = list(iter_scip_occurrences(index, commit_sha="test"))
        main_screen_defs = [
            o for o in occs
            if o.kind == SymbolKind.DEF and "MainScreen" in o.symbol_qualified_name
        ]
        assert main_screen_defs, (
            "Expected MainScreen Composable DEF, sample DEFs: "
            f"{sorted({o.symbol_qualified_name for o in occs if o.kind == SymbolKind.DEF})[:5]}"
        )
        for occ in main_screen_defs:
            assert occ.language == Language.KOTLIN, (
                f"AC#6: MainScreen DEF must be KOTLIN, got {occ.language}: {occ.symbol_qualified_name}"
            )

    def test_chart_view_composable_present(self) -> None:
        # @Composable ChartView() in :components:chartview-mini
        # AC#6: language detected KOTLIN (CR WARNING #2 fix)
        index = parse_scip_file(UW_ANDROID_SCIP)
        occs = list(iter_scip_occurrences(index, commit_sha="test"))
        chart_view_defs = [
            o for o in occs
            if o.kind == SymbolKind.DEF and "ChartView" in o.symbol_qualified_name
        ]
        assert chart_view_defs, "Expected ChartView Composable DEF in :components:chartview-mini"
        for occ in chart_view_defs:
            assert occ.language == Language.KOTLIN, (
                f"AC#6: ChartView DEF must be KOTLIN, got {occ.language}: {occ.symbol_qualified_name}"
            )

    def test_wallet_entity_def_present(self) -> None:
        index = parse_scip_file(UW_ANDROID_SCIP)
        occs = list(iter_scip_occurrences(index, commit_sha="test"))
        names = {o.symbol_qualified_name for o in occs if o.kind == SymbolKind.DEF}
        assert any("WalletEntity" in n for n in names), "Expected Room @Entity"

    def test_wallet_dao_def_present(self) -> None:
        index = parse_scip_file(UW_ANDROID_SCIP)
        occs = list(iter_scip_occurrences(index, commit_sha="test"))
        names = {o.symbol_qualified_name for o in occs if o.kind == SymbolKind.DEF}
        assert any("WalletDao" in n for n in names), "Expected Room @Dao interface"

    def test_wallet_dao_impl_ksp_generated(self) -> None:
        # AC#4 conditional gate. Branch A/B-1: must pass. Branch B-2: skipped.
        if _UW_AC4_BRANCH == "B-2":
            pytest.skip("AC#4 Branch B-2 — KSP source not visible to scip-java; followup tracked")
        index = parse_scip_file(UW_ANDROID_SCIP)
        occs = list(iter_scip_occurrences(index, commit_sha="test"))
        names = {o.symbol_qualified_name for o in occs if o.kind == SymbolKind.DEF}
        assert any("WalletDao_Impl" in n for n in names), (
            f"AC#4 Branch {_UW_AC4_BRANCH}: expected KSP-generated WalletDao_Impl as DEF"
        )

    # ─── AC#5 Cross-module USE pairs (5 total per spec) ─────────────────
    # CR CRITICAL #1 fix (rev2): plan rev1 had only 1 of 5 USE-pair tests.
    # All 5 below; dao_impl→dao conditional on AC#4 Branch A/B-1.

    def test_cross_module_use_repo_in_viewmodel(self) -> None:
        # AC#5 pair 1/5: app→repo
        # MainViewModel (in :app-mini) USEs WalletRepository (in :core-mini)
        index = parse_scip_file(UW_ANDROID_SCIP)
        occs = list(iter_scip_occurrences(index, commit_sha="test"))
        viewmodel_uses_repo = any(
            "WalletRepository" in o.symbol_qualified_name
            and o.kind == SymbolKind.USE
            and "MainViewModel" in (o.file_path or "")
            for o in occs
        )
        assert viewmodel_uses_repo, (
            "AC#5 pair 1/5 — Expected :app-mini → :core-mini cross-module USE "
            "(MainViewModel uses WalletRepository)"
        )

    def test_cross_module_use_icons_in_main_screen(self) -> None:
        # AC#5 pair 2/5: app→icons
        # MainScreen (in :app-mini) USEs WalletIcons (in :components:icons-mini)
        index = parse_scip_file(UW_ANDROID_SCIP)
        occs = list(iter_scip_occurrences(index, commit_sha="test"))
        main_screen_uses_icons = any(
            "WalletIcons" in o.symbol_qualified_name
            and o.kind == SymbolKind.USE
            and "MainScreen" in (o.file_path or "")
            for o in occs
        )
        assert main_screen_uses_icons, (
            "AC#5 pair 2/5 — Expected :app-mini → :components:icons-mini "
            "cross-module USE (MainScreen uses WalletIcons)"
        )

    def test_cross_module_use_chart_in_main_screen(self) -> None:
        # AC#5 pair 3/5: app→chart
        # MainScreen (in :app-mini) USEs ChartView (in :components:chartview-mini)
        index = parse_scip_file(UW_ANDROID_SCIP)
        occs = list(iter_scip_occurrences(index, commit_sha="test"))
        main_screen_uses_chart = any(
            "ChartView" in o.symbol_qualified_name
            and o.kind == SymbolKind.USE
            and "MainScreen" in (o.file_path or "")
            for o in occs
        )
        assert main_screen_uses_chart, (
            "AC#5 pair 3/5 — Expected :app-mini → :components:chartview-mini "
            "cross-module USE (MainScreen uses ChartView)"
        )

    def test_cross_module_use_dao_in_repository(self) -> None:
        # AC#5 pair 4/5: repo→dao
        # WalletRepository (in :core-mini/repository) USEs WalletDao (in :core-mini/db).
        # Note: intra-:core-mini cross-package; spec lists it as AC#5 because Slice 1
        # primarily proves cross-MODULE resolution but this pair anchors the
        # KSP follow-on chain (pair 5/5 dao_impl→dao). Excludes WalletDao_Impl
        # to avoid self-match.
        index = parse_scip_file(UW_ANDROID_SCIP)
        occs = list(iter_scip_occurrences(index, commit_sha="test"))
        repo_uses_dao = any(
            "WalletDao" in o.symbol_qualified_name
            and "WalletDao_Impl" not in o.symbol_qualified_name
            and o.kind == SymbolKind.USE
            and "WalletRepository" in (o.file_path or "")
            for o in occs
        )
        assert repo_uses_dao, (
            "AC#5 pair 4/5 — Expected WalletRepository USEs WalletDao "
            "(intra-:core-mini cross-package)"
        )

    def test_cross_module_use_dao_impl_to_dao(self) -> None:
        # AC#5 pair 5/5: dao_impl→dao (CONDITIONAL on AC#4 Branch A/B-1)
        # KSP-generated WalletDao_Impl extends/USEs WalletDao base interface.
        # If Phase 1.0 locked Branch B-2, this pair is untestable — skip.
        if _UW_AC4_BRANCH == "B-2":
            pytest.skip(
                "AC#4 Branch B-2 — KSP-generated source not visible to scip-java; "
                "AC#5 pair 5/5 (dao_impl→dao) untestable until KSP support followup"
            )
        index = parse_scip_file(UW_ANDROID_SCIP)
        occs = list(iter_scip_occurrences(index, commit_sha="test"))
        impl_uses_dao = any(
            "WalletDao" in o.symbol_qualified_name
            and "WalletDao_Impl" not in o.symbol_qualified_name
            and o.kind == SymbolKind.USE
            and "WalletDao_Impl" in (o.file_path or "")
            for o in occs
        )
        assert impl_uses_dao, (
            f"AC#5 pair 5/5 — Branch {_UW_AC4_BRANCH}: expected KSP-generated "
            "WalletDao_Impl USEs WalletDao base interface"
        )

    # ─── End AC#5 cross-module USE pairs ────────────────────────────────

    def test_qualified_names_have_no_scheme_prefix(self) -> None:
        index = parse_scip_file(UW_ANDROID_SCIP)
        occs = list(iter_scip_occurrences(index, commit_sha="test"))
        for occ in occs:
            qn = occ.symbol_qualified_name
            assert not qn.startswith("semanticdb"), f"qualified_name leaks scheme prefix: {qn!r}"
            assert not qn.startswith("scip-java"), f"qualified_name leaks scheme prefix: {qn!r}"
```

- [ ] **Step 5: Run new test class**

```bash
cd services/palace-mcp && uv run pytest tests/extractors/unit/test_real_scip_fixtures.py::TestUwAndroidMiniProjectFixture -v
```

Expected:
- Branch A: **17 passed** (rev2 added 4 USE-pair tests per CR CRITICAL #1 fix)
- Branch B-1: 17 passed (KSP visible after `sourceSets` workaround)
- Branch B-2: **15 passed, 2 skipped** (`test_wallet_dao_impl_ksp_generated` + `test_cross_module_use_dao_impl_to_dao`)

- [ ] **Step 6: If failures — diagnose**

Common failures:
- `test_documents_count_matches_oracle` — expected exact count; if drift → adjust oracle in REGEN.md AND `_UW_N_DOCUMENTS`.
- `test_main_screen_composable_present` — if `MainScreen` not in defs, scip-java may not have indexed `:app-mini`; check Task 6 Step 8 + Task 7 regen output.
- `test_wallet_dao_impl_ksp_generated` (Branch A) — if fails, Phase 1.0 branch lock was wrong; regen + escalate.

- [ ] **Step 7: Commit**

```bash
git add services/palace-mcp/tests/extractors/unit/test_real_scip_fixtures.py
git commit -m "test(GIM-127): TestUwAndroidMiniProjectFixture — oracle assertions for Android fixture (Compose + Room + multi-module + KSP cond on AC#4 branch)"
```

---

### Task 10: Integration test — `test_symbol_index_java_uw_integration.py` (NEW PATTERN)

> **NEW PATTERN:** distinct from existing `test_symbol_index_java_integration.py` which uses `build_jvm_scip_index()` synthetic factory + MagicMock settings. This new test reads committed fixture `.scip` from disk + uses real Neo4j (testcontainers / compose-reuse) + asserts Tantivy doc count against oracle. Sets precedent for future fixture-based integration tests across all languages.

**Files:**
- Create: `services/palace-mcp/tests/extractors/integration/test_symbol_index_java_uw_integration.py`
- Reference: `services/palace-mcp/tests/extractors/integration/test_symbol_index_java_integration.py` (existing pattern for conftest+driver fixture, NOT to be copied)

- [ ] **Step 1: Read existing integration test for fixtures conventions**

Run:
```bash
head -80 services/palace-mcp/tests/extractors/integration/test_symbol_index_java_integration.py
```

Note: how `driver` fixture is provided (testcontainers Neo4j or compose-reuse), how `tmp_path` is used for Tantivy, how `MagicMock()` builds settings.

- [ ] **Step 2: Write the new integration test**

```python
"""Integration test: SymbolIndexJava on real fixture .scip + real Neo4j.

NEW PATTERN (GIM-127 Slice 1): unlike test_symbol_index_java_integration.py
which uses synthetic build_jvm_scip_index() factory, this test reads the
committed uw-android-mini-project/scip/index.scip fixture from disk and
runs the full extractor pipeline against real Neo4j (compose-reuse).

Asserts:
- IngestRun success record in Neo4j
- phase1 + phase2 checkpoints (defs+decls and user_uses) present
- Tantivy document count matches oracle (within ±2% drift tolerance)
- Cross-module symbol resolution works (sample query)

Skipped via requires_scip_uw_android marker if fixture .scip missing.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from palace_mcp.extractors.base import ExtractorRunContext
from palace_mcp.extractors.symbol_index_java import SymbolIndexJava

FIXTURE_SCIP = (
    Path(__file__).parent.parent / "fixtures" / "uw-android-mini-project" / "scip" / "index.scip"
)

requires_scip_uw_android = pytest.mark.skipif(
    not FIXTURE_SCIP.exists(),
    reason="uw-android-mini-project/scip/index.scip not present",
)


@pytest.mark.integration
@requires_scip_uw_android
class TestSymbolIndexJavaUwIntegration:
    @pytest.mark.asyncio
    async def test_full_ingest_cycle_real_fixture(
        self, driver: object, tmp_path: Path
    ) -> None:
        """Ingest committed UW-android fixture, verify Neo4j + Tantivy state."""
        # Arrange: settings pointing to real fixture .scip + tmp Tantivy dir
        settings = MagicMock()
        settings.palace_scip_index_paths = {"uw-android-mini": str(FIXTURE_SCIP)}
        tantivy_dir = tmp_path / "tantivy"
        tantivy_dir.mkdir()
        settings.palace_tantivy_index_path = str(tantivy_dir)
        settings.palace_tantivy_heap_mb = 100
        settings.palace_max_occurrences_total = 50_000_000
        settings.palace_max_occurrences_per_project = 10_000_000
        settings.palace_importance_threshold_use = 0.0
        settings.palace_max_occurrences_per_symbol = 5_000
        settings.palace_recency_decay_days = 30.0

        ctx = ExtractorRunContext(
            project_slug="uw-android-mini",
            group_id="project/uw-android-mini",
            repo_path=tmp_path,
            run_id="uw-android-integration-001",
            duration_ms=0,
            logger=MagicMock(),
        )

        extractor = SymbolIndexJava()
        graphiti = MagicMock()

        # Act: run the extractor
        with (
            patch("palace_mcp.mcp_server.get_driver", return_value=driver),
            patch("palace_mcp.mcp_server.get_settings", return_value=settings),
        ):
            stats = await extractor.run(graphiti=graphiti, ctx=ctx)

        # Assert 1: stats reasonable (oracle-driven, allow drift)
        assert stats.nodes_written > 0, "extractor wrote zero occurrences"

        # Assert 2: IngestRun in Neo4j
        async with driver.session() as session:  # type: ignore[union-attr]
            result = await session.run(
                "MATCH (r:IngestRun {run_id: $rid}) RETURN r.success AS success",
                rid="uw-android-integration-001",
            )
            record = await result.single()
            assert record is not None, "IngestRun node not found in Neo4j"
            assert record["success"] is True, "IngestRun marked failure"

        # Assert 3: Phase 1 checkpoint persisted
        async with driver.session() as session:  # type: ignore[union-attr]
            result = await session.run(
                """
                MATCH (c:IngestCheckpoint {run_id: $rid, phase: 'phase1_defs'})
                RETURN c.expected_doc_count AS count
                """,
                rid="uw-android-integration-001",
            )
            record = await result.single()
            assert record is not None, "phase1_defs checkpoint missing"
            phase1_count = record["count"]
            assert phase1_count > 0, "phase1_defs wrote zero documents"

        # Assert 4: Tantivy doc count matches oracle (CR WARNING #1 fix — rev2)
        # Verified API: TantivyBridge.count_docs_for_run_async(run_id, phase)
        # exists at tantivy_bridge.py:112; sum phase1+phase2+phase3 for total.
        # Oracle from REGEN.md: _UW_N_OCCURRENCES_TOTAL ±2% drift tolerance.
        from tests.extractors.unit.test_real_scip_fixtures import (
            _UW_N_OCCURRENCES_TOTAL,
        )
        from palace_mcp.extractors.foundation.tantivy_bridge import TantivyBridge

        async with TantivyBridge(
            tantivy_dir, heap_size_mb=settings.palace_tantivy_heap_mb
        ) as bridge:
            phase1_docs = await bridge.count_docs_for_run_async(
                "uw-android-integration-001", "phase1_defs"
            )
            phase2_docs = await bridge.count_docs_for_run_async(
                "uw-android-integration-001", "phase2_user_uses"
            )
            phase3_docs = await bridge.count_docs_for_run_async(
                "uw-android-integration-001", "phase3_vendor_uses"
            )
        tantivy_doc_count = phase1_docs + phase2_docs + phase3_docs

        lo = int(_UW_N_OCCURRENCES_TOTAL * 0.98)
        hi = int(_UW_N_OCCURRENCES_TOTAL * 1.02)
        assert lo <= tantivy_doc_count <= hi, (
            f"Tantivy doc count {tantivy_doc_count} (p1={phase1_docs}, "
            f"p2={phase2_docs}, p3={phase3_docs}) outside oracle "
            f"{_UW_N_OCCURRENCES_TOTAL}±2% (range [{lo}, {hi}])"
        )
```

- [ ] **Step 3: Run the new integration test (requires Neo4j)**

```bash
cd services/palace-mcp
docker compose --profile review up -d neo4j
sleep 5
COMPOSE_NEO4J_URI=bolt://localhost:7687 NEO4J_PASSWORD=$(grep NEO4J_PASSWORD ../../.env | cut -d= -f2) \
  uv run pytest tests/extractors/integration/test_symbol_index_java_uw_integration.py -v -m integration
```

Expected: `1 passed` (or `1 skipped` if fixture missing).

- [ ] **Step 4: If failure — diagnose**

Common failures:
- Neo4j not reachable → check `docker compose --profile review ps`
- Tantivy `palace_tantivy_index_path` permission → ensure `tmp_path` writable
- Extractor returns 0 nodes → fixture `.scip` corrupt; re-run Task 7

- [ ] **Step 5: Commit**

```bash
git add services/palace-mcp/tests/extractors/integration/test_symbol_index_java_uw_integration.py
git commit -m "test(GIM-127): NEW integration-test pattern — real fixture .scip + real Neo4j (vs existing synthetic factory)"
```

---

### Task 11: Update `docker-compose.yml` — add `uw-android` bind-mount + Mac-specific comment

**Files:**
- Modify: `docker-compose.yml` lines ~52-54 (palace-mcp.volumes block)

- [ ] **Step 1: Verify current state**

Run:
```bash
grep -A 12 "^    volumes:" docker-compose.yml | head -15
```

Expected: existing lines including `/Users/Shared/Ios/Gimle-Palace:/repos/gimle:ro` and oz-v5-mini relative mount.

- [ ] **Step 2: Add uw-android bind-mount after gimle line**

Edit `docker-compose.yml`. Replace:
```yaml
    volumes:
      - /Users/Shared/Ios/Gimle-Palace:/repos/gimle:ro
      - ./services/palace-mcp/tests/extractors/fixtures/oz-v5-mini-project:/repos/oz-v5-mini:ro
```
With:
```yaml
    volumes:
      # NOTE: real-project bind-mounts use absolute Mac paths (operator-iMac convention).
      # Non-iMac contributors should override these in docker-compose.override.yml.
      # Fixture-based mounts (relative paths under ./services/...) work cross-platform.
      - /Users/Shared/Ios/Gimle-Palace:/repos/gimle:ro
      - /Users/Shared/Android/unstoppable-wallet-android:/repos/uw-android:ro
      - ./services/palace-mcp/tests/extractors/fixtures/oz-v5-mini-project:/repos/oz-v5-mini:ro
```

- [ ] **Step 3: Validate compose file syntactically**

Run:
```bash
docker compose config --quiet 2>&1 | head -5
```

Expected: empty output (success). Errors → fix YAML indentation.

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml
git commit -m "chore(GIM-127): add uw-android bind-mount + non-iMac contributor override note"
```

---

### Task 12: Update `.env.example` — Android slug example

**Files:**
- Modify: `.env.example` (search for `PALACE_SCIP_INDEX_PATHS` example, extend)

- [ ] **Step 1: Verify current example**

Run:
```bash
grep -B 1 -A 2 "PALACE_SCIP_INDEX_PATHS" .env.example
```

- [ ] **Step 2: Update example to include Android slug**

Edit `.env.example`. Find the `PALACE_SCIP_INDEX_PATHS` example line. Replace its example value with one showing 3 slugs:
```
# JSON map of project slug → SCIP index path (operator generates outside container)
PALACE_SCIP_INDEX_PATHS={"gimle":"/repos/gimle/scip/index.scip","oz-v5-mini":"/repos/oz-v5-mini/index.scip","uw-android":"/repos/uw-android/scip/index.scip"}
```

- [ ] **Step 3: Commit**

```bash
git add .env.example
git commit -m "docs(GIM-127): show Android slug example in PALACE_SCIP_INDEX_PATHS"
```

---

### Task 13: Update `CLAUDE.md` — Operator workflow + project mount table + override note

**Files:**
- Modify: `CLAUDE.md` (in §Extractors section: add "Operator workflow: Android symbol index" subsection; in project mount table: add `uw-android` row; add non-iMac override note)

- [ ] **Step 1: Locate Extractors section**

Run:
```bash
grep -n "^## Extractors\|^### Operator workflow\|^### Registered extractors" CLAUDE.md
```

Expected: existing "Registered extractors" + per-language operator workflow subsections.

- [ ] **Step 2: Add Android operator workflow subsection**

In CLAUDE.md, after the existing "### Operator workflow: Java/Kotlin symbol index" subsection (or equivalent), add:

```markdown
### Operator workflow: Android symbol index (modern Compose+KSP+multi-module)

Android projects (e.g., `unstoppable-wallet-android`) use scip-java with
real Android Gradle Plugin classpath. KSP-generated source (Room, etc.)
is included in the index when scip-java's source roots include
`build/generated/ksp/<variant>/kotlin`.

1. Clone target project on iMac:
   ```bash
   git clone https://github.com/horizontalsystems/unstoppable-wallet-android.git \
     /Users/Shared/Android/unstoppable-wallet-android
   ```

2. Generate `.scip` outside container (requires JDK 17+ + system Gradle ≥8.x):
   ```bash
   cd /Users/Shared/Android/unstoppable-wallet-android
   gradle :app:compileDebugKotlin
   npx @sourcegraph/scip-java index --output ./scip/index.scip
   ```

3. Set env var for palace-mcp container in `.env`:
   ```
   PALACE_SCIP_INDEX_PATHS={..., "uw-android":"/repos/uw-android/scip/index.scip"}
   ```

4. Run the extractor:
   ```
   palace.ingest.run_extractor(name="symbol_index_java", project="uw-android")
   ```

5. Query (after GIM-126 lands; currently use `palace.memory.lookup`):
   ```
   palace.code.find_references(qualified_name="WalletDao", project="uw-android")
   ```
```

- [ ] **Step 3: Update project mount table**

In CLAUDE.md, find the `## Mounting project repos for palace.git.*` section. Update the mount table:

```markdown
| Slug         | Host path                                            | Mount                |
|--------------|------------------------------------------------------|----------------------|
| `gimle`      | `/Users/Shared/Ios/Gimle-Palace`                     | `/repos/gimle:ro`    |
| `oz-v5-mini` | `./services/palace-mcp/tests/extractors/fixtures/oz-v5-mini-project` | `/repos/oz-v5-mini:ro` |
| `uw-android` | `/Users/Shared/Android/unstoppable-wallet-android`   | `/repos/uw-android:ro` |
```

- [ ] **Step 4: Add non-iMac contributor override note**

In CLAUDE.md, in the same `## Mounting project repos` section, add at end:

```markdown
### Non-iMac contributors

Real-project bind-mounts (`gimle`, `uw-android`) use absolute Mac paths
(`/Users/Shared/...`) for operator-iMac convention. Non-iMac contributors
should:

- Create `docker-compose.override.yml` redirecting these paths to local clones, OR
- Run `docker compose --profile review up` excluding affected services and use only fixture-based mounts (paths under `./services/palace-mcp/tests/extractors/fixtures/`) which work cross-platform.

iOS-related mounts (`uw-ios`) intentionally NOT yet present — Slice 3 (iOS extractor)
will add them. UW-ios may be cloned now as discretionary ops-prep but is not gated.
```

- [ ] **Step 5: Verify CLAUDE.md edit syntactically**

Run:
```bash
grep -E "uw-android|Operator workflow: Android|docker-compose.override.yml" CLAUDE.md | wc -l
```

Expected: ≥4 matches.

- [ ] **Step 6: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(GIM-127): CLAUDE.md — Android operator workflow + uw-android mount + non-iMac override note"
```

---

### Task 14: Final pre-CR mechanical review (lint + format + typecheck + test suite)

**Files:**
- Verify: all changes from Tasks 1-13

- [ ] **Step 1: Ruff check**

Run:
```bash
cd services/palace-mcp && uv run ruff check src/ tests/ 2>&1 | tail -5
```

Expected: `All checks passed!`. Otherwise fix.

- [ ] **Step 2: Ruff format check**

Run:
```bash
cd services/palace-mcp && uv run ruff format --check src/ tests/ 2>&1 | tail -5
```

Expected: `XXX files already formatted` (no `Would reformat`). Otherwise: `uv run ruff format src/ tests/` then re-check.

- [ ] **Step 3: mypy strict**

Run:
```bash
cd services/palace-mcp && uv run mypy src/ 2>&1 | tail -5
```

Expected: `Success: no issues found in N source files`.

- [ ] **Step 4: pytest GIM-127-scoped**

Run:
```bash
cd services/palace-mcp && uv run pytest tests/extractors/unit/test_real_scip_fixtures.py::TestUwAndroidMiniProjectFixture -v
```

Expected: `13 passed` (or `12 passed, 1 skipped` if Branch B-2).

- [ ] **Step 5: pytest full suite (excluding integration)**

Run:
```bash
cd services/palace-mcp && uv run pytest -v -m "not integration" 2>&1 | tail -10
```

Expected: all passed; no new failures introduced.

- [ ] **Step 6: pytest integration (if Neo4j up)**

Run:
```bash
cd services/palace-mcp && docker compose --profile review up -d neo4j && sleep 5
COMPOSE_NEO4J_URI=bolt://localhost:7687 NEO4J_PASSWORD=$(grep NEO4J_PASSWORD ../../.env | cut -d= -f2) \
  uv run pytest tests/extractors/integration/test_symbol_index_java_uw_integration.py -v -m integration
```

Expected: `1 passed`.

- [ ] **Step 7: docker compose syntax check**

Run:
```bash
docker compose config --quiet 2>&1
```

Expected: empty output.

- [ ] **Step 8: git status — verify expected changes**

Run:
```bash
git status --short
git log --oneline origin/develop..HEAD | wc -l
```

Expected: ~10-15 commits ahead of develop, no unexpected `??` files. (Phase 1.0 commits + Tasks 6-13 commits.)

- [ ] **Step 9: Push branch + open draft PR**

```bash
git push -u origin feature/GIM-127-android-scip-java-validation
gh pr create --draft --title "feat(GIM-127): Android scip-java AGP validation — Slice 1" --body "$(cat <<'PRBODY'
## Summary

- Slice 1 of 4-5 in post-Solidity language coverage roadmap (Slice 1: this → Slice 2: Android resources → Slice 3: iOS native → Slice 4: KMP bridge)
- **No new extractor code** — validates existing `symbol_index_java` (GIM-111) on real Android via vendored `unstoppable-wallet-android` subset
- 4-module fixture: `:app-mini` + `:core-mini` + `:components:icons-mini` + `:components:chartview-mini`
- Exercises: Compose @Composable + multi-module Gradle + KSP via Room + cross-module USE resolution
- Companion: GIM-126 (find_references lang-agnostic fix) — separate FB, NOT a blocker

## Test plan

- [ ] `uv run ruff check && uv run ruff format --check && uv run mypy src/` — clean
- [ ] `uv run pytest tests/extractors/unit/test_real_scip_fixtures.py::TestUwAndroidMiniProjectFixture -v` — all pass
- [ ] `uv run pytest tests/extractors/integration/test_symbol_index_java_uw_integration.py -v -m integration` — passes against Neo4j
- [ ] Phase 4.1 QA live-smoke on iMac (UW-android registered + run_extractor + memory.lookup verifies)

## QA Evidence

(Phase 4.1 QAEngineer fills after iMac deploy)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
PRBODY
)"
```

- [ ] **Step 10: Reassign in paperclip — Phase 3.1 CodeReviewer**

(Operator/CTO action, outside this plan's scope. Plan deliverable ends here.)

---

## Self-review checklist

Before marking plan complete, verify:

**1. Spec coverage:**
- [x] AC#1 (fixture compiles) — Task 7 Step 2
- [x] AC#2 (scip-java emits valid index) — Task 7 Step 3
- [x] AC#3 (oracle counts match) — Task 9 (TestUwAndroidMiniProjectFixture)
- [x] AC#4 (KSP-generated WalletDao_Impl, conditional Phase 1.0 gate) — Task 0a Step 7 + Task 9 `test_wallet_dao_impl_ksp_generated`
- [x] AC#5 (cross-module USE — **5 pairs per spec, all covered in rev2**) — Task 9:
  - pair 1/5 app→repo: `test_cross_module_use_repo_in_viewmodel`
  - pair 2/5 app→icons: `test_cross_module_use_icons_in_main_screen` ⚡rev2
  - pair 3/5 app→chart: `test_cross_module_use_chart_in_main_screen` ⚡rev2
  - pair 4/5 repo→dao: `test_cross_module_use_dao_in_repository` ⚡rev2
  - pair 5/5 dao_impl→dao: `test_cross_module_use_dao_impl_to_dao` ⚡rev2 (conditional B-2 skip)
- [x] AC#6 (@Composable qualified_names + KOTLIN language) — Task 9 `test_main_screen_composable_present` + `test_chart_view_composable_present` (both with explicit `language == Language.KOTLIN` per-DEF check, rev2 WARNING #2 fix) + `test_qualified_names_have_no_scheme_prefix`
- [x] AC#7 (integration test green) — Task 10 (with rev2 Tantivy doc count Assert 4 per WARNING #1)
- [x] AC#8 (docker-compose 1 bind-mount uw-android) — Task 11
- [x] AC#9 (.env.example documented) — Task 12
- [x] AC#10 (CLAUDE.md updated) — Task 13

**2. Placeholder scan:**
- `<FROM_REGEN_MD>` in Task 9 Step 3 is a deliberate fillable placeholder pointing to REGEN.md oracle table — instruction is concrete: "Replace with locked numbers from REGEN.md oracle table." This is acceptable per writing-plans skill (deterministic action, not vague TODO). PE replaces during Step 3, not at execution time.
- No `<count>` placeholders should reach implementation — Task 1 Step 2 enforces this gate.

**3. Type / API consistency:**
- `parse_scip_file` / `iter_scip_occurrences` / `Language.KOTLIN` / `SymbolKind.DEF` / `SymbolKind.USE` — all match existing imports in `test_real_scip_fixtures.py`.
- `ExtractorRunContext`, `SymbolIndexJava` — match existing `test_symbol_index_java_integration.py`.
- `requires_scip_uw_android` marker name consistent across pyproject.toml + test_real_scip_fixtures.py + test_symbol_index_java_uw_integration.py.

**4. Phase ordering:**
- Phase 1.0 (Board) gates Phase 2 (PE) — Task 1 Step 1-3 enforces.
- Phase 3.1 / 3.2 / 4.1 / 4.2 are downstream (out of plan scope) — Task 14 Step 9-10 hands off.
