#!/usr/bin/env python3
"""Install repo-owned UAudit Codex subagents into the shared Codex home."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import shutil
import sys
from pathlib import Path


EXPECTED = {
    "uaudit-swift-audit-specialist.toml",
    "uaudit-kotlin-audit-specialist.toml",
    "uaudit-bug-hunter.toml",
    "uaudit-security-auditor.toml",
    "uaudit-blockchain-auditor.toml",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def repo_root_from_script() -> Path:
    return Path(__file__).resolve().parents[2]


def validate_sources(source_dir: Path) -> list[Path]:
    files = sorted(source_dir.glob("uaudit-*.toml"))
    names = {path.name for path in files}
    missing = EXPECTED - names
    extra = names - EXPECTED
    if missing:
        raise ValueError(f"missing UAudit agent definitions: {', '.join(sorted(missing))}")
    if extra:
        raise ValueError(f"unexpected UAudit agent definitions: {', '.join(sorted(extra))}")
    for path in files:
        text = path.read_text()
        if 'sandbox_mode = "read-only"' not in text:
            raise ValueError(f"{path.name} must be sandbox_mode read-only")
        expected_name = path.stem
        if f'name = "{expected_name}"' not in text:
            raise ValueError(f"{path.name} name field must equal {expected_name}")
    return files


def manifest_path(backup_dir: Path) -> Path:
    return backup_dir / "uaudit-codex-agents-install.json"


def install(source_dir: Path, codex_home: Path, backup_dir: Path, dry_run: bool) -> int:
    files = validate_sources(source_dir)
    agents_dir = codex_home / "agents"
    backup_dir.mkdir(parents=True, exist_ok=True)
    print(f"sourceDir={source_dir}")
    print(f"codexHome={codex_home}")
    print(f"backupDir={backup_dir}")
    if dry_run:
        for source in files:
            print(f"WOULD INSTALL {source.name} sha256={sha256(source)}")
        return 0

    agents_dir.mkdir(parents=True, exist_ok=True)
    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    records = []
    for source in files:
        dest = agents_dir / source.name
        backup = None
        if dest.exists():
            backup = backup_dir / f"{source.name}.{timestamp}.bak"
            shutil.copy2(dest, backup)
        shutil.copy2(source, dest)
        source_sha = sha256(source)
        dest_sha = sha256(dest)
        if dest_sha != source_sha:
            raise ValueError(f"post-install sha mismatch for {source.name}")
        records.append(
            {
                "name": source.name,
                "source": str(source),
                "destination": str(dest),
                "backup": str(backup) if backup else "",
                "sha256": source_sha,
            }
        )
        print(f"INSTALLED {source.name} sha256={source_sha[:12]}")

    manifest_path(backup_dir).write_text(json.dumps(records, indent=2, sort_keys=True) + "\n")
    print(f"manifest={manifest_path(backup_dir)}")
    return 0


def rollback(backup_dir: Path) -> int:
    path = manifest_path(backup_dir)
    if not path.is_file():
        raise FileNotFoundError(f"missing install manifest: {path}")
    records = json.loads(path.read_text())
    for record in records:
        dest = Path(record["destination"])
        backup = record.get("backup", "")
        if backup:
            backup_path = Path(backup)
            if not backup_path.is_file():
                raise FileNotFoundError(f"missing backup for {record['name']}: {backup_path}")
            shutil.copy2(backup_path, dest)
            print(f"RESTORED {record['name']} from {backup_path}")
        elif dest.exists():
            dest.unlink()
            print(f"REMOVED {record['name']} (no previous backup)")
    return 0


def main() -> int:
    repo_root = repo_root_from_script()
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, default=repo_root / "paperclips/projects/uaudit/codex-agents")
    parser.add_argument("--codex-home", type=Path, default=Path.home() / ".codex")
    parser.add_argument("--backup-dir", type=Path, default=Path("/tmp/uaudit-codex-agent-backups"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--rollback", action="store_true")
    args = parser.parse_args()

    try:
        if args.rollback:
            return rollback(args.backup_dir.expanduser().resolve())
        return install(
            args.source_dir.expanduser().resolve(),
            args.codex_home.expanduser().resolve(),
            args.backup_dir.expanduser().resolve(),
            args.dry_run,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
