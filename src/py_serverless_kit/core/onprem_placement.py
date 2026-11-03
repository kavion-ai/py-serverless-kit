"""Function placement on premises: groups of functions on different servers (or clusters), one project.

``provider.options.placement`` in pskit.yml::

    placement:
      default: api                     # functions not listed (and every workflow) run here
      groups:
        api:   {server: app1}          # saved server; or {cluster: prod}, or {local: true} (this machine)
        gpu:   {server: gpu1, functions: [resize, ocr]}   # advertise: http://... when its address differs
        batch: {cluster: {name: prod, replicas: 3}, functions: [report], port: 8090}

Each group is its own host (process, container or cluster stack) with only its functions, their code and the
requirements of their sub-folders (``functions/<name>/requirements.txt`` / ``package.json``), so a server installs
only what its functions need. The hosts are independent and find each other through a peer map in their
``pskit_host.json`` (``runtime/peers.py``):

* ``invoke("resize", ...)``, a workflow step, an HTTP route or a trigger of a function in another group goes over
  HTTP to that group's host (``/__pskit/peer/<function>``), with a shared peer token;
* a built-in queue, bucket or SMTP server belongs to the group of the function it triggers (queues and buckets
  nobody consumes belong to the default group); other groups send and read through that host. A topic delivers
  to every group with a subscriber;
* workflows run on the default group (executions, logs and the studio stay in one place); their steps run
  wherever their functions are;
* other groups ship logs and invocation counts to the default group, so ``pskit logs`` and the studio see all.

The default group keeps the stage's usual paths (``onprem_app/``, unit ``pskit-<service>-<stage>``, Terraform
``terraform_data.host``), so adding placement to a deployed stage moves nothing. Group ``gpu`` gets
``onprem_app_gpu/``, unit ``pskit-<service>-<stage>-gpu`` and ``terraform_data.host_gpu``.
"""

from __future__ import annotations

import copy
import re
import secrets
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

GROUP_RE = re.compile(r"^[a-z][a-z0-9-]{0,20}$")
TARGET_KEYS = ("server", "cluster", "local")
GROUP_KEYS = set(TARGET_KEYS) | {"functions", "port", "advertise"}
TOKEN_FILE = "peer-token"  # noqa: S105 - a file name: .pskit/onprem-<stage>/peer-token (out of git)
# What a group's own pskit.yml options may not repeat (they come from its target).
_TARGET_DEPLOY_KEYS = ("server", "host", "user", "port", "pem", "identity_file", "identity", "password_file", "auth",
                       "known_hosts", "docker_host")


class PlacementError(ValueError):
    pass


def configured(options: Dict[str, Any]) -> bool:
    raw = options.get("placement")
    return isinstance(raw, dict) and bool(raw.get("groups"))


