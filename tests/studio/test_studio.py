"""pskit studio: security, meta catalog, project editing, files, handlers, discovery, jobs, VS Code."""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
import types
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from py_serverless_kit.studio import project as proj
from py_serverless_kit.studio.discover import discover
from py_serverless_kit.studio.jobs import JobManager, build_argv
from py_serverless_kit.studio.project import StudioError
from py_serverless_kit.studio.server import make_server, studio_url
from py_serverless_kit.studio.vscode import VSCode

TOKEN = "test-token-123"

CONFIG = """
service: studio-demo
provider:
  name: aws
  region: us-east-1
  environment:
    API_KEY: ${env:STUDIO_TEST_KEY, fallback}
functions:
  hello:
    handler: app.handlers.hello
    events:
      - http: GET /hello
  step:
    handler: app.handlers.hello
workflows:
  flow:
    engine: embedded
    start_at: Go
    states:
      Go: {type: task, function: step, end: true}
"""


@pytest.fixture
def studio(make_project, tmp_path):
    make_project(CONFIG)
    httpd = make_server(tmp_path, "127.0.0.1", 0, token=TOKEN)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    yield base, tmp_path, httpd
    httpd.shutdown()
    httpd.server_close()


def call(base, method, path, body=None, token=TOKEN, headers=None, raw=None):
    data = raw if raw is not None else (None if body is None else json.dumps(body).encode())
    req = Request(base + path, data=data, method=method)
    if data is not None and raw is None:
        req.add_header("content-type", "application/json")
    if token:
        req.add_header("x-studio-token", token)
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    try:
        with urlopen(req, timeout=30) as resp:
            text = resp.read().decode()
            return resp.status, (json.loads(text) if "json" in resp.headers.get("content-type", "") else text)
    except HTTPError as exc:
        payload = exc.read().decode()
        return exc.code, json.loads(payload) if payload.startswith("{") else payload


# --------------------------------------------------------------------------- security


def test_security_gates(studio):
    base, _root, httpd = studio
    assert studio_url(httpd).endswith(f"/#token={TOKEN}")
    assert call(base, "GET", "/api/health", token=None)[0] == 200
    status, body = call(base, "GET", "/api/meta", token=None)
    assert status == 401 and body["code"] == "token"
    assert call(base, "GET", "/api/meta", token="wrong")[0] == 401
    assert call(base, "GET", "/api/meta", headers={"Host": "evil.example"})[0] == 421
    status, _ = call(base, "POST", "/api/project/validate", {"raw": {}}, headers={"Origin": "http://evil.example"})
    assert status == 403
    status, body = call(base, "POST", "/api/project/parse", raw=b'{"text": "a: 1"}',
                        headers={"content-type": "text/plain"})
    assert status == 415
    big = json.dumps({"text": "x" * (3 * 1024 * 1024)}).encode()
    status, _ = call(base, "POST", "/api/project/parse", raw=big, headers={"content-type": "application/json"})
    assert status == 413
    status, page = call(base, "GET", "/", token=None)
    assert status == 200 and "<html" in page.lower()
    with urlopen(base + "/", timeout=5) as resp:
        csp = resp.headers["content-security-policy"]
    assert "frame-src http://127.0.0.1:*" in csp and "frame-ancestors 'none'" in csp
    assert call(base, "GET", "/api/nope")[0] == 404


# --------------------------------------------------------------------------- meta


