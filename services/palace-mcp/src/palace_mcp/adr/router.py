"""ADR tool router — registers palace.code.manage_adr as native @mcp.tool (GIM-274).

AD-D7: native registration, NOT CM subprocess passthrough.
Modes: read | write | supersede | query (all NEW — v1 was DISABLED).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal, NoReturn

from neo4j import AsyncDriver

logger = logging.getLogger(__name__)


def _assert_never(value: NoReturn) -> NoReturn:
    raise AssertionError(f"Unhandled mode: {value!r}")


_TOOL_DESCRIPTION = (
    "Read/write/query ADR documents stored under docs/postulates/. "
    "Modes: "
    "read(slug) — full markdown + section list, side-effect: file-to-graph projection; "
    "write(slug, section, body, decision_id?) — idempotent section upsert in file + graph; "
    "supersede(old_slug, new_slug, reason) — mark old ADR as superseded; "
    "query(keyword?, section_filter?, project_filter?) — graph-based keyword search. "
    "Distinct from palace.memory.lookup Decision: ADR = architecture decision record file; "
    "Decision = structured graph node created by palace.memory.decide."
)


def register_adr_tools(
    tool_decorator: Callable[[str, str], Any],
    base_dir: Path,
    driver_getter: Callable[[], AsyncDriver | None],
) -> None:
    """Register palace.code.manage_adr as native @mcp.tool.

    Called from mcp_server.py at module level alongside register_code_tools().
    base_dir: writable directory for ADR markdown files (docs/postulates/).
    driver_getter: callable that returns the live AsyncDriver (or None).
    """

    @tool_decorator("palace.code.manage_adr", _TOOL_DESCRIPTION)  # type: ignore[untyped-decorator]
    async def palace_code_manage_adr(
        mode: Literal["read", "write", "supersede", "query"],
        slug: str | None = None,
        section: (
            Literal[
                "PURPOSE",
                "STACK",
                "ARCHITECTURE",
                "PATTERNS",
                "TRADEOFFS",
                "PHILOSOPHY",
            ]
            | None
        ) = None,
        body: str | None = None,
        old_slug: str | None = None,
        new_slug: str | None = None,
        reason: str | None = None,
        keyword: str | None = None,
        section_filter: str | None = None,
        project_filter: str | None = None,
        decision_id: str | None = None,
    ) -> dict[str, Any]:
        driver = driver_getter()
        if driver is None:
            return {
                "ok": False,
                "error_code": "driver_unavailable",
                "message": "Neo4j driver not initialised",
            }

        if mode == "read":
            from palace_mcp.adr.reader import read_adr

            if not slug:
                return {
                    "ok": False,
                    "error_code": "missing_param",
                    "message": "read mode requires slug",
                }
            return await read_adr(slug=slug, base_dir=base_dir, driver=driver)

        if mode == "write":
            from palace_mcp.adr.writer import write_adr

            if not slug or not section or body is None:
                return {
                    "ok": False,
                    "error_code": "missing_param",
                    "message": "write mode requires slug, section, and body",
                }
            return await write_adr(
                slug=slug,
                section=section,
                body=body,
                decision_id=decision_id,
                base_dir=base_dir,
                driver=driver,
            )

        if mode == "supersede":
            from palace_mcp.adr.supersede import supersede_adr

            if not old_slug or not new_slug or not reason:
                return {
                    "ok": False,
                    "error_code": "missing_param",
                    "message": "supersede mode requires old_slug, new_slug, and reason",
                }
            return await supersede_adr(
                old_slug=old_slug,
                new_slug=new_slug,
                reason=reason,
                base_dir=base_dir,
                driver=driver,
            )

        if mode == "query":
            from palace_mcp.adr.query import query_adrs

            return await query_adrs(
                keyword=keyword,
                section_filter=section_filter,
                project_filter=project_filter,
                driver=driver,
            )

        _assert_never(mode)
