# Audit Report — tron-kit

**Generated at:** 2026-05-14T10:52:10.855062+00:00
**Depth:** full

---


## Executive Summary

Audit of project `tron-kit` at depth `full`. 8 extractors contributed data. Findings by source: library=6 example=4 test=0 other=113 6 extractor(s) had no data (blind spots): `cross_module_contract`, `error_handling_policy`, `hot_path_profiler`, `localization_accessibility`, `public_api_surface`, `reactive_dependency_tracer`. ⚠ 1 extractor(s) failed their last run: `crypto_domain_model`. ⚠ 1 section(s) have critical/high findings requiring attention. Top findings: **HIGH** [naming.type_class]; **HIGH** [structural.adt_pattern]; **HIGH** [idiom.collection_init].

---


## Architecture layer violations



No architecture rules declared — 1 modules indexed in Neo4j (no rule evaluation possible).

The `arch_layer` extractor ran but found no rule file at
`.palace/architecture-rules.yaml` or `docs/architecture-rules.yaml`.
Module DAG was written to Neo4j. To enable rule evaluation, add a rule file
to the repository. See the runbook at `docs/runbooks/arch-layer.md`.

**Provenance:** run_id `a2abd2a3-fbe8-4d76-99db-505b699ad27c`.




---


## Code Hotspots


No findings — extractor `hotspot` ran at `c36bf00e-9f8e-4ca8-94e6-3bf621054f9a`,
scanned 0 files, found 0 issues.


*Provenance: run `c36bf00e-9f8e-4ca8-94e6-3bf621054f9a`.*


---


## Dead Symbols & Binary Surface


No findings — extractor `dead_symbol_binary_surface` ran at `eff2f9e7-6df6-4969-920c-d8d5d6bf9041`,
found 0 dead symbol candidates.


*Provenance: run `eff2f9e7-6df6-4969-920c-d8d5d6bf9041`.*


---


## Dependency Surface


### ⚠ Data Quality

No `Package.resolved` (or `uv.lock` / `gradle.lockfile`) found; declared constraints only.
CVE / version-freshness checks unavailable.



*9 dependencies found (capped at 100).*


| PURL | Scope | Declared In | Declared Constraint |
|------|-------|-------------|---------------------|

| `pkg:github/Kitura/BlueSocket@unresolved` | compile | `Package.swift` | — |

| `pkg:github/apple/swift-protobuf@unresolved` | compile | `Package.swift` | — |

| `pkg:github/attaswift/BigInt@unresolved` | compile | `Package.swift` | — |

| `pkg:github/groue/GRDB.swift@unresolved` | compile | `Package.swift` | — |

| `pkg:github/horizontalsystems/HdWalletKit.Swift@unresolved` | compile | `Package.swift` | — |

| `pkg:github/horizontalsystems/HsCryptoKit.Swift@unresolved` | compile | `Package.swift` | — |

| `pkg:github/horizontalsystems/HsExtensions.Swift@unresolved` | compile | `Package.swift` | — |

| `pkg:github/horizontalsystems/HsToolKit.Swift@unresolved` | compile | `Package.swift` | — |

| `pkg:github/tristanhimmelman/ObjectMapper@unresolved` | compile | `Package.swift` | — |



**Summary:** 9 total dependencies across compile scopes.


*Provenance: run `29349e73-3c7c-4f1e-b447-ac0e01dd6ba5`.*


---


## Code Ownership


*100 files with diffuse ownership (capped at 100).*

| Severity | Path | Top Owner | Weight | Total Authors | Source |
|----------|------|-----------|--------|--------------|--------|

| INFORMATIONAL | `Sources/TronKit/Models/Contract/ContractHelper.swift` | ealymbaev@gmail.com | 0.26 | 2 | other |

| INFORMATIONAL | `Sources/TronKit/Proto/contract/common.pb.swift` | ealymbaev@gmail.com | 0.26 | 2 | other |

| INFORMATIONAL | `Sources/TronKit/Proto/TronInventoryItems.pb.swift` | ealymbaev@gmail.com | 0.27 | 2 | other |

| INFORMATIONAL | `Sources/TronKit/Decorations/NativeTransactionDecoration.swift` | ealymbaev@gmail.com | 0.27 | 2 | other |

| INFORMATIONAL | `Sources/TronKit/Events/EventHelper.swift` | esenbekkd@gmail.com | 0.28 | 2 | other |

| INFORMATIONAL | `Sources/TronKit/Core/TransactionSender.swift` | esenbekkd@gmail.com | 0.28 | 3 | other |

| INFORMATIONAL | `Sources/TronKit/SmartContract/ContractMethodHelper.swift` | esenbekkd@gmail.com | 0.28 | 2 | other |

| INFORMATIONAL | `Sources/TronKit/Proto/contract/vote_asset_contract.pb.swift` | ealymbaev@gmail.com | 0.30 | 2 | other |

| INFORMATIONAL | `Sources/TronKit/Proto/contract/market_contract.pb.swift` | ealymbaev@gmail.com | 0.33 | 2 | other |

| INFORMATIONAL | `Sources/TronKit/Proto/contract/proposal_contract.pb.swift` | ealymbaev@gmail.com | 0.33 | 2 | other |

| INFORMATIONAL | `Sources/TronKit/Proto/contract/storage_contract.pb.swift` | ealymbaev@gmail.com | 0.34 | 2 | other |

| INFORMATIONAL | `Sources/TronKit/Proto/contract/witness_contract.pb.swift` | ealymbaev@gmail.com | 0.34 | 2 | other |

| INFORMATIONAL | `Sources/TronKit/Proto/contract/account_contract.pb.swift` | ealymbaev@gmail.com | 0.35 | 2 | other |

| INFORMATIONAL | `Sources/TronKit/Decorations/TransactionDecoration.swift` | esenbekkd@gmail.com | 0.36 | 2 | other |

| INFORMATIONAL | `Sources/TronKit/Models/Records/TransactionTagRecord.swift` | esenbekkd@gmail.com | 0.36 | 3 | other |

| INFORMATIONAL | `Sources/TronKit/Proto/contract/exchange_contract.pb.swift` | ealymbaev@gmail.com | 0.36 | 2 | other |

| INFORMATIONAL | `Sources/TronKit/Decorations/UnknownTransactionDecoration.swift` | esenbekkd@gmail.com | 0.37 | 4 | other |

| INFORMATIONAL | `iOS Example/Sources/AppDelegate.swift` | esenbekkd@gmail.com | 0.37 | 2 | other |

| INFORMATIONAL | `Sources/TronKit/Core/Kit.swift` | esenbekkd@gmail.com | 0.37 | 4 | other |

| INFORMATIONAL | `iOS Example/Sources/Controllers/Cells/TransactionCell.swift` | esenbekkd@gmail.com | 0.38 | 2 | other |

| INFORMATIONAL | `Sources/TronKit/TronGrid/JsonRpc/JsonRpc.swift` | esenbekkd@gmail.com | 0.38 | 2 | other |

| INFORMATIONAL | `Sources/TronKit/Proto/contract/balance_contract.pb.swift` | ealymbaev@gmail.com | 0.38 | 2 | other |

| INFORMATIONAL | `Sources/TronKit/Models/TransactionTagQuery.swift` | esenbekkd@gmail.com | 0.38 | 3 | other |

| INFORMATIONAL | `Sources/TronKit/Core/FeeProvider.swift` | esenbekkd@gmail.com | 0.38 | 2 | other |

| INFORMATIONAL | `Sources/TronKit/Proto/Discover.pb.swift` | ealymbaev@gmail.com | 0.38 | 2 | other |

| INFORMATIONAL | `Sources/TronKit/SmartContract/Trc20/TransferMethodFactory.swift` | esenbekkd@gmail.com | 0.38 | 2 | other |

| INFORMATIONAL | `Sources/TronKit/SmartContract/Trc20/ApproveMethodFactory.swift` | esenbekkd@gmail.com | 0.38 | 2 | other |

| INFORMATIONAL | `Sources/TronKit/Models/TransactionTag.swift` | esenbekkd@gmail.com | 0.39 | 3 | other |

| INFORMATIONAL | `Sources/TronKit/Events/Trc20ApproveEvent.swift` | esenbekkd@gmail.com | 0.39 | 2 | other |

| INFORMATIONAL | `Sources/TronKit/Storage/TransactionStorage.swift` | esenbekkd@gmail.com | 0.39 | 4 | other |

| INFORMATIONAL | `Sources/TronKit/Events/Trc20TransferEvent.swift` | esenbekkd@gmail.com | 0.39 | 3 | other |

| INFORMATIONAL | `Sources/TronKit/Models/SyncState.swift` | esenbekkd@gmail.com | 0.39 | 2 | other |

| INFORMATIONAL | `Sources/TronKit/Signer/Signer.swift` | esenbekkd@gmail.com | 0.40 | 2 | other |

| INFORMATIONAL | `Sources/TronKit/TronGrid/JsonRpc/EstimateGasJsonRpc.swift` | esenbekkd@gmail.com | 0.40 | 2 | other |

| INFORMATIONAL | `Sources/TronKit/TronGrid/FullNode/CreatedTransactionResponse.swift` | esenbekkd@gmail.com | 0.41 | 2 | other |

| INFORMATIONAL | `iOS Example/Sources/Controllers/DecorationExtension.swift` | esenbekkd@gmail.com | 0.41 | 2 | other |

| INFORMATIONAL | `Sources/TronKit/Proto/contract/shield_contract.pb.swift` | ealymbaev@gmail.com | 0.42 | 2 | other |

| INFORMATIONAL | `Sources/TronKit/Core/TransactionManager.swift` | esenbekkd@gmail.com | 0.42 | 4 | other |

| INFORMATIONAL | `iOS Example/Sources/Controllers/BalanceController.swift` | esenbekkd@gmail.com | 0.42 | 2 | other |

| INFORMATIONAL | `Sources/TronKit/Proto/contract/smart_contract.pb.swift` | ealymbaev@gmail.com | 0.42 | 2 | other |

| INFORMATIONAL | `iOS Example/Sources/Controllers/TransactionsController.swift` | esenbekkd@gmail.com | 0.43 | 2 | other |

| INFORMATIONAL | `Sources/TronKit/Proto/contract/asset_issue_contract.pb.swift` | ealymbaev@gmail.com | 0.43 | 2 | other |

| INFORMATIONAL | `Sources/TronKit/TronGrid/JsonRpc/JsonRpcResponse.swift` | esenbekkd@gmail.com | 0.44 | 2 | other |