def parse(raw: Any, functions: List[str], workflows: Optional[List[str]] = None) -> Dict[str, Any]:
    """``{default, groups: {name: {target: {kind: value}, functions: [...], port?}}, function_group: {fn: group}}``.

    ``functions`` are the project's (enabled) function names; generated workflow orchestrators
    (``<workflow>-orchestrator``) always belong to the default group."""
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise PlacementError("options.placement must be a mapping with `groups` (and optionally `default`)")
    unknown = sorted(set(raw) - {"default", "groups", "gateway", "_groups"})  # _groups: resolved (resolve())
    if unknown:
        raise PlacementError(f"unknown options.placement keys {unknown}; expected default, groups, gateway")
    if raw.get("gateway") not in (None, True, False):
        raise PlacementError("options.placement.gateway is true or false")
    groups_raw = raw.get("groups")
    if not isinstance(groups_raw, dict) or not groups_raw:
        raise PlacementError("options.placement.groups must name at least one group: {api: {server: app1}}")
    default = str(raw.get("default") or next(iter(groups_raw)))
    if default not in groups_raw:
        raise PlacementError(f"options.placement.default {default!r} is not one of the groups"
                             f" ({', '.join(groups_raw)})")
    known = set(functions)
    orchestrators = {f"{w}-orchestrator" for w in workflows or []}
    function_group: Dict[str, str] = {}
    groups: Dict[str, Dict[str, Any]] = {}
    for name, body in groups_raw.items():
        where = f"options.placement.groups.{name}"
        if not GROUP_RE.match(str(name)):
            raise PlacementError(f"{where}: a group name is a lowercase letter, then letters, digits or - (max 21)")
        body = {} if body is None else body
        if not isinstance(body, dict):
            raise PlacementError(f"{where} must be a mapping such as {{server: app1, functions: [a, b]}}")
        bad = sorted(set(body) - GROUP_KEYS)
        if bad:
            raise PlacementError(f"{where}: unknown keys {bad}; expected server, cluster or local, functions, port,"
                                 " advertise")
        targets = [k for k in TARGET_KEYS if body.get(k) not in (None, "", False)]
        if len(targets) > 1:
            raise PlacementError(f"{where}: pick one of server, cluster or local")
        if not targets and name != default:
            raise PlacementError(f"{where} needs where it runs: server: NAME, cluster: NAME or local: true")
        target: Dict[str, Any] = {}
        if targets:
            kind = targets[0]
            value = body[kind]
            if kind == "server" and not isinstance(value, str):
                raise PlacementError(f"{where}.server is the name of a saved server")
            if kind == "cluster" and not isinstance(value, (str, dict)):
                raise PlacementError(f"{where}.cluster is a cluster name or {{name: prod, replicas: 3}}")
            target = {kind: value if kind != "local" else True}
        port = body.get("port")
        if port is not None and (isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535):
            raise PlacementError(f"{where}.port must be a port 1..65535")
        listed = body.get("functions") or []
        if isinstance(listed, str):
            listed = [listed]
        if not isinstance(listed, list):
            raise PlacementError(f"{where}.functions is a list of function names")
        for fn in listed:
            fn = str(fn)
            if fn in orchestrators:
                raise PlacementError(f"{where}: {fn} orchestrates a workflow; workflows run on the default group"
                                     f" ({default}), their steps run wherever their functions are")
            if fn not in known:
                raise PlacementError(f"{where}: no function {fn!r} (functions: {', '.join(sorted(known)) or 'none'})")
            if fn in function_group:
                raise PlacementError(f"function {fn} is in two groups: {function_group[fn]} and {name}")
            function_group[fn] = str(name)
        advertise = body.get("advertise")
        if advertise is not None and not str(advertise).lower().startswith(("http://", "https://")):
            raise PlacementError(f"{where}.advertise is the URL the other groups call, http://HOST:PORT")
        groups[str(name)] = {"target": target, "functions": [str(f) for f in listed],
                             **({"port": port} if port is not None else {}),
                             **({"advertise": str(advertise)} if advertise else {})}
    for fn in sorted(known | orchestrators):
        function_group.setdefault(fn, default)
    for name, group in groups.items():
        group["functions"] = sorted(f for f, g in function_group.items() if g == name)
    return {"default": default, "groups": groups, "function_group": function_group,
            **({"gateway": raw["gateway"]} if raw.get("gateway") is not None else {})}


def gateway(parsed: Dict[str, Any], options: Dict[str, Any], balanced: Any = False) -> Any:
    """Which other groups' routes a group answers, passing them on: ``True`` (every group: one URL for the
    project), a list of group names, or ``False`` (each server answers only the routes of the functions it runs).
    ``placement.gateway``; unset: on with ``options.balancer`` (it sends a request to any group's servers). Else
    ``balanced``: ``True``, or the groups behind the same load balancer as this one (:func:`balanced_peers`), since
    a load balancer attached to a cluster reaches only that cluster's servers."""
    if "gateway" in parsed:
        return bool(parsed["gateway"])
    if options.get("balancer") not in (None, "", False):
        return True
    if isinstance(balanced, (list, tuple, set)):
        return sorted(str(g) for g in balanced) or False
    return bool(balanced)


def _balancer_keys(root: Path, cluster: str, saved: Dict[str, Any]) -> set:
    """The load balancers in front of ``cluster``: its own, and every named one attached to it."""
    from .onprem_balancers import attached_to

    if not cluster:
        return set()
    keys = {f"lb:{n}" for n in attached_to(root, cluster)}
    if isinstance((saved.get(cluster) or {}).get("balancer"), dict):
        keys.add(f"own:{cluster}")
    return keys


def balanced_peers(root: Path, group_clusters: Dict[str, str]) -> Dict[str, List[str]]:
    """``{group: [other groups behind a load balancer this group is behind]}`` from each group's cluster (``""``
    for a group on a server). A group not behind a load balancer gets ``[]``."""
    from .onprem_cluster import load_clusters

    try:
        saved = load_clusters(root)
        keys = {g: _balancer_keys(root, c, saved) for g, c in group_clusters.items()}
    except Exception:  # noqa: BLE001 - unreadable saved state: no load balancer
        return {g: [] for g in group_clusters}
    return {g: sorted(o for o in group_clusters if o != g and keys[g] & keys[o]) for g in group_clusters}


