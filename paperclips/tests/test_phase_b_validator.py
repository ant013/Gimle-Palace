"""Phase B: validate_manifest rejects host-local data per spec §6.2."""
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
FIX = REPO / "paperclips" / "tests" / "fixtures" / "phase_b"


def test_clean_manifest_passes():
    from paperclips.scripts.validate_manifest import validate_manifest
    validate_manifest(FIX / "manifest_clean.yaml")


def test_uuid_in_manifest_rejected():
    from paperclips.scripts.validate_manifest import (
        ManifestValidationError,
        validate_manifest,
    )
    with pytest.raises(ManifestValidationError, match="UUID"):
        validate_manifest(FIX / "manifest_with_uuid.yaml")


def test_absolute_path_rejected():
    from paperclips.scripts.validate_manifest import (
        ManifestValidationError,
        validate_manifest,
    )
    with pytest.raises(ManifestValidationError, match="absolute path"):
        validate_manifest(FIX / "manifest_with_abs_path.yaml")


def test_telegram_plugin_id_rejected():
    from paperclips.scripts.validate_manifest import (
        ManifestValidationError,
        validate_manifest,
    )
    with pytest.raises(ManifestValidationError, match="telegram_plugin_id"):
        validate_manifest(FIX / "manifest_with_telegram_id.yaml")


def test_template_reference_allowed_in_clean_manifest():
    """{{template.refs}} are explicitly allowed and resolved at build time."""
    from paperclips.scripts.validate_manifest import validate_manifest
    # Clean fixture has no template refs; verify another scenario by constructing a manifest with refs.
    tmp = FIX / "_tmp_template.yaml"
    tmp.write_text("""\
schemaVersion: 2
project:
  key: x
  display_name: X
  issue_prefix: X
  integration_branch: main
  specs_dir: docs/specs
  plans_dir: docs/plans
mcp:
  service_name: x
  tool_namespace: x
  base_required: [codebase-memory]
overlay_marker: "{{bindings.company_id}} at {{paths.production_checkout}}"
agents: []
""")
    try:
        validate_manifest(tmp)
    finally:
        tmp.unlink()