| INFORMATIONAL | `Package.swift` | ealymbaev@gmail.com | 0.44 | 2 | other |

| INFORMATIONAL | `Sources/TronKit/Models/Records/TransactionSyncTimestamp.swift` | esenbekkd@gmail.com | 0.44 | 2 | other |

| INFORMATIONAL | `Sources/TronKit/Models/Records/ChainParameter.swift` | esenbekkd@gmail.com | 0.44 | 2 | other |

| INFORMATIONAL | `Sources/TronKit/TronGrid/ExtensionApi/AccountInfoResponse.swift` | esenbekkd@gmail.com | 0.44 | 2 | other |

| INFORMATIONAL | `Sources/TronKit/Proto/Tron.pb.swift` | ealymbaev@gmail.com | 0.44 | 2 | other |

| INFORMATIONAL | `Sources/TronKit/Models/Address.swift` | esenbekkd@gmail.com | 0.45 | 2 | other |

| INFORMATIONAL | `Sources/TronKit/TronGrid/TronGridProvider.swift` | esenbekkd@gmail.com | 0.45 | 3 | other |

| INFORMATIONAL | `Sources/TronKit/Decorations/SmartContract/ApproveEip20Decoration.swift` | esenbekkd@gmail.com | 0.45 | 2 | other |

| INFORMATIONAL | `Sources/TronKit/Models/Records/Transaction.swift` | esenbekkd@gmail.com | 0.45 | 2 | other |

| INFORMATIONAL | `Sources/TronKit/Models/Records/LastBlockHeight.swift` | esenbekkd@gmail.com | 0.45 | 2 | other |

| INFORMATIONAL | `Sources/TronKit/Core/Transforms.swift` | esenbekkd@gmail.com | 0.46 | 2 | other |

| INFORMATIONAL | `Sources/TronKit/Models/Records/Balance.swift` | esenbekkd@gmail.com | 0.46 | 2 | other |

| INFORMATIONAL | `iOS Example/Sources/Core/Manager.swift` | esenbekkd@gmail.com | 0.46 | 2 | other |

| INFORMATIONAL | `Sources/TronKit/Decorations/SmartContract/OutgoingEip20Decoration.swift` | esenbekkd@gmail.com | 0.46 | 2 | other |

| INFORMATIONAL | `Sources/TronKit/TronGrid/JsonRpc/CallJsonRpc.swift` | esenbekkd@gmail.com | 0.46 | 2 | other |

| INFORMATIONAL | `iOS Example/Sources/Configuration.swift` | esenbekkd@gmail.com | 0.46 | 2 | other |

| INFORMATIONAL | `Sources/TronKit/Core/SyncTimer.swift` | esenbekkd@gmail.com | 0.47 | 2 | other |

| INFORMATIONAL | `Sources/TronKit/Decorations/DecorationManager.swift` | esenbekkd@gmail.com | 0.47 | 2 | other |

| INFORMATIONAL | `Sources/TronKit/Events/Event.swift` | esenbekkd@gmail.com | 0.48 | 2 | other |

| INFORMATIONAL | `Sources/TronKit/Storage/SyncerStorage.swift` | esenbekkd@gmail.com | 0.48 | 2 | other |

| INFORMATIONAL | `iOS Example/Sources/Controllers/Trc20SendController.swift` | esenbekkd@gmail.com | 0.48 | 2 | other |

| INFORMATIONAL | `Sources/TronKit/Models/Records/Trc20EventRecord.swift` | esenbekkd@gmail.com | 0.48 | 2 | other |

| INFORMATIONAL | `iOS Example/Sources/Controllers/MainController.swift` | esenbekkd@gmail.com | 0.48 | 2 | other |

| INFORMATIONAL | `iOS Example/Sources/Adapters/TrxAdapter.swift` | esenbekkd@gmail.com | 0.48 | 2 | other |

| INFORMATIONAL | `iOS Example/Sources/Controllers/SendController.swift` | esenbekkd@gmail.com | 0.48 | 2 | other |

| INFORMATIONAL | `Sources/TronKit/Models/Records/InternalTransaction.swift` | esenbekkd@gmail.com | 0.48 | 2 | other |

| INFORMATIONAL | `Sources/TronKit/Core/Syncer.swift` | esenbekkd@gmail.com | 0.48 | 2 | other |

| INFORMATIONAL | `Sources/TronKit/Core/ChainParameterManager.swift` | esenbekkd@gmail.com | 0.49 | 2 | other |

| INFORMATIONAL | `Sources/TronKit/TronGrid/ExtensionApi/Trc20TransactionResponse.swift` | esenbekkd@gmail.com | 0.49 | 2 | other |

| INFORMATIONAL | `Sources/TronKit/Decorations/Trc20TransactionDecorator.swift` | esenbekkd@gmail.com | 0.49 | 2 | other |

| INFORMATIONAL | `iOS Example/Sources/Controllers/WordsController.swift` | esenbekkd@gmail.com | 0.49 | 2 | other |

| INFORMATIONAL | `Sources/TronKit/Core/Trc20DataProvider.swift` | esenbekkd@gmail.com | 0.49 | 2 | other |

| INFORMATIONAL | `Sources/TronKit/Core/AccountInfoManager.swift` | esenbekkd@gmail.com | 0.49 | 2 | other |

| INFORMATIONAL | `Sources/TronKit/Models/Contract/Contract.swift` | esenbekkd@gmail.com | 0.49 | 3 | other |

| INFORMATIONAL | `Sources/TronKit/Storage/AccountInfoStorage.swift` | esenbekkd@gmail.com | 0.49 | 2 | other |

| INFORMATIONAL | `iOS Example/iOS Example.xcodeproj/project.pbxproj` | esenbekkd@gmail.com | 0.50 | 2 | other |

| INFORMATIONAL | `CHANGELOG.md` | esenbekkd@gmail.com | 0.50 | 1 | other |

| INFORMATIONAL | `.gitignore` | esenbekkd@gmail.com | 0.50 | 1 | other |

| INFORMATIONAL | `Sources/TronKit/SmartContract/ContractMethodFactories.swift` | esenbekkd@gmail.com | 0.50 | 1 | other |

| INFORMATIONAL | `iOS Example/Sources/Core/TransactionRecord.swift` | esenbekkd@gmail.com | 0.50 | 1 | other |

| INFORMATIONAL | `Sources/TronKit/SmartContract/Trc20/TransferMethod.swift` | esenbekkd@gmail.com | 0.50 | 1 | other |

| INFORMATIONAL | `Sources/TronKit/SmartContract/ContractMethod.swift` | esenbekkd@gmail.com | 0.50 | 1 | other |

| INFORMATIONAL | `Sources/TronKit/SmartContract/Trc20/BalanceOfMethod.swift` | esenbekkd@gmail.com | 0.50 | 1 | other |

| INFORMATIONAL | `Sources/TronKit/SmartContract/Trc20/ApproveMethod.swift` | esenbekkd@gmail.com | 0.50 | 1 | other |

| INFORMATIONAL | `Sources/TronKit/Models/Contract/SupportedContract.swift` | esenbekkd@gmail.com | 0.50 | 1 | other |

| INFORMATIONAL | `Sources/TronKit/SmartContract/Trc20/AllowanceMethod.swift` | esenbekkd@gmail.com | 0.50 | 1 | other |

| INFORMATIONAL | `Sources/TronKit/Models/Network.swift` | esenbekkd@gmail.com | 0.50 | 1 | other |

| INFORMATIONAL | `.swift-version` | ealymbaev@gmail.com | 0.50 | 1 | other |

| INFORMATIONAL | `Sources/TronKit/Models/FullTransaction.swift` | esenbekkd@gmail.com | 0.50 | 1 | other |

| INFORMATIONAL | `Sources/TronKit/Models/TagToken.swift` | ant013@mail.ru | 0.50 | 1 | other |

| INFORMATIONAL | `Sources/TronKit/TronGrid/FullNode/SignedTransaction.swift` | anton.stavnichiy@gmail.com | 0.50 | 1 | other |

| INFORMATIONAL | `iOS Example/Sources/Controllers/ReceiveController.swift` | esenbekkd@gmail.com | 0.50 | 1 | other |

| INFORMATIONAL | `Sources/TronKit/TronGrid/JsonRpc/IntJsonRpc.swift` | esenbekkd@gmail.com | 0.50 | 1 | other |

| INFORMATIONAL | `Sources/TronKit/Core/AllowanceManager.swift` | anton.stavnichiy@gmail.com | 0.50 | 1 | other |

| INFORMATIONAL | `Sources/TronKit/TronGrid/JsonRpc/DataJsonRpc.swift` | esenbekkd@gmail.com | 0.50 | 1 | other |

| INFORMATIONAL | `Sources/TronKit/TronGrid/JsonRpc/BlockNumberJsonRpc.swift` | esenbekkd@gmail.com | 0.50 | 1 | other |

| INFORMATIONAL | `Sources/TronKit/TronGrid/FullNode/ChainParameterResponse.swift` | esenbekkd@gmail.com | 0.50 | 1 | other |


**Summary:** 100 files analysed,
0 with diffuse ownership (top owner weight < 0.2).


*Provenance: run `5bdaddec-a6ff-4aa2-8573-f631d6cabee7`.*


---


## Cross-Repo Version Skew


No findings — extractor `cross_repo_version_skew` ran at `3dcffdd5-f262-4e25-a365-6557f7bc6e95`,
found 0 version skew instances.


*Provenance: run `3dcffdd5-f262-4e25-a365-6557f7bc6e95`.*


---


## Coding Conventions


*10 conventions found (capped at 100).*

| Severity | Module | Rule | Dominant Choice | Confidence | Samples | Outliers | Source |
|----------|--------|------|-----------------|------------|---------|----------|--------|

| HIGH | TronKit | `naming.type_class` | `upper_camel` | heuristic | 370 | 165 | library |

| HIGH | TronKit | `structural.adt_pattern` | `enum` | heuristic | 74 | 28 | library |

| HIGH | TronKit | `idiom.collection_init` | `literal_empty` | heuristic | 86 | 15 | library |

| HIGH | Controllers | `idiom.collection_init` | `constructor` | heuristic | 6 | 1 | example |

| HIGH | TronKit | `structural.error_modeling` | `throws` | heuristic | 185 | 27 | library |

| LOW | Adapters | `idiom.computed_vs_property` | `computed_property` | heuristic | 12 | 0 | example |

| LOW | Controllers | `naming.type_class` | `upper_camel` | heuristic | 16 | 0 | example |

