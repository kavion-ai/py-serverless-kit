import json
import shutil

import pytest

from tests.conftest import full_config


def test_full_render(make_project, render):
    tf = render(make_project(full_config("aws", "eu-west-1")))
    res = tf["resource"]
    assert tf["terraform"]["required_providers"]["aws"]["source"] == "hashicorp/aws"
    assert tf["provider"]["aws"][0]["region"] == "eu-west-1"
    for rtype in (
        "aws_lambda_function",
        "aws_iam_role",
        "aws_apigatewayv2_api",
        "aws_apigatewayv2_route",
        "aws_scheduler_schedule",
        "aws_sqs_queue",
        "aws_lambda_event_source_mapping",
        "aws_s3_bucket",
        "aws_s3_bucket_notification",
        "aws_sns_topic",
        "aws_sns_topic_subscription",
        "aws_sfn_state_machine",
    ):
        assert rtype in res, rtype

    hello = res["aws_lambda_function"]["hello"]
    assert hello["function_name"] == "demo-dev-hello"
    assert hello["handler"] == "pskit_entry.handler"
    env = hello["environment"]["variables"]
    assert env["PSKIT_FUNCTION"] == "hello" and env["PSKIT_PROVIDER"] == "aws"

    routes = {r["route_key"] for r in res["aws_apigatewayv2_route"].values()}
    assert routes == {"GET /hello/{name}", "POST /hello"}
    assert res["aws_apigatewayv2_api"]["http"]["cors_configuration"]["allow_origins"] == ["*"]

    schedules = sorted(s["schedule_expression"] for s in res["aws_scheduler_schedule"].values())
    assert schedules == ["cron(0 12 ? * 2 *)", "rate(5 minutes)"]
    inputs = [json.loads(s["target"]["input"]) for s in res["aws_scheduler_schedule"].values()]
    assert {"__pskit": "schedule", "data": {"report": "weekly"}, "source": "aws.scheduler"} in inputs

    mapping = next(iter(res["aws_lambda_event_source_mapping"].values()))
    assert mapping["function_response_types"] == ["ReportBatchItemFailures"]

    sm = res["aws_sfn_state_machine"]["wf_pipeline"]
    assert "${aws_lambda_function.step.arn}" in sm["definition"]
    asl = json.loads(sm["definition"].replace("${aws_lambda_function.step.arn}", "ARN"))
    assert asl["StartAt"] == "First" and asl["States"]["Second"]["End"] is True

    outputs = tf["output"]["pskit"]["value"]
    assert set(outputs["functions"]) == {"hello", "tick", "worker", "step"}
    assert outputs["endpoint"] == "${aws_apigatewayv2_api.http.api_endpoint}"


def test_existing_resources_and_iam(make_project, render):
    tf = render(
        make_project(
            """
            service: svc
            provider:
              name: aws
              iam:
                statements:
                  - {actions: ["dynamodb:GetItem"], resources: ["arn:aws:dynamodb:*:*:table/${aws:username}"]}
                  - {actions: ["dynamodb:PutItem"], resources: ["${tf:aws_dynamodb_table.orders.arn}"]}
            functions:
              a:
                handler: app.handlers.worker
                iam: {statements: [{actions: ["s3:GetObject"]}]}
                options: {layers: ["arn:aws:lambda:us-east-1:1:layer:x:1"]}
                events:
                  - queue: {name: existing-q, existing: true}
                  - storage: {bucket: existing-b, existing: true}
                  - topic: {name: existing-t, existing: true}
            """
        )
    )
    assert "aws_sqs_queue" not in tf["resource"]
    assert set(tf["resource"]["aws_s3_bucket"]) == {"pskit_artifacts"}  # only the code bucket, not existing-b
    assert set(tf["data"]) == {"aws_sqs_queue", "aws_s3_bucket", "aws_sns_topic"}
    fn = tf["resource"]["aws_lambda_function"]["a"]
    assert fn["role"] == "${aws_iam_role.fn-a.arn}".replace("fn-a", "fn_a")
    assert fn["layers"] == ["arn:aws:lambda:us-east-1:1:layer:x:1"]
    policy = tf["resource"]["aws_iam_role_policy"]["fn_a-custom".replace("-", "_")]["policy"]
    assert "$${aws:username}" in policy  # IAM variable escaped for terraform
    assert '"${aws_dynamodb_table.orders.arn}"' in policy  # explicit ${tf:...} reference kept


def test_validation_errors(make_project):
    project = make_project(
        """
        service: svc
        provider: {name: aws}
        functions:
          a:
            handler: app.handlers.hello
            timeout: 1000
            events: [{http: {path: /x, auth: key}}]
        """
    )
    errors = [str(i) for i in project.validate() if i.level == "error"]
    assert any("API keys" in e for e in errors)
    assert any("exceeds" in e for e in errors)


def test_dead_letter_and_fifo(make_project, render):
    tf = render(
        make_project(
            """
            service: svc
            provider: {name: aws}
            functions:
              a:
                handler: app.handlers.worker
                timeout: 20
                events: [{queue: {name: orders, fifo: true, dead_letter: orders-dlq, max_receive: 3}}]
            """
        )
    )
    queues = tf["resource"]["aws_sqs_queue"]
    main = queues["q-orders_fifo".replace("-", "_")]
    assert main["fifo_queue"] is True and main["visibility_timeout_seconds"] == 120
    assert '"maxReceiveCount":3' in main["redrive_policy"]
    assert "q_orders-dlq_fifo".replace("-", "_") in queues


