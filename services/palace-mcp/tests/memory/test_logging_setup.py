import logging

import pytest

from palace_mcp.memory.logging_setup import configure_json_logging


def test_json_logger_emits_structured_record(caplog: pytest.LogCaptureFixture) -> None:
    logger = logging.getLogger("palace_mcp.test")
    with caplog.at_level(logging.INFO, logger="palace_mcp.test"):
        configure_json_logging()
        logger.info("ingest.start", extra={"source": "paperclip", "run_id": "abc"})
    record = caplog.records[-1]
    assert record.msg == "ingest.start"
    assert getattr(record, "source") == "paperclip"
    assert getattr(record, "run_id") == "abc"