| LOW | Controllers | `structural.adt_pattern` | `class_hierarchy` | heuristic | 8 | 0 | example |

| LOW | TronKit | `idiom.computed_vs_property` | `computed_property` | heuristic | 314 | 0 | library |

| LOW | TronKit | `naming.module_protocol` | `other` | heuristic | 7 | 0 | library |



### TronKit · `naming.type_class` violations

| Severity | File | Line | Message |
|----------|------|------|---------|

| HIGH | `Sources/TronKit/Proto/Discover.pb.swift` | 18 | naming.type_class prefers other; found _GeneratedWithProtocGenSwiftVersion in Sources/TronKit/Proto/Discover.pb.swift |

| HIGH | `Sources/TronKit/Proto/Discover.pb.swift` | 19 | naming.type_class prefers upper_snake; found _2 in Sources/TronKit/Proto/Discover.pb.swift |

| HIGH | `Sources/TronKit/Proto/Discover.pb.swift` | 22 | naming.type_class prefers other; found Protocol_Endpoint in Sources/TronKit/Proto/Discover.pb.swift |

| HIGH | `Sources/TronKit/Proto/Discover.pb.swift` | 38 | naming.type_class prefers other; found Protocol_PingMessage in Sources/TronKit/Proto/Discover.pb.swift |

| HIGH | `Sources/TronKit/Proto/Discover.pb.swift` | 75 | naming.type_class prefers other; found Protocol_PongMessage in Sources/TronKit/Proto/Discover.pb.swift |

| HIGH | `Sources/TronKit/Proto/Discover.pb.swift` | 101 | naming.type_class prefers other; found Protocol_FindNeighbours in Sources/TronKit/Proto/Discover.pb.swift |

| HIGH | `Sources/TronKit/Proto/Discover.pb.swift` | 127 | naming.type_class prefers other; found Protocol_Neighbours in Sources/TronKit/Proto/Discover.pb.swift |

| HIGH | `Sources/TronKit/Proto/Discover.pb.swift` | 153 | naming.type_class prefers other; found Protocol_BackupMessage in Sources/TronKit/Proto/Discover.pb.swift |

| HIGH | `Sources/TronKit/Proto/Tron.pb.swift` | 18 | naming.type_class prefers other; found _GeneratedWithProtocGenSwiftVersion in Sources/TronKit/Proto/Tron.pb.swift |

| HIGH | `Sources/TronKit/Proto/Tron.pb.swift` | 19 | naming.type_class prefers upper_snake; found _2 in Sources/TronKit/Proto/Tron.pb.swift |

| HIGH | `Sources/TronKit/Proto/Tron.pb.swift` | 198 | naming.type_class prefers other; found Protocol_AccountId in Sources/TronKit/Proto/Tron.pb.swift |

| HIGH | `Sources/TronKit/Proto/Tron.pb.swift` | 213 | naming.type_class prefers other; found Protocol_Vote in Sources/TronKit/Proto/Tron.pb.swift |

| HIGH | `Sources/TronKit/Proto/Tron.pb.swift` | 230 | naming.type_class prefers other; found Protocol_Proposal in Sources/TronKit/Proto/Tron.pb.swift |

| HIGH | `Sources/TronKit/Proto/Tron.pb.swift` | 302 | naming.type_class prefers other; found Protocol_Exchange in Sources/TronKit/Proto/Tron.pb.swift |

| HIGH | `Sources/TronKit/Proto/Tron.pb.swift` | 327 | naming.type_class prefers other; found Protocol_MarketOrder in Sources/TronKit/Proto/Tron.pb.swift |

| HIGH | `Sources/TronKit/Proto/Tron.pb.swift` | 406 | naming.type_class prefers other; found Protocol_MarketOrderList in Sources/TronKit/Proto/Tron.pb.swift |

| HIGH | `Sources/TronKit/Proto/Tron.pb.swift` | 418 | naming.type_class prefers other; found Protocol_MarketOrderPairList in Sources/TronKit/Proto/Tron.pb.swift |

| HIGH | `Sources/TronKit/Proto/Tron.pb.swift` | 430 | naming.type_class prefers other; found Protocol_MarketOrderPair in Sources/TronKit/Proto/Tron.pb.swift |

| HIGH | `Sources/TronKit/Proto/Tron.pb.swift` | 444 | naming.type_class prefers other; found Protocol_MarketAccountOrder in Sources/TronKit/Proto/Tron.pb.swift |

| HIGH | `Sources/TronKit/Proto/Tron.pb.swift` | 464 | naming.type_class prefers other; found Protocol_MarketPrice in Sources/TronKit/Proto/Tron.pb.swift |

| HIGH | `Sources/TronKit/Proto/Tron.pb.swift` | 478 | naming.type_class prefers other; found Protocol_MarketPriceList in Sources/TronKit/Proto/Tron.pb.swift |

| HIGH | `Sources/TronKit/Proto/Tron.pb.swift` | 494 | naming.type_class prefers other; found Protocol_MarketOrderIdList in Sources/TronKit/Proto/Tron.pb.swift |

| HIGH | `Sources/TronKit/Proto/Tron.pb.swift` | 508 | naming.type_class prefers other; found Protocol_ChainParameters in Sources/TronKit/Proto/Tron.pb.swift |

| HIGH | `Sources/TronKit/Proto/Tron.pb.swift` | 536 | naming.type_class prefers other; found Protocol_Account in Sources/TronKit/Proto/Tron.pb.swift |

| HIGH | `Sources/TronKit/Proto/Tron.pb.swift` | 889 | naming.type_class prefers other; found Protocol_Key in Sources/TronKit/Proto/Tron.pb.swift |

| HIGH | `Sources/TronKit/Proto/Tron.pb.swift` | 903 | naming.type_class prefers other; found Protocol_DelegatedResource in Sources/TronKit/Proto/Tron.pb.swift |

| HIGH | `Sources/TronKit/Proto/Tron.pb.swift` | 925 | naming.type_class prefers other; found Protocol_authority in Sources/TronKit/Proto/Tron.pb.swift |

| HIGH | `Sources/TronKit/Proto/Tron.pb.swift` | 949 | naming.type_class prefers other; found Protocol_Permission in Sources/TronKit/Proto/Tron.pb.swift |

| HIGH | `Sources/TronKit/Proto/Tron.pb.swift` | 1020 | naming.type_class prefers other; found Protocol_Witness in Sources/TronKit/Proto/Tron.pb.swift |

| HIGH | `Sources/TronKit/Proto/Tron.pb.swift` | 1049 | naming.type_class prefers other; found Protocol_Votes in Sources/TronKit/Proto/Tron.pb.swift |

| HIGH | `Sources/TronKit/Proto/Tron.pb.swift` | 1064 | naming.type_class prefers other; found Protocol_TXOutput in Sources/TronKit/Proto/Tron.pb.swift |

| HIGH | `Sources/TronKit/Proto/Tron.pb.swift` | 1078 | naming.type_class prefers other; found Protocol_TXInput in Sources/TronKit/Proto/Tron.pb.swift |

| HIGH | `Sources/TronKit/Proto/Tron.pb.swift` | 1097 | naming.type_class prefers other; found raw in Sources/TronKit/Proto/Tron.pb.swift |

| HIGH | `Sources/TronKit/Proto/Tron.pb.swift` | 1118 | naming.type_class prefers other; found Protocol_TXOutputs in Sources/TronKit/Proto/Tron.pb.swift |

| HIGH | `Sources/TronKit/Proto/Tron.pb.swift` | 1130 | naming.type_class prefers other; found Protocol_ResourceReceipt in Sources/TronKit/Proto/Tron.pb.swift |

| HIGH | `Sources/TronKit/Proto/Tron.pb.swift` | 1156 | naming.type_class prefers other; found Protocol_MarketOrderDetail in Sources/TronKit/Proto/Tron.pb.swift |

| HIGH | `Sources/TronKit/Proto/Tron.pb.swift` | 1174 | naming.type_class prefers other; found Protocol_Transaction in Sources/TronKit/Proto/Tron.pb.swift |

| HIGH | `Sources/TronKit/Proto/Tron.pb.swift` | 1501 | naming.type_class prefers other; found raw in Sources/TronKit/Proto/Tron.pb.swift |

| HIGH | `Sources/TronKit/Proto/Tron.pb.swift` | 1619 | naming.type_class prefers other; found Protocol_TransactionInfo in Sources/TronKit/Proto/Tron.pb.swift |

| HIGH | `Sources/TronKit/Proto/Tron.pb.swift` | 1806 | naming.type_class prefers other; found Protocol_TransactionRet in Sources/TronKit/Proto/Tron.pb.swift |

| HIGH | `Sources/TronKit/Proto/Tron.pb.swift` | 1822 | naming.type_class prefers other; found Protocol_Transactions in Sources/TronKit/Proto/Tron.pb.swift |

| HIGH | `Sources/TronKit/Proto/Tron.pb.swift` | 1834 | naming.type_class prefers other; found Protocol_BlockHeader in Sources/TronKit/Proto/Tron.pb.swift |

| HIGH | `Sources/TronKit/Proto/Tron.pb.swift` | 1853 | naming.type_class prefers other; found raw in Sources/TronKit/Proto/Tron.pb.swift |

| HIGH | `Sources/TronKit/Proto/Tron.pb.swift` | 1888 | naming.type_class prefers other; found Protocol_Block in Sources/TronKit/Proto/Tron.pb.swift |

| HIGH | `Sources/TronKit/Proto/Tron.pb.swift` | 1911 | naming.type_class prefers other; found Protocol_ChainInventory in Sources/TronKit/Proto/Tron.pb.swift |

| HIGH | `Sources/TronKit/Proto/Tron.pb.swift` | 1941 | naming.type_class prefers other; found Protocol_BlockInventory in Sources/TronKit/Proto/Tron.pb.swift |

| HIGH | `Sources/TronKit/Proto/Tron.pb.swift` | 2011 | naming.type_class prefers other; found Protocol_Inventory in Sources/TronKit/Proto/Tron.pb.swift |

| HIGH | `Sources/TronKit/Proto/Tron.pb.swift` | 2064 | naming.type_class prefers other; found Protocol_Items in Sources/TronKit/Proto/Tron.pb.swift |

| HIGH | `Sources/TronKit/Proto/Tron.pb.swift` | 2131 | naming.type_class prefers other; found Protocol_DynamicProperties in Sources/TronKit/Proto/Tron.pb.swift |

