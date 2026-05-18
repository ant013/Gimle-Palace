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


PROFILE_NAMES = ["custom", "minimal", "research", "writer", "implementer", "qa", "reviewer", "cto"]


def test_all_8_profiles_exist():
    for name in PROFILE_NAMES:
        p = PROFILES_DIR / f"{name}.yaml"
        assert p.is_file(), f"missing profile: {p}"


def test_all_8_profiles_validate():
    from paperclips.scripts.profile_schema import load_profile
    for name in PROFILE_NAMES:
        p = PROFILES_DIR / f"{name}.yaml"
        data = load_profile(p)
        assert data["name"] == name


def test_custom_opts_out_of_universal():
    from paperclips.scripts.profile_schema import load_profile
    p = load_profile(PROFILES_DIR / "custom.yaml")
    assert p["inheritsUniversal"] is False
    assert p["includes"] == []


def test_minimal_inherits_universal_with_empty_includes():
    from paperclips.scripts.profile_schema import load_profile
    p = load_profile(PROFILES_DIR / "minimal.yaml")
    assert p["inheritsUniversal"] is True
    assert p["includes"] == []


def test_qa_extends_implementer():
    from paperclips.scripts.profile_schema import load_profile
    p = load_profile(PROFILES_DIR / "qa.yaml")
    assert p["extends"] == "implementer"


def test_cto_extends_reviewer():
    from paperclips.scripts.profile_schema import load_profile
    p = load_profile(PROFILES_DIR / "cto.yaml")
    assert p["extends"] == "reviewer"


def test_extends_chain_resolution_for_cto():
    from paperclips.scripts.profile_schema import load_all_profiles, resolve_extends_chain
    all_p = load_all_profiles(PROFILES_DIR)
    chain = resolve_extends_chain(all_p["cto"], all_p)
    assert [p["name"] for p in chain] == ["reviewer", "cto"]


def test_extends_chain_resolution_for_qa():
    from paperclips.scripts.profile_schema import load_all_profiles, resolve_extends_chain
    all_p = load_all_profiles(PROFILES_DIR)
    chain = resolve_extends_chain(all_p["qa"], all_p)
    assert [p["name"] for p in chain] == ["implementer", "qa"]