def test_embedded_engine_on_request(make_project, render):
    tf = render(
        make_project(
            """
            service: svc
            provider: {name: aws}
            functions:
              step: {handler: app.handlers.step}
            workflows:
              wf:
                engine: embedded
                start_at: A
                states: {A: {type: task, function: step, end: true}}
            """
        )
    )
    fns = tf["resource"]["aws_lambda_function"]
    assert "wf_orchestrator" in fns
    assert "aws_sfn_state_machine" not in tf["resource"]
    routes = {r["route_key"] for r in tf["resource"]["aws_apigatewayv2_route"].values()}
    assert routes == {"POST /workflows/wf"}


def test_terraform_extra_and_backend(make_project, render):
    tf = render(
        make_project(
            """
            service: svc
            provider:
              name: aws
              state: {backend: s3, config: {bucket: tf-state, key: svc.tfstate, region: us-east-1}}
              terraform:
                extra:
                  resource:
                    aws_dynamodb_table:
                      orders: {name: orders, hash_key: id, billing_mode: PAY_PER_REQUEST, attribute: [{name: id, type: S}]}
            functions: {}
            """
        )
    )
    assert tf["terraform"]["backend"]["s3"]["bucket"] == "tf-state"
    assert tf["resource"]["aws_dynamodb_table"]["orders"]["name"] == "orders"


def test_default_runtime_follows_provider(make_project):
    from py_serverless_kit.providers.registry import get_provider

    yaml = "service: svc\nprovider: {name: %s%s}\nfunctions: {a: {handler: app.handlers.hello}}\n"
    for name in ("aws", "tencent", "ibm"):
        project = make_project(yaml % (name, ""))
        assert project.config.provider.runtime == get_provider(name).default_runtime
        assert not [i for i in project.validate() if i.where == "provider.runtime"]
    assert get_provider("aws").default_runtime == "python3.12"
    assert get_provider("tencent").default_runtime == "python3.10"
    pinned = make_project(yaml % ("tencent", ", runtime: python3.12"))
    assert any(i.where == "provider.runtime" and i.level == "error" for i in pinned.validate())


def test_artifact_uploaded_to_s3_by_default(make_project, render):
    tf = render(make_project(full_config("aws", "eu-west-1")))
    res = tf["resource"]
    bucket = res["aws_s3_bucket"]["pskit_artifacts"]
    assert bucket["bucket_prefix"] == "demo-dev-code-" and bucket["force_destroy"] is True
    assert res["aws_s3_bucket_public_access_block"]["pskit_artifacts"]["block_public_acls"] is True
    obj = res["aws_s3_object"]["artifact"]
    assert obj["bucket"] == "${aws_s3_bucket.pskit_artifacts.id}"
    assert obj["source"] == "${path.module}/artifact.zip"
    assert obj["key"].startswith("demo-dev/artifact-") and obj["key"].endswith(".zip")
    for lam in res["aws_lambda_function"].values():
        assert "filename" not in lam  # inline upload breaks on large zips ("bufio.Scanner: token too long")
        assert lam["s3_bucket"] == "${aws_s3_object.artifact.bucket}"
        assert lam["s3_key"] == "${aws_s3_object.artifact.key}"
        assert lam["source_code_hash"]


def test_artifact_bucket_and_direct_upload_options(make_project, render):
    yaml = """
        service: svc
        provider: {name: aws, options: {%s}}
        functions:
          a: {handler: app.handlers.hello}
        """
    res = render(make_project(yaml % "artifact_bucket: my-deploys"))["resource"]
    assert "pskit_artifacts" not in res.get("aws_s3_bucket", {})
    assert res["aws_s3_object"]["artifact"]["bucket"] == "my-deploys"

    res = render(make_project(yaml % "artifact_upload: direct"))["resource"]
    assert "aws_s3_object" not in res
    assert res["aws_lambda_function"]["a"]["filename"] == "${path.module}/artifact.zip"

    project = make_project(yaml % "artifact_upload: ftp")
    assert any(i.where == "provider.options.artifact_upload" for i in project.validate() if i.level == "error")


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


def test_node_runtime_and_shim(make_project):
    project = make_project(node_config("aws"), files=JS_HANDLERS)
    assert project.provider.runtime_id("nodejs22") == "nodejs22.x"
    files = project.provider.shim_files(project.config)
    assert list(files) == ["pskit_entry.js"]
    assert 'require("./pskit_runtime/adapters/aws").handler' in files["pskit_entry.js"]
    assert project.provider.node_package(project.config) == {}


def test_node_unsupported_runtime_is_reported(make_project):
    project = make_project(node_config("aws").replace("nodejs20", "nodejs24"), files=JS_HANDLERS)
    assert any("nodejs24" in i.message and i.level == "error" for i in project.validate())


@NODE_SKIP
def test_node_render_uses_nodejs_runtime(make_project, render):
    tf = render(make_project(node_config("aws"), files=JS_HANDLERS))
    fn = tf["resource"]["aws_lambda_function"]["hello"]
    assert fn["runtime"] == "nodejs20.x" and fn["handler"] == "pskit_entry.handler"
