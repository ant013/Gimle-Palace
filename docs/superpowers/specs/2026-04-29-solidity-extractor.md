---
slug: solidity-extractor
status: rev2 (board draft — incorporates 11-point critique)
branch: feature/GIM-124-solidity-extractor (cut from develop @ 82b909e)
paperclip_issue: GIM-124
predecessor: 82b909e (GIM-123 hardening sweep merged)
date: 2026-04-29
parent_initiative: N+2 Extractor cycle — first smart-contract language
related: GIM-105 rev2 (Q1 FQN cross-language decision), GIM-102 (Python pattern), GIM-104 (TS pattern), GIM-111 (JVM pattern)
depends_on: GIM-105 rev2 doc on develop (provides scheme/manager/dual-identity contract)
---

# Slice GIM-124 — Solidity extractor (`symbol_index_solidity`)

## Goal

Ship the **first smart-contract-language extractor** in the N+2 cycle. Solidity is the EVM smart-contract language across the operator's stack; this slice opens the door to FunC (TON) and Anchor (Solana) extractors that follow the same custom-AST→SCIP pattern.

Validation: dogfood on a vendored **OpenZeppelin Contracts v5 subset** (~6 contracts, **MIT**, solc 0.8.20+, the canonical Solidity reference library). Demonstrates **modern** Solidity patterns — custom errors (0.8.4+), `immutable`, multi-level inheritance, interface implementation, library `Context` pattern, ERC20-standard events/state — using the de-facto reference library every operator-stack DeFi project imports.

## Sequence

Fourth content extractor (after Python, TS+JS, Java+Kotlin). First non-SCIP-native language: Solidity has **no first-party SCIP indexer**, so we synthesize SCIP-shaped output from solc + slither.

## Hard dependencies

- **GIM-105 rev2 merged on develop** — provides scheme/manager/qualified_name/dual-identity decisions. Locked at SHA `81586fe`.
- Foundation substrate (GIM-101a) — provides scip_parser, Tantivy bridge, eviction, checkpoint, circuit breaker. Lang-agnostic since GIM-104.
- `Language.SOLIDITY = "solidity"` already declared (`foundation/models.py:34`).
- `SymbolKind.EVENT` and `SymbolKind.MODIFIER` already declared (`foundation/models.py:51-52`, added during 101a Architect F23).

## Architecture decisions

### From GIM-105 rev2 §Per-language action map — Solidity (locked)

| Decision | Value |
|---|---|
| SCIP scheme | `scip-solidity` |
| SCIP manager | `ethereum` |
| Package-name | Source-file path relative to project root (e.g. `contracts/token/ERC20/ERC20.sol`) |
| Version token | `.` placeholder |
| Descriptor chain | Contract = type `#`; Function/Event/Modifier = method `().`; StateVar = term `.`; Library = type `#` (treat like contract); Struct/Enum = type `#` |
| Generics policy | `keep_brackets` — `mapping(K => V)` literal type strings preserved, backtick-escaped |
| Qualified_name | `{relative_file_path}:{ContractName}.{memberName}({param_types})` after Variant B strip |
| Dual identity | Primary: source FQN. Secondary: ABI 4-byte selector (keccak4 of canonical signature) on `:Symbol.abi_selector` for externally-callable functions only |
| Local symbols | Skip pure function-body locals; store contract members globally |
| Cross-repo navigation | Symbols scoped per `group_id`. ABI selectors enable cross-contract interface detection (ERC20 etc.) — secondary index only |

### Open decisions resolved in rev2 of this spec

**SCIP-detour is preserved** (vs AST → :Symbol/:Occurrence directly). Rationale:
- Single ingest pipeline (`iter_scip_occurrences`) shared across all 4+ languages — bug fixes in substrate benefit all.
- Forward-compat: if Sourcegraph ships scip-solidity in future, swap is byte-compatible.
- Drift-test pattern via committed `.scip` provides regression detection (modulo non-determinism — see §Risks).

Cost paid: ~250 LOC `scip_emit/solidity.py` + ~1 binary blob in repo + structural-compare tests (NOT bit-exact — see §Risks). Acceptable trade.

**Slither is IN scope as AST walker**, contrary to v1 plan. Rationale:
- `slither.core.declarations.Contract` walker handles `linearizedBaseContracts` traversal, override resolution, library `using-for` resolution out of the box.
- `slither.core.declarations.Function.canonical_name` provides normalized signatures (uint→uint256 alias resolved) — directly feeds ABI selector computation.
- `slither.core.declarations.SolidityFunction` enumerates events/modifiers correctly.
- Without slither, our custom AST walker would re-implement ~150 LOC of well-tested code.

