"""Replicated databases (primary, read replicas, load balancer) on saved servers: plans, commands, state, env file."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import List, Optional, Tuple

import pytest

from py_serverless_kit.core import onprem_network as network
from py_serverless_kit.core import onprem_replication as rep
from py_serverless_kit.core import onprem_services as svc
from py_serverless_kit.runtime.onprem_host import parse_env_text

RAW = {"service": "shop", "provider": {"name": "onprem", "runtime": "python3.12"}, "package": {"source": "."},
       "functions": {"api": {"handler": "app.handlers.api"}}}
HOSTS = {"db1": "10.0.0.11", "db2": "10.0.0.12", "db3": "10.0.0.13", "lb1": "10.0.0.20"}


class FakeShell:
    """Answers the ssh / docker commands and records them as joined strings."""

    def __init__(self) -> None:
        self.calls: List[str] = []

    def __call__(self, argv: List[str], stdout: Optional[Path]) -> Tuple[int, str]:
        text = " ".join(argv).replace("'\"'\"'", "'")  # undo the shell quoting of commands sent over SSH
        self.calls.append(text)
        if "command -v docker" in text:
            return 0, "present"
        if "inspect" in text:
            return 0, "running"
        return 0, ""

    def having(self, *parts: str) -> List[str]:
        return [c for c in self.calls if all(p in c for p in parts)]


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    servers = {name: {"host": host, "user": "ubuntu", "port": 22, "auth": "agent"} for name, host in HOSTS.items()}
    (tmp_path / ".pskit").mkdir()
    (tmp_path / ".pskit" / "onprem-servers.json").write_text(json.dumps({"servers": servers}), "utf-8")
    return tmp_path


def _body(service: str = "postgres", **topology):
    topo = {"mode": "replicated", "sync": "async", "primary": "db1", "replicas": ["db2", "db3"], "balancer": "lb1"}
    topo.update(topology)
    return {"key": "orders", "service": service, "topology": topo}


def _create(root: Path, fake: FakeShell, service: str = "postgres", **topology):
    return svc.create(root, _body(service, **topology), RAW, lambda _l: None, run=fake, wait_seconds=1)


def _env(root: Path):
    return parse_env_text((root / ".env.onprem").read_text("utf-8"))


# ----------------------------------------------------------------------------------------------- plan


def test_plan_places_members_and_the_balancer_on_their_servers(root):
    req = svc.check_request(_body(), root, RAW)
    topo = req["topology"]
    assert [(m["name"], m["role"], m["server"], m["address"], m["port"]) for m in topo["members"]] == [
        ("primary", "primary", "db1", "10.0.0.11", 5432),
        ("r1", "replica", "db2", "10.0.0.12", 5432),
        ("r2", "replica", "db3", "10.0.0.13", 5432),
    ]
    assert topo["balancer"]["server"] == "lb1" and topo["balancer"]["port"] == 6432
    assert topo["failover"] == "off" and topo["write"] == "single"
    # The functions use the load balancer; the primary is the service's own target (console, logs, backup).
    assert (req["address"], req["port"]) == ("10.0.0.20", 6432)
    assert req["target"]["host"] == "10.0.0.11" and req["container"] == "pskit-shop-orders"


def test_local_plan_gives_each_member_its_own_port_on_a_private_network(root):
    req = svc.check_request(_body(primary="local", replicas=["local", "local"], balancer="local"), root, RAW)
    topo = req["topology"]
    assert [m["port"] for m in topo["members"]] == [5432, 5433, 5434]
    assert {m["network"] for m in topo["members"]} == {"pskit-shop-orders-net"}
    assert topo["members"][1]["link_host"] == "pskit-shop-orders-r1" and topo["members"][1]["link_port"] == 5432
    assert req["address"] == "127.0.0.1"


@pytest.mark.parametrize(
    ("body", "message"),
    [
        (_body("clickhouse"), "single server"),
        (_body(replicas=["db1"]), "one member per server"),
        (_body(replicas=[]), "at least one server"),
        (_body(primary=""), "topology.primary"),
        (_body(sync="eventually"), "async or sync"),
        (_body("mongodb"), "needs no load balancer"),
        (_body("mongodb", primary="local", replicas=["local"], balancer=""), "needs servers"),
        (_body(primary="local", replicas=["db2"]), "replicas must all be local"),
        (_body(replicas=["local"]), "cannot follow a primary on a server"),
        (_body(balancer="db1", balancer_port=5432), "is a database port"),
        (_body(replicas=["nope"]), "no saved SSH server 'nope'"),
    ],
)
def test_plan_refuses_what_cannot_work(root, body, message):
    if body["service"] == "clickhouse":
        body["role"] = "database"
    with pytest.raises(svc.ServiceError, match=message):
        svc.check_request(body, root, RAW)


def test_catalog_says_which_databases_replicate():
    info = {c["id"]: c.get("replication") for c in svc.catalog() if c["kind"] == "service"}
    assert {k for k, v in info.items() if v} == {"postgres", "mysql", "mariadb", "mongodb"}
    assert info["postgres"]["balancer"] == "pgpool-II" and info["mysql"]["balancer"] == "ProxySQL"
    assert info["mongodb"]["balancer"] == "" and info["mongodb"]["local"] is False
    assert info["mysql"]["multi"] is True and info["postgres"]["multi"] is False
    assert info["mongodb"]["failover_always"] is True


# ----------------------------------------------------------------------------------------------- create


def test_postgres_primary_replicas_and_pgpool(root):
    fake = FakeShell()
    entry = _create(root, fake, sync="sync")
    primary_run = fake.having("10.0.0.11", "docker", "run", "pskit.member=primary")
    assert primary_run and "0.0.0.0:5432:5432" in primary_run[0] and "wal_level=replica" in primary_run[0]
    # Each replica starts from a copy of the primary, on its own server.
    for host in ("10.0.0.12", "10.0.0.13"):
        seed = fake.having(host, "pg_basebackup -h 10.0.0.11 -p 5432 -U pskit_repl")
        assert seed and "PSKIT_REPL_PASSWORD=" in seed[0]
    assert fake.having("10.0.0.11", "CREATE ROLE pskit_repl WITH REPLICATION")
    # Sync is switched on after the replicas joined (the image's first start would wait forever otherwise).
    sync_at = next(i for i, c in enumerate(fake.calls) if "synchronous_standby_names" in c)
    last_replica = max(i for i, c in enumerate(fake.calls) if "pskit.member=r2" in c)
    assert sync_at > last_replica
    pgpool = fake.having("10.0.0.20", "bitnamilegacy/pgpool")[-1]
    assert "PGPOOL_BACKEND_NODES=0:10.0.0.11:5432:0,1:10.0.0.12:5432:1,2:10.0.0.13:5432:1" in pgpool
    assert "0.0.0.0:6432:5432" in pgpool
    assert "PGPOOL_HEALTH_CHECK" not in pgpool
    assert not fake.having("pskit.member=failover")
    env = _env(root)
    password = env["PSKIT_ORDERS_PASSWORD"]
    assert env["PSKIT_ORDERS_URL"] == f"postgresql://pskit:{password}@10.0.0.20:6432/orders"
    assert env["PSKIT_ORDERS_WRITE_URL"].endswith("@10.0.0.11:5432/orders")
    assert env["PSKIT_ORDERS_READ_URLS"].count("postgresql://") == 2
    assert entry["resource"]["connection"]["read_urls_env"] == "PSKIT_ORDERS_READ_URLS"
    assert entry["resource"]["connection"]["replication"] == "sync"


def test_secrets_stay_out_of_the_ui_and_the_log(root):
    fake = FakeShell()
    lines: List[str] = []
    svc.create(root, _body(), RAW, lines.append, run=fake, wait_seconds=1)
    entry = svc.load_state(root)["services"]["orders"]
    repl = entry["topology"]["secrets"]["replication_password"]
    assert repl not in json.dumps(svc.public_entry(entry))
    assert "secrets" not in svc.public_entry(entry)["topology"]
    assert repl not in "\n".join(lines) and entry["env"]["PSKIT_ORDERS_PASSWORD"] not in "\n".join(lines)


@pytest.mark.parametrize("service", ["mysql", "mariadb"])
def test_mysql_family_follows_the_primary_behind_proxysql(root, service):
    fake = FakeShell()
    _create(root, fake, service=service, sync="sync")
    primary_run = fake.having("10.0.0.11", "pskit.member=primary")[0]
    assert "--server-id=1" in primary_run and "--log-bin=mysql-bin" in primary_run
    replica_run = fake.having("10.0.0.12", "pskit.member=r1", "docker", "run")[0]
    assert "--server-id=101" in replica_run and "--read-only=ON" in replica_run
    follow = "CHANGE REPLICATION SOURCE TO SOURCE_HOST='10.0.0.11'" if service == "mysql" else \
        "CHANGE MASTER TO MASTER_HOST='10.0.0.11'"
    assert fake.having("10.0.0.12", follow) and fake.having("10.0.0.13", follow)
    semisync = "semisync_source.so" if service == "mysql" else "rpl-semi-sync-master-enabled"
    assert semisync in primary_run
    proxy = fake.having("10.0.0.20", "proxysql/proxysql")[-1]
    encoded = proxy.split("PSKIT_LB_SECRET_CONFIG=")[1].split("'")[0].split(" ")[0]
    config = base64.b64decode(encoded).decode("utf-8")
    assert 'address="10.0.0.11", port=3306, hostgroup=10' in config
    assert 'address="10.0.0.12", port=3306, hostgroup=20, weight=1000' in config
    assert 'match_digest="^SELECT", destination_hostgroup=20' in config
    assert 'mysql_ifaces="127.0.0.1:6032"' in config
    assert _env(root)["PSKIT_ORDERS_URL"].endswith("@10.0.0.20:6033/orders")


def test_mongodb_replica_set_with_one_url(root):
    fake = FakeShell()
    entry = _create(root, fake, service="mongodb", balancer="", sync="sync")
    runs = fake.having("docker", "run", "--replSet")
    assert len(runs) == 3 and all("PSKIT_RS_SECRET_KEY=" in r for r in runs)
    # Replicas start empty: their users come from the primary.
    assert "MONGO_INITDB_ROOT_PASSWORD" in runs[0] and "MONGO_INITDB_ROOT_PASSWORD" not in runs[1]
    assert fake.having("10.0.0.11", 'rs.initiate({_id: "rs_orders"', "w: \"majority\"")
    assert fake.having("10.0.0.11", 'const host = "10.0.0.12:27017"', "rs.add")
    url = _env(root)["PSKIT_ORDERS_URL"]
    assert "@10.0.0.11:27017,10.0.0.12:27017,10.0.0.13:27017/" in url
    assert "replicaSet=rs_orders" in url and "readPreference=secondaryPreferred" in url
    assert entry["resource"]["connection"]["replica_set"] == "rs_orders"


# ----------------------------------------------------------------------------------------------- later


def test_add_and_remove_a_replica_updates_balancer_and_env(root):
    fake = FakeShell()
    _create(root, fake, replicas=["db2"])
    fake.calls.clear()
    entry = rep.add_replica(root, "orders", "db3", lambda _l: None, run=fake, wait_seconds=1)
    assert [m["name"] for m in entry["topology"]["members"]] == ["primary", "r1", "r2"]
    assert fake.having("10.0.0.13", "pg_basebackup -h 10.0.0.11")
    assert "2:10.0.0.13:5432:1" in fake.having("10.0.0.20", "bitnamilegacy/pgpool", "run")[-1]
    assert _env(root)["PSKIT_ORDERS_READ_URLS"].count("postgresql://") == 2
    with pytest.raises(svc.ServiceError, match="already runs a member"):
        rep.add_replica(root, "orders", "db2", lambda _l: None, run=fake)

    fake.calls.clear()
    entry = rep.remove_replica(root, "orders", "db2", lambda _l: None, run=fake)  # by server name
    assert [m["name"] for m in entry["topology"]["members"]] == ["primary", "r2"]
    assert fake.having("10.0.0.12", "rm", "-f", "pskit-shop-orders-r1")
    assert "10.0.0.12" not in fake.having("10.0.0.20", "bitnamilegacy/pgpool", "run")[-1]
    assert "10.0.0.12" not in _env(root)["PSKIT_ORDERS_READ_URLS"]
    with pytest.raises(svc.ServiceError, match="last replica"):
        rep.remove_replica(root, "orders", "r2", lambda _l: None, run=fake)


def test_remove_stops_every_member_on_its_server(root):
    fake = FakeShell()
    _create(root, fake)
    fake.calls.clear()
    svc.remove(root, "orders", lambda _l: None, delete_data=True, run=fake)
    for host, container in [("10.0.0.20", "pskit-shop-orders-lb"), ("10.0.0.12", "pskit-shop-orders-r1"),
                            ("10.0.0.13", "pskit-shop-orders-r2"), ("10.0.0.11", "pskit-shop-orders")]:
        assert fake.having(host, "rm", "-f", container), host
    assert fake.having("10.0.0.12", "volume", "rm", "pskit-shop-orders-r1-data")
    assert "orders" not in svc.load_state(root)["services"]
    assert "PSKIT_ORDERS_READ_URLS" not in _env(root)


def test_firewall_rules_follow_the_topology(root):
    fake = FakeShell()
    entry = _create(root, fake)
    rules = network.resource(entry, [network.who("app1", "10.0.0.50")])
    flat = {(r["address"], r["port"], tuple(s["address"] for s in r["sources"])) for r in rules}
    assert ("10.0.0.11", "5432", ("10.0.0.12", "10.0.0.13")) in flat       # replicas copy the primary
    assert ("10.0.0.12", "5432", ("10.0.0.20",)) in flat                    # the load balancer reaches members
    assert ("10.0.0.20", "6432", ("10.0.0.50",)) in flat                    # functions reach the load balancer
    assert not any(r["address"] == "10.0.0.11" and r["port"] == "5432" and "10.0.0.50" in
                   [s["address"] for s in r["sources"]] for r in rules)


def test_status_reports_members_and_balancer_separately(root):
    fake = FakeShell()
    _create(root, fake)
    out = svc.status(root, "orders", run=fake)["topology"]
    assert [m["name"] for m in out["members"]] == ["primary", "r1", "r2"]
    assert out["balancer"]["name"] == "lb" and out["balancer"]["state"] == "running"
    assert all("target" not in m for m in out["members"])


# ----------------------------------------------------------------------------------------------- failover and multi-primary


def test_plan_refuses_several_primaries_where_the_engine_has_one(root):
    with pytest.raises(svc.ServiceError, match="one primary"):
        svc.check_request(_body(write="multi"), root, RAW)
    with pytest.raises(svc.ServiceError, match="one primary"):
        svc.check_request(_body("mongodb", balancer="", write="multi"), root, RAW)
    with pytest.raises(svc.ServiceError, match="failover must be off or auto"):
        svc.check_request(_body(failover="yes"), root, RAW)
    with pytest.raises(svc.ServiceError, match="write must be single or multi"):
        svc.check_request(_body(write="all"), root, RAW)


def test_mongodb_always_records_automatic_failover(root):
    req = svc.check_request(_body("mongodb", balancer="", failover="off"), root, RAW)
    assert req["topology"]["failover"] == "auto"
    assert req["topology"]["write"] == "single"


def test_postgres_automatic_failover_arms_pgpool_and_keeps_secrets_out_of_the_log(root):
    fake = FakeShell()
    lines: List[str] = []
    svc.create(root, _body(failover="auto"), RAW, lines.append, run=fake, wait_seconds=1)
    pgpool = fake.having("10.0.0.20", "bitnamilegacy/pgpool")[-1]
    assert "PGPOOL_HEALTH_CHECK_PERIOD=10" in pgpool
    assert "PGPOOL_FAILOVER_ON_BACKEND_ERROR=on" in pgpool
    assert fake.having("10.0.0.20", "pgpool failover command installed")
    assert not fake.having("pskit.member=failover")
    entry = svc.load_state(root)["services"]["orders"]
    secret = entry["topology"]["secrets"]["replication_password"]
    assert secret not in "\n".join(lines)
    assert entry["env"]["PSKIT_ORDERS_PASSWORD"] not in "\n".join(lines)
    assert entry["resource"]["connection"]["failover"] == "auto"


def test_mysql_automatic_failover_starts_a_watcher_beside_proxysql(root):
    fake = FakeShell()
    lines: List[str] = []
    svc.create(root, _body("mysql", failover="auto"), RAW, lines.append, run=fake, wait_seconds=1)
    assert fake.having("10.0.0.20", "network", "create", "pskit-shop-orders-lb")
    assert fake.having("10.0.0.20", "pskit.member=failover")
    proxy = fake.having("10.0.0.20", "proxysql/proxysql")[-1]
    encoded = proxy.split("PSKIT_LB_SECRET_CONFIG=")[1].split("'")[0].split(" ")[0]
    config = base64.b64decode(encoded).decode("utf-8")
    assert 'mysql_ifaces="0.0.0.0:6032"' in config
    entry = svc.load_state(root)["services"]["orders"]
    assert entry["topology"]["watcher"]["container"] == "pskit-shop-orders-failover"
    secret = entry["topology"]["secrets"]["replication_password"]
    assert secret not in "\n".join(lines) and entry["env"]["PSKIT_ORDERS_PASSWORD"] not in "\n".join(lines)
    public = svc.public_entry(entry)
    assert "secrets" not in public["topology"]
    assert secret not in json.dumps(public)


def test_mysql_multi_primary_uses_a_ring_and_equal_writers(root):
    fake = FakeShell()
    lines: List[str] = []
    entry = svc.create(root, _body("mysql", write="multi"), RAW, lines.append, run=fake, wait_seconds=1)
    assert [m["name"] for m in entry["topology"]["members"]] == ["primary", "p1", "p2"]
    primary_run = fake.having("10.0.0.11", "pskit.member=primary")[0]
    second_run = fake.having("10.0.0.12", "pskit.member=p1", "docker", "run")[0]
    assert "--server-id=1" in primary_run and "--server-id=2" in second_run
    assert "--read-only=ON" not in primary_run and "--read-only=ON" not in second_run
    assert "--auto-increment-increment=3" in primary_run
    assert "--auto-increment-offset=1" in primary_run and "--auto-increment-offset=2" in second_run
    assert fake.having("10.0.0.13", "SOURCE_HOST='10.0.0.12'")
    assert fake.having("10.0.0.11", "SOURCE_HOST='10.0.0.13'")
    proxy = fake.having("10.0.0.20", "proxysql/proxysql")[-1]
    encoded = proxy.split("PSKIT_LB_SECRET_CONFIG=")[1].split("'")[0].split(" ")[0]
    config = base64.b64decode(encoded).decode("utf-8")
    assert 'address="10.0.0.11", port=3306, hostgroup=10' in config
    assert 'address="10.0.0.12", port=3306, hostgroup=10' in config
    assert "weight=1000" not in config
    assert 'mysql_ifaces="127.0.0.1:6032"' in config
    assert entry["resource"]["connection"]["write"] == "multi"
    assert entry["env"]["PSKIT_ORDERS_READ_URLS"] == ""
    secret = entry["topology"]["secrets"]["replication_password"]
    assert secret not in "\n".join(lines)


def test_multi_primary_firewall_lets_every_primary_reach_the_others(root):
    req = svc.check_request(_body("mysql", write="multi"), root, RAW)
    entry = {"service": "mysql", "key": "orders", "topology": req["topology"]}
    rules = rep.rules(entry, [network.who("app1", "10.0.0.50")])
    flat = {(r["address"], r["port"], tuple(s["address"] for s in r["sources"])) for r in rules}
    assert ("10.0.0.11", "3306", ("10.0.0.12", "10.0.0.13")) in flat
    assert ("10.0.0.12", "3306", ("10.0.0.11", "10.0.0.13")) in flat
    assert ("10.0.0.13", "3306", ("10.0.0.11", "10.0.0.12")) in flat
