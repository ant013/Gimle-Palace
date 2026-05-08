"""Pydantic models for crypto_domain_model extractor (GIM-239)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class CryptoFinding(BaseModel):
    """A single crypto-domain finding emitted by semgrep and stored in Neo4j."""

    model_config = ConfigDict(frozen=True)

    project_id: str
    kind: str
    severity: str
    file: str
    start_line: int
    end_line: int
    message: str
    run_id: str
