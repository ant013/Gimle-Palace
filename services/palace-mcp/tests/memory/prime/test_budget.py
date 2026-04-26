"""Unit tests for palace_mcp.memory.prime.budget."""

from __future__ import annotations


from palace_mcp.memory.prime.budget import apply_budget, estimate_tokens


def test_estimate_tokens_divides_by_four() -> None:
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("a" * 100) == 25
    assert estimate_tokens("") == 0


def test_apply_budget_no_truncation_when_within_budget() -> None:
    core = "A" * 100
    extras = "B" * 100
    combined, truncated = apply_budget(core, extras, budget=10_000)
    assert not truncated
    assert core in combined
    assert extras in combined


def test_apply_budget_truncates_role_extras_not_core() -> None:
    core = "CORE:" + "C" * 40
    extras = "EXTRA:" + "E" * 800
    combined, truncated = apply_budget(core, extras, budget=20)
    assert truncated
    assert core in combined
    # extras must be truncated — not all 800 'E's should be present
    assert combined.count("E") < 800
    assert "[priming truncated to budget]" in combined


def test_apply_budget_extreme_zero_extras_budget() -> None:
    # Core already consumes entire budget → extras dropped
    core = "C" * 400
    extras = "E" * 400
    combined, truncated = apply_budget(core, extras, budget=1)
    assert truncated
    assert "C" * 400 in combined
    assert "[priming truncated to budget]" in combined


def test_apply_budget_returns_full_when_exactly_at_budget() -> None:
    core = "A"
    extras = "B"
    sep = "\n\n---\n\n"
    full = core + sep + extras
    tokens = estimate_tokens(full)
    combined, truncated = apply_budget(core, extras, budget=tokens)
    assert not truncated
    assert combined == full


def test_apply_budget_marker_present_only_when_truncated() -> None:
    core = "core"
    extras = "extras"
    combined_ok, _ = apply_budget(core, extras, budget=10_000)
    assert "[priming truncated to budget]" not in combined_ok

    combined_trunc, _ = apply_budget(core, extras, budget=1)
    assert "[priming truncated to budget]" in combined_trunc
