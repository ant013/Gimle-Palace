# Multi-Language Foundation Design: Pre-Extractor Schema Decisions

**Consumer:** CTO (architectural decisions) + downstream extractor implementers (schema dictates their work)
**Decision context:** Palace-mcp knowledge graph — canonical schemas for cross-language symbol storage, occurrence scale strategy, and dependency modeling across 9 ecosystems
**Recency window:** Sources from last 18 months (Oct 2024 — Apr 2026) unless older required for canonical reference (language specs, RFCs). Older sources flagged with date.
**Issue:** GIM-100
**Branch:** `feature/research-multi-language-foundation`
**Date:** 2026-04-27

---

## Executive Summary

This report answers three foundational design questions for palace-mcp's multi-language knowledge graph before any extractor implementation begins. The 9 target ecosystems are: Python, Kotlin, Swift, Rust, Solidity, FunC, Anchor/Solana, JavaScript, TypeScript.

**Key findings:**

1. **Q1 (FQN):** SCIP's symbol grammar is the most mature cross-language FQN standard in production use. 6 of 9 target languages already have SCIP indexers. We should adopt SCIP's format verbatim for covered languages and produce SCIP-compatible symbols via custom `palace` scheme extractors for Swift, Solidity, and FunC. Cross-language bridge edges (SKIE, Anchor IDL, JNI, WASM) are modeled as `:BRIDGES_TO` relationships.

2. **Q2 (SymbolOccurrence scale):** 30-70M occurrence nodes are within Neo4j 5.x's demonstrated operating range (benchmarked at 50M+ nodes). Start with all-in-Neo4j (option A) for operational simplicity on iMac hardware, with a clear migration path to Hybrid (option C) with Tantivy sidecar if performance degrades. The memory constraint (~21-47 GB RAM needed) is the primary risk factor.

3. **Q3 (ExternalDependency):** A unified `(:ExternalDependency)` node with `ecosystem` + `registry_url` + `name` as the identity triple works across all 9 ecosystems without special-casing. Per-ecosystem extractors share a base class. FunC/TON has no on-chain dependency system — its dependencies are npm packages for tooling only ([MATERIAL GAP]).

---

## Top-3 Recommendations (ranked by decision impact)

### 1. Adopt SCIP symbol grammar as the canonical `qualified_name` format [HIGHEST IMPACT]

**Why:** This is the single most consequential schema decision — every extractor, every query, every cross-language link depends on the FQN format. SCIP is battle-tested at Sourcegraph across 10+ languages and adopted by Mozilla Searchfox and Meta's Glean. Choosing a custom format means building all tooling from scratch; choosing SCIP means leveraging existing indexers for 6/9 languages.

**What:** Store `qualified_name` as SCIP symbol strings: `<scheme> <manager> <package-name> <version> <descriptor-chain>`. Use `palace` as scheme for languages without SCIP indexers (Swift, Solidity, FunC).

**Risk:** Swift and Solidity need custom SCIP-compatible symbol generators. FunC has no namespace system at all.

### 2. Start with All-in-Neo4j for SymbolOccurrence, plan Hybrid escape hatch [HIGH IMPACT]

**Why:** Adding Tantivy now doubles operational complexity (new Rust dependency, FFI bridge, index lifecycle, consistency coordination) for a workload that Neo4j can handle at current scale. The migration path to Hybrid is well-defined and can be triggered by monitoring thresholds.

**What:** Store all occurrences as Neo4j nodes with composite indexes. Set monitoring threshold: if DB size exceeds 60% of page cache or query p95 exceeds 100ms, begin Hybrid migration.

**Risk:** 70M occurrences on 32 GB iMac RAM will be tight. May need to start with 30M ceiling and GC aggressively.

### 3. Use ecosystem+registry+name identity triple for ExternalDependency [MEDIUM IMPACT]

**Why:** Prevents cross-ecosystem name collisions (e.g., `base64` exists on npm, PyPI, and crates.io). Avoids JVM-specific `group:artifact` patterns bleeding into the universal schema. Version lives on edges, not the node.

**What:** `uid = sha256(ecosystem + ":" + registry_url + ":" + name)` as unique constraint. One extractor per ecosystem with shared base class.

**Risk:** Low — this is a well-understood pattern.

---

## Q1 — Cross-Language FQN Unification

### 1.1 Per-Language Native FQN Format

#### Python

**Native mechanism:** `__module__` + `__qualname__` (PEP 3155, Python 3.3+) [HIGH]

- Full FQN = `__module__ + "." + __qualname__`
- Nested functions use `<locals>` as synthetic component

| Construct | `__qualname__` | Full FQN |
|---|---|---|
| Top-level function `def foo()` in `pkg.mod` | `foo` | `pkg.mod.foo` |
| Class method `class C: def f()` in `pkg.mod` | `C.f` | `pkg.mod.C.f` |
| Nested class `class C: class D:` | `C.D` | `pkg.mod.C.D` |
| Module-level constant `X = 42` | N/A | `pkg.mod.X` (convention) |
| Nested function `def f(): def g():` | `f.<locals>.g` | `pkg.mod.f.<locals>.g` |

Sources:
- PEP 3155: https://peps.python.org/pep-3155/ (accessed 2026-04-27)
- Python Data Model: https://docs.python.org/3/reference/datamodel.html (accessed 2026-04-27)

#### Kotlin

**Native mechanism:** `KClass<T>.qualifiedName` — dot-separated FQN including package. [HIGH]

- For local classes/anonymous objects, `qualifiedName` returns `null` (JVM target)
- On JS/Wasm targets, inconsistent support (KT-71517) [MEDIUM]

| Construct | FQN |
|---|---|
| Top-level function `fun foo()` in `com.example` | `com.example.foo` |
| Class method `class C { fun f() }` | `com.example.C.f` |
| Nested class `class C { class D }` | `com.example.C.D` |
| Companion object | `com.example.C.Companion` |

Sources:
- Kotlin stdlib API: https://kotlinlang.org/api/core/kotlin-stdlib/kotlin.reflect/-k-class/qualified-name.html (accessed 2026-04-27)
- KT-71517: https://youtrack.jetbrains.com/projects/KT/issues/KT-71517 (accessed 2026-04-27)

#### Swift

**Native mechanism:** Name mangling (`$s` prefix, Swift 4.0+). Demangled form uses `.` separated `Module.Type.member`. [HIGH]

| Construct | Demangled FQN |
|---|---|
| Top-level function | `MyMod.foo()` |
| Class method | `MyMod.MyClass.method(arg:)` |
| Nested type | `MyMod.A.B` |

Sources:
- Swift ABI Mangling spec: https://github.com/apple/swift/blob/main/docs/ABI/Mangling.rst (accessed 2026-04-27)

#### Rust

**Native mechanism:** v0 symbol mangling (RFC 2603). Human-readable path uses `::` separator. [HIGH]

- As of nightly-2025-11-21, v0 is the default mangling on nightly

| Construct | Human-readable path |
|---|---|
| Top-level function | `mycrate::foo` |
| Method | `<mycrate::MyStruct>::method` |
| Trait impl | `<mycrate::MyStruct as mycrate::MyTrait>::method` |
| Nested module + struct | `mycrate::sub::Inner` |

