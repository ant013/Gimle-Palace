"""Conservative regex-based bot detector — see spec GIM-186 §6."""

from __future__ import annotations

import re

_BOT_EMAIL_PATTERNS = [
    re.compile(r".*\[bot\]@users\.noreply\.github\.com$"),
    re.compile(r".*@dependabot\.com$"),
    re.compile(r"^renovate\[bot\]@.*"),
]
_BOT_NAME_PATTERNS = [
    re.compile(r"^github-actions(\[bot\])?$", re.I),
    re.compile(r"^dependabot(\[bot\])?$", re.I),
    re.compile(r"^renovate(\[bot\])?$", re.I),
    re.compile(r"^paperclip-bot$", re.I),
    re.compile(r".*\[bot\]$", re.I),
]


def is_bot(email: str | None, name: str | None) -> bool:
    """Return True if email or name matches any conservative bot pattern."""
    if email:
        if any(p.match(email) for p in _BOT_EMAIL_PATTERNS):
            return True
    if name:
        if any(p.match(name) for p in _BOT_NAME_PATTERNS):
            return True
    return False
