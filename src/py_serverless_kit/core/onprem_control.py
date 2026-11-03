"""Talk to a deployed on-premises host's control API (``/__pskit/...``).

Used by ``pskit logs``, ``pskit workflow ...`` and the live dashboard. The admin
token is read from the generated ``pskit_host.json`` and only ever sent to the
host itself.
"""

from __future__ import annotations

import base64
import json
import socket
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import Request, urlopen

from .onprem_servers import DEPLOYED_FILE, LOCAL, deployed_server
from .project import WORK_DIR

__all__ = [
    "DEPLOYED_FILE", "LOCAL", "FunctionFailed", "HostControl", "HostUnavailable", "control_for", "control_url", "deployed_host",
    "deployed_on", "deployed_server", "host_spec", "record_key", "remember_deploy", "rendered_spec",
]
_ROUTE_TTL = 120.0  # seconds a direct / SSH route decision is reused
_ROUTES: Dict[str, Tuple[str, float]] = {}

# Runs on the server over SSH: one HTTP request to the host on its loopback. The request (with the admin token)
# arrives on stdin, so nothing secret is on a command line.
_SSH_FETCH = (
    "import sys,json,base64,urllib.request,urllib.error\n"
    "r=json.loads(sys.stdin.readline())\n"
    "b=base64.b64decode(r['b']) if r.get('b') is not None else None\n"
    "q=urllib.request.Request(r['u'],data=b,method=r['m'],headers=r['h'])\n"
    "try:\n"
    " p=urllib.request.urlopen(q,timeout=r['t']);s=p.status;h=dict(p.headers);d=p.read()\n"
    "except urllib.error.HTTPError as e:\n"
    " s=e.code;h=dict(e.headers or {});d=e.read()\n"
    "except Exception as e:\n"
    " sys.stderr.write('pskit: no pskit host answers on port %s of this server (%s)\\n'"
    " % (r['u'].split(':')[2].split('/')[0],getattr(e,'reason',None) or e));sys.exit(3)\n"
    "sys.stdout.write(json.dumps({'s':s,'h':h,'b':base64.b64encode(d).decode()}))\n"
)


class HostUnavailable(OSError):
    """The host did not answer (not running, wrong address, firewall...)."""


class FunctionFailed(HostUnavailable):
    """The host answered, but the function raised: ``error_type`` and ``cause`` are its exception's. (A
    HostUnavailable so callers that report host errors report this too.)"""

    def __init__(self, error_type: str, cause: str) -> None:
        self.error_type = error_type
        self.cause = cause
        super().__init__(f"the function raised {error_type}: {cause}")


