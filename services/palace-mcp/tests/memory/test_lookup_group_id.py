"""Tasks 9, 9.5, 10: group_id scoping in lookup and MCP tool project param.

Updated for GIM-53: LookupRequest.group_id replaced by project param;
perform_lookup gains default_group_id positional arg.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from palace_mcp.memory.lookup import _build_query, perform_lookup
from palace_mcp.memory.schema import LookupRequest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _AsyncIter:
    """Minimal async iterator over a list of mock rows."""

    def __init__(self, rows: list[MagicMock]) -> None:
        self._iter = iter(rows)

    def __aiter__(self) -> _AsyncIter:
        return self

    async def __anext__(self) -> MagicMock:
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration


def _make_row(data: dict[str, Any]) -> MagicMock:
    row = MagicMock()
    row.data.return_value = data
    return row


def _make_driver(
    node_props: dict[str, Any],
    entity_type: str = "Issue",
    captured_queries: list[str] | None = None,
    captured_params: list[dict[str, Any]] | None = None,
) -> MagicMock:
    """Return a mock driver whose session.execute_read calls the real _read closure.

    project=None path: tx.run called twice (main query, count query).
    The LIST_PROJECT_SLUGS call is bypassed because project=None returns
    [default_group_id] immediately without querying the transaction.
    """
    extra: dict[str, Any] = {}
    if entity_type == "Issue":
        extra = {"assignee": None, "comments": []}
    elif entity_type == "Comment":
        extra = {"issue": None, "author": None}

    row = _make_row({"node": node_props, **extra})

    count_record = MagicMock()
    count_record.__getitem__ = MagicMock(side_effect=lambda k: 1)

    call_num: list[int] = [0]

    async def mock_run(query: str, **params: Any) -> Any:
        call_num[0] += 1
        if captured_queries is not None:
            captured_queries.append(query)
        if captured_params is not None:
            captured_params.append(params)
        if call_num[0] == 1:
            return _AsyncIter([row])
        m = MagicMock()
        m.single = AsyncMock(return_value=count_record)
        return m

    mock_tx = AsyncMock()
    mock_tx.run = mock_run

    async def fake_execute_read(fn: Any) -> Any:
        return await fn(mock_tx)

    mock_session = MagicMock()
    mock_session.execute_read = fake_execute_read
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    mock_driver = MagicMock()
    mock_driver.session.return_value = mock_session
    return mock_driver


# ---------------------------------------------------------------------------
# Task 9: LookupRequest.project replaces group_id
# ---------------------------------------------------------------------------


class TestLookupRequestProjectParam:
    def test_group_id_field_removed(self) -> None:
        with pytest.raises(ValidationError):
            LookupRequest(entity_type="Issue", group_id="project/test")  # type: ignore[call-arg]

    def test_project_none_accepted(self) -> None:
        req = LookupRequest(entity_type="Issue")
        assert req.project is None

    def test_project_string_accepted(self) -> None:
        req = LookupRequest(entity_type="Issue", project="gimle")
        assert req.project == "gimle"

    def test_project_list_accepted(self) -> None:
        req = LookupRequest(entity_type="Issue", project=["gimle", "medic"])
        assert req.project == ["gimle", "medic"]

    def test_build_query_includes_group_ids_in_clause(self) -> None:
        q = _build_query(
            "Issue",
            ["n.group_id IN $group_ids", "n.status = $status"],
            "source_updated_at",
            20,
        )
        assert "n.group_id IN $group_ids" in q


class TestPerformLookupGroupIdScoping:
    @pytest.mark.asyncio
    async def test_group_ids_passed_to_cypher(self) -> None:
        captured_queries: list[str] = []
        captured_params: list[dict[str, Any]] = []
        driver = _make_driver(
            {"id": "i1", "group_id": "project/test", "title": "T"},
            captured_queries=captured_queries,
            captured_params=captured_params,
        )
        req = LookupRequest(entity_type="Issue")  # project=None → uses default
        await perform_lookup(driver, req, "project/test")

        all_params = {k: v for d in captured_params for k, v in d.items()}
        assert "group_ids" in all_params, "group_ids not in Cypher params"
        assert all_params["group_ids"] == ["project/test"]
        assert any("n.group_id IN $group_ids" in q for q in captured_queries)


# ---------------------------------------------------------------------------
# Task 9.5: group_id stripped from response item properties
# ---------------------------------------------------------------------------


class TestPerformLookupStripsGroupId:
    @pytest.mark.asyncio
    async def test_group_id_absent_from_properties(self) -> None:
        driver = _make_driver(
            {"id": "a1", "group_id": "project/test", "name": "Bot"},
            entity_type="Agent",
        )
        req = LookupRequest(entity_type="Agent")
        resp = await perform_lookup(driver, req, "project/test")

        assert len(resp.items) == 1
        assert "group_id" not in resp.items[0].properties

    @pytest.mark.asyncio
    async def test_other_properties_preserved(self) -> None:
        driver = _make_driver(
            {"id": "a1", "group_id": "project/test", "name": "Bot", "role": "dev"},
            entity_type="Agent",
        )
        req = LookupRequest(entity_type="Agent")
        resp = await perform_lookup(driver, req, "project/test")

        props = resp.items[0].properties
        assert props["name"] == "Bot"
        assert props["role"] == "dev"
        assert props["id"] == "a1"


# ---------------------------------------------------------------------------
# Task 10: MCP tool resolves project → group_ids, falls back to server default
# ---------------------------------------------------------------------------


class TestMcpToolProjectParam:
    def test_set_default_group_id_importable(self) -> None:
        from palace_mcp.mcp_server import set_default_group_id

        set_default_group_id("project/custom")
        from palace_mcp import mcp_server

        assert mcp_server._default_group_id == "project/custom"
        set_default_group_id("project/gimle")

    @pytest.mark.asyncio
    async def test_palace_memory_lookup_passes_project_to_req(self) -> None:
        """project param is forwarded to LookupRequest.project."""
        captured_reqs: list[tuple[Any, LookupRequest, str]] = []

        async def fake_perform_lookup(
            driver: Any, req: LookupRequest, default_group_id: str
        ) -> Any:
            captured_reqs.append((driver, req, default_group_id))
            from palace_mcp.memory.schema import LookupResponse

            return LookupResponse(items=[], total_matched=0, query_ms=1)

        from palace_mcp import mcp_server
        from palace_mcp.mcp_server import palace_memory_lookup

        mcp_server._driver = MagicMock()
        with patch(
            "palace_mcp.mcp_server.perform_lookup", side_effect=fake_perform_lookup
        ):
            await palace_memory_lookup(entity_type="Issue", project="gimle")

        assert len(captured_reqs) == 1
        _, req, default_group_id = captured_reqs[0]
        assert req.project == "gimle"
        assert default_group_id == mcp_server._default_group_id
        mcp_server._driver = None

    @pytest.mark.asyncio
    async def test_palace_memory_lookup_uses_default_when_no_project(self) -> None:
        """When project is omitted, req.project is None and default_group_id is server default."""
        captured_reqs: list[tuple[Any, LookupRequest, str]] = []

        async def fake_perform_lookup(
            driver: Any, req: LookupRequest, default_group_id: str
        ) -> Any:
            captured_reqs.append((driver, req, default_group_id))
            from palace_mcp.memory.schema import LookupResponse

            return LookupResponse(items=[], total_matched=0, query_ms=1)

        from palace_mcp import mcp_server
        from palace_mcp.mcp_server import palace_memory_lookup, set_default_group_id

        set_default_group_id("project/gimle")
        mcp_server._driver = MagicMock()
        with patch(
            "palace_mcp.mcp_server.perform_lookup", side_effect=fake_perform_lookup
        ):
            await palace_memory_lookup(entity_type="Issue")

        _, req, default_group_id = captured_reqs[0]
        assert req.project is None
        assert default_group_id == "project/gimle"
        mcp_server._driver = None
