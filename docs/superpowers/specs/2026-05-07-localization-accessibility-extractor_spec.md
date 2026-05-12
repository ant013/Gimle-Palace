# Localization & Accessibility Extractor (#9) — Specification

**Document date:** 2026-05-07
**Status:** Formalized (CTO Phase 1.1 2026-05-12) · plan-first review in progress
**Author:** Board+Claude session (operator + Claude Opus 4.7)
**Team:** Claude (reassigned 2026-05-12 per roadmap rev3 §Stalled GIM-219 slices)
**Slice ID:** Phase 2 §2.2 #9 Localization & Accessibility Extractor
**Companion plan:** `2026-05-07-localization-accessibility-extractor_plan.md`
**Branch:** `feature/GIM-275-localization-accessibility-extractor`
**Blockers (rev4 — updated 2026-05-12):**
- ~~E6 closure (CX hire)~~ — no longer applies; reassigned to Claude team.
- **S0.1 IngestRun schema unification** (rev4 — CTO-XF-H1) — uses unified schema; if not yet landed, use existing `BaseExtractor` + `create_ingest_run` pattern (non-blocking).

---

## 1. Goal

Extract localization (i18n) coverage + accessibility (a11y) coverage
from Swift + Kotlin source so audit agents can answer:

- "Which strings in the codebase are hard-coded vs localised?"
- "What's the coverage of available locales?"
- "Are accessibility labels / hints present on UI controls?"
- "Which screens fail VoiceOver / TalkBack basic checks?"

Addresses target problem **#12 (i18n + a11y completeness)** in the
original 45-extractor research inventory.

**Definition of Done:**

1. New extractor `localization_accessibility` registered in
   `EXTRACTORS`.
2. `audit_contract()` returns per-screen localization + a11y coverage
   as Pydantic model.
3. Writes `:LocaleResource` + `:HardcodedString` + `:A11yMissing`
   nodes; enriches existing `:UIControl` (or equivalent) with
   `localized: bool`, `accessible: bool`.
4. `audit/templates/localization_accessibility.md` ships.
5. Operator runbook `docs/runbooks/localization-accessibility.md`.
6. Smoke run on `unstoppable-wallet-android` produces locale coverage
   per `values-XX/strings.xml` + ≥3 hard-coded string findings.

## 2. Scope

### In scope
- **iOS Swift surface**:
  - `.xcstrings` (Xcode 15+ catalog), legacy `Localizable.strings`.
    (`*.stringsdict` deferred to v2 — plural rules XML plist, low ROI for coverage metric.)
  - `NSLocalizedString(...)` invocations vs hard-coded `"text"` in
    UI code (SwiftUI `Text("...")`, UIKit `label.text = "..."`).
  - SwiftUI `.accessibilityLabel(...)`, `.accessibilityHint(...)`.
  - UIKit `accessibilityLabel`, `accessibilityHint`,
    `isAccessibilityElement`.
- **Android Kotlin surface**:
  - `res/values*/strings.xml` per locale.
  - `R.string.X` references vs hard-coded `"text"` in Compose
    (`Text("...")`) / View (`textView.text = "..."`).
  - Compose `Modifier.semantics { contentDescription = "..." }`.
  - View `android:contentDescription`, `android:labelFor`.
- **Cross-platform metrics**:
  - Coverage % per locale.
  - Count of hard-coded strings on UI surfaces.
  - Count of UI controls without accessibility metadata.

### Out of scope
- Translation quality / actual locale text correctness.
- Dynamic strings (string templates with placeholders) — only flag
  presence/absence, not interpolation correctness.
- Voice / Braille support beyond presence of accessibility metadata.
- A11y dynamic test execution (Google ATF run during extraction
  is too heavy; provide guidance in runbook for manual run only).

## 3. Detection strategy

