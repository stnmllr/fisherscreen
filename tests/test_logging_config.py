import json
import logging

import pytest

from app.logging_config import CloudJsonFormatter, configure_logging


@pytest.fixture(autouse=True)
def _restore_logging_state():
    """Snapshot + restore global logging state so basicConfig(force=True) in one
    test cannot pollute the ordering or determinism of any other test."""
    root = logging.getLogger()
    saved_handlers = root.handlers[:]
    saved_root_level = root.level
    saved_app_level = logging.getLogger("app").level
    try:
        yield
    finally:
        root.handlers[:] = saved_handlers
        root.setLevel(saved_root_level)
        logging.getLogger("app").setLevel(saved_app_level)


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


def test_configure_sets_app_info_and_root_warning():
    configure_logging()
    assert logging.getLogger().level == logging.WARNING
    assert logging.getLogger("app").level == logging.INFO


def test_app_child_info_enabled_third_party_info_suppressed():
    configure_logging()
    assert logging.getLogger("app.screener.filters").isEnabledFor(logging.INFO) is True
    assert logging.getLogger("httpx").isEnabledFor(logging.INFO) is False


def test_root_handler_uses_cloud_json_formatter():
    configure_logging()
    handlers = logging.getLogger().handlers
    assert len(handlers) == 1
    assert isinstance(handlers[0].formatter, CloudJsonFormatter)


def test_importing_app_main_configures_app_logger():
    import app.main  # noqa: F401  -- import side-effect configures logging

    assert logging.getLogger("app").level == logging.INFO