class HostControl:
    """Client for a host's ``/__pskit`` API.

    ``ssh`` (the deploy's SSH login) keeps a host on another machine reachable when its port is not: it binds
    127.0.0.1 there (the default) or a firewall blocks the port. The request then runs on the server over SSH.
    """

    def __init__(
        self,
        base_url: str,
        token: str = "",
        timeout: float = 10.0,
        *,
        ssh: Optional[Dict[str, Any]] = None,
        remote_port: Optional[int] = None,
        remote_path: str = "",
        server: Optional[str] = None,
        force_ssh: bool = False,
    ) -> None:
        if not base_url.lower().startswith(("http://", "https://")):
            raise ValueError(f"on-prem control URL must be http(s), got {base_url!r}")
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self.ssh = ssh if ssh and ssh.get("host") else None
        self.remote_port = int(remote_port or urlsplit(self.base_url).port or 8080)
        self.remote_path = remote_path
        self.server = server
        self.force_ssh = force_ssh

    @property
    def where(self) -> str:
        """The saved server and URL, for messages."""
        return f"{self.base_url} (server {self.server})" if self.server else self.base_url

    # ------------------------------------------------------------------ transport
    def fetch(
        self,
        method: str,
        path: str,
        data: Optional[bytes] = None,
        headers: Optional[Dict[str, str]] = None,
        query: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
    ) -> Tuple[int, Dict[str, str], bytes]:
        """One request: ``(status, headers, body)`` for any HTTP status, HostUnavailable when nothing answers."""
        params = {k: v for k, v in (query or {}).items() if v is not None and v != ""}
        suffix = path + ("?" + urlencode(params) if params else "")
        sent = dict(headers or {})
        if self.token:
            sent["x-pskit-token"] = self.token
        wait = timeout or self.timeout
        if self.ssh is not None and (self.force_ssh or self._route() == "ssh"):
            why = "" if self.force_ssh else "port not reachable from here"
            return self._fetch_ssh(method, suffix, data, sent, wait, direct_error=why)
        req = Request(self.base_url + suffix, data=data, method=method)  # noqa: S310 - http(s) checked in __init__
        for key, value in sent.items():
            req.add_header(key, value)
        try:
            with urlopen(req, timeout=wait) as resp:  # noqa: S310
                return resp.status, dict(resp.headers), resp.read()
        except HTTPError as exc:
            return exc.code, dict(exc.headers or {}), exc.read()
        except (URLError, OSError, ValueError) as exc:
            reason = getattr(exc, "reason", exc)
            if self.ssh is not None:
                _ROUTES[self.base_url] = ("ssh", time.monotonic() + _ROUTE_TTL)
                return self._fetch_ssh(method, suffix, data, sent, wait, direct_error=str(reason))
            raise HostUnavailable(f"on-prem host at {self.where} is not reachable: {reason}") from None

    def _route(self) -> str:
        """``direct`` when this machine can open the host's port, else ``ssh``; remembered for a while."""
        cached = _ROUTES.get(self.base_url)
        if cached and cached[1] > time.monotonic():
            return cached[0]
        parts = urlsplit(self.base_url)
        try:
            with socket.create_connection((parts.hostname or "", parts.port or 80), timeout=3):
                route = "direct"
        except OSError:
            route = "ssh"
        _ROUTES[self.base_url] = (route, time.monotonic() + _ROUTE_TTL)
        return route

    def _fetch_ssh(
        self, method: str, suffix: str, data: Optional[bytes], headers: Dict[str, str], timeout: float,
        direct_error: str = "",
    ) -> Tuple[int, Dict[str, str], bytes]:
        from ..providers.onprem_remote import _shq, _ssh_base, _target

        assert self.ssh is not None
        candidates = ([self.remote_path.rstrip("/") + "/python/bin/python3"] if self.remote_path else []) + [
            "python3", "python"]
        command = (
            'export PATH="/usr/local/bin:/usr/bin:/bin:$PATH"; '
            f"for p in {' '.join(_shq(c) for c in candidates)}; do "
            f'if command -v "$p" >/dev/null 2>&1; then exec "$p" -c {_shq(_SSH_FETCH)}; fi; done; '
            "echo 'pskit: no python3 on the server' >&2; exit 127"
        )
        request = {
            "m": method,
            "u": f"http://127.0.0.1:{self.remote_port}{suffix}",
            "h": headers,
            "b": None if data is None else base64.b64encode(data).decode("ascii"),
            "t": timeout,
        }
        argv = _ssh_base(self.ssh) + [_target(self.ssh), command]
        why = f" directly ({direct_error})" if direct_error else ""
        try:
            proc = subprocess.run(  # noqa: S603 - explicit argv, no local shell
                argv, input=(json.dumps(request) + "\n").encode("utf-8"), capture_output=True, timeout=timeout + 40
            )
        except FileNotFoundError:
            raise HostUnavailable(
                f"on-prem host at {self.where} is not reachable{why}, and `{argv[0]}` is not installed here "
                "to reach it over SSH"
            ) from None
        except subprocess.TimeoutExpired:
            raise HostUnavailable(f"on-prem host at {self.where}: no answer over SSH in {int(timeout + 40)}s") from None
        err = proc.stderr.decode("utf-8", "replace").strip()
        if proc.returncode:
            detail = err.splitlines()[-1] if err else f"ssh exited with {proc.returncode}"
            redeploy = "pskit deploy" + (f" --server {self.server}" if self.server else "")
            raise HostUnavailable(
                f"on-prem host at {self.where} is not reachable{why}, nor over SSH to {self.ssh.get('host')}: "
                f"{detail}. If the host is not running there, redeploy it: {redeploy}"
            )
        try:
            out = json.loads(proc.stdout.decode("utf-8"))
            return int(out["s"]), dict(out.get("h") or {}), base64.b64decode(out.get("b") or "")
        except (ValueError, KeyError, TypeError):
            raise HostUnavailable(f"on-prem host at {self.where}: unexpected answer over SSH: {err[-300:]}") from None

    def request(
        self,
        method: str,
        path: str,
        body: Any = None,
        query: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
        *,
        data: Optional[bytes] = None,
    ) -> Any:
        """A JSON call: ``body`` as JSON or ``data`` as raw bytes. 404 -> KeyError, 400/405/413 -> ValueError."""
        headers = {"accept": "application/json"}
        if body is not None:
            data = json.dumps(body, default=str).encode("utf-8")
            headers["content-type"] = "application/json"
        status, _headers, raw = self.fetch(method, path, data, headers, query, timeout)
        if status >= 400:
            message = _error_body(raw, status)
            if status == 404:
                raise KeyError(message)
            if status in (400, 405, 413):
                raise ValueError(message)
            if status == 401:
                raise PermissionError(f"{message} (check provider.options.admin_token)")
            failed = _function_error(raw)
            if failed is not None:
                raise failed
            raise HostUnavailable(f"{self.base_url} answered HTTP {status}: {message}")
        if not raw:
            return None
        try:
            return json.loads(raw.decode("utf-8"))
        except ValueError:
            raise HostUnavailable(f"{self.base_url} returned a non-JSON response") from None

    # ------------------------------------------------------------------ helpers
    def health(self) -> Dict[str, Any]:
        return dict(self.request("GET", "/__pskit/health", timeout=3) or {})

    def stats(self) -> Dict[str, Any]:
        return dict(self.request("GET", "/__pskit/stats") or {})

    def logs(
        self,
        since: int = 0,
        limit: int = 200,
        level: Optional[str] = None,
        function: Optional[str] = None,
        q: Optional[str] = None,
        source: Optional[str] = None,
        before: Optional[int] = None,
        local: bool = False,
    ) -> Dict[str, Any]:
        query = {
            "since": since,
            "limit": limit,
            "level": level,
            "function": function,
            "q": q,
            "source": source,
            "before": before,
        }
        path = "/__pskit/logs/local" if local else "/__pskit/logs"
        return dict(self.request("GET", path, query=query) or {})

    def log_streams(self) -> Dict[str, Any]:
        return dict(self.request("GET", "/__pskit/logs/streams") or {})

    def clear_logs(self, function: Optional[str] = None) -> Dict[str, Any]:
        return dict(self.request("DELETE", "/__pskit/logs", query={"function": function}) or {})

    def start_workflow(self, workflow: str, data: Any, wait: bool = False) -> Dict[str, Any]:
        path = "/__pskit/workflows/" + quote(workflow, safe="")
        return dict(
            self.request(
                "POST", path, body=data, query={"wait": "true" if wait else None}, timeout=None if wait else 15
            )
            or {}
        )

    def executions(
        self, workflow: Optional[str] = None, status: Optional[str] = None, limit: int = 20, offset: int = 0
    ) -> Dict[str, Any]:
        query = {"workflow": workflow, "status": status, "limit": limit, "offset": offset}
        return dict(self.request("GET", "/__pskit/executions", query=query) or {})

    def execution(self, execution_id: str) -> Dict[str, Any]:
        return dict(self.request("GET", "/__pskit/executions/" + quote(execution_id, safe="")) or {})

    def cancel(self, execution_id: str) -> Dict[str, Any]:
        return dict(self.request("POST", "/__pskit/executions/" + quote(execution_id, safe="") + "/cancel") or {})


