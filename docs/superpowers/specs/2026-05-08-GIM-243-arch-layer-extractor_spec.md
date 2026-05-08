# Audit-V1 S2.2 — Architecture Layer extractor — Specification

**Дата документа:** 2026-05-08
**Статус:** Draft for plan-first review
**Issue:** GIM-243
**Ветка:** `feature/GIM-243-arch-layer-extractor`
**Companion plan:** `docs/superpowers/plans/2026-05-08-GIM-243-arch-layer-extractor.md`
**Источник:** `docs/superpowers/sprints/B-audit-extractors.md` §S2.2, rev3
**Предшественник:** GIM-239 / S2.1 `crypto_domain_model`, merged to `develop` at `700a17a65e1187425da162981a50adafe03a5c28`

---

## 1. CTO formalisation notes

S2.2 из sprint-файла был проверен против текущего `origin/develop` после
слияния GIM-239. Найденные расхождения, которые эта спецификация исправляет:

1. `AuditContract` в коде уже не совпадает с примером в sprint-файле. Текущая
   форма: `extractor_name`, `template_name`, `query`, `severity_column`,
   `max_findings`, `severity_mapper`.
2. `dependency_surface` уже использует `(:Project)-[:DEPENDS_ON]->(:ExternalDependency)`.
   S2.2 не должен менять эту семантику и не должен создавать
   `(:Module)-[:DEPENDS_ON]->(:Module)`.
3. Упоминания `modules-graph-assert`, ArchUnit-compatible syntax и tree-sitter
   в sprint-файле не подкреплены свежим spike под `docs/research/`. Для v1
   S2.2 не вводит новые внешние tooling APIs. Если implementer хочет добавить
   такой dependency, сначала нужен отдельный live-verified spike.
4. GIM-239 уже добавил `crypto_domain_model` и audit template. S2.2 должен
   следовать этому текущему extractor/audit-contract паттерну, а не старому
   `response_model/template_path` образцу.

## 2. Goal

Добавить extractor `arch_layer`, который строит module DAG для SwiftPM и
Gradle-проектов, применяет layer rules, пишет архитектурные нарушения в Neo4j
и подключается к Audit-V1 report через `audit_contract()`.

Definition of Done:

1. `arch_layer` зарегистрирован в `EXTRACTORS`.
2. Extractor пишет `:Module`, `:Layer`, `:ArchRule`, `:ArchViolation` и
   module-level dependency edges без изменения существующего
   `dependency_surface` graph contract.
3. `ArchLayerExtractor.audit_contract()` возвращает текущий `AuditContract`.
4. Шаблон `arch_layer.md` рендерит module DAG summary, grouped violations и
   clean/no-rules состояния.
5. Runbook `docs/runbooks/arch-layer.md` описывает подготовку rule file,
   запуск, smoke и troubleshooting.
6. Unit/integration tests покрывают SwiftPM, Gradle, rule loader, writer,
   audit contract и registry.
7. QA smoke на `tronkit-swift` доказывает, что extractor запускается на
   реальном SwiftPM repo и audit report показывает либо нарушения, либо
   явное clean/no-rules состояние.

## 3. Non-goals

- Не внедрять `modules-graph-assert`, ArchUnit, tree-sitter или другие новые
  external tooling dependencies без свежего spike.
- Не менять `dependency_surface` и его `:DEPENDS_ON` semantics.
- Не делать bundle-level cross-Kit архитектурные правила. V1 работает в
  пределах одного `project_slug`; bundle rules deferred.
- Не требовать, чтобы у проекта был rule file. Если rule file отсутствует,
  extractor пишет module DAG и report явно говорит `no architecture rules declared`.

## 4. Current develop contracts

### 4.1 Extractor registry

Extractor регистрируется import-time в
`services/palace-mcp/src/palace_mcp/extractors/registry.py`:

```python
EXTRACTORS: dict[str, BaseExtractor] = {
    ...
    "crypto_domain_model": CryptoDomainModelExtractor(),
}
```

S2.2 добавляет `"arch_layer": ArchLayerExtractor()`.

