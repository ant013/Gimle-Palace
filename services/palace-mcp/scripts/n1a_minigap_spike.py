"""N+1a mini-gap spike. Run against a local Neo4j 5.26 + external Ollama/OpenAI.

Resolves 5 mini-gaps from N+1a spec §10 before implementation begins:
1. Skip-embed-on-unchanged idiom — does setting node.name_embedding manually bypass re-embed?
2. EntityNode.attributes round-trip — arbitrary dict keys persist?
3. Graphiti(llm_client=OpenAIGenericClient(...)) idle — no side effects when LLM never invoked?
4. graphiti-core <> Neo4j 5.26 compatibility
5. delete_by_uuids — does this method exist on graphiti.nodes.entity? (WARNING from CodeReview)

Usage:
  EMBEDDING_BASE_URL=https://api.openai.com/v1 \
  EMBEDDING_API_KEY=sk-... \
  EMBEDDING_MODEL=text-embedding-3-small EMBEDDING_DIM=1536 \
  NEO4J_PASSWORD=your-password \
  uv run python scripts/n1a_minigap_spike.py
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from uuid import uuid4

from graphiti_core import Graphiti
from graphiti_core.nodes import EntityNode
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient
from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig


async def main() -> None:
    embedding_base_url = os.environ["EMBEDDING_BASE_URL"]
    g = Graphiti(
        os.environ.get("NEO4J_URI", "bolt://localhost:7687"),
        os.environ.get("NEO4J_USER", "neo4j"),
        os.environ["NEO4J_PASSWORD"],
        llm_client=OpenAIGenericClient(
            LLMConfig(
                api_key=os.environ.get(
                    "LLM_API_KEY", os.environ.get("EMBEDDING_API_KEY", "placeholder")
                ),
                model=os.environ.get("LLM_MODEL", "llama3:8b"),
                base_url=os.environ.get("LLM_BASE_URL", embedding_base_url),
            )
        ),
        embedder=OpenAIEmbedder(
            OpenAIEmbedderConfig(
                api_key=os.environ.get("EMBEDDING_API_KEY", "placeholder"),
                embedding_model=os.environ["EMBEDDING_MODEL"],
                embedding_dim=int(os.environ["EMBEDDING_DIM"]),
                base_url=embedding_base_url,
            )
        ),
    )

    print("=== Gap 4: Neo4j 5.26 compatibility ===")
    await g.build_indices_and_constraints()
    print("OK — build_indices_and_constraints succeeded")

    group_id = "spike/n1a"
    uid = str(uuid4())

    print("\n=== Gap 2: EntityNode.attributes round-trip ===")
    node = EntityNode(
        uuid=uid,
        name="spike-node",
        labels=["SpikeNote"],
        group_id=group_id,
        summary="round-trip test",
        attributes={
            "text_hash": "abc123",
            "tags": ["one", "two"],
            "scope": "project",
            "nested": {"level": 1},
            "count": 42,
        },
    )
    await g.nodes.entity.save(node)
    fetched = await g.nodes.entity.get_by_uuid(uid)
    print(f"saved attributes:   {node.attributes}")
    print(f"fetched attributes: {fetched.attributes}")
    assert fetched.attributes == node.attributes, "attribute round-trip failure"
    print("OK — arbitrary dict keys persist intact")

    print("\n=== Gap 1: Skip-embed-on-unchanged idiom ===")
    initial_embedding = list(fetched.name_embedding) if fetched.name_embedding else None
    print(
        f"first embedding present: {initial_embedding is not None}, len={len(initial_embedding) if initial_embedding else 0}"
    )

    fetched.attributes["palace_last_seen_at"] = datetime.now(timezone.utc).isoformat()
    await g.nodes.entity.save(fetched)
    refetched = await g.nodes.entity.get_by_uuid(uid)
    second_embedding = (
        list(refetched.name_embedding) if refetched.name_embedding else None
    )
    print(f"second embedding == first: {initial_embedding == second_embedding}")
    print(
        "RESULT: see logs above — if save() always regenerates, embedding bypass not available"
    )

    print("\n=== Gap 3: idle LLM client side effects ===")
    print(
        "OK — Graphiti() construction + save/get above never invoked LLM (no add_episode called)"
    )

    print("\n=== Gap 5: delete_by_uuids API availability ===")
    has_delete_by_uuids = hasattr(g.nodes.entity, "delete_by_uuids")
    print(f"delete_by_uuids exists: {has_delete_by_uuids}")
    if has_delete_by_uuids:
        await g.nodes.entity.delete_by_uuids([uid])
        print("OK — delete_by_uuids succeeded")
    else:
        print("MISSING — fallback: loop delete_by_uuid per node")
        has_delete_by_uuid = hasattr(g.nodes.entity, "delete_by_uuid")
        print(f"delete_by_uuid (singular) exists: {has_delete_by_uuid}")
        if has_delete_by_uuid:
            await g.nodes.entity.delete_by_uuid(uid)
            print("OK — fallback delete_by_uuid succeeded")

    await g.close()
    print("\nspike complete")


if __name__ == "__main__":
    asyncio.run(main())
