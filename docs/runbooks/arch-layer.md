# Runbook: arch_layer extractor (GIM-243)

## Overview

The `arch_layer` extractor builds a module dependency graph (DAG) for SwiftPM
and Gradle projects, evaluates layer rules, and writes findings to Neo4j.
It participates in the Audit-V1 report pipeline via `audit_contract()`.

**Extractor name:** `arch_layer`
**Neo4j node types:** `:Module`, `:Layer`, `:ArchRule`, `:ArchViolation`
**Edge types:** `:IN_LAYER`, `:MODULE_DEPENDS_ON`, `:VIOLATES_RULE`

## Prerequisites

No external tools required. The extractor reads manifests directly:

- `Package.swift` (SwiftPM)
- `settings.gradle.kts` + per-module `build.gradle.kts` (Gradle/Kotlin DSL)

`dependency_surface` is **optional** context. `arch_layer` does not require it.
`symbol_index_swift` is **optional**; import evidence uses a lightweight text
scanner and is not dependent on SCIP indexes.

## Rule file authoring

The extractor looks for a rule file in this order (first match wins):

1. `.palace/architecture-rules.yaml` (project-level override)
2. `docs/architecture-rules.yaml` (repo default)

If no file is found, the extractor writes modules and edges but emits no
violations. The audit report will say `No architecture rules declared`.

### Minimal rule file

```yaml
layers:
  - name: core
    module_globs: ["*Core*", "Core", "domain/*"]
  - name: ui
    module_globs: ["*UI*", "UI", "presentation/*"]

rules:
  - id: core_no_ui
    kind: forbidden_dependency
    severity: high
    from_layers: ["core"]
    to_layers: ["ui"]
    message: "Core layer must not depend on UI layer"

  - id: no_cycles
    kind: no_circular_module_deps
    severity: high
```

### Supported rule kinds

| kind | description | default severity |
|------|-------------|------------------|
| `forbidden_dependency` | Manifest edge crosses layer boundary | high |
| `forbidden_module_glob_dependency` | Manifest edge matches from_globs → to_globs | high |
| `no_circular_module_deps` | SCC with size > 1 | high |
| `manifest_dep_actually_used` | Manifest dep with no import evidence | low |
| `ast_dep_not_declared` | Import evidence without manifest edge | high |

Unknown rule kinds produce a loader warning and are skipped (not a hard failure).

## Running the extractor

```
palace.ingest.run_extractor(name="arch_layer", project="<slug>")
```

Recommended ingest order when you also want external dependency context:

```
palace.ingest.run_extractor(name="dependency_surface", project="<slug>")
palace.ingest.run_extractor(name="arch_layer", project="<slug>")
```

But `dependency_surface` is not a prerequisite.

## Smoke test

```cypher
MATCH (m:Module {project_id: "project/tronkit-swift"})
RETURN m.slug, m.kind, m.manifest_path
LIMIT 20
```

Expected: count > 1.

```cypher
MATCH (v:ArchViolation {project_id: "project/tronkit-swift"})
RETURN count(v) AS violation_count
```

Expected: integer (may be 0 if no rule file or no violations).

## Idempotency

Re-running the extractor deletes all `Module`, `Layer`, `ArchRule`, and
`ArchViolation` nodes for the project and rewrites them from scratch. This
ensures that removed modules or closed violations are cleaned up.

## Troubleshooting

| Symptom | Likely cause | Action |
|---------|-------------|--------|
| `no modules found` warning, 0 writes | No Package.swift or settings.gradle.kts | Check repo mount and file existence |
| `invalid YAML in rule file` error | Syntax error in rule file | Fix the YAML; extractor aborts on bad rule files |
| Module count = 1 | Parser found only one target | Check Package.swift for target declarations |
| Violation count = 0 but rules exist | No rule matches the current DAG | Verify layer globs match actual module names |
| Parser warnings about external deps | External deps in dependencies: block | Expected; external deps are skipped (owned by dependency_surface) |
| Import scanner warnings: "ambiguous" | Multiple modules match an import prefix | Rename modules to have distinct prefixes |

## QA smoke checklist (per QAEngineer)

1. Run extractor on `tronkit-swift`:
   ```
   palace.ingest.run_extractor(name="arch_layer", project="tronkit-swift")
   ```
2. Verify `:Module` count > 1.
3. Verify report renders either grouped `ArchViolation` rows or explicit
   clean/no-rules text.
4. Restore production checkout.
