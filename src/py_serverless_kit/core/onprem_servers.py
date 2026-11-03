"""Saved SSH servers: name a machine once, then create services, install software, open consoles and deploy to it.

Stored in ``.pskit/onprem-servers.json`` (out of git, like the rest of ``.pskit``). Only connection details are
kept: a password typed in the studio goes to ``.pskit/ssh/<user>@<host>-<port>.pass`` (owner-only), never into the
JSON, ``pskit.yml`` or Terraform state.

``provider.options.deploy: {server: NAME}`` in ``pskit.yml`` (or ``pskit deploy --server NAME``) deploys the
functions to that machine: its host, user, port and login replace those in ``options.deploy``.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

SERVERS_FILE = Path(".pskit") / "onprem-servers.json"
SERVER_ENV = "PSKIT_DEPLOY_SERVER"
CLUSTER_ENV = "PSKIT_DEPLOY_CLUSTER"  # ``--cluster NAME``: deploy to that scaling cluster
LOCAL = "local"  # ``--server local``: this machine, whatever the last deploy used
DEPLOYED_FILE = "onprem_deployed.json"  # .pskit/onprem-<stage>/: where the last successful deploy went
_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,62}$")
_KEEP = ("host", "user", "port", "identity_file", "password_file", "auth", "sudo", "known_hosts")

RunFn = Callable[[List[str], Optional[Path]], Tuple[int, str]]

# One SSH round trip: what the machine is and whether pskit can use it.
_FACTS = (
    "echo os=$( (. /etc/os-release 2>/dev/null && echo \"$PRETTY_NAME\") || uname -s); "
    "echo arch=$(uname -m); echo cpus=$(nproc 2>/dev/null); "
    "echo memory_mb=$(awk '/MemTotal/ {print int($2/1024)}' /proc/meminfo 2>/dev/null); "
    "echo disk_free=$(df -h / 2>/dev/null | awk 'NR==2 {print $4}'); "
    "echo docker=$(docker --version 2>/dev/null | sed 's/,.*//'); "
    "echo docker_access=$(docker info >/dev/null 2>&1 && echo yes || (sudo -n docker info >/dev/null 2>&1 && echo sudo) || echo no); "
    "echo sudo=$(sudo -n true 2>/dev/null && echo yes || echo no); "
    "echo python=$(python3 --version 2>/dev/null); echo node=$(node -v 2>/dev/null); "
    "echo nginx=$(nginx -v 2>&1 | grep -o 'nginx/[0-9.]*')"
)


class ServerError(ValueError):
    pass


def _path(root: Path) -> Path:
    return root / SERVERS_FILE


def load_servers(root: Path) -> Dict[str, Dict[str, Any]]:
    try:
        data = json.loads(_path(root).read_text("utf-8"))
    except (OSError, ValueError):
        return {}
    servers = data.get("servers") if isinstance(data, dict) else None
    return {k: v for k, v in (servers or {}).items() if isinstance(v, dict)}


def _write(root: Path, servers: Dict[str, Dict[str, Any]]) -> None:
    path = _path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps({"servers": servers}, indent=2, sort_keys=True) + "\n").encode("utf-8"))


def list_servers(root: Path) -> List[Dict[str, Any]]:
    from .onprem_services import describe_target

    return [
        {"name": name, **{k: v for k, v in item.items() if k != "password"},
         "label": describe_target({**item, "method": "ssh"})}
        for name, item in sorted(load_servers(root).items())
    ]


def get_server(root: Path, name: str, *, origin: str = "") -> Dict[str, Any]:
    """A saved server. ``origin``: where the name came from (e.g. pskit.yml's ``provider.options.deploy.server``),
    named in the error so a server that was renamed or removed is easy to fix."""
    servers = load_servers(root)
    server = servers.get(str(name))
    if server is None:
        raise ServerError(missing_server_message(str(name), servers, origin))
    return dict(server)


def close_servers(name: str, servers: Dict[str, Any]) -> List[str]:
    """Saved names that look like ``name`` (``VM_01`` -> ``VM_01_2cpu``, ``VM_01_4cpu``), at most three."""
    import difflib

    known = sorted(servers)
    low = name.lower()
    close = [s for s in known if s.lower().startswith(low) or low.startswith(s.lower())]
    close += [s for s in difflib.get_close_matches(name, known, n=3, cutoff=0.6) if s not in close]
    return close[:3]


def missing_server_message(name: str, servers: Dict[str, Any], origin: str = "") -> str:
    """``no saved SSH server 'X' ...`` with close names and how to fix it."""
    close = close_servers(name, servers)
    where = f" ({origin} names it)" if origin else ""
    text = f"no saved SSH server {name!r}{where}; saved: {', '.join(sorted(servers)) or 'none yet'}."
    if close:
        text += f" Did you mean {' or '.join(close)}?"
    if origin:
        text += f" Change {origin} to a saved server (studio: Overview -> Deploy to), or save {name!r} again:"
        return text + " pskit resources onprem servers add"
    return text + " Add it: pskit resources onprem servers add"


def server_references(root: Path, name: str, raw: Optional[Dict[str, Any]] = None) -> Dict[str, List[str]]:
    """Where saved server ``name`` is still used: ``clusters`` it belongs to, and ``other`` places (pskit.yml,
    created resources) that would point at a server that no longer exists once it is removed."""
    from .onprem_cluster import load_clusters
    from .onprem_services import load_state

    clusters = sorted(c for c, item in load_clusters(root).items() if name in (item.get("nodes") or {}))
    other: List[str] = []
    options = ((raw or {}).get("provider") or {}).get("options") if isinstance(raw, dict) else None
    deploy = options.get("deploy") if isinstance(options, dict) else None
    if isinstance(deploy, dict) and str(deploy.get("server") or "") == name:
        other.append("pskit.yml provider.options.deploy.server")
    for key, entry in sorted(load_state(root).get("services", {}).items()):
        target = entry.get("target") if isinstance(entry, dict) else None
        if isinstance(target, dict) and target.get("server") == name:
            other.append(f"resource {key}")
    return {"clusters": clusters, "other": other}


def server_target(root: Path, name: str, *, origin: str = "") -> Dict[str, Any]:
    """The service target (``method: ssh``) of a saved server."""
    return {"method": "ssh", **get_server(root, name, origin=origin), "server": str(name)}


_SERVER_PATH = re.compile(r"^/[A-Za-z0-9._/-]*$")
_LOOPBACK_DEFAULT = "127.0.0.1"
SETTINGS = ("home", "bind", "data_dir")


def server_settings(raw: Dict[str, Any]) -> Dict[str, str]:
    """The optional per-server defaults, validated:

    * ``home``: where pskit keeps files on the server (functions in ``<home>/<service>-<stage>``, cluster scripts and
      image copies in ``<home>/pskit-cluster``). Default ``/opt/pskit`` and the SSH user's home.
    * ``bind``: the address the functions' host and services listen on (``0.0.0.0``, ``127.0.0.1`` or one of the
      server's IPs); a specific IP is also its address in a cluster.
    * ``data_dir``: where data lives (the functions' ``data_dir``, services' data as bind mounts instead of Docker
      volumes, a cluster master's main-replica data).
    """
    out: Dict[str, str] = {}
    for key in ("home", "data_dir"):
        value = str(raw.get(key) or "").strip().rstrip("/")
        if not value:
            continue
        if not _SERVER_PATH.match(value) or "/../" in value + "/" or len(value) > 200:
            raise ServerError(f"{key} must be an absolute Linux path such as /srv/pskit (letters, digits, . _ - /)")
        out[key] = value
    bind = str(raw.get("bind") or "").strip()
    if bind:
        import ipaddress

        try:
            ipaddress.IPv4Address(bind)
        except ValueError:
            raise ServerError("bind must be an IPv4 address: 0.0.0.0 (all), 127.0.0.1 or one of the server's IPs") from None
        out["bind"] = bind
    return out


def save_server(root: Path, name: str, raw: Dict[str, Any], *, description: str = "") -> Dict[str, Any]:
    """Add or replace server ``name`` (validated like a service target; a password is saved to a file)."""
    from .onprem_services import ServiceError, normalize_target

    if not _NAME.match(str(name)):
        raise ServerError("server name: start with a letter; letters, digits, _ . - (max 63)")
    if str(name).lower() == "local":
        raise ServerError("server name 'local' is reserved for this machine (--server local)")
    previous = load_servers(root).get(name) or {}
    body = {**raw, "method": "ssh"}
    body.pop("server", None)
    if body.get("auth") == "password" and not body.get("password") and not body.get("password_file"):
        body["password_file"] = previous.get("password_file") or ""    # editing: keep the saved password
    try:
        target = normalize_target(body, root)
    except ServiceError as exc:
        raise ServerError(str(exc)) from None
    item = {k: target[k] for k in _KEEP if target.get(k) not in (None, "")}
    item["sudo"] = bool(target.get("sudo"))
    item.update(server_settings(raw))
    if description:
        item["description"] = str(description)[:200]
    servers = load_servers(root)
    servers[name] = item
    _write(root, servers)
    return item


def remove_server(root: Path, name: str, raw: Optional[Dict[str, Any]] = None) -> List[str]:
    """Forget a saved server. Refused while it is in a cluster (the cluster would lose a node it cannot reach);
    returns warnings for the other places that still name it (``raw``: pskit.yml)."""
    servers = load_servers(root)
    if str(name) not in servers:
        raise ServerError(missing_server_message(str(name), servers))
    refs = server_references(root, str(name), raw)
    if refs["clusters"]:
        first = refs["clusters"][0]
        raise ServerError(f"{name!r} is in cluster {', '.join(refs['clusters'])}; take it out first: "
                          f"pskit cluster leave {first} {name} (or remove the cluster)")
    item = servers.pop(str(name))
    _write(root, servers)
    warnings = [f"{place} still names {name!r}: point it at another saved server" for place in refs["other"]]
    secret = str(item.get("password_file") or "")
    still_used = any(s.get("password_file") == secret for s in servers.values())
    if secret and not still_used and Path(secret).parent == root / ".pskit" / "ssh" and os.path.isfile(secret):
        os.remove(secret)
    return warnings


def test_server(root: Path, name: str, *, run: Optional[RunFn] = None) -> Dict[str, Any]:
    """Log in once and report the OS, CPU, memory, disk, Docker access, sudo and installed runtimes."""
    from .onprem_services import ServiceError, _default_run, _ssh_argv, check_ssh_login

    target = server_target(root, name)
    try:
        if run is None:
            check_ssh_login(target)
    except ServiceError as exc:
        return {"name": name, "ok": False, "error": str(exc)}
    code, text = (run or _default_run)(_ssh_argv(target, _FACTS), None)
    facts: Dict[str, str] = {}
    for line in text.splitlines():
        key, sep, value = line.partition("=")
        if sep and re.match(r"^[a-z_]+$", key):
            facts[key] = value.strip()
    if code or "os" not in facts:
        return {"name": name, "ok": False, "error": text.strip()[-600:] or f"ssh exited with {code}"}
    return {"name": name, "ok": True, "facts": facts}


def reachability(root: Path, *, timeout: float = 3.0) -> Dict[str, Dict[str, Any]]:
    """Every saved server's SSH port, probed in parallel (no login): ``{name: {ok, ms, error}}``. The studio's
    check marks; *Test* logs in and checks Docker, sudo and the runtimes."""
    import socket
    from concurrent.futures import ThreadPoolExecutor

    def probe(item: Tuple[str, Dict[str, Any]]) -> Tuple[str, Dict[str, Any]]:
        name, server = item
        host, port = str(server.get("host") or ""), int(server.get("port") or 22)
        started = time.monotonic()
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return name, {"ok": True, "ms": round((time.monotonic() - started) * 1000)}
        except OSError as exc:
            return name, {"ok": False, "error": f"{host}:{port}: {exc.strerror or exc}"}

    servers = load_servers(root)
    if not servers:
        return {}
    with ThreadPoolExecutor(max_workers=min(16, len(servers))) as pool:
        return dict(pool.map(probe, servers.items()))


def server_metrics(root: Path, name: str, *, run: Optional[RunFn] = None) -> Dict[str, Any]:
    """Live CPU (over one second), memory and disk use in percent, load and size of a saved server."""
    from .onprem_cluster import node_metrics

    out = node_metrics(server_target(root, name), run=run)
    out["at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return out


_LOGIN_KEYS = ("host", "user", "port", "ssh_port", "pem", "identity", "identity_file", "password_file", "auth",
               "known_hosts", "server")


def _use_cluster(options: Dict[str, Any], root: Path, name: Optional[str] = None) -> str:
    """Point ``options`` at a scaling cluster (``name`` replaces the one in pskit.yml, keeping its replicas / cpu /
    memory). Returns the master's server name."""
    from .onprem_cluster import ClusterError, deploy_spec

    if name:
        current = options.get("cluster")
        settings = dict(current) if isinstance(current, dict) else {}
        options["cluster"] = {**settings, "name": name}
    try:
        deploy_spec(root, options)
    except ClusterError as exc:
        raise ServerError(str(exc)) from None
    return str(options["deploy"]["server"])


def resolve_deploy(options: Dict[str, Any], root: Path, stage: str, server: Optional[str] = None,
                   cluster: Optional[str] = None) -> Optional[str]:
    """Pick where ``onprem-<stage>`` deploys to, in place on ``options.deploy``. Returns the server name.

    ``cluster`` (``--cluster`` / ``PSKIT_DEPLOY_CLUSTER``) or ``server`` (``--server`` / ``PSKIT_DEPLOY_SERVER``) wins;
    ``local`` means this machine. Next comes pskit.yml: ``options.cluster`` (a scaling cluster,
    ``core/onprem_cluster.py``), then ``options.deploy`` (``server``, ``host``, or a ``method`` other than local).
    Otherwise the stage goes back to where it was last deployed (a saved server or a cluster), so a deploy from
    the studio's machine picker sticks for later deploys, triggers, tests and logs.

    On a cluster the functions run on its servers, and the cluster's master becomes the SSH target used by logs
    and tests. An explicit ``server`` deploys to that one machine even when pskit.yml names a cluster.
    """
    if cluster and server:
        raise ServerError("pick one: --cluster NAME (several servers) or --server NAME (one server)")
    if cluster:
        return _use_cluster(options, root, cluster)
    if server:
        options.pop("cluster", None)
    elif options.get("cluster"):
        return _use_cluster(options, root)
    if server == LOCAL:
        deploy = options.get("deploy")
        kept = {k: v for k, v in deploy.items() if k not in _LOGIN_KEYS} if isinstance(deploy, dict) else {}
        options["deploy"] = {**kept, "method": "local"}
        return None
    if server:
        return apply_to_deploy(options, root, server)
    deploy = options.get("deploy")
    # `method: local` alone (the default a new project writes) does not pin this machine; --server local does.
    configured = (isinstance(deploy, str) and deploy != LOCAL) or (
        isinstance(deploy, dict)
        and (any(deploy.get(k) for k in ("server", "host")) or str(deploy.get("method") or LOCAL) != LOCAL)
    )
    if configured:
        return apply_to_deploy(options, root)
    remembered_cluster = deployed_cluster(root, stage)
    if remembered_cluster:
        from .onprem_cluster import load_clusters

        if remembered_cluster not in load_clusters(root):
            raise ServerError(
                f"onprem-{stage} was last deployed to cluster {remembered_cluster!r}, which no longer exists. "
                f"Pick where: --cluster NAME, --server NAME, or --server {LOCAL} for this machine"
            )
        return _use_cluster(options, root, remembered_cluster)
    remembered = deployed_server(root, stage)
    if not remembered:
        return None
    servers = load_servers(root)
    if remembered not in servers:
        close = close_servers(remembered, servers)
        hint = f"Did you mean {' or '.join(close)}? " if close else ""
        raise ServerError(
            f"onprem-{stage} was last deployed to saved server {remembered!r}, which no longer exists. {hint}"
            f"Pick the machine: --server NAME, or --server {LOCAL} for this machine"
        )
    return apply_to_deploy(options, root, remembered)


def _deployed(root: Path, stage: str, key: str) -> Optional[str]:
    try:
        data = json.loads((root / ".pskit" / f"onprem-{stage}" / DEPLOYED_FILE).read_text("utf-8"))
    except (OSError, ValueError):
        return None
    value = data.get(key) if isinstance(data, dict) else None
    return str(value) if value else None


def deployed_server(root: Path, stage: str) -> Optional[str]:
    """The saved server ``onprem-<stage>`` was last deployed to (None: this machine, an inline host, or never).
    For a cluster deploy this is the cluster's master."""
    return _deployed(root, stage, "server")


def deployed_cluster(root: Path, stage: str) -> Optional[str]:
    """The scaling cluster ``onprem-<stage>`` was last deployed to (None: one machine, or never)."""
    return _deployed(root, stage, "cluster")


def apply_to_deploy(options: Dict[str, Any], root: Path, server: Optional[str] = None) -> Optional[str]:
    """Merge a saved server into ``options.deploy`` (in place). Returns the server name used, or None.

    ``server`` (``--server`` / ``PSKIT_DEPLOY_SERVER``) wins over ``options.deploy.server``. The server's host, user,
    port and login replace those in ``options.deploy``; path, python, install, ... stay. ``method`` stays ``ssh``,
    ``scp`` or ``docker``; anything else (none, ``local``) becomes ``ssh``.
    """
    deploy = options.get("deploy")
    name = server or (deploy.get("server") if isinstance(deploy, dict) else None)
    if not name:
        return None
    item = get_server(root, str(name), origin="" if server else "pskit.yml provider.options.deploy.server")
    if not isinstance(deploy, dict):
        deploy = {"method": str(deploy)} if isinstance(deploy, str) and deploy in ("ssh", "scp", "docker") else {}
    deploy = dict(deploy)
    if str(deploy.get("method") or "local") not in ("ssh", "scp", "docker"):
        # A saved server is another machine: `method: local` (what a new pskit.yml has) would run the host here.
        deploy["method"] = "ssh"
    for key in ("identity_file", "pem", "identity", "password_file", "auth"):
        deploy.pop(key, None)
    deploy.update({"host": item["host"], "user": item.get("user") or "root", "port": int(item.get("port") or 22)})
    if item.get("identity_file"):
        deploy["pem"] = item["identity_file"]
    for key in ("password_file", "auth", "known_hosts"):
        if item.get(key):
            deploy[key] = item[key]
    if item.get("sudo") and "sudo" not in deploy:
        deploy["sudo"] = True
    deploy["server"] = str(name)
    # The server's own defaults; pskit.yml wins (its host only when it is not the default loopback).
    if item.get("home") and not deploy.get("path"):
        deploy["home"] = item["home"]
    if item.get("bind") and str(options.get("host") or _LOOPBACK_DEFAULT) == _LOOPBACK_DEFAULT:
        options["host"] = item["bind"]
    if item.get("data_dir") and not options.get("data_dir"):
        options["data_dir"] = item["data_dir"]
    options["deploy"] = deploy
    return str(name)
