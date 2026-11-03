import json

import pytest

from py_serverless_kit.providers.base import ProviderError
from py_serverless_kit.providers.tencent import TencentProvider
from tests.conftest import full_config

CONFIG = """
service: demo
provider:
  name: tencent
  runtime: python3.10
functions:
  hello:
    handler: app.handlers.hello
    events:
      - http: GET /hello/{name}
      - http: {path: "/files/{path+}", method: ANY, cors: true}
  tick:
    handler: app.handlers.tick
    events:
      - schedule: 5 minutes
      - schedule: {cron: "0 12 * * 1", input: {report: weekly}, name: weekly}
  worker:
    handler: app.handlers.worker
    events:
      - storage: {bucket: uploads-1250000000, prefix: in/}
  step:
    handler: app.handlers.step
workflows:
  pipeline:
    start_at: First
    states:
      First: {type: task, function: step}
"""


def test_full_config_reports_unsupported(make_project):
    issues = [i for i in make_project(full_config("tencent")).validate() if i.level == "error"]
    text = "\n".join(str(i) for i in issues)
    assert "`queue`" in text and "`topic`" in text
    assert "python3.12" not in text  # unpinned runtime falls back to python3.10


def test_render_function(make_project, render):
    project = make_project(CONFIG)
    doc = render(project)
    fns = doc["resource"]["tencentcloud_scf_function"]
    hello = fns["hello"]
    assert hello["name"] == "demo-dev-hello"
    assert hello["handler"] == "index.main_handler"
    assert hello["runtime"] == "Python3.10"
    assert hello["namespace"] == "default"
    zip_name = hello["zip_file"].split("/")[-1]
    assert zip_name.startswith("artifact-") and (project.work_dir / zip_name).is_file()
    assert hello["environment"]["PSKIT_PROVIDER"] == "tencent"


def test_artifact_copy_is_content_addressed(make_project, render):
    project = make_project(CONFIG)
    render(project)
    first = sorted(p.name for p in project.work_dir.glob("artifact-*.zip"))
    (project.root / "app" / "extra.py").write_text("X = 1\n")
    render(project)
    second = sorted(p.name for p in project.work_dir.glob("artifact-*.zip"))
    assert len(first) == len(second) == 1 and first != second


def test_triggers(make_project, render):
    doc = render(make_project(CONFIG))
    fns = doc["resource"]["tencentcloud_scf_function"]
    timers = {t["name"]: t for t in fns["tick"]["triggers"]}
    assert timers["timer-0"]["trigger_desc"] == "0 */5 * * * * *"
    assert timers["weekly"]["trigger_desc"] == "0 0 12 * * MON *"
    cfg = doc["resource"]["tencentcloud_scf_trigger_config"]["tick_weekly"]
    assert cfg["enable"] == "OPEN"
    assert json.loads(cfg["custom_argument"])["data"] == {"report": "weekly"}
    cos = fns["worker"]["triggers"][0]
    assert cos["type"] == "cos"
    assert cos["name"] == "uploads-1250000000.cos.ap-guangzhou.myqcloud.com"
    assert json.loads(cos["trigger_desc"]) == {
        "event": "cos:ObjectCreated:*",
        "filter": {"Prefix": "in/", "Suffix": ""},
    }
    assert "tencentcloud_cos_bucket" in doc["resource"]


def test_api_gateway(make_project, render):
    doc = render(make_project(CONFIG))
    apis = doc["resource"]["tencentcloud_api_gateway_api"]
    first = apis["hello_0"]
    assert first["request_config_path"] == "/hello/{name}"
    assert first["request_config_method"] == "GET"
    assert first["service_config_type"] == "SCF"
    assert first["request_parameters"][0]["name"] == "name"
    assert apis["hello_1"]["request_config_path"] == "/files"
    assert apis["hello_1"]["enable_cors"] is True
    release = doc["resource"]["tencentcloud_api_gateway_service_release"]["release"]
    assert release["environment_name"] == "release" and len(release["depends_on"]) == 3
    out = doc["output"]["pskit"]["value"]
    assert out["endpoint"] == "https://${tencentcloud_api_gateway_service.http.outer_sub_domain}/release"
    assert out["functions"]["hello"]["base_url"] == out["endpoint"]
    assert out["workflows"]["pipeline"]["id"] == "${tencentcloud_scf_function.pipeline_orchestrator.name}"


def test_validation_rules(make_project):
    cfg = """
    service: demo
    provider: {name: tencent, runtime: python3.9, memory: 300}
    functions:
      api:
        handler: app.handlers.hello
        events: [{http: PATCH /x}]
    """
    issues = "\n".join(str(i) for i in make_project(cfg).validate() if i.level == "error")
    assert "PATCH" in issues and "multiple of 128" in issues


def test_names():
    p = TencentProvider()
    assert p.physical_name("demo", "dev", "api_") == "demo-dev-api"
    assert len(p.physical_name("demo", "dev", "x" * 80)) <= 60
    with pytest.raises(ProviderError):
        p.runtime_id("python3.12")


def test_bucket_needs_appid(make_project):
    cfg = """
    service: demo
    provider: {name: tencent, runtime: python3.10}
    functions:
      worker:
        handler: app.handlers.worker
        events: [{storage: uploads}]
    """
    assert any("APPID" in i.message for i in make_project(cfg).validate() if i.level == "error")
