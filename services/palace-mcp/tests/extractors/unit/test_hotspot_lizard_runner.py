from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from palace_mcp.extractors.hotspot.lizard_runner import (
    LizardBatchTimeout,
    parse_lizard_xml,
    run_batch,
)

_SAMPLE_XML = """<?xml version="1.0"?>
<cppncss>
  <measure type="Function">
    <labels><label>Nr.</label><label>NCSS</label><label>CCN</label><label>Functions</label></labels>
    <item name="parse_a(...) at /tmp/repo/src/a.py:5">
      <value>1</value><value>10</value><value>3</value><value>parse_a</value>
    </item>
    <item name="big_kotlin(...) at /tmp/repo/src/b.kt:15">
      <value>2</value><value>40</value><value>9</value><value>big_kotlin</value>
    </item>
  </measure>
</cppncss>
"""


def test_parse_lizard_xml_extracts_per_file():
    repo_root = Path("/tmp/repo")
    parsed = parse_lizard_xml(_SAMPLE_XML, repo_root=repo_root)
    by_path = {p.path: p for p in parsed}
    assert by_path["src/a.py"].functions[0].name == "parse_a"
    assert by_path["src/a.py"].functions[0].ccn == 3
    assert by_path["src/b.kt"].functions[0].ccn == 9
    assert by_path["src/b.kt"].language == "kotlin"
    assert by_path["src/a.py"].language == "python"


@pytest.mark.parametrize(
    ("rel_path", "language"),
    [
        ("src/native.c", "c"),
        ("src/script.rb", "ruby"),
        ("src/web.php", "php"),
        ("src/pipeline.scala", "scala"),
    ],
)
def test_parse_lizard_xml_maps_supported_languages(
    rel_path: str, language: str
) -> None:
    repo_root = Path("/tmp/repo")
    xml_text = f"""<?xml version="1.0"?>
<cppncss>
  <measure type="Function">
    <labels><label>Nr.</label><label>NCSS</label><label>CCN</label><label>Functions</label></labels>
    <item name="demo(...) at /tmp/repo/{rel_path}:7">
      <value>1</value><value>10</value><value>3</value><value>demo</value>
    </item>
  </measure>
</cppncss>
"""

    parsed = parse_lizard_xml(xml_text, repo_root=repo_root)

    assert parsed[0].path == rel_path
    assert parsed[0].language == language


@pytest.mark.asyncio
async def test_run_batch_drop_batch_on_timeout(tmp_path: Path):
    files = [tmp_path / "a.py", tmp_path / "b.py"]
    for f in files:
        f.write_text("def x(): pass\n")

    async def fake(*args, **kwargs):
        raise TimeoutError("simulated")

    with patch(
        "palace_mcp.extractors.hotspot.lizard_runner._invoke_lizard",
        side_effect=fake,
    ):
        result = await run_batch(
            files, repo_root=tmp_path, timeout_s=1, behavior="drop_batch"
        )
    assert result.parsed == ()
    assert set(result.skipped_files) == {"a.py", "b.py"}


@pytest.mark.asyncio
async def test_run_batch_drop_batch_logs_full_skipped_file_list(tmp_path: Path):
    files = [tmp_path / "a.py", tmp_path / "b.py"]
    for f in files:
        f.write_text("def x(): pass\n")

    async def fake(*args, **kwargs):
        raise TimeoutError("simulated")

    logger_mock = MagicMock()
    with (
        patch(
            "palace_mcp.extractors.hotspot.lizard_runner._invoke_lizard",
            side_effect=fake,
        ),
        patch("palace_mcp.extractors.hotspot.lizard_runner.logger", logger_mock),
    ):
        await run_batch(files, repo_root=tmp_path, timeout_s=1, behavior="drop_batch")

    assert logger_mock.warning.call_args.kwargs["extra"]["skipped_files"] == (
        "a.py",
        "b.py",
    )


@pytest.mark.asyncio
async def test_run_batch_fail_run_on_timeout_raises(tmp_path: Path):
    files = [tmp_path / "a.py"]
    files[0].write_text("x\n")

    async def fake(*args, **kwargs):
        raise TimeoutError("simulated")

    with patch(
        "palace_mcp.extractors.hotspot.lizard_runner._invoke_lizard",
        side_effect=fake,
    ):
        with pytest.raises(LizardBatchTimeout):
            await run_batch(files, repo_root=tmp_path, timeout_s=1, behavior="fail_run")


@pytest.mark.asyncio
async def test_invoke_lizard_uses_python_module_not_path_lizard(tmp_path: Path):
    """Regression: invoke lizard as `sys.executable -m lizard`, not as `lizard`
    on PATH. The palace-mcp uvicorn server inherits a PATH that doesn't include
    the venv `bin/` directory, so a plain `lizard` exec fails with
    [Errno 2] No such file or directory even when the package is installed.
    """
    import sys

    captured: dict[str, tuple] = {}

    async def fake_create_subprocess_exec(*args, **kwargs):
        captured["args"] = args
        proc = MagicMock()

        async def communicate():
            return (b"<?xml version='1.0'?><cppncss></cppncss>", b"")

        proc.communicate = communicate
        return proc

    from palace_mcp.extractors.hotspot import lizard_runner as lr

    with patch.object(
        lr.asyncio, "create_subprocess_exec", fake_create_subprocess_exec
    ):
        await lr._invoke_lizard([tmp_path / "a.py"], timeout_s=5)

    args = captured["args"]
    assert args[0] == sys.executable, (
        f"first arg must be sys.executable to avoid PATH dependency; got {args[0]!r}"
    )
    assert args[1] == "-m", f"second arg must be -m; got {args[1]!r}"
    assert args[2] == "lizard", f"third arg must be lizard module name; got {args[2]!r}"
