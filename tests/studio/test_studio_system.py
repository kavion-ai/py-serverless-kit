"""pskit studio: file picker, setup/credentials, deployed logs, job history, provider-aware meta."""

from __future__ import annotations

import json
import os
import sys
import time

import pytest

from py_serverless_kit.providers.registry import get_provider
from py_serverless_kit.studio import project as proj
from py_serverless_kit.studio import system
from py_serverless_kit.studio.jobs import JobManager
from py_serverless_kit.studio.meta import build_meta, trigger_support
from py_serverless_kit.studio.project import StudioError

from .test_studio import call, studio  # noqa: F401 - fixture


def test_browse_lists_folder_and_marks_keys(tmp_path):
    keys = tmp_path / "keys"
    keys.mkdir()
    for name in ("server.pem", "id_ed25519", "id_ed25519.pub"):
        (keys / name).write_text("x")
    (keys / "sub").mkdir()
    listing = system.browse(str(keys))
    names = {e["name"]: e for e in listing["entries"]}
    assert listing["entries"][0]["type"] == "dir"  # folders first
    assert names["server.pem"]["key"] and names["id_ed25519"]["key"]
    assert not names["id_ed25519.pub"]["key"]
    assert listing["parent"] == str(tmp_path.resolve())
    # A file path lists its folder.
    assert system.browse(str(keys / "server.pem"))["path"] == str(keys.resolve())


def test_browse_rejects_relative_and_missing(tmp_path):
    with pytest.raises(StudioError) as exc:
        system.browse("relative/dir")
    assert exc.value.status == 400
    with pytest.raises(StudioError) as exc:
        system.browse(str(tmp_path / "nope"))
    assert exc.value.status == 404


def test_set_env_only_known_variables(monkeypatch):
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    assert system.set_env("CLOUDFLARE_ACCOUNT_ID", "abc")["set"] is True
    assert os.environ["CLOUDFLARE_ACCOUNT_ID"] == "abc"
    assert system.set_env("CLOUDFLARE_ACCOUNT_ID", "")["set"] is False
    assert "CLOUDFLARE_ACCOUNT_ID" not in os.environ
    for bad in ("PATH", "PYTHONPATH", "lower", "X"):
        with pytest.raises(StudioError):
            system.set_env(bad, "v")
    with pytest.raises(StudioError):
        system.set_env("AWS_PROFILE", "two\nlines")


def test_setup_status_never_returns_secret_values(monkeypatch, tmp_path):
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "super-secret")
    result = system.setup_status("cloudflare", {"provider": {"name": "cloudflare"}}, tmp_path)
    assert result["provider"] == "cloudflare"
    assert result["platform"] in ("windows", "macos", "linux")
    token = next(e for e in result["env"] if e["name"] == "CLOUDFLARE_API_TOKEN")
    assert token["set"] is True and token["value"] is None
    assert "super-secret" not in json.dumps(result)


def test_setup_and_fs_endpoints(studio):  # noqa: F811
    base, root, _ = studio
    status, body = call(base, "GET", "/api/setup?provider=aws")
    assert status == 200 and body["provider"] == "aws" and body["checks"]
    status, body = call(base, "GET", "/api/fs?path=" + str(root).replace("\\", "/"))
    assert status == 200 and any(e["name"] == "pskit.yml" for e in body["entries"])
    assert call(base, "POST", "/api/setup/env", {"name": "PATH", "value": "x"})[0] == 400
    assert call(base, "POST", "/api/setup/login", {"action": "rm-rf"})[0] == 400
    assert call(base, "POST", "/api/setup/ssh-test", {"deploy": {"host": "-oProxyCommand=evil"}})[0] == 400
    # Without the token nothing is reachable.
    assert call(base, "GET", "/api/fs", token=None)[0] == 401


