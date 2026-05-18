"""purl helpers for cross_repo_version_skew.

Per spec rev2 C3: GIM-191 writer stores ecosystem and resolved_version
as :ExternalDependency properties; we read those directly from Cypher.
This module is reduced to a single display helper.
"""

from __future__ import annotations


def purl_root_for_display(purl: str) -> str:
    """Strip @<version> suffix from a purl. Last `@` only (rsplit).

    Returns purl unchanged if there is no `@` separator.
    """
    if "@" not in purl:
        return purl
    return purl.rsplit("@", 1)[0]
