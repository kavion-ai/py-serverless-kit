"""Load balancing algorithms and the OpenResty (nginx + Lua) config pskit writes for them.

Pure rendering, no SSH: ``core/onprem_balancers.py`` (named load balancers shared by projects and clusters) and
``core/onprem_cluster.py`` (a cluster's own load balancer) put these files on the load balancer server.

Six algorithms, chosen per load balancer and overridable per route:

========================  =======  ===============================================================================
``round_robin``           static   each server in turn (nginx's default)
``sticky_round_robin``    static   a client's first request picks a server; a cookie keeps it there
``weighted_round_robin``  static   in turn, ``weight`` times as often for a bigger server
``ip_hash``               static   the client address picks the server (consistent hashing)
``least_connections``     dynamic  the server with the fewest open requests (pskit's earlier only choice)
``least_time``            dynamic  the fastest server: average response time x open requests (Lua)
========================  =======  ===============================================================================

Open-source nginx has no ``sticky`` or ``least_time`` (NGINX Plus only), so: sticky hashes a cookie that holds the
first request's id (``hash ... consistent``), and least time runs ``balancer_by_lua`` with a moving average of each
server's response header time kept in a shared dict. That is why the load balancer runs OpenResty.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Sequence

LB_IMAGE = "openresty/openresty:1.27.1.2-alpine"
DEFAULT_ALGORITHM = "least_connections"  # what every load balancer used before 2.3
_ADDRESS = re.compile(r"^[A-Za-z0-9.:\[\]-]+$")
_PATH = re.compile(r"^[a-z0-9][a-z0-9._-]{0,62}(/[a-z0-9][a-z0-9._-]{0,62}){0,3}$")
_RESERVED_PATHS = ("__pskit",)

ALGORITHMS: Dict[str, Dict[str, Any]] = {
    "round_robin": {
        "label": "Round robin",
        "kind": "static",
        "summary": "Each server in turn: 1, 2, 3, 1, 2, 3 ...",
        "pros": ["Simple and predictable", "No state on the load balancer", "Even spread when servers are alike"],
        "cons": ["Ignores how busy or slow a server is", "A user's requests land on different servers"],
        "best_for": "Servers of the same size and requests that cost about the same.",
    },
    "sticky_round_robin": {
        "label": "Sticky round robin",
        "kind": "static",
        "summary": "A user's first request picks a server; a cookie sends the rest of the session there.",
        "pros": ["Keeps a session on one server (in-memory caches, uploads in parts, WebSockets)",
                 "No shared session store needed"],
        "cons": ["Uneven when a few users are very busy", "Sessions move when a server joins or leaves",
                 "Clients without cookies (scripts, some APIs) are spread like round robin"],
        "best_for": "Apps that keep per-user state in memory.",
    },
    "weighted_round_robin": {
        "label": "Weighted round robin",
        "kind": "static",
        "summary": "In turn, but a server with weight 3 gets three requests for every one of a weight 1 server.",
        "pros": ["Uses big and small servers in proportion", "Still predictable",
                 "Lets you drain a server slowly (lower its weight)"],
        "cons": ["Weights are set by hand and go stale", "Ignores live load"],
        "best_for": "Servers of different sizes (CPU cores / memory).",
    },
    "ip_hash": {
        "label": "IP hash",
        "kind": "static",
        "summary": "The client's IP address picks the server, so the same client always lands on the same one.",
        "pros": ["Sticky without cookies (works for any client)", "No state on the load balancer"],
        "cons": ["Many users behind one NAT or proxy all land on one server", "Uneven with few clients",
                 "Clients move when a server joins or leaves"],
        "best_for": "Sticky sessions for API clients and devices that do not keep cookies.",
    },
    "least_connections": {
        "label": "Least connections",
        "kind": "dynamic",
        "summary": "Each request goes to the server with the fewest requests in progress.",
        "pros": ["Adapts to live load", "Good with long or uneven requests (uploads, reports, streaming)"],
        "cons": ["Open requests are not the same as work: a fast server and a slow one look alike",
                 "Not sticky"],
        "best_for": "Mixed workloads where some requests take much longer than others.",
    },
    "least_time": {
        "label": "Least time",
        "kind": "dynamic",
        "summary": "Each request goes to the fastest server: its recent average response time x requests in progress.",
        "pros": ["Routes around slow or overloaded servers", "Best latency for users",
                 "Notices a server that slows down (GC pauses, noisy neighbours, a busy disk)"],
        "cons": ["Can pile onto one fast server until its time rises", "Not sticky",
                 "Each load balancer measures on its own"],
        "best_for": "Latency-sensitive APIs on servers that differ in speed or share hardware.",
    },
}
_ALIASES = {
    "rr": "round_robin", "roundrobin": "round_robin", "round-robin": "round_robin",
    "sticky": "sticky_round_robin", "sticky-round-robin": "sticky_round_robin", "sticky_rr": "sticky_round_robin",
    "weighted": "weighted_round_robin", "wrr": "weighted_round_robin", "weighted-round-robin": "weighted_round_robin",
    "ip": "ip_hash", "iphash": "ip_hash", "ip-hash": "ip_hash", "hash": "ip_hash",
    "least_conn": "least_connections", "leastconn": "least_connections", "least-connections": "least_connections",
    "least-conn": "least_connections",
    "leasttime": "least_time", "least-time": "least_time", "fastest": "least_time",
}


def normalize_algorithm(value: Any, *, default: str = DEFAULT_ALGORITHM) -> str:
    """``value`` (a name or alias such as ``rr``, ``least_conn``) as one of :data:`ALGORITHMS`."""
    text = str(value or "").strip().lower()
    if not text:
        return default
    name = _ALIASES.get(text, text.replace("-", "_"))
    if name not in ALGORITHMS:
        raise ValueError(f"unknown load balancing algorithm {value!r}; pick one of {', '.join(ALGORITHMS)}")
    return name


def catalog() -> List[Dict[str, Any]]:
    """The algorithms in display order, for the CLI and the studio."""
    return [{"name": name, **info} for name, info in ALGORITHMS.items()]


def normalize_path(value: Any) -> str:
    """A route path such as ``xyz`` or ``team/xyz`` (no leading or trailing slash, lowercase)."""
    text = str(value or "").strip().strip("/").lower()
    if not _PATH.match(text) or text.split("/")[0] in _RESERVED_PATHS:
        raise ValueError(f"route path {value!r}: lowercase letters, digits, . _ - (and / between parts), "
                         "starting with a letter or digit; __pskit is reserved")
    return text


def route_key(path: str = "", listen: int = 0) -> str:
    """The file name of a route on the load balancer: ``p-team-xyz`` for a path, ``port-8081`` for a port."""
    if listen:
        return f"port-{int(listen)}"
    return "p-" + re.sub(r"[^a-z0-9]+", "-", normalize_path(path)).strip("-")


def _var(key: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", key.lower()).strip("_")


def upstream_name(key: str) -> str:
    return "pskit_" + _var(key)


def hostport(address: str, port: int) -> str:
    if not _ADDRESS.match(str(address)):
        raise ValueError(f"not a server address for the load balancer: {address!r}")
    if ":" in address and not address.startswith("["):
        address = f"[{address}]"
    return f"{address}:{int(port)}"


def backend(address: str, port: int, *, weight: int = 1, backup: bool = False, server: str = "",
            per_request: bool = False) -> Dict[str, Any]:
    """``per_request``: the server picks a replica per connection (a Kubernetes node: ServiceLB / kube-proxy), so
    the load balancer opens a new connection for every request instead of reusing one (``keepalive``), which would
    pin every request to the replica that connection first reached."""
    hostport(address, port)  # validates
    weight = 1 if weight is None else int(weight)
    if not 1 <= weight <= 100:
        raise ValueError(f"weight of {server or address} must be 1..100")
    out = {"address": str(address), "port": int(port), "weight": weight, "backup": bool(backup), "server": server}
    if per_request:
        out["per_request"] = True
    return out


# ----------------------------------------------------------------------------------------------- files
NGINX_CONF = """# pskit load balancer (OpenResty). Generated by pskit; per-route files are in conf.d.
worker_processes auto;
error_log /dev/stderr warn;
pid /tmp/nginx.pid;
events {
    worker_connections 4096;
}
http {
    server_tokens off;
    default_type application/octet-stream;
    sendfile on;
    keepalive_timeout 65;
    client_body_temp_path /tmp/client_body;
    proxy_temp_path /tmp/proxy;
    fastcgi_temp_path /tmp/fastcgi;
    uwsgi_temp_path /tmp/uwsgi;
    scgi_temp_path /tmp/scgi;
    lua_package_path "/etc/nginx/pskit-lua/?.lua;;";
    lua_shared_dict pskit_lb 10m;
    init_by_lua_block {
        pskit_lb = require "pskit_lb"
    }
    log_format pskit_lb '$time_iso8601 $remote_addr port=$server_port "$request" $status $body_bytes_sent '
                        '${request_time}s upstream=$upstream_addr ${upstream_response_time}s';
    access_log /dev/stdout pskit_lb;
    map $http_upgrade $pskit_connection {
        default upgrade;
        "" "";
    }
    include /etc/nginx/conf.d/*.conf;
}
"""

# Least time: score = (average response header time + 1 ms) x (requests in progress + 1) / weight. A server never
# measured scores 0 and is tried first; a failed attempt adds a penalty to its average, so it rests while the others
# answer. Backups are used only when every primary was tried.
LUA_MODULE = """-- pskit least-time balancer. Generated by pskit.
local balancer = require "ngx.balancer"
local shared = ngx.shared.pskit_lb
local M = {}
local ALPHA = 0.3
local PENALTY = 5.0

local function avg_key(route, addr) return "t|" .. route .. "|" .. addr end
local function busy_key(route, addr) return "n|" .. route .. "|" .. addr end

function M.balance(route, peers)
    local ctx = ngx.ctx
    local tried = ctx.pskit_tried
    if not tried then
        tried = {}
        ctx.pskit_tried = tried
        ctx.pskit_order = {}
        if #peers > 1 then
            balancer.set_more_tries(math.min(2, #peers - 1))
        end
    end
    local best, best_score
    for pass = 1, 2 do
        for _, p in ipairs(peers) do
            local addr = p[1] .. ":" .. p[2]
            if ((pass == 1) ~= (p[4] == true)) and not tried[addr] then
                local avg = shared:get(avg_key(route, addr)) or 0
                local busy = shared:get(busy_key(route, addr)) or 0
                local score = (avg + 0.001) * (busy + 1) / (p[3] or 1)
                if avg == 0 then score = busy * 0.000001 end
                if not best_score or score < best_score then
                    best, best_score = p, score
                end
            end
        end
        if best then break end
    end
    if not best then best = peers[1] end
    local addr = best[1] .. ":" .. best[2]
    tried[addr] = true
    table.insert(ctx.pskit_order, addr)
    shared:incr(busy_key(route, addr), 1, 0)
    local ok, err = balancer.set_current_peer(best[1], best[2])
    if not ok then
        ngx.log(ngx.ERR, "pskit least_time: ", err)
        return ngx.exit(502)
    end
end

local function split(text)
    local out = {}
    for item in string.gmatch(text or "", "[^,:%s]+") do table.insert(out, item) end
    return out
end

function M.record(route)
    local order = ngx.ctx.pskit_order
    if not order then return end
    for _, addr in ipairs(order) do
        local n = shared:incr(busy_key(route, addr), -1, 0)
        if n and n < 0 then shared:set(busy_key(route, addr), 0) end
    end
    local times = split(ngx.var.upstream_header_time)
    local statuses = split(ngx.var.upstream_status)
    for i, addr in ipairs(order) do
        local t = tonumber(times[i] or "")
        local status = tonumber(statuses[i] or "") or 0
        local key = avg_key(route, addr)
        local old = shared:get(key)
        if not t or status >= 502 then
            shared:set(key, (old or 0) + PENALTY)
        elseif old and old > 0 then
            shared:set(key, old * (1 - ALPHA) + t * ALPHA)
        else
            shared:set(key, math.max(t, 0.0001))
        end
    end
end

return M
"""


def main_server_conf(name: str, port: int) -> str:
    """The load balancer's own port: path routes (``conf.d/routes/*.loc``) and a JSON 404 for any other path."""
    missing = json.dumps({"error": f"no project at this path on load balancer {name}"})
    info = json.dumps({"balancer": name, "routes": "/__pskit/lb/routes"})
    return (
        f"# load balancer {name}: path routes on port {int(port)}\n"
        "server {\n"
        f"    listen {int(port)} default_server;\n"
        "    client_max_body_size 100m;\n"
        "    location = /__pskit/lb {\n"
        "        default_type application/json;\n"
        f"        return 200 '{info}';\n"
        "    }\n"
        "    location = /__pskit/lb/routes {\n"
        "        default_type application/json;\n"
        "        alias /etc/nginx/pskit-routes.json;\n"
        "    }\n"
        "    include /etc/nginx/conf.d/routes/*.loc;\n"
        "    location / {\n"
        "        default_type application/json;\n"
        f"        return 404 '{missing}';\n"
        "    }\n"
        "}\n"
    )


def _hashing(algorithm: str) -> bool:
    return algorithm in ("sticky_round_robin", "ip_hash")


def upstream_conf(key: str, algorithm: str, backends: Sequence[Dict[str, Any]], *, cookie_path: str = "/") -> str:
    """``upstream`` (and for sticky, the cookie maps) of one route."""
    if not backends:
        raise ValueError(f"route {key}: no server to send requests to")
    algorithm = normalize_algorithm(algorithm)
    name = upstream_name(key)
    var = _var(key)
    head = ""
    lines: List[str] = []
    if algorithm == "least_time":
        peers = ", ".join(
            "{" + f"\"{b['address']}\", {int(b['port'])}, {int(b.get('weight') or 1)}, "
            + ("true" if b.get("backup") else "false") + "}"
            for b in backends
        )
        for b in backends:
            hostport(b["address"], b["port"])
        lines.append("    server 0.0.0.1;  # placeholder: balancer_by_lua picks the server")
        lines.append(f"    balancer_by_lua_block {{ pskit_lb.balance(\"{var}\", {{{peers}}}) }}")
    else:
        if algorithm == "sticky_round_robin":
            cookie = f"pskit_lb_{var}"
            # The first request has no cookie: its id picks the server and becomes the cookie, so later requests
            # hash to the same server. Set-Cookie goes out only then (nginx does not send an empty add_header).
            head = (
                f"map $cookie_{cookie} $pskit_sticky_{var} {{\n"
                "    \"\" $request_id;\n"
                f"    default $cookie_{cookie};\n"
                "}\n"
                f"map $cookie_{cookie} $pskit_set_{var} {{\n"
                f"    \"\" \"{cookie}=$request_id; Path={cookie_path}; HttpOnly; SameSite=Lax\";\n"
                "    default \"\";\n"
                "}\n"
            )
            lines.append(f"    hash $pskit_sticky_{var} consistent;")
        elif algorithm == "ip_hash":
            lines.append("    hash $remote_addr consistent;")
        elif algorithm == "least_connections":
            lines.append("    least_conn;")
        # Shared by every worker process: one turn order, open-request counts and failure marks for all of them.
        lines.append(f"    zone {name} 64k;")
        weighted = algorithm != "round_robin"
        for b in backends:
            params = " max_fails=3 fail_timeout=10s"
            if weighted and int(b.get("weight") or 1) != 1:
                params = f" weight={int(b['weight'])}" + params
            # nginx: `backup` cannot be used with hash; there the backup server simply shares the requests.
            if b.get("backup") and not _hashing(algorithm):
                params = " backup"
            lines.append(f"    server {hostport(b['address'], b['port'])}{params};")
    if any(b.get("per_request") for b in backends):
        lines.append("    # no keepalive: Kubernetes picks a replica per connection, so each request gets a new one")
    else:
        lines.append("    keepalive 32;")
    return f"{head}upstream {name} {{\n" + "\n".join(lines) + "\n}\n"


def proxy_directives(key: str, algorithm: str, *, prefix: str = "") -> str:
    """The body of a ``location`` that sends requests to the route's upstream."""
    algorithm = normalize_algorithm(algorithm)
    name = upstream_name(key)
    var = _var(key)
    target = f"http://{name}/" if prefix else f"http://{name}"
    out = [
        f"        proxy_pass {target};",
        "        proxy_http_version 1.1;",
        "        proxy_set_header Upgrade $http_upgrade;",
        "        proxy_set_header Connection $pskit_connection;",
        "        proxy_set_header Host $host;",
        "        proxy_set_header X-Real-IP $remote_addr;",
        "        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;",
        "        proxy_set_header X-Forwarded-Proto $scheme;",
    ]
    if prefix:
        out.append(f"        proxy_set_header X-Forwarded-Prefix /{prefix};")
    out += [
        "        proxy_connect_timeout 3s;",
        "        proxy_read_timeout 900s;",
        "        proxy_send_timeout 900s;",
        "        proxy_next_upstream error timeout http_502 http_503 http_504;",
        "        proxy_next_upstream_tries 3;",
    ]
    if algorithm == "sticky_round_robin":
        out.append(f"        add_header Set-Cookie $pskit_set_{var} always;")
    if algorithm == "least_time":
        out.append(f"        log_by_lua_block {{ pskit_lb.record(\"{var}\") }}")
    return "\n".join(out) + "\n"


def path_route_files(key: str, path: str, algorithm: str, backends: Sequence[Dict[str, Any]],
                     *, comment: str = "") -> Dict[str, str]:
    """``{conf.d/r-<key>.conf, conf.d/routes/<key>.loc}``: ``/<path>/...`` on the load balancer's port ->
    ``/...`` on the backends (the prefix is removed; ``X-Forwarded-Prefix`` carries it)."""
    path = normalize_path(path)
    head = f"# {comment}\n" if comment else ""
    location = (
        f"# /{path} {comment}\n"
        f"location = /{path} {{\n"
        f"    return 308 /{path}/$is_args$args;\n"
        "}\n"
        f"location /{path}/ {{\n"
        + proxy_directives(key, algorithm, prefix=path)
        + "}\n"
    )
    return {f"conf.d/r-{key}.conf": head + upstream_conf(key, algorithm, backends, cookie_path=f"/{path}/"),
            f"conf.d/routes/{key}.loc": location}


def port_route_conf(key: str, listen: int, algorithm: str, backends: Sequence[Dict[str, Any]],
                    *, comment: str = "") -> str:
    """One deployment on its own port of the load balancer (``listen`` -> the backends)."""
    head = f"# {comment}\n" if comment else ""
    return (
        head + upstream_conf(key, algorithm, backends)
        + "server {\n"
        f"    listen {int(listen)};\n"
        "    client_max_body_size 100m;\n"
        "    location / {\n"
        + proxy_directives(key, algorithm)
        + "    }\n"
        "}\n"
    )


def describe(algorithm: str, backends: Sequence[Dict[str, Any]]) -> str:
    """One line for logs: ``least time over 10.0.0.2:8080, 10.0.0.3:8080 (backup 10.0.0.1:8080)``."""
    algorithm = normalize_algorithm(algorithm)
    label = ALGORITHMS[algorithm]["label"].lower()
    primary = [b for b in backends if not b.get("backup")]
    backup = [b for b in backends if b.get("backup")]

    def show(b: Dict[str, Any]) -> str:
        weight = f" x{b['weight']}" if algorithm != "round_robin" and int(b.get("weight") or 1) != 1 else ""
        return (b.get("server") or b["address"]) + weight

    text = f"{label} over " + ", ".join(show(b) for b in primary)
    if backup:
        text += " (backup " + ", ".join(show(b) for b in backup) + ")"
    return text


def weights_for(servers: Sequence[str], weights: Optional[Dict[str, Any]]) -> Dict[str, int]:
    """``weights`` (server name -> 1..100) checked against ``servers``; missing servers get 1."""
    out = {s: 1 for s in servers}
    for server, value in (weights or {}).items():
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 100:
            raise ValueError(f"weight of {server} must be an integer 1..100")
        out[str(server)] = value
    return out


# ----------------------------------------------------------------------------------------------- server scripts
SECTION = "PSKIT_SECTION="
_CHECK_URL = re.compile(r"^http://127\.0\.0\.1:\d+/[A-Za-z0-9._/-]*$")
_LABEL = re.compile(r"^[A-Za-z0-9._-]+$")


def balancer_dir(name: str = "") -> str:
    """Where a load balancer keeps its files, under the folder the scripts run from (the server's home path):
    ``pskit-cluster/lb-<name>`` for a named load balancer, ``pskit-cluster/lb`` for a cluster's own one."""
    return f"pskit-cluster/lb-{name}" if name else "pskit-cluster/lb"


def container_name(name: str = "") -> str:
    return f"pskit-lb-{name}" if name else "pskit-lb"


def base_files(name: str, port: int, algorithm: str) -> Dict[str, str]:
    """The files every load balancer has: nginx.conf, the least-time Lua module, its settings and (named load
    balancers) its own port with the path routes."""
    files = {"nginx.conf": NGINX_CONF, "pskit-lua/pskit_lb.lua": LUA_MODULE,
             "lb.json": json.dumps({"name": name, "port": int(port), "algorithm": algorithm}, sort_keys=True) + "\n"}
    if name:
        files["conf.d/00-main.conf"] = main_server_conf(name, port)
    return files


def route_files(key: str) -> List[str]:
    """Every file a route can have on the load balancer server."""
    return [f"conf.d/r-{key}.conf", f"conf.d/routes/{key}.loc", f"routes/{key}.json"]


def _running(container: str) -> str:
    return f"[ \"$(dk inspect -f '{{{{.State.Running}}}}' {container} 2>/dev/null || echo false)\" = true ]"


def _mounts(folder: str) -> str:
    return (f' -v "{folder}/nginx.conf:/usr/local/openresty/nginx/conf/nginx.conf:ro"'
            f' -v "{folder}/conf.d:/etc/nginx/conf.d:ro"'
            f' -v "{folder}/pskit-lua:/etc/nginx/pskit-lua:ro"'
            f' -v "{folder}/pskit-routes.json:/etc/nginx/pskit-routes.json:ro"')


# The route list the load balancer serves at /__pskit/lb/routes: every routes/*.json in one object.
_ROUTE_INDEX = (
    '{ printf "{"; sep=""; for f in "$next"/routes/*.json; do [ -f "$f" ] || continue; k=$(basename "$f" .json);'
    " printf '%s\"%s\": ' \"$sep\" \"$k\"; tr -d '\\n' < \"$f\"; sep=', '; done; printf '}\\n'; }"
    ' > "$next/pskit-routes.json"\n'
)


def apply_script(name: str, write: Dict[str, str], remove: Sequence[str] = (), *, replace_routes: bool = False,
                 checks: Optional[Dict[str, str]] = None) -> str:
    """Runs on the load balancer server: change its files, check them with ``nginx -t``, then reload.

    ``write`` maps file paths under the load balancer's folder to their text; ``remove`` lists paths to delete
    (``replace_routes`` deletes every route first: a cluster's own load balancer is rewritten whole). The change is
    made on a copy that a throwaway container checks, so a config nginx refuses leaves the running one untouched.
    Projects changing the same load balancer at once take turns (``flock``). ``checks`` maps a label to a local
    URL; each prints ``PSKIT_LB_OK=<label>`` or ``PSKIT_LB_FAIL=<label>`` (a server still starting is no error)."""
    from .onprem_cluster_scripts import _docker_install_block, _docker_ready_block, _header

    container = container_name(name)
    for rel in list(write) + list(remove):
        if rel.startswith("/") or ".." in rel.split("/") or not re.match(r"^[A-Za-z0-9._/-]+$", rel):
            raise ValueError(f"not a load balancer file: {rel}")
    writes = ""
    for rel, text in sorted(write.items()):
        if "\nPSKIT_LB\n" in "\n" + text:
            raise ValueError(f"{rel} cannot contain a line PSKIT_LB")
        folder = rel.rsplit("/", 1)[0] if "/" in rel else ""
        writes += (f'mkdir -p "$next/{folder}"\n' if folder else "") + f"cat > \"$next/{rel}\" <<'PSKIT_LB'\n{text}PSKIT_LB\n"
    removes = "".join(f'rm -f "$next/{rel}"\n' for rel in sorted(remove))
    if replace_routes:
        removes = 'rm -f "$next"/conf.d/*.conf "$next"/conf.d/routes/*.loc "$next"/routes/*.json\n' + removes
    script = (
        _header() + _docker_install_block() + _docker_ready_block()
        + f'lb="$(pwd)/{balancer_dir(name)}"\n'
        + 'mkdir -p "$lb/conf.d/routes" "$lb/routes" "$lb/pskit-lua"\n'
        + 'if need flock; then exec 9>"$lb/.lock"; flock -w 300 9 2>/dev/null || flock 9 || true; fi\n'
        + '[ -f "$lb/pskit-routes.json" ] || echo "{}" > "$lb/pskit-routes.json"\n'
        + '[ -f "$lb/nginx.conf" ] || : > "$lb/nginx.conf"\n'
        + 'next="$lb/next"\nrm -rf "$next"\nmkdir -p "$next"\n'
        + 'for d in conf.d routes pskit-lua; do cp -R "$lb/$d" "$next/$d"; done\n'
        + 'cp "$lb/nginx.conf" "$next/nginx.conf"\n'
        + removes + writes + _ROUTE_INDEX
        + f"dk image inspect {LB_IMAGE} >/dev/null 2>&1 || dk pull {LB_IMAGE} >/dev/null\n"
        + f'if ! pskit_test=$(dk run --rm{_mounts("$next")} {LB_IMAGE} nginx -t 2>&1); then\n'
        + '  echo "$pskit_test" >&2\n'
        + '  echo "pskit: nginx refused the new load balancer config; the running one is unchanged" >&2\n'
        + '  rm -rf "$next"\n  exit 1\nfi\n'
        # Files are replaced inside the mounted folders, and mounted files are rewritten in place (same inode),
        # so the container's bind mounts keep seeing them.
        + 'for d in conf.d/routes conf.d routes pskit-lua; do\n'
          '  for f in "$lb/$d"/*; do if [ -f "$f" ]; then rm -f "$f"; fi; done\n'
          '  for f in "$next/$d"/*; do if [ -f "$f" ]; then cp "$f" "$lb/$d/"; fi; done\n'
          'done\n'
        + 'cat "$next/nginx.conf" > "$lb/nginx.conf"\ncat "$next/pskit-routes.json" > "$lb/pskit-routes.json"\n'
        + 'if [ -f "$next/lb.json" ]; then cp "$next/lb.json" "$lb/lb.json"; fi\n'
        + 'rm -rf "$next"\n'
        + f"image=$(dk inspect -f '{{{{.Config.Image}}}}' {container} 2>/dev/null || true)\n"
        + f'if {_running(container)} && [ "$image" = "{LB_IMAGE}" ]; then\n'
        + f"  dk exec {container} nginx -s reload\n"
        + "else\n"
        + f"  dk rm -f {container} >/dev/null 2>&1 || true\n"
        + f'  dk run -d --name {container} --restart unless-stopped --network host{_mounts("$lb")} {LB_IMAGE} >/dev/null\n'
        + "fi\nsleep 1\n"
        + f"if ! {_running(container)}; then\n"
        + f"  dk logs --tail 30 {container} >&2 || true\n"
        + '  echo "pskit: the load balancer container is not running (is the port in use?)" >&2\n'
        + "  exit 1\nfi\n"
    )
    for label, url in sorted((checks or {}).items()):
        if not _CHECK_URL.match(url) or not _LABEL.match(label):
            raise ValueError(f"bad load balancer check {label}: {url}")
        script += (
            "pskit_ok=0\npskit_i=0\n"
            'while [ "$pskit_i" -lt 10 ]; do\n'
            f'  if curl -fsS -m 3 "{url}" >/dev/null 2>&1; then pskit_ok=1; break; fi\n'
            "  pskit_i=$((pskit_i + 1))\n  sleep 2\ndone\n"
            f'if [ "$pskit_ok" = 1 ]; then echo "PSKIT_LB_OK={label}"; else echo "PSKIT_LB_FAIL={label}"; fi\n'
        )
    return script + "echo PSKIT_LB_DONE=1\n"


def read_script(name: str) -> str:
    """Prints the load balancer's settings, every route (one JSON line each) and its container state."""
    container = container_name(name)
    fmt = "'{{.State.Status}}'"
    return (
        "#!/bin/sh\n"
        f'lb="$(pwd)/{balancer_dir(name)}"\n'
        f'echo "{SECTION}lb"\ncat "$lb/lb.json" 2>/dev/null\necho\n'
        f'echo "{SECTION}routes"\n'
        "for f in \"$lb\"/routes/*.json; do if [ -f \"$f\" ]; then tr -d '\\n' < \"$f\"; echo; fi; done\n"
        f'echo "{SECTION}state"\n'
        f"docker inspect -f {fmt} {container} 2>/dev/null || sudo -n docker inspect -f {fmt} {container} 2>/dev/null"
        " || echo missing\n"
    )


def remove_script(name: str) -> str:
    """Stop and remove the load balancer's container and its files."""
    from .onprem_cluster_scripts import _header

    return _header() + (f"dk rm -f {container_name(name)} >/dev/null 2>&1 || true\n"
                        f'rm -rf "$(pwd)/{balancer_dir(name)}"\n')


def logs_script(name: str, lines: int) -> str:
    """The access log (one line per request, with the server that answered: ``upstream=``) and nginx errors."""
    from .onprem_cluster_scripts import _header

    return _header() + f"dk logs --tail {int(lines)} {container_name(name)} 2>&1\n"


def state_command(name: str = "") -> str:
    """One line: the container's state (running, exited, ...) or ``missing``."""
    container = container_name(name)
    fmt = "'{{.State.Status}}'"
    return (f"docker inspect -f {fmt} {container} 2>/dev/null"
            f" || sudo -n docker inspect -f {fmt} {container} 2>/dev/null || echo missing")
