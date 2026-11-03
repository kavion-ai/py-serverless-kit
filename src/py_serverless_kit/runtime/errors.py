"""Exceptions a handler can raise to produce a well-formed HTTP error response.

For non-HTTP events these are re-raised so the platform's retry / dead-letter
semantics apply unchanged.
"""

from __future__ import annotations

from typing import Any, Dict, Optional


class PskitError(Exception):
    """Base class for runtime errors raised by the kit itself."""


class HandlerNotFound(PskitError):
    """The configured ``module.function`` handler could not be imported."""


class HttpError(Exception):
    status: int = 500
    default_message: str = "Internal Server Error"

    def __init__(
        self,
        message: Optional[str] = None,
        *,
        status: Optional[int] = None,
        details: Any = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> None:
        self.message = message or self.default_message
        if status is not None:
            self.status = status
        self.details = details
        self.headers = dict(headers or {})
        super().__init__(self.message)

    def to_body(self) -> Dict[str, Any]:
        body: Dict[str, Any] = {"error": self.message, "status": self.status}
        if self.details is not None:
            body["details"] = self.details
        return body


class BadRequest(HttpError):
    status = 400
    default_message = "Bad Request"


class Unauthorized(HttpError):
    status = 401
    default_message = "Unauthorized"


class Forbidden(HttpError):
    status = 403
    default_message = "Forbidden"


class NotFound(HttpError):
    status = 404
    default_message = "Not Found"


class MethodNotAllowed(HttpError):
    status = 405
    default_message = "Method Not Allowed"


class Conflict(HttpError):
    status = 409
    default_message = "Conflict"


class UnprocessableEntity(HttpError):
    status = 422
    default_message = "Unprocessable Entity"


class TooManyRequests(HttpError):
    status = 429
    default_message = "Too Many Requests"
