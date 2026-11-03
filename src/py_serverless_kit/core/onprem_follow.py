"""On-prem services follow the functions when they move (``pskit deploy`` to another server or cluster, or after
the server they ran on was removed).

The functions' host reads queues, topics and buckets itself, at the address the service was created with (kept in
the env file); only the SMTP service sends to the host (see :func:`onprem_smtp.retarget`). Before a deploy, for each
service the deployed functions use:

* an address pskit picked that no longer fits is switched: a server's cluster address works only inside that
  cluster, so functions outside it use the server's own address, and functions on that cluster its cluster address
  (env file and services state; the deploy then ships the new values);
* what cannot be fixed here is a warning naming the fix: the service's server was removed, the service runs on this
  machine or listens on 127.0.0.1 only, or its container has the old address built in.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Set

Emit = Callable[[str], None]


def used_services(root: Path, keys: List[str]) -> List[str]:
    """The keys of ``keys`` that are on-prem services (containers) of this project."""
    from .onprem_services import load_state

    services = load_state(root).get("services") or {}
    return [k for k in sorted(set(keys)) if isinstance(services.get(k), dict) and services[k].get("kind") == "service"]


def functions_where(raw: Dict[str, Any], root: Path) -> Dict[str, Any]:
    """Where this deploy puts the functions: ``{"method": "local"}``, an SSH server, or a cluster's master tagged with
    ``cluster`` (from the resolved ``provider.options``, not an earlier deploy)."""
    from .onprem_services import default_target, functions_target

    if default_target(raw) == {"method": "local"}:
        return {"method": "local"}
    return functions_target(raw, root)


def _cluster_nodes(root: Path, name: str) -> Dict[str, Dict[str, Any]]:
    from .onprem_cluster import load_clusters

    return dict((load_clusters(root).get(name) or {}).get("nodes") or {})


def _function_hosts(root: Path, where: Dict[str, Any]) -> Set[str]:
    """Hosts / saved server names the functions run on."""
    from .onprem_servers import load_servers

    if where.get("cluster"):
        servers = load_servers(root)
        out: Set[str] = set()
        for name, node in _cluster_nodes(root, str(where["cluster"])).items():
            out |= {name, str(node.get("address") or ""), str((servers.get(name) or {}).get("host") or "")}
        return out - {""}
    if where.get("method") == "ssh":
        return {str(where.get("host") or ""), str(where.get("server") or "")} - {""}
    return set()


def _wanted_address(root: Path, entry: Dict[str, Any], where: Dict[str, Any]) -> str:
    """The address the functions reach a service at: its server's cluster address when they run on that cluster,
    else the server's own address."""
    target = entry.get("target") or {}
    cluster = str(target.get("cluster") or "")
    if cluster and cluster == str(where.get("cluster") or ""):
        node = _cluster_nodes(root, cluster).get(str(target.get("server") or "")) or {}
        if node.get("address"):
            return str(node["address"])
    return str(target.get("host") or entry.get("address") or "")


def _picked_by_pskit(root: Path, entry: Dict[str, Any]) -> bool:
    """Whether pskit picked the service's address (so it may change it). Services created before this was recorded:
    the address is the server's own or one of its cluster addresses."""
    if "address_auto" in entry:
        return bool(entry["address_auto"])
    from .onprem_cluster import load_clusters

    target = entry.get("target") or {}
    address = str(entry.get("address") or "")
    if address and address == str(target.get("host") or ""):
        return True
    server = str(target.get("server") or "")
    return bool(server) and any(str(((c.get("nodes") or {}).get(server) or {}).get("address") or "") == address
                                for c in load_clusters(root).values())


def _built_in(entry: Dict[str, Any]) -> bool:
    """Whether the container got the address at start (Kafka's advertised listeners, ...): a new one needs a
    re-create."""
    from .onprem_services import SERVICES

    spec = SERVICES.get(str(entry.get("service") or "")) or {}
    return "{address}" in json.dumps({k: v for k, v in spec.items() if k != "connect"}, default=str)