def test_meta_catalog(studio):
    from py_serverless_kit.providers.onprem import DRIVERS

    base, _root, _httpd = studio
    status, meta = call(base, "GET", "/api/meta")
    assert status == 200
    names = {p["name"] for p in meta["providers"]}
    assert names == {"aws", "azure", "gcp", "alibaba", "oracle", "ibm", "digitalocean", "tencent", "huawei",
                     "cloudflare", "onprem"}
    aws = next(p for p in meta["providers"] if p["name"] == "aws")
    assert "queue" in aws["capabilities"] and aws["default_region"] == "us-east-1" and aws["runtimes"]
    gcp = next(p for p in meta["providers"] if p["name"] == "gcp")
    assert any(f["key"] == "project" and f["required"] for f in gcp["options"])
    assert set(meta["events"]) == {"http", "schedule", "queue", "storage", "topic", "smtp"}
    method = next(f for f in meta["events"]["http"] if f["key"] == "method")
    assert method["type"] == "enum" and "POST" in method["options"]
    batch = next(f for f in meta["events"]["queue"] if f["key"] == "batch_size")
    assert batch["type"] == "int" and batch["min"] == 1 and batch["default"] == 10
    assert "choice" in meta["workflow"]["state_types"] and "equals" in meta["workflow"]["choice_operators"]
    drivers = meta["onprem"]["drivers"]
    queue = {d["name"] for d in drivers["queue"]}
    storage = {d["name"] for d in drivers["storage"]}
    assert {"sqs", "azure_queue", "pubsub", "mns", "cloudflare_queue", "custom", "redis"} <= queue
    assert {"aws", "oss", "cos", "obs", "oci", "ibm_cos", "spaces", "r2", "minio", "azure_blob", "gcs"} <= storage
    # the catalog and the validator name exactly the same drivers
    for kind, allowed in DRIVERS.items():
        assert {d["name"] for d in drivers[kind]} == set(allowed), kind
    secret = next(f for f in next(d for d in drivers["queue"] if d["name"] == "sqs")["fields"]
                  if f["key"] == "secret_key")
    assert secret["type"] == "secret" and secret["env_ok"] is True
    assert set(meta["onprem"]["deploy_fields"]) == {"local", "ssh", "docker"}
    assert "__FUNC__" in meta["handler_templates"]["queue"] and "BatchResult" in meta["handler_templates"]["queue"]


# --------------------------------------------------------------------------- project


def test_project_get_validate_save(studio):
    base, root, _httpd = studio
    status, current = call(base, "GET", "/api/project")
    assert status == 200 and current["exists"] and current["path"] == "pskit.yml"
    assert current["raw"]["provider"]["environment"]["API_KEY"] == "${env:STUDIO_TEST_KEY, fallback}"
    assert current["issues"] == [] or all(i["level"] == "warning" for i in current["issues"])

    draft = json.loads(json.dumps(current["raw"]))
    draft["functions"]["hello"]["events"] = [{"http": {"method": "FETCH", "path": "/hello"}}]
    status, result = call(base, "POST", "/api/project/validate", {"raw": draft})
    assert status == 200 and result["ok"] is False
    assert any(i["where"].startswith("functions.hello.events[0]") for i in result["issues"]), result["issues"]
    assert not list(root.glob(".pskit-studio-draft-*"))

    good = json.loads(json.dumps(current["raw"]))
    status, result = call(base, "POST", "/api/project/validate", {"raw": good, "provider": "gcp"})
    assert any("project" in i["message"] for i in result["issues"])  # gcp needs options.project
    status, result = call(base, "POST", "/api/project/validate", {"raw": good})
    assert result["ok"] is True
    names = {f["name"]: f for f in result["functions"]}
    assert names["flow-orchestrator"]["generated"] is True and result["engines"] == {"flow": "embedded"}

    good["functions"]["bye"] = {"handler": "app.handlers.hello"}
    status, saved = call(base, "PUT", "/api/project", {"raw": good, "mtime": current["mtime"]})
    assert status == 200 and "bye" in saved["raw"]["functions"]
    text = (root / "pskit.yml").read_text("utf-8")
    assert text.startswith("# Edited with pskit studio") and "${env:STUDIO_TEST_KEY, fallback}" in text
    assert len(list((root / ".pskit" / "studio" / "backups").glob("pskit.*.yml"))) == 1

    status, body = call(base, "PUT", "/api/project", {"raw": good, "mtime": current["mtime"]})
    assert status == 409 and body["code"] == "conflict"
    assert call(base, "PUT", "/api/project", {"raw": good, "mtime": current["mtime"], "force": True})[0] == 200
    assert call(base, "PUT", "/api/project", {"raw": ["not", "a", "mapping"]})[0] == 400