def _function_error(raw: bytes) -> Optional[FunctionFailed]:
    """The host's answer when the function itself raised: ``{"errorType": ..., "cause": ...}``."""
    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception:  # noqa: BLE001
        return None
    if isinstance(payload, dict) and payload.get("errorType"):
        return FunctionFailed(str(payload["errorType"]), str(payload.get("cause") or ""))
    return None


def _error_body(raw: bytes, status: int) -> str:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception:  # noqa: BLE001
        return f"HTTP {status}"
    if isinstance(payload, dict):
        return str(payload.get("error") or payload.get("cause") or payload)
    return str(payload)


def record_key(record: Dict[str, Any]) -> str:
    return str(record.get("key") or f"{record.get('provider')}-{record.get('stage')}")


def host_spec(record: Dict[str, Any], root: Path) -> Optional[Dict[str, Any]]:
    """The spec the host was last *deployed* with, else the one last rendered (package / plan rewrite that)."""
    deployed = deployed_host(root, str(record.get("stage") or ""), record)
    if deployed is not None:
        return dict(deployed.get("spec") or {})
    return rendered_spec(Path(root) / WORK_DIR / record_key(record))


def rendered_spec(work_dir: Path) -> Optional[Dict[str, Any]]:
    try:
        spec = json.loads((Path(work_dir) / "onprem_app" / "pskit_host.json").read_text("utf-8"))
    except (OSError, ValueError):
        return None
    return spec if isinstance(spec, dict) else None


