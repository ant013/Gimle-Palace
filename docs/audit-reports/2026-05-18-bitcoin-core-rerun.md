# Audit Report — bitcoin-core

**Generated at:** 2026-05-18T08:03:38.078047+00:00
**Depth:** full

---


## Executive Summary

Audit of project `bitcoin-core` at depth `full`. 9 extractors contributed data. Findings by source: library=6 example=0 test=1 other=3090 ⚠ 6 extractor(s) failed their last run: `code_ownership`, `crypto_domain_model`, `dead_symbol_binary_surface`, `error_handling_policy`, `hotspot`, `localization_accessibility`. ⚠ 1 section(s) have critical/high findings requiring attention. Top findings: **HIGH** [structural.adt_pattern]; **HIGH** [structural.error_modeling]; **MEDIUM** [idiom.collection_init].

---


## Architecture layer violations



No architecture rules declared — 2 modules indexed in Neo4j (no rule evaluation possible).

The `arch_layer` extractor ran but found no rule file at
`.palace/architecture-rules.yaml` or `docs/architecture-rules.yaml`.
Module DAG was written to Neo4j. To enable rule evaluation, add a rule file
to the repository. See the runbook at `docs/runbooks/arch-layer.md`.

**Provenance:** run_id `cb4ef7f7-b74b-4b36-9046-d9c86c01eaf5`.




---


## Dependency Surface



*37 dependencies found (capped at 100).*


| PURL | Scope | Declared In | Resolved Version |
|------|-------|-------------|-----------------|

| `pkg:generic/spm-package?vcs_url=..%2FAtomicCounter%2F@unresolved` | compile | `Package.swift` | unresolved |

| `pkg:github/Alamofire/Alamofire@unresolved` | compile | `Package.swift` | unresolved |

| `pkg:github/Brightify/Cuckoo@1.9.1` | compile | `Package.swift` | 1.9.1 |

| `pkg:github/Carthage/Commandant@0.15.0` | compile | `Package.swift` | 0.15.0 |

| `pkg:github/GigaBitcoin/secp256k1.swift@unresolved` | compile | `Package.swift` | unresolved |

| `pkg:github/Quick/Nimble@10.0.0` | compile | `Package.swift` | 10.0.0 |

| `pkg:github/Quick/Nimble@9.1.0` | compile | `Package.swift` | 9.1.0 |

| `pkg:github/Quick/Quick@5.0.1` | compile | `Package.swift` | 5.0.1 |

| `pkg:github/ReactiveX/RxSwift@unresolved` | compile | `Package.swift` | unresolved |

| `pkg:github/apple/swift-atomics@unresolved` | compile | `Package.swift` | unresolved |

| `pkg:github/apple/swift-collections-benchmark@0.0.2` | compile | `Package.swift` | 0.0.2 |

| `pkg:github/apple/swift-collections@unresolved` | compile | `Package.swift` | unresolved |

| `pkg:github/apple/swift-crypto@unresolved` | compile | `Package.swift` | unresolved |

| `pkg:github/apple/swift-docc-plugin@unresolved` | compile | `Package.swift` | unresolved |

| `pkg:github/apple/swift-nio-ssl@unresolved` | compile | `Package.swift` | unresolved |

| `pkg:github/apple/swift-nio@unresolved` | compile | `Package.swift` | unresolved |

| `pkg:github/attaswift/BigInt@5.3.0` | compile | `Package.swift` | 5.3.0 |

| `pkg:github/attaswift/BigInt@unresolved` | compile | `Package.swift` | unresolved |

| `pkg:github/csjones/lefthook@unresolved` | compile | `Package.swift` | unresolved |

| `pkg:github/groue/GRDB.swift@5.26.1` | compile | `Package.swift` | 5.26.1 |

| `pkg:github/horizontalsystems/Checkpoints@1.0.2` | compile | `Package.swift` | 1.0.2 |

| `pkg:github/horizontalsystems/HdWalletKit.Swift@1.2.1` | compile | `Package.swift` | 1.2.1 |

| `pkg:github/horizontalsystems/HsCryptoKit.Swift@1.2.1` | compile | `Package.swift` | 1.2.1 |

| `pkg:github/horizontalsystems/HsCryptoKit.Swift@unresolved` | compile | `Package.swift` | unresolved |

| `pkg:github/horizontalsystems/HsExtensions.Swift@1.0.0` | compile | `Package.swift` | 1.0.0 |

| `pkg:github/horizontalsystems/HsExtensions.Swift@1.0.3` | compile | `Package.swift` | 1.0.3 |

| `pkg:github/horizontalsystems/HsExtensions.Swift@unresolved` | compile | `Package.swift` | unresolved |

| `pkg:github/horizontalsystems/HsToolKit.Swift@1.0.0` | compile | `Package.swift` | 1.0.0 |

| `pkg:github/jpsim/SourceKitten@0.21.3` | compile | `Package.swift` | 0.21.3 |

| `pkg:github/kylef/Stencil@0.14.2` | compile | `Package.swift` | 0.14.2 |

| `pkg:github/mattgallagher/CwlCatchException@unresolved` | compile | `Package.swift` | unresolved |

| `pkg:github/mattgallagher/CwlPreconditionTesting@2.0.0` | compile | `Package.swift` | 2.0.0 |

| `pkg:github/mattgallagher/CwlPreconditionTesting@2.1.0` | compile | `Package.swift` | 2.1.0 |

| `pkg:github/nicklockwood/SwiftFormat@unresolved` | compile | `Package.swift` | unresolved |

| `pkg:github/nvzqz/FileKit@unresolved` | compile | `Package.swift` | unresolved |

| `pkg:github/realm/SwiftLint@unresolved` | compile | `Package.swift` | unresolved |

| `pkg:github/tristanhimmelman/ObjectMapper@unresolved` | compile | `Package.swift` | unresolved |



**Summary:** 37 total dependencies across compile scopes.


*Provenance: run `9fb932e9-beaa-4ae7-a20b-9ebceb09eb5a`.*


---


## Cross-Repo Version Skew


No findings — extractor `cross_repo_version_skew` ran at `0da026c9-0217-449e-ad63-38392a5c0a64`,
found 0 version skew instances.


*Provenance: run `0da026c9-0217-449e-ad63-38392a5c0a64`.*


---


## Cross-Module Contract Drift


No findings — extractor `cross_module_contract` ran at `778420a2-bc4a-4c5e-b0fe-c6100e383dba`,
found 0 cross-module contract deltas.


*Provenance: run `778420a2-bc4a-4c5e-b0fe-c6100e383dba`.*


---


## Public API Surface


No findings — extractor `public_api_surface` ran at `58d501b7-d363-4c0e-a54a-b994cc00734d`,
found 0 public API symbols.


*Provenance: run `58d501b7-d363-4c0e-a54a-b994cc00734d`.*


---


## Coding Conventions


*7 conventions found (capped at 100).*

| Severity | Module | Rule | Dominant Choice | Confidence | Samples | Outliers | Source |
|----------|--------|------|-----------------|------------|---------|----------|--------|

| HIGH | BitcoinCore | `structural.adt_pattern` | `class_hierarchy` | heuristic | 171 | 72 | library |

| HIGH | BitcoinCore | `structural.error_modeling` | `throws` | heuristic | 184 | 50 | library |

| MEDIUM | BitcoinCore | `idiom.collection_init` | `constructor` | heuristic | 115 | 10 | library |

| MEDIUM | BitcoinCoreTests | `idiom.collection_init` | `constructor` | heuristic | 21 | 1 | test |

| MEDIUM | BitcoinCore | `idiom.computed_vs_property` | `computed_property` | heuristic | 179 | 3 | library |

| LOW | BitcoinCore | `naming.module_protocol` | `other` | heuristic | 104 | 0 | library |

| LOW | BitcoinCore | `naming.type_class` | `upper_camel` | heuristic | 434 | 0 | library |



### BitcoinCore · `structural.adt_pattern` violations

| Severity | File | Line | Message |
|----------|------|------|---------|

| HIGH | `Sources/BitcoinCore/Classes/ApiSync/BlockchairSync/BlockchairResponse.swift` | 3 | structural.adt_pattern prefers enum; found BlockchairResponse in Sources/BitcoinCore/Classes/ApiSync/BlockchairSync/BlockchairResponse.swift |

| HIGH | `Sources/BitcoinCore/Classes/Blocks/InitialBlockDownload.swift` | 4 | structural.adt_pattern prefers enum; found InitialDownloadEvent in Sources/BitcoinCore/Classes/Blocks/InitialBlockDownload.swift |

