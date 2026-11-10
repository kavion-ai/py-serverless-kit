"""Replicated databases: one primary that takes the writes, read replicas on other servers, and an optional load
balancer that gives the functions a single address and splits reads from writes.

A database service is created on a single server (:mod:`onprem_services`) or, with ``topology.mode: replicated``,
as a group of containers this module starts and records under the service's state entry (``topology``):

=============  ============================  ===================================  ===============================
engine         replication                   sync (commit waits for a replica)    one address for the functions
=============  ============================  ===================================  ===============================
PostgreSQL     streaming replication (WAL)   ``synchronous_standby_names``        pgpool-II (reads to replicas)
MySQL          GTID replication              semi-synchronous plugin              ProxySQL (SELECT to replicas)
MariaDB        GTID replication              built-in semi-synchronous            ProxySQL (SELECT to replicas)
MongoDB        replica set                   write concern ``majority``           the driver (replica set URL)
=============  ============================  ===================================  ===============================

Every member is a saved SSH server (one member per server), or every member runs on this machine (each on its own
port, on a private Docker network) to try it out. Replicas are added and removed later with :func:`add_replica` and
:func:`remove_replica`; the load balancer and the env file follow. The handler code never changes: the resource's
``url_env`` points at the load balancer (or the primary), ``<KEY>_WRITE_URL`` at the primary and ``<KEY>_READ_URLS``
at the replicas.

``topology.failover: auto`` promotes a replica when the primary stops answering (MongoDB already elects one).
``topology.write: multi`` (MySQL and MariaDB) lets every member accept writes. PostgreSQL stays one primary.

Only ``docker`` and ``ssh`` commands run, as everywhere in on-prem services. Secrets travel as container environment
variables (masked in the job log), never inside a command line.
"""

from __future__ import annotations

import base64
import re
import secrets
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple
from urllib.parse import quote

Emit = Callable[[str], None]
RunFn = Callable[[List[str], Optional[Path]], Tuple[int, str]]

LOCAL = "local"
SYNC_MODES = ("async", "sync")
MAX_REPLICAS = 9
REPL_USER = "pskit_repl"
PGPOOL_IMAGE = "bitnamilegacy/pgpool:4.6.3"
PROXYSQL_IMAGE = "proxysql/proxysql:2.7.3"

# What the studio shows for each engine (catalog item ``replication``).
ENGINES: Dict[str, Dict[str, Any]] = {
    "postgres": {
        "method": "Streaming replication (WAL)",
        "balancer": "pgpool-II",
        "balancer_image": PGPOOL_IMAGE,
        "balancer_port": 6432,
        "balancer_container_port": 5432,
        "async": "The primary commits at once and streams the WAL to the replicas, which follow a few milliseconds "
                 "behind. Fastest; a crash of the primary can lose the last transactions not yet streamed.",
        "sync": "A commit waits until at least one replica has the WAL on disk (synchronous_standby_names = "
                "ANY 1 (*)). No committed write is lost, but writes wait while no replica is connected.",
        "routing": "pgpool-II sends writes and transactions to the primary and spreads plain SELECTs over the "
                   "replicas (the primary only when none is up).",
    },
    "mysql": {
        "method": "GTID replication (binary log)",
        "balancer": "ProxySQL",
        "balancer_image": PROXYSQL_IMAGE,
        "balancer_port": 6033,
        "balancer_container_port": 6033,
        "async": "The primary commits at once; replicas apply the binary log right after. Fastest; a crash of the "
                 "primary can lose the last transactions.",
        "sync": "Semi-synchronous: a commit waits until one replica has received it (back to async after 10 s "
                "without a replica, so writes never hang).",
        "routing": "ProxySQL sends writes, transactions and SELECT ... FOR UPDATE to the primary and other SELECTs "
                   "to the replicas (the primary only when none is up).",
    },
    "mariadb": {
        "method": "GTID replication (binary log)",
        "balancer": "ProxySQL",
        "balancer_image": PROXYSQL_IMAGE,
        "balancer_port": 6033,
        "balancer_container_port": 6033,
        "async": "The primary commits at once; replicas apply the binary log right after. Fastest; a crash of the "
                 "primary can lose the last transactions.",
        "sync": "Semi-synchronous: a commit waits until one replica has received it (back to async after 10 s "
                "without a replica, so writes never hang).",
        "routing": "ProxySQL sends writes, transactions and SELECT ... FOR UPDATE to the primary and other SELECTs "
                   "to the replicas (the primary only when none is up).",
    },
    "mongodb": {
        "method": "Replica set",
        "balancer": "",
        "balancer_port": 0,
        "async": "Write concern w: 1: a write is acknowledged by the primary alone; secondaries copy the oplog right "
                 "after. A crash of the primary can roll back the last writes.",
        "sync": "Write concern w: majority: a write is acknowledged once most members have it, so it survives the "
                "loss of the primary.",
        "routing": "No load balancer: the MongoDB driver connects to every member from one replica set URL, writes "
                   "to the primary and reads from secondaries (readPreference=secondaryPreferred). If the primary "
                   "fails, the members elect a new one and the driver follows.",
    },
}


class _Ctx:
    """What one operation needs: the service module, a command runner and the job's emit."""

    def __init__(self, emit: Emit, run: Optional[RunFn]) -> None:
        from . import onprem_services as svc

        self.svc = svc
        self.emit = emit
        self.run = run
        self.sh = svc._Runner(emit, run)

    def docker(self, target: Dict[str, Any], args: Sequence[str], **kw: Any) -> str:
        return str(self.sh(self.svc.docker_argv(target, list(args)), **kw))

    def code(self, target: Dict[str, Any], args: Sequence[str]) -> Tuple[int, str]:
        return self.sh.run_fn(self.svc.docker_argv(target, list(args)), None)


def _error(message: str) -> Exception:
    from .onprem_services import ServiceError

    return ServiceError(message)


def supports(service: str) -> bool:
    return service in ENGINES


def catalog_info(service: str) -> Optional[Dict[str, Any]]:
    """The ``replication`` block of a catalog item (None: single server only)."""
    eng = ENGINES.get(service)
    if not eng:
        return None
    info = {k: eng[k] for k in ("method", "balancer", "balancer_port", "async", "sync", "routing")}
    info["local"] = service != "mongodb"      # every member on this machine (to try it out)
    info["multi"] = service in ("mysql", "mariadb")
    info["failover_always"] = service == "mongodb"
    if service == "mongodb":
        info["failover_note"] = "Members elect a new primary themselves, and the driver follows."
        info["multi_note"] = "A replica set has one primary. That election covers a dead primary."
    elif service == "postgres":
        info["failover_note"] = (
            "Off keeps the primary you picked. Auto promotes a replica when that primary stops answering. "
            "With pgpool-II, new writes go to the promoted member. Without it, the functions' URL stays "
            "the old primary until you redeploy."
        )
        info["multi_note"] = "Streaming replication has one primary. Use automatic failover if that primary dies."
    else:
        info["failover_note"] = (
            "Off keeps the primary you picked. Auto promotes a replica when that primary stops answering. "
            "With ProxySQL, new writes go to the promoted member. Without it, the functions' URL stays "
            "the old primary until you redeploy."
        )
        info["multi_note"] = "Every member accepts writes (circular GTID). Two members changing the same row can diverge."
    return info


def is_replicated(body_or_entry: Dict[str, Any]) -> bool:
    topo = body_or_entry.get("topology")
    return isinstance(topo, dict) and str(topo.get("mode") or "single") == "replicated"


# ----------------------------------------------------------------------------------------------- plan


