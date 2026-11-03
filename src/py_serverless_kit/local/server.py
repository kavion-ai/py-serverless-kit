"""``pskit dev`` - a local HTTP server that routes requests to your handlers.

* Every ``http`` event in the config becomes a route (``{id}`` / ``{path+}`` supported).
* ``POST /__pskit/invoke/<function>``        invoke any function with a JSON body
  (``?type=queue|topic|storage|schedule|invoke``; default ``invoke``).
* ``POST /__pskit/workflows/<workflow>``     run a workflow on the embedded engine.
* ``GET  /__pskit/``                         the dashboard (local view of the project).
* Code changes are picked up on the next request (no restart needed).
"""

from __future__ import annotations

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qsl, urlsplit

from ..runtime.event import Event, EventType, Headers, HttpRequest
from ..runtime.response import Response, dumps
from ..runtime.routing import match_path, method_matches
from ..runtime.workflow import WorkflowFailed
from .runner import LocalRunner, build_event

Route = Tuple[str, str, str]  # (method, path, function)


def _routes(runner: LocalRunner) -> List[Route]:
    routes = []
    for name, fn in runner.project.config.functions.items():
        for ev in fn.events_of("http"):
            routes.append((ev.method, ev.path, name))
    # Static segments first so /users/me wins over /users/{id}.
    routes.sort(key=lambda r: (r[1].count("{"), -len(r[1])))
    return routes


class _Watcher:
    """Detects source changes by polling mtimes on request (cheap and portable)."""

    def __init__(self, root: Path, suffixes: Tuple[str, ...] = (".py",)) -> None:
        self.root = root
        self.suffixes = suffixes
        self.stamp = self._scan()
        self.lock = threading.Lock()

    def _scan(self) -> float:
        latest = 0.0
        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = [
                d for d in dirnames if not d.startswith(".") and d not in ("__pycache__", "venv", "node_modules")
            ]
            for f in filenames:
                if f.endswith(self.suffixes):
                    try:
                        latest = max(latest, os.stat(os.path.join(dirpath, f)).st_mtime)
                    except OSError:
                        pass
        return latest

    def changed(self) -> bool:
        with self.lock:
            now = self._scan()
            if now != self.stamp:
                self.stamp = now
                return True
            return False


def make_handler(runner: LocalRunner, echo=print):  # noqa: ANN001
    routes = _routes(runner)
    suffixes = (".js", ".mjs", ".cjs", ".ts", ".mts", ".cts", ".json") if runner.language == "node" else (".py",)
    watcher = _Watcher(runner.source, suffixes)
    lock = threading.Lock()  # handlers share os.environ; serialize invocations

    class Handler(BaseHTTPRequestHandler):
        server_version = "pskit-dev"

        def log_message(self, fmt: str, *args: Any) -> None:  # quieter default logging
            pass

        def _send(self, status: int, headers: Dict[str, str], body: bytes, cookies: Optional[List[str]] = None) -> None:
            self.send_response(status)
            for k, v in headers.items():
                self.send_header(k, v)
            for cookie in cookies or []:
                self.send_header("set-cookie", cookie)
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _json(self, status: int, payload: Any) -> None:
            self._send(status, {"content-type": "application/json"}, dumps(payload).encode("utf-8"))

        def _body(self) -> bytes:
            length = int(self.headers.get("content-length") or 0)
            return self.rfile.read(length) if length else b""

        def _dispatch(self) -> None:
            if watcher.changed():
                runner.reload()
                echo("  (reloaded changed source files)")
            url = urlsplit(self.path)
            if url.path.startswith("/__pskit"):
                return self._internal(url.path, dict(parse_qsl(url.query)))
            for method, pattern, fn in routes:
                params = match_path(pattern, url.path, tolerant=False)
                if params is None or not (method_matches(method, self.command) or self.command == "OPTIONS"):
                    continue
                req = HttpRequest(
                    method=self.command,
                    path=url.path,
                    headers=Headers(list(self.headers.items())),
                    query=dict(parse_qsl(url.query, keep_blank_values=True)),
                    path_params=params,
                    body=self._body(),
                    source_ip=self.client_address[0],
                )
                with lock:
                    resp: Response = runner.invoke(fn, Event(type=EventType.HTTP, http=req))
                status, headers, raw = resp.render()
                echo(f"  {self.command} {url.path} -> {fn} [{status}]")
                return self._send(status, headers, raw, resp.cookies)
            self._json(404, {"error": "Not Found", "status": 404, "routes": [f"{m} {p}" for m, p, _ in routes]})

        def _internal(self, path: str, query: Dict[str, str]) -> None:
            parts = [p for p in path.split("/") if p][1:]
            if not parts or parts == ["dashboard"]:
                from ..dashboard.generator import local_record, render_html

                html = render_html([local_record(runner.project)], title=f"{runner.project.config.service} (local)")
                return self._send(200, {"content-type": "text/html; charset=utf-8"}, html.encode("utf-8"))
            raw = self._body()
            try:
                data = json.loads(raw) if raw else None
            except ValueError:
                data = raw.decode("utf-8", "replace")
            if parts[0] == "invoke" and len(parts) == 2:
                kind = query.get("type", EventType.INVOKE)
                try:
                    with lock:
                        result = runner.invoke(parts[1], build_event(kind, data))
                except KeyError as exc:
                    return self._json(404, {"error": str(exc)})
                except Exception as exc:  # noqa: BLE001 - surface handler errors to the caller
                    return self._json(500, {"errorType": type(exc).__name__, "cause": str(exc)})
                from .runner import response_to_dict

                echo(f"  invoke {parts[1]} ({kind})")
                return self._json(200, {"result": response_to_dict(result)})
            if parts[0] == "workflows" and len(parts) == 2:
                try:
                    with lock:
                        out = runner.run_workflow(parts[1], data)
                except KeyError as exc:
                    return self._json(404, {"error": str(exc)})
                except WorkflowFailed as exc:
                    return self._json(
                        500, {"status": "FAILED", "error": exc.error, "cause": exc.cause, "history": exc.history}
                    )
                echo(f"  workflow {parts[1]} SUCCEEDED")
                return self._json(200, {"status": "SUCCEEDED", **out})
            self._json(404, {"error": f"unknown internal path {path}"})

        do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = do_OPTIONS = _dispatch

    return Handler, routes


def serve(runner: LocalRunner, host: str = "127.0.0.1", port: int = 3000, echo=print) -> None:  # noqa: ANN001
    handler, routes = make_handler(runner, echo)
    httpd = ThreadingHTTPServer((host, port), handler)
    base = f"http://{host}:{port}"
    echo(f"pskit dev server for '{runner.project.config.service}' on {base}")
    for method, path, fn in routes:
        echo(f"  {method:7} {base}{path}  -> {fn}")
    echo(f"  POST    {base}/__pskit/invoke/<function>?type=invoke|queue|topic|storage|schedule")
    if runner.project.config.workflows:
        echo(f"  POST    {base}/__pskit/workflows/<workflow>")
    echo(f"  GET     {base}/__pskit/  (dashboard)")
    echo("Press Ctrl+C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        echo("stopping")
    finally:
        httpd.server_close()
        runner.close()


def start_background(runner: LocalRunner, host: str = "127.0.0.1", port: int = 0) -> Tuple[ThreadingHTTPServer, str]:
    """Start the server on a thread (used by tests). Returns ``(server, base_url)``."""
    handler, _ = make_handler(runner, echo=lambda _m: None)
    httpd = ThreadingHTTPServer((host, port), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, f"http://{host}:{httpd.server_address[1]}"


__all__ = ["serve", "start_background"]
