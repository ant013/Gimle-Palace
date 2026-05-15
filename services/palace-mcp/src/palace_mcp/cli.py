"""palace-mcp CLI.

Entrypoint:
    python -m palace_mcp.cli <command> [args]

Commands:
    audit run   --project=<slug>|--bundle=<name> [--url=<mcp-url>] [--depth=full|quick]
    audit launch --project=<slug>|--bundle=<name> --auditor-id=<uuid>
                 [--api-url=<url>] [--company-id=<id>] [--api-key=<key>] [--dry-run]
    tool call <tool-name> [--url=<mcp-url>] [--json=<json-args>]
    project analyze --repo-path=<path> --slug=<slug> --language-profile=<profile>
                    [--emit-scip=auto|always|never] [--url=<mcp-url>]
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import shlex
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from palace_mcp.extractors.foundation.profiles import get_ordered_extractors

_SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
_DEFAULT_MCP_URL = "http://localhost:8000/mcp"
_DEFAULT_PROJECT_ANALYZE_URL = "http://localhost:8080/mcp"
_DEFAULT_API_URL = "http://localhost:3100"
_DEFAULT_COMPANY_ID = "9d8f432c-ff7d-4e3a-bbe3-3cd355f73b64"
_DEFAULT_PROJECT_ANALYZE_POLL_SECONDS = 2
_PROJECT_ACTIVE_STATUSES = {"PENDING", "RUNNING", "RESUMABLE"}
_PROJECT_SUCCESS_STATUSES = {"SUCCEEDED", "SUCCEEDED_WITH_FAILURES"}
_SWIFT_SCIP_EMITTER_NAME = "palace-swift-scip-emit-cli"
_SWIFT_SCIP_EMITTER_VERSION = "2026-05-15"
_DEFAULT_REMOTE_HOST = "imac-ssh.ant013.work"
_DEFAULT_REMOTE_BASE = "/Users/Shared/Ios/HorizontalSystems"
_DEFAULT_MACBOOK_BASE = "/Users/ant013/Ios/HorizontalSystems"
_REPO_ROOT = Path(__file__).resolve().parents[4]
_DEFAULT_ENV_FILE = _REPO_ROOT / ".env"
_DEFAULT_RUNTIME_DIR = _REPO_ROOT / ".gimle" / "runtime" / "project-analyze"
_DEFAULT_PROJECT_ANALYZE_STAGE_ROOT = (
    Path.home() / ".cache" / "palace" / "project-analyze-mounts"
)
_DEFAULT_COMPOSE_OVERRIDE_PATH = (
    _DEFAULT_RUNTIME_DIR / "docker-compose.project-analyze.yml"
)
_DEFAULT_MANIFEST_PATH = (
    _REPO_ROOT / "services" / "palace-mcp" / "scripts" / "uw-ios-bundle-manifest.json"
)
_DEFAULT_SWIFT_EMITTER_DIR = _REPO_ROOT / "services" / "palace-mcp" / "scip_emit_swift"

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


class ProjectAnalyzeCliError(RuntimeError):
    """Typed host-CLI error with a machine-readable code."""

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "project_analyze_cli_error",
    ) -> None:
        super().__init__(message)
        self.error_code = error_code


class ScipEmitToolchainUnsupported(ProjectAnalyzeCliError):
    """Swift toolchain is unavailable or unusable on the current host."""

    def __init__(
        self,
        *,
        message: str,
        fallback_command: str,
    ) -> None:
        super().__init__(message, error_code="SCIP_EMIT_TOOLCHAIN_UNSUPPORTED")
        self.fallback_command = fallback_command


@dataclass(frozen=True)
class ComposeMount:
    host_path: Path
    container_path: str


@dataclass(frozen=True)
class ManifestMember:
    bundle_name: str | None
    parent_mount: str | None
    relative_path: str | None


@dataclass(frozen=True)
class ProjectRuntimeSpec:
    repo_path: Path
    slug: str
    language_profile: str
    bundle: str | None
    parent_mount: str
    relative_path: str
    container_repo_path: str
    container_scip_path: str
    env_file: Path
    compose_override_path: Path
    report_out: Path
    summary_out: Path
    host_mount_path: Path | None
    container_mount_path: str | None

    @property
    def compose_files(self) -> list[Path]:
        return [
            _REPO_ROOT / "docker-compose.yml",
            self.compose_override_path,
        ]


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


def normalize_tool_name(name: str) -> str:
    if name.startswith("palace."):
        return name
    return f"palace.{name}"


def parse_tool_json_arg(payload: str) -> dict[str, Any]:
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON arguments: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("invalid JSON arguments: expected a JSON object")
    return parsed


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
            f'Fetch data via `palace.audit.run(project="{target}")`, '
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


def _default_report_path(slug: str) -> Path:
    return _DEFAULT_RUNTIME_DIR / f"{slug}-analysis-report.md"


def _default_summary_path(slug: str) -> Path:
    return _DEFAULT_RUNTIME_DIR / f"{slug}-analysis-summary.json"


def _load_manifest_member(
    manifest_path: Path,
    slug: str,
) -> ManifestMember | None:
    if not manifest_path.exists():
        return None
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    members = data.get("members")
    if not isinstance(members, list):
        return None
    for member in members:
        if isinstance(member, dict) and member.get("slug") == slug:
            return ManifestMember(
                bundle_name=data.get("bundle_name")
                if isinstance(data.get("bundle_name"), str)
                else None,
                parent_mount=data.get("parent_mount")
                if isinstance(data.get("parent_mount"), str)
                else None,
                relative_path=member.get("relative_path")
                if isinstance(member.get("relative_path"), str)
                else None,
            )
    return None


def _sanitize_parent_mount(candidate: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", candidate.lower()).strip("-")
    if not normalized:
        normalized = "local"
    if not normalized[0].isalpha():
        normalized = f"m{normalized}"
    return normalized[:16]


def _runtime_stage_parent_mount(parent_mount: str) -> str:
    candidate = f"{parent_mount}-stage"
    if len(candidate) <= 16:
        return candidate
    return "stage"


def _docker_context_name() -> str:
    try:
        result = _run_command(["docker", "context", "show"], capture_output=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""
    return result.stdout.strip()


def _host_path_requires_staging(repo_path: Path) -> bool:
    if _docker_context_name() != "colima":
        return False
    try:
        repo_path.relative_to(Path.home())
    except ValueError:
        return True
    return False


def _discover_existing_mount(repo_path: Path) -> ComposeMount | None:
    compose_path = _REPO_ROOT / "docker-compose.yml"
    if not compose_path.exists():
        return None
    mount_re = re.compile(
        r"^\s*-\s*(?P<host>/[^:]+):(?P<container>/repos-[^:]+):ro\s*$"
    )
    for line in compose_path.read_text(encoding="utf-8").splitlines():
        match = mount_re.match(line)
        if match is None:
            continue
        host_path = Path(match.group("host")).expanduser()
        try:
            repo_path.relative_to(host_path)
        except ValueError:
            continue
        return ComposeMount(
            host_path=host_path, container_path=match.group("container")
        )
    return None


def resolve_project_runtime_spec(
    *,
    repo_path: Path,
    slug: str,
    language_profile: str,
    bundle: str | None,
    env_file: Path = _DEFAULT_ENV_FILE,
    manifest_path: Path = _DEFAULT_MANIFEST_PATH,
    compose_override_path: Path = _DEFAULT_COMPOSE_OVERRIDE_PATH,
    report_out: Path | None = None,
    summary_out: Path | None = None,
) -> ProjectRuntimeSpec:
    manifest_member = _load_manifest_member(manifest_path, slug)
    existing_mount = _discover_existing_mount(repo_path)

    resolved_bundle = bundle or (
        manifest_member.bundle_name if manifest_member else None
    )
    if existing_mount is not None:
        relative_path = repo_path.relative_to(existing_mount.host_path).as_posix()
        parent_mount = existing_mount.container_path.removeprefix("/repos-")
        container_repo_path = f"{existing_mount.container_path}/{relative_path}"
        host_mount_path = None
        container_mount_path = None
    else:
        parent_mount = (
            manifest_member.parent_mount
            if manifest_member and manifest_member.parent_mount
            else _sanitize_parent_mount(repo_path.parent.name or slug)
        )
        relative_path = repo_path.name
        container_mount_path = f"/repos-{parent_mount}"
        container_repo_path = f"{container_mount_path}/{relative_path}"
        host_mount_path = repo_path.parent

    return ProjectRuntimeSpec(
        repo_path=repo_path,
        slug=slug,
        language_profile=language_profile,
        bundle=resolved_bundle,
        parent_mount=parent_mount,
        relative_path=relative_path,
        container_repo_path=container_repo_path,
        container_scip_path=f"{container_repo_path}/scip/index.scip",
        env_file=env_file,
        compose_override_path=compose_override_path,
        report_out=report_out or _default_report_path(slug),
        summary_out=summary_out or _default_summary_path(slug),
        host_mount_path=host_mount_path,
        container_mount_path=container_mount_path,
    )


def _copy_runtime_stage(source_repo_path: Path, staged_repo_path: Path) -> None:
    if shutil.which("rsync") is None:
        raise ProjectAnalyzeCliError(
            "rsync is required for colima runtime staging but was not found on PATH",
            error_code="missing_rsync",
        )
    staged_repo_path.parent.mkdir(parents=True, exist_ok=True)
    _run_command(
        [
            "rsync",
            "-a",
            "--delete",
            "--exclude",
            ".build/",
            f"{source_repo_path}/",
            f"{staged_repo_path}/",
        ]
    )


def stage_project_runtime_spec(
    spec: ProjectRuntimeSpec,
    *,
    stage_root: Path = _DEFAULT_PROJECT_ANALYZE_STAGE_ROOT,
) -> ProjectRuntimeSpec:
    stage_parent_mount = _runtime_stage_parent_mount(spec.parent_mount)
    stage_host_root = stage_root / stage_parent_mount
    staged_repo_path = stage_host_root / spec.relative_path
    _copy_runtime_stage(spec.repo_path, staged_repo_path)

    container_mount_path = f"/repos-{stage_parent_mount}"
    container_repo_path = f"{container_mount_path}/{spec.relative_path}"
    return ProjectRuntimeSpec(
        repo_path=spec.repo_path,
        slug=spec.slug,
        language_profile=spec.language_profile,
        bundle=spec.bundle,
        parent_mount=stage_parent_mount,
        relative_path=spec.relative_path,
        container_repo_path=container_repo_path,
        container_scip_path=f"{container_repo_path}/scip/index.scip",
        env_file=spec.env_file,
        compose_override_path=spec.compose_override_path,
        report_out=spec.report_out,
        summary_out=spec.summary_out,
        host_mount_path=stage_host_root,
        container_mount_path=container_mount_path,
    )


def _render_compose_override(spec: ProjectRuntimeSpec) -> str:
    if spec.host_mount_path is None or spec.container_mount_path is None:
        return "services: {}\n"
    return (
        "services:\n"
        "  palace-mcp:\n"
        "    volumes:\n"
        f"      - {spec.host_mount_path}:{spec.container_mount_path}:ro\n"
    )


def write_project_analyze_compose_override(spec: ProjectRuntimeSpec) -> bool:
    content = _render_compose_override(spec)
    spec.compose_override_path.parent.mkdir(parents=True, exist_ok=True)
    existing = (
        spec.compose_override_path.read_text(encoding="utf-8")
        if spec.compose_override_path.exists()
        else None
    )
    if existing == content:
        return False
    spec.compose_override_path.write_text(content, encoding="utf-8")
    return True


def merge_scip_index_env_mapping(
    *,
    env_file: Path,
    slug: str,
    container_scip_path: str,
) -> tuple[bool, dict[str, str]]:
    env_file.parent.mkdir(parents=True, exist_ok=True)
    lines = (
        env_file.read_text(encoding="utf-8").splitlines() if env_file.exists() else []
    )
    merged: dict[str, str] = {}
    new_lines: list[str] = []
    updated = False
    found = False

    for line in lines:
        if not line.startswith("PALACE_SCIP_INDEX_PATHS="):
            new_lines.append(line)
            continue
        found = True
        raw_value = line.split("=", 1)[1]
        if raw_value.strip():
            try:
                parsed = json.loads(raw_value)
            except json.JSONDecodeError as exc:
                raise ProjectAnalyzeCliError(
                    f"PALACE_SCIP_INDEX_PATHS is not valid JSON in {env_file}: {exc}",
                    error_code="invalid_scip_index_env_json",
                ) from exc
            if not isinstance(parsed, dict) or not all(
                isinstance(key, str) and isinstance(value, str)
                for key, value in parsed.items()
            ):
                raise ProjectAnalyzeCliError(
                    "PALACE_SCIP_INDEX_PATHS must be a JSON object of string paths",
                    error_code="invalid_scip_index_env_shape",
                )
            merged.update(parsed)
        if merged.get(slug) != container_scip_path:
            updated = True
        merged[slug] = container_scip_path
        encoded = json.dumps(merged, sort_keys=True, separators=(",", ":"))
        new_lines.append(f"PALACE_SCIP_INDEX_PATHS={encoded}")

    if not found:
        merged = {slug: container_scip_path}
        encoded = json.dumps(merged, sort_keys=True, separators=(",", ":"))
        new_lines.append(f"PALACE_SCIP_INDEX_PATHS={encoded}")
        updated = True

    if updated:
        env_file.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    return updated, merged


def _run_command(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    capture_output: bool = False,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd is not None else None,
        check=True,
        text=True,
        capture_output=capture_output,
    )


def _git_head_sha(repo_path: Path) -> str:
    result = _run_command(
        ["git", "-C", str(repo_path), "rev-parse", "HEAD"],
        capture_output=True,
    )
    return result.stdout.strip()


def _build_macbook_fallback_command(spec: ProjectRuntimeSpec) -> str:
    macbook_repo_path = str(Path(_DEFAULT_MACBOOK_BASE) / spec.relative_path)
    parts = [
        "bash",
        "paperclips/scripts/scip_emit_swift_kit.sh",
        spec.slug,
        "--repo-path",
        macbook_repo_path,
        "--remote-host",
        _DEFAULT_REMOTE_HOST,
        "--remote-base",
        _DEFAULT_REMOTE_BASE,
        "--remote-relative-path",
        spec.relative_path,
    ]
    return " ".join(shlex.quote(part) for part in parts)


def _load_scip_metadata(meta_path: Path) -> dict[str, Any] | None:
    if not meta_path.exists():
        return None
    try:
        payload = json.loads(meta_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def swift_scip_metadata_needs_regeneration(
    *,
    repo_path: Path,
    repo_head_sha: str,
    metadata: dict[str, Any] | None,
) -> tuple[bool, str]:
    if metadata is None:
        return True, "metadata missing or invalid"
    resolved_repo_path = str(repo_path.resolve())
    required = {
        "repo_head_sha": repo_head_sha,
        "emitter_name": _SWIFT_SCIP_EMITTER_NAME,
        "emitter_version": _SWIFT_SCIP_EMITTER_VERSION,
        "package_path": "Package.swift",
        "destination_repo_path": resolved_repo_path,
    }
    for key, expected in required.items():
        if metadata.get(key) != expected:
            return True, f"{key} mismatch"
    source_repo_path = metadata.get("source_repo_path")
    generator_host = metadata.get("generator_host")
    if not isinstance(source_repo_path, str) or not source_repo_path:
        return True, "source_repo_path missing"
    if not isinstance(generator_host, str) or not generator_host:
        return True, "generator_host missing"
    if metadata.get("artifact_origin") == "remote_copy":
        return False, "metadata current (remote_copy)"
    if source_repo_path != resolved_repo_path:
        return True, "source_repo_path mismatch"
    if generator_host != socket.gethostname():
        return True, "generator_host mismatch"
    return False, "metadata current"


def _write_scip_metadata(
    *,
    meta_path: Path,
    spec: ProjectRuntimeSpec,
    repo_head_sha: str,
) -> dict[str, Any]:
    payload = {
        "slug": spec.slug,
        "repo_head_sha": repo_head_sha,
        "emitter_name": _SWIFT_SCIP_EMITTER_NAME,
        "emitter_version": _SWIFT_SCIP_EMITTER_VERSION,
        "artifact_origin": "local",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "package_path": "Package.swift",
        "generator_host": socket.gethostname(),
        "source_repo_path": str(spec.repo_path.resolve()),
        "destination_repo_path": str(spec.repo_path.resolve()),
    }
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return payload


def _emit_swift_scip(
    *,
    spec: ProjectRuntimeSpec,
    repo_head_sha: str,
) -> dict[str, Any]:
    fallback_command = _build_macbook_fallback_command(spec)
    missing = [
        command for command in ("xcrun", "swift") if shutil.which(command) is None
    ]
    if missing:
        raise ScipEmitToolchainUnsupported(
            message=f"missing Swift toolchain command(s): {', '.join(missing)}",
            fallback_command=fallback_command,
        )

    emitter_dir = _DEFAULT_SWIFT_EMITTER_DIR
    emitter_bin = emitter_dir / ".build" / "release" / _SWIFT_SCIP_EMITTER_NAME
    scratch_path = spec.repo_path / ".palace-scip-build"
    index_store = spec.repo_path / ".palace-scip-index-store"
    derived_data = spec.repo_path / ".palace-scip-derived-data"
    output_path = spec.repo_path / "scip" / "index.scip"
    meta_path = spec.repo_path / "scip" / "index.scip.meta.json"

    if not emitter_dir.exists():
        raise ProjectAnalyzeCliError(
            f"emitter package dir not found: {emitter_dir}",
            error_code="missing_swift_scip_emitter",
        )

    try:
        if not emitter_bin.exists():
            _run_command(
                [
                    "xcrun",
                    "swift",
                    "build",
                    "-c",
                    "release",
                    "--package-path",
                    str(emitter_dir),
                ]
            )

        shutil.rmtree(scratch_path, ignore_errors=True)
        shutil.rmtree(index_store, ignore_errors=True)
        shutil.rmtree(derived_data, ignore_errors=True)
        (derived_data / "Index.noindex").mkdir(parents=True, exist_ok=True)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        _run_command(
            [
                "xcrun",
                "swift",
                "build",
                "--package-path",
                str(spec.repo_path),
                "--scratch-path",
                str(scratch_path),
                "-Xswiftc",
                "-index-store-path",
                "-Xswiftc",
                str(index_store),
            ]
        )
        shutil.copytree(index_store, derived_data / "Index.noindex" / "DataStore")
        _run_command(
            [
                str(emitter_bin),
                "--derived-data",
                str(derived_data),
                "--project-root",
                str(spec.repo_path),
                "--output",
                str(output_path),
                "--verbose",
            ]
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        raise ScipEmitToolchainUnsupported(
            message=f"local Swift SCIP emit failed: {exc}",
            fallback_command=fallback_command,
        ) from exc

    if not output_path.exists() or output_path.stat().st_size == 0:
        raise ScipEmitToolchainUnsupported(
            message=f"generated SCIP file missing or empty: {output_path}",
            fallback_command=fallback_command,
        )

    metadata = _write_scip_metadata(
        meta_path=meta_path,
        spec=spec,
        repo_head_sha=repo_head_sha,
    )
    return {
        "emitted": True,
        "host_scip_path": str(output_path),
        "meta_path": str(meta_path),
        "metadata": metadata,
    }


def ensure_swift_scip_artifact(
    *,
    spec: ProjectRuntimeSpec,
    emit_scip: str,
) -> dict[str, Any]:
    output_path = spec.repo_path / "scip" / "index.scip"
    meta_path = spec.repo_path / "scip" / "index.scip.meta.json"
    repo_head_sha = _git_head_sha(spec.repo_path)
    metadata = _load_scip_metadata(meta_path)
    stale, reason = swift_scip_metadata_needs_regeneration(
        repo_path=spec.repo_path,
        repo_head_sha=repo_head_sha,
        metadata=metadata,
    )
    usable_index = output_path.exists() and output_path.stat().st_size > 0

    if emit_scip == "always":
        return _emit_swift_scip(spec=spec, repo_head_sha=repo_head_sha)

    if emit_scip == "never":
        if not usable_index or stale:
            raise ProjectAnalyzeCliError(
                "usable SCIP artifact required for --emit-scip=never",
                error_code="missing_required_scip_artifact",
            )
        return {
            "emitted": False,
            "host_scip_path": str(output_path),
            "meta_path": str(meta_path),
            "metadata": metadata,
            "reason": "existing artifact reused",
        }

    if not usable_index or stale:
        return _emit_swift_scip(spec=spec, repo_head_sha=repo_head_sha)

    return {
        "emitted": False,
        "host_scip_path": str(output_path),
        "meta_path": str(meta_path),
        "metadata": metadata,
        "reason": reason,
    }


def _healthz_url(mcp_url: str) -> str:
    if mcp_url.endswith("/mcp"):
        return f"{mcp_url[:-4]}/healthz"
    return f"{mcp_url.rstrip('/')}/healthz"


def _candidate_mcp_urls(mcp_url: str) -> list[str]:
    normalized = mcp_url.rstrip("/")
    candidates = [normalized]
    parsed = urlsplit(normalized)
    if parsed.hostname != "localhost":
        return candidates
    netloc = "127.0.0.1"
    if parsed.port is not None:
        netloc = f"{netloc}:{parsed.port}"
    loopback_url = urlunsplit(
        (parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment)
    ).rstrip("/")
    if loopback_url not in candidates:
        candidates.append(loopback_url)
    return candidates


async def _probe_mcp_session(url: str) -> None:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    async with streamablehttp_client(url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()


def _probe_mcp_url_once(mcp_url: str) -> None:
    healthz_url = _healthz_url(mcp_url)
    with urllib.request.urlopen(healthz_url, timeout=5) as response:
        if not 200 <= response.status < 300:
            raise ProjectAnalyzeCliError(
                f"palace-mcp health check returned http {response.status} at {healthz_url}",
                error_code="mcp_health_timeout",
            )
    asyncio.run(_probe_mcp_session(mcp_url))


def wait_for_mcp_ready(mcp_url: str, *, timeout_seconds: int = 60) -> str:
    candidates = _candidate_mcp_urls(mcp_url)
    deadline = time.time() + timeout_seconds
    last_errors: dict[str, str] = {
        candidate: "not yet checked" for candidate in candidates
    }
    while time.time() < deadline:
        for candidate in candidates:
            try:
                _probe_mcp_url_once(candidate)
                return candidate
            except (
                ProjectAnalyzeCliError,
                urllib.error.URLError,
                ValueError,
                OSError,
            ) as exc:
                last_errors[candidate] = str(exc)
        time.sleep(2)
    error_summary = "; ".join(
        f"{candidate}: {message}" for candidate, message in last_errors.items()
    )
    raise ProjectAnalyzeCliError(
        f"palace-mcp did not become ready via {', '.join(candidates)}: {error_summary}",
        error_code="mcp_health_timeout",
    )


def ensure_project_analyze_runtime(
    *,
    spec: ProjectRuntimeSpec,
    mcp_url: str,
    recreate_palace: bool,
) -> str:
    cmd = [
        "docker",
        "compose",
        "--env-file",
        str(spec.env_file),
        "-f",
        str(spec.compose_files[0]),
        "-f",
        str(spec.compose_files[1]),
        "--profile",
        "review",
        "up",
        "-d",
    ]
    if recreate_palace:
        cmd.append("--force-recreate")
    cmd.extend(["neo4j", "palace-mcp"])
    _run_command(cmd, cwd=_REPO_ROOT)
    return wait_for_mcp_ready(mcp_url)


def build_project_analyze_idempotency_key(
    *,
    slug: str,
    language_profile: str,
    repo_head_sha: str,
    depth: str,
    extractors: list[str],
    container_repo_path: str,
) -> str:
    payload = {
        "slug": slug,
        "language_profile": language_profile,
        "repo_head_sha": repo_head_sha,
        "depth": depth,
        "extractors": extractors,
        "container_repo_path": container_repo_path,
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return digest


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


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
        raise ValueError(
            f"unexpected content type from palace.audit.run: {type(first)}"
        )
    return json.loads(first.text)  # type: ignore[no-any-return]


async def _call_tool(
    *,
    url: str,
    tool_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client
    from mcp.types import TextContent

    async with streamablehttp_client(url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)

    first = result.content[0]
    if not isinstance(first, TextContent):
        raise ValueError(f"unexpected content type from {tool_name}: {type(first)}")
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


async def _run_project_analyze_to_terminal(
    *,
    url: str,
    request_payload: dict[str, Any],
) -> dict[str, Any]:
    start_payload = await _call_tool(
        url=url,
        tool_name="palace.project.analyze",
        arguments=request_payload,
    )
    if not start_payload.get("ok"):
        return start_payload

    run_id = start_payload["run_id"]
    while True:
        status_payload = await _call_tool(
            url=url,
            tool_name="palace.project.analyze_status",
            arguments={"run_id": run_id},
        )
        if not status_payload.get("ok"):
            return status_payload
        status = status_payload.get("status")
        if status == "RESUMABLE":
            resume_payload = await _call_tool(
                url=url,
                tool_name="palace.project.analyze_resume",
                arguments={"run_id": run_id},
            )
            if not resume_payload.get("ok"):
                return resume_payload
        if status not in _PROJECT_ACTIVE_STATUSES:
            return status_payload
        await asyncio.sleep(
            status_payload.get(
                "next_poll_after_seconds", _DEFAULT_PROJECT_ANALYZE_POLL_SECONDS
            )
        )


def _parse_extractors_csv(value: str | None) -> list[str] | None:
    if value is None:
        return None
    items = [item.strip() for item in value.split(",") if item.strip()]
    if not items:
        raise ProjectAnalyzeCliError(
            "--extractors must contain at least one extractor name",
            error_code="empty_extractors_override",
        )
    return items


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


def _cmd_tool_call(args: argparse.Namespace) -> int:
    try:
        tool_name = normalize_tool_name(args.tool_name)
        payload = parse_tool_json_arg(args.json)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    try:
        result = asyncio.run(
            _call_tool(url=args.url, tool_name=tool_name, arguments=payload)
        )
    except Exception as exc:
        print(f"error: MCP call failed: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2))
    if isinstance(result, dict) and result.get("ok") is False:
        return 1
    return 0


def _cmd_project_analyze(args: argparse.Namespace) -> int:
    try:
        repo_path = Path(args.repo_path).expanduser().resolve(strict=True)
        if not repo_path.is_dir():
            raise ProjectAnalyzeCliError(
                f"repo path is not a directory: {repo_path}",
                error_code="invalid_repo_path",
            )
        validate_slug(args.slug)
        extractors = _parse_extractors_csv(args.extractors)
        spec = resolve_project_runtime_spec(
            repo_path=repo_path,
            slug=args.slug,
            language_profile=args.language_profile,
            bundle=args.bundle,
            env_file=Path(args.env_file).expanduser(),
            manifest_path=Path(args.manifest).expanduser(),
            compose_override_path=_DEFAULT_COMPOSE_OVERRIDE_PATH,
            report_out=Path(args.report_out).expanduser() if args.report_out else None,
            summary_out=Path(args.summary_out).expanduser()
            if args.summary_out
            else None,
        )

        ordered_extractors = extractors or list(
            get_ordered_extractors(args.language_profile)
        )
        scip_info: dict[str, Any] | None = None
        env_changed = False
        merged_mapping: dict[str, str] | None = None

        if args.language_profile == "swift_kit":
            scip_info = ensure_swift_scip_artifact(
                spec=spec,
                emit_scip=args.emit_scip,
            )

        runtime_stage_used = False
        runtime_stage_root: str | None = None
        if _host_path_requires_staging(spec.repo_path):
            spec = stage_project_runtime_spec(spec)
            runtime_stage_used = True
            runtime_stage_root = (
                str(spec.host_mount_path) if spec.host_mount_path is not None else None
            )

        if args.language_profile == "swift_kit":
            env_changed, merged_mapping = merge_scip_index_env_mapping(
                env_file=spec.env_file,
                slug=spec.slug,
                container_scip_path=spec.container_scip_path,
            )

        override_changed = write_project_analyze_compose_override(spec)
        recreate_palace = env_changed or override_changed
        resolved_mcp_url = ensure_project_analyze_runtime(
            spec=spec,
            mcp_url=args.url,
            recreate_palace=recreate_palace,
        )

        repo_head_sha = _git_head_sha(spec.repo_path)
        idempotency_key = build_project_analyze_idempotency_key(
            slug=spec.slug,
            language_profile=args.language_profile,
            repo_head_sha=repo_head_sha,
            depth=args.depth,
            extractors=ordered_extractors,
            container_repo_path=spec.container_repo_path,
        )
        request_payload: dict[str, Any] = {
            "slug": spec.slug,
            "parent_mount": spec.parent_mount,
            "relative_path": spec.relative_path,
            "language_profile": args.language_profile,
            "bundle": spec.bundle,
            "depth": args.depth,
            "continue_on_failure": True,
            "idempotency_key": idempotency_key,
            "extractors": ordered_extractors,
        }
        if args.name:
            request_payload["name"] = args.name

        final_payload = asyncio.run(
            _run_project_analyze_to_terminal(
                url=resolved_mcp_url,
                request_payload=request_payload,
            )
        )
        ok = (
            final_payload.get("ok") is True
            and final_payload.get("status") in _PROJECT_SUCCESS_STATUSES
        )
        run_payload = final_payload.get("run") or {}
        report_markdown = run_payload.get("report_markdown")
        if isinstance(report_markdown, str) and report_markdown:
            spec.report_out.parent.mkdir(parents=True, exist_ok=True)
            spec.report_out.write_text(report_markdown, encoding="utf-8")

        summary = {
            "ok": ok,
            "slug": spec.slug,
            "repo_path": str(spec.repo_path),
            "language_profile": args.language_profile,
            "bundle": spec.bundle,
            "emit_scip": args.emit_scip,
            "requested_mcp_url": args.url,
            "mcp_url": resolved_mcp_url,
            "env_file": str(spec.env_file),
            "compose_files": [str(path) for path in spec.compose_files],
            "compose_override_changed": override_changed,
            "env_changed": env_changed,
            "palace_recreated": recreate_palace,
            "runtime_stage_used": runtime_stage_used,
            "runtime_stage_root": runtime_stage_root,
            "parent_mount": spec.parent_mount,
            "relative_path": spec.relative_path,
            "container_repo_path": spec.container_repo_path,
            "container_scip_path": spec.container_scip_path,
            "extractors": ordered_extractors,
            "idempotency_key": idempotency_key,
            "run_id": final_payload.get("run_id"),
            "status": final_payload.get("status"),
            "report_out": str(spec.report_out),
            "summary_out": str(spec.summary_out),
            "scip": scip_info,
            "scip_index_paths": merged_mapping,
            "result": final_payload,
        }
        _write_json(spec.summary_out, summary)

        if isinstance(report_markdown, str) and report_markdown:
            print(report_markdown)
        print(
            json.dumps(
                {
                    "run_id": summary["run_id"],
                    "status": summary["status"],
                    "report_out": summary["report_out"],
                    "summary_out": summary["summary_out"],
                },
                indent=2,
            )
        )
        return 0 if ok else 1
    except ScipEmitToolchainUnsupported as exc:
        fallback_spec = locals().get("spec")
        summary_out = (
            fallback_spec.summary_out
            if isinstance(fallback_spec, ProjectRuntimeSpec)
            else _default_summary_path(args.slug)
        )
        summary = {
            "ok": False,
            "error_code": exc.error_code,
            "message": str(exc),
            "slug": args.slug,
            "repo_path": str(Path(args.repo_path).expanduser()),
            "fallback_command": exc.fallback_command,
            "summary_out": str(summary_out),
        }
        _write_json(summary_out, summary)
        print(json.dumps(summary, indent=2), file=sys.stderr)
        return 1
    except (ProjectAnalyzeCliError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


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

    tool_p = top.add_parser("tool", help="Generic MCP tool commands")
    tool_sub = tool_p.add_subparsers(dest="tool_command", required=True)

    tool_call_p = tool_sub.add_parser("call", help="Call a Palace MCP tool")
    tool_call_p.add_argument(
        "tool_name", help="Tool name, with or without palace. prefix"
    )
    tool_call_p.add_argument(
        "--url", default=_DEFAULT_MCP_URL, help="palace-mcp MCP URL"
    )
    tool_call_p.add_argument(
        "--json",
        default="{}",
        help="JSON object of tool arguments (default: {})",
    )

    project_p = top.add_parser("project", help="Host-side project orchestration")
    project_sub = project_p.add_subparsers(dest="project_command", required=True)

    analyze_p = project_sub.add_parser(
        "analyze",
        help="Start or resume a durable project analysis run from a host repo path",
    )
    analyze_p.add_argument("--repo-path", required=True, help="Absolute host repo path")
    analyze_p.add_argument("--slug", required=True, help="Project slug")
    analyze_p.add_argument(
        "--language-profile",
        required=True,
        help="Existing :Project.language_profile / orchestrator profile name",
    )
    analyze_p.add_argument("--name", help="Optional project display name")
    analyze_p.add_argument("--bundle", help="Optional bundle name")
    analyze_p.add_argument(
        "--extractors",
        help="Optional CSV override for extractor execution order",
    )
    analyze_p.add_argument(
        "--emit-scip",
        default="auto",
        choices=["auto", "always", "never"],
        help="Swift SCIP emission policy",
    )
    analyze_p.add_argument(
        "--depth",
        default="full",
        choices=["quick", "full"],
        help="Analysis depth forwarded to palace.project.analyze",
    )
    analyze_p.add_argument(
        "--url",
        default=_DEFAULT_PROJECT_ANALYZE_URL,
        help="Host-published palace-mcp MCP URL",
    )
    analyze_p.add_argument(
        "--report-out",
        help="Path to write the final markdown report",
    )
    analyze_p.add_argument(
        "--summary-out",
        help="Path to write the machine-readable JSON summary",
    )
    analyze_p.add_argument(
        "--env-file",
        default=str(_DEFAULT_ENV_FILE),
        help="Env file used for docker compose and PALACE_SCIP_INDEX_PATHS merge",
    )
    analyze_p.add_argument(
        "--manifest",
        default=str(_DEFAULT_MANIFEST_PATH),
        help="Bundle manifest used for slug metadata",
    )
    analyze_p.add_argument(
        "--audit",
        action="store_true",
        help="Accepted for smoke-command parity; audit is already part of the MCP workflow",
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "audit":
        if args.audit_command == "run":
            sys.exit(_cmd_audit_run(args))
        if args.audit_command == "launch":
            sys.exit(_cmd_audit_launch(args))
    if args.command == "tool":
        if args.tool_command == "call":
            sys.exit(_cmd_tool_call(args))
    if args.command == "project":
        if args.project_command == "analyze":
            sys.exit(_cmd_project_analyze(args))

    parser.print_help()
    sys.exit(2)


if __name__ == "__main__":
    main()
