from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from py_serverless_kit.core import onprem_usage as usage

SERVERS = {
    "app1": {"host": "10.0.0.5", "user": "ubuntu", "port": 22},
    "app2": {"host": "10.0.0.6", "user": "ubuntu", "port": 22},
    "gpu1": {"host": "10.0.0.7", "user": "ubuntu", "port": 22},
    "lb1": {"host": "10.0.0.8", "user": "ubuntu", "port": 22},
    "db1": {"host": "10.0.0.9", "user": "ubuntu", "port": 22},
    "db2": {"host": "10.0.0.10", "user": "ubuntu", "port": 22},
    "spare": {"host": "10.0.0.11", "user": "ubuntu", "port": 22},
}


def _write(root: Path, name: str, data: Dict[str, Any]) -> None:
    path = root / ".pskit" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), "utf-8")


def _project(root: Path) -> Dict[str, Any]:
    _write(root, "onprem-servers.json", {"servers": SERVERS})
    _write(root, "onprem-clusters.json", {"clusters": {"prod": {
        "orchestrator": "swarm", "master": "app1", "advertise": "10.0.0.5",
        "nodes": {"app1": {"role": "master", "address": "10.0.0.5"}, "app2": {"role": "worker", "address": "10.0.0.6"}},
        "balancer": {"server": "lb1", "address": "10.0.0.8", "algorithm": "least_time"},
        "deployments": {"pskit-shop-prod": {}},
    }}})
    _write(root, "onprem-balancers.json", {"balancers": {"edge": {"server": "lb1", "address": "10.0.0.8", "port": 80,
                                                                   "clusters": ["prod"]}}})
    _write(root, "onprem-services.json", {"services": {
        "cache": {"key": "cache", "service": "redis", "kind": "service", "role": "cache", "port": 6379,
                  "target": {"method": "ssh", "server": "db1", "host": "10.0.0.9"}},
        "orders": {"key": "orders", "service": "postgres", "kind": "service", "port": 5432,
                   "target": {"method": "ssh", "server": "db1", "host": "10.0.0.9"},
                   "topology": {"mode": "replicated", "members": [
                       {"name": "primary", "role": "primary", "server": "db1", "address": "10.0.0.9", "port": 5432},
                       {"name": "r1", "role": "replica", "server": "db2", "address": "10.0.0.10", "port": 5432}],
                       "balancer": {"name": "lb", "role": "balancer", "server": "db2", "address": "10.0.0.10",
                                    "port": 6432}}},
        "node": {"key": "node", "service": "node", "kind": "runtime", "version": "22",
                 "target": {"method": "ssh", "server": "gpu1"}},
    }})
    return {
        "service": "shop",
        "provider": {"name": "onprem", "stage": "prod", "options": {
            "cluster": "prod",
            "placement": {"default": "api", "groups": {"api": {"cluster": "prod"},
                                                       "gpu": {"server": "gpu1", "functions": ["resize"]}}},
        }},
        "functions": {"api": {"handler": "handlers.api.main"}, "resize": {"handler": "handlers.img.resize"},
                      "report": {"handler": "handlers.report.main"}},
        "resources": {"cache": {"type": "cache", "functions": ["api"]}, "orders": {"type": "database"}},
    }


def test_every_place_a_server_is_used(tmp_path):
    raw = _project(tmp_path)
    out = usage.server_usage(tmp_path, raw)

    assert out["spare"] == []  # saved, named nowhere
    roles = {s: sorted((u["kind"], u["name"], u["role"]) for u in uses) for s, uses in out.items()}
    assert roles["app1"] == [("cluster", "prod", "master"), ("placement", "api", "function group on cluster prod")]
    assert ("cluster", "prod", "joined server") in roles["app2"]
    assert roles["gpu1"] == [("placement", "gpu", "function group"), ("runtime", "node", "installed")]
    assert roles["lb1"] == [("balancer", "edge", "load balancer"), ("cluster-balancer", "prod", "cluster load balancer")]
    assert roles["db1"] == [("service", "cache", "cache"), ("service", "orders", "primary")]
    assert roles["db2"] == [("service", "orders", "database load balancer"), ("service", "orders", "read replica")]

    gpu = next(u for u in out["gpu1"] if u["kind"] == "placement")
    assert gpu["functions"] == ["resize"] and gpu["view"] == "functions"
    api = next(u for u in out["app1"] if u["kind"] == "placement")
    assert api["functions"] == ["api", "report"]  # the default group gets every unlisted function
    cache = next(u for u in out["db1"] if u["name"] == "cache")
    assert cache["functions"] == ["api"]  # resources.cache.functions
    orders = next(u for u in out["db1"] if u["name"] == "orders")
    assert orders["functions"] == ["api", "report", "resize"]  # no functions: list -> all of them
    assert "not used" not in usage.describe(cache) and "functions: api" in usage.describe(cache)


