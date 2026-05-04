"""purl (Package URL) construction helpers for dependency_surface extractor.

Spec §6 — purl conventions per ecosystem:
  pypi  → pkg:pypi/<name_lowercase>@<version>
  maven → pkg:maven/<group>/<artifact>@<version>  (name = "group:artifact")
  github (SPM) → pkg:github/<owner>/<repo>@<version>
  generic SPM fallback → pkg:generic/spm-package?vcs_url=<encoded>@<version>
"""

from __future__ import annotations

from urllib.parse import quote, urlparse


def build_purl(*, ecosystem: str, name: str, version: str, **_extras: str) -> str:
    """Build a Package URL string for the given ecosystem/name/version."""
    if ecosystem == "pypi":
        return f"pkg:pypi/{name.lower()}@{version}"

    if ecosystem == "maven":
        # name is expected as "group:artifact"
        if ":" in name:
            group, artifact = name.split(":", 1)
        else:
            group, artifact = name, name
        return f"pkg:maven/{group}/{artifact}@{version}"

    if ecosystem == "github":
        # name is "owner/repo"
        return f"pkg:github/{name}@{version}"

    # Fallback
    return f"pkg:{ecosystem}/{name}@{version}"


def spm_purl_from_url(url: str, version: str) -> str:
    """Build a purl from an SPM package URL.

    - GitHub URLs → pkg:github/<owner>/<repo>@<version>
    - All others → pkg:generic/spm-package?vcs_url=<encoded>@<version>
    """
    parsed = urlparse(url)
    host = parsed.hostname or ""

    if host.lower() == "github.com":
        path = parsed.path.rstrip("/")
        if path.endswith(".git"):
            path = path[: -len(".git")]
        # path is now /owner/repo — strip leading slash
        owner_repo = path.lstrip("/")
        return f"pkg:github/{owner_repo}@{version}"

    # Non-GitHub: generic fallback with URL-encoded vcs_url
    encoded = quote(url, safe="")
    return f"pkg:generic/spm-package?vcs_url={encoded}@{version}"
