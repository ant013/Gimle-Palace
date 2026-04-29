# Q1: Cross-language FQN format decision — rev2 (GIM-105)

**Status:** Decision committed. Five sub-questions answered for the full 10-language stack.
**Supersedes:** [`2026-04-27-q1-fqn-cross-language.md`](./2026-04-27-q1-fqn-cross-language.md) (rev1, GIM-104, Python+TypeScript only). Rev1 retained for the deeper Variant A/B/C/D rationale; rev2 here is the active contract.
**Grounding:** `services/palace-mcp/src/palace_mcp/extractors/scip_parser.py` and `foundation/models.py` on `origin/develop` HEAD `da3a325`.
**Research method:** voltAgent lang-specialists (python-pro, typescript-pro, java-architect, swift-expert, cpp-pro, rust-engineer) + research-analyst, 2026-04-29; intermediate per-item JSON working notes not committed.
**Predecessor slices:** GIM-101a (foundation), GIM-102 (Python), GIM-104 (TypeScript, also produced rev1), GIM-111 (Java/Kotlin) — all merged.

## TL;DR

| | |
|---|---|
| **Variant B is correct** | `_extract_qualified_name()` (strip scheme+manager+package+version, keep `package_name + descriptors`) is the canonical algorithm. Validated against 5 mature SCIP indexers (Python/TS/Java/Kotlin/Rust) plus C++ via scip-clang. KEEP. |
| **qualified_name MUST NOT include type arguments at use sites** | All 6 SCIP-conformant indexers erase generics at occurrence sites; only Swift USR mangles ABI-style. This is now a hard contract. |
| **TS/JS, Java/Kotlin, RUST/ANCHOR — all stay split** | Per-document `doc.language` distinguishes. Collapsing breaks per-language queries with zero benefit. |
| **Add `TOLK`** | Zero-cost pre-emptive enum entry. TON's next-gen language replaces FunC since 2025; distinct codepath in `ton-language-server`. |
| **Defer Swift, C++, Solidity, FunC, Move** | Each gets a per-language extractor PR with the contract pre-specified here. |
| **12 minimum invariants** below are the contract every future extractor MUST honor. Quote verbatim into Phase 1.1 of any per-language plan. |

## Q1 — Symbol-string format per indexer

Real `Occurrence.symbol` strings (from committed fixtures + indexer source):

| Lang | Indexer | Scheme | Manager | Real example |
|---|---|---|---|---|
| Python | scip-python v0.6.6 | `scip-python` | `python` | `scip-python python pymini 1.0.0 \`src.pymini.greeter\`/Greeter#greet().` |
| TS/JS/TSX/JSX | scip-typescript | `scip-typescript` | `npm` | `scip-typescript npm ts-mini-project 1.0.0 src/\`Cache.ts\`/Cache#put().` |
| Java/Kotlin | scip-java (via SemanticDB) | **`semanticdb`** | `maven` | `semanticdb maven com.example 1.0.0 com/example/Cache#put().` |
| C/C++/Obj-C | scip-clang (beta) | `scip-clang` | **(empty: two spaces)** | `scip-clang  . . util/Formatter#toString().` |
| Rust + Anchor | scip-rust / rust-analyzer | `scip-rust` | `cargo` | `scip-rust cargo mylib 0.1.0 src/lib.rs/\`State\`#process().` |
| Swift | **none** (USR is not SCIP) | — | — | USR: `s:14swift_ide_test1SV` (ABI-mangled, ≠ SCIP) |
| Solidity | **none** | proposed `scip-solidity` | proposed `ethereum` | `scip-solidity ethereum contracts/ERC20.sol . ERC20#transfer(address,uint256).` |
| FunC | **none** (LSP only) | proposed `scip-func` | proposed `ton` | `scip-func ton contracts/wallet.fc . recv_internal(int,int,cell,slice).` |
| Tolk | **none** (LSP only) | proposed `scip-tolk` | proposed `tolk` | `scip-tolk tolk <project> . \`wallet.tolk\`/send_tokens().` |

