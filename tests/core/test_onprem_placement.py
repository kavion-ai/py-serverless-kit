"""Functions placed on several servers (provider.options.placement) and function sub-projects."""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from types import SimpleNamespace

import pytest

from py_serverless_kit.core import onprem_placement as pl
from py_serverless_kit.core import onprem_servers as srv
from py_serverless_kit.packaging import subprojects

FUNCTIONS = ["hello", "resize", "worker"]


# ------------------------------------------------------------------------------------------- parse
def test_parse_defaults_and_assignment():
    parsed = pl.parse({"groups": {"api": {"server": "app1"}, "gpu": {"server": "gpu1", "functions": ["resize"]}}},
                      FUNCTIONS, ["checkout"])
    assert parsed["default"] == "api"
    assert parsed["function_group"] == {"hello": "api", "resize": "gpu", "worker": "api",
                                        "checkout-orchestrator": "api"}
    assert parsed["groups"]["gpu"]["functions"] == ["resize"]
    assert parsed["groups"]["api"]["target"] == {"server": "app1"}


@pytest.mark.parametrize("raw, message", [
    ({"groups": {}}, "at least one group"),
    ({"groups": {"api": {}}, "default": "x"}, "not one of the groups"),
    ({"groups": {"Api": {}}}, "group name"),
    ({"groups": {"api": {}, "gpu": {"functions": ["resize"]}}}, "needs where it runs"),
    ({"groups": {"api": {"server": "a", "local": True}}}, "pick one of"),
    ({"groups": {"api": {}, "gpu": {"local": True, "functions": ["nope"]}}}, "no function 'nope'"),
    ({"groups": {"a": {"local": True, "functions": ["hello"]}, "b": {"local": True, "functions": ["hello"]}}},
     "in two groups"),
    ({"groups": {"api": {}, "w": {"local": True, "functions": ["checkout-orchestrator"]}}}, "workflows run on"),
    ({"groups": {"api": {"port": 0}}}, "port"),
    ({"groups": {"api": {"advertise": "10.0.0.5"}}}, "advertise"),
    ({"groups": {"api": {"color": 1}}}, "unknown keys"),
])
def test_parse_errors(raw, message):
    with pytest.raises(pl.PlacementError, match=message):
        pl.parse(raw, FUNCTIONS, ["checkout"])


def test_group_options_give_each_group_its_own_target():
    options = {"port": 8080, "advertise": "http://lb:8080", "deploy": {"server": "app1", "python": "bundle",
                                                                      "path": "/opt/x"}, "cluster": "prod",
               "placement": {"groups": {}}}
    gpu = pl.group_options(options, "gpu", {"target": {"server": "gpu1"}, "port": 8081}, "api")
    assert gpu["deploy"] == {"server": "gpu1", "python": "bundle"} and gpu["port"] == 8081
    assert "advertise" not in gpu and "cluster" not in gpu and "placement" not in gpu
    batch = pl.group_options(options, "batch", {"target": {"cluster": {"name": "prod", "replicas": 3}}}, "api")
    assert batch["cluster"] == {"name": "prod", "replicas": 3}
    assert pl.group_options(options, "here", {"target": {"local": True}}, "api")["deploy"]["method"] == "local"
    assert pl.group_options(options, "api", {"target": {}}, "api")["advertise"] == "http://lb:8080"
    assert pl.group_stage("dev", "gpu", "api") == "dev-gpu" and pl.group_stage("dev", "api", "api") == "dev"
    assert pl.app_dir("gpu-2", "api") == "onprem_app_gpu_2" and pl.resource_name("api", "api") == "host"


