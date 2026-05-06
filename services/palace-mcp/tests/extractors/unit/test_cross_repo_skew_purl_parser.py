"""Unit tests for purl_root_for_display."""

from __future__ import annotations

from palace_mcp.extractors.cross_repo_version_skew.purl_parser import (
    purl_root_for_display,
)


def test_github_purl_strips_version():
    assert (
        purl_root_for_display("pkg:github/horizontalsystems/marketkit@1.5.0")
        == "pkg:github/horizontalsystems/marketkit"
    )


def test_maven_purl_strips_version():
    assert (
        purl_root_for_display("pkg:maven/com.example/lib@1.0.0")
        == "pkg:maven/com.example/lib"
    )


def test_pypi_purl_strips_version():
    assert purl_root_for_display("pkg:pypi/requests@2.31.0") == "pkg:pypi/requests"


def test_generic_spm_purl_with_query_qualifier():
    """Generic SPM purl: pkg:generic/spm-package?vcs_url=<encoded>@<version>.

    rfind('@') finds the version separator (URL-encoded vcs_url has %40 not @).
    """
    purl = "pkg:generic/spm-package?vcs_url=https%3A%2F%2Fexample.com%2Frepo.git@1.0.0"
    assert (
        purl_root_for_display(purl)
        == "pkg:generic/spm-package?vcs_url=https%3A%2F%2Fexample.com%2Frepo.git"
    )


def test_multiple_at_uses_rsplit():
    """Last @ is the version separator (defensive)."""
    assert purl_root_for_display("pkg:maven/g/a@b@1.0.0") == "pkg:maven/g/a@b"


def test_no_version_returns_input_unchanged():
    """If no @ separator, return input as-is (caller filters via Cypher anyway)."""
    assert purl_root_for_display("pkg:pypi/foo") == "pkg:pypi/foo"
