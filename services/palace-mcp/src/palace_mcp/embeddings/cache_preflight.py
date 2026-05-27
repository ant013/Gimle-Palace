"""ML model cache preflight checks.

Verifies HuggingFace/Qodo model cache before loading.
Reports status without exposing secrets or tokens.
"""

from __future__ import annotations

import enum
import json
import logging
import os
import stat
from dataclasses import dataclass
from pathlib import Path

_logger = logging.getLogger(__name__)

class CacheStatus(enum.Enum):
    absent = "absent"
    present = "present"
    stale = "stale"
    readonly = "readonly"


@dataclass
class CacheCheckResult:
    status: CacheStatus
    cache_root: str
    model_id: str
    size_bytes: int = 0
    owner_ok: bool = True
    writeable: bool = True
    detail: str = ""


@dataclass
class CacheProvenance:
    model_id: str
    source: str
    revision: str
    cache_root: str
    recorded_at: str = ""
    version_marker: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "model_id": self.model_id,
            "source": self.source,
            "revision": self.revision,
            "cache_root": self.cache_root,
            "recorded_at": self.recorded_at,
            "version_marker": self.version_marker,
        }


# HF hub stores models under: <HF_HOME>/hub/models--<org>--<name>/snapshots/
_HF_HUB_SUBDIR = "hub"

# Sentinel file written by record_cache_provenance().
_PROVENANCE_FILENAME = "palace_cache_provenance.json"


def _hf_model_dir(cache_root: Path, model_id: str) -> Path:
    """Return the HF hub directory for a model inside cache_root."""
    repo_folder = "models--" + model_id.replace("/", "--")
    return cache_root / _HF_HUB_SUBDIR / repo_folder


def _dir_size(path: Path) -> int:
    total = 0
    try:
        for entry in path.rglob("*"):
            try:
                st = entry.stat(follow_symlinks=False)
                if stat.S_ISREG(st.st_mode):
                    total += st.st_size
            except OSError:
                pass
    except OSError:
        pass
    return total


def _owner_ok(path: Path) -> tuple[bool, str]:
    """Return (ok, reason).

    Rejects world-writable directories and mixed-owner trees
    (any file owned by a different uid than the cache root).
    """
    try:
        root_stat = path.stat()
        root_uid = root_stat.st_uid
        root_mode = root_stat.st_mode

        if root_mode & stat.S_IWOTH:
            return False, f"{path} is world-writable (mode {oct(root_mode)})"

        for entry in path.rglob("*"):
            try:
                entry_stat = entry.stat()
            except OSError:
                continue
            if entry_stat.st_uid != root_uid:
                return False, (
                    f"mixed owner: {entry} owned by uid {entry_stat.st_uid}, "
                    f"root owned by {root_uid}"
                )
            if entry.is_dir() and (entry_stat.st_mode & stat.S_IWOTH):
                return (
                    False,
                    f"{entry} is world-writable (mode {oct(entry_stat.st_mode)})",
                )

    except OSError as exc:
        return False, str(exc)
    return True, ""