| HIGH | `Sources/BitcoinCore/Classes/Core/BitcoinCore.swift` | 412 | structural.adt_pattern prefers enum; found KitState in Sources/BitcoinCore/Classes/Core/BitcoinCore.swift |

| HIGH | `Sources/BitcoinCore/Classes/Core/BitcoinCore.swift` | 429 | structural.adt_pattern prefers enum; found SyncMode in Sources/BitcoinCore/Classes/Core/BitcoinCore.swift |

| HIGH | `Sources/BitcoinCore/Classes/Core/BitcoinCore.swift` | 443 | structural.adt_pattern prefers enum; found SendType in Sources/BitcoinCore/Classes/Core/BitcoinCore.swift |

| HIGH | `Sources/BitcoinCore/Classes/Core/BitcoinCore.swift` | 448 | structural.adt_pattern prefers enum; found TransactionFilter in Sources/BitcoinCore/Classes/Core/BitcoinCore.swift |

| HIGH | `Sources/BitcoinCore/Classes/Core/BitcoinCore.swift` | 473 | structural.adt_pattern prefers enum; found CoreError in Sources/BitcoinCore/Classes/Core/BitcoinCore.swift |

| HIGH | `Sources/BitcoinCore/Classes/Core/BitcoinCore.swift` | 476 | structural.adt_pattern prefers enum; found StateError in Sources/BitcoinCore/Classes/Core/BitcoinCore.swift |

| HIGH | `Sources/BitcoinCore/Classes/Core/BitcoinCoreBuilder.swift` | 6 | structural.adt_pattern prefers enum; found BuildError in Sources/BitcoinCore/Classes/Core/BitcoinCoreBuilder.swift |

| HIGH | `Sources/BitcoinCore/Classes/Core/BitcoinCoreErrors.swift` | 2 | structural.adt_pattern prefers enum; found BitcoinCoreErrors in Sources/BitcoinCore/Classes/Core/BitcoinCoreErrors.swift |

| HIGH | `Sources/BitcoinCore/Classes/Core/BitcoinCoreErrors.swift` | 4 | structural.adt_pattern prefers enum; found AddressConversion in Sources/BitcoinCore/Classes/Core/BitcoinCoreErrors.swift |

| HIGH | `Sources/BitcoinCore/Classes/Core/BitcoinCoreErrors.swift` | 10 | structural.adt_pattern prefers enum; found TransactionSendError in Sources/BitcoinCore/Classes/Core/BitcoinCoreErrors.swift |

| HIGH | `Sources/BitcoinCore/Classes/Core/BitcoinCoreErrors.swift` | 17 | structural.adt_pattern prefers enum; found MerkleBlockValidation in Sources/BitcoinCore/Classes/Core/BitcoinCoreErrors.swift |

| HIGH | `Sources/BitcoinCore/Classes/Core/BitcoinCoreErrors.swift` | 30 | structural.adt_pattern prefers enum; found BlockValidation in Sources/BitcoinCore/Classes/Core/BitcoinCoreErrors.swift |

| HIGH | `Sources/BitcoinCore/Classes/Core/BitcoinCoreErrors.swift` | 40 | structural.adt_pattern prefers enum; found MessageSerialization in Sources/BitcoinCore/Classes/Core/BitcoinCoreErrors.swift |

| HIGH | `Sources/BitcoinCore/Classes/Core/BitcoinCoreErrors.swift` | 44 | structural.adt_pattern prefers enum; found ScriptBuild in Sources/BitcoinCore/Classes/Core/BitcoinCoreErrors.swift |

| HIGH | `Sources/BitcoinCore/Classes/Core/BitcoinCoreErrors.swift` | 53 | structural.adt_pattern prefers enum; found SendValueErrors in Sources/BitcoinCore/Classes/Core/BitcoinCoreErrors.swift |

| HIGH | `Sources/BitcoinCore/Classes/Core/BitcoinCoreErrors.swift` | 60 | structural.adt_pattern prefers enum; found Unexpected in Sources/BitcoinCore/Classes/Core/BitcoinCoreErrors.swift |

| HIGH | `Sources/BitcoinCore/Classes/Core/HDWallet.swift` | 5 | structural.adt_pattern prefers enum; found HDWalletError in Sources/BitcoinCore/Classes/Core/HDWallet.swift |

| HIGH | `Sources/BitcoinCore/Classes/Core/Protocols.swift` | 6 | structural.adt_pattern prefers enum; found BlockValidatorType in Sources/BitcoinCore/Classes/Core/Protocols.swift |

| HIGH | `Sources/BitcoinCore/Classes/Core/ReadOnlyWallet.swift` | 4 | structural.adt_pattern prefers enum; found ReadOnlyWalletError in Sources/BitcoinCore/Classes/Core/ReadOnlyWallet.swift |

| HIGH | `Sources/BitcoinCore/Classes/Crypto/BloomFilter.swift` | 56 | structural.adt_pattern prefers enum; found Bit in Sources/BitcoinCore/Classes/Crypto/BloomFilter.swift |

| HIGH | `Sources/BitcoinCore/Classes/Crypto/MurmurHash.swift` | 10 | structural.adt_pattern prefers enum; found MurmurHash in Sources/BitcoinCore/Classes/Crypto/MurmurHash.swift |

| HIGH | `Sources/BitcoinCore/Classes/Helpers/Bip69.swift` | 2 | structural.adt_pattern prefers enum; found Bip69 in Sources/BitcoinCore/Classes/Helpers/Bip69.swift |

| HIGH | `Sources/BitcoinCore/Classes/Helpers/DirectoryHelper.swift` | 2 | structural.adt_pattern prefers enum; found DirectoryHelper in Sources/BitcoinCore/Classes/Helpers/DirectoryHelper.swift |

| HIGH | `Sources/BitcoinCore/Classes/Managers/PluginManager.swift` | 5 | structural.adt_pattern prefers enum; found PluginError in Sources/BitcoinCore/Classes/Managers/PluginManager.swift |

| HIGH | `Sources/BitcoinCore/Classes/Managers/PublicKeyManager.swift` | 5 | structural.adt_pattern prefers enum; found PublicKeyManagerError in Sources/BitcoinCore/Classes/Managers/PublicKeyManager.swift |

| HIGH | `Sources/BitcoinCore/Classes/Models/Address.swift` | 2 | structural.adt_pattern prefers enum; found AddressType in Sources/BitcoinCore/Classes/Models/Address.swift |

| HIGH | `Sources/BitcoinCore/Classes/Models/Block.swift` | 38 | structural.adt_pattern prefers enum; found Columns in Sources/BitcoinCore/Classes/Models/Block.swift |

| HIGH | `Sources/BitcoinCore/Classes/Models/BlockHash.swift` | 33 | structural.adt_pattern prefers enum; found Columns in Sources/BitcoinCore/Classes/Models/BlockHash.swift |

| HIGH | `Sources/BitcoinCore/Classes/Models/BlockHashPublicKey.swift` | 18 | structural.adt_pattern prefers enum; found Columns in Sources/BitcoinCore/Classes/Models/BlockHashPublicKey.swift |

| HIGH | `Sources/BitcoinCore/Classes/Models/BlockchainState.swift` | 17 | structural.adt_pattern prefers enum; found Columns in Sources/BitcoinCore/Classes/Models/BlockchainState.swift |

| HIGH | `Sources/BitcoinCore/Classes/Models/Checkpoint.swift` | 54 | structural.adt_pattern prefers enum; found ParseError in Sources/BitcoinCore/Classes/Models/Checkpoint.swift |

| HIGH | `Sources/BitcoinCore/Classes/Models/InfoObjects.swift` | 64 | structural.adt_pattern prefers enum; found CodingKeys in Sources/BitcoinCore/Classes/Models/InfoObjects.swift |

| HIGH | `Sources/BitcoinCore/Classes/Models/Input.swift` | 26 | structural.adt_pattern prefers enum; found Columns in Sources/BitcoinCore/Classes/Models/Input.swift |

| HIGH | `Sources/BitcoinCore/Classes/Models/Input.swift` | 68 | structural.adt_pattern prefers enum; found SerializationError in Sources/BitcoinCore/Classes/Models/Input.swift |

| HIGH | `Sources/BitcoinCore/Classes/Models/Output.swift` | 4 | structural.adt_pattern prefers enum; found ScriptType in Sources/BitcoinCore/Classes/Models/Output.swift |

| HIGH | `Sources/BitcoinCore/Classes/Models/Output.swift` | 87 | structural.adt_pattern prefers enum; found Columns in Sources/BitcoinCore/Classes/Models/Output.swift |

