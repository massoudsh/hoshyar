from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar
from datetime import datetime, timezone

# Carried into every log line emitted while a request is being handled.
request_id: ContextVar[str | None] = ContextVar("request_id", default=None)

_RESERVED = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    """One JSON object per line, so a log shipper can index fields instead of parsing prose."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "time": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
        }
        current = request_id.get()
        if current:
            payload["request_id"] = current
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure(level: str = "info") -> logging.Logger:
    """Install the JSON handler once; repeat calls only adjust the level."""
    logger = logging.getLogger("hoshyar")
    if not any(isinstance(handler.formatter, JsonFormatter) for handler in logger.handlers):
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
        logger.propagate = False
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    return logger


def get_logger() -> logging.Logger:
    return logging.getLogger("hoshyar")
