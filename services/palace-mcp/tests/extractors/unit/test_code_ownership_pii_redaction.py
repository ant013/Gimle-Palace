"""Audit test: code_ownership package source must not log raw emails.

Per spec rev2 §8: error_message + INFO logs MUST NOT contain raw email
addresses. This test scans the package source for log calls that
include obvious email-typed expressions (e.g. f-strings on .email or
identity_key passed to logger.* calls). The check is conservative;
maintainers may explicitly opt-out per call-site with `# noqa: PII`.
"""

from __future__ import annotations

import re
from pathlib import Path

PKG = (
    Path(__file__).resolve().parents[3]
    / "src"
    / "palace_mcp"
    / "extractors"
    / "code_ownership"
)

_LOG_RE = re.compile(r"logger\.(info|warning|error|debug|exception)\(")
_EMAIL_TOKENS = ("\\.email", "\\.identity_key", "raw_email", "canonical_email")


def _line_has_email_expr(line: str) -> bool:
    return any(re.search(token, line) for token in _EMAIL_TOKENS)


def test_no_email_log_calls_in_code_ownership_package() -> None:
    """`# noqa: PII` opt-out is allowed for explicit, audited exceptions."""
    offenders: list[tuple[Path, int, str]] = []
    for py in sorted(PKG.rglob("*.py")):
        for n, line in enumerate(py.read_text().splitlines(), start=1):
            if "noqa: PII" in line:
                continue
            if _LOG_RE.search(line) and _line_has_email_expr(line):
                offenders.append((py, n, line.strip()))
    assert offenders == [], (
        "Found logger calls that interpolate email-typed values:\n"
        + "\n".join(f"  {p}:{n}: {ln}" for p, n, ln in offenders)
    )