def test_backups_are_capped(tmp_path):
    (tmp_path / "pskit.yml").write_text("service: aa\nprovider: {name: aws}\n", "utf-8")
    for _ in range(proj.KEEP_BACKUPS + 3):
        proj.save_project(tmp_path, {"service": "aa", "provider": {"name": "aws"}})
    assert len(list((tmp_path / proj.BACKUP_DIR).glob("pskit.*.yml"))) <= proj.KEEP_BACKUPS


def test_parse_and_notices(studio):
    base, root, _httpd = studio
    status, out = call(base, "POST", "/api/project/parse", {"text": "service: [unclosed\n"})
    assert out["raw"] is None and out["issues"][0]["where"].startswith("line")
    status, out = call(base, "POST", "/api/project/parse", {"text": "- a\n- b\n"})
    assert out["raw"] is None and "mapping" in out["issues"][0]["message"]
    status, out = call(base, "POST", "/api/project/parse", {"text": "service: x\n"})
    assert out["raw"] == {"service": "x"}
    (root / "pskit.yml").write_text("# my notes\n" + CONFIG, "utf-8")
    status, current = call(base, "GET", "/api/project")
    assert any("Comments" in n for n in current["notices"])


def test_init_in_empty_dir(tmp_path):
    out = proj.init_project(tmp_path, "fresh-app", "onprem", "workflow")
    assert out["exists"] and (tmp_path / "app" / "handlers.py").is_file() and "pskit.yml" in out["created"]
    with pytest.raises(StudioError) as exc:
        proj.init_project(tmp_path, "fresh-app", "onprem", "http")
    assert exc.value.status == 409
    with pytest.raises(StudioError):
        proj.init_project(tmp_path / "x", "Bad_Name", "aws", "http")
    with pytest.raises(StudioError):
        proj.init_project(tmp_path / "y", "good", "nope", "http")
    empty = proj.get_project(tmp_path / "missing")
    assert empty["exists"] is False and empty["raw"] is None


# --------------------------------------------------------------------------- files


def test_files_api(studio):
    base, root, _httpd = studio
    (root / ".pskit").mkdir(exist_ok=True)
    (root / ".pskit" / "secret.txt").write_text("x", "utf-8")
    (root / "blob.bin").write_bytes(b"\x00\x01\x02")
    status, tree = call(base, "GET", "/api/files/tree")
    paths = {e["path"] for e in tree["entries"]}
    assert "app/handlers.py" in paths and "app" in paths and not any(p.startswith(".pskit") for p in paths)

    status, f = call(base, "GET", "/api/files?path=app/handlers.py")
    assert status == 200 and f["language"] == "python" and "def hello" in f["text"]
    assert call(base, "GET", "/api/files?path=../outside.txt")[0] == 400
    assert call(base, "GET", "/api/files?path=.pskit/secret.txt")[0] == 403
    assert call(base, "GET", "/api/files?path=/etc/passwd")[0] == 400
    assert call(base, "GET", "/api/files?path=C:/Windows/win.ini")[0] == 400
    assert call(base, "GET", "/api/files?path=blob.bin")[0] == 415
    assert call(base, "GET", "/api/files?path=nope.py")[0] == 404

    status, wrote = call(base, "PUT", "/api/files", {"path": "app/new_mod.py", "text": "X = 1\r\n"})
    assert status == 200 and (root / "app" / "new_mod.py").read_bytes() == b"X = 1\n"
    status, body = call(base, "PUT", "/api/files", {"path": "app/new_mod.py", "text": "X = 2\n", "mtime": 1.0})
    assert status == 409
    assert call(base, "PUT", "/api/files", {"path": "../x.py", "text": ""})[0] == 400
    assert call(base, "PUT", "/api/files", {"path": ".git/config", "text": ""})[0] == 403


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need privileges on Windows")
def test_files_symlink_escape(tmp_path):
    from py_serverless_kit.studio import files

    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "s.txt").write_text("secret", "utf-8")
    proj_dir = tmp_path / "proj"
    proj_dir.mkdir()
    (proj_dir / "link").symlink_to(outside)
    with pytest.raises(StudioError) as exc:
        files.read_file(proj_dir, "link/s.txt")
    assert exc.value.status == 403


