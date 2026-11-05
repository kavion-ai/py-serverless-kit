"""The one error type of the vault package; ``status`` maps it onto HTTP in the studio."""

from __future__ import annotations

from typing import Any


class VaultError(Exception):
    def __init__(self, message: str, status: int = 400, code: str = "", **extra: Any) -> None:
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code
        self.extra = extra
