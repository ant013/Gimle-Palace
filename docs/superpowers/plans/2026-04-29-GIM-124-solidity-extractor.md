# symbol_index_solidity — Solidity extractor Implementation Plan (rev2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fourth production extractor `symbol_index_solidity` covering Solidity smart contracts via custom AST→SCIP emitter (no first-party SCIP indexer for Solidity). First non-SCIP-native language; opens path to FunC and Anchor.

**Architecture:** Near-symmetric copy of `symbol_index_java.py` for the **runtime ingest path** (reads pre-generated `.scip`, calls `iter_scip_occurrences`, writes Tantivy + Neo4j). Novel work is **upstream**: a custom `scip_emit/solidity.py` library converting **slither's parsed AST** to SCIP-shaped protobuf, packaged as a slither printer + CLI script in the fixture for offline regen.

**Tech Stack:** Python 3.13, palace-mcp extractor framework (GIM-101a substrate, lang-agnostic since GIM-104), SCIP protobuf, Tantivy, Neo4j 5.x, pytest, **solc 0.8.20+** (external, pinned to OpenZeppelin Contracts v5 minimum), **slither-analyzer** (~v0.11.5+, fixture-regen only — solc 0.8 supported), **pycryptodome** (for keccak4 ABI selector).

**Predecessor SHA:** `82b909e` (GIM-123 hardening sweep merged to develop).

---

## Phase 1.0: Manual oracle count (CTO MUST complete before authorizing Phase 2)

> **GIM-114 discipline gate.** Plan acceptance criterion AC#1 requires concrete `nodes_written≥<oracle>`. CTO performs the count after Task 6 vendor lands the fixture, BEFORE PythonEngineer starts implementation. Without pinned oracle values, Phase 3.1 cannot detect silent scope reduction.

**Task 0a — Vendor fixture and run manual count**

After Task 6 (fixture vendoring) commits to the feature branch, CTO checks out the branch and:

1. Runs `cd tests/extractors/fixtures/oz-v5-mini-project && solc --ast-compact-json contracts/**/*.sol > ast.json` (or equivalent slither output).
2. Manually counts:
   - `<N_CONTRACTS>` = number of `ContractDefinition` nodes (incl. libraries, interfaces, abstract)
   - `<N_FUNCTIONS>` = number of `FunctionDefinition` nodes (sum across all contracts)
   - `<N_EVENTS>` = number of `EventDefinition` nodes
   - `<N_MODIFIERS>` = number of `ModifierDefinition` nodes
   - `<N_STATEVARS>` = number of `StateVariable` declarations
   - `<N_OCCURRENCES_TOTAL>` = total Occurrence records emitted (defs + decls + uses across all docs)
3. Pins these values in the plan (this section), updates AC#1 in spec to use the concrete `<N_OCCURRENCES_TOTAL>` lower bound.
4. Picks two well-known ABI selector oracles for cross-validation: `transfer(address,uint256) → 0xa9059cbb` (ERC20 standard, must match) and one OZ-specific (e.g., `Ownable.owner() → 0x8da5cb5b`, `Ownable.transferOwnership(address) → 0xf2fde38b`). Pins values in plan.

**Task 0a deliverable:** This section becomes a filled-in oracle table:

```
Manual oracle count for OpenZeppelin Contracts v5.2.0 subset (6 .sol files, 8 contracts):
Counted by CTO from source on 2026-04-29, branch c97fea3.

| Metric | Value | Source |
|---|---|---|
| N_CONTRACTS | 8 | Context, IERC20, IERC20Metadata, Ownable, IERC20Errors, IERC721Errors, IERC1155Errors, ERC20 |
| N_FUNCTIONS | 35 | Context:3, IERC20:6, IERC20Metadata:3, Ownable:6(incl ctor), IERC6093:0, ERC20:17(incl ctor) |
| N_EVENTS | 3 | IERC20:Transfer+Approval, Ownable:OwnershipTransferred |
| N_MODIFIERS | 1 | Ownable:onlyOwner |
| N_STATEVARS | 6 | Ownable:_owner(1), ERC20:_balances+_allowances+_totalSupply+_name+_symbol(5) |
| N_CUSTOM_ERRORS | 23 | Ownable:2, IERC20Errors:6, IERC721Errors:8, IERC1155Errors:7 |
| N_OCCURRENCES_TOTAL | ≥76 | defs only: 8+35+3+1+6+23=76; uses TBD after Task 3 regen |
| ORACLE_ABI_SELECTOR transfer(address,uint256) | 0xa9059cbb | keccak4, verified in Task 2 tests |
| ORACLE_ABI_SELECTOR owner() | 0x8da5cb5b | keccak4, verified in Task 2 tests |
| ORACLE_ABI_SELECTOR transferOwnership(address) | 0xf2fde38b | keccak4, verified in Task 2 tests |
```

