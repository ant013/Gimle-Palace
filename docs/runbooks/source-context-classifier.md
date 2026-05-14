# Source-Context Classifier Runbook

**Module:** `palace_mcp.extractors.foundation.source_context`
**Introduced:** GIM-283-4 (Slice 3)

## Overview

The source-context classifier assigns one of four labels to each audit finding based on the file path where the finding was detected:

| Context | Meaning |
|---------|---------|
| `library` | Production library code — counts toward executive-summary severity |
| `example` | Example/sample/demo applications — excluded from HIGH count in executive summary |
| `test` | Test files — excluded from HIGH count in executive summary |
| `other` | Scripts, docs, generated code, etc. |

## Classification rules (priority order)

1. **Overrides YAML** (highest priority) — per-project override via `.gimle/source-context-overrides.yaml`
2. **example** — directory component contains Example / Examples / Sample / Samples / Demo / Demos (case-insensitive, including compound names like `ios-example`, `IOS_EXAMPLE`, `iOS Example`)
3. **test** — directory component is Tests / Test / spec, OR file ends with `Tests.swift` / `_test.py` / `Test.kt`
4. **library** — directory component is Sources / src / lib / libs
5. **other** — no rule matched

All matching is case-insensitive.

## Per-project overrides

Create `.gimle/source-context-overrides.yaml` in the repo root to override the default classification for specific path patterns:

```yaml
# Override vendor directories to "other" even if inside Sources/
"**/Vendor/**": "other"
# Override generated code
"**/Generated/**": "other"
# Override a specific module to example
"Sources/ExampleKit/**": "example"
```

Valid context values: `library`, `example`, `test`, `other`.
Invalid values are silently ignored. The file may be absent — that's fine.

## Python API

```python
from palace_mcp.extractors.foundation.source_context import classify, load_overrides

overrides = load_overrides(repo_root="/path/to/repo")  # None if no override file
ctx = classify("Sources/TronKit/Signer/Signer.swift", overrides=overrides)
# → "library"
```

## Effect on audit reports

- **Executive summary HIGH count**: library findings only. Example and test findings are excluded.
- **Distribution line** (in §Executive Summary header): `Findings by source: library=N example=N test=N other=N`
- **`library_findings_empty` warning**: emitted when total > 10 findings but library count = 0. Indicates the classifier may not recognize the project's source layout. Add overrides as needed.
- **Per-section tables**: include a `Source` column showing the context for each finding row.
