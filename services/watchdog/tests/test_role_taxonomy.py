"""Tests for watchdog.role_taxonomy — classify() and drift detection."""

from __future__ import annotations

import os

import pytest

from gimle_watchdog.role_taxonomy import VALID_ROLE_CLASSES, classify


# All 20 entries from the spec §4.3 _ROLE_CLASS_RAW
_ALL_KNOWN_AGENTS = [
    ("CEO", "cto"),
    ("CTO", "cto"),
    ("CodeReviewer", "reviewer"),
    ("OpusArchitectReviewer", "reviewer"),
    ("PythonEngineer", "implementer"),
    ("MCPEngineer", "implementer"),
    ("InfraEngineer", "implementer"),
    ("BlockchainEngineer", "implementer"),
    ("QAEngineer", "qa"),
    ("ResearchAgent", "research"),
    ("TechnicalWriter", "writer"),
    ("SecurityAuditor", "reviewer"),
    ("CXCTO", "cto"),
    ("CXCodeReviewer", "reviewer"),
    ("CodexArchitectReviewer", "reviewer"),
    ("CXPythonEngineer", "implementer"),
    ("CXMCPEngineer", "implementer"),
    ("CXInfraEngineer", "implementer"),
    ("CXQAEngineer", "qa"),
    ("CXResearchAgent", "research"),
    ("CXTechnicalWriter", "writer"),
]


@pytest.mark.parametrize("name,expected_class", _ALL_KNOWN_AGENTS)
def test_classify_returns_role_class_for_each_known_agent(name: str, expected_class: str):
    assert classify(name) == expected_class


def test_classify_returns_none_for_unknown_agent():
    assert classify("UnknownAgent") is None
    assert classify("") is None
    assert classify("not-a-real-agent") is None


def test_classify_is_case_insensitive():
    assert classify("pythonengineer") == "implementer"
    assert classify("PYTHONENGINEER") == "implementer"
    assert classify("PythonEngineer") == "implementer"
    assert classify("cto") == "cto"
    assert classify("CTO") == "cto"


def test_role_class_values_are_subset_of_valid_set():
    for _, role_class in _ALL_KNOWN_AGENTS:
        assert role_class in VALID_ROLE_CLASSES, f"{role_class!r} not in VALID_ROLE_CLASSES"


@pytest.mark.requires_paperclip
def test_role_taxonomy_covers_all_hired_agents():
    """Live API check: every hired agent name must classify to a role class."""
    import httpx

    api_url = os.environ["PAPERCLIP_API_URL"]
    api_key = os.environ["PAPERCLIP_API_KEY"]
    company_id = os.environ["PAPERCLIP_COMPANY_ID"]

    resp = httpx.get(
        f"{api_url}/api/companies/{company_id}/agents",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=10.0,
    )
    resp.raise_for_status()
    agents = resp.json()
    unknown = [a["name"] for a in agents if classify(a["name"]) is None]
    assert unknown == [], (
        f"These hired agent names have no role-class mapping: {unknown}. "
        f"Add them to role_taxonomy._ROLE_CLASS_RAW."
    )