**Overload discovery:** Only overload pair in fixture is `ERC20._approve(address,address,uint256)` vs
`ERC20._approve(address,address,uint256,bool)` — both `internal`, so neither has an ABI selector.
AC#5 can assert distinct `qualified_name` but NOT distinct `abi_selector` for this pair.
PE should adjust Task 11 accordingly (test overload qualified_name distinction; skip selector assertion
for internal-only overloads, or add a synthetic fixture with a public overload pair).

**N_OCCURRENCES_TOTAL refinement:** Lower bound 76 covers definition occurrences only.
After Task 3 emitter produces `index.scip`, PE runs `regen.sh` which prints the actual total.
PE MUST update this table and REGEN.md with the actual count before Task 11 tests pin it.
CTO will verify the final count in a followup check.

CTO authorizes Phase 2 (Tasks 3-5, 11-12) with these oracle values.

---

## Task 0b: Q1 FQN verification reference (CTO Phase 1.1)

**Architecture decisions are pre-locked** in [`docs/research/2026-04-27-q1-fqn-cross-language-rev2.md`](../../research/2026-04-27-q1-fqn-cross-language-rev2.md). The 12 minimum invariants from that doc MUST be honored by Task 3 emit logic.

Solidity edge cases verified in research and rev2 spec:
- **Inheritance:** Slither resolves `linearizedBaseContracts`. Emit inherited member at inheriting qualified_name **only if current contract does NOT override**.
- **Mapping types:** `mapping(address => uint256)` literal preserved in parameter lists; backtick-escaped (embedded `=>` and space).
- **Constructors:** Slither exposes via `Function.is_constructor`; emit as `<ContractName>.<ContractName>(...)`.
- **Fallback / receive:** Solc 0.6+ uses dedicated nodeTypes; slither exposes via `Function.is_fallback` / `Function.is_receive`. Emit as `fallback()` / `receive()`.
- **Public state vars:** Slither exposes auto-generated getters via `Variable.visibility=='public'`; emit BOTH state-var symbol AND method symbol.
- **Overloads:** Each overload = distinct `qualified_name` (`param_types` part of FQN), distinct `abi_selector`. No deduplication.
- **ABI selectors:** Slither's `Function.canonical_name` provides normalized signature; pass to `pycryptodome` keccak4.
- **Local symbols:** Slither's `Function.local_variables` enumerates locals; we **skip** them (only contract-level members ingested).

---

## File Structure

### New files

