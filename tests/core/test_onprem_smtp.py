"""The SMTP on-prem service: settings, docker run arguments, pskit.yml edits, guide and test events."""

from __future__ import annotations

import base64
import copy
import email
import email.policy

import pytest

from py_serverless_kit.config.schema import ServiceConfig
from py_serverless_kit.core import onprem_services as svc
from py_serverless_kit.core import onprem_smtp

from .test_onprem_services import RAW, FakeDocker

SSH = {"method": "ssh", "host": "20.40.60.80", "user": "ubuntu", "identity_file": "key.pem"}


def _raw(deploy=None, **options):
    raw = copy.deepcopy(RAW)
    raw["functions"]["on-mail"] = {"handler": "app.handlers.on_mail"}
    raw["provider"]["options"] = {**options, **({"deploy": deploy} if deploy else {})}
    return raw


def _create(tmp_path, raw, **body):
    fake = FakeDocker()
    req = {"key": "inbound", "service": "smtp", "domains": ["inbound.example.com"], **body}
    entry = svc.create(tmp_path, req, raw, lambda _l: None, run=fake, wait_seconds=1)
    run = next(c for c in fake.calls if "run" in c or any("'run'" in part for part in c))
    return entry, run


def test_local_service_publishes_the_port_and_reaches_the_host_through_docker(tmp_path):
    entry, run = _create(tmp_path, _raw(port=9000), attach=["on-mail"])
    assert run[:2] == ["docker", "run"]
    assert "127.0.0.1:25:25" in run and "host.docker.internal:host-gateway" in run
    env = dict(run[i + 1].split("=", 1) for i, arg in enumerate(run) if arg == "-e")
    assert env["PSKIT_FUNCTIONS_URL"] == "http://host.docker.internal:9000"
    assert env["PSKIT_SMTP_DOMAINS"] == "inbound.example.com" and env["PSKIT_SMTP_PORT"] == "25"
    assert base64.b64decode(env["PSKIT_SMTP_JS"]) == onprem_smtp.SCRIPT.read_bytes()
    assert "PSKIT_ADMIN_TOKEN" not in env
    assert run[-3:] == ["sh", "-c", onprem_smtp.START] and run[-4] == "node:22-alpine"
    assert entry["resource"] == {"type": "smtp", "external": True, "connection": {
        "host": "127.0.0.1", "port": 25, "domains": "inbound.example.com", "hostname": "mail.inbound.example.com"}}
    assert entry["smtp"]["network"] == "bridge" and not entry["env"] and "token" not in entry


def test_ssh_service_on_the_functions_server_uses_the_host_network(tmp_path):
    raw = _raw(deploy={"host": "20.40.60.80", "user": "ubuntu"}, admin_token="s3cret")
    entry, run = _create(tmp_path, raw, target=SSH, port=2525)
    command = run[-1]
    assert "'--network' 'host'" in command and "'-p'" not in command
    assert "'PSKIT_FUNCTIONS_URL=http://127.0.0.1:8080'" in command
    assert "'PSKIT_SMTP_PORT=2525'" in command and "'PSKIT_SMTP_BIND=0.0.0.0'" in command
    assert "'PSKIT_ADMIN_TOKEN=s3cret'" in command
    assert entry["address"] == "20.40.60.80"


def _cluster_project(tmp_path, orchestrator="swarm"):
    import json

    pskit = tmp_path / ".pskit"
    pskit.mkdir()
    servers = {f"vm{i}": {"host": f"20.0.0.{i}", "user": "ubuntu"} for i in (1, 2, 3)}
    (pskit / "onprem-servers.json").write_text(json.dumps({"servers": servers}))
    nodes = {"vm1": {"role": "master", "node": "n1", "address": "10.0.0.1"},
             "vm2": {"role": "worker", "node": "n2", "address": "10.0.0.2"}}
    clusters = {"prod": {"master": "vm1", "orchestrator": orchestrator, "nodes": nodes}}
    (pskit / "onprem-clusters.json").write_text(json.dumps({"clusters": clusters}))
    return pskit


