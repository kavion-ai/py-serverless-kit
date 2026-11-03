"""Firewall rules with real server names (core/onprem_network.py), printed by each step and by pskit firewall."""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

import pytest
from click.testing import CliRunner

from py_serverless_kit.cli.main import cli
from py_serverless_kit.core import onprem_balancers as bal
from py_serverless_kit.core import onprem_cluster as clu
from py_serverless_kit.core import onprem_network as net
from py_serverless_kit.core import onprem_servers as srv
from tests.core.test_onprem_balancers import FakeServers
from tests.core.test_onprem_cluster import FakeSSH, _deploy


@pytest.fixture
def root(tmp_path: Path) -> Path:
    for name, host in (("edge1", "10.0.0.5"), ("edge2", "10.0.0.6"), ("edge3", "10.0.0.7"), ("lb1", "10.0.0.9")):
        srv.save_server(tmp_path, name, {"host": host, "user": "root", "auth": "agent"})
    return tmp_path


def _rule(rules, server, port, proto="tcp"):
    found = [r for r in net.merge(rules) if r["server"] == server and r["port"] == str(port) and r["proto"] == proto]
    assert found, f"no rule for {server} {proto}/{port}"
    return found[0]


def _sources(rule) -> List[str]:
    return sorted(s["name"] for s in rule["sources"])


def test_each_cluster_step_prints_its_rules_with_server_names(root):
    fake = FakeSSH()
    lines: List[str] = []
    clu.create_cluster(root, "prod", "swarm", "edge1", lines.append, run=fake)
    text = "\n".join(lines)
    assert "Firewall - cluster prod (Docker Swarm, master edge1)" in text
    assert "edge1 (10.0.0.5)" in text and "inbound  TCP 22" in text

    lines.clear()
    clu.join_server(root, "prod", "edge2", lines.append, run=fake)
    text = "\n".join(lines)
    assert "Firewall - edge2 joined cluster prod" in text
    assert "[REQUIRED] inbound  TCP 2377" in text and "from edge2 (10.0.0.6)" in text
    assert "      sudo ufw allow from 10.0.0.6 to any port 2377 proto tcp" in text
    assert "UDP 4789" in text

    rules = net.cluster("prod", clu.get_cluster(root, "prod"))
    assert _sources(_rule(rules, "edge1", 2377)) == ["edge2"]  # workers -> manager
    assert _sources(_rule(rules, "edge2", 7946, "udp")) == ["edge1"]
    assert _rule(rules, "edge1", 22)["sources"][0]["name"] == "admin"


@pytest.mark.parametrize("orch, port, proto, opener, source", [
    ("kubernetes", 6443, "tcp", "edge1", "edge2"), ("kubernetes", 10250, "tcp", "edge2", "edge1"),
    ("kubernetes", 8472, "udp", "edge2", "edge1"), ("nomad", 4647, "tcp", "edge1", "edge2"),
])
def test_orchestrator_ports(orch, port, proto, opener, source):
    item = {"orchestrator": orch, "master": "edge1", "nodes": {
        "edge1": {"address": "10.0.0.5"}, "edge2": {"address": "10.0.0.6"}}}
    assert _sources(_rule(net.cluster("prod", item), opener, port, proto)) == [source]


def test_deploy_then_load_balancer_moves_users_to_the_balancer(root):
    fake = FakeSSH()
    clu.create_cluster(root, "prod", "swarm", "edge1", lambda _l: None, run=fake)
    clu.join_server(root, "prod", "edge2", lambda _l: None, run=fake)
    lines: List[str] = []
    _deploy(root, fake, lines, orchestrator="swarm")
    text = "\n".join(lines)
    assert "Firewall - pskit-shop-dev on cluster prod" in text
    rules = net.cluster("prod", clu.get_cluster(root, "prod"))
    assert _sources(_rule(rules, "edge2", 8080)) == ["users"]
    assert "edge2" in _sources(_rule(rules, "edge1", 8080))  # web replicas -> main replica

    servers = FakeServers()
    lines.clear()
    bal.create_balancer(root, "edge", "lb1", lines.append, run=servers)
    assert any("load balancer edge on lb1" in line for line in lines)
    lines.clear()
    bal.attach_cluster(root, "edge", "prod", lines.append, run=servers)
    text = "\n".join(lines)
    assert "Firewall - load balancer edge -> cluster prod" in text
    assert "ufw allow from 10.0.0.9 to any port 8080 proto tcp" in text
    project = net.project(root)
    assert _sources(_rule(project, "lb1", 80)) == ["users"]
    assert "lb1" in _sources(_rule(project, "edge2", 8080))  # behind the load balancer now
    assert "users" not in _sources(_rule(net.cluster("prod", clu._with_named(root, "prod", clu.get_cluster(
        root, "prod"))), "edge2", 8080))


def test_placement_groups_open_their_ports_to_each_other():
    groups = {"api": {"server": "app1", "address": "10.0.0.5", "port": 8080},
              "gpu": {"server": "gpu1", "address": "10.0.0.7", "port": 8081}}
    rules = net.placement(groups, "api")
    assert _sources(_rule(rules, "app1", 8080)) == ["gpu1"] and _sources(_rule(rules, "gpu1", 8081)) == ["app1"]
    assert "logs and workflow starts" in _rule(rules, "app1", 8080)["why"]


def test_resource_rules_name_the_function_hosts():
    entry = {"key": "cache", "service": "redis", "port": 6379, "address": "10.0.0.8",
             "target": {"method": "ssh", "server": "db1", "host": "10.0.0.8"}}
    rules = net.resource(entry, [net.who("app1", "10.0.0.5")])
    assert _sources(_rule(rules, "db1", 6379)) == ["app1"]
    smtp = net.resource({**entry, "service": "smtp", "port": 2525}, [{**net.who("app1", "10.0.0.5"), "port": "8090"}])
    assert _sources(_rule(smtp, "db1", 25)) == ["internet"] and _sources(_rule(smtp, "app1", 8090)) == ["db1"]
    assert net.resource({**entry, "target": {"method": "local"}}, []) == []


def test_pskit_firewall_lists_every_server(root, monkeypatch):
    fake = FakeSSH()
    clu.create_cluster(root, "prod", "nomad", "edge1", lambda _l: None, run=fake)
    clu.join_server(root, "prod", "edge2", lambda _l: None, run=fake)
    (root / "pskit.yml").write_text("service: shop\nprovider: {name: onprem}\nfunctions: {}\n", "utf-8")
    monkeypatch.chdir(root)
    out = CliRunner().invoke(cli, ["firewall"]).output
    assert "edge1 (10.0.0.5)" in out and "TCP 4647" in out and "from edge2 (10.0.0.6)" in out
    data = json.loads(CliRunner().invoke(cli, ["firewall", "--server", "edge2", "--json"]).output)
    assert [s["server"] for s in data] == ["edge2"] and data[0]["ufw"]
