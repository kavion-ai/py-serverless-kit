"""On-prem service provisioning: commands, state, env file and pskit.yml edits, without Docker."""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional, Tuple

import pytest
import yaml

from py_serverless_kit.config.loader import load_config
from py_serverless_kit.core import onprem_services as svc
from py_serverless_kit.providers.onprem import DRIVERS
from py_serverless_kit.providers.onprem_catalog import DRIVER_CATALOG
from py_serverless_kit.runtime.onprem_host import parse_env_text

RAW = {
    "service": "shop",
    "provider": {"name": "onprem", "runtime": "python3.12"},
    "package": {"source": "."},
    "functions": {"api": {"handler": "app.handlers.api"}, "worker": {"handler": "app.handlers.work"}},
}


class FakeDocker:
    """Answers the docker / ssh commands the provisioner runs, and records them."""

    def __init__(self, fail: str = "") -> None:
        self.calls: List[List[str]] = []
        self.fail = fail

    def __call__(self, argv: List[str], stdout: Optional[Path]) -> Tuple[int, str]:
        self.calls.append(argv)
        text = " ".join(argv)
        if self.fail and self.fail in text:
            return 1, "boom"
        if "version" in argv and "--format" in argv:
            return 0, "27.1.0"
        if "inspect" in text:
            detailed = "Health" in text
            return 0, "running||2026-01-01T00:00:00Z|redis:7-alpine" if detailed else "running"
        if "command -v docker" in text:
            return 0, "present"
        if stdout is not None:
            stdout.write_bytes(b"DUMP")
        return 0, ""


def _create(tmp_path, fake, **body):
    req = {"key": "jobs", "service": "redis", **body}
    return svc.create(tmp_path, req, RAW, lambda _l: None, run=fake, wait_seconds=1)


def test_catalog_and_driver_lists_agree():
    ids = {item["id"] for item in svc.catalog()}
    assert {"redis", "valkey", "kafka", "nats", "rabbitmq", "postgres", "minio", "python", "docker"} <= ids
    for kind, drivers in DRIVER_CATALOG.items():
        assert {d["name"] for d in drivers} == set(DRIVERS[kind]), kind
    assert "redis_stream" in DRIVERS["queue"] and "pskit_host" in DRIVERS["queue"]
    for name in svc.DRIVER_TEMPLATES.values():
        assert (Path(svc.__file__).with_name("onprem_templates") / f"{name[0]}.py.txt").is_file()


def test_create_redis_queue_locally_writes_state_and_env_file(tmp_path):
    (tmp_path / ".gitignore").write_text(".pskit/\n", "utf-8")
    fake = FakeDocker()
    entry = _create(tmp_path, fake, port=6400, attach=["worker"])
    run = next(c for c in fake.calls if c[:2] == ["docker", "run"])
    assert "127.0.0.1:6400:6379" in run and "pskit-shop-jobs-data:/data" in run and run[-4] == "redis:7-alpine"
    password = next(a for a in run if a.startswith("REDIS_PASSWORD=")).split("=", 1)[1]
    assert entry["resource"] == {
        "type": "queue",
        "external": True,
        "options": {"driver": "redis", "url_env": "PSKIT_JOBS_URL", "key": "jobs"},
    }
    env = parse_env_text((tmp_path / ".env.onprem").read_text("utf-8"))
    assert env["PSKIT_JOBS_URL"] == f"redis://:{password}@127.0.0.1:6400/0"
    assert ".env.onprem" in (tmp_path / ".gitignore").read_text("utf-8")
    assert password not in json.dumps(svc.public_entry(entry))  # masked for the UI
    assert svc.load_state(tmp_path)["services"]["jobs"]["container"] == "pskit-shop-jobs"

    raw = svc.apply_to_raw(RAW, entry)
    assert raw["resources"]["jobs"]["options"]["driver"] == "redis"
    assert raw["provider"]["options"]["env_file"] == ".env.onprem"
    assert raw["functions"]["worker"]["events"] == [{"queue": {"resource": "jobs"}}]
    assert svc.apply_to_raw(raw, entry)["functions"]["worker"]["events"] == [{"queue": {"resource": "jobs"}}]
    assert "events" not in raw["functions"]["api"]

    # The edited file is a valid on-prem config.
    (tmp_path / "pskit.yml").write_text(yaml.safe_dump(raw), "utf-8")
    loaded = load_config(tmp_path / "pskit.yml")
    assert loaded.config.resources["jobs"].options["driver"] == "redis"

    cleaned = svc.remove_from_raw(raw, "jobs")
    assert "jobs" not in cleaned["resources"] and cleaned["functions"]["worker"]["events"] == []