**Routing gotchas the parser MUST handle:**
- scip-java emits scheme `semanticdb`, NOT `scip-java`. Route by `scheme+manager`, never tool name.
- scip-clang emits empty manager → two consecutive spaces in symbol string. Naive `split(" ")` will produce a wrong token count for malformed-vs-valid checks. Use a parser that tolerates empty fields.
- Smart-contract and Tolk indexers don't exist; the proposed scheme/manager pairs above are the contract for the future per-language PR.

## Q2 — Canonical `qualified_name` format

**Variant B (already in code, line 144 `_extract_qualified_name`) is correct.** Strip first 4 tokens (scheme, manager, package-name, version), keep `package_name + ' ' + descriptor_chain`. Result format: `<package_name> <descriptors-joined>`.

Why keep raw structure (vs deeper normalization):
- The 5 SCIP-conformant indexers all converge on the same EBNF grammar from `scip.proto`. Variant B is the lowest-loss canonical form.
- Stripping version stabilizes identity across library upgrades (the same library symbol is the same node post-bump).
- Keeping the descriptor chain enables round-trip back to SCIP tools and CONTAINS-edge reconstruction.

**One safety upgrade required when scip-clang or scip-kotlin land:** the current naive space-split is not backtick-aware. C++ `\`operator==\``, Kotlin keyword-as-identifier, file-paths-with-dots all need a backtick-tolerant tokenizer. Followup slice when first non-Variant-B-safe language ships.

## Q3 — Generics

**Empirical convergence across all 6 SCIP-conformant indexers: type arguments are stripped at occurrence (use) sites; only at definition sites do type parameters appear as separate `[T]` descriptor symbols.**

| Lang | Definition site | Use site |
|---|---|---|
| scip-python | bare `Cache#`; `[K]` and `[V]` as separate Term descriptors | `Cache#` |
| scip-typescript | `Cache#[K]`, `Cache#[V]` | `Cache#` |
| scip-java (SemanticDB) | erased entirely (`java/util/Map#` regardless of `<K,V>`) | `java/util/Map#` |
| scip-clang | implicit instantiations → primary template; explicit specializations get distinct symbols | `std/map#` |
| scip-rust | `HashMap[K][V]#` | `HashMap#` |
| Swift USR | type-level USR erases T (`s:...6GenClsC`); init mangles via `yxG` | (USR ≠ SCIP) |
| Solidity (proposed) | `mapping(address => uint256)` literal in parameter list (no analog) | same |

