"""Every example must validate, package and run locally."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from py_serverless_kit.core.deployer import Deployer
from py_serverless_kit.core.project import Project
from py_serverless_kit.local import LocalRunner, http_event
from py_serverless_kit.providers.registry import get_provider

from .node_support import node_skip_reason, tool_path

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
PROJECT_DIRS = sorted(p.parent for p in EXAMPLES.rglob("pskit.yml") if ".pskit" not in p.parts)
ALL_PROVIDERS = (
    "aws",
    "gcp",
    "azure",
    "alibaba",
    "tencent",
    "huawei",
    "oracle",
    "ibm",
    "digitalocean",
    "cloudflare",
    "onprem",
)

# (example dir, function, method, path, body, expected status)
HTTP_CASES = [
    ("01-hello-http", "hello", "GET", "/hello?name=Ada", None, 200),
    ("02-rest-api", "list-books", "GET", "/books?author=gibson", None, 200),
    ("02-rest-api", "get-book", "GET", "/books/b1", None, 200),
    ("02-rest-api", "get-book", "GET", "/books/nope", None, 404),
    ("02-rest-api", "create-book", "POST", "/books", {"title": 1}, 400),
    (
        "02-rest-api",
        "create-book",
        "POST",
        "/books",
        {"title": "Dune", "author": "F. Herbert", "year": 1965, "isbn": "9780441013593"},
        409,
    ),
    ("02-rest-api", "cover", "GET", "/books/b1/cover", None, 200),
    ("02-rest-api", "docs", "GET", "/docs", None, 302),
    ("02-rest-api", "session", "POST", "/session", {"user": "ada"}, 200),
    ("04-queue-worker", "enqueue", "POST", "/jobs", {"kind": "email"}, 202),
    ("08-multi-cloud", "whoami", "GET", "/whoami", None, 200),
    ("08-multi-cloud", "echo", "POST", "/echo", {"a": 1}, 200),
    (
        "09-function-invoke",
        "quote",
        "POST",
        "/quote",
        {"country": "DE", "items": [{"sku": "a", "qty": 2, "unit_price": 10}]},
        200,
    ),
    ("10-stages-and-config", "config", "GET", "/config", None, 200),
    ("11-custom-terraform", "create-order", "POST", "/orders", {"item": "book"}, 201),
    ("12-async-and-context", "aggregate", "GET", "/aggregate", None, 200),
    ("12-async-and-context", "inspect", "POST", "/inspect", {}, 200),
    ("13-migrate-from-aws-lambda/after", "create-order", "POST", "/orders", {"items": [{"qty": 1, "price": 5}]}, 202),
    ("14-testing", "price", "POST", "/price", {"amount": 100, "code": "VIP25"}, 200),
    ("15-ci-cd-deploy", "health", "GET", "/health", None, 200),
    ("16-on-premises", "hello", "GET", "/hello?name=Ada", None, 200),
    ("17-on-premises-remote", "hello", "GET", "/hello?name=Ada", None, 200),
    ("18-resources", "api", "GET", "/bindings", None, 200),
    ("19-custom-drivers", "enqueue", "POST", "/jobs", {"task": "resize"}, 202),
    ("19-custom-drivers", "enqueue", "POST", "/jobs", {"nope": 1}, 400),
    ("20-onprem-external-clouds", "status", "GET", "/status", None, 200),
    ("21-nodejs-typescript", "hello", "GET", "/hello?name=Ada", None, 200),
    ("21-nodejs-typescript", "create-order", "POST", "/orders", {"item": "pen", "quantity": 2, "unitPrice": 1.5}, 201),
    ("21-nodejs-typescript", "create-order", "POST", "/orders", {"item": ""}, 400),
    ("21-nodejs-typescript", "get-order", "GET", "/orders/ord-1", None, 200),
    ("21-nodejs-typescript", "get-order", "GET", "/orders/nope", None, 404),
]

WORKFLOW_CASES = [
    ("07-workflow-orders", "order-pipeline", "events/happy.json", "SUCCEEDED"),
    ("07-workflow-orders", "order-pipeline", "events/b2b.json", "SUCCEEDED"),
    ("07-workflow-orders", "order-pipeline", "events/declined.json", "PaymentDeclined"),
    ("13-migrate-from-aws-lambda/after", "order-processing", {"items": [{"qty": 2, "price": 300}]}, "SUCCEEDED"),
    ("13-migrate-from-aws-lambda/after", "order-processing", {"items": [{"qty": 0, "price": 1}]}, "OrderRejected"),
    ("14-testing", "scoring", {"vip": True}, "SUCCEEDED"),
    ("16-on-premises", "ping", {}, "SUCCEEDED"),
    ("21-nodejs-typescript", "order-pipeline", "events/order.json", "SUCCEEDED"),
    ("21-nodejs-typescript", "order-pipeline", "events/bad-order.json", "OrderRejected"),
]


def _id(path: Path) -> str:
    return path.relative_to(EXAMPLES).as_posix()


def _copy(example: Path, tmp_path: Path) -> Path:
    target = tmp_path / example.name
    shutil.copytree(
        example, target, ignore=shutil.ignore_patterns(".pskit", "__pycache__", ".pytest_cache", "node_modules")
    )
    return target


@pytest.fixture(autouse=True)
def _node_tools(monkeypatch):
    monkeypatch.setenv("PATH", tool_path())


def _require_node_if_needed(root: Path, run: bool = True) -> None:
    """Node.js examples need node (and tsc for TypeScript) to build or run; skip cleanly without them."""
    if "runtime: nodejs" not in (root / "pskit.yml").read_text("utf-8"):
        return
    reason = node_skip_reason(typescript=any(root.rglob("*.ts"))) if run else None
    if reason:
        pytest.skip(reason)


def _require_provider(name: str) -> None:
    try:
        get_provider(name)
    except Exception as exc:  # noqa: BLE001 - provider still being written
        pytest.skip(f"provider {name} not importable: {exc}")


def _errors(project: Project) -> list:
    return [str(i) for i in project.validate() if i.level == "error"]


def test_every_example_is_discovered():
    names = {_id(p) for p in PROJECT_DIRS}
    assert len(names) == 21, names


@pytest.mark.parametrize("example", PROJECT_DIRS, ids=_id)
def test_validates_and_packages(example: Path, tmp_path: Path):
    root = _copy(example, tmp_path)
    _require_node_if_needed(root)
    project = Project.load(cwd=root)
    _require_provider(project.config.provider.name)
    assert _errors(project) == []
    result = Deployer(project, echo=lambda _m: None).package(skip_deps=True)
    tf = json.loads(result.tf_file.read_text("utf-8"))
    assert "pskit" in tf["output"]
    assert result.artifact.size > 0


@pytest.mark.parametrize("example", PROJECT_DIRS, ids=_id)
@pytest.mark.parametrize("provider", ["aws", "gcp", "azure"])
def test_portable_to_big_three(example: Path, provider: str, tmp_path: Path):
    if _id(example) == "11-custom-terraform" and provider != "aws":
        pytest.skip("terraform.extra in this example is AWS-specific by design")
    _require_provider(provider)
    project = Project.load(cwd=_copy(example, tmp_path), provider=provider)
    assert _errors(project) == []


@pytest.mark.parametrize("example", PROJECT_DIRS, ids=_id)
def test_portable_to_onprem(example: Path, tmp_path: Path):
    _require_provider("onprem")
    root = _copy(example, tmp_path)
    _require_node_if_needed(root)
    project = Project.load(cwd=root, provider="onprem")
    assert _errors(project) == []
    Deployer(project, echo=lambda _m: None).package(skip_deps=True)


@pytest.mark.parametrize("provider", ALL_PROVIDERS)
def test_multi_cloud_all_providers(provider: str, tmp_path: Path):
    _require_provider(provider)
    root = _copy(EXAMPLES / "08-multi-cloud", tmp_path)
    project = Project.load(cwd=root, provider=provider)
    assert _errors(project) == []
    Deployer(project, echo=lambda _m: None).package(skip_deps=True)


@pytest.mark.parametrize("cloud,region", [("aws", "eu-west-1"), ("gcp", "europe-west1"), ("azure", "northeurope")])
def test_multi_cloud_extends_files(cloud: str, region: str, tmp_path: Path):
    _require_provider(cloud)
    root = _copy(EXAMPLES / "08-multi-cloud", tmp_path)
    project = Project.load(f"pskit.{cloud}.yml", cwd=root)
    assert project.config.provider.name == cloud
    assert project.config.provider.region == region
    assert _errors(project) == []


@pytest.mark.parametrize(
    "example,function,method,path,body,status",
    HTTP_CASES,
    ids=[f"{c[0]}:{c[1]}:{c[5]}" for c in HTTP_CASES],
)
def test_http_functions_locally(example, function, method, path, body, status, tmp_path):
    root = _copy(EXAMPLES / example, tmp_path)
    _require_node_if_needed(root)
    runner = LocalRunner(Project.load(cwd=root), env_file=None)
    try:
        resp = runner.invoke(function, http_event(method, path, body))
    finally:
        runner.close()
    assert resp.status == status, resp.render()


@pytest.mark.parametrize(
    "example,workflow,data,expected",
    WORKFLOW_CASES,
    ids=[f"{c[0]}:{c[1]}:{c[3]}" for c in WORKFLOW_CASES],
)
def test_workflows_locally(example, workflow, data, expected, tmp_path):
    from py_serverless_kit.runtime.workflow import WorkflowFailed

    root = _copy(EXAMPLES / example, tmp_path)
    _require_node_if_needed(root)
    if isinstance(data, str):
        data = json.loads((root / data).read_text("utf-8"))
    runner = LocalRunner(Project.load(cwd=root), env_file=None)
    try:
        if expected == "SUCCEEDED":
            assert runner.run_workflow(workflow, data)["output"] is not None
        else:
            with pytest.raises(WorkflowFailed) as exc:
                runner.run_workflow(workflow, data)
            assert exc.value.error == expected
    finally:
        runner.close()


def test_nodejs_queue_worker_partial_failures(tmp_path):
    from py_serverless_kit.local import build_event

    root = _copy(EXAMPLES / "21-nodejs-typescript", tmp_path)
    _require_node_if_needed(root)
    runner = LocalRunner(Project.load(cwd=root), env_file=None)
    try:
        event = build_event("queue", [{"item": "pen"}, {"item": ""}, {"item": "cup", "quantity": 3}])
        assert runner.invoke("process-orders", event).failed == ["local-1"]
    finally:
        runner.close()


def test_queue_worker_partial_failures(tmp_path):
    from py_serverless_kit.local import build_event

    root = _copy(EXAMPLES / "04-queue-worker", tmp_path)
    runner = LocalRunner(Project.load(cwd=root), env_file=None)
    event = build_event("queue", [{"kind": "email"}, {"kind": "email", "simulate_failure": True}, {"kind": "nope"}])
    assert runner.invoke("process-jobs", event).failed == ["local-1"]


def test_stage_overrides(tmp_path):
    root = _copy(EXAMPLES / "10-stages-and-config", tmp_path)
    prod = Project.load(cwd=root, stage="prod").config
    assert prod.provider.memory == 1024
    assert prod.provider.environment["TABLE_NAME"] == "shop-config-prod-orders"
    assert prod.functions["config"].concurrency == 100
    assert prod.provider.state.backend == "s3"


def test_custom_drivers_example_runs_in_the_onprem_host(tmp_path):
    """examples/19: SqliteQueue + FolderStorage feed handlers; failures retry, then dead-letter."""
    import time

    from py_serverless_kit import Event
    from py_serverless_kit.runtime import hostlog
    from py_serverless_kit.runtime.onprem_host import Host, activate_layout

    root = _copy(EXAMPLES / "19-custom-drivers", tmp_path)
    project = Project.load(cwd=root)
    Deployer(project, echo=lambda _m: None).package(skip_deps=True)
    app_root = project.work_dir / "onprem_app"
    activate_layout(app_root)
    host = Host(app_root)
    host.open()
    hostlog.install(host.logs, capture_streams=False)  # what serve_forever() does
    try:
        broker = host.broker
        assert type(broker.queue_driver("jobs").inner).__name__ == "SqliteQueue"
        assert (app_root / "data" / "queues.sqlite3").is_file()  # relative to the host root

        resp = host.invoke("enqueue", Event(type="http", http=_http("POST", "/jobs", {"task": "resize"})))
        assert resp.status == 202 and json.loads(resp.render()[2])["queued"]
        broker.submit_queue("jobs", {"task": "explode"})
        assert broker.queue_depth("jobs") == 2

        now = time.time()
        for attempt in range(3):  # max_receive: 3
            host.pump_queues(now + attempt)
        assert broker.queue_depth("jobs") == 0
        assert broker.queue_depth("jobs-dlq") == 1
        host.pump_queues(now + 10)  # dead-letters consumes the DLQ
        assert broker.queue_depth("jobs-dlq") == 0
        stats = host.stats()["functions"]
        assert stats["worker"]["invocations"] == 3 and stats["dead-letters"]["invocations"] == 1

        inbox = app_root / "data" / "inbox"
        broker.put_object("inbox", "reports/a.csv", b"x,y")
        assert (inbox / "reports" / "a.csv").read_bytes() == b"x,y"
        host.pump_storage(time.time())
        (inbox / "reports" / "a.csv").unlink()
        host.pump_storage(time.time())
        actions = [
            e["fields"].get("action")
            for e in host.logs.query(function="on-file", source="function")["entries"]
            if e["message"] == "file event"
        ]
        assert actions == ["created", "deleted"]
        dead = [e for e in host.logs.query(function="dead-letters")["entries"] if e["message"] == "dead letter"]
        assert dead and "explode" in dead[0]["fields"]["body"]
    finally:
        hostlog.uninstall()
        host.executor.shutdown()
        host.logs.close()


def _http(method, path, body):
    from py_serverless_kit import Headers, HttpRequest

    return HttpRequest(
        method=method,
        path=path,
        headers=Headers({"content-type": "application/json"}),
        body=json.dumps(body).encode(),
    )
