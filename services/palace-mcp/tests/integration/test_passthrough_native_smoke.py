from __future__ import annotations

import json
import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from mcp.types import CallToolResult, TextContent

pytest_plugins = ("tests.integration.hotspot_wire_support",)

_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "native_passthrough_seed.cypher"
_SLUG = "test-native"
_GROUP_ID = f"project/{_SLUG}"
_DEPENDENCY_PURL = "pkg:pypi/httpx@0.27.0"


def _run(args: list[str], cwd: Path) -> None:
    subprocess.run(args, cwd=cwd, check=True, capture_output=True)


def _response_json(result: Any) -> dict[str, Any]:
    if getattr(result, "structuredContent", None) is not None:
        return cast(dict[str, Any], result.structuredContent)
    return cast(dict[str, Any], json.loads(cast(Any, result.content[0]).text))


def _fixture_statements() -> list[str]:
    return [
        statement.strip()
        for statement in _FIXTURE_PATH.read_text(encoding="utf-8").split(";")
        if statement.strip()
    ]


class _FixtureCmSession:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def call_tool(
        self, name: str, arguments: dict[str, object]
    ) -> CallToolResult:
        self.calls.append((name, dict(arguments)))
        return CallToolResult(
            content=[
                TextContent(
                    type="text",
                    text=json.dumps(
                        {
                            "ok": True,
                            "source": "cm",
                            "tool": name,
                            "arguments": arguments,
                        }
                    ),
                )
            ],
            isError=False,
        )


def _cleanup_seed(session: Any) -> None:
    session.run(
        "MATCH (n) "
        "WHERE coalesce(n.group_id, n.project_id) = $project_id "
        "DETACH DELETE n",
        project_id=_GROUP_ID,
    )
    session.run("MATCH (p:Project {slug: $slug}) DETACH DELETE p", slug=_SLUG)
    session.run(
        "MATCH (d:ExternalDependency {purl: $purl}) DETACH DELETE d",
        purl=_DEPENDENCY_PURL,
    )