| HIGH | `Sources/BitcoinCore/Classes/Models/PeerAddress.swift` | 18 | structural.adt_pattern prefers enum; found Columns in Sources/BitcoinCore/Classes/Models/PeerAddress.swift |

| HIGH | `Sources/BitcoinCore/Classes/Models/PublicKey.swift` | 6 | structural.adt_pattern prefers enum; found InitError in Sources/BitcoinCore/Classes/Models/PublicKey.swift |

| HIGH | `Sources/BitcoinCore/Classes/Models/PublicKey.swift` | 49 | structural.adt_pattern prefers enum; found Columns in Sources/BitcoinCore/Classes/Models/PublicKey.swift |

| HIGH | `Sources/BitcoinCore/Classes/Models/SentTransaction.swift` | 27 | structural.adt_pattern prefers enum; found Columns in Sources/BitcoinCore/Classes/Models/SentTransaction.swift |

| HIGH | `Sources/BitcoinCore/Classes/Models/SigHashType.swift` | 2 | structural.adt_pattern prefers enum; found SigHashType in Sources/BitcoinCore/Classes/Models/SigHashType.swift |

| HIGH | `Sources/BitcoinCore/Classes/Models/Transaction.swift` | 4 | structural.adt_pattern prefers enum; found TransactionStatus in Sources/BitcoinCore/Classes/Models/Transaction.swift |

| HIGH | `Sources/BitcoinCore/Classes/Models/Transaction.swift` | 41 | structural.adt_pattern prefers enum; found Columns in Sources/BitcoinCore/Classes/Models/Transaction.swift |

| HIGH | `Sources/BitcoinCore/Classes/Models/TransactionDataSortType.swift` | 1 | structural.adt_pattern prefers enum; found TransactionDataSortType in Sources/BitcoinCore/Classes/Models/TransactionDataSortType.swift |

| HIGH | `Sources/BitcoinCore/Classes/Models/TransactionMetadata.swift` | 3 | structural.adt_pattern prefers enum; found TransactionType in Sources/BitcoinCore/Classes/Models/TransactionMetadata.swift |

| HIGH | `Sources/BitcoinCore/Classes/Models/TransactionMetadata.swift` | 9 | structural.adt_pattern prefers enum; found TransactionFilterType in Sources/BitcoinCore/Classes/Models/TransactionMetadata.swift |

| HIGH | `Sources/BitcoinCore/Classes/Models/TransactionMetadata.swift` | 39 | structural.adt_pattern prefers enum; found Columns in Sources/BitcoinCore/Classes/Models/TransactionMetadata.swift |

| HIGH | `Sources/BitcoinCore/Classes/Network/Messages/InventoryItem.swift` | 43 | structural.adt_pattern prefers enum; found ObjectType in Sources/BitcoinCore/Classes/Network/Messages/InventoryItem.swift |

| HIGH | `Sources/BitcoinCore/Classes/Network/Peer/ConnectionTimeoutManager.swift` | 5 | structural.adt_pattern prefers enum; found TimeoutError in Sources/BitcoinCore/Classes/Network/Peer/ConnectionTimeoutManager.swift |

| HIGH | `Sources/BitcoinCore/Classes/Network/Peer/Peer.swift` | 5 | structural.adt_pattern prefers enum; found PeerError in Sources/BitcoinCore/Classes/Network/Peer/Peer.swift |

| HIGH | `Sources/BitcoinCore/Classes/Network/Peer/PeerConnection.swift` | 8 | structural.adt_pattern prefers enum; found PeerConnectionError in Sources/BitcoinCore/Classes/Network/Peer/PeerConnection.swift |

| HIGH | `Sources/BitcoinCore/Classes/Network/Peer/PeerGroup.swift` | 5 | structural.adt_pattern prefers enum; found PeerGroupEvent in Sources/BitcoinCore/Classes/Network/Peer/PeerGroup.swift |

| HIGH | `Sources/BitcoinCore/Classes/ReplacementTransaction/ReplacementTransactionBuilder.swift` | 345 | structural.adt_pattern prefers enum; found ReplacementTransactionBuildError in Sources/BitcoinCore/Classes/ReplacementTransaction/ReplacementTransactionBuilder.swift |

| HIGH | `Sources/BitcoinCore/Classes/ReplacementTransaction/ReplacementType.swift` | 1 | structural.adt_pattern prefers enum; found ReplacementType in Sources/BitcoinCore/Classes/ReplacementTransaction/ReplacementType.swift |

| HIGH | `Sources/BitcoinCore/Classes/SegWit/Bech32.swift` | 152 | structural.adt_pattern prefers enum; found DecodingError in Sources/BitcoinCore/Classes/SegWit/Bech32.swift |

| HIGH | `Sources/BitcoinCore/Classes/SegWit/Bech32.swift` | 187 | structural.adt_pattern prefers enum; found Encoding in Sources/BitcoinCore/Classes/SegWit/Bech32.swift |

| HIGH | `Sources/BitcoinCore/Classes/SegWit/SegWitBech32.swift` | 84 | structural.adt_pattern prefers enum; found CoderError in Sources/BitcoinCore/Classes/SegWit/SegWitBech32.swift |

| HIGH | `Sources/BitcoinCore/Classes/Serializers/DataListSerializer.swift` | 3 | structural.adt_pattern prefers enum; found DataListSerializer in Sources/BitcoinCore/Classes/Serializers/DataListSerializer.swift |

| HIGH | `Sources/BitcoinCore/Classes/Serializers/SignatureScriptSerializer.swift` | 3 | structural.adt_pattern prefers enum; found SignatureScriptSerializer in Sources/BitcoinCore/Classes/Serializers/SignatureScriptSerializer.swift |

| HIGH | `Sources/BitcoinCore/Classes/Serializers/TransactionInputSerializer.swift` | 3 | structural.adt_pattern prefers enum; found TransactionInputSerializer in Sources/BitcoinCore/Classes/Serializers/TransactionInputSerializer.swift |

| HIGH | `Sources/BitcoinCore/Classes/Serializers/TransactionOutputSerializer.swift` | 3 | structural.adt_pattern prefers enum; found TransactionOutputSerializer in Sources/BitcoinCore/Classes/Serializers/TransactionOutputSerializer.swift |

| HIGH | `Sources/BitcoinCore/Classes/Serializers/TransactionSerializer.swift` | 4 | structural.adt_pattern prefers enum; found TransactionSerializer in Sources/BitcoinCore/Classes/Serializers/TransactionSerializer.swift |

| HIGH | `Sources/BitcoinCore/Classes/Transactions/Builder/EcdsaInputSigner.swift` | 7 | structural.adt_pattern prefers enum; found SignError in Sources/BitcoinCore/Classes/Transactions/Builder/EcdsaInputSigner.swift |

| HIGH | `Sources/BitcoinCore/Classes/Transactions/Builder/InputSetter.swift` | 4 | structural.adt_pattern prefers enum; found UnspentOutputError in Sources/BitcoinCore/Classes/Transactions/Builder/InputSetter.swift |

| HIGH | `Sources/BitcoinCore/Classes/Transactions/Builder/SchnorrInputSigner.swift` | 7 | structural.adt_pattern prefers enum; found SignError in Sources/BitcoinCore/Classes/Transactions/Builder/SchnorrInputSigner.swift |

| HIGH | `Sources/BitcoinCore/Classes/Transactions/Builder/TransactionSigner.swift` | 4 | structural.adt_pattern prefers enum; found SignError in Sources/BitcoinCore/Classes/Transactions/Builder/TransactionSigner.swift |

| HIGH | `Sources/BitcoinCore/Classes/Transactions/Extractors/TransactionInputExtractor.swift` | 4 | structural.adt_pattern prefers enum; found ScriptError in Sources/BitcoinCore/Classes/Transactions/Extractors/TransactionInputExtractor.swift |

| HIGH | `Sources/BitcoinCore/Classes/Transactions/Scripts/OpCode.swift` | 3 | structural.adt_pattern prefers enum; found OpCode in Sources/BitcoinCore/Classes/Transactions/Scripts/OpCode.swift |

| HIGH | `Sources/BitcoinCore/Classes/Transactions/TransactionCreator.swift` | 5 | structural.adt_pattern prefers enum; found CreationError in Sources/BitcoinCore/Classes/Transactions/TransactionCreator.swift |

| HIGH | `Sources/BitcoinCore/Classes/Transactions/TransactionSizeCalculator.swift` | 160 | structural.adt_pattern prefers enum; found CalculationError in Sources/BitcoinCore/Classes/Transactions/TransactionSizeCalculator.swift |