What's still **out** for v1: data-flow edges (`function.variables_read` / `variables_written`). That's a separate slice when `:READS`/`:WRITES` Neo4j edges are on roadmap.

**`scip_emit/` as a package** (vs single module). Rationale: pre-emptive for FunC and Anchor extractors which will follow the same custom-AST→SCIP pattern. Single-module would force refactor when the second smart-contract language ships.

**`pycryptodome` for keccak4** (vs `eth-utils`, `pysha3`, hand-rolled). Rationale:
- `pysha3` unmaintained (stuck at Python 3.10).
- `eth-utils` heavyweight (5+ MB transitive); only need keccak.
- `pycryptodome` actively maintained, has `Crypto.Hash.keccak`, likely already a transitive dep via crypto-aware graphiti/neo4j.
- Hand-rolled adds risk of bugs vs minimal dep cost.

## Non-goals (explicitly defer)

- **Slither data-flow edges** (`variables_read` / `variables_written`) — separate slice when Neo4j `:READS`/`:WRITES` edges are on roadmap.
- **Foundry-vs-Hardhat layout abstraction** — fixture is Foundry-style; other layouts handled when operator's real projects ship.
- **Multi-version solc support** — fixture pinned to **0.8.20+** (OZ v5's required version). solc 0.5/0.6/0.7 syntax NOT exercised; followup slice can add a legacy fixture (e.g., Uniswap V2/V3) only if a real operator-stack project on legacy solc surfaces.
- **Inline assembly** — `assembly { ... }` blocks treated opaque; no symbol extraction inside. Documented limitation. OZ v5 has minimal assembly (only in low-level utilities outside the chosen subset).
- **Drift-check via byte-equality** — protobuf serialization is non-deterministic; v1 has no `index.scip` byte-equality test. Followup may add structural-compare regen test if useful.
- **Path-rename robustness** — qualified_name embeds file path; renames invalidate `:Symbol`. Followup uses git-mv detection for graceful migration. Documented in §Risks.

## Test strategy

Mirror **real-fixture pattern** from GIM-104 / GIM-111, with **structural compare** instead of byte-exact:

- Vendor 12 OpenZeppelin v5 `.sol` files under `tests/extractors/fixtures/oz-v5-mini-project/contracts/` — committed source + LICENSE.
- Pre-generate `index.scip` via `regen.sh` calling `slither --print=scip-emit` (custom slither printer) → commit binary blob.
- `tests/extractors/unit/test_real_scip_fixtures.py` — extend with Solidity assertions: pin **exact counts** of contracts/libraries/functions/events/modifiers from manual oracle. ABI selector spot-checks: `transfer(address,uint256) → 0xa9059cbb` (ERC20.transfer), `owner() → 0x8da5cb5b` (Ownable.owner), `transferOwnership(address) → 0xf2fde38b`.
- `tests/extractors/integration/test_symbol_index_solidity_integration.py` — real Neo4j via compose reuse, asserts `:Symbol` count + `:CONTAINS` edge structure.
- Drift-check **dropped from v1** (low CI coverage anyway — `solc 0.7.6` rarely on runners). Followup if needed.

## Acceptance criteria

1. `palace.ingest.run_extractor name=symbol_index_solidity project=oz-v5-mini` returns `success=true, nodes_written≥<oracle>` against vendored fixture. **`<oracle>` is pinned in plan Phase 1.0 by manual count after vendor (Task 6); CTO MUST verify the count exists before authorizing Phase 2.**
2. `palace.code.find_references qualified_name="contracts/token/ERC20/ERC20.sol:ERC20.transfer" project=oz-v5-mini` returns ≥1 occurrence.
3. Real-fixture test asserts ABI selector oracles: `transfer(address,uint256) → 0xa9059cbb`, `owner() → 0x8da5cb5b`, `transferOwnership(address) → 0xf2fde38b`.
4. Real-fixture test asserts at least one **inherited member** correctly attributed to inheriting contract via `linearizedBaseContracts` walk.
5. Real-fixture test asserts at least one **overload pair** (e.g., overloaded constructor or function) yields two distinct `:Symbol` nodes with different `abi_selector` values.
6. CI green: lint, typecheck, test, docker-build, watchdog-tests, submodule-drift-check.
7. QA Phase 4.1 catalog smoke confirms 5 → 6 extractors registered.
8. Phase 3.1 file-count audit + Phase 3.2 coverage matrix audit pass per GIM-114 discipline.
9. **`oz-v5-mini` registered as palace project**: docker-compose mount, `palace.memory.register_project` call documented in plan, `palace_scip_index_paths` config entry.

## Risks

| Risk | Mitigation |
|---|---|
| Custom AST→SCIP emitter is novel (no upstream reference) | Slither is the AST walker (well-tested); we only encode descriptor chain. Bit-exact tests dropped (protobuf non-deterministic); use **structural compare** on parsed Index. Small synthetic unit fixtures BEFORE OZ v5 real fixture. |
| Protobuf serialization non-deterministic | All emit-side tests structural-compare on parsed Index, NOT byte-equal. Drift-check dropped from v1. |
| ABI selector uint/uint256 alias gotcha | Slither's `function.canonical_name` already normalizes `uint`→`uint256`/`int`→`int256`. Test against known ERC20 oracle (0xa9059cbb) regardless. |
| `mapping(address => uint256)` parameter type contains space | Backtick-escape entire mapping string; rely on GIM-123 backtick-aware `_split_scip_top_level()` for round-tripping. |
| Inheritance C3 linearization conflict | Slither resolves linearization. Rule: emit inherited member at inheriting contract's qualified_name **only if current contract does NOT override**. Test case in plan Task 4. |
| Function overloads (same name, different params) | Each overload distinct qualified_name (param_types in FQN), distinct `abi_selector`. Test case in plan Task 4. |
| 0.8.x-only fixture doesn't exercise legacy solc | Acknowledged — operator stack is modern Solidity. v1 exercises **custom errors, immutable, multi-level inheritance, ERC20 standard, modifiers**. Legacy fixture (V2/V3) only if real legacy project surfaces. |
| `oz-v5-mini` is new mounted project (not `gimle`) | Plan adds docker-compose entry, `palace.memory.register_project` step, `palace_scip_index_paths` config. CTO Phase 1.1 verifies these paths. |
| Path-based qualified_name fragile to renames | Documented. v1 ships as-is; followup adds git-mv detection. |
| Vendoring as new fixture pattern | Existing fixtures are synthetic; this is first vendored real-world. **OpenZeppelin Contracts v5 is MIT** (verified — unambiguous compat with gimle-palace MIT). Vendored LICENSE preserves OZ copyright. REGEN.md pins source commit. submodule-drift-check unaffected (vendored ≠ submodule). |
| Slither dependency weight in palace-mcp Docker | Slither + dependencies (~30 MB). Acceptable: palace-mcp image already heavy with Neo4j + Tantivy. Slither is **fixture-regen-only** — does NOT ship in extractor runtime path (extractor consumes pre-generated `.scip`). |
| Effort underestimation | Estimated **4-5 days** (PythonEngineer TDD). Initial v1 was 2-3 days — corrected after critique acknowledged custom emit + ABI + linearization + overload + integration test all add real time. |

## Operator review verification (rev2)

This rev2 explicitly addresses the 11-point critique against rev1. Each item:

| # | Critique | Resolution |
|---|---|---|
| 1 | solc 0.5.16 vs 0.8.x contradiction | **OZ v5 (0.8.20+) — modern syntax fully exercised** (custom errors, immutable, etc.) |
| 2 | Slither vs rev2 §Q9 contradiction | Slither IN scope as AST walker; data-flow remains followup |
| 3 | SCIP-detour unjustified | Explicit rationale added (single pipeline + future-proof) |
| 4 | AC#1 N undefined | AC#1 specifies `<oracle>` pinned in plan Phase 1.0 by manual count; CTO MUST verify before Phase 2 |
| 5 | AC#1 project=gimle wrong | New AC#9: `oz-v5-mini` mount + register_project; AC#1 reformulated |
| 6 | Overloads | New AC#5 + plan Task 4 explicit handling |
| 7 | C3 linearization conflict | Slither resolves; rule documented (emit only if not overridden); plan Task 4 covers |
| 8 | eth-utils dep weight | `pycryptodome` selected; reasoning in §Architecture decisions |
| 9 | scip_emit/ namespace | Pre-emptive for FunC/Anchor; rationale documented |
| 10 | Vendoring as new pattern | Acknowledged in §Risks; LICENSE compat verified (MIT∩MIT) |
| 11 | Effort 2-3 → 4-5 days | Updated; bit-exact replaced with structural compare; drift-check dropped from v1 |
