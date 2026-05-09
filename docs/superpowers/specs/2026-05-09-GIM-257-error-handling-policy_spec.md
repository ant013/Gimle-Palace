# Audit-V1 S2.3 — Error Handling Policy extractor — Specification

**Дата документа:** 2026-05-09
**Статус:** Draft for plan-first review
**Issue:** GIM-257
**Ветка:** `feature/GIM-257-error-handling-policy`
**Companion plan:** `docs/superpowers/plans/2026-05-09-GIM-257-error-handling-policy.md`
**Источник:** `docs/superpowers/sprints/B-audit-extractors.md` §S2.3, rev3
**Предшественник:** GIM-243 / S2.2 `arch_layer`, merged to `develop` at `42e2894584fecdbc623ab1c8257004b3063a571e`

---

## 1. CXCTO formalisation notes

S2.3 из sprint-файла проверен против текущего `origin/develop` после слияния
GIM-243. Найденные расхождения, которые эта спецификация исправляет:

1. **Sprint tech stack преувеличен.** Sprint §S2.3 перечисляет SwiftSyntax,
   detekt, SourceKit-LSP, ast-grep как tech stack. На `origin/develop` ни один
   из них не является зависимостью palace-mcp. `semgrep>=1.162.0` уже pinned.
   Для v1 S2.3 использует **только semgrep** для Swift (как crypto_domain_model
   GIM-239) — это проверенный, работающий подход. Kotlin/detekt/ast-grep
   deferred до S2.4+ или отдельного spike.

2. **Research JSON entity model слишком амбициозен.** Research doc
   (`results/Error_Handling_Policy_Extractor.json`) описывает `:ErrorPolicy`,
   `:ErrorBoundary`, `:GOVERNS`, `:VIOLATES` nodes с layer-aware policy
   inference. Это полная v2+ vision. V1 фокусируется на конкретных
   антипаттернах ошибок — **`:ErrorFinding`** nodes с semgrep rules — и
   сохраняет sprint smoke surface через **`:CatchSite`** inventory/aggregate
   nodes. Не пытаемся делать `:ErrorPolicy` inference или layer assignment.

3. **AuditContract shape.** Текущий `AuditContract` (contracts.py):
   `extractor_name`, `template_name`, `query`, `severity_column`,
   `max_findings`, `severity_mapper`. Sprint-файл показывает устаревшую форму
   с `response_model` / `template_path`. S2.3 следует текущей форме.

4. **Спринтовый claim "SwiftSyntax visitor"** не подкреплён. SwiftSyntax —
   Swift-only AST library, недоступна внутри Python container. crypto_domain_model
   уже доказал, что semgrep + YAML rules покрывают Swift AST patterns
   достаточно для v1 аудита. S2.3 повторяет этот подход.

5. **No external tooling gate** — как в arch_layer spec §11, implementer
   не добавляет ast-grep, detekt, SwiftSyntax, tree-sitter или другие новые
   dependencies без свежего spike.

## 2. Goal

Добавить extractor `error_handling_policy`, который сканирует Swift исходники
semgrep custom rules для обнаружения антипаттернов обработки ошибок (empty catch,
swallowed errors, try? в критических paths), пишет `:CatchSite` и
`:ErrorFinding` nodes в Neo4j и подключается к Audit-V1 report через
`audit_contract()`.

Definition of Done:

1. `error_handling_policy` зарегистрирован в `EXTRACTORS`.
2. Extractor пишет `:CatchSite` inventory/aggregate nodes и
   `:ErrorFinding` severity-graded findings.
3. `ErrorHandlingPolicyExtractor.audit_contract()` возвращает текущий
   `AuditContract`.
4. Шаблон `error_handling_policy.md` рендерит findings grouped by severity
   + per-module aggregate summary + clean state.
5. Runbook `docs/runbooks/error-handling-policy.md` описывает запуск,
   smoke и troubleshooting.
6. Unit/integration tests покрывают rule loading, semgrep invocation,
   dedup, Neo4j writer, audit contract и registry.
7. QA smoke на `tronkit-swift` доказывает `:CatchSite` count > 0 и
   ≥1 finding (или explicit "no critical-path swallowed catches" с file count).

## 3. Non-goals

- Не внедрять SwiftSyntax, ast-grep, detekt, tree-sitter или другие новые
  external tooling dependencies без свежего spike.
