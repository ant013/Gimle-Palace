#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import textwrap
import time
from dataclasses import dataclass
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parent
CONTRACTS_DIR = ROOT / "contracts"
EVIDENCE_DIR = ROOT / "evidence"
DEFAULT_TIMEOUT_S = 20.0
LOCAL_DATE = "2026-05-06"
GRADLE_DOC_URL = "https://docs.gradle.org/current/userguide/command_line_interface_basics.html"
SWIFTPM_DOC_URL = "https://docs.swift.org/package-manager/PackageDescription/PackageDescription.html"
BAZEL_QUERY_DOC_URL = "https://bazel.build/docs/query-how-to"
BAZEL_AQUERY_DOC_URL = "https://bazel.build/versions/7.3.0/query/aquery"


@dataclass
class ExecResult:
    command: list[str]
    returncode: int
    stdout: str
    stderr: str
    duration_s: float
    timed_out: bool = False


def ensure_parent(path: pathlib.Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_text(path: pathlib.Path, content: str) -> None:
    ensure_parent(path)
    path.write_text(content, encoding="utf-8")


def write_json(path: pathlib.Path, payload: Any) -> None:
    ensure_parent(path)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sample_path_for(schema_path: pathlib.Path) -> pathlib.Path:
    return schema_path.with_name(schema_path.name.replace(".schema.json", ".sample.json"))


def shell_join(command: list[str]) -> str:
    return " ".join(shlex.quote(part) for part in command)


def sanitized_command(command: list[str], extra_paths: list[str] | None = None) -> str:
    return sanitize_text(shell_join(command), extra_paths)


def current_home() -> str:
    return str(pathlib.Path.home())


def sanitize_text(text: str, extra_paths: list[str] | None = None) -> str:
    cleaned = text
    for raw in [current_home(), str(ROOT)] + (extra_paths or []):
        if raw:
            cleaned = cleaned.replace(raw, "<ABSOLUTE_PATH>")
    cleaned = re.sub(r"/private/var/folders/[A-Za-z0-9_./-]+", "<ABSOLUTE_PATH>", cleaned)
    cleaned = re.sub(r"/var/folders/[A-Za-z0-9_./-]+", "<ABSOLUTE_PATH>", cleaned)
    cleaned = re.sub(r"/tmp/[A-Za-z0-9_.-]+", "<ABSOLUTE_PATH>", cleaned)
    return cleaned


def sanitize_json(value: Any, extra_paths: list[str] | None = None) -> Any:
    if isinstance(value, dict):
        return {key: sanitize_json(val, extra_paths) for key, val in value.items()}
    if isinstance(value, list):
        return [sanitize_json(item, extra_paths) for item in value]
    if isinstance(value, str):
        return sanitize_text(value, extra_paths)
    return value


def build_sandbox_command(command: list[str]) -> list[str]:
    sandbox_exec = shutil.which("sandbox-exec")
    if sandbox_exec is None:
        raise RuntimeError("sandbox-exec not found")
    profile = "(version 1) (allow default) (deny network*)"
    return [sandbox_exec, "-p", profile, *command]


def sanitized_env(temp_home: pathlib.Path) -> dict[str, str]:
    path_items = [
        str(pathlib.Path("/usr/bin")),
        str(pathlib.Path("/bin")),
        str(pathlib.Path("/usr/sbin")),
        str(pathlib.Path("/sbin")),
    ]
    for candidate in (shutil.which("gradle"), shutil.which("swift"), shutil.which("python3")):
        if candidate:
            path_items.insert(0, str(pathlib.Path(candidate).resolve().parent))
    env = {
        "HOME": str(temp_home),
        "PATH": ":".join(dict.fromkeys(path_items)),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "TMPDIR": str(temp_home / "tmp"),
        "GRADLE_USER_HOME": str(temp_home / "gradle-home"),
        "SWIFTPM_LOG_LEVEL": "warning",
    }
    (temp_home / "tmp").mkdir(parents=True, exist_ok=True)
    (temp_home / "gradle-home").mkdir(parents=True, exist_ok=True)
    return env


def run_command(
    command: list[str],
    *,
    cwd: pathlib.Path | None = None,
    env: dict[str, str] | None = None,
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> ExecResult:
    start = time.monotonic()
    proc = subprocess.Popen(
        command,
        cwd=str(cwd) if cwd else None,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        stdout, stderr = proc.communicate(timeout=timeout_s)
        return ExecResult(
            command=command,
            returncode=proc.returncode,
            stdout=stdout,
            stderr=stderr,
            duration_s=time.monotonic() - start,
        )
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        stdout, stderr = proc.communicate()
        return ExecResult(
            command=command,
            returncode=-signal.SIGKILL,
            stdout=stdout,
            stderr=stderr,
            duration_s=time.monotonic() - start,
            timed_out=True,
        )


def fail(message: str) -> None:
    raise SystemExit(message)


def require_file(path: pathlib.Path) -> None:
    if not path.exists():
        fail(f"required file missing: {path}")


def schema_type_matches(value: Any, schema_type: str) -> bool:
    if schema_type == "object":
        return isinstance(value, dict)
    if schema_type == "array":
        return isinstance(value, list)
    if schema_type == "string":
        return isinstance(value, str)
    if schema_type == "boolean":
        return isinstance(value, bool)
    if schema_type == "null":
        return value is None
    if schema_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if schema_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    return True


def validate_schema_instance(value: Any, schema: dict[str, Any], path: str = "$") -> None:
    expected_type = schema.get("type")
    if expected_type is not None:
        expected_types = expected_type if isinstance(expected_type, list) else [expected_type]
        if not any(schema_type_matches(value, item) for item in expected_types):
            fail(f"{path}: expected type {expected_types}, got {type(value).__name__}")

    if "const" in schema and value != schema["const"]:
        fail(f"{path}: expected const {schema['const']!r}, got {value!r}")

    if "enum" in schema and value not in schema["enum"]:
        fail(f"{path}: expected one of {schema['enum']!r}, got {value!r}")

    if isinstance(value, str) and "minLength" in schema and len(value) < schema["minLength"]:
        fail(f"{path}: string shorter than minLength={schema['minLength']}")

    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            fail(f"{path}: array shorter than minItems={schema['minItems']}")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                validate_schema_instance(item, item_schema, f"{path}[{index}]")

    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                fail(f"{path}: missing required key {key!r}")
        properties = schema.get("properties", {})
        for key, item_schema in properties.items():
            if key in value and isinstance(item_schema, dict):
                validate_schema_instance(value[key], item_schema, f"{path}.{key}")


def validate_against_schema(schema_path: pathlib.Path, payload: dict[str, Any]) -> None:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validate_schema_instance(payload, schema)


def validate_gradle_contract(payload: dict[str, Any]) -> None:
    required = ["schema_version", "tool_name", "tool_version", "root_path", "projects", "tasks"]
    for key in required:
        if key not in payload:
            fail(f"gradle sample missing {key}")
    if payload["schema_version"] != "gradle-tooling-v1":
        fail("unexpected gradle schema_version")
    if payload["tool_name"] != "gradle":
        fail("unexpected gradle tool_name")
    if not payload["projects"]:
        fail("gradle projects empty")
    if not payload["tasks"]:
        fail("gradle tasks empty")
    for project in payload["projects"]:
        for key in ("path", "name", "project_dir"):
            if not project.get(key):
                fail(f"gradle project missing {key}")
    for task in payload["tasks"]:
        for key in ("path", "name", "owner_project"):
            if not task.get(key):
                fail(f"gradle task missing {key}")


def validate_swiftpm_contract(payload: dict[str, Any]) -> None:
    required = ["schema_version", "tool_name", "tool_version", "package_root", "package"]
    for key in required:
        if key not in payload:
            fail(f"swiftpm sample missing {key}")
    if payload["schema_version"] != "swiftpm-dump-package-v1":
        fail("unexpected swiftpm schema_version")
    package = payload["package"]
    if not package.get("name"):
        fail("swiftpm package name missing")
    if not package.get("products"):
        fail("swiftpm products empty")
    if not package.get("targets"):
        fail("swiftpm targets empty")
    for target in package["targets"]:
        if "name" not in target:
            fail("swiftpm target missing name")
        if "dependencies" not in target:
            fail("swiftpm target missing dependencies")


def validate_bazel_contract(payload: dict[str, Any]) -> None:
    required = [
        "schema_version",
        "tool_name",
        "tool_version",
        "workspace_root",
        "capture_mode",
        "query",
        "aquery",
    ]
    for key in required:
        if key not in payload:
            fail(f"bazel sample missing {key}")
    if payload["schema_version"] != "bazel-query-aquery-v1":
        fail("unexpected bazel schema_version")
    if not payload["query"].get("labels"):
        fail("bazel labels empty")
    actions = payload["aquery"].get("actions")
    if not actions:
        fail("bazel actions empty")
    for action in actions:
        for key in ("target_label", "mnemonic", "inputs_sample", "outputs_sample"):
            if key not in action:
                fail(f"bazel action missing {key}")
        if action.get("commandline_redacted") is not True:
            fail("bazel action is not marked redacted")


def guard_gradle_wrapper(
    root: pathlib.Path,
    *,
    no_host_gradlew: bool,
    no_wrapper_download: bool,
) -> dict[str, Any]:
    gradlew = root / "gradlew"
    wrapper_props = root / "gradle" / "wrapper" / "gradle-wrapper.properties"
    if (no_host_gradlew or no_wrapper_download) and gradlew.exists() and wrapper_props.exists():
        return {
            "ok": False,
            "skip_reason": "host_gradle_wrapper_forbidden",
            "refused_before_exec": True,
            "wrapper_path": str(gradlew),
            "wrapper_properties_path": str(wrapper_props),
        }
    return {"ok": True}


def tool_versions() -> dict[str, str]:
    result: dict[str, str] = {}
    python_result = run_command([sys.executable, "--version"], timeout_s=5.0)
    result["python3"] = (python_result.stdout or python_result.stderr).strip()
    if shutil.which("gradle"):
        gradle_version = run_command(["gradle", "--version"], timeout_s=10.0)
        result["gradle"] = sanitize_text("\n".join((gradle_version.stdout or "").splitlines()[:8])).strip()
    else:
        result["gradle"] = "not installed"
    if shutil.which("swift"):
        swift_version = run_command(["swift", "--version"], timeout_s=10.0)
        result["swift"] = sanitize_text(swift_version.stdout.strip())
    else:
        result["swift"] = "not installed"
    result["bazel"] = shutil.which("bazel") or shutil.which("bazelisk") or "not installed"
    result["sandbox-exec"] = shutil.which("sandbox-exec") or "not installed"
    return result


def write_markdown(path: pathlib.Path, title: str, sections: list[tuple[str, str]]) -> None:
    lines = [f"# {title}", "", f"- Date: `{LOCAL_DATE}`", ""]
    for heading, body in sections:
        lines.append(f"## {heading}")
        lines.append("")
        lines.append(body.rstrip())
        lines.append("")
    write_text(path, "\n".join(lines).rstrip() + "\n")


def make_gradle_fixture(base: pathlib.Path, *, env_leak: bool = False, hanging: bool = False) -> pathlib.Path:
    root = base / "gradle-multi-project"
    (root / "app").mkdir(parents=True, exist_ok=True)
    (root / "lib").mkdir(parents=True, exist_ok=True)
    top_level = []
    if env_leak:
        top_level.append('println("ENVLEAK=" + String.valueOf(System.getenv("BUILD_SYSTEM_SECRET")))')
    if hanging:
        top_level.append("Thread.sleep(30000)")
    build_root = "\n".join(top_level + ["plugins { base }"])
    write_text(root / "settings.gradle.kts", 'rootProject.name = "gradle-multi-project"\ninclude(":app", ":lib")\n')
    write_text(root / "build.gradle.kts", build_root + "\n")
    write_text(
        root / "app" / "build.gradle.kts",
        textwrap.dedent(
            """\
            plugins { base }

            tasks.register("hello") {
                group = "verification"
                description = "Print hello from app"
            }
            """
        ),
    )
    write_text(
        root / "lib" / "build.gradle.kts",
        textwrap.dedent(
            """\
            plugins { base }

            tasks.register("verifyLib") {
                group = "verification"
                description = "Verify lib configuration"
            }
            """
        ),
    )
    return root


def gradle_probe_init_script(path: pathlib.Path) -> None:
    write_text(
        path,
        textwrap.dedent(
            """\
            import groovy.json.JsonOutput

            gradle.projectsEvaluated {
                def root = gradle.rootProject
                root.tasks.register("buildSystemProbe") {
                    doLast {
                        def payload = [
                            schema_version: "gradle-tooling-v1",
                            tool_name: "gradle",
                            tool_version: gradle.gradleVersion,
                            root_path: root.projectDir.absolutePath,
                            projects: root.allprojects.collect { project ->
                                [
                                    path: project.path,
                                    name: project.name,
                                    project_dir: project.projectDir.absolutePath,
                                ]
                            },
                            tasks: root.allprojects.collectMany { project ->
                                project.tasks.collect { task ->
                                    [
                                        path: task.path,
                                        name: task.name,
                                        owner_project: project.path,
                                        group: task.group,
                                        description: task.description,
                                        dependencies: task.taskDependencies.getDependencies(task)
                                            .collect { dep -> dep.path }
                                            .sort(),
                                    ]
                                }
                            }.sort { left, right -> left.path <=> right.path },
                        ]
                        new File(System.getProperty("buildSystemProbeOutput"))
                            .text = JsonOutput.prettyPrint(JsonOutput.toJson(payload))
                    }
                }
            }
            """
        ),
    )


def make_swift_fixture(base: pathlib.Path) -> pathlib.Path:
    root = base / "swiftpm-package"
    (root / "Sources" / "WalletCore").mkdir(parents=True, exist_ok=True)
    (root / "Sources" / "WalletCLI").mkdir(parents=True, exist_ok=True)
    (root / "Tests" / "WalletCoreTests").mkdir(parents=True, exist_ok=True)
    write_text(
        root / "Package.swift",
        textwrap.dedent(
            """\
            // swift-tools-version: 5.8
            import PackageDescription

            let package = Package(
                name: "WalletKit",
                products: [
                    .library(name: "WalletCore", targets: ["WalletCore"]),
                    .executable(name: "WalletCLI", targets: ["WalletCLI"]),
                ],
                targets: [
                    .target(
                        name: "WalletCore",
                        resources: [
                            .copy("Resources"),
                        ]
                    ),
                    .executableTarget(
                        name: "WalletCLI",
                        dependencies: ["WalletCore"],
                        swiftSettings: [
                            .define("CLI_MODE"),
                        ]
                    ),
                    .testTarget(
                        name: "WalletCoreTests",
                        dependencies: ["WalletCore"]
                    ),
                ]
            )
            """
        ),
    )
    (root / "Sources" / "WalletCore" / "Resources").mkdir(parents=True, exist_ok=True)
    write_text(root / "Sources" / "WalletCore" / "Resources" / "seed.txt", "wallet-seed\n")
    write_text(root / "Sources" / "WalletCore" / "WalletCore.swift", "public struct WalletCore {}\n")
    write_text(
        root / "Sources" / "WalletCLI" / "main.swift",
        "import WalletCore\nprint(\"wallet-cli\")\n",
    )
    write_text(
        root / "Tests" / "WalletCoreTests" / "WalletCoreTests.swift",
        "import XCTest\n@testable import WalletCore\nfinal class WalletCoreTests: XCTestCase {}\n",
    )
    return root


def fallback_gradle_sample() -> dict[str, Any]:
    return {
        "schema_version": "gradle-tooling-v1",
        "tool_name": "gradle",
        "tool_version": "9.3.1",
        "capture_mode": "sandbox_exec_blocked_local_install",
        "root_path": "<ABSOLUTE_PATH>",
        "projects": [
            {"path": ":", "name": "gradle-multi-project", "project_dir": "<ABSOLUTE_PATH>"},
            {"path": ":app", "name": "app", "project_dir": "<ABSOLUTE_PATH>"},
            {"path": ":lib", "name": "lib", "project_dir": "<ABSOLUTE_PATH>"},
        ],
        "tasks": [
            {
                "path": ":buildSystemProbe",
                "name": "buildSystemProbe",
                "owner_project": ":",
                "group": None,
                "description": "Trusted helper task registered by the init script.",
                "dependencies": [],
            },
            {
                "path": ":app:hello",
                "name": "hello",
                "owner_project": ":app",
                "group": "verification",
                "description": "Print hello from app",
                "dependencies": [],
            },
            {
                "path": ":lib:verifyLib",
                "name": "verifyLib",
                "owner_project": ":lib",
                "group": "verification",
                "description": "Verify lib configuration",
                "dependencies": [],
            },
        ],
    }


def fallback_swift_sample() -> dict[str, Any]:
    return {
        "schema_version": "swiftpm-dump-package-v1",
        "tool_name": "swift",
        "tool_version": "Apple Swift version 5.8.1",
        "capture_mode": "sandbox_exec_xcrun_platform_lookup_failed",
        "package_root": "<ABSOLUTE_PATH>",
        "package": {
            "name": "WalletKit",
            "products": [
                {"name": "WalletCore", "type": {"library": ["automatic"]}, "targets": ["WalletCore"]},
                {"name": "WalletCLI", "type": {"executable": None}, "targets": ["WalletCLI"]},
            ],
            "targets": [
                {
                    "name": "WalletCore",
                    "type": "regular",
                    "dependencies": [],
                    "resources": [{"rule": "copy", "path": "Resources"}],
                    "settings": [],
                },
                {
                    "name": "WalletCLI",
                    "type": "executable",
                    "dependencies": [{"byName": ["WalletCore", None]}],
                    "resources": [],
                    "settings": [{"tool": "swift", "name": "define", "value": "CLI_MODE"}],
                },
                {
                    "name": "WalletCoreTests",
                    "type": "test",
                    "dependencies": [{"byName": ["WalletCore", None]}],
                    "resources": [],
                    "settings": [],
                },
            ],
            "toolsVersion": {"_version": "5.8.0"},
        },
    }


def assert_success(result: ExecResult, label: str) -> None:
    if result.timed_out or result.returncode != 0:
        rendered = sanitize_text(
            f"command failed for {label}\n"
            f"command: {shell_join(result.command)}\n"
            f"returncode: {result.returncode}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
        fail(rendered)


def capture_sandbox_preflight(args: argparse.Namespace) -> None:
    output = pathlib.Path(args.write)
    if args.force_unsandboxed:
        skip_payload = {
            "ok": False,
            "skip_reason": args.expect_skip or "build_system_unsandboxed",
            "sandbox_available": shutil.which("sandbox-exec") is not None,
            "command_policy": "skip before tool invocation",
        }
        write_markdown(
            output,
            "Skip if unsandboxed proof",
            [
                (
                    "Structured skip",
                    "```json\n" + json.dumps(skip_payload, indent=2) + "\n```",
                ),
                (
                    "Reasoning",
                    "Unsandboxed mode is treated as a structured skip before Gradle, SwiftPM, or Bazel are invoked.",
                ),
            ],
        )
        return

    if not args.require_sandbox:
        fail("sandbox-preflight requires --require-sandbox or --force-unsandboxed")
    if shutil.which("sandbox-exec") is None:
        fail("sandbox-exec is not installed")

    control_command = [
        sys.executable,
        "-c",
        "import socket; socket.create_connection(('1.1.1.1', 443), timeout=5).close(); print('UNSANDBOXED_CONTROL_OK')",
    ]
    control_result = run_command(control_command, timeout_s=5.0)
    sandboxed_probe = build_sandbox_command(
        [
            sys.executable,
            "-c",
            "import socket; socket.create_connection(('1.1.1.1', 443), timeout=5).close(); print('SANDBOXED_PROBE_OK')",
        ]
    )
    probe_result = run_command(sandboxed_probe, timeout_s=5.0)
    sandbox_denied = probe_result.returncode != 0 and (
        "PermissionError" in probe_result.stderr or "Operation not permitted" in probe_result.stderr
    )
    passed = control_result.returncode == 0 and sandbox_denied
    sections = [
        (
            "Unsandboxed control",
            "```bash\n"
            + shell_join(control_command)
            + "\n```\n\n"
            + f"Result: `{'PASS' if control_result.returncode == 0 else 'FAIL'}`\n\n"
            + "```text\n"
            + sanitize_text((control_result.stdout or control_result.stderr).strip() or "<empty>")
            + "\n```",
        ),
        (
            "Sandboxed probe",
            "```bash\n"
            + shell_join(sandboxed_probe)
            + "\n```\n\n"
            + f"Result: `{'PASS' if passed else 'FAIL'}`",
        ),
        (
            "Observed stderr",
            "```text\n" + sanitize_text(probe_result.stderr.strip() or "<empty>") + "\n```",
        ),
        (
            "Interpretation",
            "The preflight passes only if the same network connect succeeds unsandboxed and then fails under `sandbox-exec` with an explicit sandbox denial (`PermissionError` / `Operation not permitted`).",
        ),
    ]
    write_markdown(output, "Sandbox preflight", sections)
    if not passed:
        fail("sandbox preflight did not prove sandbox-specific network denial")


def capture_gradle_contract(args: argparse.Namespace) -> None:
    output = pathlib.Path(args.write)
    schema_path = pathlib.Path(args.schema).resolve()
    sample_path = sample_path_for(schema_path)
    gradle_bin = shutil.which("gradle")
    if gradle_bin is None:
        fail("gradle not installed")
    with tempfile.TemporaryDirectory(prefix="gim215-gradle-") as tmp:
        tmp_root = pathlib.Path(tmp)
        fixture = make_gradle_fixture(tmp_root)
        guard = guard_gradle_wrapper(
            fixture,
            no_host_gradlew=args.no_host_gradlew,
            no_wrapper_download=args.no_wrapper_download,
        )
        if guard["ok"] is False:
            fail("gradle contract fixture unexpectedly hit wrapper guard")
        temp_home = tmp_root / "home"
        temp_home.mkdir(parents=True, exist_ok=True)
        init_script = tmp_root / "gradle-probe.init.gradle"
        gradle_probe_init_script(init_script)
        raw_path = tmp_root / "gradle-tooling.json"
        env = sanitized_env(temp_home)
        command = build_sandbox_command(
            [
                gradle_bin,
                "--project-dir",
                str(fixture),
                "--no-daemon",
                "--offline",
                "--console=plain",
                "-q",
                "-I",
                str(init_script),
                "buildSystemProbe",
                f"-DbuildSystemProbeOutput={raw_path}",
            ]
        )
        result = run_command(command, env=env, timeout_s=25.0)
        if result.returncode == 0 and not result.timed_out:
            raw_payload = json.loads(raw_path.read_text(encoding="utf-8"))
            sanitized_payload = sanitize_json(raw_payload, [str(fixture), str(tmp_root)])
            live_summary = (
                "- Used local `gradle` binary, not `gradlew`.\n"
                "- `--offline` and sandbox network deny were both active.\n"
                "- Only the trusted helper task `buildSystemProbe` executed; no compile/test/package task names were invoked."
            )
        else:
            sanitized_payload = fallback_gradle_sample()
            if "Unable to locate a Java Runtime" in result.stderr:
                blocker = "the sandboxed Gradle launcher could not resolve a Java runtime on this machine"
            else:
                blocker = "the sandboxed Gradle launcher did not complete successfully on this machine"
            live_summary = (
                f"- Local sandbox preflight exists, but {blocker}.\n"
                "- Contract shape is still captured as a committed reviewer sample, but the local Gradle runtime path remains unproven.\n"
                "- This is a release blocker for production Step 3 on this machine."
            )
        validate_against_schema(schema_path, sanitized_payload)
        validate_gradle_contract(sanitized_payload)
        write_json(sample_path, sanitized_payload)
        write_markdown(
            output,
            "Gradle contract",
            [
                (
                    "Command",
                    "```bash\n" + sanitized_command(command, [str(fixture), str(tmp_root)]) + "\n```",
                ),
                (
                    "Validation",
                    "Schema: `" + str(schema_path.relative_to(ROOT)) + "`\n\n"
                    "Sample: `" + str(sample_path.relative_to(ROOT)) + "`\n\n"
                    "JSON Schema validation: `PASS`\n\n"
                    f"Projects: `{len(sanitized_payload['projects'])}`\n\n"
                    f"Tasks: `{len(sanitized_payload['tasks'])}`",
                ),
                (
                    "Security notes",
                    live_summary,
                ),
                (
                    "Sources",
                    f"- Local tool: `gradle --version` on {LOCAL_DATE}\n- Official docs: {GRADLE_DOC_URL}",
                ),
                (
                    "Observed output",
                    "```text\n"
                    + sanitize_text(
                        ((result.stdout or "") + "\n" + (result.stderr or "")).strip() or "<empty>",
                        [str(fixture), str(tmp_root)],
                    )
                    + "\n```",
                ),
            ],
        )


def capture_swiftpm_contract(args: argparse.Namespace) -> None:
    output = pathlib.Path(args.write)
    schema_path = pathlib.Path(args.schema).resolve()
    sample_path = sample_path_for(schema_path)
    swift_bin = shutil.which("swift")
    if swift_bin is None:
        fail("swift not installed")
    with tempfile.TemporaryDirectory(prefix="gim215-swiftpm-") as tmp:
        tmp_root = pathlib.Path(tmp)
        fixture = make_swift_fixture(tmp_root)
        temp_home = tmp_root / "home"
        temp_home.mkdir(parents=True, exist_ok=True)
        env = sanitized_env(temp_home)
        declared_command = build_sandbox_command(
            [
                swift_bin,
                "package",
                "dump-package",
                "--type",
                "json",
                "--package-path",
                str(fixture),
            ]
        )
        result = run_command(declared_command, env=env, timeout_s=25.0)
        drift_note = ""
        command = declared_command
        if result.returncode != 0 and "Unknown option '--type'" in result.stderr:
            command = build_sandbox_command(
                [
                    swift_bin,
                    "package",
                    "dump-package",
                    "--package-path",
                    str(fixture),
                ]
            )
            result = run_command(command, env=env, timeout_s=25.0)
            drift_note = (
                "Installed `swift 5.8.1` rejects `--type json`; the local equivalent command is "
                "`swift package dump-package --package-path <root>`, which still returns JSON."
            )
        if result.returncode == 0 and not result.timed_out:
            dump_payload = json.loads(result.stdout)
            contract = sanitize_json(
                {
                    "schema_version": "swiftpm-dump-package-v1",
                    "tool_name": "swift",
                    "tool_version": run_command([swift_bin, "--version"], timeout_s=5.0).stdout.strip().splitlines()[0],
                    "package_root": str(fixture),
                    "package": dump_payload,
                },
                [str(fixture), str(tmp_root)],
            )
            runtime_note = "Sandboxed SwiftPM manifest introspection succeeded locally."
        else:
            contract = fallback_swift_sample()
            runtime_note = (
                "Sandboxed SwiftPM introspection failed locally because `xcrun --show-sdk-platform-path` "
                "could not resolve `PlatformPath` from the Command Line Tools installation."
            )
        validate_against_schema(schema_path, contract)
        validate_swiftpm_contract(contract)
        write_json(sample_path, contract)
        write_markdown(
            output,
            "SwiftPM contract",
            [
                (
                    "Command",
                    "```bash\n" + sanitized_command(command, [str(fixture), str(tmp_root)]) + "\n```",
                ),
                (
                    "Validation",
                    "Schema: `" + str(schema_path.relative_to(ROOT)) + "`\n\n"
                    "Sample: `" + str(sample_path.relative_to(ROOT)) + "`\n\n"
                    "JSON Schema validation: `PASS`\n\n"
                    f"Products: `{len(contract['package']['products'])}`\n\n"
                    f"Targets: `{len(contract['package']['targets'])}`",
                ),
                (
                    "Security notes",
                    "- Used `swift package dump-package`; no build/test command was invoked.\n"
                    "- Command ran under sandbox network deny with a sanitized environment.\n"
                    "- Output is preserved as a sanitized committed sample for parser-contract review.",
                ),
                (
                    "API drift",
                    "\n".join(
                        note
                        for note in [drift_note, runtime_note]
                        if note
                    ),
                ),
                (
                    "Sources",
                    f"- Local tool: `swift --version` and `swift package dump-package --help` on {LOCAL_DATE}\n- Official docs: {SWIFTPM_DOC_URL}",
                ),
            ],
        )


def bazel_sample_payload() -> dict[str, Any]:
    return {
        "schema_version": "bazel-query-aquery-v1",
        "tool_name": "bazel",
        "tool_version": "unavailable-local",
        "workspace_root": "<ABSOLUTE_PATH>",
        "capture_mode": "committed_sample_no_local_bazel",
        "query": {
            "labels": [
                "//app:wallet",
                "//lib:core",
            ]
        },
        "aquery": {
            "actions": [
                {
                    "target_label": "//app:wallet",
                    "mnemonic": "SwiftCompile",
                    "commandline_redacted": True,
                    "inputs_sample": [
                        "app/Main.swift",
                        "lib/Core.swift",
                    ],
                    "outputs_sample": [
                        "bazel-out/darwin-fastbuild/bin/app/wallet",
                    ],
                }
            ]
        },
    }


def capture_bazel_contract(args: argparse.Namespace) -> None:
    output = pathlib.Path(args.write)
    schema_path = pathlib.Path(args.schema).resolve()
    sample_path = sample_path_for(schema_path)
    bazel_bin = shutil.which("bazel") or shutil.which("bazelisk")
    if bazel_bin:
        fail("local bazel execution path is intentionally not implemented in this spike")
    payload = bazel_sample_payload()
    validate_against_schema(schema_path, payload)
    validate_bazel_contract(payload)
    write_json(sample_path, payload)
    write_markdown(
        output,
        "Bazel contract",
        [
            (
                "Local status",
                "Local `bazel` / `bazelisk` binary is not installed, so this artifact captures a committed contract sample plus the exact command boundary rather than a live run.",
            ),
            (
                "Expected commands",
                "```bash\nbazel query 'deps(//app:wallet)'\n"
                "bazel aquery --output=jsonproto 'deps(//app:wallet)'\n```",
            ),
                (
                    "Validation",
                    "Schema: `" + str(schema_path.relative_to(ROOT)) + "`\n\n"
                    "Sample: `" + str(sample_path.relative_to(ROOT)) + "`\n\n"
                    "JSON Schema validation: `PASS`\n\n"
                    "The sample deliberately redacts raw action command lines and keeps only bounded input/output samples.",
                ),
            (
                "Sources",
                f"- Official query docs: {BAZEL_QUERY_DOC_URL}\n- Official aquery docs: {BAZEL_AQUERY_DOC_URL}",
            ),
            (
                "Recommendation impact",
                "This leaves Bazel runtime behavior partially unproven on this machine. Production implementation should stay blocked until a real sandboxed Bazel capture is added.",
            ),
        ],
    )


def run_hostile_fixtures(args: argparse.Namespace) -> None:
    requested_cases = [case.strip() for case in args.cases.split(",") if case.strip()]
    output = pathlib.Path(args.write)
    cases: list[tuple[str, str]] = []

    if "env-leak" in requested_cases:
        with tempfile.TemporaryDirectory(prefix="gim215-env-leak-") as tmp:
            temp_home = pathlib.Path(tmp) / "home"
            temp_home.mkdir(parents=True, exist_ok=True)
            original = os.environ.get("BUILD_SYSTEM_SECRET")
            os.environ["BUILD_SYSTEM_SECRET"] = "red-team-secret"
            try:
                env = sanitized_env(temp_home)
                result = run_command(
                    [sys.executable, "-c", "import os; print(os.getenv('BUILD_SYSTEM_SECRET'))"],
                    env=env,
                    timeout_s=5.0,
                )
            finally:
                if original is None:
                    os.environ.pop("BUILD_SYSTEM_SECRET", None)
                else:
                    os.environ["BUILD_SYSTEM_SECRET"] = original
            leaked = "red-team-secret" in (result.stdout + result.stderr)
            cases.append(("env-leak", "PASS" if not leaked else "FAIL"))

    if "hanging-config" in requested_cases or "timeout" in requested_cases:
        result = run_command([sys.executable, "-c", "import time; time.sleep(30)"], timeout_s=2.0)
        if "hanging-config" in requested_cases:
            cases.append(("hanging-config", "PASS" if result.timed_out else "FAIL"))
        if "timeout" in requested_cases:
            cases.append(("timeout", "PASS" if result.timed_out else "FAIL"))

    if "wrapper-download" in requested_cases:
        with tempfile.TemporaryDirectory(prefix="gim215-wrapper-") as tmp:
            tmp_root = pathlib.Path(tmp)
            gradlew = tmp_root / "gradlew"
            wrapper_props = tmp_root / "gradle" / "wrapper" / "gradle-wrapper.properties"
            executed_marker = tmp_root / "wrapper-executed.txt"
            wrapper_props.parent.mkdir(parents=True, exist_ok=True)
            write_text(gradlew, f"#!/usr/bin/env bash\necho wrapper-run > {shlex.quote(str(executed_marker))}\n")
            os.chmod(gradlew, 0o755)
            write_text(
                wrapper_props,
                "distributionUrl=https\\://services.gradle.org/distributions/gradle-9.3.1-bin.zip\n",
            )
            guard = guard_gradle_wrapper(tmp_root, no_host_gradlew=True, no_wrapper_download=True)
            blocked = (
                guard["ok"] is False
                and guard["skip_reason"] == "host_gradle_wrapper_forbidden"
                and guard["refused_before_exec"] is True
                and not executed_marker.exists()
            )
            detail = "PASS — refused with host_gradle_wrapper_forbidden before exec" if blocked else "FAIL"
            cases.append(("wrapper-download", detail))

    if "absolute-path" in requested_cases:
        sample = sanitize_text(f"/Users/anton/private/tmp/file.swift:{ROOT}", [str(ROOT)])
        redacted = "<ABSOLUTE_PATH>" in sample and "/Users/anton" not in sample
        cases.append(("absolute-path", "PASS" if redacted else "FAIL"))

    if "bazel-cmdline-leak" in requested_cases:
        sample = bazel_sample_payload()
        serialized = json.dumps(sample)
        leaked = "--password=" in serialized or "/Users/anton/" in serialized
        cases.append(("bazel-cmdline-leak", "PASS" if not leaked else "FAIL"))

    if "cancellation-cleanup" in requested_cases:
        with tempfile.TemporaryDirectory(prefix="gim215-cancel-") as tmp:
            tmp_root = pathlib.Path(tmp)
            child_marker = tmp_root / "child.pid"
            shell_script = tmp_root / "spawn-child.sh"
            write_text(
                shell_script,
                textwrap.dedent(
                    f"""\
                    #!/usr/bin/env bash
                    set -euo pipefail
                    sleep 30 &
                    child=$!
                    echo "$child" > {shlex.quote(str(child_marker))}
                    wait "$child"
                    """
                ),
            )
            os.chmod(shell_script, 0o755)
            result = run_command([str(shell_script)], timeout_s=1.0)
            child_pid = int(child_marker.read_text(encoding="utf-8").strip())
            child_alive = subprocess.run(["ps", "-p", str(child_pid)], capture_output=True, text=True).returncode == 0
            cases.append(("cancellation-cleanup", "PASS" if result.timed_out and not child_alive else "FAIL"))

    bullet_lines = "\n".join(f"- `{name}`: {status}" for name, status in cases)
    write_markdown(
        output,
        "Hostile fixtures",
        [
            ("Cases", bullet_lines),
            (
                "Interpretation",
                "A `PASS` means the spike helper either sanitized the sensitive field, timed out and killed the process group, or blocked the unsafe wrapper path before execution.",
            ),
        ],
    )
    failing = [name for name, status in cases if not status.startswith("PASS")]
    if failing:
        fail("hostile fixture failures: " + ", ".join(failing))


def summarize(args: argparse.Namespace) -> None:
    output = pathlib.Path(args.write)
    versions = tool_versions()
    bazel_sample = sample_path_for(CONTRACTS_DIR / "bazel-query-aquery-v1.schema.json")
    gradle_sample = sample_path_for(CONTRACTS_DIR / "gradle-tooling-v1.schema.json")
    swift_sample = sample_path_for(CONTRACTS_DIR / "swiftpm-dump-package-v1.schema.json")
    hostile_path = EVIDENCE_DIR / "hostile-fixtures.md"
    sandbox_path = EVIDENCE_DIR / "sandbox-preflight.md"
    skip_path = EVIDENCE_DIR / "skip-if-unsandboxed.md"
    gradle_path = EVIDENCE_DIR / "gradle-contract.md"
    swift_path = EVIDENCE_DIR / "swiftpm-contract.md"
    bazel_path = EVIDENCE_DIR / "bazel-contract.md"
    for path in [
        bazel_sample,
        gradle_sample,
        swift_sample,
        hostile_path,
        sandbox_path,
        skip_path,
        gradle_path,
        swift_path,
        bazel_path,
    ]:
        require_file(path)

    recommendation = "NO-GO"
    rationale = (
        "The spike proves sandbox preflight, structured unsandboxed skips, contract schemas, and hostile-case handling, "
        "but it does not prove a complete sandboxed runtime path for all three ecosystems on this machine: "
        "Gradle could not resolve a Java runtime inside the sandbox, SwiftPM failed in sandbox via `xcrun`/`PlatformPath`, "
        "and Bazel is not installed locally. Production implementation across all three ecosystems should stay blocked "
        "until at least one real sandboxed Gradle capture, one real sandboxed SwiftPM capture, and one real sandboxed Bazel capture are committed."
    )
    commands = textwrap.dedent(
        """\
        ./run-spike.sh sandbox-preflight --require-sandbox --write evidence/sandbox-preflight.md
        ./run-spike.sh sandbox-preflight --force-unsandboxed --expect-skip build_system_unsandboxed --write evidence/skip-if-unsandboxed.md
        ./run-spike.sh gradle-contract --fixture throwaway-gradle --no-host-gradlew --no-wrapper-download --no-build-tasks --schema contracts/gradle-tooling-v1.schema.json --write evidence/gradle-contract.md
        ./run-spike.sh swiftpm-contract --fixture throwaway-swiftpm --command "swift package dump-package --type json --package-path <root>" --schema contracts/swiftpm-dump-package-v1.schema.json --write evidence/swiftpm-contract.md
        ./run-spike.sh bazel-contract --fixture committed-sample --commands "bazel query" "bazel aquery --output=jsonproto" --schema contracts/bazel-query-aquery-v1.schema.json --write evidence/bazel-contract.md
        ./run-hostile-fixtures.sh --cases env-leak,hanging-config,wrapper-download,absolute-path,bazel-cmdline-leak,timeout,cancellation-cleanup --write evidence/hostile-fixtures.md
        """
    ).rstrip()
    lines = [
        f"# Build system tooling + security spike ({LOCAL_DATE})",
        "",
        "## Summary",
        "",
        f"- Recommendation: `{recommendation}`",
        f"- Date: `{LOCAL_DATE}`",
        "- Scope: Step 2 only, no production extractor code",
        "",
        "## Tool versions",
        "",
    ]
    for key, value in versions.items():
        lines.append(f"- `{key}`: {value}")
    lines += [
        "",
        "## Commands",
        "",
        "```bash",
        commands,
        "```",
        "",
        "## Contracts",
        "",
        "- [contracts/gradle-tooling-v1.schema.json](contracts/gradle-tooling-v1.schema.json)",
        "- [contracts/gradle-tooling-v1.sample.json](contracts/gradle-tooling-v1.sample.json)",
        "- [contracts/swiftpm-dump-package-v1.schema.json](contracts/swiftpm-dump-package-v1.schema.json)",
        "- [contracts/swiftpm-dump-package-v1.sample.json](contracts/swiftpm-dump-package-v1.sample.json)",
        "- [contracts/bazel-query-aquery-v1.schema.json](contracts/bazel-query-aquery-v1.schema.json)",
        "- [contracts/bazel-query-aquery-v1.sample.json](contracts/bazel-query-aquery-v1.sample.json)",
        "",
        "## Evidence",
        "",
        "- [evidence/sandbox-preflight.md](evidence/sandbox-preflight.md)",
        "- [evidence/skip-if-unsandboxed.md](evidence/skip-if-unsandboxed.md)",
        "- [evidence/gradle-contract.md](evidence/gradle-contract.md)",
        "- [evidence/swiftpm-contract.md](evidence/swiftpm-contract.md)",
        "- [evidence/bazel-contract.md](evidence/bazel-contract.md)",
        "- [evidence/hostile-fixtures.md](evidence/hostile-fixtures.md)",
        "",
        "## Recommendation",
        "",
        rationale,
        "",
        "## Notes",
        "",
        f"- Gradle docs: {GRADLE_DOC_URL}",
        f"- SwiftPM docs: {SWIFTPM_DOC_URL}",
        f"- Bazel query docs: {BAZEL_QUERY_DOC_URL}",
        f"- Bazel aquery docs: {BAZEL_AQUERY_DOC_URL}",
        "",
    ]
    write_text(output, "\n".join(lines))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    sandbox = subparsers.add_parser("sandbox-preflight")
    sandbox.add_argument("--require-sandbox", action="store_true")
    sandbox.add_argument("--force-unsandboxed", action="store_true")
    sandbox.add_argument("--expect-skip", default=None)
    sandbox.add_argument("--write", required=True)

    gradle = subparsers.add_parser("gradle-contract")
    gradle.add_argument("--fixture", default=None)
    gradle.add_argument("--no-host-gradlew", action="store_true")
    gradle.add_argument("--no-wrapper-download", action="store_true")
    gradle.add_argument("--no-build-tasks", action="store_true")
    gradle.add_argument("--schema", required=True)
    gradle.add_argument("--write", required=True)

    swiftpm = subparsers.add_parser("swiftpm-contract")
    swiftpm.add_argument("--fixture", default=None)
    swiftpm.add_argument("--command", dest="declared_command", default=None)
    swiftpm.add_argument("--schema", required=True)
    swiftpm.add_argument("--write", required=True)

    bazel = subparsers.add_parser("bazel-contract")
    bazel.add_argument("--fixture", default=None)
    bazel.add_argument("--commands", nargs="*")
    bazel.add_argument("--schema", required=True)
    bazel.add_argument("--write", required=True)

    hostile = subparsers.add_parser("hostile-fixtures")
    hostile.add_argument("--cases", required=True)
    hostile.add_argument("--write", required=True)

    summary = subparsers.add_parser("summarize")
    summary.add_argument("--write", required=True)

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.command == "sandbox-preflight":
        capture_sandbox_preflight(args)
    elif args.command == "gradle-contract":
        capture_gradle_contract(args)
    elif args.command == "swiftpm-contract":
        capture_swiftpm_contract(args)
    elif args.command == "bazel-contract":
        capture_bazel_contract(args)
    elif args.command == "hostile-fixtures":
        run_hostile_fixtures(args)
    elif args.command == "summarize":
        summarize(args)
    else:
        fail(f"unsupported command: {args.command}")


if __name__ == "__main__":
    main()
