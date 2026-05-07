"""palace-mcp CLI — audit subcommands.

Entrypoint:
    python -m palace_mcp.cli <command> [args]

Commands:
    audit run   --project=<slug>|--bundle=<name> [--url=<mcp-url>] [--depth=full|quick]
    audit launch --project=<slug>|--bundle=<name> --auditor-id=<uuid>
                 [--api-url=<url>] [--company-id=<id>] [--api-key=<key>] [--dry-run]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from typing import Any

_SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
_DEFAULT_MCP_URL = "http://localhost:8000/mcp"
_DEFAULT_API_URL = "http://localhost:3100"
_DEFAULT_COMPANY_ID = "9d8f432c-ff7d-4e3a-bbe3-3cd355f73b64"

# Domain agents that receive child audit issues (from AGENTS.md roster)
_DOMAIN_AGENTS: list[dict[str, str]] = [
    {
        "domain": "audit-arch",
        "role": "OpusArchitectReviewer",
        "agent_id": "8d6649e2-2df6-412a-a6bc-2d94bab3b73f",
    },
    {
        "domain": "audit-sec",
        "role": "SecurityAuditor",
        "agent_id": "a56f9e4a-ef9c-46d4-a736-1db5e19bbde4",
    },
    {
        "domain": "audit-crypto",
        "role": "BlockchainEngineer",
        "agent_id": "9874ad7a-dfbc-49b0-b3ed-d0efda6453bb",
    },
]


# ---------------------------------------------------------------------------
# Pure payload builders — testable without network
# ---------------------------------------------------------------------------


def validate_slug(slug: str) -> None:
    if not _SLUG_RE.match(slug):
        raise ValueError(f"invalid slug {slug!r}: must match [a-z0-9-]{{1,64}}")


def build_mcp_run_args(
    *,
    project: str | None,
    bundle: str | None,
    depth: str,
) -> dict[str, Any]:
    args: dict[str, Any] = {"depth": depth}
    if project:
        args["project"] = project
    if bundle:
        args["bundle"] = bundle
    return args


def build_parent_payload(
    target: str,
    auditor_id: str,
    company_id: str,
) -> dict[str, Any]:
    return {
        "title": f"audit: {target}",
        "body": (
            f"Full Audit-V1 report for `{target}`.\n\n"
            f"Orchestrator: wait for 3 domain child issues to complete, "
            f"then assemble the final report from their sub-report comments."
        ),
        "assigneeAgentId": auditor_id,
        "companyId": company_id,
    }


def build_child_payload(
    target: str,
    domain: str,
    agent_id: str,
    parent_id: str,
    company_id: str,
) -> dict[str, Any]:
    return {
        "title": f"audit-domain: {target}/{domain}",
        "body": (
            f"Domain audit sub-report for `{target}`.\n\n"
            f"Domain: `{domain}`.\n"
            f"Fetch data via `palace.audit.run(project=\"{target}\")`, "
            f"produce a markdown sub-report per Auditor role instructions."
        ),
        "assigneeAgentId": agent_id,
        "parentIssueId": parent_id,
        "companyId": company_id,
    }


def build_dry_run_payloads(
    target: str,
    auditor_id: str,
    company_id: str,
) -> list[dict[str, Any]]:
    """Return all 4 issue payloads without calling the API."""
    parent = build_parent_payload(target, auditor_id, company_id)
    children = [
        build_child_payload(
            target=target,
            domain=d["domain"],
            agent_id=d["agent_id"],
            parent_id="<parent-id-placeholder>",
            company_id=company_id,
        )
        for d in _DOMAIN_AGENTS
    ]
    return [parent] + children


# ---------------------------------------------------------------------------
# Async I/O helpers
# ---------------------------------------------------------------------------


async def _call_audit_run(
    url: str,
    project: str | None,
    bundle: str | None,
    depth: str,
) -> dict[str, Any]:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    from mcp.types import TextContent

    call_args = build_mcp_run_args(project=project, bundle=bundle, depth=depth)
    async with streamablehttp_client(url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("palace.audit.run", call_args)
    first = result.content[0]
    if not isinstance(first, TextContent):
        raise ValueError(f"unexpected content type from palace.audit.run: {type(first)}")
    return json.loads(first.text)  # type: ignore[no-any-return]


async def _create_issues(
    api_url: str,
    api_key: str,
    company_id: str,
    auditor_id: str,
    target: str,
) -> list[dict[str, Any]]:
    import httpx

    headers: dict[str, str] = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    created: list[dict[str, Any]] = []
    async with httpx.AsyncClient(headers=headers, timeout=30) as client:
        parent_payload = build_parent_payload(target, auditor_id, company_id)
        resp = await client.post(
            f"{api_url}/api/companies/{company_id}/issues",
            json=parent_payload,
        )
        resp.raise_for_status()
        parent = resp.json()
        created.append(parent)
        parent_id: str = parent["id"]

        for da in _DOMAIN_AGENTS:
            child_payload = build_child_payload(
                target=target,
                domain=da["domain"],
                agent_id=da["agent_id"],
                parent_id=parent_id,
                company_id=company_id,
            )
            resp = await client.post(
                f"{api_url}/api/companies/{company_id}/issues",
                json=child_payload,
            )
            resp.raise_for_status()
            created.append(resp.json())

    return created


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def _add_target_args(sub: argparse.ArgumentParser) -> None:
    group = sub.add_mutually_exclusive_group(required=True)
    group.add_argument("--project", help="Project slug")
    group.add_argument("--bundle", help="Bundle name")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="palace-mcp",
        description="palace-mcp command-line interface",
    )
    top = parser.add_subparsers(dest="command", required=True)

    audit_p = top.add_parser("audit", help="Audit commands")
    audit_sub = audit_p.add_subparsers(dest="audit_command", required=True)

    run_p = audit_sub.add_parser("run", help="Run synchronous audit report")
    _add_target_args(run_p)
    run_p.add_argument("--url", default=_DEFAULT_MCP_URL, help="palace-mcp MCP URL")
    run_p.add_argument("--depth", default="full", choices=["quick", "full"])

    launch_p = audit_sub.add_parser("launch", help="Launch async audit workflow")
    _add_target_args(launch_p)
    launch_p.add_argument(
        "--auditor-id", required=True, help="Auditor agent UUID in Paperclip"
    )
    launch_p.add_argument("--api-url", default=_DEFAULT_API_URL)
    launch_p.add_argument("--api-key", default="")
    launch_p.add_argument("--company-id", default=_DEFAULT_COMPANY_ID)
    launch_p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print all 4 issue payloads as JSON without calling the Paperclip API",
    )

    return parser


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------


def _cmd_audit_run(args: argparse.Namespace) -> int:
    target = args.project or args.bundle
    try:
        validate_slug(target)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    try:
        payload = asyncio.run(
            _call_audit_run(
                url=args.url,
                project=args.project,
                bundle=args.bundle,
                depth=args.depth,
            )
        )
    except Exception as exc:
        print(f"error: MCP call failed: {exc}", file=sys.stderr)
        return 1

    if not payload.get("ok"):
        print(
            f"error: {payload.get('error_code')}: {payload.get('message')}",
            file=sys.stderr,
        )
        return 1

    print(payload["report_markdown"])
    return 0


def _cmd_audit_launch(args: argparse.Namespace) -> int:
    target = args.project or args.bundle
    try:
        validate_slug(target)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.dry_run:
        payloads = build_dry_run_payloads(
            target=target,
            auditor_id=args.auditor_id,
            company_id=args.company_id,
        )
        print(json.dumps(payloads, indent=2))
        return 0

    try:
        created = asyncio.run(
            _create_issues(
                api_url=args.api_url,
                api_key=args.api_key,
                company_id=args.company_id,
                auditor_id=args.auditor_id,
                target=target,
            )
        )
    except Exception as exc:
        print(f"error: Paperclip API call failed: {exc}", file=sys.stderr)
        return 1

    parent = created[0]
    children = created[1:]
    print(f"Created parent issue: {parent.get('id')} — {parent.get('title')}")
    for child in children:
        print(f"  Child: {child.get('id')} — {child.get('title')}")
    return 0


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "audit":
        if args.audit_command == "run":
            sys.exit(_cmd_audit_run(args))
        if args.audit_command == "launch":
            sys.exit(_cmd_audit_launch(args))

    parser.print_help()
    sys.exit(2)


if __name__ == "__main__":
    main()
