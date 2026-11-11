"""``ApiError`` (answered as ``{"__type": code, "message": ...}``) and the errors AWS answers most often."""

from __future__ import annotations


class ApiError(Exception):
    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def not_found(what: str = "secret") -> ApiError:
    return ApiError("ResourceNotFoundException", f"Secrets Manager can't find the specified {what}.")


def invalid(message: str) -> ApiError:
    return ApiError("InvalidParameterException", message)


def bad_request(message: str) -> ApiError:
    return ApiError("InvalidRequestException", message)
