# UW iOS vs Android Cross-Platform Extractor Diff Report — 2026-05-20

**GIM-380 — M2.2 · UW Discovery Readiness rev2**

## Summary

Side-by-side comparison of palace-mcp extractor results across `uw-ios` (fixture
baseline) and `uw-android` (real repo ingest). Produced to identify parity gaps
before M3 UW Discovery work begins.

| Metric | iOS (`uw-ios-mini`) | Android (`uw-android`) |
|---|---:|---:|
| Data source | `docs/runbooks/uw-ios-mini-audit-baseline-2026-05-19.json` | `docs/runbooks/uw-android-ingest-2026-05-20.md` |
| Run type | Fixture (GIM-375 M1.1) | Real repo, pin `c0489d5a` (GIM-379) |
| Language profile | `swift_kit` | `android_kit` |
| Unique extractors run | 15 functional + 2 infra | 12 functional + 1 infra |
| Status OK | 12 | 12 |
| Status RUN_FAILED | 2 | 0 |
| Status NOT_ATTEMPTED | 1 | 0 |
| Acceptance met | Yes (12/10 threshold) | Yes |

18 unique extractors across both platforms. **10 divergences** across 3 categories.

---

## Row-by-Row Extractor Table

Legend — Status: **OK** · **RUN\_FAILED** · **NOT\_ATTEMPTED** · `—` = not in bounded set for this platform.  
Match column: ✓ = both OK with compatible outcomes · **DIVERGE** = real difference · *iOS-only* · *Android-only* · *platform-infra* = language-specific infra.

### Functional Extractors

| Extractor | iOS Status | iOS Outcome | Android Status | Android Outcome | Match |
|---|---|---|---:|---|---|
| `arch_layer` | OK | `ok` | OK | `ok` | ✓ |
| `code_ownership` | NOT\_ATTEMPTED | — | OK | `ok` | **DIVERGE** |
| `coding_convention` | OK | `ok` | OK | `ok` | ✓ |
| `cross_module_contract` | OK | `skipped` | OK | `skipped` | ✓ |
| `cross_repo_version_skew` | OK | `missing_input` | OK | `ok` | ✓ note¹ |
| `crypto_domain_model` | OK | `ok` | — | — | *iOS-only* |
| `dead_symbol_binary_surface` | RUN\_FAILED | `periphery_fixtures_missing` | — | — | *iOS-only* |
| `dependency_surface` | OK | `ok` | OK | `ok` | ✓ |
| `error_handling_policy` | OK | `ok` | — | — | *iOS-only* |
| `hot_path_profiler` | OK | `missing_input` | OK | `missing_input` | ✓ |
| `hotspot` | RUN\_FAILED | `prerequisite_missing` | OK | `ok` | **DIVERGE** |
| `localization_accessibility` | OK | `ok` | — | — | *iOS-only*² |
| `public_api_surface` | OK | `missing_input` | OK | `missing_input` | ✓ |
| `reactive_dependency_tracer` | OK | `ok` | — | — | *iOS-only* |
| `testability_di` | OK | `ok` | OK | `ok` | ✓ |

### Infrastructure Extractors

| Extractor | iOS Status | iOS Outcome | Android Status | Android Outcome | Match |
|---|---|---|---|---|---|
| `git_history` | ERROR | `error` | OK | `ok` | **DIVERGE** |
| `symbol_index_swift` | OK | `ok` | — | — | *platform-infra* |
| `symbol_index_java` | — | — | OK | `ok` | *platform-infra* |

---

## Divergence Analysis

### Category A — Platform-specific infrastructure (expected, 2 extractors)

| Extractor | Platform | Reason |
|---|---|---|
| `symbol_index_swift` | iOS only | Swift SCIP index — not applicable to Android |
| `symbol_index_java` | Android only | Kotlin/Java SemanticDB index — not applicable to iOS |

No action required. These are language-layer infrastructure extractors that are
intentionally scoped per platform.

### Category B — iOS-only profile extractors (not run on Android, 5 extractors)

| Extractor | iOS Result | Android | Reason |
|---|---|---|---|
| `crypto_domain_model` | OK / `ok` | not run | Not in `android_kit` bounded set |
| `error_handling_policy` | OK / `ok` | not run | Not in `android_kit` bounded set |
| `localization_accessibility` | OK / `ok` | excluded² | Excluded from GIM-379 bounded run (unbounded live behavior) |
| `reactive_dependency_tracer` | OK / `ok` | not run | Not in `android_kit` bounded set |
| `dead_symbol_binary_surface` | RUN\_FAILED / `periphery_fixtures_missing` | not run | iOS fixture gap; Periphery is Swift-only tooling |

> ² `localization_accessibility` exists in the android_kit profile but was excluded
> from the GIM-379 bounded run because it showed unbounded live-runtime behavior on
> the full uw-android repo. Needs a bounded run or timeout guard before inclusion.

**Action:** Evaluate `localization_accessibility` for Android inclusion in M3.
Other extractors in this category are Swift-specific and have no Android equivalent.

### Category C — iOS fixture limitations (real divergences, 3 extractors)

These extractors are in scope for both platforms but produce different results
because the iOS run used a fixture directory without a real git repository.

| Extractor | iOS Status | iOS Outcome | Android Status | Android Outcome | Root cause |
|---|---|---|---|---|---|
| `git_history` | ERROR | `error` | OK | `ok` | iOS fixture has no real `.git`; Android ran against pinned real repo |
| `hotspot` | RUN\_FAILED | `prerequisite_missing` | OK | `ok` | Blocked by iOS `git_history` failure; unblocked on Android |
| `code_ownership` | NOT\_ATTEMPTED | — | OK | `ok` | Blocked by iOS `git_history` failure; unblocked on Android |

All three failures cascade from a single root cause: the iOS fixture at
`services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project` lacks a real
git repository. The `.git` mount is a symlink-only stub.

**Action (M3 prerequisite):** Before running the iOS full-repo audit
(GIM-377 bundle, real `/Users/Shared/Ios/unstoppable-wallet-ios` repo), verify
that `git_history` passes on the live repo. If it does, `hotspot` and
`code_ownership` will also clear automatically.

---

## Notes

¹ `cross_repo_version_skew`: both platforms returned status `OK`, but outcomes
differ (`missing_input` on iOS vs `ok` on Android). The iOS fixture has 0
declared dependencies, so there was no data to evaluate skew. Android has 1 node
written. Not a functional divergence — the extractor behaves correctly in both
cases given the available input.

---

## Known Caveats

| Caveat | Detail |
|---|---|
| iOS = fixture run | iOS data comes from `uw-ios-mini-project` fixture, not the real Unstoppable Wallet iOS repo. Results reflect fixture limitations, not the production codebase. |
| Android = real repo | Android data comes from a live ingest against the pinned repo (`c0489d5a`). Results are representative of the production codebase. |
| Different bounded sets | The `swift_kit` and `android_kit` profiles do not share identical extractor sets. Extractors listed as iOS-only or Android-only reflect profile boundaries, not missing implementations. |
| `localization_accessibility` not verified on Android | Excluded from GIM-379 run scope. Status on Android real repo is unknown. |

---

## Data Provenance

| Source | Path | Commit |
|---|---|---|
| iOS JSON baseline | `docs/runbooks/uw-ios-mini-audit-baseline-2026-05-19.json` | `origin/develop` |
| Android ingest runbook | `docs/runbooks/uw-android-ingest-2026-05-20.md` | `2fda32c` on `origin/develop` |
| This report | `docs/runbooks/uw-cross-platform-diff-2026-05-20.md` | GIM-380 M2.2 |
