"""Compose per-agent AGENTS.md from profile + role + custom_includes + overlays.

Per UAA spec §3, §5.2.1.

Composition order:
1. Universal layer (if profile.inheritsUniversal anywhere in extends chain)
2. Profile.includes from extends chain (deduplicated)
3. Custom includes (per-agent)
4. Role craft (role_source content)
5. Overlay blocks (appended last; from §6.7 apply_overlay)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# UAA rev2 DevOps#5 fix: strip Phase A intermediate-state sentinel from composed output.
# Sentinel lives in source craft files (paperclips/roles/*.md, roles-codex/*.md) as a
# guard against deploying slim crafts without compose. Now that compose engine works
# (Phase B), composed bundles are safe to deploy — strip the sentinel from output
# so imac-agents-deploy.sh verify step doesn't false-positive block.
PHASE_A_SENTINEL_RE = re.compile(
    r"^<!-- PHASE-A-ONLY:[^\n]*-->\s*\n?",
    re.MULTILINE,
)

# Make `paperclips.scripts.profile_schema` importable from this module.
_THIS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _THIS_DIR.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from paperclips.scripts.profile_schema import (
    load_all_profiles,
    resolve_extends_chain,
)

UNIVERSAL_FRAGMENTS = [
    "universal/karpathy.md",
    "universal/wake-and-handoff-basics.md",
    "universal/escalation-board.md",
]


def _read_fragment(fragments_dir: Path, rel_path: str) -> str:
    """Read fragment by 'subdir/file.md' relative path.

    rev2 Security C-1/C-2/C-3 fix: reject path traversal via .. segments or
    absolute path components. Resolved file MUST live under fragments_dir.
    """
    # Reject obvious traversal patterns up front
    if rel_path.startswith("/"):
        raise ValueError(f"fragment path must be relative, got absolute: {rel_path!r}")
    parts = rel_path.split("/")
    if any(part in ("..", "") for part in parts):
        raise ValueError(f"fragment path contains traversal segment: {rel_path!r}")
    p = (fragments_dir / rel_path).resolve()
    base = fragments_dir.resolve()
    # Defense-in-depth: even after .. rejection, verify resolved path stays under base.
    try:
        p.relative_to(base)
    except ValueError:
        raise ValueError(
            f"fragment path escapes fragments_dir: {rel_path!r} → {p}",
        )
    if not p.is_file():
        raise FileNotFoundError(f"fragment not found: {p}")
    return p.read_text()


def compose(
    *,
    profile_name: str,
    profiles_dir: Path,
    fragments_dir: Path,
    role_source_text: str,
    custom_includes: list[str],
    overlay_blocks: list[str],
) -> str:
    """Compose final AGENTS.md content.

    Args:
        profile_name: profile to look up in profiles_dir.
        profiles_dir: directory containing *.yaml profile definitions.
        fragments_dir: root for include path resolution (e.g.
                       paperclips/fragments/shared/fragments).
        role_source_text: contents of the agent's craft file (slim role .md).
        custom_includes: per-agent extra fragment paths.
        overlay_blocks: project overlay contents to append last.

    Returns:
        Composed AGENTS.md as a single string.
    """
    all_profiles = load_all_profiles(profiles_dir)
    if profile_name not in all_profiles:
        # Phase B back-compat: legacy/synthetic role files may declare profile names
        # that aren't in the new §5.1 vocabulary (e.g. "core", "task-start", etc.).
        # Fall back to "minimal" (universal layer only) with a stderr warning.
        # Phase E/F/G migrations will rewrite manifests to use new profile names.
        print(
            f"  WARN: unknown profile {profile_name!r}; available: {sorted(all_profiles)}; "
            f"falling back to 'minimal'",
            file=sys.stderr,
        )
        # rev2 DevOps #1/#4: deterministic fallback order (sorted, not filesystem-glob)
        profile_name = "minimal" if "minimal" in all_profiles else next(iter(sorted(all_profiles)))

    profile = all_profiles[profile_name]
    chain = resolve_extends_chain(profile, all_profiles)

    sections: list[str] = []

    # 1. Universal layer (once, if any profile in chain claims it)
    inherits_universal = any(p["inheritsUniversal"] for p in chain)
    if inherits_universal:
        for u in UNIVERSAL_FRAGMENTS:
            sections.append(_read_fragment(fragments_dir, u))

    # 2. Profile.includes from chain, deduplicated
    seen: set[str] = set()
    for p in chain:
        for inc in p["includes"]:
            if inc in seen:
                print(
                    f"  dedup applied: {inc} (already included earlier in extends-chain)",
                    file=sys.stderr,
                )
                continue
            seen.add(inc)
            sections.append(_read_fragment(fragments_dir, inc))

    # 3. Custom includes (per-agent)
    for inc in custom_includes:
        if inc in seen:
            print(
                f"  dedup applied: {inc} (already in profile)",
                file=sys.stderr,
            )
            continue
        seen.add(inc)
        sections.append(_read_fragment(fragments_dir, inc))

    # 4. Role craft (with Phase A sentinel stripped — see PHASE_A_SENTINEL_RE comment)
    role_text_clean = PHASE_A_SENTINEL_RE.sub("", role_source_text)
    sections.append(role_text_clean)

    # 5. Overlay blocks
    for ov in overlay_blocks:
        sections.append(ov)

    return "\n\n".join(sections) + "\n"