### 4.2 AuditContract

`arch_layer` must return:

```python
AuditContract(
    extractor_name="arch_layer",
    template_name="arch_layer.md",
    query=_QUERY,
    severity_column="severity",
    severity_mapper=_arch_severity,
)
```

`_QUERY` receives both `$project` and `$project_id` from the fetcher. This
extractor must query `project_id: $project_id` because GIM-239 writes domain
findings with `ctx.group_id`, i.e. `project/<slug>`.

### 4.3 Existing dependency graph

`dependency_surface` owns:

```cypher
(:Project {slug})-[:DEPENDS_ON {scope, declared_in, declared_version_constraint}]->(:ExternalDependency {purl})
```

S2.2 introduces a separate edge type:

```cypher
(:Module)-[:MODULE_DEPENDS_ON {scope, declared_in, evidence_kind, run_id}]->(:Module)
```

This avoids overloading `:DEPENDS_ON` with a different source and target label.

## 5. Inputs

Extractor reads:

- `ctx.repo_path`, `ctx.project_slug`, `ctx.group_id`, `ctx.run_id`.
- `Package.swift` files for SwiftPM projects.
- `settings.gradle.kts`, `build.gradle.kts` and nested module build files for
  Gradle/Kotlin projects.
- Swift/Kotlin source imports for rules that compare actual imports to
  manifest declarations.
- Architecture rule file, first match wins:
  1. `.palace/architecture-rules.yaml`
  2. `docs/architecture-rules.yaml`

If no manifests are found, extractor returns zero writes and logs a warning.
If manifests exist but no rule file exists, it still writes modules and
dependencies, then emits no violations.

## 6. Rule file contract

Minimal YAML shape:

```yaml
layers:
  - name: core
    module_globs: ["*-core", "Core*", "domain/*"]
  - name: ui
    module_globs: ["*-ui", "UI*", "presentation/*"]

rules:
  - id: wallet_core_no_ui_import
    kind: forbidden_dependency
    severity: high
    from_layers: ["core"]
    to_layers: ["ui"]
    message: "Core module must not depend on UI module"
```

V1 supports these rule kinds:

- `forbidden_dependency`: actual module edge from `from_layers` to `to_layers`
  creates `ArchViolation`.
- `forbidden_module_glob_dependency`: actual edge where source/destination
  module names match configured globs creates `ArchViolation`.
- `no_circular_module_deps`: strongly connected component with size > 1 creates
  one `ArchViolation` per cycle summary.
- `manifest_dep_actually_used`: manifest dependency with no import evidence is
  `low` or configured severity.
- `ast_dep_not_declared`: import evidence without manifest edge is `high` or
  configured severity.

Unknown rule kinds are warnings, not hard failures. Invalid YAML is a hard
extractor configuration error because the operator must fix the rule file.

## 7. Graph writes

Nodes:

```cypher
(:Module {
  project_id, slug, name, kind, manifest_path, source_root, run_id
})

(:Layer {
  project_id, name, rule_source, run_id
})

(:ArchRule {
  project_id, rule_id, kind, severity, rule_source, run_id
})

(:ArchViolation {
  project_id, kind, severity, src_module, dst_module,
  rule_id, message, evidence, file, start_line, run_id
})
```

Edges:

```cypher
(:Module)-[:IN_LAYER {run_id}]->(:Layer)
(:Module)-[:MODULE_DEPENDS_ON {scope, declared_in, evidence_kind, run_id}]->(:Module)
(:ArchViolation)-[:VIOLATES_RULE]->(:ArchRule)
```

Constraints/indexes:

- Unique `Module(project_id, slug)`.
- Unique `Layer(project_id, name)`.
- Unique `ArchRule(project_id, rule_id)`.
- Unique `ArchViolation(project_id, rule_id, src_module, dst_module, evidence)`.
- Index `ArchViolation(project_id)`.
- Index `ArchViolation(severity)`.

Writers must be idempotent: re-running the same extractor on the same repo must
not duplicate nodes or edges.

## 8. Parsing strategy

