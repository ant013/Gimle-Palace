#!/usr/bin/env python3
"""One-time deploy backfill for :Project.indexed_commit (F2, Sprint-1).

For every :Project with code stats, populate the authoritative indexed commit
from :ExtractorBaseline (ingest-time tree HEAD). Projects without a baseline
are left null with indexed_commit_status='unavailable' — honestly reported as
unknown until their next re-ingest. Also applies the F3 registry repairs when
--repair is passed (tron-kit repo_path, hd-wallet-kit relative_path) and
prints a before/after identity sweep.

Usage:
  backfill_indexed_commit.py --uri bolt://localhost:7687 --user neo4j \
      --password-env NEO4J_PASSWORD [--repair] [--dry-run]
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone

from neo4j import GraphDatabase

BACKFILL = """
MATCH (p:Project)
WHERE p.parent_mount IS NOT NULL
OPTIONAL MATCH (b:ExtractorBaseline {project_id: 'project/' + p.slug})
WITH p, b ORDER BY b.updated_at DESC
WITH p, collect(coalesce(b.indexed_commit, b.commit_sha))[0] AS commit
RETURN p.slug AS slug, p.indexed_commit AS existing, commit
ORDER BY slug
"""

SET_OK = """
MATCH (p:Project {slug: $slug})
SET p.indexed_commit = $commit,
    p.indexed_at = $now,
    p.indexed_commit_status = 'ok',
    p.indexed_commit_checked_at = $now
"""

SET_UNAVAILABLE = """
MATCH (p:Project {slug: $slug})
SET p.indexed_commit_status = 'unavailable',
    p.indexed_commit_checked_at = $now
"""

REPAIRS = [
    (
        "tron-kit",
        "MATCH (p:Project {slug: 'tron-kit'}) "
        "SET p.repo_path = '/Users/Shared/Ios/Gimle-Repos/HorizontalSystems/TronKit.Swift' "
        "RETURN p.repo_path",
    ),
    (
        "hd-wallet-kit",
        "MATCH (p:Project {slug: 'hd-wallet-kit'}) "
        "SET p.relative_path = 'hd-wallet-kit-ios' "
        "RETURN p.relative_path",
    ),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--uri", default="bolt://localhost:7687")
    ap.add_argument("--user", default="neo4j")
    ap.add_argument("--password-env", default="NEO4J_PASSWORD")
    ap.add_argument("--repair", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    password = os.environ.get(args.password_env)
    if not password:
        print(f"missing env {args.password_env}", file=sys.stderr)
        return 2

    now = datetime.now(timezone.utc).isoformat()
    driver = GraphDatabase.driver(args.uri, auth=(args.user, password))
    with driver.session() as session:
        if args.repair:
            for slug, stmt in REPAIRS:
                if args.dry_run:
                    print(f"DRY-RUN repair {slug}")
                else:
                    session.run(stmt).consume()
                    print(f"repaired {slug}")

        rows = list(session.run(BACKFILL))
        for row in rows:
            slug, existing, commit = row["slug"], row["existing"], row["commit"]
            if existing:
                print(f"{slug}: keep existing {existing[:9]}")
                continue
            if commit:
                if args.dry_run:
                    print(f"{slug}: DRY-RUN would set {commit[:9]}")
                else:
                    session.run(SET_OK, slug=slug, commit=commit, now=now).consume()
                    print(f"{slug}: set {commit[:9]}")
            else:
                if args.dry_run:
                    print(f"{slug}: DRY-RUN would mark unavailable (no baseline)")
                else:
                    session.run(SET_UNAVAILABLE, slug=slug, now=now).consume()
                    print(f"{slug}: unavailable (no baseline)")
    driver.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