| HIGH | `Sources/TronKit/Proto/Tron.pb.swift` | 2142 | naming.type_class prefers other; found Protocol_DisconnectMessage in Sources/TronKit/Proto/Tron.pb.swift |

| HIGH | `Sources/TronKit/Proto/Tron.pb.swift` | 2154 | naming.type_class prefers other; found Protocol_HelloMessage in Sources/TronKit/Proto/Tron.pb.swift |

| HIGH | `Sources/TronKit/Proto/Tron.pb.swift` | 2235 | naming.type_class prefers other; found Protocol_InternalTransaction in Sources/TronKit/Proto/Tron.pb.swift |

| HIGH | `Sources/TronKit/Proto/Tron.pb.swift` | 2279 | naming.type_class prefers other; found Protocol_DelegatedResourceAccountIndex in Sources/TronKit/Proto/Tron.pb.swift |

| HIGH | `Sources/TronKit/Proto/Tron.pb.swift` | 2297 | naming.type_class prefers other; found Protocol_NodeInfo in Sources/TronKit/Proto/Tron.pb.swift |

| HIGH | `Sources/TronKit/Proto/Tron.pb.swift` | 2699 | naming.type_class prefers other; found Protocol_MetricsInfo in Sources/TronKit/Proto/Tron.pb.swift |

| HIGH | `Sources/TronKit/Proto/Tron.pb.swift` | 3160 | naming.type_class prefers other; found Protocol_PBFTMessage in Sources/TronKit/Proto/Tron.pb.swift |

| HIGH | `Sources/TronKit/Proto/Tron.pb.swift` | 3290 | naming.type_class prefers other; found Protocol_PBFTCommitResult in Sources/TronKit/Proto/Tron.pb.swift |

| HIGH | `Sources/TronKit/Proto/Tron.pb.swift` | 3304 | naming.type_class prefers other; found Protocol_SRL in Sources/TronKit/Proto/Tron.pb.swift |

| HIGH | `Sources/TronKit/Proto/Tron.pb.swift` | 4168 | naming.type_class prefers other; found _StorageClass in Sources/TronKit/Proto/Tron.pb.swift |

| HIGH | `Sources/TronKit/Proto/Tron.pb.swift` | 5760 | naming.type_class prefers other; found _StorageClass in Sources/TronKit/Proto/Tron.pb.swift |

| HIGH | `Sources/TronKit/Proto/Tron.pb.swift` | 6889 | naming.type_class prefers other; found _StorageClass in Sources/TronKit/Proto/Tron.pb.swift |

| HIGH | `Sources/TronKit/Proto/Tron.pb.swift` | 7051 | naming.type_class prefers other; found _StorageClass in Sources/TronKit/Proto/Tron.pb.swift |

| HIGH | `Sources/TronKit/Proto/Tron.pb.swift` | 7301 | naming.type_class prefers other; found _StorageClass in Sources/TronKit/Proto/Tron.pb.swift |

| HIGH | `Sources/TronKit/Proto/Tron.pb.swift` | 7835 | naming.type_class prefers other; found _StorageClass in Sources/TronKit/Proto/Tron.pb.swift |

| HIGH | `Sources/TronKit/Proto/Tron.pb.swift` | 8135 | naming.type_class prefers other; found _StorageClass in Sources/TronKit/Proto/Tron.pb.swift |

| HIGH | `Sources/TronKit/Proto/TronInventoryItems.pb.swift` | 18 | naming.type_class prefers other; found _GeneratedWithProtocGenSwiftVersion in Sources/TronKit/Proto/TronInventoryItems.pb.swift |

| HIGH | `Sources/TronKit/Proto/TronInventoryItems.pb.swift` | 19 | naming.type_class prefers upper_snake; found _2 in Sources/TronKit/Proto/TronInventoryItems.pb.swift |

| HIGH | `Sources/TronKit/Proto/TronInventoryItems.pb.swift` | 22 | naming.type_class prefers other; found Protocol_InventoryItems in Sources/TronKit/Proto/TronInventoryItems.pb.swift |

| HIGH | `Sources/TronKit/Proto/contract/account_contract.pb.swift` | 32 | naming.type_class prefers other; found _GeneratedWithProtocGenSwiftVersion in Sources/TronKit/Proto/contract/account_contract.pb.swift |

| HIGH | `Sources/TronKit/Proto/contract/account_contract.pb.swift` | 33 | naming.type_class prefers upper_snake; found _2 in Sources/TronKit/Proto/contract/account_contract.pb.swift |

| HIGH | `Sources/TronKit/Proto/contract/account_contract.pb.swift` | 36 | naming.type_class prefers other; found Protocol_AccountCreateContract in Sources/TronKit/Proto/contract/account_contract.pb.swift |

| HIGH | `Sources/TronKit/Proto/contract/account_contract.pb.swift` | 54 | naming.type_class prefers other; found Protocol_AccountUpdateContract in Sources/TronKit/Proto/contract/account_contract.pb.swift |

| HIGH | `Sources/TronKit/Proto/contract/account_contract.pb.swift` | 69 | naming.type_class prefers other; found Protocol_SetAccountIdContract in Sources/TronKit/Proto/contract/account_contract.pb.swift |

| HIGH | `Sources/TronKit/Proto/contract/account_contract.pb.swift` | 82 | naming.type_class prefers other; found Protocol_AccountPermissionUpdateContract in Sources/TronKit/Proto/contract/account_contract.pb.swift |

| HIGH | `Sources/TronKit/Proto/contract/asset_issue_contract.pb.swift` | 18 | naming.type_class prefers other; found _GeneratedWithProtocGenSwiftVersion in Sources/TronKit/Proto/contract/asset_issue_contract.pb.swift |

| HIGH | `Sources/TronKit/Proto/contract/asset_issue_contract.pb.swift` | 19 | naming.type_class prefers upper_snake; found _2 in Sources/TronKit/Proto/contract/asset_issue_contract.pb.swift |

| HIGH | `Sources/TronKit/Proto/contract/asset_issue_contract.pb.swift` | 22 | naming.type_class prefers other; found Protocol_AssetIssueContract in Sources/TronKit/Proto/contract/asset_issue_contract.pb.swift |

| HIGH | `Sources/TronKit/Proto/contract/asset_issue_contract.pb.swift` | 144 | naming.type_class prefers other; found Protocol_TransferAssetContract in Sources/TronKit/Proto/contract/asset_issue_contract.pb.swift |

| HIGH | `Sources/TronKit/Proto/contract/asset_issue_contract.pb.swift` | 163 | naming.type_class prefers other; found Protocol_UnfreezeAssetContract in Sources/TronKit/Proto/contract/asset_issue_contract.pb.swift |

| HIGH | `Sources/TronKit/Proto/contract/asset_issue_contract.pb.swift` | 175 | naming.type_class prefers other; found Protocol_UpdateAssetContract in Sources/TronKit/Proto/contract/asset_issue_contract.pb.swift |

| HIGH | `Sources/TronKit/Proto/contract/asset_issue_contract.pb.swift` | 195 | naming.type_class prefers other; found Protocol_ParticipateAssetIssueContract in Sources/TronKit/Proto/contract/asset_issue_contract.pb.swift |

| HIGH | `Sources/TronKit/Proto/contract/asset_issue_contract.pb.swift` | 252 | naming.type_class prefers other; found _StorageClass in Sources/TronKit/Proto/contract/asset_issue_contract.pb.swift |

| HIGH | `Sources/TronKit/Proto/contract/balance_contract.pb.swift` | 18 | naming.type_class prefers other; found _GeneratedWithProtocGenSwiftVersion in Sources/TronKit/Proto/contract/balance_contract.pb.swift |

| HIGH | `Sources/TronKit/Proto/contract/balance_contract.pb.swift` | 19 | naming.type_class prefers upper_snake; found _2 in Sources/TronKit/Proto/contract/balance_contract.pb.swift |

| HIGH | `Sources/TronKit/Proto/contract/balance_contract.pb.swift` | 22 | naming.type_class prefers other; found Protocol_FreezeBalanceContract in Sources/TronKit/Proto/contract/balance_contract.pb.swift |

| HIGH | `Sources/TronKit/Proto/contract/balance_contract.pb.swift` | 42 | naming.type_class prefers other; found Protocol_UnfreezeBalanceContract in Sources/TronKit/Proto/contract/balance_contract.pb.swift |

| HIGH | `Sources/TronKit/Proto/contract/balance_contract.pb.swift` | 58 | naming.type_class prefers other; found Protocol_WithdrawBalanceContract in Sources/TronKit/Proto/contract/balance_contract.pb.swift |

| HIGH | `Sources/TronKit/Proto/contract/balance_contract.pb.swift` | 70 | naming.type_class prefers other; found Protocol_TransferContract in Sources/TronKit/Proto/contract/balance_contract.pb.swift |

| HIGH | `Sources/TronKit/Proto/contract/balance_contract.pb.swift` | 86 | naming.type_class prefers other; found Protocol_TransactionBalanceTrace in Sources/TronKit/Proto/contract/balance_contract.pb.swift |

| HIGH | `Sources/TronKit/Proto/contract/balance_contract.pb.swift` | 120 | naming.type_class prefers other; found Protocol_BlockBalanceTrace in Sources/TronKit/Proto/contract/balance_contract.pb.swift |

| HIGH | `Sources/TronKit/Proto/contract/balance_contract.pb.swift` | 161 | naming.type_class prefers other; found Protocol_AccountTrace in Sources/TronKit/Proto/contract/balance_contract.pb.swift |

| HIGH | `Sources/TronKit/Proto/contract/balance_contract.pb.swift` | 175 | naming.type_class prefers other; found Protocol_AccountIdentifier in Sources/TronKit/Proto/contract/balance_contract.pb.swift |

| HIGH | `Sources/TronKit/Proto/contract/balance_contract.pb.swift` | 187 | naming.type_class prefers other; found Protocol_AccountBalanceRequest in Sources/TronKit/Proto/contract/balance_contract.pb.swift |

| HIGH | `Sources/TronKit/Proto/contract/balance_contract.pb.swift` | 220 | naming.type_class prefers other; found Protocol_AccountBalanceResponse in Sources/TronKit/Proto/contract/balance_contract.pb.swift |

| HIGH | `Sources/TronKit/Proto/contract/balance_contract.pb.swift` | 244 | naming.type_class prefers other; found Protocol_FreezeBalanceV2Contract in Sources/TronKit/Proto/contract/balance_contract.pb.swift |

