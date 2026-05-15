from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

import palace_mcp.cli as cli


def test_project_analyze_parser_defaults_to_host_port_8080() -> None:
    parser = cli.build_parser()
    args = parser.parse_args(
        [
            "project",
            "analyze",
            "--repo-path",
            "/tmp/TronKit.Swift",
            "--slug",
            "tron-kit",
            "--language-profile",
            "swift_kit",
        ]
    )
    assert args.url == "http://localhost:8080/mcp"


def test_stage_project_runtime_spec_switches_to_stage_mount(
    tmp_path: Path, monkeypatch
) -> None:
    repo_path = tmp_path / "TronKit.Swift"
    repo_path.mkdir()
    spec = cli.ProjectRuntimeSpec(
        repo_path=repo_path,
        slug="tron-kit",
        language_profile="swift_kit",
        bundle=None,
        parent_mount="hs",
        relative_path="TronKit.Swift",
        container_repo_path="/repos-hs/TronKit.Swift",
        container_scip_path="/repos-hs/TronKit.Swift/scip/index.scip",
        env_file=tmp_path / ".env",
        compose_override_path=tmp_path / "docker-compose.project-analyze.yml",
        report_out=tmp_path / "report.md",
        summary_out=tmp_path / "summary.json",
        host_mount_path=None,
        container_mount_path=None,
    )
    copied: list[tuple[Path, Path]] = []
    monkeypatch.setattr(
        cli,
        "_copy_runtime_stage",
        lambda source, staged: copied.append((source, staged)),
    )

    staged_spec = cli.stage_project_runtime_spec(
        spec,
        stage_root=tmp_path / "project-analyze-mounts",
    )

    assert copied == [
        (
            repo_path,
            tmp_path / "project-analyze-mounts" / "hs-stage" / "TronKit.Swift",
        )
    ]
    assert staged_spec.repo_path == repo_path
    assert staged_spec.parent_mount == "hs-stage"
    assert staged_spec.container_mount_path == "/repos-hs-stage"
    assert staged_spec.container_repo_path == "/repos-hs-stage/TronKit.Swift"
    assert (
        staged_spec.container_scip_path
        == "/repos-hs-stage/TronKit.Swift/scip/index.scip"
    )
    assert (
        staged_spec.host_mount_path == tmp_path / "project-analyze-mounts" / "hs-stage"
    )


def test_wait_for_mcp_ready_falls_back_to_loopback(monkeypatch) -> None:
    attempts: list[str] = []

    def fake_probe(url: str) -> None:
        attempts.append(url)
        if url == "http://localhost:8080/mcp":
            raise ValueError("non-json response")

    monkeypatch.setattr(cli, "_probe_mcp_url_once", fake_probe)

    resolved = cli.wait_for_mcp_ready("http://localhost:8080/mcp", timeout_seconds=1)

    assert resolved == "http://127.0.0.1:8080/mcp"
    assert attempts == [
        "http://localhost:8080/mcp",
        "http://127.0.0.1:8080/mcp",
    ]


def test_merge_scip_index_env_mapping_preserves_existing_entries(
    tmp_path: Path,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "OPENAI_API_KEY=sk-test\n"
        'PALACE_SCIP_INDEX_PATHS={"evm-kit":"/repos-hs/EvmKit.Swift/scip/index.scip"}\n',
        encoding="utf-8",
    )

    changed, merged = cli.merge_scip_index_env_mapping(
        env_file=env_file,
        slug="tron-kit",
        container_scip_path="/repos-hs/TronKit.Swift/scip/index.scip",
    )

    assert changed is True
    assert merged == {
        "evm-kit": "/repos-hs/EvmKit.Swift/scip/index.scip",
        "tron-kit": "/repos-hs/TronKit.Swift/scip/index.scip",
    }
    written = env_file.read_text(encoding="utf-8")
    assert "OPENAI_API_KEY=sk-test" in written
    assert (
        'PALACE_SCIP_INDEX_PATHS={"evm-kit":"/repos-hs/EvmKit.Swift/scip/index.scip","tron-kit":"/repos-hs/TronKit.Swift/scip/index.scip"}'
        in written
    )


