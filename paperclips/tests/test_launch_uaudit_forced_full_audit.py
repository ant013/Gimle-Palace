from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "paperclips/scripts/launch_uaudit_forced_full_audit.py"
SPEC = importlib.util.spec_from_file_location("launch_uaudit_forced_full_audit", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def routine(platform: str, *, major: int = 0) -> dict:
    return {
        "id": f"daily-{platform}-version-audit",
        "app_id": "unstoppable_wallet",
        "platform": platform,
        "release_policy": {"major": major, "transition": "when-active-branch-missing"},
        "repo_local_path_template": "{{paths.repo}}",
        "dispatcher": "UWACTO" if platform == "android" else "UWICTO",
    }


def test_full_range_payload_requires_canonical_refs_and_forbids_cursor_mutation(tmp_path, monkeypatch):
    monkeypatch.setattr(MODULE, "git", lambda *_args: "")
    config = {"apps": [{"id": "unstoppable_wallet", "enabled": True}], "routines": [routine("android"), routine("ios")]}
    payloads = MODULE.build_payloads(
        config,
        {"repo": str(tmp_path)},
        {"UWACTO": "android-dispatcher", "UWICTO": "ios-dispatcher"},
        "unstoppable_wallet",
        "all",
        "version/0.52",
        "a" * 40,
        "b" * 40,
    )
    assert len(payloads) == 2
    assert all("UAudit forced full-range audit" in item["description"] for item in payloads)
    assert all("daily_limits_bypassed: true" in item["description"] for item in payloads)
    assert all("app_id: unstoppable_wallet" in item["description"] for item in payloads)
    assert all("branch: version/0.52" in item["description"] for item in payloads)
    assert all("cursor_mutation: forbidden" in item["description"] for item in payloads)
    assert all("schedule_mutation: forbidden" in item["description"] for item in payloads)
    assert all("cursor:" not in item["description"] for item in payloads)


def test_full_range_payload_rejects_non_sha(tmp_path):
    with pytest.raises(ValueError, match="from_sha"):
        MODULE.build_payloads(
            {"apps": [{"id": "unstoppable_wallet", "enabled": True}], "routines": [routine("android")]},
            {"repo": str(tmp_path)},
            {"UWACTO": "android-dispatcher"},
            "unstoppable_wallet",
            "android",
            "version/0.52",
            "not-a-sha",
            "b" * 40,
        )


@pytest.mark.parametrize(
    "branch",
    ("version/00.52", "version/0.052", "version/0", "release/0.52"),
)
def test_full_range_payload_rejects_noncanonical_branch(tmp_path, branch):
    with pytest.raises(ValueError, match="branch must be canonical"):
        MODULE.build_payloads(
            {"apps": [{"id": "unstoppable_wallet", "enabled": True}], "routines": [routine("android")]},
            {"repo": str(tmp_path)},
            {"UWACTO": "android-dispatcher"},
            "unstoppable_wallet",
            "android",
            branch,
            "a" * 40,
            "b" * 40,
        )


def test_full_range_payload_rejects_branch_outside_release_policy_major(tmp_path):
    with pytest.raises(ValueError, match=r"branch major 1 does not match android release_policy\.major 0"):
        MODULE.build_payloads(
            {"apps": [{"id": "unstoppable_wallet", "enabled": True}], "routines": [routine("android")]},
            {"repo": str(tmp_path)},
            {"UWACTO": "android-dispatcher"},
            "unstoppable_wallet",
            "android",
            "version/1.0",
            "a" * 40,
            "b" * 40,
        )