def test_roles_and_services_produce_the_right_resources(tmp_path):
    fake = FakeDocker()
    stream = _create(tmp_path, fake, key="st", service="valkey", role="stream")
    assert stream["resource"]["type"] == "queue" and stream["resource"]["options"]["driver"] == "redis_stream"
    kafka = _create(tmp_path, fake, key="events", service="kafka", port=19092)
    assert kafka["resource"]["options"]["class"] == "pskit_drivers.kafka_queue:KafkaQueue"
    assert kafka["resource"]["options"]["bootstrap_servers"] == "127.0.0.1:19092"
    run = [c for c in fake.calls if c[:2] == ["docker", "run"]][-1]
    assert "internal://127.0.0.1:9093,external://127.0.0.1:19092,docker://pskit-shop-events:9095" in run
    assert any("rpk topic create events" in " ".join(c) for c in fake.calls)
    nats = _create(tmp_path, fake, key="tasks", service="nats")
    assert nats["resource"]["options"]["url_env"] == "PSKIT_TASKS_URL"
    assert (tmp_path / "pskit_drivers" / "kafka_queue.py").is_file()
    assert (tmp_path / "pskit_drivers" / "nats_queue.py").is_file()
    reqs = (tmp_path / "requirements.txt").read_text("utf-8")
    assert "kafka-python" in reqs and "nats-py" in reqs
    _create(tmp_path, fake, key="more-events", service="kafka", port=19093)
    assert (tmp_path / "requirements.txt").read_text("utf-8").count("kafka-python") == 1

    db = _create(tmp_path, fake, key="orders-db", service="postgres")
    assert db["resource"]["type"] == "database"
    assert db["resource"]["connection"]["password_env"] == "PSKIT_ORDERS_DB_PASSWORD"
    files = _create(tmp_path, fake, key="Media_Files", service="minio")
    assert files["resource"]["name"] == "media-files" and files["resource"]["options"]["driver"] == "minio"


def test_ssh_target_runs_docker_remotely_and_runtime_installs(tmp_path, monkeypatch):
    fake = FakeDocker()
    target = {"method": "ssh", "host": "10.0.0.5", "user": "ubuntu", "identity_file": "key.pem", "sudo": True}
    entry = _create(tmp_path, fake, target=target)
    run = next(c for c in fake.calls if c[0] == "ssh" and c[-1].startswith("sudo -n docker 'run'"))
    assert run[0] == "ssh" and "ubuntu@10.0.0.5" in run and run[-1].startswith("sudo -n docker 'run'")
    assert "'0.0.0.0:6379:6379'" in run[-1]
    assert entry["address"] == "10.0.0.5" and entry["target"]["identity_file"] == str(tmp_path / "key.pem")

    fake = FakeDocker()
    svc.create(tmp_path, {"key": "py", "service": "python", "target": target}, RAW, lambda _l: None, run=fake)
    assert fake.calls[0][0] == "scp" and "sh /tmp/pskit-install-python.sh" in fake.calls[1][-1]
    with pytest.raises(svc.ServiceError, match="SSH server"):
        svc.check_request({"key": "py2", "service": "python"}, tmp_path, RAW)


