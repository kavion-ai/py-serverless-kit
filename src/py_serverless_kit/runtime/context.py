"""Provider-neutral invocation context."""

from __future__ import annotations

import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Optional

from .log import get_logger


@dataclass
class Context:
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    function: str = ""
    provider: str = "local"
    service: str = field(default_factory=lambda: os.environ.get("PSKIT_SERVICE", ""))
    stage: str = field(default_factory=lambda: os.environ.get("PSKIT_STAGE", ""))
    region: str = field(default_factory=lambda: os.environ.get("PSKIT_REGION", ""))
    memory_mb: Optional[int] = None
    deadline: Optional[float] = None  # unix epoch seconds
    raw: Any = None
    _remaining: Optional[Callable[[], int]] = field(default=None, repr=False)
    _logger: Optional[logging.LoggerAdapter] = field(default=None, repr=False)

    @property
    def env(self) -> Mapping[str, str]:
        return os.environ

    @property
    def logger(self) -> logging.LoggerAdapter:
        if self._logger is None:
            self._logger = get_logger(function=self.function, request_id=self.request_id, provider=self.provider)
        return self._logger

    def remaining_time_ms(self) -> Optional[int]:
        """Milliseconds until the platform kills this invocation, if known."""
        if self._remaining is not None:
            return int(self._remaining())
        if self.deadline is not None:
            return max(0, int((self.deadline - time.time()) * 1000))
        return None
