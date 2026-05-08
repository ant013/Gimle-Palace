# Testability / DI Pattern Extractor (#8) — спецификация

**Дата документа:** 2026-05-08
**Статус:** Formalised for GIM-242 · rev1 CTO re-scope to Python heuristic v1
**Исходный материал:** generic spec из PR #112 (`docs(audit-v1): rev1-rev4 plan + 8 slice spec+plan pairs`)
**Формализация:** CXCTO
**Команда:** Codex
**Slice ID:** Phase 2 §2.2 #8 Testability/DI Pattern Extractor
**Issue:** GIM-242
**Companion plan:** `docs/superpowers/plans/2026-05-08-GIM-242-testability-di-pattern-extractor.md`
**Branch:** `feature/GIM-242-testability-di-pattern-extractor`
**Blockers:** none

## 0. Phase 1.1 discovery evidence

- `git fetch origin --prune` выполнен перед git discovery.
- `git log --all --grep="testability|DI Pattern|dependency-injection|dependency injection" --oneline --regexp-ignore-case`
  нашел только generic docs commits `0ae3b5c` / `6d110c0` из roadmap/spec пакетирования, не реализацию extractor #8.
- `gh pr list --state all --search "testability DI Pattern extractor"` нашел только merged PR #112 с generic docs.
- По Paperclip API найден текущий активный GIM-242 и уже закрытый predecessor GIM-238; активного duplicate issue для #8 нет.
- `rg` по `docs/` подтвердил наличие generic файлов без `GIM-242`, которые эта ревизия формализует.
- Serena discovery: `find_symbol("Testability")` в `services/palace-mcp/src` вернул пустой результат; `find_symbol("Extractor")` показывает существующие extractor classes, включая `CodingConventionExtractor`, но не `TestabilityDiExtractor`.
- Codebase-memory по indexed project `Users-Shared-Ios-Gimle-Palace` не показал существующий `testability_di` extractor; основной поиск вернулся к registry/audit symbols.
- Проверка `docs/research/*spike*` не нашла live-verified spikes для Konsist, Harmonize, detekt, semgrep или SwiftSyntax. Поэтому rev1 не требует этих runtime toolchains.

## 1. Цель

Добавить extractor `testability_di`, который выявляет project-specific dependency-injection и test-double patterns в Swift и Kotlin кодовых базах. Результат нужен audit agents, чтобы отвечать:

- где код использует constructor/protocol/interface injection;
- где проект привязан к DI framework или service locator;
- какие mocking/test-double подходы используются в test targets;
- какие production sites трудно тестировать из-за hard-coded collaborators, clock/network/filesystem access или singleton access.

Extractor закрывает target problem **#11 (testability / DI pattern coverage)** из research inventory.

## 2. Scope

### In scope

- Swift + Kotlin source scanning без внешних AST/toolchain runtime dependencies.
- Per-module DI style classification:
  - `init_injection`
  - `property_injection`
  - `factory`
  - `framework_bound`
  - `service_locator`
- DI framework signal detection by source text/import/annotation patterns:
  - Kotlin: Hilt, Dagger, Koin
  - Swift: Resolver, Swinject, Factory, Needle
- Test-double detection:
  - Kotlin: MockK, Mockito, hand-rolled fake/stub/spy/mock classes
  - Swift: Cuckoo-style names/imports, hand-rolled fake/stub/spy/mock classes, XCTest manual doubles
- Untestable-site detection:
  - hard-coded singleton/service locator access in non-test code;
  - direct clock access without seam;
  - direct session/network/filesystem/user-defaults access in business logic.
- Audit contract and template for audit-v1 report section.
- Runbook for operator smoke on real repos.

### Out of scope