def test_merge_scip_index_env_mapping_rejects_invalid_json(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "PALACE_SCIP_INDEX_PATHS={not-json}\n",
        encoding="utf-8",
    )

    try:
        cli.merge_scip_index_env_mapping(
            env_file=env_file,
            slug="tron-kit",
            container_scip_path="/repos-hs/TronKit.Swift/scip/index.scip",
        )
    except cli.ProjectAnalyzeCliError as exc:
        assert exc.error_code == "invalid_scip_index_env_json"
    else:
        raise AssertionError("expected ProjectAnalyzeCliError")


def test_swift_scip_metadata_needs_regeneration_on_head_mismatch(
    tmp_path: Path,
) -> None:
    repo_path = tmp_path / "TronKit.Swift"
    repo_path.mkdir()
    stale, reason = cli.swift_scip_metadata_needs_regeneration(
        repo_path=repo_path,
        repo_head_sha="abc123",
        metadata={
            "repo_head_sha": "old",
            "emitter_name": "palace-swift-scip-emit-cli",
            "emitter_version": "2026-05-15",
            "package_path": "Package.swift",
            "destination_repo_path": str(repo_path.resolve()),
        },
    )
    assert stale is True
    assert reason == "repo_head_sha mismatch"


def test_swift_scip_metadata_needs_regeneration_on_source_repo_path_mismatch(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_path = tmp_path / "TronKit.Swift"
    repo_path.mkdir()
    monkeypatch.setattr(cli.socket, "gethostname", lambda: "local-host")

    stale, reason = cli.swift_scip_metadata_needs_regeneration(
        repo_path=repo_path,
        repo_head_sha="abc123",
        metadata={
            "repo_head_sha": "abc123",
            "emitter_name": "palace-swift-scip-emit-cli",
            "emitter_version": "2026-05-15",
            "package_path": "Package.swift",
            "generator_host": "local-host",
            "source_repo_path": "/different/source",
            "destination_repo_path": str(repo_path.resolve()),
        },
    )

    assert stale is True
    assert reason == "source_repo_path mismatch"


def test_swift_scip_metadata_needs_regeneration_on_generator_host_mismatch(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_path = tmp_path / "TronKit.Swift"
    repo_path.mkdir()
    monkeypatch.setattr(cli.socket, "gethostname", lambda: "current-host")

    stale, reason = cli.swift_scip_metadata_needs_regeneration(
        repo_path=repo_path,
        repo_head_sha="abc123",
        metadata={
            "repo_head_sha": "abc123",
            "emitter_name": "palace-swift-scip-emit-cli",
            "emitter_version": "2026-05-15",
            "package_path": "Package.swift",
            "generator_host": "different-host",
            "source_repo_path": str(repo_path.resolve()),
            "destination_repo_path": str(repo_path.resolve()),
        },
    )

    assert stale is True
    assert reason == "generator_host mismatch"


def test_swift_scip_metadata_accepts_remote_copy_provenance(
    tmp_path: Path,
) -> None:
    repo_path = tmp_path / "TronKit.Swift"
    repo_path.mkdir()

    stale, reason = cli.swift_scip_metadata_needs_regeneration(
        repo_path=repo_path,
        repo_head_sha="abc123",
        metadata={
            "repo_head_sha": "abc123",
            "emitter_name": "palace-swift-scip-emit-cli",
            "emitter_version": "2026-05-15",
            "artifact_origin": "remote_copy",
            "package_path": "Package.swift",
            "generator_host": "macbook-host",
            "source_repo_path": "/Users/ant013/Ios/HorizontalSystems/TronKit.Swift",
            "destination_repo_path": str(repo_path.resolve()),
        },
    )

    assert stale is False
    assert reason == "metadata current (remote_copy)"


def test_build_macbook_fallback_command_uses_macbook_repo_path() -> None:
    spec = cli.ProjectRuntimeSpec(
        repo_path=Path("/Users/Shared/Ios/HorizontalSystems/TronKit.Swift"),
        slug="tron-kit",
        language_profile="swift_kit",
        bundle=None,
        parent_mount="hs",
        relative_path="TronKit.Swift",
        container_repo_path="/repos-hs/TronKit.Swift",
        container_scip_path="/repos-hs/TronKit.Swift/scip/index.scip",
        env_file=Path("/tmp/.env"),
        compose_override_path=Path("/tmp/docker-compose.project-analyze.yml"),
        report_out=Path("/tmp/report.md"),
        summary_out=Path("/tmp/summary.json"),
        host_mount_path=None,
        container_mount_path=None,
    )

    command = cli._build_macbook_fallback_command(spec)

    assert "--repo-path /Users/ant013/Ios/HorizontalSystems/TronKit.Swift" in command
    assert "/Users/Shared/Ios/HorizontalSystems/TronKit.Swift" not in command


def test_project_analyze_writes_summary_and_report(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_path = tmp_path / "TronKit.Swift"
    repo_path.mkdir()
    (repo_path / "Package.swift").write_text("// swift-tools-version: 5.9\n")
    env_file = tmp_path / ".env"
    env_file.write_text("OPENAI_API_KEY=sk-test\n", encoding="utf-8")
    report_out = tmp_path / "report.md"
    summary_out = tmp_path / "summary.json"

    spec = cli.ProjectRuntimeSpec(
        repo_path=repo_path,
        slug="tron-kit",
        language_profile="swift_kit",
        bundle="uw-ios",
        parent_mount="hs",
        relative_path="TronKit.Swift",
        container_repo_path="/repos-hs/TronKit.Swift",
        container_scip_path="/repos-hs/TronKit.Swift/scip/index.scip",
        env_file=env_file,
        compose_override_path=tmp_path / "docker-compose.project-analyze.yml",
        report_out=report_out,
        summary_out=summary_out,
        host_mount_path=None,
        container_mount_path=None,
    )

    monkeypatch.setattr(cli, "resolve_project_runtime_spec", lambda **_: spec)
    monkeypatch.setattr(
        cli,
        "ensure_swift_scip_artifact",
        lambda **_: {
            "emitted": False,
            "host_scip_path": str(repo_path / "scip" / "index.scip"),
            "meta_path": str(repo_path / "scip" / "index.scip.meta.json"),
            "metadata": {"repo_head_sha": "abc123"},
        },
    )
    monkeypatch.setattr(
        cli,
        "merge_scip_index_env_mapping",
        lambda **_: (
            True,
            {"tron-kit": "/repos-hs/TronKit.Swift/scip/index.scip"},
        ),
    )
    monkeypatch.setattr(
        cli, "write_project_analyze_compose_override", lambda _spec: True
    )
    runtime_calls: list[bool] = []
    monkeypatch.setattr(
        cli,
        "ensure_project_analyze_runtime",
        lambda **kwargs: runtime_calls.append(kwargs["recreate_palace"]),
    )
    monkeypatch.setattr(cli, "_git_head_sha", lambda _path: "abc123")

    async def _fake_run_project_analyze_to_terminal(**_: object) -> dict[str, object]:
        return {
            "ok": True,
            "run_id": "run-123",
            "status": "SUCCEEDED_WITH_FAILURES",
            "run": {
                "report_markdown": "# AnalysisRun run-123\n",
                "overview": {"OK": 17},
                "audit": {"ok": False, "error_code": "STALE_EXTERNAL_RUN"},
                "next_actions": ["resume only if extractors change"],
            },
        }

    monkeypatch.setattr(
        cli,
        "_run_project_analyze_to_terminal",
        _fake_run_project_analyze_to_terminal,
    )
    monkeypatch.setattr(
        cli,
        "get_ordered_extractors",
        lambda _profile: ("symbol_index_swift", "hotspot"),
    )
    monkeypatch.setattr(cli, "_host_path_requires_staging", lambda _path: False)

    args = SimpleNamespace(
        repo_path=str(repo_path),
        slug="tron-kit",
        language_profile="swift_kit",
        bundle="uw-ios",
        name=None,
        extractors=None,
        emit_scip="auto",
        depth="full",
        url="http://localhost:8080/mcp",
        report_out=str(report_out),
        summary_out=str(summary_out),
        env_file=str(env_file),
        manifest=str(tmp_path / "missing-manifest.json"),
        audit=True,
    )

    exit_code = cli._cmd_project_analyze(args)

    assert exit_code == 0
    assert runtime_calls == [True]
    assert report_out.read_text(encoding="utf-8") == "# AnalysisRun run-123\n"
    summary = json.loads(summary_out.read_text(encoding="utf-8"))
    assert summary["ok"] is True
    assert summary["palace_recreated"] is True
    assert summary["run_id"] == "run-123"
    assert summary["compose_override_changed"] is True
    assert summary["env_changed"] is True
    assert summary["runtime_stage_used"] is False


def test_host_path_requires_staging_when_docker_host_targets_colima_socket(
    monkeypatch,
) -> None:
    monkeypatch.setattr(cli, "_docker_context_name", lambda: "default")
    monkeypatch.setenv(
        "DOCKER_HOST",
        f"unix://{Path.home()}/.colima/default/docker.sock",
    )

    assert (
        cli._host_path_requires_staging(
            Path("/Users/Shared/Ios/HorizontalSystems/TronKit.Swift")
        )
        is True
    )


def test_project_analyze_full_run_uses_staged_paths_for_colima_docker_host(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_path = tmp_path / "TronKit.Swift"
    repo_path.mkdir()
    (repo_path / "Package.swift").write_text("// swift-tools-version: 5.9\n")
    env_file = tmp_path / ".env"
    env_file.write_text("OPENAI_API_KEY=sk-test\n", encoding="utf-8")
    summary_out = tmp_path / "summary.json"
    report_out = tmp_path / "report.md"
    override_path = tmp_path / "docker-compose.project-analyze.yml"

    spec = cli.ProjectRuntimeSpec(
        repo_path=repo_path,
        slug="tron-kit",
        language_profile="swift_kit",
        bundle="uw-ios",
        parent_mount="hs",
        relative_path="TronKit.Swift",
        container_repo_path="/repos-hs/TronKit.Swift",
        container_scip_path="/repos-hs/TronKit.Swift/scip/index.scip",
        env_file=env_file,
        compose_override_path=override_path,
        report_out=report_out,
        summary_out=summary_out,
        host_mount_path=None,
        container_mount_path=None,
    )

    monkeypatch.setattr(cli, "resolve_project_runtime_spec", lambda **_: spec)
    monkeypatch.setattr(cli, "_docker_context_name", lambda: "default")
    monkeypatch.setenv(
        "DOCKER_HOST",
        f"unix://{Path.home()}/.colima/default/docker.sock",
    )
    copied: list[tuple[Path, Path]] = []
    monkeypatch.setattr(
        cli,
        "_copy_runtime_stage",
        lambda source, staged: copied.append((source, staged)),
    )
    real_stage_project_runtime_spec = cli.stage_project_runtime_spec
    monkeypatch.setattr(
        cli,
        "stage_project_runtime_spec",
        lambda current_spec: real_stage_project_runtime_spec(
            current_spec,
            stage_root=tmp_path / "project-analyze-mounts",
        ),
    )
    monkeypatch.setattr(
        cli,
        "ensure_swift_scip_artifact",
        lambda **_: {
            "emitted": False,
            "host_scip_path": str(repo_path / "scip" / "index.scip"),
            "meta_path": str(repo_path / "scip" / "index.scip.meta.json"),
            "metadata": {"repo_head_sha": "abc123"},
        },
    )
    monkeypatch.setattr(
        cli,
        "ensure_project_analyze_runtime",
        lambda **kwargs: kwargs["mcp_url"],
    )
    monkeypatch.setattr(cli, "_git_head_sha", lambda _path: "abc123")
    monkeypatch.setattr(
        cli,
        "get_ordered_extractors",
        lambda _profile: ("symbol_index_swift", "code_ownership"),
    )

    seen_payloads: list[dict[str, object]] = []

    async def _fake_run_project_analyze_to_terminal(
        *,
        url: str,
        request_payload: dict[str, object],
    ) -> dict[str, object]:
        seen_payloads.append(request_payload)
        return {
            "ok": True,
            "run_id": "run-123",
            "status": "SUCCEEDED_WITH_FAILURES",
            "run": {
                "report_markdown": "# AnalysisRun run-123\n",
                "overview": {"OK": 2},
                "audit": {"ok": False, "error_code": "STALE_EXTERNAL_RUN"},
                "next_actions": [],
            },
        }

    monkeypatch.setattr(
        cli,
        "_run_project_analyze_to_terminal",
        _fake_run_project_analyze_to_terminal,
    )

    args = SimpleNamespace(
        repo_path=str(repo_path),
        slug="tron-kit",
        language_profile="swift_kit",
        bundle="uw-ios",
        name=None,
        extractors=None,
        emit_scip="never",
        depth="full",
        url="http://localhost:8080/mcp",
        report_out=str(report_out),
        summary_out=str(summary_out),
        env_file=str(env_file),
        manifest=str(tmp_path / "missing-manifest.json"),
        audit=True,
    )

    exit_code = cli._cmd_project_analyze(args)

    assert exit_code == 0
    assert copied == [
        (
            repo_path,
            tmp_path / "project-analyze-mounts" / "hs-stage" / "TronKit.Swift",
        )
    ]
    assert len(seen_payloads) == 1
    assert seen_payloads[0]["parent_mount"] == "hs-stage"
    assert seen_payloads[0]["relative_path"] == "TronKit.Swift"
    assert seen_payloads[0]["language_profile"] == "swift_kit"
    assert seen_payloads[0]["bundle"] == "uw-ios"
    assert seen_payloads[0]["depth"] == "full"
    assert seen_payloads[0]["extractors"] == [
        "symbol_index_swift",
        "code_ownership",
    ]
    summary = json.loads(summary_out.read_text(encoding="utf-8"))
    assert summary["runtime_stage_used"] is True
    assert summary["runtime_stage_root"] == str(
        tmp_path / "project-analyze-mounts" / "hs-stage"
    )
    assert summary["parent_mount"] == "hs-stage"
    assert summary["container_repo_path"] == "/repos-hs-stage/TronKit.Swift"
    assert (
        summary["container_scip_path"]
        == "/repos-hs-stage/TronKit.Swift/scip/index.scip"
    )
    assert summary["scip_index_paths"] == {
        "tron-kit": "/repos-hs-stage/TronKit.Swift/scip/index.scip"
    }
    assert "/repos-hs/TronKit.Swift" not in summary_out.read_text(encoding="utf-8")
    assert (
        override_path.read_text(encoding="utf-8")
        == "services:\n"
        "  palace-mcp:\n"
        "    volumes:\n"
        f"      - {tmp_path / 'project-analyze-mounts' / 'hs-stage'}:/repos-hs-stage:ro\n"
    )


@pytest.mark.asyncio
async def test_run_project_analyze_to_terminal_recovers_after_status_disconnect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str, dict[str, object]]] = []

    async def fake_call_tool(
        *,
        url: str,
        tool_name: str,
        arguments: dict[str, object],
    ) -> dict[str, object]:
        calls.append((url, tool_name, arguments))
        if tool_name == "palace.project.analyze":
            return {"ok": True, "run_id": "run-123"}
        if tool_name == "palace.project.analyze_status":
            attempt = sum(
                1 for _url, seen_tool_name, _args in calls
                if seen_tool_name == "palace.project.analyze_status"
            )
            if attempt == 1:
                raise httpx.RemoteProtocolError(
                    "Server disconnected without sending a response."
                )
            return {
                "ok": True,
                "run_id": "run-123",
                "status": "SUCCEEDED",
                "next_poll_after_seconds": 0,
            }
        raise AssertionError(f"unexpected tool call: {tool_name}")

    recovered_urls: list[tuple[str, int]] = []

    def fake_wait_for_mcp_ready(url: str, *, timeout_seconds: int = 60) -> str:
        recovered_urls.append((url, timeout_seconds))
        return "http://127.0.0.1:8080/mcp"

    monkeypatch.setattr(cli, "_call_tool", fake_call_tool)
    monkeypatch.setattr(cli, "wait_for_mcp_ready", fake_wait_for_mcp_ready)

    payload = await cli._run_project_analyze_to_terminal(
        url="http://localhost:8080/mcp",
        request_payload={"slug": "tron-kit"},
    )

    assert payload["ok"] is True
    assert payload["status"] == "SUCCEEDED"
    assert recovered_urls == [
        (
            "http://localhost:8080/mcp",
            cli._DEFAULT_PROJECT_ANALYZE_RECOVERY_TIMEOUT_SECONDS,
        )
    ]
    assert [tool_name for _url, tool_name, _arguments in calls] == [
        "palace.project.analyze",
        "palace.project.analyze_status",
        "palace.project.analyze_status",
    ]
    assert calls[-1][0] == "http://127.0.0.1:8080/mcp"


def test_project_analyze_transport_failure_writes_structured_summary(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_path = tmp_path / "tron-kit"
    repo_path.mkdir()
    env_file = tmp_path / ".env"
    env_file.write_text("OPENAI_API_KEY=sk-test\n", encoding="utf-8")
    summary_out = tmp_path / "summary.json"
    report_out = tmp_path / "report.md"

    spec = cli.ProjectRuntimeSpec(
        repo_path=repo_path,
        slug="tron-kit",
        language_profile="python_service",
        bundle=None,
        parent_mount="repos",
        relative_path="tron-kit",
        container_repo_path="/repos/repos/tron-kit",
        container_scip_path="/repos/repos/tron-kit/scip/index.scip",
        env_file=env_file,
        compose_override_path=tmp_path / "docker-compose.project-analyze.yml",
        report_out=report_out,
        summary_out=summary_out,
        host_mount_path=repo_path.parent,
        container_mount_path="/repos/repos",
    )

    monkeypatch.setattr(cli, "resolve_project_runtime_spec", lambda **_: spec)
    monkeypatch.setattr(
        cli,
        "ensure_project_analyze_runtime",
        lambda **kwargs: kwargs["mcp_url"],
    )
    monkeypatch.setattr(cli, "_git_head_sha", lambda _path: "abc123")
    monkeypatch.setattr(
        cli,
        "get_ordered_extractors",
        lambda _profile: ("symbol_index_python",),
    )
    monkeypatch.setattr(cli, "_host_path_requires_staging", lambda _path: False)

    async def fake_run_project_analyze_to_terminal(**_: object) -> dict[str, object]:
        raise cli.ProjectAnalyzeCliError(
            "palace.project.analyze_status failed after 3 attempts: Server disconnected without sending a response.",
            error_code="project_analyze_transport_error",
        )

    monkeypatch.setattr(
        cli,
        "_run_project_analyze_to_terminal",
        fake_run_project_analyze_to_terminal,
    )

    args = SimpleNamespace(
        repo_path=str(repo_path),
        slug="tron-kit",
        language_profile="python_service",
        bundle=None,
        name=None,
        extractors=None,
        emit_scip="never",
        depth="full",
        url="http://localhost:8080/mcp",
        report_out=str(report_out),
        summary_out=str(summary_out),
        env_file=str(env_file),
        manifest=str(tmp_path / "missing-manifest.json"),
        audit=True,
    )

    exit_code = cli._cmd_project_analyze(args)

    assert exit_code == 1
    summary = json.loads(summary_out.read_text(encoding="utf-8"))
    assert summary["ok"] is False
    assert summary["error_code"] == "project_analyze_transport_error"
    assert summary["requested_mcp_url"] == "http://localhost:8080/mcp"
    assert summary["parent_mount"] == "repos"
    assert summary["container_repo_path"] == "/repos/repos/tron-kit"
    assert summary["summary_out"] == str(summary_out)


def test_project_analyze_toolchain_unsupported_writes_structured_summary(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_path = tmp_path / "TronKit.Swift"
    repo_path.mkdir()
    env_file = tmp_path / ".env"
    summary_out = tmp_path / "summary.json"
    spec = cli.ProjectRuntimeSpec(
        repo_path=repo_path,
        slug="tron-kit",
        language_profile="swift_kit",
        bundle=None,
        parent_mount="hs",
        relative_path="TronKit.Swift",
        container_repo_path="/repos-hs/TronKit.Swift",
        container_scip_path="/repos-hs/TronKit.Swift/scip/index.scip",
        env_file=env_file,
        compose_override_path=tmp_path / "docker-compose.project-analyze.yml",
        report_out=tmp_path / "report.md",
        summary_out=summary_out,
        host_mount_path=None,
        container_mount_path=None,
    )
    monkeypatch.setattr(cli, "resolve_project_runtime_spec", lambda **_: spec)
    monkeypatch.setattr(
        cli,
        "ensure_swift_scip_artifact",
        lambda **_: (_ for _ in ()).throw(
            cli.ScipEmitToolchainUnsupported(
                message="missing Swift toolchain command(s): xcrun",
                fallback_command="bash paperclips/scripts/scip_emit_swift_kit.sh tron-kit",
            )
        ),
    )
    args = SimpleNamespace(
        repo_path=str(repo_path),
        slug="tron-kit",
        language_profile="swift_kit",
        bundle=None,
        name=None,
        extractors=None,
        emit_scip="auto",
        depth="full",
        url="http://localhost:8080/mcp",
        report_out=None,
        summary_out=str(summary_out),
        env_file=str(env_file),
        manifest=str(tmp_path / "missing-manifest.json"),
        audit=True,
    )

    exit_code = cli._cmd_project_analyze(args)

    assert exit_code == 1
    summary = json.loads(summary_out.read_text(encoding="utf-8"))
    assert summary["error_code"] == "SCIP_EMIT_TOOLCHAIN_UNSUPPORTED"
    assert "scip_emit_swift_kit.sh tron-kit" in summary["fallback_command"]