def test_logs_endpoints_before_deploy(studio):  # noqa: F811
    base, _root, _ = studio
    status, body = call(base, "GET", "/api/logs?provider=aws&stage=dev")
    assert status == 200 and body["supported"] is False and "deployed" in body["reason"]
    status, body = call(base, "GET", "/api/logs/streams?provider=aws&stage=dev")
    assert status == 200 and body["supported"] is False
    assert call(base, "POST", "/api/logs/delete?provider=aws&stage=dev", {"all": True})[0] == 404
    assert call(base, "GET", "/api/logs?since=abc")[0] == 400


def test_logs_endpoints_use_the_deployment_record(studio, monkeypatch):  # noqa: F811
    base, root, _ = studio
    work = root / ".pskit" / "aws-dev"
    work.mkdir(parents=True)
    (work / "deployment.json").write_text(json.dumps({"provider": "aws", "stage": "dev", "functions": []}))
    calls = {}

    class Fake:
        console = "https://console.example"
        can_delete = True

        def query(self, **kw):
            calls["query"] = kw
            return {"supported": True, "mode": "time", "entries": [], "next": 5}

        def streams(self, function=None):
            return {"supported": True, "items": [{"id": "s1", "function": "hello", "name": "s1"}]}

        def delete(self, ids=None, function=None, all=False):  # noqa: A002 - matches LogBackend
            calls["delete"] = (ids, function, all)
            return {"deleted": len(ids or []) or 3}

    monkeypatch.setattr("py_serverless_kit.core.cloud_logs.log_backend", lambda record, root: Fake())
    status, body = call(base, "GET", "/api/logs?provider=aws&stage=dev&since=7&function=hello")
    assert status == 200 and body["next"] == 5 and body["console"] == "https://console.example"
    assert calls["query"]["since"] == 7 and calls["query"]["function"] == "hello"
    status, body = call(base, "GET", "/api/logs/streams?provider=aws&stage=dev")
    assert body["items"][0]["id"] == "s1" and body["can_delete"] is True
    status, body = call(base, "POST", "/api/logs/delete?provider=aws&stage=dev", {"ids": ["s1"]})
    assert status == 200 and calls["delete"] == (["s1"], None, False)
    assert call(base, "POST", "/api/logs/delete?provider=aws&stage=dev", {})[0] == 400
    assert call(base, "POST", "/api/logs/delete?provider=aws&stage=dev", {"ids": [1]})[0] == 400


def _wait(job, timeout=20.0):
    deadline = time.time() + timeout
    while job.status == "running" and time.time() < deadline:
        time.sleep(0.05)


def test_job_history_can_be_cleared(tmp_path):
    jobs = JobManager(tmp_path)
    done = jobs.run_process("validate", [sys.executable, "-c", "print(1)"])
    running = jobs.run_process("validate", [sys.executable, "-c", "import time; time.sleep(30)"])
    _wait(done)
    try:
        with pytest.raises(StudioError) as exc:
            jobs.clear(running.id)
        assert exc.value.status == 409
        assert jobs.clear() == {"removed": 1}
        assert [j["job_id"] for j in jobs.list()] == [running.id]
    finally:
        jobs.cancel(running.id)
    _wait(running)
    assert jobs.clear(running.id) == {"removed": 1}
    assert jobs.list() == []


def test_jobs_delete_endpoint(studio):  # noqa: F811
    base, _root, _ = studio
    status, body = call(base, "DELETE", "/api/jobs")
    assert status == 200 and body == {"removed": 0}
    assert call(base, "DELETE", "/api/jobs/nope")[0] == 404


def test_meta_has_regions_suggestions_and_trigger_support():
    meta = build_meta()
    aws = next(p for p in meta["providers"] if p["name"] == "aws")
    assert any(r["id"] == "us-east-1" for r in aws["regions"])
    assert any(r["key"] == "auth" and r["value"] == "key" and r["level"] == "error" for r in aws["trigger_support"]["http"])
    azure = next(p for p in meta["providers"] if p["name"] == "azure")
    assert any(r["key"] == "events" and r["level"] == "error" for r in azure["trigger_support"]["storage"])
    pem = next(f for f in meta["onprem"]["deploy_fields"]["ssh"] if f["key"] == "pem")
    assert pem["type"] == "file"
    memory = next(f for f in meta["provider_fields"] if f["key"] == "memory")
    assert 1024 in memory["suggestions"]


