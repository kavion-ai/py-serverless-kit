"""The firewall rules on-prem servers need, with their real names and addresses (docs/onprem-network.md).

Every on-prem step prints the rules it just made necessary (``pskit cluster create / join``, ``pskit deploy``,
``pskit lb create / attach``, ``pskit resources onprem create``) and ``pskit firewall`` lists them for the whole
project, per server, with ``ufw`` commands. The studio shows the same (``GET /api/onprem-firewall``).

A rule is one inbound (or outbound) opening on one server::

    {"server": "edge2", "address": "10.0.0.6", "direction": "inbound", "proto": "tcp", "port": "2377",
     "sources": [{"name": "edge1", "address": "10.0.0.5"}], "why": "...", "level": "required"}

``sources`` are machines, or one of the words ``users``, ``internet``, ``admin`` (the machine running pskit).
``level`` is ``required``, ``feature`` (needed for that feature) or ``optional`` (pskit falls back to SSH).
"""

from __future__ import annotations

import json
import socket
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

Emit = Callable[[str], None]
Rule = Dict[str, Any]
Who = Dict[str, str]

USERS: Who = {"name": "users", "address": ""}
INTERNET: Who = {"name": "internet", "address": ""}
LEVEL_MARK = {"required": "REQUIRED", "feature": "NEEDED  ", "optional": "optional"}

# Between cluster servers: (proto, port, who opens it: master | workers | all, from: workers | master | others, why)
ORCHESTRATOR_PORTS: Dict[str, List[Tuple[str, str, str, str, str]]] = {
    "swarm": [
        ("tcp", "2377", "master", "workers", "Swarm cluster management (managers)"),
        ("tcp", "7946", "all", "others", "Swarm node discovery"),
        ("udp", "7946", "all", "others", "Swarm node discovery"),
        ("udp", "4789", "all", "others", "Swarm overlay network (VXLAN)"),
    ],
    "kubernetes": [
        ("tcp", "6443", "master", "workers", "k3s API: agents register and sync"),
        ("udp", "8472", "all", "others", "k3s Flannel VXLAN (pod network)"),
        ("tcp", "10250", "workers", "master", "kubelet (logs, exec, metrics)"),
    ],
    "nomad": [
        ("tcp", "4646", "master", "workers", "Nomad HTTP API"),
        ("tcp", "4647", "master", "workers", "Nomad RPC (clients register)"),
        ("tcp", "4648", "master", "workers", "Nomad gossip"),
        ("udp", "4648", "master", "workers", "Nomad gossip"),
    ],
}


def who(name: str, address: str = "") -> Who:
    return {"name": str(name), "address": str(address or "")}


def admin(toward: str = "") -> Who:
    """This machine (running pskit), with the address it uses to reach ``toward`` when it can tell."""
    return {"name": "admin", "address": local_address(toward) if toward else ""}


