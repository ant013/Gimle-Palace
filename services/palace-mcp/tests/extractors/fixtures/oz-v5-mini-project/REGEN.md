# oz-v5-mini-project — Fixture Regen Instructions

## Source

- **Repository:** https://github.com/OpenZeppelin/openzeppelin-contracts
- **Tag:** v5.2.0
- **Commit SHA:** (pin after regen — run `git rev-parse v5.2.0^{}`)
- **License:** MIT (Copyright (c) 2016-2024 Zeppelin Group Ltd)

## Vendored files (6)

| Fixture path | Source path |
|---|---|
| `contracts/token/ERC20/ERC20.sol` | `contracts/token/ERC20/ERC20.sol` |
| `contracts/token/ERC20/IERC20.sol` | `contracts/token/ERC20/IERC20.sol` |
| `contracts/token/ERC20/extensions/IERC20Metadata.sol` | `contracts/token/ERC20/extensions/IERC20Metadata.sol` |
| `contracts/access/Ownable.sol` | `contracts/access/Ownable.sol` |
| `contracts/utils/Context.sol` | `contracts/utils/Context.sol` |
| `contracts/interfaces/draft-IERC6093.sol` | `contracts/interfaces/draft-IERC6093.sol` |

## Regen index.scip

Requires: `slither-analyzer>=0.11.5`, `solc 0.8.20+` on PATH.

```bash
cd services/palace-mcp/tests/extractors/fixtures/oz-v5-mini-project
bash regen.sh
```

Alternatively, using the Makefile from the repo root:
```bash
make regen-solidity-fixture
```

After regen, commit the updated `index.scip` binary and update the oracle
table below with the new counts (run `python regen.sh --count` or inspect
the slither output manually).

## Manual oracle table (Phase 1.0 — CTO must fill BEFORE authorizing PE Phase 2)

> Fill after running regen.sh and counting output from slither.
> PE: do NOT implement oracle-dependent tests until this table is complete.

| Metric | Value | Source |
|---|---|---|
| N_CONTRACTS | TBD | manual count |
| N_FUNCTIONS | TBD | manual count |
| N_EVENTS | TBD | manual count |
| N_MODIFIERS | TBD | manual count |
| N_STATEVARS | TBD | manual count |
| N_OCCURRENCES_TOTAL | TBD | manual count (emit output) |
| ORACLE_ABI_SELECTOR transfer | 0xa9059cbb | keccak4("transfer(address,uint256)") |
| ORACLE_ABI_SELECTOR owner | 0x8da5cb5b | keccak4("owner()") |
| ORACLE_ABI_SELECTOR transferOwnership | 0xf2fde38b | keccak4("transferOwnership(address)") |

## Updating source files

1. Check out the new OZ tag.
2. Copy the 6 files listed above, preserving relative paths.
3. Update the commit SHA in this file.
4. Run `bash regen.sh` to regenerate `index.scip`.
5. Update the oracle table.
6. Commit both `.sol` changes and the new `index.scip` binary.
