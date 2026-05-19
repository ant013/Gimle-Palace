# BitcoinCore Post-Fix Validation - 2026-05-19

## Scope

Validation for GIM-374 after GIM-355, GIM-356, and GIM-357 landed on
`develop` through `c19769922e60f88eb290972ea80a9022918ea351`.

## Command

```bash
COMPOSE_PROJECT_NAME=gimle-palace COMPOSE_PROFILES=review \
  ./paperclips/scripts/ingest_swift_kit.sh bitcoin-core
```

Runtime setup:

- Worktree: `feature/GIM-374-m02-btc-post-fix-validation` at `c1976992`.
- `palace-mcp` image rebuilt from this worktree before the run.
- `palace-mcp` health: `{"status":"ok","neo4j":"reachable"}`.
- Repo path: `/Users/Shared/Ios/HorizontalSystems/BitcoinCore.Swift`.
- Container path: `/repos-hs/BitcoinCore.Swift`.
- SCIP path: `/repos-hs/BitcoinCore.Swift/scip/index.scip`.

## Result Summary

- Total extractors: 17.
- Script-level `OK`: 16/17.
- Expected non-OK: 1/17, `dead_symbol_binary_surface`.
- Raw script final status: `partial_failure` because
  `dead_symbol_binary_surface` still reports `status=failed` with
  `error_code=periphery_fixtures_missing`.
- Acceptance classification: expected `MISSING_INPUT` for
  `dead_symbol_binary_surface`; the missing fixture is
  `/repos-hs/BitcoinCore.Swift/periphery/periphery-3.7.4-swiftpm.json`.

`hot_path_profiler` and `public_api_surface` also reported non-failing
`outcome=missing_input` while keeping script `status=ok`; they do not reduce the
16/17 script-level OK count.

## Extractor Matrix

| Extractor | Status | Outcome / Error | Run ID | Writes |
|---|---:|---|---|---:|
| `symbol_index_swift` | OK | `ok` | `466fd588-aae1-4563-abcf-ecb744b65458` | 219767 nodes / 0 edges |
| `arch_layer` | OK | `ok` | `1e296926-9019-4633-8d0e-f8a11c9869b4` | 2 nodes / 1 edge |
| `git_history` | OK | `ok` | `22cf17ef-e6a2-483f-afe7-0e38716dde05` | 0 nodes / 0 edges |
| `code_ownership` | OK | `ok` | `fce6bd58-4c07-4563-ad96-2747516c498d` | 266 nodes / 649 edges |
| `coding_convention` | OK | `ok` | `ca3b3691-f9ec-4e86-ad52-9a713297b871` | 143 nodes / 0 edges |
| `crypto_domain_model` | OK | `ok` | `fb43cbbf-1e2a-41fa-ae24-fae17d08b109` | 4 nodes / 0 edges |
| `cross_module_contract` | OK | `skipped` | `da987c0c-c8d9-40bb-8b3f-c2303e7bcaa6` | 0 nodes / 0 edges |
| `cross_repo_version_skew` | OK | `ok` | `6698f0d5-661d-4e1c-b47b-148072ce2e66` | 1 node / 0 edges |
| `dead_symbol_binary_surface` | MISSING_INPUT | `periphery_fixtures_missing` | n/a | n/a |
| `dependency_surface` | OK | `ok` | `11bc46cb-d23e-4982-9f82-b03cffadd02e` | 0 nodes / 0 edges |
| `error_handling_policy` | OK | `ok` | `1229bf9d-70d8-42c9-8893-20faef32c80d` | 362 nodes / 0 edges |
| `hot_path_profiler` | OK | `missing_input` | `53d61e86-973f-4eb0-acec-93cabe5b3b90` | 0 nodes / 0 edges |
| `hotspot` | OK | `ok` | `198c6278-cea0-4f0d-b05d-bb464c5bea5f` | 1181 nodes / 1009 edges |
| `localization_accessibility` | OK | `ok` | `8fe17141-8c42-40c8-90a7-c7e4f7b50235` | 0 nodes / 0 edges |
| `public_api_surface` | OK | `missing_input` | `1408dc9a-d700-4aeb-9717-14ff9265304b` | 0 nodes / 0 edges |
| `reactive_dependency_tracer` | OK | `ok` | `6c0c7c36-8985-4959-9131-af175ece6ddf` | 3051 nodes / 0 edges |
| `testability_di` | OK | `ok` | `4a6b64c3-de90-4e20-a8cc-b83ce382d9dc` | 70 nodes / 0 edges |

## Verification

The final JSON summary contained 17 extractor entries, 16 with `status=ok`, and
one expected periphery fixture gap for `dead_symbol_binary_surface`.
