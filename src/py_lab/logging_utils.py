from __future__ import annotations

import json
import logging
import traceback
from typing import Any


def log_exception(logger: logging.Logger, exc:Exception,event: str, **fields: Any) -> None:
    exc_type = type(exc).__name__
    exc_tb = traceback.format_exc()
    log_json(
        logger,
        logging.ERROR,
        event,
        exception_type=exc_type,
        exception_message=str(exc),
        exception_traceback=exc_tb,
        **fields
    )

def log_json(logger: logging.Logger, level:int, event:str, **fields:Any) -> None:

    payload = {"event": event, **fields}
    logger.log(level, json.dumps(payload, ensure_ascii=False, separators=(",", ":")))

class RequestIdFilter(logging.Filter):
    """Logging filter to add request ID to log records."""

    def __init__(self, request_id: str = "-") -> None:
        super().__init__()
        self.request_id = request_id

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = self.request_id
        return True

def setup_logging(level: str = "INFO") -> None:
    """Set up logging configuration."""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s request_id=%(request_id)s %(message)s",
    )