def test_trigger_support_only_lists_supported_events():
    cf = get_provider("cloudflare")
    assert set(trigger_support(cf, "cloudflare")) <= set(cf.capabilities)


DISABLED = """
service: demo
provider: {name: aws}
functions:
  hello: {handler: app.handlers.hello, events: [{http: GET /hello}]}
  later: {handler: app.handlers.hello, events: [{queue: jobs}]}
providers:
  cloudflare:
    functions:
      later: {enabled: false}
"""


def test_validate_reports_disabled(tmp_path, make_project):
    make_project(DISABLED)
    raw = proj.get_project(tmp_path)["raw"]
    aws = proj.validate(tmp_path, raw, "aws")
    assert aws["disabled"] == {"functions": [], "workflows": []}
    cf = proj.validate(tmp_path, raw, "cloudflare")
    assert cf["disabled"]["functions"] == ["later"]
    assert any(i["where"] == "functions.later" and "disabled" in i["message"] for i in cf["issues"])


def test_cloud_resources_endpoint_and_delete_job_args(studio):  # noqa: F811
    from py_serverless_kit.studio.jobs import build_argv

    base, _root, _ = studio
    status, body = call(base, "GET", "/api/cloud-resources?provider=aws&stage=dev")
    assert status == 200 and body["deployed"] == [] and body["kept"] == [] and "reason" in body
    argv = build_argv("resources-delete", "aws", "dev", {"addresses": ["aws_s3_bucket.b_uploads"]})
    assert argv == ["resources", "delete", "--provider", "aws", "--stage", "dev", "--yes", "aws_s3_bucket.b_uploads"]
    for bad in ([], ["-target=x"], ["a b"], "aws_s3_bucket.b"):
        with pytest.raises(StudioError):
            build_argv("resources-delete", "aws", "dev", {"addresses": bad})


def test_test_guide_events_and_trigger_job(studio):  # noqa: F811
    from py_serverless_kit.studio.jobs import build_argv

    base, root, _ = studio
    status, body = call(base, "GET", "/api/test-guide?provider=aws&stage=dev")
    assert status == 200 and not body["deployed"] and {f["name"] for f in body["functions"]} >= {"hello", "step"}
    events = {"hello": [{"name": "big", "event": 0, "payload": {"n": 1}, "path": "/hello?x=1"}]}
    assert call(base, "PUT", "/api/test-events", {"events": events}) == (200, events)
    assert call(base, "GET", "/api/test-events") == (200, events)
    assert (root / ".pskit" / "studio" / "test-events.json").is_file()
    assert call(base, "PUT", "/api/test-events", {"events": {"hello": "x"}})[0] == 400
    argv = build_argv("trigger", "aws", "dev", {"function": "hello", "event": 0, "data": {"a": 1}, "path": "/hello?x=1"})
    assert argv == ["trigger", "--provider", "aws", "--stage", "dev", "-f", "hello", "--json", "-e", "0",
                    "--path", "/hello?x=1", "-d", '{"a": 1}']
    assert "--direct" in build_argv("trigger", "aws", "dev", {"function": "hello", "event": -1})
    for bad in ({"function": "-x"}, {"function": "hello", "event": "0; rm"}, {"function": "hello", "path": "x y"}):
        with pytest.raises(StudioError):
            build_argv("trigger", "aws", "dev", bad)


def test_resource_test_guide_and_send_args(studio):  # noqa: F811
    from py_serverless_kit.studio.jobs import build_argv

    base, _root, _ = studio
    status, body = call(base, "GET", "/api/resource-test-guide?provider=aws&stage=dev")
    assert status == 200 and body["resources"] == []
    argv = build_argv("resource-send", "aws", "dev", {"resource": "jobs", "data": {"a": 1}})
    assert argv == ["resources", "send", "--provider", "aws", "--stage", "dev", "jobs", "--json", "-d", '{"a": 1}']
    with pytest.raises(StudioError):
        build_argv("resource-send", "aws", "dev", {"resource": "--all"})