### BitcoinCore · `structural.error_modeling` violations

| Severity | File | Line | Message |
|----------|------|------|---------|

| HIGH | `Sources/BitcoinCore/Classes/Core/BitcoinCore.swift` | 152 | structural.error_modeling prefers nullable; found nullable in Sources/BitcoinCore/Classes/Core/BitcoinCore.swift |

| HIGH | `Sources/BitcoinCore/Classes/Core/BitcoinCore.swift` | 309 | structural.error_modeling prefers nullable; found nullable in Sources/BitcoinCore/Classes/Core/BitcoinCore.swift |

| HIGH | `Sources/BitcoinCore/Classes/Core/DataProvider.swift` | 104 | structural.error_modeling prefers nullable; found nullable in Sources/BitcoinCore/Classes/Core/DataProvider.swift |

| HIGH | `Sources/BitcoinCore/Classes/Core/DataProvider.swift` | 132 | structural.error_modeling prefers nullable; found nullable in Sources/BitcoinCore/Classes/Core/DataProvider.swift |

| HIGH | `Sources/BitcoinCore/Classes/Core/Protocols.swift` | 20 | structural.error_modeling prefers nullable; found nullable in Sources/BitcoinCore/Classes/Core/Protocols.swift |

| HIGH | `Sources/BitcoinCore/Classes/Core/Protocols.swift` | 21 | structural.error_modeling prefers nullable; found nullable in Sources/BitcoinCore/Classes/Core/Protocols.swift |

| HIGH | `Sources/BitcoinCore/Classes/Core/Protocols.swift` | 61 | structural.error_modeling prefers nullable; found nullable in Sources/BitcoinCore/Classes/Core/Protocols.swift |

| HIGH | `Sources/BitcoinCore/Classes/Core/Protocols.swift` | 68 | structural.error_modeling prefers nullable; found nullable in Sources/BitcoinCore/Classes/Core/Protocols.swift |

| HIGH | `Sources/BitcoinCore/Classes/Core/Protocols.swift` | 101 | structural.error_modeling prefers nullable; found nullable in Sources/BitcoinCore/Classes/Core/Protocols.swift |

| HIGH | `Sources/BitcoinCore/Classes/Core/Protocols.swift` | 102 | structural.error_modeling prefers nullable; found nullable in Sources/BitcoinCore/Classes/Core/Protocols.swift |

| HIGH | `Sources/BitcoinCore/Classes/Core/Protocols.swift` | 103 | structural.error_modeling prefers nullable; found nullable in Sources/BitcoinCore/Classes/Core/Protocols.swift |

| HIGH | `Sources/BitcoinCore/Classes/Core/Protocols.swift` | 104 | structural.error_modeling prefers nullable; found nullable in Sources/BitcoinCore/Classes/Core/Protocols.swift |

| HIGH | `Sources/BitcoinCore/Classes/Core/Protocols.swift` | 112 | structural.error_modeling prefers nullable; found nullable in Sources/BitcoinCore/Classes/Core/Protocols.swift |

| HIGH | `Sources/BitcoinCore/Classes/Core/Protocols.swift` | 113 | structural.error_modeling prefers nullable; found nullable in Sources/BitcoinCore/Classes/Core/Protocols.swift |

| HIGH | `Sources/BitcoinCore/Classes/Core/Protocols.swift` | 114 | structural.error_modeling prefers nullable; found nullable in Sources/BitcoinCore/Classes/Core/Protocols.swift |

| HIGH | `Sources/BitcoinCore/Classes/Core/Protocols.swift` | 115 | structural.error_modeling prefers nullable; found nullable in Sources/BitcoinCore/Classes/Core/Protocols.swift |

| HIGH | `Sources/BitcoinCore/Classes/Core/Protocols.swift` | 125 | structural.error_modeling prefers nullable; found nullable in Sources/BitcoinCore/Classes/Core/Protocols.swift |

| HIGH | `Sources/BitcoinCore/Classes/Core/Protocols.swift` | 132 | structural.error_modeling prefers nullable; found nullable in Sources/BitcoinCore/Classes/Core/Protocols.swift |

| HIGH | `Sources/BitcoinCore/Classes/Core/Protocols.swift` | 142 | structural.error_modeling prefers nullable; found nullable in Sources/BitcoinCore/Classes/Core/Protocols.swift |

| HIGH | `Sources/BitcoinCore/Classes/Core/Protocols.swift` | 149 | structural.error_modeling prefers nullable; found nullable in Sources/BitcoinCore/Classes/Core/Protocols.swift |

| HIGH | `Sources/BitcoinCore/Classes/Core/Protocols.swift` | 150 | structural.error_modeling prefers nullable; found nullable in Sources/BitcoinCore/Classes/Core/Protocols.swift |

| HIGH | `Sources/BitcoinCore/Classes/Core/Protocols.swift` | 151 | structural.error_modeling prefers nullable; found nullable in Sources/BitcoinCore/Classes/Core/Protocols.swift |

| HIGH | `Sources/BitcoinCore/Classes/Core/Protocols.swift` | 152 | structural.error_modeling prefers nullable; found nullable in Sources/BitcoinCore/Classes/Core/Protocols.swift |

| HIGH | `Sources/BitcoinCore/Classes/Core/Protocols.swift` | 155 | structural.error_modeling prefers nullable; found nullable in Sources/BitcoinCore/Classes/Core/Protocols.swift |

| HIGH | `Sources/BitcoinCore/Classes/Core/Protocols.swift` | 338 | structural.error_modeling prefers nullable; found nullable in Sources/BitcoinCore/Classes/Core/Protocols.swift |

| HIGH | `Sources/BitcoinCore/Classes/Core/Protocols.swift` | 478 | structural.error_modeling prefers nullable; found nullable in Sources/BitcoinCore/Classes/Core/Protocols.swift |

| HIGH | `Sources/BitcoinCore/Classes/Core/Protocols.swift` | 480 | structural.error_modeling prefers nullable; found nullable in Sources/BitcoinCore/Classes/Core/Protocols.swift |

| HIGH | `Sources/BitcoinCore/Classes/Core/Protocols.swift` | 526 | structural.error_modeling prefers nullable; found nullable in Sources/BitcoinCore/Classes/Core/Protocols.swift |

| HIGH | `Sources/BitcoinCore/Classes/Core/Protocols.swift` | 544 | structural.error_modeling prefers nullable; found nullable in Sources/BitcoinCore/Classes/Core/Protocols.swift |

| HIGH | `Sources/BitcoinCore/Classes/Core/Protocols.swift` | 635 | structural.error_modeling prefers nullable; found nullable in Sources/BitcoinCore/Classes/Core/Protocols.swift |

| HIGH | `Sources/BitcoinCore/Classes/Core/Protocols.swift` | 641 | structural.error_modeling prefers nullable; found nullable in Sources/BitcoinCore/Classes/Core/Protocols.swift |

| HIGH | `Sources/BitcoinCore/Classes/Extensions/SynchronizedArray.swift` | 55 | structural.error_modeling prefers nullable; found nullable in Sources/BitcoinCore/Classes/Extensions/SynchronizedArray.swift |

| HIGH | `Sources/BitcoinCore/Classes/Extensions/SynchronizedArray.swift` | 75 | structural.error_modeling prefers nullable; found nullable in Sources/BitcoinCore/Classes/Extensions/SynchronizedArray.swift |

| HIGH | `Sources/BitcoinCore/Classes/Extensions/SynchronizedArray.swift` | 156 | structural.error_modeling prefers nullable; found nullable in Sources/BitcoinCore/Classes/Extensions/SynchronizedArray.swift |

| HIGH | `Sources/BitcoinCore/Classes/Extensions/SynchronizedArray.swift` | 171 | structural.error_modeling prefers nullable; found nullable in Sources/BitcoinCore/Classes/Extensions/SynchronizedArray.swift |

| HIGH | `Sources/BitcoinCore/Classes/Extensions/SynchronizedArray.swift` | 185 | structural.error_modeling prefers nullable; found nullable in Sources/BitcoinCore/Classes/Extensions/SynchronizedArray.swift |

| HIGH | `Sources/BitcoinCore/Classes/Network/Parsers/NetworkMessageParser.swift` | 16 | structural.error_modeling prefers nullable; found nullable in Sources/BitcoinCore/Classes/Network/Parsers/NetworkMessageParser.swift |

