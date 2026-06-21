# GIM-1603 — cross_module_contract baseline snapshot after public API regen

Grounded in `origin/develop` at `922a35e8a0d0c9d10c6ba9b09a0b42e096f7bd12`.

## Assumptions

- GIM-1602 is complete and `evm-kit` now has `.palace/public-api/swift/EvmKit.swiftinterface`.
- `public_api_surface` writes `PublicApiSurface` / `PublicApiSymbol` rows for `evm-kit`.
- Real Swift SCIP names are currently mangled while `public_api_surface` stores source-facing declarations, so exact consumer occurrence matching may legitimately produce zero consumption edges until a later demangling/correlation slice.

## Scope

- Keep `cross_module_contract` skipped when `PublicApiSurface` is absent.
- When a producer surface exists but no cross-module consumer matches are found, write a deterministic zero-consumption `ModuleContractSnapshot` for the producer surface.
- Preserve existing non-empty consumption snapshot behavior and delta behavior.
- Add focused unit/integration coverage.

## Affected Areas

- `services/palace-mcp/src/palace_mcp/extractors/cross_module_contract.py`
- `services/palace-mcp/tests/extractors/unit/test_cross_module_contract.py`
- `services/palace-mcp/tests/extractors/integration/test_cross_module_contract_integration.py`
- `docs/runbooks/cross-module-contract.md`

## Acceptance Criteria

- `cross_module_contract` returns OK for `evm-kit` after `public_api_surface`.
- `MATCH (s:ModuleContractSnapshot {group_id: "project/evm-kit"}) RETURN count(s)` returns `> 0`.
- Existing tests for missing public API still return `skipped`.
- Existing tests for real consumer matches still write `CONSUMES_PUBLIC_SYMBOL`.

## Verification Plan

- `uv run pytest tests/extractors/unit/test_cross_module_contract.py -v`
- `uv run pytest tests/extractors/integration/test_cross_module_contract_integration.py -v`
- Live MCP run on `evm-kit`: `public_api_surface`, `symbol_index_swift`, `cross_module_contract`, then snapshot count query.

## Open Questions

- A later slice should map source-facing `.swiftinterface` declarations to SCIP mangled names or demangled names so `CONSUMES_PUBLIC_SYMBOL` edges can be populated for real Swift packages.
