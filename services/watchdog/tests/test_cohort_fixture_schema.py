"""Validate the structure of gim255_cohort.json. Real data is operator-supplied."""

from __future__ import annotations

import json
import uuid
from pathlib import Path


_FIXTURE = Path(__file__).parent / "fixtures" / "gim255_cohort.json"


def test_fixture_has_required_schema() -> None:
    data = json.loads(_FIXTURE.read_text())
    assert isinstance(data["paperclip_issue_ids"], list)
    assert len(data["paperclip_issue_ids"]) == 52
    assert all(_is_uuid(item) for item in data["paperclip_issue_ids"])

    assert isinstance(data["issue_numbers"], list)
    assert len(data["issue_numbers"]) == len(data["paperclip_issue_ids"])
    assert all(isinstance(number, int) for number in data["issue_numbers"])

    assert isinstance(data["comment_ids"], list)
    assert len(data["comment_ids"]) == 379
    assert all(_is_uuid(item) for item in data["comment_ids"])

    assert data["posted_at_window"]["from"].endswith("Z")
    assert data["posted_at_window"]["to"].endswith("Z")
    assert isinstance(data["comment_markers"], list)
    assert all(_is_uuid(item) for item in data["author_agent_ids"])
    assert all(isinstance(item, str) and item for item in data["author_user_ids"])
    assert data["author_agent_ids"] or data["author_user_ids"]


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
        return True
    except (ValueError, TypeError):
        return False
