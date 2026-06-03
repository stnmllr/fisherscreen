import json
import logging


class CloudJsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "severity": record.levelname,
            "message": record.getMessage(),
            "module": record.module,
            "funcName": record.funcName,
        }
        trace = getattr(record, "trace", None)
        if trace:
            log_entry["logging.googleapis.com/trace"] = trace
        return json.dumps(log_entry)


def configure_logging(
    app_level: int = logging.INFO, root_level: int = logging.WARNING
) -> None:
    """Install structured JSON logging for Cloud Run.

    The root logger is set to WARNING so chatty third-party libraries (httpx logs
    every HTTP request at INFO, yfinance, etc.) stay quiet, while the ``app``
    logger is set to INFO so our own aggregate lines (filter stage counts,
    ``edgar_skipped`` totals, run start/end) are emitted. Propagation does not
    re-check ancestor logger levels, so ``app.*`` INFO records reach the root
    JSON handler even though root itself is WARNING.
    """
    handler = logging.StreamHandler()
    handler.setFormatter(CloudJsonFormatter())
    logging.basicConfig(level=root_level, handlers=[handler], force=True)
    logging.getLogger("app").setLevel(app_level)
