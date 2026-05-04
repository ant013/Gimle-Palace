#!/usr/bin/env python3
"""Smoke test for dependency_surface extractor.

Runs the extractor against a local repo path and prints stats.
Requires PALACE_NEO4J_URI (and optionally PALACE_NEO4J_PASSWORD) env vars,
or a running palace-mcp server accessible via MCP.

Usage:
    python scripts/smoke_dependency_surface.py --project gimle
    python scripts/smoke_dependency_surface.py --project uw-android
    python scripts/smoke_dependency_surface.py --project gimle --repo-path /path/to/repo
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


async def run_smoke(project: str, repo_path: Path | None) -> None:
    """Run dependency_surface extractor and print results."""
    import os

    from neo4j import AsyncGraphDatabase

    from palace_mcp.extractors.dependency_surface.extractor import (
        DependencySurfaceExtractor,
    )
    from palace_mcp.extractors.base import ExtractorRunContext
    import logging
    import uuid

    uri = os.environ.get("PALACE_NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("PALACE_NEO4J_USER", "neo4j")
    password = os.environ.get("PALACE_NEO4J_PASSWORD", "password")

    if repo_path is None:
        # Infer from PALACE_SCIP_INDEX_PATHS or default
        scip_paths_raw = os.environ.get("PALACE_SCIP_INDEX_PATHS", "{}")
        scip_paths = json.loads(scip_paths_raw)
        # Try to find the repo path from known locations
        known = {
            "gimle": "/repos/gimle",
            "uw-android": "/repos/uw-android",
            "uw-ios": "/repos/uw-ios",
        }
        resolved = scip_paths.get(project) or known.get(project)
        if resolved:
            repo_path = (
                Path(resolved).parent if resolved.endswith(".scip") else Path(resolved)
            )
        else:
            print(
                f"ERROR: --repo-path required for project {project!r}", file=sys.stderr
            )
            sys.exit(1)

    print(f"Smoke: dependency_surface project={project} repo_path={repo_path}")

    driver = AsyncGraphDatabase.driver(uri, auth=(user, password))
    try:
        # Monkey-patch get_driver
        import palace_mcp.mcp_server as _ms

        _ms._driver = driver  # type: ignore[attr-defined]

        from palace_mcp.extractors.foundation.schema import ensure_custom_schema

        await ensure_custom_schema(driver)

        # Ensure :Project exists
        async with driver.session() as s:
            await s.run(
                "MERGE (p:Project {slug: $slug, group_id: $gid})",
                slug=project,
                gid=f"project/{project}",
            )

        extractor = DependencySurfaceExtractor()
        ctx = ExtractorRunContext(
            project_slug=project,
            group_id=f"project/{project}",
            repo_path=repo_path,
            run_id=str(uuid.uuid4()),
            duration_ms=0,
            logger=logging.getLogger("smoke"),
        )
        from unittest.mock import MagicMock

        stats = await extractor.run(graphiti=MagicMock(), ctx=ctx)

        print(f"  nodes_written={stats.nodes_written}")
        print(f"  edges_written={stats.edges_written}")

        # Cypher: verify edges
        async with driver.session() as s:
            result = await s.run(
                "MATCH (p:Project {slug: $slug})-[r:DEPENDS_ON]->(d:ExternalDependency) "
                "RETURN d.purl AS purl, r.scope AS scope, r.declared_in AS declared_in "
                "ORDER BY d.purl LIMIT 20",
                slug=project,
            )
            records = await result.data()

        print(f"\n  Sample deps ({min(len(records), 20)} shown):")
        for r in records:
            print(
                f"    {r['purl']}  scope={r['scope']}  declared_in={r['declared_in']}"
            )

        print("\nSMOKE PASS")
    finally:
        await driver.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Smoke test for dependency_surface extractor"
    )
    parser.add_argument(
        "--project", required=True, help="Project slug (e.g. gimle, uw-android)"
    )
    parser.add_argument(
        "--repo-path", type=Path, default=None, help="Path to repo root"
    )
    args = parser.parse_args()
    asyncio.run(run_smoke(args.project, args.repo_path))


if __name__ == "__main__":
    main()