def local_address(toward: str) -> str:
    """The local IP the OS would use to reach ``toward`` (no packet is sent), or ""."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect((toward, 9))
            address = str(sock.getsockname()[0])
    except OSError:
        return ""
    return "" if address.startswith("127.") or address == "0.0.0.0" else address  # noqa: S104


def rule(server: Who, port: Any, sources: Sequence[Who], why: str, *, proto: str = "tcp",
         level: str = "required", direction: str = "inbound") -> Rule:
    return {"server": server["name"], "address": server["address"], "direction": direction, "proto": proto,
            "port": str(port), "sources": [dict(s) for s in sources], "why": why, "level": level}


def ssh_rule(server: Who, port: Any = 22, *, why: str = "pskit over SSH (scripts, copies, logs, status)") -> Rule:
    return rule(server, port or 22, [admin(server["address"])], why)


def internet_rule(server: Who, why: str) -> Rule:
    return rule(server, "443, 80", [INTERNET], why, direction="outbound", level="feature")


# ----------------------------------------------------------------------------------------------- per step
def single_server(server: Who, port: int, *, ssh_port: int = 22, local: bool = False) -> List[Rule]:
    """One function host (``pskit deploy`` to a server, or this machine)."""
    rules = [rule(server, port, [USERS], "your functions' HTTP, workflow starts, SQS / Lambda compatible APIs")]
    if not local:
        rules.insert(0, ssh_rule(server, ssh_port))
        rules.append(rule(server, port, [admin(server["address"])], "logs, tests and the studio (else an SSH tunnel)",
                          level="optional"))
    return rules


def placement(groups: Dict[str, Dict[str, Any]], default: str) -> List[Rule]:
    """Function groups on several servers: every group host reaches every other one on its port."""
    rules: List[Rule] = []
    hosts = {g: who(str(v.get("server") or v.get("address") or g), str(v.get("address") or ""))
             for g, v in groups.items()}
    for group, body in sorted(groups.items()):
        others = [hosts[g] for g in sorted(groups) if g != group and hosts[g]["address"] != hosts[group]["address"]]
        if not others:
            continue
        why = (f"group {group}: invoke(), HTTP routes, workflow steps and queues from the other groups"
               + ("; their logs and workflow starts (default group)" if group == default else ""))
        rules.append(rule(hosts[group], int(body.get("port") or 8080), others, why))
    return rules


def cluster(name: str, item: Dict[str, Any], *, only: str = "") -> List[Rule]:
    """A scaling cluster: orchestrator ports between its servers, the functions' port, SSH. ``only``: rules that
    involve that server (the one that just joined)."""
    orch = str(item.get("orchestrator") or "")
    master_name = str(item.get("master") or "")
    nodes = {s: who(s, str((n or {}).get("address") or "")) for s, n in (item.get("nodes") or {}).items()}
    master = nodes.get(master_name)
    workers = [n for s, n in sorted(nodes.items()) if s != master_name]
    rules: List[Rule] = [ssh_rule(n) for _s, n in sorted(nodes.items())]
    rules += [internet_rule(n, "first time: Docker / k3s / Nomad downloads and images") for _s, n in sorted(nodes.items())]
    for proto, port, opens, sources, why in ORCHESTRATOR_PORTS.get(orch, []):
        targets = [master] if opens == "master" else workers if opens == "workers" else list(nodes.values())
        for target in [t for t in targets if t]:
            if sources == "workers":
                src = workers
            elif sources == "master":
                src = [master] if master else []
            else:
                src = [n for n in nodes.values() if n["name"] != target["name"]]
            if src:
                rules.append(rule(target, port, src, f"cluster {name}: {why}", proto=proto))
    balancer_servers = [who(str(b["server"]), str(b.get("address") or ""))
                        for b in _cluster_balancers(item)]
    for stack, dep in sorted((item.get("deployments") or {}).items()):
        fn_port = int(dep.get("port") or 8080)
        if master and workers:
            rules.append(rule(master, fn_port, workers, f"{stack}: web replicas reach the main replica"))
        public = list(nodes.values()) if orch != "nomad" else (workers or ([master] if master else []))
        for node in public:
            if balancer_servers:
                rules.append(rule(node, fn_port, balancer_servers, f"{stack}: the load balancer forwards requests"))
            else:
                rules.append(rule(node, fn_port, [USERS], f"{stack}: users call any server (no load balancer)"))
    if only:
        rules = [r for r in rules if r["server"] == only or any(s["name"] == only for s in r["sources"])]
    return rules


def _cluster_balancers(item: Dict[str, Any]) -> List[Dict[str, Any]]:
    out = []
    own = item.get("balancer")
    if isinstance(own, dict) and own.get("server"):
        out.append(own)
    out.extend(b for b in item.get("_named_balancers") or [] if b.get("server"))
    return out


def balancer(name: str, server: Who, ports: Iterable[int], backends: Sequence[Dict[str, Any]]) -> List[Rule]:
    """A load balancer: users -> its ports, it -> every backend's port, the admin machine -> SSH."""
    rules = [ssh_rule(server), internet_rule(server, "first time: Docker and the OpenResty image")]
    for port in sorted(set(int(p) for p in ports)):
        rules.append(rule(server, port, [USERS], f"load balancer {name}: the public URLs"))
    seen = set()
    for backend in backends:
        key = (str(backend.get("address")), int(backend.get("port") or 8080))
        if key in seen or not key[0]:
            continue
        seen.add(key)
        target = who(str(backend.get("server") or key[0]), key[0])
        rules.append(rule(target, key[1], [server], f"load balancer {name} forwards requests and checks health"))
    return rules