| File | Responsibility |
|---|---|
| `services/palace-mcp/src/palace_mcp/extractors/symbol_index_solidity.py` | `SymbolIndexSolidity` runtime extractor |
| `services/palace-mcp/src/palace_mcp/scip_emit/__init__.py` | Package init |
| `services/palace-mcp/src/palace_mcp/scip_emit/solidity.py` | slither AST → SCIP `Index` protobuf |
| `services/palace-mcp/src/palace_mcp/scip_emit/abi_selector.py` | ABI 4-byte selector via pycryptodome keccak4 |
| `services/palace-mcp/tests/extractors/unit/test_symbol_index_solidity.py` | Unit tests (mocked driver+bridge) |
| `services/palace-mcp/tests/extractors/integration/test_symbol_index_solidity_integration.py` | Integration (real Neo4j) |
| `services/palace-mcp/tests/scip_emit/__init__.py` | Tests package init |
| `services/palace-mcp/tests/scip_emit/test_solidity_emit.py` | Unit: slither AST → Index, structural compare |
| `services/palace-mcp/tests/scip_emit/test_abi_selector.py` | Unit: ERC20 + Ownable oracle selectors |
| `services/palace-mcp/tests/extractors/fixtures/oz-v5-mini-project/contracts/token/ERC20/ERC20.sol` | Vendored — ERC20 reference impl |
| `services/palace-mcp/tests/extractors/fixtures/oz-v5-mini-project/contracts/token/ERC20/IERC20.sol` | Vendored — ERC20 interface |
| `services/palace-mcp/tests/extractors/fixtures/oz-v5-mini-project/contracts/token/ERC20/extensions/IERC20Metadata.sol` | Vendored — name/symbol/decimals |
| `services/palace-mcp/tests/extractors/fixtures/oz-v5-mini-project/contracts/access/Ownable.sol` | Vendored — `onlyOwner` modifier exemplar |
| `services/palace-mcp/tests/extractors/fixtures/oz-v5-mini-project/contracts/utils/Context.sol` | Vendored — `_msgSender()` abstract base |
| `services/palace-mcp/tests/extractors/fixtures/oz-v5-mini-project/contracts/interfaces/draft-IERC6093.sol` | Vendored — custom errors interface (0.8.4+ feature exemplar) |
| `services/palace-mcp/tests/extractors/fixtures/oz-v5-mini-project/foundry.toml` | Foundry config (`solc_version = "0.8.20"`) |
| `services/palace-mcp/tests/extractors/fixtures/oz-v5-mini-project/index.scip` | Pre-generated SCIP index (committed binary) |
| `services/palace-mcp/tests/extractors/fixtures/oz-v5-mini-project/REGEN.md` | Regen instructions, source URL+commit (OpenZeppelin/openzeppelin-contracts), expected oracle table |
| `services/palace-mcp/tests/extractors/fixtures/oz-v5-mini-project/regen.sh` | One-shot: solc + slither → emit → index.scip |
| `services/palace-mcp/tests/extractors/fixtures/oz-v5-mini-project/LICENSE` | Vendored MIT (OpenZeppelin copyright) |

### Modified files

| File | Change |
|---|---|
| `services/palace-mcp/src/palace_mcp/extractors/scip_parser.py` | Add `"solidity"` to `_SCIP_LANGUAGE_MAP`; add `.sol` to `_language_from_path()` |
| `services/palace-mcp/src/palace_mcp/extractors/registry.py` | Import + register `SymbolIndexSolidity` |
| `docker-compose.yml` | Add bind-mount: `tests/extractors/fixtures/oz-v5-mini-project:/repos/oz-v5-mini:ro` for `palace-mcp` service |
| `services/palace-mcp/tests/extractors/unit/test_real_scip_fixtures.py` | Add Solidity assertions block |
| `services/palace-mcp/tests/extractors/fixtures/scip_factory.py` | Add `build_solidity_scip_index()` factory |
| `services/palace-mcp/pyproject.toml` | Add `pycryptodome` to runtime deps; add `slither-analyzer` to dev/regen deps (NOT runtime) |
| `Makefile` | Add `SOLIDITY_FIXTURE_DIR` + `regen-solidity-fixture` target |
| `CLAUDE.md` | Add `symbol_index_solidity` to registered extractors; document `oz-v5-mini` mount in §"Mounting project repos for palace.git.*" |

---

## Task 1: Add Solidity routing to scip_parser

- [ ] **Test:** `tests/extractors/unit/test_scip_parser_language.py` — `_language_from_path("contracts/A.sol") == Language.SOLIDITY`; `_SCIP_LANGUAGE_MAP["solidity"] == Language.SOLIDITY`.
- [ ] **Impl:** Update `_SCIP_LANGUAGE_MAP` and `_language_from_path` in `scip_parser.py`.
- [ ] **Commit:** `feat(GIM-124): route .sol files and 'solidity' doc.language to Language.SOLIDITY`

## Task 2: ABI selector computation (pycryptodome keccak4)