def test_default_target_follows_the_ssh_deploy():
    raw = {"provider": {"name": "onprem", "options": {"deploy": {"method": "ssh", "host": "h", "user": "u", "pem": "k"}}}}
    assert svc.default_target(raw) == {"method": "ssh", "host": "h", "user": "u", "port": 22, "sudo": False, "identity_file": "k"}
    assert svc.default_target(RAW) == {"method": "local"}


def test_validation_errors(tmp_path):
    for body, message in (
        ({"key": "1x", "service": "redis"}, "key must"),
        ({"key": "a", "service": "oracle"}, "service must"),
        ({"key": "a", "service": "postgres", "role": "queue"}, "can be used as"),
        ({"key": "a", "service": "redis", "port": 70000}, "port must"),
        ({"key": "a", "service": "redis", "image": "-x"}, "image must"),
        ({"key": "a", "service": "redis", "target": {"method": "ssh", "host": "-oProxy"}}, "target.host"),
        ({"key": "a", "service": "redis", "attach": ["bad name"]}, "attach"),
    ):
        with pytest.raises(svc.ServiceError, match=message):
            svc.check_request(body, tmp_path, RAW)


def test_status_backup_remove(tmp_path):
    fake = FakeDocker()
    _create(tmp_path, fake)
    info = svc.status(tmp_path, "jobs", run=fake)
    assert info["state"] == "running" and info["ready"] is True
    path = svc.backup(tmp_path, "jobs", lambda _l: None, run=fake)
    assert path.read_bytes() == b"DUMP" and path.suffix == ".rdb"
    assert svc.load_state(tmp_path)["services"]["jobs"]["backups"][0]["size"] == 4
    svc.remove(tmp_path, "jobs", lambda _l: None, delete_data=True, run=fake)
    assert ["docker", "volume", "rm", "pskit-shop-jobs-data"] in fake.calls
    assert "PSKIT_JOBS_URL" not in (tmp_path / ".env.onprem").read_text("utf-8")
    assert svc.list_services(tmp_path) == []
    with pytest.raises(svc.ServiceError, match="no on-prem service"):
        svc.status(tmp_path, "jobs", run=fake)


def test_failed_docker_run_is_reported(tmp_path):
    with pytest.raises(svc.ServiceError, match="boom"):
        _create(tmp_path, FakeDocker(fail="run -d"))
    assert svc.list_services(tmp_path) == []


def test_apply_under_providers_onprem_when_another_cloud_is_main(tmp_path):
    entry = _create(tmp_path, FakeDocker(), attach=["worker"])
    raw = dict(RAW, provider={"name": "aws"}, functions={"worker": {"handler": "app.h.w", "events": [{"http": "GET /"}]}})
    out = svc.apply_to_raw(raw, entry)
    assert "resources" not in out
    onprem = out["providers"]["onprem"]
    assert onprem["resources"]["jobs"]["options"]["driver"] == "redis"
    assert onprem["provider"]["options"]["env_file"] == ".env.onprem"
    assert onprem["functions"]["worker"]["events"] == [{"http": "GET /"}, {"queue": {"resource": "jobs"}}]
    assert out["functions"]["worker"]["events"] == [{"http": "GET /"}]  # aws untouched
    back = svc.remove_from_raw(out, "jobs")
    assert back["providers"]["onprem"]["functions"]["worker"]["events"] == [{"http": "GET /"}]


