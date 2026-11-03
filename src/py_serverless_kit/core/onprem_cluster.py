"""Scaling clusters for on-prem functions: Docker Swarm, Kubernetes (k3s) or HashiCorp Nomad on saved SSH servers.

A cluster is a master server plus any number of joined servers, all saved servers (``core/onprem_servers.py``).
pskit installs the orchestrator, joins servers (also while functions are running), copies the function host
image to every server (no registry), deploys it, shows each server's CPU / memory / disk, and when every
server is full can call one of your functions (and / or a webhook) so DevOps hears about it and adds a server.

Functions use a cluster with ``provider.options.cluster`` in pskit.yml (``cluster: prod`` or
``{name: prod, replicas: 3, cpu: 0.25, memory: 256}``, or ``pskit deploy --cluster prod``); without it nothing
changes: the host runs on one machine. Resources (``pskit resources onprem create``) run on one server, or on one
server of a cluster (``--cluster prod``: the server with the most free memory, or ``--node``); see :func:`place`.

A cluster can have a **load balancer**: one more saved server, outside the orchestrator, that runs OpenResty in
Docker (``pskit cluster balancer set prod lb1 --algorithm least_time``) and spreads each deployment's HTTP over the
cluster's servers, one port per deployment. Named load balancers (``core/onprem_balancers.py``) can also be attached
to a cluster (``pskit lb attach edge --cluster prod``) and serve its deployments by path next to other projects.
pskit rewrites both on every deploy, remove, join and leave; see :func:`set_balancer`. Logs, tests and the admin
API keep going to the master, as without one.

Stored in ``.pskit/onprem-clusters.json`` (out of git): orchestrator, master, joined servers, capacity limits,
alert settings, recent alerts and what is deployed. Logins stay in the saved servers.
"""

from __future__ import annotations

import json
import re
import socket
import tempfile
import threading
import time
import zlib
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from . import onprem_balancers as balancers
from . import onprem_cluster_scripts as scripts
from . import onprem_lb as lb
from . import onprem_network as network
from .onprem_services import ServiceError, _default_run, _Runner, _ssh_argv, check_ssh_login, ssh_options

CLUSTERS_FILE = Path(".pskit") / "onprem-clusters.json"
CLUSTER_SPEC = "onprem_cluster.json"  # next to pskit_host.json: where a cluster deploy goes (not hashed)
ORCHESTRATORS: Dict[str, Dict[str, str]] = {
    "swarm": {
        "label": "Docker Swarm",
        "summary": "Docker on every server; the built-in routing mesh answers on the port of every server.",
        "ports": "2377/tcp, 7946/tcp+udp, 4789/udp between servers; the functions port from users",
    },
    "kubernetes": {
        "label": "Kubernetes (k3s)",
        "summary": "Lightweight Kubernetes (k3s, no Docker needed); ServiceLB answers on the port of every server.",
        "ports": "6443/tcp, 8472/udp, 10250/tcp between servers; the functions port from users",
    },
    "nomad": {
        "label": "HashiCorp Nomad",
        "summary": "Nomad with the Docker driver. The master runs the main replica; every other server runs one web replica on its own port. A load balancer is optional.",
        "ports": "4646-4648/tcp (+4648/udp) between servers; the functions port from users",
    },
}
DEFAULT_CAPACITY = {"cpu": 85, "memory": 85, "disk": 90}
DEFAULT_ALERT = {"function": "", "stage": "", "webhook": "", "cooldown_minutes": 30}
DEFAULT_BALANCER_PORT = 80
_NAME = re.compile(r"^[a-z][a-z0-9-]{0,30}$")
_MAX_ALERTS = 50
Emit = Callable[[str], None]
RunFn = Callable[[List[str], Optional[Path]], Tuple[int, str]]


class ClusterError(ValueError):
    pass


# ----------------------------------------------------------------------------------------------- store
def _path(root: Path) -> Path:
    return Path(root) / CLUSTERS_FILE


def load_clusters(root: Path) -> Dict[str, Dict[str, Any]]:
    try:
        data = json.loads(_path(root).read_text("utf-8"))
    except (OSError, ValueError):
        return {}
    clusters = data.get("clusters") if isinstance(data, dict) else None
    return {k: v for k, v in (clusters or {}).items() if isinstance(v, dict)}


_LOCK = threading.RLock()  # the studio's watcher and requests update the file from several threads


def _save(root: Path, clusters: Dict[str, Dict[str, Any]]) -> None:
    path = _path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps({"clusters": clusters}, indent=2, sort_keys=True) + "\n").encode("utf-8"))


def _update(root: Path, name: str, change: Callable[[Dict[str, Any]], None]) -> Dict[str, Any]:
    with _LOCK:
        clusters = load_clusters(root)
        if name not in clusters:
            raise ClusterError(_unknown(root, name))
        change(clusters[name])
        _save(root, clusters)
        return clusters[name]


def _unknown(root: Path, name: str) -> str:
    known = ", ".join(sorted(load_clusters(root))) or "none yet"
    return f"no cluster {name!r} (clusters: {known}). Create one: pskit cluster create NAME --master SERVER"


def get_cluster(root: Path, name: str) -> Dict[str, Any]:
    cluster = load_clusters(root).get(str(name))
    if cluster is None:
        raise ClusterError(_unknown(root, name))
    return cluster


def list_clusters(root: Path) -> List[Dict[str, Any]]:
    return [public(name, item, root) for name, item in sorted(load_clusters(root).items())]


def master_serves(item: Dict[str, Any]) -> bool:
    """Whether the master takes a share of the requests next to the other servers.

    On: the load balancers send it requests like any other server (Nomad: its main replica answers them;
    Swarm / k3s: web replicas may also run on it). Off: it is only a backup there, used while every other
    server is down, so it keeps its CPU for the control plane, schedules, queues and data (Swarm / k3s also
    keep web replicas off it while another server can take them). Clusters saved without the setting keep
    what they did before: off on Nomad, on on Swarm and k3s."""
    value = item.get("master_serves")
    return value if isinstance(value, bool) else str(item.get("orchestrator") or "") != "nomad"


def public(name: str, item: Dict[str, Any], root: Optional[Path] = None) -> Dict[str, Any]:
    """What the CLI and studio show (no logins: those stay in the saved servers)."""
    orch = str(item.get("orchestrator") or "")
    return {
        "name": name,
        "orchestrator": orch,
        "orchestrator_label": ORCHESTRATORS.get(orch, {}).get("label", orch),
        "master": item.get("master"),
        "master_serves": master_serves(item),
        "advertise": item.get("advertise"),
        "nodes": [{"server": s, **n} for s, n in sorted((item.get("nodes") or {}).items())],
        "capacity": {**DEFAULT_CAPACITY, **(item.get("capacity") or {})},
        "alert": {**DEFAULT_ALERT, **(item.get("alert") or {})},
        "watch": item.get("watch") or {"enabled": False, "interval_seconds": 60},
        "alerts": list(item.get("alerts") or [])[-_MAX_ALERTS:],
        "deployments": item.get("deployments") or {},
        "balancer": _balancer_public(item),
        "balancers": _attached_public(root, name, item) if root is not None else [],
        "created_at": item.get("created_at"),
    }