def resource(entry: Dict[str, Any], clients: Sequence[Who]) -> List[Rule]:
    """An on-prem service (Redis, Postgres, SMTP, ...): the function hosts reach its port."""
    if isinstance(entry.get("topology"), dict) and entry["topology"].get("mode") == "replicated":
        from .onprem_replication import rules as replication_rules

        return replication_rules(entry, clients)
    target = entry.get("target") or {}
    if str(target.get("method") or "") == "local" or not entry.get("port"):
        return []
    server = who(str(target.get("server") or target.get("host") or entry.get("address")),
                 str(entry.get("address") or target.get("host") or ""))
    label = f"{entry.get('service')} {entry.get('key')!r}"
    rules = [ssh_rule(server)]
    if entry.get("service") == "smtp":
        rules.append(rule(server, 25, [INTERNET], f"{label}: incoming mail (point an MX record at it)"))
        if int(entry.get("port") or 25) != 25:
            rules.append(rule(server, entry["port"], [INTERNET], f"{label}: incoming mail (port 25 forwarded here)"))
        rules += [rule(c, c.get("port") or 8080, [server], f"{label}: delivers mail to the smtp triggers")
                  for c in clients if c["address"] and c["address"] != server["address"]]
        return rules
    sources = [c for c in clients if c["address"] != server["address"]] or [who("your function servers")]
    rules.append(rule(server, entry["port"], sources, f"{label}: your functions connect to it"))
    for gui in entry.get("gui") or []:
        if isinstance(gui, dict) and gui.get("port"):
            rules.append(rule(server, gui["port"], [admin(server["address"])], f"{label}: web console",
                              level="optional"))
    return rules


# ----------------------------------------------------------------------------------------------- output
def _source(s: Dict[str, str]) -> str:
    if s["name"] == "admin":
        return f"this machine ({s['address']})" if s["address"] else "this machine (pskit)"
    if s["name"] in ("users", "internet"):
        return s["name"]
    return f"{s['name']} ({s['address']})" if s["address"] and s["address"] != s["name"] else s["name"]


def merge(rules: Iterable[Rule]) -> List[Rule]:
    """One rule per server / direction / proto / port, with every source and reason."""
    out: Dict[Tuple[str, str, str, str], Rule] = {}
    order = {"required": 0, "feature": 1, "optional": 2}
    for r in rules:
        key = (r["server"], r["direction"], r["proto"], r["port"])
        if key not in out:
            out[key] = {**r, "sources": list(r["sources"]), "why": r["why"]}
            continue
        current = out[key]
        for s in r["sources"]:
            if s not in current["sources"]:
                current["sources"].append(s)
        if r["why"] not in current["why"].split("; "):
            current["why"] += "; " + r["why"]
        if order[r["level"]] < order[current["level"]]:
            current["level"] = r["level"]
    return sorted(out.values(), key=lambda r: (r["server"], r["direction"] != "inbound", _port_key(r["port"]),
                                               r["proto"]))


def _port_key(port: str) -> Tuple[int, str]:
    head = port.split(",")[0].strip()
    return (int(head), port) if head.isdigit() else (99999, port)


def by_server(rules: Iterable[Rule]) -> List[Dict[str, Any]]:
    """``[{server, address, rules, ufw}]`` for the CLI, the studio and JSON."""
    servers: Dict[str, Dict[str, Any]] = {}
    for r in merge(rules):
        item = servers.setdefault(r["server"], {"server": r["server"], "address": r["address"], "rules": []})
        item["address"] = item["address"] or r["address"]
        item["rules"].append(r)
    for item in servers.values():
        item["ufw"] = ufw(item["rules"])
    return [servers[k] for k in sorted(servers)]


def ufw(rules: Iterable[Rule]) -> List[str]:
    """``ufw`` commands for one server's inbound rules (sources with an address; users / internet: anyone)."""
    out: List[str] = []
    for r in rules:
        if r["direction"] != "inbound" or not str(r["port"]).replace(" ", "").replace(",", "").isdigit():
            continue
        for port in [p.strip() for p in str(r["port"]).split(",")]:
            addresses = [s["address"] for s in r["sources"] if s["address"]]
            if any(s["name"] in ("users", "internet") for s in r["sources"]) or not addresses:
                line = f"sudo ufw allow {port}/{r['proto']}"
                if not any(s["name"] in ("users", "internet") for s in r["sources"]):
                    line += "   # from: " + ", ".join(_source(s) for s in r["sources"])
                out.append(line)
                continue
            out += [f"sudo ufw allow from {a} to any port {port} proto {r['proto']}" for a in addresses]
    return list(dict.fromkeys(out))


