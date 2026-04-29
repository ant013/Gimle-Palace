"""Unit tests for ABI 4-byte selector computation (GIM-124).

Oracle values verified against ERC20/Ownable standards.
"""

from __future__ import annotations

import pytest

from palace_mcp.scip_emit.abi_selector import compute_abi_selector


class TestComputeAbiSelector:
    def test_transfer_erc20(self) -> None:
        assert compute_abi_selector("transfer(address,uint256)") == "0xa9059cbb"

    def test_approve_erc20(self) -> None:
        assert compute_abi_selector("approve(address,uint256)") == "0x095ea7b3"

    def test_owner_ownable(self) -> None:
        assert compute_abi_selector("owner()") == "0x8da5cb5b"

    def test_transfer_ownership_ownable(self) -> None:
        assert compute_abi_selector("transferOwnership(address)") == "0xf2fde38b"

    def test_name_erc20_metadata(self) -> None:
        assert compute_abi_selector("name()") == "0x06fdde03"

    def test_returns_lowercase_hex_with_prefix(self) -> None:
        result = compute_abi_selector("transfer(address,uint256)")
        assert result.startswith("0x")
        assert result == result.lower()
        assert len(result) == 10  # 0x + 8 hex chars

    def test_balance_of_erc20(self) -> None:
        assert compute_abi_selector("balanceOf(address)") == "0x70a08231"

    def test_total_supply_erc20(self) -> None:
        assert compute_abi_selector("totalSupply()") == "0x18160ddd"
