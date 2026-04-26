"""Token budget enforcement for palace.memory.prime.

Task 5: estimate_tokens + tail-truncate role extras if over budget.
Universal core and standing instruction are never truncated.
"""

from __future__ import annotations

_TRUNCATION_MARKER = "\n\n[priming truncated to budget]"


def estimate_tokens(text: str) -> int:
    """Approximate token count: len(text) // 4."""
    return len(text) // 4


def apply_budget(
    universal_core: str,
    role_extras: str,
    budget: int,
) -> tuple[str, bool]:
    """Enforce token budget; tail-truncate role_extras if needed.

    Returns (combined_content, truncated).
    Universal core is always preserved intact.
    """
    separator = "\n\n---\n\n"
    full = universal_core + separator + role_extras

    if estimate_tokens(full) <= budget:
        return full, False

    # How many chars can role_extras use?
    core_tokens = estimate_tokens(universal_core + separator)
    marker_tokens = estimate_tokens(_TRUNCATION_MARKER)
    extras_budget_tokens = budget - core_tokens - marker_tokens
    if extras_budget_tokens <= 0:
        return universal_core + separator + _TRUNCATION_MARKER, True

    extras_budget_chars = extras_budget_tokens * 4
    truncated_extras = role_extras[:extras_budget_chars]
    return universal_core + separator + truncated_extras + _TRUNCATION_MARKER, True
