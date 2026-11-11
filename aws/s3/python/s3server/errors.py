"""``S3Error`` (code, message, HTTP status, extra XML fields) and helpers for the common errors."""

from __future__ import annotations

from typing import Dict


class S3Error(Exception):
    def __init__(self, code: str, message: str, status: int = 400, **extra: str) -> None:
        super().__init__(message)
        self.code, self.message, self.status, self.extra = code, message, status, extra
        self.headers: Dict[str, str] = {}


def no_bucket(name: str) -> S3Error:
    return S3Error("NoSuchBucket", "The specified bucket does not exist", 404, BucketName=name)


def no_key(key: str) -> S3Error:
    return S3Error("NoSuchKey", "The specified key does not exist.", 404, Key=key)


def invalid(message: str, name: str = "", value: str = "") -> S3Error:
    extra = {"ArgumentName": name, "ArgumentValue": value} if name else {}
    return S3Error("InvalidArgument", message, 400, **extra)


def malformed() -> S3Error:
    return S3Error(
        "MalformedXML", "The XML you provided was not well-formed or did not validate against our published schema"
    )


def denied(message: str = "Access Denied") -> S3Error:
    return S3Error("AccessDenied", message, 403)
