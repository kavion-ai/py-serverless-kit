"""Test events: the per-trigger guide, and sending real events to a deployed stage."""

from __future__ import annotations

import io
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from click.testing import CliRunner

from py_serverless_kit.cli.main import cli
from py_serverless_kit.core import testing
from py_serverless_kit.core.testing import TriggerError, guide, send

CONFIG = """
service: shop
provider: {name: aws, region: eu-west-1}
functions:
  api: {handler: app.handlers.hello, events: [{http: POST /orders}]}
  worker: {handler: app.handlers.hello, events: [{queue: jobs}]}
  images: {handler: app.handlers.hello, events: [{storage: {bucket: media, prefix: in/, suffix: .png}}]}
  fanout: {handler: app.handlers.hello, events: [{topic: orders}]}
  nightly: {handler: app.handlers.hello, events: [{schedule: {cron: "0 1 * * *", input: {report: x}}}]}
"""


def _record(url="https://api.example.com"):
    return {
        "provider": "aws",
        "stage": "dev",
        "status": "deployed",
        "functions": [
            {"name": "api", "url": url, "urls": [{"method": "POST", "url": url + "/orders"}]},
            {"name": "worker", "resource_name": "shop-dev-worker", "arn": "arn:aws:lambda:eu-west-1:1:function:w"},
            {"name": "images", "resource_name": "shop-dev-images"},
            {"name": "fanout", "resource_name": "shop-dev-fanout"},
            {"name": "nightly", "resource_name": "shop-dev-nightly", "arn": "arn:aws:lambda:eu-west-1:1:function:n"},
        ],
    }


def _by(g, name):
    return {t["index"]: t for t in next(f for f in g["functions"] if f["name"] == name)["triggers"]}


def test_guide_without_deploy_is_local_only(make_project):
    project = make_project(CONFIG)
    g = guide(project, None)
    assert not g["deployed"]
    worker = _by(g, "worker")
    assert worker[0]["sample"] == [{"order_id": 1, "action": "create"}]
    assert worker[0]["local"][0].startswith("pskit invoke -f worker -p aws -s dev -t queue -d ")
    assert worker[0]["remote"]["supported"] is False and worker[0]["remote"]["cli"] == []
    assert -1 in worker and worker[-1]["type"] == "invoke"  # direct invoke is always offered
    images = _by(g, "images")[0]
    assert images["sample"]["key"] == "in/hello.png"  # matches the trigger's prefix/suffix
    assert _by(g, "nightly")[0]["sample"] == {"report": "x"}  # the schedule's own input


def test_guide_when_deployed_has_commands_and_console_steps(make_project):
    project = make_project(CONFIG)
    g = guide(project, _record())
    worker = _by(g, "worker")[0]["remote"]
    assert worker["supported"] and worker["pskit"][0].startswith("pskit trigger -f worker -e 0 -p aws -s dev")
    assert "aws sqs send-message --region eu-west-1" in worker["cli"][0] and "--queue-name jobs" in worker["cli"][0]
    assert any("Send and receive messages" in s for s in worker["console"])
    assert "aws s3 cp hello.txt s3://media/in/hello.png" in _by(g, "images")[0]["remote"]["cli"][0]
    assert "aws sns publish" in _by(g, "fanout")[0]["remote"]["cli"][0]
    nightly = _by(g, "nightly")[0]["remote"]["cli"][0]
    assert "aws lambda invoke --function-name shop-dev-nightly" in nightly and '"__pskit":"schedule"' in nightly
    assert "curl -i -X POST https://api.example.com/orders" in _by(g, "api")[0]["remote"]["cli"][0]


class _FakeClient:
    def __init__(self, calls, service):
        self.calls, self.service = calls, service

    def __getattr__(self, op):
        def call(**kw):
            self.calls.append((self.service, op, kw))
            if op == "get_queue_url":
                return {"QueueUrl": "https://sqs.eu-west-1.amazonaws.com/1/jobs"}
            if op == "get_caller_identity":
                return {"Account": "123456789012"}
            if op == "invoke":
                return {"StatusCode": 200, "Payload": io.BytesIO(b'{"ok": true}')}
            return {"MessageId": "m-1"}

        return call


class _FakeSession:
    region_name = "eu-west-1"

    def __init__(self, calls):
        self.calls = calls

    def client(self, service):
        return _FakeClient(self.calls, service)