Sources:
- RFC 2603: https://rust-lang.github.io/rfcs/2603-rust-symbol-name-mangling-v0.html (accessed 2026-04-27)
- v0 Symbol Format: https://doc.rust-lang.org/rustc/symbol-mangling/v0.html (accessed 2026-04-27)
- Rust Blog on v0 switch: https://blog.rust-lang.org/2025/11/20/switching-to-v0-mangling-on-nightly/ (accessed 2026-04-27)

#### Solidity

**Native mechanism:** `ContractName.memberName` within compilation model. Library linking uses `source_unit:ContractName`. [MEDIUM]

| Construct | FQN |
|---|---|
| Contract function | `ERC20.transfer` |
| Nested struct | `C.S` |
| Library function | `Math.add` |

Sources:
- Solidity docs: https://docs.soliditylang.org/en/latest/contracts.html (accessed 2026-04-27)

#### FunC (TON) [MATERIAL GAP]

**No formal FQN system.** [LOW]

- No modules, packages, namespaces, or classes
- Functions identified by plain names within `#include` chain
- Method IDs computed by CRC of function name
- Tact (compiling to FunC) has module-like imports but no standardized FQN

| Construct | Identifier |
|---|---|
| Top-level function | `recv_internal` |
| Helper function | `calculate_fee` |
| Constant | `SEND_MODE` |

Sources:
- TON FunC docs: https://ton.org/secure-smart-contract-programming-in-func (accessed 2026-04-27)

#### Anchor/Solana

**Native mechanism:** Standard Rust `::` paths + Anchor IDL JSON layer. [HIGH]

| Construct | Rust FQN | IDL name |
|---|---|---|
| Instruction | `my_program::initialize` | `"initialize"` |
| Account struct | `my_program::Init` | `"Init"` |

- Discriminators: `sha256("global:instruction_name")[:8]`

Sources:
- Anchor docs: https://www.anchor-lang.com/docs/basics/program-structure (accessed 2026-04-27)
- Anchor IDL: https://www.anchor-lang.com/docs/basics/idl (accessed 2026-04-27)

#### JavaScript

**No built-in FQN system.** [HIGH]

- ES modules use file-path-based resolution
- `Function.name` provides name but NOT qualified path
- Tooling (scip-typescript) creates synthetic FQNs from file paths

| Construct | Conventional identifier |
|---|---|
| Named export in `src/utils.js` | `src/utils.foo` |
| Class method | `src/utils.C.method` |

Sources:
- MDN Function.name: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Function/name (accessed 2026-04-27)
- Node.js ESM resolution: https://nodejs.org/api/esm.html#resolution-algorithm (accessed 2026-04-27)
- scip-typescript: https://github.com/sourcegraph/scip-typescript (accessed 2026-04-27)

#### TypeScript

**Native mechanism:** `typeChecker.getFullyQualifiedName(symbol)` from compiler API. [HIGH]

- Returns quoted module paths: `"src/utils".MyClass.method`
- TypeScript namespaces produce `Namespace.Type.member`

Sources:
- TypeScript Compiler API: https://github.com/microsoft/TypeScript/wiki/Using-the-Compiler-API (accessed 2026-04-27)
- scip-typescript blog: https://sourcegraph.com/blog/announcing-scip-typescript (accessed 2026-04-27)

### 1.2 Semantic Index Tool Outputs

#### SCIP (Sourcegraph Code Intelligence Protocol)

**SCIP Symbol Format** (canonical grammar from `scip.proto`): [HIGH]

```
<symbol>     ::= <scheme> ' ' <package> ' ' (<descriptor>)+ | 'local ' <local-id>
<package>    ::= <manager> ' ' <package-name> ' ' <version>
<descriptor> ::= <namespace> | <type> | <term> | <method> | <type-parameter> | <parameter> | <meta> | <macro>
```

**Descriptor suffixes:**
- `/` = namespace (module, package)
- `#` = type (class, struct, enum, interface)
- `.` = term (variable, constant, field)
- `().` = method (with optional `(+N)` disambiguator for overloads)
- `[T]` = type parameter
- `(param)` = parameter
- `!` = macro

**SCIP Indexer Coverage for 9 Target Languages:**

| Language | SCIP Indexer | Status | Scheme |
|---|---|---|---|
| **Python** | scip-python 0.4.x | Production | `scip-python` |
| **Kotlin** | scip-java 0.12.x | Production (covers Kotlin) | `scip-java` |
| **Swift** | **None** | [MATERIAL GAP] | N/A |
| **Rust** | rust-analyzer v0.3.2870 (2026-04-20) | Production | `rust-analyzer` |
| **Solidity** | **None** | [MATERIAL GAP] (enum exists: `Solidity=95`) | N/A |
| **FunC** | **None** | [MATERIAL GAP] | N/A |
| **Anchor/Solana** | rust-analyzer (Rust layer) | Partial | `rust-analyzer` |
| **JavaScript** | scip-typescript 0.4.0 | Production | `scip-typescript` |
| **TypeScript** | scip-typescript 0.4.0 | Production | `scip-typescript` |

**Example SCIP symbols:**
```
rust-analyzer cargo main . foo/Bar#              -- struct Bar in module foo, crate main
scip-java maven com.example app 1.0 com/example/MyClass#myMethod(+1).  -- overloaded Java method
scip-python pip mypackage 1.0 mypackage/module/MyClass#method().       -- Python class method
```

Sources:
- SCIP proto (as of Feb 2026, last indexed): https://github.com/sourcegraph/scip/blob/main/scip.proto (accessed 2026-04-27)
- SCIP docs: https://github.com/sourcegraph/scip/blob/main/docs/scip.md (accessed 2026-04-27)
- scip-code.org: https://scip-code.org/ (accessed 2026-04-27)
- rust-analyzer SCIP: https://rust-lang.github.io/rust-analyzer/src/rust_analyzer/cli/scip.rs.html (accessed 2026-04-27)
- scip-python: https://github.com/sourcegraph/scip-python (accessed 2026-04-27)
- scip-java: https://sourcegraph.github.io/scip-java/ (accessed 2026-04-27)

#### Tree-sitter / Stack Graphs

**Tree-sitter tags:** Produces `(name, role, kind, location)` tuples. Does NOT produce qualified names — only simple names with roles. [HIGH]

**Stack graphs (GitHub):** Extend tree-sitter for name resolution via graph structures where paths represent valid name bindings. Produce FQNs like `stove.broil` for Python. Language-agnostic but requires per-language DSL rules. As of the 2021 blog post, used for Python, TypeScript, Java, Ruby at GitHub. [HIGH] [VERSION GAP — 2021 coverage claim; current language support may differ]

Sources:
- Tree-sitter Code Navigation: https://tree-sitter.github.io/tree-sitter/4-code-navigation.html (accessed 2026-04-27)
- GitHub stack graphs blog: https://github.blog/open-source/introducing-stack-graphs/ (accessed 2026-04-27)

#### LSP

**`textDocument/documentSymbol`** returns `DocumentSymbol[]` with `name`, `kind`, `range`, `children` — no explicit FQN field. `SymbolInformation` has optional `containerName`. FQN must be reconstructed by client. No canonical FQN format defined by LSP. [HIGH]

