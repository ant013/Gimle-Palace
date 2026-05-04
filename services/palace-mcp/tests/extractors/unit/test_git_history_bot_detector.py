import pytest
from palace_mcp.extractors.git_history.bot_detector import is_bot


@pytest.mark.parametrize(
    "email,name,expected",
    [
        # Positive — known bots
        ("github-actions[bot]@users.noreply.github.com", "github-actions[bot]", True),
        ("dependabot[bot]@users.noreply.github.com", "dependabot[bot]", True),
        ("any@dependabot.com", "Dependabot", True),
        ("renovate[bot]@whatever.com", "renovate[bot]", True),
        (None, "github-actions", True),
        (None, "Dependabot", True),
        (None, "Renovate[bot]", True),
        (None, "paperclip-bot", True),
        (None, "Custom[bot]", True),
        # Negative — humans with bot-like substrings (rev2 tightening)
        ("bot-fan@company.com", "Bot Fan", False),
        ("someone-bot@company.com", "Someone", False),  # rev2 critical: was bot in rev1
        ("robot@example.com", "Robot Joe", False),
        ("foo@bar.com", "github-action", False),  # close but not exact
        # Edge — empty/None handling
        (None, None, False),
        ("", "", False),
        ("foo@bar.com", "", False),
        (None, "", False),
        # Edge — case sensitivity
        (
            "any@DEPENDABOT.com",
            "any",
            False,
        ),  # email regex is case-sensitive (per spec); known limitation
        (None, "GITHUB-ACTIONS", True),  # name regex IS case-insensitive (per re.I)
        # Edge — Unicode in name
        (None, "Пётр[bot]", True),  # generic *[bot] suffix matches
        # Trailing whitespace
        (None, "github-actions ", False),  # exact match required; trailing ws breaks
    ],
)
def test_is_bot_parametrized(email, name, expected):
    assert is_bot(email, name) is expected