# --------------------------------------------------------------------------- handlers


def test_handler_ensure(studio):
    base, root, _httpd = studio
    status, out = call(base, "POST", "/api/handlers/ensure", {"handler": "app.workers.consume", "events": ["queue"]})
    assert status == 200 and out["created"] and out["path"] == "app/workers.py"
    text = (root / "app" / "workers.py").read_text("utf-8")
    assert "from py_serverless_kit import BatchResult, Context, Event" in text and "def consume(" in text
    compile(text, "workers.py", "exec")
    assert text.splitlines()[out["line"] - 1].startswith("def consume(")
    status, again = call(base, "POST", "/api/handlers/ensure", {"handler": "app.workers.consume"})
    assert again["created"] is False and again["line"] == out["line"]

    status, more = call(base, "POST", "/api/handlers/ensure", {"handler": "app.workers:tick", "events": ["schedule"]})
    text = (root / "app" / "workers.py").read_text("utf-8")
    assert more["created"] and text.count("from py_serverless_kit import") == 1 and "def tick(" in text
    compile(text, "workers.py", "exec")

    status, nested = call(base, "POST", "/api/handlers/ensure", {"handler": "svc.billing.api.charge"})
    assert nested["created"] and (root / "svc" / "__init__.py").is_file()
    assert (root / "svc" / "billing" / "__init__.py").is_file()
    status, existing = call(base, "POST", "/api/handlers/ensure", {"handler": "app.handlers.hello"})
    assert existing["created"] is False
    assert call(base, "POST", "/api/handlers/ensure", {"handler": "not a handler"})[0] == 400


# --------------------------------------------------------------------------- discover


def test_discover_with_fake_boto3(studio, monkeypatch):
    base, root, _httpd = studio

    class FakeClient:
        def __init__(self, service):
            self.service = service

        def list_queues(self, **kw):
            if "NextToken" in kw:
                return {"QueueUrls": ["https://sqs.us-east-1.amazonaws.com/1/second"]}
            return {"QueueUrls": ["https://sqs.us-east-1.amazonaws.com/1/first"], "NextToken": "t"}

        def list_buckets(self):
            return {"Buckets": [{"Name": "media"}]}

        def list_topics(self, **kw):
            return {"Topics": [{"TopicArn": "arn:aws:sns:us-east-1:1:orders"}]}

        def list_state_machines(self, **kw):
            return {"stateMachines": [{"name": "flow", "stateMachineArn": "arn:sm", "type": "STANDARD"}]}

    class FakeSession:
        def __init__(self, region_name=None):
            self.region_name = region_name or "us-east-1"

        def client(self, service):
            return FakeClient(service)

    fake = types.ModuleType("boto3")
    fake.session = types.SimpleNamespace(Session=FakeSession)  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "boto3", fake)
    status, out = call(base, "GET", "/api/discover?provider=aws&kind=queue&region=us-east-1")
    assert out["supported"] and [i["name"] for i in out["items"]] == ["first", "second"]
    assert call(base, "GET", "/api/discover?kind=storage")[1]["items"][0]["arn"] == "arn:aws:s3:::media"
    assert call(base, "GET", "/api/discover?kind=topic")[1]["items"][0]["name"] == "orders"
    assert call(base, "GET", "/api/discover?kind=workflow")[1]["items"][0]["detail"] == "STANDARD"

    class Broken(FakeClient):
        def list_buckets(self):
            raise RuntimeError("AccessDenied")

    monkeypatch.setattr(FakeSession, "client", lambda self, service: Broken(service))
    out = call(base, "GET", "/api/discover?kind=storage")[1]
    assert out["supported"] and "AccessDenied" in out["error"] and out["items"] == []


