"""Named load balancers: one saved server running OpenResty that many projects and clusters share by path.

``pskit lb create edge --server lb1 --algorithm least_time`` makes saved server ``lb1`` a load balancer named
``edge``. Projects then appear on it by path: ``http://<lb1>/xyz/``, ``http://<lb1>/abc/``, ...

* a project names it in ``pskit.yml`` (``provider.options.balancer: edge`` or ``{name: edge, path: xyz,
  algorithm: sticky_round_robin, weights: {app1: 3}}``); every deploy updates its route, ``pskit remove`` drops it.
* a cluster attaches it (``pskit lb attach edge --cluster prod``): every deployment on that cluster gets a route
  at ``/<service>`` (a project's own ``balancer`` setting wins), kept up to date on deploy, remove, join and leave.

The routes live **on the load balancer server** (``pskit-cluster/lb-<name>/routes/*.json`` beside the nginx files),
not in one project, so projects in other folders or on other machines share it without overwriting each other:
each change rewrites only its own route files, under a lock, after ``nginx -t``. A route belongs to one deployment
(its owner, ``pskit-<service>-<stage>``); another deployment cannot take its path.

Load balancers this project uses are listed in ``.pskit/onprem-balancers.json`` (server, address, port, default
algorithm, weights, attached clusters). Algorithms and the config itself: ``core/onprem_lb.py``.
"""

from __future__ import annotations

import json
import re
import socket
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from . import onprem_lb as lb
from . import onprem_network as network

BALANCERS_FILE = Path(".pskit") / "onprem-balancers.json"
DEFAULT_PORT = 80
_NAME = re.compile(r"^[a-z][a-z0-9-]{0,30}$")
Emit = Callable[[str], None]
RunFn = Callable[[List[str], Optional[Path]], Tuple[int, str]]
_LOCK = threading.RLock()


class BalancerError(ValueError):
    pass


# ----------------------------------------------------------------------------------------------- store
def _path(root: Path) -> Path:
    return Path(root) / BALANCERS_FILE


def load_balancers(root: Path) -> Dict[str, Dict[str, Any]]:
    try:
        data = json.loads(_path(root).read_text("utf-8"))
    except (OSError, ValueError):
        return {}
    items = data.get("balancers") if isinstance(data, dict) else None
    return {k: v for k, v in (items or {}).items() if isinstance(v, dict)}


def _save(root: Path, items: Dict[str, Dict[str, Any]]) -> None:
    path = _path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps({"balancers": items}, indent=2, sort_keys=True) + "\n").encode("utf-8"))


def _update(root: Path, name: str, change: Callable[[Dict[str, Any]], None]) -> Dict[str, Any]:
    with _LOCK:
        items = load_balancers(root)
        if name not in items:
            raise BalancerError(_unknown(root, name))
        change(items[name])
        _save(root, items)
        return items[name]


def _unknown(root: Path, name: str) -> str:
    known = ", ".join(sorted(load_balancers(root))) or "none yet"
    return (f"no load balancer {name!r} (load balancers: {known}). Create one: pskit lb create NAME --server SERVER,"
            " or add one another project created: pskit lb create NAME --server SERVER (it is found on the server)")


def get_balancer(root: Path, name: str) -> Dict[str, Any]:
    item = load_balancers(root).get(str(name))
    if item is None:
        raise BalancerError(_unknown(root, name))
    return item


def base_url(item: Dict[str, Any]) -> str:
    host = str(item.get("address") or "")
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    port = int(item.get("port") or DEFAULT_PORT)
    return f"http://{host}" if port == 80 else f"http://{host}:{port}"


def route_url(item: Dict[str, Any], path: str) -> str:
    return f"{base_url(item)}/{lb.normalize_path(path)}/"


def public(name: str, item: Dict[str, Any]) -> Dict[str, Any]:
    algorithm = lb.normalize_algorithm(item.get("algorithm"))
    info = lb.ALGORITHMS[algorithm]
    return {
        "name": name, "server": item.get("server"), "address": item.get("address"),
        "port": int(item.get("port") or DEFAULT_PORT), "algorithm": algorithm, "algorithm_label": info["label"],
        "kind": info["kind"], "url": base_url(item), "weights": dict(item.get("weights") or {}),
        "clusters": sorted(item.get("clusters") or []), "created_at": item.get("created_at"),
    }


def list_balancers(root: Path) -> List[Dict[str, Any]]:
    return [public(name, item) for name, item in sorted(load_balancers(root).items())]


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _cluster():  # noqa: ANN202 - the module (imported late: it imports this one)
    from . import onprem_cluster

    return onprem_cluster


