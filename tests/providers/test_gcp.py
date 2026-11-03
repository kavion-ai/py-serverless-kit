from __future__ import annotations

import base64
import json
import shutil

import pytest

from py_serverless_kit.providers.registry import get_provider
from tests.conftest import full_config

GCP_CONFIG = """
service: demo
provider:
  name: gcp
  options: {project: my-proj}
functions:
  hello:
    handler: app.handlers.hello
    events:
      - http: GET /hello/{name}
      - schedule: {cron: "0 12 * * 1", input: {a: 1}}
  worker:
    handler: app.handlers.worker
    events:
      - queue: jobs
      - schedule: 5 minutes
  files:
    handler: app.handlers.worker
    events: [{storage: {bucket: demo-uploads-1234, suffix: .csv}}]
  step:
    handler: app.handlers.step
workflows:
  pipeline:
    start_at: First
    states:
      First: {type: task, function: step, next: Second}
      Second: {type: task, function: step, end: true}
"""


def _errors(project):
    return [i for i in project.validate() if i.level == "error"]


def test_render_resources(make_project, render):
    project = make_project(GCP_CONFIG)
    assert _errors(project) == []
    tf = render(project)
    res = tf["resource"]
    for rtype in (
        "google_storage_bucket",
        "google_storage_bucket_object",
        "google_service_account",
        "google_cloudfunctions2_function",
        "google_cloud_run_service_iam_member",
        "google_cloud_scheduler_job",
        "google_pubsub_topic",
        "google_project_iam_member",
        "google_workflows_workflow",
    ):
        assert rtype in res, rtype
    fns = res["google_cloudfunctions2_function"]
    assert fns["hello"]["build_config"]["entry_point"] == "pskit_http"
    assert fns["hello"]["build_config"]["runtime"] == "python312"
    assert fns["worker"]["build_config"]["entry_point"] == "pskit_event"
    assert fns["worker"]["event_trigger"]["event_type"].endswith("messagePublished")
    env = fns["worker"]["service_config"]["environment_variables"]
    assert env["PSKIT_TRIGGER_KIND"] == "queue" and env["PSKIT_GCP_PROJECT"] == "my-proj"
    assert fns["files"]["event_trigger"]["event_type"].endswith("finalized")
    assert fns["files"]["service_config"]["environment_variables"]["PSKIT_STORAGE_SUFFIX"] == ".csv"
    assert "hello_public" in res["google_cloud_run_service_iam_member"]
    assert "worker_public" not in res["google_cloud_run_service_iam_member"]

    jobs = res["google_cloud_scheduler_job"]
    body = json.loads(base64.b64decode(jobs["hello_0"]["http_target"]["body"]))
    assert body == {"__pskit": "schedule", "data": {"a": 1}, "source": "gcp.scheduler"}
    assert "pubsub_target" in jobs["worker_0"]

    wf = res["google_workflows_workflow"]["wf_pipeline"]["source_contents"]
    assert "${google_cloudfunctions2_function.step.url}" in wf
    assert "$${data}" in wf  # workflow expressions escaped for terraform

    out = tf["output"]["pskit"]["value"]
    assert out["functions"]["hello"]["url"] == "${google_cloudfunctions2_function.hello.url}"
    assert "url" not in out["functions"]["worker"]
    assert tf["provider"]["google"][0]["project"] == "my-proj"


def test_full_config_renders_with_split_functions(make_project, render):
    project = make_project(full_config("gcp", options={"project": "p"}))
    assert _errors(project) == []
    tf = render(project)
    fns = tf["resource"]["google_cloudfunctions2_function"]
    # worker has queue + storage + topic -> three event deployments, no HTTP one
    assert {"worker_queue0", "worker_storage0", "worker_topic0"} <= set(fns)
    assert "worker" not in fns
    for key in ("worker_queue0", "worker_storage0", "worker_topic0"):
        env = fns[key]["service_config"]["environment_variables"]
        assert env["PSKIT_FUNCTION"] == "worker"
        assert fns[key]["build_config"]["entry_point"] == "pskit_event"
    assert fns["worker_queue0"]["name"] == "demo-dev-worker-queue0"
    # hello (http only), tick (schedules only) and step (workflow task) are single HTTP deployments
    for key in ("hello", "tick", "step"):
        assert fns[key]["build_config"]["entry_point"] == "pskit_http"
    out = tf["output"]["pskit"]["value"]["functions"]
    assert out["worker"]["id"] == "${google_cloudfunctions2_function.worker_queue0.name}"
    assert out["worker"]["extra"] == [
        "${google_cloudfunctions2_function.worker_storage0.name}",
        "${google_cloudfunctions2_function.worker_topic0.name}",
    ]
    assert "extra" not in out["hello"]


