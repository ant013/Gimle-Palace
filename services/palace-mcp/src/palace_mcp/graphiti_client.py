"""Graphiti instance factory.

Constructs a graphiti-core Graphiti client from IngestSettings using
OpenAIClient + OpenAIEmbedder against an OpenAI-compat endpoint
(works for external Ollama, Alibaba DashScope, OpenAI, Voyage, Cohere).

LLM client is required by Graphiti() constructor but never invoked in N+1a
(structured ingest via add_triplet bypasses LLM extraction entirely).
"""

from __future__ import annotations

from graphiti_core import Graphiti
from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.llm_client.openai_client import OpenAIClient

from palace_mcp.config import IngestSettings, Settings


def build_graphiti(settings: IngestSettings | Settings) -> Graphiti:
    """Build a Graphiti instance from settings.

    Caller is responsible for ``await graphiti.close()`` when done.
    """
    llm_client = OpenAIClient(
        config=LLMConfig(
            api_key=settings.effective_llm_api_key.get_secret_value(),
            model=settings.llm_model,
            base_url=settings.effective_llm_base_url,
        )
    )
    embedder = OpenAIEmbedder(
        config=OpenAIEmbedderConfig(
            api_key=settings.embedding_api_key.get_secret_value(),
            embedding_model=settings.embedding_model,
            embedding_dim=settings.embedding_dim,
            base_url=settings.embedding_base_url,
        )
    )
    return Graphiti(
        settings.neo4j_uri,
        "neo4j",
        settings.neo4j_password.get_secret_value(),
        llm_client=llm_client,
        embedder=embedder,
    )
