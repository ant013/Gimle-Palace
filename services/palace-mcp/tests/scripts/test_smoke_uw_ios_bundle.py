from __future__ import annotations

import importlib.util
from pathlib import Path


_SCRIPT_PATH = (
    Path(__file__).parent.parent.parent / "scripts" / "smoke_uw_ios_bundle.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("_smoke_uw_ios_bundle", _SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def test_build_smoke_gate_verdict_green() -> None:
    module = _load_module()

    verdict = module.build_smoke_gate_verdict(
        {
            "state": "succeeded",
            "members_ok": 41,
            "runs": [{"slug": "uw-ios-app", "ok": True}],
        },
        {
            "occurrences": [{"path": "Sources/Foo.swift"}],
            "bundle_health": {
                "members_total": 41,
                "query_failed_slugs": [],
                "ingest_failed_slugs": [],
                "never_ingested_slugs": [],
            },
        },
    )

    assert verdict == {"ok": True, "errors": []}


def test_build_smoke_gate_verdict_red_collects_errors() -> None:
    module = _load_module()

    verdict = module.build_smoke_gate_verdict(
        {
            "state": "failed",
            "members_failed": 2,
            "members_ok": 39,
            "runs": [{"slug": "uw-ios-app", "ok": False}],
        },
        {
            "occurrences": [],
            "bundle_health": {
                "members_total": 40,
                "query_failed_slugs": ["uw-ios-app"],
                "ingest_failed_slugs": [],
                "never_ingested_slugs": [],
            },
        },
    )

    assert verdict["ok"] is False
    assert verdict["errors"] == [
        "ingest failed: members_failed=2, uw-ios-app_ok=False",
        "members_ok=39 < 40",
        "uw-ios-app is in failed runs",
        "occurrences_count=0 for 'EvmKit.Address'",
        "bundle_health.members_total=40 != 41",
        "uw-ios-app in query_failed_slugs",
    ]