def test_send_aws_events(make_project, monkeypatch):
    project = make_project(CONFIG)
    calls: list = []
    monkeypatch.setattr(testing, "_boto3", lambda region: _FakeSession(calls))
    out = send(project, _record(), "worker", 0, [{"a": 1}, {"a": 2}])
    assert out["sent"] == 2 and [c[1] for c in calls].count("send_message") == 2
    assert calls[1][2]["MessageBody"] == '{"a":1}'
    calls.clear()
    send(project, _record(), "fanout", 0, {"message": {"x": 1}, "attributes": {"k": "v"}})
    publish = next(c for c in calls if c[1] == "publish")[2]
    assert publish["TopicArn"] == "arn:aws:sns:eu-west-1:123456789012:orders"
    assert publish["MessageAttributes"]["k"]["StringValue"] == "v"
    calls.clear()
    out = send(project, _record(), "images", 0, {"key": "in/a.png", "content": "hi"})
    assert out["uploaded"] == "s3://media/in/a.png" and calls[0][2]["Body"] == b"hi"
    calls.clear()
    out = send(project, _record(), "nightly", 0, {"report": "x"})
    sent = json.loads(calls[0][2]["Payload"])
    assert sent == {"__pskit": "schedule", "data": {"report": "x"}} and out["result"] == {"ok": True}