@pytest.mark.parametrize("orchestrator, worker_url", [("swarm", "http://127.0.0.1:8080"),
                                                      ("kubernetes", "http://10.0.0.1:8080")])
def test_functions_url_on_a_scaling_cluster(tmp_path, orchestrator, worker_url):
    import json

    pskit = _cluster_project(tmp_path, orchestrator)
    body = {"domains": "a.example.com"}

    def url(server):
        target = svc.normalize_target({"server": server}, tmp_path)
        return onprem_smtp.check(body, _raw(), tmp_path, target)["functions_url"]

    # Not deployed yet: an SMTP server on a cluster node sends to that cluster.
    assert url("vm1") == "http://127.0.0.1:8080" and url("vm2") == worker_url
    with pytest.raises(svc.ServiceError, match="not deployed to a server yet"):
        url("vm3")
    # Deployed with --cluster (no target in pskit.yml): the last deploy is used, also from outside the cluster.
    (pskit / "onprem-dev").mkdir()
    (pskit / "onprem-dev" / "onprem_deployed.json").write_text(json.dumps({"cluster": "prod", "server": "vm1"}))
    assert url("vm3") == "http://20.0.0.1:8080" and url("vm2") == worker_url
    # Deployed with --server: that server.
    (pskit / "onprem-dev" / "onprem_deployed.json").write_text(json.dumps({"server": "vm3"}))
    assert url("vm3") == "http://127.0.0.1:8080" and url("vm1") == "http://20.0.0.3:8080"


def test_functions_url_defaults_and_errors(tmp_path):
    other = {"method": "ssh", "host": "20.40.60.81"}
    raw = _raw(deploy={"host": "20.40.60.80"})
    assert onprem_smtp.check({"domains": "a.example.com"}, raw, tmp_path, other)["functions_url"] == \
        "http://20.40.60.80:8080"
    with pytest.raises(svc.ServiceError, match="SSH server"):
        onprem_smtp.check({"domains": "a.example.com"}, raw, tmp_path, {"method": "local"})
    with pytest.raises(svc.ServiceError, match="not deployed to a server yet"):
        onprem_smtp.check({"domains": "a.example.com"}, _raw(), tmp_path, other)
    explicit = onprem_smtp.check({"domains": "a.example.com", "functions_url": "https://fn.example.com/"}, _raw(),
                                 tmp_path, other)
    assert explicit["functions_url"] == "https://fn.example.com"
    with pytest.raises(svc.ServiceError, match="domains"):
        onprem_smtp.check({}, _raw(), tmp_path, {"method": "local"})
    with pytest.raises(svc.ServiceError, match="not a domain"):
        onprem_smtp.check({"domains": ["not a domain"]}, _raw(), tmp_path, {"method": "local"})
    with pytest.raises(svc.ServiceError, match="leave user and password empty"):
        svc.check_request({"key": "m", "service": "smtp", "domains": "a.example.com", "password": "x" * 10},
                          tmp_path, _raw())


def test_admin_token_from_the_env_file(tmp_path):
    raw = _raw(admin_token="${env:HOST_TOKEN}")
    with pytest.raises(svc.ServiceError, match="HOST_TOKEN"):
        onprem_smtp.admin_token(raw, tmp_path, ".env.onprem")
    (tmp_path / ".env.onprem").write_text("HOST_TOKEN=abc\n", "utf-8")
    assert onprem_smtp.admin_token(raw, tmp_path, ".env.onprem") == "abc"


def test_apply_adds_the_resource_and_smtp_triggers(tmp_path):
    entry, _run = _create(tmp_path, _raw(), attach=["on-mail"])
    out = svc.apply_to_raw(_raw(), entry)
    assert out["resources"]["inbound"]["type"] == "smtp"
    assert out["functions"]["on-mail"]["events"] == [{"smtp": {"resource": "inbound"}}]
    config = ServiceConfig.model_validate(out)
    assert config.functions["on-mail"].events[0].config.name == "inbound"
    assert svc.remove_from_raw(out, "inbound")["functions"]["on-mail"]["events"] == []