def test_resource_code_is_valid_for_every_provider_and_flavor():
    import shutil
    import subprocess
    import types

    from py_serverless_kit.core.resource_code import code_for, flavor_of

    cases = [(p, k, None, {}) for p in ("onprem", "aws", "gcp", "azure", "ibm") for k in ("queue", "storage", "topic")]
    cases += [("onprem", "database", s, {"host": "h"}) for s in ("postgres", "mysql", "mongodb", "redis", "memcached", "mailpit", None)]
    scripts = []
    for provider, kind, service, conn in cases:
        out = code_for(provider, "order-jobs", types.SimpleNamespace(type=kind, connection=conn), service)
        compile(out["python"], f"{provider}-{kind}-{service}.py", "exec")
        scripts.append(out["node"])
    assert "submit_queue" in code_for("onprem", "j", types.SimpleNamespace(type="queue", connection={}))["python"]
    assert flavor_of(types.SimpleNamespace(connection={"port": 5432})) == "postgres"
    assert flavor_of(types.SimpleNamespace(connection={"smtp_host": "m"})) == "smtp"
    if shutil.which("node"):
        for text in scripts:
            proc = subprocess.run(["node", "--check", "-"], input=text, capture_output=True, text=True)
            assert proc.returncode == 0, proc.stderr + text


def test_elasticmq_resource_recreates_its_queue(tmp_path):
    req = svc.check_request({"key": "sq", "service": "elasticmq"}, tmp_path, RAW)
    resource, env, _notes = svc._connection(req, "pw")
    assert resource["options"]["create_queue"] is True and env == {}


def test_credentials_are_validated_and_url_encoded(tmp_path):
    fake = FakeDocker()
    entry = _create(tmp_path, fake, key="cache", role="cache", user="app_user", password="Str0ng.pass#1")
    run = next(c for c in fake.calls if c[:2] == ["docker", "run"])
    assert "REDIS_USER=app_user" in run and "REDIS_PASSWORD=Str0ng.pass#1" in run
    env = parse_env_text((tmp_path / ".env.onprem").read_text("utf-8"))
    assert env["PSKIT_CACHE_URL"] == "redis://app_user:Str0ng.pass%231@127.0.0.1:6379/0"
    assert entry["user"] == "app_user"
    default = _create(tmp_path, FakeDocker(), key="cache2", role="cache")
    assert parse_env_text((tmp_path / ".env.onprem").read_text("utf-8"))["PSKIT_CACHE2_URL"].startswith("redis://:")
    assert default["user"] == "default"
    db = _create(tmp_path, FakeDocker(), key="db", service="postgres", user="orders", password="abcdefgh")
    assert db["resource"]["connection"]["user"] == "orders"
    for body, message in (
        ({"key": "k", "service": "kafka", "password": "abcdefgh"}, "without authentication"),
        ({"key": "k", "service": "redis", "password": "short"}, "password must"),
        ({"key": "k", "service": "redis", "password": "has space 123"}, "password must"),
        ({"key": "k", "service": "redis", "user": "1bad"}, "user must"),
    ):
        with pytest.raises(svc.ServiceError, match=message):
            svc.check_request(body, tmp_path, RAW)


def test_any_program_clients_are_valid_code(tmp_path):
    import shutil
    import subprocess

    from py_serverless_kit.core.onprem_clients import direct, via_host

    values = {"url_env": "PSKIT_X_URL", "key": "jobs", "queue_url": "http://h:9324/000000000000/jobs", "endpoint": "http://h:9",
              "bootstrap_servers": "h:9092", "topic": "events", "stream": "jobs", "subject": "jobs.jobs", "queue": "jobs",
              "bucket": "files", "host": "h", "port": 1}
    snippets = [direct(f, values) for f in ("redis", "redis_stream", "sqs", "kafka", "nats", "rabbitmq", "s3", "postgres",
                                            "mysql", "mongodb", "cache_redis", "memcached", "smtp")]
    snippets += [via_host(k, "jobs", "jobs", "http://127.0.0.1:8080") for k in ("queue", "storage", "topic")]
    for snip in snippets:
        assert snip is not None
        compile(snip["python"], "client.py", "exec")
        if shutil.which("node"):
            proc = subprocess.run(["node", "--check", "-"], input=snip["node"], capture_output=True, text=True)
            assert proc.returncode == 0, proc.stderr + snip["node"]


