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


def configure_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(CloudJsonFormatter())
    logging.basicConfig(level=level, handlers=[handler], force=True)