| HIGH | `Sources/TronKit/Proto/contract/balance_contract.pb.swift` | 260 | naming.type_class prefers other; found Protocol_UnfreezeBalanceV2Contract in Sources/TronKit/Proto/contract/balance_contract.pb.swift |

| HIGH | `Sources/TronKit/Proto/contract/balance_contract.pb.swift` | 276 | naming.type_class prefers other; found Protocol_WithdrawExpireUnfreezeContract in Sources/TronKit/Proto/contract/balance_contract.pb.swift |

| HIGH | `Sources/TronKit/Proto/contract/balance_contract.pb.swift` | 288 | naming.type_class prefers other; found Protocol_DelegateResourceContract in Sources/TronKit/Proto/contract/balance_contract.pb.swift |

| HIGH | `Sources/TronKit/Proto/contract/balance_contract.pb.swift` | 308 | naming.type_class prefers other; found Protocol_UnDelegateResourceContract in Sources/TronKit/Proto/contract/balance_contract.pb.swift |

| HIGH | `Sources/TronKit/Proto/contract/common.pb.swift` | 18 | naming.type_class prefers other; found _GeneratedWithProtocGenSwiftVersion in Sources/TronKit/Proto/contract/common.pb.swift |

| HIGH | `Sources/TronKit/Proto/contract/common.pb.swift` | 19 | naming.type_class prefers upper_snake; found _2 in Sources/TronKit/Proto/contract/common.pb.swift |

| HIGH | `Sources/TronKit/Proto/contract/exchange_contract.pb.swift` | 18 | naming.type_class prefers other; found _GeneratedWithProtocGenSwiftVersion in Sources/TronKit/Proto/contract/exchange_contract.pb.swift |

| HIGH | `Sources/TronKit/Proto/contract/exchange_contract.pb.swift` | 19 | naming.type_class prefers upper_snake; found _2 in Sources/TronKit/Proto/contract/exchange_contract.pb.swift |

| HIGH | `Sources/TronKit/Proto/contract/exchange_contract.pb.swift` | 22 | naming.type_class prefers other; found Protocol_ExchangeCreateContract in Sources/TronKit/Proto/contract/exchange_contract.pb.swift |

| HIGH | `Sources/TronKit/Proto/contract/exchange_contract.pb.swift` | 42 | naming.type_class prefers other; found Protocol_ExchangeInjectContract in Sources/TronKit/Proto/contract/exchange_contract.pb.swift |

| HIGH | `Sources/TronKit/Proto/contract/exchange_contract.pb.swift` | 60 | naming.type_class prefers other; found Protocol_ExchangeWithdrawContract in Sources/TronKit/Proto/contract/exchange_contract.pb.swift |

| HIGH | `Sources/TronKit/Proto/contract/exchange_contract.pb.swift` | 78 | naming.type_class prefers other; found Protocol_ExchangeTransactionContract in Sources/TronKit/Proto/contract/exchange_contract.pb.swift |

| HIGH | `Sources/TronKit/Proto/contract/market_contract.pb.swift` | 18 | naming.type_class prefers other; found _GeneratedWithProtocGenSwiftVersion in Sources/TronKit/Proto/contract/market_contract.pb.swift |

| HIGH | `Sources/TronKit/Proto/contract/market_contract.pb.swift` | 19 | naming.type_class prefers upper_snake; found _2 in Sources/TronKit/Proto/contract/market_contract.pb.swift |

| HIGH | `Sources/TronKit/Proto/contract/market_contract.pb.swift` | 22 | naming.type_class prefers other; found Protocol_MarketSellAssetContract in Sources/TronKit/Proto/contract/market_contract.pb.swift |

| HIGH | `Sources/TronKit/Proto/contract/market_contract.pb.swift` | 43 | naming.type_class prefers other; found Protocol_MarketCancelOrderContract in Sources/TronKit/Proto/contract/market_contract.pb.swift |

| HIGH | `Sources/TronKit/Proto/contract/proposal_contract.pb.swift` | 18 | naming.type_class prefers other; found _GeneratedWithProtocGenSwiftVersion in Sources/TronKit/Proto/contract/proposal_contract.pb.swift |

| HIGH | `Sources/TronKit/Proto/contract/proposal_contract.pb.swift` | 19 | naming.type_class prefers upper_snake; found _2 in Sources/TronKit/Proto/contract/proposal_contract.pb.swift |

| HIGH | `Sources/TronKit/Proto/contract/proposal_contract.pb.swift` | 22 | naming.type_class prefers other; found Protocol_ProposalApproveContract in Sources/TronKit/Proto/contract/proposal_contract.pb.swift |

| HIGH | `Sources/TronKit/Proto/contract/proposal_contract.pb.swift` | 39 | naming.type_class prefers other; found Protocol_ProposalCreateContract in Sources/TronKit/Proto/contract/proposal_contract.pb.swift |

| HIGH | `Sources/TronKit/Proto/contract/proposal_contract.pb.swift` | 53 | naming.type_class prefers other; found Protocol_ProposalDeleteContract in Sources/TronKit/Proto/contract/proposal_contract.pb.swift |

| HIGH | `Sources/TronKit/Proto/contract/shield_contract.pb.swift` | 18 | naming.type_class prefers other; found _GeneratedWithProtocGenSwiftVersion in Sources/TronKit/Proto/contract/shield_contract.pb.swift |

| HIGH | `Sources/TronKit/Proto/contract/shield_contract.pb.swift` | 19 | naming.type_class prefers upper_snake; found _2 in Sources/TronKit/Proto/contract/shield_contract.pb.swift |

| HIGH | `Sources/TronKit/Proto/contract/shield_contract.pb.swift` | 22 | naming.type_class prefers other; found Protocol_AuthenticationPath in Sources/TronKit/Proto/contract/shield_contract.pb.swift |

| HIGH | `Sources/TronKit/Proto/contract/shield_contract.pb.swift` | 34 | naming.type_class prefers other; found Protocol_MerklePath in Sources/TronKit/Proto/contract/shield_contract.pb.swift |

| HIGH | `Sources/TronKit/Proto/contract/shield_contract.pb.swift` | 50 | naming.type_class prefers other; found Protocol_OutputPoint in Sources/TronKit/Proto/contract/shield_contract.pb.swift |

| HIGH | `Sources/TronKit/Proto/contract/shield_contract.pb.swift` | 64 | naming.type_class prefers other; found Protocol_OutputPointInfo in Sources/TronKit/Proto/contract/shield_contract.pb.swift |

| HIGH | `Sources/TronKit/Proto/contract/shield_contract.pb.swift` | 78 | naming.type_class prefers other; found Protocol_PedersenHash in Sources/TronKit/Proto/contract/shield_contract.pb.swift |

| HIGH | `Sources/TronKit/Proto/contract/shield_contract.pb.swift` | 90 | naming.type_class prefers other; found Protocol_IncrementalMerkleTree in Sources/TronKit/Proto/contract/shield_contract.pb.swift |

| HIGH | `Sources/TronKit/Proto/contract/shield_contract.pb.swift` | 125 | naming.type_class prefers other; found Protocol_IncrementalMerkleVoucher in Sources/TronKit/Proto/contract/shield_contract.pb.swift |

| HIGH | `Sources/TronKit/Proto/contract/shield_contract.pb.swift` | 175 | naming.type_class prefers other; found Protocol_IncrementalMerkleVoucherInfo in Sources/TronKit/Proto/contract/shield_contract.pb.swift |

| HIGH | `Sources/TronKit/Proto/contract/shield_contract.pb.swift` | 189 | naming.type_class prefers other; found Protocol_SpendDescription in Sources/TronKit/Proto/contract/shield_contract.pb.swift |

| HIGH | `Sources/TronKit/Proto/contract/shield_contract.pb.swift` | 214 | naming.type_class prefers other; found Protocol_ReceiveDescription in Sources/TronKit/Proto/contract/shield_contract.pb.swift |

| HIGH | `Sources/TronKit/Proto/contract/shield_contract.pb.swift` | 239 | naming.type_class prefers other; found Protocol_ShieldedTransferContract in Sources/TronKit/Proto/contract/shield_contract.pb.swift |

| HIGH | `Sources/TronKit/Proto/contract/smart_contract.pb.swift` | 18 | naming.type_class prefers other; found _GeneratedWithProtocGenSwiftVersion in Sources/TronKit/Proto/contract/smart_contract.pb.swift |

| HIGH | `Sources/TronKit/Proto/contract/smart_contract.pb.swift` | 19 | naming.type_class prefers upper_snake; found _2 in Sources/TronKit/Proto/contract/smart_contract.pb.swift |

| HIGH | `Sources/TronKit/Proto/contract/smart_contract.pb.swift` | 22 | naming.type_class prefers other; found Protocol_SmartContract in Sources/TronKit/Proto/contract/smart_contract.pb.swift |

| HIGH | `Sources/TronKit/Proto/contract/smart_contract.pb.swift` | 225 | naming.type_class prefers other; found Protocol_ContractState in Sources/TronKit/Proto/contract/smart_contract.pb.swift |

| HIGH | `Sources/TronKit/Proto/contract/smart_contract.pb.swift` | 241 | naming.type_class prefers other; found Protocol_CreateSmartContract in Sources/TronKit/Proto/contract/smart_contract.pb.swift |

| HIGH | `Sources/TronKit/Proto/contract/smart_contract.pb.swift` | 269 | naming.type_class prefers other; found Protocol_TriggerSmartContract in Sources/TronKit/Proto/contract/smart_contract.pb.swift |

| HIGH | `Sources/TronKit/Proto/contract/smart_contract.pb.swift` | 291 | naming.type_class prefers other; found Protocol_ClearABIContract in Sources/TronKit/Proto/contract/smart_contract.pb.swift |

| HIGH | `Sources/TronKit/Proto/contract/smart_contract.pb.swift` | 305 | naming.type_class prefers other; found Protocol_UpdateSettingContract in Sources/TronKit/Proto/contract/smart_contract.pb.swift |

| HIGH | `Sources/TronKit/Proto/contract/smart_contract.pb.swift` | 321 | naming.type_class prefers other; found Protocol_UpdateEnergyLimitContract in Sources/TronKit/Proto/contract/smart_contract.pb.swift |

| HIGH | `Sources/TronKit/Proto/contract/smart_contract.pb.swift` | 337 | naming.type_class prefers other; found Protocol_SmartContractDataWrapper in Sources/TronKit/Proto/contract/smart_contract.pb.swift |

| HIGH | `Sources/TronKit/Proto/contract/storage_contract.pb.swift` | 18 | naming.type_class prefers other; found _GeneratedWithProtocGenSwiftVersion in Sources/TronKit/Proto/contract/storage_contract.pb.swift |