def test_send_http_to_the_deployed_url(make_project):
    seen = {}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            seen["path"] = self.path
            seen["body"] = self.rfile.read(int(self.headers["content-length"])).decode()
            data = b'{"created": true}'
            self.send_response(201)
            self.send_header("content-length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *a):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        project = make_project(CONFIG)
        out = send(project, _record(f"http://127.0.0.1:{server.server_address[1]}"), "api", 0, {"id": 7}, path="/orders?x=1")
        assert out["status"] == 201 and out["body"] == {"created": True}
        assert seen == {"path": "/orders?x=1", "body": '{"id":7}'}
    finally:
        server.shutdown()


def test_send_onprem_uses_the_host_api(make_project, monkeypatch):
    project = make_project(CONFIG.replace("name: aws, region: eu-west-1", "name: onprem"))
    calls = []

    class Control:
        base_url, token = "http://127.0.0.1:9", ""

        def request(self, method, path, body=None, timeout=None):
            calls.append((method, path, body))
            return {"ok": True}

    monkeypatch.setattr("py_serverless_kit.core.onprem_control.control_for", lambda record, root: Control())
    record = {**_record(), "provider": "onprem"}
    send(project, record, "worker", 0, [{"a": 1}])
    send(project, record, "fanout", 0, {"x": 1})
    send(project, record, "worker", -1, {"y": 2})
    assert calls == [
        ("POST", "/__pskit/queues/jobs", {"messages": [{"a": 1}]}),
        ("POST", "/__pskit/topics/orders", {"message": {"x": 1}}),
        ("POST", "/__pskit/invoke/worker", {"__pskit": "invoke", "data": {"y": 2}}),
    ]


def test_send_refuses_what_it_cannot_do(make_project):
    project = make_project(CONFIG)
    with pytest.raises(TriggerError, match="not deployed"):
        send(project, None, "worker", 0, {})
    with pytest.raises(TriggerError, match="no trigger #3"):
        send(project, _record(), "worker", 3, {})
    tencent = make_project(CONFIG.replace("name: aws, region: eu-west-1", "name: tencent"))
    with pytest.raises(TriggerError, match="isn't available on tencent"):
        send(tencent, {**_record(), "provider": "tencent"}, "fanout", 0, {})


def test_cli_trigger(make_project, monkeypatch, tmp_path):
    make_project(CONFIG)
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(cli, ["trigger", "--list"])
    assert result.exit_code == 0 and "pskit invoke -f worker" in result.output and "not deployed" in result.output
    result = CliRunner().invoke(cli, ["trigger", "-f", "worker", "-e", "0"])
    assert result.exit_code == 1 and "not deployed" in result.output
    (tmp_path / ".pskit" / "aws-dev").mkdir(parents=True)
    (tmp_path / ".pskit" / "aws-dev" / "deployment.json").write_text(json.dumps(_record()))
    calls: list = []
    monkeypatch.setattr(testing, "_boto3", lambda region: _FakeSession(calls))
    result = CliRunner().invoke(cli, ["trigger", "-f", "worker", "-e", "0", "-d", '{"n": 1}', "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["sent"] == 1


RESOURCES = """
service: shop
provider: {name: aws, region: eu-west-1}
functions:
  worker: {handler: app.handlers.hello, events: [{queue: {resource: jobs}}]}
resources:
  jobs: {type: queue}
  uploads: {type: storage, external: true, name: company-uploads}
  events: {type: topic, functions: [worker]}
  orders-db: {type: database, external: true, connection: {host: db.internal, port: 5432}}
"""


def test_resource_guide(make_project):
    project = make_project(RESOURCES)
    g = {r["key"]: r for r in testing.resource_guide(project, None)["resources"]}
    assert g["jobs"]["sendable"] and g["jobs"]["action"] == "Send a message"
    assert not g["jobs"]["remote"]["supported"] and "deploy first" in g["jobs"]["remote"]["reason"]
    # External resources exist already: testable without deploying, with commands.
    up = g["uploads"]
    assert up["remote"]["supported"] and up["name"] == "company-uploads"
    assert up["remote"]["pskit"][0].startswith("pskit resources send uploads -p aws -s dev")
    assert "s3://company-uploads/" in up["remote"]["cli"][0]
    db = g["orders-db"]
    assert not db["sendable"] and "PSKIT_RESOURCE_ORDERS_DB_HOST" in db["env"]
    assert 'resource("orders-db")' in db["snippets"]["python"] and 'r.get("host")' in db["snippets"]["node"]
    assert g["events"]["functions"] == ["worker"]


def test_send_resource(make_project, monkeypatch):
    project = make_project(RESOURCES)
    calls: list = []
    monkeypatch.setattr(testing, "_boto3", lambda region: _FakeSession(calls))
    out = testing.send_resource(project, None, "uploads", {"key": "a.txt", "content": "x"})
    assert out["uploaded"] == "s3://company-uploads/a.txt"
    with pytest.raises(TriggerError, match="deploy first"):
        testing.send_resource(project, None, "jobs", None)
    record = {"provider": "aws", "status": "deployed", "functions": []}
    out = testing.send_resource(project, record, "jobs", None)  # default sample
    assert out["sent"] == 1 and out["functions"] == ["worker"]
    with pytest.raises(TriggerError, match="can't send to a database"):
        testing.send_resource(project, record, "orders-db", {})
    with pytest.raises(TriggerError, match="unknown resource"):
        testing.send_resource(project, record, "nope", {})


def test_cli_resources_send(make_project, monkeypatch, tmp_path):
    make_project(RESOURCES)
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(cli, ["resources", "send", "--list"])
    assert result.exit_code == 0 and "orders-db" in result.output and "PSKIT_RESOURCE_ORDERS_DB_HOST" in result.output
    calls: list = []
    monkeypatch.setattr(testing, "_boto3", lambda region: _FakeSession(calls))
    result = CliRunner().invoke(cli, ["resources", "send", "uploads", "-d", '{"key": "k", "content": "c"}', "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["uploaded"] == "s3://company-uploads/k"


def test_azure_connection_strings_come_from_the_deployment(make_project, monkeypatch):
    import sys
    import types

    project = make_project(RESOURCES.replace("name: aws, region: eu-west-1", "name: azure"))
    monkeypatch.delenv("AZURE_STORAGE_CONNECTION_STRING", raising=False)
    monkeypatch.delenv("AZURE_SERVICEBUS_CONNECTION_STRING", raising=False)
    project.work_dir.mkdir(parents=True, exist_ok=True)
    state = {
        "resources": [
            {"mode": "managed", "type": "azurerm_storage_account", "name": "app",
             "instances": [{"attributes": {"primary_connection_string": "DefaultEndpointsProtocol=https;AccountName=x"}}]},
            {"mode": "managed", "type": "azurerm_servicebus_namespace", "name": "bus",
             "instances": [{"attributes": {"default_primary_connection_string": "Endpoint=sb://bus/"}}]},
        ]
    }
    (project.work_dir / "terraform.tfstate").write_text(json.dumps(state))
    conns = testing.azure_connections(project)
    assert conns == {"storage": "DefaultEndpointsProtocol=https;AccountName=x", "servicebus": "Endpoint=sb://bus/"}
    monkeypatch.setenv("AZURE_STORAGE_CONNECTION_STRING", "from-env")
    assert testing.azure_connections(project)["storage"] == "from-env"
    monkeypatch.delenv("AZURE_STORAGE_CONNECTION_STRING")

    sent = []

    class QueueClient:
        @classmethod
        def from_connection_string(cls, conn, queue, message_encode_policy=None):
            sent.append(("conn", conn, queue))
            return cls()

        def send_message(self, text):
            sent.append(("msg", text))

    fake = types.ModuleType("azure.storage.queue")
    fake.QueueClient = QueueClient  # type: ignore[attr-defined]
    fake.TextBase64EncodePolicy = lambda: None  # type: ignore[attr-defined]
    for name in ("azure", "azure.storage"):
        monkeypatch.setitem(sys.modules, name, sys.modules.get(name) or types.ModuleType(name))
    monkeypatch.setitem(sys.modules, "azure.storage.queue", fake)
    record = {"provider": "azure", "status": "deployed", "functions": []}
    out = testing.send_resource(project, record, "jobs", {"order_id": 1})
    assert out["sent"] == 1
    assert sent == [("conn", "DefaultEndpointsProtocol=https;AccountName=x", "jobs"), ("msg", '{"order_id":1}')]
    (project.work_dir / "terraform.tfstate").unlink()
    with pytest.raises(TriggerError, match="az storage account show-connection-string"):
        testing.send_resource(project, record, "jobs", {"order_id": 1})
