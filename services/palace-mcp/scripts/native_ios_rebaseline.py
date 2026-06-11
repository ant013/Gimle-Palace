#!/usr/bin/env python3
"""Native MacBook seven-repo iOS rebaseline helper.

This is intentionally separate from the Docker-first ingest shell scripts. By
default it performs validation only. Pass --apply to mutate native Neo4j/Tantivy
state and call MCP extractors.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import subprocess
import sys
import time
from contextlib import AsyncExitStack
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from palace_mcp.extractors.foundation.profiles import get_ordered_extractors

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_MANIFEST = SCRIPT_DIR / "native-ios-rebaseline-manifest.json"
DEFAULT_REPO_ROOT = Path("/Users/Shared/Ios/Gimle-Repos/HorizontalSystems")
DEFAULT_NATIVE_ENV = Path("/Users/ant013/Android/Gimle-Palace-native/.env")
DEFAULT_MCP_URL = "http://127.0.0.1:8765/mcp"
DEFAULT_REPORT = Path("native-ios-rebaseline-report.json")
DEFAULT_FORBIDDEN_ROOTS = (
    Path("/Users/Shared/Ios/HorizontalSystems"),
    Path("/Users/ant013/Ios/uw-fresh-2026-06-04"),
)
DEFAULT_FORBIDDEN_PREFIXES = ("/Users/ant013/Ios/uw-fresh-",)
EXPECTED_SLUGS = (
    "bitcoin-core",
    "bitcoin-kit",
    "dash-kit",
    "evm-kit",
    "component-kit",
    "hd-wallet-kit",
    "uw-ios-app",
)
OCCURRENCE_PHASES = ("phase1_defs", "phase2_user_uses", "phase3_vendor_uses")
PERIPHERY_REQUIRED_RESULT_KEYS = (
    "accessibility",
    "attributes",
    "hints",
    "ids",
    "kind",
    "location",
    "modifiers",
    "modules",
    "name",
)


class RebaselineError(RuntimeError):
    """Operator-facing failure."""


@dataclass(frozen=True)
class ProjectSpec:
    slug: str
    name: str
    relative_path: str
    language: str
    framework: str
    language_profile: str

    @property
    def group_id(self) -> str:
        return f"project/{self.slug}"


@dataclass(frozen=True)
class NativeProfile:
    profile_name: str
    repo_root: Path
    parent_mount: str
    projects: tuple[ProjectSpec, ...]


class McpClient(Protocol):
    async def call_tool(self, tool: str, args: dict[str, Any]) -> dict[str, Any]: ...


class HttpMcpClient:
    def __init__(self, mcp_url: str, timeout_s: float = 7200.0) -> None:
        self.mcp_url = mcp_url
        self.timeout_s = timeout_s
        self._stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None

    async def _ensure_session(self) -> ClientSession:
        if self._session is not None:
            return self._session
        stack = AsyncExitStack()
        read, write, _ = await stack.enter_async_context(
            streamablehttp_client(
                self.mcp_url,
                timeout=30.0,
                sse_read_timeout=self.timeout_s,
            )
        )
        session = await stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        self._stack = stack
        self._session = session
        return session

    async def call_tool(self, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        session = await self._ensure_session()
        result = await session.call_tool(tool, args)
        for item in result.content:
            if item.type == "text":
                return json.loads(item.text)
        return {"result": result.model_dump(mode="json")}

    async def close(self) -> None:
        if self._stack is not None:
            await self._stack.aclose()
            self._stack = None
            self._session = None


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def load_profile(manifest_path: Path, repo_root_override: Path | None = None) -> NativeProfile:
    raw = json.loads(manifest_path.read_text())
    repo_root = repo_root_override or Path(raw["repo_root"])
    projects = tuple(
        ProjectSpec(
            slug=str(item["slug"]),
            name=str(item["name"]),
            relative_path=str(item["relative_path"]),
            language=str(item.get("language", "swift")),
            framework=str(item.get("framework", "swiftpm")),
            language_profile=str(item.get("language_profile", "swift_kit")),
        )
        for item in raw.get("projects", [])
    )
    profile = NativeProfile(
        profile_name=str(raw["profile_name"]),
        repo_root=repo_root,
        parent_mount=str(raw.get("parent_mount", "hs")),
        projects=projects,
    )
    validate_exact_scope(profile)
    return profile


def validate_exact_scope(profile: NativeProfile) -> None:
    slugs = tuple(project.slug for project in profile.projects)
    if slugs != EXPECTED_SLUGS:
        raise RebaselineError(
            f"native profile must contain exactly {EXPECTED_SLUGS}; got {slugs}"
        )
    android = [slug for slug in slugs if "android" in slug]
    if android:
        raise RebaselineError(f"android slugs are out of scope: {android}")


def parse_env_file(env_path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not env_path.exists():
        return values
    for raw_line in env_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("'").strip('"')
    return values


def realpath(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def reject_forbidden_path(
    path: Path,
    *,
    forbidden_roots: tuple[Path, ...] = DEFAULT_FORBIDDEN_ROOTS,
    forbidden_prefixes: tuple[str, ...] = DEFAULT_FORBIDDEN_PREFIXES,
) -> None:
    resolved = realpath(path)
    resolved_str = str(resolved)
    for prefix in forbidden_prefixes:
        if resolved_str.startswith(prefix):
            raise RebaselineError(f"forbidden native rebaseline path: {resolved}")
    for forbidden in forbidden_roots:
        forbidden_resolved = realpath(forbidden)
        if resolved == forbidden_resolved or _is_relative_to(resolved, forbidden_resolved):
            raise RebaselineError(f"forbidden native rebaseline path: {resolved}")


def require_under(path: Path, root: Path) -> Path:
    resolved = realpath(path)
    root_resolved = realpath(root)
    if resolved != root_resolved and not _is_relative_to(resolved, root_resolved):
        raise RebaselineError(f"{resolved} is not under dedicated root {root_resolved}")
    reject_forbidden_path(resolved)
    return resolved


def env_scip_paths(env: dict[str, str], profile: NativeProfile) -> dict[str, str]:
    raw = env.get("PALACE_SCIP_INDEX_PATHS", "{}")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RebaselineError(f"PALACE_SCIP_INDEX_PATHS is not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in parsed.items()
    ):
        raise RebaselineError("PALACE_SCIP_INDEX_PATHS must be a JSON object of string paths")

    validated: dict[str, str] = {}
    for project in profile.projects:
        scip_raw = parsed.get(project.slug)
        if scip_raw is None:
            raise RebaselineError(f"PALACE_SCIP_INDEX_PATHS missing {project.slug}")
        scip_path = require_under(Path(scip_raw), profile.repo_root)
        validated[project.slug] = str(scip_path)

    for slug, scip_raw in parsed.items():
        if "android" in slug.lower():
            raise RebaselineError(f"android SCIP path is out of scope: {slug}")
        reject_forbidden_path(Path(scip_raw))
    return validated


def run_git(repo: Path, args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=check,
        capture_output=True,
        text=True,
    )


def repo_state(repo: Path, *, fetch: bool, apply: bool) -> dict[str, Any]:
    if fetch and apply:
        run_git(repo, ["fetch", "origin", "--prune"])
        upstream = run_git(
            repo,
            ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
            check=False,
        )
        if upstream.returncode == 0:
            run_git(repo, ["merge", "--ff-only", upstream.stdout.strip()])
    branch_result = run_git(repo, ["rev-parse", "--abbrev-ref", "HEAD"], check=False)
    head_result = run_git(repo, ["rev-parse", "HEAD"], check=False)
    origin_result = run_git(repo, ["remote", "get-url", "origin"], check=False)
    status_result = run_git(repo, ["status", "--short"], check=False)
    return {
        "path": str(repo),
        "branch": branch_result.stdout.strip() if branch_result.returncode == 0 else None,
        "head": head_result.stdout.strip() if head_result.returncode == 0 else None,
        "origin": origin_result.stdout.strip() if origin_result.returncode == 0 else None,
        "dirty": bool(status_result.stdout.strip()),
        "status": status_result.stdout.splitlines(),
        "fetch_applied": fetch and apply,
    }


def scip_state(repo: Path) -> dict[str, Any]:
    scip_path = repo / "scip" / "index.scip"
    meta_path = repo / "scip" / "index.scip.meta.json"
    state: dict[str, Any] = {
        "path": str(scip_path),
        "exists": scip_path.exists(),
        "size_bytes": scip_path.stat().st_size if scip_path.exists() else 0,
        "meta_path": str(meta_path),
        "meta_exists": meta_path.exists(),
        "repo_head_sha_match": None,
    }
    if not scip_path.exists() or state["size_bytes"] <= 0:
        raise RebaselineError(f"SCIP index missing or empty: {scip_path}")
    if meta_path.exists():
        meta = json.loads(meta_path.read_text())
        repo_head_sha = meta.get("repo_head_sha")
        head = run_git(repo, ["rev-parse", "HEAD"], check=False).stdout.strip()
        state["repo_head_sha"] = repo_head_sha
        state["repo_head_sha_match"] = repo_head_sha == head
        if repo_head_sha != head:
            raise RebaselineError(
                f"SCIP metadata does not match repo HEAD for {repo}: "
                f"meta repo_head_sha={repo_head_sha}; HEAD={head}"
            )
    return state


def periphery_state(repo: Path) -> dict[str, Any]:
    report_path = repo / "periphery" / "periphery-3.7.4-swiftpm.json"
    contract_path = repo / "periphery" / "contract.json"
    state: dict[str, Any] = {
        "report_path": str(report_path),
        "report_exists": report_path.exists(),
        "report_size_bytes": report_path.stat().st_size if report_path.exists() else 0,
        "contract_path": str(contract_path),
        "contract_exists": contract_path.exists(),
        "result_count": None,
    }
    if not report_path.exists() or state["report_size_bytes"] <= 0:
        raise RebaselineError(f"Periphery report missing or empty: {report_path}")
    if not contract_path.exists():
        raise RebaselineError(f"Periphery contract missing: {contract_path}")

    raw_report = json.loads(report_path.read_text())
    if not isinstance(raw_report, list):
        raise RebaselineError(f"Periphery report must be a JSON array: {report_path}")
    contract = json.loads(contract_path.read_text())
    if not isinstance(contract, dict):
        raise RebaselineError(f"Periphery contract must be a JSON object: {contract_path}")
    required_keys = contract.get("required_result_keys")
    if tuple(required_keys or ()) != PERIPHERY_REQUIRED_RESULT_KEYS:
        raise RebaselineError(
            "Periphery contract required_result_keys mismatch for "
            f"{contract_path}: expected {PERIPHERY_REQUIRED_RESULT_KEYS}; got {required_keys}"
        )
    result_count = contract.get("result_count")
    if result_count is not None and result_count != len(raw_report):
        raise RebaselineError(
            f"Periphery contract result_count mismatch for {contract_path}: "
            f"expected {len(raw_report)}; got {result_count}"
        )
    state["result_count"] = len(raw_report)
    state["required_result_keys"] = list(required_keys)
    return state


async def health_check(mcp_url: str) -> dict[str, Any]:
    health_url = mcp_url.removesuffix("/mcp") + "/healthz"
    async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
        response = await client.get(health_url)
        response.raise_for_status()
        return response.json()


async def neo4j_driver_from_env(env: dict[str, str]) -> Any:
    try:
        from neo4j import AsyncGraphDatabase
    except ImportError as exc:  # pragma: no cover - dependency is present in service env
        raise RebaselineError("neo4j package is required for --apply") from exc
    password = env.get("NEO4J_PASSWORD")
    if not password:
        raise RebaselineError("NEO4J_PASSWORD missing from native env")
    uri = env.get("NEO4J_URI", "bolt://localhost:7687")
    user = env.get("NEO4J_USER", "neo4j")
    return AsyncGraphDatabase.driver(uri, auth=(user, password))


async def verify_neo4j(driver: Any) -> int:
    async with driver.session() as session:
        result = await session.run("RETURN 1 AS ok")
        row = await result.single()
    return int(row["ok"])


async def label_counts(driver: Any, group_id: str) -> dict[str, int]:
    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (n)
            WHERE n.group_id = $group_id
            UNWIND labels(n) AS label
            RETURN label, count(*) AS count
            ORDER BY label
            """,
            group_id=group_id,
        )
        rows = await result.data()
    return {str(row["label"]): int(row["count"]) for row in rows}


