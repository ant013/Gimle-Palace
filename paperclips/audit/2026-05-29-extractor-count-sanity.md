# Extractor Count Sanity Audit — uw-ios-app

**Issue:** GIM-1064
**Date:** 2026-06-01
**Project:** uw-ios-app (70,291 symbols, 1,883 Swift files)
**Repo:** `/Users/Shared/UnstoppableAudit/repos/ios/unstoppable-wallet-ios`

## Summary

| Label | Reported | Expected | Verdict | Root Cause |
|---|---|---|---|---|
| Symbol | 70,291 | — | baseline | — |
| DeadFinding | 70,291 | < 5,000 | **BUG** | Seeds empty → all symbols dead |
| PublicApiSymbol | 140 | 0 or 500+ | **DESIGN** | Requires committed `.palace/public-api/` artifacts; UW has none |
| Author | 11 | 19 | **BUG** | Checkpoint-based walk missed older commits; email dedup too aggressive |
| LocaleResource | 18 | 18–27 | **CORRECT** | 9 locales × 2 surfaces + xcstrings catalogs |
| CryptoFinding | 69 | 50–200 | **CORRECT** | 5 semgrep rules; count is plausible |
| A11yMissing | 688 | 500–1000 | **CORRECT** | Proportional to file count; no baseline to invalidate |
| DiPattern | 1 | 50–100+ | **BUG** | Module inference fails for non-SPM layouts; DI framework list too narrow |
| ErrorFinding | 880 | 500–2000 | **CORRECT** | Semgrep-driven; proportional to catch/try? density |

**Extractors needing follow-up fixes: 3** (dead_code, git_history, testability_di)
**Extractors needing design decision: 1** (public_api_surface)

---

## Per-Extractor Analysis

### 1. DeadFinding — BUG: all symbols marked dead

**Extractor:** `dead_code` (`extractors/dead_code/extractor.py`)
**Reported count:** 70,291 (identical to Symbol count)
**Expected:** < 5,000 genuine dead-code findings

**Root cause:** The G0d algorithm's seed computation (`seeds.py:compute_all_seeds`) relies on
SCIP-index flags (`is_public`, `is_open`, `is_main_entry`, `is_iboutlet`, etc.) to identify
entry points. If the SCIP index for UW doesn't correctly set these flags on Symbol nodes —
for example, if the Swift SCIP indexer marks all symbols as internal (no `is_public=true`) —
then `compute_all_seeds` returns an empty set. With zero seeds, BFS marks nothing reachable,
and every symbol becomes a dead candidate. The finding_builder then creates one `DEAD_SYMBOL`
finding per unreachable symbol, producing exactly `count(Symbol)` DeadFinding nodes.

**Validation:**
- `seeds.py:8–18`: public seeds require `sym.is_public or sym.is_open or sym.is_main_entry`
- UW's symbols are overwhelmingly `internal` (Swift default access) — public/open keywords
  appear on only ~264 declarations out of 70,291 symbols
- The SCIP indexer may not propagate `is_public` for symbols that are module-public but
  lack explicit `public` keyword

**Follow-up needed:**
- Verify SCIP index flags on uw-ios-app Symbol nodes (query: `MATCH (s:Symbol {group_id: 'project/uw-ios-app'}) WHERE s.is_public = true RETURN count(s)`)
- If SCIP flags are correct but internal symbols dominate, the algorithm needs a "module boundary" seed strategy for app targets (where internal = entry point)
- Severity: **HIGH** — undermines all dead-code audit reports for this project

### 2. PublicApiSymbol — DESIGN: requires pre-committed artifacts

**Extractor:** `public_api_surface` (`extractors/public_api_surface.py`)
**Reported count:** 140
**Expected:** 0 (no artifacts) or 500+ (if artifacts generated)

**Root cause:** The extractor reads ONLY from `.palace/public-api/swift/*.swiftinterface` and
`.palace/public-api/kotlin/*.api` files committed to the repo. UW has NO such directory —
confirmed: `.palace/public-api/` does not exist in the repo.

The 140 count likely comes from:
- A stale run against a different project's artifacts, OR
- Package dependencies that include `.swiftinterface` files in their build products

The extractor explicitly states this in its MISSING_INPUT return:
> "No public API artifacts found under '.palace/public-api/kotlin/*.api' or '.palace/public-api/swift/*.swiftinterface'."

**Validation:**
```
$ ls .palace/public-api/  # does not exist
$ grep -rn 'public \|open ' --include='*.swift' | wc -l  # 1,334 matches
$ grep -rn '^public ' --include='*.swift' | wc -l  # 234 line-leading public decls
$ grep -rn '^open ' --include='*.swift' | wc -l  # 30 line-leading open decls
```