| HIGH | `Sources/TronKit/Proto/contract/storage_contract.pb.swift` | 19 | naming.type_class prefers upper_snake; found _2 in Sources/TronKit/Proto/contract/storage_contract.pb.swift |

| HIGH | `Sources/TronKit/Proto/contract/storage_contract.pb.swift` | 22 | naming.type_class prefers other; found Protocol_BuyStorageBytesContract in Sources/TronKit/Proto/contract/storage_contract.pb.swift |

| HIGH | `Sources/TronKit/Proto/contract/storage_contract.pb.swift` | 37 | naming.type_class prefers other; found Protocol_BuyStorageContract in Sources/TronKit/Proto/contract/storage_contract.pb.swift |

| HIGH | `Sources/TronKit/Proto/contract/storage_contract.pb.swift` | 52 | naming.type_class prefers other; found Protocol_SellStorageContract in Sources/TronKit/Proto/contract/storage_contract.pb.swift |

| HIGH | `Sources/TronKit/Proto/contract/storage_contract.pb.swift` | 66 | naming.type_class prefers other; found Protocol_UpdateBrokerageContract in Sources/TronKit/Proto/contract/storage_contract.pb.swift |

| HIGH | `Sources/TronKit/Proto/contract/vote_asset_contract.pb.swift` | 18 | naming.type_class prefers other; found _GeneratedWithProtocGenSwiftVersion in Sources/TronKit/Proto/contract/vote_asset_contract.pb.swift |

| HIGH | `Sources/TronKit/Proto/contract/vote_asset_contract.pb.swift` | 19 | naming.type_class prefers upper_snake; found _2 in Sources/TronKit/Proto/contract/vote_asset_contract.pb.swift |

| HIGH | `Sources/TronKit/Proto/contract/vote_asset_contract.pb.swift` | 22 | naming.type_class prefers other; found Protocol_VoteAssetContract in Sources/TronKit/Proto/contract/vote_asset_contract.pb.swift |

| HIGH | `Sources/TronKit/Proto/contract/witness_contract.pb.swift` | 18 | naming.type_class prefers other; found _GeneratedWithProtocGenSwiftVersion in Sources/TronKit/Proto/contract/witness_contract.pb.swift |

| HIGH | `Sources/TronKit/Proto/contract/witness_contract.pb.swift` | 19 | naming.type_class prefers upper_snake; found _2 in Sources/TronKit/Proto/contract/witness_contract.pb.swift |

| HIGH | `Sources/TronKit/Proto/contract/witness_contract.pb.swift` | 22 | naming.type_class prefers other; found Protocol_WitnessCreateContract in Sources/TronKit/Proto/contract/witness_contract.pb.swift |

| HIGH | `Sources/TronKit/Proto/contract/witness_contract.pb.swift` | 36 | naming.type_class prefers other; found Protocol_WitnessUpdateContract in Sources/TronKit/Proto/contract/witness_contract.pb.swift |

| HIGH | `Sources/TronKit/Proto/contract/witness_contract.pb.swift` | 50 | naming.type_class prefers other; found Protocol_VoteWitnessContract in Sources/TronKit/Proto/contract/witness_contract.pb.swift |

| HIGH | `Sources/TronKit/SmartContract/ContractMethodHelper.swift` | 48 | naming.type_class prefers other; found func in Sources/TronKit/SmartContract/ContractMethodHelper.swift |

| HIGH | `Sources/TronKit/SmartContract/ContractMethodHelper.swift` | 110 | naming.type_class prefers other; found func in Sources/TronKit/SmartContract/ContractMethodHelper.swift |

| HIGH | `Sources/TronKit/SmartContract/ContractMethodHelper.swift` | 114 | naming.type_class prefers other; found func in Sources/TronKit/SmartContract/ContractMethodHelper.swift |

| HIGH | `Sources/TronKit/SmartContract/ContractMethodHelper.swift` | 127 | naming.type_class prefers other; found func in Sources/TronKit/SmartContract/ContractMethodHelper.swift |

| HIGH | `Sources/TronKit/SmartContract/ContractMethodHelper.swift` | 140 | naming.type_class prefers other; found func in Sources/TronKit/SmartContract/ContractMethodHelper.swift |

| HIGH | `Sources/TronKit/SmartContract/ContractMethodHelper.swift` | 146 | naming.type_class prefers other; found func in Sources/TronKit/SmartContract/ContractMethodHelper.swift |

| HIGH | `Sources/TronKit/SmartContract/ContractMethodHelper.swift` | 48 | naming.type_class prefers other; found func in Sources/TronKit/SmartContract/ContractMethodHelper.swift |

| HIGH | `Sources/TronKit/SmartContract/ContractMethodHelper.swift` | 110 | naming.type_class prefers other; found func in Sources/TronKit/SmartContract/ContractMethodHelper.swift |

| HIGH | `Sources/TronKit/SmartContract/ContractMethodHelper.swift` | 114 | naming.type_class prefers other; found func in Sources/TronKit/SmartContract/ContractMethodHelper.swift |

| HIGH | `Sources/TronKit/SmartContract/ContractMethodHelper.swift` | 127 | naming.type_class prefers other; found func in Sources/TronKit/SmartContract/ContractMethodHelper.swift |

| HIGH | `Sources/TronKit/SmartContract/ContractMethodHelper.swift` | 140 | naming.type_class prefers other; found func in Sources/TronKit/SmartContract/ContractMethodHelper.swift |

| HIGH | `Sources/TronKit/SmartContract/ContractMethodHelper.swift` | 146 | naming.type_class prefers other; found func in Sources/TronKit/SmartContract/ContractMethodHelper.swift |



### TronKit · `structural.adt_pattern` violations

| Severity | File | Line | Message |
|----------|------|------|---------|

| HIGH | `Sources/TronKit/Core/Trc20DataProvider.swift` | 67 | structural.adt_pattern prefers class_hierarchy; found NameMethod in Sources/TronKit/Core/Trc20DataProvider.swift |

| HIGH | `Sources/TronKit/Core/Trc20DataProvider.swift` | 71 | structural.adt_pattern prefers class_hierarchy; found SymbolMethod in Sources/TronKit/Core/Trc20DataProvider.swift |

| HIGH | `Sources/TronKit/Core/Trc20DataProvider.swift` | 76 | structural.adt_pattern prefers class_hierarchy; found DecimalsMethod in Sources/TronKit/Core/Trc20DataProvider.swift |

| HIGH | `Sources/TronKit/Decorations/NativeTransactionDecoration.swift` | 1 | structural.adt_pattern prefers class_hierarchy; found NativeTransactionDecoration in Sources/TronKit/Decorations/NativeTransactionDecoration.swift |

| HIGH | `Sources/TronKit/Decorations/SmartContract/ApproveEip20Decoration.swift` | 2 | structural.adt_pattern prefers class_hierarchy; found ApproveEip20Decoration in Sources/TronKit/Decorations/SmartContract/ApproveEip20Decoration.swift |

| HIGH | `Sources/TronKit/Decorations/SmartContract/OutgoingEip20Decoration.swift` | 2 | structural.adt_pattern prefers class_hierarchy; found OutgoingEip20Decoration in Sources/TronKit/Decorations/SmartContract/OutgoingEip20Decoration.swift |

| HIGH | `Sources/TronKit/Decorations/UnknownTransactionDecoration.swift` | 3 | structural.adt_pattern prefers class_hierarchy; found UnknownTransactionDecoration in Sources/TronKit/Decorations/UnknownTransactionDecoration.swift |

| HIGH | `Sources/TronKit/Events/Trc20ApproveEvent.swift` | 2 | structural.adt_pattern prefers class_hierarchy; found Trc20ApproveEvent in Sources/TronKit/Events/Trc20ApproveEvent.swift |

| HIGH | `Sources/TronKit/Events/Trc20TransferEvent.swift` | 2 | structural.adt_pattern prefers class_hierarchy; found Trc20TransferEvent in Sources/TronKit/Events/Trc20TransferEvent.swift |

| HIGH | `Sources/TronKit/Models/Records/Balance.swift` | 3 | structural.adt_pattern prefers class_hierarchy; found Balance in Sources/TronKit/Models/Records/Balance.swift |

| HIGH | `Sources/TronKit/Models/Records/ChainParameter.swift` | 2 | structural.adt_pattern prefers class_hierarchy; found ChainParameter in Sources/TronKit/Models/Records/ChainParameter.swift |

| HIGH | `Sources/TronKit/Models/Records/InternalTransaction.swift` | 3 | structural.adt_pattern prefers class_hierarchy; found InternalTransaction in Sources/TronKit/Models/Records/InternalTransaction.swift |

| HIGH | `Sources/TronKit/Models/Records/LastBlockHeight.swift` | 2 | structural.adt_pattern prefers class_hierarchy; found LastBlockHeight in Sources/TronKit/Models/Records/LastBlockHeight.swift |

| HIGH | `Sources/TronKit/Models/Records/Transaction.swift` | 4 | structural.adt_pattern prefers class_hierarchy; found Transaction in Sources/TronKit/Models/Records/Transaction.swift |

| HIGH | `Sources/TronKit/Models/Records/TransactionSyncTimestamp.swift` | 2 | structural.adt_pattern prefers class_hierarchy; found TransactionSyncTimestamp in Sources/TronKit/Models/Records/TransactionSyncTimestamp.swift |

| HIGH | `Sources/TronKit/Models/Records/TransactionTagRecord.swift` | 3 | structural.adt_pattern prefers class_hierarchy; found TransactionTagRecord in Sources/TronKit/Models/Records/TransactionTagRecord.swift |

| HIGH | `Sources/TronKit/Models/Records/Trc20EventRecord.swift` | 4 | structural.adt_pattern prefers class_hierarchy; found Trc20EventRecord in Sources/TronKit/Models/Records/Trc20EventRecord.swift |

| HIGH | `Sources/TronKit/SmartContract/Trc20/AllowanceMethod.swift` | 1 | structural.adt_pattern prefers class_hierarchy; found AllowanceMethod in Sources/TronKit/SmartContract/Trc20/AllowanceMethod.swift |

| HIGH | `Sources/TronKit/SmartContract/Trc20/ApproveMethod.swift` | 2 | structural.adt_pattern prefers class_hierarchy; found ApproveMethod in Sources/TronKit/SmartContract/Trc20/ApproveMethod.swift |