async def symbol_ids_for_tantivy_purge(driver: Any, group_id: str) -> list[int]:
    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (n:SymbolOccurrenceShadow {group_id: $group_id})
            WHERE n.symbol_id IS NOT NULL
            RETURN DISTINCT n.symbol_id AS symbol_id
            """,
            group_id=group_id,
        )
        rows = await result.data()
    return [int(row["symbol_id"]) for row in rows]


async def purge_tantivy_by_symbol_ids(index_path: Path, symbol_ids: list[int]) -> int:
    if not symbol_ids:
        return 0
    from palace_mcp.extractors.foundation.tantivy_bridge import TantivyBridge

    async with TantivyBridge(index_path) as bridge:
        return await bridge.delete_by_symbol_ids_async(symbol_ids)


async def delete_group(driver: Any, group_id: str) -> int:
    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (n)
            WHERE n.group_id = $group_id
            WITH collect(n) AS nodes, count(n) AS deleted
            FOREACH (node IN nodes | DETACH DELETE node)
            RETURN deleted
            """,
            group_id=group_id,
        )
        row = await result.single()
    return int(row["deleted"])


async def ingest_runs(driver: Any, group_id: str, extractor: str) -> list[dict[str, Any]]:
    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (r:IngestRun {group_id: $group_id, extractor_name: $extractor})
            RETURN r
            ORDER BY coalesce(r.finished_at, r.started_at) DESC
            LIMIT 3
            """,
            group_id=group_id,
            extractor=extractor,
        )
        rows = await result.data()
    return [dict(row["r"]) for row in rows]


async def occurrence_counts_for_run(index_path: Path, run_id: str) -> dict[str, int]:
    from palace_mcp.extractors.foundation.tantivy_bridge import TantivyBridge

    async with TantivyBridge(index_path) as bridge:
        return {
            phase: await bridge.count_docs_for_run_async(run_id, phase)
            for phase in OCCURRENCE_PHASES
        }


async def register_project(client: McpClient, profile: NativeProfile, project: ProjectSpec) -> dict[str, Any]:
    return await client.call_tool(
        "palace.memory.register_project",
        {
            "slug": project.slug,
            "name": project.name,
            "language": project.language,
            "framework": project.framework,
            "parent_mount": profile.parent_mount,
            "relative_path": project.relative_path,
            "language_profile": project.language_profile,
            "expected_profile": True,
        },
    )


async def run_extractor(
    client: McpClient,
    project: ProjectSpec,
    extractor: str,
) -> dict[str, Any]:
    payload = {"name": extractor, "project": project.slug}
    if extractor == "symbol_index_swift":
        payload["scip_path"] = "scip/index.scip"
    return await client.call_tool("palace.ingest.run_extractor", payload)


async def run_sequential_extractors(
    client: McpClient,
    profile: NativeProfile,
    extractors: tuple[str, ...],
    *,
    start_project: str | None = None,
    start_after_extractor: str | None = None,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    project_started = start_project is None
    for project in profile.projects:
        if not project_started:
            if project.slug != start_project:
                continue
            project_started = True
        project_extractors = extractors
        if project.slug == start_project and start_after_extractor:
            start_index = extractors.index(start_after_extractor) + 1
            project_extractors = extractors[start_index:]
        await register_project(client, profile, project)
        for extractor in project_extractors:
            started_at = utc_now()
            started = time.monotonic()
            response = await run_extractor(client, project, extractor)
            finished_at = utc_now()
            item = {
                "project": project.slug,
                "extractor": extractor,
                "started_at": started_at,
                "finished_at": finished_at,
                "wall_seconds": round(time.monotonic() - started, 3),
                "response": response,
            }
            results.append(item)
            if response.get("ok") is False or response.get("error_code"):
                raise RebaselineError(
                    f"{project.slug}/{extractor} failed: {response.get('message') or response}"
                )
    return results


def validate_resume_args(
    profile: NativeProfile,
    extractors: tuple[str, ...],
    *,
    start_project: str | None,
    start_after_extractor: str | None,
) -> None:
    project_slugs = {project.slug for project in profile.projects}
    if start_project is not None and start_project not in project_slugs:
        raise RebaselineError(f"--start-project must be one of {sorted(project_slugs)}")
    if start_after_extractor is not None:
        if start_project is None:
            raise RebaselineError("--start-after-extractor requires --start-project")
        if start_after_extractor not in extractors:
            raise RebaselineError(
                f"--start-after-extractor must be one of {list(extractors)}"
            )


async def build_report(args: argparse.Namespace) -> dict[str, Any]:
    profile = load_profile(args.manifest, args.repo_root)
    native_env = parse_env_file(args.native_env)
    if realpath(args.native_env) != realpath(DEFAULT_NATIVE_ENV):
        raise RebaselineError(f"unexpected native env path: {args.native_env}")

    report: dict[str, Any] = {
        "started_at": utc_now(),
        "mode": "apply" if args.apply else "dry-run",
        "manifest": str(args.manifest),
        "mcp_url": args.mcp_url,
        "native_env": str(args.native_env),
        "profile": profile.profile_name,
        "env_scip_paths": env_scip_paths(native_env, profile),
        "projects": [],
        "cleanup": [],
        "extractor_runs": [],
        "verification": {},
    }

    if args.apply:
        report["verification"]["healthz"] = await health_check(args.mcp_url)
        client: McpClient = HttpMcpClient(args.mcp_url)
        registered = await client.call_tool("palace.ingest.list_extractors", {})
        report["verification"]["registered_extractors"] = registered
    else:
        client = HttpMcpClient(args.mcp_url)

    for project in profile.projects:
        repo = require_under(profile.repo_root / project.relative_path, profile.repo_root)
        scip_path = require_under(repo / "scip" / "index.scip", profile.repo_root)
        reject_forbidden_path(scip_path)
        project_report = {
            "slug": project.slug,
            "group_id": project.group_id,
            "repo": repo_state(repo, fetch=not args.skip_fetch, apply=args.apply),
            "scip": scip_state(repo),
            "periphery": periphery_state(repo),
        }
        report["projects"].append(project_report)

    extractors = tuple(args.extractors or get_ordered_extractors("swift_kit"))
    validate_resume_args(
        profile,
        extractors,
        start_project=args.start_project,
        start_after_extractor=args.start_after_extractor,
    )
    report["resume"] = {
        "skip_cleanup": args.skip_cleanup,
        "start_project": args.start_project,
        "start_after_extractor": args.start_after_extractor,
    }

    if args.apply:
        driver = await neo4j_driver_from_env(native_env)
        try:
            report["verification"]["neo4j_return_1"] = await verify_neo4j(driver)
            tantivy_path = Path(
                native_env.get("PALACE_TANTIVY_INDEX_PATH", "/var/lib/palace/tantivy")
            )
            if args.wipe_tantivy_index:
                require_under(tantivy_path, Path.home())
                reject_forbidden_path(tantivy_path)
                shutil.rmtree(tantivy_path, ignore_errors=True)
                tantivy_path.mkdir(parents=True, exist_ok=True)
                report["verification"]["tantivy_wipe"] = {
                    "path": str(tantivy_path),
                    "mode": "full_native_index_wipe",
                }
            if args.skip_cleanup:
                report["cleanup"].append(
                    {
                        "mode": "skipped",
                        "reason": "resume_existing_native_rebaseline",
                    }
                )
            else:
                for project in profile.projects:
                    before = await label_counts(driver, project.group_id)
                    symbol_ids = await symbol_ids_for_tantivy_purge(driver, project.group_id)
                    if args.wipe_tantivy_index:
                        tantivy_deleted = 0
                    else:
                        tantivy_deleted = await purge_tantivy_by_symbol_ids(
                            tantivy_path, symbol_ids
                        )
                    graph_deleted = await delete_group(driver, project.group_id)
                    after = await label_counts(driver, project.group_id)
                    report["cleanup"].append(
                        {
                            "project": project.slug,
                            "group_id": project.group_id,
                            "before_label_counts": before,
                            "symbol_ids_for_tantivy": len(symbol_ids),
                            "tantivy_delete_requests": tantivy_deleted,
                            "tantivy_purge_mode": "skipped_after_full_wipe"
                            if args.wipe_tantivy_index
                            else "delete_by_symbol_id",
                            "neo4j_nodes_deleted": graph_deleted,
                            "after_label_counts": after,
                        }
                    )

            report["extractor_runs"] = await run_sequential_extractors(
                client,
                profile,
                extractors,
                start_project=args.start_project,
                start_after_extractor=args.start_after_extractor,
            )
            for item in report["extractor_runs"]:
                project = str(item["project"])
                extractor = str(item["extractor"])
                group_id = f"project/{project}"
                item["neo4j_ingest_runs"] = await ingest_runs(driver, group_id, extractor)
                item["label_counts_after"] = await label_counts(driver, group_id)
                run_id = item["response"].get("run_id")
                if run_id and extractor in {
                    "symbol_index_swift",
                    "dead_code",
                    "dead_symbol_binary_surface",
                }:
                    item["occurrence_counts"] = await occurrence_counts_for_run(
                        tantivy_path, str(run_id)
                    )
        finally:
            await driver.close()
    else:
        report["extractors_planned"] = list(extractors)
        report["note"] = "dry-run only; pass --apply to clean native state and ingest"

    report["finished_at"] = utc_now()
    return report


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Native MacBook seven-repo iOS rebaseline helper"
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--repo-root", type=Path, default=None)
    parser.add_argument("--native-env", type=Path, default=DEFAULT_NATIVE_ENV)
    parser.add_argument("--mcp-url", default=DEFAULT_MCP_URL)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--extractors", default="")
    parser.add_argument("--skip-fetch", action="store_true")
    parser.add_argument(
        "--skip-cleanup",
        action="store_true",
        help="resume without deleting existing native Neo4j/Tantivy state",
    )
    parser.add_argument(
        "--start-project",
        default=None,
        help="resume at this project slug, skipping earlier projects",
    )
    parser.add_argument(
        "--start-after-extractor",
        default=None,
        help="for --start-project, skip extractors through this extractor",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="mutate native Neo4j/Tantivy state and call MCP extractors",
    )
    parser.add_argument(
        "--wipe-tantivy-index",
        action="store_true",
        help="delete the native Tantivy index directory once before ingest",
    )
    args = parser.parse_args(argv)
    args.extractors = (
        tuple(part.strip() for part in args.extractors.split(",") if part.strip())
        if args.extractors
        else ()
    )
    return args


async def amain(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        report = await build_report(args)
    except RebaselineError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


def main() -> int:
    return asyncio.run(amain(sys.argv[1:]))


if __name__ == "__main__":
    raise SystemExit(main())
