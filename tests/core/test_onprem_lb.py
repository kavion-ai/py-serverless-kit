"""Load balancing algorithms and the OpenResty config pskit writes (core/onprem_lb.py)."""

from __future__ import annotations

import shutil
import subprocess

import pytest

from py_serverless_kit.core import onprem_lb as lb

BACKENDS = [lb.backend("10.0.0.6", 8080, weight=3, server="app1"), lb.backend("10.0.0.7", 8080, server="app2"),
            lb.backend("10.0.0.5", 8080, backup=True, server="app0")]


def _sh_ok(text: str) -> None:
    shell = shutil.which("sh") or shutil.which("bash")
    if shell is None:
        return
    proc = subprocess.run([shell, "-n"], input=text.encode("utf-8"), capture_output=True)
    assert proc.returncode == 0, proc.stderr.decode()


def test_catalog_has_six_algorithms_static_and_dynamic():
    items = lb.catalog()
    assert [i["name"] for i in items] == ["round_robin", "sticky_round_robin", "weighted_round_robin", "ip_hash",
                                          "least_connections", "least_time"]
    assert {i["name"] for i in items if i["kind"] == "dynamic"} == {"least_connections", "least_time"}
    for item in items:
        assert item["pros"] and item["cons"] and item["summary"] and item["best_for"] and item["label"]
    assert lb.DEFAULT_ALGORITHM == "least_connections"  # what every load balancer used before


@pytest.mark.parametrize("alias, name", [("rr", "round_robin"), ("sticky", "sticky_round_robin"),
                                         ("WRR", "weighted_round_robin"), ("ip-hash", "ip_hash"),
                                         ("least_conn", "least_connections"), ("least-time", "least_time"),
                                         ("", "least_connections")])
def test_algorithm_aliases(alias, name):
    assert lb.normalize_algorithm(alias) == name


def test_unknown_algorithm_and_bad_values_are_refused():
    with pytest.raises(ValueError, match="unknown load balancing algorithm"):
        lb.normalize_algorithm("random")
    with pytest.raises(ValueError):
        lb.backend("10.0.0.6; evil", 80)
    with pytest.raises(ValueError, match="1..100"):
        lb.backend("10.0.0.6", 80, weight=0)
    with pytest.raises(ValueError, match="1..100"):
        lb.weights_for([], {"app1": 101})
    for bad in ("", "/", "__pskit", "-x", "a b", "x/../y"):
        with pytest.raises(ValueError):
            lb.normalize_path(bad)
    assert lb.normalize_path("/Team/XYZ/") == "team/xyz"
    assert lb.route_key("team/xyz") == "p-team-xyz" and lb.route_key(listen=8081) == "port-8081"


def test_each_algorithm_renders_its_upstream():
    def up(alg):
        return lb.upstream_conf("p-xyz", alg, BACKENDS)

    rr = up("round_robin")
    assert "least_conn" not in rr and "hash" not in rr and "weight=" not in rr  # round robin ignores weights
    assert "zone pskit_p_xyz 64k;" in rr and "server 10.0.0.5:8080 backup;" in rr
    assert "server 10.0.0.6:8080 weight=3 max_fails=3" in up("weighted_round_robin")
    assert "least_conn;" in up("least_connections") and "weight=3" in up("least_connections")
    ip = up("ip_hash")
    assert "hash $remote_addr consistent;" in ip
    assert "backup" not in ip  # nginx refuses backup with hash: the backup shares the requests
    sticky = up("sticky_round_robin")
    assert "hash $pskit_sticky_p_xyz consistent;" in sticky
    assert '"" $request_id;' in sticky and "default $cookie_pskit_lb_p_xyz;" in sticky
    assert 'pskit_lb_p_xyz=$request_id; Path=/; HttpOnly; SameSite=Lax' in sticky
    least_time = up("least_time")
    assert 'balancer_by_lua_block { pskit_lb.balance("p_xyz", {{"10.0.0.6", 8080, 3, false},' in least_time
    assert '{"10.0.0.5", 8080, 1, true}' in least_time and "server 0.0.0.1;" in least_time
    with pytest.raises(ValueError, match="no server"):
        lb.upstream_conf("p-xyz", "round_robin", [])


def test_path_route_strips_its_prefix_and_sets_the_cookie_path():
    files = lb.path_route_files("p-xyz", "xyz", "sticky_round_robin", BACKENDS, comment="pskit-xyz-dev")
    loc = files["conf.d/routes/p-xyz.loc"]
    assert "location = /xyz {\n    return 308 /xyz/$is_args$args;" in loc
    assert "location /xyz/ {" in loc and "proxy_pass http://pskit_p_xyz/;" in loc
    assert "proxy_set_header X-Forwarded-Prefix /xyz;" in loc
    assert "add_header Set-Cookie $pskit_set_p_xyz always;" in loc
    assert "Path=/xyz/;" in files["conf.d/r-p-xyz.conf"]
    timed = lb.path_route_files("p-xyz", "xyz", "least_time", BACKENDS)["conf.d/routes/p-xyz.loc"]
    assert 'log_by_lua_block { pskit_lb.record("p_xyz") }' in timed
    port = lb.port_route_conf("port-81", 81, "ip_hash", BACKENDS)
    assert "listen 81;" in port and "proxy_pass http://pskit_port_81;" in port


def test_base_files_and_main_server():
    files = lb.base_files("edge", 8088, "least_time")
    assert "lua_shared_dict pskit_lb 10m;" in files["nginx.conf"]
    assert 'pskit_lb = require "pskit_lb"' in files["nginx.conf"]
    assert "function M.balance(route, peers)" in files["pskit-lua/pskit_lb.lua"]
    main = files["conf.d/00-main.conf"]
    assert "listen 8088 default_server;" in main and "include /etc/nginx/conf.d/routes/*.loc;" in main
    assert "conf.d/00-main.conf" not in lb.base_files("", 80, "round_robin")  # a cluster's own: ports only
    assert '"algorithm": "least_time"' in files["lb.json"]


def test_apply_script_checks_swaps_and_reloads():
    write = {**lb.base_files("edge", 80, "round_robin"), **lb.path_route_files("p-xyz", "xyz", "round_robin", BACKENDS)}
    script = lb.apply_script("edge", write, lb.route_files("p-old"), checks={"p-xyz": "http://127.0.0.1:80/xyz/x"})
    assert script.startswith("#!/bin/sh\nset -eu\n")
    assert 'lb="$(pwd)/pskit-cluster/lb-edge"' in script and "flock" in script
    assert 'rm -f "$next/conf.d/r-p-old.conf"' in script and 'rm -f "$next/routes/p-old.json"' in script
    assert f"{lb.LB_IMAGE} nginx -t" in script and "dk exec pskit-lb-edge nginx -s reload" in script
    assert "the running one is unchanged" in script and "PSKIT_LB_OK=p-xyz" in script
    assert script.endswith("echo PSKIT_LB_DONE=1\n")
    _sh_ok(script)
    for text in (lb.read_script("edge"), lb.remove_script("edge"), lb.logs_script("edge", 10)):
        _sh_ok(text)
    with pytest.raises(ValueError):
        lb.apply_script("edge", {"conf.d/x.conf": "a\nPSKIT_LB\nb"})
    with pytest.raises(ValueError):
        lb.apply_script("edge", {}, checks={"x": "http://evil.example/"})


def test_describe():
    text = lb.describe("weighted_round_robin", BACKENDS)
    assert text == "weighted round robin over app1 x3, app2 (backup app0)"
