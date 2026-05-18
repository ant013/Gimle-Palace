"""Tests for PaperclipClient.list_companies()."""

from __future__ import annotations

import pytest

from gimle_watchdog import paperclip as pc
from gimle_watchdog.paperclip import PaperclipClient, PaperclipError


async def _noop_sleep(_: float) -> None:
    """Drop-in async no-op replacement for retry backoff in tests."""


@pytest.mark.asyncio
async def test_list_companies_returns_active_only(mock_paperclip) -> None:
    """Archived companies are filtered out client-side."""

    base_url, state = mock_paperclip
    state.companies = [
        {"id": "uuid-1", "name": "Gimle", "archived": False},
        {"id": "uuid-2", "name": "OldCo", "archived": True},
        {"id": "uuid-3", "name": "Trading", "archived": False},
    ]
    client = PaperclipClient(base_url=base_url, api_key="test")
    try:
        companies = await client.list_companies()
    finally:
        await client.aclose()
    assert {company["id"] for company in companies} == {"uuid-1", "uuid-3"}


@pytest.mark.asyncio
async def test_list_companies_raises_on_connect_error() -> None:
    """Transport failures must propagate as PaperclipError; never silent []."""

    original_sleep = pc._sleep
    pc._sleep = _noop_sleep
    client = PaperclipClient(base_url="http://127.0.0.1:1", api_key="test")
    try:
        with pytest.raises(PaperclipError, match="exhausted"):
            await client.list_companies()
    finally:
        pc._sleep = original_sleep
        await client.aclose()