- Не делать Kotlin/Java analysis. V1 — Swift only (как crypto_domain_model).
- Не делать per-module policy inference (`:ErrorPolicy` с style classification).
  V1 находит конкретные антипаттерны, а не классифицирует стиль.
- Не делать layer-aware analysis. V1 использует file-path heuristics для
  определения "critical path", не зависит от `arch_layer` graph.
- Не делать cross-module consistency checks (`:ErrorBoundary`). Deferred.
- Не менять существующие extractors или audit infrastructure.

## 4. Current develop contracts

### 4.1 Extractor registry

S2.3 добавляет `"error_handling_policy": ErrorHandlingPolicyExtractor()` в
`EXTRACTORS` dict в `registry.py`.

### 4.2 AuditContract

```python
AuditContract(
    extractor_name="error_handling_policy",
    template_name="error_handling_policy.md",
    query=_QUERY,
    severity_column="severity",
    severity_mapper=_ehp_severity,
)
```

`_QUERY` queries `:CatchSite` aggregate rows and `:ErrorFinding` rows by
`project_id: $project_id`, so the §4 Security report can prove both the
catch-site smoke surface and the surfaced violations.

### 4.3 Semgrep precedent

`crypto_domain_model` (GIM-239) установил паттерн: semgrep YAML rules under
`extractors/<name>/rules/`, async subprocess invocation, JSON output parsing,
dedup, MERGE writes. S2.3 повторяет этот паттерн.

## 5. Inputs

Extractor reads:

- `ctx.repo_path` — mounted repo path for semgrep scan target.
- `ctx.project_slug`, `ctx.group_id`, `ctx.run_id` — standard context.
- Swift source files (`**/*.swift`) scanned by semgrep.

No rule file required from the project (rules are bundled in the extractor
package, same as crypto_domain_model).

## 6. Detection strategy

### 6.1 Tool: semgrep

Same invocation pattern as crypto_domain_model:

```bash
semgrep --config <rules_dir> --json --quiet <target_repo>
```

Rules are YAML files in `extractors/error_handling_policy/rules/`.

### 6.2 V1 rule set (≤8 rules, Swift only)

| Rule ID | Severity | Description |
|---------|----------|-------------|
| `empty_catch_block` | high | `catch { }` or `catch { break/continue/return }` with no error handling |
| `empty_catch_in_crypto_path` | critical | Empty catch in files matching `*Sign*`, `*Crypto*`, `*Key*`, `*Wallet*`, `*Balance*` |
| `try_optional_swallow` | medium | `try?` discarding error result (assigned to `_` or unused) |
| `try_optional_in_crypto_path` | high | `try?` in crypto/signing file paths |
| `catch_only_logs` | medium | `catch { logger.error(...) }` or `catch { print(...) }` with no rethrow/return |
| `generic_catch_all` | low | `catch` without specific error type binding |
| `error_as_string` | low | Throwing/returning string-typed errors instead of typed Error |
| `nil_coalesce_swallows_error` | medium | `try? expr ?? defaultValue` pattern swallowing error |

The extractor also keeps a non-finding catch-site inventory surface. It may be
implemented either as an informational semgrep pattern bundled with an existing
rule file or as bounded source-line inventory in `extractor.py`; either way it
must not create `:ErrorFinding` rows by itself. Its purpose is to populate
`:CatchSite` for the sprint smoke gate and template aggregate.

### 6.3 Critical path heuristics (EHP-D1)

File path regex determines severity escalation:

```python
CRITICAL_PATH_RE = re.compile(
    r"(Sign|Crypto|Key|Wallet|Balance|Mnemonic|Seed|Private|Secret)",
    re.IGNORECASE,
)
```

Rules `empty_catch_in_crypto_path` and `try_optional_in_crypto_path` are
separate semgrep rules with `paths.include` patterns (semgrep native feature)
rather than post-processing — cleaner and no false-positive noise from
non-critical files.

### 6.4 Deliberate suppression (EHP-D2)

If a catch block has `// ehp:ignore` or `// MARK: deliberate` comment on the
same or preceding line, the finding severity is downgraded to `informational`.
This is handled in post-processing (semgrep does not natively understand these
markers), by scanning matched line ranges for the suppression comment.

### 6.5 Deduplication (D5 equivalent)

Same as crypto_domain_model: coalesce per `(file, start_line, end_line, kind)`,
keep highest severity.

## 7. Graph writes

### 7.1 Nodes

