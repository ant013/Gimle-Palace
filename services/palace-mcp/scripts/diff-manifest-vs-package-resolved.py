"""CI drift check: compare uw-ios-bundle-manifest.json vs UW-iOS Package.resolved (GIM-182 §8).

Exit 0 — in sync.
Exit 1 — drift detected; prints diff to stderr.

Usage:
    python diff-manifest-vs-package-resolved.py \
        --manifest services/palace-mcp/scripts/uw-ios-bundle-manifest.json \
        --package-resolved path/to/unstoppable-wallet-ios/Package.resolved
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def load_manifest_slugs(manifest_path: Path) -> dict[str, str]:
    """Return {slug: relative_path} for first-party members (excludes user tier)."""
    manifest = json.loads(manifest_path.read_text())
    return {
        m["slug"]: m["relative_path"]
        for m in manifest["members"]
        if m.get("tier") == "first-party"
    }


def load_resolved_packages(resolved_path: Path) -> set[str]:
    """Return set of package repository base names from Package.resolved v2 or v3."""
    resolved = json.loads(resolved_path.read_text())
    pins = resolved.get("pins") or resolved.get("object", {}).get("pins", [])
    names: set[str] = set()
    for pin in pins:
        url = pin.get("location") or pin.get("repositoryURL", "")
        if "horizontalsystems" in url.lower():
            # Extract base repo name (strip .git suffix and path prefix)
            name = url.rstrip("/").split("/")[-1]
            if name.endswith(".git"):
                name = name[:-4]
            names.add(name)
    return names


def main() -> int:
    parser = argparse.ArgumentParser(description="Check manifest vs Package.resolved drift")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--package-resolved", required=True, type=Path, dest="resolved")
    args = parser.parse_args()

    manifest_slugs = load_manifest_slugs(args.manifest)
    manifest_rel_paths = set(manifest_slugs.values())
    resolved_names = load_resolved_packages(args.resolved)

    # Cross-match by relative_path (directory name) vs Package.resolved repo name
    manifest_repo_names = {p.split("/")[-1] if "/" in p else p for p in manifest_rel_paths}

    in_resolved_not_manifest = resolved_names - manifest_repo_names
    in_manifest_not_resolved = manifest_repo_names - resolved_names

    if not in_resolved_not_manifest and not in_manifest_not_resolved:
        print(f"OK: manifest and Package.resolved are in sync ({len(resolved_names)} HS packages)")
        return 0

    print("DRIFT DETECTED:", file=sys.stderr)
    if in_resolved_not_manifest:
        print(
            f"  In Package.resolved but NOT in manifest ({len(in_resolved_not_manifest)}):",
            file=sys.stderr,
        )
        for name in sorted(in_resolved_not_manifest):
            print(f"    + {name}", file=sys.stderr)
    if in_manifest_not_resolved:
        print(
            f"  In manifest but NOT in Package.resolved ({len(in_manifest_not_resolved)}):",
            file=sys.stderr,
        )
        for name in sorted(in_manifest_not_resolved):
            print(f"    - {name}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
