"""PrimingDeps — dependency container for palace.memory.prime inner functions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from graphiti_core import Graphiti
from neo4j import AsyncDriver

from palace_mcp.config import Settings


@dataclass
class PrimingDeps:
    """Wraps lifespan globals for injection into pure prime functions.

    No paperclip_client field — paperclip API integration deferred to GIM-95b.
    v1 uses static instructions for in_progress_slices / backlog placeholders.
    """

    graphiti: Graphiti
    driver: AsyncDriver
    settings: Settings
    default_group_id: str
    role_prime_dir: Path  # resolved from settings.palace_git_workspace at construction
