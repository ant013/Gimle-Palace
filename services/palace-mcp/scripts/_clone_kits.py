"""Clone or update all HorizontalSystems Kits listed in the manifest (GIM-182 §7.1).

Usage:
    python3 _clone_kits.py \
        --manifest uw-ios-bundle-manifest.json \
        --base /Users/Shared/Ios/HorizontalSystems

Idempotent: if a repo already exists at <base>/<relative_path>, runs git fetch + pull.
Requires: git on PATH; SSH key access to github.com (or configured HTTPS credentials).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

HS_GITHUB_ORG = "https://github.com/horizontalsystems"


def _run(cmd: list[str], cwd: Path | None = None) -> int:
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  STDERR: {result.stderr.strip()[:300]}", file=sys.stderr)
    return result.returncode


def clone_or_update(rel_path: str, base_dir: Path, slug: str) -> bool:
    kit_dir = base_dir / rel_path
    repo_name = rel_path.split("/")[-1] if "/" in rel_path else rel_path
    remote_url = f"{HS_GITHUB_ORG}/{repo_name}.git"

    if (kit_dir / ".git").exists():
        print(f"  update: {slug} ({rel_path})")
        rc = _run(["git", "-C", str(kit_dir), "fetch", "--quiet", "origin"], cwd=base_dir)
        if rc != 0:
            print(f"  WARN: fetch failed for {slug}", file=sys.stderr)
            return False
        _run(["git", "-C", str(kit_dir), "pull", "--ff-only", "--quiet"], cwd=base_dir)
        return True

    print(f"  clone: {slug} → {kit_dir}")
    kit_dir.parent.mkdir(parents=True, exist_ok=True)
    rc = _run(["git", "clone", "--depth=1", "--quiet", remote_url, str(kit_dir)])
    if rc != 0:
        print(f"  FAIL: clone failed for {slug} from {remote_url}", file=sys.stderr)
        return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Clone/update all HS Kits from manifest")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--base", required=True, type=Path)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text())
    args.base.mkdir(parents=True, exist_ok=True)

    ok = fail = 0
    for m in manifest["members"]:
        if clone_or_update(m["relative_path"], args.base, m["slug"]):
            ok += 1
        else:
            fail += 1

    print(f"Done: {ok} ok, {fail} failed")
    return 1 if fail > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
