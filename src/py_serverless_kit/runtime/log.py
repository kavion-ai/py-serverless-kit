"""Structured JSON logging that every provider's log pipeline can ingest.

Set ``PSKIT_LOG_FORMAT=text`` for human readable output (the local CLI does this)
and ``LOG_LEVEL`` / ``PSKIT_LOG_LEVEL`` to control verbosity.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict

_CONFIGURED = False
_RESERVED = set(vars(logging.LogRecord("", 0, "", 0, "", (), None))) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def _configure() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    _CONFIGURED = True
    logger = logging.getLogger("pskit")
    level = os.environ.get("PSKIT_LOG_LEVEL") or os.environ.get("LOG_LEVEL") or "INFO"
    logger.setLevel(level.upper() if isinstance(level, str) else level)
    # The on-prem host tees stdout into its log buffer and records log calls itself;
    # write to the real stream so records are not captured twice.
    handler = logging.StreamHandler(getattr(sys.stdout, "pskit_passthrough", sys.stdout))
    if os.environ.get("PSKIT_LOG_FORMAT", "json").lower() == "text":
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s"))
    else:
        handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    logger.propagate = False


class _FieldsAdapter(logging.LoggerAdapter):
    """Like LoggerAdapter, but merges call-site ``extra=`` with the bound fields
    (the stdlib adapter replaces them before Python 3.13)."""

    def process(self, msg: Any, kwargs: Any) -> Any:
        merged = {**(self.extra or {}), **(kwargs.get("extra") or {})}
        # Keys such as "name" or "message" are reserved by LogRecord and would make
        # logging raise KeyError - a log call must never crash a handler.
        kwargs["extra"] = {(f"{k}_" if k in _RESERVED else k): v for k, v in merged.items()}
        return msg, kwargs


def get_logger(name: str = "pskit.function", **fields: Any) -> logging.LoggerAdapter:
    _configure()
    if not name.startswith("pskit"):
        name = f"pskit.{name}"
    return _FieldsAdapter(logging.getLogger(name), fields)
