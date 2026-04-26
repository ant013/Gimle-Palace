"""palace.memory.prime — per-role agent priming module."""

from palace_mcp.memory.prime.budget import apply_budget, estimate_tokens
from palace_mcp.memory.prime.core import detect_slice_id, render_universal_core
from palace_mcp.memory.prime.deps import PrimingDeps
from palace_mcp.memory.prime.roles import render_role_extras

__all__ = [
    "PrimingDeps",
    "apply_budget",
    "detect_slice_id",
    "estimate_tokens",
    "render_role_extras",
    "render_universal_core",
]