| Surface | Tool | Method |
|---|---|---|
| Swift `.xcstrings` | xcstrings parser (XML/JSON) | enumerate keys × locales; flag missing |
| Swift `Localizable.strings` | Apple `plutil` / regex | parse key=value pairs per locale |
| Swift `NSLocalizedString` | SwiftSyntax visitor | match call-site arg vs literal |
| SwiftUI `Text(...)` | SwiftSyntax visitor | distinguish literal vs key-based |
| SwiftUI / UIKit a11y | SwiftSyntax visitor | match `.accessibilityLabel(...)` chains |
| Kotlin Android `strings.xml` | XML parser per locale dir | enumerate keys; compute coverage |
| Compose `Text("...")` | Konsist + tree-sitter | distinguish literal arg vs `stringResource(R.string.X)` |
| Compose semantics | Konsist | match `Modifier.semantics { ... }` chains |
| View XML `contentDescription` | Android Lint rule + tree-sitter-xml | match attribute presence |
| Cross-lang hard-coded check | semgrep | match user-facing string literal in UI declaration |

### Confidence
`heuristic` per research inventory. SwiftSyntax / Konsist AST
results = `certain`; semgrep = `heuristic`.

## 4. Schema impact

```cypher
(:LocaleResource {
  project_id, run_id,
  locale: string,             // "en", "ru", "es", "default"
  source: string,             // file path of strings catalogue
  key_count: int,
  surface: string             // "ios" | "android"
})

(:HardcodedString {
  project_id, run_id,
  file, start_line, end_line,
  literal: string,            // the actual string (max 100 chars)
  context: string,            // "swiftui_text" | "uikit_label" | "compose_text" | "view_xml" | "other"
  severity: string,           // "high" if visible UI; "medium" if logging; "low" if debug
  message: string
})

(:A11yMissing {
  project_id, run_id,
  file, start_line, end_line,
  control_kind: string,       // "button" | "textfield" | "image" | "icon" | "tappable_view"
  surface: string,            // "ios" | "android"
  severity: string,           // "high" for buttons/icons; "medium" for tap-views; "low" for decorative
  message: string
})
```

Indices:
- `INDEX :LocaleResource(project_id, locale)`.
- `INDEX :HardcodedString(project_id, severity)`.
- `INDEX :A11yMissing(project_id, severity)`.

## 5. `audit_contract()`

```python
def audit_contract(self) -> AuditContract:
    return AuditContract(
        query="""
            MATCH (lr:LocaleResource {project: $project})
            WITH collect(lr) AS locales
            OPTIONAL MATCH (h:HardcodedString {project: $project})
            WITH locales, collect(h) AS hardcoded
            OPTIONAL MATCH (a:A11yMissing {project: $project})
            RETURN locales, hardcoded, collect(a) AS a11y_missing
        """,
        response_model=LocAuditList,
        template_path=Path("audit/templates/localization_accessibility.md"),
        severity_mapper=lambda x: x.severity,  # already encoded
    )
```

Audit report renders: locale coverage matrix + top hard-coded
strings + top a11y misses.

## 6. Initial rule set (≤6 rules)

1. **`loc.locale_coverage`** — count `LocaleResource` rows per
   project; compute coverage % vs base locale's key count.
2. **`loc.hardcoded_swiftui`** — `Text("...")` / `Label("...", ...)`
   with literal string in non-test SwiftUI code.
3. **`loc.hardcoded_compose`** — `Text("...")` Compose call with
   literal string (not via `stringResource(R.string.X)`).
4. **`loc.hardcoded_uikit`** — UIKit `*.text = "..."` with literal
   user-facing string.
5. **`a11y.missing_label_swiftui`** — `Image`, `Button`, `Icon`
   without `.accessibilityLabel(...)` (Image-only) or no
   accessible text (Button without text).
6. **`a11y.missing_compose`** — `Image`, clickable `Modifier`, custom
   touch targets without `Modifier.semantics { contentDescription }`.

## 7. Decision points

