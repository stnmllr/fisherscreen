import json
import logging

from app.logging_config import CloudJsonFormatter, configure_logging


def _make_record(msg: str, level: int = logging.INFO) -> logging.LogRecord:
    return logging.LogRecord(
        name="test",
        level=level,
        pathname="",
        lineno=0,
        msg=msg,
        args=(),
        exc_info=None,
    )


def test_produces_valid_json():
    formatter = CloudJsonFormatter()
    output = formatter.format(_make_record("hello world"))
    parsed = json.loads(output)
    assert parsed["message"] == "hello world"


def test_uses_severity_not_level():
    formatter = CloudJsonFormatter()
    parsed = json.loads(formatter.format(_make_record("msg", logging.WARNING)))
    assert parsed["severity"] == "WARNING"
    assert "level" not in parsed


def test_includes_module_and_funcname():
    formatter = CloudJsonFormatter()
    parsed = json.loads(formatter.format(_make_record("msg")))
    assert "module" in parsed
    assert "funcName" in parsed


def test_includes_trace_when_set():
    formatter = CloudJsonFormatter()
    record = _make_record("traced")
    record.trace = "projects/myproject/traces/abc123"
    parsed = json.loads(formatter.format(record))
    assert parsed["logging.googleapis.com/trace"] == "projects/myproject/traces/abc123"


def test_omits_trace_when_absent():
    formatter = CloudJsonFormatter()
    parsed = json.loads(formatter.format(_make_record("no trace")))
    assert "logging.googleapis.com/trace" not in parsed


def test_configure_logging_does_not_raise():
    configure_logging()