- [ ] **Test:** `tests/scip_emit/test_abi_selector.py`:
  - Oracle: `compute_abi_selector("transfer(address,uint256)") == "0xa9059cbb"`
  - Oracle: `compute_abi_selector("approve(address,uint256)") == "0x095ea7b3"`
  - Oracle: `compute_abi_selector("owner()") == "0x8da5cb5b"` (Ownable.owner)
  - Oracle: `compute_abi_selector("transferOwnership(address)") == "0xf2fde38b"` (Ownable)
  - Edge: empty-params `compute_abi_selector("name()") == "0x06fdde03"` (ERC20 metadata)
- [ ] **Impl:** `scip_emit/abi_selector.py` — `compute_abi_selector(canonical_signature: str) -> str` using `Crypto.Hash.keccak`. Input must be already canonical (caller — slither — normalizes uint→uint256).
- [ ] **Commit:** `feat(GIM-124): ABI 4-byte selector computation via pycryptodome keccak4`

## Task 3: scip_emit.solidity — slither AST → Index protobuf

- [ ] **Test:** `tests/scip_emit/test_solidity_emit.py` with **structural compare** (NOT byte-exact). Synthetic small `.sol` fixture: 1 contract with 1 function + 1 event + 1 modifier + 1 state var. Run slither parse → `emit_index()` → assert resulting `Index` has expected `Document` count, expected `Occurrence` symbols (parsed from string, compared as set), expected `SymbolInformation.kind` values (Function, Event, Modifier, Field), expected descriptor structure.
- [ ] **Impl:** `scip_emit/solidity.py` — `emit_index(slither_obj, root_path: Path) -> scip_pb2.Index`. Walk `slither.contracts`; for each `Contract`: emit ContractDefinition occurrence; walk `contract.functions`/`contract.events`/`contract.modifiers`/`contract.state_variables`. Encode descriptor chain. Backtick-escape mapping types in parameter lists. Set SymbolKind for each.
- [ ] **Commit:** `feat(GIM-124): scip_emit.solidity — slither walker → Index protobuf for contracts/funcs/events/modifiers/state-vars`

## Task 4: Inheritance, overrides, overloads, special functions

- [ ] **Test:** Extend `test_solidity_emit.py`:
  - `test_inherited_member_emitted_at_inheriting_contract` — Contract `B inherits A`, `A.foo()` not overridden in B → expect symbol `B:B.foo()` AND `A:A.foo()` (each at its own contract qualified_name).
  - `test_overridden_member_emitted_only_once` — Contract `B inherits A`, `A.foo()` overridden in B → expect ONLY `B:B.foo()` (no inherited copy at B level).
  - `test_overload_distinct_symbols_and_selectors` — Contract has `mint(address)` and `mint(address,uint256)` → two `:Symbol` records with different `qualified_name` AND different `abi_selector`.
  - `test_constructor_named_after_contract` — slither `is_constructor=True` → emitted as `<C>.<C>(...)`.
  - `test_fallback_and_receive_named_correctly` — emitted as `fallback()` / `receive()`.
  - `test_public_state_var_dual_emit` — `uint256 public totalSupply` → both Field symbol and Method getter symbol.
- [ ] **Impl:** Update `solidity_emit` to handle slither's `Function.is_constructor` / `is_fallback` / `is_receive`, override resolution via slither's `Contract.functions_inherited`, public-state-var auto-getter via `Variable.visibility=='public'`.
- [ ] **Commit:** `feat(GIM-124): inheritance walk, override resolution, overloads, special functions in solidity_emit`

## Task 5: Mapping type backtick-escape in parameter lists

- [ ] **Test:** Synthetic contract with internal function `_setBalance(mapping(address => uint256) storage map, address user, uint256 amount)` (mapping types only valid in internal). Assert emitted symbol contains backtick-escaped mapping in descriptor chain. Verify round-trip via GIM-123 `_split_scip_top_level()`.
- [ ] **Impl:** In `solidity_emit`, when encoding parameter type, detect SCIP-special chars (` `, `(`, `)`, `=`, `>`, etc.) and wrap entire type string in backticks, doubling internal backticks per SCIP grammar.
- [ ] **Commit:** `feat(GIM-124): backtick-escape mapping type strings in solidity_emit parameter lists`

## Task 6: Vendor OpenZeppelin v5 fixture sources