def test_resolve_uses_saved_servers_and_refuses_a_shared_port(tmp_path):
    for name, host in (("app1", "10.0.0.5"), ("gpu1", "10.0.0.7")):
        srv.save_server(tmp_path, name, {"host": host, "user": "root", "auth": "agent"})
    options = {"data_dir": "/data/pskit", "placement": {"default": "api", "groups": {
        "api": {"server": "app1"}, "gpu": {"server": "gpu1", "functions": ["resize"]}}}}
    pl.resolve(options, tmp_path, "dev")
    groups = options["placement"]["_groups"]
    assert groups["gpu"]["deploy"]["host"] == "10.0.0.7" and groups["gpu"]["data_dir"] == "/data/pskit/groups/gpu"
    assert options["deploy"]["host"] == "10.0.0.5" and options["data_dir"] == "/data/pskit"  # the default group's
    shared = {"placement": {"groups": {"api": {"server": "app1"}, "gpu": {"server": "app1", "functions": ["x"]}}}}
    with pytest.raises(pl.PlacementError, match="both run on app1 port 8080"):
        pl.resolve(shared, tmp_path, "dev")


def _event(kind, **body):
    return SimpleNamespace(type=kind, config=SimpleNamespace(**body))


def test_owners_keep_builtin_resources_with_their_consumers():
    def fn(*events):
        return SimpleNamespace(enabled=True, events=list(events))

    config = SimpleNamespace(
        functions={"worker": fn(_event("queue", name="jobs", resource=None, dead_letter="jobs-dlq")),
                   "thumbs": fn(_event("storage", bucket="uploads", resource=None)),
                   "a": fn(_event("topic", name="events")), "b": fn(_event("topic", name="events")),
                   "mail": fn(_event("smtp", resource="inbox", name="inbox"))},
        resources={"spare": SimpleNamespace(type="queue", native_name=lambda key: key)})
    groups = {"worker": "gpu", "thumbs": "api", "a": "api", "b": "gpu", "mail": "gpu"}
    found, errors = pl.owners(config, groups, "api", {})
    assert errors == []
    assert found == {"queue:jobs": "gpu", "queue:jobs-dlq": "gpu", "storage:uploads": "api",
                     "topic:events": ["api", "gpu"], "smtp:inbox": ["gpu"], "queue:spare": "api"}
    config.functions["worker2"] = fn(_event("queue", name="jobs", resource=None, dead_letter=None))
    _found, errors = pl.owners(config, {**groups, "worker2": "api"}, "api", {})
    assert errors and "keep its consumers in one group" in errors[0]
    # A queue with a shared driver (redis, sqs, ...) is reached from every group: not routed, no conflict.
    found, errors = pl.owners(config, {**groups, "worker2": "api"}, "api", {"queue:jobs": {"use": "redis"}})
    assert errors == [] and "queue:jobs" not in found


def test_peer_token_is_made_once(tmp_path):
    token = pl.peer_token(tmp_path, "dev")
    assert len(token) >= 32 and pl.peer_token(tmp_path, "dev") == token != pl.peer_token(tmp_path, "prod")


# ------------------------------------------------------------------------------------------- sub-projects
def test_function_dirs_and_requirements(tmp_path):
    for name, reqs in (("resize", "Pillow==10.0.0\nsix==1.16.0\n"), ("ocr", "six==1.16.0\n")):
        folder = tmp_path / "functions" / name
        folder.mkdir(parents=True)
        (folder / "handler.py").write_text("def main(e, c): pass\n")
        (folder / "requirements.txt").write_text(reqs)
    (tmp_path / "app.py").write_text("")
    fns = {n: SimpleNamespace(enabled=True, handler=h) for n, h in (
        ("resize", "functions.resize.handler.main"), ("ocr", "functions.ocr.handler.main"), ("root", "app.main"))}
    dirs = subprojects.function_dirs(tmp_path, fns)
    assert {n: d.relative_to(tmp_path.resolve()).as_posix() for n, d in dirs.items()} == {
        "resize": "functions/resize", "ocr": "functions/ocr"}
    # Sub-projects in name order (ocr, resize); a requirement two of them share is installed once.
    assert subprojects.function_requirements(tmp_path, fns) == ["six==1.16.0", "Pillow==10.0.0"]
    assert subprojects.function_requirements(tmp_path, fns, ["ocr"]) == ["six==1.16.0"]
    assert subprojects.excluded_dirs(tmp_path, fns, ["ocr", "root"]) == ["functions/resize"]
    assert subprojects.function_dir(tmp_path, "functions.missing.handler.main") is None


