"""``POST /__pskit/smtp/<resource>``: mail from the SMTP on-prem service runs the functions attached to it."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from py_serverless_kit.core.deployer import Deployer
from py_serverless_kit.core.onprem_smtp import test_event as make_mail
from py_serverless_kit.runtime.onprem_host import Host, activate_layout

from .test_onprem_host import _expect_http_error, _json, _server

HANDLERS = """
import base64
import json
import os


def on_mail(event, ctx):
    mail = event.data
    ses = mail["Records"][0]["ses"]["mail"]["commonHeaders"]
    att = mail["attachments"][0]
    with open(os.environ["OUT"], "a") as fh:
        fh.write(json.dumps([event.type, mail["from"], mail["to"], ses["subject"], att["filename"],
                             base64.b64decode(att["content"]).decode()]) + "\\n")
    return {"ok": True}


def broken(event, ctx):
    raise RuntimeError("cannot store the mail")
"""

CONFIG = """
service: mail
provider:
  name: onprem
  runtime: python3.12
  options: {{host: 127.0.0.1, port: 8098, data_dir: {data}}}
  environment: {{OUT: "{out}"}}
resources:
  inbound: {{type: smtp, external: true, connection: {{host: 127.0.0.1, port: 2525, domains: example.com}}}}
  backup: {{type: smtp, external: true}}
  quiet: {{type: smtp, external: true}}
functions:
  on-mail:
    handler: app.handlers.on_mail
    events: [{{smtp: {{resource: inbound}}}}]
  broken:
    handler: app.handlers.broken
    events: [{{smtp: backup}}]
"""


@pytest.fixture
def host(make_project, tmp_path: Path):
    out = tmp_path / "out.txt"
    project = make_project(CONFIG.format(data=(tmp_path / "data").as_posix(), out=out.as_posix()),
                           files={"app/handlers.py": HANDLERS})
    Deployer(project, echo=lambda _m: None).package(skip_deps=True)
    root = project.work_dir / "onprem_app"
    activate_layout(root)
    h = Host(root)
    h.open()
    httpd, base = _server(h)
    try:
        yield h, base, out
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_mail_runs_the_attached_functions(host):
    h, base, out = host
    mail = make_mail({"from": "jane@client.org", "to": ["support@example.com"], "subject": "Order 7",
                      "attachments": [{"filename": "a.txt", "content": "Total: 42"}]}, "inbound")
    status, body = _json("POST", base + "/__pskit/smtp/inbound", mail)
    assert status == 200 and body == {"delivered": {"on-mail": {"ok": True}}}
    assert json.loads(out.read_text().strip()) == ["smtp", "jane@client.org", ["support@example.com"], "Order 7",
                                                    "a.txt", "Total: 42"]
    logs = h.logs.query(function="on-mail")["entries"]
    assert any("jane@client.org" in item["message"] and "on-mail" in item["message"] for item in logs)


def test_failures_and_unattached_servers_make_the_sender_retry(host):
    h, base, _out = host
    _expect_http_error(500, "POST", base + "/__pskit/smtp/backup", make_mail({}, "backup"))
    _expect_http_error(404, "POST", base + "/__pskit/smtp/quiet", make_mail({}, "quiet"))
    _expect_http_error(400, "POST", base + "/__pskit/smtp/inbound", [1, 2])
    h.spec["admin_token"] = "secret"
    _expect_http_error(401, "POST", base + "/__pskit/smtp/inbound", make_mail({}))
    status, _body = _json("POST", base + "/__pskit/smtp/inbound", make_mail({"attachments": [{"filename": "x"}]}),
                          token="secret")
    assert status == 200
