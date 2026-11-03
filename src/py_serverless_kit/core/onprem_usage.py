"""Where each saved on-prem server is used, how the machines connect, and which functions really use a resource.

Studio: *Servers → Used in* (and the *Forget* confirmation), the *Network map* page, and the *Bound to* column of
*Resources*. CLI: ``pskit resources onprem servers usage [NAME]``.

Only the files pskit keeps are read (``pskit.yml``, ``.pskit/onprem-*.json`` and the deploy records); nothing runs
over SSH, so this is instant and works while servers are down.

A *use* is one place that names a server::

    {"kind": "cluster", "name": "prod", "role": "master", "detail": "Docker Swarm, 3 servers",
     "functions": ["api", "report"], "view": "cluster"}

``kind`` is one of ``deploy`` (pskit.yml deploys there), ``deployed`` (a stage last went there), ``placement`` (a
function group), ``cluster`` (master or joined server), ``cluster-balancer`` (a cluster's own load balancer),
``balancer`` (a named load balancer runs there), ``service`` (a one-click service or a member of a replicated
database) and ``runtime`` (software pskit installed). ``view`` is the studio page that manages it.

The network map turns the firewall rules (``core/onprem_network.py``) into edges ``from → to`` on a port, so each
server's inbound and outbound connections are what has to be open for the project to work.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

Use = Dict[str, Any]

KINDS = ("deploy", "deployed", "placement", "cluster", "cluster-balancer", "balancer", "service", "runtime")
SPECIAL = ("users", "internet", "admin")  # firewall sources that are not machines


def _obj(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _onprem_options(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """``provider.options`` of an onprem pskit.yml, or ``providers.onprem`` overrides of another one."""
    provider = _obj(_obj(raw).get("provider"))
    options: Dict[str, Any] = {}
    if provider.get("name") == "onprem":
        options.update(_obj(provider.get("options")))
    block = _obj(_obj(_obj(raw).get("providers")).get("onprem"))
    options.update(_obj(block.get("options")))
    options.update(_obj(_obj(block.get("provider")).get("options")))
    return options


def _user_functions(raw: Optional[Dict[str, Any]]) -> List[str]:
    functions = (raw or {}).get("functions")
    return sorted(str(k) for k in functions) if isinstance(functions, dict) else []


def _name_of(value: Any) -> str:
    """``prod`` or ``{name: prod, replicas: 3}`` -> ``prod``."""
    if isinstance(value, dict):
        return str(value.get("name") or "")
    return str(value or "")


def _placement_groups(options: Dict[str, Any], functions: List[str]) -> Dict[str, Dict[str, Any]]:
    """``{group: {server|cluster|local, functions}}``, with the functions each group really gets."""
    from . import onprem_placement as placement

    raw = options.get("placement")
    if not placement.configured(options):
        return {}
    try:
        parsed = placement.parse(raw, functions)
    except Exception:  # noqa: BLE001 - an invalid placement still names its servers
        out_raw: Dict[str, Dict[str, Any]] = {}
        for name, body in _obj(_obj(raw).get("groups")).items():
            body = _obj(body)
            listed = body.get("functions")
            out_raw[str(name)] = {**body, "functions": [str(f) for f in listed] if isinstance(listed, list) else []}
        return out_raw
    out: Dict[str, Dict[str, Any]] = {}
    for name, group in parsed["groups"].items():
        functions_of = [f for f in group["functions"] if not f.endswith("-orchestrator")]
        out[name] = {**group["target"], "functions": functions_of, "default": name == parsed["default"]}
    return out


def _records(root: Path) -> List[Dict[str, Any]]:
    """Every on-prem stage's deploy record: ``{stage, server, cluster, groups}``."""
    from .onprem_servers import DEPLOYED_FILE

    out: List[Dict[str, Any]] = []
    pskit = Path(root) / ".pskit"
    for path in sorted(pskit.glob(f"onprem-*/{DEPLOYED_FILE}")) if pskit.is_dir() else []:
        try:
            data = json.loads(path.read_text("utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        groups: Dict[str, Any] = {}
        try:
            record = json.loads((path.parent / "deployment.json").read_text("utf-8"))
            if isinstance(record, dict) and isinstance(record.get("groups"), dict):
                groups = record["groups"]
        except (OSError, ValueError):
            pass
        out.append({"stage": path.parent.name[len("onprem-"):], "server": str(data.get("server") or ""),
                    "cluster": str(data.get("cluster") or ""), "groups": groups})
    return out


def _resource_functions(raw: Optional[Dict[str, Any]], key: str) -> List[str]:
    """Functions that get resource ``key``: its ``functions:`` list, else every function."""
    res = ((raw or {}).get("resources") or {}).get(key) if isinstance((raw or {}).get("resources"), dict) else None
    if not isinstance(res, dict):
        return []
    listed = res.get("functions")
    if isinstance(listed, list):
        return sorted(str(f) for f in listed)
    return _user_functions(raw)


def server_usage(root: Path, raw: Optional[Dict[str, Any]] = None) -> Dict[str, List[Use]]:
    """``{server: [use, ...]}`` for every saved server (an empty list: not used anywhere), plus any server name
    that is used but no longer saved."""
    from .onprem_balancers import load_balancers
    from .onprem_cluster import ORCHESTRATORS, load_clusters
    from .onprem_servers import load_servers
    from .onprem_services import load_state

    root = Path(root)
    out: Dict[str, List[Use]] = {name: [] for name in sorted(load_servers(root))}

    def add(server: str, use: Use) -> None:
        if server and server != "local":
            out.setdefault(server, []).append(use)

    functions = _user_functions(raw)
    options = _onprem_options(raw)
    stage = str(((raw or {}).get("provider") or {}).get("stage") or "dev") if isinstance(raw, dict) else "dev"
    clusters = load_clusters(root)

    # pskit.yml: where the functions deploy, and the function groups.
    deploy = options.get("deploy")
    deploy_server = str(deploy.get("server") or "") if isinstance(deploy, dict) else ""
    configured_cluster = _name_of(options.get("cluster"))
    groups = _placement_groups(options, functions)
    if deploy_server and not configured_cluster and not groups:
        add(deploy_server, {"kind": "deploy", "name": "pskit.yml", "role": "deploy target",
                            "detail": f"provider.options.deploy.server: every function of stage {stage} runs here",
                            "functions": functions, "view": "overview"})
    for group, body in sorted(groups.items()):
        fns = list(body.get("functions") or [])
        detail = f"function group {group}" + (" (default: workflows and unlisted functions)" if body.get("default") else "")
        if body.get("server"):
            add(str(body["server"]), {"kind": "placement", "name": group, "role": "function group",
                                      "detail": detail, "functions": fns, "view": "functions"})
        elif body.get("cluster"):
            cname = _name_of(body["cluster"])
            for node in sorted((clusters.get(cname) or {}).get("nodes") or {}):
                add(node, {"kind": "placement", "name": group, "role": f"function group on cluster {cname}",
                           "detail": detail, "functions": fns, "view": "functions"})

    # Where each stage was last deployed.
    records = _records(root)
    for rec in records:
        if rec["cluster"]:
            continue  # shown with the cluster
        if rec["groups"]:
            for group, body in sorted(rec["groups"].items()):
                if isinstance(body, dict) and body.get("server"):
                    add(str(body["server"]), {
                        "kind": "deployed", "name": f"onprem-{rec['stage']}", "role": f"group {group} deployed",
                        "detail": str(body.get("endpoint") or ""),
                        "functions": [str(f) for f in body.get("functions") or []], "view": "deploy"})
        elif rec["server"]:
            add(rec["server"], {"kind": "deployed", "name": f"onprem-{rec['stage']}", "role": "functions deployed",
                                "detail": f"stage {rec['stage']} was last deployed here", "functions": functions,
                                "view": "deploy"})

    # Scaling clusters: master, joined servers, the cluster's own load balancer.
    for cname, item in sorted(clusters.items()):
        nodes = item.get("nodes") or {}
        orch = ORCHESTRATORS.get(str(item.get("orchestrator") or ""), {}).get("label", str(item.get("orchestrator") or ""))
        stacks = sorted(item.get("deployments") or {})
        uses_cluster = configured_cluster == cname or any(r["cluster"] == cname for r in records) or any(
            _name_of(g.get("cluster")) == cname for g in groups.values())
        fns = functions if uses_cluster and not groups else sorted(
            {f for g in groups.values() if _name_of(g.get("cluster")) == cname for f in g.get("functions") or []})
        for node in sorted(nodes):
            role = "master" if node == item.get("master") else "joined server"
            detail = f"{orch}, {len(nodes)} server(s)" + (f"; deployments: {', '.join(stacks)}" if stacks else "")
            add(node, {"kind": "cluster", "name": cname, "role": role, "detail": detail, "functions": fns,
                       "view": "cluster"})
        balancer = item.get("balancer")
        if isinstance(balancer, dict) and balancer.get("server"):
            add(str(balancer["server"]), {
                "kind": "cluster-balancer", "name": cname, "role": "cluster load balancer",
                "detail": f"{balancer.get('algorithm') or 'least_connections'} over {len(nodes)} server(s)",
                "functions": fns, "view": "cluster"})

    # Named load balancers.
    lb_name = _name_of(options.get("balancer"))
    for name, item in sorted(load_balancers(root).items()):
        attached = sorted(item.get("clusters") or [])
        parts = [f"port {item.get('port') or 80}", f"algorithm {item.get('algorithm') or 'least_connections'}"]
        if attached:
            parts.append(f"clusters {', '.join(attached)}")
        if lb_name == name:
            parts.append("this project's functions are routed through it")
        add(str(item.get("server") or ""), {"kind": "balancer", "name": name, "role": "load balancer",
                                            "detail": "; ".join(parts),
                                            "functions": functions if lb_name == name else [],
                                            "view": "balancers"})

    # One-click services (single server or every member of a replicated database) and installed runtimes.
    for key, entry in sorted(load_state(root).get("services", {}).items()):
        if not isinstance(entry, dict):
            continue
        service = str(entry.get("service") or "")
        if entry.get("kind") == "runtime":
            add(str((entry.get("target") or {}).get("server") or ""), {
                "kind": "runtime", "name": key, "role": "installed",
                "detail": f"{service} {entry.get('version') or ''}".strip(), "functions": [], "view": "resources"})
            continue
        fns = _resource_functions(raw, key)
        topo = entry.get("topology")
        if isinstance(topo, dict) and topo.get("mode") == "replicated":
            members = [m for m in topo.get("members") or [] if isinstance(m, dict)]
            if isinstance(topo.get("balancer"), dict):
                members.append(topo["balancer"])
            for m in members:
                role = {"primary": "primary", "replica": "read replica", "balancer": "database load balancer"}.get(
                    str(m.get("role") or ""), str(m.get("role") or "member"))
                add(str(m.get("server") or ""), {
                    "kind": "service", "name": key, "role": role,
                    "detail": f"{service} on port {m.get('port')}", "functions": fns, "view": "resources"})
            continue
        add(str((entry.get("target") or {}).get("server") or ""), {
            "kind": "service", "name": key, "role": str(entry.get("role") or "service"),
            "detail": f"{service} on port {entry.get('port')}" if entry.get("port") else service,
            "functions": fns, "view": "resources"})
    return out


def describe(use: Use) -> str:
    """One line for the CLI and the remove warnings."""
    text = f"{use['kind']} {use['name']}: {use['role']}"
    if use.get("detail"):
        text += f" ({use['detail']})"
    if use.get("functions"):
        text += f"; functions: {', '.join(use['functions'])}"
    return text


# ----------------------------------------------------------------------------------------------- network map
def network_map(root: Path, raw: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """``{nodes, edges}``: every saved server (used or not), the machines and sources the firewall rules name,
    and one edge per rule and source, ``from`` the connecting side ``to`` the side that has to accept it."""
    from . import onprem_network as network
    from .onprem_servers import load_servers

    root = Path(root)
    usage = server_usage(root, raw)
    saved = load_servers(root)
    nodes: Dict[str, Dict[str, Any]] = {}

    def node(name: str, address: str = "") -> None:
        kind = name if name in SPECIAL else "server" if name in saved else "host"
        item = nodes.setdefault(name, {"id": name, "kind": kind, "address": "", "saved": name in saved,
                                       "roles": sorted({u["role"] for u in usage.get(name, [])}),
                                       "uses": len(usage.get(name, []))})
        item["address"] = item["address"] or address or str((saved.get(name) or {}).get("host") or "")

    for name in usage:
        node(name)
    edges: List[Dict[str, Any]] = []
    error = ""
    try:
        rules = network.merge(network.project(root))
    except Exception as exc:  # noqa: BLE001 - a broken state file must not hide the servers
        rules, error = [], f"connections not shown: {exc.__class__.__name__}: {exc}"
    for r in rules:
        node(r["server"], r["address"])
        for s in r["sources"]:
            other = str(s.get("name") or "")
            if not other:
                continue
            node(other, str(s.get("address") or ""))
            inbound = r["direction"] == "inbound"
            edges.append({"from": other if inbound else r["server"], "to": r["server"] if inbound else other,
                          "port": r["port"], "proto": r["proto"], "why": r["why"], "level": r["level"]})
    order = {"admin": 0, "users": 1, "internet": 3}
    return {"nodes": sorted(nodes.values(), key=lambda n: (order.get(n["kind"], 2), n["id"])), "edges": edges,
            **({"error": error} if error else {})}


# ----------------------------------------------------------------------------------------------- resources
_CODE_SUFFIXES = (".py", ".js", ".mjs", ".cjs", ".ts", ".mts", ".cts")


def _handler_files(source: Path, handler: str) -> List[Path]:
    """The file ``module.function`` points at, and the function's own folder (``functions/<name>/``) if any."""
    module = handler.replace(":", ".").rsplit(".", 1)[0]
    base = source.joinpath(*module.split("."))
    found = [base.with_suffix(s) for s in _CODE_SUFFIXES if base.with_suffix(s).is_file()]
    found += [base / f"__init__{s}" for s in (".py",) if (base / f"__init__{s}").is_file()]
    found += [base / f"index{s}" for s in _CODE_SUFFIXES if (base / f"index{s}").is_file()]
    return found


def _mentions(text: str, key: str) -> bool:
    """``resource("key")`` / ``resource('key')`` or ``PSKIT_RESOURCE_<KEY>_`` in the code."""
    from ..config.schema import env_key

    quoted = re.escape(key)
    if re.search(r"""resource\s*\(\s*["']""" + quoted + r"""["']""", text):
        return True
    return f"PSKIT_RESOURCE_{env_key(key)}_" in text


def resource_bindings(root: Path, raw: Optional[Dict[str, Any]] = None) -> Dict[str, Dict[str, Any]]:
    """``{key: {restricted, bound, triggers, code, used_by}}`` per resource in pskit.yml.

    ``bound``: the functions that get its variables (``functions:``, else all of them); ``triggers``: functions
    with an event on it; ``code``: functions whose handler file calls ``resource("key")`` or reads
    ``PSKIT_RESOURCE_<KEY>_*``; ``used_by``: triggers and code together, the functions that really use it."""
    root = Path(root)
    resources = _obj(_obj(raw).get("resources"))
    functions = _obj(_obj(raw).get("functions"))
    package = _obj(_obj(raw).get("package"))
    source = root / str(package.get("source") or ".")
    texts: Dict[str, str] = {}
    for fn, body in functions.items():
        handler = str((body or {}).get("handler") or "") if isinstance(body, dict) else ""
        chunks = []
        for path in _handler_files(source, handler) if handler else []:
            try:
                chunks.append(path.read_text("utf-8", errors="replace"))
            except OSError:
                pass
        texts[str(fn)] = "\n".join(chunks)
    out: Dict[str, Dict[str, Any]] = {}
    for key, res in resources.items():
        key = str(key)
        res = res if isinstance(res, dict) else {}
        listed = res.get("functions")
        restricted = isinstance(listed, list)
        bound = sorted(str(f) for f in (listed if isinstance(listed, list) else functions))
        triggers = sorted(
            str(fn) for fn, body in functions.items() if isinstance(body, dict) and any(
                isinstance(ev, dict) and any(isinstance(c, dict) and c.get("resource") == key for c in ev.values())
                for ev in body.get("events") or []))
        code = sorted(fn for fn, text in texts.items() if text and _mentions(text, key))
        out[key] = {"restricted": restricted, "bound": bound, "triggers": triggers, "code": code,
                    "used_by": sorted(set(triggers) | set(code))}
    return out