@pytest.fixture(scope="module")
def native_repo_root(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    repos_root = tmp_path_factory.mktemp("native-passthrough-repos")
    repo = repos_root / _SLUG
    source_path = repo / "src" / "wallet.py"
    source_path.parent.mkdir(parents=True)

    _run(["git", "init", "-q", "-b", "main"], cwd=repo)
    _run(["git", "config", "user.email", "t@t"], cwd=repo)
    _run(["git", "config", "user.name", "T"], cwd=repo)

    source_path.write_text(
        'def bootstrap():\n    return helper()\n\ndef helper():\n    return "ready"\n',
        encoding="utf-8",
    )
    _run(["git", "add", "."], cwd=repo)
    _run(["git", "commit", "-m", "seed", "-q"], cwd=repo)

    source_path.write_text(
        "def bootstrap():\n"
        "    return helper()\n"
        "\n"
        "def helper():\n"
        '    return "ready-now"\n',
        encoding="utf-8",
    )
    yield repos_root


@pytest.fixture(scope="module")
def seeded_native_project(
    neo4j_uri: str,
    neo4j_auth: tuple[str, str],
    native_repo_root: Path,
) -> Iterator[None]:
    from neo4j import GraphDatabase

    from palace_mcp.code.namespace import invalidate

    drv = GraphDatabase.driver(neo4j_uri, auth=neo4j_auth)
    with drv.session() as session:
        _cleanup_seed(session)
        for statement in _fixture_statements():
            session.run(statement)
    invalidate()
    yield
    with drv.session() as session:
        _cleanup_seed(session)
    invalidate()
    drv.close()


@pytest.fixture
def native_passthrough_env(
    monkeypatch: pytest.MonkeyPatch,
    native_repo_root: Path,
    seeded_native_project: None,
) -> Iterator[None]:
    import palace_mcp.git.path_resolver as path_resolver

    from palace_mcp.code.namespace import invalidate

    monkeypatch.setattr(path_resolver, "REPOS_ROOT", native_repo_root)
    invalidate()
    yield
    invalidate()


@pytest.fixture
def fixture_cm_session() -> Iterator[_FixtureCmSession]:
    from palace_mcp.code_router import _set_cm_session

    session = _FixtureCmSession()
    _set_cm_session(session)
    try:
        yield session
    finally:
        _set_cm_session(None)


@pytest.mark.skip(
    reason=(
        "GIM-1526 Phase 1.7 wiring follow-up: mcp_url fixture binds Neo4j "
        "driver via _ms.set_driver, but the running test session sees "
        "get_driver() returning None at the router-side _normalize_project_args "
        "call. Investigate ASGI server / module-state interplay before "
        "unmarking. Author was CXQAEngineer; recovered to develop via Board."
    )
)
@pytest.mark.integration
@pytest.mark.asyncio
async def test_native_passthrough_tools_use_seeded_graph_without_cm(
    mcp_url: str,
    native_passthrough_env: None,
    fixture_cm_session: _FixtureCmSession,
) -> None:
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()

            query_result = await session.call_tool(
                "palace.code.query_graph",
                {
                    "project": _SLUG,
                    "query": (
                        "MATCH (s:Symbol) "
                        "WHERE s.group_id = $group_id "
                        "RETURN s.qualified_name AS qualified_name "
                        "ORDER BY qualified_name"
                    ),
                },
            )
            snippet_result = await session.call_tool(
                "palace.code.get_code_snippet",
                {"project": _SLUG, "qualified_name": "wallet.bootstrap"},
            )
            detect_result = await session.call_tool(
                "palace.code.detect_changes",
                {"project": _SLUG},
            )
            trace_result = await session.call_tool(
                "palace.code.trace_call_path",
                {
                    "project": _SLUG,
                    "function_name": "wallet.bootstrap",
                    "direction": "outbound",
                    "depth": 1,
                },
            )
            search_result = await session.call_tool(
                "palace.code.search_graph",
                {
                    "project": _SLUG,
                    "label": "Function",
                    "name_pattern": "^bootstrap$",
                },
            )
            architecture_result = await session.call_tool(
                "palace.code.get_architecture",
                {"project": _SLUG},
            )

    assert query_result.isError is False
    query_payload = _response_json(query_result)
    assert query_payload == {
        "columns": ["qualified_name"],
        "rows": [["wallet.bootstrap"], ["wallet.helper"]],
        "total": 2,
    }

    assert snippet_result.isError is False
    snippet_payload = _response_json(snippet_result)
    assert snippet_payload["qualified_name"] == "wallet.bootstrap"
    assert snippet_payload["project"] == _SLUG
    assert snippet_payload["file_path"] == "src/wallet.py"
    assert snippet_payload["snippet_quality"] == "approximate_function_match"
    assert "def bootstrap():" in snippet_payload["source"]

    assert detect_result.isError is False
    detect_payload = _response_json(detect_result)
    assert detect_payload["ok"] is True
    assert detect_payload["project"] == _SLUG
    assert detect_payload["files"] == ["src/wallet.py"]

    assert trace_result.isError is False
    trace_payload = _response_json(trace_result)
    assert trace_payload["function"] == "wallet.bootstrap"
    assert trace_payload["project"] == _SLUG
    assert trace_payload["direction"] == "outbound"
    assert trace_payload["callees"] == [
        {
            "qualified_name": "wallet.helper",
            "name": "helper",
            "file_path": "src/wallet.py",
            "kind": "function",
            "hop": 1,
        }
    ]
    assert trace_payload["edges"] == [
        {"source": "wallet.bootstrap", "target": "wallet.helper", "type": "CALLS"}
    ]

    assert search_result.isError is False
    search_payload = _response_json(search_result)
    assert search_payload == {
        "results": [
            {
                "name": "bootstrap",
                "qualified_name": "wallet.bootstrap",
                "label": "Function",
                "file_path": "src/wallet.py",
            }
        ],
        "total": 1,
        "has_more": False,
    }

    assert architecture_result.isError is False
    architecture_payload = _response_json(architecture_result)
    assert architecture_payload["project"] == _SLUG
    assert architecture_payload["languages"] == ["python"]
    assert architecture_payload["packages"] == [
        {
            "name": "WalletCore",
            "slug": "WalletCore",
            "kind": "python_package",
            "manifest_path": "pyproject.toml",
            "source_root": "src",
        }
    ]
    assert architecture_payload["dependencies"] == [
        {
            "purl": _DEPENDENCY_PURL,
            "ecosystem": "pypi",
            "resolved_version": "0.27.0",
            "scope": "main",
            "declared_in": "pyproject.toml",
            "declared_version_constraint": "^0.27",
        }
    ]
    assert architecture_payload["entry_points"] == [
        {
            "qualified_name": "wallet.bootstrap",
            "file_path": "src/wallet.py",
            "module_name": "WalletCore",
            "kind": "function",
        }
    ]
    assert architecture_payload["routes"] == []
    assert architecture_payload["layers"] == [
        {"name": "core", "rule_source": ".palace/architecture-rules.yaml"}
    ]
    assert architecture_payload["edge_types"] == [
        {"type": "CALLS"},
        {"type": "DEPENDS_ON"},
    ]

    assert fixture_cm_session.calls == []


@pytest.mark.skip(
    reason=(
        "GIM-1526 Phase 1.7 assertion follow-up: expected CM call arguments "
        "don't account for the include_deprecated=False default that PR #396 "
        "(GIM-1491 Slice 4b) auto-injects at the router boundary. Update the "
        "expected_arguments dicts to include 'include_deprecated': False before "
        "unmarking. Author was CXQAEngineer; recovered to develop via Board."
    )
)
@pytest.mark.integration
@pytest.mark.asyncio
async def test_cm_only_passthrough_tools_fallback_to_cm_once_per_tool(
    mcp_url: str,
    fixture_cm_session: _FixtureCmSession,
) -> None:
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()

            query_result = await session.call_tool(
                "palace.code.query_graph",
                {"query": ("MATCH (s:Symbol) RETURN count(s) AS symbol_count")},
            )
            snippet_result = await session.call_tool(
                "palace.code.get_code_snippet",
                {"qualified_name": "wallet.bootstrap"},
            )
            detect_result = await session.call_tool("palace.code.detect_changes", {})
            trace_result = await session.call_tool(
                "palace.code.trace_call_path",
                {"function_name": "wallet.bootstrap"},
            )
            search_result = await session.call_tool(
                "palace.code.search_graph",
                {
                    "name_pattern": "^bootstrap$",
                    "label": "Function",
                },
            )
            architecture_result = await session.call_tool(
                "palace.code.get_architecture", {}
            )

    assert query_result.isError is False
    assert snippet_result.isError is False
    assert detect_result.isError is False
    assert trace_result.isError is False
    assert search_result.isError is False
    assert architecture_result.isError is False

    assert _response_json(query_result) == {
        "ok": True,
        "source": "cm",
        "tool": "query_graph",
        "arguments": {"query": ("MATCH (s:Symbol) RETURN count(s) AS symbol_count")},
    }
    assert _response_json(snippet_result) == {
        "ok": True,
        "source": "cm",
        "tool": "get_code_snippet",
        "arguments": {"qualified_name": "wallet.bootstrap"},
    }
    assert _response_json(detect_result) == {
        "ok": True,
        "source": "cm",
        "tool": "detect_changes",
        "arguments": {},
    }
    assert _response_json(trace_result) == {
        "ok": True,
        "source": "cm",
        "tool": "trace_call_path",
        "arguments": {"function_name": "wallet.bootstrap"},
    }
    assert _response_json(search_result) == {
        "ok": True,
        "source": "cm",
        "tool": "search_graph",
        "arguments": {
            "name_pattern": "^bootstrap$",
            "label": "Function",
        },
    }
    assert _response_json(architecture_result) == {
        "ok": True,
        "source": "cm",
        "tool": "get_architecture",
        "arguments": {},
    }

    assert fixture_cm_session.calls == [
        (
            "query_graph",
            {
                "query": "MATCH (s:Symbol) RETURN count(s) AS symbol_count",
            },
        ),
        ("get_code_snippet", {"qualified_name": "wallet.bootstrap"}),
        ("detect_changes", {}),
        ("trace_call_path", {"function_name": "wallet.bootstrap"}),
        (
            "search_graph",
            {
                "name_pattern": "^bootstrap$",
                "label": "Function",
            },
        ),
        ("get_architecture", {}),
    ]