def _ident(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", text)


def _member(svc: Any, req: Dict[str, Any], root: Path, *, role: str, index: int, server: str, port: int,
            network: str) -> Dict[str, Any]:
    spec = svc.SERVICES[req["service"]]
    if index == 0:
        name, container = "primary", req["container"]
    elif role == "primary":
        name = f"p{index}"
        container = f"{req['container']}-{name}"
    else:
        name = f"r{index}"
        container = f"{req['container']}-{name}"
    if server == LOCAL:
        target: Dict[str, Any] = {"method": "local"}
        address, bind = "127.0.0.1", "127.0.0.1"
        link_host, link_port = container, int(spec["port"])      # members talk on the private network
    else:
        target = svc.normalize_target({"server": server}, root)
        address = str(target["host"])
        bind = str(target.get("bind") or "0.0.0.0")  # noqa: S104 - the other members connect to it
        if bind == "127.0.0.1":
            raise _error(f"server {server!r} keeps services on 127.0.0.1 (its bind setting), so the other members "
                         "cannot reach this one; change the server's bind or pick another server")
        link_host, link_port = address, port
    return {
        "name": name,
        "role": role,
        "index": index,
        "server": "" if server == LOCAL else server,
        "target": target,
        "address": address,
        "port": port,
        "bind": bind,
        "link_host": link_host,
        "link_port": link_port,
        "container": container,
        "volume": svc.data_mount(target, container),
        "network": network,
    }


def _balancer(svc: Any, req: Dict[str, Any], root: Path, server: str, port: int, network: str) -> Dict[str, Any]:
    eng = ENGINES[req["service"]]
    container = f"{req['container']}-lb"
    if server == LOCAL:
        target: Dict[str, Any] = {"method": "local"}
        address, bind = "127.0.0.1", "127.0.0.1"
    else:
        target = svc.normalize_target({"server": server}, root)
        address = str(target["host"])
        bind = str(target.get("bind") or "0.0.0.0")  # noqa: S104 - the functions connect to it
    return {"name": "lb", "role": "balancer", "server": "" if server == LOCAL else server, "target": target,
            "address": address, "port": port, "bind": bind, "container": container, "image": eng["balancer_image"],
            "kind": eng["balancer"], "network": network}


def _int(value: Any, what: str) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise _error(f"{what} must be a number") from None
    if not 1 <= number <= 65535:
        raise _error(f"{what} must be between 1 and 65535")
    return number


def check(body: Dict[str, Any], req: Dict[str, Any], root: Path) -> Dict[str, Any]:
    """``req`` (from :func:`onprem_services.check_request`) with the replicated topology planned: members,
    load balancer, and the target / address / port the functions use. No SSH."""
    from . import onprem_services as svc

    topo = body.get("topology")
    if not isinstance(topo, dict):
        raise _error("topology must be an object: {mode, sync, primary, replicas, balancer}")
    mode = str(topo.get("mode") or "single")
    if mode == "single":
        return req
    if mode != "replicated":
        raise _error("topology.mode must be single or replicated")
    service = req["service"]
    label = svc.SERVICES[service]["label"]
    if service not in ENGINES:
        raise _error(f"{label} runs on a single server here; replication is available for "
                     "PostgreSQL, MySQL, MariaDB and MongoDB")
    if req.get("role") != "database":
        raise _error("only a database is replicated")
    sync = str(topo.get("sync") or "async")
    if sync not in SYNC_MODES:
        raise _error("topology.sync must be async or sync")
    failover = str(topo.get("failover") or "off").strip() or "off"
    write = str(topo.get("write") or "single").strip() or "single"
    if failover not in ("off", "auto"):
        raise _error("topology.failover must be off or auto")
    if write not in ("single", "multi"):
        raise _error("topology.write must be single or multi")
    if service == "postgres" and write == "multi":
        raise _error("PostgreSQL streaming replication has one primary; use automatic failover (failover: auto)")
    if service == "mongodb":
        if write == "multi":
            raise _error("a MongoDB replica set has one primary; it already elects a new one if that primary dies")
        failover = "auto"
    primary = str(topo.get("primary") or "").strip()
    if not primary:
        raise _error("topology.primary: the saved server that takes the writes (or local for this machine)")
    replicas = topo.get("replicas")
    if isinstance(replicas, str):
        replicas = [replicas]
    if isinstance(replicas, int) and primary == LOCAL:
        replicas = [LOCAL] * replicas
    if not isinstance(replicas, list) or not replicas or not all(isinstance(r, str) and r.strip() for r in replicas):
        raise _error("topology.replicas: at least one server for a read replica")
    replicas = [r.strip() for r in replicas]
    if len(replicas) > MAX_REPLICAS:
        raise _error(f"at most {MAX_REPLICAS} replicas")
    local = primary == LOCAL
    if local and any(r != LOCAL for r in replicas):
        raise _error("on this machine every member runs here: replicas must all be local too")
    if not local and LOCAL in replicas:
        raise _error("a replica on this machine cannot follow a primary on a server; pick saved servers")
    if not local:
        seen = [primary, *replicas]
        dup = sorted({s for s in seen if seen.count(s) > 1})
        if dup:
            raise _error(f"one member per server: {', '.join(dup)} is used twice (a replica on the primary's "
                         "server protects nothing)")
    if local and service == "mongodb":
        raise _error("a MongoDB replica set needs servers: its members are reached at the same addresses from the "
                     "functions and from each other. Pick saved servers, or a single server here")
    eng = ENGINES[service]
    balancer = str(topo.get("balancer") or "").strip()
    if balancer and not eng["balancer"]:
        raise _error(f"{label} needs no load balancer: the driver connects to the replica set; leave balancer empty")
    if balancer and local and balancer != LOCAL:
        raise _error("with every member on this machine, the load balancer runs here too (balancer: local)")
    if balancer == LOCAL and not local:
        raise _error("the load balancer must run on a server the functions reach; pick a saved server")
    port = int(req["port"])
    network = f"{req['container']}-net" if local else ""
    multi = write == "multi"
    members = [_member(svc, req, root, role="primary", index=0, server=primary, port=port, network=network)]
    for i, server in enumerate(replicas, start=1):
        members.append(_member(svc, req, root, role="primary" if multi else "replica", index=i, server=server,
                               port=port + i if local else port, network=network))
    lb: Optional[Dict[str, Any]] = None
    if balancer:
        lb_port = _int(topo.get("balancer_port") or eng["balancer_port"], "topology.balancer_port")
        used = {(m["server"], m["port"]) for m in members}
        if (("" if balancer == LOCAL else balancer), lb_port) in used:
            raise _error(f"port {lb_port} is a database port on {balancer}; pick another balancer_port")
        lb = _balancer(svc, req, root, balancer, lb_port, network)
        if failover == "auto" and service in ("mysql", "mariadb") and not local:
            # The watcher and ProxySQL admin share this network. It is not published to the host.
            lb["network"] = f"{req['container']}-lb"
    first = members[0]
    out = dict(req)
    out.update({
        "target": first["target"],
        "volume": first["volume"],
        "data_dir": str(first["target"].get("data_dir") or ""),
        "bind": first["bind"],
        "address": lb["address"] if lb else first["address"],
        "port": lb["port"] if lb else first["port"],
        "address_auto": True,
        "topology": {
            "mode": "replicated",
            "engine": service,
            "sync": sync,
            "failover": failover,
            "write": write,
            "local": local,
            "network": network,
            "replica_set": f"rs_{_ident(req['key'])}" if service == "mongodb" else "",
            "members": members,
            "balancer": lb,
            "next_index": len(members),
        },
    })
    return out


# ----------------------------------------------------------------------------------------------- engines


def _primary_of(topo: Dict[str, Any]) -> Dict[str, Any]:
    return next(m for m in topo["members"] if m["role"] == "primary")


def _replicas_of(topo: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [m for m in topo["members"] if m["role"] == "replica"]


def _server_args(service: str, topo: Dict[str, Any], member: Dict[str, Any]) -> List[str]:
    """mysqld / mariadbd / postgres arguments of a member.

    With ``write: single`` (the default) the arguments are unchanged: server-id 1 on the primary and 101+ on
    replicas, replicas read-only. ``write: multi`` gives every member its own server-id, circular GTID and
    auto-increment offsets so two primaries do not mint the same ids.
    """
    sync = topo["sync"] == "sync"
    primary = member["role"] == "primary"
    multi = topo.get("write") == "multi"
    if service == "postgres":
        # Sync is switched on once a replica follows (_sync_on): set at start, the image's first-run setup would
        # wait forever for a replica.
        return ["postgres", "-c", "wal_level=replica", "-c", "max_wal_senders=16", "-c", "wal_keep_size=1GB",
                "-c", "hot_standby=on", "-c", f"cluster_name={member['name']}"]
    if multi:
        count = sum(1 for item in topo["members"] if item["role"] == "primary") or 1
        server_id = 1 + int(member["index"])
    else:
        count = 1
        server_id = 1 if primary else 100 + int(member["index"])
    args = [f"--server-id={server_id}", "--log-bin=mysql-bin", "--binlog-format=ROW", "--relay-log=relay-bin"]
    if service == "mysql":
        args += ["--gtid-mode=ON", "--enforce-gtid-consistency=ON", "--loose-mysql-native-password=ON"]
        if multi:
            args += ["--log-replica-updates=ON"]
        if sync and multi:
            args += ["--plugin-load-add=semisync_source.so", "--loose-rpl-semi-sync-source-enabled=1",
                     "--loose-rpl-semi-sync-source-timeout=10000",
                     "--plugin-load-add=semisync_replica.so", "--loose-rpl-semi-sync-replica-enabled=1"]
        elif sync:
            args += (["--plugin-load-add=semisync_source.so", "--loose-rpl-semi-sync-source-enabled=1",
                      "--loose-rpl-semi-sync-source-timeout=10000"] if primary else
                     ["--plugin-load-add=semisync_replica.so", "--loose-rpl-semi-sync-replica-enabled=1"])
    else:
        args += ["--log-slave-updates=ON"]
        if sync and multi:
            args += ["--rpl-semi-sync-master-enabled=ON", "--rpl-semi-sync-master-timeout=10000",
                     "--rpl-semi-sync-slave-enabled=ON"]
        elif sync:
            args += (["--rpl-semi-sync-master-enabled=ON", "--rpl-semi-sync-master-timeout=10000"] if primary else
                     ["--rpl-semi-sync-slave-enabled=ON"])
    if multi:
        args += [f"--auto-increment-increment={count}", f"--auto-increment-offset={int(member['index']) + 1}"]
    elif not primary:
        args += ["--read-only=ON"]
    return args


_MONGO_START = (
    'printf "%s" "$PSKIT_RS_SECRET_KEY" > /etc/pskit-rs.key && chmod 400 /etc/pskit-rs.key && '
    "chown 999:999 /etc/pskit-rs.key && exec docker-entrypoint.sh mongod --replSet \"$PSKIT_RS_NAME\" "
    "--keyFile /etc/pskit-rs.key --bind_ip_all"
)


def _launch(service: str, topo: Dict[str, Any], member: Dict[str, Any], secret: Dict[str, str]
            ) -> Tuple[List[str], List[str], Dict[str, str]]:
    """(``--entrypoint`` args, command, extra env) of a member's container."""
    if service == "mongodb":
        env = {"PSKIT_RS_SECRET_KEY": secret["keyfile"], "PSKIT_RS_NAME": topo["replica_set"]}
        return ["--entrypoint", "sh"], ["-c", _MONGO_START], env
    return [], _server_args(service, topo, member), {}


def _mysql_users_sql(service: str) -> str:
    """Replication / monitor user, the same on every member (replicas run it with sql_log_bin=0)."""
    if service == "mysql":
        ident = "IDENTIFIED WITH mysql_native_password BY"
        app = "ALTER USER '$MYSQL_USER'@'%' IDENTIFIED WITH mysql_native_password BY '$MYSQL_PASSWORD';"
    else:
        ident, app = "IDENTIFIED BY", ""
    return (f"CREATE USER IF NOT EXISTS '{REPL_USER}'@'%' {ident} '$PSKIT_REPL_PASSWORD'; "
            f"ALTER USER '{REPL_USER}'@'%' {ident} '$PSKIT_REPL_PASSWORD'; "
            f"GRANT REPLICATION SLAVE, REPLICATION CLIENT ON *.* TO '{REPL_USER}'@'%'; {app}")


def _primary_setup(service: str, topo: Dict[str, Any]) -> Tuple[List[str], str]:
    """(``docker exec`` options, ``sh -c`` script) run in the primary once it is ready."""
    if service == "postgres":
        script = (  # the role name is a constant; the password comes from the container environment
            "set -e\n"  # noqa: S608
            'q() { psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "$1"; }\n'
            f"if [ \"$(q \"SELECT 1 FROM pg_roles WHERE rolname='{REPL_USER}'\")\" = 1 ]; "
            f"then q \"ALTER ROLE {REPL_USER} WITH REPLICATION LOGIN PASSWORD '$PSKIT_REPL_PASSWORD'\" >/dev/null; "
            f"else q \"CREATE ROLE {REPL_USER} WITH REPLICATION LOGIN PASSWORD '$PSKIT_REPL_PASSWORD'\" >/dev/null; fi\n"
            "grep -q 'pskit replication' \"$PGDATA/pg_hba.conf\" || "
            f"echo 'host replication {REPL_USER} all scram-sha-256 # pskit replication' >> \"$PGDATA/pg_hba.conf\"\n"
            'q "SELECT pg_reload_conf()" >/dev/null\n'
            f"echo 'replication user {REPL_USER} ready'\n"
        )
        return [], script
    if service in ("mysql", "mariadb"):
        client = "mysql" if service == "mysql" else "mariadb"
        root_pw = "MYSQL_ROOT_PASSWORD" if service == "mysql" else "MARIADB_ROOT_PASSWORD"
        sql = _mysql_users_sql(service)
        if service == "mariadb":
            sql = sql.replace("$MYSQL_USER", "$MARIADB_USER").replace("$MYSQL_PASSWORD", "$MARIADB_PASSWORD")
        script = f'set -e\nexport MYSQL_PWD="${root_pw}"\n{client} -uroot -e "{sql}"\necho "replication user {REPL_USER} ready"\n'
        return [], script
    # MongoDB: start the replica set with the primary alone (replicas join one by one), then the write concern.
    primary = _primary_of(topo)
    concern = '"majority"' if topo["sync"] == "sync" else "1"
    js = (
        f'const host = "{primary["link_host"]}:{primary["link_port"]}";\n'
        "try { rs.status(); print('replica set already started'); }\n"
        f'catch (e) {{ rs.initiate({{_id: "{topo["replica_set"]}", members: [{{_id: 0, host: host, priority: 2}}]}}); }}\n'
        "for (let i = 0; i < 90 && !db.hello().isWritablePrimary; i++) sleep(1000);\n"
        "if (!db.hello().isWritablePrimary) throw new Error('the member did not become primary');\n"
        f"db.adminCommand({{setDefaultRWConcern: 1, defaultWriteConcern: {{w: {concern}}}}});\n"
        "print('primary ' + host + ' ready');\n"
    )
    return ["-e", f"PSKIT_JS={js}"], _MONGOSH


# Retried: the image's first-run mongod (no users yet, answers ping) runs before the real one, and the script is
# safe to repeat.
_MONGOSH = ('i=0; until OUT=$(mongosh --quiet -u "$MONGO_INITDB_ROOT_USERNAME" -p "$MONGO_INITDB_ROOT_PASSWORD" '
            '--authenticationDatabase admin --eval "$PSKIT_JS" 2>&1); do i=$((i+1)); '
            'if [ $i -ge 45 ]; then echo "$OUT"; exit 1; fi; sleep 2; done; echo "$OUT"')


def _pg_seed_script(primary: Dict[str, Any], data: str) -> str:
    """A fresh replica's data directory: a copy of the primary (pg_basebackup -R writes standby.signal)."""
    return (
        "set -e\n"
        f"D={data}\n"
        'if [ -f "$D/standby.signal" ]; then echo "replica data kept (already following the primary)"; exit 0; fi\n'
        'mkdir -p "$D"; find "$D" -mindepth 1 -delete\n'
        'chown postgres:postgres "$D"; chmod 700 "$D"\n'
        "if command -v su-exec >/dev/null 2>&1; then R=su-exec; else R=gosu; fi\n"
        f'PGPASSWORD="$PSKIT_REPL_PASSWORD" $R postgres pg_basebackup -h {primary["link_host"]} '
        f'-p {primary["link_port"]} -U {REPL_USER} -D "$D" -R -X stream\n'
        "echo 'copied the primary'\n"
    )


def _mysql_replica_script(service: str, primary: Dict[str, Any]) -> str:
    """Run in a new replica: copy the primary's databases, then follow it from that point (GTID)."""
    host, port = primary["link_host"], primary["link_port"]
    users = _mysql_users_sql(service)
    schemas = ("SELECT GROUP_CONCAT(schema_name SEPARATOR ' ') FROM information_schema.schemata WHERE schema_name "
               "NOT IN ('mysql','information_schema','performance_schema','sys')")
    if service == "mysql":
        return (
            "set -e\n"
            'export MYSQL_PWD="$MYSQL_ROOT_PASSWORD"\n'
            f'R="-h {host} -P {port} -uroot --get-server-public-key"\n'
            f'mysql -uroot -e "SET sql_log_bin=0; {users}"\n'
            'mysql -uroot -e "STOP REPLICA; RESET REPLICA ALL;" 2>/dev/null || true\n'
            'mysql -uroot -e "RESET BINARY LOGS AND GTIDS" 2>/dev/null || mysql -uroot -e "RESET MASTER"\n'
            f'DBS=$(mysql $R -N -e "{schemas}")\n'
            'if [ -n "$DBS" ] && [ "$DBS" != NULL ]; then\n'
            "  echo \"copying $DBS from the primary\"\n"
            "  mysqldump $R --single-transaction --set-gtid-purged=ON --routines --triggers --events "
            "--databases $DBS | mysql -uroot\n"
            "else\n"
            '  G=$(mysql $R -N -e "SELECT @@GLOBAL.gtid_executed" | tr -d "\\n")\n'
            '  mysql -uroot -e "SET GLOBAL gtid_purged=\'$G\'"\n'
            "fi\n"
            f"mysql -uroot -e \"CHANGE REPLICATION SOURCE TO SOURCE_HOST='{host}', SOURCE_PORT={port}, "
            f"SOURCE_USER='{REPL_USER}', SOURCE_PASSWORD='$PSKIT_REPL_PASSWORD', SOURCE_AUTO_POSITION=1, "
            'GET_SOURCE_PUBLIC_KEY=1; START REPLICA;"\n'
            "echo 'following the primary'\n"
        )
    users = users.replace("$MYSQL_USER", "$MARIADB_USER").replace("$MYSQL_PASSWORD", "$MARIADB_PASSWORD")
    return (
        "set -e\n"
        'export MYSQL_PWD="$MARIADB_ROOT_PASSWORD"\n'
        f'R="-h {host} -P {port} -uroot"\n'
        f'mariadb -uroot -e "SET sql_log_bin=0; {users}"\n'
        'mariadb -uroot -e "STOP SLAVE; RESET SLAVE ALL;" 2>/dev/null || true\n'
        f'DBS=$(mariadb $R -N -e "{schemas}")\n'
        'if [ -n "$DBS" ] && [ "$DBS" != NULL ]; then\n'
        "  echo \"copying $DBS from the primary\"\n"
        "  mariadb-dump $R --single-transaction --gtid --master-data=1 --routines --triggers --events "
        "--databases $DBS | mariadb -uroot\n"
        "else\n"
        '  G=$(mariadb $R -N -e "SELECT @@GLOBAL.gtid_binlog_pos")\n'
        '  mariadb -uroot -e "SET GLOBAL gtid_slave_pos=\'$G\'"\n'
        "fi\n"
        f"mariadb -uroot -e \"CHANGE MASTER TO MASTER_HOST='{host}', MASTER_PORT={port}, "
        f"MASTER_USER='{REPL_USER}', MASTER_PASSWORD='$PSKIT_REPL_PASSWORD', MASTER_USE_GTID=slave_pos; "
        'START SLAVE;"\n'
        "echo 'following the primary'\n"
    )


def _sync_on(ctx: _Ctx, topo: Dict[str, Any]) -> None:
    """PostgreSQL in sync mode: from now on a commit waits for one replica (kept across restarts)."""
    primary = _primary_of(topo)
    script = ('psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "ALTER SYSTEM SET '
              "synchronous_standby_names = 'ANY 1 (*)'\" -c 'SELECT pg_reload_conf()' >/dev/null && "
              "echo 'sync replication on: a commit waits for one replica'")
    _exec(ctx, primary["target"], primary["container"], [], script, {})


def _mongo_add_js(member: Dict[str, Any], wait: int) -> str:
    return (
        f'const host = "{member["link_host"]}:{member["link_port"]}";\n'
        "if (!rs.conf().members.some((m) => m.host === host)) rs.add({host: host, priority: 1});\n"
        "let state = '';\n"
        f"for (let i = 0; i < {int(wait)}; i++) {{\n"
        "  const m = rs.status().members.find((x) => x.name === host);\n"
        "  state = m ? m.stateStr : '';\n"
        "  if (state === 'SECONDARY') break;\n"
        "  sleep(1000);\n"
        "}\n"
        "print(host + ' is ' + (state || 'joining') + (state === 'SECONDARY' ? '' : ' (still copying the data)'));\n"
    )


def _mongo_remove_js(member: Dict[str, Any]) -> str:
    return (f'const host = "{member["link_host"]}:{member["link_port"]}";\n'
            "if (rs.conf().members.some((m) => m.host === host)) rs.remove(host);\n"
            "print('removed ' + host + ' from the replica set');\n")


def _replication_report(service: str) -> Tuple[List[str], str]:
    """``docker exec`` options and script that print the replication state, run on the primary."""
    if service == "postgres":
        return [], ('psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -P pager=off -c "SELECT application_name AS replica, '
                    "client_addr, state, sync_state, replay_lag FROM pg_stat_replication ORDER BY 1\"")
    if service == "mysql":
        return [], ('MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot -e "SELECT @@hostname AS primary_host, '
                    '@@gtid_executed AS executed_gtids; SHOW REPLICAS;"')
    if service == "mariadb":
        return [], ('MYSQL_PWD="$MARIADB_ROOT_PASSWORD" mariadb -uroot -e "SELECT @@gtid_binlog_pos AS '
                    'binlog_position; SHOW SLAVE HOSTS;"')
    js = ("rs.status().members.forEach((m) => print(m.name + '  ' + m.stateStr + "
          "(m.optimeDate ? '  last write ' + m.optimeDate.toISOString() : '')));")
    return ["-e", f"PSKIT_JS={js}"], _MONGOSH


def _replica_lag_script(service: str) -> str:
    """Run in a replica: how far behind the primary it is."""
    if service == "postgres":
        return ('psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "SELECT CASE WHEN pg_is_in_recovery() THEN '
                "'replica, ' || COALESCE('last change replayed ' || EXTRACT(EPOCH FROM now() - "
                "pg_last_xact_replay_timestamp())::int || ' s ago', 'no change replayed yet') ELSE 'not a replica' END\"")
    if service == "mysql":
        return ('MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot -e "SHOW REPLICA STATUS\\G" | grep -E '
                "'Replica_IO_Running:|Replica_SQL_Running:|Seconds_Behind_Source:|Last_.*Error:' || true")
    if service == "mariadb":
        return ('MYSQL_PWD="$MARIADB_ROOT_PASSWORD" mariadb -uroot -e "SHOW SLAVE STATUS\\G" | grep -E '
                "'Slave_IO_Running:|Slave_SQL_Running:|Seconds_Behind_Master:|Last_.*Error:' || true")
    return ""


# ----------------------------------------------------------------------------------------------- load balancer


def _pgpool_args(req: Dict[str, Any], topo: Dict[str, Any], lb: Dict[str, Any], password: str,
                 secret: Dict[str, str]) -> List[str]:
    nodes, names = [], []
    multi = topo.get("write") == "multi"
    for i, m in enumerate(topo["members"]):
        # Reads go to replicas (the primary when none is up). Multi-primary: every member takes reads and writes.
        weight = 1 if multi else (0 if m["role"] == "primary" else 1)
        nodes.append(f"{i}:{m['link_host']}:{m['link_port']}:{weight}")
        names.append(m["name"])
    user = str(req.get("user") or "pskit")
    env = {
        "PGPOOL_BACKEND_NODES": ",".join(nodes),
        "PGPOOL_BACKEND_APPLICATION_NAMES": ",".join(names),
        "PGPOOL_AUTO_FAILBACK": "yes",
        "PGPOOL_SR_CHECK_USER": user,
        "PGPOOL_SR_CHECK_PASSWORD": password,
        "PGPOOL_POSTGRES_USERNAME": user,
        "PGPOOL_POSTGRES_PASSWORD": password,
        "PGPOOL_ADMIN_USERNAME": "pskit_admin",
        "PGPOOL_ADMIN_PASSWORD": secret["admin_password"],
        "PGPOOL_ENABLE_LOAD_BALANCING": "yes",
        "PGPOOL_SR_CHECK_PERIOD": "5",
    }
    if topo.get("failover") == "auto":
        # Health checks only when failover is on, so the default pgpool command line stays the same.
        env["PGPOOL_HEALTH_CHECK_USER"] = user
        env["PGPOOL_HEALTH_CHECK_PASSWORD"] = password
        env["PGPOOL_HEALTH_CHECK_PERIOD"] = "10"
        env["PGPOOL_HEALTH_CHECK_MAX_RETRIES"] = "2"
        env["PGPOOL_HEALTH_CHECK_RETRY_DELAY"] = "5"
        env["PGPOOL_FAILOVER_ON_BACKEND_ERROR"] = "on"
        env["PSKIT_REPL_PASSWORD"] = secret["replication_password"]
    argv = _lb_head(req, lb)
    for k, v in env.items():
        argv += ["-e", f"{k}={v}"]
    return [*argv, lb["image"]]


def proxysql_config(req: Dict[str, Any], topo: Dict[str, Any], password: str, secret: Dict[str, str]) -> str:
    """ProxySQL's configuration: writes to hostgroup 10 (the primary), SELECTs to 20 (replicas, the primary as a
    last resort with weight 1)."""
    multi = topo.get("write") == "multi"
    # Admin listens on the Docker network only when a watcher must reach it. It is not published to the host.
    admin_iface = "0.0.0.0:6032" if topo.get("failover") == "auto" else "127.0.0.1:6032"  # noqa: S104
    servers = []
    for m in topo["members"]:
        if multi:
            servers.append(f'  {{ address="{m["link_host"]}", port={m["link_port"]}, hostgroup=10, weight=1 }}')
            servers.append(f'  {{ address="{m["link_host"]}", port={m["link_port"]}, hostgroup=20, weight=1 }}')
        elif m["role"] == "primary":
            servers.append(f'  {{ address="{m["link_host"]}", port={m["link_port"]}, hostgroup=10, weight=1 }}')
            servers.append(f'  {{ address="{m["link_host"]}", port={m["link_port"]}, hostgroup=20, weight=1 }}')
        else:
            servers.append(f'  {{ address="{m["link_host"]}", port={m["link_port"]}, hostgroup=20, weight=1000 }}')
    version = "8.4.0" if req["service"] == "mysql" else "11.4.0-MariaDB"
    user = str(req.get("user") or "pskit")
    return (
        'datadir="/var/lib/proxysql"\n'
        "admin_variables=\n{\n"
        f'  admin_credentials="pskit_admin:{secret["admin_password"]}"\n'
        f'  mysql_ifaces="{admin_iface}"\n'
        "}\n"
        "mysql_variables=\n{\n"
        "  threads=4\n  max_connections=2048\n"
        '  interfaces="0.0.0.0:6033"\n'
        f'  server_version="{version}"\n'
        f'  monitor_username="{REPL_USER}"\n'
        f'  monitor_password="{secret["replication_password"]}"\n'
        "  monitor_connect_interval=10000\n  monitor_ping_interval=5000\n"
        "}\n"
        "mysql_servers=\n(\n" + ",\n".join(servers) + "\n)\n"
        "mysql_users=\n(\n"
        f'  {{ username="{user}", password="{password}", default_hostgroup=10, transaction_persistent=1, active=1 }}\n'
        ")\n"
        "mysql_query_rules=\n(\n"
        '  { rule_id=1, active=1, match_digest="^SELECT.*FOR UPDATE", destination_hostgroup=10, apply=1 },\n'
        '  { rule_id=2, active=1, match_digest="^SELECT", destination_hostgroup=20, apply=1 }\n'
        ")\n"
    )


_PROXYSQL_START = ('echo "$PSKIT_LB_SECRET_CONFIG" | base64 -d > /etc/proxysql.cnf && '
                   "exec proxysql -f --initial -c /etc/proxysql.cnf -D /var/lib/proxysql")

# The watcher points ProxySQL's write hostgroup at the promoted member. Placeholders are filled from the plan.
_PROXYSQL_PROMOTE = (
    '    {client} --host="{container}" --port=6032 -upskit_admin -p"$PSKIT_ADMIN_PASSWORD" -e '
    '"DELETE FROM mysql_servers WHERE hostgroup_id=10; '
    "INSERT INTO mysql_servers (hostgroup_id, hostname, port, weight) VALUES (10, '{host}', {port}, 1); "
    'LOAD MYSQL SERVERS TO RUNTIME;" || true'
)


def _proxysql_args(req: Dict[str, Any], topo: Dict[str, Any], lb: Dict[str, Any], password: str,
                   secret: Dict[str, str]) -> List[str]:
    config = base64.b64encode(proxysql_config(req, topo, password, secret).encode("utf-8")).decode("ascii")
    argv = _lb_head(req, lb)
    argv += ["-e", f"PSKIT_LB_SECRET_CONFIG={config}", "--entrypoint", "sh", lb["image"], "-c", _PROXYSQL_START]
    return argv


def _lb_head(req: Dict[str, Any], lb: Dict[str, Any]) -> List[str]:
    eng = ENGINES[req["service"]]
    argv = ["run", "-d", "--name", lb["container"], "--restart", "unless-stopped",
            "--label", f"pskit.key={req['key']}", "--label", "pskit.member=lb",
            "-p", f"{lb['bind']}:{lb['port']}:{eng['balancer_container_port']}"]
    if lb.get("network"):
        argv += ["--network", lb["network"]]
    return argv


def _lb_health(service: str) -> str:
    if service == "postgres":
        return "/opt/bitnami/scripts/pgpool/healthcheck.sh"
    return "bash -c 'echo > /dev/tcp/127.0.0.1/6033'"


def _start_balancer(ctx: _Ctx, req: Dict[str, Any], topo: Dict[str, Any], password: str, secret: Dict[str, str],
                    wait_seconds: float) -> None:
    lb = topo["balancer"]
    target = lb["target"]
    ctx.emit(f"Starting the load balancer ({lb['kind']}) on {_where(lb)} port {lb['port']}")
    ctx.docker(target, ["rm", "-f", lb["container"]], check=False, show=False)
    ctx.docker(target, ["pull", lb["image"]])
    build = _pgpool_args if req["service"] == "postgres" else _proxysql_args
    ctx.docker(target, build(req, topo, lb, password, secret))
    _wait_container(ctx, target, lb["container"], _lb_health(req["service"]), f"the load balancer {lb['kind']}",
                    wait_seconds)
    if req["service"] == "postgres" and topo.get("failover") == "auto":
        _install_pgpool_failover(ctx, topo)


def _check_balancer(ctx: _Ctx, req: Dict[str, Any], topo: Dict[str, Any]) -> None:
    """Ask through the load balancer which member answered a read: proves the whole path works."""
    lb = topo["balancer"]
    primary = _primary_of(topo)
    host = lb["container"] if topo.get("local") else lb["address"]
    port = ENGINES[req["service"]]["balancer_container_port"] if topo.get("local") else lb["port"]
    if req["service"] == "postgres":
        # pgpool picks one node per session for plain SELECTs; SHOW pool_nodes marks it load_balance_node.
        script = (f'PGPASSWORD="$POSTGRES_PASSWORD" psql -h {host} -p {port} -U "$POSTGRES_USER" -d "$POSTGRES_DB" '
                  "-A -F '|' -c 'SHOW pool_nodes' | awk -F'|' 'NR==1{for(i=1;i<=NF;i++){if($i==\"role\")r=i;"
                  "if($i==\"load_balance_node\")l=i}} NR>1 && $l==\"true\"{print ($r==\"primary\" ? "
                  "\"the primary\" : \"a replica\")}'")
    elif req["service"] == "mysql":
        script = (f'MYSQL_PWD="$MYSQL_PASSWORD" mysql -h {host} -P {port} -u"$MYSQL_USER" -N -e '
                  "\"SELECT IF(@@read_only, 'a replica', 'the primary')\"")
    else:
        script = (f'MYSQL_PWD="$MARIADB_PASSWORD" mariadb -h {host} -P {port} -u"$MARIADB_USER" -N -e '
                  "\"SELECT IF(@@read_only, 'a replica', 'the primary')\"")
    code, out = ctx.code(primary["target"], ["exec", primary["container"], "sh", "-c", script])
    answer = (out.strip().splitlines() or [""])[-1].strip()
    if code == 0 and answer:
        ctx.emit(f"checked: a read through {lb['kind']} was answered by {answer}")
    else:
        ctx.emit(f"note: could not query through {lb['kind']} from the primary's server yet ({answer or 'no answer'});"
                 " it retries its backends on its own")


# ----------------------------------------------------------------------------------------------- running


def _where(item: Dict[str, Any]) -> str:
    return f"server {item['server']} ({item['address']})" if item.get("server") else "this machine"


def _wait_container(ctx: _Ctx, target: Dict[str, Any], container: str, health: str, what: str,
                    wait_seconds: float) -> None:
    deadline = time.monotonic() + wait_seconds
    ctx.emit(f"waiting for {what}...")
    while True:
        state = ctx.docker(target, ["inspect", "-f", "{{.State.Status}}", container], check=False, show=False).strip()
        if state in ("exited", "dead", "restarting"):
            logs = ctx.docker(target, ["logs", "--tail", "40", container], check=False, show=False)
            raise _error(f"{what} stopped ({state}). Last log lines:\n{logs.strip() or '(no logs)'}")
        if state == "running":
            code, _ = ctx.code(target, ["exec", container, "sh", "-c", health])
            if code == 0:
                return
        if time.monotonic() >= deadline:
            logs = ctx.docker(target, ["logs", "--tail", "40", container], check=False, show=False)
            raise _error(f"{what} did not become ready within {int(wait_seconds)} s. Last log lines:\n"
                         f"{logs.strip() or '(no logs)'}")
        time.sleep(2)


def _member_req(req: Dict[str, Any], member: Dict[str, Any]) -> Dict[str, Any]:
    return {**req, "container": member["container"], "volume": member["volume"], "address": member["address"],
            "port": member["port"], "bind": member["bind"], "target": member["target"],
            "data_dir": str(member["target"].get("data_dir") or "")}


def _run_member_args(svc: Any, req: Dict[str, Any], topo: Dict[str, Any], member: Dict[str, Any], password: str,
                     secret: Dict[str, str]) -> List[str]:
    spec = svc.SERVICES[req["service"]]
    values = svc._values(req, password)
    entrypoint, command, extra = _launch(req["service"], topo, member, secret)
    argv = ["run", "-d", "--name", member["container"], "--restart", "unless-stopped",
            "--label", f"pskit.service={req['service']}", "--label", f"pskit.key={req['key']}",
            "--label", f"pskit.member={member['name']}",
            "-p", f"{member['bind']}:{member['port']}:{spec['port']}"]
    for name, template in spec["env"].items():
        # A MongoDB replica starts empty: its users and data come from the primary when it joins.
        if req["service"] == "mongodb" and member["role"] == "replica":
            continue
        argv += ["-e", f"{name}={svc._fill(template, values)}"]
    for name, value in extra.items():
        argv += ["-e", f"{name}={value}"]
    argv += ["-v", f"{member['volume']}:{spec['data']}"]
    if member.get("network"):
        argv += ["--network", member["network"], "--network-alias", member["container"]]
    argv += entrypoint
    argv.append(req["image"])
    argv += command
    return argv


def _exec(ctx: _Ctx, target: Dict[str, Any], container: str, options: List[str], script: str,
          env: Dict[str, str]) -> str:
    args = ["exec"]
    for name, value in env.items():
        args += ["-e", f"{name}={value}"]
    return ctx.docker(target, [*args, *options, container, "sh", "-c", script])


def _start_member(ctx: _Ctx, req: Dict[str, Any], topo: Dict[str, Any], member: Dict[str, Any], password: str,
                  secret: Dict[str, str], wait_seconds: float) -> None:
    svc = ctx.svc
    spec = svc.SERVICES[req["service"]]
    target = member["target"]
    mreq = _member_req(req, member)
    if member["role"] == "primary" and member["name"] != "primary":
        what = f"primary {member['name']} (writes)"
    elif member["role"] == "primary":
        what = "primary (writes)"
    else:
        what = f"replica {member['name']} (reads)"
    ctx.emit(f"Starting the {what} on {_where(member)} port {member['port']}")
    ctx.docker(target, ["rm", "-f", member["container"]], check=False, show=False)
    svc._prepare_volume(mreq, spec, target, ctx.sh, ctx.emit)
    if req["service"] == "postgres" and member["role"] == "replica":
        primary = _primary_of(topo)
        ctx.emit(f"copying the primary into {member['name']} (pg_basebackup)...")
        seed = ["run", "--rm", "--name", f"{member['container']}-seed",
                "-e", f"PSKIT_REPL_PASSWORD={secret['replication_password']}",
                "-v", f"{member['volume']}:{spec['data']}"]
        if member.get("network"):
            seed += ["--network", member["network"]]
        ctx.docker(target, [*seed, "--entrypoint", "sh", req["image"], "-c",
                            _pg_seed_script(primary, str(spec["data"]))])
    ctx.docker(target, _run_member_args(svc, req, topo, member, password, secret))
    svc._wait_ready(mreq, spec, target, ctx.sh, wait_seconds, ctx.emit)


def _join(ctx: _Ctx, req: Dict[str, Any], topo: Dict[str, Any], member: Dict[str, Any], secret: Dict[str, str],
          wait_seconds: float) -> None:
    """Make a started replica follow the primary."""
    service = req["service"]
    primary = _primary_of(topo)
    if service in ("mysql", "mariadb"):
        ctx.emit(f"{member['name']}: copying the databases and following the primary (GTID)")
        _exec(ctx, member["target"], member["container"], [], _mysql_replica_script(service, primary),
              {"PSKIT_REPL_PASSWORD": secret["replication_password"]})
    elif service == "mongodb":
        ctx.emit(f"{member['name']}: joining the replica set")
        _exec(ctx, primary["target"], primary["container"],
              ["-e", f"PSKIT_JS={_mongo_add_js(member, int(min(wait_seconds, 120)))}"], _MONGOSH, {})
    else:
        ctx.emit(f"{member['name']} follows the primary (streaming replication)")


def _pull(ctx: _Ctx, targets: List[Dict[str, Any]], image: str) -> None:
    from .onprem_services import describe_target

    done = set()
    for target in targets:
        label = describe_target(target)
        if label in done:
            continue
        done.add(label)
        ctx.docker(target, ["pull", image])


def _prepare_targets(ctx: _Ctx, targets: List[Dict[str, Any]], install_docker: bool) -> None:
    from .onprem_services import describe_target

    done = set()
    for target in targets:
        label = describe_target(target)
        if label in done:
            continue
        done.add(label)
        if ctx.run is None and target.get("method") == "ssh":
            ctx.svc.check_ssh_login(target)
        ctx.svc._ensure_docker(target, ctx.sh, install=install_docker)


def _new_secrets(service: str) -> Dict[str, str]:
    out = {"replication_password": secrets.token_hex(16), "admin_password": secrets.token_hex(12)}
    if service == "mongodb":
        out["keyfile"] = base64.b64encode(secrets.token_bytes(96)).decode("ascii")
    return out


def _url(service: str, user: str, password: str, address: str, port: int, database: str) -> str:
    scheme = "postgresql" if service == "postgres" else "mysql"
    return f"{scheme}://{quote(user, safe='')}:{quote(password, safe='')}@{address}:{port}/{database}"


def connection(req: Dict[str, Any], topo: Dict[str, Any], password: str) -> Tuple[Dict[str, Any], Dict[str, str]]:
    """The resource and env values: ``URL`` is what handlers use (load balancer, primary, or the replica set);
    ``WRITE_URL`` / ``READ_URLS`` reach the members directly."""
    from .onprem_services import _connection, _var_prefix

    service = req["service"]
    primary = _primary_of(topo)
    replicas = _replicas_of(topo)
    lb = topo.get("balancer")
    front = {**req, "address": lb["address"] if lb else primary["address"], "port": lb["port"] if lb else primary["port"]}
    resource, env, _notes = _connection(front, password)
    prefix = _var_prefix(req["key"])
    user = str(req.get("user") or "pskit")
    database = re.sub(r"[^A-Za-z0-9_]", "_", req["key"])
    connection_values = dict(resource.get("connection") or {})
    if service == "mongodb":
        hosts = ",".join(f"{m['address']}:{m['port']}" for m in topo["members"])
        env[f"{prefix}_URL"] = (f"mongodb://{quote(user, safe='')}:{quote(password, safe='')}@{hosts}/"
                                f"?replicaSet={topo['replica_set']}&authSource=admin&readPreference=secondaryPreferred")
        connection_values["replica_set"] = topo["replica_set"]
    else:
        env[f"{prefix}_WRITE_URL"] = _url(service, user, password, primary["address"], primary["port"], database)
        env[f"{prefix}_READ_URLS"] = ",".join(_url(service, user, password, m["address"], m["port"], database)
                                              for m in replicas)
        connection_values["write_url_env"] = f"{prefix}_WRITE_URL"
        connection_values["read_urls_env"] = f"{prefix}_READ_URLS"
    connection_values["replicas"] = len(replicas)
    connection_values["replication"] = topo["sync"]
    if topo.get("write"):
        connection_values["write"] = topo["write"]
    if topo.get("failover"):
        connection_values["failover"] = topo["failover"]
    resource["connection"] = connection_values
    return resource, env


def _pg_failover_script(topo: Dict[str, Any]) -> str:
    """pgpool ``failover_command``. New main host and port are ``$5`` and ``$6`` (``%H`` and ``%r``).

    The replication password stays in ``PSKIT_REPL_PASSWORD``, already set on the container.
    """
    lines = [
        "#!/bin/sh",
        "NEW_HOST=$5",
        "NEW_PORT=$6",
        'USER="$PGPOOL_POSTGRES_USERNAME"',
        'export PGPASSWORD="$PGPOOL_POSTGRES_PASSWORD"',
        'psql -h "$NEW_HOST" -p "$NEW_PORT" -U "$USER" -d postgres -v ON_ERROR_STOP=1 '
        '-c "SELECT pg_promote(false, 30);"',
    ]
    sql = (
        f"ALTER SYSTEM SET primary_conninfo = 'host=$NEW_HOST port=$NEW_PORT user={REPL_USER} "
        "password=$PSKIT_REPL_PASSWORD'; SELECT pg_reload_conf();"
    )
    for member in topo["members"]:
        host, port = member["link_host"], member["link_port"]
        lines.append(
            f'if [ "$NEW_HOST" != "{host}" ] || [ "$NEW_PORT" != "{port}" ]; then '
            f'inrec=$(psql -h "{host}" -p "{port}" -U "$USER" -d postgres -tAc '
            '"SELECT pg_is_in_recovery()" || true); '
            'if [ "$inrec" = "t" ]; then '
            f'psql -h "{host}" -p "{port}" -U "$USER" -d postgres -c "{sql}"; fi; fi'
        )
    return "\n".join(lines) + "\n"


def _install_pgpool_failover(ctx: _Ctx, topo: Dict[str, Any]) -> None:
    """Replace bitnami's echo failover_command so a dead primary is actually promoted."""
    lb = topo["balancer"]
    encoded = base64.b64encode(_pg_failover_script(topo).encode("utf-8")).decode("ascii")
    script = (
        "set -e\n"
        "printf '%s' \"$PSKIT_FAILOVER_B64\" | base64 -d > /tmp/pskit-failover.sh\n"
        "chmod 755 /tmp/pskit-failover.sh\n"
        "conf=/opt/bitnami/pgpool/conf/pgpool.conf\n"
        "line=\"failover_command = '/tmp/pskit-failover.sh %d %h %p %m %H %r %M %P'\"\n"
        "if grep -q '^failover_command' \"$conf\"; then sed -i \"s|^failover_command *=.*|$line|\" \"$conf\"; "
        "else echo \"$line\" >> \"$conf\"; fi\n"
        "pgpool reload >/dev/null 2>&1 || kill -HUP 1 || true\n"
        "echo 'pgpool failover command installed'\n"
    )
    ctx.emit("Installing the pgpool failover command (promotes a replica if the primary stops answering)")
    _exec(ctx, lb["target"], lb["container"], [], script, {"PSKIT_FAILOVER_B64": encoded})


def _mysql_follow_script(service: str, source: Dict[str, Any]) -> str:
    """Point one member at ``source`` and open writes. Safe on a member that was not a replica yet."""
    host, port = source["link_host"], source["link_port"]
    if service == "mysql":
        client, stop, start, root = "mysql", "STOP REPLICA", "START REPLICA", "MYSQL_ROOT_PASSWORD"
        change = (
            f"CHANGE REPLICATION SOURCE TO SOURCE_HOST='{host}', SOURCE_PORT={port}, "
            f"SOURCE_USER='{REPL_USER}', SOURCE_PASSWORD='$PSKIT_REPL_PASSWORD', "
            "SOURCE_AUTO_POSITION=1, GET_SOURCE_PUBLIC_KEY=1"
        )
    else:
        client, stop, start, root = "mariadb", "STOP SLAVE", "START SLAVE", "MARIADB_ROOT_PASSWORD"
        change = (
            f"CHANGE MASTER TO MASTER_HOST='{host}', MASTER_PORT={port}, "
            f"MASTER_USER='{REPL_USER}', MASTER_PASSWORD='$PSKIT_REPL_PASSWORD', MASTER_USE_GTID=slave_pos"
        )
    return (
        "set -e\n"
        f'export MYSQL_PWD="${root}"\n'
        f'{client} -uroot -e "{stop};" 2>/dev/null || true\n'
        f'{client} -uroot -e "{change}; {start}; SET GLOBAL read_only=OFF;"\n'
        "echo 'following the previous primary'\n"
    )


def _enable_multi(ctx: _Ctx, req: Dict[str, Any], topo: Dict[str, Any], secret: Dict[str, str]) -> None:
    """Close the ring: member i follows i-1, and the first follows the last. Member 1 already follows 0."""
    service = req["service"]
    primaries = [m for m in topo["members"] if m["role"] == "primary"]
    if len(primaries) < 2:
        return
    env = {"PSKIT_REPL_PASSWORD": secret["replication_password"]}
    for index in range(2, len(primaries)):
        follower, source = primaries[index], primaries[index - 1]
        ctx.emit(f"{follower['name']} follows {source['name']} (multi-primary ring)")
        _exec(ctx, follower["target"], follower["container"], [], _mysql_follow_script(service, source), env)
    first, last = primaries[0], primaries[-1]
    ctx.emit(f"{first['name']} follows {last['name']} (multi-primary ring)")
    _exec(ctx, first["target"], first["container"], [], _mysql_follow_script(service, last), env)


def _watcher_host(topo: Dict[str, Any]) -> Dict[str, Any]:
    """A host that is still up when the first primary dies: the load balancer, else the first other member."""
    if topo.get("balancer"):
        return topo["balancer"]
    replicas = _replicas_of(topo)
    if replicas:
        return replicas[0]
    others = [m for m in topo["members"] if m["role"] == "primary" and m["name"] != "primary"]
    if not others:
        raise _error("automatic failover needs a replica, another primary, or a load balancer that stays up "
                     "when the primary dies")
    return others[0]


def _mysql_watcher_script(service: str, topo: Dict[str, Any]) -> str:
    """Ping the primary twice, then promote the first member that still answers and repoint the others."""
    client = "mysql" if service == "mysql" else "mariadb"
    admin = "mysqladmin" if service == "mysql" else "mariadb-admin"
    stop = "STOP REPLICA; RESET REPLICA ALL" if service == "mysql" else "STOP SLAVE; RESET SLAVE ALL"
    follow = (
        "STOP REPLICA; CHANGE REPLICATION SOURCE TO SOURCE_HOST='{h}', SOURCE_PORT={p}, "
        "SOURCE_USER='{u}', SOURCE_PASSWORD='$PSKIT_REPL_PASSWORD', SOURCE_AUTO_POSITION=1, "
        "GET_SOURCE_PUBLIC_KEY=1; START REPLICA;"
        if service == "mysql" else
        "STOP SLAVE; CHANGE MASTER TO MASTER_HOST='{h}', MASTER_PORT={p}, "
        "MASTER_USER='{u}', MASTER_PASSWORD='$PSKIT_REPL_PASSWORD', MASTER_USE_GTID=slave_pos; START SLAVE;"
    )
    primary = _primary_of(topo)
    lines = [
        "#!/bin/sh",
        "miss=0",
        f'PRIMARY_HOST="{primary["link_host"]}"',
        f'PRIMARY_PORT="{primary["link_port"]}"',
        'export MYSQL_PWD="$MYSQL_ROOT_PASSWORD"',
        "while true; do",
        f'  if {admin} --host="$PRIMARY_HOST" --port="$PRIMARY_PORT" -uroot --silent ping >/dev/null 2>&1; then',
        "    miss=0; sleep 5; continue",
        "  fi",
        "  miss=$((miss + 1))",
        '  if [ "$miss" -lt 2 ]; then sleep 5; continue; fi',
        '  echo "primary $PRIMARY_HOST is not answering"',
    ]
    for member in topo["members"]:
        if member["name"] == primary["name"]:
            continue
        host, port, name = member["link_host"], member["link_port"], member["name"]
        lines.append(f'  if {admin} --host="{host}" --port="{port}" -uroot --silent ping >/dev/null 2>&1; then')
        lines.append(f'    echo "promoting {name}"')
        lines.append(
            f'    {client} --host="{host}" --port="{port}" -uroot -e "{stop}; SET GLOBAL read_only=OFF;" || true'
        )
        for other in topo["members"]:
            if other["name"] == name:
                continue
            sql = follow.format(h=host, p=port, u=REPL_USER)
            lines.append(
                f'    {client} --host="{other["link_host"]}" --port="{other["link_port"]}" -uroot -e "{sql}" || true'
            )
        lb = topo.get("balancer")
        if lb:
            lines.append(_PROXYSQL_PROMOTE.format(
                client=client, container=lb["container"], host=host, port=port))
        lines.append(f'    PRIMARY_HOST="{host}"; PRIMARY_PORT="{port}"; miss=0; sleep 15; continue')
        lines.append("  fi")
    lines.extend(["  sleep 5", "done", ""])
    return "\n".join(lines)


def _pg_watcher_script(topo: Dict[str, Any]) -> str:
    """Same loop as the MySQL watcher, with ``pg_isready`` and ``pg_promote``. Used when there is no pgpool."""
    primary = _primary_of(topo)
    lines = [
        "#!/bin/sh",
        "miss=0",
        f'PRIMARY_HOST="{primary["link_host"]}"',
        f'PRIMARY_PORT="{primary["link_port"]}"',
        'export PGPASSWORD="$POSTGRES_PASSWORD"',
        'USER="$POSTGRES_USER"',
        "while true; do",
        '  if pg_isready -h "$PRIMARY_HOST" -p "$PRIMARY_PORT" -U "$USER" >/dev/null 2>&1; then',
        "    miss=0; sleep 5; continue",
        "  fi",
        "  miss=$((miss + 1))",
        '  if [ "$miss" -lt 2 ]; then sleep 5; continue; fi',
        '  echo "primary $PRIMARY_HOST is not answering"',
    ]
    for member in topo["members"]:
        if member["name"] == primary["name"]:
            continue
        host, port, name = member["link_host"], member["link_port"], member["name"]
        lines.append(f'  if pg_isready -h "{host}" -p "{port}" -U "$USER" >/dev/null 2>&1; then')
        lines.append(f'    echo "promoting {name}"')
        lines.append(
            f'    psql -h "{host}" -p "{port}" -U "$USER" -d postgres -c "SELECT pg_promote(false, 30);" || true'
        )
        for other in topo["members"]:
            if other["name"] == name:
                continue
            lines.append(
                f'    inrec=$(psql -h "{other["link_host"]}" -p "{other["link_port"]}" -U "$USER" -d postgres '
                '-tAc "SELECT pg_is_in_recovery()" || true); '
                'if [ "$inrec" = "t" ]; then '
                f'psql -h "{other["link_host"]}" -p "{other["link_port"]}" -U "$USER" -d postgres -c '
                f"\"ALTER SYSTEM SET primary_conninfo = 'host={host} port={port} user={REPL_USER} "
                "password=$PSKIT_REPL_PASSWORD'; SELECT pg_reload_conf();\"; fi"
            )
        lines.append(f'    PRIMARY_HOST="{host}"; PRIMARY_PORT="{port}"; miss=0; sleep 15; continue')
        lines.append("  fi")
    lines.extend(["  sleep 5", "done", ""])
    return "\n".join(lines)


def _start_watcher(ctx: _Ctx, req: Dict[str, Any], topo: Dict[str, Any], password: str, secret: Dict[str, str],
                   wait_seconds: float) -> None:
    """A container that promotes a member when the primary stops answering. No Docker socket."""
    host_item = _watcher_host(topo)
    service = req["service"]
    container = f"{req['container']}-failover"
    if service == "postgres":
        script = _pg_watcher_script(topo)
        extra = [f"POSTGRES_PASSWORD={password}", f"POSTGRES_USER={req.get('user') or 'pskit'}",
                 f"PSKIT_REPL_PASSWORD={secret['replication_password']}"]
    else:
        script = _mysql_watcher_script(service, topo)
        extra = [f"MYSQL_ROOT_PASSWORD={password}", f"PSKIT_REPL_PASSWORD={secret['replication_password']}"]
        if topo.get("balancer"):
            extra.append(f"PSKIT_ADMIN_PASSWORD={secret['admin_password']}")
    encoded = base64.b64encode(script.encode("utf-8")).decode("ascii")
    argv = ["run", "-d", "--name", container, "--restart", "unless-stopped",
            "--label", f"pskit.key={req['key']}", "--label", "pskit.member=failover",
            "-e", f"PSKIT_FAILOVER_B64={encoded}"]
    for item in extra:
        argv += ["-e", item]
    network = str(host_item.get("network") or "")
    if network:
        argv += ["--network", network]
    argv += ["--entrypoint", "sh", req["image"], "-c",
             'echo "$PSKIT_FAILOVER_B64" | base64 -d > /tmp/pskit-failover.sh && exec sh /tmp/pskit-failover.sh']
    ctx.emit(f"Starting the failover watcher on {_where(host_item)} "
             "(promotes a member if the primary stops answering)")
    ctx.docker(host_item["target"], ["rm", "-f", container], check=False, show=False)
    ctx.docker(host_item["target"], argv)
    _wait_container(ctx, host_item["target"], container, "true", "the failover watcher", min(float(wait_seconds), 30))
    topo["watcher"] = {
        "name": "failover", "role": "watcher", "server": host_item.get("server") or "",
        "address": host_item.get("address") or "", "port": 0, "container": container,
        "target": host_item["target"], "network": network,
    }
    if not topo.get("balancer"):
        ctx.emit("automatic failover promotes a replica, but the functions' URL stays the old primary until you "
                 "point WRITE_URL at the new one or add a load balancer")


def _arm_failover(ctx: _Ctx, req: Dict[str, Any], topo: Dict[str, Any], password: str, secret: Dict[str, str],
                  wait_seconds: float) -> None:
    """Start the watcher. PostgreSQL with pgpool installs its command inside the load balancer instead."""
    if str(topo.get("failover") or "off") != "auto" or req["service"] == "mongodb":
        return
    if req["service"] == "postgres" and topo.get("balancer"):
        return
    _start_watcher(ctx, req, topo, password, secret, wait_seconds)


def create(root: Path, req: Dict[str, Any], body: Dict[str, Any], raw: Optional[Dict[str, Any]], emit: Emit, *,
           run: Optional[RunFn] = None, wait_seconds: float = 90) -> Dict[str, Any]:
    """Start the primary, the replicas and the load balancer of a replicated database; record and return it."""
    from . import onprem_network as network

    ctx = _Ctx(emit, run)
    svc = ctx.svc
    service = req["service"]
    spec = svc.SERVICES[service]
    topo = req["topology"]
    eng = ENGINES[service]
    password = req["password"] or secrets.token_urlsafe(18).replace("-", "x").replace("_", "y")
    secret = _new_secrets(service)
    members = topo["members"]
    lb = topo.get("balancer")
    if topo.get("write") == "multi":
        shape = f"{len(members)} primaries"
    else:
        shape = f"primary + {len(members) - 1} replica(s)"
    extra = ", automatic failover" if topo.get("failover") == "auto" and service != "mongodb" else ""
    emit(f"Creating {spec['label']} {req['key']!r}: {shape}, {topo['sync']} "
         f"{eng['method'].lower()}{extra}" + (f", load balancer {lb['kind']}" if lb else ""))
    wait = max(wait_seconds, 120)
    _prepare_targets(ctx, [m["target"] for m in members] + ([lb["target"]] if lb else []),
                     bool(body.get("install_docker", True)))
    if topo.get("network"):
        ctx.docker(members[0]["target"], ["network", "create", topo["network"]], check=False, show=False)
    _pull(ctx, [m["target"] for m in members], req["image"])
    primary = members[0]
    _start_member(ctx, req, topo, primary, password, secret, wait)
    options, script = _primary_setup(service, topo)
    _exec(ctx, primary["target"], primary["container"], options, script,
          {"PSKIT_REPL_PASSWORD": secret["replication_password"]})
    if req.get("import"):
        # Into the primary before the replicas start: each replica copies it with the rest.
        from .onprem_monitor import import_data

        import_data(primary["target"], primary["container"], service, req["import"], emit, run=run)
    for member in members[1:]:
        _start_member(ctx, req, topo, member, password, secret, wait)
        _join(ctx, req, topo, member, secret, wait)
    if service == "postgres" and topo["sync"] == "sync":
        _sync_on(ctx, topo)
    if topo.get("write") == "multi" and service in ("mysql", "mariadb"):
        _enable_multi(ctx, req, topo, secret)
    if lb:
        lb_net = str(lb.get("network") or "")
        if lb_net and lb_net != str(topo.get("network") or ""):
            # Watcher and ProxySQL admin share this network. It is not published to the host.
            ctx.docker(lb["target"], ["network", "create", lb_net], check=False, show=False)
        _start_balancer(ctx, req, topo, password, secret, wait)
    _arm_failover(ctx, req, topo, password, secret, wait)
    resource, env_values = connection(req, topo, password)
    env_file = svc.env_file_of(raw)
    update = svc.update_env_file
    update(root / env_file, dict(env_values))
    svc._ensure_ignored(root, env_file)
    notes = [f"credentials written to {env_file} (loaded by the host; keep it out of git)",
             f"{svc._var_prefix(req['key'])}_URL: " + (f"the load balancer ({lb['kind']})" if lb else
                                                     "the replica set" if service == "mongodb" else
                                                     "the primary; reads can use _READ_URLS")]
    if topo.get("write") == "multi":
        notes.append("every member accepts writes; two members changing the same row can diverge. "
                     "Use the load balancer URL")
    entry = {
        "key": req["key"],
        "service": service,
        "kind": "service",
        "role": req["role"],
        "target": primary["target"],
        "image": req["image"],
        "container": primary["container"],
        "volume": primary["volume"],
        **({"data_dir": req["data_dir"]} if req.get("data_dir") else {}),
        "port": req["port"],
        "address": req["address"],
        "address_auto": True,
        "bind": primary["bind"],
        "user": req["user"],
        "attach": [],
        "env_file": env_file,
        "env": env_values,
        "resource": resource,
        "notes": notes,
        "created_at": svc._now(),
        "topology": {**topo, "secrets": secret},
        **({"alert": req["alert"]} if req.get("alert") else {}),
    }
    state = svc.load_state(root)
    state["services"][req["key"]] = entry
    svc.save_state(root, state)
    if lb:
        _check_balancer(ctx, req, topo)
    for note in notes:
        emit(note)
    emit(f"{spec['label']} is ready: functions connect to {req['address']}:{req['port']}")
    network.emit_rules(emit, f"{spec['label']} {req['key']!r}", rules(entry, network.function_hosts(root)))
    return entry


def _req_of(entry: Dict[str, Any]) -> Dict[str, Any]:
    """A create request rebuilt from a recorded service (for adding a replica later)."""
    return {"key": entry["key"], "service": entry["service"], "role": entry.get("role") or "database",
            "image": entry["image"], "user": entry.get("user") or "pskit", "container": entry["container"],
            "port": entry["port"], "address": entry["address"], "project": ""}


def _password(entry: Dict[str, Any]) -> str:
    from .onprem_services import _var_prefix

    password = str((entry.get("env") or {}).get(f"{_var_prefix(entry['key'])}_PASSWORD") or "")
    if not password:
        raise _error(f"the password of {entry['key']!r} is not recorded; create the service again")
    return password


def _save(root: Path, entry: Dict[str, Any], req: Dict[str, Any], topo: Dict[str, Any], password: str,
          emit: Emit) -> Dict[str, Any]:
    from . import onprem_services as svc

    resource, env_values = connection(req, topo, password)
    env_file = root / str(entry.get("env_file") or svc.DEFAULT_ENV_FILE)
    gone = {k: None for k in (entry.get("env") or {}) if k not in env_values}
    svc.update_env_file(env_file, {**gone, **env_values})
    entry = {**entry, "env": env_values, "resource": resource, "topology": topo}
    state = svc.load_state(root)
    state["services"][entry["key"]] = entry
    svc.save_state(root, state)
    where = entry.get("env_file") or svc.DEFAULT_ENV_FILE
    if topo.get("balancer"):
        emit(f"updated {where}; the functions keep using the load balancer, which already sends reads to the new list")
    else:
        emit(f"updated {where}: redeploy the functions so they use the new list of members")
    return entry


def add_replica(root: Path, key: str, server: str, emit: Emit, *, run: Optional[RunFn] = None,
                wait_seconds: float = 120) -> Dict[str, Any]:
    """Start one more read replica of a replicated database on ``server`` (``local`` when every member runs here)."""
    from . import onprem_services as svc

    entry = svc._entry(root, key)
    if not is_replicated(entry):
        raise _error(f"{key!r} runs on a single server; create it as a replicated database to add replicas")
    topo = dict(entry["topology"])
    secret = dict(topo.get("secrets") or {})
    members = [dict(m) for m in topo["members"]]
    server = str(server or "").strip() or (LOCAL if topo.get("local") else "")
    if not server:
        raise _error("server: the saved server for the new replica")
    if topo.get("local") and server != LOCAL:
        raise _error("every member of this database runs on this machine; add the replica here (local)")
    if not topo.get("local"):
        if server == LOCAL:
            raise _error("this database runs on servers; pick a saved server for the replica")
        if any(m["server"] == server for m in members):
            raise _error(f"server {server!r} already runs a member of {key!r}; pick another one")
    if len(members) - 1 >= MAX_REPLICAS:
        raise _error(f"at most {MAX_REPLICAS} replicas")
    req = _req_of(entry)
    multi = topo.get("write") == "multi"
    index = int(topo.get("next_index") or len(members))
    port = int(members[0]["port"])
    if topo.get("local"):
        port = max(int(m["port"]) for m in members) + 1
    member = _member(svc, req, root, role="primary" if multi else "replica", index=index, server=server, port=port,
                     network=str(topo.get("network") or ""))
    topo["members"] = [*members, member]
    topo["next_index"] = index + 1
    password = _password(entry)
    ctx = _Ctx(emit, run)
    kind = "primary" if multi else "replica"
    emit(f"Adding {kind} {member['name']} of {key!r} on {_where(member)}")
    _prepare_targets(ctx, [member["target"]], True)
    _pull(ctx, [member["target"]], req["image"])
    _start_member(ctx, req, topo, member, password, secret, wait_seconds)
    _join(ctx, req, topo, member, secret, wait_seconds)
    if multi and req["service"] in ("mysql", "mariadb"):
        _enable_multi(ctx, req, topo, secret)
    if topo.get("balancer"):
        _start_balancer(ctx, req, topo, password, secret, wait_seconds)
    _arm_failover(ctx, req, topo, password, secret, wait_seconds)
    entry = _save(root, entry, req, topo, password, emit)
    from . import onprem_network as network

    network.emit_rules(emit, f"replica {member['name']} of {key!r}",
                       rules(entry, network.function_hosts(root)))
    return entry


def remove_replica(root: Path, key: str, name: str, emit: Emit, *, delete_data: bool = False,
                   run: Optional[RunFn] = None) -> Dict[str, Any]:
    """Stop one read replica (by member name ``r2`` or its server) and take it out of the load balancer."""
    from . import onprem_services as svc

    entry = svc._entry(root, key)
    if not is_replicated(entry):
        raise _error(f"{key!r} has no replicas")
    topo = dict(entry["topology"])
    secret = dict(topo.get("secrets") or {})
    multi = str(topo.get("write") or "single") == "multi"
    if multi:
        member = next((m for m in topo["members"]
                       if name in (m["name"], m["server"]) and m["role"] == "primary" and m["name"] != "primary"),
                      None)
        if member is None:
            if any(name in (m["name"], m.get("server")) and m["name"] == "primary" for m in topo["members"]):
                raise _error("the first primary stays; remove another primary, or remove the whole database")
            names = ", ".join(
                f"{m['name']}" + (f" ({m['server']})" if m["server"] else "")
                for m in topo["members"] if m["role"] == "primary" and m["name"] != "primary"
            )
            raise _error(f"{key!r} has no other primary {name!r}; other primaries: {names}")
        others = [m for m in topo["members"] if m["role"] == "primary" and m["name"] != "primary"]
        if len(others) <= 1:
            raise _error("this is the last other primary; a multi-primary database keeps at least two. "
                         "Remove the whole database instead")
    else:
        member = next((m for m in topo["members"] if name in (m["name"], m["server"]) and m["role"] == "replica"),
                      None)
        if member is None:
            names = ", ".join(
                f"{m['name']}" + (f" ({m['server']})" if m["server"] else "") for m in _replicas_of(topo)
            )
            raise _error(f"{key!r} has no replica {name!r}; replicas: {names}")
        if len(_replicas_of(topo)) == 1:
            raise _error("this is the last replica; remove the whole database instead (a replicated database keeps "
                         "at least one)")
    ctx = _Ctx(emit, run)
    req = _req_of(entry)
    emit(f"Removing {'primary' if multi else 'replica'} {member['name']} of {key!r} from {_where(member)}")
    if entry["service"] == "mongodb":
        primary = _primary_of(topo)
        _exec(ctx, primary["target"], primary["container"], ["-e", f"PSKIT_JS={_mongo_remove_js(member)}"],
              _MONGOSH, {})
    topo["members"] = [m for m in topo["members"] if m["name"] != member["name"]]
    password = _password(entry)
    if multi and entry["service"] in ("mysql", "mariadb"):
        _enable_multi(ctx, req, topo, secret)
    if topo.get("balancer"):
        _start_balancer(ctx, req, topo, password, secret, 120)
    _arm_failover(ctx, req, topo, password, secret, 30)
    ctx.docker(member["target"], ["rm", "-f", member["container"]], check=False)
    if delete_data:
        svc._drop_volume(member["target"], ctx.sh, member["volume"])
    else:
        emit(f"kept the data volume {member['volume']} on {_where(member)}")
    return _save(root, entry, req, topo, password, emit)


def remove_members(entry: Dict[str, Any], emit: Emit, *, delete_data: bool, run: Optional[RunFn] = None) -> None:
    """Before the primary goes (by :func:`onprem_services.remove`): the load balancer and the replicas."""
    if not is_replicated(entry):
        return
    from .onprem_services import _drop_volume

    ctx = _Ctx(emit, run)
    topo = entry["topology"]
    lb = topo.get("balancer")
    watcher = topo.get("watcher") if isinstance(topo.get("watcher"), dict) else None
    if watcher and watcher.get("container"):
        ctx.docker(watcher["target"], ["rm", "-f", watcher["container"]], check=False)
    if lb:
        ctx.docker(lb["target"], ["rm", "-f", lb["container"]], check=False)
    primary_container = str(entry.get("container") or "")
    for member in topo["members"]:
        if member.get("name") == "primary" or member.get("container") == primary_container:
            continue
        ctx.docker(member["target"], ["rm", "-f", member["container"]], check=False)
        if delete_data:
            _drop_volume(member["target"], ctx.sh, member["volume"])
        else:
            emit(f"kept the data volume {member['volume']} on {_where(member)}")
    lb_net = str((lb or {}).get("network") or "")
    if lb_net and lb_net != str(topo.get("network") or ""):
        target = (lb or watcher or {}).get("target")
        if target:
            ctx.docker(target, ["network", "rm", lb_net], check=False, show=False)


def status(entry: Dict[str, Any], *, run: Optional[RunFn] = None) -> Dict[str, Any]:
    """``members`` and ``balancer`` with their container ``state`` (and each replica's lag in ``replication``), and
    ``report``: what the primary says about its replicas."""
    ctx = _Ctx(lambda _l: None, run)
    topo = public(entry["topology"])
    service = entry["service"]

    def row(item: Dict[str, Any]) -> Dict[str, Any]:
        code, text = ctx.code(item["target"], ["inspect", "-f", "{{.State.Status}}", item["container"]])
        state = (text.strip().splitlines() or ["missing"])[-1] if code == 0 else "missing"
        out = {k: v for k, v in item.items() if k != "target"}
        out["state"] = state
        script = _replica_lag_script(service) if item["role"] == "replica" else ""
        if state == "running" and script:
            _code, text = ctx.code(item["target"], ["exec", item["container"], "sh", "-c", script])
            out["replication"] = text.strip()[-600:]
        return out

    members = [row(m) for m in topo["members"]]
    report = ""
    primary = _primary_of(topo)
    if any(m["role"] == "primary" and m["state"] == "running" for m in members):
        options, script = _replication_report(service)
        _code, text = ctx.code(primary["target"], ["exec", *options, primary["container"], "sh", "-c", script])
        report = text.strip()[-3000:]
    return {"members": members, "balancer": row(topo["balancer"]) if topo.get("balancer") else None, "report": report}


def public(topo: Dict[str, Any]) -> Dict[str, Any]:
    """The topology for the UI: no secrets, member targets without passwords."""
    out = {k: v for k, v in topo.items() if k != "secrets"}

    def clean(item: Dict[str, Any]) -> Dict[str, Any]:
        target = {k: v for k, v in (item.get("target") or {}).items() if k not in ("password",)}
        return {**item, "target": target}

    out["members"] = [clean(m) for m in topo.get("members") or []]
    if topo.get("balancer"):
        out["balancer"] = clean(topo["balancer"])
    if isinstance(topo.get("watcher"), dict):
        out["watcher"] = clean(topo["watcher"])
    return out


# ----------------------------------------------------------------------------------------------- firewall


def rules(entry: Dict[str, Any], clients: Sequence[Dict[str, str]]) -> List[Dict[str, Any]]:
    """Replicas -> primary (replication), load balancer -> every member, functions -> the load balancer (or every
    member when there is none), this machine -> SSH on each server."""
    from . import onprem_network as network

    topo = entry["topology"]
    if topo.get("local"):
        return []
    label = f"{entry.get('service')} {entry.get('key')!r}"
    out: List[Dict[str, Any]] = []
    members = topo["members"]
    lb = topo.get("balancer")
    whos = {m["name"]: network.who(m["server"] or m["address"], m["address"]) for m in members}
    for m in members:
        out.append(network.ssh_rule(whos[m["name"]]))
    primary = _primary_of(topo)
    replicas = _replicas_of(topo)
    primaries = [m for m in members if m["role"] == "primary"]
    if len(primaries) > 1:
        for m in primaries:
            others = [whos[o["name"]] for o in primaries if o["name"] != m["name"]]
            out.append(network.rule(whos[m["name"]], m["port"], others, f"{label}: primaries copy each other"))
    else:
        out.append(network.rule(whos["primary"], primary["port"], [whos[m["name"]] for m in replicas],
                                f"{label}: replicas copy the primary's changes"))
    if entry.get("service") == "mongodb":
        for m in members:
            others = [whos[o["name"]] for o in members if o["name"] != m["name"]]
            out.append(network.rule(whos[m["name"]], m["port"], others, f"{label}: replica set members talk"))
    front: List[Tuple[Dict[str, str], int]]
    if lb:
        lb_who = network.who(lb["server"] or lb["address"], lb["address"])
        out.append(network.ssh_rule(lb_who))
        for m in members:
            out.append(network.rule(whos[m["name"]], m["port"], [lb_who], f"{label}: the load balancer forwards"))
        front = [(lb_who, int(lb["port"]))]
    else:
        front = [(whos[m["name"]], int(m["port"])) for m in members]
    for server, port in front:
        sources = [c for c in clients if c["address"] != server["address"]] or [network.who("your function servers")]
        out.append(network.rule(server, port, sources, f"{label}: your functions connect to it"))
    watcher = topo.get("watcher") if isinstance(topo.get("watcher"), dict) else None
    if watcher and str(topo.get("failover") or "") == "auto":
        w_addr = str(watcher.get("address") or "")
        lb_addr = str((lb or {}).get("address") or "")
        # A watcher on the load balancer's server is already allowed to reach every member.
        if w_addr and w_addr != lb_addr:
            w_who = network.who(str(watcher.get("server") or w_addr), w_addr)
            for m in members:
                if str(m.get("address") or "") == w_addr:
                    continue
                out.append(network.rule(whos[m["name"]], m["port"], [w_who],
                                        f"{label}: the failover watcher checks members"))
    return out
