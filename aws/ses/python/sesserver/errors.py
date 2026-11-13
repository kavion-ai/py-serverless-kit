"""``ApiError``: one error, answered in the shape of the API that was called.

``code`` is the SES v2 name (``NotFoundException``, ``BadRequestException``, ...). The v1 Query API answers with its
own code for the same error (``v1``): ``TemplateDoesNotExist``, ``InvalidParameterValue``, ...
"""

from __future__ import annotations

from typing import Optional


class ApiError(Exception):
    def __init__(self, code: str, message: str, status: int = 400, v1: Optional[str] = None) -> None:
        super().__init__(message)
        self.code, self.message, self.status = code, message, status
        self.v1 = v1 or {
            "BadRequestException": "InvalidParameterValue",
            "NotFoundException": "NotFound",
            "AlreadyExistsException": "AlreadyExists",
            "TooManyRequestsException": "Throttling",
            "LimitExceededException": "LimitExceeded",
            "SendingPausedException": "AccountSendingPausedException",
        }.get(code, code)


def bad_request(message: str) -> ApiError:
    return ApiError("BadRequestException", message)


def not_found(message: str, v1: Optional[str] = None) -> ApiError:
    return ApiError("NotFoundException", message, 404, v1)


def exists(message: str, v1: Optional[str] = None) -> ApiError:
    return ApiError("AlreadyExistsException", message, 400, v1)


def rejected(message: str) -> ApiError:
    return ApiError("MessageRejected", message)