Source: LSP 3.17 spec: https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/ (accessed 2026-04-27)

### 1.3 Special Cases Catalog

#### Generics/Templates

| Language | Handling |
|---|---|
| Python | PEP 695 generics NOT reflected in `__qualname__` — `class C[T]` -> `"C"` |
| Kotlin | `qualifiedName` excludes type parameters — `List<String>` -> `kotlin.collections.List` |
| Swift | Mangled name encodes generic parameters fully |
| Rust | v0 mangling encodes generics: `I <path> {<generic-arg>} E` |
| Solidity | No generics |
| FunC | No generics |
| JS/TS | SCIP omits type args from symbol |
| **SCIP** | Type parameters get `[T]` descriptors; generic instantiations are NOT separate symbols |

#### Lambdas and Anonymous Functions

| Language | Handling |
|---|---|
| Python | `<lambda>` in `__qualname__` — NOT unique |
| Kotlin | Anonymous -> inner classes `$1`, `$2`. No stable FQN |
| Swift | `closure #1 (Type) -> Type in Module.Function` |
| Rust | `{closure#0}`, `{closure#1}` within enclosing function |
| JS/TS | `Function.name` is `""` for arrows; SCIP uses local symbols |
| Solidity/FunC | No lambdas |

#### Trait/Protocol Implementations

| Language | Handling |
|---|---|
| Rust | `<Type as Trait>::method` in v0 mangling. SCIP rust-analyzer currently flattens |
| Swift | Protocol conformance encoded in mangled form |
| Kotlin | Interface impl has same FQN as class method. SCIP uses `Relationship.is_implementation` edges |
| Solidity | C3 linearization for inheritance, no distinct FQN for overrides |

#### Extension Methods

| Language | Handling |
|---|---|
| Kotlin | Compiled to static methods. FQN: `com.example.UtilsKt.myExtension` |
| Swift | Mangled with extended type's module+name |
| Rust | Inherent impls: `<Type>::method`. No separate "extension" concept |

#### Macros

| Language | Handling |
|---|---|
| Rust | `!` suffix in SCIP: `my_macro!`. Proc macros have own crate path |
| Solidity/FunC | No user-defined macros |

#### Overloaded Functions

| Language | Handling |
|---|---|
| Kotlin | SCIP uses `(+1)`, `(+2)` method disambiguators |
| Swift | Full type signature in mangled name |
| Rust | No function overloading |
| TypeScript | Overload signatures share same SCIP symbol |
| Solidity | Selector from `function_name(type1,type2)` |

### 1.4 Canonical Recommendation: SCIP-Aligned Format with Palace Scheme

**Canonical `qualified_name` format:**

```
<scheme> <manager> <package-name> <version> <descriptor-chain>
```

Fields are space-separated (matching SCIP exactly). Descriptor suffixes use SCIP conventions (`/` namespace, `#` type, `.` term, `().` method, `!` macro, `[T]` type param, `(param)` parameter).

**Per-language scheme/manager mappings:**

| Language | scheme | manager | package-name example | Example symbol |
|---|---|---|---|---|
| Python | `scip-python` | `pip` | `mypackage` | `scip-python pip mypackage 1.0.0 mypackage/module/MyClass#method().` |
| Kotlin | `scip-java` | `maven` | `com.example:app` | `scip-java maven com.example:app 1.0 com/example/MyClass#method(+1).` |
| Swift | `palace` | `spm` | `MyModule` | `palace spm MyModule 1.0 MyModule/MyClass#method().` |
| Rust | `rust-analyzer` | `cargo` | `my_crate` | `rust-analyzer cargo my_crate 0.1.0 my_module/MyStruct#method().` |
| Solidity | `palace` | `npm` | `@openzeppelin/contracts` | `palace npm @openzeppelin/contracts 5.0 ERC20#transfer().` |
| FunC | `palace` | `.` | `my_contract` | `palace . my_contract . recv_internal().` |
| Anchor | `rust-analyzer` | `cargo` | `my_program` | `rust-analyzer cargo my_program 0.1.0 instructions/initialize().` |
| JavaScript | `scip-typescript` | `npm` | `my-lib` | `scip-typescript npm my-lib 1.0.0 src/utils.js/MyClass#method().` |
| TypeScript | `scip-typescript` | `npm` | `my-lib` | `scip-typescript npm my-lib 1.0.0 src/utils.ts/MyClass#method().` |

**Key design decisions:**

1. **Use SCIP grammar directly** — battle-tested at Sourcegraph, Mozilla Searchfox, Meta Glean [HIGH]
2. **For languages WITH SCIP indexers** (Python, Kotlin, Rust, JS, TS): use indexer output verbatim
3. **For languages WITHOUT SCIP indexers** (Swift, Solidity, FunC): use `palace` scheme, same grammar
4. **Version field:** package version when available; `.` placeholder when none (FunC contracts)
5. **Generics:** NOT encoded in symbol (SCIP convention). `[T]` only for type parameter definitions
6. **Lambdas/closures:** `local N` symbols (SCIP local symbols) — not externally addressable
7. **Trait impls:** Standard SCIP descriptors with `Relationship` edges (`is_implementation: true`)
8. **Overloads:** SCIP `(+N)` disambiguator in method descriptor

**Why not alternatives:**
- JVM internal names (`com/example/C`) — only works for JVM languages
- Universal `::` separator — conflicts with Rust, doesn't map to Python dots or JS file paths
- URI-based (`lang://package/path#symbol`) — more complex, no existing ecosystem
- Custom format — loses SCIP indexer ecosystem for 6 languages

### 1.5 Cross-Language Linkage

#### Swift <-> Kotlin via SKIE Bridge (KMP)

SKIE generates Swift wrapper code on top of Kotlin/Native ObjC headers. [HIGH]

**Graph edge:**
```
(:Symbol {qualified_name: "palace spm shared 1.0 DataManager#fetchData()."})
  -[:BRIDGES_TO {bridge_type: "skie", direction: "kotlin_to_swift"}]->
(:Symbol {qualified_name: "scip-java maven com.example:shared 1.0 com/example/DataManager#fetchData()."})
```

Sources:
- SKIE docs: https://skie.touchlab.co/ (accessed 2026-04-27)
- Kotlin/Native ObjC interop: https://kotlinlang.org/docs/native-objc-interop.html (accessed 2026-04-27)

#### Anchor Solana <-> JavaScript/TypeScript

Anchor IDL JSON bridges Rust instructions to JS/TS client code. [HIGH]

**Graph edge:**
```
(:Symbol {qualified_name: "scip-typescript npm @project/client 1.0 src/client.ts/initialize()."})
  -[:CALLS_VIA {bridge_type: "anchor_idl", program_id: "...", discriminator: "afaf6d1f0d989bed"}]->
(:Symbol {qualified_name: "rust-analyzer cargo my_program 0.1.0 instructions/initialize()."})
```

#### JNI (Java/Kotlin to Native)

JNI uses deterministic C function name from Java FQN: `Java_com_example_Native_nativeMethod`. [HIGH]

#### WASM