def lines(title: str, rules: Iterable[Rule], *, commands: bool = True) -> List[str]:
    """What a step prints: per server, each opening with who needs it and why, then ufw commands."""
    grouped = by_server(rules)
    if not grouped:
        return []
    out = [f"Firewall - {title} (open these; docs/onprem-network.md):"]
    for item in grouped:
        name = item["server"]
        head = f"{name} ({item['address']})" if item["address"] and item["address"] != name else name
        out.append(f"  {head}")
        for r in item["rules"]:
            arrow = "inbound " if r["direction"] == "inbound" else "outbound"
            ports = f"{r['proto'].upper()} {r['port']}"
            peer = ("from " if r["direction"] == "inbound" else "to ") + ", ".join(_source(s) for s in r["sources"])
            out.append(f"    [{LEVEL_MARK[r['level']]}] {arrow} {ports:<12} {peer}  - {r['why']}")
        if commands and item["ufw"]:
            out.append(f"    ufw on {name}:")
            out += [f"      {command}" for command in item["ufw"]]
    return out


def emit_rules(emit: Emit, title: str, rules: Iterable[Rule]) -> None:
    for line in lines(title, rules):
        emit(line)


# ----------------------------------------------------------------------------------------------- whole project
def _target_who(root: Path, server: Optional[str], host: str) -> Who:
    if server:
        try:
            from .onprem_servers import get_server

            item = get_server(root, server)
            return who(server, _resolve(str(item.get("bind") or "") if str(item.get("bind") or "") not in (
                "", "0.0.0.0", "127.0.0.1") else str(item.get("host") or host)))  # noqa: S104
        except ValueError:
            pass
    return who(server or host or "this machine", _resolve(host))


def _resolve(host: str) -> str:
    if not host:
        return ""
    try:
        socket.inet_aton(host)
        return host
    except OSError:
        pass
    try:
        return socket.gethostbyname(host)
    except OSError:
        return host


def function_hosts(root: Path) -> List[Who]:
    """Servers that run this project's functions (every deployed on-prem stage, group and cluster server)."""
    out: List[Who] = []
    pskit = Path(root) / ".pskit"
    for path in sorted(pskit.glob("onprem-*/onprem_deployed.json")) if pskit.is_dir() else []:
        try:
            data = json.loads(path.read_text("utf-8"))
        except (OSError, ValueError):
            continue
        spec = data.get("spec") or {}
        method = str((spec.get("deploy") or {}).get("method") or "local")
        host = str(((spec.get("deploy") or {}).get("ssh") or {}).get("host") or "")
        if data.get("cluster"):
            from .onprem_cluster import load_clusters

            nodes = (load_clusters(root).get(str(data["cluster"])) or {}).get("nodes") or {}
            out += [who(s, str(n.get("address") or "")) for s, n in sorted(nodes.items())]
        elif method != "local" or host:
            out.append({**_target_who(root, data.get("server"), host), "port": str(spec.get("port") or 8080)})
        record = _record(path.parent)
        for group in (record.get("groups") or {}).values():
            from urllib.parse import urlsplit

            port = urlsplit(str(group.get("endpoint") or "")).port or 8080
            out.append({**_endpoint_who(str(group.get("server") or ""), str(group.get("endpoint") or "")),
                        "port": str(port)})
    seen, unique = set(), []
    for w in out:
        if w["address"] and w["address"] not in seen and not w["address"].startswith("127."):
            seen.add(w["address"])
            unique.append(w)
    return unique


