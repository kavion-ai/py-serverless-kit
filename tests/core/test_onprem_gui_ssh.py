"""Web UI login choices, the web UI check, and SSH logins without a key file (agent, password)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pytest

from py_serverless_kit.core import onprem_services as svc
from py_serverless_kit.runtime.onprem_host import parse_env_text

from .test_onprem_services import RAW, FakeDocker, _create


def _ui_run(fake: FakeDocker, image: str) -> List[str]:
    return [c for c in fake.calls if c[:2] == ["docker", "run"] and image in c][-1]


def test_web_ui_without_login(tmp_path):
    fake = FakeDocker()
    lines: List[str] = []
    _create(tmp_path, fake, key="cache", service="redis", role="cache", bind="0.0.0.0", gui=True, gui_login="none")
    run = _ui_run(fake, "rediscommander/redis-commander:latest")
    assert not any(a.startswith(("HTTP_USER=", "HTTP_PASSWORD=")) for a in run)
    entry = svc.load_state(tmp_path)["services"]["cache"]
    assert entry["gui"]["login"] == "no login" and entry["gui"]["login_mode"] == "none"
    assert "GUI_PASSWORD" not in (tmp_path / ".env.onprem").read_text("utf-8")

    _create(tmp_path, fake, key="events", service="kafka", bind="0.0.0.0")
    svc.add_gui(tmp_path, "events", lines.append, run=fake, login="none")
    run = _ui_run(fake, "provectuslabs/kafka-ui:v0.7.2")
    assert "AUTH_TYPE=DISABLED" in run and not any(a.startswith("SPRING_SECURITY_USER") for a in run)
    assert any("no login" in line and "anyone" in line for line in lines)        # warned: open interface

    _create(tmp_path, fake, key="docs", service="mongodb")
    svc.add_gui(tmp_path, "docs", lambda _l: None, run=fake, login="none")
    run = _ui_run(fake, "mongo-express:1.0.2")
    assert "ME_CONFIG_BASICAUTH=false" in run and not any(a.startswith("ME_CONFIG_BASICAUTH_USERNAME") for a in run)

    _create(tmp_path, fake, key="db", service="postgres")
    with pytest.raises(svc.ServiceError, match="always asks"):
        svc.add_gui(tmp_path, "db", lambda _l: None, run=fake, login="none")
    with pytest.raises(svc.ServiceError, match="always asks"):
        _create(tmp_path, fake, key="db2", service="postgres", gui=True, gui_login="none")
    assert svc.gui_login_choices("postgres") == ["password"] and svc.gui_login_choices("redis") == ["password", "none"]
    assert svc.gui_login_choices("rabbitmq") == []


def test_web_ui_with_your_own_password(tmp_path):
    fake = FakeDocker()
    _create(tmp_path, fake, key="cache", service="redis", role="cache", gui=True, gui_password="My-ui-pass1")
    run = _ui_run(fake, "rediscommander/redis-commander:latest")
    assert "HTTP_USER=admin" in run and "HTTP_PASSWORD=My-ui-pass1" in run
    assert parse_env_text((tmp_path / ".env.onprem").read_text("utf-8"))["PSKIT_CACHE_GUI_PASSWORD"] == "My-ui-pass1"

    _create(tmp_path, fake, key="docs", service="mongodb")
    svc.add_gui(tmp_path, "docs", lambda _l: None, run=fake)                      # default: the MongoDB login
    service_pw = parse_env_text((tmp_path / ".env.onprem").read_text("utf-8"))["PSKIT_DOCS_PASSWORD"]
    assert f"ME_CONFIG_BASICAUTH_PASSWORD={service_pw}" in _ui_run(fake, "mongo-express:1.0.2")
    gui = svc.add_gui(tmp_path, "docs", lambda _l: None, run=fake, password="Other-pass9")
    assert "ME_CONFIG_BASICAUTH_PASSWORD=Other-pass9" in _ui_run(fake, "mongo-express:1.0.2")
    assert gui["password_env"] == "PSKIT_DOCS_GUI_PASSWORD" and "PSKIT_DOCS_GUI_PASSWORD" in gui["login"]
    with pytest.raises(svc.ServiceError, match="8-128"):
        svc.add_gui(tmp_path, "docs", lambda _l: None, run=fake, password="short")


def test_second_web_ui_on_a_server_gets_the_next_port(tmp_path):
    fake = FakeDocker()
    _create(tmp_path, fake, key="a", service="redis", role="cache", gui=True)
    _create(tmp_path, fake, key="b", service="redis", role="cache", port=6390, gui=True)
    state = svc.load_state(tmp_path)["services"]
    assert state["a"]["gui"]["port"] == 8082 and state["b"]["gui"]["port"] == 8083
    assert "127.0.0.1:8083:8081" in _ui_run(fake, "rediscommander/redis-commander:latest")


class ServerDocker(FakeDocker):
    """A remote server: docker port / inspect answers and the server-side probe, keyed by what is asked."""

    def __init__(self, ports: str, probe: str = "200", facts: str = "", status: str = "running") -> None:
        super().__init__()
        self.ports, self.probe, self.facts, self.status = ports, probe, facts, status

    def __call__(self, argv: List[str], stdout: Optional[Path]) -> Tuple[int, str]:
        text = " ".join(argv)
        if "169.254.169.254" in text:
            self.calls.append(argv)
            return 0, self.facts
        if "http_code" in text and "u=" in text:
            self.calls.append(argv)
            return 0, self.probe
        if "'port'" in text or argv[-2:-1] == ["port"]:
            self.calls.append(argv)
            return 0, self.ports
        if "{{.State.Status}}" in text:
            self.calls.append(argv)
            return 0, self.status
        return super().__call__(argv, stdout)


def _remote_emq(tmp_path, _fake) -> Dict[str, object]:
    """ElasticMQ created earlier on an Azure VM over SSH (UI on 9325)."""
    entry = {"key": "jobs", "service": "elasticmq", "kind": "service", "container": "pskit-shop-jobs",
             "address": "13.72.87.80", "port": 9324, "bind": "0.0.0.0", "env": {},
             "target": {"method": "ssh", "host": "13.72.87.80", "user": "azureuser", "port": 22}}
    svc.save_state(tmp_path, {"services": {"jobs": entry}})
    return entry


def test_gui_check_names_the_azure_nsg_when_the_port_is_dropped(tmp_path):
    facts = "azure_rg=my-rg\nazure_vm=my-vm\ncloud=azure\nufw=inactive\nfirewalld=inactive\nips=10.0.0.4"
    fake = ServerDocker("9324/tcp -> 0.0.0.0:9324\n9325/tcp -> 0.0.0.0:9325\n9325/tcp -> [::]:9325", facts=facts)
    _remote_emq(tmp_path, fake)
    lines: List[str] = []
    result = svc.gui_check(tmp_path, "jobs", lines.append, run=fake, probe=lambda _u: "timeout")
    link = result["links"][0]
    assert result["ok"] is False and link["on_server"] == "http 200" and link["from_here"] == "timeout"
    assert "firewall drops" in link["verdict"]
    fixes = "\n".join(link["fix"])
    assert "az vm open-port -g my-rg -n my-vm --port 9325" in fixes and "subnet" in fixes
    assert "tunnel jobs --remote-port 9325" in fixes
    assert result["server"]["cloud"] == "azure"
    assert any("from this machine" in line for line in lines)


def test_gui_check_verdicts(tmp_path):
    fake = ServerDocker("9324/tcp -> 0.0.0.0:9324\n9325/tcp -> 0.0.0.0:9325")
    _remote_emq(tmp_path, fake)
    ok = svc.gui_check(tmp_path, "jobs", lambda _l: None, run=fake, probe=lambda _u: "http 200")
    assert ok["ok"] and ok["links"][0]["verdict"] == "reachable"

    fake.ports = "9324/tcp -> 127.0.0.1:9324\n9325/tcp -> 127.0.0.1:9325"
    local_only = svc.gui_check(tmp_path, "jobs", lambda _l: None, run=fake, probe=lambda _u: "http 200")["links"][0]
    assert "127.0.0.1 only" in local_only["verdict"] and "Bind 0.0.0.0" in "\n".join(local_only["fix"])

    fake.ports = "9324/tcp -> 0.0.0.0:9324"
    missing = svc.gui_check(tmp_path, "jobs", lambda _l: None, run=fake, probe=lambda _u: "http 200")["links"][0]
    assert "not published" in missing["verdict"]

    fake.ports, fake.probe = "9325/tcp -> 0.0.0.0:9325", "000"
    silent = svc.gui_check(tmp_path, "jobs", lambda _l: None, run=fake, probe=lambda _u: "http 200")["links"][0]
    assert "does not answer on the server" in silent["verdict"]

    fake.probe, fake.status = "200", "exited"
    stopped = svc.gui_check(tmp_path, "jobs", lambda _l: None, run=fake)["links"][0]
    assert stopped["verdict"] == "the container is not running"

    fake.status = "running"
    refused = svc.gui_check(tmp_path, "jobs", lambda _l: None, run=fake, probe=lambda _u: "refused")["links"][0]
    assert "refused" in refused["verdict"]

    state = svc.load_state(tmp_path)
    state["services"]["files"] = {**state["services"]["jobs"], "key": "files", "service": "fake-gcs"}
    svc.save_state(tmp_path, state)
    with pytest.raises(svc.ServiceError, match="no web UI"):
        svc.gui_check(tmp_path, "files", lambda _l: None, run=fake)


def test_ssh_password_is_kept_out_of_state_and_command_lines(tmp_path, monkeypatch):
    target = svc.normalize_target({"method": "ssh", "host": "10.0.0.5", "user": "ubuntu", "password": "S3cret!pw"}, tmp_path)
    secret = Path(target["password_file"])
    assert target["auth"] == "password" and secret.parent == tmp_path / ".pskit" / "ssh"
    assert secret.read_text("utf-8") == "S3cret!pw"
    assert "S3cret" not in json.dumps(target)
    argv = svc.docker_argv(target, ["ps"])
    assert argv[:3] == ["sshpass", "-f", str(secret)] and argv[3] == "ssh"
    assert "BatchMode=no" in argv and "PubkeyAuthentication=no" in argv and "S3cret!pw" not in argv
    tunnel = svc.tunnel_argv(target, 9000, 9325)
    assert tunnel[:4] == ["sshpass", "-f", str(secret), "ssh"] and "BatchMode=yes" not in tunnel

    agent = svc.normalize_target({"method": "ssh", "host": "10.0.0.5", "auth": "agent", "identity_file": "x.pem"}, tmp_path)
    assert "identity_file" not in agent and svc.docker_argv(agent, ["ps"])[0] == "ssh"
    assert "-i" not in svc.docker_argv(agent, ["ps"])
    with pytest.raises(svc.ServiceError, match="auth"):
        svc.normalize_target({"method": "ssh", "host": "h", "auth": "magic"}, tmp_path)

    from py_serverless_kit.providers import onprem_remote

    monkeypatch.setattr(onprem_remote.shutil, "which", lambda _n: None)
    with pytest.raises(svc.ServiceError, match="ssh-key"):
        svc.check_ssh_login(target)


def test_deploy_options_take_a_password_file(tmp_path):
    from py_serverless_kit.providers.onprem_spec import parse_deploy, uses_password, validate_identity

    spec = parse_deploy({"deploy": {"method": "ssh", "host": "10.0.0.5", "user": "u", "password_file": "~/srv.pass"}},
                        service="s", stage="dev", runtime="python3.12", architecture="x86_64")
    assert uses_password(spec) and spec.as_json()["ssh"]["password_file"].endswith("srv.pass")
    assert "password_file" in (validate_identity(spec) or "")                  # warned: the file is missing
    raw = {**RAW, "provider": {"name": "onprem", "options": {"deploy": {"host": "h", "auth": "password",
                                                                         "password_file": "/k/p"}}}}
    assert svc.default_target(raw)["password_file"].replace("\\", "/").endswith("/k/p")


def test_install_ssh_key_logs_in_once_then_uses_the_key(tmp_path):
    calls: List[List[str]] = []

    class Done:
        returncode = 0

    def fake(argv, **kwargs):
        calls.append(list(argv))
        if argv[0] == "ssh-keygen":
            key = Path(argv[-1])
            key.write_text("PRIVATE", "utf-8")
            Path(str(key) + ".pub").write_text("ssh-ed25519 AAAA pskit", "utf-8")
        return Done()

    key = svc.install_ssh_key({"host": "13.72.87.80", "user": "azureuser"}, lambda _l: None,
                              key_path=str(tmp_path / "k"), run=fake)
    assert key == tmp_path / "k"
    assert calls[0][0] == "ssh-keygen"
    assert calls[1][0] == "ssh" and "PubkeyAuthentication=no" in calls[1] and "azureuser@13.72.87.80" in calls[1]
    assert calls[2][:1] == ["ssh"] and "-i" in calls[2] and "BatchMode=yes" in calls[2]