def test_discover_unsupported(tmp_path, monkeypatch):
    out = discover(tmp_path, "tencent", "queue")
    assert out["supported"] is False and "type the name" in out["reason"]
    assert discover(tmp_path, "aws", "nope")["supported"] is False
    monkeypatch.setitem(sys.modules, "boto3", None)
    assert "boto3" in discover(tmp_path, "aws", "queue")["reason"]
    monkeypatch.delenv("AZURE_STORAGE_CONNECTION_STRING", raising=False)
    assert discover(tmp_path, "azure", "queue")["supported"] is False
    data = tmp_path / ".pskit" / "onprem-data" / "svc-dev" / "queues"
    (data / "jobs").mkdir(parents=True)
    out = discover(tmp_path, "onprem", "queue", raw={"service": "svc", "provider": {"name": "onprem"}})
    assert out["supported"] and [i["name"] for i in out["items"]] == ["jobs"]


# --------------------------------------------------------------------------- jobs


def test_build_argv():
    assert build_argv("validate", "gcp", "prod") == ["validate", "--provider", "gcp", "--stage", "prod"]
    assert build_argv("remove") == ["remove", "--yes"]
    assert build_argv("deploy", args={"skip_deps": True}) == ["deploy", "--skip-deps"]
    assert build_argv("deploy") == ["deploy"]
    assert build_argv("invoke", args={"function": "hello", "type": "http", "data": {"a": 1}}) == [
        "invoke", "-f", "hello", "-t", "http", "-d", '{"a": 1}'
    ]
    assert build_argv("workflow-run", args={"workflow": "flow", "data": {}}) == ["workflow", "run", "flow", "-i", "{}"]
    for bad in (("rm -rf", None), ("deploy", "a b"), ("invoke", None)):
        with pytest.raises(StudioError):
            build_argv(bad[0], bad[1]) if bad[0] != "invoke" else build_argv("invoke", args={"function": "x;y"})
    with pytest.raises(StudioError):
        build_argv("invoke", args={"function": "hello", "data": "@/etc/passwd"})


def test_validate_job_end_to_end(studio):
    base, _root, _httpd = studio
    status, started = call(base, "POST", "/api/jobs", {"command": "validate"})
    assert status == 202
    job_id = started["job_id"]
    deadline = time.time() + 60
    snap = {}
    while time.time() < deadline:
        _s, snap = call(base, "GET", f"/api/jobs/{job_id}?since=0")
        if snap["status"] != "running":
            break
        time.sleep(0.2)
    assert snap["status"] == "succeeded", snap
    text = "\n".join(line["text"] for line in snap["lines"])
    assert "valid" in text.lower()
    _s, later = call(base, "GET", f"/api/jobs/{job_id}?since={snap['next']}")
    assert later["lines"] == []
    assert any(j["job_id"] == job_id for j in call(base, "GET", "/api/jobs")[1]["jobs"])
    assert call(base, "GET", "/api/jobs/unknown")[0] == 404
    assert call(base, "POST", "/api/jobs", {"command": "explode"})[0] == 400