def _target(root: Path, server: str) -> Dict[str, Any]:
    try:
        return _cluster()._target(root, server)
    except ValueError as exc:
        raise BalancerError(str(exc)) from None


def _script(target: Dict[str, Any], script: str, emit: Emit, run: Optional[RunFn], label: str) -> str:
    from .onprem_services import ServiceError

    try:
        return _cluster()._script(target, script, emit, run, label=label, show=False, check=False)
    except ServiceError as exc:
        raise BalancerError(str(exc)) from None


# ----------------------------------------------------------------------------------------------- read the server
def read_server(root: Path, name: str, *, run: Optional[RunFn] = None,
                item: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """What is on the load balancer server: ``{settings, routes: {key: route}, state}`` (state is the container's:
    running, exited, ... or missing). Raises when the server does not answer."""
    item = item or get_balancer(root, name)
    out = _script(_target(root, str(item["server"])), lb.read_script(name), lambda _l: None, run, f"lb-{name}-read")
    sections: Dict[str, List[str]] = {}
    current = ""
    for line in out.splitlines():
        if line.startswith(lb.SECTION):
            current = line[len(lb.SECTION):].strip()
            sections[current] = []
        elif current:
            sections[current].append(line)
    if "routes" not in sections:
        raise BalancerError(f"{item['server']} did not list the load balancer: {out.strip()[-300:] or 'no output'}")
    settings = _json("\n".join(sections.get("lb") or []))
    routes: Dict[str, Dict[str, Any]] = {}
    for line in sections.get("routes") or []:
        route = _json(line)
        if isinstance(route, dict) and route.get("key"):
            routes[str(route["key"])] = route
    state = ([s.strip() for s in sections.get("state") or [] if s.strip()] or ["missing"])[-1]
    return {"settings": settings if isinstance(settings, dict) else {}, "routes": routes, "state": state}


def _json(text: str) -> Any:
    try:
        return json.loads(text.strip() or "null")
    except ValueError:
        return None


def _apply(root: Path, name: str, item: Dict[str, Any], emit: Emit, run: Optional[RunFn], write: Dict[str, str],
           remove: List[str], checks: Dict[str, str]) -> Dict[str, bool]:
    """Run the apply script on the load balancer server. Returns ``{check label: healthy}``."""
    out = _script(_target(root, str(item["server"])), lb.apply_script(name, write, remove, checks=checks), emit, run,
                  f"lb-{name}")
    if "PSKIT_LB_DONE=1" not in out:
        tail = [line for line in out.strip().splitlines() if line.strip()][-8:]
        raise BalancerError(f"load balancer {name} on {item['server']}: " + (" | ".join(tail) or "no output"))
    ok = {line.split("=", 1)[1].strip() for line in out.splitlines() if line.startswith("PSKIT_LB_OK=")}
    return {label: label in ok for label in checks}


# ----------------------------------------------------------------------------------------------- lifecycle
def create_balancer(
    root: Path, name: str, server: str, emit: Emit, *, port: Optional[int] = None, algorithm: Optional[str] = None,
    address: str = "", weights: Optional[Dict[str, Any]] = None, run: Optional[RunFn] = None,
) -> Dict[str, Any]:
    """Make saved server ``server`` load balancer ``name`` (Docker + OpenResty there), or add one that already runs
    there (created by another project: its port and algorithm are kept unless given here)."""
    if not _NAME.match(str(name)):
        raise BalancerError("load balancer name: lowercase letter first; lowercase letters, digits and - (max 31)")
    items = load_balancers(root)
    if name in items:
        raise BalancerError(f"load balancer {name!r} already exists (pskit lb update {name} ... changes it)")
    _check_server(root, server, name)
    target = _target(root, server)
    if run is None:
        from .onprem_services import check_ssh_login

        check_ssh_login(target)
    addr = address or _cluster()._bind_address(target) or _cluster()._ip(str(target["host"]))
    try:
        lb.hostport(addr, 80)
    except ValueError as exc:
        raise BalancerError(str(exc)) from None
    try:
        existing = read_server(root, name, run=run, item={"server": server})
    except BalancerError:
        existing = {"settings": {}, "routes": {}, "state": "missing"}
    settings = existing["settings"]
    if settings:
        emit(f"{server} already runs load balancer {name} (port {settings.get('port')},"
             f" {settings.get('algorithm')}, {len(existing['routes'])} route(s)): adding it to this project")
    chosen_port = int(port if port is not None else settings.get("port") or DEFAULT_PORT)
    if not 1 <= chosen_port <= 65535:
        raise BalancerError("the load balancer port must be 1..65535")
    try:
        chosen = lb.normalize_algorithm(algorithm if algorithm is not None else settings.get("algorithm"))
        checked = lb.weights_for([], weights)
    except ValueError as exc:
        raise BalancerError(str(exc)) from None
    item: Dict[str, Any] = {"server": server, "address": addr, "port": chosen_port, "algorithm": chosen, "weights": checked,
            "clusters": [], "created_at": _now()}
    emit(f"Setting up load balancer {name} (OpenResty in Docker) on {server} ({addr}), "
         f"{lb.ALGORITHMS[chosen]['label'].lower()}, port {chosen_port} ...")
    changed = bool(settings) and (int(settings.get("port") or 0) != chosen_port or settings.get("algorithm") != chosen)
    write, remove = _rerender(name, item, existing["routes"]) if changed else ({}, [])
    write.update(lb.base_files(name, chosen_port, chosen))
    _apply(root, name, item, emit, run, write, remove, {})
    with _LOCK:
        items = load_balancers(root)
        items[name] = item
        _save(root, items)
    emit(f"Load balancer {name}: {base_url(item)}/<path>/. Attach it to a cluster (pskit lb attach {name} --cluster"
         f" NAME) or name it in a project's pskit.yml (provider.options.balancer: {name}).")
    network.emit_rules(emit, f"load balancer {name} on {server}",
                       network.balancer(name, network.who(server, addr), [chosen_port], []))
    return public(name, item)


def update_balancer(
    root: Path, name: str, emit: Emit, *, port: Optional[int] = None, algorithm: Optional[str] = None,
    address: Optional[str] = None, weights: Optional[Dict[str, Any]] = None, run: Optional[RunFn] = None,
) -> Dict[str, Any]:
    """Change the port, the default algorithm, the weights or the public address. Routes that use the default
    algorithm (every project's, unless it picked its own) switch at once."""
    item = dict(get_balancer(root, name))
    try:
        if algorithm is not None:
            item["algorithm"] = lb.normalize_algorithm(algorithm)
        if weights is not None:
            item["weights"] = lb.weights_for([], weights)
    except ValueError as exc:
        raise BalancerError(str(exc)) from None
    if port is not None:
        if isinstance(port, bool) or not 1 <= int(port) <= 65535:
            raise BalancerError("the load balancer port must be 1..65535")
        item["port"] = int(port)
    if address:
        try:
            lb.hostport(address, 80)
        except ValueError as exc:
            raise BalancerError(str(exc)) from None
        item["address"] = address
    current = read_server(root, name, run=run, item=item)
    write, remove = _rerender(name, item, current["routes"])
    write.update(lb.base_files(name, int(item["port"]), str(item["algorithm"])))
    emit(f"Updating load balancer {name} on {item['server']}: {lb.ALGORITHMS[item['algorithm']]['label'].lower()},"
         f" port {item['port']}, {len(current['routes'])} route(s) ...")
    _apply(root, name, item, emit, run, write, remove, {})
    _update(root, name, lambda c: c.update(item))
    return public(name, item)


def _rerender(name: str, item: Dict[str, Any], routes: Dict[str, Dict[str, Any]]) -> Tuple[Dict[str, str], List[str]]:
    """Every route's files again (from its saved settings) with the load balancer's current default and weights."""
    write: Dict[str, str] = {}
    remove: List[str] = []
    for key, route in sorted(routes.items()):
        try:
            write.update(_route_files(item, route))
        except (ValueError, KeyError):
            remove.extend(lb.route_files(key))  # a route pskit can no longer read: dropped, not left half-written
    return write, remove


def remove_balancer(root: Path, name: str, emit: Emit, *, force: bool = False, run: Optional[RunFn] = None) -> None:
    """Stop the load balancer and remove it from its server. Routes of other projects block this unless ``force``
    (their URLs stop answering too)."""
    item = get_balancer(root, name)
    try:
        current = read_server(root, name, run=run)
        mine = _owners(root)
        others = sorted({str(r.get("owner")) for r in current["routes"].values() if r.get("owner") not in mine})
        if others and not force:
            raise BalancerError(f"load balancer {name} also serves {', '.join(others)} (other projects). Remove it"
                                f" anyway with --force, or only from this project: pskit lb forget {name}")
        _script(_target(root, str(item["server"])), lb.remove_script(name), emit, run, f"lb-{name}-remove")
        emit(f"Stopped load balancer {name} on {item['server']}.")
    except BalancerError as exc:
        if "also serves" in str(exc):
            raise
        emit(f"  {item['server']} did not answer ({exc}). Remove it there later: docker rm -f {lb.container_name(name)}")
    forget_balancer(root, name)


def forget_balancer(root: Path, name: str) -> None:
    """Remove the load balancer from this project only (it keeps running for the others)."""
    with _LOCK:
        items = load_balancers(root)
        if items.pop(str(name), None) is None:
            raise BalancerError(_unknown(root, name))
        _save(root, items)


def _check_server(root: Path, server: str, name: str) -> None:
    for cname, cluster in _cluster().load_clusters(root).items():
        if server in (cluster.get("nodes") or {}):
            raise BalancerError(f"server {server!r} is in cluster {cname!r}. A load balancer is a server outside the"
                                " clusters it serves: save another one (pskit resources onprem servers add)")
        if (cluster.get("balancer") or {}).get("server") == server:
            raise BalancerError(f"server {server!r} is the load balancer of cluster {cname!r}"
                                f" (pskit cluster balancer remove {cname} first, or attach {name} there instead)")


def _owners(root: Path) -> set:
    """Deployments of this project (route owners it may change)."""
    owners: set = set()
    for cluster in _cluster().load_clusters(root).values():
        owners.update((cluster.get("deployments") or {}).keys())
    pskit = Path(root) / ".pskit"
    for record in pskit.glob("onprem-*/onprem_deployed.json") if pskit.is_dir() else []:
        try:
            data = json.loads(record.read_text("utf-8"))
        except (OSError, ValueError):
            continue
        for entry in data.get("balancers") or []:
            if isinstance(entry, dict) and entry.get("owner"):
                owners.add(str(entry["owner"]))
    return owners


# ----------------------------------------------------------------------------------------------- routes
def _route_files(item: Dict[str, Any], route: Dict[str, Any]) -> Dict[str, str]:
    key = str(route["key"])
    algorithm = lb.normalize_algorithm(route.get("algorithm") or item.get("algorithm"))
    weights = {**(item.get("weights") or {}), **(route.get("weights") or {})}
    backends = []
    for b in route.get("backends") or []:
        weight = weights.get(str(b.get("server") or ""), b.get("weight") or 1)
        backends.append(lb.backend(str(b["address"]), int(b["port"]), weight=int(weight), backup=bool(b.get("backup")),
                                   server=str(b.get("server") or ""), per_request=bool(b.get("per_request"))))
    comment = f"{route.get('owner')} ({route.get('source') or 'project'})"
    if route.get("listen"):
        files = {f"conf.d/r-{key}.conf": lb.port_route_conf(key, int(route["listen"]), algorithm, backends,
                                                            comment=comment)}
    else:
        files = lb.path_route_files(key, str(route["path"]), algorithm, backends, comment=comment)
    files[f"routes/{key}.json"] = json.dumps(route, sort_keys=True) + "\n"
    return files


def _route_check(item: Dict[str, Any], route: Dict[str, Any]) -> str:
    if route.get("listen"):
        return f"http://127.0.0.1:{int(route['listen'])}/__pskit/health"
    return f"http://127.0.0.1:{int(item.get('port') or DEFAULT_PORT)}/{route['path']}/__pskit/health"


def make_route(owner: str, backends: List[Dict[str, Any]], *, path: str = "", listen: int = 0,
               algorithm: Optional[str] = None, weights: Optional[Dict[str, Any]] = None, source: str = "project",
               service: str = "", stage: str = "") -> Dict[str, Any]:
    """A route's saved settings (also what ``routes/<key>.json`` on the server holds)."""
    try:
        key = lb.route_key(path, listen)
        route: Dict[str, Any] = {
            "key": key, "owner": owner, "source": source, "service": service, "stage": stage,
            "algorithm": lb.normalize_algorithm(algorithm) if algorithm else None,
            "weights": lb.weights_for([], weights),
            "backends": [lb.backend(str(b["address"]), int(b["port"]), weight=int(b.get("weight") or 1),
                                    backup=bool(b.get("backup")), server=str(b.get("server") or ""),
                                    per_request=bool(b.get("per_request")))
                         for b in backends],
            "updated_at": _now(), "updated_from": socket.gethostname(),
        }
    except ValueError as exc:
        raise BalancerError(str(exc)) from None
    if listen:
        route["listen"] = int(listen)
    else:
        route["path"] = lb.normalize_path(path)
    if not route["backends"]:
        raise BalancerError(f"{owner}: no server to send requests to")
    return route


def set_routes(root: Path, name: str, routes: List[Dict[str, Any]], emit: Emit, *, drop_owners: Tuple[str, ...] = (),
               drop_sources: Optional[Tuple[str, Tuple[str, ...]]] = None, run: Optional[RunFn] = None,
               strict: bool = True) -> List[Dict[str, Any]]:
    """Write ``routes`` (from :func:`make_route`) on load balancer ``name`` in one change.

    Other routes of the same owners are dropped (a path that changed), as are every route of ``drop_owners`` and,
    with ``drop_sources=(source, keep_owners)``, routes from ``source`` whose owner is not in ``keep_owners`` (a
    cluster's deployments that are gone). A path taken by another owner is an error. Returns the routes with
    ``url`` and ``healthy``; ``strict=False`` only warns when the load balancer cannot be reached."""
    item = get_balancer(root, name)
    try:
        current = read_server(root, name, run=run, item=item)["routes"]
    except BalancerError as exc:
        if strict:
            raise
        emit(f"  WARNING: load balancer {name} on {item['server']} did not answer ({exc}). Once it does: pskit lb"
             f" sync {name}")
        return []
    owners = {str(r["owner"]) for r in routes}
    for route in routes:
        taken = current.get(route["key"])
        if taken and taken.get("owner") != route["owner"]:
            where = f"path /{route['path']}" if route.get("path") else f"port {route.get('listen')}"
            raise BalancerError(f"{where} on load balancer {name} already serves {taken.get('owner')}"
                                f" ({taken.get('source') or 'project'}). Pick another: provider.options.balancer.path")
    wanted = {r["key"] for r in routes}
    dropped: List[str] = []
    for key, route in sorted(current.items()):
        owner = str(route.get("owner") or "")
        gone = drop_sources is not None and route.get("source") == drop_sources[0] and owner not in drop_sources[1]
        if key not in wanted and (owner in owners or owner in drop_owners or gone):
            dropped.append(key)
    remove = [p for key in dropped for p in lb.route_files(key)]
    write: Dict[str, str] = {}
    checks: Dict[str, str] = {}
    for route in routes:
        write.update(_route_files(item, route))
        checks[route["key"]] = _route_check(item, route)
    if not write and not remove:
        return []
    try:
        healthy = _apply(root, name, item, lambda _l: None, run, write, remove, checks)
    except BalancerError as exc:
        if strict:
            raise
        emit(f"  WARNING: could not update load balancer {name} on {item['server']}: {exc}. Once it is reachable:"
             f" pskit lb sync {name}")
        return []
    out = []
    for route in routes:
        url = route_url(item, route["path"]) if route.get("path") else _port_url(item, int(route["listen"]))
        algorithm = lb.normalize_algorithm(route.get("algorithm") or item.get("algorithm"))
        line = f"  {url} -> {route['owner']}: {lb.describe(algorithm, _weighted(item, route))}"
        if not healthy.get(route["key"]):
            line = (f"  WARNING: {url}__pskit/health did not answer yet ({route['owner']}). The servers may still be"
                    f" starting, or {item['server']} cannot reach them (firewall).")
        emit(line)
        out.append({**route, "url": url, "healthy": bool(healthy.get(route["key"])), "balancer": name})
    for key in dropped:
        emit(f"  removed /{current[key].get('path') or key} ({current[key].get('owner')}) from load balancer {name}")
    return out


def _weighted(item: Dict[str, Any], route: Dict[str, Any]) -> List[Dict[str, Any]]:
    weights = {**(item.get("weights") or {}), **(route.get("weights") or {})}
    return [{**b, "weight": int(weights.get(str(b.get("server") or ""), b.get("weight") or 1))}
            for b in route.get("backends") or []]


def _port_url(item: Dict[str, Any], port: int) -> str:
    return base_url({**item, "port": port}) + "/"


def remove_owner(root: Path, name: str, owner: str, emit: Emit, *, run: Optional[RunFn] = None,
                 strict: bool = False) -> int:
    """Drop every route of ``owner`` (a deployment that was removed). Returns how many were removed."""
    item = get_balancer(root, name)
    try:
        current = read_server(root, name, run=run, item=item)["routes"]
    except BalancerError as exc:
        if strict:
            raise
        emit(f"  WARNING: load balancer {name} did not answer ({exc}); its route for {owner} stays until"
             f" pskit lb routes remove {name} PATH")
        return 0
    keys = [k for k, r in current.items() if r.get("owner") == owner]
    if keys:
        _apply(root, name, item, emit, run, {}, [p for k in keys for p in lb.route_files(k)], {})
        emit(f"  load balancer {name}: removed {', '.join('/' + str(current[k].get('path') or k) for k in keys)}")
    return len(keys)


def remove_route(root: Path, name: str, path: str, emit: Emit, *, run: Optional[RunFn] = None) -> Dict[str, Any]:
    """Drop the route at ``path`` (``/xyz`` or ``port-8081``) whoever owns it."""
    item = get_balancer(root, name)
    try:
        key = path if str(path).startswith("port-") else lb.route_key(path)
    except ValueError as exc:
        raise BalancerError(str(exc)) from None
    current = read_server(root, name, run=run, item=item)["routes"]
    if key not in current:
        raise BalancerError(f"load balancer {name} has no route {path} (routes: "
                            + (", ".join(sorted("/" + str(r.get("path") or k) for k, r in current.items())) or "none")
                            + ")")
    _apply(root, name, item, emit, run, {}, lb.route_files(key), {})
    emit(f"Removed {path} ({current[key].get('owner')}) from load balancer {name}.")
    return current[key]


def sync_balancer(root: Path, name: str, emit: Emit, *, run: Optional[RunFn] = None) -> Dict[str, Any]:
    """Rewrite everything on the load balancer (settings, every route) and the routes of attached clusters."""
    item = get_balancer(root, name)
    current = read_server(root, name, run=run, item=item)
    write, remove = _rerender(name, item, current["routes"])
    write.update(lb.base_files(name, int(item.get("port") or DEFAULT_PORT), str(item.get("algorithm"))))
    checks = {k: _route_check(item, r) for k, r in current["routes"].items() if f"routes/{k}.json" in write}
    emit(f"Rewriting load balancer {name} on {item['server']} ({len(current['routes'])} route(s)) ...")
    healthy = _apply(root, name, item, emit, run, write, remove, checks)
    for key, ok in sorted(healthy.items()):
        if not ok:
            emit(f"  WARNING: route {key} did not answer /__pskit/health yet")
    for cluster in sorted(item.get("clusters") or []):
        sync_cluster(root, cluster, emit, run=run, only=name)
    return status(root, name, run=run)


# ----------------------------------------------------------------------------------------------- clusters
def attach_cluster(root: Path, name: str, cluster: str, emit: Emit, *, run: Optional[RunFn] = None) -> Dict[str, Any]:
    """Put every deployment of ``cluster`` on load balancer ``name`` (path ``/<service>``) from now on."""
    get_balancer(root, name)
    _cluster().get_cluster(root, cluster)  # exists
    _update(root, name, lambda c: c.__setitem__("clusters", sorted(set(c.get("clusters") or []) | {cluster})))
    emit(f"Load balancer {name} now serves cluster {cluster}.")
    sync_cluster(root, cluster, emit, run=run, only=name, strict=True)
    network.emit_rules(emit, f"load balancer {name} -> cluster {cluster}",
                       network.named_cluster_rules(name, get_balancer(root, name), _cluster().get_cluster(root, cluster)))
    return public(name, get_balancer(root, name))


def detach_cluster(root: Path, name: str, cluster: str, emit: Emit, *, run: Optional[RunFn] = None) -> Dict[str, Any]:
    """Stop serving ``cluster`` on ``name``: its routes there are removed (a project's own ``balancer`` stays)."""
    item = get_balancer(root, name)
    if cluster not in (item.get("clusters") or []):
        raise BalancerError(f"load balancer {name} does not serve cluster {cluster}")
    _update(root, name, lambda c: c.__setitem__("clusters", sorted(set(c.get("clusters") or []) - {cluster})))
    # The other attached clusters' routes are rewritten too: a project placed on both loses this one's servers.
    _sync_attached(root, name, _cluster().load_clusters(root), emit, run=run, strict=False, label=cluster)
    emit(f"Load balancer {name} no longer serves cluster {cluster}.")
    return public(name, get_balancer(root, name))


def attached_to(root: Path, cluster: str) -> List[str]:
    return sorted(n for n, item in load_balancers(root).items() if cluster in (item.get("clusters") or []))


def cluster_backends(cluster: Dict[str, Any], port: int) -> List[Dict[str, Any]]:
    """Every server of a cluster that answers a deployment's port (the master as backup when it does not serve).
    Kubernetes servers are marked ``per_request`` (see :func:`onprem_lb.backend`)."""
    primary, backup = _cluster()._backends(cluster)
    nodes = cluster.get("nodes") or {}
    extra = {"per_request": True} if cluster.get("orchestrator") == "kubernetes" else {}
    return ([{"address": str(nodes[s].get("address")), "port": port, "server": s, **extra} for s in primary]
            + [{"address": str(nodes[s].get("address")), "port": port, "server": s, "backup": True, **extra}
               for s in backup])


def deployment_owner(stack: str, dep: Dict[str, Any]) -> str:
    """The project deployment a cluster stack belongs to (``pskit-<service>-<stage>``): the placement groups of one
    project (``pskit-<service>-<stage>-<group>``, maybe on other clusters) share it, and so one route."""
    if not dep.get("service") or not dep.get("stage"):
        return stack
    return str(_cluster().scripts.stack_name(str(dep["service"]), str(dep["stage"])))


def owner_backends(clusters: Dict[str, Dict[str, Any]], owner: str) -> List[Dict[str, Any]]:
    """The servers of every cluster in ``clusters`` that runs a group of ``owner``, each on that group's port."""
    out: List[Dict[str, Any]] = []
    seen: set = set()
    for _name, cluster in sorted(clusters.items()):
        for stack, dep in sorted((cluster.get("deployments") or {}).items()):
            if deployment_owner(stack, dep) != owner:
                continue
            for b in cluster_backends(cluster, int(dep.get("port") or 8080)):
                if (b["address"], b["port"]) not in seen:
                    seen.add((b["address"], b["port"]))
                    out.append(b)
    return out


def sync_cluster(root: Path, cluster_name: str, emit: Emit, *, run: Optional[RunFn] = None,
                 cluster: Optional[Dict[str, Any]] = None, only: str = "", strict: bool = False) -> None:
    """Each load balancer attached to ``cluster_name`` gets a route per deployment there (``/<service>``, or
    ``/<service>-<stage>`` when two stages of one service share it). ``cluster`` replaces the saved one (a server
    that is leaving). Deployments with their own route from ``provider.options.balancer`` keep it."""
    names = [only] if only else attached_to(root, cluster_name)
    if not names:
        return
    saved = dict(_cluster().load_clusters(root))
    saved[cluster_name] = cluster if cluster is not None else _cluster().get_cluster(root, cluster_name)
    for name in names:
        _sync_attached(root, name, saved, emit, run=run, strict=strict, label=cluster_name)


def _sync_attached(root: Path, name: str, clusters: Dict[str, Dict[str, Any]], emit: Emit, *,
                   run: Optional[RunFn] = None, strict: bool = False, label: str = "") -> None:
    """Rewrite every cluster route on load balancer ``name`` from all the clusters attached to it. A project whose
    placement groups run on several attached clusters gets one route to the servers of all of them (each host
    passes another group's routes on to it)."""
    attached = {c: clusters[c] for c in (get_balancer(root, name).get("clusters") or []) if c in clusters}
    try:
        existing = read_server(root, name, run=run)["routes"]
    except BalancerError as exc:
        if strict:
            raise
        emit(f"  WARNING: load balancer {name} did not answer ({exc}). Once it does: pskit lb sync {name}")
        return
    # The project set its own route (provider.options.balancer): left to the project.
    own = {str(r.get("owner")) for r in existing.values()
           if r.get("source") is not None and not str(r.get("source")).startswith("cluster:")}
    found: Dict[str, Dict[str, Any]] = {}
    for cname, current in sorted(attached.items()):
        for stack, dep in sorted((current.get("deployments") or {}).items()):
            owner = deployment_owner(stack, dep)
            entry = found.setdefault(owner, {"service": str(dep.get("service") or stack),
                                             "stage": str(dep.get("stage") or ""), "clusters": []})
            entry["clusters"].append(cname)
            if stack == owner:
                entry["home"] = cname  # the default group's cluster
    services: Dict[str, int] = {}
    for entry in found.values():
        services[entry["service"]] = services.get(entry["service"], 0) + 1
    routes = []
    for owner, entry in sorted(found.items()):
        if owner in own:
            continue
        service = entry["service"]
        path = service if services.get(service, 0) < 2 else f"{service}-{entry['stage']}"
        backends = owner_backends(attached, owner)
        if not backends:
            emit(f"  WARNING: {owner} is not on load balancer {name}: the cluster has no server with an address")
            continue
        home = entry.get("home") or entry["clusters"][0]
        routes.append(make_route(owner, backends, path=path, source=f"cluster:{home}", service=service,
                                 stage=entry["stage"]))
    gone = tuple(sorted({str(r.get("owner")) for r in existing.values()
                         if str(r.get("source") or "").startswith("cluster:")} - set(found)))
    emit(f"Updating load balancer {name} for cluster {label} ...")
    try:
        set_routes(root, name, routes, emit, drop_owners=gone, run=run, strict=strict)
    except BalancerError as exc:
        if strict:
            raise
        emit(f"  WARNING: {exc}")


# ----------------------------------------------------------------------------------------------- status
def status(root: Path, name: str, *, run: Optional[RunFn] = None) -> Dict[str, Any]:
    """The load balancer, its server's use, whether OpenResty runs, and every route with its URL."""
    item = get_balancer(root, name)
    shown = public(name, item)
    try:
        target = _target(root, str(item["server"]))
    except BalancerError as exc:
        return {**shown, "reachable": False, "error": str(exc), "state": "unknown", "running": False, "routes": []}
    metrics = _cluster().node_metrics(target, run)
    if not metrics.get("reachable"):
        return {**shown, **metrics, "state": "unknown", "running": False, "routes": []}
    try:
        current = read_server(root, name, run=run, item=item)
    except BalancerError as exc:
        return {**shown, **metrics, "state": "unknown", "running": False, "routes": [], "error": str(exc)}
    mine = _owners(root)
    routes = []
    for _key, route in sorted(current["routes"].items()):
        algorithm = lb.normalize_algorithm(route.get("algorithm") or item.get("algorithm"))
        url = route_url(item, route["path"]) if route.get("path") else _port_url(item, int(route.get("listen") or 0))
        routes.append({**route, "url": url, "effective_algorithm": algorithm, "inherits": not route.get("algorithm"),
                       "mine": route.get("owner") in mine, "backends": _weighted(item, route)})
    server_settings = current["settings"]
    drift = bool(server_settings) and (int(server_settings.get("port") or 0) != shown["port"]
                                       or server_settings.get("algorithm") != shown["algorithm"])
    return {**shown, **metrics, "state": current["state"], "running": current["state"] == "running",
            "routes": routes, "server_settings": server_settings, "drift": drift}


def logs(root: Path, name: str, lines: int = 100, *, run: Optional[RunFn] = None) -> str:
    item = get_balancer(root, name)
    return _script(_target(root, str(item["server"])), lb.logs_script(name, max(1, min(int(lines), 10000))),
                   lambda _l: None, run, f"lb-{name}-logs")


# ----------------------------------------------------------------------------------------------- projects
def parse_option(raw: Any) -> List[Dict[str, Any]]:
    """``provider.options.balancer``: ``edge``, ``{name: edge, path: xyz, algorithm: ..., weights: {...}}`` or a list
    of those. Returns ``[{name, path?, algorithm?, weights?}]``; raises ``ValueError`` on a bad value."""
    if raw in (None, "", False):
        return []
    items = raw if isinstance(raw, list) else [raw]
    out = []
    for entry in items:
        body: Dict[str, Any] = {"name": entry} if isinstance(entry, str) else dict(entry or {})
        unknown = sorted(set(body) - {"name", "path", "algorithm", "weights"})
        if unknown:
            raise ValueError(f"unknown options.balancer keys {unknown}; expected name, path, algorithm, weights")
        if not _NAME.match(str(body.get("name") or "")):
            raise ValueError("options.balancer needs the load balancer's name: balancer: NAME or {name: NAME, path: ...}")
        clean: Dict[str, Any] = {"name": str(body["name"])}
        if body.get("path"):
            clean["path"] = lb.normalize_path(body["path"])
        if body.get("algorithm"):
            clean["algorithm"] = lb.normalize_algorithm(body["algorithm"])
        if body.get("weights") is not None:
            if not isinstance(body["weights"], dict):
                raise ValueError("options.balancer.weights maps a saved server name to a weight 1..100")
            clean["weights"] = lb.weights_for([], body["weights"])
        out.append(clean)
    names = [b["name"] for b in out]
    if len(set(names)) != len(names):
        raise ValueError("options.balancer names one load balancer more than once")
    return out


def sync_project(root: Path, options: List[Dict[str, Any]], owner: str, service: str, stage: str,
                 backends: List[Dict[str, Any]], emit: Emit, *, previous: Optional[List[Dict[str, Any]]] = None,
                 run: Optional[RunFn] = None) -> List[Dict[str, Any]]:
    """After a deploy: the project's route on every load balancer in ``options`` (default path: the service).
    Load balancers it used last time (``previous``) but no longer names lose its route. Returns
    ``[{name, key, path, url, owner}]`` to keep in the deploy record (only warns when one cannot be reached)."""
    done: List[Dict[str, Any]] = []
    for option in options:
        name = option["name"]
        if name not in load_balancers(root):
            emit(f"  WARNING: provider.options.balancer names {name!r}, which this project does not know:"
                 f" pskit lb create {name} --server SERVER (it is found when another project created it)")
            continue
        route = make_route(owner, backends, path=option.get("path") or service, algorithm=option.get("algorithm"),
                           weights=option.get("weights"), service=service, stage=stage)
        emit(f"Load balancer {name}:")
        for item in set_routes(root, name, [route], emit, run=run, strict=False):
            done.append({"name": name, "key": item["key"], "path": item.get("path"), "url": item["url"],
                         "owner": owner, "backends": route["backends"]})
        lb_item = load_balancers(root)[name]
        network.emit_rules(emit, f"load balancer {name} -> {service}",
                           network.balancer(name, network.who(str(lb_item["server"]), str(lb_item.get("address") or "")),
                                            [int(lb_item.get("port") or DEFAULT_PORT)], route["backends"]))
    named = {o["name"] for o in options}
    for old in previous or []:
        if old.get("name") not in named and old.get("name") in load_balancers(root):
            remove_owner(root, str(old["name"]), owner, emit, run=run)
    return done
