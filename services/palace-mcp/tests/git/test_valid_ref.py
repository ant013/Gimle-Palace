"""Security tests for _valid_ref. Spec §5.2."""

from __future__ import annotations

import pytest

from palace_mcp.git.tools import _valid_ref


VALID_REFS = [
    "HEAD",
    "main",
    "develop",
    "feature/my-branch",
    "v1.0.0",
    "refs/heads/main",
    "abc1234",
    "a" * 200,  # max length
    "HEAD~3",
    "origin/main",
    "tag@v1",
]

INVALID_REFS = [
    "",  # empty
    " main",  # leading space
    "main branch",  # space in middle
    "--injected-flag",  # leading dash (flag injection)
    "-n",  # flag injection
    "\x00hidden",  # NUL byte
    "ref\nnewline",  # newline
    "ref\ttab",  # tab
    "a" * 201,  # exceeds 200 chars
    "$(evil)",  # shell metachar
    "`backtick`",  # backtick
    "ref;evil",  # semicolon
    "ref|pipe",  # pipe
    "ref&bg",  # ampersand
    "ref>redirect",  # redirect
    "ref<redirect",  # redirect
    "ref'quote",  # single quote
    'ref"quote',  # double quote
    "ref\\backslash",  # backslash (not in whitelist)
]


@pytest.mark.parametrize("ref", VALID_REFS)
def test_valid_ref_accepts(ref: str) -> None:
    assert _valid_ref(ref) is True, f"expected valid: {ref!r}"


@pytest.mark.parametrize("ref", INVALID_REFS)
def test_valid_ref_rejects(ref: str) -> None:
    assert _valid_ref(ref) is False, f"expected invalid: {ref!r}"
