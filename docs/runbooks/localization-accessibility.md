# Runbook: localization_accessibility extractor (GIM-275, Roadmap #9)

## Overview

Scans iOS and Android source for locale coverage gaps and accessibility
defects. Writes three node kinds to Neo4j:

| Node | Description |
|------|-------------|
| `:LocaleResource` | Per-locale key count + coverage % relative to English base |
| `:HardcodedString` | Literal strings found by semgrep (SwiftUI/UIKit/Compose rules) |
| `:A11yMissing` | Missing accessibility labels / semantics found by semgrep |

No external `.scip` file or env vars required. Reads the mounted repo
directory directly.

## Prerequisites

- Repo mounted in `docker-compose.yml` at `/repos/<slug>`.
- `semgrep` CLI available in the `palace-mcp` container (included in
  the Python environment via `pyproject.toml`).

## Running the extractor

```
palace.ingest.run_extractor(name="localization_accessibility", project="uw-ios")
```

Expected response on success:

```json
{
  "ok": true,
  "extractor": "localization_accessibility",
  "project": "uw-ios",
  "nodes_written": <N>,
  "edges_written": 0
}
```

## Querying results

### Locale coverage

```cypher
MATCH (lr:LocaleResource {project_id: "project/uw-ios"})
RETURN lr.locale, lr.key_count, lr.coverage_pct, lr.surface, lr.source
ORDER BY lr.coverage_pct DESC
```

### Top hardcoded strings

```cypher
MATCH (h:HardcodedString {project_id: "project/uw-ios"})
RETURN h.severity, h.context, h.file, h.start_line, h.message
ORDER BY CASE h.severity
  WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
  h.file, h.start_line
LIMIT 50
```

### Accessibility gaps

```cypher
MATCH (a:A11yMissing {project_id: "project/uw-ios"})
RETURN a.severity, a.surface, a.control_kind, a.file, a.start_line, a.message
ORDER BY a.file, a.start_line
LIMIT 50
```

## Allowlist

Strings in `.gimle/loc-allowlist.txt` at the repo root are excluded from
`:HardcodedString` findings. Useful for product names, crypto symbols, etc.

```
# .gimle/loc-allowlist.txt
Bitcoin
Ethereum
Satoshi
```

One entry per line; blank lines and leading/trailing whitespace ignored.

## Semgrep rules

Five rules live in
`services/palace-mcp/src/palace_mcp/extractors/localization_accessibility/semgrep_rules/`:

| Rule | Language | Detects |
|------|----------|---------|
| `loc_hardcoded_swiftui.yaml` | Swift | `Text("literal")` without `Text(verbatim:)` |
| `loc_hardcoded_uikit.yaml` | Swift | `.text = "literal"` or `setTitle("literal",` |
| `loc_hardcoded_compose.yaml` | Kotlin | `Text("literal")` in Compose |
| `a11y_missing_label_swiftui.yaml` | Swift | `Image(…)` without `.accessibilityLabel` or `.accessibilityHidden(true)` |
| `a11y_missing_compose.yaml` | Kotlin | `Modifier.clickable(…)` without `.semantics(…)` |

Rules use `pattern-regex:` (Swift) or `patterns:` (Kotlin AST) to avoid
requiring a paid semgrep license.

## File discovery

The extractor walks the repo for:

- `**/*.xcstrings` — Xcode 15+ string catalog (JSON)
- `**/Localizable.strings` in `.lproj` directories
- `**/strings.xml` under `res/values*` directories

Semgrep scans all `.swift`, `.kt`, `.kts` files not in test directories
(`Tests/`, `Test/`, `UnitTests/`, `UITests/`, `test/`, `androidTest/`).

## Limitations

- **No `.strings` plurals support** — `NSLocalizedPluralString` is not
  counted in `Localizable.strings` (uses same `=` syntax, counted as
  regular keys).
- **Android View XML not scanned** — layout XML hardcoded strings are
  out of scope for v1.
- **Kotlin a11y rule scope** — only `Modifier.clickable` without
  `semantics` is detected; `Box`, `Row`, `Column` with `clickable`
  modifier but no `semantics` are not covered.
- **Large repos** — file enumeration collects all Swift/Kotlin files
  before invoking semgrep. On repos with >5 000 such files the command
  line could become very long; the extractor logs a warning and continues
  (followup: batching).
- **SwiftUI a11y multi-line modifier chains** — the `a11y.missing_label_swiftui`
  rule uses a single-line negative lookahead (`Image(...) (?!.accessibilityLabel)`).
  Idiomatic SwiftUI places modifiers on the next line, so a correctly-labelled
  `Image` will be falsely reported as missing a label. Expected high false-positive
  rate on real-world SwiftUI code. Followup: multi-line regex or context-line scan.
- **Locale base source ambiguity** — when multiple English source files exist
  (e.g. both `.xcstrings` and `Localizable.strings`), `compute_coverage` uses
  the first encountered `"en"` resource as the base key count. Coverage percentages
  may differ slightly depending on which file is found first during traversal.

## Troubleshooting

### `extractor_runtime_error` — semgrep not found

Ensure `semgrep` is installed in the container's Python environment:

```bash
docker exec palace-mcp uv run semgrep --version
```

If missing, add it to `pyproject.toml` dependencies and rebuild.

### `nodes_written = 0` for semgrep findings

1. Check that the repo has `.swift` or `.kt` source files:
   ```bash
   find /repos/<slug> -name "*.swift" -o -name "*.kt" | head -10
   ```
2. Run semgrep manually to verify rules match:
   ```bash
   docker exec palace-mcp bash -c \
     "semgrep --config /app/palace_mcp/extractors/localization_accessibility/semgrep_rules \
              --json --quiet /repos/<slug>/Sources/SomeView.swift"
   ```

### `nodes_written = 0` for locale resources

Check that the expected file types exist:
```bash
find /repos/<slug> -name "*.xcstrings" -o -name "Localizable.strings" -o \
  \( -name "strings.xml" -path "*/res/values*" \) | head -10
```