WASM exports functions by name strings. wasm-bindgen creates JS glue code analyzable for mapping. [MEDIUM]

#### General Cross-Language Edge Schema

```
(:Symbol)-[:BRIDGES_TO {
  bridge_type: "skie" | "anchor_idl" | "jni" | "wasm_export" | "objc_header" | "ffi",
  confidence: 0.0..1.0,
  direction: "a_calls_b" | "bidirectional",
  mapping_source: "static_analysis" | "idl" | "naming_convention" | "manual"
}]->(:Symbol)
```

Populated by: static analysis of IDL/ABI files, naming convention parsers, bridge tool output analysis, manual annotation.

---

## Q2 — SymbolOccurrence Storage Scale & Strategy

### 2.1 Neo4j 5.x Empirical Scale Data

#### Storage Format and Per-Node Overhead

**Neo4j 5.x Block Format (block.x1.db):** Each node gets a static 128-byte block at offset `128 * nodeId`. Contains two 64-byte records for node data and relationship data. [HIGH]

Source: https://neo4j.com/docs/operations-manual/current/database-internals/store-formats/ (accessed April 2026)

**Per-SymbolOccurrence estimated cost:** ~200-350 bytes on disk (128-byte base block + string property storage). [MEDIUM — derived from official format docs + disk planning formulas from https://sgerogia.github.io/Disk-Capacity-Planning-for-Neo4J/]

**For 30-70M occurrences:**
- Node storage: 9-21 GB
- Relationship storage (one edge per occurrence to Symbol): 4-9 GB
- **Total: 13-30 GB for occurrence graph alone** [MEDIUM]

#### Insertion Throughput

**neo4j-admin import (offline):** [HIGH — multiple sources]
- 788M nodes + 4.2B relationships in ~2 hours (Neo4j 5.20). ~100K+ nodes/sec sustained. (Source: https://community.neo4j.com/t/extremely-slow-import-for-large-graph-database-using-neo4j-admin-import/27347)
- 6B nodes + 10B relationships in 2-3 hours on optimized hardware. (Source: https://community.neo4j.com/t/load-csv-very-slow-with-millions-of-nodes/7786)

**UNWIND MERGE (online):** [HIGH — multiple sources]
- 7M items in ~107s (65K items/sec). Linear scaling. (Source: https://achantavy.github.io/cartography/performance/cypher/neo4j/2020/07/19/loading-7m-items-to-neo4j-with-and-without-unwind.html)
- 20K-55K nodes/sec with batched UNWIND, scaling with parallelism. (Source: https://neo4j.com/blog/nodes/nodes-2019-best-practices-to-make-large-updates-in-neo4j/)
- Mix-and-batch: ~60K relationships/sec with 12 vCPUs. (Source: https://neo4j.com/blog/developer/mix-and-batch-relationship-load/)

**Projected load for 30-70M occurrences:**
- `neo4j-admin import` (offline): **5-15 minutes**
- UNWIND MERGE (online): **20-50 minutes** including relationship creation

#### Query Latency

**Neo4j 5.x Parallel Runtime** benchmarked on Stack Overflow data (50M nodes, 124M rels). Significant speedups for listing and aggregation queries. (Source: https://neo4j.com/blog/developer/cypher-performance-neo4j-5/) [MEDIUM]

- Point lookups (indexed property match + relationship traversal): **1-50ms** when in page cache [MEDIUM]
- "Find all occurrences of symbol X" with composite index: **1-20ms** for typical fan-outs (10-1000 per symbol) [MEDIUM — inferred from benchmark patterns]
- 100M+ nodes with 16GB RAM: OOM on complex aggregation; simple indexed lookups work with proper page cache. (Source: https://community.neo4j.com/t/how-to-efficiently-query-over-100-million-nodes-on-a-system-with-16gb-ram/69755)

#### Memory Requirements

**Rule of thumb** (Neo4j official): `Total Memory = Heap + Page Cache + OS`. Page cache = store size + 10%. [HIGH]

Source: https://neo4j.com/docs/operations-manual/current/performance/memory-configuration/ (accessed April 2026)

For 30-70M occurrence nodes:
- Page cache: 15-35 GB
- Heap: 4-8 GB
- OS: 2-4 GB
- **Total: 21-47 GB RAM recommended** [MEDIUM]

**Note:** These estimates cover occurrence nodes only. Existing graph data (Symbol nodes, ExternalDependency nodes, paperclip ingest nodes, edges) will add ~10-20% overhead depending on graph size. Budget accordingly.

#### Published Limits

- Neo4j theoretical: up to 2^45 (~35T) node IDs [HIGH]
- Practical single-instance: 50M-200M nodes commonly reported [MEDIUM]
- Neo4j "Infinigraph" for beyond single-machine scale announced 2025. (Source: https://neo4j.com/blog/news/2025-ai-scalability/) [HIGH]

### 2.2 Tantivy + Lucene Benchmarks

#### Tantivy 0.24.x (Rust, MIT)

- **~2x faster than Lucene** on search benchmarks. Confirmed by Lucene committer Adrien Grand. (Sources: https://www.paradedb.com/learn/tantivy/introduction; https://seekstorm.github.io/SeekStorm.github.io/) [HIGH]
- Startup: <10ms. (Source: ParadeDB docs) [MEDIUM]
- Indexing: 40% improvement in 0.22 via specialized term hashmap. (Source: https://quickwit.io/blog/tantivy-0.22) [MEDIUM]
- Query latency (warm): single-digit ms for point lookups. ~8ms search on 10M documents across 32 shards. (Source: https://www.shayon.dev/post/2025/314/a-hypothetical-search-engine-on-s3-with-tantivy-and-warm-cache-on-nvme/) [MEDIUM]
- mmap-based, uses OS page cache. Very efficient on commodity hardware. [MEDIUM]
- Write model limitation: segments are immutable (WORM). Updates = insert-new + delete-old. [HIGH]

#### Sourcegraph Zoekt

- Trigram-based code search. Sub-second queries across billions of lines of code, 1M+ repos. (Source: https://sourcegraph.com/code-search) [HIGH]
- **Limitation:** Designed for full-text code search, not structured occurrence records. Poor fit for our workload. [SPECULATIVE]

#### GitHub Blackbird

- Scale: 53B files, 200M+ repos, 115 TB code. 5,184 vCPUs, 40 TB RAM. (Source: https://github.blog/engineering/architecture-optimization/the-technology-behind-githubs-new-code-search/) [HIGH]
- Custom ngram index (not just trigrams). 120K docs/sec ingest. p99 ~100ms per shard. [HIGH]
- Demonstrates inverted indexes are industry standard for code occurrence at massive scale.

#### GitLab Code Search

Uses Elasticsearch. [MATERIAL GAP] — no specific benchmarks at our scale found.

#### Projected Tantivy Performance for Our Workload [MEDIUM — inferred]

- **Indexing 30-70M records:** 1-10 minutes (100K-500K docs/sec for simple documents)
- **Index size:** 2-5 GB (compact fields)
- **Query latency:** sub-ms to low single-digit ms for term lookups
- **Memory:** 2-8 GB RSS (mmap-based)

### 2.3 Tradeoff Matrix

| Dimension | (A) All-in-Neo4j | (B) Tantivy Sidecar | (C) Hybrid | (D) Just-in-Time |
|---|---|---|---|---|
| **Insertion (5-10M/repo)** | neo4j-admin: 5-15m; MERGE: 20-50m [HIGH] | 1-5m [MEDIUM] | Fast sidecar + minimal graph [MEDIUM] | Zero (no storage) [HIGH] |
| **Query latency** | 1-20ms indexed lookups [MEDIUM] | Sub-ms to low-ms [MEDIUM] | Best of both [SPECULATIVE] | Seconds-minutes (tree-sitter parse) [MEDIUM] |
| **Storage (30-70M)** | 13-30 GB [MEDIUM] | 2-5 GB [MEDIUM] | 2-5 GB total [SPECULATIVE] | Zero persistent [HIGH] |
| **Ops complexity** | Low (Neo4j already in stack) [HIGH] | Medium (new dep, FFI, lifecycle) [MEDIUM] | Medium-High (two systems) [SPECULATIVE] | Low ops, high compute [MEDIUM] |
| **Schema flexibility** | Excellent (add properties freely) [HIGH] | Good (re-index for schema changes) [MEDIUM] | Good [SPECULATIVE] | Excellent (no schema) [HIGH] |
| **Multi-tenant** | Good (group_id filtering) [HIGH] | Good (per-project indexes) [MEDIUM] | Good [SPECULATIVE] | Inherent (separate repos) [HIGH] |

**Scoring (1-5, weighted):**

Ops complexity carries 2x weight for iMac single-operator deployment — adding a new system has outsized operational cost. All other dimensions weighted 1x.

| Dimension | Weight | A | B | C | D |
|---|---|---|---|---|---|
| Insertion | 1x | 3 | 5 | 4 | 5 |
| Query latency | 1x | 4 | 5 | 5 | 1 |
| Storage | 1x | 2 | 4 | 4 | 5 |
| Ops complexity | **2x** | 5 (10) | 3 (6) | 2 (4) | 4 (8) |
| Schema flexibility | 1x | 5 | 4 | 4 | 5 |
| Multi-tenant | 1x | 5 | 4 | 4 | 5 |
| **Weighted Total** | | **29** | **28** | **25** | **29** |

Option A and D tie at 29. D is eliminated because seconds-to-minutes query latency (score 1) is unacceptable for interactive MCP tool calls. **A wins on ops simplicity with acceptable query performance.**

### 2.4 Recommendation: All-in-Neo4j with Hybrid Escape Hatch

**Recommended: Option (A) — All-in-Neo4j, with migration path to (C) Hybrid if performance degrades.**

**Rationale:**

1. **Operational simplicity paramount on iMac hardware.** Neo4j is the sole persistence layer. Tantivy = new Rust dep + FFI/sidecar + index lifecycle + consistency coordination. Marginal performance gain doesn't justify complexity. [HIGH]

2. **30-70M within Neo4j's range.** Stack Overflow benchmark (50M nodes, 124M rels) runs successfully on Neo4j 5.x with Parallel Runtime. [HIGH]

3. **Memory is the main risk.** 30M occurrences ~ 21 GB RAM; 70M ~ 47 GB. iMac with 32 GB handles the lower end; 64 GB needed for upper. **Mitigation:** aggregate occurrence counts on Symbol nodes (`ref_count`, `definition_files`) so most queries never touch occurrence nodes. [MEDIUM]

4. **Offline bulk load fast.** neo4j-admin import: <15 min for 30-70M. UNWIND MERGE: adequate for batch pipeline. [HIGH]

5. **Graph connectivity advantage.** "Find all symbols referenced by files that also reference symbol X" — trivial in Neo4j, requires joins in sidecar. [MEDIUM]

6. **Clear escape hatch.** If degradation occurs: keep Symbol nodes in Neo4j (500K-2M), move occurrence records to Tantivy. Query routing by pattern. [MEDIUM]

**Implementation guardrails:**
- Composite indexes on `(:SymbolOccurrence {symbol_fqn})` and `(:SymbolOccurrence {file_path})`
- UNWIND batch size: 5,000-10,000 per transaction
- `server.memory.pagecache.size` >= store size + 20%
- Prune aggressively: delete occurrences on re-index, don't accumulate
- **Monitor threshold:** DB size > 60% of page cache OR query p95 > 100ms -> begin Hybrid migration

---

## Q3 — Unified ExternalDependency Schema

### 3.1 Per-Ecosystem Manifest Survey

#### Python (pip / pyproject.toml)

| Property | Value |
|---|---|
| **Manifest** | `pyproject.toml` (TOML, PEP 621); legacy: `setup.py`, `requirements.txt` |
| **Lockfile** | `poetry.lock` (TOML), `uv.lock` (TOML-like); pip has no native lockfile |
| **Identifier** | Simple name, PEP 503 normalized: `requests`, `numpy` |
| **Version syntax** | PEP 440: `>=1.0,<2.0`, `~=1.4.2`, `==1.0.0`; Poetry adds `^1.0` |
| **Registry** | https://pypi.org/simple/ |
| **Resolution** | SAT-based (pip 20.3+), flat `site-packages` |
| **Special** | Extras (optional deps), markers (`; python_version < "3.11"`), path/git deps |

[HIGH] Sources: PEP 440 https://peps.python.org/pep-0440/, PEP 621 https://peps.python.org/pep-0621/, Poetry docs https://python-poetry.org/docs/dependency-specification/ (accessed 2026-04-27)

#### Kotlin/JVM (Gradle)

| Property | Value |
|---|---|
| **Manifest** | `build.gradle.kts` (Kotlin DSL); `gradle/libs.versions.toml` (Version Catalog) |
| **Lockfile** | `gradle.lockfile` (opt-in, per-configuration) |
| **Identifier** | Maven GAV: `org.jetbrains.kotlin:kotlin-stdlib:1.9.22` |
| **Version syntax** | Exact `"1.9.22"`, range `"[1.0,2.0)"`, dynamic `"1.+"`, rich `strictly`/`require`/`prefer` |
| **Registry** | Maven Central, Google Maven, Artifactory/Nexus |
| **Resolution** | Flat, highest-version-wins. Configurations: `implementation`, `api`, `compileOnly`, etc. |
| **Special** | Version catalogs, BOM/platform support, project deps, capability conflicts |

[HIGH] Sources: Gradle docs https://docs.gradle.org/current/userguide/declaring_dependencies.html, Version catalogs https://docs.gradle.org/current/userguide/version_catalogs.html (accessed 2026-04-27)

#### Swift/iOS (SPM, CocoaPods, Carthage)

| Property | SPM | CocoaPods | Carthage |
|---|---|---|---|
| **Manifest** | `Package.swift` (Swift) | `Podfile` (Ruby DSL) | `Cartfile` (text) |
| **Lockfile** | `Package.resolved` (JSON) | `Podfile.lock` (YAML) | `Cartfile.resolved` |
| **Identifier** | Git URL | Pod name | `github "Org/Repo"` |
| **Version** | `.from("5.0")`, `.exact()`, `.branch()` | `~> 5.6`, `>= 1.0` | `~> 5.6` |
| **Registry** | No public registry (git-based) | CocoaPods trunk | None (GitHub) |

[HIGH] Sources: SPM overview https://inrhythm.com/blog-post/a-comprehensive-introduction-to-swift-package-manager/, CocoaPods/Carthage comparison https://blog.stackademic.com/efficient-ios-dependency-management-with-swift-package-manager-cocoapods-and-carthage-bbcf639d7e92 (accessed 2026-04-27)

#### Rust (Cargo)

| Property | Value |
|---|---|
| **Manifest** | `Cargo.toml` (TOML); workspace `[workspace.dependencies]` |
| **Lockfile** | `Cargo.lock` (TOML) — exact versions, checksums |
| **Identifier** | Crate name: `serde`, `tokio`. Flat namespace. Aliasing via `package` key |
| **Version syntax** | Caret `"1.2.3"` (default), tilde `"~1.2.3"`, exact `"=1.2.3"`, range, git, path |
| **Registry** | https://crates.io/ |
| **Resolution** | SAT-based. Allows multiple semver-incompatible versions in one tree |
| **Special** | Features (compile-time flags), workspace inheritance, resolver v2, platform-specific deps |

[HIGH] Sources: Cargo book https://doc.rust-lang.org/cargo/reference/specifying-dependencies.html, Features https://doc.rust-lang.org/cargo/reference/features.html (accessed 2026-04-27)

#### Solidity/EVM (Foundry/Hardhat)

| Property | Foundry (Soldeer) | Hardhat |
|---|---|---|
| **Manifest** | `foundry.toml` `[dependencies]` / `soldeer.toml` | `package.json` (npm) |
| **Lockfile** | `soldeer.lock` (SHA-256 hashes) | npm/yarn/pnpm lockfiles |
| **Identifier** | Soldeer name: `@openzeppelin-contracts` | npm name: `@openzeppelin/contracts` |
| **Version** | Semver ops `^`, `~`, `>=`, `=` | npm semver |
| **Registry** | https://soldeer.xyz/ | npm |
| **Special** | Import remappings (`remappings.txt`) unique to Solidity |

[HIGH] Sources: Soldeer 0.10.1 (2026-02-16) USAGE.md https://github.com/mario-eth/soldeer/blob/main/USAGE.md, Hardhat 3 docs https://hardhat.org/docs/guides/writing-contracts/dependencies (accessed 2026-04-27)

#### FunC/TON [MATERIAL GAP]

**No on-chain dependency system.** [LOW]

- Build system: Blueprint SDK (`@ton/blueprint` 0.42.0, npm package)
- Smart contract languages: FunC, Tolk, Tact
- Dependencies are npm packages for tooling: `@ton/core`, `@ton/crypto`, `@tact-lang/compiler`
- No contract-level package registry or dependency management
- TON's 2025 roadmap mentions "shared libraries for smart contracts" as future feature — not yet available [SPECULATIVE — no direct roadmap URL found; based on community discussion]

[LOW] Sources: TON Blueprint https://docs.ton.org/contract-dev/blueprint/overview, Tact compilation https://docs.tact-lang.org/book/compile/ (accessed 2026-04-27)

#### Anchor/Solana

**Three manifest layers:** [HIGH]

1. `Cargo.toml` — Rust crate dependencies (`anchor-lang`, `solana-program`)
2. `Anchor.toml` — workspace config, program addresses, toolchain versions (NOT dependency declarations)
3. `package.json` — TypeScript client dependencies (`@coral-xyz/anchor`, `@solana/web3.js`)

**Lockfiles:** `Cargo.lock` (Rust), `yarn.lock`/`package-lock.json` (TS)

Sources: Anchor.toml reference https://www.anchor-lang.com/docs/references/anchor-toml, Organization https://rareskills.io/post/organizing-solana-programs (accessed 2026-04-27)

#### JavaScript (npm/pnpm/yarn)

| Property | Value |
|---|---|
| **Manifest** | `package.json` (JSON) |
| **Lockfile** | `package-lock.json`, `yarn.lock`, `pnpm-lock.yaml` |
| **Identifier** | Scoped/unscoped: `react`, `@types/react`, `@babel/core` |
| **Version syntax** | `^1.2.3` (caret, default), `~1.2.3`, ranges, exact, git, file, aliases |
| **Registry** | https://registry.npmjs.org/ |
| **Resolution** | npm: flat dedup; pnpm: strict symlinked; yarn berry: PnP |
| **Special** | `dependencies`, `devDependencies`, `peerDependencies`, `optionalDependencies`, workspaces, `overrides` |

[HIGH]

#### TypeScript

Same as JavaScript ecosystem. Additional: `tsconfig.json` `paths` mapping, `@types/*` devDependencies, module resolution modes. [HIGH]

### 3.2 Conflict & Overlap Analysis

#### Cross-Ecosystem Name Collisions

| Name | npm | PyPI | crates.io | Notes |
|---|---|---|---|---|
| `base64` | yes | yes | yes | Completely different packages |
| `requests` | yes | yes | no | Different functionality |

**Schema implication:** `(ecosystem, registry, name)` triple required for uniqueness. Name alone insufficient. [HIGH]

#### Lockfile vs Manifest Precedence

| Ecosystem | Source of truth for installed version |
|---|---|
| Python (pip) | No lockfile; resolved at install time |
| Python (Poetry/uv) | Lockfile pins exact |
| Rust | `Cargo.lock` pins exact |
| JS (npm/yarn/pnpm) | Lockfile pins exact |
| Gradle | `gradle.lockfile` if enabled |
| Swift SPM | `Package.resolved` pins exact |
| CocoaPods | `Podfile.lock` pins exact |
| Foundry/Soldeer | `soldeer.lock` pins exact + SHA-256 |

**Schema implication:** Must store both `version_constraint` (manifest) and `resolved_version` (lockfile) — version_constraint on `:DEPENDS_ON` edge, resolved_version on `:RESOLVES_TO` edge. [HIGH]

#### Vendored Dependencies

| Ecosystem | Mechanism |
|---|---|
| Foundry (legacy) | Git submodules in `lib/` |
| Foundry (Soldeer) | ZIPs in `dependencies/` |
| CocoaPods | Copied into `Pods/` |
| Cargo | `cargo vendor` into `vendor/` (opt-in) |
| npm | `node_modules/` (always, just not committed) |

**Schema implication:** `source_type` property: `registry | git | path | vendored`. [HIGH]

#### Ecosystem-Specific Gotchas

- **npm flat vs pnpm strict:** Same `package.json`, different behavior under different managers [HIGH]
- **Cargo features:** Dependency pulled with different feature sets by different dependents. Additive unification. Unique to Rust [HIGH]
- **Gradle configurations:** `implementation`/`api`/`compileOnly` change transitive visibility [HIGH]
- **Solidity remappings:** Import paths are filesystem prefixes, not package names [HIGH]
- **Anchor dual-ecosystem:** One project, two dependency trees (Cargo + npm) [HIGH]
- **TON:** npm-only for tooling. No on-chain deps [MATERIAL GAP]

### 3.3 Canonical Schema Proposal

#### `:ExternalDependency` Node

```cypher
(:ExternalDependency {
  // === IDENTITY (unique constraint) ===
  uid:              String!   // sha256(ecosystem + ":" + registry_url + ":" + name)
  name:             String!   // "serde", "@types/react", "org.jetbrains.kotlin:kotlin-stdlib"
  ecosystem:        String!   // "python" | "kotlin_jvm" | "swift" | "rust" | "solidity_evm"
                              // | "ton" | "anchor_solana" | "javascript" | "typescript"
  registry_url:     String?   // "https://pypi.org/simple/", "https://crates.io/", null for git/path

  // === VERSION ===
  latest_version:   String?   // latest version seen in any lockfile

  // === METADATA ===
  description:      String?
  license:          String?   // SPDX identifier
  homepage_url:     String?

  // === ENRICHMENT (secondary extractors) ===
  cve_ids:          String[]? // CVE identifiers from vulnerability scanner
  deprecated:       Boolean?
  last_published:   DateTime?

  // === HOUSEKEEPING ===
  group_id:         String!   // "project/gimle"
  created_at:       DateTime!
  updated_at:       DateTime!
})
```

**Design decisions:**
1. **`ecosystem` as property, not label** — single query pattern `MATCH (d:ExternalDependency {ecosystem: $eco})`. Optional secondary labels (`:RustCrate`, `:NpmPackage`) for query optimization [HIGH]
2. **`name` carries full identifier** — GAV for JVM (`org.jetbrains.kotlin:kotlin-stdlib`), scoped for npm (`@types/react`), simple for Cargo/Python. Avoids JVM-specific `group_id/artifact_id` columns [HIGH]
3. **No version on node** — represents the package itself. Versions live on edges [HIGH]

#### Edge: `:DEPENDS_ON`

```cypher
(:Project|:Module)-[:DEPENDS_ON {
  version_constraint: String!   // "^1.2.3", ">=1.0,<2.0", "~> 5.6"
  scope:              String!   // "runtime" | "dev" | "build" | "test" | "compile_only" | "peer" | "optional"
  optional:           Boolean!  // default false
  features:           String[]? // Cargo features, Gradle capabilities

  source_type:        String!   // "registry" | "git" | "path" | "url"
  source_ref:         String?   // git URL/branch/rev, path, ZIP URL

  configuration:      String?   // Gradle: "implementation"|"api"; Solidity: remapping prefix; CocoaPods: subspec
  platform_filter:    String?   // 'cfg(target_os = "linux")', '; python_version < "3.11"'

  manifest_file:      String!   // "Cargo.toml", "package.json", etc.
  group_id:           String!
}]->(:ExternalDependency)
```

**Scope mapping:**

| Ecosystem | Scope values |
|---|---|
| Python | `runtime`, `dev`, `optional` |
| Cargo | `runtime`, `dev`, `build` |
| Gradle | `runtime`, `compile_only`, `test`, `runtime_only` |
| npm/TS | `runtime`, `dev`, `peer`, `optional` |
| Swift SPM | `runtime` |
| CocoaPods | `runtime`, `dev` |
| Foundry | `runtime` |
| Anchor | `runtime` + `dev` + `build` (Cargo); `runtime` + `dev` (npm) |

#### Edge: `:RESOLVES_TO`

```cypher
(:Project|:Module)-[:RESOLVES_TO {
  resolved_version:  String!   // exact: "1.2.3", commit SHA for git deps
  integrity_hash:    String?   // SHA-256/SHA-512 from lockfile
  lockfile:          String!   // "Cargo.lock", "yarn.lock", "soldeer.lock"
  resolved_at:       DateTime?
  group_id:          String!
}]->(:ExternalDependency)
```

**Rationale for separate edge:** Single `:ExternalDependency` node can have multiple `:DEPENDS_ON` from different modules with different constraints, all resolving to same lockfile version. [HIGH]

#### Unique Constraint

```cypher
CREATE CONSTRAINT exdep_uid FOR (d:ExternalDependency) REQUIRE d.uid IS UNIQUE;
```

`uid = sha256(ecosystem + ":" + registry_url + ":" + name)` [HIGH]

### 3.4 Cross-Extractor Coordination

#### Extractor Architecture: One Per Ecosystem with Shared Base

```
BaseExternalDependencyExtractor (abstract)
  +-- PythonDependencyExtractor        # pyproject.toml, setup.cfg, poetry.lock, uv.lock
  +-- CargoDependencyExtractor         # Cargo.toml, Cargo.lock (pure Rust + Anchor)
  +-- GradleDependencyExtractor        # build.gradle.kts, libs.versions.toml, gradle.lockfile
  +-- NpmDependencyExtractor           # package.json, lockfiles (JS, TS, TON, Hardhat)
  +-- SwiftDependencyExtractor         # Package.swift, Package.resolved, Podfile, Podfile.lock
  +-- SolidityDependencyExtractor      # foundry.toml (soldeer), soldeer.lock, remappings.txt
```

**Why per-ecosystem, not universal:** Each manifest format needs its own parser. A universal extractor = 2000-line monolith. Per-ecosystem = 200-400 lines each, independently testable. [HIGH]

**Shared base provides:** MERGE logic, edge creation, `uid` generation, `group_id` scoping.

#### Enrichment Extractors

| Enricher | Adds | Trigger |
|---|---|---|
| VulnerabilityScanner | `cve_ids`, `deprecated` | After dependency extraction; queries OSV/GitHub Advisory |
| LicenseExtractor | `license` | Queries registry APIs |
| MetadataExtractor | `description`, `homepage_url`, `last_published` | Queries registry APIs |

Enrichers use `MATCH ... SET` — never create nodes. [HIGH]

#### Idempotency & MERGE Strategy

```cypher
MERGE (d:ExternalDependency {uid: $uid})
ON CREATE SET d.name=$name, d.ecosystem=$ecosystem, d.registry_url=$registry_url,
              d.group_id=$group_id, d.created_at=datetime(), d.updated_at=datetime()
ON MATCH SET  d.updated_at=datetime()
```

Stale edges GC'd by comparing extracted edges against existing for same `(module, manifest_file)` pair. [HIGH]

#### Extraction Ordering

**Dependency extractors run BEFORE symbol extractors:** [HIGH]
1. `file_tree` (maps filesystem)
2. `dependency` (parses manifests, creates `:ExternalDependency` nodes)
3. `symbol` (parses source, creates `:Symbol` nodes, links to deps via `:IMPORTED_FROM`)

---

## Cross-Schema Consistency Check (Q1 x Q2 x Q3)

| Integration point | Q1 (FQN) | Q2 (Occurrences) | Q3 (Dependencies) | Status |
|---|---|---|---|---|
| Symbol identity | `qualified_name` in SCIP format | `symbol_fqn` references same format | `:IMPORTED_FROM` edge links to dep's FQN | **Consistent** [HIGH] |
| Package/version | SCIP `<manager> <package> <version>` | N/A | `:ExternalDependency {ecosystem, name}` | **Compatible** [HIGH] — SCIP's package maps to ExternalDependency node |
| Ecosystem scoping | `scheme` field identifies ecosystem | `group_id` scopes to project | `ecosystem` property | **Consistent** [HIGH] — different fields, same intent |
| Scale | ~500K-2M symbol nodes | 30-70M occurrence nodes | ~5K-50K dependency nodes | **No conflict** [MEDIUM] — occurrence scale drives storage decision |

---

## [MATERIAL GAP] Flags

| Gap | Area | Impact | Mitigation |
|---|---|---|---|
| No SCIP indexer for Swift | Q1 | Must build custom `palace` scheme extractor | Use `swift-demangle` + tree-sitter for FQN generation |
| No SCIP indexer for Solidity | Q1 | Must build custom `palace` scheme extractor | Use `solc --ast-compact-json` + ABI for FQN |
| No SCIP indexer for FunC | Q1 | Must build custom `palace` scheme extractor | Flat namespace, simple mapping |
| FunC has no namespace system | Q1 | All FunC FQNs are flat (`recv_internal`) | Acceptable — FunC contracts are small |
| No on-chain dependency system for TON | Q3 | Can only model npm tooling deps | Flag as ecosystem limitation |
| GitLab code search benchmarks | Q2 | Cannot compare Elasticsearch approach | Use Zoekt/Blackbird data as proxy |
| Neo4j 5.26-specific benchmarks | Q2 | Closest data is 5.x general | [STALE-RISK] on older community reports |
| Tantivy for structured records | Q2 | Benchmarks are for full-text, not our pattern | Projected numbers are [SPECULATIVE] |

---

## [VERSION GAP] Flags

| Claim | Version cited | Risk |
|---|---|---|
| Neo4j block format 128-byte blocks | Neo4j 5.x (block.x1.db) | Format may change in 5.27+ |
| Tantivy ~2x faster than Lucene | Tantivy 0.22-0.24.x | Lucene may close gap in future versions |
| SCIP symbol format | scip.proto as of Apr 2026 | SCIP is still evolving (see open issues) |
| rust-analyzer SCIP output | rust-analyzer nightly | Some trait impl flattening may change |
| Soldeer in Foundry | Soldeer 0.10.1 (Feb 2026) | Soldeer is young, API may change |
| Stack Graphs language coverage | Blog post 2021 | Current language support may differ |

---

## Follow-Up Questions for Unanswered Axes

1. **Swift SCIP indexer priority:** Should we build a custom palace-swift SCIP-compatible extractor, or wait for potential community efforts? SourceKit-LSP outputs some symbol data — is it sufficient as a bridge? **Decision owner: CTO**

2. **Neo4j memory ceiling on target iMac:** What is the actual RAM available after other services (Docker, palace-mcp itself, Neo4j heap)? This directly determines whether 30M or 70M occurrences are feasible. **Decision owner: InfraEngineer/Operator**

3. **Tantivy migration trigger:** Should the Hybrid escape hatch be pre-built as a plugin interface, or implemented only when threshold is hit? Pre-building adds complexity now; waiting risks a harder migration later. **Decision owner: CTO**

4. **FunC/Tact evolution:** TON's roadmap mentions "shared libraries for smart contracts." If this launches, the dependency schema may need a `ton_shared_lib` source_type. Monitor? **Decision owner: Board (low priority)**

5. **Anchor IDL bridge automation:** The cross-language edge between Rust instructions and TS client calls could be auto-generated from IDL JSON. Is this a priority for the bridge extractor? **Decision owner: CTO**

6. **SCIP version pinning strategy:** SCIP proto evolves. Should we pin to a specific commit of `scip.proto` and vendor it, or track upstream? **Decision owner: MCPEngineer**

---

## Source Summary Table

| Source | Type | Date | Tier | Used in |
|---|---|---|---|---|
| SCIP proto (sourcegraph/scip) | Official spec | Apr 2026 | 1 | Q1 |
| scip-code.org | Official docs | Apr 2026 | 1 | Q1 |
| PEP 3155, 440, 621 | Language spec | 2012-2021 | 1 | Q1, Q3 |
| Kotlin stdlib API docs | Official docs | Apr 2026 | 1 | Q1 |
| Swift ABI Mangling spec | Official spec | Apr 2026 | 1 | Q1 |
| Rust RFC 2603 | Language spec | 2018 | 1 | Q1 |
| Rust Blog (v0 mangling) | Official blog | Nov 2025 | 1 | Q1 |
| Solidity docs | Official docs | Apr 2026 | 1 | Q1, Q3 |
| Anchor docs | Official docs | Apr 2026 | 1 | Q1, Q3 |
| TON Blueprint docs | Official docs | Apr 2026 | 1 | Q1, Q3 |
| LSP 3.17 spec | Official spec | Apr 2026 | 1 | Q1 |
| GitHub stack graphs blog | Official blog | 2021 | 1 | Q1 |
| Tree-sitter docs | Official docs | Apr 2026 | 1 | Q1 |
| Neo4j Store Formats docs | Official docs | Apr 2026 | 1 | Q2 |
| Neo4j Memory Configuration | Official docs | Apr 2026 | 1 | Q2 |
| Neo4j Parallel Runtime blog | Official blog | Nov 2024 | 2 | Q2 |
| Neo4j NODES 2019 updates | Official conf | 2019 | 2 | Q2 |
| UNWIND benchmark (achantavy) | Engineering blog | 2020 | 2 | Q2 |
| neo4j-admin import community | Community report | 2024 | 3 | Q2 |
| Mix-and-batch blog | Official blog | 2022 | 2 | Q2 |
| Memgraph comparison | Vendor benchmark | 2023 | 3 | Q2 |
| Max De Marzi benchmark | Expert blog | Jan 2023 | 2 | Q2 |
| 100M+ nodes community | Community report | 2024 | 3 | Q2 |
| Disk capacity planning (sgerogia) | Community blog | 2019 [STALE-RISK] | 3 | Q2 |
| Neo4j Infinigraph announcement | Official blog | 2025 | 1 | Q2 |
| ParadeDB Tantivy introduction | Official docs | Apr 2026 | 1 | Q2 |
| Tantivy 0.22 release (Quickwit) | Maintainer blog | Sep 2024 | 2 | Q2 |
| SeekStorm benchmark | Benchmark | 2024 | 3 | Q2 |
| Tantivy on S3 (shayon.dev) | Engineering blog | 2025 | 3 | Q2 |
| GitHub Blackbird blog | Official blog | 2023 | 1 | Q2 |
| Sourcegraph Zoekt | Official product | Apr 2026 | 1 | Q2 |
| Cargo book | Official docs | Apr 2026 | 1 | Q3 |
| Gradle docs | Official docs | Apr 2026 | 1 | Q3 |
| Poetry docs | Official docs | Apr 2026 | 1 | Q3 |
| Soldeer USAGE.md | Source code | Apr 2026 | 1 | Q3 |
| Hardhat 3 docs | Official docs | Apr 2026 | 1 | Q3 |
| Tact compilation docs | Official docs | Apr 2026 | 1 | Q3 |
| SPM overview (InRhythm) | Technical blog | Apr 2026 | 2 | Q3 |
| SKIE docs (Touchlab) | Official docs | Apr 2026 | 1 | Q1 |
| Kotlin/Native ObjC interop | Official docs | Apr 2026 | 1 | Q1 |
