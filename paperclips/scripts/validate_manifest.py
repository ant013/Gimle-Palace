"""Validate that a committed manifest is path-free and UUID-free per UAA spec §6.2.

Rejects:
- literal UUIDs (regex `[0-9a-f]{8}-[0-9a-f]{4}-…`)
- absolute paths starting with /Users/, /home/, /private/, /var/, /opt/
- forbidden keys: company_id, agent_id, telegram_plugin_id, bot_token, chat_id

Allows {{template.references}} that resolve from host-local sources at build time.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: pyyaml not installed", file=sys.stderr)
    raise

UUID_RE = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)
ABS_PATH_RE = re.compile(r"(?<![\w/])/(Users|home|private|var|opt)/[^\s\"',}]+", re.I)
FORBIDDEN_KEYS = {"company_id", "agent_id", "telegram_plugin_id", "bot_token", "chat_id"}
TEMPLATE_REF_RE = re.compile(r"\{\{[^}]+\}\}")
WORKFLOW_ROLE_RE = re.compile(r"^[a-z][a-z0-9_]*$")
PAPERCLIP_ROLES = {
    "ceo", "cto", "cmo", "cfo", "security", "engineer", "designer",
    "pm", "qa", "devops", "researcher", "general",
}
PAPERCLIP_ICONS = {
    "bot", "cpu", "brain", "zap", "rocket", "code", "terminal",
    "shield", "eye", "search", "wrench", "hammer", "lightbulb",
    "sparkles", "star", "heart", "flame", "bug", "cog", "database",
    "globe", "lock", "mail", "message-square", "file-code",
    "git-branch", "package", "puzzle", "target", "wand", "atom",
    "circuit-board", "radar", "swords", "telescope", "microscope",
    "crown", "gem", "hexagon", "pentagon", "fingerprint",
}


class ManifestValidationError(Exception):
    pass


def _strip_template_refs(text: str) -> str:
    return TEMPLATE_REF_RE.sub("", text)


def _scan_text_for_forbidden(raw_text: str, source: str) -> list[str]:
    errors: list[str] = []
    cleaned = _strip_template_refs(raw_text)
    for m in UUID_RE.finditer(cleaned):
        errors.append(f"{source}: contains literal UUID {m.group(0)}")
    for m in ABS_PATH_RE.finditer(cleaned):
        errors.append(f"{source}: contains absolute path {m.group(0)}")
    return errors


def _scan_keys_for_forbidden(data: object, path: str = "") -> list[str]:
    errors: list[str] = []
    if isinstance(data, dict):
        for k, v in data.items():
            cur = f"{path}.{k}" if path else k
            if k.lower() in FORBIDDEN_KEYS:
                errors.append(
                    f"forbidden key {cur!r} (host-local data, must move to "
                    f"~/.paperclip/projects/<key>/)",
                )
            errors.extend(_scan_keys_for_forbidden(v, cur))
    elif isinstance(data, list):
        for i, item in enumerate(data):
            errors.extend(_scan_keys_for_forbidden(item, f"{path}[{i}]"))
    return errors


def _validate_optional_agent_identity_fields(data: object) -> list[str]:
    if not isinstance(data, dict):
        return []
    agents = data.get("agents", [])
    if not isinstance(agents, list):
        return ["agents must be a list"]

    errors: list[str] = []
    for index, agent in enumerate(agents):
        if not isinstance(agent, dict):
            errors.append(f"agents[{index}] must be a mapping")
            continue
        name = agent.get("agent_name", f"agents[{index}]")
        paperclip_role = agent.get("paperclip_role")
        if paperclip_role is not None and paperclip_role not in PAPERCLIP_ROLES:
            errors.append(
                f"agent {name!r}: paperclip_role {paperclip_role!r} is not supported"
            )
        paperclip_icon = agent.get("paperclip_icon")
        if paperclip_icon is not None and paperclip_icon not in PAPERCLIP_ICONS:
            errors.append(
                f"agent {name!r}: paperclip_icon {paperclip_icon!r} is not supported"
            )
        workflow_role = agent.get("workflow_role")
        if workflow_role is not None and (
            not isinstance(workflow_role, str)
            or WORKFLOW_ROLE_RE.fullmatch(workflow_role) is None
        ):
            errors.append(
                f"agent {name!r}: workflow_role {workflow_role!r} must be snake_case"
            )
    return errors


def validate_manifest(path: Path) -> None:
    """Raise ManifestValidationError if manifest contains host-local data."""
    raw_text = path.read_text()
    errors: list[str] = []

    errors.extend(_scan_text_for_forbidden(raw_text, str(path)))

    data = yaml.safe_load(raw_text)
    errors.extend(_scan_keys_for_forbidden(data))
    errors.extend(_validate_optional_agent_identity_fields(data))

    if errors:
        raise ManifestValidationError("; ".join(errors))


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: validate_manifest.py <path-to-manifest.yaml>", file=sys.stderr)
        return 2
    try:
        validate_manifest(Path(sys.argv[1]))
        print(f"OK: {sys.argv[1]} clean")
        return 0
    except ManifestValidationError as e:
        print(f"REJECT: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
