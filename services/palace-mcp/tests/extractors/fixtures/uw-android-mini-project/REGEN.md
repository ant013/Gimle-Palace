# uw-android-mini-project — Fixture Regen Instructions

## Source

- **Repository:** https://github.com/horizontalsystems/unstoppable-wallet-android
- **Branch tracked:** `master`
- **Phase 1.0 trial SHA:** `f830bb528998855dcfe276c1e4ff927a1e2cd9a1` (2026-04-30)
- **License:** MIT

## Phase 1.0 trial outcome (2026-04-30, dev-Mac)

### Fixture compile: PASS ✅

`gradle :app-mini:compileDebugKotlin :core-mini:compileDebugKotlin :components:icons-mini:compileDebugKotlin :components:chartview-mini:compileDebugKotlin` — **BUILD SUCCESSFUL**.

### KSP generation: PASS ✅ (preliminary AC#4 Branch A signal)

KSP did generate `WalletDao_Impl.kt` and `AppDatabase_Impl.kt` at:
- `core-mini/build/generated/ksp/debug/kotlin/io/horizontalsystems/uwmini/core/db/WalletDao_Impl.kt`
- `core-mini/build/generated/ksp/debug/kotlin/io/horizontalsystems/uwmini/core/db/AppDatabase_Impl.kt`

This is the AC#4 KSP-source-visibility prerequisite. Full validation (whether scip-java *sees* generated source) blocked by next item.

### scip-java index: FAIL ❌ (BLOCKER)

`scip-java 0.12.3` (latest stable, released 2024) **fails** when run against this fixture:
```
> Task :app-mini:scipPrintDependencies FAILED
> java.util.ConcurrentModificationException (no error message)
```

Root cause (probable): `com.sourcegraph.gradle.semanticdb.SemanticdbGradlePlugin` (scip-java's auto-injected Gradle plugin) is **not compatible with AGP 9.1.0 + Gradle 9.3.1 + Kotlin 2.3.10**. This combination is from 2026; scip-java's last release predates it.

Workaround attempts that did not resolve:
- `--no-parallel --no-daemon` Gradle args via scip-java trailing
- `--stacktrace` (revealed scip-java falls back to `gradle help` instead of `scipPrintDependencies` when trailing args present)

### Toolchain on dev-Mac

- Java 21.0.1 LTS
- Gradle 9.3.1 (from Homebrew)
- Kotlin 2.3.10 + KSP 2.3.2 + Compose 1.10.2 + Room 2.8.1 (from UW `libs.versions.toml`)
- AGP 9.1.0
- scip-java 0.12.3 (installed via `cs install --contrib scip-java`)
- Android SDK 36 at `~/Library/Android/sdk`

## Decision required (escalated to operator 2026-04-30)

Three options for Phase 1.0 unblock:

### Option 1 — Pin fixture to AGP 8.x + Gradle 8.x + Kotlin 2.0/2.1

Trade-off: fixture lags behind real-world UW master (which uses AGP 9). Most operator Android projects (incl. likely Medic) probably still on AGP 8.x — fixture remains representative. **Lowest engineering cost, fastest unblock.**

### Option 2 — Manual semanticdb mode

Apply Sourcegraph's semanticdb compiler plugin manually in each module's `build.gradle.kts`, bypass scip-java auto-config. Run `scip-java index-semanticdb --targetroot build/semanticdb-targetroot`. **High engineering cost; uncharted territory.**

### Option 3 — Park GIM-127

Wait until scip-java releases AGP 9 support. Move to other slices (Slice 2/3/4 or other backlog). Re-trial later. **Zero engineering on this slice now; opportunity cost on roadmap.**

## Vendoring strategy (per spec rev3)

| Module | Strategy |
|---|---|
| `:components:icons-mini/WalletIcons.kt` | **SYNTHESIZED** — UW upstream has no Kotlin in `:components:icons` |
| `:components:chartview-mini/{ChartViewType,ChartDraw,models/ChartPointF}.kt` | **VENDORED VERBATIM** from UW `:components:chartview` (package adapted) |
| `:components:chartview-mini/ChartView.kt` | **SYNTHESIZED** — UW's `ChartView.kt` is View-based, not Compose |
| `:core-mini/db/*` (`WalletEntity`, `WalletDao`, `AppDatabase`) | **SYNTHESIZED** in UW DAO style — UW Room actually in `:app/.../core/storage/` |
| `:core-mini/{model,repository}/*` | **SYNTHESIZED** |
| `:app-mini/*` | **SYNTHESIZED** |
| `LICENSE` + `gradle/libs.versions.toml` | **VENDORED** (libs.versions.toml trimmed: dropped blockchain SDK entries, kept Kotlin/AGP/Compose/Room core) |

## Manual oracle table (Phase 1.0 — BLOCKED on scip-java)

> Oracle counts pending: scip-java index step failed. Phase 1.0 cannot complete the count column until decision on Options 1/2/3 above.

| Metric | Value | Notes |
|---|---|---|
| N_MODULES | 4 | :app-mini, :core-mini, :components:icons-mini, :components:chartview-mini ✅ |
| N_DOCUMENTS_TOTAL | BLOCKED | scip-java fails before producing index |
| N_DEFS_TOTAL | BLOCKED | — |
| N_DECLS_TOTAL | BLOCKED | — |
| N_USES_TOTAL | BLOCKED | — |
| N_OCCURRENCES_TOTAL | BLOCKED | — |
| N_DEFS_KSP_GENERATED | BLOCKED-PROBABLY-OK | KSP did generate sources in `core-mini/build/generated/ksp/debug/kotlin/`; scip-java visibility untestable until Options 1/2/3 resolved |
| AC#4 Branch | TBD | Cannot lock until scip-java works |

## Regen procedure (post-decision)

Requires: JDK 17+, system Gradle (version pinned per Option 1 outcome), `scip-java` (installed via `cs install --contrib scip-java` after `brew install coursier/formulas/coursier`), Android SDK at `$ANDROID_HOME` or `local.properties`.

```bash
cd services/palace-mcp/tests/extractors/fixtures/uw-android-mini-project
echo "sdk.dir=$HOME/Library/Android/sdk" > local.properties  # or set ANDROID_HOME
bash regen.sh
```

`regen.sh` runs `gradle compileDebugKotlin` × 4 modules, then invokes scip-java. **Currently `regen.sh` will fail at the scip-java step** until Phase 1.0 decision resolves.
