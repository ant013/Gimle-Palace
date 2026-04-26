"""Role extras dispatcher for palace.memory.prime.

Task 4: reads role-prime/{role}.md from fragments submodule,
substitutes {{ placeholders }} for operator role, returns stubs for others.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from palace_mcp.git.command import SAFE_ENV
from palace_mcp.memory.prime.deps import PrimingDeps

logger = logging.getLogger(__name__)

VALID_ROLES: frozenset[str] = frozenset(
    {
        "operator",
        "cto",
        "codereviewer",
        "pythonengineer",
        "opusarchitectreviewer",
        "qaengineer",
    }
)


async def _fetch_recent_commits(workspace: str) -> str:
    """Run git log --oneline -5 origin/develop; return output or placeholder."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "git",
            "log",
            "--oneline",
            "-5",
            "origin/develop",
            cwd=workspace,
            env=SAFE_ENV,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=2.0)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            return "(git log timed out)"

        out = stdout.decode().strip()
        return out if out else "(no commits found)"
    except Exception:
        logger.warning("prime.roles: failed to fetch recent commits", exc_info=True)
        return "(git log unavailable)"


def _read_role_file(role_prime_dir: Path, role: str) -> str | None:
    """Read role-prime/{role}.md; return content or None if not found."""
    role_file = role_prime_dir / f"{role}.md"
    try:
        return role_file.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except Exception:
        logger.warning("prime.roles: failed to read %s", role_file, exc_info=True)
        return None


def _substitute_static_placeholders(content: str, deps: PrimingDeps) -> str:
    """Replace settings-derived placeholders synchronously."""
    content = content.replace(
        "{{ paperclip_api_url }}", deps.settings.paperclip_api_url
    )
    content = content.replace("{{ git_workspace }}", deps.settings.palace_git_workspace)
    return content


def _substitute_static_instructions(content: str) -> str:
    """Replace paperclip API placeholders with static lookup instructions (v1)."""
    content = content.replace(
        "{{ in_progress_slices }}",
        "Run `palace.memory.lookup(entity_type='Issue', filters={'status': 'in_progress'})` "
        "to see in-flight slices (paperclip API integration in GIM-95b).",
    )
    content = content.replace(
        "{{ backlog_high_priority }}",
        "Run `palace.memory.lookup(entity_type='Issue', filters={'status': 'backlog', 'priority': 'high'})` "
        "to see high-priority backlog (paperclip API integration in GIM-95b).",
    )
    return content


async def render_role_extras(role: str, deps: PrimingDeps) -> str:
    """Render role-specific extras section.

    For 'operator': full content from operator.md with placeholder substitution.
    For other valid roles: stub content with minimal useful-tools list.
    Unknown role: raises ValueError.
    """
    if role not in VALID_ROLES:
        raise ValueError(f"Unknown role {role!r}. Valid roles: {sorted(VALID_ROLES)}")

    raw = _read_role_file(deps.role_prime_dir, role)

    if raw is None:
        # Fragment file not present (expected until GIM-95b for non-operator roles)
        return (
            f"## {role} role context (v1 stub — full content in GIM-95b)\n\n"
            f"GIM-95b ships {role}-specific extras. Until that slice merges, refer to\n"
            f"your role file (`paperclips/dist/{role}.md`) for primary discipline.\n\n"
            "Useful tools (call when investigating):\n"
            '- palace.code.search_graph(name_pattern="...", project="repos-gimle")\n'
            '- palace.code.trace_call_path(function_name="...", project="repos-gimle", mode="callers")\n'
            '- palace.code.get_code_snippet(qualified_name="...", project="repos-gimle")\n'
            '- palace.memory.lookup(entity_type="Decision", filters={"slice_ref":"..."}, limit=5)\n'
            "- palace.memory.decide(...) — record verdict at end of phase\n"
            "- palace.memory.health() — check graph state\n"
        )

    # Substitute async placeholders
    if role == "operator":
        recent_commits = await _fetch_recent_commits(deps.settings.palace_git_workspace)
        raw = raw.replace("{{ recent_develop_commits }}", recent_commits)

    # Substitute static placeholders
    raw = _substitute_static_placeholders(raw, deps)
    raw = _substitute_static_instructions(raw)

    return raw
