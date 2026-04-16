# BlockchainEngineer — Research Notes

**Research date:** 2026-04-16
**Purpose:** inform `paperclips/roles/blockchain-engineer.md` (Slice #11)
**Target:** expert advisor для wallet-client architecture + crypto code analysis (особенно Unstoppable Wallet integration)

## 1. Sources reviewed

| Source | Stars | Relevance | Signal |
|---|---|---|---|
| **VoltAgent `blockchain-developer.md`** | ~17k | direct | EVM-security checklist (reentrancy, overflow, oracle), `slither`/`mythril` invocation patterns — base prompt reference |
| **wshobson/agents `blockchain-web3` plugin** | ~33k | inventory | 4 skills (DeFi, NFT, Solidity security, Web3 testing) — нет wallet-client agent — **gap** |
| **VoltAgent Binance Skills Hub** | — | crypto data | `query-token-audit` / `query-address-info` / `trading-signal` — единственные production-grade crypto skills |
| **Anthropic Red Team — $4.6M smart contract exploit** | — | methodology | Static-first + LLM-second = dual confidence at <$2/run. Подтверждает pattern "static check before reasoning" |
| **Etherscan MCP server** (`crazyrabbitLTC`) | — | tooling | 72+ networks, ABI lookup, gas data — primary on-chain context source |
| garrytan/gstack | ~73k | none | 0 blockchain agents — gap в top repos |
| Anthropic Cookbook | — | none | Нет wallet-specific examples |

5 directly applicable sources. **Common gap:** community покрывает EVM/Solidity but NOT wallet-client architecture (BIP32/39/44, multi-chain abstraction, key storage).

## 2. Stack tools mapping (orchestration plan)

| Trigger | Subagent / Tool | Why |
|---|---|---|
| Kotlin wallet kit code | `voltagent-lang:kotlin-specialist` | Gradle multi-module, coroutines, SPV patterns |
| Swift wallet code (iOS) | `voltagent-lang:swift-expert` | Secure Enclave, Keychain APIs |
| Smart contract security | `voltagent-qa-sec:security-auditor` | Slither/Mythril wrapper |
| Mobile attack surface | `voltagent-qa-sec:penetration-tester` | OWASP Mobile Top-10 |
| DeFi/Swap interface design | `voltagent-core-dev:api-designer` | Chain-agnostic abstraction |
| On-chain context | Etherscan MCP | Live transaction/balance/ABI data |
| CVE lookup | `voltagent-research:search-specialist` | NVD + GitHub advisories sweep |
| Generic blockchain checklist | VoltAgent `blockchain-developer` prompt | Base reference |

**NOT use:** `voltagent-lang:rust-engineer` для Solana — Unstoppable обычно через SDK wrappers, native Rust только если инжестируем Solana labs source.

## 3. Top-3 Gimle-specific additions (нет в community)

### 3.1 Wallet taxonomy для palace-mcp graph
Per spec §5.4.1: `HandlesMnemonic` / `HandlesNonce` / `HandlesChain` / `HandlesAddress` nodes. Unique add: **`bip44_coin_type` annotations** (Bitcoin=0, Ethereum=60, Solana=501) на `:Module` nodes. Позволяет MCP запросы типа "какой module отвечает за Solana?" без full scan.

### 3.2 Kit-abstraction graph для Unstoppable
Unstoppable использует 15+ kit-libraries (`bitcoin-kit-android`, `ethereum-kit-android`, etc). Unique task: определить chain-agnostic interfaces (`IAdapter`, `IWalletManager`, `ISendBitcoinAdapter`) как первоклассные `:Interface` nodes. Без этого LLM путает concrete `EthereumAdapter` с general `Adapter`.

### 3.3 Key-storage check #1 priority
`verify_keystore_usage` — первый static check, до LLM. iOS: Keychain SecItem / SecureEnclave / access groups. Android: AndroidKeyStore / EncryptedSharedPreferences. Anti-pattern: UserDefaults / SharedPreferences plaintext. Подтверждено Anthropic red-team study — static-first, LLM-second.

## 4. Subagent invocation triggers (full table — see role file)

Главный value этой role — **знание когда что вызывать**, не исполнение. Specific triggers документированы в template.

## 5. Final template structure (95 lines role)

1. Role + advisor scope (NOT implementer)
2. Зона ответственности (5 artifacts) + НЕ зона
3. 5 invocation triggers (mnemonic keywords highest priority)
4. 5 принципов (static-first, key-storage #1, multi-chain abstraction, BIP44 derivation, smallest safe change)
5. Subagent orchestration table (8 triggers → subagent)
6. MCP servers + skills (Etherscan, Binance Skills, serena, context7)
7. Advisory output checklist
8. Skills + fragment includes