| HIGH | `Sources/BitcoinCore/Classes/Network/Parsers/NetworkMessageSerializer.swift` | 50 | structural.error_modeling prefers nullable; found nullable in Sources/BitcoinCore/Classes/Network/Parsers/NetworkMessageSerializer.swift |

| HIGH | `Sources/BitcoinCore/Classes/Network/Parsers/NetworkMessageSerializer.swift` | 69 | structural.error_modeling prefers nullable; found nullable in Sources/BitcoinCore/Classes/Network/Parsers/NetworkMessageSerializer.swift |

| HIGH | `Sources/BitcoinCore/Classes/Network/Parsers/NetworkMessageSerializer.swift` | 88 | structural.error_modeling prefers nullable; found nullable in Sources/BitcoinCore/Classes/Network/Parsers/NetworkMessageSerializer.swift |

| HIGH | `Sources/BitcoinCore/Classes/Network/Parsers/NetworkMessageSerializer.swift` | 105 | structural.error_modeling prefers nullable; found nullable in Sources/BitcoinCore/Classes/Network/Parsers/NetworkMessageSerializer.swift |

| HIGH | `Sources/BitcoinCore/Classes/Network/Parsers/NetworkMessageSerializer.swift` | 119 | structural.error_modeling prefers nullable; found nullable in Sources/BitcoinCore/Classes/Network/Parsers/NetworkMessageSerializer.swift |

| HIGH | `Sources/BitcoinCore/Classes/Network/Parsers/NetworkMessageSerializer.swift` | 133 | structural.error_modeling prefers nullable; found nullable in Sources/BitcoinCore/Classes/Network/Parsers/NetworkMessageSerializer.swift |

| HIGH | `Sources/BitcoinCore/Classes/Network/Parsers/NetworkMessageSerializer.swift` | 155 | structural.error_modeling prefers nullable; found nullable in Sources/BitcoinCore/Classes/Network/Parsers/NetworkMessageSerializer.swift |

| HIGH | `Sources/BitcoinCore/Classes/Network/Parsers/NetworkMessageSerializer.swift` | 167 | structural.error_modeling prefers nullable; found nullable in Sources/BitcoinCore/Classes/Network/Parsers/NetworkMessageSerializer.swift |

| HIGH | `Sources/BitcoinCore/Classes/Network/Parsers/NetworkMessageSerializer.swift` | 179 | structural.error_modeling prefers nullable; found nullable in Sources/BitcoinCore/Classes/Network/Parsers/NetworkMessageSerializer.swift |

| HIGH | `Sources/BitcoinCore/Classes/Network/Parsers/NetworkMessageSerializer.swift` | 191 | structural.error_modeling prefers nullable; found nullable in Sources/BitcoinCore/Classes/Network/Parsers/NetworkMessageSerializer.swift |

| HIGH | `Sources/BitcoinCore/Classes/ReplacementTransaction/ReplacementTransactionBuilder.swift` | 282 | structural.error_modeling prefers nullable; found nullable in Sources/BitcoinCore/Classes/ReplacementTransaction/ReplacementTransactionBuilder.swift |

| HIGH | `Sources/BitcoinCore/Classes/Storage/GrdbStorage.swift` | 234 | structural.error_modeling prefers nullable; found nullable in Sources/BitcoinCore/Classes/Storage/GrdbStorage.swift |

| HIGH | `Sources/BitcoinCore/Classes/Transactions/Extractors/MyOutputsCache.swift` | 19 | structural.error_modeling prefers nullable; found nullable in Sources/BitcoinCore/Classes/Transactions/Extractors/MyOutputsCache.swift |



### BitcoinCore · `idiom.collection_init` violations

| Severity | File | Line | Message |
|----------|------|------|---------|

| MEDIUM | `Sources/BitcoinCore/Classes/ApiSync/BlockchairSync/BlockchairApi.swift` | 17 | idiom.collection_init prefers literal_empty; found literal_empty in Sources/BitcoinCore/Classes/ApiSync/BlockchairSync/BlockchairApi.swift |

| MEDIUM | `Sources/BitcoinCore/Classes/ApiSync/BlockchairSync/BlockchairApi.swift` | 17 | idiom.collection_init prefers literal_empty; found literal_empty in Sources/BitcoinCore/Classes/ApiSync/BlockchairSync/BlockchairApi.swift |

| MEDIUM | `Sources/BitcoinCore/Classes/ApiSync/InsightApi.swift` | 36 | idiom.collection_init prefers literal_empty; found literal_empty in Sources/BitcoinCore/Classes/ApiSync/InsightApi.swift |

| MEDIUM | `Sources/BitcoinCore/Classes/ApiSync/InsightApi.swift` | 50 | idiom.collection_init prefers literal_empty; found literal_empty in Sources/BitcoinCore/Classes/ApiSync/InsightApi.swift |

| MEDIUM | `Sources/BitcoinCore/Classes/ApiSync/LegacySync/BlockHashDiscoveryBatch.swift` | 20 | idiom.collection_init prefers literal_empty; found literal_empty in Sources/BitcoinCore/Classes/ApiSync/LegacySync/BlockHashDiscoveryBatch.swift |

| MEDIUM | `Sources/BitcoinCore/Classes/ApiSync/LegacySync/BlockHashDiscoveryBatch.swift` | 59 | idiom.collection_init prefers literal_empty; found literal_empty in Sources/BitcoinCore/Classes/ApiSync/LegacySync/BlockHashDiscoveryBatch.swift |

| MEDIUM | `Sources/BitcoinCore/Classes/Managers/UnspentOutputQueue.swift` | 35 | idiom.collection_init prefers literal_empty; found literal_empty in Sources/BitcoinCore/Classes/Managers/UnspentOutputQueue.swift |

| MEDIUM | `Sources/BitcoinCore/Classes/Network/Peer/Peer.swift` | 26 | idiom.collection_init prefers literal_empty; found literal_empty in Sources/BitcoinCore/Classes/Network/Peer/Peer.swift |

| MEDIUM | `Sources/BitcoinCore/Classes/Network/Peer/PeerAddressManagerState.swift` | 4 | idiom.collection_init prefers literal_empty; found literal_empty in Sources/BitcoinCore/Classes/Network/Peer/PeerAddressManagerState.swift |

| MEDIUM | `Sources/BitcoinCore/Classes/Network/Peer/PeerManager.swift` | 4 | idiom.collection_init prefers literal_empty; found literal_empty in Sources/BitcoinCore/Classes/Network/Peer/PeerManager.swift |



### BitcoinCoreTests · `idiom.collection_init` violations

| Severity | File | Line | Message |
|----------|------|------|---------|

| MEDIUM | `Tests/BitcoinCoreTests/Transactions/TransactionProcessorTests.swift` | 465 | idiom.collection_init prefers literal_empty; found literal_empty in Tests/BitcoinCoreTests/Transactions/TransactionProcessorTests.swift |



### BitcoinCore · `idiom.computed_vs_property` violations

| Severity | File | Line | Message |
|----------|------|------|---------|

| MEDIUM | `Sources/BitcoinCore/Classes/Models/DataObjects.swift` | 29 | idiom.computed_vs_property prefers lazy_property; found lazy_property in Sources/BitcoinCore/Classes/Models/DataObjects.swift |

| MEDIUM | `Sources/BitcoinCore/Classes/Models/Transaction.swift` | 22 | idiom.computed_vs_property prefers lazy_property; found lazy_property in Sources/BitcoinCore/Classes/Models/Transaction.swift |

| MEDIUM | `Sources/BitcoinCore/Classes/Network/Messages/MerkleBlock.swift` | 8 | idiom.computed_vs_property prefers lazy_property; found lazy_property in Sources/BitcoinCore/Classes/Network/Messages/MerkleBlock.swift |



**Summary:** 7 conventions surfaced by the audit query.


*Provenance: run `85836b7b-7a87-49fc-9e08-fc4061149d09`.*


---


## Reactive dependency tracer


*50 diagnostics found (capped at 50).*

| Severity | Diagnostic code | File | Language | Message |
|----------|----------------|------|----------|---------|

| MEDIUM | `swift_helper_unavailable` | - | swift | Expected pre-generated helper JSON at reactive_facts.json |

| INFORMATIONAL | `swift_generated_or_vendor_skipped` | .build/checkouts/Alamofire/Example/Source/AppDelegate.swift | swift | Skipped generated or vendor Swift file: .build/checkouts/Alamofire/Example/Source/AppDelegate.swift |

| INFORMATIONAL | `swift_generated_or_vendor_skipped` | .build/checkouts/Alamofire/Example/Source/DetailViewController.swift | swift | Skipped generated or vendor Swift file: .build/checkouts/Alamofire/Example/Source/DetailViewController.swift |

