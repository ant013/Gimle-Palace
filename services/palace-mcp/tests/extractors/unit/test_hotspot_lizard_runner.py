from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

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