def _balancer_public(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The load balancer and each deployment's URL on it, or None."""
    balancer = item.get("balancer")
    if not isinstance(balancer, dict) or not balancer.get("server"):
        return None
    urls = {stack: _balancer_url(balancer, _listen_port(balancer, dep))
            for stack, dep in sorted((item.get("deployments") or {}).items())}
    return {**balancer, "urls": urls}


def _with_named(root: Path, name: str, item: Dict[str, Any]) -> Dict[str, Any]:
    """``item`` with the named load balancers attached to it (for the firewall rules)."""
    named = [b for b in balancers.load_balancers(root).values() if name in (b.get("clusters") or [])]
    return {**item, "_named_balancers": named}


def _attached_public(root: Path, name: str, item: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Named load balancers attached to cluster ``name`` and the URL each deployment has there (unless a project
    gave its route another path)."""
    attached = []
    deployments = item.get("deployments") or {}
    services: Dict[str, int] = {}
    for dep in deployments.values():
        services[str(dep.get("service"))] = services.get(str(dep.get("service")), 0) + 1
    for lb_name, lb_item in sorted(balancers.load_balancers(root).items()):
        if name not in (lb_item.get("clusters") or []):
            continue
        urls = {}
        for stack, dep in sorted(deployments.items()):
            service = str(dep.get("service") or stack)
            path = service if services.get(service, 0) < 2 else f"{service}-{dep.get('stage')}"
            try:
                urls[stack] = balancers.route_url(lb_item, path)
            except ValueError:
                continue
        attached.append({**balancers.public(lb_name, lb_item), "urls": urls})
    return attached


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _target(root: Path, server: str) -> Dict[str, Any]:
    from .onprem_servers import ServerError, server_target

    try:
        return server_target(root, server)
    except ServerError as exc:
        raise ClusterError(str(exc)) from None


def _bind_address(target: Dict[str, Any]) -> str:
    """A saved server's bind address when it is one specific IP (not 0.0.0.0 / 127.0.0.1): its cluster address."""
    bind = str(target.get("bind") or "")
    return "" if bind in ("", "0.0.0.0", "127.0.0.1") else bind  # noqa: S104


def _ip(host: str) -> str:
    """The address the orchestrator advertises: an IP (Swarm, k3s and Nomad reject host names)."""
    try:
        socket.inet_aton(host)
        return host
    except OSError:
        pass
    try:
        return socket.gethostbyname(host)
    except OSError:
        return host


# ----------------------------------------------------------------------------------------------- SSH
def _workdir(target: Dict[str, Any]) -> str:
    """``<home>/pskit-cluster`` for a server with a home path, else ``pskit-cluster`` in the SSH user's home."""
    home = str(target.get("home") or "").rstrip("/")
    return f"{home}/pskit-cluster" if home else "pskit-cluster"


def _mkdir_command(target: Dict[str, Any]) -> str:
    path = _workdir(target)
    if not path.startswith("/"):
        return f"mkdir -p {path}"
    # A home path such as /opt/pskit may need sudo once; the folder then belongs to the SSH user.
    return (f"mkdir -p {path} 2>/dev/null || {{ sudo -n mkdir -p {path} && "
            f"sudo -n chown \"$(id -u):$(id -g)\" {path}; }}")


def _script(target: Dict[str, Any], script: str, emit: Emit, run: Optional[RunFn], *, label: str,
            show: bool = True, check: bool = True) -> str:
    """Copy ``script`` to ``<workdir>/<label>.sh`` on the server and run it from the folder above (the home path,
    or the SSH user's home), so paths in the script (``pskit-cluster/...``) land there. Returns its output."""
    from ..providers.onprem_remote import scp_argv

    runner = _Runner(emit, run)
    remote = f"{_workdir(target)}/{label}.sh"
    home = str(target.get("home") or "").rstrip("/")
    with tempfile.TemporaryDirectory(prefix="pskit-cluster-") as tmp:
        local = Path(tmp) / f"{label}.sh"
        local.write_bytes(script.replace("\r\n", "\n").encode("utf-8"))
        runner(_ssh_argv(target, _mkdir_command(target)), show=False)
        runner(scp_argv(ssh_options(target), str(local), remote), show=False)
    command = f"cd {home} && sh pskit-cluster/{label}.sh" if home else f"sh {remote}"
    return runner(_ssh_argv(target, command), show=show, check=check)


def _values(text: str, key: str) -> List[str]:
    return [line.split("=", 1)[1].strip() for line in text.splitlines() if line.startswith(key + "=")]


# ----------------------------------------------------------------------------------------------- lifecycle
def create_cluster(
    root: Path, name: str, orchestrator: str, master: str, emit: Emit, *, advertise: str = "",
    nomad_version: str = "", serve_on_master: Optional[bool] = None, run: Optional[RunFn] = None,
) -> Dict[str, Any]:
    """Install the orchestrator on saved server ``master`` and save cluster ``name``.

    ``serve_on_master``: whether the master also takes requests (see :func:`master_serves`); None keeps the
    orchestrator's default (Nomad: no, Swarm / k3s: yes)."""
    if not _NAME.match(str(name)):
        raise ClusterError("cluster name: lowercase letter first; lowercase letters, digits and - (max 31)")
    if orchestrator not in ORCHESTRATORS:
        raise ClusterError(f"orchestrator must be one of {', '.join(ORCHESTRATORS)}")
    clusters = load_clusters(root)
    if name in clusters:
        raise ClusterError(f"cluster {name!r} already exists")
    for other, item in clusters.items():
        if master in (item.get("nodes") or {}):
            raise ClusterError(f"server {master!r} is already in cluster {other!r}")
    _not_a_balancer(clusters, master, root=root)
    target = _target(root, master)
    if run is None:
        check_ssh_login(target)
    addr = advertise or _bind_address(target) or _ip(str(target["host"]))
    version = nomad_version or scripts.NOMAD_VERSION
    emit(f"Installing {ORCHESTRATORS[orchestrator]['label']} on {master} ({addr}) ...")
    out = _script(target, scripts.master_script(orchestrator, addr, version), emit, run, label="master")
    node = (_values(out, "PSKIT_NODE") or [str(target["host"])])[-1]
    item = {
        "orchestrator": orchestrator,
        "master": master,
        "advertise": addr,
        "nodes": {master: {"role": "master", "node": node, "address": addr, "joined_at": _now()}},
        "capacity": dict(DEFAULT_CAPACITY),
        "alert": dict(DEFAULT_ALERT),
        "created_at": _now(),
    }
    item["master_serves"] = master_serves({**item, "master_serves": serve_on_master})
    if orchestrator == "nomad" and nomad_version:
        item["nomad_version"] = nomad_version
    with _LOCK:
        clusters = load_clusters(root)
        clusters[name] = item
        _save(root, clusters)
    emit(f"Cluster {name} is ready: master {master} (node {node}). Join more servers: pskit cluster join {name} SERVER")
    emit(f"  {_serving_note(item)}")
    network.emit_rules(emit, f"cluster {name} ({ORCHESTRATORS[orchestrator]['label']}, master {master})",
                       network.cluster(name, item))
    return public(name, item, root)


def join_server(root: Path, name: str, server: str, emit: Emit, *, advertise: str = "",
                run: Optional[RunFn] = None) -> Dict[str, Any]:
    """Install the agent on saved server ``server``, join it, and copy the deployed images to it."""
    cluster = get_cluster(root, name)
    for other, item in load_clusters(root).items():
        if server in (item.get("nodes") or {}):
            raise ClusterError(f"server {server!r} is already in cluster {other!r}")
    _not_a_balancer(load_clusters(root), server, root=root)
    orch = cluster["orchestrator"]
    master = _target(root, cluster["master"])
    target = _target(root, server)
    if run is None:
        check_ssh_login(target)
    addr = advertise or _bind_address(target) or _ip(str(target["host"]))
    emit(f"Asking {cluster['master']} for a join token ...")
    out = _script(master, scripts.join_token_script(orch), emit, run, label="token", show=False)
    token = (_values(out, "PSKIT_TOKEN") or [""])[-1]
    members = (_values(out, "PSKIT_MEMBERS") or [""])[-1].split()
    if orch != "nomad" and not token:
        raise ClusterError(f"the master {cluster['master']} gave no join token: {out.strip()[-300:]}")
    emit(f"Installing {ORCHESTRATORS[orch]['label']} on {server} ({addr}) and joining {name} ...")
    version = str(cluster.get("nomad_version") or scripts.NOMAD_VERSION)
    out = _script(target, scripts.join_script(orch, str(cluster["advertise"]), token, addr, version, members), emit,
                  run, label="join")
    node = (_values(out, "PSKIT_NODE") or [str(target["host"])])[-1]
    node_id = (_values(out, "PSKIT_NODE_ID") or [""])[-1]
    if orch == "swarm" and node_id:
        _script(master, scripts.forget_stale_script(orch, node, node_id), emit, run, label="forget-stale",
                show=False, check=False)
    deployments = dict(cluster.get("deployments") or {})
    for dep in (d for _k, d in sorted(deployments.items())):
        if dep.get("image"):
            emit(f"Copying image {dep['image']} to {server} ...")
            try:
                ship_image(orch, str(dep["image"]), {server: target}, emit, run)
            except ServiceError as exc:
                emit(f"  could not copy {dep['image']}: {exc}. Run pskit deploy again to copy it.")
    _update(root, name, lambda c: c.setdefault("nodes", {}).__setitem__(
        server, {"role": "worker", "node": node, "address": addr, "joined_at": _now()}))
    emit(f"{server} joined {name} as node {node}. Replicas spread to it as the orchestrator schedules them.")
    if not master_serves(cluster) and orch != "nomad" and deployments:
        emit(f"  The master does not serve requests: run pskit deploy again to move web replicas off"
             f" {cluster['master']} now that {server} can take them.")
    sync_balancer(root, name, emit, run=run)
    balancers.sync_cluster(root, name, emit, run=run)
    network.emit_rules(emit, f"{server} joined cluster {name}", network.cluster(
        name, _with_named(root, name, get_cluster(root, name)), only=server))
    return public(name, get_cluster(root, name), root)


def leave_server(root: Path, name: str, server: str, emit: Emit, *, run: Optional[RunFn] = None) -> Dict[str, Any]:
    """Drain ``server`` (its replicas move to the others), stop its agent and remove it from the cluster."""
    cluster = get_cluster(root, name)
    node = (cluster.get("nodes") or {}).get(server)
    if node is None:
        raise ClusterError(f"{server!r} is not in cluster {name}")
    if server == cluster["master"]:
        raise ClusterError(f"the master cannot leave; remove the cluster instead (uninstalls it from every server):"
                           f" pskit cluster remove {name} --uninstall")
    orch = cluster["orchestrator"]
    master = _target(root, cluster["master"])
    node_name = str(node.get("node") or "")
    node_id = _nomad_node_id(master, node_name, emit, run) if orch == "nomad" else ""
    # Stop sending requests to it first, so draining does not cut requests in flight through a load balancer.
    others = {s: n for s, n in (cluster.get("nodes") or {}).items() if s != server}
    if cluster.get("balancer"):
        sync_balancer(root, name, emit, run=run, cluster={**cluster, "nodes": others})
    balancers.sync_cluster(root, name, emit, run=run, cluster={**cluster, "nodes": others})
    emit(f"Draining {server} (node {node_name}) ...")
    _script(master, scripts.drain_script(orch, node_name, node_id), emit, run, label="drain", check=False)
    emit(f"Stopping the agent on {server} ...")
    try:
        _script(_target(root, server), scripts.leave_script(orch), emit, run, label="leave", check=False)
    except (ServiceError, ClusterError) as exc:
        emit(f"  {server} did not answer ({exc}); removing it from the cluster anyway")
    _script(master, scripts.forget_script(orch, node_name, node_id), emit, run, label="forget", check=False)
    _update(root, name, lambda c: (c.get("nodes") or {}).pop(server, None))
    _untag_resources(root, name, server, emit)
    emit(f"{server} left {name}.")
    return public(name, get_cluster(root, name), root)


def remove_cluster(root: Path, name: str, emit: Emit, *, uninstall: bool = False, delete_data: bool = False,
                   run: Optional[RunFn] = None) -> None:
    """Forget the cluster (servers keep their orchestrator; deployed functions keep running).

    ``uninstall``: first take off everything pskit installed: the deployments, the load balancer, the agent on
    every joined server and the orchestrator on the master (see :func:`uninstall_cluster`)."""
    if uninstall:
        uninstall_cluster(root, name, emit, delete_data=delete_data, run=run)
    with _LOCK:
        clusters = load_clusters(root)
        removed = clusters.pop(str(name), None)
        if removed is None:
            raise ClusterError(_unknown(root, name))
        _save(root, clusters)
    _untag_resources(root, name, None, emit)
    if uninstall:
        emit(f"Removed cluster {name}. Docker and the saved servers stay. Each project that deployed to it still has"
             " its Terraform state: run pskit remove there, or deploy it again without the cluster.")
        return
    emit(f"Forgot cluster {name}. The servers keep running; remove deployments first with pskit remove.")
    emit(f"  To also uninstall the orchestrator from every server: pskit cluster remove {name} --uninstall"
         " (before forgetting it).")
    balancer = (removed.get("balancer") or {}).get("server")
    if balancer:
        emit(f"The load balancer on {balancer} keeps running too: pskit cluster balancer remove {name} first, or"
             f" docker rm -f {lb.container_name()} on {balancer}.")


def uninstall_cluster(root: Path, name: str, emit: Emit, *, delete_data: bool = False,
                      run: Optional[RunFn] = None) -> None:
    """Take off what pskit installed for cluster ``name`` (the cluster itself stays saved; see
    :func:`remove_cluster`): its load balancer, its routes on named load balancers, the deployments, the agent on
    every joined server and then the orchestrator on the master. A server that does not answer only warns, so an
    offline server never blocks the removal. ``delete_data``: also delete the main replicas' data on the master."""
    cluster = get_cluster(root, name)
    orch = str(cluster["orchestrator"])
    master_server = str(cluster["master"])
    stacks = sorted(cluster.get("deployments") or {})
    if (cluster.get("balancer") or {}).get("server"):
        remove_balancer(root, name, emit, run=run)
    for lb_name in balancers.attached_to(root, name):
        try:
            balancers.detach_cluster(root, lb_name, name, emit, run=run)
        except (ServiceError, ClusterError, ValueError) as exc:
            emit(f"  could not take {name} off load balancer {lb_name}: {exc}")

    def on(server: str, script: str, label: str) -> bool:
        try:
            _script(_target(root, server), script, emit, run, label=label, check=False)
            return True
        except (ServiceError, ClusterError) as exc:
            emit(f"  WARNING: {server} did not answer ({exc}). Uninstall it there by hand later.")
            return False

    for stack in stacks:
        emit(f"Removing deployment {stack} ...")
        on(master_server, scripts.destroy_script(orch, stack), f"destroy-{stack}")
    workers = sorted(s for s in (cluster.get("nodes") or {}) if s != master_server)
    for server in workers:
        emit(f"Uninstalling the {ORCHESTRATORS[orch]['label']} agent from {server} ...")
        on(server, scripts.uninstall_script(orch, master=False, stacks=stacks), "uninstall")
    try:
        data_root = str(_target(root, master_server).get("data_dir") or "")
    except ClusterError:
        data_root = ""
    emit(f"Uninstalling {ORCHESTRATORS[orch]['label']} from the master {master_server} ...")
    on(master_server, scripts.uninstall_script(orch, master=True, stacks=stacks, data_root=data_root,
                                               delete_data=delete_data), "uninstall")
    if stacks and not delete_data:
        where = data_root or scripts.DATA_ROOT
        emit(f"  The main replicas' data stays on {master_server} ({where}/<stack>"
             + (", or Docker volumes <stack>_data)" if orch == "swarm" else ")")
             + "; remove the cluster with --delete-data to delete it too.")


def _nomad_node_id(master: Dict[str, Any], node: str, emit: Emit, run: Optional[RunFn]) -> str:
    code, text = (run or _default_run)(_ssh_argv(master, "curl -fsS http://127.0.0.1:4646/v1/nodes"), None)
    try:
        nodes = json.loads(text) if not code else []
    except ValueError:
        nodes = []
    for item in nodes if isinstance(nodes, list) else []:
        if item.get("Name") == node:
            return str(item.get("ID") or "")
    emit(f"  Nomad does not list node {node}")
    return ""


def save_settings(root: Path, name: str, body: Dict[str, Any]) -> Dict[str, Any]:
    """Capacity limits (percent), alert target (function / webhook, cooldown) and the studio's watcher."""
    capacity = body.get("capacity")
    alert = body.get("alert")
    watch = body.get("watch")

    def change(c: Dict[str, Any]) -> None:
        if isinstance(capacity, dict):
            merged = {**DEFAULT_CAPACITY, **(c.get("capacity") or {})}
            for key in DEFAULT_CAPACITY:
                if key in capacity:
                    value = int(capacity[key])
                    if not 10 <= value <= 100:
                        raise ClusterError(f"capacity.{key} must be 10..100 (percent)")
                    merged[key] = value
            c["capacity"] = merged
        if isinstance(alert, dict):
            merged_alert = {**DEFAULT_ALERT, **(c.get("alert") or {})}
            for key in ("function", "stage", "webhook"):
                if key in alert:
                    merged_alert[key] = str(alert[key] or "").strip()
            if merged_alert["webhook"] and not merged_alert["webhook"].lower().startswith(("http://", "https://")):
                raise ClusterError("alert.webhook must be an http(s) URL")
            if "cooldown_minutes" in alert:
                merged_alert["cooldown_minutes"] = max(1, int(alert["cooldown_minutes"] or 30))
            c["alert"] = merged_alert
        if isinstance(watch, dict):
            c["watch"] = {"enabled": bool(watch.get("enabled")),
                          "interval_seconds": max(15, int(watch.get("interval_seconds") or 60))}

    return public(name, _update(root, name, change), root)


def _serving_note(cluster: Dict[str, Any]) -> str:
    master = cluster.get("master")
    if master_serves(cluster):
        return (f"The master {master} serves requests too: load balancers spread them over every server,"
                f" the master included.")
    keep = "" if cluster.get("orchestrator") == "nomad" else " and web replicas stay off it while another server can run them"
    return (f"The master {master} does not serve requests: load balancers use it only while every other server is"
            f" down{keep}. Until a server joins, the master serves everything.")


def set_master_serves(root: Path, name: str, enabled: bool, emit: Emit, *, run: Optional[RunFn] = None
                      ) -> Dict[str, Any]:
    """Turn requests to the master on or off (see :func:`master_serves`) and update the load balancers now.
    Swarm and k3s move web replicas on or off the master at the next ``pskit deploy``."""
    cluster = _update(root, name, lambda c: c.__setitem__("master_serves", bool(enabled)))
    emit(_serving_note(cluster))
    if isinstance(cluster.get("balancer"), dict) and cluster["balancer"].get("server"):
        sync_balancer(root, name, emit, run=run)
    balancers.sync_cluster(root, name, emit, run=run)
    if cluster.get("orchestrator") != "nomad" and cluster.get("deployments"):
        emit("  Run pskit deploy again for each deployment so its web replicas follow"
             f" ({', '.join(sorted(cluster['deployments']))}).")
    return public(name, cluster, root)


# ----------------------------------------------------------------------------------------------- images
CHUNK_BYTES = 16 * 1024 * 1024  # one scp per part: a dropped connection costs one part, not the whole image
COPY_ATTEMPTS = 6
RETRY_DELAY = 5.0  # seconds before the first retry; doubles each time (max 60)


def ship_image(orchestrator: str, image: str, targets: Dict[str, Dict[str, Any]], emit: Emit,
               run: Optional[RunFn] = None, *, tar: Optional[Path] = None, required: Tuple[str, ...] = ()) -> List[str]:
    """Copy ``image`` (built on this machine) to every server that does not have it yet, in parallel.

    The image goes gzip-compressed in parts with checksums. A server gets only the parts it does not already
    have, so a broken connection is retried from where it stopped (also by the next ``pskit deploy``). Returns
    the servers that still could not get it; raises when one of ``required`` (the master) or every server failed.
    """
    runner = _Runner(emit, run)
    fn = run or _default_run
    missing = {s: t for s, t in targets.items() if fn(_ssh_argv(t, scripts.has_image_command(orchestrator, image)), None)[0]}
    if not missing:
        emit(f"  every server already has {image}")
        return []
    with tempfile.TemporaryDirectory(prefix="pskit-image-") as tmp:
        archive = tar or Path(tmp) / "image.tar"
        if tar is None:
            runner(["docker", "save", "-o", str(archive), image])
        if not archive.is_file():
            raise ServiceError(f"docker save wrote no {archive.name} for {image}")
        parts, digest, size = _pack_image(archive, Path(tmp) / "parts")
        emit(f"  compressed to {size / 1e6:.0f} MB in {len(parts)} part(s)")
        slug = re.sub(r"[^A-Za-z0-9._-]+", "-", image)
        repo = re.sub(r"[^A-Za-z0-9._-]+", "-", image.rsplit(":", 1)[0])

        def one(server: str) -> Optional[str]:
            target = missing[server]
            parts_dir = f"{_workdir(target)}/{slug}.parts"
            stale = f"{_workdir(target)}/{repo}-{'?' * 12}.parts"  # older tags of this stack only
            load = scripts.image_load_script(orchestrator, parts_dir, digest, stale_glob=stale)
            delay = RETRY_DELAY
            error: Optional[ServiceError] = None
            for attempt in range(1, COPY_ATTEMPTS + 1):
                try:
                    _send_parts(target, server, parts_dir, parts, size, runner, fn, emit)
                    _script(target, load, emit, run, label="load", show=False)
                    emit(f"  {server}: loaded {image}")
                    return None
                except ServiceError as exc:
                    error = exc
                if not fn(_ssh_argv(target, scripts.has_image_command(orchestrator, image)), None)[0]:
                    emit(f"  {server}: loaded {image}")  # the load went through; only a later step failed
                    return None
                if attempt < COPY_ATTEMPTS:
                    emit(f"  {server}: copy interrupted ({error}); resuming in {delay:.0f} s"
                         f" (attempt {attempt + 1} of {COPY_ATTEMPTS})")
                    time.sleep(delay)
                    delay = min(60.0, delay * 2)
            return f"{server}: {error}"

        with ThreadPoolExecutor(max_workers=min(8, len(missing))) as pool:
            results = dict(zip(sorted(missing), pool.map(one, sorted(missing))))
    failed = {s: e for s, e in results.items() if e}
    if failed and (len(failed) == len(missing) or any(s in failed for s in required)):
        raise ServiceError("could not copy the image to " + "; ".join(failed.values())
                           + ". Check the connection and run the deploy again: parts already copied are kept")
    for error in failed.values():
        emit(f"  WARNING: {error}. Replicas placed on that server cannot start until the image is there:"
             " run the deploy again to finish the copy")
    return sorted(failed)


def _pack_image(archive: Path, out: Path) -> Tuple[List[Tuple[str, Path, str, int]], str, int]:
    """gzip ``archive`` (reproducibly) into ``out/part-NNNNN`` files of ``CHUNK_BYTES``.
    Returns ``[(name, path, sha256, bytes)]``, the sha256 of the whole gzip and its size."""
    import gzip
    import hashlib
    import shutil

    out.mkdir(parents=True, exist_ok=True)
    packed = out / "image.tar.gz"
    with open(archive, "rb") as src, open(packed, "wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, compresslevel=6, mtime=0) as gz:
            shutil.copyfileobj(src, gz, 1024 * 1024)
    whole = hashlib.sha256()
    parts: List[Tuple[str, Path, str, int]] = []
    with open(packed, "rb") as handle:
        while True:
            chunk = handle.read(CHUNK_BYTES)
            if not chunk and parts:
                break
            name = f"part-{len(parts):05d}"
            path = out / name
            path.write_bytes(chunk)
            whole.update(chunk)
            parts.append((name, path, hashlib.sha256(chunk).hexdigest(), len(chunk)))
            if not chunk:
                break
    size = packed.stat().st_size
    packed.unlink()
    return parts, whole.hexdigest(), size


def _send_parts(target: Dict[str, Any], server: str, parts_dir: str, parts: List[Tuple[str, Path, str, int]],
                size: int, runner: _Runner, fn: RunFn, emit: Emit) -> None:
    """scp the parts the server does not have yet (checked by sha256), reporting progress."""
    from ..providers.onprem_remote import _shq, scp_argv

    runner(_ssh_argv(target, f"{_mkdir_command(target)} && mkdir -p {_shq(parts_dir)}"), show=False)
    _code, listing = fn(_ssh_argv(target, f"cd {_shq(parts_dir)} && sha256sum part-* 2>/dev/null || true"), None)
    have = {}
    for line in listing.splitlines():
        bits = line.split()
        if len(bits) == 2:
            have[bits[1].lstrip("*")] = bits[0]
    todo = [p for p in parts if have.get(p[0]) != p[2]]
    done = size - sum(p[3] for p in todo)
    if done and todo:
        emit(f"  {server}: {done / 1e6:.0f} of {size / 1e6:.0f} MB already there, sending the rest")
    for index, (name, path, _sha, length) in enumerate(todo, 1):
        runner(scp_argv(ssh_options(target), str(path), f"{parts_dir}/{name}"), show=False)
        done += length
        if index == len(todo) or index % 4 == 0:
            emit(f"  {server}: {done / 1e6:.0f} of {size / 1e6:.0f} MB")


# ----------------------------------------------------------------------------------------------- deploy
def deploy_spec(root: Path, options: Dict[str, Any]) -> Dict[str, Any]:
    """``provider.options.cluster`` -> the deploy target in place on ``options`` (``deploy`` becomes the master over
    SSH so logs, test and the studio reach the host). Returns the normalized cluster settings."""
    raw = options.get("cluster")
    body: Dict[str, Any] = {"name": raw} if isinstance(raw, str) else dict(raw or {})
    name = str(body.get("name") or "")
    if not name:
        raise ClusterError("options.cluster needs a name: cluster: NAME or cluster: {name: NAME, replicas: 3}")
    cluster = get_cluster(root, name)
    replicas = body.get("replicas", 2)
    cpu = body.get("cpu", 0.25)
    memory = body.get("memory", 256)
    if isinstance(replicas, bool) or not isinstance(replicas, int) or not 1 <= replicas <= 500:
        raise ClusterError("options.cluster.replicas must be an integer 1..500")
    if isinstance(cpu, bool) or not isinstance(cpu, (int, float)) or not 0.05 <= float(cpu) <= 64:
        raise ClusterError("options.cluster.cpu must be 0.05..64 (CPU cores each replica reserves)")
    if isinstance(memory, bool) or not isinstance(memory, int) or not 32 <= memory <= 262144:
        raise ClusterError("options.cluster.memory must be 32..262144 (MB each replica reserves)")
    balancer_port = body.get("balancer_port")
    if balancer_port is not None and (isinstance(balancer_port, bool) or not isinstance(balancer_port, int)
                                      or not 1 <= balancer_port <= 65535):
        raise ClusterError("options.cluster.balancer_port must be a port 1..65535 (on the cluster's load balancer)")
    unknown = sorted(set(body) - {"name", "replicas", "cpu", "memory", "balancer_port"})
    if unknown:
        raise ClusterError(f"unknown options.cluster keys {unknown}; expected name, replicas, cpu, memory,"
                           " balancer_port")
    master = get_server_item(root, str(cluster["master"]))
    deploy = options.get("deploy")
    deploy = deploy if isinstance(deploy, dict) else {}
    kept = {k: v for k, v in deploy.items() if k in ("python", "target_arch")}
    new = {**kept, "method": "docker", "host": master["host"], "user": master.get("user") or "root",
           "port": int(master.get("port") or 22), "server": str(cluster["master"])}
    if master.get("identity_file"):
        new["pem"] = master["identity_file"]
    for key in ("password_file", "auth", "known_hosts"):
        if master.get(key):
            new[key] = master[key]
    if master.get("sudo"):
        new["sudo"] = True
    options["deploy"] = new
    settings = {"name": name, "orchestrator": cluster["orchestrator"], "replicas": replicas, "cpu": float(cpu),
                "memory": memory}
    if balancer_port is not None:
        settings["balancer_port"] = balancer_port
    options["cluster"] = settings
    return settings


def get_server_item(root: Path, server: str) -> Dict[str, Any]:
    from .onprem_servers import ServerError, get_server

    try:
        return get_server(root, server)
    except ServerError as exc:
        raise ClusterError(str(exc)) from None


def cluster_file(root: Path, settings: Dict[str, Any]) -> Dict[str, Any]:
    """``onprem_cluster.json`` for the deploy step: the cluster's servers with their logins (paths, no secrets)."""
    cluster = get_cluster(root, settings["name"])
    nodes = {s: {**n, "target": _target(root, s)} for s, n in (cluster.get("nodes") or {}).items()}
    return {**settings, "project_root": str(Path(root).resolve()), "master": cluster["master"],
            "advertise": cluster["advertise"], "master_serves": master_serves(cluster), "nodes": nodes}


def deploy(app_dir: Path, spec: Dict[str, Any], emit: Emit, run: Optional[RunFn] = None) -> Dict[str, Any]:
    """Terraform apply of a cluster deploy: build the image here, copy it to every server, apply, wait healthy."""
    info = json.loads((app_dir / CLUSTER_SPEC).read_text("utf-8"))
    orch = str(info["orchestrator"])
    stack = scripts.stack_name(str(spec["service"]), str(spec.get("deploy_stage") or spec["stage"]))
    port = int(spec.get("port") or 8080)
    root = Path(str(info.get("project_root") or app_dir.parents[2]))
    balancer_port = int(info["balancer_port"]) if info.get("balancer_port") else None
    _check_listen_port(root, str(info["name"]), stack, balancer_port)
    runner = _Runner(emit, run)
    emit(f"Building the function host image for {stack} ...")
    if run is None:
        _build(app_dir, stack)
    else:
        runner(["docker", "build", "-t", f"{stack}:build", "."], show=False)
    ident = runner(["docker", "image", "inspect", "--format", "{{.Id}}", f"{stack}:build"], show=False).strip()
    tag = re.sub(r"^sha256:", "", ident)[:12] or "latest"
    image = f"{stack}:{tag}"
    runner(["docker", "tag", f"{stack}:build", image], show=False)
    nodes = info["nodes"]
    master_server = str(info["master"])
    master = nodes[master_server]
    emit(f"Copying {image} to {len(nodes)} server(s) ...")
    ship_image(orch, image, {s: n["target"] for s, n in nodes.items()}, emit, run, required=(master_server,))
    replicas = int(info["replicas"])
    data_root = str((master.get("target") or {}).get("data_dir") or "")
    common: Dict[str, Any] = {"port": port, "replicas": replicas, "master_node": str(master["node"]),
                              "cpu": float(info["cpu"]), "memory_mb": int(info["memory"]),
                              "data_root": data_root or None}
    # Off: web replicas skip the master, but only while another server can run them (else nothing would answer).
    avoid_master = info.get("master_serves") is False and len(nodes) > 1
    if orch in ("swarm", "kubernetes"):
        common["avoid_master"] = avoid_master
        if avoid_master:
            emit(f"  The master {master_server} does not serve requests: web replicas run on the other server(s)")
    if orch == "swarm":
        python = "python3" if spec.get("language") == "node" else "python"
        manifest = scripts.swarm_stack(stack, image, python=python, **common)
    elif orch == "kubernetes":
        manifest = scripts.kubernetes_manifest(stack, image, **common)
    else:
        manifest = scripts.nomad_job(stack, image, master_addr=str(info["advertise"]), **common)
        workers = len(nodes) - 1
        if replicas > workers:
            emit(f"  Nomad runs one web replica per server besides the master: {workers} of {replicas} can start "
                 "now, the rest start when you join more servers")
    emit(f"Deploying {stack} on {ORCHESTRATORS[orch]['label']} ({replicas} web replica(s) + 1 main) ...")
    data_path = f"{data_root or scripts.DATA_ROOT}/{stack}" if data_root or orch != "swarm" else ""
    _script(master["target"], scripts.apply_script(orch, stack, manifest, port, data_path=data_path), emit, run,
            label=f"apply-{stack}")
    for node in nodes.values():
        try:
            _script(node["target"], scripts.prune_script(orch, stack, tag), emit, run, label="prune", show=False,
                    check=False)
        except ServiceError:
            pass
    endpoint = str(spec.get("endpoint") or f"http://{info['advertise']}:{port}")
    record = {"service": spec["service"], "stage": spec["stage"], "image": image, "replicas": replicas, "port": port,
              "endpoint": endpoint, "work_dir": str(app_dir.parent.resolve()), "deployed_at": _now()}
    if balancer_port:
        record["balancer_port"] = balancer_port
    try:
        cluster = _update(root, str(info["name"]), lambda c: c.setdefault("deployments", {}).__setitem__(stack, record))
    except ClusterError:
        cluster = {}
    emit(f"{stack} is running on cluster {info['name']}: {endpoint}")
    if cluster:
        network.emit_rules(emit, f"{stack} on cluster {info['name']}", [
            r for r in network.cluster(str(info["name"]), _with_named(root, str(info["name"]), cluster))
            if stack in r["why"] or r["why"].startswith(f"cluster {info['name']}:")])
    balancer = cluster.get("balancer") if isinstance(cluster.get("balancer"), dict) else None
    if cluster:
        balancers.sync_cluster(root, str(info["name"]), emit, run=run)
    if balancer:
        record["url"] = _balancer_url(balancer, _listen_port(balancer, record))
        sync_balancer(root, str(info["name"]), emit, run=run)
        emit(f"  Public URL (load balancer on {balancer['server']}): {record['url']}")
        emit(f"  {endpoint} stays the master's address: logs, tests and the admin API use it.")
    elif balancers.attached_to(root, str(info["name"])):
        emit(f"  {endpoint} stays the master's address: logs, tests and the admin API use it.")
    elif orch == "nomad":
        others = [name for name in nodes if name != master_server]
        where = ", ".join(others) if others else "no other server yet"
        emit("  Nomad does not load-balance. This address is the main replica on the master.")
        emit(f"  Web replicas answer on the same port on: {where}.")
        emit("  A load balancer (nginx, HAProxy, Traefik) is optional, and only when you want one URL for all of them.")
    return record


def _build(app_dir: Path, stack: str) -> None:
    import subprocess

    proc = subprocess.run(  # noqa: S603 - fixed argv
        ["docker", "build", "-t", f"{stack}:build", "."], cwd=str(app_dir), stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
    )
    if proc.returncode:
        tail = proc.stdout.decode("utf-8", "replace").strip().splitlines()[-30:]
        raise ServiceError("docker build failed (Docker must run on this machine):\n" + "\n".join(tail))


def destroy(app_dir: Path, spec: Dict[str, Any], emit: Emit, run: Optional[RunFn] = None) -> None:
    """Terraform destroy: remove the workloads (the main replica's data stays on the master)."""
    info = json.loads((app_dir / CLUSTER_SPEC).read_text("utf-8"))
    stack = scripts.stack_name(str(spec["service"]), str(spec.get("deploy_stage") or spec["stage"]))
    master = info["nodes"][str(info["master"])]
    root = Path(str(info.get("project_root") or app_dir.parents[2]))
    try:
        cluster = _update(root, str(info["name"]), lambda c: (c.get("deployments") or {}).pop(stack, None))
    except ClusterError:
        cluster = {}
    if cluster.get("balancer"):
        # Off the load balancer before the replicas stop, so it does not answer 502 in between.
        sync_balancer(root, str(info["name"]), emit, run=run)
    if cluster:
        balancers.sync_cluster(root, str(info["name"]), emit, run=run)
    _script(master["target"], scripts.destroy_script(str(info["orchestrator"]), stack), emit, run,
            label=f"destroy-{stack}", check=False)


def scale(root: Path, name: str, stack: str, replicas: int, emit: Emit, run: Optional[RunFn] = None) -> Dict[str, Any]:
    """Change the web replicas now (lasts until the next deploy, which uses options.cluster.replicas)."""
    cluster = get_cluster(root, name)
    if stack not in (cluster.get("deployments") or {}):
        raise ClusterError(f"{stack!r} is not deployed on cluster {name}")
    if not 0 <= int(replicas) <= 500:
        raise ClusterError("replicas must be 0..500")
    master = _target(root, cluster["master"])
    live = None
    if cluster["orchestrator"] == "nomad":
        code, text = (run or _default_run)(_ssh_argv(master, f"curl -fsS http://127.0.0.1:4646/v1/job/{stack}"), None)
        live = _json(text) if not code else None
        if not isinstance(live, dict) or not live.get("TaskGroups"):
            raise ClusterError(f"Nomad does not know job {stack}: {text.strip()[-300:]}")
    _script(master, scripts.scale_script(cluster["orchestrator"], stack, int(replicas), live), emit, run, label="scale")
    _update(root, name, lambda c: c["deployments"][stack].__setitem__("replicas", int(replicas)))
    emit(f"{stack}: {replicas} web replica(s)")
    return public(name, get_cluster(root, name), root)


# ----------------------------------------------------------------------------------------------- load balancer
def set_balancer(root: Path, name: str, server: str, emit: Emit, *, port: int = DEFAULT_BALANCER_PORT,
                 address: str = "", algorithm: Optional[str] = None, weights: Optional[Dict[str, Any]] = None,
                 run: Optional[RunFn] = None) -> Dict[str, Any]:
    """Make saved server ``server`` (not a member of any cluster) the load balancer of cluster ``name``.

    It runs OpenResty in Docker (container ``pskit-lb``, host network). Each deployment answers on ``port`` there
    (``options.cluster.balancer_port`` gives one deployment its own) and is spread over the cluster's servers by
    ``algorithm`` (``core/onprem_lb.py``; default least connections; ``weights`` per server for the weighted
    ones): every server; when the master does not serve requests (Nomad's default) it is only a backup.
    Running it again changes the port, address or algorithm; naming another server moves the load balancer there."""
    cluster = get_cluster(root, name)
    if isinstance(port, bool) or not 1 <= int(port) <= 65535:
        raise ClusterError("the load balancer port must be 1..65535")
    previous_lb: Dict[str, Any] = dict(cluster.get("balancer") or {})
    try:
        chosen = lb.normalize_algorithm(algorithm if algorithm is not None else previous_lb.get("algorithm"))
        chosen_weights = lb.weights_for([], weights if weights is not None else previous_lb.get("weights"))
    except ValueError as exc:
        raise ClusterError(str(exc)) from None
    strange = sorted(set(chosen_weights) - set(cluster.get("nodes") or {}))
    if strange:
        emit(f"  note: weights for {', '.join(strange)}, which are not in cluster {name} (yet)")
    clusters = load_clusters(root)
    for other, item in clusters.items():
        if server in (item.get("nodes") or {}):
            raise ClusterError(f"server {server!r} is in cluster {other!r}. The load balancer is a server outside the"
                               " cluster: save another one (pskit resources onprem servers add) and use it")
    _not_a_balancer(clusters, server, allow=name, root=root)
    target = _target(root, server)
    if run is None:
        check_ssh_login(target)
    addr = address or _bind_address(target) or _ip(str(target["host"]))
    try:
        lb.hostport(addr, int(port))
    except ValueError as exc:
        raise ClusterError(str(exc)) from None
    previous = previous_lb
    balancer = {"server": server, "address": addr, "port": int(port), "algorithm": chosen, "weights": chosen_weights,
                "set_at": _now()}
    emit(f"Setting up the load balancer (OpenResty in Docker, {lb.ALGORITHMS[chosen]['label'].lower()}) on {server}"
         f" ({addr}) ...")
    _apply_balancer(root, name, {**cluster, "balancer": balancer}, emit, run)
    _update(root, name, lambda c: c.__setitem__("balancer", balancer))
    if previous.get("server") and previous["server"] != server:
        emit(f"Removing the old load balancer from {previous['server']} ...")
        _teardown_balancer(root, str(previous["server"]), emit, run)
    emit(f"Load balancer of {name}: {_balancer_url(balancer, int(port))}. Deploys, removes, joins and leaves update it.")
    network.emit_rules(emit, f"load balancer {server} of cluster {name}",
                       network.cluster_balancer_rules(name, get_cluster(root, name)))
    return public(name, get_cluster(root, name), root)


def remove_balancer(root: Path, name: str, emit: Emit, *, run: Optional[RunFn] = None) -> Dict[str, Any]:
    """Stop OpenResty on the load balancer server and forget it (the deployments keep running on the cluster)."""
    cluster = get_cluster(root, name)
    balancer = cluster.get("balancer")
    if not isinstance(balancer, dict) or not balancer.get("server"):
        raise ClusterError(f"cluster {name} has no load balancer")
    emit(f"Stopping the load balancer on {balancer['server']} ...")
    _teardown_balancer(root, str(balancer["server"]), emit, run)
    _update(root, name, lambda c: c.pop("balancer", None))
    emit(f"Cluster {name} has no load balancer now. Users reach the servers on their own ports again.")
    return public(name, get_cluster(root, name), root)


def sync_balancer(root: Path, name: str, emit: Emit, *, run: Optional[RunFn] = None,
                  cluster: Optional[Dict[str, Any]] = None, strict: bool = False) -> bool:
    """Rewrite the load balancer's config from the cluster's servers and deployments (``cluster`` replaces the
    saved one, e.g. without a server that is leaving). No load balancer: nothing to do.

    A load balancer that cannot be reached only warns (the deploy or join itself went through) unless ``strict``."""
    current = cluster if cluster is not None else get_cluster(root, name)
    balancer = current.get("balancer")
    if not isinstance(balancer, dict) or not balancer.get("server"):
        if strict:
            raise ClusterError(f"cluster {name} has no load balancer (pskit cluster balancer set {name} SERVER)")
        return False
    emit(f"Updating the load balancer on {balancer['server']} ...")
    try:
        _apply_balancer(root, name, current, emit, run)
    except (ServiceError, ClusterError) as exc:
        if strict:
            raise
        emit(f"  WARNING: could not update the load balancer on {balancer['server']}: {exc}."
             f" Once it is reachable: pskit cluster balancer sync {name}")
        return False
    return True


def balancer_logs(root: Path, name: str, lines: int = 100, *, run: Optional[RunFn] = None) -> str:
    """The load balancer's last ``lines`` log lines: one per request with the server that answered
    (``upstream=``), and nginx errors."""
    balancer = get_cluster(root, name).get("balancer")
    if not isinstance(balancer, dict) or not balancer.get("server"):
        raise ClusterError(f"cluster {name} has no load balancer")
    target = _target(root, str(balancer["server"]))
    return _script(target, lb.logs_script("", max(1, min(int(lines), 10000))), lambda _l: None, run,
                   label="balancer-logs", show=False)


def _apply_balancer(root: Path, name: str, cluster: Dict[str, Any], emit: Emit, run: Optional[RunFn]) -> None:
    balancer = cluster["balancer"]
    target = _target(root, str(balancer["server"]))
    files, used, warnings = _balancer_files(cluster)
    for warning in warnings:
        emit(f"  WARNING: {warning}")
    checks = {str(listen): f"http://127.0.0.1:{listen}/__pskit/health" for listen in sorted(used)}
    try:
        script = lb.apply_script("", files, replace_routes=True, checks=checks)
    except ValueError as exc:
        raise ClusterError(str(exc)) from None
    out = _script(target, script, emit, run, label="balancer", show=False, check=False)
    if "PSKIT_LB_DONE=1" not in out:
        tail = [line for line in out.strip().splitlines() if line.strip()][-8:]
        raise ClusterError("the load balancer did not start: " + (" | ".join(tail) or "no output"))
    healthy = set(_values(out, "PSKIT_LB_OK"))
    primary, backup = _backends(cluster)
    algorithm = lb.normalize_algorithm(balancer.get("algorithm"))
    spread = f"{lb.ALGORITHMS[algorithm]['label'].lower()} over " + ", ".join(primary) + (
        f" (backup {', '.join(backup)})" if backup else "")
    for listen, stack in sorted(used.items()):
        url = _balancer_url(balancer, listen)
        if str(listen) in healthy:
            emit(f"  {url} -> {stack} on {spread}")
        else:
            emit(f"  WARNING: {url}/__pskit/health did not answer yet ({stack} on {spread}). The replicas may still"
                 f" be starting, or the load balancer cannot reach port"
                 f" {(cluster.get('deployments') or {}).get(stack, {}).get('port') or 8080} on them (firewall)."
                 f" Check: pskit cluster status {name}")
    if not used:
        emit("  OpenResty is ready; deployments appear on it when you deploy to the cluster")


def _balancer_files(cluster: Dict[str, Any]) -> Tuple[Dict[str, str], Dict[int, str], List[str]]:
    """The load balancer's files for every deployment, ``{listen port: stack}`` and warnings for those left out."""
    balancer = cluster["balancer"]
    algorithm = lb.normalize_algorithm(balancer.get("algorithm"))
    weights = dict(balancer.get("weights") or {})
    files = lb.base_files("", int(balancer.get("port") or DEFAULT_BALANCER_PORT), algorithm)
    used: Dict[int, str] = {}
    warnings: List[str] = []
    for stack, dep in sorted((cluster.get("deployments") or {}).items()):
        listen = _listen_port(balancer, dep)
        if listen in used:
            warnings.append(f"{stack} is not on the load balancer: port {listen} there already serves {used[listen]}."
                            " Give it its own with provider.options.cluster.balancer_port and deploy again")
            continue
        found = balancers.cluster_backends(cluster, int(dep.get("port") or 8080))
        if not found:
            warnings.append(f"{stack} is not on the load balancer: the cluster has no server with an address")
            continue
        try:
            backends = [lb.backend(b["address"], b["port"], weight=int(weights.get(b["server"], 1)),
                                   backup=bool(b.get("backup")), server=b["server"],
                                   per_request=bool(b.get("per_request"))) for b in found]
            files[f"conf.d/r-port-{listen}.conf"] = lb.port_route_conf(f"port-{listen}", listen, algorithm, backends,
                                                                      comment=stack)
        except ValueError as exc:
            raise ClusterError(str(exc)) from None
        used[listen] = stack
    return files, used, warnings


def _backends(cluster: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    """``(primary, backup)`` servers behind the load balancer. Swarm and k3s: every server (each one's port
    reaches every web replica). Nomad: the servers with a web replica, plus the master's main replica.

    When the master does not serve requests (:func:`master_serves`), it is only the backup, used while every
    other server is down; a cluster of one server still sends it everything."""
    nodes = cluster.get("nodes") or {}
    master = str(cluster.get("master") or "")
    servers = sorted(s for s, n in nodes.items() if (n or {}).get("address"))
    workers = [s for s in servers if s != master]
    if workers and master in servers and not master_serves(cluster):
        return workers, [master]
    return servers, []


def _listen_port(balancer: Dict[str, Any], dep: Dict[str, Any]) -> int:
    return int(dep.get("balancer_port") or balancer.get("port") or DEFAULT_BALANCER_PORT)


def _balancer_url(balancer: Dict[str, Any], port: int) -> str:
    host = str(balancer.get("address") or "")
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    return f"http://{host}" if int(port) == 80 else f"http://{host}:{int(port)}"


def _check_listen_port(root: Path, name: str, stack: str, balancer_port: Optional[int]) -> None:
    """Before a deploy: two deployments cannot share a port on the load balancer."""
    try:
        cluster = get_cluster(root, name)
    except ClusterError:
        return
    balancer = cluster.get("balancer")
    if not isinstance(balancer, dict) or not balancer.get("server"):
        return
    deployments = cluster.get("deployments") or {}
    taken = {_listen_port(balancer, dep): other for other, dep in deployments.items() if other != stack}
    listen = _listen_port(balancer, {"balancer_port": balancer_port})
    if listen in taken:
        free = next(p for p in range(8081, 65536) if p not in taken)
        raise ClusterError(f"port {listen} on the load balancer {balancer['server']} already serves {taken[listen]}."
                           f" Give this deployment its own port: provider.options.cluster.balancer_port: {free}")


def _not_a_balancer(clusters: Dict[str, Dict[str, Any]], server: str, allow: str = "", root: Optional[Path] = None
                    ) -> None:
    for other, item in clusters.items():
        if other != allow and ((item.get("balancer") or {}).get("server")) == server:
            raise ClusterError(f"server {server!r} is the load balancer of cluster {other!r}"
                               f" (pskit cluster balancer remove {other} first)")
    for name, item in balancers.load_balancers(root).items() if root is not None else []:
        if item.get("server") == server:
            raise ClusterError(f"server {server!r} runs load balancer {name!r}. Use another server, or attach {name}"
                               f" to the cluster instead: pskit lb attach {name} --cluster CLUSTER")


def _teardown_balancer(root: Path, server: str, emit: Emit, run: Optional[RunFn]) -> None:
    try:
        _script(_target(root, server), lb.remove_script(""), emit, run, label="balancer-remove",
                show=False, check=False)
    except (ServiceError, ClusterError) as exc:
        emit(f"  {server} did not answer ({exc}). Remove it there later: docker rm -f {lb.container_name()}")


def _balancer_view(root: Path, cluster: Dict[str, Any], run: Optional[RunFn]) -> Optional[Dict[str, Any]]:
    """For status: the load balancer's server use, whether nginx runs, and each deployment's URL."""
    shown = _balancer_public(cluster)
    if shown is None:
        return None
    try:
        target = _target(root, str(shown["server"]))
    except ClusterError as exc:
        return {**shown, "reachable": False, "error": str(exc), "state": "unknown", "running": False}
    metrics = node_metrics(target, run)
    state = "unknown"
    if metrics.get("reachable"):
        code, text = (run or _default_run)(_ssh_argv(target, lb.state_command()), None)
        lines = text.strip().splitlines()
        state = lines[-1].strip() if not code and lines else "unknown"
    return {**shown, **metrics, "state": state, "running": state == "running"}


# ----------------------------------------------------------------------------------------------- status
def node_metrics(target: Dict[str, Any], run: Optional[RunFn] = None) -> Dict[str, Any]:
    """CPU (busy over one second), memory and disk use in percent, load and CPU count of one server."""
    code, text = (run or _default_run)(_ssh_argv(target, scripts.metrics_command()), None)
    values: Dict[str, str] = {}
    for line in text.splitlines():
        key, sep, value = line.partition("=")
        if sep and re.match(r"^[a-z_]+$", key):
            values[key] = value.strip()
    if code or "cpu_b" not in values:
        return {"reachable": False, "error": (text.strip().splitlines() or [f"ssh exited with {code}"])[-1][-300:]}
    out: Dict[str, Any] = {"reachable": True, "hostname": values.get("hostname", "")}
    try:
        a = [int(x) for x in values["cpu_a"].split()[1:]]
        b = [int(x) for x in values["cpu_b"].split()[1:]]
        total = sum(b) - sum(a)
        idle = (b[3] + (b[4] if len(b) > 4 else 0)) - (a[3] + (a[4] if len(a) > 4 else 0))
        out["cpu"] = round(100.0 * (total - idle) / total, 1) if total > 0 else 0.0
    except (ValueError, IndexError):
        out["cpu"] = None
    try:
        mem_total = int(values["mem_total_kb"])
        out["memory"] = round(100.0 * (mem_total - int(values["mem_avail_kb"])) / mem_total, 1)
        out["memory_mb"] = mem_total // 1024
    except (KeyError, ValueError, ZeroDivisionError):
        out["memory"] = None
    try:
        out["disk"] = round(100.0 * int(values["disk_used_kb"]) / int(values["disk_total_kb"]), 1)
        out["disk_gb"] = round(int(values["disk_total_kb"]) / 1024 / 1024, 1)
    except (KeyError, ValueError, ZeroDivisionError):
        out["disk"] = None
    out["cpus"] = int(values["cpus"]) if values.get("cpus", "").isdigit() else None
    out["load"] = values.get("load", "")
    return out


def place(root: Path, name: str, server: str = "", *, run: Optional[RunFn] = None,
          measure: bool = True) -> Dict[str, Any]:
    """The cluster server a resource (Redis, Postgres, ...) runs on: ``server`` when given (it must be in the
    cluster), else the reachable server with the most free memory under every capacity limit. Returns
    ``{server, address, metrics}``; ``address`` is the server's cluster address, which every replica reaches.

    ``measure=False`` only checks the names (the master stands in): the studio's fast check before the job."""
    cluster = get_cluster(root, name)
    nodes = dict(cluster.get("nodes") or {})
    if server:
        if server not in nodes:
            raise ClusterError(f"{server!r} is not in cluster {name} (servers: {', '.join(sorted(nodes))})")
        return {"server": server, "address": str(nodes[server].get("address") or ""), "metrics": None}
    if not measure:
        master = str(cluster["master"])
        return {"server": master, "address": str((nodes.get(master) or {}).get("address") or ""), "metrics": None}
    capacity = {**DEFAULT_CAPACITY, **(cluster.get("capacity") or {})}
    targets = {}
    for member in nodes:
        try:
            targets[member] = _target(root, member)
        except ClusterError:
            continue
    with ThreadPoolExecutor(max_workers=min(16, len(targets) + 1)) as pool:
        metrics = dict(zip(targets, pool.map(lambda t: node_metrics(t, run), targets.values())))

    def free(member: str) -> Tuple[float, float, float]:
        m = metrics[member]
        return (float(m.get("memory") or 0), float(m.get("cpu") or 0), float(m.get("disk") or 0))

    usable = [s for s, m in metrics.items() if m.get("reachable")
              and not any(isinstance(m.get(k), (int, float)) and m[k] >= capacity[k] for k in capacity)]
    if not usable:
        raise ClusterError(f"every server of cluster {name} is unreachable or over a capacity limit. Join a server "
                           f"(pskit cluster join {name} SERVER) or pick one of its servers")
    best = min(sorted(usable), key=free)
    return {"server": best, "address": str(nodes[best].get("address") or ""), "metrics": metrics[best]}


def requests_feed(root: Path, name: str, stack: str = "", since: int = 0, limit: int = 200,
                  control: Any = None) -> Dict[str, Any]:
    """The live request view of a deployment on cluster ``name``: recent requests (oldest first) from the main
    replica, each with the saved server and replica that handled it, plus per-server counts of this page.

    Poll with ``since=next``. ``stack`` defaults to the only (or first) deployment."""
    from .onprem_control import HostControl, deployed_host

    cluster = get_cluster(root, name)
    deployments = dict(cluster.get("deployments") or {})
    if not deployments:
        raise ClusterError(f"nothing is deployed on cluster {name} yet (pskit deploy --cluster {name})")
    stack = stack or sorted(deployments)[0]
    dep = deployments.get(stack)
    if dep is None:
        raise ClusterError(f"{stack!r} is not deployed on cluster {name} (deployed: {', '.join(sorted(deployments))})")
    if control is None:
        spec = (deployed_host(root, str(dep.get("stage") or "")) or {}).get("spec") or {}
        ssh = (spec.get("deploy") or {}).get("ssh") or None
        control = HostControl(str(dep.get("endpoint") or spec.get("endpoint")),
                              token=str(spec.get("admin_token") or ""), ssh=ssh,
                              remote_port=int(dep.get("port") or spec.get("port") or 8080), timeout=10)
    page = dict(control.request("GET", "/__pskit/requests", query={"since": since, "limit": limit}) or {})
    nodes = dict(cluster.get("nodes") or {})
    by_node = {str(n.get("node")): server for server, n in nodes.items() if n.get("node")}
    counts: Dict[str, int] = {}
    http_counts: Dict[str, int] = {}
    for item in page.get("items") or []:
        server = by_node.get(str(item.get("node") or ""))
        if not server and item.get("replica") == "main":
            server = str(cluster["master"])  # the main replica always runs on the master
        item["server"] = server or item.get("node") or ""
        counts[item["server"]] = counts.get(item["server"], 0) + 1
        if item.get("method"):
            http_counts[item["server"]] = http_counts.get(item["server"], 0) + 1
    return {"stack": stack, "stacks": sorted(deployments), "items": page.get("items") or [],
            "next": page.get("next", since), "servers": counts,
            "balance": _balance(cluster, dep, http_counts)}


def _balance(cluster: Dict[str, Any], dep: Dict[str, Any], http_counts: Dict[str, int]) -> Dict[str, Any]:
    """Every server of this deployment: its URL, what answers there, and this page's HTTP counts.

    Swarm and k3s spread HTTP from any server's port. Nomad serves the main replica on the master and
    one web replica on each other server. Servers with no requests in ``http_counts`` are still listed.
    """
    orch = str(cluster.get("orchestrator") or "")
    spreads = orch in ("swarm", "kubernetes")
    port = int((dep or {}).get("port") or 8080)
    master = str(cluster.get("master") or "")
    rows = []
    for server, node in sorted((cluster.get("nodes") or {}).items()):
        address = str((node or {}).get("address") or "")
        is_master = server == master
        rows.append({
            "server": server,
            "role": "master" if is_master else "worker",
            "address": address,
            "url": f"http://{address}:{port}" if address else "",
            "serves": "web" if spreads or not is_master else "main",
            "requests": int(http_counts.get(server, 0)),
        })
    total = sum(row["requests"] for row in rows)
    for row in rows:
        row["share"] = round(100.0 * row["requests"] / total, 1) if total else 0.0
    balancer = cluster.get("balancer") if isinstance(cluster.get("balancer"), dict) else None
    url = ""
    if balancer:
        url = _balancer_url(balancer, _listen_port(balancer, dep or {}))
        primary, backup = _backends(cluster)
        for row in rows:
            row["balancer"] = "primary" if row["server"] in primary else "backup" if row["server"] in backup else ""
        note = f"The load balancer {url} spreads HTTP across " + ", ".join(primary) + (
            f" ({', '.join(backup)} only while those are down)." if backup else ".")
    elif spreads:
        note = "Any server's port spreads HTTP across the web replicas."
    else:
        note = ("The master's URL is the main replica. Each other server's URL is one web replica. "
                "A load balancer is optional, and only when you want one URL for all of them.")
    mode = "balancer" if balancer else "mesh" if spreads else "per-server"
    return {"orchestrator": orch, "mode": mode, "spreads": spreads or bool(balancer), "note": note, "port": port,
            "servers": rows, "balancer_url": url}


def _ts_ms(ts: str) -> int:
    text = str(ts or "").strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return int(datetime.fromisoformat(text).timestamp() * 1000)
    except ValueError:
        return 0


def _log_seq(entry: Dict[str, Any], local_seq: int) -> int:
    """A seq that stays the same for the same line, ordered by time, across replicas."""
    replica = str((entry.get("fields") or {}).get("replica") or "")
    salt = zlib.crc32(replica.encode("utf-8")) % 10
    return _ts_ms(str(entry.get("ts") or "")) * 10000 + salt * 1000 + (int(local_seq) % 1000)


def logs_feed(
    root: Path,
    name: str,
    servers: List[str],
    *,
    master: str,
    port: int,
    token: str = "",
    since: int = 0,
    limit: int = 200,
    level: Optional[str] = None,
    function: Optional[str] = None,
    q: Optional[str] = None,
    source: Optional[str] = None,
    read: Optional[Callable[[str], Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Nomad live logs: each server's own buffer, merged.

    ``GET /__pskit/logs`` on a web replica is forwarded to the main replica, so a line stays invisible
    until that replica can reach the master. This reads ``/__pskit/logs/local`` on each server (SSH to
    that server's loopback). A copy the main replica already ingested is kept only when the server it
    came from did not answer. ``read(server)`` replaces the SSH call in tests.
    """
    cluster = get_cluster(root, name)
    nodes = cluster.get("nodes") or {}
    wanted = [s for s in servers if s in nodes] or list(nodes)
    if not wanted:
        raise ClusterError(f"cluster {name} has no servers")
    window = min(2000, max(int(limit or 200), 400))

    def _default_read(server: str) -> Dict[str, Any]:
        from .onprem_control import HostControl

        target = _target(root, server)
        control = HostControl(
            f"http://127.0.0.1:{int(port)}", token=token, ssh=ssh_options(target), remote_port=int(port),
            server=server, force_ssh=True, timeout=8,
        )
        page = control.logs(since=0, limit=window, level=level, function=function, q=q, source=source, local=True)
        return {"entries": list(page.get("entries") or [])}

    fetch = read or _default_read

    def _one(server: str) -> Tuple[str, Dict[str, Any]]:
        try:
            return server, dict(fetch(server) or {})
        except (OSError, ValueError) as exc:
            return server, {"error": str(exc), "entries": []}

    pages: Dict[str, Dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=min(8, len(wanted))) as pool:
        for server, page in pool.map(_one, wanted):
            pages[server] = page

    errors: List[str] = []
    answered = False
    read_replicas = set()
    shipped: List[Tuple[str, Dict[str, Any]]] = []
    merged: List[Dict[str, Any]] = []
    for server in wanted:
        page = pages.get(server) or {}
        if page.get("error"):
            errors.append(f"{server}: {page['error']}")
            continue
        answered = True
        is_main = server == master
        for raw in page.get("entries") or []:
            if not isinstance(raw, dict):
                continue
            entry = dict(raw)
            fields = dict(entry.get("fields") or {})
            replica = str(fields.get("replica") or "")
            local_seq = int(entry.get("seq") or 0)
            if is_main and replica and replica != "main":
                shipped.append((replica, entry))
                continue
            fields["server"] = server
            entry["fields"] = fields
            entry["seq"] = _log_seq(entry, local_seq)
            merged.append(entry)
            if not is_main and replica:
                read_replicas.add(replica)
    if not answered:
        detail = "; ".join(errors) or "no answer"
        raise ClusterError(
            f"no replica on cluster {name} answered on port {port} ({detail}). "
            "Redeploy so each server listens on that port."
        )
    for replica, raw in shipped:
        if replica in read_replicas:
            continue
        entry = dict(raw)
        entry["fields"] = dict(entry.get("fields") or {})
        entry["seq"] = _log_seq(entry, int(entry.get("seq") or 0))
        merged.append(entry)
    merged.sort(key=lambda item: int(item.get("seq") or 0))
    unique: List[Dict[str, Any]] = []
    seen = set()
    for entry in merged:
        seq = int(entry["seq"])
        if seq in seen:
            continue
        seen.add(seq)
        unique.append(entry)
    last = int(unique[-1]["seq"]) if unique else 0
    since_n = max(0, int(since or 0))
    size = max(1, int(limit or 200))
    if since_n == 0:
        picked = unique[-size:]
    else:
        picked = [entry for entry in unique if int(entry["seq"]) > since_n][:size]
    oldest = int(unique[0]["seq"]) if unique else last + 1
    return {"entries": picked, "next": last, "oldest": oldest, "partial": errors}


def resources_of(root: Path, name: str) -> List[Dict[str, Any]]:
    """The on-prem services (Redis, Postgres, ...) placed on cluster ``name``, with the server each runs on."""
    from .onprem_services import load_state

    out = []
    for key, entry in sorted(load_state(root)["services"].items()):
        target = entry.get("target") if isinstance(entry, dict) else None
        if isinstance(target, dict) and target.get("cluster") == name:
            out.append({"key": key, "service": entry.get("service"), "kind": entry.get("kind"),
                        "server": target.get("server"), "address": entry.get("address"), "port": entry.get("port")})
    return out


def _untag_resources(root: Path, name: str, server: Optional[str], emit: Emit) -> None:
    """Resources on a server that leaves (or on a forgotten cluster) keep running there as one-server resources."""
    from .onprem_services import load_state, save_state

    state = load_state(root)
    moved = []
    for key, entry in state["services"].items():
        target = entry.get("target") if isinstance(entry, dict) else None
        if isinstance(target, dict) and target.get("cluster") == name and server in (None, target.get("server")):
            target.pop("cluster", None)
            moved.append(f"{key} ({entry.get('service')}) on {target.get('server')}")
    if moved:
        save_state(root, state)
        emit("These resources keep running on their server, now outside the cluster: " + ", ".join(moved))


def _sections(text: str) -> Dict[str, str]:
    found: Dict[str, List[str]] = {}
    current = ""
    for line in text.splitlines():
        if line.startswith(scripts.MARK):
            current = line[len(scripts.MARK):].strip()
            found[current] = []
        elif current:
            found[current].append(line)
    return {k: "\n".join(v) for k, v in found.items()}


def _json_lines(text: str) -> List[Dict[str, Any]]:
    out = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    return out


def _json(text: str) -> Any:
    try:
        return json.loads(text.strip() or "null")
    except ValueError:
        return None


def parse_orchestrator(orchestrator: str, text: str) -> Dict[str, Any]:
    """The master's status script output -> ``{nodes: {name: {...}}, workloads: [...], pending: [...]}``."""
    parts = _sections(text)
    nodes: Dict[str, Dict[str, Any]] = {}
    workloads: List[Dict[str, Any]] = []
    pending: List[str] = []
    if orchestrator == "swarm":
        for item in _json_lines(parts.get("nodes", "")):
            nodes[str(item.get("Hostname"))] = {
                "ready": item.get("Status") == "Ready", "state": item.get("Status"),
                "availability": item.get("Availability"), "manager": bool(item.get("ManagerStatus")),
            }
        for item in _json_lines(parts.get("services", "")):
            ran, _, wanted = str(item.get("Replicas") or "0/0").partition(" ")[0].partition("/")
            workloads.append({"name": item.get("Name"), "running": _int(ran), "desired": _int(wanted)})
        for item in _json_lines(parts.get("pending", "")):
            pending.append(f"{item.get('Name')}: {item.get('Error') or item.get('CurrentState')}")
    elif orchestrator == "kubernetes":
        for item in (_json(parts.get("nodes", "")) or {}).get("items", []):
            conditions = {c.get("type"): c.get("status") for c in item.get("status", {}).get("conditions", [])}
            name = item.get("metadata", {}).get("name")
            labels = item.get("metadata", {}).get("labels", {})
            nodes[str(name)] = {
                "ready": conditions.get("Ready") == "True", "state": "Ready" if conditions.get("Ready") == "True"
                else "NotReady", "availability": "Drain" if item.get("spec", {}).get("unschedulable") else "Active",
                "manager": "node-role.kubernetes.io/control-plane" in labels,
            }
        for item in (_json(parts.get("services", "")) or {}).get("items", []):
            status = item.get("status", {})
            workloads.append({"name": item.get("metadata", {}).get("name"),
                              "running": int(status.get("readyReplicas") or 0),
                              "desired": int(item.get("spec", {}).get("replicas") or 0)})
        for item in (_json(parts.get("pending", "")) or {}).get("items", []):
            reasons = [c.get("message") for c in item.get("status", {}).get("conditions", []) if c.get("message")]
            pending.append(f"{item.get('metadata', {}).get('name')}: {'; '.join(reasons) or 'Pending'}")
    else:
        for item in _json(parts.get("nodes", "")) or []:
            nodes[str(item.get("Name"))] = {
                "ready": item.get("Status") == "ready", "state": item.get("Status"),
                "availability": "Drain" if item.get("Drain") or item.get("SchedulingEligibility") == "ineligible"
                else "Active", "manager": False, "id": item.get("ID"),
            }
        for job in _json(parts.get("services", "")) or []:
            summary = (job.get("JobSummary") or {}).get("Summary") or {}
            for group, counts in sorted(summary.items()):
                running = int(counts.get("Running") or 0)
                queued = int(counts.get("Queued") or 0)
                workloads.append({"name": f"{job.get('ID')}/{group}", "running": running,
                                  "desired": running + queued + int(counts.get("Starting") or 0)})
                if queued:
                    pending.append(f"{job.get('ID')}/{group}: {queued} allocation(s) cannot be placed")
    return {"nodes": nodes, "workloads": workloads, "pending": pending}


def _int(text: Any) -> int:
    try:
        return int(str(text).strip())
    except ValueError:
        return 0


def status(root: Path, name: str, run: Optional[RunFn] = None) -> Dict[str, Any]:
    """Live view: every server's use (in parallel over SSH), the orchestrator's nodes and workloads, and whether
    the cluster is full (every reachable, schedulable server over a limit, or replicas that cannot be placed)."""
    cluster = get_cluster(root, name)
    orch = cluster["orchestrator"]
    capacity = {**DEFAULT_CAPACITY, **(cluster.get("capacity") or {})}
    servers = dict(cluster.get("nodes") or {})
    targets = {}
    errors: Dict[str, str] = {}
    for server in servers:
        try:
            targets[server] = _target(root, server)
        except ClusterError as exc:
            errors[server] = str(exc)
    with ThreadPoolExecutor(max_workers=min(16, len(targets) + 2)) as pool:
        orch_future = pool.submit(_orchestrator_view, targets.get(cluster["master"]), orch, run)
        balancer_future = pool.submit(_balancer_view, root, cluster, run)
        futures = {s: pool.submit(node_metrics, t, run) for s, t in targets.items()}
        metrics = {s: f.result() for s, f in futures.items()}
        view = orch_future.result()
        balancer = balancer_future.result()
    resources = resources_of(root, name)
    rows = []
    for server, node in sorted(servers.items(), key=lambda kv: (kv[1].get("role") != "master", kv[0])):
        m = metrics.get(server) or {"reachable": False, "error": errors.get(server, "no saved server")}
        o = (view.get("nodes") or {}).get(str(node.get("node"))) or {}
        over = [k for k in ("cpu", "memory", "disk") if isinstance(m.get(k), (int, float)) and m[k] >= capacity[k]]
        rows.append({
            "server": server, "role": node.get("role"), "node": node.get("node"), "address": node.get("address"),
            **m, "ready": bool(o.get("ready")), "state": o.get("state") or ("unknown" if view.get("error") else "missing"),
            "availability": o.get("availability") or "", "over": over, "full": bool(over),
            "resources": [r["key"] for r in resources if r["server"] == server],
        })
    usable = [r for r in rows if r.get("reachable") and r["ready"] and r["availability"] in ("Active", "")]
    pending = list(view.get("pending") or [])
    full = bool(usable) and all(r["full"] for r in usable)
    reasons = []
    if full:
        reasons.append(f"all {len(usable)} server(s) are over a capacity limit")
    if not usable and rows:
        reasons.append("no server is ready")
    if pending:
        reasons.append(f"{len(pending)} replica(s) cannot be placed")
    if view.get("error"):
        reasons.append(f"the master did not answer: {view['error']}")
    return {
        "name": name, "orchestrator": orch, "capacity": capacity, "nodes": rows, "balancer": balancer,
        "workloads": view.get("workloads") or [], "resources": resources, "pending": pending,
        "full": full or bool(pending) or not usable,
        "reasons": reasons, "orchestrator_error": view.get("error"), "checked_at": _now(),
    }


def _orchestrator_view(master: Optional[Dict[str, Any]], orch: str, run: Optional[RunFn]) -> Dict[str, Any]:
    if master is None:
        return {"error": "the master is not a saved server"}
    try:
        out = _script(master, scripts.status_script(orch), lambda _line: None, run, label="status", show=False)
    except ServiceError as exc:
        return {"error": str(exc)}
    return parse_orchestrator(orch, out)


# ----------------------------------------------------------------------------------------------- alerts
def check(root: Path, name: str, *, alert: bool = True, run: Optional[RunFn] = None,
          send: Optional[Callable[..., Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Status, and when the cluster is full the alert (at most once per cooldown)."""
    current = status(root, name, run=run)
    if current["full"] and alert:
        cluster = get_cluster(root, name)
        settings = {**DEFAULT_ALERT, **(cluster.get("alert") or {})}
        last = float(cluster.get("last_alert_ts") or 0)
        if time.time() - last >= 60 * int(settings["cooldown_minutes"]):
            current["alert"] = (send or send_alert)(root, name, current)
        else:
            current["alert"] = {"skipped": "cooldown", "next_after_minutes": round(
                (last + 60 * int(settings["cooldown_minutes"]) - time.time()) / 60, 1)}
    return current


def alert_event(name: str, current: Dict[str, Any], *, test: bool = False) -> Dict[str, Any]:
    """``event.data`` of the alert function (also the webhook's JSON body)."""
    nodes = [{k: n.get(k) for k in ("server", "node", "role", "cpu", "memory", "disk", "reachable", "state", "over")}
             for n in current.get("nodes") or []]
    reasons = current.get("reasons") or (["test alert"] if test else [])
    message = (f"pskit cluster {name} is full: {'; '.join(reasons)}. Add a server: pskit cluster join {name} SERVER"
               if not test else f"Test alert from pskit cluster {name}")
    return {
        "type": "pskit.cluster.capacity", "test": test, "cluster": name, "orchestrator": current.get("orchestrator"),
        "full": bool(current.get("full")), "reasons": reasons, "message": message, "subject": (
            f"[pskit] cluster {name} needs another server" if not test else f"[pskit] test alert for cluster {name}"),
        "capacity": current.get("capacity"), "nodes": nodes, "workloads": current.get("workloads") or [],
        "pending": current.get("pending") or [], "checked_at": current.get("checked_at") or _now(),
    }


def send_alert(root: Path, name: str, current: Dict[str, Any], *, test: bool = False) -> Dict[str, Any]:
    """Call the alert function (through the deployed host) and / or POST the webhook. Recorded in the history."""
    cluster = get_cluster(root, name)
    settings = {**DEFAULT_ALERT, **(cluster.get("alert") or {})}
    event = alert_event(name, current, test=test)
    sent: List[str] = []
    failures: List[str] = []
    if settings["function"]:
        try:
            _invoke_alert(root, cluster, settings, event)
            sent.append(f"function {settings['function']}")
        except Exception as exc:  # noqa: BLE001 - reported in the result and history
            failures.append(f"function {settings['function']}: {exc}")
    if settings["webhook"]:
        try:
            _post_webhook(str(settings["webhook"]), event)
            sent.append("webhook")
        except Exception as exc:  # noqa: BLE001
            failures.append(f"webhook: {exc}")
    if not settings["function"] and not settings["webhook"]:
        failures.append("no alert function or webhook is set (cluster settings)")
    entry = {"at": _now(), "test": test, "message": event["message"], "sent": sent, "errors": failures}

    def record(c: Dict[str, Any]) -> None:
        c["alerts"] = (list(c.get("alerts") or []) + [entry])[-_MAX_ALERTS:]
        if sent and not test:
            c["last_alert_ts"] = time.time()

    _update(root, name, record)
    return entry


def _invoke_alert(root: Path, cluster: Dict[str, Any], settings: Dict[str, Any], event: Dict[str, Any]) -> None:
    """``POST /__pskit/invoke/<function>`` on the host of the stage that has the function (any deployment)."""
    from urllib.parse import quote

    from .onprem_control import HostControl, deployed_host

    stage = str(settings.get("stage") or "")
    deployed = deployed_host(root, stage) if stage else None
    spec = (deployed or {}).get("spec") or {}
    if not spec:
        for dep in (cluster.get("deployments") or {}).values():
            if not stage or dep.get("stage") == stage:
                spec = (deployed_host(root, str(dep.get("stage"))) or {}).get("spec") or {}
                if spec:
                    break
    if not spec:
        raise ClusterError("no deployed on-prem stage to run it on (deploy the project, or set alert.stage)")
    ssh = (spec.get("deploy") or {}).get("ssh") or None
    control = HostControl(str(spec.get("endpoint")), token=str(spec.get("admin_token") or ""), ssh=ssh,
                          remote_port=int(spec.get("port") or 8080), timeout=60)
    control.request("POST", "/__pskit/invoke/" + quote(str(settings["function"]), safe=""), event)


def _post_webhook(url: str, event: Dict[str, Any]) -> None:
    from urllib.request import Request, urlopen

    # Slack / Teams / Google Chat incoming webhooks show `text`; other receivers get the whole event.
    body = json.dumps({"text": event["message"], **event}, default=str).encode("utf-8")
    req = Request(url, data=body, method="POST", headers={"content-type": "application/json"})  # noqa: S310
    with urlopen(req, timeout=20) as resp:  # noqa: S310 - the user's own webhook URL
        resp.read()


class Watcher:
    """Checks clusters on their interval while the studio runs (``pskit cluster watch`` does it from a shell)."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.last: Dict[str, Dict[str, Any]] = {}
        self._due: Dict[str, float] = {}

    def start(self) -> None:
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._loop, name="pskit-cluster-watch", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.wait(5):
            for name, item in load_clusters(self.root).items():
                watch = item.get("watch") or {}
                if not watch.get("enabled") or time.time() < self._due.get(name, 0):
                    continue
                self._due[name] = time.time() + max(15, int(watch.get("interval_seconds") or 60))
                try:
                    self.last[name] = check(self.root, name)
                except Exception as exc:  # noqa: BLE001 - keep watching the others
                    self.last[name] = {"error": str(exc), "checked_at": _now()}
