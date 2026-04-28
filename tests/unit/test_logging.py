import io
import json

from ah_research.logging import configure_logging, get_logger


def test_configure_logging_emits_json():
    buf = io.StringIO()
    configure_logging(level="INFO", stream=buf, json_output=True)
    log = get_logger("test")
    log.info("hello", foo="bar", n=42)

    line = buf.getvalue().strip()
    record = json.loads(line)
    assert record["event"] == "hello"
    assert record["foo"] == "bar"
    assert record["n"] == 42
    assert record["level"] == "info"


def test_get_logger_returns_bound_logger():
    log = get_logger("ah_research.test")
    bound = log.bind(request_id="abc")
    assert bound is not None


def test_default_level_is_info():
    buf = io.StringIO()
    configure_logging(stream=buf, json_output=True)
    log = get_logger("test")
    log.debug("should not appear")
    log.info("should appear")
    output = buf.getvalue()
    assert "should appear" in output
    assert "should not appear" not in output
