"""``pskit studio``: build a project in the browser instead of writing YAML by hand.

Serves ``studio.html`` (a single-file React build of ``dashboard-ui/``) and the
JSON API it uses. The studio can write files and run deploys, so every API call
needs the session token printed on start (``x-studio-token``). The server also
binds loopback by default, checks the ``Host`` header (DNS rebinding), requires
a same-origin ``Origin`` and a JSON body on writes, and confines file access to
the project.
"""

from __future__ import annotations

import json
import secrets
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, unquote, urlsplit

from .._version import __version__
from ..dashboard.server import _allowed_hosts, is_loopback
from . import devenv, files, guides, project, system
from .discover import discover
from .jobs import JobManager
from .project import StudioError
from .vscode import VSCode

PAGE = Path(__file__).with_name("studio.html")
MAX_BODY = 2 * 1024 * 1024
# Uploads through a service browser carry the file as base64 in JSON (64 MB file -> ~86 MB body).
MAX_UPLOAD_BODY = 90 * 1024 * 1024
_CSP = (
    "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; "
    "img-src 'self' data:; font-src 'self' data:; frame-src http://127.0.0.1:* http://localhost:*; "
    "base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
)
_MUTATING = ("POST", "PUT", "DELETE")


class Studio:
    """State shared by request handlers."""

    def __init__(self, root: Path, token: Optional[str] = None, vscode_image: Optional[str] = None) -> None:
        self.root = Path(root).resolve()
        self.token = token if token is not None else secrets.token_urlsafe(24)
        self.jobs = JobManager(self.root)
        self.terminal_urls: Dict[str, str] = {}  # browser terminal name -> its secret URL (known only here)
        self.vscode = VSCode(self.root, image=vscode_image)
        self._meta: Optional[Dict[str, Any]] = None
        self._cluster_watch: Any = None
        self._service_watch: Any = None
        self._hana: Any = None

    def hana(self) -> Any:
        """Hana, the studio's AI assistant: where the model runs (``runtime``) and the chats (``chat``)."""
        if self._hana is None:
            from .hana.runtime import Runtime
            from .hana.session import Hana

            runtime = Runtime(self.root)
            self._hana = (runtime, Hana(self.root, runtime.model))
        return self._hana

    def service_watch(self) -> Any:
        """Checks on-prem services whose alerts are on (database CPU / memory / disk / lag) while the studio runs."""
        if self._service_watch is None:
            from ..core.onprem_monitor import Watcher as ServiceWatcher

            self._service_watch = ServiceWatcher(self.root)
            self._service_watch.start()
        return self._service_watch

    def cluster_watch(self) -> Any:
        """Checks scaling clusters that have `watch` on (capacity alerts) while the studio runs."""
        if self._cluster_watch is None:
            from ..core.onprem_cluster import Watcher

            self._cluster_watch = Watcher(self.root)
            self._cluster_watch.start()
        return self._cluster_watch

    def meta(self) -> Dict[str, Any]:
        if self._meta is None:
            from .meta import build_meta

            self._meta = build_meta()
        return self._meta

    def page(self) -> bytes:
        try:
            return PAGE.read_bytes()
        except OSError:
            return b"<!doctype html><title>pskit studio</title><p>studio.html is missing from this install.</p>"

    def raw_config(self) -> Dict[str, Any]:
        path = project.config_path(self.root)
        if path is None:
            return {}
        raw, _ = project.parse_text(path.read_text("utf-8"))
        return raw or {}


def _param(params: Dict[str, List[str]], name: str) -> Optional[str]:
    raw = (params.get(name) or [""])[0].strip()
    return raw or None


def _int(params: Dict[str, List[str]], name: str, default: int) -> int:
    raw = _param(params, name)
    if raw is None:
        return default
    if not raw.isdigit():
        raise StudioError(400, f"{name} must be a non-negative integer")
    return int(raw)


def _deployed_on(root: Path, stage: str) -> Optional[Dict[str, Any]]:
    """Where ``onprem-<stage>`` was last deployed: the studio's server pickers default to it."""
    from ..core.onprem_control import deployed_host, deployed_on
    from .system import deployment_record

    data = deployed_host(root, stage)
    if data is None:
        return None
    out = {**deployed_on(data["spec"], data.get("server"), data.get("cluster")), "deployed_at": data.get("deployed_at")}
    record = deployment_record(root, "onprem", stage) or {}
    for key in ("groups", "balancers"):  # provider.options.placement / .balancer (deployment.json)
        if record.get(key):
            out[key] = record[key]
    return out


def _obj(body: Any) -> Dict[str, Any]:
    if body is None:
        return {}
    if not isinstance(body, dict):
        raise StudioError(400, "request body must be a JSON object")
    return body