def test_service_usage_guides(tmp_path):
    fake = FakeDocker()
    for key, body in (("jobs", {}), ("st", {"service": "valkey", "role": "stream"}), ("events", {"service": "kafka"}),
                      ("tasks", {"service": "nats"}), ("db", {"service": "postgres"}), ("files", {"service": "minio"})):
        _create(tmp_path, fake, key=key, **body)
        md = svc.service_usage(tmp_path, key)["markdown"]
        assert "## Use it from any program" in md and "## Security" in md, key
        assert "```python" in md and "```js" in md, key
    hidden = svc.service_usage(tmp_path, "db")["markdown"]
    shown = svc.service_usage(tmp_path, "db", reveal=True)["markdown"]
    password = parse_env_text((tmp_path / ".env.onprem").read_text("utf-8"))["PSKIT_DB_PASSWORD"]
    assert password not in hidden and password in shown
    assert "without authentication" not in svc.service_usage(tmp_path, "db")["markdown"]
    assert "No authentication" in svc.service_usage(tmp_path, "events")["markdown"]


def test_new_services_map_to_existing_drivers(tmp_path, monkeypatch):
    monkeypatch.setattr(svc, "_http_answers", lambda _url: True)   # no real containers here
    fake = FakeDocker()
    expect = {
        ("df", "dragonfly", "stream"): "redis_stream",
        ("kdb", "keydb", "queue"): "redis",
        ("ak", "apache-kafka", "queue"): "custom",
        ("lav", "lavinmq", "queue"): "custom",
        ("azq", "azurite", "queue"): "azure_queue",
        ("azb", "azurite", "storage"): "azure_blob",
        ("lsq", "localstack", "queue"): "sqs",
        ("lsb", "localstack", "storage"): "s3",
        ("gcs", "fake-gcs", "storage"): "gcs",
        ("rfs", "rustfs", "storage"): "s3",
    }
    for (key, service, role), driver in expect.items():
        body = {"key": key, "service": service, "role": role}
        if service == "azurite":
            body["user"] = "acct1"
        entry = _create(tmp_path, fake, **body)
        assert entry["resource"]["options"]["driver"] == driver, key
    env = parse_env_text((tmp_path / ".env.onprem").read_text("utf-8"))
    assert "AccountName=acct1;" in env["PSKIT_AZQ_CONNECTION_STRING"]
    assert svc.load_state(tmp_path)["services"]["azb"]["resource"]["options"]["create_bucket"] is True
    assert (tmp_path / "pskit_drivers" / "rabbitmq_queue.py").is_file()   # LavinMQ speaks AMQP
    with pytest.raises(svc.ServiceError, match="password only"):
        svc.check_request({"key": "x", "service": "dragonfly", "user": "bob"}, tmp_path, RAW)
    with pytest.raises(svc.ServiceError, match="Azurite account"):
        svc.check_request({"key": "x", "service": "azurite", "user": "Bad_Name"}, tmp_path, RAW)


def test_extra_ports_move_with_the_main_port(tmp_path):
    fake = FakeDocker()
    entry = _create(tmp_path, fake, key="mq", service="rabbitmq", port=5682)
    run = [c for c in fake.calls if c[:2] == ["docker", "run"]][-1]
    assert "127.0.0.1:5682:5672" in run and "127.0.0.1:15682:15672" in run
    assert entry["resource"]["connection"]["management_url"] == "http://127.0.0.1:15682"
    assert [g["port"] for g in svc.gui_links(entry)] == [15682]
    assert svc.host_port({"service": "azurite", "port": 10020}, 10001) == 10021


