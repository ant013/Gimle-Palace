from __future__ import annotations

import pytest

from palace_mcp.symbol_identity import (
    canonical_symbol_kind,
    canonical_symbol_label,
    canonical_symbol_short_name,
    canonical_symbol_short_name_candidates,
)


@pytest.mark.parametrize(
    (
        "qualified_name",
        "kind",
        "expected_short_name",
        "expected_kind",
        "expected_label",
    ),
    [
        ("WalletKit.BalanceData", "Class", "BalanceData", "class", "Class"),
        (
            "scip-python python example . ClassA .",
            "Class",
            "ClassA",
            "class",
            "Class",
        ),
        (
            "Unstoppable s%3A11Unstoppable18BitcoinBaseAdapterC0B11BalanceDataV",
            "Struct",
            "BalanceData",
            "struct",
            "Struct",
        ),
        (
            "WalletKit s:9WalletKit16BalanceProvidingP",
            "Protocol",
            "BalanceProviding",
            "protocol",
            "Protocol",
        ),
        (
            "WalletKit s:9WalletKit11BalanceDataV6amountSivp",
            "Property",
            "amount",
            "property",
            "Property",
        ),
        (
            "example ClassA . __init__ .",
            "Method",
            "__init__",
            "method",
            "Method",
        ),
        (
            "WalletKit s:9WalletKit11BalanceDataV9formattedSSyF",
            "Method",
            "formatted",
            "method",
            "Method",
        ),
        (
            "scip-python python example . helper .",
            "Function",
            "helper",
            "function",
            "Function",
        ),
    ],
)
def test_canonical_symbol_identity_contract(
    qualified_name: str,
    kind: str,
    expected_short_name: str,
    expected_kind: str,
    expected_label: str,
) -> None:
    assert canonical_symbol_short_name(qualified_name) == expected_short_name
    assert canonical_symbol_kind(kind) == expected_kind
    assert canonical_symbol_label(kind) == expected_label


def test_short_name_candidates_strip_parameter_suffix() -> None:
    assert canonical_symbol_short_name_candidates("WalletKit.Service.fetch(id:)") == [
        "fetch(id:)",
        "fetch",
    ]