def make_handler(app: Studio) -> type:
    class Handler(BaseHTTPRequestHandler):
        server_version = "pskit-studio"
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
            self._send(status, json.dumps(payload, default=str).encode("utf-8"), "application/json; charset=utf-8")

        def _length(self) -> int:
            try:
                length = int(self.headers.get("content-length") or "0")
            except ValueError:
                raise StudioError(400, "invalid content-length") from None
            limit = MAX_UPLOAD_BODY if "/browse/" in self.path or "/settings-bundle/" in self.path else MAX_BODY
            if length < 0 or length > limit:
                raise StudioError(413, f"request body must be at most {limit} bytes")
            return length

        def _body(self) -> Any:
            length = self._length()
            raw = self.rfile.read(length) if length else b""
            if not raw.strip():
                return None
            try:
                return json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, ValueError):
                raise StudioError(400, "request body must be JSON") from None

        def _drain(self) -> None:
            # Unread request body: read a bounded amount, then close, so the client gets the error
            # instead of a reset connection.
            if (self.headers.get("content-length") or "0").strip() in ("", "0"):
                return
            self.close_connection = True
            try:
                self.connection.settimeout(0.5)
                left = 8 * 1024 * 1024  # enough for any realistic oversized request
                while left > 0:
                    chunk = self.rfile.read1(min(left, 8192))  # type: ignore[attr-defined]
                    if not chunk:
                        break
                    left -= len(chunk)
            except OSError:
                pass

        # ------------------------------------------------------------ checks
        def _host_ok(self) -> bool:
            allowed = getattr(self.server, "allowed_hosts", None)
            return allowed is None or (self.headers.get("host") or "").strip().lower() in allowed

        def _token_ok(self) -> bool:
            sent = self.headers.get("x-studio-token") or ""
            return bool(app.token) and secrets.compare_digest(sent.encode(), app.token.encode())

        def _write_problem(self) -> Optional[Tuple[int, str]]:
            origin = self.headers.get("origin")
            if origin is not None:
                host = (self.headers.get("host") or "").strip().lower()
                parsed = urlsplit(origin)
                if parsed.scheme not in ("http", "https") or parsed.netloc.lower() != host:
                    return 403, "cross-origin request refused"
            if self.command in ("POST", "PUT"):
                ctype = (self.headers.get("content-type") or "").split(";")[0].strip().lower()
                if ctype != "application/json":
                    return 415, "requests must use content-type: application/json"
            return None

        # ------------------------------------------------------------ verbs
        def do_GET(self) -> None:  # noqa: N802
            self._handle()

        def do_HEAD(self) -> None:  # noqa: N802
            self._handle()

        def do_POST(self) -> None:  # noqa: N802
            self._handle()

        def do_PUT(self) -> None:  # noqa: N802
            self._handle()

        def do_DELETE(self) -> None:  # noqa: N802
            self._handle()

        def _handle(self) -> None:
            method = "GET" if self.command == "HEAD" else self.command
            if not self._host_ok():
                self._drain()
                return self._json(421, {"error": "unexpected Host header"})
            url = urlsplit(self.path)
            try:
                if not url.path.startswith("/api/"):
                    if method != "GET":
                        raise StudioError(405, "method not allowed")
                    if url.path in ("/", "/index.html", "/studio.html"):
                        return self._send(
                            200, app.page(), "text/html; charset=utf-8", {"content-security-policy": _CSP}
                        )
                    raise StudioError(404, "not found")
                if url.path == "/api/health" and method == "GET":
                    return self._json(200, {"ok": True, "version": __version__, "root": str(app.root)})
                if not self._token_ok():
                    raise StudioError(401, "studio token required", code="token")
                if method in _MUTATING:
                    problem = self._write_problem()
                    if problem:
                        raise StudioError(*problem)
                status, payload = self._api(method, url.path, parse_qs(url.query, keep_blank_values=True))
                self._json(status, payload)
            except StudioError as exc:
                if exc.status in (401, 403, 413, 415):
                    self._drain()
                self._json(exc.status, {"error": exc.message, **exc.extra})
            except Exception as exc:  # noqa: BLE001 - last-resort JSON error
                self._json(500, {"error": f"{type(exc).__name__}: {exc}"})

        # ------------------------------------------------------------ routes
        def _api(self, method: str, path: str, params: Dict[str, List[str]]) -> Tuple[int, Any]:
            parts = [unquote(p) for p in path.split("/") if p][1:]
            root = app.root
            if parts == ["meta"] and method == "GET":
                return 200, app.meta()
            if parts == ["project"]:
                if method == "GET":
                    return 200, project.get_project(root)
                if method == "PUT":
                    body = _obj(self._body())
                    return 200, project.save_project(root, body.get("raw"), body.get("mtime"), bool(body.get("force")))
            if parts == ["project", "validate"] and method == "POST":
                body = _obj(self._body())
                return 200, project.validate(root, body.get("raw"), body.get("provider"), body.get("stage"))
            if parts == ["project", "parse"] and method == "POST":
                body = _obj(self._body())
                text = body.get("text")
                if not isinstance(text, str):
                    raise StudioError(400, "text must be a string")
                raw, issues = project.parse_text(text)
                return 200, {"raw": raw, "issues": issues}
            if parts == ["project", "init"] and method == "POST":
                body = _obj(self._body())
                return 201, project.init_project(
                    root,
                    str(body.get("service") or ""),
                    str(body.get("provider") or ""),
                    str(body.get("template") or "http"),
                    bool(body.get("force")),
                    str(body.get("language") or "python"),
                )
            if parts == ["files", "tree"] and method == "GET":
                return 200, files.tree(root)
            if parts == ["files"]:
                if method == "GET":
                    return 200, files.read_file(root, _param(params, "path"))
                if method == "PUT":
                    body = _obj(self._body())
                    return 200, files.write_file(
                        root, body.get("path"), body.get("text"), body.get("mtime"), bool(body.get("force"))
                    )
            if parts == ["handlers", "ensure"] and method == "POST":
                body = _obj(self._body())
                events = body.get("events") or []
                if not isinstance(events, list):
                    raise StudioError(400, "events must be a list")
                return 200, project.ensure_handler(root, str(body.get("handler") or ""), [str(e) for e in events],
                                                   subproject=bool(body.get("subproject")))
            if parts == ["functions", "shared"] and method == "GET":
                from ..core import function_split

                try:
                    return 200, {"shared": function_split.shared_in_project(root)}
                except function_split.SplitError as exc:
                    raise StudioError(400, str(exc)) from None
            if len(parts) == 3 and parts[0] == "functions" and parts[2] == "split" and method == "POST":
                from ..core import function_split

                body = _obj(self._body())
                try:
                    run = function_split.plan if body.get("dry_run") else function_split.split
                    result = run(root, parts[1])
                except function_split.SplitError as exc:
                    raise StudioError(400, str(exc)) from None
                return 200, {**result, "lines": function_split.describe(result), "project": project.get_project(root)}
            if parts == ["discover"] and method == "GET":
                provider = _param(params, "provider") or str((app.raw_config().get("provider") or {}).get("name") or "")
                return 200, discover(
                    root, provider, _param(params, "kind") or "", _param(params, "region"), app.raw_config()
                )
            if parts == ["env"] and method == "GET":
                reqs = str((app.raw_config().get("package") or {}).get("requirements") or "requirements.txt")
                return 200, devenv.status(root, reqs)
            if parts == ["env", "setup"] and method == "POST":
                body = _obj(self._body())
                raw = app.raw_config()
                runtime = str((raw.get("provider") or {}).get("runtime") or "")
                language = str(body.get("language") or ("node" if runtime.startswith("nodejs") else "python"))
                if language not in ("python", "node"):
                    raise StudioError(400, "language must be python or node")
                try:
                    steps = devenv.plan(
                        root,
                        language=language,
                        python=str(body["python"]) if body.get("python") else None,
                        recreate=bool(body.get("recreate")),
                        requirements=str((raw.get("package") or {}).get("requirements") or "requirements.txt"),
                    )
                except ValueError as exc:
                    raise StudioError(400, str(exc)) from None
                label = "npm install" if language == "node" else "Create .venv and install requirements"
                job = app.jobs.run_callable("env", lambda j: devenv.run_steps(root, steps, j.emit), label=label)
                return 202, {"job_id": job.id}
            if parts == ["test-guide"] and method == "GET":
                provider = _param(params, "provider") or str((app.raw_config().get("provider") or {}).get("name") or "")
                stage = _param(params, "stage") or str((app.raw_config().get("provider") or {}).get("stage") or "dev")
                return 200, system.test_guide(root, provider, stage)
            if parts == ["resource-test-guide"] and method == "GET":
                provider = _param(params, "provider") or str((app.raw_config().get("provider") or {}).get("name") or "")
                stage = _param(params, "stage") or str((app.raw_config().get("provider") or {}).get("stage") or "dev")
                return 200, system.resource_test_guide(root, provider, stage)
            if parts and parts[0] in ("resource-check", "resource-clear", "resource-usage", "resource-data",
                                      "resource-object", "resource-message-delete") \
                    and len(parts) == 1 and method == "POST":
                body = _obj(self._body())
                raw_provider = (app.raw_config().get("provider") or {})
                provider = str(body.get("provider") or raw_provider.get("name") or "")
                stage = str(body.get("stage") or raw_provider.get("stage") or "dev")
                action = parts[0].split("-", 1)[1]
                return 200, system.resource_action(root, provider, stage, str(body.get("key") or ""), action, body)
            if parts == ["test-events"]:
                if method == "GET":
                    return 200, system.test_events(root)
                if method == "PUT":
                    return 200, system.save_test_events(root, _obj(self._body()).get("events"))
            if parts == ["cloud-resources"] and method == "GET":
                provider = _param(params, "provider") or str((app.raw_config().get("provider") or {}).get("name") or "")
                stage = _param(params, "stage") or str((app.raw_config().get("provider") or {}).get("stage") or "dev")
                return 200, system.cloud_resources(root, provider, stage)
            if parts and parts[0] == "resource-guides" and method == "GET":
                if len(parts) == 1:
                    return 200, guides.index()
                if len(parts) == 3:
                    return 200, guides.page(parts[1], parts[2])
            if parts and parts[0] == "hana":
                return self._hana(method, parts[1:], params)
            if parts and parts[0] == "onprem-services":
                return self._onprem_services(method, parts[1:], params)
            if parts and parts[0] in ("onprem-servers", "onprem-terminals"):
                return self._onprem_machines(method, parts, params)
            if parts and parts[0] == "onprem-clusters":
                return self._onprem_clusters(method, parts[1:], params)
            if parts and parts[0] == "onprem-balancers":
                return self._onprem_balancers(method, parts[1:], params)
            if parts == ["onprem-firewall"] and method == "GET":
                from ..core import onprem_network as network

                return 200, {"servers": network.by_server(network.project(app.root))}
            if parts == ["onprem-usage"] and method == "GET":
                from ..core import onprem_usage as usage

                raw = app.raw_config()
                return 200, {"servers": usage.server_usage(app.root, raw), "map": usage.network_map(app.root, raw)}
            if parts == ["resource-bindings"] and method == "GET":
                from ..core import onprem_usage as usage

                return 200, {"resources": usage.resource_bindings(app.root, app.raw_config())}
            if parts == ["fs"] and method == "GET":
                return 200, system.browse(_param(params, "path"))
            if parts == ["setup"] and method == "GET":
                provider = _param(params, "provider") or str((app.raw_config().get("provider") or {}).get("name") or "")
                return 200, system.setup_status(provider, app.raw_config(), root)
            if parts == ["setup", "env"] and method == "POST":
                body = _obj(self._body())
                value = body.get("value")
                return 200, system.set_env(str(body.get("name") or ""), None if value is None else str(value))
            if parts == ["setup", "aws-profile"] and method == "POST":
                return 200, system.aws_profile(_obj(self._body()))
            if parts == ["setup", "login"] and method == "POST":
                body = _obj(self._body())
                action = str(body.get("action") or "")
                job = app.jobs.run_process("login", system.login_command(action), label=f"login: {action}")
                return 202, {"job_id": job.id}
            if parts and parts[0] == "settings-bundle" and method == "POST":
                return self._settings_bundle(parts[1:], _obj(self._body()))
            if parts == ["setup", "ssh-test"] and method == "POST":
                body = _obj(self._body())
                job = app.jobs.run_process("ssh-test", system.ssh_command(body.get("deploy")), label="SSH test")
                return 202, {"job_id": job.id}
            if parts and parts[0] == "logs":
                provider = _param(params, "provider") or str((app.raw_config().get("provider") or {}).get("name") or "")
                stage = _param(params, "stage") or str((app.raw_config().get("provider") or {}).get("stage") or "dev")
                server = _param(params, "server") or None
                if parts == ["logs"] and method == "GET":
                    return 200, system.logs_query(
                        root,
                        provider,
                        stage,
                        server=server,
                        since=_int(params, "since", 0),
                        limit=max(1, min(1000, _int(params, "limit", 200))),
                        level=_param(params, "level"),
                        function=_param(params, "function"),
                        q=_param(params, "q"),
                        source=_param(params, "source"),
                    )
                if parts == ["logs", "streams"] and method == "GET":
                    return 200, system.logs_streams(root, provider, stage, _param(params, "function"), server)
                if parts == ["logs", "delete"] and method == "POST":
                    return 200, system.logs_delete(root, provider, stage, _obj(self._body()), server)
            if parts == ["jobs"]:
                if method == "GET":
                    return 200, {"jobs": app.jobs.list()}
                if method == "DELETE":
                    return 200, app.jobs.clear()
                if method == "POST":
                    body = _obj(self._body())
                    args = body.get("args") or {}
                    if not isinstance(args, dict):
                        raise StudioError(400, "args must be an object")
                    job = app.jobs.start(str(body.get("command") or ""), body.get("provider"), body.get("stage"), args)
                    return 202, {"job_id": job.id}
            if len(parts) == 2 and parts[0] == "jobs" and method == "DELETE":
                return 200, app.jobs.clear(parts[1])
            if len(parts) == 2 and parts[0] == "jobs" and method == "GET":
                since = _param(params, "since") or "0"
                if not since.isdigit():
                    raise StudioError(400, "since must be an integer")
                return 200, app.jobs.get(parts[1]).snapshot(int(since))
            if len(parts) == 3 and parts[0] == "jobs" and parts[2] == "cancel" and method == "POST":
                self._body()
                return 200, app.jobs.cancel(parts[1])
            if parts == ["vscode"] and method == "GET":
                return 200, app.vscode.status()
            if parts == ["vscode", "start"] and method == "POST":
                body = _obj(self._body())
                if body.get("image"):
                    image = str(body["image"])
                    if any(c.isspace() for c in image) or image.startswith("-"):
                        raise StudioError(400, "invalid image name")
                    app.vscode.image = image
                try:
                    app.vscode.set_runtimes(
                        str(body["python"]) if body.get("python") else None,
                        str(body["node"]) if body.get("node") else None,
                    )
                except ValueError as exc:
                    raise StudioError(400, str(exc)) from None
                job = app.jobs.run_callable("vscode", app.vscode.start, label="VS Code (code-server)")
                app.vscode.log_job = job.id
                return 202, {"job_id": job.id}
            if parts == ["vscode", "stop"] and method == "POST":
                self._body()
                stopped = app.vscode.stop()
                state = app.vscode.status()  # the UI renders the panel from the full state
                state.update(stopped)
                return 200, state
            raise StudioError(404 if method == "GET" else 405, "unknown API endpoint")

        def _hana(self, method: str, rest: List[str], params: Dict[str, List[str]]) -> Tuple[int, Any]:
            """Hana, the AI assistant: where the model runs, chats, turns and the user's answers to her."""
            from .hana.runtime import DEFAULT_IMAGE, check_image

            runtime, chat = app.hana()
            if not rest and method == "GET":
                return 200, {"runtime": runtime.status(), "sessions": chat.list()}
            if rest == ["install"] and method == "POST":
                body = _obj(self._body())
                image = check_image(str(body.get("image") or DEFAULT_IMAGE))
                target = str(body.get("target") or "local")
                if target == "server":
                    server = str(body.get("server") or "")
                    if not server:
                        raise StudioError(400, "server is required")
                    job = app.jobs.run_callable("hana", lambda j: runtime.install_server(j, server, image),
                                                label=f"Install Hana on {server}")
                elif target == "local":
                    job = app.jobs.run_callable("hana", lambda j: runtime.install_local(j, image),
                                                label="Install Hana (Docker, this machine)")
                elif target == "huggingface":
                    from .hana.runtime import HF_FILES

                    file = str(body.get("file") or HF_FILES[0]["file"])
                    job = app.jobs.run_callable("hana", lambda j: runtime.install_hf(j, file),
                                                label="Install Hana (Hugging Face, in studio)")
                else:
                    raise StudioError(400, "target must be local, server or huggingface")
                return 202, {"job_id": job.id}
            if rest == ["endpoint"] and method == "POST":
                body = _obj(self._body())
                return 200, runtime.use_endpoint(str(body.get("url") or ""), str(body.get("api_key_env") or ""))
            if rest == ["stop"] and method == "POST":
                body = _obj(self._body())
                return 200, runtime.stop(remove_data=bool(body.get("remove_data")))
            if rest == ["messages"] and method == "POST":
                body = _obj(self._body())
                env = _obj(body.get("env"))
                turn = chat.send(str(body.get("session") or "") or None, str(body.get("text") or ""), env)
                return 202, {"session_id": turn.session.id, "turn_id": turn.id}
            if len(rest) == 2 and rest[0] == "sessions":
                session = chat.get(rest[1])
                if method == "GET":
                    running = session.turn if session.turn and session.turn.status in ("running", "waiting") else None
                    return 200, {**session.summary(), "display": session.display,
                                 "turn_id": running.id if running else None}
                if method == "DELETE":
                    return 200, chat.delete(rest[1])
            if len(rest) == 3 and rest[0] == "sessions" and rest[2] == "edit" and method == "POST":
                body = _obj(self._body())
                index = body.get("index")
                if not isinstance(index, int):
                    raise StudioError(400, "index must be a number")
                turn = chat.edit(rest[1], index, str(body.get("text") or ""), _obj(body.get("env")))
                return 202, {"session_id": turn.session.id, "turn_id": turn.id}
            if rest == ["sessions"] and method == "DELETE":
                return 200, chat.delete_all()
            if rest == ["functions"] and method == "POST":
                from .hana.edits import create_functions

                body = _obj(self._body())
                fns = body.get("names")
                if not isinstance(fns, list):
                    raise StudioError(400, "names must be a list")
                existing = body.get("existing") or {}
                if not isinstance(existing, dict):
                    raise StudioError(400, "existing must map a function name to update, rename or skip")
                return 200, create_functions(app.root, [str(n) for n in fns], str(body.get("trigger") or "none"),
                                             str(body.get("schedule") or "5 minutes"),
                                             placement=str(body.get("placement") or "module"),
                                             module=str(body.get("module") or ""),
                                             existing={str(k): str(v) for k, v in existing.items()})
            if rest == ["separate"] and method == "POST":
                from .hana.edits import separate_functions

                fns = _obj(self._body()).get("functions")
                if not isinstance(fns, list) or not fns:
                    raise StudioError(400, "functions must be a list of function names")
                return 200, separate_functions(app.root, [str(n) for n in fns])
            if rest == ["resources"] and method == "POST":
                from .hana.edits import create_resources

                body = _obj(self._body())
                items = body.get("items")
                if not isinstance(items, list) or not all(isinstance(i, dict) for i in items):
                    raise StudioError(400, "items must be a list of resources")
                return 200, create_resources(app.root, items)
            if rest == ["code"] and method == "POST":
                from .hana.edits import write_code

                body = _obj(self._body())
                fns = body.get("functions")
                if not isinstance(fns, list):
                    raise StudioError(400, "functions must be a list")
                return 200, write_code(app.root, [str(n) for n in fns])
            if rest == ["workflow"] and method == "POST":
                from .hana.edits import create_workflow

                body = _obj(self._body())
                steps = body.get("steps")
                if not isinstance(steps, list):
                    raise StudioError(400, "steps must be a list of function names")
                create = body.get("create_functions") or []
                try:
                    wait = float(body.get("wait_seconds") or 0)
                except (TypeError, ValueError):
                    raise StudioError(400, "wait_seconds must be a number") from None
                return 200, create_workflow(app.root, str(body.get("name") or ""), [str(s) for s in steps],
                                            str(body.get("description") or ""), wait_seconds=wait,
                                            create_functions=[str(f) for f in create] if isinstance(create, list) else [])
            if rest == ["remove-item"] and method == "POST":
                from .hana.edits import remove

                body = _obj(self._body())
                return 200, remove(app.root, str(body.get("kind") or ""), str(body.get("name") or ""),
                                   delete_code=body.get("delete_code") is not False)
            if len(rest) == 3 and rest[0] == "sessions" and rest[2] == "note" and method == "POST":
                return 200, chat.note(rest[1], str(_obj(self._body()).get("text") or ""))
            if len(rest) == 2 and rest[0] == "turns" and method == "GET":
                return 200, chat.turn(rest[1]).snapshot(_int(params, "since", 0))
            if len(rest) == 3 and rest[0] == "turns" and rest[2] == "answer" and method == "POST":
                body = _obj(self._body())
                decision = str(body.get("decision") or "")
                if decision not in ("approve", "reject", "answer"):
                    raise StudioError(400, "decision must be approve, reject or answer")
                chat.turn(rest[1]).respond(str(body.get("pending_id") or ""),
                                           {"decision": decision, "text": str(body.get("text") or "")[:2000]})
                return 200, {"ok": True}
            if len(rest) == 3 and rest[0] == "turns" and rest[2] == "stop" and method == "POST":
                self._body()
                chat.turn(rest[1]).stop()
                return 200, {"ok": True}
            raise StudioError(404 if method == "GET" else 405, "unknown Hana endpoint")

        def _onprem_services(self, method: str, rest: List[str], params: Dict[str, List[str]]) -> Tuple[int, Any]:
            """Docker services for on-prem functions: create, inspect, back up, remove (long steps as jobs)."""
            from ..core import onprem_monitor as mon
            from ..core import onprem_services as svc

            root = app.root
            watcher = app.service_watch()
            try:
                if not rest and method == "GET":
                    raw = app.raw_config()
                    return 200, {
                        "catalog": svc.catalog(),
                        "services": svc.list_services(root),
                        "default_target": svc.default_target(raw),
                        "default_target_problem": svc.default_target_problem(raw, root),
                        "env_file": svc.env_file_of(raw),
                    }
                if not rest and method == "POST":
                    body = _obj(self._body())
                    raw = app.raw_config()
                    svc.check_request(body, root, raw, place=False)  # fail fast with a 400, not a failed job
                    label = f"Create {body.get('service')} {body.get('key')}"

                    def create(job: Any) -> int:
                        svc.create(root, body, raw, job.emit)
                        return 0

                    return 202, {"job_id": app.jobs.run_callable("onprem-service", create, label=label).id}
                if rest in (["apply"], ["unapply"]) and method == "POST":
                    body = _obj(self._body())
                    draft = body.get("raw")
                    if not isinstance(draft, dict):
                        raise StudioError(400, "raw must be the project as an object")
                    key = str(body.get("key") or "")
                    if rest == ["unapply"]:
                        return 200, {"raw": svc.remove_from_raw(draft, key)}
                    entry = svc.load_state(root)["services"].get(key)
                    if not isinstance(entry, dict):
                        raise StudioError(404, f"no on-prem service {key!r}")
                    attach = body.get("attach")
                    return 200, {"raw": svc.apply_to_raw(draft, entry, attach if isinstance(attach, list) else None)}
                if len(rest) == 1 and method == "GET":
                    reveal = _param(params, "reveal") in ("1", "true")
                    return 200, svc.status(root, rest[0], reveal=reveal)
                if len(rest) == 2 and rest[1] == "usage" and method == "GET":
                    return 200, svc.service_usage(root, rest[0], reveal=_param(params, "reveal") in ("1", "true"))
                if len(rest) == 2 and rest[1] == "logs" and method == "GET":
                    return 200, {"text": svc.logs(root, rest[0], tail=max(10, min(2000, _int(params, "tail", 200))))}
                if len(rest) == 2 and rest[1] in ("gui", "gui-remove", "gui-check") and method == "POST":
                    key, action = rest
                    body = _obj(self._body())
                    svc._entry(root, key)

                    def run_gui(job: Any) -> int:
                        if action == "gui":
                            port = body.get("port")
                            svc.add_gui(root, key, job.emit, port=int(port) if port else None,
                                        login=str(body.get("login") or "password"), password=str(body.get("password") or ""))
                        elif action == "gui-check":
                            return 0 if svc.gui_check(root, key, job.emit)["ok"] else 1
                        else:
                            svc.remove_gui(root, key, job.emit)
                        return 0

                    label = {"gui": "Start", "gui-remove": "Remove", "gui-check": "Check"}[action] + f" web UI of {key}"
                    return 202, {"job_id": app.jobs.run_callable("onprem-service", run_gui, label=label).id}
                if len(rest) == 4 and rest[1] == "browse" and method == "POST":
                    from ..core import onprem_browser as brw

                    try:
                        return 200, brw.browse(svc._entry(root, rest[0]), rest[2], rest[3], _obj(self._body()))
                    except brw.BrowseError as exc:
                        raise StudioError(400, str(exc)) from None
                if len(rest) == 2 and rest[1] == "console":
                    from ..core import onprem_console as con

                    if method == "GET":
                        return 200, con.console_info(svc._entry(root, rest[0]))
                    if method == "POST":
                        body = _obj(self._body())
                        try:
                            return 200, con.run_line(root, rest[0], str(body.get("line") or ""), shell=bool(body.get("shell")))
                        except con.ConsoleError as exc:
                            raise StudioError(400, str(exc)) from None
                if len(rest) == 2 and rest[1] == "monitor" and method == "GET":
                    return 200, mon.sample(root, rest[0])
                if len(rest) == 2 and rest[1] == "alert":
                    key = rest[0]
                    if method == "PUT":
                        mon.set_alert(root, key, _obj(self._body()))
                    entry = svc._entry(root, key)
                    return 200, {"alert": mon.alert_settings(entry), "history": list(entry.get("alerts") or [])[-20:],
                                 "last": watcher.last.get(key)}
                if len(rest) == 2 and rest[1] in ("alert-test", "alert-check") and method == "POST":
                    key = rest[0]
                    if rest[1] == "alert-test":
                        return 200, mon.send_alert(root, key, mon.sample(root, key), [], test=True)
                    result = mon.check(root, key)
                    watcher.last[key] = {"checked_at": result["checked_at"], "reasons": result["reasons"],
                                         "alert": result.get("alert")}
                    return 200, result
                if rest == ["alert-function"] and method == "POST":
                    body = _obj(self._body())
                    from .project import ensure_handler

                    return 200, ensure_handler(root, str(body.get("handler") or ""), ["invoke"])
                if len(rest) == 2 and rest[1] in ("replicas", "replicas-remove") and method == "POST":
                    from ..core import onprem_replication as rep

                    key, action = rest
                    body = _obj(self._body())
                    if not rep.is_replicated(svc._entry(root, key)):
                        raise StudioError(400, f"{key!r} runs on a single server; it has no replicas")

                    def run_replica(job: Any) -> int:
                        if action == "replicas":
                            rep.add_replica(root, key, str(body.get("server") or ""), job.emit)
                        else:
                            rep.remove_replica(root, key, str(body.get("name") or ""), job.emit,
                                               delete_data=bool(body.get("delete_data")))
                        return 0

                    what = f"Add a replica to {key}" if action == "replicas" else f"Remove replica {body.get('name')} of {key}"
                    return 202, {"job_id": app.jobs.run_callable("onprem-service", run_replica, label=what).id}
                if len(rest) == 2 and rest[1] in ("backup", "remove") and method == "POST":
                    key, action = rest
                    body = _obj(self._body())
                    svc.public_entry(svc._entry(root, key))  # 400 for an unknown key before starting a job

                    folder = str(body.get("folder") or "").strip()
                    if action == "backup" and folder and not Path(folder).expanduser().is_dir():
                        raise StudioError(400, f"no folder {folder}")

                    def run(job: Any) -> int:
                        if action == "backup":
                            entry = svc._entry(root, key)
                            spec = svc.SERVICES.get(str(entry.get("service"))) or {}
                            dest = None
                            if folder:
                                stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
                                dest = Path(folder).expanduser() / f"{key}-{stamp}.{spec.get('backup_ext') or 'dump'}"
                            svc.backup(root, key, job.emit, dest=dest)
                        else:
                            svc.remove(root, key, job.emit, delete_data=bool(body.get("delete_data")))
                        return 0

                    job = app.jobs.run_callable("onprem-service", run, label=f"{action.capitalize()} {key}")
                    return 202, {"job_id": job.id}
            except svc.ServiceError as exc:
                raise StudioError(400, str(exc)) from None
            raise StudioError(404 if method == "GET" else 405, "unknown on-prem service endpoint")

        def _settings_bundle(self, rest: List[str], body: Dict[str, Any]) -> Tuple[int, Any]:
            """Export / preview / import the project's ``.pskit`` settings and secrets as one encrypted file."""
            from ..core import settings_bundle as bundle

            root = app.root
            passphrase = str(body.get("passphrase") or "")
            try:
                if rest == ["export"]:
                    raw = app.raw_config()
                    text, summary = bundle.export_settings(root, passphrase, env_files=bundle.env_files_of(raw),
                                                           pskit_version=__version__,
                                                           config=bool(body.get("include_config")))
                    name = f"{raw.get('service') or 'pskit'}{bundle.SUFFIX}"
                    return 200, {"filename": name, "content": text, "summary": summary}
                if rest in (["preview"], ["import"]):
                    payload = bundle.decrypt(str(body.get("content") or ""), passphrase)
                    replace = bool(body.get("replace"))
                    if rest == ["preview"]:
                        return 200, bundle.preview(root, payload, replace=replace)
                    return 200, bundle.import_settings(root, payload, replace=replace)
            except bundle.SettingsError as exc:
                raise StudioError(400, str(exc)) from None
            raise StudioError(404, "unknown settings endpoint")

        def _onprem_clusters(self, method: str, rest: List[str], params: Dict[str, List[str]]) -> Tuple[int, Any]:
            """Scaling clusters (Swarm / Kubernetes / Nomad): create, join / remove servers, monitor, scale, alerts."""
            from ..core import onprem_cluster as clu
            from ..core.onprem_servers import list_servers
            from ..core.onprem_services import ServiceError

            root = app.root
            watcher = app.cluster_watch()
            try:
                if not rest and method == "GET":
                    return 200, {
                        "clusters": clu.list_clusters(root),
                        "servers": list_servers(root),
                        "orchestrators": [{"id": k, **v} for k, v in clu.ORCHESTRATORS.items()],
                        "last": watcher.last,
                    }
                if not rest and method == "POST":
                    body = _obj(self._body())
                    name, orch, master = (str(body.get(k) or "") for k in ("name", "orchestrator", "master"))
                    if not name or not master or orch not in clu.ORCHESTRATORS:
                        raise StudioError(400, "name, orchestrator (swarm, kubernetes, nomad) and master are required")
                    if name in clu.load_clusters(root):
                        raise StudioError(400, f"cluster {name!r} already exists")

                    def create(job: Any) -> int:
                        serves = body.get("master_serves")
                        clu.create_cluster(root, name, orch, master, job.emit, advertise=str(body.get("advertise") or ""),
                                           nomad_version=str(body.get("nomad_version") or ""),
                                           serve_on_master=serves if isinstance(serves, bool) else None)
                        return 0

                    label = f"Create cluster {name} ({clu.ORCHESTRATORS[orch]['label']})"
                    return 202, {"job_id": app.jobs.run_callable("onprem-cluster", create, label=label).id}
                if len(rest) == 1 and method == "GET":
                    return 200, clu.public(rest[0], clu.get_cluster(root, rest[0]), root)
                if len(rest) == 2 and rest[1] == "status" and method == "GET":
                    current = clu.status(root, rest[0])
                    watcher.last[rest[0]] = current
                    return 200, current
                if len(rest) == 2 and rest[1] == "requests" and method == "GET":
                    from ..core.onprem_control import HostUnavailable

                    try:
                        return 200, clu.requests_feed(root, rest[0], _param(params, "stack") or "",
                                                      _int(params, "since", 0), _int(params, "limit", 200))
                    except (HostUnavailable, KeyError, PermissionError) as exc:
                        raise StudioError(502, str(exc.args[0] if exc.args else exc)) from None
                if len(rest) == 2 and rest[1] == "settings" and method == "PUT":
                    return 200, clu.save_settings(root, rest[0], _obj(self._body()))
                if len(rest) == 2 and rest[1] == "check" and method == "POST":
                    current = clu.check(root, rest[0])
                    watcher.last[rest[0]] = current
                    return 200, current
                if len(rest) == 2 and rest[1] == "test-alert" and method == "POST":
                    current = watcher.last.get(rest[0]) or {"orchestrator": clu.get_cluster(root, rest[0])["orchestrator"]}
                    return 200, clu.send_alert(root, rest[0], current, test=True)
                if len(rest) == 2 and rest[1] == "balancer-logs" and method == "GET":
                    return 200, {"text": clu.balancer_logs(root, rest[0], _int(params, "lines", 100))}
                actions = ("join", "leave", "scale", "remove", "balancer-set", "balancer-remove", "balancer-sync",
                           "master-serves")
                if len(rest) == 2 and rest[1] in actions and method == "POST":
                    name, action = rest
                    body = _obj(self._body())
                    clu.get_cluster(root, name)  # 400 for an unknown cluster before starting a job
                    server = str(body.get("server") or "")
                    if action in ("join", "leave", "balancer-set") and not server:
                        raise StudioError(400, "server is required")

                    def run(job: Any) -> int:
                        if action == "join":
                            clu.join_server(root, name, server, job.emit, advertise=str(body.get("advertise") or ""))
                        elif action == "leave":
                            clu.leave_server(root, name, server, job.emit)
                        elif action == "scale":
                            clu.scale(root, name, str(body.get("stack") or ""), int(body.get("replicas") or 0), job.emit)
                        elif action == "balancer-set":
                            weights = body.get("weights")
                            clu.set_balancer(root, name, server, job.emit, port=int(body.get("port") or 80),
                                             address=str(body.get("address") or ""),
                                             algorithm=str(body.get("algorithm") or "") or None,
                                             weights=weights if isinstance(weights, dict) else None)
                        elif action == "balancer-remove":
                            clu.remove_balancer(root, name, job.emit)
                        elif action == "balancer-sync":
                            clu.sync_balancer(root, name, job.emit, strict=True)
                        elif action == "master-serves":
                            clu.set_master_serves(root, name, bool(body.get("enabled")), job.emit)
                        else:
                            clu.remove_cluster(root, name, job.emit, uninstall=bool(body.get("uninstall")),
                                               delete_data=bool(body.get("delete_data")))
                        return 0

                    label = {"join": f"Join {server} to", "leave": f"Remove {server} from", "scale": "Scale",
                             "remove": "Uninstall and remove" if body.get("uninstall") else "Forget",
                             "balancer-set": f"Load balancer {server} for",
                             "balancer-remove": "Remove the load balancer of",
                             "balancer-sync": "Update the load balancer of",
                             "master-serves": "Requests to the master of"}[action] + f" cluster {name}"
                    return 202, {"job_id": app.jobs.run_callable("onprem-cluster", run, label=label).id}
            except (clu.ClusterError, ServiceError, ValueError) as exc:
                raise StudioError(400, str(exc)) from None
            raise StudioError(404 if method == "GET" else 405, "unknown cluster endpoint")

        def _onprem_balancers(self, method: str, rest: List[str], params: Dict[str, List[str]]) -> Tuple[int, Any]:
            """Named load balancers shared by projects and clusters (``core/onprem_balancers.py``)."""
            from ..core import onprem_balancers as bal
            from ..core import onprem_cluster as clu
            from ..core import onprem_lb
            from ..core.onprem_servers import list_servers
            from ..core.onprem_services import ServiceError

            root = app.root
            try:
                if not rest and method == "GET":
                    return 200, {
                        "balancers": bal.list_balancers(root),
                        "algorithms": onprem_lb.catalog(),
                        "default_algorithm": onprem_lb.DEFAULT_ALGORITHM,
                        "servers": list_servers(root),
                        "clusters": [{"name": c["name"], "nodes": [n["server"] for n in c["nodes"]],
                                      "balancer": (c.get("balancer") or {}).get("server")}
                                     for c in clu.list_clusters(root)],
                    }
                if not rest and method == "POST":
                    body = _obj(self._body())
                    name, server = str(body.get("name") or ""), str(body.get("server") or "")
                    if not name or not server:
                        raise StudioError(400, "name and server are required")
                    if name in bal.load_balancers(root):
                        raise StudioError(400, f"load balancer {name!r} already exists")
                    port = body.get("port")
                    weights = body.get("weights")
                    attach = [str(c) for c in body.get("clusters") or [] if c]

                    def create(job: Any) -> int:
                        bal.create_balancer(root, name, server, job.emit, port=int(port) if port else None,
                                            algorithm=str(body.get("algorithm") or "") or None,
                                            address=str(body.get("address") or ""),
                                            weights=weights if isinstance(weights, dict) else None)
                        for cluster in attach:
                            bal.attach_cluster(root, name, cluster, job.emit)
                        return 0

                    label = f"Create load balancer {name} on {server}"
                    return 202, {"job_id": app.jobs.run_callable("onprem-balancer", create, label=label).id}
                if len(rest) == 1 and method == "GET":
                    return 200, bal.public(rest[0], bal.get_balancer(root, rest[0]))
                if len(rest) == 2 and rest[1] == "status" and method == "GET":
                    return 200, bal.status(root, rest[0])
                if len(rest) == 2 and rest[1] == "logs" and method == "GET":
                    return 200, {"text": bal.logs(root, rest[0], _int(params, "lines", 100))}
                if len(rest) == 2 and rest[1] == "forget" and method == "POST":
                    bal.forget_balancer(root, rest[0])
                    return 200, {"forgotten": rest[0]}
                actions = ("update", "attach", "detach", "sync", "remove", "route-remove")
                if len(rest) == 2 and rest[1] in actions and method == "POST":
                    name, action = rest
                    body = _obj(self._body())
                    bal.get_balancer(root, name)  # 400 for an unknown load balancer before starting a job
                    cluster = str(body.get("cluster") or "")
                    if action in ("attach", "detach") and not cluster:
                        raise StudioError(400, "cluster is required")
                    if action == "route-remove" and not body.get("path"):
                        raise StudioError(400, "path is required")
                    weights = body.get("weights")

                    def run(job: Any) -> int:
                        if action == "update":
                            bal.update_balancer(root, name, job.emit,
                                                port=int(body["port"]) if body.get("port") else None,
                                                algorithm=str(body.get("algorithm") or "") or None,
                                                address=str(body.get("address") or "") or None,
                                                weights=weights if isinstance(weights, dict) else None)
                        elif action == "attach":
                            bal.attach_cluster(root, name, cluster, job.emit)
                        elif action == "detach":
                            bal.detach_cluster(root, name, cluster, job.emit)
                        elif action == "sync":
                            bal.sync_balancer(root, name, job.emit)
                        elif action == "route-remove":
                            bal.remove_route(root, name, str(body["path"]), job.emit)
                        else:
                            bal.remove_balancer(root, name, job.emit, force=bool(body.get("force")))
                        return 0

                    label = {"update": "Update", "attach": f"Attach cluster {cluster} to", "detach":
                             f"Detach cluster {cluster} from", "sync": "Rewrite", "remove": "Remove",
                             "route-remove": f"Remove /{body.get('path')} from"}[action] + f" load balancer {name}"
                    return 202, {"job_id": app.jobs.run_callable("onprem-balancer", run, label=label).id}
            except (bal.BalancerError, clu.ClusterError, ServiceError, ValueError) as exc:
                raise StudioError(400, str(exc)) from None
            raise StudioError(404 if method == "GET" else 405, "unknown load balancer endpoint")

        def _onprem_machines(self, method: str, parts: List[str], params: Dict[str, List[str]]) -> Tuple[int, Any]:
            """Saved SSH servers (add / test / shell / remove) and browser terminals (ttyd in Docker)."""
            from ..core import onprem_console as con
            from ..core import onprem_servers as srv
            from ..core import onprem_terminal as term
            from ..core.onprem_services import ServiceError

            root = app.root
            try:
                if parts == ["onprem-servers"] and method == "GET":
                    out: Dict[str, Any] = {"servers": srv.list_servers(root)}
                    stage = _param(params, "stage")
                    if stage:
                        out["deployed"] = _deployed_on(root, stage)
                    return 200, out
                if parts == ["onprem-servers", "reachability"] and method == "GET":
                    return 200, {"servers": srv.reachability(root)}
                if len(parts) == 3 and parts[0] == "onprem-servers" and parts[2] == "metrics" and method == "GET":
                    return 200, srv.server_metrics(root, parts[1])
                if parts == ["onprem-servers"] and method == "POST":
                    body = _obj(self._body())
                    name = str(body.get("name") or "")
                    target = _obj(body.get("target"))
                    item = srv.save_server(root, name, target, description=str(body.get("description") or ""))
                    return 200, {"name": name, "server": {k: v for k, v in item.items() if k != "password"}}
                if len(parts) == 3 and parts[0] == "onprem-servers" and method == "POST":
                    name, action = parts[1], parts[2]
                    if action == "test":
                        return 200, srv.test_server(root, name)
                    if action == "remove":
                        warnings = srv.remove_server(root, name, app.raw_config())
                        return 200, {"removed": name, "warnings": warnings}
                    if action == "shell":
                        body = _obj(self._body())
                        return 200, con.run_server(srv.server_target(root, name), str(body.get("line") or ""))
                if parts == ["onprem-terminals"] and method == "GET":
                    running = term.list_terminals()
                    for item in running:
                        item["url"] = app.terminal_urls.get(item["name"], "")
                    return 200, {"terminals": running}
                if parts == ["onprem-terminals"] and method == "POST":
                    body = _obj(self._body())
                    lines: List[str] = []
                    result = term.start_terminal(root, lines.append, server=str(body.get("server") or "") or None,
                                                 key=str(body.get("key") or "") or None, shell=bool(body.get("shell")))
                    app.terminal_urls[result["name"]] = result["url"]
                    return 200, {**result, "log": lines}
                if len(parts) == 3 and parts[0] == "onprem-terminals" and parts[2] == "stop" and method == "POST":
                    term.stop_terminal(parts[1])
                    app.terminal_urls.pop(parts[1], None)
                    return 200, {"stopped": parts[1]}
            except (srv.ServerError, term.TerminalError, con.ConsoleError, ServiceError) as exc:
                raise StudioError(400, str(exc)) from None
            raise StudioError(404 if method == "GET" else 405, "unknown endpoint")

    return Handler


class StudioHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    allowed_hosts: Optional[set] = None
    studio: Optional[Studio] = None


def make_server(
    root: Path,
    host: str = "127.0.0.1",
    port: int = 8770,
    token: Optional[str] = None,
    vscode_image: Optional[str] = None,
) -> StudioHTTPServer:
    app = Studio(root, token=token, vscode_image=vscode_image)
    httpd = StudioHTTPServer((host, port), make_handler(app))
    httpd.allowed_hosts = _allowed_hosts(host, httpd.server_address[1])
    httpd.studio = app
    return httpd


def studio_url(httpd: StudioHTTPServer) -> str:
    host, port = httpd.server_address[0], httpd.server_address[1]
    shown = "127.0.0.1" if host in ("0.0.0.0", "::") else str(host)  # noqa: S104
    token = httpd.studio.token if httpd.studio else ""
    return f"http://{shown}:{port}/#token={token}"


__all__ = ["Studio", "StudioHTTPServer", "is_loopback", "make_server", "studio_url"]
