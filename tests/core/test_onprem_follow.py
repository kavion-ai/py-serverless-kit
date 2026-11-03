"""On-prem services follow the functions when they move to another server or cluster (core/onprem_follow.py)."""

from __future__ import annotations

import copy

from py_serverless_kit.core import onprem_follow
from py_serverless_kit.core import onprem_services as svc

from .test_onprem_services import RAW, FakeDocker
from .test_onprem_smtp import _cluster_project


def _raw(**options):
    raw = copy.deepcopy(RAW)
    raw["provider"]["options"] = options
    return raw


def _create(tmp_path, key, service="redis", **body):
    return svc.create(tmp_path, {"key": key, "service": service, **body}, _raw(), lambda _l: None, run=FakeDocker(),
                      wait_seconds=1)


def _follow(tmp_path, raw, *keys):
    lines = []
    changed = onprem_follow.follow(tmp_path, raw, list(keys), lines.append)
    return changed, "\n".join(lines)


def test_a_cluster_address_switches_when_the_functions_leave_the_cluster_and_back(tmp_path):
    _cluster_project(tmp_path)
    entry = _create(tmp_path, "jobs", role="queue", target={"cluster": "prod", "server": "vm2"})
    assert entry["address"] == "10.0.0.2" and entry["address_auto"]
    url_key = next(k for k in entry["env"] if k.endswith("_URL"))
    assert "@10.0.0.2:" in entry["env"][url_key]

    # The functions move to vm3, outside the cluster: the server's own address.
    changed, out = _follow(tmp_path, _raw(deploy={"server": "vm3"}), "jobs", "not-a-service")
    assert changed == ["jobs"] and "at 20.0.0.2 (was 10.0.0.2)" in out
    saved = svc.load_state(tmp_path)["services"]["jobs"]
    assert saved["address"] == "20.0.0.2" and "@20.0.0.2:" in saved["env"][url_key]
    env_text = (tmp_path / saved["env_file"]).read_text("utf-8")
    assert f"{url_key}={saved['env'][url_key]}" in env_text and "10.0.0.2" not in env_text

    # Same place again: nothing to do. Back on the cluster: its cluster address.
    assert _follow(tmp_path, _raw(deploy={"server": "vm3"}), "jobs")[0] == []
    assert _follow(tmp_path, _raw(cluster="prod"), "jobs")[0] == ["jobs"]
    assert svc.load_state(tmp_path)["services"]["jobs"]["address"] == "10.0.0.2"


def test_an_address_typed_in_is_kept(tmp_path):
    _cluster_project(tmp_path)
    _create(tmp_path, "jobs", role="queue", target={"cluster": "prod", "server": "vm2"}, address="redis.internal")
    assert _follow(tmp_path, _raw(deploy={"server": "vm3"}), "jobs") == ([], "")


def test_what_cannot_be_fixed_is_a_warning(tmp_path):
    import json

    pskit = _cluster_project(tmp_path)
    _create(tmp_path, "here")                                                    # this machine
    _create(tmp_path, "gone", target={"server": "vm3"})
    _create(tmp_path, "lo", target={"server": "vm2"}, bind="127.0.0.1")
    _create(tmp_path, "events", "kafka", role="queue", target={"cluster": "prod", "server": "vm2"})
    servers = json.loads((pskit / "onprem-servers.json").read_text())
    del servers["servers"]["vm3"]
    (pskit / "onprem-servers.json").write_text(json.dumps(servers))

    changed, out = _follow(tmp_path, _raw(deploy={"server": "vm1"}), "here", "gone", "lo", "events")
    assert changed == []
    assert "'here' runs on this machine" in out
    assert "'gone' ran on server 'vm3', which was removed" in out
    assert "'lo' listens on 127.0.0.1 of vm2 only" in out
    assert "'events' is reached at 10.0.0.2" in out and "address built in" in out
    # Functions on the same server as a 127.0.0.1 service, or on this machine with a local one: fine.
    assert _follow(tmp_path, _raw(deploy={"server": "vm2"}), "lo")[1] == ""
    assert _follow(tmp_path, _raw(), "here")[1] == ""


def test_services_from_before_the_flag_follow_when_pskit_picked_their_address(tmp_path):
    _cluster_project(tmp_path)
    _create(tmp_path, "jobs", role="queue", target={"cluster": "prod", "server": "vm2"})
    state = svc.load_state(tmp_path)
    del state["services"]["jobs"]["address_auto"]
    svc.save_state(tmp_path, state)
    assert _follow(tmp_path, _raw(deploy={"server": "vm3"}), "jobs")[0] == ["jobs"]


def test_firewall_lists_the_rules_for_the_services_used(tmp_path):
    _cluster_project(tmp_path)
    _create(tmp_path, "jobs", role="queue", target={"server": "vm2"})
    lines = []
    onprem_follow.firewall(tmp_path, ["jobs", "missing"], lines.append, "shop (dev)")
    assert any("shop (dev)" in line for line in lines) and any("6379" in line for line in lines)