def _record(work: Path) -> Dict[str, Any]:
    try:
        data = json.loads((work / "deployment.json").read_text("utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _endpoint_who(server: str, endpoint: str) -> Who:
    from urllib.parse import urlsplit

    host = urlsplit(endpoint).hostname or ""
    return who(server or host, _resolve(host))


def deployment(root: Path, work: Path) -> List[Rule]:
    """Rules of one deployed on-prem stage (``.pskit/onprem-<stage>``): its host, or its groups."""
    from urllib.parse import urlsplit

    try:
        data = json.loads((work / "onprem_deployed.json").read_text("utf-8"))
    except (OSError, ValueError):
        return []
    if data.get("cluster"):
        return []  # the cluster's own rules cover it
    spec = data.get("spec") or {}
    record = _record(work)
    groups = record.get("groups") if isinstance(record.get("groups"), dict) else None
    rules: List[Rule] = []
    if groups and len(groups) > 1:
        hosts: Dict[str, Dict[str, Any]] = {}
        for name, group in groups.items():
            url = urlsplit(str(group.get("endpoint") or ""))
            target = _endpoint_who(str(group.get("server") or ""), str(group.get("endpoint") or ""))
            hosts[name] = {"server": target["name"], "address": target["address"], "port": url.port or 8080}
            if group.get("cluster"):
                continue
            local = str(group.get("deploy") or "") == "local"
            rules += single_server(target, int(url.port or 8080), local=local)
        default = next((g for g, v in groups.items() if v.get("endpoint") == spec.get("endpoint")), "")
        rules += placement(hosts, default)
    else:
        method = str((spec.get("deploy") or {}).get("method") or "local")
        host = str(((spec.get("deploy") or {}).get("ssh") or {}).get("host") or "")
        target = _target_who(root, data.get("server"), host) if (host or data.get("server")) else _endpoint_who(
            "this machine", str(spec.get("endpoint") or ""))
        rules += single_server(target, int(spec.get("port") or 8080), local=method == "local",
                               ssh_port=int(((spec.get("deploy") or {}).get("ssh") or {}).get("port") or 22))
        if method == "docker":
            rules.append(internet_rule(target, "first time: Docker install and the base image"))
    return rules


def project(root: Path) -> List[Rule]:
    """Every rule this project needs now: deployments, clusters, load balancers, resources."""
    from .onprem_balancers import load_balancers
    from .onprem_cluster import load_clusters
    from .onprem_services import load_state

    root = Path(root)
    rules: List[Rule] = []
    pskit = root / ".pskit"
    for path in sorted(pskit.glob("onprem-*/onprem_deployed.json")) if pskit.is_dir() else []:
        rules += deployment(root, path.parent)
        for route in json.loads(path.read_text("utf-8")).get("balancers") or []:
            item = load_balancers(root).get(str(route.get("name")))
            if item and route.get("backends"):
                rules += balancer(str(route["name"]), who(str(item["server"]), str(item.get("address") or "")),
                                  [int(item.get("port") or 80)], route["backends"])
    clusters = load_clusters(root)
    named = load_balancers(root)
    for name, item in sorted(clusters.items()):
        attached = [n for n, b in named.items() if name in (b.get("clusters") or [])]
        rules += cluster(name, {**item, "_named_balancers": [named[n] for n in attached]})
        own = item.get("balancer")
        if isinstance(own, dict) and own.get("server"):
            rules += cluster_balancer_rules(name, item)
        for lb_name in attached:
            rules += named_cluster_rules(lb_name, named[lb_name], item)
    clients = function_hosts(root)
    for entry in load_state(root)["services"].values():
        if isinstance(entry, dict) and entry.get("kind") == "service":
            rules += resource(entry, clients)
    return rules


def cluster_balancer_rules(name: str, item: Dict[str, Any]) -> List[Rule]:
    """A cluster's own load balancer: its ports (one per deployment) and every cluster server behind it."""
    from .onprem_balancers import cluster_backends
    from .onprem_cluster import _listen_port

    own = item["balancer"]
    ports = {_listen_port(own, dep) for dep in (item.get("deployments") or {}).values()} or {int(own.get("port") or 80)}
    backends = [b for dep in (item.get("deployments") or {}).values()
                for b in cluster_backends(item, int(dep.get("port") or 8080))]
    return balancer(f"of cluster {name}", who(str(own["server"]), str(own.get("address") or "")), ports, backends)


def named_cluster_rules(lb_name: str, lb_item: Dict[str, Any], item: Dict[str, Any]) -> List[Rule]:
    from .onprem_balancers import cluster_backends

    backends = [b for dep in (item.get("deployments") or {}).values()
                for b in cluster_backends(item, int(dep.get("port") or 8080))]
    return balancer(lb_name, who(str(lb_item["server"]), str(lb_item.get("address") or "")),
                    [int(lb_item.get("port") or 80)], backends)
