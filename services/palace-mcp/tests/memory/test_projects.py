"""Unit tests for palace_mcp.memory.projects — resolve_group_ids."""

from __future__ import annotations

import pytest

from palace_mcp.memory.projects import UnknownProjectError, resolve_group_ids


class _FakeTx:
    def __init__(self, slugs: list[str]) -> None:
        self._slugs = slugs

    async def run(self, query: str, **params: object) -> object:
        class _R:
            def __init__(s, rows: list[dict[str, str]]) -> None:
                s._rows = rows

            def __aiter__(s) -> object:
                s._i = iter(s._rows)
                return s

            async def __anext__(s) -> dict[str, str]:
                try:
                    return next(s._i)
                except StopIteration:
                    raise StopAsyncIteration

        return _R([{"slug": sl} for sl in self._slugs])


@pytest.mark.asyncio
async def test_resolve_none_returns_default() -> None:
    tx = _FakeTx(["gimle"])
    out = await resolve_group_ids(tx, None, default_group_id="project/gimle")
    assert out == ["project/gimle"]


@pytest.mark.asyncio
async def test_resolve_star_returns_all() -> None:
    tx = _FakeTx(["gimle", "medic"])
    out = await resolve_group_ids(tx, "*", default_group_id="project/gimle")
    assert out == ["project/gimle", "project/medic"]


@pytest.mark.asyncio
async def test_resolve_single_validates_existence() -> None:
    tx = _FakeTx(["gimle"])
    with pytest.raises(UnknownProjectError, match="medic"):
        await resolve_group_ids(tx, "medic", default_group_id="project/gimle")


@pytest.mark.asyncio
async def test_resolve_list_validates_each() -> None:
    tx = _FakeTx(["gimle"])
    with pytest.raises(UnknownProjectError, match="medic, other"):
        await resolve_group_ids(tx, ["gimle", "medic", "other"], default_group_id="project/gimle")


@pytest.mark.asyncio
async def test_resolve_list_ok() -> None:
    tx = _FakeTx(["gimle", "medic"])
    out = await resolve_group_ids(tx, ["gimle", "medic"], default_group_id="project/gimle")
    assert out == ["project/gimle", "project/medic"]


@pytest.mark.asyncio
async def test_resolve_wrong_type_raises_typeerror() -> None:
    tx = _FakeTx(["gimle"])
    with pytest.raises(TypeError, match="project must be"):
        await resolve_group_ids(tx, 42, default_group_id="project/gimle")  # type: ignore[arg-type]