def _swap(value: Any, old: str, new: str) -> Any:
    """``value`` with the host ``old`` replaced by ``new`` (only as a whole host name, in strings at any depth)."""
    if isinstance(value, str):
        return re.sub(rf"(?<![\w.-]){re.escape(old)}(?![\w-]|\.\w)", new, value)
    if isinstance(value, dict):
        return {k: _swap(v, old, new) for k, v in value.items()}
    if isinstance(value, list):
        return [_swap(v, old, new) for v in value]
    return value


def follow(root: Path, raw: Dict[str, Any], keys: List[str], emit: Emit) -> List[str]:
    """Before a deploy: make the services ``keys`` reachable from where the functions will run (see the module).
    Only warns when it cannot. Returns the keys whose address was changed."""
    from .onprem_servers import load_servers
    from .onprem_services import ServiceError, describe_target, load_state, save_state, update_env_file

    keys = used_services(root, keys)
    if not keys:
        return []
    try:
        where = functions_where(raw, root)
    except ServiceError as exc:
        emit(f"  WARNING: services not checked: {exc}")
        return []
    hosts = _function_hosts(root, where)
    here = "this machine" if where.get("method") == "local" else describe_target(where)
    servers = load_servers(root)
    state = load_state(root)
    changed: List[str] = []
    for key in keys:
        entry = state["services"][key]
        target = entry.get("target") or {}
        label = f"{entry.get('service')} {key!r}"
        if target.get("server") and target["server"] not in servers:
            emit(f"  WARNING: {label} ran on server {target['server']!r}, which was removed: the functions cannot "
                 "reach it, so its triggers do not run. Create the service again (same key) on a server that exists, "
                 "then deploy.")
            continue
        if entry.get("service") == "smtp":
            continue  # it sends to the functions: onprem_smtp.retarget after the deploy
        if isinstance(entry.get("topology"), dict):
            continue  # a replicated database: its members are reached at their servers' own addresses
        if target.get("method", "local") == "local":
            if where.get("method") != "local":
                emit(f"  WARNING: {label} runs on this machine (127.0.0.1), which the functions on {here} cannot "
                     "reach. Create the service again (same key) on a server, then deploy.")
            continue
        alone = not where.get("cluster") and str(target.get("host") or "") in hosts
        if str(entry.get("bind") or "") == "127.0.0.1" and not alone:
            emit(f"  WARNING: {label} listens on 127.0.0.1 of {target.get('server') or target.get('host')} only, so "
                 f"the functions on {here} cannot connect. Create it again with bind 0.0.0.0 (or a private IP of "
                 "the server), then deploy.")
            continue
        old = str(entry.get("address") or "")
        new = _wanted_address(root, entry, where)
        if not new or new == old or not _picked_by_pskit(root, entry):
            continue
        if _built_in(entry):
            emit(f"  WARNING: {label} is reached at {old}, but the functions on {here} need {new}, and its container "
                 "has the address built in. Create it again (same key, keeps the data), then deploy.")
            continue
        env = {k: _swap(v, old, new) for k, v in (entry.get("env") or {}).items()}
        env_file = str(entry.get("env_file") or "")
        if env_file and env != (entry.get("env") or {}):
            update_env_file(root / env_file, {k: v for k, v in env.items() if v != entry["env"].get(k)})
        state["services"][key] = {**entry, "address": new, "address_auto": True, "env": env,
                                  "resource": _swap(entry.get("resource") or {}, old, new)}
        save_state(root, state)
        emit(f"{label}: the functions now run on {here}, so they reach it at {new} (was {old})")
        changed.append(key)
    return changed


def firewall(root: Path, keys: List[str], emit: Emit, title: str = "") -> None:
    """After a deploy: the rules the function servers need to reach the services ``keys``."""
    from . import onprem_network as network
    from .onprem_services import load_state

    services = load_state(root).get("services") or {}
    rules: List[Dict[str, Any]] = []
    clients = network.function_hosts(root)
    for key in used_services(root, keys):
        rules += network.resource(services[key], clients)
    if rules:
        network.emit_rules(emit, title or "services used by the functions", rules)