- [ ] **Source:** `https://github.com/OpenZeppelin/openzeppelin-contracts` @ tag **`v5.x`** latest (pin SHA in REGEN.md). **License: MIT** — clean compat with gimle-palace MIT.
- [ ] **Files vendored** (6, listed in §File Structure):
  - `contracts/token/ERC20/ERC20.sol`
  - `contracts/token/ERC20/IERC20.sol`
  - `contracts/token/ERC20/extensions/IERC20Metadata.sol`
  - `contracts/access/Ownable.sol`
  - `contracts/utils/Context.sol`
  - `contracts/interfaces/draft-IERC6093.sol` (custom errors interface — exercises 0.8.4+ syntax)
- [ ] **Add:** `foundry.toml` with `solc_version = "0.8.20"`.
- [ ] **Add:** `REGEN.md` — source URL+commit SHA, MIT note, vendored file list, regen.sh invocation, **manual oracle table from Phase 1.0**.
- [ ] **Add:** `LICENSE` file preserving OpenZeppelin copyright + MIT text.
- [ ] **Commit:** `chore(GIM-124): vendor OpenZeppelin v5 contracts subset as fixture (6 files, MIT)`

## Task 7: Fixture regen script + initial index.scip generation

- [ ] **Test:** Manual at this stage — run `regen.sh` locally with slither installed, verify `index.scip` produced (binary blob, ~10-30 KB expected for OZ v5 subset of 6 files).
- [ ] **Impl:** `regen.sh` invokes a slither printer (or standalone Python script importing `scip_emit.solidity.emit_index`) that walks the slither object and serializes Index to `index.scip`.
- [ ] **Commit:** `feat(GIM-124): fixture regen.sh — slither walk → solidity_emit → committed index.scip`

## Task 8: docker-compose mount + project registration

- [ ] **Test:** Manual smoke after compose up — verify `/repos/oz-v5-mini` visible in palace-mcp container (`docker exec ... ls /repos/oz-v5-mini`).
- [ ] **Impl:** Add bind-mount entry `./services/palace-mcp/tests/extractors/fixtures/oz-v5-mini-project:/repos/oz-v5-mini:ro` in `docker-compose.yml` under `palace-mcp.volumes`. Update CLAUDE.md mount table.
- [ ] **Manual register step (documented in plan, NOT a code change):**
  ```
  palace.memory.register_project slug="oz-v5-mini" name="OpenZeppelin Contracts v5 mini-fixture"
  ```
  This is performed once after deploy via MCP call (not committed code).
- [ ] **Commit:** `chore(GIM-124): docker-compose bind-mount /repos/oz-v5-mini + CLAUDE.md docs`

## Task 9: SymbolIndexSolidity runtime extractor

- [ ] **Test:** `tests/extractors/unit/test_symbol_index_solidity.py` — mock driver + bridge; mirror `test_symbol_index_java.py`. Assert extractor reads scip path from `palace_scip_index_paths["oz-v5-mini"]`, calls `iter_scip_occurrences(language=Language.SOLIDITY)`, writes through bridge.
- [ ] **Impl:** `extractors/symbol_index_solidity.py` — class inheriting `BaseExtractor`. Mirror `SymbolIndexJava` 1:1; only differences: name, description, language override.
- [ ] **Commit:** `feat(GIM-124): SymbolIndexSolidity runtime extractor — mirrors JVM, consumes pre-generated .scip`

## Task 10: Register extractor

- [ ] **Test:** `tests/extractors/unit/test_registry.py` — `EXTRACTORS["symbol_index_solidity"]` exists.
- [ ] **Impl:** Add import + entry in `extractors/registry.py`.
- [ ] **Commit:** `feat(GIM-124): register symbol_index_solidity in extractors registry`

## Task 11: Real-fixture assertions

