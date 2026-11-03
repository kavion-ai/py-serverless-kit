"""``pskit dashboard --serve``: the dashboard page plus a small JSON API.

The API adds live data that a static page cannot have:

* ``GET  /api/deployments``                                  every deployment record
* ``GET  /api/deployments/<key>/health``                     on-prem host health and invocation stats
* ``GET  /api/deployments/<key>/logs?since=&limit=&...``     log tail (on-prem host, CloudWatch, Cloud Logging, ...)
* ``GET  /api/deployments/<key>/logs/streams?function=``      log streams (per function / container)
* ``POST /api/deployments/<key>/logs/delete``                 delete streams: ``{ids | function | all: true}``
* ``GET  /api/deployments/<key>/executions?workflow=&...``   workflow executions (paginated)
* ``GET  /api/deployments/<key>/executions/<id>``            one execution with history and output
* ``POST /api/deployments/<key>/workflows/<name>/start``     start an execution (body = input JSON)
* ``POST /api/deployments/<key>/executions/<id>/cancel``     cancel a running execution

``<key>`` is the ``.pskit/<provider>-<stage>`` directory name. The server binds
loopback by default, checks the ``Host`` header (DNS rebinding) and the
``Origin`` of every POST, and talks to on-prem hosts and cloud log APIs itself
(with this machine's credentials) so tokens never reach the browser.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, unquote, urlsplit

from .generator import collect_records, default_title, local_record, record_key, render_html

MAX_BODY = 1024 * 1024
_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_LOOPBACK = ("127.0.0.1", "localhost", "::1", "[::1]")
_WILDCARD = ("0.0.0.0", "::", "[::]")  # noqa: S104 - names, not a bind
_CSP = (
    "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; "
    "img-src 'self' data:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
)


class ApiError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


def _int(params: Dict[str, List[str]], name: str, default: int, low: int, high: int) -> int:
    raw = (params.get(name) or [""])[0].strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ApiError(400, f"{name} must be an integer") from None
    return max(low, min(high, value))


def _str(params: Dict[str, List[str]], name: str) -> Optional[str]:
    raw = (params.get(name) or [""])[0].strip()
    return raw or None


class Dashboard:
    """State shared by request handlers: the project root and how to load records."""

    def __init__(self, root: Path, title: Optional[str] = None) -> None:
        self.root = Path(root).resolve()
        self.title = title

    # ---------------------------------------------------------------- records
    def records(self) -> List[Dict[str, Any]]:
        records = collect_records(self.root)
        if records:
            return records
        try:
            from ..core.project import Project

            return [local_record(Project.load(cwd=self.root))]
        except Exception:  # noqa: BLE001 - no config here: an empty dashboard is still useful
            return []

    def record(self, key: str) -> Dict[str, Any]:
        if not _KEY_RE.match(key):
            raise ApiError(400, "invalid deployment key")
        for record in self.records():
            if record_key(record) == key:
                return record
        raise ApiError(404, f"unknown deployment {key!r}")

    def page(self) -> str:
        records = self.records()
        return render_html(records, self.title or default_title(records))

    # ---------------------------------------------------------------- live data
    def health(self, record: Dict[str, Any]) -> Dict[str, Any]:
        from ..core.onprem_control import HostUnavailable, control_for

        control = control_for(record, self.root)
        if control is None:
            return {"live": False, "reason": f"{record.get('provider')} deployments have no live host to query"}
        try:
            health = control.health()
            stats = control.stats()
        except HostUnavailable as exc:
            return {"live": False, "reason": str(exc)}
        return {"live": True, "health": health, "stats": stats}

    def _logs(self, record: Dict[str, Any]) -> Any:
        from ..core.cloud_logs import log_backend

        return log_backend(record, self.root)

    @staticmethod
    def _log_call(fn: Callable[[], Any]) -> Any:
        from ..core.cloud_logs import LogError
        from ..core.onprem_control import HostUnavailable

        try:
            return fn()
        except HostUnavailable as exc:
            raise ApiError(502, f"on-premises host unreachable: {exc}") from exc
        except LogError as exc:
            raise ApiError(502, str(exc)) from exc
        except (KeyError, LookupError) as exc:
            raise ApiError(404, str(exc.args[0] if exc.args else exc)) from exc
        except ValueError as exc:
            raise ApiError(400, str(exc)) from exc
        except PermissionError as exc:
            raise ApiError(502, str(exc)) from exc

    def logs(self, record: Dict[str, Any], params: Dict[str, List[str]]) -> Dict[str, Any]:
        backend = self._logs(record)
        if not backend.supported:
            return {**backend.info(), "entries": [], "next": 0}
        since = _int(params, "since", 0, 0, 2**62)
        limit = _int(params, "limit", 200, 1, 1000)
        result = self._log_call(
            lambda: backend.query(
                since=since,
                limit=limit,
                level=_str(params, "level"),
                function=_str(params, "function"),
                q=_str(params, "q"),
                source=_str(params, "source"),
            )
        )
        out = dict(result or {})
        out.setdefault("entries", [])
        out.setdefault("next", 0)
        out["supported"] = True
        return out

    def log_streams(self, record: Dict[str, Any], params: Dict[str, List[str]]) -> Dict[str, Any]:
        backend = self._logs(record)
        if not backend.supported:
            return {**backend.info(), "items": []}
        return dict(self._log_call(lambda: backend.streams(_str(params, "function"))) or {})

    def delete_logs(self, record: Dict[str, Any], body: Any) -> Dict[str, Any]:
        if body is None:
            body = {}
        if not isinstance(body, dict):
            raise ApiError(400, "body must be a JSON object")
        ids = body.get("ids")
        if ids is not None and (not isinstance(ids, list) or not all(isinstance(i, str) for i in ids)):
            raise ApiError(400, "ids must be a list of strings")
        function = body.get("function")
        if function is not None and not isinstance(function, str):
            raise ApiError(400, "function must be a string")
        everything = body.get("all") is True
        if not ids and not function and not everything:
            raise ApiError(400, "pass ids, function or all: true")
        backend = self._logs(record)
        if not backend.supported or not backend.can_delete:
            raise ApiError(400, backend.reason or "deleting logs is not supported for this deployment")
        return dict(self._log_call(lambda: backend.delete(ids=ids or None, function=function, all=everything)) or {})

    def _backend(self, record: Dict[str, Any]) -> Any:
        from ..core.executions import backend_for

        return backend_for(record, self.root)

    def _workflow(self, record: Dict[str, Any], name: Optional[str]) -> Optional[str]:
        if name is None:
            return None
        known = {str(w.get("name")) for w in record.get("workflows") or []}
        if name not in known:
            raise ApiError(404, f"unknown workflow {name!r}")
        return name

    def executions(self, record: Dict[str, Any], params: Dict[str, List[str]]) -> Dict[str, Any]:
        workflow = self._workflow(record, _str(params, "workflow"))
        backend = self._backend(record)
        if not backend.supported:
            return {"items": [], "total": 0, "next_token": None, "supported": False, "reason": backend.reason}
        result = self._call(
            lambda: backend.list(
                workflow=workflow,
                status=_str(params, "status"),
                limit=_int(params, "limit", 20, 1, 200),
                offset=_int(params, "offset", 0, 0, 10**9),
                token=_str(params, "token"),
            )
        )
        out = dict(result or {})
        out.setdefault("items", [])
        out.setdefault("supported", True)
        out.setdefault("reason", "")
        return out

    def execution(self, record: Dict[str, Any], execution_id: str, params: Dict[str, List[str]]) -> Dict[str, Any]:
        workflow = self._workflow(record, _str(params, "workflow"))
        backend = self._supported(record)
        return dict(self._call(lambda: backend.get(execution_id, workflow=workflow)) or {})

    def start(self, record: Dict[str, Any], workflow: str, data: Any) -> Dict[str, Any]:
        name = self._workflow(record, workflow) or workflow
        backend = self._backend(record)
        # Embedded cloud workflows keep no history but can still be started (synchronously).
        if not backend.supported and not getattr(backend, "can_start", False):
            raise ApiError(400, backend.reason or "workflows cannot be started for this deployment")
        return dict(self._call(lambda: backend.start(name, data)) or {})

    def cancel(self, record: Dict[str, Any], execution_id: str, params: Dict[str, List[str]]) -> Dict[str, Any]:
        workflow = self._workflow(record, _str(params, "workflow"))
        backend = self._supported(record)
        return dict(self._call(lambda: backend.cancel(execution_id, workflow=workflow)) or {})

    def _supported(self, record: Dict[str, Any]) -> Any:
        backend = self._backend(record)
        if not backend.supported:
            raise ApiError(400, backend.reason or "workflow executions are not available for this deployment")
        return backend

    @staticmethod
    def _call(fn: Callable[[], Any]) -> Any:
        from ..core.executions import ExecutionError

        try:
            return fn()
        except ApiError:
            raise
        except (KeyError, LookupError) as exc:
            raise ApiError(404, str(exc.args[0] if exc.args else exc)) from exc
        except ValueError as exc:
            raise ApiError(400, str(exc)) from exc
        except (ExecutionError, ImportError, OSError) as exc:
            raise ApiError(502, str(exc)) from exc


def _allowed_hosts(host: str, port: int) -> Optional[set]:
    """Host header values accepted, or None to accept any (wildcard bind)."""
    if host in _WILDCARD:
        return None

    def fmt(name: str) -> str:
        bare = name.strip("[]")
        return f"[{bare}]" if ":" in bare else bare

    names = {host}
    if host in _LOOPBACK:
        names.update(_LOOPBACK)
    return {f"{fmt(name)}:{port}".lower() for name in names}


def make_handler(app: Dashboard) -> type:
    class Handler(BaseHTTPRequestHandler):
        server_version = "pskit-dashboard"
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt: str, *args: Any) -> None:
            return None

        # ------------------------------------------------------------ io
        def _send(self, status: int, body: bytes, content_type: str, extra: Optional[Dict[str, str]] = None) -> None:
            self.send_response(status)
            self.send_header("content-type", content_type)
            self.send_header("content-length", str(len(body)))
            self.send_header("cache-control", "no-store")
            self.send_header("x-content-type-options", "nosniff")
            self.send_header("referrer-policy", "no-referrer")
            self.send_header("x-frame-options", "DENY")
            for key, value in (extra or {}).items():
                self.send_header(key, value)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _json(self, status: int, payload: Any) -> None:
            body = json.dumps(payload, default=str).encode("utf-8")
            self._send(status, body, "application/json; charset=utf-8")

        def _read_raw(self) -> bytes:
            """Read the request body once (cached). Raises 400/413 for a bad or oversized length."""
            cached = getattr(self, "_raw_body", None)
            if cached is not None:
                return cached
            raw_length = self.headers.get("content-length") or "0"
            try:
                length = int(raw_length)
            except ValueError:
                raise ApiError(400, "invalid content-length") from None
            if length < 0 or length > MAX_BODY:
                raise ApiError(413, f"request body must be at most {MAX_BODY} bytes")
            self._raw_body: Optional[bytes] = self.rfile.read(length) if length else b""
            return self._raw_body

        def _body(self) -> Any:
            raw = self._read_raw()
            if not raw.strip():
                return None
            try:
                return json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, ValueError):
                raise ApiError(400, "request body must be JSON") from None

        def _discard_body(self) -> None:
            # The unread body must not be parsed as the next request. Read a bounded amount so
            # closing does not reset the connection before the client has read the 413.
            self.close_connection = True
            try:
                self.connection.settimeout(0.5)
                left = 64 * 1024
                while left > 0:
                    chunk = self.rfile.read1(min(left, 8192))  # type: ignore[attr-defined]
                    if not chunk:
                        break
                    left -= len(chunk)
            except OSError:
                pass

        # ------------------------------------------------------------ checks
        def _host_ok(self) -> bool:
            server = self.server
            allowed = getattr(server, "allowed_hosts", None)
            if allowed is None:
                return True
            return (self.headers.get("host") or "").strip().lower() in allowed

        def _post_ok(self) -> Optional[str]:
            ctype = (self.headers.get("content-type") or "").split(";")[0].strip().lower()
            if ctype != "application/json":
                return "POST requires content-type: application/json"
            origin = self.headers.get("origin")
            if origin is None:
                return None  # not a browser cross-origin request (curl, scripts)
            host = (self.headers.get("host") or "").strip().lower()
            parsed = urlsplit(origin)
            if parsed.scheme not in ("http", "https") or parsed.netloc.lower() != host:
                return "cross-origin request refused"
            return None

        # ------------------------------------------------------------ verbs
        def do_GET(self) -> None:  # noqa: N802
            self._handle("GET")

        def do_HEAD(self) -> None:  # noqa: N802
            self._handle("GET")

        def do_POST(self) -> None:  # noqa: N802
            self._handle("POST")

        def _handle(self, method: str) -> None:
            self._raw_body = None
            if not self._host_ok():
                return self._json(421, {"error": "unexpected Host header"})
            url = urlsplit(self.path)
            try:
                if not url.path.startswith("/api/"):
                    if method != "GET":
                        raise ApiError(405, "method not allowed")
                    if url.path in ("/", "/index.html"):
                        body = app.page().encode("utf-8")
                        return self._send(200, body, "text/html; charset=utf-8", {"content-security-policy": _CSP})
                    raise ApiError(404, "not found")
                if method == "POST":
                    # Read the body before any check can reject the request: answering with unread
                    # data in the socket makes Windows reset the connection before the client reads it.
                    self._read_raw()
                    problem = self._post_ok()
                    if problem:
                        raise ApiError(403, problem)
                status, payload = self._api(method, url.path, parse_qs(url.query, keep_blank_values=True))
                self._json(status, payload)
            except ApiError as exc:
                self._json(exc.status, {"error": exc.message})
                if exc.status == 413:
                    self._discard_body()
            except Exception as exc:  # noqa: BLE001 - last-resort JSON error
                self._json(500, {"error": f"{type(exc).__name__}: {exc}"})

        def _api(self, method: str, path: str, params: Dict[str, List[str]]) -> Tuple[int, Any]:
            parts = [unquote(p) for p in path.split("/") if p][1:]  # drop "api"
            if parts == ["deployments"] and method == "GET":
                stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
                return 200, {"generated_at": stamp, "deployments": app.records()}
            if len(parts) < 3 or parts[0] != "deployments":
                raise ApiError(404, "unknown API endpoint")
            record = app.record(parts[1])
            rest = parts[2:]
            if method == "GET":
                if rest == ["health"]:
                    return 200, app.health(record)
                if rest == ["logs"]:
                    return 200, app.logs(record, params)
                if rest == ["logs", "streams"]:
                    return 200, app.log_streams(record, params)
                if rest == ["executions"]:
                    return 200, app.executions(record, params)
                if len(rest) == 2 and rest[0] == "executions":
                    return 200, app.execution(record, rest[1], params)
            if method == "POST":
                if rest == ["logs", "delete"]:
                    return 200, app.delete_logs(record, self._body())
                if len(rest) == 3 and rest[0] == "workflows" and rest[2] == "start":
                    return 202, app.start(record, rest[1], self._body())
                if len(rest) == 3 and rest[0] == "executions" and rest[2] == "cancel":
                    self._body()
                    return 200, app.cancel(record, rest[1], params)
            raise ApiError(404 if method == "GET" else 405, "unknown API endpoint")

    return Handler


class DashboardHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    allowed_hosts: Optional[set] = None


def make_server(
    root: Path, host: str = "127.0.0.1", port: int = 8765, title: Optional[str] = None
) -> DashboardHTTPServer:
    app = Dashboard(root, title)
    httpd = DashboardHTTPServer((host, port), make_handler(app))
    httpd.allowed_hosts = _allowed_hosts(host, httpd.server_address[1])
    return httpd


def is_loopback(host: str) -> bool:
    return host in _LOOPBACK
