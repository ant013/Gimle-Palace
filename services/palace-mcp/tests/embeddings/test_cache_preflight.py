"""Tests for cache_preflight module."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from palace_mcp.embeddings.cache_preflight import (
    CacheStatus,
    check_model_cache,
    preflight_or_fail,
    record_cache_provenance,
)

MODEL_ID = "Qodo/Qodo-Embed-1-1.5B"
_SNAPSHOT_HASH = "abc123"


def _make_model_dir(cache_root: Path, model_id: str) -> Path:
    repo_folder = "models--" + model_id.replace("/", "--")
    snapshot_dir = cache_root / "hub" / repo_folder / "snapshots" / _SNAPSHOT_HASH
    snapshot_dir.mkdir(parents=True)
    (snapshot_dir / "config.json").write_text("{}")
    return snapshot_dir


# ── absent ────────────────────────────────────────────────────────────────────

def test_absent_when_cache_root_missing(tmp_path: Path) -> None:
    missing = tmp_path / "no-such-dir"
    result = check_model_cache(MODEL_ID, cache_root=missing)
    assert result.status == CacheStatus.absent


def test_absent_when_model_dir_missing(tmp_path: Path) -> None:
    (tmp_path / "hub").mkdir(parents=True)
    result = check_model_cache(MODEL_ID, cache_root=tmp_path)
    assert result.status == CacheStatus.absent


# ── stale ─────────────────────────────────────────────────────────────────────

def test_stale_when_no_snapshots(tmp_path: Path) -> None:
    model_repo = "models--" + MODEL_ID.replace("/", "--")
    (tmp_path / "hub" / model_repo).mkdir(parents=True)
    result = check_model_cache(MODEL_ID, cache_root=tmp_path)
    assert result.status == CacheStatus.stale


def test_stale_when_snapshot_exists_but_no_provenance(tmp_path: Path) -> None:
    _make_model_dir(tmp_path, MODEL_ID)
    result = check_model_cache(MODEL_ID, cache_root=tmp_path)
    assert result.status == CacheStatus.stale
    assert "provenance" in result.detail


# ── present ───────────────────────────────────────────────────────────────────

def test_present_with_snapshot_and_provenance(tmp_path: Path) -> None:
    _make_model_dir(tmp_path, MODEL_ID)
    record_cache_provenance(MODEL_ID, source="huggingface", revision="main", cache_root=tmp_path)
    result = check_model_cache(MODEL_ID, cache_root=tmp_path)
    assert result.status == CacheStatus.present
    assert result.owner_ok
    assert result.writeable
    assert result.size_bytes > 0


def test_present_size_bytes_nonzero(tmp_path: Path) -> None:
    _make_model_dir(tmp_path, MODEL_ID)
    record_cache_provenance(MODEL_ID, source="huggingface", revision="main", cache_root=tmp_path)
    result = check_model_cache(MODEL_ID, cache_root=tmp_path)
    assert result.size_bytes > 0


# ── readonly ──────────────────────────────────────────────────────────────────

@pytest.mark.skipif(os.getuid() == 0, reason="root bypasses permission checks")
def test_readonly_when_cache_root_not_writeable(tmp_path: Path) -> None:
    _make_model_dir(tmp_path, MODEL_ID)
    record_cache_provenance(MODEL_ID, source="huggingface", revision="main", cache_root=tmp_path)
    tmp_path.chmod(0o555)
    try:
        result = check_model_cache(MODEL_ID, cache_root=tmp_path)
        assert result.status == CacheStatus.readonly
        assert not result.writeable
    finally:
        tmp_path.chmod(0o755)


@pytest.mark.skipif(os.getuid() == 0, reason="root bypasses world-writable checks")
def test_readonly_when_world_writable(tmp_path: Path) -> None:
    _make_model_dir(tmp_path, MODEL_ID)
    tmp_path.chmod(0o777)
    try:
        result = check_model_cache(MODEL_ID, cache_root=tmp_path)
        assert result.status == CacheStatus.readonly
        assert not result.owner_ok
    finally:
        tmp_path.chmod(0o755)


# ── preflight_or_fail ─────────────────────────────────────────────────────────

def test_preflight_passes_when_present(tmp_path: Path) -> None:
    _make_model_dir(tmp_path, MODEL_ID)
    record_cache_provenance(MODEL_ID, source="huggingface", revision="main", cache_root=tmp_path)
    result = preflight_or_fail(MODEL_ID, cache_root=tmp_path, local_only=True)
    assert result.status == CacheStatus.present


def test_preflight_raises_on_absent_in_local_only(tmp_path: Path) -> None:
    missing = tmp_path / "no-cache"
    with pytest.raises(RuntimeError, match="PALACE_EMBEDDING_LOCAL_ONLY"):
        preflight_or_fail(MODEL_ID, cache_root=missing, local_only=True)


def test_preflight_raises_on_stale_in_local_only(tmp_path: Path) -> None:
    _make_model_dir(tmp_path, MODEL_ID)
    # No provenance → stale
    with pytest.raises(RuntimeError, match="stale"):
        preflight_or_fail(MODEL_ID, cache_root=tmp_path, local_only=True)


def test_preflight_does_not_raise_when_absent_and_not_local_only(tmp_path: Path) -> None:
    missing = tmp_path / "no-cache"
    result = preflight_or_fail(MODEL_ID, cache_root=missing, local_only=False)
    assert result.status == CacheStatus.absent


# ── provenance ────────────────────────────────────────────────────────────────

def test_record_cache_provenance_no_secrets(tmp_path: Path) -> None:
    record_cache_provenance(MODEL_ID, source="huggingface", revision="main", cache_root=tmp_path)
    provenance_path = tmp_path / "palace_cache_provenance.json"
    assert provenance_path.exists()
    data = json.loads(provenance_path.read_text())
    assert data["model_id"] == MODEL_ID
    assert data["source"] == "huggingface"
    assert data["revision"] == "main"
    assert "token" not in data
    assert "key" not in data
    assert "secret" not in data


def test_record_cache_provenance_integrity_marker(tmp_path: Path) -> None:
    record_cache_provenance(MODEL_ID, source="huggingface", revision="abc123", cache_root=tmp_path)
    data = json.loads((tmp_path / "palace_cache_provenance.json").read_text())
    assert data["integrity_marker"] == f"{MODEL_ID}@abc123"


# ── env-var default ───────────────────────────────────────────────────────────

def test_cache_root_from_hf_home_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HF_HOME", str(tmp_path))
    result = check_model_cache(MODEL_ID)
    assert result.cache_root == str(tmp_path)