| HIGH | `Sources/TronKit/SmartContract/Trc20/ApproveMethodFactory.swift` | 3 | structural.adt_pattern prefers class_hierarchy; found ApproveMethodFactory in Sources/TronKit/SmartContract/Trc20/ApproveMethodFactory.swift |

| HIGH | `Sources/TronKit/SmartContract/Trc20/BalanceOfMethod.swift` | 1 | structural.adt_pattern prefers class_hierarchy; found BalanceOfMethod in Sources/TronKit/SmartContract/Trc20/BalanceOfMethod.swift |

| HIGH | `Sources/TronKit/SmartContract/Trc20/TransferMethod.swift` | 2 | structural.adt_pattern prefers class_hierarchy; found TransferMethod in Sources/TronKit/SmartContract/Trc20/TransferMethod.swift |

| HIGH | `Sources/TronKit/SmartContract/Trc20/TransferMethodFactory.swift` | 3 | structural.adt_pattern prefers class_hierarchy; found TransferMethodFactory in Sources/TronKit/SmartContract/Trc20/TransferMethodFactory.swift |

| HIGH | `Sources/TronKit/TronGrid/JsonRpc/BlockNumberJsonRpc.swift` | 1 | structural.adt_pattern prefers class_hierarchy; found BlockNumberJsonRpc in Sources/TronKit/TronGrid/JsonRpc/BlockNumberJsonRpc.swift |

| HIGH | `Sources/TronKit/TronGrid/JsonRpc/CallJsonRpc.swift` | 2 | structural.adt_pattern prefers class_hierarchy; found CallJsonRpc in Sources/TronKit/TronGrid/JsonRpc/CallJsonRpc.swift |

| HIGH | `Sources/TronKit/TronGrid/JsonRpc/DataJsonRpc.swift` | 2 | structural.adt_pattern prefers class_hierarchy; found DataJsonRpc in Sources/TronKit/TronGrid/JsonRpc/DataJsonRpc.swift |

| HIGH | `Sources/TronKit/TronGrid/JsonRpc/EstimateGasJsonRpc.swift` | 3 | structural.adt_pattern prefers class_hierarchy; found EstimateGasJsonRpc in Sources/TronKit/TronGrid/JsonRpc/EstimateGasJsonRpc.swift |

| HIGH | `Sources/TronKit/TronGrid/JsonRpc/IntJsonRpc.swift` | 2 | structural.adt_pattern prefers class_hierarchy; found IntJsonRpc in Sources/TronKit/TronGrid/JsonRpc/IntJsonRpc.swift |



### TronKit · `idiom.collection_init` violations

| Severity | File | Line | Message |
|----------|------|------|---------|

| HIGH | `Sources/TronKit/Core/FeeProvider.swift` | 37 | idiom.collection_init prefers constructor; found constructor in Sources/TronKit/Core/FeeProvider.swift |

| HIGH | `Sources/TronKit/Core/TransactionManager.swift` | 138 | idiom.collection_init prefers constructor; found constructor in Sources/TronKit/Core/TransactionManager.swift |

| HIGH | `Sources/TronKit/Decorations/DecorationManager.swift` | 7 | idiom.collection_init prefers constructor; found constructor in Sources/TronKit/Decorations/DecorationManager.swift |

| HIGH | `Sources/TronKit/Decorations/NativeTransactionDecoration.swift` | 9 | idiom.collection_init prefers constructor; found constructor in Sources/TronKit/Decorations/NativeTransactionDecoration.swift |

| HIGH | `Sources/TronKit/Decorations/UnknownTransactionDecoration.swift` | 51 | idiom.collection_init prefers constructor; found constructor in Sources/TronKit/Decorations/UnknownTransactionDecoration.swift |

| HIGH | `Sources/TronKit/Decorations/UnknownTransactionDecoration.swift` | 68 | idiom.collection_init prefers constructor; found constructor in Sources/TronKit/Decorations/UnknownTransactionDecoration.swift |

| HIGH | `Sources/TronKit/Events/Trc20TransferEvent.swift` | 20 | idiom.collection_init prefers constructor; found constructor in Sources/TronKit/Events/Trc20TransferEvent.swift |

| HIGH | `Sources/TronKit/SmartContract/ContractMethodFactories.swift` | 23 | idiom.collection_init prefers constructor; found constructor in Sources/TronKit/SmartContract/ContractMethodFactories.swift |

| HIGH | `Sources/TronKit/SmartContract/ContractMethodHelper.swift` | 51 | idiom.collection_init prefers constructor; found constructor in Sources/TronKit/SmartContract/ContractMethodHelper.swift |

| HIGH | `Sources/TronKit/SmartContract/ContractMethodHelper.swift` | 118 | idiom.collection_init prefers constructor; found constructor in Sources/TronKit/SmartContract/ContractMethodHelper.swift |

| HIGH | `Sources/TronKit/SmartContract/ContractMethodHelper.swift` | 131 | idiom.collection_init prefers constructor; found constructor in Sources/TronKit/SmartContract/ContractMethodHelper.swift |

| HIGH | `Sources/TronKit/SmartContract/ContractMethodHelper.swift` | 150 | idiom.collection_init prefers constructor; found constructor in Sources/TronKit/SmartContract/ContractMethodHelper.swift |

| HIGH | `Sources/TronKit/Storage/TransactionStorage.swift` | 95 | idiom.collection_init prefers constructor; found constructor in Sources/TronKit/Storage/TransactionStorage.swift |

| HIGH | `Sources/TronKit/Storage/TransactionStorage.swift` | 103 | idiom.collection_init prefers constructor; found constructor in Sources/TronKit/Storage/TransactionStorage.swift |

| HIGH | `Sources/TronKit/TronGrid/ExtensionApi/AccountInfoResponse.swift` | 12 | idiom.collection_init prefers constructor; found constructor in Sources/TronKit/TronGrid/ExtensionApi/AccountInfoResponse.swift |



### Controllers · `idiom.collection_init` violations

| Severity | File | Line | Message |
|----------|------|------|---------|

| HIGH | `iOS Example/Sources/Controllers/TransactionsController.swift` | 41 | idiom.collection_init prefers literal_empty; found literal_empty in iOS Example/Sources/Controllers/TransactionsController.swift |



### TronKit · `structural.error_modeling` violations

| Severity | File | Line | Message |
|----------|------|------|---------|

| HIGH | `Sources/TronKit/Core/Kit.swift` | 105 | structural.error_modeling prefers nullable; found nullable in Sources/TronKit/Core/Kit.swift |

| HIGH | `Sources/TronKit/Core/TransactionManager.swift` | 54 | structural.error_modeling prefers nullable; found nullable in Sources/TronKit/Core/TransactionManager.swift |

| HIGH | `Sources/TronKit/Core/TransactionManager.swift` | 180 | structural.error_modeling prefers nullable; found nullable in Sources/TronKit/Core/TransactionManager.swift |

| HIGH | `Sources/TronKit/Core/Transforms.swift` | 6 | structural.error_modeling prefers nullable; found nullable in Sources/TronKit/Core/Transforms.swift |

| HIGH | `Sources/TronKit/Core/Transforms.swift` | 13 | structural.error_modeling prefers nullable; found nullable in Sources/TronKit/Core/Transforms.swift |

| HIGH | `Sources/TronKit/Core/Transforms.swift` | 20 | structural.error_modeling prefers nullable; found nullable in Sources/TronKit/Core/Transforms.swift |

| HIGH | `Sources/TronKit/Core/Transforms.swift` | 23 | structural.error_modeling prefers nullable; found nullable in Sources/TronKit/Core/Transforms.swift |

| HIGH | `Sources/TronKit/Core/Transforms.swift` | 30 | structural.error_modeling prefers nullable; found nullable in Sources/TronKit/Core/Transforms.swift |

| HIGH | `Sources/TronKit/Core/Transforms.swift` | 37 | structural.error_modeling prefers nullable; found nullable in Sources/TronKit/Core/Transforms.swift |

| HIGH | `Sources/TronKit/Core/Transforms.swift` | 44 | structural.error_modeling prefers nullable; found nullable in Sources/TronKit/Core/Transforms.swift |

| HIGH | `Sources/TronKit/Core/Transforms.swift` | 51 | structural.error_modeling prefers nullable; found nullable in Sources/TronKit/Core/Transforms.swift |

| HIGH | `Sources/TronKit/Core/Transforms.swift` | 58 | structural.error_modeling prefers nullable; found nullable in Sources/TronKit/Core/Transforms.swift |

| HIGH | `Sources/TronKit/Core/Transforms.swift` | 65 | structural.error_modeling prefers nullable; found nullable in Sources/TronKit/Core/Transforms.swift |

| HIGH | `Sources/TronKit/Core/Transforms.swift` | 72 | structural.error_modeling prefers nullable; found nullable in Sources/TronKit/Core/Transforms.swift |

| HIGH | `Sources/TronKit/Core/Transforms.swift` | 79 | structural.error_modeling prefers nullable; found nullable in Sources/TronKit/Core/Transforms.swift |

| HIGH | `Sources/TronKit/Core/Transforms.swift` | 86 | structural.error_modeling prefers nullable; found nullable in Sources/TronKit/Core/Transforms.swift |

| HIGH | `Sources/TronKit/Core/Transforms.swift` | 93 | structural.error_modeling prefers nullable; found nullable in Sources/TronKit/Core/Transforms.swift |

| HIGH | `Sources/TronKit/Core/Transforms.swift` | 100 | structural.error_modeling prefers nullable; found nullable in Sources/TronKit/Core/Transforms.swift |

| HIGH | `Sources/TronKit/Core/Transforms.swift` | 107 | structural.error_modeling prefers nullable; found nullable in Sources/TronKit/Core/Transforms.swift |

| HIGH | `Sources/TronKit/Core/Transforms.swift` | 114 | structural.error_modeling prefers nullable; found nullable in Sources/TronKit/Core/Transforms.swift |

| HIGH | `Sources/TronKit/Core/Transforms.swift` | 121 | structural.error_modeling prefers nullable; found nullable in Sources/TronKit/Core/Transforms.swift |

| HIGH | `Sources/TronKit/Decorations/DecorationManager.swift` | 85 | structural.error_modeling prefers nullable; found nullable in Sources/TronKit/Decorations/DecorationManager.swift |

| HIGH | `Sources/TronKit/Decorations/Trc20TransactionDecorator.swift` | 14 | structural.error_modeling prefers nullable; found nullable in Sources/TronKit/Decorations/Trc20TransactionDecorator.swift |