**Decision: `qualified_name` MUST NOT include type arguments at use sites. (Invariant #1).** Definition-site type-parameter descriptors ARE valid separate symbols and SHOULD be preserved.

Tantivy tokenization is unaffected by the strip — but is broken for OTHER reasons; see [Followups](#known-gaps--followups).

## Q4 — Language enum

Current `foundation/models.py` enum: `PYTHON, TYPESCRIPT, JAVASCRIPT, JAVA, KOTLIN, SWIFT, RUST, SOLIDITY, FUNC, ANCHOR, UNKNOWN`.

| Decision | Rationale |
|---|---|
| **PYTHON** keep | Distinct indexer + per-document language detection. |
| **TYPESCRIPT + JAVASCRIPT** keep split | Single `scip-typescript` package, but `doc.language` distinguishes `'typescript' / 'javascript' / 'TypeScriptReact' / 'JavaScriptReact'` — fan-out queries break if collapsed. |
| **JAVA + KOTLIN** keep split | Per-document language detection in `scip-java`. Kotlin has companion-object/extension-function quirks Java doesn't. |
| **SWIFT** keep entry, no extractor | macOS+Xcode+DerivedData requirement conflicts with palace-mcp Linux container. Defer; pre-declared enum costs nothing. |
| **RUST + ANCHOR** keep BOTH split | Anchor needs IDL-JSON enrichment, BPF/SBF target, `Anchor.toml` workspace layout, proc-macro `local <id>` workaround — Anchor-specific heuristics on top of shared `scip-rust` parser. |
| **SOLIDITY** keep | `SymbolKind.EVENT` and `SymbolKind.MODIFIER` already declared for it (models.py lines 51-52). |
| **FUNC** keep | Deprecated by Tolk but legacy contracts remain. |
| **ADD `TOLK = "tolk"`** | TON next-gen (replaces FunC, 40% gas reduction, since 2025). Distinct codepath in `ton-language-server`. Zero-cost pre-emptive entry. |
| **CPP, C, OBJC** — defer | Not confirmed in operator stack. When scip-clang extractor PR lands, add three separate entries (do NOT collapse to single CPP). |
| **MOVE / MOVE_SUI / MOVE_APTOS** — do NOT add | Not in operator stack. Sui+Aptos diverge in object model; if ever needed, add as TWO separate entries. |
| **Bug followup** | `_SCIP_LANGUAGE_MAP` (line 167) is missing `'TypeScriptReact'` and `'JavaScriptReact'` keys. `.tsx`/`.jsx` files currently fall through to extension fallback — works but fragile. Fix in TS extractor followup. |

## Q5 — Minimum invariants (the contract)

**Quote these verbatim into the spec frontmatter of every future per-language extractor PR.** Source: SCIP protobuf spec @ `sourcegraph/scip` + cross-validated against all 6 mature indexers.

1. **SYMBOL_INTEGRITY** — Apply Variant B qname extraction (strip scheme+manager+version, keep `package_name + descriptor_chain`). Never further normalize before storing as `:Symbol.qualified_name`.
2. **LOCAL_CONTAINMENT** — `local <id>` symbols never enter the global `:Symbol` pool. If ever stored, key as `<doc_path>:local:<id>`. Must never appear in `Index.external_symbols`.
3. **ROLE_BITSET** — Decode `Occurrence.symbol_roles` with bitwise AND (`role&0x1`, `role&0x4`, ...), never equality. Multiple bits can be set simultaneously (e.g., `Definition|Test = 0x21`).
4. **DESCRIPTOR_SUFFIX_ROUTING** — Use `Descriptor.suffix` enum values (`1=Namespace, 2=Type, 3=Term, 4=Method, 5=TypeParameter, 6=Parameter, 7=Meta, 8=Local, 9=Macro`) for label/relationship routing. Never string-pattern-match on suffix characters.
5. **ENCLOSING_SYMBOL_EDGES** — If `SymbolInformation.enclosing_symbol` is non-empty, emit `:CONTAINS` edge from it to this symbol. If absent, reconstruct from descriptor chain.
6. **RELATIONSHIPS_OPTIONAL** — Never hard-fail on empty `SymbolInformation.relationships`. Emit `:IMPLEMENTS`/`:TYPE_DEF` only when present.
7. **WRITEACCESS_DEGRADATION** — If neither `WriteAccess` (0x4) nor `ReadAccess` (0x8) bit set on a non-Definition occurrence, emit undirected `:REFERENCES` edge. Never drop the reference.
8. **KIND_FALLBACK** — When `SymbolInformation.kind == UnspecifiedKind (0)`, fall back to descriptor-suffix heuristics. Never block ingest on missing kind.
9. **EXTERNAL_SYMBOLS** — `Index.external_symbols` are dependency symbols. Ingest as `:Symbol` nodes WITHOUT `:DEFINED_IN` edges.
10. **STREAMING** — Parse SCIP index one Document at a time. Never load full Index into memory. (50M+ occurrence indexes break naive parsers.)
11. **BACKTICK_UNESCAPE** — Symbol parser must handle backtick-escaped names (`\`operator==\``, `\`some name with spaces\``) and unescape `` `` `` → `` ` `` before using name as Neo4j key.
12. **VERSION_PLACEHOLDER** — Version `.` means unversioned (project-local). Treat differently from real version strings in cross-version deduplication logic.

## Per-language action map

| Lang | Action in this commit | Deferred to per-language PR |
|---|---|---|
| Python | None — Variant B validated against `py-mini-project` fixture | Cross-ingest dedup risk (def-site `src.pymini.cache` vs import-site `pymini.cache`) — alias resolution |
| TypeScript / JavaScript | None | Fix `_SCIP_LANGUAGE_MAP` to include `TypeScriptReact`/`JavaScriptReact` |
| Java / Kotlin | None — generics-erasure invariant codified above | Consume `enclosing_symbol`, `kind`, `relationships` (currently ignored) |
| Swift | Enum entry exists; mark deferred | USR→SCIP converter (~1000 LOC Swift macOS + 200 LOC Python). Re-evaluate when iOS work needs symbol-graph |
| C / C++ / Obj-C | (no enum entry yet) | Add `CPP`, `C`, `OBJC` separately; ~600-900 LOC for scip-clang adapter (handles empty-manager + backtick + header-dedup) |
| Rust | None | Standard scip-rust parser shares Variant B path |
| Anchor (Solana) | None — separate enum entry stays | Anchor IDL JSON enrichment layer (`target/idl/<program>.json` → instruction discriminators, account fields, error codes) |
| Solidity | None — `SOLIDITY` already declared | Custom AST→SCIP via solc `--ast-compact-json` + slither (~600-900 LOC). Dual identity: source FQN + ABI 4-byte selector. `EVENT`/`MODIFIER` SymbolKinds confirmed |
| FunC | None — `FUNC` already declared | Low priority (Tolk replaces). Custom AST via tree-sitter or LSP batch (~300-500 LOC if ever) |
| **Tolk** | **ADD `TOLK = "tolk"` to enum** | Custom SCIP emitter on `ton-language-server` AST when operator confirms Tolk usage |
| Move (Sui/Aptos) | Do not add | Defer indefinitely; not in stack |

## Smart-contract source-vs-ABI identity

For Solidity (and any future EVM-style language with stable selectors), use **dual identity**:
- **Primary:** source-level qualified_name `contracts/ERC20.sol:ERC20.transfer(address,uint256)` — stable within a version, scoped per `group_id`.
- **Secondary:** ABI 4-byte selector `0xa9059cbb` as an indexed field on the `:Symbol` node — stable across cosmetic refactors, useful for cross-contract interface detection (ERC20, ERC721).

Never use ABI selector as primary `qualified_name` — collides across contracts that share signatures.

For FunC: source-level only. Get-method `method_id` (crc16-derived, e.g., `97865` for `get_balance`) goes in a secondary indexed field.

For Move: source-level only (`<address>::<module>::<function>`). On-chain address instability blocks cross-deploy identity — register `address → version` mapping if ever pursued.

## Known gaps & followups

1. **Tantivy tokenization regression** — default whitespace+lowercase tokenizer doesn't split on `/`, `#`, `.`, `(`, `)`, `:`, `,`. Query `Cache` misses `com/example/Cache#put().`. Affects all languages equally. Fix: custom analyzer treating SCIP descriptor delimiters as token boundaries. Sized as a dedicated infra slice.
2. **palace-mcp scip_parser does NOT consume** `SymbolInformation.kind`, `enclosing_symbol`, `relationships`, `doc.language` (always empty in py fixture). Four separate followup slices to leverage these for Neo4j edges (CONTAINS, IMPLEMENTS, TYPE_DEF) and replace heuristic kind detection.
3. **Backtick-aware parser** — current `_extract_qualified_name()` is naive `split(" ")`. Fine for Python/TS/Java/Rust today; will fail on C++ operators and Kotlin keywords. Fix when first non-safe extractor PR lands.
4. **Python cross-ingest dedup** — same module emits different qname at def-site vs import-site (`src.pymini.cache` vs `pymini.cache`). Risk: duplicate `:Symbol` nodes. Alias resolution slice required if multi-project Python ingest scales.
5. **scip-clang empty-manager parsing** — current parser tolerates two consecutive spaces by accident (split fills `parts[1]=''`). Verify explicitly when scip-clang extractor PR lands.

## What palace-mcp does TODAY (no code change)

The current implementation (`origin/develop` HEAD `da3a325`) is **conformant** with this decision for the three production extractors (Python, TypeScript, Java/Kotlin). No retroactive code change needed to comply with the 12 invariants — they describe the existing contract.

## What this commit ADDS

- This document (`docs/research/2026-04-27-q1-fqn-cross-language.md`).
- `Language.TOLK = "tolk"` added to `services/palace-mcp/src/palace_mcp/extractors/foundation/models.py` (zero-cost pre-emptive).

Per-language extractor implementation belongs in dedicated GIM slices following this contract.
