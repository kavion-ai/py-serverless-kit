import json

from py_serverless_kit.config.schema import ScheduleEvent
from py_serverless_kit.providers.alibaba import AlibabaProvider
from py_serverless_kit.providers.schedule import named_cron5
from tests.conftest import full_config

CONFIG = """
service: demo
provider:
  name: alibaba
  region: cn-shanghai
functions:
  hello:
    handler: app.handlers.hello
    memory: 512
    events:
      - http: GET /hello/{name}
      - http: {path: /hello, method: POST, cors: true}
  tick:
    handler: app.handlers.tick
    events:
      - schedule: 5 minutes
      - schedule: {cron: "0 12 * * 1-5", input: {report: weekly}}
  worker:
    handler: app.handlers.worker
    events:
      - storage: {bucket: demo-uploads-1234, suffix: .csv, events: [created, deleted]}
      - topic: events
  step:
    handler: app.handlers.step
workflows:
  pipeline:
    start_at: First
    states:
      First: {type: task, function: step}
"""


def test_queue_events_are_rejected(make_project):
    project = make_project(full_config("alibaba"))
    errors = [i for i in project.validate() if i.level == "error"]
    assert any("does not support `queue`" in str(e) for e in errors)


def test_render_functions_and_triggers(make_project, render):
    doc = render(make_project(CONFIG))
    assert doc["provider"]["alicloud"][0]["region"] == "cn-shanghai"
    assert doc["terraform"]["required_providers"]["alicloud"]["source"] == "aliyun/alicloud"

    fns = doc["resource"]["alicloud_fcv3_function"]
    assert set(fns) == {"hello", "tick", "worker", "step", "pipeline_orchestrator"}
    hello = fns["hello"]
    assert hello["function_name"] == "demo-dev-hello"
    assert hello["handler"] == "index.handler"
    assert hello["runtime"] == "python3.12"
    assert hello["memory_size"] == 512
    assert "filebase64" in hello["code"]["zip_file"]
    assert hello["environment_variables"]["PSKIT_FUNCTION"] == "hello"
    assert fns["pipeline_orchestrator"]["environment_variables"]["PSKIT_HANDLER"].endswith("workflow.orchestrate")

    triggers = doc["resource"]["alicloud_fcv3_trigger"]
    http = json.loads(triggers["hello_http"]["trigger_config"])
    assert http["authType"] == "anonymous" and http["methods"] == ["GET", "POST", "OPTIONS"]
    rate = json.loads(triggers["tick_timer_0"]["trigger_config"])
    assert rate["cronExpression"] == "@every 5m"
    cron = json.loads(triggers["tick_timer_1"]["trigger_config"])
    assert cron["cronExpression"] == "0 0 12 * * MON-FRI"
    assert json.loads(cron["payload"]) == {
        "__pskit": "schedule",
        "data": {"report": "weekly"},
        "source": "alibaba.timer",
    }

    oss = triggers["worker_oss_demo_uploads_1234"]
    assert oss["trigger_type"] == "oss"
    assert oss["source_arn"] == "acs:oss:cn-shanghai:${data.alicloud_account.current.id}:demo-uploads-1234"
    assert oss["invocation_role"] == "${alicloud_ram_role.triggers.arn}"
    assert json.loads(oss["trigger_config"])["events"] == ["oss:ObjectCreated:*", "oss:ObjectRemoved:*"]
    assert triggers["worker_mns_events"]["trigger_type"] == "mns_topic"
    assert "alicloud_oss_bucket" in doc["resource"]
    assert "alicloud_message_service_topic" in doc["resource"]


def test_outputs(make_project, render):
    out = render(make_project(CONFIG))["output"]["pskit"]["value"]
    hello = out["functions"]["hello"]
    assert hello["url"] == "${alicloud_fcv3_trigger.hello_http.http_trigger[0].url_internet}"
    assert hello["base_url"] == hello["url"]
    assert out["endpoint"] == hello["url"]
    assert out["workflows"]["pipeline"]["id"] == "${alicloud_fcv3_function.pipeline_orchestrator.function_name}"
    assert "url" not in out["functions"]["tick"]


def test_shim_in_bundle(make_project, render):
    project = make_project(CONFIG)
    render(project)
    shim = (project.work_dir / "build" / "index.py").read_text()
    assert "adapters.alibaba import handler" in shim


def test_existing_resources_and_no_role_when_unneeded(make_project, render):
    cfg = """
    service: demo
    provider: {name: alibaba}
    functions:
      api:
        handler: app.handlers.hello
        events: [{http: GET /}]
    """
    doc = render(make_project(cfg))
    assert "alicloud_ram_role" not in doc["resource"]
    assert "data" not in doc


def test_unsupported_auth_and_iam_warning(make_project):
    cfg = """
    service: demo
    provider:
      name: alibaba
      iam: {statements: [{actions: ["oss:GetObject"]}]}
    functions:
      api:
        handler: app.handlers.hello
        events: [{http: {path: /, auth: jwt}}]
    """
    issues = make_project(cfg).validate()
    assert any(i.level == "error" and "auth `jwt`" in i.message for i in issues)
    assert any(i.level == "warning" and "RAM" in i.message for i in issues)


def test_named_cron_and_runtime_ids():
    assert named_cron5(ScheduleEvent(cron="0 1 * * 0,6")) == "0 1 * * SUN,SAT"
    assert named_cron5(ScheduleEvent(cron="*/5 * * * *")) == "*/5 * * * *"
    provider = AlibabaProvider()
    assert provider.physical_name("demo", "dev", "Hello.World") == "demo-dev-hello-world"
    assert provider.runtime_id("python3.10") == "python3.10"