def test_usage_guide_lists_the_dns_records(tmp_path):
    _create(tmp_path, _raw(deploy={"host": "20.40.60.80"}), target=SSH)
    text = svc.service_usage(tmp_path, "inbound", probe=False)["markdown"]
    assert "| A | `mail.inbound.example.com` | `20.40.60.80` |" in text
    assert "| MX | `inbound.example.com` | `10 mail.inbound.example.com` |" in text
    assert "Records" in text and "- smtp: {resource: inbound}" in text
    private = onprem_smtp.dns_records({"address": "10.0.0.5", "smtp": {"domains": ["x.example.com"]}})
    assert private[0]["value"] == "<public IP of the server>"


def test_catalog_has_the_smtp_service():
    item = next(c for c in svc.catalog() if c["id"] == "smtp")
    assert item["group"] == "Mail" and item["roles"] == ["smtp"] and item["auth"] is False


def test_test_event_has_the_simple_fields_ses_records_and_raw_content():
    ev = onprem_smtp.test_event({"from": "Jane <jane@client.org>", "to": ["support@example.com"],
                                 "cc": "team@example.com", "subject": "Order", "text": "Hi", "html": "<p>Hi</p>",
                                 "attachments": [{"filename": "a.txt", "content_type": "text/plain",
                                                  "content": "Total: 42"}]}, "inbound")
    assert ev["from"] == "jane@client.org" and ev["from_name"] == "Jane" and ev["cc"] == ["team@example.com"]
    assert base64.b64decode(ev["attachments"][0]["content"]) == b"Total: 42" and ev["attachments"][0]["size"] == 9
    ses = ev["Records"][0]["ses"]
    assert ev["Records"][0]["eventSource"] == "aws:ses"
    assert ses["mail"]["commonHeaders"]["subject"] == "Order"
    assert ses["mail"]["destination"] == ["support@example.com", "team@example.com"]
    message = email.message_from_bytes(base64.b64decode(ev["content"]), policy=email.policy.default)
    assert message["Subject"] == "Order" and [p.get_filename() for p in message.iter_attachments()] == ["a.txt"]
    assert onprem_smtp.test_event(ev) is ev


def _deployed(pskit, **data):
    import json

    (pskit / "onprem-dev").mkdir(exist_ok=True)
    (pskit / "onprem-dev" / "onprem_deployed.json").write_text(json.dumps(data))


def _url_in(call):
    text = " ".join(call)
    return next(p.split("=", 1)[1].strip("'") for p in text.split() if "PSKIT_FUNCTIONS_URL=" in p)


def test_deploy_points_the_smtp_server_at_where_the_functions_run_now(tmp_path):
    pskit = _cluster_project(tmp_path)
    _deployed(pskit, server="vm1")
    fake = FakeDocker()
    target = {"server": "vm3"}
    entry = svc.create(tmp_path, {"key": "inbound", "service": "smtp", "domains": "a.example.com", "target": target},
                       _raw(), lambda _l: None, run=fake, wait_seconds=1)
    assert entry["smtp"]["functions_url"] == "http://20.0.0.1:8080" and entry["smtp"]["functions_url_auto"]

    # Same place: nothing to do.
    fake.calls.clear()
    assert onprem_smtp.retarget(tmp_path, _raw(), ["inbound"], lambda _l: None, run=fake) == []
    assert fake.calls == []

    # vm1 removed, the functions deployed to vm2: the container is started again with vm2's URL.
    _deployed(pskit, server="vm2")
    lines = []
    assert onprem_smtp.retarget(tmp_path, _raw(), ["inbound"], lines.append, run=fake) == ["inbound"]
    run = next(c for c in fake.calls if "'run'" in " ".join(c))
    assert _url_in(run) == "http://20.0.0.2:8080"
    assert any("'rm' '-f'" in " ".join(c) for c in fake.calls)
    assert svc.load_state(tmp_path)["services"]["inbound"]["smtp"]["functions_url"] == "http://20.0.0.2:8080"
    assert any("was http://20.0.0.1:8080" in line for line in lines)

    # Then to a cluster the SMTP server's machine is not in: the master's host.
    _deployed(pskit, cluster="prod", server="vm1")
    assert onprem_smtp.retarget(tmp_path, _raw(), ["inbound"], lambda _l: None, run=fake) == ["inbound"]
    assert svc.load_state(tmp_path)["services"]["inbound"]["smtp"]["functions_url"] == "http://20.0.0.1:8080"


