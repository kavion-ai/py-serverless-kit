"""Calls the user's handler with a normalized event and normalizes the result.

This is the single choke-point shared by every provider adapter, so behaviour
(error mapping, CORS, routing, logging) is identical on every cloud.
"""

from __future__ import annotations

import asyncio
import importlib
import inspect
import os
import sys
import time
from typing import Any, Callable, Dict, Optional, Tuple

from .batch import BatchResult
from .context import Context
from .errors import HandlerNotFound, HttpError
from .event import Event, EventType
from .log import get_logger
from .manifest import FunctionSpec, Route, resolve_function
from .response import Response, to_response
from .routing import match_path, method_matches

_HANDLERS: Dict[str, Tuple[Callable[..., Any], int]] = {}
_log = get_logger("pskit.runtime")

DEFAULT_CORS = {
    "origins": ["*"],
    "methods": ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    "headers": ["Content-Type", "Authorization", "X-Requested-With"],
    "expose_headers": [],
    "allow_credentials": False,
    "max_age": 600,
}


def _ensure_bundle_on_path() -> None:
    # <bundle>/py_serverless_kit/runtime/dispatch.py -> make <bundle> importable.
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if root not in sys.path:
        sys.path.insert(0, root)


def resolve_handler(path: str) -> Tuple[Callable[..., Any], int]:
    """Import ``package.module.function`` (or ``package.module:function``).

    Returns the callable and how many positional args it accepts (1 or 2).
    """
    cached = _HANDLERS.get(path)
    if cached is not None:
        return cached
    if ":" in path:
        module_name, _, attr = path.partition(":")
    else:
        module_name, _, attr = path.rpartition(".")
    if not module_name or not attr:
        raise HandlerNotFound(f"Handler {path!r} must look like 'package.module.function'")
    _ensure_bundle_on_path()
    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        raise HandlerNotFound(f"Cannot import module {module_name!r} for handler {path!r}: {exc}") from exc
    target: Any = module
    for part in attr.split("."):
        target = getattr(target, part, None)
        if target is None:
            raise HandlerNotFound(f"Module {module_name!r} has no attribute {attr!r}")
    if not callable(target):
        raise HandlerNotFound(f"Handler {path!r} is not callable")
    arity = 2
    try:
        params = [
            p
            for p in inspect.signature(target).parameters.values()
            if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD, p.VAR_POSITIONAL)
        ]
        if len(params) == 1 and params[0].kind != params[0].VAR_POSITIONAL:
            arity = 1
    except (TypeError, ValueError):
        pass
    _HANDLERS[path] = (target, arity)
    return target, arity


# ---------------------------------------------------------------- routing / CORS


def _select_route(spec: FunctionSpec, event: Event) -> Tuple[Optional[Route], Optional[Response]]:
    """Match the request against configured routes, filling ``path_params``.

    Returns ``(route, early_response)``; ``early_response`` is a 405 when the
    path matched but no route allows the method.
    """
    req = event.http
    if req is None or not spec.routes:
        return None, None
    path_matched: Optional[Route] = None
    # Exact matches win over tolerant ones (e.g. GET /hello vs GET /hello/{name}).
    for tolerant in (False, True):
        for route in spec.routes:
            params = match_path(route.path, req.path, tolerant=tolerant)
            if params is None:
                continue
            path_matched = path_matched or route
            if method_matches(route.method, req.method) or req.method == "OPTIONS":
                if not req.path_params:
                    req.path_params = params
                req.route = route.path
                return route, None
        if path_matched is not None:
            break
    if path_matched is not None:
        allowed = sorted({r.method.upper() for r in spec.routes if match_path(r.path, req.path) is not None})
        resp = Response.json({"error": "Method Not Allowed", "status": 405}, 405, {"allow": ", ".join(allowed)})
        return path_matched, resp
    return None, None


def _cors_config(route: Optional[Route], spec: FunctionSpec) -> Optional[Dict[str, Any]]:
    cors = route.cors if route is not None else next((r.cors for r in spec.routes if r.cors), None)
    if not cors:
        return None
    merged = dict(DEFAULT_CORS)
    if isinstance(cors, dict):
        merged.update({k: v for k, v in cors.items() if v is not None})
    return merged


def _apply_cors(resp: Response, cors: Dict[str, Any], origin: Optional[str], preflight: bool) -> Response:
    origins = cors.get("origins") or ["*"]
    if "*" in origins and not cors.get("allow_credentials"):
        allow_origin = "*"
    elif origin and (origin in origins or "*" in origins):
        allow_origin = origin
    else:
        return resp
    headers = {"access-control-allow-origin": allow_origin}
    if allow_origin != "*":
        headers["vary"] = "Origin"
    if cors.get("allow_credentials"):
        headers["access-control-allow-credentials"] = "true"
    if cors.get("expose_headers"):
        headers["access-control-expose-headers"] = ", ".join(cors["expose_headers"])
    if preflight:
        headers["access-control-allow-methods"] = ", ".join(cors.get("methods") or [])
        headers["access-control-allow-headers"] = ", ".join(cors.get("headers") or [])
        headers["access-control-max-age"] = str(cors.get("max_age", 600))
    for key, value in headers.items():
        resp.headers.setdefault(key, value)
    return resp


