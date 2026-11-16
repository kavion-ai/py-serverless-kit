"""monitoring.logs / monitoring.metrics switches and the resource descriptions shown before a deploy."""

import json

from py_serverless_kit.config.schema import FunctionConfig
from py_serverless_kit.core.deployer import Deployer
from py_serverless_kit.providers import descriptions

YML = """
service: mon
provider:
  name: {provider}
  {options}
  {monitoring}
functions:
  api:
    handler: app.handlers.hello
    events:
      - http: GET /hello
  worker:
    handler: app.handlers.worker
    {fn_monitoring}
    events:
      - queue: {{name: mon-jobs}}
"""


def yml(provider="aws", options="", monitoring="", fn_monitoring=""):
    return YML.format(provider=provider, options=options, monitoring=monitoring, fn_monitoring=fn_monitoring)


def package(project):
    result = Deployer(project, echo=lambda _m: None).package(skip_deps=True)
    return result, json.loads(result.tf_file.read_text("utf-8"))


def test_monitoring_shorthand_and_inheritance(make_project):
    assert FunctionConfig.model_validate({"handler": "a.b", "monitoring": False}).monitoring.logs is False
    cfg = make_project(yml(monitoring="monitoring: {logs: false}", fn_monitoring="monitoring: {logs: true}")).config
    assert cfg.logs_of(cfg.functions["api"]) is False  # provider default
    assert cfg.logs_of(cfg.functions["worker"]) is True  # function wins
    assert cfg.metrics_of(cfg.functions["api"]) is True  # on unless switched off


# --------------------------------------------------------------------------- AWS
def test_aws_logs_on_by_default(make_project):
    _r, tf = package(make_project(yml()))
    res = tf["resource"]
    assert set(res["aws_cloudwatch_log_group"]) == {"logs_api", "logs_worker"}
    assert "lambda_nologs" not in res["aws_iam_role"]


def test_aws_logs_off_for_one_function(make_project):
    _r, tf = package(make_project(yml(fn_monitoring="monitoring: {logs: false}")))
    res = tf["resource"]
    assert set(res["aws_cloudwatch_log_group"]) == {"logs_api"}
    assert res["aws_lambda_function"]["worker"]["role"] == "${aws_iam_role.lambda_nologs.arn}"
    assert res["aws_lambda_function"]["api"]["role"] == "${aws_iam_role.lambda.arn}"
    attachments = {k: v["policy_arn"] for k, v in res["aws_iam_role_policy_attachment"].items()}
    assert not any(k.startswith("lambda_nologs") for k in attachments)  # no CloudWatch Logs managed policies
    sqs = json.loads(res["aws_iam_role_policy"]["lambda-nologs-sqs".replace("-", "_")]["policy"])
    assert "logs:PutLogEvents" not in json.dumps(sqs) and "sqs:ReceiveMessage" in json.dumps(sqs)


def test_aws_metrics_off_warns(make_project):
    issues = make_project(yml(monitoring="monitoring: {metrics: false}")).validate()
    assert any(i.level == "warning" and i.where == "monitoring.metrics" for i in issues)


# --------------------------------------------------------------------------- Azure
AZ = "options: {subscription_id: '00000000-0000-0000-0000-000000000000'}"


def test_azure_logs_off_sets_host_log_level(make_project):
    project = make_project(yml("azure", AZ, fn_monitoring="monitoring: {logs: false}"))
    _r, tf = package(project)
    host = json.loads((project.work_dir / "build" / "host.json").read_text("utf-8"))
    levels = host["logging"]["logLevel"]
    assert levels["default"] == "Information"
    assert [k for k, v in levels.items() if v == "None"] == ["Function.worker_queue_0"]
    assert "azurerm_application_insights" in tf["resource"]  # api still uses it


def test_azure_everything_off_drops_insights(make_project):
    _r, tf = package(make_project(yml("azure", AZ, monitoring="monitoring: false")))
    assert "azurerm_application_insights" not in tf["resource"]
    assert "azurerm_log_analytics_workspace" not in tf["resource"]


def test_azure_partial_metrics_warns(make_project):
    issues = make_project(yml("azure", AZ, fn_monitoring="monitoring: {metrics: false}")).validate()
    assert any(i.where == "monitoring.metrics" and "shares one Application Insights" in i.message for i in issues)


def test_gcp_switches_have_no_effect(make_project):
    issues = make_project(yml("gcp", "options: {project: p}", monitoring="monitoring: false")).validate()
    assert {i.where for i in issues if i.level == "warning"} >= {"monitoring.logs", "monitoring.metrics"}


# --------------------------------------------------------------------------- descriptions
def test_summary_describes_every_resource(make_project):
    project = make_project(yml())
    result, tf = package(project)
    types = {r["type"] for r in result.resources}
    assert types == set(tf["resource"])
    assert sum(r["count"] for r in result.resources) == result.resource_count
    log_groups = next(r for r in result.resources if r["type"] == "aws_cloudwatch_log_group")
    assert log_groups["category"] == "monitoring" and log_groups["optional"] == descriptions.LOGS
    saved = descriptions.load(project.work_dir)
    assert saved["provider"] == "aws" and saved["monitoring"]["worker"] == {"logs": True, "metrics": True}
    text = "\n".join(descriptions.lines(result.resources))
    assert text.startswith("Will create or update") and "Lambda function that runs your handler" in text


def test_unknown_types_get_a_generic_description():
    summary = descriptions.summarize({"resource": {"acme_widget_thing": {"a": {}}}})
    assert summary[0]["category"] == "other" and "widget thing" in summary[0]["description"]


def test_every_generated_type_is_described(make_project):
    """Each provider's representative render uses only types the catalog knows."""
    from tests.conftest import full_config

    for provider, opts in (("aws", None), ("azure", {"subscription_id": "x"}), ("gcp", {"project": "p"})):
        result, _tf = package(make_project(full_config(provider, options=opts)))
        unknown = [r["type"] for r in result.resources if r["category"] == "other"]
        assert not unknown, (provider, unknown)


def test_studio_deploy_resources(make_project, tmp_path):
    from py_serverless_kit.studio import system

    assert "Package" in system.deploy_resources(tmp_path, "aws", "dev")["reason"]
    package(make_project(yml()))
    data = system.deploy_resources(tmp_path, "aws", "dev")
    assert data["resources"] and data["package_type"] == "zip"
