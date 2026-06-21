"""Unit tests for palace_mcp.memory.projects — resolve_group_ids."""

from __future__ import annotations

import pytest

from palace_mcp.memory.cypher import LIST_PROJECT_SLUGS, LOOKUP_PROJECT_NAMESPACE
from palace_mcp.memory.projects import UnknownProjectError, resolve_group_ids


def _project(slug: str, *, cm_project_name: str | None = None) -> dict[str, str | None]:
    return {"slug": slug, "cm_project_name": cm_project_name}


class _FakeResult:
    def __init__(
        self,
        *,
        rows: list[dict[str, str]] | None = None,
        single_row: dict[str, str | None] | None = None,
    ) -> None:
        self._rows = rows or []
        self._single_row = single_row

    def __aiter__(self) -> object:
        self._i = iter(self._rows)
        return self

    async def __anext__(self) -> dict[str, str]:
        try:
            return next(self._i)
        except StopIteration:
            raise StopAsyncIteration

    async def single(self) -> dict[str, str | None] | None:
        return self._single_row


class _FakeTx:
    def __init__(self, projects: list[dict[str, str | None]]) -> None:
        self._projects = projects

    async def run(self, query: str, **params: object) -> object:
        if query == LIST_PROJECT_SLUGS:
            return _FakeResult(
                rows=[
                    {"slug": project["slug"]}
                    for project in self._projects
                    if project["slug"]
                ]
            )

        if query == LOOKUP_PROJECT_NAMESPACE:
            value = params["value"]
            slug_match = next(
                (project for project in self._projects if project["slug"] == value),
                None,
            )
            if slug_match is not None:
                return _FakeResult(single_row=slug_match)
            cm_match = next(
                (
                    project
                    for project in self._projects
                    if project["cm_project_name"] == value
                ),
                None,
            )
            return _FakeResult(single_row=cm_match)

        raise AssertionError(f"unexpected query: {query}")


@pytest.mark.asyncio
async def test_resolve_none_returns_default() -> None:
    tx = _FakeTx([_project("gimle")])
    out = await resolve_group_ids(tx, None, default_group_id="project/gimle")
    assert out == ["project/gimle"]


@pytest.mark.asyncio
async def test_resolve_star_returns_all() -> None:
    tx = _FakeTx([_project("gimle"), _project("medic")])
    out = await resolve_group_ids(tx, "*", default_group_id="project/gimle")
    assert out == ["project/gimle", "project/medic"]


@pytest.mark.asyncio
async def test_resolve_single_validates_existence() -> None:
    tx = _FakeTx([_project("gimle")])
    with pytest.raises(UnknownProjectError, match="medic"):
        await resolve_group_ids(tx, "medic", default_group_id="project/gimle")


@pytest.mark.asyncio
async def test_resolve_list_validates_each() -> None:
    tx = _FakeTx([_project("gimle")])
    with pytest.raises(UnknownProjectError, match="medic, other"):
        await resolve_group_ids(
            tx, ["gimle", "medic", "other"], default_group_id="project/gimle"
        )


@pytest.mark.asyncio
async def test_resolve_list_ok() -> None:
    tx = _FakeTx([_project("gimle"), _project("medic")])
    out = await resolve_group_ids(
        tx, ["gimle", "medic"], default_group_id="project/gimle"
    )
    assert out == ["project/gimle", "project/medic"]


@pytest.mark.asyncio
async def test_resolve_wrong_type_raises_typeerror() -> None:
    tx = _FakeTx([_project("gimle")])
    with pytest.raises(TypeError, match="project must be"):
        await resolve_group_ids(tx, 42, default_group_id="project/gimle")  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_resolve_single_accepts_cm_project_name() -> None:
    tx = _FakeTx([_project("uw-ios-app", cm_project_name="repos-ios-app")])
    out = await resolve_group_ids(
        tx,
        "repos-ios-app",
        default_group_id="project/gimle",
    )
    assert out == ["project/uw-ios-app"]


@pytest.mark.asyncio
async def test_resolve_list_canonicalizes_cm_project_names() -> None:
    tx = _FakeTx(
        [
            _project("gimle", cm_project_name="repos-gimle"),
            _project("uw-ios-app", cm_project_name="repos-ios-app"),
        ]
    )
    out = await resolve_group_ids(
        tx,
        ["gimle", "repos-ios-app"],
        default_group_id="project/gimle",
    )
    assert out == ["project/gimle", "project/uw-ios-app"]
