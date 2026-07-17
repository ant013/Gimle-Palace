"""Sequential git sync/status wrapper for Palace-managed repositories."""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
from collections.abc import Sequence
from dataclasses import asdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CommandResult:
    argv: list[str]
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class RepositorySpec:
    slug: str
    repo_path: Path
    project: str | None = None
    explicit_ref: str | None = None


@dataclass
class RepoSyncReport:
    slug: str
    project: str | None
    repo_path: str
    branch: str | None = None
    upstream: str | None = None
    compare_ref: str | None = None
    head_before: str | None = None
    head_after: str | None = None
    remote_head: str | None = None
    ahead: int | None = None
    behind: int | None = None
    dirty: bool = False
    untracked_count: int = 0
    status: str = "unknown"
    updated: bool = False
    skipped_reason: str | None = None
    fetch: dict[str, Any] | None = None
    update_command: dict[str, Any] | None = None
    analyze: dict[str, Any] | None = None
    errors: list[str] | None = None


def _run(argv: Sequence[str], *, cwd: Path) -> CommandResult:
    completed = subprocess.run(
        list(argv),
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    return CommandResult(
        argv=list(argv),
        returncode=completed.returncode,
        stdout=completed.stdout.strip(),
        stderr=completed.stderr.strip(),
    )


def _command_payload(result: CommandResult) -> dict[str, Any]:
    return {
        "argv": result.argv,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def _git(repo_path: Path, *args: str) -> CommandResult:
    return _run(["git", *args], cwd=repo_path)


def _git_text(repo_path: Path, *args: str) -> str | None:
    result = _git(repo_path, *args)
    if result.returncode != 0:
        return None
    return result.stdout


def _parse_status(porcelain: str) -> tuple[bool, int]:
    lines = [line for line in porcelain.splitlines() if line]
    untracked = sum(1 for line in lines if line.startswith("??"))
    return bool(lines), untracked


def _parse_ahead_behind(value: str) -> tuple[int | None, int | None]:
    parts = value.split()
    if len(parts) != 2:
        return None, None
    return int(parts[0]), int(parts[1])


def _format_template_command(
    template: str,
    *,
    spec: RepositorySpec,
) -> list[str]:
    formatted = template.format(
        slug=spec.slug,
        project=spec.project or spec.slug,
        repo_path=str(spec.repo_path),
    )
    return shlex.split(formatted)


def sync_repository(
    spec: RepositorySpec,
    *,
    fetch: bool = True,
    dry_run: bool = False,
    analyze_command: str | None = None,
) -> RepoSyncReport:
    report = RepoSyncReport(
        slug=spec.slug,
        project=spec.project,
        repo_path=str(spec.repo_path),
        errors=[],
    )
    if not (spec.repo_path / ".git").exists():
        report.status = "error"
        report.errors = [f"not a git checkout: {spec.repo_path}"]
        return report

    if fetch:
        fetch_result = _git(spec.repo_path, "fetch", "origin", "--prune")
        report.fetch = _command_payload(fetch_result)
        if fetch_result.returncode != 0:
            report.status = "error"
            report.errors = [fetch_result.stderr or "git fetch failed"]
            return report

    report.branch = _git_text(spec.repo_path, "rev-parse", "--abbrev-ref", "HEAD")
    report.head_before = _git_text(spec.repo_path, "rev-parse", "HEAD")
    report.upstream = _git_text(
        spec.repo_path,
        "rev-parse",
        "--abbrev-ref",
        "--symbolic-full-name",
        "@{u}",
    )
    report.compare_ref = spec.explicit_ref or report.upstream
    if report.compare_ref is None:
        report.status = "blocked"
        report.skipped_reason = "compare_ref_missing"
        report.head_after = report.head_before
        return report

    report.remote_head = _git_text(spec.repo_path, "rev-parse", report.compare_ref)
    if report.remote_head is None:
        report.status = "error"
        report.errors = [f"compare ref not found: {report.compare_ref}"]
        report.head_after = report.head_before
        return report

    status_result = _git(spec.repo_path, "status", "--porcelain")
    report.dirty, report.untracked_count = _parse_status(status_result.stdout)
    ahead_behind = _git_text(
        spec.repo_path,
        "rev-list",
        "--left-right",
        "--count",
        f"HEAD...{report.compare_ref}",
    )
    if ahead_behind is not None:
        report.ahead, report.behind = _parse_ahead_behind(ahead_behind)

    if report.ahead == 0 and report.behind == 0:
        report.status = "up_to_date"
    elif report.dirty:
        report.status = "blocked"
        report.skipped_reason = "dirty_worktree"
    elif report.ahead == 0 and report.behind and report.behind > 0:
        report.status = "dry_run_fast_forward" if dry_run else "fast_forwarded"
        if not dry_run:
            merge_result = _git(
                spec.repo_path, "merge", "--ff-only", report.compare_ref
            )
            report.update_command = _command_payload(merge_result)
            if merge_result.returncode != 0:
                report.status = "error"
                report.errors = [merge_result.stderr or "git merge --ff-only failed"]
            else:
                report.updated = True
    elif report.ahead and report.ahead > 0 and report.behind == 0:
        report.status = "ahead"
        report.skipped_reason = "local_ahead"
    else:
        report.status = "blocked"
        report.skipped_reason = "diverged"

    report.head_after = _git_text(spec.repo_path, "rev-parse", "HEAD")

    if analyze_command and report.status in {
        "up_to_date",
        "fast_forwarded",
        "dry_run_fast_forward",
    }:
        argv = _format_template_command(analyze_command, spec=spec)
        if dry_run:
            report.analyze = {"argv": argv, "returncode": None, "dry_run": True}
        else:
            report.analyze = _command_payload(_run(argv, cwd=spec.repo_path))
            if report.analyze["returncode"] != 0:
                report.status = "error"
                report.errors = [report.analyze["stderr"] or "analyze command failed"]

    return report


def sync_repositories(
    specs: Sequence[RepositorySpec],
    *,
    fetch: bool = True,
    dry_run: bool = False,
    analyze_command: str | None = None,
) -> list[RepoSyncReport]:
    reports: list[RepoSyncReport] = []
    for spec in specs:
        reports.append(
            sync_repository(
                spec,
                fetch=fetch,
                dry_run=dry_run,
                analyze_command=analyze_command,
            )
        )
    return reports


def render_markdown(reports: Sequence[RepoSyncReport]) -> str:
    lines = [
        "# Palace Sync Status",
        "",
        "| Repo | Status | Branch | Compare ref | Ahead | Behind | Dirty | Updated | Reason |",
        "| --- | --- | --- | --- | ---: | ---: | --- | --- | --- |",
    ]
    for report in reports:
        lines.append(
            "| {repo} | {status} | {branch} | {compare_ref} | {ahead} | {behind} | {dirty} | {updated} | {reason} |".format(
                repo=report.slug,
                status=report.status,
                branch=report.branch or "",
                compare_ref=report.compare_ref or "",
                ahead="" if report.ahead is None else report.ahead,
                behind="" if report.behind is None else report.behind,
                dirty="yes" if report.dirty else "no",
                updated="yes" if report.updated else "no",
                reason=report.skipped_reason or "",
            )
        )
    return "\n".join(lines) + "\n"


def reports_payload(reports: Sequence[RepoSyncReport]) -> dict[str, Any]:
    return {"repositories": [asdict(report) for report in reports]}


def _parse_key_values(values: list[str] | None) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for value in values or []:
        key, separator, raw = value.partition("=")
        if not separator or not key or not raw:
            raise argparse.ArgumentTypeError(f"expected KEY=VALUE, got: {value}")
        parsed[key] = raw
    return parsed


def _discover_repo_root(root: Path) -> list[RepositorySpec]:
    specs: list[RepositorySpec] = []
    for child in sorted(root.iterdir()):
        if (child / ".git").exists():
            specs.append(RepositorySpec(slug=child.name, repo_path=child))
    return specs


def _parse_repo_specs(
    repo_args: list[str] | None,
    repo_root: Path | None,
    explicit_refs: dict[str, str],
    projects: dict[str, str],
) -> list[RepositorySpec]:
    specs = _discover_repo_root(repo_root) if repo_root else []
    for raw in repo_args or []:
        slug, separator, path = raw.partition("=")
        if not separator or not slug or not path:
            raise argparse.ArgumentTypeError(f"expected slug=/path/to/repo, got: {raw}")
        specs.append(RepositorySpec(slug=slug, repo_path=Path(path)))
    return [
        RepositorySpec(
            slug=spec.slug,
            repo_path=spec.repo_path,
            project=projects.get(spec.slug, spec.project),
            explicit_ref=explicit_refs.get(spec.slug, spec.explicit_ref),
        )
        for spec in specs
    ]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Sequentially fetch, status-check, and fast-forward Palace-managed "
            "git repositories with explicit JSON/Markdown evidence."
        )
    )
    parser.add_argument("--repo", action="append", help="Repo spec: slug=/path/to/repo")
    parser.add_argument("--repo-root", help="Discover immediate git children")
    parser.add_argument(
        "--explicit-ref",
        action="append",
        help="Per-repo compare ref for repos without upstream: slug=origin/develop",
    )
    parser.add_argument(
        "--project",
        action="append",
        help="Optional Palace project slug mapping: repo-slug=project-slug",
    )
    parser.add_argument("--no-fetch", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--analyze-command",
        help=(
            "Optional command template run after clean/up-to-date/updated repos. "
            "Supports {slug}, {project}, and {repo_path}."
        ),
    )
    parser.add_argument("--output-json", help="Write JSON report to path")
    parser.add_argument("--output-md", help="Write Markdown report to path")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero if any repo is error or blocked.",
    )
    return parser


def _run_cli(args: argparse.Namespace) -> int:
    explicit_refs = _parse_key_values(args.explicit_ref)
    projects = _parse_key_values(args.project)
    specs = _parse_repo_specs(
        args.repo,
        Path(args.repo_root) if args.repo_root else None,
        explicit_refs,
        projects,
    )
    reports = sync_repositories(
        specs,
        fetch=not args.no_fetch,
        dry_run=args.dry_run,
        analyze_command=args.analyze_command,
    )
    payload = reports_payload(reports)
    json_text = json.dumps(payload, indent=2)
    md_text = render_markdown(reports)
    if args.output_json:
        Path(args.output_json).write_text(json_text + "\n", encoding="utf-8")
    if args.output_md:
        Path(args.output_md).write_text(md_text, encoding="utf-8")
    if not args.output_json and not args.output_md:
        print(json_text)
    if args.strict and any(report.status in {"error", "blocked"} for report in reports):
        return 1
    return 0


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    raise SystemExit(_run_cli(args))


if __name__ == "__main__":
    main()
