"""Where an on-prem stage was deployed: remembered after deploy, used by trigger / logs / test, reached over SSH."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from py_serverless_kit.core import onprem_control as ctl
from py_serverless_kit.core import onprem_servers as srv
from py_serverless_kit.core.testing import TriggerError, send

SSH_SPEC = {
    "host": "127.0.0.1",
    "port": 8080,
    "endpoint": "http://10.0.0.5:8080",
    "admin_token": "tok",
    "deploy": {"method": "ssh", "ssh": {"host": "10.0.0.5", "user": "ubuntu", "port": 22, "path": "/opt/pskit/shop"}},
}
LOCAL_SPEC = {"host": "127.0.0.1", "port": 8080, "endpoint": "http://127.0.0.1:8080", "admin_token": "tok",
              "deploy": {"method": "local"}}
RECORD = {"provider": "onprem", "stage": "dev", "key": "onprem-dev", "status": "deployed",
          "endpoint": "http://127.0.0.1:8080"}


def _render(root: Path, spec: dict) -> Path:
    work = root / ".pskit" / "onprem-dev"
    (work / "onprem_app").mkdir(parents=True, exist_ok=True)
    (work / "onprem_app" / "pskit_host.json").write_text(json.dumps(spec), "utf-8")
    return work


@pytest.fixture(autouse=True)
def _no_routes(monkeypatch):
    monkeypatch.delenv(srv.SERVER_ENV, raising=False)
    ctl._ROUTES.clear()
    yield
    ctl._ROUTES.clear()


def test_last_deploy_wins_over_a_later_package(tmp_path):
    srv.save_server(tmp_path, "VM_01", {"host": "10.0.0.5", "user": "ubuntu"})
    work = _render(tmp_path, SSH_SPEC)
    data = ctl.remember_deploy(work, "VM_01")
    assert data["server"] == "VM_01" and "functions" not in data["spec"]
    assert ctl.deployed_server(tmp_path, "dev") == "VM_01"
    assert ctl.deployed_on(data["spec"], "VM_01")["label"] == "VM_01 (10.0.0.5)"

    _render(tmp_path, LOCAL_SPEC)  # `pskit package` without --server re-rendered the spec for this machine
    control = ctl.control_for(RECORD, tmp_path)
    assert control.base_url == "http://10.0.0.5:8080" and control.token == "tok"
    assert control.server == "VM_01" and control.ssh["host"] == "10.0.0.5" and control.remote_path == "/opt/pskit/shop"

    local = ctl.control_for(RECORD, tmp_path, ctl.LOCAL)
    assert local.base_url == "http://127.0.0.1:8080" and local.ssh is None


def test_resolve_deploy_goes_back_to_the_remembered_server(tmp_path):
    srv.save_server(tmp_path, "VM_01", {"host": "10.0.0.5", "user": "ubuntu"})
    srv.save_server(tmp_path, "VM_02", {"host": "10.0.0.6", "user": "root"})
    assert srv.resolve_deploy({}, tmp_path, "dev") is None  # never deployed: pskit.yml decides (this machine)
    ctl.remember_deploy(_render(tmp_path, SSH_SPEC), "VM_01")

    options: dict = {"deploy": {"install": "systemd"}}
    assert srv.resolve_deploy(options, tmp_path, "dev") == "VM_01"
    assert options["deploy"]["host"] == "10.0.0.5" and options["deploy"]["install"] == "systemd"

    options = {}
    assert srv.resolve_deploy(options, tmp_path, "dev", "VM_02") == "VM_02"  # --server wins
    assert options["deploy"]["host"] == "10.0.0.6"

    # pskit.yml written by a new project says `method: local`: a chosen or remembered server still deploys there.
    options = {"deploy": {"method": "local", "host_python": "python3.10"}}
    assert srv.resolve_deploy(options, tmp_path, "dev", "VM_02") == "VM_02"
    assert options["deploy"]["method"] == "ssh" and options["deploy"]["host"] == "10.0.0.6"
    options = {"deploy": {"method": "local"}}
    assert srv.resolve_deploy(options, tmp_path, "dev") == "VM_01"
    assert options["deploy"]["method"] == "ssh" and options["deploy"]["host"] == "10.0.0.5"
    options = {"deploy": {"method": "docker"}}
    assert srv.resolve_deploy(options, tmp_path, "dev", "VM_02") == "VM_02" and options["deploy"]["method"] == "docker"

    options = {"deploy": {"method": "ssh", "host": "10.9.9.9", "user": "x", "install": "systemd"}}
    assert srv.resolve_deploy(dict(options), tmp_path, "dev") is None  # an inline host in pskit.yml wins
    assert srv.resolve_deploy(options, tmp_path, "dev", ctl.LOCAL) is None  # --server local
    assert options["deploy"] == {"install": "systemd", "method": "local"}
    assert srv.resolve_deploy({}, tmp_path, "prod") is None  # another stage, other memory

    srv.remove_server(tmp_path, "VM_01")
    with pytest.raises(srv.ServerError, match="no longer exists"):
        srv.resolve_deploy({}, tmp_path, "dev")
    with pytest.raises(srv.ServerError, match="reserved"):
        srv.save_server(tmp_path, "local", {"host": "10.0.0.7"})


def test_deployer_records_where_it_deployed(tmp_path):
    from py_serverless_kit.core.deployer import Deployer

    work = _render(tmp_path, SSH_SPEC)
    project = SimpleNamespace(work_dir=work, config=SimpleNamespace(
        provider=SimpleNamespace(name="onprem", options={"deploy": {"server": "VM_01", "host": "10.0.0.5"}})))
    record: dict = {}
    Deployer._remember_onprem(SimpleNamespace(project=project), record)
    assert record["deployed_on"]["server"] == "VM_01" and record["deployed_on"]["host"] == "10.0.0.5"
    assert json.loads((work / ctl.DEPLOYED_FILE).read_text("utf-8"))["server"] == "VM_01"


def _fake_ssh(calls: list, answer: dict, code: int = 0, err: bytes = b""):
    def run(argv, input=None, capture_output=None, timeout=None):  # noqa: A002 - subprocess.run's own name
        calls.append({"argv": argv, "request": json.loads(input.decode("utf-8"))})
        return SimpleNamespace(returncode=code, stdout=json.dumps(answer).encode(), stderr=err)

    return run


def test_closed_port_is_reached_over_ssh(monkeypatch):
    calls: list = []
    body = base64.b64encode(json.dumps({"items": [], "next": 3}).encode()).decode()
    monkeypatch.setattr(ctl.subprocess, "run", _fake_ssh(calls, {"s": 200, "h": {}, "b": body}))
    control = ctl.HostControl("http://127.0.0.1:1", token="secret-tok",
                              ssh={"host": "10.0.0.5", "user": "ubuntu", "port": 22}, remote_port=8080,
                              remote_path="/opt/pskit/shop", server="VM_01")
    assert control.logs(since=2) == {"items": [], "next": 3}
    control.logs(local=True)
    assert "/__pskit/logs/local?" in calls[-1]["request"]["u"]
    request = calls[0]["request"]
    assert request["u"].startswith("http://127.0.0.1:8080/__pskit/logs?") and "since=2" in request["u"]
    assert request["h"]["x-pskit-token"] == "secret-tok"
    assert not any("secret-tok" in part for part in calls[0]["argv"])  # the token goes over stdin only
    assert "ubuntu@10.0.0.5" in calls[0]["argv"] and "/opt/pskit/shop/python/bin/python3" in calls[0]["argv"][-1]

    # The route is remembered: the next call does not try the closed port again.
    control.request("PUT", "/__pskit/storage/b/k.txt", data=b"hi")
    assert len(calls) == 3 and base64.b64decode(calls[2]["request"]["b"]) == b"hi"


def test_force_ssh_does_not_dial_the_url(monkeypatch):
    def boom(*_a, **_k):
        raise AssertionError("direct dial")

    monkeypatch.setattr(ctl.socket, "create_connection", boom)
    monkeypatch.setattr(ctl.subprocess, "run", _fake_ssh([], {"s": 200, "h": {}, "b": ""}))
    control = ctl.HostControl("http://127.0.0.1:8080", ssh={"host": "10.0.0.5", "user": "u"}, force_ssh=True)
    assert control.fetch("GET", "/__pskit/logs/local")[0] == 200


def test_ssh_route_failure_says_what_to_do(monkeypatch):
    monkeypatch.setattr(ctl.subprocess, "run", _fake_ssh(
        [], {}, code=3, err=b"pskit: no pskit host answers on port 8080 of this server (Connection refused)\n"))
    control = ctl.HostControl("http://127.0.0.1:1", ssh={"host": "10.0.0.5", "user": "u"}, server="VM_01")
    with pytest.raises(ctl.HostUnavailable, match="no pskit host answers on port 8080.*pskit deploy --server VM_01"):
        control.health()
    with pytest.raises(ctl.HostUnavailable, match="not reachable"):
        ctl.HostControl("http://127.0.0.1:1", timeout=1).health()  # no SSH login: plain error

    def missing(*_a, **_k):
        raise FileNotFoundError("ssh")

    monkeypatch.setattr(ctl.subprocess, "run", missing)
    with pytest.raises(ctl.HostUnavailable, match="not installed here"):
        control.health()


def test_send_onprem_storage_and_http_use_the_deployed_host(make_project, monkeypatch):
    project = make_project("""