| INFORMATIONAL | `swift_generated_or_vendor_skipped` | .build/checkouts/Alamofire/Example/Source/MasterViewController.swift | swift | Skipped generated or vendor Swift file: .build/checkouts/Alamofire/Example/Source/MasterViewController.swift |

| INFORMATIONAL | `swift_generated_or_vendor_skipped` | .build/checkouts/Alamofire/Package.swift | swift | Skipped generated or vendor Swift file: .build/checkouts/Alamofire/Package.swift |

| INFORMATIONAL | `swift_generated_or_vendor_skipped` | .build/checkouts/Alamofire/Package@swift-5.3.swift | swift | Skipped generated or vendor Swift file: .build/checkouts/Alamofire/Package@swift-5.3.swift |

| INFORMATIONAL | `swift_generated_or_vendor_skipped` | .build/checkouts/Alamofire/Package@swift-5.4.swift | swift | Skipped generated or vendor Swift file: .build/checkouts/Alamofire/Package@swift-5.4.swift |

| INFORMATIONAL | `swift_generated_or_vendor_skipped` | .build/checkouts/Alamofire/Package@swift-5.5.swift | swift | Skipped generated or vendor Swift file: .build/checkouts/Alamofire/Package@swift-5.5.swift |

| INFORMATIONAL | `swift_generated_or_vendor_skipped` | .build/checkouts/Alamofire/Source/AFError.swift | swift | Skipped generated or vendor Swift file: .build/checkouts/Alamofire/Source/AFError.swift |

| INFORMATIONAL | `swift_generated_or_vendor_skipped` | .build/checkouts/Alamofire/Source/Alamofire.swift | swift | Skipped generated or vendor Swift file: .build/checkouts/Alamofire/Source/Alamofire.swift |

| INFORMATIONAL | `swift_generated_or_vendor_skipped` | .build/checkouts/Alamofire/Source/AlamofireExtended.swift | swift | Skipped generated or vendor Swift file: .build/checkouts/Alamofire/Source/AlamofireExtended.swift |

| INFORMATIONAL | `swift_generated_or_vendor_skipped` | .build/checkouts/Alamofire/Source/AuthenticationInterceptor.swift | swift | Skipped generated or vendor Swift file: .build/checkouts/Alamofire/Source/AuthenticationInterceptor.swift |

| INFORMATIONAL | `swift_generated_or_vendor_skipped` | .build/checkouts/Alamofire/Source/CachedResponseHandler.swift | swift | Skipped generated or vendor Swift file: .build/checkouts/Alamofire/Source/CachedResponseHandler.swift |

| INFORMATIONAL | `swift_generated_or_vendor_skipped` | .build/checkouts/Alamofire/Source/Combine.swift | swift | Skipped generated or vendor Swift file: .build/checkouts/Alamofire/Source/Combine.swift |

| INFORMATIONAL | `swift_generated_or_vendor_skipped` | .build/checkouts/Alamofire/Source/Concurrency.swift | swift | Skipped generated or vendor Swift file: .build/checkouts/Alamofire/Source/Concurrency.swift |

| INFORMATIONAL | `swift_generated_or_vendor_skipped` | .build/checkouts/Alamofire/Source/DispatchQueue+Alamofire.swift | swift | Skipped generated or vendor Swift file: .build/checkouts/Alamofire/Source/DispatchQueue+Alamofire.swift |

| INFORMATIONAL | `swift_generated_or_vendor_skipped` | .build/checkouts/Alamofire/Source/EventMonitor.swift | swift | Skipped generated or vendor Swift file: .build/checkouts/Alamofire/Source/EventMonitor.swift |

| INFORMATIONAL | `swift_generated_or_vendor_skipped` | .build/checkouts/Alamofire/Source/HTTPHeaders.swift | swift | Skipped generated or vendor Swift file: .build/checkouts/Alamofire/Source/HTTPHeaders.swift |

| INFORMATIONAL | `swift_generated_or_vendor_skipped` | .build/checkouts/Alamofire/Source/HTTPMethod.swift | swift | Skipped generated or vendor Swift file: .build/checkouts/Alamofire/Source/HTTPMethod.swift |

| INFORMATIONAL | `swift_generated_or_vendor_skipped` | .build/checkouts/Alamofire/Source/MultipartFormData.swift | swift | Skipped generated or vendor Swift file: .build/checkouts/Alamofire/Source/MultipartFormData.swift |

| INFORMATIONAL | `swift_generated_or_vendor_skipped` | .build/checkouts/Alamofire/Source/MultipartUpload.swift | swift | Skipped generated or vendor Swift file: .build/checkouts/Alamofire/Source/MultipartUpload.swift |

| INFORMATIONAL | `swift_generated_or_vendor_skipped` | .build/checkouts/Alamofire/Source/NetworkReachabilityManager.swift | swift | Skipped generated or vendor Swift file: .build/checkouts/Alamofire/Source/NetworkReachabilityManager.swift |

| INFORMATIONAL | `swift_generated_or_vendor_skipped` | .build/checkouts/Alamofire/Source/Notifications.swift | swift | Skipped generated or vendor Swift file: .build/checkouts/Alamofire/Source/Notifications.swift |

| INFORMATIONAL | `swift_generated_or_vendor_skipped` | .build/checkouts/Alamofire/Source/OperationQueue+Alamofire.swift | swift | Skipped generated or vendor Swift file: .build/checkouts/Alamofire/Source/OperationQueue+Alamofire.swift |

| INFORMATIONAL | `swift_generated_or_vendor_skipped` | .build/checkouts/Alamofire/Source/ParameterEncoder.swift | swift | Skipped generated or vendor Swift file: .build/checkouts/Alamofire/Source/ParameterEncoder.swift |

| INFORMATIONAL | `swift_generated_or_vendor_skipped` | .build/checkouts/Alamofire/Source/ParameterEncoding.swift | swift | Skipped generated or vendor Swift file: .build/checkouts/Alamofire/Source/ParameterEncoding.swift |

| INFORMATIONAL | `swift_generated_or_vendor_skipped` | .build/checkouts/Alamofire/Source/Protected.swift | swift | Skipped generated or vendor Swift file: .build/checkouts/Alamofire/Source/Protected.swift |

| INFORMATIONAL | `swift_generated_or_vendor_skipped` | .build/checkouts/Alamofire/Source/RedirectHandler.swift | swift | Skipped generated or vendor Swift file: .build/checkouts/Alamofire/Source/RedirectHandler.swift |

| INFORMATIONAL | `swift_generated_or_vendor_skipped` | .build/checkouts/Alamofire/Source/Request.swift | swift | Skipped generated or vendor Swift file: .build/checkouts/Alamofire/Source/Request.swift |

| INFORMATIONAL | `swift_generated_or_vendor_skipped` | .build/checkouts/Alamofire/Source/RequestInterceptor.swift | swift | Skipped generated or vendor Swift file: .build/checkouts/Alamofire/Source/RequestInterceptor.swift |

| INFORMATIONAL | `swift_generated_or_vendor_skipped` | .build/checkouts/Alamofire/Source/RequestTaskMap.swift | swift | Skipped generated or vendor Swift file: .build/checkouts/Alamofire/Source/RequestTaskMap.swift |

| INFORMATIONAL | `swift_generated_or_vendor_skipped` | .build/checkouts/Alamofire/Source/Response.swift | swift | Skipped generated or vendor Swift file: .build/checkouts/Alamofire/Source/Response.swift |

| INFORMATIONAL | `swift_generated_or_vendor_skipped` | .build/checkouts/Alamofire/Source/ResponseSerialization.swift | swift | Skipped generated or vendor Swift file: .build/checkouts/Alamofire/Source/ResponseSerialization.swift |

| INFORMATIONAL | `swift_generated_or_vendor_skipped` | .build/checkouts/Alamofire/Source/Result+Alamofire.swift | swift | Skipped generated or vendor Swift file: .build/checkouts/Alamofire/Source/Result+Alamofire.swift |

| INFORMATIONAL | `swift_generated_or_vendor_skipped` | .build/checkouts/Alamofire/Source/RetryPolicy.swift | swift | Skipped generated or vendor Swift file: .build/checkouts/Alamofire/Source/RetryPolicy.swift |

| INFORMATIONAL | `swift_generated_or_vendor_skipped` | .build/checkouts/Alamofire/Source/ServerTrustEvaluation.swift | swift | Skipped generated or vendor Swift file: .build/checkouts/Alamofire/Source/ServerTrustEvaluation.swift |