```cypher
(:CatchSite {
    project_id,     -- "project/<slug>"
    file,           -- repo-relative file path
    start_line,     -- int
    end_line,       -- int
    kind,           -- "catch"|"try_optional"|"nil_coalesce_try_optional"|rule ID
    swallowed,      -- bool; true when site maps to a swallowed-error finding
    rethrows,       -- bool; true when catch body rethrows/throws
    module,         -- best-effort module/path bucket for aggregate display
    run_id          -- UUID of extractor run
})

(:ErrorFinding {
    project_id,     -- "project/<slug>"
    kind,           -- rule ID (e.g. "empty_catch_block")
    severity,       -- "critical"|"high"|"medium"|"low"|"informational"
    file,           -- repo-relative file path
    start_line,     -- int
    end_line,       -- int
    message,        -- human-readable from semgrep rule
    run_id          -- UUID of extractor run
})
```

### 7.2 Constraints and indexes

```cypher
CREATE CONSTRAINT error_finding_unique IF NOT EXISTS
FOR (f:ErrorFinding) REQUIRE
(f.project_id, f.kind, f.file, f.start_line, f.end_line) IS UNIQUE

CREATE INDEX error_finding_project IF NOT EXISTS
FOR (f:ErrorFinding) ON (f.project_id)

CREATE INDEX error_finding_severity IF NOT EXISTS
FOR (f:ErrorFinding) ON (f.severity)

CREATE CONSTRAINT catch_site_unique IF NOT EXISTS
FOR (c:CatchSite) REQUIRE
(c.project_id, c.file, c.start_line, c.end_line, c.kind) IS UNIQUE

CREATE INDEX catch_site_project IF NOT EXISTS
FOR (c:CatchSite) ON (c.project_id)

CREATE INDEX catch_site_module IF NOT EXISTS
FOR (c:CatchSite) ON (c.project_id, c.module)
```

### 7.3 Edges

V1 writes no edges. `:CatchSite` and `:ErrorFinding` are standalone nodes; the
template/audit query joins them by `project_id`, `file`, and line range when it
needs aggregate context.

### 7.4 Write pattern

Snapshot replacement in one managed write transaction:

```cypher
MATCH (n)
WHERE (n:CatchSite OR n:ErrorFinding) AND n.project_id = $project_id
DETACH DELETE n

CREATE (c:CatchSite)
SET c.project_id = $project_id,
    c.file = $file,
    c.start_line = $start_line,
    c.end_line = $end_line,
    c.kind = $catch_site_kind,
    c.swallowed = $swallowed,
    c.rethrows = $rethrows,
    c.module = $module,
    c.run_id = $run_id

CREATE (f:ErrorFinding)
SET f.project_id = $project_id,
    f.kind = $kind,
    f.file = $file,
    f.start_line = $start_line,
    f.end_line = $end_line,
    f.severity = $severity,
    f.message = $message,
    f.run_id = $run_id
```

Why this differs from `crypto_domain_model`: S2.3 has an explicit clean-state
report requirement. Re-runs must replace the current project snapshot so stale
findings disappear when the source repo is fixed.

## 8. Audit template

`audit/templates/error_handling_policy.md`:

- Module aggregate summary: files scanned, `:CatchSite` count,
  swallowed/rethrows breakdown, critical/high/medium/low finding breakdown.
- Critical/high findings section.
- Medium/low/informational findings section.
- Clean state: "no error handling issues found" with file count.
- Provenance: run_id + completed_at.

Template follows established patterns from `crypto_domain_model.md` and
`arch_layer.md`.

## 9. Severity mapping

`_ehp_severity` maps raw severity strings to `Severity` enum. Unknown values
map to `INFORMATIONAL`, matching `severity_from_str` fallback.

## 10. File layout

Implementation scope:

