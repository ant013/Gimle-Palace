# Native iOS Gimle Rebaseline Report

Grounded branch state: `docs/native-macbook-rebaseline-spec` at
`1f16179577fda00df469fabb56d888a56c886096` before the implementation/report
commit. All timestamps below are UTC.

## Scope

- Native MCP URL: `http://127.0.0.1:8765/mcp`
- Native Neo4j: `bolt://localhost:7687`
- Native env: `/Users/ant013/Android/Gimle-Palace-native/.env`
- Dedicated source root:
  `/Users/Shared/Ios/Gimle-Repos/HorizontalSystems`
- Manifest:
  `services/palace-mcp/scripts/native-ios-rebaseline-manifest.json`
- Excluded by helper preflight:
  `/Users/Shared/Ios/HorizontalSystems`, `/Users/ant013/Ios/uw-fresh-*`, and
  Android repositories.

## Changes Made

- Added a native-only iOS rebaseline helper and manifest for the exact seven
  iOS repositories.
- Added guardrails for forbidden live checkout roots and Android scope.
- Added resume controls for sequential recovery:
  `--skip-cleanup`, `--start-project`, and `--start-after-extractor`.
- Hardened `code_ownership` so a stale checkpoint SHA falls back to a full HEAD
  scan instead of failing on a missing commit object.
- Made `launch_native_macos.sh` resolve `SERVICE_ROOT` relative to the checked
  out script instead of the old hard-coded clone path.
- Updated the native MacBook runbook with the seven-repo path and current
  embedding cap.

## Source Revisions And Artifacts

| Project | Branch | HEAD | SCIP bytes | Periphery findings |
| --- | --- | --- | ---: | ---: |
| bitcoin-core | master | `5b49f424f495904cf06519b1a7b861ef37b45b50` | 32,203,871 | 90 |
| bitcoin-kit | master | `26609dbef9cadd188e8a0c454acb8437915f1414` | 32,393,892 | 1 |
| dash-kit | master | `25bef76b18986e7831073986c935f5e1e00a7629` | 33,163,658 | 29 |
| evm-kit | master | `375e38c14716d9f2f4a82a523ebc0f955d98956f` | 29,794,444 | 27 |
| component-kit | master | `b22e0d80bc0f51dac313f83ebb8bae9791185594` | 7,075,717 | 97 |
| hd-wallet-kit | master | `1bc214b259bd7d78e5eac7146b4e200aa120c130` | 185,617 | 2 |
| uw-ios-app | version/0.49 | `5ed53c3143de394837dd8e9b579a547fbabd6d47` | 174,062,458 | 1,796 |

All SCIP meta files matched the corresponding repository HEAD SHA. Tantivy
index size after the run: `278M` at `/Users/ant013/.cache/palace-tantivy`.

## Final Neo4j Coverage

| Project | Symbols | Embedded | scope_project | scope_dependency |
| --- | ---: | ---: | ---: | ---: |
| bitcoin-core | 48,166 | 48,166 | 7,154 | 41,012 |
| bitcoin-kit | 48,490 | 48,490 | 219 | 48,271 |
| dash-kit | 49,788 | 49,788 | 1,596 | 48,192 |
| evm-kit | 44,661 | 44,661 | 3,181 | 41,480 |
| component-kit | 11,836 | 11,836 | 0 | 11,836 |
| hd-wallet-kit | 226 | 226 | 0 | 226 |
| uw-ios-app | 254,764 | 254,764 | 69,987 | 184,777 |

Every project has 100% symbol embedding coverage. Latest `IngestRun` status is
successful for all 19 extractors in the active profile:
`arch_layer`, `code_ownership`, `coding_convention`, `cross_module_contract`,
`cross_repo_version_skew`, `crypto_domain_model`,
`dead_symbol_binary_surface`, `dependency_surface`, `embedding_symbol`,
`error_handling_policy`, `git_history`, `hot_path_profiler`, `hotspot`,
`localization_accessibility`, `prune_swift_symbols`, `public_api_surface`,
`reactive_dependency_tracer`, `symbol_index_swift`, `testability_di`.

## Timing Notes

The full first helper report was not written because the original run failed at
`component-kit/code_ownership` before process completion. Neo4j `IngestRun`
records and the resume reports provide the timing evidence:

| Project | Latest profile start | Latest profile finish |
| --- | --- | --- |
| bitcoin-core | 2026-06-10T13:22:00Z | 2026-06-10T14:45:18Z |
| bitcoin-kit | 2026-06-10T14:45:18Z | 2026-06-10T15:49:12Z |
| dash-kit | 2026-06-10T15:49:12Z | 2026-06-10T16:53:08Z |
| evm-kit | 2026-06-10T16:53:09Z | 2026-06-10T17:48:22Z |
| component-kit | 2026-06-10T17:48:23Z | 2026-06-10T18:14:45Z |
| hd-wallet-kit | 2026-06-10T18:14:45Z | 2026-06-10T18:15:22Z |
| uw-ios-app | 2026-06-10T18:15:22Z | 2026-06-11T00:56:32Z |

Key extractor timings:

| Project | symbol_index_swift | git_history | code_ownership | embedding_symbol |
| --- | ---: | ---: | ---: | ---: |
| bitcoin-core | 101.1s | 42.3s | 0.0s | 4,690.2s |
| bitcoin-kit | 117.4s | 63.7s | 0.0s | 3,627.5s |
| dash-kit | 110.5s | 53.8s | 0.1s | 3,611.4s |
| evm-kit | 98.6s | 22.5s | 0.1s | 3,134.6s |
| component-kit | 19.5s | 10.3s | 14.4s | 758.5s |
| hd-wallet-kit | 2.3s | 1.5s | 3.6s | 17.7s |
| uw-ios-app | 2,746.3s | 258.0s | 576.8s | 7,086.8s first pass, 4,922.4s final successful pass |

`uw-ios-app` needed multiple incremental embedding passes after raising
`PALACE_EMBEDDING_MAX_SYMBOLS` to `300000`: the first successful pass wrote
100,000 embeddings, one 7,200s pass timed out after persisting progress, and
the final successful pass wrote 59,148 embeddings.

## Smoke Checks

- `/healthz` returned `{"status":"ok","neo4j":"reachable"}`.
- `palace.code.semantic_search` for
  `project=uw-ios-app query="wallet balance sync adapter" limit=3` returned
  `ok=true`, backend `qodo`, `embedded_symbol_count=254764`,
  `eligible_symbols=254764`, and top file
  `packages/WalletCore/Sources/WalletCore/Modules/Wallet/WalletAdapterService.swift`.

## Residuals

- A historical failed `component-kit/code_ownership` run remains in Neo4j, but
  the latest run is successful after the checkpoint fallback fix.
- A historical failed `uw-ios-app/embedding_symbol` timeout run remains in
  Neo4j, but the latest run is successful and coverage is 254,764 / 254,764.
- The server logged a non-blocking background `ensure_schema` warning about an
  orphan old group id `project/unstoppable-wallet-ios baseline (871c0e8)`.
  This is not one of the seven active project groups and should be cleaned as a
  separate maintenance task if needed.
- `component-kit`, `hd-wallet-kit`, and `uw-ios-app` SCIP generation used
  partial IndexStore artifacts where the Xcode build did not fully link, but
  valid SCIP files were produced and their meta SHAs match repository HEAD.