def behind_balancer(root: Path, clusters: List[str]) -> bool:
    """Whether one of ``clusters`` has its own load balancer or is attached to a named one."""
    from .onprem_cluster import load_clusters

    try:
        saved = load_clusters(root)
        return any(_balancer_keys(root, c, saved) for c in clusters)
    except Exception:  # noqa: BLE001 - unreadable saved state: no load balancer
        return False


def group_stage(stage: str, group: str, default: str) -> str:
    """The stage name that keys a group's unit, paths and container: the stage itself for the default group."""
    return stage if group == default else f"{stage}-{group}"


def app_dir(group: str, default: str) -> str:
    return "onprem_app" if group == default else f"onprem_app_{group.replace('-', '_')}"


def resource_name(group: str, default: str) -> str:
    return "host" if group == default else f"host_{group.replace('-', '_')}"


def group_data_dir(data_dir: str, group: str) -> str:
    """``<data_dir>/groups/<group>``: a group's queues, buckets and logs, inside the default group's data dir."""
    sep = "\\" if "\\" in data_dir and "/" not in data_dir else "/"
    return data_dir.rstrip("/\\") + f"{sep}groups{sep}{group}"


def group_options(options: Dict[str, Any], group: str, body: Dict[str, Any], default: str) -> Dict[str, Any]:
    """The provider options one group deploys with: pskit.yml's, without placement, with the group's target."""
    out = copy.deepcopy({k: v for k, v in options.items() if k != "placement"})
    target = body.get("target") or {}
    if group != default:
        out.pop("advertise", None)  # pskit.yml's advertise URL is the default group's
    if body.get("port"):
        out["port"] = int(body["port"])
    if body.get("advertise"):
        out["advertise"] = body["advertise"]
    if not target:  # the default group without a target: pskit.yml's deploy / cluster, --server, the last deploy
        return out
    deploy = out.get("deploy")
    kept = {k: v for k, v in deploy.items() if k not in _TARGET_DEPLOY_KEYS} if isinstance(deploy, dict) else {}
    if group != default:
        kept.pop("path", None)  # each group gets its own folder on a shared server
        kept.pop("container", None)
        kept.pop("name", None)
    out.pop("cluster", None)
    if "server" in target:
        method = str(kept.get("method") or "")
        out["deploy"] = {**kept, "server": str(target["server"]),
                         **({"method": method} if method in ("ssh", "scp", "docker") else {})}
    elif "cluster" in target:
        out["deploy"] = kept
        out["cluster"] = copy.deepcopy(target["cluster"])
    else:
        out["deploy"] = {**kept, "method": "local"}
    return out


def resolve(options: Dict[str, Any], root: Path, stage: str, server: Optional[str] = None,
            cluster: Optional[str] = None) -> None:
    """Resolve every group's target in place: ``options.placement._groups = {group: options}``.

    ``server`` / ``cluster`` (``--server`` / ``--cluster``) move the default group only; the other groups always
    run where pskit.yml puts them. The top-level ``options.deploy`` / ``cluster`` become the default group's, so
    logs, tests and the studio reach the default host as before."""
    from .onprem_servers import resolve_deploy

    raw = options.get("placement")
    names = list((raw or {}).get("groups") or {}) if isinstance(raw, dict) else []
    parsed = parse(raw, _fn_names_from(raw), [])  # targets only; functions are checked in validation
    default = parsed["default"]
    resolved: Dict[str, Dict[str, Any]] = {}
    for name in names:
        body = parsed["groups"][name]
        opts = group_options(options, name, body, default)
        if name == default:
            resolve_deploy(opts, root, stage, server, cluster)
        else:
            resolve_deploy(opts, root, group_stage(stage, name, default))
        if name != default and opts.get("data_dir"):
            # pskit.yml's data_dir (or the saved server's): each group keeps its own state in a folder inside it.
            # Never beside it: a saved server's data_dir is often the home folder, and its parent (/home) is not
            # writable.
            opts["data_dir"] = group_data_dir(str(opts["data_dir"]), name)
        resolved[name] = opts
    seen: Dict[Tuple[str, int], str] = {}
    for name, opts in resolved.items():
        raw_deploy = opts.get("deploy")
        deploy: Dict[str, Any] = raw_deploy if isinstance(raw_deploy, dict) else {}
        where = str(deploy.get("server") or deploy.get("host") or ("local" if not opts.get("cluster") else ""))
        if not where:
            continue
        spot = (where, int(opts.get("port") or 8080))
        if spot in seen:
            raise PlacementError(f"groups {seen[spot]} and {name} both run on {where} port {spot[1]}: give one its"
                                 f" own port (options.placement.groups.{name}.port: {spot[1] + 1})")
        seen[spot] = name
    default_opts = resolved[default]
    for key in ("deploy", "cluster", "host", "data_dir"):
        if key in default_opts:
            options[key] = copy.deepcopy(default_opts[key])
        else:
            options.pop(key, None)
    options["placement"] = {**dict(raw or {}), "_groups": resolved}