def check_model_cache(
    model_id: str,
    *,
    cache_root: str | Path | None = None,
) -> CacheCheckResult:
    """Check HF model cache status for model_id.

    cache_root defaults to $HF_HOME or $TRANSFORMERS_CACHE or ~/.cache/huggingface.
    """
    if cache_root is None:
        cache_root = (
            os.environ.get("HF_HOME")
            or os.environ.get("TRANSFORMERS_CACHE")
            or os.path.join(os.path.expanduser("~"), ".cache", "huggingface")
        )
    root = Path(cache_root)

    result = CacheCheckResult(
        status=CacheStatus.absent,
        cache_root=str(root),
        model_id=model_id,
    )

    if not root.exists():
        result.detail = f"cache_root {root} does not exist"
        return result

    # Check ownership safety — unsafe ownership (world-writable/mixed-owner) is an
    # immediate hard stop regardless of model presence.
    ok, reason = _owner_ok(root)
    result.owner_ok = ok
    if not ok:
        result.status = CacheStatus.readonly
        result.detail = reason
        return result

    # Record writeability but do NOT early-return: a non-writeable (immutable) bind-mount
    # is a valid secure pattern. Model presence checks continue so local-only mode can
    # use a read-only cache without triggering a spurious readonly status.
    result.writeable = os.access(root, os.W_OK)

    # Check for HF snapshot directory.
    model_dir = _hf_model_dir(root, model_id)
    snapshots_dir = model_dir / "snapshots"

    if not model_dir.exists():
        result.detail = f"model dir {model_dir} not found"
        return result

    # A complete snapshot has at least one hash-named subdirectory with files.
    snapshot_dirs: list[Path] = []
    if snapshots_dir.exists():
        snapshot_dirs = [d for d in snapshots_dir.iterdir() if d.is_dir()]

    if not snapshot_dirs:
        result.status = CacheStatus.stale
        result.detail = (
            "model dir exists but no snapshot subdirectories found (partial download?)"
        )
        result.size_bytes = _dir_size(model_dir)
        return result

    # Check provenance marker.
    provenance_path = root / _PROVENANCE_FILENAME
    if not provenance_path.exists():
        # Cache exists but no provenance → stale from provenance perspective.
        result.status = CacheStatus.stale
        result.detail = f"model snapshot exists but {_PROVENANCE_FILENAME} not found"
        result.size_bytes = _dir_size(model_dir)
        return result

    result.status = CacheStatus.present
    result.size_bytes = _dir_size(model_dir)
    return result


def record_cache_provenance(
    model_id: str,
    *,
    source: str,
    revision: str,
    cache_root: str | Path | None = None,
) -> None:
    """Write provenance record to cache_root/palace_cache_provenance.json.

    Does not include secrets, tokens, or API keys.
    """
    import datetime

    if cache_root is None:
        cache_root = (
            os.environ.get("HF_HOME")
            or os.environ.get("TRANSFORMERS_CACHE")
            or os.path.join(os.path.expanduser("~"), ".cache", "huggingface")
        )
    root = Path(cache_root)
    root.mkdir(parents=True, exist_ok=True)

    provenance = CacheProvenance(
        model_id=model_id,
        source=source,
        revision=revision,
        cache_root=str(root),
        recorded_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        version_marker=f"{model_id}@{revision}",
    )

    provenance_path = root / _PROVENANCE_FILENAME
    provenance_path.write_text(json.dumps(provenance.to_dict(), indent=2))


def preflight_or_fail(
    model_id: str,
    *,
    cache_root: str | Path | None = None,
    local_only: bool = False,
) -> CacheCheckResult:
    """Run cache preflight and raise RuntimeError if local_only and cache is not ready.

    Always prints cache status (without secrets).
    Returns the CacheCheckResult for informational use.
    """
    result = check_model_cache(model_id, cache_root=cache_root)
    _print_cache_status(result)

    if not result.owner_ok:
        raise RuntimeError(
            f"Model cache at {result.cache_root} has unsafe ownership: "
            f"{result.detail}. "
            f"Fix cache directory ownership or permissions, then retry."
        )

    if local_only and result.status in (CacheStatus.absent, CacheStatus.stale):
        root = result.cache_root
        raise RuntimeError(
            f"Model '{model_id}' cache is {result.status.value} "
            f"(PALACE_EMBEDDING_LOCAL_ONLY=true). "
            f"Cache root: {root}. "
            f"To download: huggingface-cli download {model_id} "
            f"--cache-dir {root}. "
            f"Or set PALACE_EMBEDDING_LOCAL_ONLY=false to allow network access."
        )

    return result


def _print_cache_status(result: CacheCheckResult) -> None:
    size_mb = result.size_bytes / (1024 * 1024)
    _logger.info(
        "[cache-preflight] model=%s status=%s cache_root=%s size=%.1fMB "
        "owner_ok=%s writeable=%s%s",
        result.model_id,
        result.status.value,
        result.cache_root,
        size_mb,
        result.owner_ok,
        result.writeable,
        f" detail={result.detail!r}" if result.detail else "",
    )