def test_job_cancel_and_exclusive(tmp_path):
    jobs = JobManager(tmp_path)
    job = jobs.run_process("deploy", [sys.executable, "-c", "import time; print('start', flush=True); time.sleep(60)"],
                           exclusive=True)
    deadline = time.time() + 10
    while not any(line["text"] == "start" for line in job.snapshot()["lines"]) and time.time() < deadline:
        time.sleep(0.05)
    with pytest.raises(StudioError) as exc:
        jobs.run_process("remove", [sys.executable, "-c", "pass"], exclusive=True)
    assert exc.value.status == 409
    jobs.cancel(job.id)
    deadline = time.time() + 15
    while job.status == "running" and time.time() < deadline:
        time.sleep(0.05)
    assert job.status == "cancelled"


# --------------------------------------------------------------------------- vscode


class FakeDocker:
    def __init__(self, daemon=True, image=True, container=None):
        self.daemon, self.image, self.container = daemon, image, container
        self.calls = []

    def __call__(self, cmd, timeout):
        self.calls.append(cmd)
        args = cmd[1:]

        def done(code=0, out="", err=""):
            return subprocess.CompletedProcess(cmd, code, out, err)

        if args[0] == "version":
            return done(0, "27.1.1") if self.daemon else done(1, "", "Cannot connect to the Docker daemon")
        if args[:2] == ["image", "inspect"]:
            return done(0 if self.image else 1)
        if args[:2] == ["container", "inspect"]:
            if self.container is None:
                return done(1, "", "No such container")
            return done(0, json.dumps([self.container]))
        if args[0] == "run":
            self.container = {"State": {"Running": True},
                              "NetworkSettings": {"Ports": {"8080/tcp": [{"HostPort": args[args.index("-p") + 1]
                                                                          .split(":")[1]}]}}}
            return done(0, "abc123")
        if args[0] == "rm":
            self.container = None
            return done(0)
        return done(0)


class FakeJob:
    def __init__(self):
        self.lines = []

    def emit(self, text, stream="stdout"):
        self.lines.append((stream, text))


def test_vscode_status_and_start(tmp_path, monkeypatch):
    from py_serverless_kit.studio import vscode as vs

    docker = FakeDocker(daemon=False)
    code = VSCode(tmp_path, runner=docker)
    assert code.status()["docker"]["available"] is False
    job = FakeJob()
    assert code.start(job) == 1 and "daemon" in job.lines[-1][1]

    def missing(cmd, timeout):
        raise FileNotFoundError("docker")

    assert "not installed" in VSCode(tmp_path, runner=missing).docker_info()["error"]

    docker = FakeDocker(image=False)
    code = VSCode(tmp_path, runner=docker, image="codercom/code-server:4.96.4")
    pulled = []
    monkeypatch.setattr(code, "_stream", lambda cmd, job: pulled.append(cmd) or (setattr(docker, "image", True) or 0))
    monkeypatch.setattr(vs, "_wait_http", lambda url, timeout: True)
    job = FakeJob()
    assert code.start(job) == 0
    assert pulled and pulled[0][1:] == ["pull", "codercom/code-server:4.96.4"]
    run = next(c for c in docker.calls if c[1] == "run")
    assert "--auth" in run and "none" in run and run[run.index("-p") + 1].startswith("127.0.0.1:")
    assert any(a.endswith(":/home/coder/project") for a in run)
    status = code.status()
    assert status["running"] and status["url"].startswith("http://127.0.0.1:") and status["image_present"]

    job = FakeJob()
    assert code.start(job) == 0 and "already running" in job.lines[-1][1]
    assert code.stop() == {"stopped": True} and code.status()["running"] is False


def test_vscode_host_root_mapping(tmp_path, monkeypatch):
    from py_serverless_kit.studio.vscode import host_path

    monkeypatch.setenv("PSKIT_STUDIO_HOST_ROOT", "/srv/projects/demo")
    assert host_path(tmp_path) == "/srv/projects/demo"
    monkeypatch.delenv("PSKIT_STUDIO_HOST_ROOT")
    assert "\\" not in host_path(tmp_path)


