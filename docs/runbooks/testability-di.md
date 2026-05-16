# Runbook: testability_di extractor

> GIM-242 · Testability / DI Pattern Extractor (#8)

## Overview

`testability_di` is a heuristic source scanner for Swift + Kotlin repositories.
It detects:

- DI style summaries as `:DiPattern`
- framework and hand-rolled doubles as `:TestDouble`
- untestable seams as `:UntestableSite`

The extractor writes graph rows with `project_id="project/<slug>"` and feeds
audit-v1 through `palace.audit.run(project="<slug>", depth="full")`.

## Local verification

Lint + types:

```bash
cd services/palace-mcp
uv run ruff check src tests
uv run mypy src/
```

Targeted unit + template tests:

```bash
cd services/palace-mcp
uv run pytest \
  tests/extractors/unit/test_testability_di_scaffold.py \
  tests/extractors/unit/test_testability_di_scanner.py \
  tests/extractors/unit/test_testability_di_rules_di_style.py \
  tests/extractors/unit/test_testability_di_rules_test_doubles.py \
  tests/extractors/unit/test_testability_di_rules_untestable.py \
  tests/extractors/unit/test_testability_di_neo4j_writer.py \
  tests/extractors/unit/test_testability_di_audit_contract.py \
  tests/audit/test_testability_di_template.py -v
```

## Integration verification

If a shared compose Neo4j is already running:

```bash
cd services/palace-mcp
COMPOSE_NEO4J_URI=bolt://127.0.0.1:7687 \
COMPOSE_NEO4J_USER=neo4j \
COMPOSE_NEO4J_PASSWORD=password \
uv run pytest tests/extractors/integration/test_testability_di_extractor.py -m integration -v
```

If no shared Neo4j is available, start a throwaway local container first:

```bash
docker rm -f gimle-test-neo4j >/dev/null 2>&1 || true
docker run -d --rm \
  --name gimle-test-neo4j \
  -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/password \
  neo4j:5.26.0
```

Then rerun the integration command above.

## MCP invocation

Precondition: the target slug must resolve to a real git-backed mount inside
the container. Before invoking the extractor, verify:

```bash
docker compose exec -T palace-mcp sh -lc '
  test -e /repos/uw-ios/.git &&
  git -C /repos/uw-ios rev-parse --is-inside-work-tree
'
```

If this precheck fails, `repo_not_mounted` is an environment/mount problem,
not an extractor regression. Fix the bind-mount or register a temporary
git-backed QA repo before continuing smoke.

Extractor-only ingest:

```text
palace.ingest.run_extractor(name="testability_di", project="uw-ios")
```

Expected success envelope:

```json
{
  "ok": true,
  "run_id": "<uuid>",
  "extractor": "testability_di",
  "project": "uw-ios",
  "nodes_written": 9,
  "edges_written": 0,
  "success": true
}
```

Audit rendering:

```text
palace.audit.run(project="uw-ios", depth="full")
```

## Cypher checks

Quick label counts:

```cypher
MATCH (d:DiPattern {project_id: "project/uw-ios"})
RETURN count(d) AS di_patterns;
```

```cypher
MATCH (d:TestDouble {project_id: "project/uw-ios"})
RETURN count(d) AS test_doubles;
```

```cypher
MATCH (u:UntestableSite {project_id: "project/uw-ios"})
RETURN count(u) AS untestable_sites;
```

Audit-facing rollup:

```cypher
CALL {
  MATCH (di:DiPattern {project_id: "project/uw-ios"})
  RETURN di.module AS module
  UNION
  MATCH (td:TestDouble {project_id: "project/uw-ios"})
  RETURN td.module AS module
  UNION
  MATCH (us:UntestableSite {project_id: "project/uw-ios"})
  RETURN us.module AS module
}
WITH DISTINCT module
OPTIONAL MATCH (di:DiPattern {project_id: "project/uw-ios", module: module})
WITH module,
     [pattern IN collect(DISTINCT di {
       .language, .style, .framework, .sample_count, .outliers, .confidence
     }) WHERE pattern.style IS NOT NULL] AS di_patterns
OPTIONAL MATCH (td:TestDouble {project_id: "project/uw-ios", module: module})
WITH module,
     di_patterns,
     [double IN collect(DISTINCT td {
       .kind, .language, .target_symbol, .test_file
     }) WHERE double.kind IS NOT NULL] AS test_doubles
OPTIONAL MATCH (us:UntestableSite {project_id: "project/uw-ios", module: module})
WITH module,
     di_patterns,
     test_doubles,
     [site IN collect(DISTINCT us {
       .file, .language, .start_line, .end_line, .category,
       .symbol_referenced, .severity, .message
     }) WHERE site.file IS NOT NULL] AS untestable_sites
WITH module,
     CASE
       WHEN size(di_patterns) = 0 THEN [{
         language: coalesce(
           head([double IN test_doubles WHERE double.language IS NOT NULL | double.language]),
           head([site IN untestable_sites WHERE site.language IS NOT NULL | site.language]),
           "unknown"
         ),
         style: null,
         framework: null,
         sample_count: 0,
         outliers: 0,
         confidence: "heuristic"
       }]
       ELSE di_patterns
     END AS rows,
     test_doubles,
     untestable_sites
UNWIND rows AS row
RETURN module,
       row.language AS language,
       row.style AS style,
       row.framework AS framework,
       row.sample_count AS sample_count,
       row.outliers AS outliers,
       size(test_doubles) AS test_doubles,
       size(untestable_sites) AS untestable_sites
ORDER BY module, style;
```

Если `style` вернулся как `null`, это standalone audit row без `:DiPattern`; в markdown-рендере он отображается как `STANDALONE_SIGNAL`.

## Labels and indexes

Nodes written:

- `:DiPattern(project_id, module, language, style, framework, sample_count, outliers, confidence, run_id)`
- `:TestDouble(project_id, module, language, kind, target_symbol, test_file, run_id)`
- `:UntestableSite(project_id, module, language, file, start_line, end_line, category, symbol_referenced, severity, message, run_id)`

Indexes:

- `di_pattern_lookup`
- `test_double_lookup`
- `untestable_site_severity`

## Heuristic limits

1. Rev1 is regex/path based. It does not resolve full AST or type information.
2. Composition roots are allowlisted by filename/path hints (`assembler`, `bootstrap`, `AppRoot`, etc.).
3. Service-locator detection is intentionally conservative for test files and aggressive for production `getInstance()`/`.shared` usage.
4. `sample_count` is the number of rule hits aggregated per `(module, language, style, framework)`; rev1 does not attempt dominant-style inference.