def test_companion_web_ui(tmp_path):
    fake = FakeDocker()
    _create(tmp_path, fake, key="db", service="postgres", gui=True)
    entry = svc.load_state(tmp_path)["services"]["db"]
    assert entry["gui"]["name"] == "adminer" and entry["gui"]["port"] == 8089
    ui = next(c for c in fake.calls if c[:2] == ["docker", "run"] and "adminer:4.8.1" in c)
    assert "--network" in ui and "ADMINER_DEFAULT_SERVER=pskit-shop-db:5432" in ui
    assert ["docker", "network", "connect", "pskit-shop-db-net", "pskit-shop-db"] in fake.calls
    links = svc.gui_links(entry)
    assert links[0]["kind"] == "companion" and links[0]["url"] == "http://127.0.0.1:8089/"
    assert "## Web UI" in svc.service_usage(tmp_path, "db", probe=False)["markdown"]

    _create(tmp_path, fake, key="cache", service="redis", role="cache")
    gui = svc.add_gui(tmp_path, "cache", lambda _l: None, run=fake)
    run = next(c for c in fake.calls if c[:2] == ["docker", "run"] and "rediscommander/redis-commander:latest" in c)
    service_pw = parse_env_text((tmp_path / ".env.onprem").read_text("utf-8"))["PSKIT_CACHE_PASSWORD"]
    assert f"REDIS_PASSWORD={service_pw}" in run
    assert gui["password_env"] == "PSKIT_CACHE_GUI_PASSWORD" and "PSKIT_CACHE_GUI_PASSWORD" in gui["login"]
    svc.add_gui(tmp_path, "cache", lambda _l: None, run=fake)            # again: still the service password
    run = [c for c in fake.calls if c[:2] == ["docker", "run"] and "rediscommander/redis-commander:latest" in c][-1]
    assert f"REDIS_PASSWORD={service_pw}" in run
    svc.remove_gui(tmp_path, "cache", lambda _l: None, run=fake)
    assert "gui" not in svc.load_state(tmp_path)["services"]["cache"]
    assert "PSKIT_CACHE_GUI_PASSWORD" not in (tmp_path / ".env.onprem").read_text("utf-8")
    with pytest.raises(svc.ServiceError, match="built-in web UI"):
        _create(tmp_path, fake, key="mq", service="rabbitmq")
        svc.add_gui(tmp_path, "mq", lambda _l: None, run=fake)


def test_ensured_drivers_create_once_and_after_a_restart():
    from py_serverless_kit.runtime.drivers import Ensured

    calls = []

    class Inner:
        def __init__(self):
            self.lost = False

        def put(self, key, data):
            if self.lost:
                self.lost = False
                raise RuntimeError("s3: request failed (404): NoSuchBucket")
            calls.append(("put", key))

    inner = Inner()
    wrapped = Ensured(inner, lambda: calls.append("create") or 200, "bucket b")
    wrapped.put("a", b"1")
    wrapped.put("b", b"2")
    inner.lost = True                                  # the emulator restarted without its bucket
    wrapped.put("c", b"3")
    assert calls == ["create", ("put", "a"), ("put", "b"), "create", ("put", "c")]
    assert Ensured(inner, lambda: 409, "x")._ensure() is None   # already exists is fine
    with pytest.raises(RuntimeError, match="could not create"):
        Ensured(inner, lambda: 403, "x")._ensure()


def _server(tmp_path, data_dir="/home/azureuser"):
    from py_serverless_kit.core.onprem_servers import save_server

    save_server(tmp_path, "box", {"host": "10.0.0.5", "user": "azureuser", "auth": "agent", "sudo": True,
                                  "data_dir": data_dir})


def test_minio_named_volume_is_chowned_to_uid_1001(tmp_path):
    fake = FakeDocker()
    _create(tmp_path, fake, key="files", service="minio")
    chown = next(c for c in fake.calls if "--entrypoint" in c and "chown" in c)
    assert chown[chown.index("--entrypoint") + 1] == "chown"
    assert "--user" in chown and chown[chown.index("--user") + 1] == "0"
    assert "pskit-shop-files-data:/bitnami/minio/data" in chown
    assert "1001:1001" in chown
    service = next(c for c in fake.calls if c[:2] == ["docker", "run"] and "-d" in c)
    assert "bitnamilegacy/minio:2025.7.23" in service
    assert fake.calls.index(chown) < fake.calls.index(service)


