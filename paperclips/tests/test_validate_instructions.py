from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import validate_instructions  # noqa: E402


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    shutil.copytree(Path(__file__).resolve().parents[1], repo / "paperclips")
    for noisy in [
        repo / "paperclips" / "tests",
        repo / "paperclips" / "scripts" / "__pycache__",
    ]:
        if noisy.exists():
            shutil.rmtree(noisy)
    return repo


def test_current_repo_metadata_valid() -> None:
    errors = validate_instructions.validate(Path(__file__).resolve().parents[2])
    assert errors == []


def test_unknown_profile_fails(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    role_path = repo / "paperclips" / "roles" / "python-engineer.md"
    role_path.write_text(
        role_path.read_text().replace(
            "profiles: [core, task-start, implementation, handoff]",
            "profiles: [core, missing-profile]",
            1,
        )
    )

    errors = validate_instructions.validate(repo)

    assert any("unknown profile missing-profile" in error for error in errors)


def test_generated_front_matter_fails(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    dist_path = repo / "paperclips" / "dist" / "python-engineer.md"
    dist_path.write_text("---\nrole_id: bad\n---\n" + dist_path.read_text())
    baseline_path = repo / "paperclips" / "bundle-size-baseline.json"
    baseline = json.loads(baseline_path.read_text())
    for bundle in baseline["bundles"]:
        if bundle["path"] == "paperclips/dist/python-engineer.md":
            text = dist_path.read_text()
            bundle["bytes"] = len(text.encode("utf-8"))
            bundle["lines"] = text.count("\n")
            bundle["tokenEstimate"] = (bundle["bytes"] + 3) // 4
    baseline_path.write_text(json.dumps(baseline, indent=2) + "\n")

    errors = validate_instructions.validate(repo)

    assert any("generated bundle contains front matter" in error for error in errors)


def test_baseline_size_mismatch_fails(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    baseline_path = repo / "paperclips" / "bundle-size-baseline.json"
    baseline = json.loads(baseline_path.read_text())
    baseline["bundles"][0]["bytes"] += 1
    baseline_path.write_text(json.dumps(baseline, indent=2) + "\n")

    errors = validate_instructions.validate(repo)

    assert any("baseline byte mismatch" in error for error in errors)


def test_runbook_profile_requires_inline_rule(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    profiles_path = repo / "paperclips" / "instruction-profiles.yaml"
    profiles_path.write_text(
        profiles_path.read_text()
        + "\n  unsafe-runbook-only:\n"
        + "    fragments:\n"
        + "      - paperclips/fragments/shared/fragments/language.md\n"
        + "    runbooks:\n"
        + "      - paperclips/fragments/shared/fragments/phase-handoff.md\n"
    )

    errors = validate_instructions.validate(repo)

    assert any("has runbooks but does not require inline rules" in error for error in errors)
