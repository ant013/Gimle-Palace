"""Phase B: profile YAMLs load and validate."""

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
PROFILES_DIR = REPO / "paperclips" / "fragments" / "profiles"


def test_load_profile_returns_dict():
    from paperclips.scripts.profile_schema import load_profile
    p = PROFILES_DIR / "implementer.yaml"
    if not p.exists():
        pytest.skip("profile yaml not yet created — Tasks 2-9")
    data = load_profile(p)
    assert isinstance(data, dict)
    assert data["name"] == "implementer"
    assert data["schemaVersion"] == 2
    assert "includes" in data
    assert isinstance(data["includes"], list)


def test_validate_profile_rejects_missing_name():
    from paperclips.scripts.profile_schema import ProfileSchemaError, validate_profile
    bad = {"schemaVersion": 2, "includes": []}
    with pytest.raises(ProfileSchemaError, match="name"):
        validate_profile(bad)


def test_validate_profile_rejects_wrong_version():
    from paperclips.scripts.profile_schema import ProfileSchemaError, validate_profile
    bad = {"schemaVersion": 1, "name": "implementer", "includes": []}
    with pytest.raises(ProfileSchemaError, match="schemaVersion"):
        validate_profile(bad)


def test_validate_profile_rejects_unknown_keys():
    from paperclips.scripts.profile_schema import ProfileSchemaError, validate_profile
    bad = {"schemaVersion": 2, "name": "x", "includes": [], "extraField": "nope"}
    with pytest.raises(ProfileSchemaError, match="unknown"):
        validate_profile(bad)


def test_validate_profile_default_inheritsUniversal():
    from paperclips.scripts.profile_schema import validate_profile
    p = {"schemaVersion": 2, "name": "x", "includes": []}
    out = validate_profile(p)
    assert out["inheritsUniversal"] is True


def test_validate_profile_rejects_bare_filename_in_includes():
    from paperclips.scripts.profile_schema import ProfileSchemaError, validate_profile
    bad = {"schemaVersion": 2, "name": "x", "includes": ["bare.md"]}
    with pytest.raises(ProfileSchemaError, match="subdir/file"):
        validate_profile(bad)


def test_resolve_extends_chain_returns_base_first():
    from paperclips.scripts.profile_schema import resolve_extends_chain
    a = {"name": "a", "extends": None, "includes": [], "inheritsUniversal": True}
    b = {"name": "b", "extends": "a", "includes": [], "inheritsUniversal": True}
    c = {"name": "c", "extends": "b", "includes": [], "inheritsUniversal": True}
    chain = resolve_extends_chain(c, {"a": a, "b": b, "c": c})
    assert [p["name"] for p in chain] == ["a", "b", "c"]


def test_resolve_extends_detects_cycle():
    from paperclips.scripts.profile_schema import ProfileSchemaError, resolve_extends_chain
    a = {"name": "a", "extends": "b", "includes": [], "inheritsUniversal": True}
    b = {"name": "b", "extends": "a", "includes": [], "inheritsUniversal": True}
    with pytest.raises(ProfileSchemaError, match="cycle"):
        resolve_extends_chain(b, {"a": a, "b": b})
