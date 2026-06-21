from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def build_passthrough_project_listing(
    passthrough_tools: Mapping[str, Any],
) -> dict[str, list[str]]:
    native: list[str] = []
    cm_only: list[str] = []

    for tool_name, entry in passthrough_tools.items():
        full_name = f"palace.code.{tool_name}"
        if getattr(entry, "native_handler", None) is None:
            cm_only.append(full_name)
        else:
            native.append(full_name)

    return {"native": native, "cm_only": cm_only}
