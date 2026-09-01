"""Behavior tests for the Glitcherry Paperclip Project reconciler."""

from __future__ import annotations

import json
import os
import subprocess
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import yaml


REPO = Path(__file__).resolve().parents[2]
PROJECT = REPO / "paperclips" / "projects" / "glitcherry-android"
SCRIPT = PROJECT / "scripts" / "reconcile-paperclip-project.sh"
MANIFEST = PROJECT / "paperclip-agent-assembly.yaml"
AGENT_NAMES = [
    "GlitcherryCEO",
    "GlitcherryCTO",
    "GlitcherryAndroidEngineer",
    "GlitcherryMediaPipelineEngineer",
    "GlitcherryCodeReviewer",
    "GlitcherryQAEngineer",
]
COMPANY_ID = "00000000-0000-4000-8000-000000000001"
PROJECT_ID = "00000000-0000-4000-8000-000000000100"


class _PaperclipState:
    def __init__(self) -> None:
        self.projects: list[dict] = []
        self.workspaces: list[dict] = []
        self.project_posts = 0
        self.workspace_posts = 0
        self.project_patches: list[dict] = []


class _Handler(BaseHTTPRequestHandler):
    server: "_Server"

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(length) or b"{}")

    def _json(self, status: int, value: object) -> None:
        payload = json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802
        state = self.server.state
        if self.path == f"/api/companies/{COMPANY_ID}/projects":
            self._json(200, state.projects)
        elif self.path == f"/api/projects/{PROJECT_ID}":
            project = next((item for item in state.projects if item["id"] == PROJECT_ID), None)
            self._json(200 if project else 404, project or {"error": "not found"})
        elif self.path == f"/api/projects/{PROJECT_ID}/workspaces":
            self._json(200, state.workspaces)
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        state = self.server.state
        body = self._body()
        if self.path == f"/api/companies/{COMPANY_ID}/projects":
            state.project_posts += 1
            project = {"id": PROJECT_ID, "companyId": COMPANY_ID, **body}
            state.projects.append(project)
            self._json(201, project)
            return
        if self.path == f"/api/projects/{PROJECT_ID}/workspaces":
            state.workspace_posts += 1
            workspace = {
                "id": str(uuid.UUID(int=0x200 + state.workspace_posts)),
                "projectId": PROJECT_ID,
                "companyId": COMPANY_ID,
                **body,
            }
            state.workspaces.append(workspace)
            self._json(201, workspace)
            return
        self._json(404, {"error": "not found"})

    def do_PATCH(self) -> None:  # noqa: N802
        state = self.server.state
        if self.path != f"/api/projects/{PROJECT_ID}":
            self._json(404, {"error": "not found"})
            return
        body = self._body()
        state.project_patches.append(body)
        state.projects[0].update(body)
        self._json(200, state.projects[0])


class _Server(ThreadingHTTPServer):
    def __init__(self, state: _PaperclipState):
        super().__init__(("127.0.0.1", 0), _Handler)
        self.state = state


def _write_private(path: Path, value: str) -> None:
    path.write_text(value)
    path.chmod(0o600)


def _fixture(tmp_path: Path) -> dict[str, object]:
    team_root = tmp_path / "runs"
    for name in AGENT_NAMES:
        workspace = team_root / name / "workspace"
        workspace.mkdir(parents=True)
        (workspace / "AGENTS.md").write_text(f"# {name}\n")

    paths = tmp_path / "paths.yaml"
    _write_private(
        paths,
        f"schemaVersion: 2\nteam_workspace_root: {team_root}\n",
    )
    bindings = tmp_path / "bindings.yaml"
    agent_lines = "\n".join(
        f"  {name}: {uuid.UUID(int=index + 10)}"
        for index, name in enumerate(AGENT_NAMES)
    )
    _write_private(
        bindings,
        f"schemaVersion: 2\ncompany_id: {COMPANY_ID}\nagents:\n{agent_lines}\n",
    )
    return {"team_root": team_root, "paths": paths, "bindings": bindings}


def _run(
    fixture: dict[str, object], state: _PaperclipState
) -> subprocess.CompletedProcess[str]:
    server = _Server(state)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        return subprocess.run(
            [
                "bash",
                str(SCRIPT),
                "--manifest",
                str(MANIFEST),
                "--paths",
                str(fixture["paths"]),
                "--bindings",
                str(fixture["bindings"]),
            ],
            check=False,
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "HOME": str(Path(fixture["team_root"]).parent / "home"),
                "PAPERCLIP_API_URL": f"http://127.0.0.1:{server.server_port}",
                "PAPERCLIP_API_KEY": "test-only-secret",
            },
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_reconciler_creates_exact_project_and_six_workspaces_idempotently(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    state = _PaperclipState()

    first = _run(fixture, state)
    assert first.returncode == 0, first.stderr
    assert state.project_posts == 1
    assert state.workspace_posts == 6
    assert len(state.projects) == 1
    assert [workspace["name"] for workspace in state.workspaces] == AGENT_NAMES
    assert state.project_patches[-1]["executionWorkspacePolicy"] == {
        "enabled": True,
        "defaultMode": "shared_workspace",
        "allowIssueOverride": True,
        "defaultProjectWorkspaceId": state.workspaces[1]["id"],
    }

    bindings = yaml.safe_load(Path(fixture["bindings"]).read_text())
    assert bindings["project_id"] == PROJECT_ID
    assert set(bindings["workspaces"]) == set(AGENT_NAMES)
    assert Path(fixture["bindings"]).stat().st_mode & 0o777 == 0o600

    second = _run(fixture, state)
    assert second.returncode == 0, second.stderr
    assert state.project_posts == 1
    assert state.workspace_posts == 6
    assert len(state.projects) == 1
    assert len(state.workspaces) == 6
    assert "test-only-secret" not in first.stdout + first.stderr + second.stdout + second.stderr


def test_reconciler_rejects_wrong_existing_workspace_before_creating_more(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    state = _PaperclipState()
    state.projects.append(
        {
            "id": PROJECT_ID,
            "companyId": COMPANY_ID,
            "name": "Glitcherry Android Development",
            "status": "in_progress",
        }
    )
    state.workspaces.append(
        {
            "id": "00000000-0000-4000-8000-000000000201",
            "projectId": PROJECT_ID,
            "companyId": COMPANY_ID,
            "name": "GlitcherryCTO",
            "sourceType": "local_path",
            "cwd": "/wrong/path",
            "isPrimary": True,
        }
    )

    result = _run(fixture, state)
    assert result.returncode != 0
    assert "wrong path" in result.stderr.lower()
    assert state.project_posts == 0
    assert state.workspace_posts == 0


def test_reconciler_requires_private_host_files(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    Path(fixture["bindings"]).chmod(0o644)
    state = _PaperclipState()

    result = _run(fixture, state)
    assert result.returncode != 0
    assert "mode-600" in result.stderr
    assert state.project_posts == 0
    assert state.workspace_posts == 0
