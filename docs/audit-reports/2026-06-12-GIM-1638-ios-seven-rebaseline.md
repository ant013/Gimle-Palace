# GIM-1638 iOS seven-repo rebaseline report

Grounded in `origin/develop` at `f9615bfc` plus fix branch
`fix/GIM-1638-error-handling-semgrep-timeout` at `d963ca90`.

## Substrate

- Runtime: native MacBook `palace-mcp`, launchd
  `work.ant013.palace-mcp-native`, not Docker.
- Service root during final targeted rerun:
  `/Users/Shared/Ios/Gimle-Palace/services/palace-mcp`.
- Health after restart: `{"status":"ok","neo4j":"reachable"}`.
- Native env override used for the final rerun:
  `PALACE_ERROR_HANDLING_SEMGREP_TIMEOUT_S=1800`.

## Corpus

| Project | Path | HEAD | Git commits |
| --- | --- | --- | ---: |
| `bitcoin-core` | `/Users/Shared/Ios/Gimle-Repos/HorizontalSystems/BitcoinCore.Swift` | `5b49f424` | 1330 |
| `bitcoin-kit` | `/Users/Shared/Ios/Gimle-Repos/HorizontalSystems/BitcoinKit.Swift` | `26609dbe` | 1266 |
| `component-kit` | `/Users/Shared/Ios/Gimle-Repos/HorizontalSystems/component-kit-ios` | `b22e0d8` | 276 |
| `dash-kit` | `/Users/Shared/Ios/Gimle-Repos/HorizontalSystems/DashKit.Swift` | `25bef76b` | 1266 |
| `evm-kit` | `/Users/Shared/Ios/Gimle-Repos/HorizontalSystems/EvmKit.Swift` | `375e38c` | 608 |
| `hd-wallet-kit` | `/Users/Shared/Ios/Gimle-Repos/HorizontalSystems/hd-wallet-kit-ios` | `1bc214b` | 37 |
| `uw-ios-app` | `/Users/Shared/Ios/Gimle-Repos/HorizontalSystems/unstoppable-wallet-ios` | `5ed53c314` | 7632 |

## Clean Start

- Initial single-transaction purge hit Neo4j memory pressure and was discarded.
- Batched clean purge completed.
- Deleted scoped nodes: `625,626`.
- Evidence: `/tmp/gim-1638-rebaseline/clean-prep.json`.

## Run Summary

- Main sequential run: `112` extractor/project runs.
- Main sequential wall time: `4,673,638ms`.
- Main run wrote before semgrep repair: `499,300` nodes, `220,105` edges.
- Semgrep launchd PATH repair converted the initial semgrep `FileNotFoundError`
  failures into successful reruns.
- Final targeted rerun fixed the last hard failure:
  `error_handling_policy/uw-ios-app`.
- Final effective status: `112/112` extractor/project slots completed as
  `ok`, `skipped`, `missing_input`, or `not_applicable`; `0` hard failures.
- Final effective node total from the successful paths: `502,982` nodes.
- Final effective edge total: `220,105` edges.

## Extractor Outcomes

| Extractor | Projects | Final outcome summary | Nodes | Edges |
| --- | ---: | --- | ---: | ---: |
| `arch_layer` | 7 | 7 ok | 26 | 5 |
| `code_ownership` | 7 | 7 ok | 4,422 | 6,760 |
| `coding_convention` | 7 | 7 ok | 1,684 | 0 |
| `cross_module_contract` | 7 | 7 skipped, zero-consumer baselines where producer surfaces exist | 4 | 4 |
| `crypto_domain_model` | 7 | 7 ok after semgrep PATH rerun | 147 | 0 |
| `dead_symbol_binary_surface` | 7 | 7 ok | 1,337 | 10 |
| `dependency_surface` | 7 | 7 ok | 17 | 20 |
| `error_handling_policy` | 7 | 7 ok after timeout fix and targeted app rerun | 2,508 | 0 |
| `git_history` | 7 | 7 skipped outcome after commit walk because GitHub token is absent | 12,415 | 199,481 |
| `hot_path_profiler` | 7 | 7 missing_input, profiles directories absent | 0 | 0 |
| `hotspot` | 7 | 7 ok | 14,808 | 12,635 |
| `localization_accessibility` | 7 | 7 ok after semgrep PATH rerun | 1,027 | 0 |
| `public_api_surface` | 7 | 4 ok, 3 not_applicable | 1,194 | 1,190 |
| `reactive_dependency_tracer` | 7 | 7 missing_input, helper JSON absent | 3,723 | 0 |
| `symbol_index_swift` | 7 | 7 ok | 457,931 | 0 |
| `testability_di` | 7 | 7 ok | 1,739 | 0 |

## Cross-Repo Version Skew

