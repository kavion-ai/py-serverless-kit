"""Saved SSH servers (and deploying to one), software installs, consoles, browser terminals and secrets."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, List, Tuple

import pytest

from py_serverless_kit.core import onprem_console as con
from py_serverless_kit.core import onprem_runtimes as rts
from py_serverless_kit.core import onprem_servers as srv
from py_serverless_kit.core import onprem_services as svc
from py_serverless_kit.core import onprem_terminal as term

from .test_onprem_services import RAW, FakeDocker, _create

# ----------------------------------------------------------------------------- servers


def test_saved_servers_round_trip(tmp_path):
    srv.save_server(tmp_path, "edge1", {"host": "10.0.0.5", "user": "ubuntu", "auth": "key", "identity_file": "k.pem"},
                    description="rack 2")
    srv.save_server(tmp_path, "lab", {"host": "192.168.1.20", "user": "root", "auth": "password", "password": "Lab-pass1"})
    srv.save_server(tmp_path, "home", {"host": "home.example.com", "auth": "agent", "sudo": True})
    names = [s["name"] for s in srv.list_servers(tmp_path)]
    assert names == ["edge1", "home", "lab"]
    stored = json.loads((tmp_path / ".pskit" / "onprem-servers.json").read_text("utf-8"))["servers"]
    assert "Lab-pass1" not in json.dumps(stored)
    secret = Path(stored["lab"]["password_file"])
    assert secret.read_text("utf-8") == "Lab-pass1"
    assert stored["edge1"]["identity_file"].endswith("k.pem") and stored["edge1"]["description"] == "rack 2"
    assert "identity_file" not in stored["home"] and stored["home"]["sudo"] is True

    # Editing without retyping the password keeps it.
    srv.save_server(tmp_path, "lab", {"host": "192.168.1.21", "user": "root", "auth": "password"})
    assert srv.get_server(tmp_path, "lab")["password_file"] == str(secret)

    target = svc.normalize_target({"server": "edge1"}, tmp_path)
    assert target["host"] == "10.0.0.5" and target["server"] == "edge1"
    assert svc.describe_target(target) == "edge1 (ubuntu@10.0.0.5:22)"
    with pytest.raises(svc.ServiceError, match="no saved SSH server 'nope'"):
        svc.normalize_target({"server": "nope"}, tmp_path)
    with pytest.raises(srv.ServerError, match="server name"):
        srv.save_server(tmp_path, "9x", {"host": "h"})

    srv.remove_server(tmp_path, "lab")
    assert not secret.exists() and "lab" not in srv.load_servers(tmp_path)


def test_create_on_a_saved_server(tmp_path):
    srv.save_server(tmp_path, "edge1", {"host": "10.0.0.5", "user": "ubuntu", "auth": "agent"})
    fake = FakeDocker()
    entry = _create(tmp_path, fake, key="cache", service="redis", role="cache", target={"server": "edge1"})
    assert entry["target"]["host"] == "10.0.0.5" and entry["address"] == "10.0.0.5"
    assert any(c[0] == "ssh" and "ubuntu@10.0.0.5" in c for c in fake.calls)


def test_server_test_reports_facts(tmp_path):
    srv.save_server(tmp_path, "edge1", {"host": "10.0.0.5", "user": "ubuntu"})

    def fake(argv, _stdout):
        return 0, "os=Ubuntu 24.04 LTS\narch=x86_64\ncpus=2\nmemory_mb=3900\ndocker=Docker version 27.1.0\ndocker_access=sudo\nsudo=yes\n"

    result = srv.test_server(tmp_path, "edge1", run=fake)
    assert result["ok"] and result["facts"]["os"] == "Ubuntu 24.04 LTS" and result["facts"]["docker_access"] == "sudo"
    assert srv.test_server(tmp_path, "edge1", run=lambda a, s: (255, "ssh: connect timed out"))["ok"] is False


def test_deploy_to_a_saved_server(tmp_path, make_project, monkeypatch):
    srv.save_server(tmp_path, "edge1", {"host": "10.0.0.5", "user": "ubuntu", "auth": "key", "identity_file": "k.pem"})
    srv.save_server(tmp_path, "edge2", {"host": "10.0.0.6", "user": "deploy", "auth": "password", "password": "Pw-123456"})
    project = make_project(
        """
        service: shop
        provider:
          name: onprem
          options: {port: 9090, deploy: {server: edge1, path: /opt/shop}}
        functions: {api: {handler: app.handlers.hello}}
        """
    )
    from py_serverless_kit.core.project import Project

    loaded = Project.load(cwd=project.root)
    deploy = loaded.config.provider.options["deploy"]
    assert deploy["host"] == "10.0.0.5" and deploy["method"] == "ssh" and deploy["path"] == "/opt/shop"
    assert deploy["pem"].endswith("k.pem")

    monkeypatch.setenv(srv.SERVER_ENV, "edge2")                    # pskit deploy --server edge2
    deploy = Project.load(cwd=project.root).config.provider.options["deploy"]
    assert deploy["host"] == "10.0.0.6" and deploy["user"] == "deploy" and "pem" not in deploy
    assert deploy["password_file"].endswith(".pass") and deploy["auth"] == "password"
    monkeypatch.setenv(srv.SERVER_ENV, "missing")
    from py_serverless_kit.config.loader import ConfigError

    with pytest.raises(ConfigError, match="no saved SSH server"):
        Project.load(cwd=project.root)


def test_studio_deploy_job_passes_the_machine():
    from py_serverless_kit.studio.jobs import build_argv

    assert build_argv("deploy", "onprem", "dev", {"server": "edge1"})[-2:] == ["--server", "edge1"]
    assert "--server" not in build_argv("validate", "onprem", "dev", {"server": "edge1"})


# ----------------------------------------------------------------------------- software installs


def test_runtime_catalog_and_versions(tmp_path):
    ids = {c["id"]: c for c in svc.catalog() if c["kind"] == "runtime"}
    assert {"python", "docker", "nodejs", "nginx", "java", "go", "pm2", "caddy", "certbot", "git", "tools"} <= set(ids)
    assert ids["nodejs"]["versions"][0] == "22"
    assert rts.check_version("nodejs", None) == "22" and rts.check_version("go", "1.22.1") == "1.22.1"
    assert rts.check_version("python", None) == "system" and rts.check_version("python", "3.12") == "3.12"
    assert "python3-venv" in rts.install_script("python", "system")
    script = rts.install_script("python", "3.11")
    assert "UV_PYTHON_INSTALL_DIR" in script and "python install 3.11" in script and "/usr/local/bin/python3.11" in script
    with pytest.raises(ValueError):
        rts.check_version("python", "3.12; reboot")
    with pytest.raises(ValueError):
        rts.check_version("nginx", "1.2")
    with pytest.raises(ValueError):
        rts.check_version("nodejs", "22; rm -rf /")
    assert "setup_20.x" in rts.install_script("nodejs", "20")
    assert "go1.23.4.linux-$arch.tar.gz" in rts.install_script("go", "1.23.4")

    srv.save_server(tmp_path, "edge1", {"host": "10.0.0.5", "user": "ubuntu"})
    fake = FakeDocker()
    entry = svc.create(tmp_path, {"key": "node", "service": "nodejs", "version": "20", "target": {"server": "edge1"}},
                       RAW, lambda _l: None, run=fake)
    assert entry["kind"] == "runtime" and entry["version"] == "20"
    assert any(c[0] == "scp" for c in fake.calls)
    with pytest.raises(svc.ServiceError, match="version"):
        svc.check_request({"key": "n2", "service": "nodejs", "version": "x", "target": {"server": "edge1"}}, tmp_path, RAW)


# ----------------------------------------------------------------------------- consoles


def _entry(service: str, **extra) -> Dict[str, object]:
    return {"key": "k", "service": service, "container": "pskit-shop-k", "user": extra.pop("user", "app"),
            "env": {"PSKIT_K_PASSWORD": "Pw-12345678", "PSKIT_K_TOKEN": "Tok-12345678", "PSKIT_K_ACCESS_KEY": "app",
                    "PSKIT_K_SECRET_KEY": "Sk-12345678"}, **extra}


@pytest.mark.parametrize(
    ("service", "line", "how", "expect"),
    [
        ("redis", "LLEN jobs", "exec", ["redis-cli", "--user", "app", "--pass", "Pw-12345678", "--no-auth-warning", "LLEN", "jobs"]),
        ("dragonfly", "PING", con.REDIS_CLI, ["redis-cli", "-h", "pskit-shop-k", "-p", "6379", "-a", "Pw-12345678"]),
        ("postgres", "SELECT 1;", "exec", ["psql", "-U", "app", "-d", "k", "-v", "ON_ERROR_STOP=1", "-c", "SELECT 1;"]),
        ("mysql", "SHOW TABLES;", "exec", ["env", "MYSQL_PWD=Pw-12345678", "mysql", "-u", "app", "-t", "k", "-e"]),
        ("mongodb", "db.stats()", "exec", ["mongosh", "--quiet", "-u", "app", "-p", "Pw-12345678"]),
        ("kafka", "topic list", "exec", ["rpk", "topic", "list", "-X", "brokers=127.0.0.1:9093"]),
        ("apache-kafka", "kafka-topics.sh --list", "exec", ["/opt/kafka/bin/kafka-topics.sh", "--list", "--bootstrap-server"]),
        ("nats", "stream ls", con.NATS_BOX, ["nats", "-s", "nats://pskit-shop-k:4222", "--user", "app"]),
        ("rustfs", "s3 ls", con.AWS_CLI, ["env", "AWS_ACCESS_KEY_ID=app", "AWS_SECRET_ACCESS_KEY=Sk-12345678"]),
        ("openbao", "kv list secret", "exec", ["env", "BAO_ADDR=http://127.0.0.1:8200", "BAO_TOKEN=Tok-12345678", "bao", "kv"]),
        ("fake-gcs", "/storage/v1/b", con.CURL, ["curl", "-sS", "--max-time", "20", "http://pskit-shop-k:4443/storage/v1/b"]),
    ],
)
def test_console_commands(service, line, how, expect):
    got_how, args = con.command_args(_entry(service), line)
    assert got_how == how
    assert args[: len(expect)] == expect


def test_console_runs_and_hides_credentials(tmp_path):
    fake = FakeDocker()
    _create(tmp_path, fake, key="cache", service="redis", role="cache", user="app")
    password = svc.load_state(tmp_path)["services"]["cache"]["env"]["PSKIT_CACHE_PASSWORD"]
    calls: List[List[str]] = []

    def run(argv, _stdout):
        calls.append(argv)
        return 0, f"echo {password}\nOK"

    result = con.run_line(tmp_path, "cache", "GET greeting", run=run)
    assert calls[-1][:3] == ["docker", "exec", "pskit-shop-cache"] and calls[-1][-2:] == ["GET", "greeting"]
    assert password not in result["output"] and password not in result["command"] and "***" in result["command"]
    con.run_line(tmp_path, "cache", "ls /data", shell=True, run=run)
    assert calls[-1][-3:] == ["sh", "-c", "ls /data"]
    with pytest.raises(con.ConsoleError, match="type a command"):
        con.run_line(tmp_path, "cache", "  ", run=run)
    info = con.console_info(svc.load_state(tmp_path)["services"]["cache"])
    assert info["available"] and "LLEN jobs" in info["examples"]
    assert con.console_info({"service": "azurite"})["available"] is False


def test_console_helper_container_joins_the_private_network(tmp_path):
    state = {"services": {"q": {"key": "q", "service": "elasticmq", "kind": "service", "container": "pskit-shop-q",
                                "target": {"method": "local"}, "env": {}}}}
    svc.save_state(tmp_path, state)
    calls: List[List[str]] = []
    con.run_line(tmp_path, "q", "sqs list-queues", run=lambda a, s: (calls.append(a), (0, "{}"))[1])
    assert ["docker", "network", "connect", "pskit-shop-q-net", "pskit-shop-q"] in calls
    last = calls[-1]
    assert last[:5] == ["docker", "run", "--rm", "--network", "pskit-shop-q-net"] and con.AWS_CLI in last
    assert last[-2:] == ["sqs", "list-queues"] and "http://pskit-shop-q:9324" in last


def test_server_shell_and_interactive_argv(tmp_path):
    srv.save_server(tmp_path, "edge1", {"host": "10.0.0.5", "user": "ubuntu"})
    seen: List[List[str]] = []
    out = con.run_server(srv.server_target(tmp_path, "edge1"), "df -h", run=lambda a, s: (seen.append(a), (0, "ok"))[1])
    assert out["output"] == "ok" and seen[0][0] == "ssh" and seen[0][-1] == "df -h"
    with pytest.raises(con.ConsoleError):
        con.run_server({"method": "local"}, "ls")

    _create(tmp_path, FakeDocker(), key="db", service="postgres", target={"server": "edge1"})
    argv = con.interactive_argv(tmp_path, "db")
    assert argv[0] == "ssh" and argv[1] == "-t" and "psql" in argv[-1] and "exec -it" in argv[-1].replace("'", "")


# ----------------------------------------------------------------------------- browser terminal


def test_terminal_for_a_server_and_a_service(tmp_path):
    key = tmp_path / "edge.pem"
    key.write_text("KEY", "utf-8")
    srv.save_server(tmp_path, "edge1", {"host": "10.0.0.5", "user": "ubuntu", "auth": "key", "identity_file": str(key)})
    calls: List[List[str]] = []

    def run(argv, _stdout):
        calls.append(argv)
        if argv[:3] == ["docker", "ps", "--filter"]:
            return 0, "7681\n"                       # one terminal already uses 7681
        return 0, ""

    result = term.start_terminal(tmp_path, lambda _l: None, server="edge1", run=run, build=lambda _d: 0)
    started = calls[-1]
    assert result["port"] == 7682 and result["url"].startswith("http://127.0.0.1:7682/") and result["url"].endswith("/")
    assert "127.0.0.1:7682:7681" in started and f"{key}:/pskit/key:ro" in started
    token = result["url"].split("/")[3]
    assert started[started.index("-b") + 1] == f"/{token}" and len(token) >= 20
    assert "ubuntu@10.0.0.5" in started[-1] and "chmod 600" in started[-1]

    _create(tmp_path, FakeDocker(), key="cache", service="redis", role="cache")
    term.start_terminal(tmp_path, lambda _l: None, key="cache", run=run, build=lambda _d: 0)
    started = calls[-1]
    assert "/var/run/docker.sock:/var/run/docker.sock" in started
    assert started[-1].startswith("exec docker exec -it pskit-shop-cache redis-cli")

    with pytest.raises(term.TerminalError):
        term.stop_terminal("redis")
    term.stop_terminal("pskit-term-7682", run=run)
    assert calls[-1] == ["docker", "rm", "-f", "pskit-term-7682"]


# ----------------------------------------------------------------------------- secret managers


def test_secret_manager_services(tmp_path):
    fake = FakeDocker()
    entry = _create(tmp_path, fake, key="secrets", service="openbao")
    env = json.loads(json.dumps(svc.load_state(tmp_path)["services"]["secrets"]["env"]))
    assert env["PSKIT_SECRETS_DRIVER"] == "vault" and env["PSKIT_SECRETS_URL"] == "http://127.0.0.1:8200"
    assert entry["resource"]["type"] == "custom" and entry["resource"]["connection"]["driver"] == "vault"
    run = next(c for c in fake.calls if c[:2] == ["docker", "run"])
    assert any(a.startswith("PSKIT_TOKEN=") for a in run) and "openbao/openbao:2.1.0" in run

    _create(tmp_path, fake, key="aws", service="localstack", role="secrets", port=4570)
    env = svc.load_state(tmp_path)["services"]["aws"]["env"]
    assert env["PSKIT_AWS_DRIVER"] == "aws" and env["PSKIT_AWS_URL"] == "http://127.0.0.1:4570"
    assert "options" not in svc.load_state(tmp_path)["services"]["aws"]["resource"]
    assert svc._mask("PSKIT_TOKEN=abc") == "PSKIT_TOKEN=***"


class _KV(BaseHTTPRequestHandler):
    store: Dict[str, Dict[str, str]] = {}
    seen: List[Tuple[str, str, Dict[str, str]]] = []

    def log_message(self, *_a):
        pass

    def _reply(self, status: int, body: object) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):  # noqa: N802
        self.seen.append(("GET", self.path, dict(self.headers)))
        if self.headers.get("X-Vault-Token") != "tok":
            return self._reply(403, {"errors": ["permission denied"]})
        name = self.path.split("/data/", 1)[1]
        if name not in self.store:
            return self._reply(404, {"errors": []})
        return self._reply(200, {"data": {"data": self.store[name]}})

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("content-length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        self.seen.append(("POST", self.path, dict(self.headers)))
        target = self.headers.get("x-amz-target")
        if target:                                     # a tiny Secrets Manager
            assert self.headers["authorization"].startswith("AWS4-HMAC-SHA256 Credential=test/")
            if target.endswith("GetSecretValue"):
                value = self.store.get("aws:" + body["SecretId"])
                if value is None:
                    return self._reply(400, {"__type": "ResourceNotFoundException", "message": "nope"})
                return self._reply(200, {"SecretString": value["value"]})
            if target.endswith("PutSecretValue"):
                assert body.get("ClientRequestToken")
                if "aws:" + body["SecretId"] not in self.store:
                    return self._reply(400, {"__type": "ResourceNotFoundException", "message": "nope"})
                self.store["aws:" + body["SecretId"]] = {"value": body["SecretString"]}
                return self._reply(200, {})
            if target.endswith("CreateSecret"):
                self.store["aws:" + body["Name"]] = {"value": body["SecretString"]}
                return self._reply(200, {})
        self.store[self.path.split("/data/", 1)[1]] = body["data"]
        return self._reply(200, {})


@pytest.fixture
def kv_server():
    _KV.store, _KV.seen = {}, []
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _KV)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def test_get_secret_vault_aws_and_env(kv_server, monkeypatch):
    from py_serverless_kit import SecretNotFound, get_secret, get_secrets, put_secret
    from py_serverless_kit.runtime import secrets as sec

    sec._cache.clear()
    monkeypatch.setenv("PSKIT_SECRETS_URL", kv_server)
    monkeypatch.setenv("PSKIT_SECRETS_TOKEN", "tok")
    put_secret("db-password", "s3cret")
    put_secret("stripe", {"key": "sk_1", "webhook": "wh_2"})
    assert get_secret("db-password") == "s3cret"
    assert get_secret("stripe", "webhook") == "wh_2" and get_secrets("stripe") == {"key": "sk_1", "webhook": "wh_2"}
    assert json.loads(get_secret("stripe")) == {"key": "sk_1", "webhook": "wh_2"}
    with pytest.raises(SecretNotFound):
        get_secret("nope")
    assert get_secret("nope", default="d") == "d"
    with pytest.raises(SecretNotFound, match="no field"):
        get_secret("stripe", "other")

    monkeypatch.setenv("PSKIT_AWS_DRIVER", "aws")
    monkeypatch.setenv("PSKIT_AWS_URL", kv_server)
    monkeypatch.setenv("PSKIT_AWS_ACCESS_KEY", "test")
    monkeypatch.setenv("PSKIT_AWS_SECRET_KEY", "test")
    put_secret("api-key", "v1", store="aws")              # CreateSecret
    put_secret("api-key", "v2", store="aws")              # PutSecretValue
    assert get_secret("api-key", store="aws") == "v2"
    put_secret("db", {"user": "u", "password": "p"}, store="aws")
    assert get_secret("db", "password", store="aws") == "p"

    monkeypatch.delenv("PSKIT_SECRETS_URL")
    monkeypatch.delenv("PSKIT_SECRETS_TOKEN")
    monkeypatch.setenv("PSKIT_SECRET_SMTP_PASSWORD", "mail-pw")
    assert get_secret("smtp-password") == "mail-pw"
    with pytest.raises(sec.SecretError, match="read-only"):
        put_secret("x", "y")


def test_get_secret_in_node(kv_server, tmp_path):
    import shutil
    import subprocess

    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    from py_serverless_kit import put_secret
    from py_serverless_kit.runtime import secrets as sec

    sec._cache.clear()
    runtime = Path(svc.__file__).resolve().parents[1] / "runtime_js" / "index.js"
    script = tmp_path / "t.js"
    script.write_text(
        f"const p = require({json.dumps(str(runtime))});\n"
        "(async () => { await p.putSecret('n', {a: '1'}); console.log(await p.getSecret('n', 'a'));"
        " console.log(await p.getSecret('missing', {default: 'd'})); })().catch((e) => { console.error(e); process.exit(1); });\n",
        "utf-8",
    )
    env = {**__import__("os").environ, "PSKIT_SECRETS_URL": kv_server, "PSKIT_SECRETS_TOKEN": "tok"}
    out = subprocess.run([node, str(script)], capture_output=True, text=True, env=env, timeout=60)
    assert out.returncode == 0, out.stderr
    assert out.stdout.split() == ["1", "d"]
    del put_secret


def test_host_control_for_a_chosen_server(tmp_path, monkeypatch):
    from py_serverless_kit.core.cloud_logs import OnPremLogs, log_backend
    from py_serverless_kit.core.onprem_control import control_for

    app = tmp_path / ".pskit" / "onprem-dev" / "onprem_app"
    app.mkdir(parents=True)
    (app / "pskit_host.json").write_text(json.dumps({"port": 9090, "admin_token": "tok", "endpoint": "http://10.0.0.5:9090",
                                                     "deploy": {"method": "ssh"}}), "utf-8")
    srv.save_server(tmp_path, "edge2", {"host": "10.0.0.6", "user": "u"})
    record = {"provider": "onprem", "stage": "dev", "key": "onprem-dev"}
    assert control_for(record, tmp_path).base_url == "http://10.0.0.5:9090"            # the last deploy
    chosen = control_for(record, tmp_path, "edge2")
    assert chosen.base_url == "http://10.0.0.6:9090" and chosen.token == "tok"
    monkeypatch.setenv(srv.SERVER_ENV, "edge2")                                   # pskit logs --server edge2
    assert control_for(record, tmp_path).base_url == "http://10.0.0.6:9090"
    monkeypatch.delenv(srv.SERVER_ENV)
    assert isinstance(log_backend(record, tmp_path, "edge2"), OnPremLogs)
    with pytest.raises(ValueError, match="no saved SSH server"):
        control_for(record, tmp_path, "nope")


# ----------------------------------------------------------------------------- a removed / renamed saved server
STALE_RAW = {**RAW, "provider": {"name": "onprem", "runtime": "python3.12",
                                 "options": {"port": 8080, "deploy": {"method": "ssh", "server": "VM_01"}}}}


def _vm_servers(root: Path) -> None:
    for name, host in (("VM_01_2cpu", "10.0.0.5"), ("VM_01_4cpu", "10.0.0.6"), ("VM_02_2cpu", "10.0.0.7")):
        srv.save_server(root, name, {"host": host, "user": "azureuser", "auth": "agent"})


def test_missing_server_names_close_matches_and_where_it_came_from(tmp_path):
    _vm_servers(tmp_path)
    with pytest.raises(srv.ServerError) as exc:
        srv.get_server(tmp_path, "VM_01", origin=svc.CONFIG_SERVER)
    text = str(exc.value)
    assert "Did you mean VM_01_2cpu or VM_01_4cpu?" in text and "VM_02_2cpu" not in text.split("Did you mean")[1]
    assert "pskit.yml provider.options.deploy.server names it" in text and "Change pskit.yml" in text
    assert srv.close_servers("vm_02_2CPU", srv.load_servers(tmp_path))[0] == "VM_02_2cpu"
    assert srv.close_servers("other", srv.load_servers(tmp_path)) == []

    options = {"deploy": {"method": "ssh", "server": "VM_01"}}
    with pytest.raises(srv.ServerError, match="pskit.yml provider.options.deploy.server names it"):
        srv.resolve_deploy(options, tmp_path, "dev")


def test_picked_server_works_while_pskit_yml_names_a_removed_one(tmp_path):
    _vm_servers(tmp_path)
    assert "Did you mean VM_01_2cpu" in svc.default_target_problem(STALE_RAW, tmp_path)
    assert svc.default_target_problem(RAW, tmp_path) == ""
    fake = FakeDocker()
    entry = svc.create(tmp_path, {"key": "jobs", "service": "redis", "target": {"method": "ssh", "server": "VM_01_2cpu"}},
                       STALE_RAW, lambda _l: None, run=fake, wait_seconds=1)
    assert entry["target"]["server"] == "VM_01_2cpu"
    # No target picked: the error says pskit.yml names the removed server.
    with pytest.raises(svc.ServiceError, match="names it.*Did you mean VM_01_2cpu"):
        svc.check_request({"key": "cache", "service": "redis"}, tmp_path, STALE_RAW, place=False)


def test_smtp_with_a_removed_functions_server_says_how_to_fix(tmp_path):
    _vm_servers(tmp_path)
    body = {"key": "mail", "service": "smtp", "domains": ["inbound.example.com"],
            "target": {"method": "ssh", "server": "VM_01_2cpu"}}
    with pytest.raises(svc.ServiceError, match="Did you mean VM_01_2cpu.*Or set functions_url"):
        svc.check_request(body, tmp_path, STALE_RAW, place=False)
    ok = svc.check_request({**body, "functions_url": "http://10.0.0.5:8080"}, tmp_path, STALE_RAW, place=False)
    assert ok["smtp"]["functions_url"] == "http://10.0.0.5:8080"


def test_remove_server_in_a_cluster_is_refused_and_warns_about_references(tmp_path):
    from py_serverless_kit.core import onprem_cluster as clu

    _vm_servers(tmp_path)
    with clu._LOCK:
        clu._save(tmp_path, {"fun": {"orchestrator": "swarm", "master": "VM_01_2cpu", "advertise": "10.0.0.5",
                                     "nodes": {"VM_01_2cpu": {"role": "master"}, "VM_02_2cpu": {"role": "worker"}}}})
    with pytest.raises(srv.ServerError, match="is in cluster fun; take it out first: pskit cluster leave fun VM_02_2cpu"):
        srv.remove_server(tmp_path, "VM_02_2cpu")
    assert "VM_02_2cpu" in srv.load_servers(tmp_path)

    raw = {**RAW, "provider": {"name": "onprem", "options": {"deploy": {"server": "VM_01_4cpu"}}}}
    warnings = srv.remove_server(tmp_path, "VM_01_4cpu", raw)
    assert warnings == ["pskit.yml provider.options.deploy.server still names 'VM_01_4cpu': point it at another "
                        "saved server"]
    with pytest.raises(srv.ServerError, match="Did you mean VM_01_2cpu"):
        srv.remove_server(tmp_path, "VM_01")