service: shop
provider: {name: onprem}
functions:
  api: {handler: app.handlers.hello, events: [{http: GET /hello}]}
  images: {handler: app.handlers.hello, events: [{storage: {bucket: media-vm-03, prefix: in}}]}
""")
    calls = []

    class Control:
        base_url, token, where = "http://10.0.0.5:8080", "", "VM_01"

        def fetch(self, method, path, data=None, headers=None, query=None, timeout=None):
            calls.append((method, path, data))
            return 201, {}, b'{"ok": true}'

    monkeypatch.setattr("py_serverless_kit.core.onprem_control.control_for", lambda record, root: Control())
    record = {**RECORD, "functions": [{"name": "api", "urls": [{"method": "GET", "url": "http://127.0.0.1:8080/hello"}]},
                                      {"name": "images"}]}
    out = send(project, record, "images", 0, {"key": "in/hello world.txt", "content": "hi"})
    assert out["status"] == 201 and out["host"] == "VM_01"
    out = send(project, record, "api", 0, None)
    assert out["url"] == "http://10.0.0.5:8080/hello"  # not the 127.0.0.1 URL of a later re-render
    assert calls == [("PUT", "/__pskit/storage/media-vm-03/in/hello%20world.txt", b"hi"), ("GET", "/hello", None)]

    class Down(Control):
        def fetch(self, *a, **k):
            raise ctl.HostUnavailable("on-prem host at http://10.0.0.5:8080 is not reachable")

    monkeypatch.setattr("py_serverless_kit.core.onprem_control.control_for", lambda record, root: Down())
    with pytest.raises(TriggerError, match="not reachable"):
        send(project, record, "images", 0, {"key": "in/a.txt"})


def test_studio_passes_the_server_to_trigger_jobs_and_reports_the_deploy(tmp_path):
    from py_serverless_kit.studio.jobs import build_argv
    from py_serverless_kit.studio.server import _deployed_on

    argv = build_argv("trigger", "onprem", "dev", {"function": "f", "event": 0, "server": "VM_01"})
    assert argv[:7] == ["trigger", "--provider", "onprem", "--stage", "dev", "--server", "VM_01"]
    assert "--server" in build_argv("resource-send", "onprem", "dev", {"resource": "r", "server": "local"})
    assert "--server" not in build_argv("invoke", "onprem", "dev", {"function": "f", "server": "VM_01"})

    assert _deployed_on(tmp_path, "dev") is None
    ctl.remember_deploy(_render(tmp_path, SSH_SPEC), "VM_01")
    info = _deployed_on(tmp_path, "dev")
    assert info["server"] == "VM_01" and info["endpoint"] == "http://10.0.0.5:8080" and info["deployed_at"]



def test_stale_providers_block_that_shadows_provider_is_reported(make_project, tmp_path):
    srv.save_server(tmp_path, "VM_01", {"host": "10.0.0.5", "user": "ubuntu"})
    project = make_project("""
service: shop
provider:
  name: onprem
  options: {host: 0.0.0.0, port: 8080, deploy: {method: ssh, server: VM_01}}
functions:
  hello: {handler: app.handlers.hello, events: [{http: GET /hello}]}
providers:
  onprem:
    options: {host: 127.0.0.1, port: 8080, deploy: {method: local}}
  aws:
    region: us-east-1
""")
    found = {i.where: i.message for i in project.validate() if i.where.startswith("providers.")}
    assert set(found) == {"providers.onprem.options.host", "providers.onprem.options.deploy.method"}
    assert "'127.0.0.1', which overrides '0.0.0.0'" in found["providers.onprem.options.host"]