def test_vscode_api_reports_docker(studio, monkeypatch):
    base, _root, httpd = studio
    httpd.studio.vscode.runner = FakeDocker(daemon=False)
    status, out = call(base, "GET", "/api/vscode")
    assert status == 200 and out["docker"]["available"] is False and out["image"]
    assert call(base, "POST", "/api/vscode/start", {"image": "--evil"})[0] == 400
    status, started = call(base, "POST", "/api/vscode/start", {})
    assert status == 202 and started["job_id"]


def test_cli_studio_help():
    from click.testing import CliRunner

    from py_serverless_kit.cli.main import cli

    result = CliRunner().invoke(cli, ["studio", "--help"])
    assert result.exit_code == 0 and "--vscode-image" in result.output


def test_placeholder_page_is_packaged():
    assert (Path(proj.__file__).with_name("studio.html")).is_file()


# --------------------------------------------------------------------------- on-prem services + guides
def test_resource_guides_are_served(studio):
    base, _root, _httpd = studio
    status, index = call(base, "GET", "/api/resource-guides")
    assert status == 200 and index["available"]
    assert index["clouds"][0]["id"] == "index" and "compatibility" in {p["id"] for p in index["clouds"][0]["pages"]}
    assert index["clouds"][1]["id"] == "onprem"
    onprem = index["clouds"][1]
    assert {"readme", "queue", "services"} <= {p["id"] for p in onprem["pages"]}
    status, page = call(base, "GET", "/api/resource-guides/onprem/queue")
    assert status == 200 and page["markdown"].startswith("# ")
    assert call(base, "GET", "/api/resource-guides/index/readme")[0] == 200
    assert "Lambda Invoke API" in call(base, "GET", "/api/resource-guides/index/compatibility")[1]["markdown"]
    assert call(base, "GET", "/api/resource-guides/onprem/..%2Fsecret")[0] == 400
    assert call(base, "GET", "/api/resource-guides/onprem/nope")[0] == 404


def test_onprem_services_api(studio):
    from py_serverless_kit.core import onprem_services as svc

    base, root, _httpd = studio
    status, state = call(base, "GET", "/api/onprem-services")
    assert status == 200 and state["services"] == [] and state["default_target"] == {"method": "local"}
    assert any(item["id"] == "kafka" for item in state["catalog"])
    status, out = call(base, "POST", "/api/onprem-services", {"key": "9bad", "service": "redis"})
    assert status == 400 and "key must" in out["error"]
    assert call(base, "GET", "/api/onprem-services/missing")[0] == 400

    # A service recorded earlier (as `create` would) can be applied to and removed from a draft.
    entry = {
        "key": "jobs",
        "service": "redis",
        "kind": "service",
        "role": "queue",
        "target": {"method": "local"},
        "env": {"PSKIT_JOBS_URL": "redis://:pw@127.0.0.1:6379/0"},
        "env_file": ".env.onprem",
        "resource": {"type": "queue", "external": True, "options": {"driver": "redis", "url_env": "PSKIT_JOBS_URL"}},
    }
    svc.save_state(root, {"services": {"jobs": entry}})
    draft = proj.get_project(root)["raw"]
    status, out = call(base, "POST", "/api/onprem-services/apply", {"raw": draft, "key": "jobs", "attach": ["step"]})
    assert status == 200
    onprem = out["raw"]["providers"]["onprem"]  # the main provider is aws: everything goes under providers.onprem
    assert onprem["resources"]["jobs"]["options"]["driver"] == "redis"
    assert {"queue": {"resource": "jobs"}} in onprem["functions"]["step"]["events"]
    status, back = call(base, "POST", "/api/onprem-services/unapply", {"raw": out["raw"], "key": "jobs"})
    assert status == 200 and "jobs" not in json.dumps(back["raw"]["providers"]["onprem"].get("resources", {}))
    status, listed = call(base, "GET", "/api/onprem-services")
    assert listed["services"][0]["env"]["PSKIT_JOBS_URL"] == "***"