### 8.1 SwiftPM

V1 parses enough of `Package.swift` to recover:

- target names;
- target dependency names;
- product target membership when available;
- source paths when explicitly declared.

The parser may use conservative text scanning similar to the existing
`dependency_surface` SwiftPM parser. It must be fixture-backed and must fail
closed: if a dependency cannot be mapped to an internal target, it is ignored
for module-level edges and recorded in parser warnings.

### 8.2 Gradle/Kotlin

V1 parses:

- `settings.gradle.kts` `include(":module")` declarations;
- per-module `build.gradle.kts` `implementation(project(":x"))`,
  `api(project(":x"))`, `compileOnly(project(":x"))`,
  `testImplementation(project(":x"))`.

External Maven dependencies remain owned by `dependency_surface`; S2.2 only
needs intra-project module edges.

### 8.3 Import evidence

V1 uses a lightweight import scanner:

- Swift: `import ModuleName`.
- Kotlin/Java: `import package.name...`.

The scanner maps import names to known module names only when the mapping is
unambiguous. Ambiguous imports are warnings and must not create violations.

## 9. Severity mapping

Default severity:

- `forbidden_dependency`: configured severity, default `high`.
- `forbidden_module_glob_dependency`: configured severity, default `high`.
- `no_circular_module_deps`: default `high`.
- `ast_dep_not_declared`: default `high`.
- `manifest_dep_actually_used`: default `low`.
- parser warnings are not `ArchViolation`; they appear in summary stats.

`_arch_severity` maps unknown values to `informational`, matching
`severity_from_str` fallback behavior.

## 10. File layout

Implementation scope:

- `services/palace-mcp/src/palace_mcp/extractors/arch_layer/`
- `services/palace-mcp/src/palace_mcp/audit/templates/arch_layer.md`
- `services/palace-mcp/src/palace_mcp/extractors/registry.py`
- `services/palace-mcp/tests/extractors/unit/test_arch_layer_*.py`
- `services/palace-mcp/tests/extractors/integration/test_arch_layer_integration.py`
- `services/palace-mcp/tests/extractors/fixtures/arch-layer-mini-project/`
- `docs/runbooks/arch-layer.md`

Out of scope:

- changes to `dependency_surface`;
- changes to `audit/fetcher.py`, unless CodeReviewer confirms a real contract
  mismatch;
- changes to unrelated extractors.

## 11. Required validation

Unit:

- rule loader valid/invalid/no-file cases;
- SwiftPM parser target + dependency extraction;
- Gradle parser module + dependency extraction;
- import scanner declared/undeclared/unused cases;
- rule evaluator for each V1 rule kind;
- severity mapper;
- `audit_contract()` shape.

Integration:

- synthetic fixture writes expected `:Module`, `:Layer`,
  `:MODULE_DEPENDS_ON`, `:ArchViolation` counts;
- idempotent second run writes no duplicates;
- registry includes `arch_layer`;
- audit fetcher can execute `arch_layer` contract query and renderer uses
  `arch_layer.md`.

QA smoke:

- run `dependency_surface` first only if the operator wants external dependency
  context in the report; `arch_layer` itself must not require it;
- run `symbol_index_swift` only if import source coverage is required by the
  selected smoke invariant; `arch_layer` must still parse manifests without it;
- run `arch_layer` on `tronkit-swift`;
- verify `:Module` count > 1;
- verify report renders either grouped `ArchViolation` rows or explicit
  clean/no-rules text with the active rule source.

## 12. Risks

- Swift `Package.swift` is executable Swift, not pure data. V1 parser is
  conservative by design; unsupported constructs produce warnings rather than
  guessed edges.
- Gradle Kotlin DSL can hide module dependencies behind variables. V1 supports
  direct `project(":x")` calls only.
- Import evidence can be noisy. Violations that depend on import evidence must
  include `evidence_kind` and parser warnings in summary stats so QA can inspect
  false positives.
- Reusing `:DEPENDS_ON` would make downstream queries ambiguous. This spec
  forbids that and requires `:MODULE_DEPENDS_ON`.