def test_deploy_target_and_last_deploy(tmp_path):
    _write(tmp_path, "onprem-servers.json", {"servers": SERVERS})
    _write(tmp_path, "onprem-dev/onprem_deployed.json", {"server": "app2"})
    raw = {"provider": {"name": "onprem", "stage": "dev", "options": {"deploy": {"server": "app1"}}},
           "functions": {"hello": {"handler": "h.main"}}}
    out = usage.server_usage(tmp_path, raw)
    assert [(u["kind"], u["functions"]) for u in out["app1"]] == [("deploy", ["hello"])]
    assert [(u["kind"], u["name"]) for u in out["app2"]] == [("deployed", "onprem-dev")]
    # Another cloud's pskit.yml with a providers.onprem override still counts.
    other = {"provider": {"name": "aws"}, "providers": {"onprem": {"provider": {"options": {"deploy": {"server": "gpu1"}}}}}}
    assert [u["kind"] for u in usage.server_usage(tmp_path, other)["gpu1"]] == ["deploy"]


def test_a_used_server_that_is_no_longer_saved_still_shows(tmp_path):
    _write(tmp_path, "onprem-servers.json", {"servers": {}})
    raw = {"provider": {"name": "onprem", "options": {"deploy": {"server": "gone"}}}}
    assert [u["kind"] for u in usage.server_usage(tmp_path, raw)["gone"]] == ["deploy"]
    assert usage.server_usage(tmp_path, None) == {}


def test_network_map_has_inbound_and_outbound_edges(tmp_path):
    raw = _project(tmp_path)
    graph = usage.network_map(tmp_path, raw)
    ids = {n["id"]: n for n in graph["nodes"]}
    assert ids["spare"]["uses"] == 0 and ids["spare"]["kind"] == "server"
    assert ids["app1"]["uses"] == 2 and "master" in ids["app1"]["roles"]
    # Swarm: the master accepts the other servers on 2377; pskit reaches every server over SSH.
    assert any(e["from"] == "app2" and e["to"] == "app1" and "2377" in e["port"] for e in graph["edges"])
    assert any(e["from"] == "admin" and e["to"] == "app1" and e["port"] == "22" for e in graph["edges"])
    # The cluster's load balancer sends the requests to the cluster servers.
    assert any(e["from"] == "lb1" and e["to"] in ("app1", "app2") for e in graph["edges"])
    assert all(e["level"] in ("required", "feature", "optional") for e in graph["edges"])
    assert any(e["from"] == "db2" and e["to"] == "db1" and e["port"] == "5432" for e in graph["edges"])  # replication
    assert graph["nodes"][0]["kind"] == "admin"


def test_resource_bindings_show_who_really_uses_a_resource(tmp_path):
    (tmp_path / "handlers").mkdir()
    (tmp_path / "handlers" / "api.py").write_text('from py_serverless_kit import resource\nr = resource("orders")\n')
    (tmp_path / "handlers" / "report.py").write_text('import os\nos.environ["PSKIT_RESOURCE_MY_CACHE_URL"]\n')
    (tmp_path / "handlers" / "worker.py").write_text("def main(event, context): ...\n")
    raw = {
        "functions": {
            "api": {"handler": "handlers.api.main"},
            "report": {"handler": "handlers.report.main"},
            "worker": {"handler": "handlers.worker.main", "events": [{"queue": {"resource": "jobs"}}]},
        },
        "resources": {"orders": {"type": "database"}, "my-cache": {"type": "cache", "functions": ["api", "report"]},
                      "jobs": {"type": "queue"}, "unused": {"type": "storage"}},
    }
    out = usage.resource_bindings(tmp_path, raw)
    assert out["orders"] == {"restricted": False, "bound": ["api", "report", "worker"], "triggers": [],
                             "code": ["api"], "used_by": ["api"]}
    assert out["my-cache"]["restricted"] and out["my-cache"]["bound"] == ["api", "report"]
    assert out["my-cache"]["used_by"] == ["report"]
    assert out["jobs"]["triggers"] == ["worker"] and out["jobs"]["used_by"] == ["worker"]
    assert out["unused"]["used_by"] == []
