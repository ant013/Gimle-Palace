# uw-android-mini-project — Fixture Regen Instructions

## Source

- **Repository:** https://github.com/horizontalsystems/unstoppable-wallet-android
- **Branch tracked:** `master` (with **pinned-pre-AGP-9 trade-off** — see Toolchain section)
- **Phase 1.0 lock SHA:** `c0489d5a33f5da441f07b1f685d42b25b805ffd1` (2026-02-11, "Bump version code after merge" — last commit before AGP 9 upgrade in `18d767c5`)
- **License:** MIT

## Toolchain

Pinned to UW@`c0489d5a3` to bypass scip-java's lack of Kotlin 2.3 / AGP 9 support (see [Sourcegraph issue #864](https://github.com/sourcegraph/scip-java/issues/864)).

| Component | Version | Source |
|---|---|---|
| AGP | 8.13.2 | UW@c0489d5a3 |
| Kotlin | 2.1.20 | UW@c0489d5a3 |
| KSP | 2.1.20-1.0.32 | UW@c0489d5a3 |
| Compose | 1.9.2 | UW@c0489d5a3 |
| Compose Material3 | 1.4.0 | UW@c0489d5a3 |
| Room | 2.8.1 | UW@c0489d5a3 |
| compileSdk | 36 | UW@c0489d5a3 |
| minSdk | 27 | UW@c0489d5a3 |
| **semanticdb-kotlinc** | **0.5.0** | Sourcegraph Maven Central — **0.6.0 fails on Kotlin 2.1+** (`AbstractMethodError` in `FirDeclarationChecker.check`); 0.5.0 works |
| scip-java | 0.12.3 | `cs install --contrib scip-java` |
| Gradle | 9.3.1 | system (Homebrew) — works with AGP 8.13.2 |

**Trade-off:** UW master uses AGP 9.1 / Kotlin 2.3.10 / Compose 1.10.2. Our pin is ~2.5 months stale relative to master. Architecture (Room schema, Compose patterns) unchanged in this window. **Followup**: re-pin to master once Sourcegraph adds Kotlin 2.3 support to scip-java/semanticdb-kotlinc.

## Phase 1.0 oracle (locked 2026-04-30)

> Oracle locked from end-to-end regen on dev Mac (Java 21, Gradle 9.3.1, scip-java 0.12.3, semanticdb-kotlinc 0.5.0). PE Phase 2 unblocked.

| Metric | Value |
|---|---|
| N_MODULES | 4 |
| N_DOCUMENTS_TOTAL | 17 |
| N_DEFS_TOTAL | 269 |
| N_DECLS_TOTAL | 0 |
| N_USES_TOTAL | 1201 |
| N_OCCURRENCES_TOTAL | 1470 |
| N_DEFS_KSP_GENERATED | 37 (WalletDao_Impl + AppDatabase_Impl + their members) |
| **AC#4 Branch** | **A** — KSP-generated source visible without workaround |

### AC#5 cross-module USE pairs (all 5 verified)

| # | Pair | USE count |
|---|---|---|
| 1 | MainViewModel → WalletRepository (`:app-mini` → `:core-mini`) | 4 |
| 2 | MainScreen → WalletIcons (`:app-mini` → `:components:icons-mini`) | 3 |
| 3 | MainScreen → ChartView (`:app-mini` → `:components:chartview-mini`) | 2 |
| 4 | WalletRepository → WalletDao (intra-`:core-mini` cross-package) | 8 |
| 5 | WalletDao_Impl → WalletDao (KSP-generated → source interface) | 1 |

### AC#6 Composable KOTLIN language

`MainScreen` (3 DEFs) and `ChartView` (11 DEFs) — all DEFs language=`KOTLIN`.

## Vendoring strategy (per spec rev3)

| Module | Strategy |
|---|---|
| `:components:chartview-mini/{ChartViewType,ChartDraw,models/ChartPointF}.kt` | **VENDORED VERBATIM** from UW@c0489d5a3 `:components:chartview` (package adapted to `io.horizontalsystems.uwmini.chartview`). Files are SHA-stable: identical at master and c0489d5a3. |
| `:components:chartview-mini/ChartView.kt` | **SYNTHESIZED** Compose Composable wrapping vendored types. UW upstream's `ChartView.kt` is `View`-based, not Compose. |
| `:components:icons-mini/WalletIcons.kt` | **SYNTHESIZED** — UW upstream `:components:icons` is XML-resources-only (no Kotlin). Compose `ImageVector` constants in UW style. |
| `:core-mini/db/*` (`WalletEntity`, `WalletDao`, `AppDatabase`) | **SYNTHESIZED** — UW Room actually lives in `:app/.../core/storage/` (20+ DAOs), not `:core`. Mirrors UW DAO conventions (snake-case tables, suspend + Flow, mixed @Insert/Update/Delete/Query). |
| `:core-mini/{model,repository}/*` | **SYNTHESIZED** |
| `:app-mini/*` | **SYNTHESIZED** in UW Activity+Compose+ViewModel+StateFlow style. |
| `LICENSE` | **VENDORED** from UW root |
| `gradle/libs.versions.toml` | **DERIVED** from UW@c0489d5a3 (trimmed: dropped blockchain SDK entries — web3j, bitcoin/ethereum/solana/tron/ton kits, Tor, Reown — kept Kotlin/AGP/Compose/Room/Coroutines core; added `semanticdbKotlinc = "0.5.0"` for Phase 2 manual scip-kotlin path) |

**Net vendoring count:** 1 of 4 modules has files truly vendored verbatim (`:components:chartview-mini` — 3 small files + 1 synthesized Composable wrapper). 3 of 4 modules synthesized in UW style with all version pins from UW@c0489d5a3 `libs.versions.toml`.

## Regen procedure

Requires (one-time):
- JDK 17+ (we use Java 21)
- System Gradle ≥8.x (Phase 1.0 used 9.3.1)
- Android SDK at `$ANDROID_HOME` or `local.properties`
- `coursier` + `scip-java`:
  ```bash
  brew install coursier/formulas/coursier
  cs install --contrib scip-java
  # binary at ~/Library/Application Support/Coursier/bin/scip-java
  ```

Per regen:

```bash
cd services/palace-mcp/tests/extractors/fixtures/uw-android-mini-project
echo "sdk.dir=$HOME/Library/Android/sdk" > local.properties  # or set ANDROID_HOME
bash regen.sh
```

`regen.sh` runs:
1. `gradle compileDebugKotlin` × 4 modules (semanticdb-kotlinc auto-injected via each module's `kotlinCompilerPluginClasspath`)
2. `scip-java index-semanticdb --targetroot build/semanticdb-targetroot --output ./scip/index.scip` (NOT `scip-java index` — auto-mode is broken on AGP 8 too for Kotlin-only modules)
3. AC#4 KSP-source-visibility check + count
4. Commit updated `index.scip`

## Updating the pin

When UW master diverges enough OR Sourcegraph adds Kotlin 2.3 support:

1. Re-trial scip-java + semanticdb-kotlinc against UW master
2. If working — update SHA pin in this file + regen
3. If still failing — pick more recent pre-AGP-9 SHA (or evaluate own emitter path per `project_scip_java_strategy_2026-04-30.md`)

## Followup gates

- 2026-05-07 — check status of [Sourcegraph issue #864](https://github.com/sourcegraph/scip-java/issues/864)
- After iOS slice merges — re-evaluate scip-java state; if still broken, kick off custom emitter / upstream PR contribution
