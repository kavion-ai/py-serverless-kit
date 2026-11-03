import json

from py_serverless_kit.config.schema import ScheduleEvent
from py_serverless_kit.providers.huawei import HuaweiProvider, quartz_cron, rate_expression
from tests.conftest import full_config

CONFIG = """
service: demo
provider:
  name: huawei
  options: {apig_instance_id: inst-123}
functions:
  hello:
    handler: app.handlers.hello
    events:
      - http: GET /hello/{name}
      - http: {path: "/files/{path+}", method: ANY, auth: iam}
  tick:
    handler: app.handlers.tick
    events:
      - schedule: 2 hours
      - schedule: {cron: "30 6 * * 1", input: {report: weekly}, enabled: false}
  worker:
    handler: app.handlers.worker
    events:
      - storage: {bucket: uploads, suffix: .csv}
      - topic: {name: events, existing: true}
  step:
    handler: app.handlers.step
workflows:
  pipeline:
    start_at: First
    states:
      First: {type: task, function: step}
"""


def test_full_config_needs_apig_and_rejects_queue(make_project):
    issues = "\n".join(str(i) for i in make_project(full_config("huawei")).validate() if i.level == "error")
    assert "apig_instance_id" in issues
    assert "`queue`" in issues


def test_function(make_project, render):
    doc = render(make_project(CONFIG))
    fn = doc["resource"]["huaweicloud_fgs_function"]["hello"]
    assert fn["name"] == "demo-dev-hello"
    assert fn["handler"] == "index.handler"
    assert fn["runtime"] == "Python3.12"
    assert fn["code_type"] == "zip"
    assert "filebase64" in fn["func_code"]
    env = json.loads(fn["user_data"])
    assert env["PSKIT_FUNCTION"] == "hello" and env["PSKIT_PROVIDER"] == "huawei"
    assert doc["provider"]["huaweicloud"][0]["region"] == "cn-north-4"


def test_gateway(make_project, render):
    doc = render(make_project(CONFIG))
    res = doc["resource"]
    assert res["huaweicloud_apig_group"]["http"]["instance_id"] == "inst-123"
    apis = res["huaweicloud_apig_api"]
    assert apis["hello_0"]["request_path"] == "/hello/{name}"
    assert apis["hello_0"]["matching"] == "Exact"
    assert apis["hello_0"]["request_params"][0]["location"] == "PATH"
    assert apis["hello_0"]["func_graph"]["function_urn"] == "${huaweicloud_fgs_function.hello.urn}"
    assert apis["hello_1"]["request_path"] == "/files" and apis["hello_1"]["matching"] == "Prefix"
    assert apis["hello_1"]["security_authentication"] == "IAM"
    assert set(res["huaweicloud_apig_api_publishment"]) == {"hello_0", "hello_1", "pipeline_orchestrator_0"}
    out = doc["output"]["pskit"]["value"]
    assert out["endpoint"] == "https://${data.huaweicloud_apig_groups.http.groups[0].sl_domain}"


def test_triggers(make_project, render):
    doc = render(make_project(CONFIG))
    trig = doc["resource"]["huaweicloud_fgs_trigger"]
    rate = trig["tick_timer_0"]
    assert rate["type"] == "TIMER" and rate["timer"]["schedule_type"] == "Rate" and rate["timer"]["schedule"] == "2h"
    cron = trig["tick_timer_1"]
    assert cron["status"] == "DISABLED"
    assert cron["timer"]["schedule"] == "0 30 6 ? * MON"
    assert json.loads(cron["timer"]["additional_information"])["data"] == {"report": "weekly"}
    obs = trig["worker_obs_uploads"]
    assert obs["obs"]["bucket_name"] == "uploads" and obs["obs"]["events"] == ["ObjectCreated"]
    assert obs["depends_on"] == ["huaweicloud_obs_bucket.b_uploads"]
    smn = trig["worker_smn_events"]
    assert smn["smn"]["topic_urn"] == "${data.huaweicloud_smn_topics.t_events.topics[0].topic_urn}"
    assert "huaweicloud_smn_topic" not in doc["resource"]


def test_helpers():
    assert quartz_cron(ScheduleEvent(cron="0 0 1 * *")) == "0 0 0 1 * ?"
    assert quartz_cron(ScheduleEvent(cron="15 10 * * *")) == "0 15 10 * * ?"
    assert rate_expression(ScheduleEvent(rate="1 day")) == "1d"
    assert HuaweiProvider().physical_name("demo", "dev", "api") == "demo-dev-api"
