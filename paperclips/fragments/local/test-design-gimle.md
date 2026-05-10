## Test-design — {{PROJECT}} specifics

### Shared-infra paths (touching any = full `uv run pytest tests/`)

- `{{paths.primary_mcp_service_dir}}/src/{{mcp.package_name}}/main.py` (lifespan)
- `{{paths.primary_mcp_service_dir}}/src/{{mcp.package_name}}/memory/` (Cypher + schema)
- `{{paths.primary_mcp_service_dir}}/src/{{mcp.package_name}}/extractors/schema.py` + `runner.py`

### Python+pytest anti-pattern examples

- **Happy-path substrate mock:** `MagicMock(spec=<ExternalClass>)` where
  class is from `graphiti-core`, `neo4j`, `httpx`, `pygit2`. Prefer
  `testcontainers-neo4j`, real `git` subprocess, `tmp_path`,
  `httpx.MockTransport` respectively.
- **Partial async-driver mock:** `AsyncMock()` covering only subset of
  `driver.session()` contract (e.g., without `__aenter__`/`__aexit__`
  when new code adds `async with`). Prefer testcontainers integration.

### Past incidents caught by this rule

- **GIM-48** (2026-04-18) — mocked `Graphiti.nodes.*`; real graphiti-core
  0.4.3 lacks `.nodes`. `docs/postmortems/2026-04-18-GIM-48-n1a-broken-merge.md`.
- **GIM-59** (2026-04-20) — `AsyncMock(driver)` regression in
  `tests/test_startup_hardening.py` after lifespan added
  `ensure_extractors_schema`. Scoped `pytest tests/extractors/` missed it.

See `fragments/shared/fragments/test-design-discipline.md` for generic rule + CR checklist.