| ID | Question | Default | Impact |
|----|----------|---------|--------|
| **LA-D1** | Run on iOS only / Android only / both | both | reduces ROI if only one |
| **LA-D2** | Hard-coded threshold for severity=high | string visible in UI control directly | broader = more findings, higher false-positive |
| **LA-D3** | A11y check applies to test code? | no — skip test files | yes = inflated finding count |
| **LA-D4** | Allowlist legitimate hard-coded strings (e.g., trademark "Bitcoin") | yes — allowlist file `<project>/.gimle/loc-allowlist.txt` | no allowlist = noise |
| **LA-D5** | Locale base reference | `"en"` for both iOS+Android | other = configurable per-project |

## 7a. Decision resolutions (CTO Phase 1.1, 2026-05-12)

| ID | Resolution | Rationale |
|----|-----------|-----------|
| **LA-D1** | **iOS: full. Android: Slice 2-lite (Manifest + strings.xml only).** | UW-Android is Compose-first (1418 @Composable, 9 layouts, 0 ViewBinding per 2026-04-30 inventory). Full Android a11y scan is dead scope — 80% of detection rules target View XML that doesn't exist. Android side limited to `strings.xml` locale-resource parsing + hard-coded-in-Compose detection. Defer Android layout/View a11y scan as out-of-scope. |
| **LA-D2** | Default: string visible in UI control directly → severity=high. | Spec default accepted. |
| **LA-D3** | No — skip test files. | Spec default accepted. |
| **LA-D4** | Yes — allowlist at `<project>/.gimle/loc-allowlist.txt`. | Spec default accepted. |
| **LA-D5** | `"en"` for both platforms. | Spec default accepted. |

**Slice 2-lite narrowing (Android side):** ViewBinding/layout XML scan, `android:contentDescription` on View XML, and `android:labelFor` are **deferred** — no implementation in this slice. Rule `a11y.missing_compose` remains in scope (Compose semantics detection). Rule 6 from spec §6 is narrowed to Compose-only (no View XML `contentDescription` check).

## 8. Test plan

- **Unit per parser**: synthetic xcstrings / strings.xml /
  Compose / SwiftUI fixtures → assert `:LocaleResource` rows.
- **Unit per rule**: per-rule fixtures (good case + bad case) →
  assert `:HardcodedString` / `:A11yMissing` rows.
- **Integration**: testcontainers Neo4j + multi-locale fixture →
  assert coverage matrix + finding counts.
- **Smoke**: real `unstoppable-wallet-android` → operator review
  top-5 hard-coded strings for plausibility (≤2/5 false positives).

## 9. Risks

- **R1**: false positives from non-user-facing strings (debug
  logs, IDs, accessibility identifiers). Mitigation: per-rule
  context-aware classification; allowlist file (LA-D4).
- **R2**: SwiftUI declarations that are technically literal but
  i18n'd downstream (e.g., `Text(verbatim:)` for proper nouns).
  Mitigation: `Text(verbatim:)` recognised as deliberate;
  do not flag.
- **R3**: Compose functions with implicit i18n via custom DSL.
  Mitigation: rule allows opt-out via per-project config file.
- **R4**: locale-resource churn — strings added/removed per
  release. Mitigation: extractor reports point-in-time snapshot;
  drift over time tracked by `git_history` cross-reference (post-v1).

## 10. Out of scope

- Translation quality / pseudo-localisation testing.
- Dynamic content i18n (server strings, push notifications).
- Live VoiceOver / TalkBack run.
- Right-to-left layout validation.

## 11. Cross-references

- Original research: `docs/research/extractor-library/report.md` §2.2
  row #9 + `Localization_Accessibility_Extractor.json`.
- Roadmap: `docs/roadmap-archive.md` §2.2 #9.
- E6 prereq: `2026-05-07-cx-team-hire-blockchain-security-pyorch_*.md`.
- Audit-V1 integration: feeds §3 Quality of report; potential
  future §11 "Internationalisation & Accessibility" sub-section.
- Companion: `2026-05-07-localization-accessibility-extractor_plan.md`.
