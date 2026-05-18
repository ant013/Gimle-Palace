from __future__ import annotations

import socket
from urllib.parse import urlparse

import pytest


def ensure_reachable_neo4j_uri(uri: str) -> str:
    parsed = urlparse(uri)
    host = parsed.hostname
    port = parsed.port
    if host is None or port is None:
        pytest.skip(f"Invalid COMPOSE_NEO4J_URI for Neo4j integration: {uri}")

    try:
        with socket.create_connection((host, port), timeout=0.5):
            return uri
    except OSError as exc:
        pytest.skip(
            "COMPOSE_NEO4J_URI is set but Neo4j is unreachable "
            f"at {host}:{port} — skipping integration tests: {exc}"
        )