- Bundle: `ios-seven-rebaseline`.
- Run id: `rb-04eebe9864554e42`.
- State: `succeeded`.
- Members: 7 done, 6 ok, 1 missing_input, 0 failed.
- `hd-wallet-kit` returned explicit `missing_input` because targets have no
  usable `:DEPENDS_ON` data for skew aggregation.
- Evidence: `/tmp/gim-1638-rebaseline/cross-repo-version-skew-bundle.json`.

## Final Targeted Rerun

The remaining hard failure before this fix was:

```text
error_handling_policy / uw-ios-app:
semgrep timed out after 120s
```

Fix branch `d963ca90` added the missing Settings fields and an
`error_handling_policy` class-level runner timeout matching neighboring
semgrep-backed extractors.

Final targeted result:

| Field | Value |
| --- | --- |
| Run id | `5e752817-c75e-4f6f-aed9-9979e2a9bfe2` |
| Outcome | `ok` |
| Duration | `59,553ms` |
| Nodes written | `1,878` |
| Edges written | `0` |
| `ErrorFinding` count for `project/uw-ios-app` | `1,012` |

Evidence:

- `/tmp/gim-1638-rebaseline/error-handling-uw-ios-targeted-rerun.json`
- `/tmp/gim-1638-rebaseline/error-handling-uw-ios-post-sanity.json`

## Sanity Queries

This section inlines the native Neo4j sanity outcomes that were previously only
referenced via `/tmp/gim-1638-rebaseline/final-sanity.json`.

| Extractor | Sanity metric | Result |
| --- | --- | --- |
| `arch_layer` | module/layer graph footprint | `26` nodes, `5` edges, `7/7` projects `ok` |
| `public_api_surface` | public API surface/symbol footprint | `1,194` nodes, `1,190` edges, `4` projects `ok`, `3` projects `NOT_APPLICABLE` |
| `cross_module_contract` | consumer-correlation baseline | `4` nodes, `4` edges, `7/7` projects recorded as skipped zero-consumer baselines |
| `cross_repo_version_skew` | bundle skew aggregation | bundle `ios-seven-rebaseline` `succeeded`; `7` members done, `6` `ok`, `1` `MISSING_INPUT` (`hd-wallet-kit`), `0` failed |
| `code_ownership` | ownership state footprint | `4,422` nodes, `6,760` edges, `7/7` projects `ok` |
| `reactive_dependency_tracer` | reactive graph / missing-input diagnostics | `3,723` nodes, `0` edges, `7/7` projects `MISSING_INPUT` because helper JSON was absent |
| `hot_path_profiler` | profiler graph / missing-input diagnostics | `0` nodes, `0` edges, `7/7` projects `MISSING_INPUT` because profiles directories were absent |

### `git_history` commit-count sanity

The native sanity bundle verified `git_history` commit counts against local
`git rev-list --count HEAD` for each dedicated iOS repo. The same counts are
captured below and match the corpus used for the rebaseline.

| Project | `git rev-list --count HEAD` |
| --- | ---: |
| `bitcoin-core` | 1330 |
| `bitcoin-kit` | 1266 |
| `component-kit` | 276 |
| `dash-kit` | 1266 |
| `evm-kit` | 608 |
| `hd-wallet-kit` | 37 |
| `uw-ios-app` | 7632 |

Aggregate `git_history` write footprint from the successful commit-walk paths:
`12,415` nodes and `199,481` edges. The final run outcome stayed `skipped`
only for GitHub PR/comment enrichment because no GitHub token was configured.

## Evidence Files

- `/tmp/gim-1638-rebaseline/clean-prep.json`
- `/tmp/gim-1638-rebaseline/extractor-results.json`
- `/tmp/gim-1638-rebaseline/extractor-results-summary.json`
- `/tmp/gim-1638-rebaseline/semgrep-rerun-results.json`
- `/tmp/gim-1638-rebaseline/semgrep-rerun-results.tsv`
- `/tmp/gim-1638-rebaseline/cross-repo-version-skew-bundle.json`
- `/tmp/gim-1638-rebaseline/final-sanity.json`
- `/tmp/gim-1638-rebaseline/latest-ingest-outcomes.tsv`
- `/tmp/gim-1638-rebaseline/error-handling-uw-ios-targeted-rerun.json`
- `/tmp/gim-1638-rebaseline/error-handling-uw-ios-post-sanity.json`

## Notes

- `git_history` commit counts match `git rev-list --count`; the `skipped`
  outcome is limited to GitHub PR/comment enrichment because no GitHub token was
  configured.
- `reactive_dependency_tracer` and `hot_path_profiler` are explicit
  `missing_input`, not hard failures.
- `public_api_surface` is `not_applicable` for app/no-public-artifact projects.
- `cross_module_contract` still reports zero consumer correlation. The report
  treats that as a baseline outcome, not a hard failure for GIM-1638.