- Runtime integration with Konsist, Harmonize, detekt, semgrep or SwiftSyntax before live-verified spikes exist.
- Coverage measurement (#28).
- Test smell/flaky-test detection (#38).
- Mutation testing.
- Auto-fix/refactor suggestions.
- Changing semantics of existing graph fields. This slice adds new labels/properties only.

## 3. CTO scope decision for rev1

Rev1 deliberately follows GIM-238's re-scope pattern: ship a deterministic Python heuristic/file scanner first, defer external AST/toolchain collectors until the project has live-verified spikes and provisioned executables.

Reasoning:

- Project rule requires live verification for spec lines that depend on external library APIs.
- Current research source ranks #8 as `heuristic`, so a conservative source scanner is acceptable for v1.
- The downstream value comes from stable audit signals and graph schema first; collector precision can improve later without changing audit contract shape.

Future hardening may add SwiftSyntax/Konsist/detekt/semgrep collectors behind the same model only after a fresh spike is checked into `docs/research/`.

## 4. Schema impact

New nodes:

```cypher
(:DiPattern {
  project_id: string,
  module: string,
  style: string,          // init_injection | property_injection | factory | framework_bound | service_locator
  framework: string|null, // hilt | dagger | koin | resolver | swinject | factory | needle | null
  language: string,       // swift | kotlin
  sample_count: int,
  outliers: int,
  confidence: string,     // heuristic in rev1
  run_id: string
})

(:TestDouble {
  project_id: string,
  module: string,
  language: string,       // swift | kotlin
  kind: string,           // mockk | mockito | cuckoo | spy | stub | fake | mock | hand_rolled
  target_symbol: string|null,
  test_file: string,
  run_id: string
})

(:UntestableSite {
  project_id: string,
  module: string,
  language: string,       // swift | kotlin
  file: string,
  start_line: int,
  end_line: int,
  category: string,       // service_locator | direct_clock | direct_session | direct_filesystem | direct_preferences
  symbol_referenced: string,
  severity: string,       // low | medium | high
  message: string,
  run_id: string
})
```

Indexes/constraints requested for implementation:

- `INDEX :DiPattern(project_id, module, style)`
- `INDEX :TestDouble(project_id, module, kind)`
- `INDEX :UntestableSite(project_id, severity)`

Writer requirements:

- Use `ctx.group_id` as `project_id`, matching existing extractor nodes.
- Use current runner `ctx.run_id`; when linking or updating run extras, match existing runner-created `:IngestRun` by `{id: $run_id}`.
- Delete/rewrite only this extractor's rows for the same `project_id` during a run; do not touch existing labels from other extractors.

## 5. Audit contract

`TestabilityDiExtractor.audit_contract()` must use the current internal contract shape from `palace_mcp.audit.contracts.AuditContract`:

- `extractor_name="testability_di"`
- `template_name="testability_di.md"`
- `query` receives `$project`
- `severity_column` points to a returned severity field
- optional `severity_mapper` may reuse `Severity` parsing if the query returns canonical severity strings

Expected query shape:

```cypher
MATCH (di:DiPattern {project_id: $project})
OPTIONAL MATCH (td:TestDouble {project_id: $project, module: di.module})
OPTIONAL MATCH (us:UntestableSite {project_id: $project, module: di.module})
WITH di,
     collect(DISTINCT td {
       .kind, .language, .target_symbol, .test_file
     }) AS test_doubles,
     collect(DISTINCT us {
       .file, .start_line, .end_line, .category,
       .symbol_referenced, .severity, .message
     }) AS untestable_sites
RETURN di.module AS module,
       di.language AS language,
       di.style AS style,
       di.framework AS framework,
       di.sample_count AS sample_count,
       di.outliers AS outliers,
       di.confidence AS confidence,
       test_doubles AS test_doubles,
       untestable_sites AS untestable_sites,
       CASE
         WHEN any(site IN untestable_sites WHERE site.severity = "high") THEN "high"
         WHEN di.style = "service_locator" THEN "high"
         WHEN size(untestable_sites) > 0 OR di.outliers > 0 THEN "medium"
         ELSE "low"
       END AS max_severity
ORDER BY max_severity DESC, di.module, di.style
LIMIT 100
```

The implementation may refactor the Cypher for Neo4j syntax correctness, but the returned columns and severity semantics are acceptance criteria.

## 6. Initial rule set

Keep rev1 to seven rules:

1. `di.init_injection` — constructor/init parameters that accept collaborators or abstractions.
2. `di.property_injection` — `@Inject lateinit var`, resolver/property wrappers, or analogous property assignment seams.
3. `di.framework_bound` — Hilt/Dagger/Koin/Resolver/Swinject/Factory/Needle signals.
4. `di.service_locator` — `.shared`, `.default`, `getInstance()`, container/service-locator access outside DI composition code.
5. `mock.framework_usage` — MockK/Mockito/Cuckoo imports and factory calls in test files.
6. `mock.hand_rolled_double` — `Fake`, `Stub`, `Spy`, `Mock` classes or protocols/interfaces under test paths.
7. `untestable.direct_resource` — direct clock/session/preferences/filesystem access in non-test code without an obvious abstraction seam.

Every rule must have at least one Swift fixture and one Kotlin fixture unless a language-specific exception is explicitly documented in the test name.

## 7. Resolved decision points

| ID | Decision |
|---|---|
| TD-D1 | Run both Swift and Kotlin in rev1. |
| TD-D2 | `service_locator` severity defaults to `high`; direct resource access defaults to `medium` unless in critical path, where it may be `high`. |
| TD-D3 | Keep `:TestDouble` nodes in graph, not only aggregate counts. |
| TD-D4 | Scan whole project; severity may be higher for wallet/crypto/business-logic paths. |
| TD-D5 | Start permissive with allowlists for DI composition/test files; QA must report false-positive examples from smoke. |

## 8. Test and QA expectations

Implementation tests:

- scaffolding and registry unit tests;
- per-rule Swift/Kotlin unit tests;
- writer unit tests for Cypher parameters and `project_id/run_id` propagation;
- integration test that writes `:DiPattern`, `:TestDouble`, and `:UntestableSite` rows against Neo4j/testcontainers or the repo's current integration harness;
- audit contract/template render tests.

QA evidence:

- `uv run ruff check`
- `uv run mypy src/`
- `uv run pytest`
- `docker compose build`
- live `docker compose --profile full up` healthchecks
- real MCP call invoking `palace.ingest.run_extractor` for `testability_di`
- Cypher evidence:
  - `MATCH (d:DiPattern {project_id: $project}) RETURN d.style, count(*)`
  - `MATCH (t:TestDouble {project_id: $project}) RETURN t.kind, count(*)`
  - `MATCH (u:UntestableSite {project_id: $project}) RETURN u.category, u.severity, count(*)`

## 9. Risks

- R1: Heuristic scanner misses custom DI helpers. Mitigation: emit conservative `confidence="heuristic"` and collect smoke false negatives for future AST pass.
- R2: Service-locator patterns can be legitimate in composition roots. Mitigation: allowlist `DI`, `Module`, `Assembly`, `Container`, `AppDelegate`, test paths and equivalent Kotlin modules.
- R3: Hand-rolled fake/stub naming can overcount helpers. Mitigation: only count under test paths or files importing XCTest/JUnit-like test symbols.
- R4: Large repo scanning cost. Mitigation: stream files, skip ignored/build directories, cap samples per module where needed.

## 10. Cross-references

- Research source: `docs/research/extractor-library/outline.yaml` item #8.
- Research report: `docs/research/extractor-library/report.md` row #8.
- Generic source docs: PR #112, commits `0ae3b5c` / `6d110c0`.
- Predecessor: GIM-238 / PR #118, squash merge `1a4ae620619ba01422fd4a381de772b592b9af21`.
- Related scope split: #28 coverage gaps, #38 test smells, #23 test harness.