| INFORMATIONAL | `swift_generated_or_vendor_skipped` | .build/checkouts/Alamofire/Source/Session.swift | swift | Skipped generated or vendor Swift file: .build/checkouts/Alamofire/Source/Session.swift |

| INFORMATIONAL | `swift_generated_or_vendor_skipped` | .build/checkouts/Alamofire/Source/SessionDelegate.swift | swift | Skipped generated or vendor Swift file: .build/checkouts/Alamofire/Source/SessionDelegate.swift |

| INFORMATIONAL | `swift_generated_or_vendor_skipped` | .build/checkouts/Alamofire/Source/StringEncoding+Alamofire.swift | swift | Skipped generated or vendor Swift file: .build/checkouts/Alamofire/Source/StringEncoding+Alamofire.swift |

| INFORMATIONAL | `swift_generated_or_vendor_skipped` | .build/checkouts/Alamofire/Source/URLConvertible+URLRequestConvertible.swift | swift | Skipped generated or vendor Swift file: .build/checkouts/Alamofire/Source/URLConvertible+URLRequestConvertible.swift |

| INFORMATIONAL | `swift_generated_or_vendor_skipped` | .build/checkouts/Alamofire/Source/URLEncodedFormEncoder.swift | swift | Skipped generated or vendor Swift file: .build/checkouts/Alamofire/Source/URLEncodedFormEncoder.swift |

| INFORMATIONAL | `swift_generated_or_vendor_skipped` | .build/checkouts/Alamofire/Source/URLRequest+Alamofire.swift | swift | Skipped generated or vendor Swift file: .build/checkouts/Alamofire/Source/URLRequest+Alamofire.swift |

| INFORMATIONAL | `swift_generated_or_vendor_skipped` | .build/checkouts/Alamofire/Source/URLSessionConfiguration+Alamofire.swift | swift | Skipped generated or vendor Swift file: .build/checkouts/Alamofire/Source/URLSessionConfiguration+Alamofire.swift |

| INFORMATIONAL | `swift_generated_or_vendor_skipped` | .build/checkouts/Alamofire/Source/Validation.swift | swift | Skipped generated or vendor Swift file: .build/checkouts/Alamofire/Source/Validation.swift |

| INFORMATIONAL | `swift_generated_or_vendor_skipped` | .build/checkouts/Alamofire/Tests/AFError+AlamofireTests.swift | swift | Skipped generated or vendor Swift file: .build/checkouts/Alamofire/Tests/AFError+AlamofireTests.swift |

| INFORMATIONAL | `swift_generated_or_vendor_skipped` | .build/checkouts/Alamofire/Tests/AuthenticationInterceptorTests.swift | swift | Skipped generated or vendor Swift file: .build/checkouts/Alamofire/Tests/AuthenticationInterceptorTests.swift |

| INFORMATIONAL | `swift_generated_or_vendor_skipped` | .build/checkouts/Alamofire/Tests/AuthenticationTests.swift | swift | Skipped generated or vendor Swift file: .build/checkouts/Alamofire/Tests/AuthenticationTests.swift |

| INFORMATIONAL | `swift_generated_or_vendor_skipped` | .build/checkouts/Alamofire/Tests/BaseTestCase.swift | swift | Skipped generated or vendor Swift file: .build/checkouts/Alamofire/Tests/BaseTestCase.swift |

| INFORMATIONAL | `swift_generated_or_vendor_skipped` | .build/checkouts/Alamofire/Tests/Bundle+AlamofireTests.swift | swift | Skipped generated or vendor Swift file: .build/checkouts/Alamofire/Tests/Bundle+AlamofireTests.swift |

| INFORMATIONAL | `swift_generated_or_vendor_skipped` | .build/checkouts/Alamofire/Tests/CacheTests.swift | swift | Skipped generated or vendor Swift file: .build/checkouts/Alamofire/Tests/CacheTests.swift |






**Warnings (1):** partial data — reactive graph may be incomplete.




*Provenance: run `99f60886-6a14-499c-b3e0-dff87ba359d6`.*


---


## Testability / DI patterns


*2 findings found (capped at 100).*

| Severity | Module | Language | Style | Framework | Samples | Outliers | Confidence |
|----------|--------|----------|-------|-----------|---------|----------|------------|

| HIGH | BitcoinCore | swift | `INIT_INJECTION` | - | 126 | 0 | heuristic |

| LOW | BitcoinCoreTests | swift | `STANDALONE_SIGNAL` | - | 0 | 0 | heuristic |



### BitcoinCore · `INIT_INJECTION` · HIGH


Test doubles: none linked for this module/style.



Untestable sites:

- **HIGH** `Sources/BitcoinCore/Classes/Models/Transaction.swift:30` `direct_clock` via `Date()` — Direct Date() access should be abstracted for tests.

- **MEDIUM** `Sources/BitcoinCore/Classes/Network/Peer/Peer.swift:67` `direct_clock` via `Date()` — Direct Date() access should be abstracted for tests.

- **MEDIUM** `Sources/BitcoinCore/Classes/Network/Peer/Peer.swift:93` `direct_clock` via `Date()` — Direct Date() access should be abstracted for tests.

- **MEDIUM** `Sources/BitcoinCore/Classes/Network/Peer/Peer.swift:170` `direct_clock` via `Date()` — Direct Date() access should be abstracted for tests.




### BitcoinCoreTests · `STANDALONE_SIGNAL` · LOW


Test doubles:

- `cuckoo` in `Tests/BitcoinCoreTests/BlockHeaders/DifficultyEncoderTests.swift`

- `cuckoo` in `Tests/BitcoinCoreTests/Blocks/BlockSyncerTests.swift`

- `cuckoo` in `Tests/BitcoinCoreTests/Blocks/BlockchainTests.swift`

- `cuckoo` in `Tests/BitcoinCoreTests/Blocks/KitStateProviderTests.swift`

- `cuckoo` in `Tests/BitcoinCoreTests/Blocks/MerkleBlockValidatorTests.swift`

- `cuckoo` in `Tests/BitcoinCoreTests/Blocks/Validators/BitsValidatorTests.swift`

- `cuckoo` in `Tests/BitcoinCoreTests/Blocks/Validators/LegacyDifficultyAdjustmentValidatorTests.swift`

- `cuckoo` in `Tests/BitcoinCoreTests/Blocks/Validators/LegacyTestNetDifficultyValidatorTests.swift`

- `cuckoo` in `Tests/BitcoinCoreTests/Blocks/Validators/ProofOfWorkValidatorTests.swift`

- `cuckoo` in `Tests/BitcoinCoreTests/Core/DataProviderTests.swift`

- `cuckoo` in `Tests/BitcoinCoreTests/Extensions.swift`

- `cuckoo` in `Tests/BitcoinCoreTests/HDWallet/HDPrivateKeyTests.swift`

- `cuckoo` in `Tests/BitcoinCoreTests/Helpers/AddressConverterTests.swift`

- `cuckoo` in `Tests/BitcoinCoreTests/Helpers/Bip69Tests.swift`

- `cuckoo` in `Tests/BitcoinCoreTests/Helpers/BlockValidatorHelperTests.swift`

- `cuckoo` in `Tests/BitcoinCoreTests/Helpers/MerkleBranchTests.swift`

- `cuckoo` in `Tests/BitcoinCoreTests/Helpers/PaymentAddressParserTests.swift`

- `cuckoo` in `Tests/BitcoinCoreTests/Managers/BloomFilterManagerTests.swift`

- `cuckoo` in `Tests/BitcoinCoreTests/Managers/InitialSync/BlockDiscoveryBatchTest.swift`

- `cuckoo` in `Tests/BitcoinCoreTests/Managers/InitialSync/BlockHashFetcherHelperTests.swift`

- `cuckoo` in `Tests/BitcoinCoreTests/Managers/InitialSync/BlockHashFetcherTests.swift`

- `cuckoo` in `Tests/BitcoinCoreTests/Managers/InitialSyncerTests.swift`

- `cuckoo` in `Tests/BitcoinCoreTests/Managers/IrregularOutputFinderTests.swift`

- `cuckoo` in `Tests/BitcoinCoreTests/Managers/PublicKeyManagerTests.swift`

- `cuckoo` in `Tests/BitcoinCoreTests/Managers/StateManagerTests.swift`

- `cuckoo` in `Tests/BitcoinCoreTests/Managers/UnspentOutputProviderTests.swift`

- `cuckoo` in `Tests/BitcoinCoreTests/Managers/UnspentOutputSelectorOldTests.swift`

