"""Role taxonomy — casefold-normalized mapping from agent name to role class."""

from __future__ import annotations

_ROLE_CLASS_RAW: dict[str, str] = {
    # Claude team
    "CEO": "cto",
    "CTO": "cto",
    "CodeReviewer": "reviewer",
    "OpusArchitectReviewer": "reviewer",
    "PythonEngineer": "implementer",
    "MCPEngineer": "implementer",
    "InfraEngineer": "implementer",
    "BlockchainEngineer": "implementer",
    "QAEngineer": "qa",
    "ResearchAgent": "research",
    "TechnicalWriter": "writer",
    "SecurityAuditor": "reviewer",
    # CX team
    "CXCTO": "cto",
    "CXCodeReviewer": "reviewer",
    "CodexArchitectReviewer": "reviewer",
    "CXPythonEngineer": "implementer",
    "CXMCPEngineer": "implementer",
    "CXInfraEngineer": "implementer",
    "CXQAEngineer": "qa",
    "CXResearchAgent": "research",
    "CXTechnicalWriter": "writer",
}

_ROLE_CLASS: dict[str, str] = {k.casefold(): v for k, v in _ROLE_CLASS_RAW.items()}

VALID_ROLE_CLASSES: frozenset[str] = frozenset(
    {"cto", "reviewer", "implementer", "qa", "research", "writer"}
)


def classify(agent_name: str) -> str | None:
    """Return role class for agent_name, or None if unknown. Case-insensitive."""
    return _ROLE_CLASS.get(agent_name.casefold())
