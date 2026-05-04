"""Unit tests for purl construction helpers — Task 2."""

from __future__ import annotations

import pytest

from palace_mcp.extractors.dependency_surface.purl import build_purl, spm_purl_from_url


@pytest.mark.parametrize(
    "ecosystem,name,version,extras,expected",
    [
        ("pypi", "neo4j", "5.28.2", {}, "pkg:pypi/neo4j@5.28.2"),
        ("pypi", "graphiti-core", "0.28.2", {}, "pkg:pypi/graphiti-core@0.28.2"),
        ("pypi", "FastAPI", "0.115.0", {}, "pkg:pypi/fastapi@0.115.0"),
        (
            "maven",
            "androidx.appcompat:appcompat",
            "1.7.1",
            {},
            "pkg:maven/androidx.appcompat/appcompat@1.7.1",
        ),
        (
            "maven",
            "com.squareup.retrofit2:retrofit",
            "3.0.0",
            {},
            "pkg:maven/com.squareup.retrofit2/retrofit@3.0.0",
        ),
        (
            "github",
            "horizontalsystems/EvmKit.Swift",
            "1.5.3",
            {},
            "pkg:github/horizontalsystems/EvmKit.Swift@1.5.3",
        ),
        (
            "github",
            "apple/swift-collections",
            "1.1.4",
            {},
            "pkg:github/apple/swift-collections@1.1.4",
        ),
        ("pypi", "pytest", "8.3.4", {}, "pkg:pypi/pytest@8.3.4"),
        (
            "maven",
            "org.jetbrains.kotlin:kotlin-stdlib",
            "2.0.0",
            {},
            "pkg:maven/org.jetbrains.kotlin/kotlin-stdlib@2.0.0",
        ),
        ("pypi", "httpx", "0.27.0", {}, "pkg:pypi/httpx@0.27.0"),
        ("pypi", "pydantic", "2.10.0", {}, "pkg:pypi/pydantic@2.10.0"),
    ],
)
def test_purl_construction(
    ecosystem: str, name: str, version: str, extras: dict[str, str], expected: str
) -> None:
    assert (
        build_purl(ecosystem=ecosystem, name=name, version=version, **extras)
        == expected
    )


def test_spm_url_to_purl_github() -> None:
    assert (
        spm_purl_from_url(
            "https://github.com/horizontalsystems/EvmKit.Swift.git", "1.5.3"
        )
        == "pkg:github/horizontalsystems/EvmKit.Swift@1.5.3"
    )


def test_spm_url_to_purl_github_no_dot_git() -> None:
    assert (
        spm_purl_from_url("https://github.com/horizontalsystems/EvmKit.Swift", "1.5.3")
        == "pkg:github/horizontalsystems/EvmKit.Swift@1.5.3"
    )


def test_spm_url_to_purl_github_case_insensitive() -> None:
    assert (
        spm_purl_from_url("https://GitHub.com/apple/swift-collections.git", "1.1.4")
        == "pkg:github/apple/swift-collections@1.1.4"
    )


def test_spm_url_to_purl_non_github_fallback() -> None:
    purl = spm_purl_from_url("https://example.com/foo.git", "1.0.0")
    assert purl.startswith("pkg:generic/spm-package?vcs_url=")
    assert "example.com" in purl
    assert purl.endswith("@1.0.0")


def test_spm_url_non_github_contains_encoded_url() -> None:
    purl = spm_purl_from_url("https://gitlab.example.com/org/repo.git", "2.0.0")
    assert purl.startswith("pkg:generic/spm-package?vcs_url=")
    assert purl.endswith("@2.0.0")
    assert "%" in purl  # URL-encoded


def test_build_purl_maven_splits_on_colon() -> None:
    purl = build_purl(ecosystem="maven", name="com.example:artifact", version="1.0.0")
    assert purl == "pkg:maven/com.example/artifact@1.0.0"


def test_build_purl_pypi_lowercases_name() -> None:
    # PyPI names are case-insensitive; canonical form is lowercase
    purl = build_purl(ecosystem="pypi", name="SQLAlchemy", version="2.0.0")
    assert purl == "pkg:pypi/sqlalchemy@2.0.0"