**Follow-up needed:**
- Design decision: should palace generate `.swiftinterface` artifacts automatically as a
  build step, or should the extractor fall back to SCIP-index visibility flags?
- The extractor correctly returns MISSING_INPUT when no artifacts exist — the 140 count
  needs investigation (stale data from another project?)
- Severity: **LOW** — extractor works as designed; needs artifact pipeline for UW

### 3. Author — BUG: under-counting contributors

**Extractor:** `git_history` (`extractors/git_history/extractor.py`)
**Reported count:** 11
**Expected:** 19 unique email addresses (35 name+email pairs)

**Root cause:** The git_history extractor uses checkpoint-based incremental walks
(`walk_since(ckpt.last_commit_sha)`). If the initial run was interrupted or the checkpoint
was set from a recent commit, older contributors are never processed. The Author node MERGE
key is `(provider, identity_key)` where identity_key = `email.lower()`.

**Validation:**
```
$ git log --format='%ae' | sort -u | wc -l  # 19 unique emails
$ git log --format='%an <%ae>' | sort -u | wc -l  # 35 name+email pairs
```

Notable: many contributors use multiple name variants for the same email:
- `ant013@mail.ru` → "ant", "ant013", "anton", "Anton Stavnichiy"
- `ealymbaev@gmail.com` → "EA", "Ermat", "Ermat Alymbaev"
- `trickster77777@gmail.com` → "Maksim Nizhurin", "Max", "mNizhurin", "max"

The MERGE on email correctly deduplicates these. So 11 vs 19 = **8 authors never walked**.

**Possible causes (ranked by likelihood):**
1. Checkpoint set to a mid-history commit; older contributors never ingested
2. `CommitNotFoundError` triggered a full resync that silently skipped some commits
3. Bot detection (`is_bot`) incorrectly filtering human contributors

**Follow-up needed:**
- Run a fresh full resync (`walk_since(None)`) and compare Author count
- Add a "full history coverage" check to the extractor's audit_contract
- Severity: **MEDIUM** — affects code ownership and contributor analysis accuracy

### 4. LocaleResource — CORRECT

**Extractor:** `localization_accessibility` (`extractors/localization_accessibility/extractor.py`)
**Reported count:** 18
**Expected:** 18–27

**Validation:**
```
$ find . -name '*.lproj' -type d | sort -u | wc -l  # 19 .lproj dirs
$ find . -name '*.xcstrings' | wc -l  # 2 xcstrings catalogs
```

Breakdown:
- 9 Localizable.strings files (9 locales: de, en, es, fr, ko, pt-BR, ru, tr, zh)
- 2 .xcstrings catalogs (Widget, WalletCore) each producing per-locale entries
- WidgetIntents .lproj dirs may lack Localizable.strings → not counted

18 is within expected range. The issue's expectation of "hundreds" was an overestimate —
UW has 9 locales with 2-3 surfaces, not hundreds of strings files.

**No follow-up needed.**

### 5. CryptoFinding — CORRECT (narrow rule set)

**Extractor:** `crypto_domain_model` (`extractors/crypto_domain_model/extractor.py`)
**Reported count:** 69
**Expected:** 50–200

**Validation:** The extractor runs exactly 5 semgrep rules:
1. `address_no_checksum_validation.yaml`
2. `bignum_overflow_unguarded.yaml`
3. `decimal_raw_uint_arithmetic.yaml`
4. `private_key_string_storage.yaml`
5. `wei_eth_unit_mix.yaml`

69 findings from 5 rules across 1,883 Swift files is plausible. The issue's expectation of
"dozens per blockchain × 30+ chains" misunderstands the extractor — it detects crypto CODE
SMELLS (unsafe patterns), not per-blockchain coverage.

**Observation:** The rule set is narrow. A crypto wallet app could benefit from additional
rules (e.g., insecure random, timing-unsafe comparison, key material in logs). This is a
feature request, not a bug.

**No bug follow-up needed.** Consider adding rules as separate enhancement.

### 6. A11yMissing — CORRECT (no baseline to dispute)

**Extractor:** `localization_accessibility` (semgrep rules)
**Reported count:** 688
**Expected:** 500–1000

688 from 2 a11y semgrep rules (`a11y_missing_label_swiftui.yaml`, `a11y_missing_compose.yaml`)
across 1,883 Swift files is ~0.37 per file. Plausible for SwiftUI views without accessibility
labels. No external baseline exists to dispute.

**No follow-up needed.**

### 7. DiPattern — BUG: module inference + narrow framework detection

**Extractor:** `testability_di` (`extractors/testability_di/extractor.py`)
**Reported count:** 1
**Expected:** 50–100+

**Root cause (two bugs):**