def _fn_names_from(raw: Any) -> List[str]:
    out: List[str] = []
    for body in ((raw or {}).get("groups") or {}).values() if isinstance(raw, dict) else []:
        listed = (body or {}).get("functions") if isinstance(body, dict) else None
        out.extend(str(f) for f in ([listed] if isinstance(listed, str) else listed or []))
    return out


def owners(config: Any, function_group: Dict[str, str], default: str,
           routed: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """Which group keeps each built-in queue, bucket, topic and SMTP server, and errors for ones that cannot be
    kept in one place. ``routed`` maps resource keys to their on-prem driver (only builtin / directory ones are
    routed; redis, sqs, s3, ... are reached directly from every group)."""
    out: Dict[str, Any] = {}
    errors: List[str] = []

    def builtin(kind: str, name: str, resource: str = "") -> bool:
        driver = routed.get(resource) or routed.get(f"{kind}:{name}") or {}
        return str(driver.get("use") or "builtin") in ("builtin", "directory")

    for fn_name, fn in config.functions.items():
        if not getattr(fn, "enabled", True):
            continue
        group = function_group.get(fn_name, default)
        for ev in fn.events:
            body = ev.config
            if ev.type == "queue" and builtin("queue", body.name, getattr(body, "resource", "") or ""):
                key = f"queue:{body.name}"
                if out.setdefault(key, group) != group:
                    errors.append(f"queue {body.name} triggers functions in groups {out[key]} and {group}: keep its"
                                  " consumers in one group, or give it a shared driver (redis, sqs)")
                dead = getattr(body, "dead_letter", None)
                if dead:
                    dead_name = config.resources[dead].native_name(dead) if dead in config.resources else dead
                    out.setdefault(f"queue:{dead_name}", group)
            elif ev.type == "storage" and builtin("storage", body.bucket, getattr(body, "resource", "") or ""):
                key = f"storage:{body.bucket}"
                if out.setdefault(key, group) != group:
                    errors.append(f"bucket {body.bucket} triggers functions in groups {out[key]} and {group}: keep"
                                  " them in one group, or give it a shared driver (s3, minio)")
            elif ev.type == "topic":
                groups = out.setdefault(f"topic:{body.name}", [])
                if group not in groups:
                    groups.append(group)
            elif ev.type == "smtp":
                server = str(getattr(body, "resource", "") or getattr(body, "name", "") or "")
                groups = out.setdefault(f"smtp:{server}", [])
                if group not in groups:
                    groups.append(group)
    for key, res in config.resources.items():
        if res.type in ("queue", "storage", "topic") and builtin(res.type, res.native_name(key), key):
            name = res.native_name(key)
            if res.type == "topic":
                out.setdefault(f"topic:{name}", [])
            else:
                out.setdefault(f"{res.type}:{name}", default)
    for key, value in out.items():
        if isinstance(value, list):
            out[key] = sorted(value)
    return out, errors


def peer_token(root: Path, stage: str) -> str:
    """The hosts' shared secret for ``onprem-<stage>``: made once, kept in ``.pskit`` (out of git) so a deploy
    from the same project always renders the same token."""
    path = Path(root) / ".pskit" / f"onprem-{stage}" / TOKEN_FILE
    try:
        token = path.read_text("utf-8").strip()
    except OSError:
        token = ""
    if not re.match(r"^[A-Za-z0-9_-]{32,}$", token):
        token = secrets.token_urlsafe(32)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(token.encode("utf-8"))
        try:
            path.chmod(0o600)
        except OSError:
            pass
    return token