# ------------------------------------------------------------------------------------------- render
HANDLERS = {
    "functions/__init__.py": "",
    "functions/hello/__init__.py": "",
    "functions/hello/handler.py": """
        from py_serverless_kit import invoke


        def main(event, context):
            if event.http is not None:
                return {"hello": "api", "resize": invoke("resize", {"size": 2})}
            return {"step": "hello", "data": event.data}
    """,
    "functions/resize/__init__.py": "",
    "functions/resize/requirements.txt": "six==1.16.0\n",
    "functions/resize/handler.py": """
        def main(event, context):
            return {"resize": "gpu", "data": event.data if event.http is None else None}
    """,
    "functions/worker/__init__.py": "",
    "functions/worker/handler.py": """
        import json, os


        def main(event, context):
            with open(os.path.join(os.environ["PSKIT_ONPREM_ROOT"], "got.txt"), "a") as f:
                for r in event.records:
                    f.write(json.dumps(r.json()) + "\\n")
    """,
}


def _config(api_port: int, gpu_port: int) -> str:
    return f"""
        service: split
        provider:
          name: onprem
          runtime: python3.{sys.version_info.minor}
          options:
            port: {api_port}
            placement:
              default: api
              groups:
                api: {{local: true}}
                gpu: {{local: true, port: {gpu_port}, functions: [resize, worker]}}
        functions:
          hello:
            handler: functions.hello.handler.main
            events: [{{http: {{method: GET, path: /hello}}}}]
          resize:
            handler: functions.resize.handler.main
            events: [{{http: {{method: GET, path: /resize}}}}]
          worker:
            handler: functions.worker.handler.main
            events: [{{queue: {{name: jobs}}}}]
        workflows:
          pipeline:
            start_at: First
            states:
              First: {{type: task, function: hello, next: Second}}
              Second: {{type: task, function: resize, end: true}}
    """


GPU_JOB = """
          gpujob:
            start_at: Resize
            states:
              Resize: {type: task, function: resize, next: Hello}
              Hello: {type: task, function: hello, end: true}
"""


def test_render_one_host_per_group(make_project, render):
    project = make_project(_config(9180, 9181), files=HANDLERS)
    assert [str(i) for i in project.validate() if i.level == "error"] == []
    tf = render(project)
    hosts = tf["resource"]["terraform_data"]
    assert set(hosts) == {"host", "host_gpu"}  # the default group keeps the stage's resource
    assert hosts["host_gpu"]["provisioner"][0]["local-exec"]["working_dir"].endswith("/onprem_app_gpu")
    out = tf["output"]["pskit"]["value"]
    assert out["groups"]["gpu"]["functions"] == ["resize", "worker"]
    assert out["functions"]["resize"]["group"] == "gpu"
    work = project.work_dir
    api = json.loads((work / "onprem_app" / "pskit_host.json").read_text("utf-8"))
    gpu = json.loads((work / "onprem_app_gpu" / "pskit_host.json").read_text("utf-8"))
    assert sorted(api["functions"]) == ["hello", "pipeline-orchestrator"] and sorted(gpu["functions"]) == [
        "resize", "worker"]
    assert api["groups"] == gpu["groups"] == {"api": {"url": "http://127.0.0.1:9180"},
                                              "gpu": {"url": "http://127.0.0.1:9181"}}
    assert gpu["owners"]["queue:jobs"] == "gpu" and api["peer_token"] == gpu["peer_token"]
    assert api["host"] == "0.0.0.0" and gpu["deploy_stage"] == "dev-gpu"
    assert gpu["unit_name"] == "pskit-split-dev-gpu" and gpu["data_dir"].endswith("split-dev-gpu")
    # Each bundle has only its own functions' folders.
    assert not (work / "onprem_app" / "staging" / "functions" / "resize").exists()
    assert (work / "onprem_app_gpu" / "staging" / "functions" / "resize" / "handler.py").is_file()
    # functions/hello has no requirements.txt: it is shared code, not a sub-project, so every bundle keeps it.
    assert (work / "onprem_app_gpu" / "staging" / "functions" / "hello" / "handler.py").is_file()