def test_deploy_keeps_a_functions_url_that_was_typed_in(tmp_path):
    pskit = _cluster_project(tmp_path)
    _deployed(pskit, server="vm1")
    fake = FakeDocker()
    svc.create(tmp_path, {"key": "inbound", "service": "smtp", "domains": "a.example.com", "target": {"server": "vm3"},
                          "functions_url": "http://20.0.0.1:8080"}, _raw(), lambda _l: None, run=fake, wait_seconds=1)
    _deployed(pskit, server="vm2")
    fake.calls.clear()
    assert onprem_smtp.retarget(tmp_path, _raw(), ["inbound", "missing"], lambda _l: None, run=fake) == []
    assert fake.calls == []


def test_smtp_servers_created_before_the_flag_follow_when_their_url_is_one_pskit_picks(tmp_path):
    pskit = _cluster_project(tmp_path)
    _deployed(pskit, server="vm2")
    state = {"services": {
        "old": {"key": "old", "service": "smtp", "target": svc.normalize_target({"server": "vm3"}, tmp_path),
                "container": "pskit-old", "image": "node:22-alpine", "volume": "pskit-old-data", "port": 25,
                "bind": "0.0.0.0", "smtp": {"domains": ["a.example.com"], "functions_url": "http://20.0.0.1:8080",
                                            "hostname": "mail.a.example.com", "max_size_mb": 25, "network": "host"}},
        "typed": {"key": "typed", "service": "smtp", "target": {"method": "ssh", "host": "20.0.0.3"},
                  "container": "pskit-typed", "smtp": {"functions_url": "https://lb.example.com/fn"}},
    }}
    svc.save_state(tmp_path, state)
    fake = FakeDocker()
    assert onprem_smtp.retarget(tmp_path, _raw(), ["old", "typed"], lambda _l: None, run=fake) == ["old"]
    saved = svc.load_state(tmp_path)["services"]
    assert saved["old"]["smtp"]["functions_url"] == "http://20.0.0.2:8080" and saved["old"]["smtp"]["functions_url_auto"]
    assert saved["typed"]["smtp"]["functions_url"] == "https://lb.example.com/fn"


def test_deployer_retargets_only_the_smtp_servers_its_functions_use(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from py_serverless_kit.core.deployer import Deployer

    raw = _raw()
    raw["resources"] = {"inbound": {"type": "smtp"}, "jobs": {"type": "queue"}}
    raw["functions"]["on-mail"]["events"] = [{"smtp": "inbound"}]
    raw["functions"]["on-job"] = {"handler": "app.handlers.on_job", "events": [{"queue": {"resource": "jobs"}}]}
    config = ServiceConfig.model_validate(raw)
    seen = []
    monkeypatch.setattr(onprem_smtp, "retarget", lambda root, r, keys, emit: seen.append((root, r, keys)))
    deployer = object.__new__(Deployer)
    deployer.project, deployer.echo = SimpleNamespace(root=tmp_path, config=config), lambda _l: None
    deployer._onprem_smtp()
    assert seen == [(tmp_path, {"service": config.service, "provider": {
        "name": "onprem", "stage": config.provider.stage, "options": config.provider.options}}, ["inbound"])]
