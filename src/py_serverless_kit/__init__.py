"""py_serverless_kit - write a Python function once, deploy it to any cloud.

Only the *runtime* API is exported here. It is pure standard library so it can be
shipped inside every deployment bundle. The CLI, config loader and Terraform
renderers live in sub-packages that are never imported at function runtime.
"""

from ._version import __author__, __version__
from .runtime.batch import BatchResult
from .runtime.context import Context
from .runtime.errors import (
    BadRequest,
    Conflict,
    Forbidden,
    HttpError,
    MethodNotAllowed,
    NotFound,
    TooManyRequests,
    Unauthorized,
    UnprocessableEntity,
)
from .runtime.event import Event, EventType, Headers, HttpRequest, Record
from .runtime.invoke import invoke
from .runtime.resources import Resource, resource, resources
from .runtime.response import Response
from .runtime.secrets import SecretError, SecretNotFound, get_secret, get_secrets, put_secret

__all__ = [
    "__author__",
    "__version__",
    "BadRequest",
    "BatchResult",
    "Conflict",
    "Context",
    "Event",
    "EventType",
    "Forbidden",
    "Headers",
    "HttpError",
    "HttpRequest",
    "MethodNotAllowed",
    "NotFound",
    "Record",
    "Resource",
    "Response",
    "SecretError",
    "SecretNotFound",
    "TooManyRequests",
    "Unauthorized",
    "UnprocessableEntity",
    "get_secret",
    "get_secrets",
    "invoke",
    "put_secret",
    "resource",
    "resources",
]