def test_onprem_servers_console_and_terminal_api(studio, monkeypatch):
    from py_serverless_kit.core import onprem_console as con
    from py_serverless_kit.core import onprem_services as svc
    from py_serverless_kit.core import onprem_terminal as term

    base, root, _httpd = studio
    status, out = call(base, "POST", "/api/onprem-servers",
                       {"name": "edge1", "target": {"host": "10.0.0.5", "user": "ubuntu", "auth": "agent"}})
    assert status == 200 and out["name"] == "edge1"
    assert call(base, "POST", "/api/onprem-servers", {"name": "9x", "target": {"host": "h"}})[0] == 400
    status, listed = call(base, "GET", "/api/onprem-servers")
    assert [s["name"] for s in listed["servers"]] == ["edge1"]

    monkeypatch.setattr(con, "_run", lambda argv, timeout: (0, "Linux edge1"))
    status, shell = call(base, "POST", "/api/onprem-servers/edge1/shell", {"line": "uname -a"})
    assert status == 200 and shell["output"] == "Linux edge1"

    svc.save_state(root, {"services": {"cache": {"key": "cache", "service": "redis", "kind": "service",
                                                 "container": "pskit-x-cache", "target": {"method": "local"}, "env": {}}}})
    status, info = call(base, "GET", "/api/onprem-services/cache/console")
    assert status == 200 and info["label"] == "redis-cli"
    status, ran = call(base, "POST", "/api/onprem-services/cache/console", {"line": "PING"})
    assert status == 200 and ran["exit_code"] == 0
    assert call(base, "POST", "/api/onprem-services/cache/console", {"line": ""})[0] == 400

    monkeypatch.setattr(term, "start_terminal", lambda root, emit, **kw: {"name": "pskit-term-7681", "port": 7681,
                                                                          "url": "http://127.0.0.1:7681/t/", "title": "edge1"})
    monkeypatch.setattr(term, "list_terminals", lambda **kw: [{"name": "pskit-term-7681", "port": 7681, "title": "edge1"}])
    status, started = call(base, "POST", "/api/onprem-terminals", {"server": "edge1"})
    assert status == 200 and started["url"].startswith("http://127.0.0.1:7681/")
    assert call(base, "GET", "/api/onprem-terminals")[1]["terminals"][0]["url"] == "http://127.0.0.1:7681/t/"
    assert call(base, "POST", "/api/onprem-terminals/nope/stop", {})[0] == 400
    assert call(base, "POST", "/api/onprem-servers/edge1/remove", {})[0] == 200


def test_settings_bundle_api(studio):
    from py_serverless_kit.core import onprem_servers as srv

    base, root, _ = studio
    srv.save_server(root, "edge1", {"host": "10.0.0.5", "user": "root", "auth": "password", "password": "pw-1"})
    assert call(base, "POST", "/api/settings-bundle/export", {"passphrase": "short"})[0] == 400
    status, exported = call(base, "POST", "/api/settings-bundle/export", {"passphrase": "a long passphrase"})
    assert status == 200 and exported["filename"].endswith(".pskit-settings")
    assert "pw-1" not in exported["content"] and exported["summary"]["entries"]["onprem-servers.servers"] == ["edge1"]

    srv.remove_server(root, "edge1")
    body = {"content": exported["content"], "passphrase": "a long passphrase"}
    status, plan = call(base, "POST", "/api/settings-bundle/preview", body)
    assert status == 200 and plan["stores"]["onprem-servers.servers"]["add"] == ["edge1"]
    assert call(base, "POST", "/api/settings-bundle/import", {**body, "passphrase": "wrong one!"})[0] == 400
    status, result = call(base, "POST", "/api/settings-bundle/import", body)
    assert status == 200 and ".pskit/onprem-servers.json" in result["written"]
    assert Path(srv.load_servers(root)["edge1"]["password_file"]).read_text("utf-8") == "pw-1"
