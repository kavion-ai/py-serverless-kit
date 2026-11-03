"""The on-prem host speaks the Lambda Invoke and SQS APIs: boto3 code only changes endpoint_url."""

from __future__ import annotations

import json
import threading
import time

import pytest

from py_serverless_kit.core.deployer import Deployer
from py_serverless_kit.runtime.onprem_host import Host, activate_layout

boto3 = pytest.importorskip("boto3")
from botocore.config import Config  # noqa: E402
from botocore.exceptions import ClientError  # noqa: E402

HANDLERS = """
def billing(event, ctx):
    return {"charged": event.data}

def boom(event, ctx):
    raise ValueError("card declined")
"""


@pytest.fixture
def aws_host(make_project, tmp_path):
    project = make_project(
        f"""
        service: shop
        provider:
          name: onprem
          options: {{data_dir: "{(tmp_path / 'd').as_posix()}", admin_token: tok3n}}
        resources:
          jobs: {{type: queue, name: order-jobs}}
        functions:
          billing: {{handler: app.handlers.billing}}
          boom: {{handler: app.handlers.boom}}
        """,
        files={"app/handlers.py": HANDLERS},
    )
    Deployer(project, echo=lambda _m: None).package(skip_deps=True)
    root = project.work_dir / "onprem_app"
    activate_layout(root)
    host = Host(root)
    host.open()
    httpd = host.make_server(0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield host, f"http://127.0.0.1:{httpd.server_address[1]}", project
    httpd.shutdown()
    httpd.server_close()
    host.executor.shutdown()
    host.logs.close()


def _client(service, base, key="tok3n"):
    return boto3.client(service, endpoint_url=base, region_name="eu-west-1", aws_access_key_id=key,
                        aws_secret_access_key="x", config=Config(retries={"total_max_attempts": 1, "mode": "standard"}))


def test_lambda_invoke_api_with_names_and_arns(aws_host):
    _host, base, _project = aws_host
    lam = _client("lambda", base)
    for name in ("billing", "shop-dev-billing", "arn:aws:lambda:eu-west-1:123456789012:function:shop-dev-billing",
                 "arn:aws:lambda:eu-west-1:123456789012:function:shop-dev-billing:prod"):
        out = lam.invoke(FunctionName=name, Payload=json.dumps({"amount": 5}))
        assert out["StatusCode"] == 200 and "FunctionError" not in out
        assert json.loads(out["Payload"].read()) == {"charged": {"amount": 5}}
    failed = lam.invoke(FunctionName="boom", Payload=b"{}")
    assert failed["FunctionError"] == "Unhandled"
    assert json.loads(failed["Payload"].read())["errorMessage"] == "card declined"
    assert lam.invoke(FunctionName="billing", InvocationType="Event", Payload=b"{}")["StatusCode"] == 202
    with pytest.raises(ClientError, match="ResourceNotFoundException"):
        lam.invoke(FunctionName="missing")
    with pytest.raises(ClientError) as exc:
        _client("lambda", base, key="wrong").invoke(FunctionName="billing")
    assert exc.value.response["ResponseMetadata"]["HTTPStatusCode"] == 403


def test_sqs_api_over_host_queues(aws_host):
    host, base, _project = aws_host
    sqs = _client("sqs", base)
    assert any(u.endswith("/order-jobs") for u in sqs.list_queues()["QueueUrls"])
    url = sqs.get_queue_url(QueueName="order-jobs")["QueueUrl"]
    sent = sqs.send_message(QueueUrl=url, MessageBody="one", MessageAttributes={"k": {"DataType": "String", "StringValue": "v"}})
    assert sent["MD5OfMessageBody"] == "f97c5d29941bfb1b2fdab0874906ab82"  # md5("one")
    batch = sqs.send_message_batch(QueueUrl=url, Entries=[{"Id": "a", "MessageBody": "two"}, {"Id": "b", "MessageBody": "three"}])
    assert [e["Id"] for e in batch["Successful"]] == ["a", "b"]
    attrs = sqs.get_queue_attributes(QueueUrl=url, AttributeNames=["ApproximateNumberOfMessages"])["Attributes"]
    assert attrs["ApproximateNumberOfMessages"] == "3"
    got = sqs.receive_message(QueueUrl=url, MaxNumberOfMessages=2, MessageAttributeNames=["All"])["Messages"]
    assert [m["Body"] for m in got] == ["one", "two"] and got[0]["MessageAttributes"]["k"]["StringValue"] == "v"
    sqs.delete_message(QueueUrl=url, ReceiptHandle=got[0]["ReceiptHandle"])
    sqs.change_message_visibility(QueueUrl=url, ReceiptHandle=got[1]["ReceiptHandle"], VisibilityTimeout=0)
    again = sqs.receive_message(QueueUrl=url, MaxNumberOfMessages=10)["Messages"]
    assert sorted(m["Body"] for m in again) == ["three", "two"]
    assert again[[m["Body"] for m in again].index("two")]["Attributes"]["ApproximateReceiveCount"] == "2"
    sqs.delete_message_batch(QueueUrl=url, Entries=[{"Id": str(i), "ReceiptHandle": m["ReceiptHandle"]} for i, m in enumerate(again)])
    assert host.broker.queue_depth("order-jobs") == 0
    started = time.monotonic()
    assert "Messages" not in sqs.receive_message(QueueUrl=url, WaitTimeSeconds=1)
    assert time.monotonic() - started >= 0.9          # long polling waited
    sqs.send_message(QueueUrl=url, MessageBody="x")
    sqs.purge_queue(QueueUrl=url)
    assert host.broker.queue_depth("order-jobs") == 0
    with pytest.raises(ClientError) as exc:
        sqs.get_queue_url(QueueName="nope")
    assert exc.value.response["Error"]["Code"] in ("QueueDoesNotExist", "AWS.SimpleQueueService.NonExistentQueue")


def test_invoke_accepts_arns_and_deployed_names(aws_host, monkeypatch):
    _host, _base, project = aws_host
    from py_serverless_kit.runtime import invoke as inv
    from py_serverless_kit.runtime.manifest import set_manifest

    root = project.work_dir / "onprem_app"
    monkeypatch.setenv("PSKIT_MANIFEST", str(root / "app" / "pskit_manifest.json"))
    monkeypatch.setenv("PSKIT_SERVICE", "shop")
    monkeypatch.setenv("PSKIT_STAGE", "dev")
    set_manifest(None)
    assert inv.logical_name("billing") == "billing"
    assert inv.logical_name("shop-dev-billing") == "billing"
    assert inv.logical_name("arn:aws:lambda:eu-west-1:1:function:shop-dev-billing:live") == "billing"
    assert inv.logical_name("someone-else") == "someone-else"


def test_onprem_queue_url_binding(make_project, render):
    project = make_project(
        """
        service: shop
        provider: {name: onprem, options: {port: 9090}}
        resources: {jobs: {type: queue}}
        functions: {worker: {handler: app.handlers.hello}}
        """
    )
    from py_serverless_kit.core.deployer import Deployer as D

    D(project, echo=lambda _m: None).package(skip_deps=True)
    spec = json.loads((project.work_dir / "onprem_app" / "pskit_host.json").read_text("utf-8"))
    env = spec["functions"]["worker"]["environment"]
    assert env["PSKIT_RESOURCE_JOBS_URL"] == "http://127.0.0.1:9090/000000000000/jobs"
