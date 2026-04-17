"""Tests for config.py — verify SecretStr masking and env var loading."""

import pytest
from pydantic import ValidationError

from palace_mcp.config import IngestSettings, Settings


def test_settings_loads_from_env(monkeypatch):
    monkeypatch.setenv("NEO4J_PASSWORD", "s3cr3t")
    s = Settings()
    assert s.neo4j_uri == "bolt://neo4j:7687"
    # get_secret_value() returns the real value
    assert s.neo4j_password.get_secret_value() == "s3cr3t"


def test_settings_neo4j_uri_override(monkeypatch):
    monkeypatch.setenv("NEO4J_URI", "bolt://custom:7687")
    monkeypatch.setenv("NEO4J_PASSWORD", "pw")
    s = Settings()
    assert s.neo4j_uri == "bolt://custom:7687"


def test_settings_password_masked_in_repr(monkeypatch):
    monkeypatch.setenv("NEO4J_PASSWORD", "s3cr3t")
    s = Settings()
    rep = repr(s)
    assert "s3cr3t" not in rep
    assert "**********" in rep


def test_settings_missing_password_raises(monkeypatch):
    monkeypatch.delenv("NEO4J_PASSWORD", raising=False)
    with pytest.raises(ValidationError):
        Settings()


def test_ingest_settings_loads_all_fields(monkeypatch):
    monkeypatch.setenv("NEO4J_PASSWORD", "neo_pw")
    monkeypatch.setenv("PAPERCLIP_API_URL", "https://api.example.com")
    monkeypatch.setenv("PAPERCLIP_INGEST_API_KEY", "key-abc")
    monkeypatch.setenv("PAPERCLIP_COMPANY_ID", "co-123")
    s = IngestSettings()
    assert s.paperclip_api_url == "https://api.example.com"
    assert s.paperclip_ingest_api_key.get_secret_value() == "key-abc"
    assert s.paperclip_company_id == "co-123"


def test_ingest_settings_api_key_masked_in_repr(monkeypatch):
    monkeypatch.setenv("NEO4J_PASSWORD", "neo_pw")
    monkeypatch.setenv("PAPERCLIP_API_URL", "https://api.example.com")
    monkeypatch.setenv("PAPERCLIP_INGEST_API_KEY", "secret-key")
    monkeypatch.setenv("PAPERCLIP_COMPANY_ID", "co-123")
    s = IngestSettings()
    rep = repr(s)
    assert "secret-key" not in rep
    assert "neo_pw" not in rep


def test_ingest_settings_missing_required_raises(monkeypatch):
    monkeypatch.setenv("NEO4J_PASSWORD", "pw")
    monkeypatch.delenv("PAPERCLIP_API_URL", raising=False)
    monkeypatch.delenv("PAPERCLIP_INGEST_API_KEY", raising=False)
    monkeypatch.delenv("PAPERCLIP_COMPANY_ID", raising=False)
    with pytest.raises(ValidationError):
        IngestSettings()
