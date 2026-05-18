"""Unit tests for symbol resolution heuristics."""

from __future__ import annotations

from palace_mcp.extractors.hot_path_profiler.symbol_resolver import resolve_symbol_name


def test_resolve_symbol_name_matches_qualified_name_and_suffix() -> None:
    lookup = {
        "walletapp.appdelegate.bootstrap": "WalletApp.AppDelegate.bootstrap()",
        "bootstrap": "WalletApp.AppDelegate.bootstrap()",
        "homeviewmodel.loaddashboard": "WalletApp.HomeViewModel.loadDashboard()",
    }

    assert (
        resolve_symbol_name("WalletApp.AppDelegate.bootstrap()", lookup)
        == "WalletApp.AppDelegate.bootstrap()"
    )
    assert (
        resolve_symbol_name("bootstrap()", lookup)
        == "WalletApp.AppDelegate.bootstrap()"
    )
    assert (
        resolve_symbol_name("HomeViewModel.loadDashboard()", lookup)
        == "WalletApp.HomeViewModel.loadDashboard()"
    )
    assert resolve_symbol_name("NoMatch.perform()", lookup) is None