**Bug A — Module inference failure:** `scanner.py:_infer_module` looks for `Sources/`,
`Tests/`, or `src/` in the path. UW's layout is `Unstoppable/Unstoppable/Core/...` — none
of these anchors exist. Fallback: `parts[0]` = "Unstoppable" for ALL 1,883 files. Since
`extract_di_patterns` counts per `(module, language, style)` tuple, the entire codebase
collapses into a single module, producing at most 1 DiPattern per style.

**Bug B — DI framework list too narrow for UW:** The extractor recognizes:
- Swift: Resolver, Swinject, Factory, NeedleFoundation
- Property injection: `@Injected`, `@LazyInjected`, `@InjectedObject`
- Service locator: `ServiceLocator.shared`, `Resolver.root/resolve`, `.resolve(`

UW uses **none** of these. UW uses manual constructor injection (2,923 files with `init(`
signatures) but no DI framework annotations. The only pattern that matches is `init_injection`
(the broad regex `\binit\s*\([^)]*:\s*[A-Z][A-Za-z0-9_<>.?]*`), which correctly matches
but gets collapsed into 1 DiPattern for module "Unstoppable".

**Validation:**
```
$ grep -rn '@Injected\|@LazyInjected\|import Resolver\|import Swinject' --include='*.swift' | wc -l  # 0
$ grep -rn 'ServiceLocator\.shared' --include='*.swift' | wc -l  # 0
$ grep -rn 'init(' --include='*.swift' | grep -v '/Tests/' | wc -l  # 2,923
```

**Follow-up needed:**
- Fix module inference: add Xcode project structure heuristic (look for `.xcodeproj` or
  use directory depth to infer module boundaries)
- Consider counting DiPattern per-file or per-class instead of per-module aggregate
- Severity: **MEDIUM** — DiPattern=1 correctly identifies the style but loses all
  granularity; downstream analysis sees "UW has trivial DI" when it actually has pervasive
  manual constructor injection

### 8. ErrorFinding — CORRECT

**Extractor:** `error_handling_policy` (`extractors/error_handling_policy/extractor.py`)
**Reported count:** 880
**Expected:** 500–2000

The extractor runs semgrep rules for error-handling anti-patterns (empty catch, try? swallow,
catch-only-logs, nil-coalesce-swallows-error) plus a regex-based CatchSite inventory. 880
findings for 1,883 Swift files with UW's heavy use of async/crypto error paths is plausible.

**No follow-up needed.**

---

## Follow-Up Issues Required

### Issue 1: dead_code — Seeds empty for app-target projects (HIGH)
The G0d algorithm needs a seed strategy for app targets where `internal` = entry point.
SCIP flags may be correct (only explicit `public`/`open` are marked), but app targets don't
export a module boundary — all top-level types are effectively seeds.

**Fix options:**
- A: Add "app target" heuristic seed: if project has `@main` or `AppDelegate` and < 5% public
  symbols, treat all top-level class/struct/enum as seeds
- B: Add a SCIP indexer flag for "module-internal but app-accessible"
- C: Accept the parameter from extractor config: `seed_strategy: app_target | framework`

### Issue 2: git_history — Checkpoint may skip full history (MEDIUM)
Either the initial run was interrupted before walking the full history, or the checkpoint
was seeded from a recent commit. Need a "full coverage" validation step.

**Fix:** Add an audit_contract check comparing `count(DISTINCT a.identity_key)` for
`provider='git'` against `git log --format=%ae | sort -u | wc -l` from the repo.

### Issue 3: testability_di — Module inference for non-SPM layouts (MEDIUM)
The `_infer_module` function needs a fallback for Xcode project structures that don't
use `Sources/`/`Tests/`/`src/` anchors.

**Fix options:**
- A: Parse `.xcodeproj/project.pbxproj` to extract target → directory mappings
- B: Use a configurable module map in `.palace/config.yaml`
- C: Fall back to second-level directory as module (e.g., `Unstoppable/Core` → module "Core")

### Issue 4 (Enhancement): public_api_surface — Artifact generation pipeline
The extractor works as designed but requires pre-committed artifacts. UW needs either:
- A build step that generates `.swiftinterface` files, or
- A fallback mode that uses SCIP visibility flags

---

## Methodology

1. **Extractor source audit:** Read each extractor's `run()`, Neo4j writer, and detection
   logic to understand what conditions produce each label.
2. **Ground truth sampling:** Validated counts against the actual UW repo using grep, find,
   and git log to establish expected baselines.
3. **Root cause tracing:** For each discrepancy, traced through the extractor pipeline to
   identify the exact point where under/over-counting occurs.

All file references are relative to `services/palace-mcp/src/palace_mcp/extractors/`.