# ---------------------------------------------------------------- execution


def _error_response(exc: BaseException, context: Context) -> Response:
    if isinstance(exc, HttpError):
        return Response.json(exc.to_body(), exc.status, exc.headers)
    body: Dict[str, Any] = {"error": "Internal Server Error", "status": 500, "request_id": context.request_id}
    if os.environ.get("PSKIT_DEBUG", "").lower() in ("1", "true", "yes"):
        body["detail"] = f"{type(exc).__name__}: {exc}"
    return Response.json(body, 500)


class _Prepared:
    __slots__ = ("spec", "route", "cors", "early", "started")

    def __init__(self) -> None:
        self.spec: Optional[FunctionSpec] = None
        self.route: Optional[Route] = None
        self.cors: Optional[Dict[str, Any]] = None
        self.early: Optional[Response] = None
        self.started = time.perf_counter()


def _prepare(event: Event, context: Context, function: Optional[str]) -> _Prepared:
    prep = _Prepared()
    spec = resolve_function(function or event.function or None)
    prep.spec = spec
    event.function = event.function or spec.name
    context.function = context.function or spec.name
    if event.http is not None:
        prep.route, prep.early = _select_route(spec, event)
        prep.cors = _cors_config(prep.route, spec)
        if prep.early is None and prep.cors and event.http.method == "OPTIONS":
            prep.early = Response(204, "")
    return prep


def _finish(prep: _Prepared, event: Event, context: Context, result: Any, error: Optional[BaseException]) -> Any:
    elapsed_ms = round((time.perf_counter() - prep.started) * 1000, 2)
    if event.http is None:
        if error is not None:
            context.logger.error(
                "handler failed",
                exc_info=(type(error), error, error.__traceback__),
                extra={"event_type": event.type, "duration_ms": elapsed_ms},
            )
            raise error
        context.logger.debug("handler ok", extra={"event_type": event.type, "duration_ms": elapsed_ms})
        # AWS, the local runner and the on-premises host report partial failures.
        # Everywhere else the whole batch must fail so the platform redelivers it.
        if isinstance(result, BatchResult) and event.provider not in ("aws", "local", "onprem"):
            result.raise_if_failed()
            return None
        return result
    if error is not None:
        if not isinstance(error, HttpError) or error.status >= 500:
            context.logger.error(
                "handler failed",
                exc_info=(type(error), error, error.__traceback__),
                extra={"method": event.http.method, "path": event.http.path},
            )
        resp = _error_response(error, context)
    else:
        resp = to_response(result)
    if prep.cors:
        _apply_cors(resp, prep.cors, event.http.headers.get("origin"), event.http.method == "OPTIONS")
    context.logger.info(
        "request",
        extra={
            "method": event.http.method,
            "path": event.http.path,
            "status": resp.status,
            "duration_ms": elapsed_ms,
        },
    )
    return resp


def execute(event: Event, context: Context, function: Optional[str] = None) -> Any:
    """Run the handler synchronously.

    For HTTP events always returns a :class:`Response`; for everything else
    returns the handler's raw result and lets exceptions propagate so the
    platform's retry policy applies.
    """
    prep = _prepare(event, context, function)
    if prep.early is not None:
        return _finish(prep, event, context, prep.early, None)
    try:
        fn, arity = resolve_handler(prep.spec.handler)  # type: ignore[union-attr]
        result = fn(event) if arity == 1 else fn(event, context)
        if inspect.isawaitable(result):
            result = asyncio.run(_await(result))
    except BaseException as exc:  # noqa: BLE001 - re-raised for non-HTTP events
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        return _finish(prep, event, context, None, exc)
    return _finish(prep, event, context, result, None)


async def execute_async(event: Event, context: Context, function: Optional[str] = None) -> Any:
    """Async variant for runtimes that already run an event loop (Cloudflare, Azure async)."""
    prep = _prepare(event, context, function)
    if prep.early is not None:
        return _finish(prep, event, context, prep.early, None)
    try:
        fn, arity = resolve_handler(prep.spec.handler)  # type: ignore[union-attr]
        result = fn(event) if arity == 1 else fn(event, context)
        if inspect.isawaitable(result):
            result = await result
    except BaseException as exc:  # noqa: BLE001
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        return _finish(prep, event, context, None, exc)
    return _finish(prep, event, context, result, None)


async def _await(awaitable: Any) -> Any:
    return await awaitable


def is_http(event: Event) -> bool:
    return event.type == EventType.HTTP