def test_http_and_events_split(make_project, render):
    project = make_project("""
    service: demo
    provider: {name: gcp, options: {project: p}}
    functions:
      mixed:
        handler: app.handlers.hello
        events:
          - http: GET /x
          - topic: t
          - storage: {bucket: up-123, events: [created, deleted]}
          - schedule: 5 minutes
    """)
    assert _errors(project) == []
    tf = render(project)
    fns = tf["resource"]["google_cloudfunctions2_function"]
    assert set(fns) == {"mixed", "mixed_topic0", "mixed_storage0", "mixed_storage1"}
    assert fns["mixed"]["build_config"]["entry_point"] == "pskit_http"
    assert fns["mixed_storage0"]["event_trigger"]["event_type"].endswith("finalized")
    assert fns["mixed_storage1"]["event_trigger"]["event_type"].endswith("deleted")
    job = tf["resource"]["google_cloud_scheduler_job"]["mixed_0"]
    assert job["http_target"]["uri"] == "${google_cloudfunctions2_function.mixed.url}"
    out = tf["output"]["pskit"]["value"]["functions"]["mixed"]
    assert out["id"] == "${google_cloudfunctions2_function.mixed.name}" and len(out["extra"]) == 3
    assert out["url"] == "${google_cloudfunctions2_function.mixed.url}"


def test_event_only_workflow_task_gets_http_deployment(make_project, render):
    project = make_project("""
    service: demo
    provider: {name: gcp, options: {project: p}}
    functions:
      step:
        handler: app.handlers.step
        events: [{queue: jobs}]
    workflows:
      wf:
        start_at: A
        states: {A: {type: task, function: step}}
    """)
    assert _errors(project) == []
    tf = render(project)
    fns = tf["resource"]["google_cloudfunctions2_function"]
    assert set(fns) == {"step", "step_queue0"}
    assert fns["step"]["build_config"]["entry_point"] == "pskit_http"
    src = tf["resource"]["google_workflows_workflow"]["wf_wf"]["source_contents"]
    assert "${google_cloudfunctions2_function.step.url}" in src


def test_storage_with_schedule_gets_http_deployment(make_project, render):
    project = make_project("""
    service: demo
    provider: {name: gcp, options: {project: p}}
    functions:
      f:
        handler: app.handlers.worker
        events: [{storage: up-123}, {schedule: 1 hours}]
    """)
    tf = render(project)
    assert set(tf["resource"]["google_cloudfunctions2_function"]) == {"f", "f_storage0"}
    assert "http_target" in tf["resource"]["google_cloud_scheduler_job"]["f_0"]


def test_requires_project(make_project):
    project = make_project("""
    service: demo
    provider: {name: gcp}
    functions:
      hello: {handler: app.handlers.hello, events: [{http: GET /x}]}
    """)
    assert any("options.project" in i.message for i in _errors(project))


def test_event_timeout_limit(make_project):
    project = make_project("""
    service: demo
    provider: {name: gcp, options: {project: p}}
    functions:
      slow:
        handler: app.handlers.worker
        timeout: 900
        events: [{topic: t}]
    """)
    assert any("540" in i.message for i in _errors(project))


def test_shim_compiles():
    provider = get_provider("gcp")
    files = provider.shim_files(None)  # type: ignore[arg-type]
    compile(files["main.py"], "main.py", "exec")
    assert "def pskit_http" in files["main.py"] and "def pskit_event" in files["main.py"]


def test_requirements_include_functions_framework(make_project, tmp_path):
    from py_serverless_kit.core.deployer import Deployer

    project = make_project(GCP_CONFIG)
    (tmp_path / "requirements.txt").write_text("requests\npy-serverless-kit\n")
    Deployer(project, echo=lambda _m: None).package(skip_deps=True)
    reqs = (project.work_dir / "build" / "requirements.txt").read_text().split()
    assert reqs == ["requests", "functions-framework>=3.5"]


NODE_SKIP = pytest.mark.skipif(shutil.which("node") is None or shutil.which("npm") is None, reason="needs Node.js and npm")

JS_HANDLERS = {"app/handlers.js": "exports.hello = async () => ({ ok: true });\nexports.tick = async () => null;\n"}


def node_config(provider: str, options: str = "{}", extra: str = "") -> str:
    return f"""
service: demo
provider:
  name: {provider}
  runtime: nodejs20
  options: {options}
functions:
  hello:
    handler: app.handlers.hello
    events:
      - http: "GET /hello/{{name}}"
  tick:
    handler: app.handlers.tick
{extra}
"""


def test_node_shim_and_package(make_project):
    project = make_project(node_config("gcp", "{project: p1}"), files=JS_HANDLERS)
    files = project.provider.shim_files(project.config)
    entry = files["pskit_entry.js"]
    assert 'functions.http("pskit_http", pskit.http)' in entry
    assert 'functions.cloudEvent("pskit_event", pskit.cloudEvent)' in entry
    package = project.provider.node_package(project.config)
    assert package["main"] == "pskit_entry.js"
    assert "@google-cloud/functions-framework" in package["dependencies"]
    assert project.provider.node_vendor_dependencies is False


@NODE_SKIP
def test_node_render_runtime_and_entry_points(make_project, render):
    tf = render(make_project(node_config("gcp", "{project: p1}"), files=JS_HANDLERS))
    fn = tf["resource"]["google_cloudfunctions2_function"]["hello"]
    assert fn["build_config"]["runtime"] == "nodejs20"
    assert fn["build_config"]["entry_point"] == "pskit_http"