- [ ] **Test:** Extend `tests/extractors/unit/test_real_scip_fixtures.py` with Solidity section. Concrete assertions using values from Phase 1.0 oracle table:
  - `<N_CONTRACTS>` ContractDefinition occurrences
  - `<N_FUNCTIONS>` FunctionDefinition occurrences
  - `<N_EVENTS>` EventDefinition occurrences
  - `<N_MODIFIERS>` ModifierDefinition occurrences (must include `NoDelegateCall.lock`)
  - At least one inherited-member assertion: `ERC20` inherits `Context` and implements `IERC20` + `IERC20Metadata` — assert `_msgSender` accessible on ERC20-level qualified_name (from Context)
  - At least one custom-error assertion (`draft-IERC6093.ERC20InvalidSender` etc. emitted as Symbol with appropriate kind)
  - ABI selector oracles: `transfer(address,uint256) → 0xa9059cbb`, `owner() → 0x8da5cb5b`, `transferOwnership(address) → 0xf2fde38b`
  - At least one overload pair if any in OZ v5 subset (note: OZ v5 mostly avoids overloading; if no native overload, test deferred to followup with synthetic fixture)
- [ ] **Impl:** Pure test code; no production change.
- [ ] **Commit:** `test(GIM-124): real OpenZeppelin v5 fixture assertions in test_real_scip_fixtures`

## Task 12: Integration test against real Neo4j

- [ ] **Test:** `tests/extractors/integration/test_symbol_index_solidity_integration.py` — compose-reuse pattern from GIM-111. Run extractor against real Neo4j; query resulting `:Symbol` count + `:CONTAINS` edge structure; assert ≥`<N_CONTRACTS>` Symbol nodes with `language=solidity`.
- [ ] **Impl:** Mirror JVM integration test.
- [ ] **Commit:** `test(GIM-124): integration — extractor → real Neo4j → graph shape`

## Task 13: Wiring (CLAUDE.md, Makefile, pyproject)

- [ ] **CLAUDE.md** §Extractors: register `symbol_index_solidity` with one-line description; §Mounting project repos: add `oz-v5-mini` row.
- [ ] **Makefile**: `SOLIDITY_FIXTURE_DIR` + `regen-solidity-fixture` target.
- [ ] **pyproject.toml**: add `pycryptodome` to `[project] dependencies`; add `slither-analyzer` to `[tool.uv.dev-dependencies]` (regen-only, not runtime).
- [ ] **Test:** `uv run mypy src/` clean; CI lint+typecheck pass.
- [ ] **Commit:** `chore(GIM-124): wiring — CLAUDE.md, Makefile, pyproject deps for Solidity extractor`

---

## Acceptance criteria (mirrors spec rev2)

1. ✅ `palace.ingest.run_extractor name=symbol_index_solidity project=oz-v5-mini` returns `success=true, nodes_written≥<N_OCCURRENCES_TOTAL>` (oracle from Phase 1.0)
2. ✅ `palace.code.find_references qualified_name="contracts/token/ERC20/ERC20.sol:ERC20.transfer" project=oz-v5-mini` returns ≥1 occurrence
3. ✅ Real-fixture test: ABI selectors match: `transfer(address,uint256) → 0xa9059cbb`, `owner() → 0x8da5cb5b`
4. ✅ Real-fixture test: ≥1 inherited-member case correctly attributed to inheriting contract
5. ✅ Real-fixture test: ≥1 overload pair → 2 `:Symbol` nodes with distinct qualified_name AND distinct abi_selector
6. ✅ CI green: lint, typecheck, test, docker-build, watchdog-tests, submodule-drift-check
7. ✅ Phase 4.1 catalog smoke confirms 5 → 6 extractors
8. ✅ Phase 3.1 file-count + Phase 3.2 coverage matrix audits pass (per GIM-114)
9. ✅ `oz-v5-mini` mount in docker-compose; `palace.memory.register_project` documented in plan; `palace_scip_index_paths` config entry

## Estimated effort

**Implementation: 4-5 days** (PythonEngineer TDD through 13 tasks).

| Component | LOC estimate |
|---|---|
| `scip_emit/solidity.py` | ~300 |
| `scip_emit/abi_selector.py` | ~50 |
| `symbol_index_solidity.py` | ~150 |
| Tests (unit + integration + scip_emit) | ~600-800 |
| Vendored .sol files (OpenZeppelin v5 subset, 6 files) | ~600-800 (NOT counted as palace-mcp LOC) |
| Wiring (compose, pyproject, Makefile, CLAUDE.md) | ~30 |