# ---------------------------------------------------------------------- where a stage was deployed
_SPEC_KEYS = ("host", "port", "endpoint", "admin_token", "deploy", "unit_name", "service", "stage")


def deployed_host(
    root: Path, stage: str, record: Optional[Dict[str, Any]] = None
) -> Optional[Dict[str, Any]]:
    """``{server, spec, deployed_at}`` written by the last successful ``pskit deploy`` of ``onprem-<stage>``."""
    key = record_key(record) if record else f"onprem-{stage}"
    try:
        data = json.loads((Path(root) / WORK_DIR / key / DEPLOYED_FILE).read_text("utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and isinstance(data.get("spec"), dict) else None


def remember_deploy(work_dir: Path, server: Optional[str], cluster: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """After a successful deploy: keep where the host runs, so trigger / logs / test and the next deploy use it.
    On a scaling cluster ``server`` is its master and ``cluster`` its name."""
    spec = rendered_spec(work_dir)
    if spec is None:
        return None
    data = {
        "server": server or None,
        "cluster": cluster or None,
        "deployed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "spec": {k: spec[k] for k in _SPEC_KEYS if k in spec},
    }
    path = Path(work_dir) / DEPLOYED_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(data, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    return data


def deployed_on(spec: Dict[str, Any], server: Optional[str], cluster: Optional[str] = None) -> Dict[str, Any]:
    """The ``deployed_on`` summary kept in ``deployment.json`` (shown by deploy, info and the studio)."""
    deploy = spec.get("deploy") or {}
    method = str(deploy.get("method") or "local")
    ssh_host = str((deploy.get("ssh") or {}).get("host") or "")
    where = "this machine" if method == "local" or not ssh_host else ssh_host
    label = f"{server} ({where})" if server else where
    if cluster:
        label = f"cluster {cluster} (master {label})"
    return {"server": server or None, "cluster": cluster or None, "method": method, "host": ssh_host or None,
            "label": label, "endpoint": spec.get("endpoint")}


def control_url(spec: Dict[str, Any], record: Optional[Dict[str, Any]] = None) -> str:
    """Loopback for a host on this machine, otherwise the advertised endpoint."""
    from ..runtime.onprem_host import health_url

    method = str((spec.get("deploy") or {}).get("method") or "local")
    if method == "local":
        return health_url(spec)[: -len("/__pskit/health")]
    endpoint = spec.get("endpoint") or (record or {}).get("endpoint")
    if not endpoint:
        return health_url(spec)[: -len("/__pskit/health")]
    return str(endpoint).rstrip("/")


def _spec_ssh(spec: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], str]:
    """The SSH login and remote folder of a host deployed over SSH (also docker on an SSH host)."""
    deploy = spec.get("deploy") or {}
    ssh = deploy.get("ssh") or {}
    if str(deploy.get("method") or "local") == "local" or not ssh.get("host") or not ssh.get("user"):
        return None, ""
    return dict(ssh), str(ssh.get("path") or "")


def control_for_group(record: Dict[str, Any], root: Path, group: str) -> Optional[HostControl]:
    """A client for the host of placement group ``group`` (``provider.options.placement``): each server answers
    only the routes of its own functions. None when the group is the default one (use ``control_for``) or its
    spec is not here."""
    from .onprem_placement import app_dir

    main = host_spec(record, root) or {}
    default = str(main.get("default_group") or "")
    if not group or not default or group == default:
        return None
    try:
        spec = json.loads((Path(root) / WORK_DIR / record_key(record) / app_dir(group, default) / "pskit_host.json")
                          .read_text("utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(spec, dict) or not spec.get("endpoint"):
        return None
    ssh, remote_path = _spec_ssh(spec)
    port = int(spec.get("port") or 8080)
    return HostControl(str(spec["endpoint"]), token=str(spec.get("admin_token") or ""), ssh=ssh, remote_port=port,
                       remote_path=remote_path)


def control_for(record: Dict[str, Any], root: Path, server: Optional[str] = None) -> Optional[HostControl]:
    """A client for the deployment's host, or None when it is not an on-prem deployment.

    Without ``server`` this is the host of the last successful deploy (its saved server, SSH host or this
    machine), even after ``package`` / ``plan`` re-rendered the spec for another target. ``server`` (or
    ``PSKIT_DEPLOY_SERVER``, set by ``--server``) picks the host on that saved SSH server instead: the same
    project deployed to several machines. ``local`` picks this machine. A host whose port cannot be reached
    from here is called over SSH.
    """
    import os

    if record.get("provider") != "onprem":
        return None
    from .onprem_servers import SERVER_ENV, get_server

    spec = host_spec(record, root)
    deployed = deployed_host(root, str(record.get("stage") or ""), record)
    token = str((spec or {}).get("admin_token") or "")
    port = int((spec or {}).get("port") or 8080)
    name = server or os.environ.get(SERVER_ENV) or None
    if name == LOCAL:
        from ..runtime.onprem_host import health_url

        return HostControl(health_url({**(spec or {}), "host": "127.0.0.1"})[: -len("/__pskit/health")], token=token)
    if name and name != (deployed or {}).get("server"):
        from .onprem_servers import server_target
        from .onprem_services import ssh_options

        item = get_server(root, name)  # ServerError (a ValueError) for an unknown name
        _ssh, remote_path = _spec_ssh(spec or {})
        return HostControl(f"http://{item['host']}:{port}", token=token, ssh=ssh_options(server_target(root, name)),
                           remote_port=port, remote_path=remote_path, server=name)
    if spec is None:
        endpoint = record.get("endpoint")
        if not endpoint:
            return None
        return HostControl(str(endpoint))
    ssh, remote_path = _spec_ssh(spec)
    return HostControl(control_url(spec, record), token=token, ssh=ssh, remote_port=port, remote_path=remote_path,
                       server=(deployed or {}).get("server") or None)