def test_rustfs_bind_mount_is_chowned_and_probed_on_the_server(tmp_path):
    _server(tmp_path)
    fake = FakeDocker()
    notes = []
    entry = svc.create(
        tmp_path, {"key": "files", "service": "rustfs", "target": {"server": "box"}}, RAW, notes.append, run=fake
    )
    assert entry["resource"]["options"]["driver"] == "s3"
    joined = [" ".join(c) for c in fake.calls]
    assert any("chown -R '10001:10001' '/home/azureuser/pskit-shop-files'" in line for line in joined)
    probe = next(line for line in joined if "127.0.0.1:9000/health" in line)
    assert "%{http_code}" in probe and "10.0.0.5:9000" not in probe
    run = next(line for line in joined if "'run'" in line and "rustfs/rustfs:latest" in line)
    assert "RUSTFS_ADDRESS=:9000" in run and "/home/azureuser/pskit-shop-files:/data" in run
    assert any("owned by 10001:10001" in line for line in notes)


def test_bind_mount_owner_comes_from_the_image_user(tmp_path):
    _server(tmp_path, "/data/pskit")

    class Users(FakeDocker):
        def __call__(self, argv, stdout):
            if "{{.Config.User}}" in " ".join(argv):
                return 0, "472"
            return super().__call__(argv, stdout)

    class Named(FakeDocker):
        def __call__(self, argv, stdout):
            text = " ".join(argv)
            if "{{.Config.User}}" in text:
                return 0, "nobody"
            if "awk" in text and "nobody" in text:
                return 0, "65534:65534"
            return super().__call__(argv, stdout)

    grafana = Users()
    svc.create(tmp_path, {"key": "dash", "service": "grafana", "target": {"server": "box"}}, RAW, lambda _l: None,
               run=grafana)
    assert any("chown -R '472:472' '/data/pskit/pskit-shop-dash'" in " ".join(c) for c in grafana.calls)

    prom = Named()
    svc.create(tmp_path, {"key": "metrics", "service": "prometheus", "target": {"server": "box"}}, RAW,
               lambda _l: None, run=prom)
    assert any("chown -R '65534:65534' '/data/pskit/pskit-shop-metrics'" in " ".join(c) for c in prom.calls)


def test_restarting_container_reports_its_logs(tmp_path):
    class Crash:
        def __call__(self, argv, stdout):
            if "logs" in argv:
                return 0, "[FATAL] Server runtime failed: Io error: Permission denied (os error 13)"
            if "inspect" in argv:
                return 0, "restarting"
            if "version" in argv:
                return 0, "27.1.0"
            return 0, ""

    with pytest.raises(svc.ServiceError, match="Permission denied") as raised:
        svc.create(tmp_path, {"key": "files", "service": "rustfs"}, RAW, lambda _l: None, run=Crash(), wait_seconds=30)
    message = str(raised.value)
    assert "keeps restarting" in message and "not writable" in message
    assert svc.list_services(tmp_path) == []


def test_readiness_timeout_includes_the_container_logs(tmp_path):
    class Slow:
        def __call__(self, argv, stdout):
            if "logs" in argv:
                return 0, "still starting"
            if "exec" in argv:
                return 1, "not yet"
            if "inspect" in argv:
                return 0, "running"
            if "version" in argv:
                return 0, "27.1.0"
            return 0, ""

    with pytest.raises(svc.ServiceError, match="still starting"):
        svc.create(tmp_path, {"key": "jobs", "service": "redis"}, RAW, lambda _l: None, run=Slow(), wait_seconds=0)