| HIGH | `Sources/TronKit/Storage/AccountInfoStorage.swift` | 40 | structural.error_modeling prefers nullable; found nullable in Sources/TronKit/Storage/AccountInfoStorage.swift |

| HIGH | `Sources/TronKit/Storage/SyncerStorage.swift` | 61 | structural.error_modeling prefers nullable; found nullable in Sources/TronKit/Storage/SyncerStorage.swift |

| HIGH | `Sources/TronKit/Storage/SyncerStorage.swift` | 74 | structural.error_modeling prefers nullable; found nullable in Sources/TronKit/Storage/SyncerStorage.swift |

| HIGH | `Sources/TronKit/Storage/TransactionStorage.swift` | 189 | structural.error_modeling prefers nullable; found nullable in Sources/TronKit/Storage/TransactionStorage.swift |



**Summary:** 10 conventions surfaced by the audit query.


*Provenance: run `8afcdfa8-32aa-4964-ab85-a606eb63116c`.*


---


## Testability / DI patterns


*4 findings found (capped at 100).*

| Severity | Module | Language | Style | Framework | Samples | Outliers | Confidence |
|----------|--------|----------|-------|-----------|---------|----------|------------|

| MEDIUM | Core | swift | `STANDALONE_SIGNAL` | - | 0 | 0 | heuristic |

| MEDIUM | TronKit | swift | `INIT_INJECTION` | - | 50 | 0 | heuristic |

| LOW | Adapters | swift | `INIT_INJECTION` | - | 1 | 0 | heuristic |

| LOW | Controllers | swift | `INIT_INJECTION` | - | 1 | 0 | heuristic |



### Core · `STANDALONE_SIGNAL` · MEDIUM


Test doubles: none linked for this module/style.



Untestable sites:

- **MEDIUM** `iOS Example/Sources/Core/Manager.swift:63` `direct_preferences` via `UserDefaults.standard` — Direct UserDefaults.standard access should be abstracted for tests.

- **MEDIUM** `iOS Example/Sources/Core/Manager.swift:71` `direct_preferences` via `UserDefaults.standard` — Direct UserDefaults.standard access should be abstracted for tests.

- **MEDIUM** `iOS Example/Sources/Core/Manager.swift:79` `direct_preferences` via `UserDefaults.standard` — Direct UserDefaults.standard access should be abstracted for tests.

- **MEDIUM** `iOS Example/Sources/Core/Manager.swift:80` `direct_preferences` via `UserDefaults.standard` — Direct UserDefaults.standard access should be abstracted for tests.

- **MEDIUM** `iOS Example/Sources/Core/Manager.swift:84` `direct_preferences` via `UserDefaults.standard` — Direct UserDefaults.standard access should be abstracted for tests.

- **MEDIUM** `iOS Example/Sources/Core/Manager.swift:85` `direct_preferences` via `UserDefaults.standard` — Direct UserDefaults.standard access should be abstracted for tests.

- **MEDIUM** `iOS Example/Sources/Core/Manager.swift:89` `direct_preferences` via `UserDefaults.standard` — Direct UserDefaults.standard access should be abstracted for tests.

- **MEDIUM** `iOS Example/Sources/Core/Manager.swift:90` `direct_preferences` via `UserDefaults.standard` — Direct UserDefaults.standard access should be abstracted for tests.

- **MEDIUM** `iOS Example/Sources/Core/Manager.swift:91` `direct_preferences` via `UserDefaults.standard` — Direct UserDefaults.standard access should be abstracted for tests.




### TronKit · `INIT_INJECTION` · MEDIUM


Test doubles: none linked for this module/style.



Untestable sites:

- **MEDIUM** `Sources/TronKit/Core/FeeProvider.swift:77` `direct_clock` via `Date()` — Direct Date() access should be abstracted for tests.

- **MEDIUM** `Sources/TronKit/Core/Kit.swift:172` `direct_filesystem` via `FileManager.default` — Direct FileManager.default access should be abstracted for tests.

- **MEDIUM** `Sources/TronKit/Core/Kit.swift:230` `direct_filesystem` via `FileManager.default` — Direct FileManager.default access should be abstracted for tests.




### Adapters · `INIT_INJECTION` · LOW


Test doubles: none linked for this module/style.



Untestable sites: none linked for this module/style.



### Controllers · `INIT_INJECTION` · LOW


Test doubles: none linked for this module/style.



Untestable sites: none linked for this module/style.



**Summary:** 3 patterns,
0 test doubles,
12 untestable sites.


*Provenance: run `ddcb121e-01ff-4c8e-a756-ea644411500a`.*


---



## Failed Extractors

The following extractors completed their last run with `success=False`. Their data is excluded from this report.

| Extractor | Run ID | Error Code | Message | Next Action |
|-----------|--------|------------|---------|-------------|

| `crypto_domain_model` | `3c34a967-4310-48d6-8fc4-870115b9dde3` | `—` |  | `palace.ingest.run_extractor(name="crypto_domain_model", project="tron-kit")` |



---



## Blind Spots

The following extractors have not run for project `tron-kit` and are excluded from this report:



- ⚠ `cross_module_contract` — run `palace.ingest.run_extractor(name="cross_module_contract", project="tron-kit")` to populate

- ⚠ `error_handling_policy` — run `palace.ingest.run_extractor(name="error_handling_policy", project="tron-kit")` to populate

- ⚠ `hot_path_profiler` — run `palace.ingest.run_extractor(name="hot_path_profiler", project="tron-kit")` to populate

- ⚠ `localization_accessibility` — run `palace.ingest.run_extractor(name="localization_accessibility", project="tron-kit")` to populate

- ⚠ `public_api_surface` — run `palace.ingest.run_extractor(name="public_api_surface", project="tron-kit")` to populate

- ⚠ `reactive_dependency_tracer` — run `palace.ingest.run_extractor(name="reactive_dependency_tracer", project="tron-kit")` to populate




---



## Profile Coverage

| Status | Count |
|--------|-------|
| OK | 8 |
| RUN_FAILED | 1 |
| FETCH_FAILED | 0 |
| NOT_ATTEMPTED | 6 |
| NOT_APPLICABLE | 0 |
| **Total (R)** | **15** |


---


## Provenance

| Field | Value |
|-------|-------|
| Project | `tron-kit` |
| Generated at | `2026-05-14T10:52:10.855062+00:00` |
| Fetched extractors | `arch_layer, code_ownership, coding_convention, dead_symbol_binary_surface, dependency_surface, testability_di, hotspot, cross_repo_version_skew` |
| Blind spots | `cross_module_contract, error_handling_policy, hot_path_profiler, localization_accessibility, public_api_surface, reactive_dependency_tracer` |

| `arch_layer` run ID | `a2abd2a3-fbe8-4d76-99db-505b699ad27c` |

| `code_ownership` run ID | `5bdaddec-a6ff-4aa2-8573-f631d6cabee7` |

| `coding_convention` run ID | `8afcdfa8-32aa-4964-ab85-a606eb63116c` |

| `dead_symbol_binary_surface` run ID | `eff2f9e7-6df6-4969-920c-d8d5d6bf9041` |

| `dependency_surface` run ID | `29349e73-3c7c-4f1e-b447-ac0e01dd6ba5` |

| `testability_di` run ID | `ddcb121e-01ff-4c8e-a756-ea644411500a` |

| `hotspot` run ID | `c36bf00e-9f8e-4ca8-94e6-3bf621054f9a` |

| `cross_repo_version_skew` run ID | `3dcffdd5-f262-4e25-a365-6557f7bc6e95` |




---

## Known Limitations — Suspicious Zeros (GIM-333 diagnostic, 2026-05-17)

Three "zero findings" sections in this report are NOT indicators of a clean codebase.
They are CONFIG_GAP or VALID_EMPTY results diagnosed by [GIM-333](/GIM/issues/GIM-333).
Full diagnostic: `docs/runbooks/suspicious-zero-diagnostic-2026-05-17.md`.

### `hotspot` — "scanned 0 files, found 0 issues"

**True cause:** VALID_EMPTY + TEMPLATE_BUG (RAN_SUCCESS_ZERO)

The hotspot extractor ran correctly and wrote 1,613 nodes (86 File nodes + functions).
All `hotspot_score = 0.0` because every commit predates the 90-day churn window
(TronKit's last commit was 2025-08-13; run date 2026-05-14; cutoff 2026-02-14).
With zero churn, `score = log(ccn+1) × log(0+1) = 0` for all files.

The template text "scanned 0 files" is misleading — 86 source files were processed.
See bug issue (child of [GIM-333](/GIM/issues/GIM-333)).

**Operator note:** To see hotspot results, either extend `PALACE_HOTSPOT_CHURN_WINDOW_DAYS`
to ≥280 (covering last 9 months) or re-run after TronKit receives new commits.

### `dead_symbol_binary_surface` — "found 0 dead symbol candidates"

**True cause:** CONFIG_GAP + SILENT_ZERO_BUG (RAN_SUCCESS_ZERO)

The extractor ran successfully but wrote 0 nodes because `periphery/periphery-3.7.4-swiftpm.json`
and `periphery/contract.json` are absent from the TronKit repo. Without these Periphery
fixture files, dead symbol detection is impossible. The extractor returns `success=True`
silently without surfacing `MISSING_INPUT`.

**Operator action:** Run `periphery scan` on TronKit and commit the JSON fixture to
`periphery/` before re-running this extractor.

### `cross_repo_version_skew` — "found 0 version skew instances"

**True cause:** CONFIG_GAP + VALID_EMPTY (RAN_SUCCESS_ZERO)

The extractor ran correctly but `Package.resolved` is absent from TronKit, so all
9 SPM dependencies have `resolved_version=NULL`. The skew query filters for
`size(versions) > 1`, but `collect(distinct NULL)=[]`, so no skew is found.

Additionally, TronKit is a single-module SPM library — even with a lockfile, it
cannot have intra-project version skew. This extractor targets bundle/multi-project comparisons.

**Operator action:** None required for correctness. For resolved version tracking,
commit `Package.resolved` to TronKit (run `swift package resolve`).

### `public_api_surface` and `cross_module_contract` — BLIND SPOTS (not zeros)

**Note:** These two appear as blind spots in this report (correctly). The
[GIM-333](/GIM/issues/GIM-333) issue description incorrectly characterized them
as "0 symbols" and "0 deltas" — they were never run for this project.

- `public_api_surface` (CONFIG_GAP): requires `.palace/public-api/swift/*.swiftinterface`
- `cross_module_contract` (CASCADING_EMPTY): depends on `public_api_surface` first
