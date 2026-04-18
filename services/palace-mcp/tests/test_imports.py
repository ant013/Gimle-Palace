"""Import smoke tests.

Catches broken module-level imports (like API renames in graphiti-core)
at CI time rather than at container startup in production.

Added after GIM-48 hotfix: N+1a merge contained `OpenAIGenericClient`
reference that no longer exists in installed graphiti-core; container
crash-looped on startup because no test exercised the import chain.
"""

from __future__ import annotations

import inspect


def test_main_imports() -> None:
    """Importing palace_mcp.main must not raise."""
    from palace_mcp import main

    assert main is not None


def test_graphiti_client_imports() -> None:
    """Importing graphiti_client must resolve all external symbols."""
    from palace_mcp.graphiti_client import build_graphiti

    assert callable(build_graphiti)


def test_no_stale_graphiti_core_names_in_graphiti_client() -> None:
    """Catch graphiti-core API renames early (lesson from GIM-48 hotfix).

    These names existed in older graphiti-core versions but were removed
    or renamed. Keeping them would cause runtime ImportError at container
    startup even when unit tests with mocks pass.
    """
    from palace_mcp import graphiti_client

    source = inspect.getsource(graphiti_client)
    assert "OpenAIGenericClient" not in source, (
        "graphiti-core renamed OpenAIGenericClient to OpenAIClient; "
        "import path openai_generic_client no longer exists"
    )
    assert "openai_generic_client" not in source, (
        "module path graphiti_core.llm_client.openai_generic_client "
        "was removed; use graphiti_core.llm_client.openai_client"
    )


def test_build_graphiti_does_not_require_openai_api_key_env(
    monkeypatch,
) -> None:
    """build_graphiti() must not fail when OPENAI_API_KEY is unset.

    Graphiti() unconditionally instantiates a cross_encoder if one is not
    provided, which calls AsyncOpenAI() and reads OPENAI_API_KEY from env.
    We must pass our own cross_encoder backed by the same LLMConfig as
    llm_client so startup works against external Ollama / OpenAI-compat
    endpoints without leaking a dependency on OPENAI_API_KEY.

    Regression test for GIM-48 hotfix round 2.
    """
    from pydantic import SecretStr

    from palace_mcp.config import Settings
    from palace_mcp.graphiti_client import build_graphiti

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    settings = Settings(
        neo4j_uri="bolt://localhost:7687",
        neo4j_password=SecretStr("test"),
        embedding_base_url="http://localhost:11434/v1",
        embedding_api_key=SecretStr("placeholder"),
    )

    graphiti = build_graphiti(settings)
    assert graphiti is not None