def test_validation_reports_split_consumers(make_project):
    text = _config(9180, 9181).replace("gpu: {local: true, port: 9181, functions: [resize, worker]}",
                                       "gpu: {local: true, port: 9181, functions: [resize]}")
    text = text.replace("""          worker:
            handler: functions.worker.handler.main
            events: [{queue: {name: jobs}}]""", """          worker:
            handler: functions.worker.handler.main
            events: [{queue: {name: jobs}}]
          worker2:
            handler: functions.worker.handler.main
            events: [{queue: {name: jobs}}]""")
    text = text.replace("functions: [resize]}", "functions: [resize, worker2]}")
    project = make_project(text, files=HANDLERS)
    errors = [str(i) for i in project.validate() if i.level == "error"]
    assert any("keep its consumers in one group" in e for e in errors), errors


# ------------------------------------------------------------------------------------------- run both hosts
def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _http(url: str, data: bytes = None, timeout: float = 30):  # type: ignore[assignment]
    req = urllib.request.Request(url, data=data, method="POST" if data is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - test hosts
            return resp.status, json.loads(resp.read().decode() or "null")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()


def test_groups_call_each_other(make_project, render, tmp_path):
    api_port, gpu_port = _free_port(), _free_port()
    project = make_project(_config(api_port, gpu_port).replace(
        "            port:", f"            data_dir: {tmp_path.as_posix()}/d\n            port:", 1) + GPU_JOB,
        files=HANDLERS)
    render(project)
    procs = []
    try:
        for folder in ("onprem_app", "onprem_app_gpu"):
            root = project.work_dir / folder
            procs.append(subprocess.Popen([sys.executable, str(root / "onprem_ctl.py"), "foreground"], cwd=str(root),
                                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        deadline = time.time() + 30
        for port in (api_port, gpu_port):
            while True:
                try:
                    if _http(f"http://127.0.0.1:{port}/__pskit/health", timeout=2)[0] == 200:
                        break
                except OSError:
                    pass
                assert time.time() < deadline, f"host on {port} did not start"
                time.sleep(0.2)
        # Each server answers only the routes of its own functions (no placement.gateway): it says where to go.
        status, body = _http(f"http://127.0.0.1:{api_port}/resize")
        assert status == 404 and f"127.0.0.1:{gpu_port}/resize" in body and "runs on group gpu" in body
        assert _http(f"http://127.0.0.1:{gpu_port}/resize") == (200, {"resize": "gpu", "data": None})
        # resize is gpujob's first task: its call on the gpu host starts gpujob, which runs on the default group.
        while True:
            items = _http(f"http://127.0.0.1:{api_port}/__pskit/executions?workflow=gpujob")[1]["items"]
            if items and items[0]["status"] != "RUNNING":
                break
            assert time.time() < deadline + 15, items
            time.sleep(0.2)
        run = _http(f"http://127.0.0.1:{api_port}/__pskit/executions/{items[0]['execution_id']}")[1]
        assert run["status"] == "SUCCEEDED", run
        assert run["output"] == {"step": "hello", "data": {"resize": "gpu", "data": None}}
        # pskit trigger --direct / the studio's Test: the envelope is unwrapped, and the call reaches gpu.
        status, body = _http(f"http://127.0.0.1:{api_port}/__pskit/invoke/resize", b'{"__pskit": "invoke", "data": {"n": 1}}')
        assert (status, body) == (200, {"result": {"resize": "gpu", "data": {"n": 1}}})
        status, body = _http(f"http://127.0.0.1:{api_port}/hello")
        assert status == 200 and body["resize"] == {"resize": "gpu", "data": {"size": 2}}
        status, body = _http(f"http://127.0.0.1:{api_port}/workflows/pipeline?wait=true", b'{"x": 1}')
        assert status == 200 and body["status"] == "SUCCEEDED"
        assert body["output"] == {"resize": "gpu", "data": {"step": "hello", "data": {"x": 1}}}
        # A queue owned by the gpu group, sent to through the api host, runs the gpu group's worker.
        status, _ = _http(f"http://127.0.0.1:{api_port}/__pskit/queues/jobs", b'{"messages": [{"message": {"n": 7}}]}')
        assert status == 202
        got = project.work_dir / "onprem_app_gpu" / "got.txt"
        while not got.is_file() and time.time() < deadline + 15:
            time.sleep(0.2)
        assert json.loads(got.read_text("utf-8").splitlines()[0]) == {"n": 7}
    finally:
        for proc in procs:
            proc.terminate()
        for proc in procs:
            proc.wait(timeout=10)


def test_a_saved_servers_home_data_dir_keeps_groups_inside_it(tmp_path):
    # A saved server's data_dir is often the home folder: a sibling (/home/azureuser-test-02) is not writable.
    srv.save_server(tmp_path, "vm1", {"host": "10.0.0.5", "user": "azureuser", "auth": "agent",
                                      "data_dir": "/home/azureuser"})
    options = {"placement": {"default": "test-01", "groups": {
        "test-01": {"server": "vm1", "port": 3000}, "test-03": {"server": "vm1", "functions": ["x"]}}}}
    pl.resolve(options, tmp_path, "dev")
    assert options["placement"]["_groups"]["test-03"]["data_dir"] == "/home/azureuser/groups/test-03"
    assert pl.group_data_dir("C:\\data\\pskit", "gpu") == "C:\\data\\pskit\\groups\\gpu"


SHARED = {
    "app/__init__.py": "",
    "app/handlers.py": """
        import json
        from py_serverless_kit import NotFound

        _ITEMS = {"1": {"id": "1"}}


        def hello(event, context):
            return {"hello": "api"}


        def get_item(event, context):
            if "1" not in _ITEMS:
                raise NotFound("none")
            return json.loads(json.dumps(_ITEMS["1"]))
    """,
}


def test_each_group_gets_only_its_own_handlers_of_a_shared_file(make_project, render):
    text = _config(9180, 9181).replace("functions: [resize, worker]", "functions: [get-item]").replace(
        """          resize:
            handler: functions.resize.handler.main
            events: [{http: {method: GET, path: /resize}}]
          worker:
            handler: functions.worker.handler.main
            events: [{queue: {name: jobs}}]
""", """          get-item:
            handler: app.handlers.get_item
            events: [{http: {method: GET, path: /items}}]
""").replace("handler: functions.hello.handler.main", "handler: app.handlers.hello").replace(
        "Second: {type: task, function: resize, end: true}", "Second: {type: task, function: get-item, end: true}")
    project = make_project(text, files=SHARED)
    render(project)
    work = project.work_dir
    api_code = (work / "onprem_app" / "staging" / "app" / "handlers.py").read_text("utf-8")
    gpu_code = (work / "onprem_app_gpu" / "staging" / "app" / "handlers.py").read_text("utf-8")
    assert "def hello" in api_code and "def get_item" not in api_code and "NotFound" not in api_code
    assert "def get_item" in gpu_code and "def hello" not in gpu_code and "_ITEMS" in gpu_code
    assert (project.root / "app" / "handlers.py").read_text("utf-8").count("def ") == 2  # the source is untouched
    api = json.loads((work / "onprem_app" / "pskit_host.json").read_text("utf-8"))
    gpu = json.loads((work / "onprem_app_gpu" / "pskit_host.json").read_text("utf-8"))
    assert api["stripped"] == {"app/handlers.py": ["get_item"]} and gpu["stripped"] == {"app/handlers.py": ["hello"]}
    assert api["gateway"] is False and gpu["gateway"] is False  # each server answers only its own routes


def test_gateway_is_on_with_a_load_balancer():
    parsed = pl.parse({"groups": {"api": {}, "gpu": {"local": True, "functions": ["r"]}}}, ["r"])
    assert pl.gateway(parsed, {}) is False and pl.gateway(parsed, {"balancer": "edge"}) is True
    assert pl.gateway(parsed, {}, balanced=True) is True  # a group's cluster is behind a load balancer
    assert pl.gateway(pl.parse({"gateway": False, "groups": {"api": {}}}, []), {}, balanced=True) is False
    explicit = pl.parse({"gateway": True, "groups": {"api": {}}}, [])
    assert pl.gateway(explicit, {}) is True
    # Behind a load balancer attached to some clusters: only the groups behind the same one.
    assert pl.gateway(parsed, {}, ["gpu"]) == ["gpu"] and pl.gateway(parsed, {}, []) is False
    assert pl.gateway(parsed, {"balancer": "edge"}, []) is True


def test_a_group_passes_on_only_the_routes_of_groups_behind_its_load_balancer():
    from py_serverless_kit.runtime.onprem_host import Host

    peers = SimpleNamespace(remote=lambda fn: {"a": "c2", "b": "vm", "c": "c1b"}.get(fn))
    groups = {g: {"url": f"http://{g}:8080"} for g in ("c2", "vm", "c1b")}
    host = SimpleNamespace(peers=peers, spec={"functions": {"own": {}}, "gateway": ["c1b"], "groups": groups})
    assert Host.served_elsewhere(host, "own") is None
    assert Host.served_elsewhere(host, "c") is None  # behind the same load balancer: passed on
    assert Host.served_elsewhere(host, "a") == ("c2", "http://c2:8080")
    assert Host.served_elsewhere(host, "b") == ("vm", "http://vm:8080")
    host.spec["gateway"] = True
    assert Host.served_elsewhere(host, "a") is None
    with pytest.raises(pl.PlacementError, match="gateway is true or false"):
        pl.parse({"gateway": "yes", "groups": {"api": {}}}, [])


def test_tests_of_http_functions_go_to_their_groups_host(make_project, render):
    from py_serverless_kit.core.onprem_control import control_for_group

    project = make_project(_config(9180, 9181), files=HANDLERS)
    render(project)
    record = {"provider": "onprem", "stage": "dev", "key": "onprem-dev"}
    gpu = control_for_group(record, project.root, "gpu")
    assert gpu is not None and gpu.base_url == "http://127.0.0.1:9181"
    assert control_for_group(record, project.root, "api") is None  # the default group: control_for
    assert control_for_group(record, project.root, "") is None


def test_a_function_error_is_not_reported_as_an_unreachable_host(monkeypatch):
    from py_serverless_kit.core.onprem_control import FunctionFailed, HostControl

    control = HostControl("http://127.0.0.1:9")
    body = b'{"errorType": "AttributeError", "cause": "\'NoneType\' object has no attribute \'query\'"}'
    monkeypatch.setattr(control, "fetch", lambda *a, **k: (500, {}, body))
    with pytest.raises(FunctionFailed) as info:
        control.request("POST", "/__pskit/invoke/step01", {"x": 1})
    assert info.value.error_type == "AttributeError" and "raised AttributeError" in str(info.value)


def test_the_studios_http_handler_stub_also_runs_as_a_workflow_step(tmp_path):
    from py_serverless_kit.runtime.context import Context
    from py_serverless_kit.runtime.event import Event, EventType
    from py_serverless_kit.studio.project import ensure_handler

    (tmp_path / "pskit.yml").write_text("service: s\nprovider: {name: onprem}\nfunctions: {}\n", "utf-8")
    ensure_handler(tmp_path, "functions.step01.handler.main", ["http"], subproject=True)
    scope: dict = {}
    exec((tmp_path / "functions" / "step01" / "handler.py").read_text("utf-8"), scope)  # noqa: S102 - our stub
    out = scope["main"](Event(type=EventType.INVOKE, data={"hello": "world"}), Context(function="step01"))
    assert out == {"message": "Hello, world!", "input": {"hello": "world"}}