- `cuckoo` in `Tests/BitcoinCoreTests/Managers/UnspentOutputSelectorSingleNoChangeTests.swift`

- `cuckoo` in `Tests/BitcoinCoreTests/Managers/UnspentOutputSelectorTests.swift`

- `cuckoo` in `Tests/BitcoinCoreTests/Managers/WatchedTransactionManagerTests.swift`

- `cuckoo` in `Tests/BitcoinCoreTests/Network/BitcoinCashMainNetTests.swift`

- `cuckoo` in `Tests/BitcoinCoreTests/Network/BitcoinMainNetTests.swift`

- `cuckoo` in `Tests/BitcoinCoreTests/Network/BitcoinRegTestNetTests.swift`

- `cuckoo` in `Tests/BitcoinCoreTests/Network/BitcoinTestNetTests.swift`

- `cuckoo` in `Tests/BitcoinCoreTests/Network/Peer/ConnectionTimeoutManagerTests.swift`

- `cuckoo` in `Tests/BitcoinCoreTests/Network/Peer/PeerAddressManagerTests.swift`

- `cuckoo` in `Tests/BitcoinCoreTests/Network/Peer/PeerGroupTests/BloomFilterManagerDelegateTests.swift`

- `cuckoo` in `Tests/BitcoinCoreTests/Network/Peer/PeerGroupTests/IPeerGroupTests.swift`

- `cuckoo` in `Tests/BitcoinCoreTests/Network/Peer/PeerGroupTests/PeerDelegateTests.swift`

- `cuckoo` in `Tests/BitcoinCoreTests/Network/Peer/PeerGroupTests/PeerGroupTests.swift`

- `cuckoo` in `Tests/BitcoinCoreTests/Network/Peer/PeerGroupTests/PeerHostManagerDelegateTests.swift`

- `cuckoo` in `Tests/BitcoinCoreTests/Network/Peer/PeerManagerTests.swift`

- `cuckoo` in `Tests/BitcoinCoreTests/Network/Peer/PeerTask/GetBlockHashesTaskTests.swift`

- `cuckoo` in `Tests/BitcoinCoreTests/Network/Peer/PeerTask/GetMerkleBlocksTaskTests.swift`

- `cuckoo` in `Tests/BitcoinCoreTests/Network/Peer/PeerTask/RequestTransactionTaskTests.swift`

- `cuckoo` in `Tests/BitcoinCoreTests/Network/Peer/PeerTask/SendTransactionTaskTests.swift`

- `cuckoo` in `Tests/BitcoinCoreTests/Network/Peer/PeerTests/IPeerTaskDelegateTests.swift`

- `cuckoo` in `Tests/BitcoinCoreTests/Network/Peer/PeerTests/IPeerTaskRequesterTests.swift`

- `cuckoo` in `Tests/BitcoinCoreTests/Network/Peer/PeerTests/IPeerTests.swift`

- `cuckoo` in `Tests/BitcoinCoreTests/Network/Peer/PeerTests/PeerConnectionDelegateTests.swift`

- `cuckoo` in `Tests/BitcoinCoreTests/Network/TransactionSenderTests.swift`

- `cuckoo` in `Tests/BitcoinCoreTests/SegWit/SegWitBech32AddressConverterTests.swift`

- `cuckoo` in `Tests/BitcoinCoreTests/Transactions/Builder/InputSignerTests.swift`

- `cuckoo` in `Tests/BitcoinCoreTests/Transactions/OutputSetterTests.swift`

- `cuckoo` in `Tests/BitcoinCoreTests/Transactions/Scripts/ChunkTests.swift`

- `cuckoo` in `Tests/BitcoinCoreTests/Transactions/Scripts/ScriptConverterTests.swift`

- `cuckoo` in `Tests/BitcoinCoreTests/Transactions/Scripts/ScriptTests.swift`

- `cuckoo` in `Tests/BitcoinCoreTests/Transactions/TransactionCreatorTests.swift`

- `cuckoo` in `Tests/BitcoinCoreTests/Transactions/TransactionInputExtractorTests.swift`

- `cuckoo` in `Tests/BitcoinCoreTests/Transactions/TransactionOutputAddressExtractorTests.swift`

- `cuckoo` in `Tests/BitcoinCoreTests/Transactions/TransactionOutputExtractorTests.swift`

- `cuckoo` in `Tests/BitcoinCoreTests/Transactions/TransactionProcessorTests.swift`

- `cuckoo` in `Tests/BitcoinCoreTests/Transactions/TransactionPublicKeySetterTests.swift`

- `cuckoo` in `Tests/BitcoinCoreTests/Transactions/TransactionSizeCalculatorTests.swift`

- `cuckoo` in `Tests/BitcoinCoreTests/Transactions/TransactionSyncerTests.swift`




Untestable sites: none linked for this module/style.



**Summary:** 1 pattern,
65 test doubles,
4 untestable sites.


*Provenance: run `172cdf44-4e56-4735-a4a9-548ddbf6d353`.*


---


## Runtime Hot Paths


No findings — extractor `hot_path_profiler` ran at `e205f951-2475-4c1d-8686-4581b673b75c`,
returned 0 hot-path entries above threshold.


*Provenance: run `e205f951-2475-4c1d-8686-4581b673b75c`.*


---



## Failed Extractors

The following extractors completed their last run with `success=False`. Their data is excluded from this report.

| Extractor | Run ID | Error Code | Message | Next Action |
|-----------|--------|------------|---------|-------------|

| `code_ownership` | `1f77bceb-35e9-4703-bc43-48e38d743abe` | `—` |  | `palace.ingest.run_extractor(name="code_ownership", project="bitcoin-core")` |

| `crypto_domain_model` | `9d25b20d-fe5c-4c5a-b369-270fd5662535` | `—` |  | `palace.ingest.run_extractor(name="crypto_domain_model", project="bitcoin-core")` |

| `dead_symbol_binary_surface` | `7d7398ea-a786-40a6-ae9d-e77fc4714916` | `periphery_fixtures_missing` |  | `palace.ingest.run_extractor(name="dead_symbol_binary_surface", project="bitcoin-core")` |

| `error_handling_policy` | `bea9eab6-8c6b-496e-85a9-d2f651437376` | `—` |  | `palace.ingest.run_extractor(name="error_handling_policy", project="bitcoin-core")` |

| `hotspot` | `525d4d64-67d5-4360-88e4-b330daf0b056` | `—` |  | `palace.ingest.run_extractor(name="hotspot", project="bitcoin-core")` |

| `localization_accessibility` | `91788a84-b957-4c57-997c-addc54c02279` | `—` |  | `palace.ingest.run_extractor(name="localization_accessibility", project="bitcoin-core")` |



---



## Blind Spots

The following extractors have not run for project `bitcoin-core` and are excluded from this report:


All registered audit extractors produced data. No blind spots.



---



## Profile Coverage

| Status | Count |
|--------|-------|
| OK | 9 |
| RUN_FAILED | 6 |
| FETCH_FAILED | 0 |
| NOT_ATTEMPTED | 0 |
| NOT_APPLICABLE | 0 |
| **Total (R)** | **15** |


---


## Provenance

| Field | Value |
|-------|-------|
| Project | `bitcoin-core` |
| Generated at | `2026-05-18T08:03:38.078047+00:00` |
| Fetched extractors | `arch_layer, coding_convention, cross_module_contract, public_api_surface, dependency_surface, reactive_dependency_tracer, testability_di, hot_path_profiler, cross_repo_version_skew` |
| Blind spots | `none` |

| `arch_layer` run ID | `cb4ef7f7-b74b-4b36-9046-d9c86c01eaf5` |

| `coding_convention` run ID | `85836b7b-7a87-49fc-9e08-fc4061149d09` |

| `cross_module_contract` run ID | `778420a2-bc4a-4c5e-b0fe-c6100e383dba` |

| `public_api_surface` run ID | `58d501b7-d363-4c0e-a54a-b994cc00734d` |

| `dependency_surface` run ID | `9fb932e9-beaa-4ae7-a20b-9ebceb09eb5a` |

| `reactive_dependency_tracer` run ID | `99f60886-6a14-499c-b3e0-dff87ba359d6` |

| `testability_di` run ID | `172cdf44-4e56-4735-a4a9-548ddbf6d353` |

| `hot_path_profiler` run ID | `e205f951-2475-4c1d-8686-4581b673b75c` |

| `cross_repo_version_skew` run ID | `0da026c9-0217-449e-ad63-38392a5c0a64` |