| Status | Path |
|--------|------|
| NEW | `services/palace-mcp/src/palace_mcp/extractors/error_handling_policy/__init__.py` |
| NEW | `services/palace-mcp/src/palace_mcp/extractors/error_handling_policy/extractor.py` |
| NEW | `services/palace-mcp/src/palace_mcp/extractors/error_handling_policy/rules/empty_catch_block.yaml` |
| NEW | `services/palace-mcp/src/palace_mcp/extractors/error_handling_policy/rules/empty_catch_in_crypto_path.yaml` |
| NEW | `services/palace-mcp/src/palace_mcp/extractors/error_handling_policy/rules/try_optional_swallow.yaml` |
| NEW | `services/palace-mcp/src/palace_mcp/extractors/error_handling_policy/rules/try_optional_in_crypto_path.yaml` |
| NEW | `services/palace-mcp/src/palace_mcp/extractors/error_handling_policy/rules/catch_only_logs.yaml` |
| NEW | `services/palace-mcp/src/palace_mcp/extractors/error_handling_policy/rules/generic_catch_all.yaml` |
| NEW | `services/palace-mcp/src/palace_mcp/extractors/error_handling_policy/rules/error_as_string.yaml` |
| NEW | `services/palace-mcp/src/palace_mcp/extractors/error_handling_policy/rules/nil_coalesce_swallows_error.yaml` |
| MOD | `services/palace-mcp/src/palace_mcp/extractors/registry.py` |
| NEW | `services/palace-mcp/src/palace_mcp/audit/templates/error_handling_policy.md` |
| NEW | `services/palace-mcp/tests/extractors/unit/test_error_handling_policy.py` |
| NEW | `services/palace-mcp/tests/extractors/integration/test_error_handling_policy_integration.py` |
| MOD | `services/palace-mcp/tests/extractors/unit/test_registry.py` |
| MOD | `services/palace-mcp/tests/audit/unit/test_templates.py` |
| NEW | `services/palace-mcp/tests/extractors/fixtures/error-handling-mini-project/Sources/Bad/EmptyCatch.swift` |
| NEW | `services/palace-mcp/tests/extractors/fixtures/error-handling-mini-project/Sources/Bad/TryOptionalSwallow.swift` |
| NEW | `services/palace-mcp/tests/extractors/fixtures/error-handling-mini-project/Sources/Bad/CatchOnlyLogs.swift` |
| NEW | `services/palace-mcp/tests/extractors/fixtures/error-handling-mini-project/Sources/Bad/CryptoSigner.swift` |
| NEW | `services/palace-mcp/tests/extractors/fixtures/error-handling-mini-project/Sources/Good/ProperCatch.swift` |
| NEW | `services/palace-mcp/tests/extractors/fixtures/error-handling-mini-project/Sources/Good/TypedErrors.swift` |
| NEW | `docs/runbooks/error-handling-policy.md` |

Total: **23 files** (**20 NEW + 3 MOD**).

Out of scope:

- changes to `crypto_domain_model`, `arch_layer`, or other extractors;
- changes to `audit/fetcher.py`, `audit/discovery.py`, `audit/renderer.py`;
- Kotlin/Java rules or detekt integration;
- changes to unrelated tests.

## 11. Required validation

Unit:

- each semgrep rule fires on bad fixture, does not fire on good fixture;
- dedup coalesces same location, keeps highest severity;
- deliberate-suppression downgrade works;
- severity mapper covers all enum values + unknown;
- `audit_contract()` returns valid shape;
- template renders without error (empty + non-empty findings).

Integration:

- synthetic fixture writes expected `:CatchSite` and `:ErrorFinding` counts;
- second run on the same repo is idempotent for both labels;
- clean rerun after bad fixtures are removed leaves `:ErrorFinding` count at 0;
- registry includes `error_handling_policy`;
- `fetch_audit_data()` executes the contract query and returns the current
  `:CatchSite` aggregate / summary row.

QA smoke:

- run `error_handling_policy` on `tronkit-swift`;
- verify `:CatchSite` count > 0;
- verify ≥1 `ErrorFinding` or explicit "no critical-path swallowed catches"
  with file count cited;
- report renders findings or clean state.

## 12. Risks

- **Semgrep Swift grammar** coverage may miss complex `do-catch` patterns with
  nested closures. Acceptable for v1 — findings are true positives even if
  coverage is incomplete.
- **False positives** on intentional error swallowing at UI boundaries.
  Mitigated by: (a) `// ehp:ignore` suppression, (b) `generic_catch_all` is
  `low` severity, (c) `catch_only_logs` is `medium` not `high`.
- **Critical path heuristic** is filename-based, not semantic. A crypto-related
  class in a generically named file will not get severity escalation. Acceptable
  for v1.
- **No Kotlin coverage** means Android projects get no error handling audit.
  Acknowledged in non-goals; deferred to future slice.

## 13. External tooling gate

Implementation may not add ast-grep, detekt, SwiftSyntax, tree-sitter,
SourceKit-LSP or a new semgrep plugin in this issue unless a fresh
`docs/research/<tool>-error-handling-spike/` artifact is added first and
reviewed by CXCodeReviewer. Default plan uses semgrep (already pinned) only.
