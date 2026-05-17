"""Handoff strict rules — restored from pre-Phase-A1 phase-handoff.md.

Operator 2026-05-17 confirmed live smoke: agents kept writing past `your turn.`,
paperclip SIGTERMs mid-write, recipient never wakes. Phase A.1 slim refactor
dropped the strict-format rule. Restored in handoff/basics.md (submodule) +
profiles/handoff.md (super-repo).
"""
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BASICS = REPO / "paperclips" / "fragments" / "shared" / "fragments" / "handoff" / "basics.md"
PROFILE = REPO / "paperclips" / "fragments" / "profiles" / "handoff.md"


def test_basics_has_strict_format_rule():
    """LAST sentence MUST be `[@Recipient](agent://uuid?i=icon) your turn.` —
    period, nothing after. Stop writing."""
    text = BASICS.read_text()
    must_have = [
        "your turn.",
        "LAST sentence",
        "STOP",
        "Nothing after",
    ]
    missing = [m for m in must_have if m not in text]
    assert not missing, (
        f"handoff/basics.md missing strict-format markers: {missing}"
    )


def test_basics_has_fallback_to_cto():
    """Operator rule: if next agent unknown → handoff to CTO. Never drop."""
    text = BASICS.read_text()
    must_have = [
        "handoff to your CTO",
        "if next is unknown",
        "NEVER drop the issue",
    ]
    missing = [m for m in must_have if m.lower() not in text.lower()]
    assert not missing, (
        f"handoff/basics.md missing 'fallback-to-CTO' rule: {missing}"
    )


def test_basics_has_comment_not_handoff_iron_rule():
    """Comment alone does NOT handoff; only PATCH wakes recipient."""
    text = BASICS.read_text()
    assert "Comment ≠ handoff" in text or "Comment != handoff" in text, (
        "handoff/basics.md missing 'comment alone does not handoff' iron rule"
    )
    assert "ONLY `PATCH" in text or "only PATCH" in text.lower(), (
        "must emphasize PATCH is the wake mechanism"
    )


def test_basics_has_wrong_examples():
    """Examples of WRONG forms must be present (anti-patterns):
    - trailing prose after `your turn.`
    - `@Role:` punctuation
    - plain `Reassigning to` without formal mention
    """
    text = BASICS.read_text()
    assert "❌" in text, "handoff/basics.md missing anti-pattern examples (❌)"
    # Should show trailing prose anti-pattern
    assert "trailing prose" in text.lower() or "your turn —" in text, (
        "missing example showing trailing prose after `your turn.`"
    )


def test_profile_handoff_compatible():
    """profiles/handoff.md (super-repo) must reinforce the basics.md rule,
    not contradict it."""
    text = PROFILE.read_text()
    must_have = [
        "your turn.",
        "STOP",
        "your CTO",
        "Nothing after",
    ]
    missing = [m for m in must_have if m not in text]
    assert not missing, f"profiles/handoff.md missing: {missing}"


def test_profile_no_trailing_prose_example():
    """profiles/handoff.md MUST NOT show the bad `your turn — Phase X: do Y`
    example that allows trailing prose. That was the bug operator flagged."""
    text = PROFILE.read_text()
    # Bad pattern: `your turn —` (em-dash followed by prose, suggesting more text after)
    assert "your turn —" not in text, (
        "profiles/handoff.md still shows `your turn — Phase X: ...` pattern "
        "(allows trailing prose; bug operator explicitly flagged 2026-05-17)"
    )
