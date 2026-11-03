"""Log backends: on-prem host, CloudWatch, Cloud Logging, Azure and the fallback."""

from __future__ import annotations

import json
import sys
import types
from datetime import datetime, timezone
from typing import Any, Dict, List

import pytest
from click.testing import CliRunner

from py_serverless_kit.core import cloud_logs
from py_serverless_kit.core.cloud_logs import (
    AwsLogs,
    AzureLogs,
    GcpLogs,
    LogError,
    OnPremLogs,
    UnsupportedLogs,
    log_backend,
    parse_line,
)


def _record(provider: str, **extra: Any) -> Dict[str, Any]:
    record = {
        "provider": provider,
        "status": "deployed",
        "region": "eu-west-1",
        "functions": [
            {"name": "api", "resource_name": "svc-dev-api", "console": "https://console.example/api"},
            {"name": "worker", "resource_name": "svc-dev-worker"},
        ],
    }
    record.update(extra)
    return record


# ---------------------------------------------------------------------- parsing


def test_parse_line_formats():
    js = parse_line(json.dumps({"ts": "x", "level": "WARNING", "message": "slow", "request_id": "r1", "order": 7}))
    assert js["level"] == "WARNING" and js["message"] == "slow" and js["request_id"] == "r1"
    assert js["fields"] == {"order": 7}
    lam = parse_line("[ERROR]\t2024-01-01T00:00:00Z\tabc-123\tsomething broke\n")
    assert lam["level"] == "ERROR" and lam["request_id"] == "abc-123" and lam["message"] == "something broke"
    report = parse_line("REPORT RequestId: abc-123\tDuration: 3 ms\tStatus: error")
    assert report["source"] == "invocation" and report["level"] == "ERROR" and report["request_id"] == "abc-123"
    assert parse_line("START RequestId: q Version: $LATEST")["level"] == "INFO"
    assert parse_line("Traceback (most recent call last):")["level"] == "ERROR"
    plain = parse_line("hello {not json")
    assert plain["level"] == "INFO" and plain["message"] == "hello {not json"


# ---------------------------------------------------------------------- factory


def test_factory_picks_backends(tmp_path, monkeypatch):
    assert isinstance(log_backend(_record("aws", status="local"), tmp_path), UnsupportedLogs)
    monkeypatch.setattr(cloud_logs, "_installed", lambda module: False)
    aws = log_backend(_record("aws"), tmp_path)
    assert not aws.supported and "boto3" in aws.reason and aws.info()["console"] == "https://console.example/api"
    assert "google-cloud-logging" in log_backend(_record("gcp"), tmp_path).reason
    assert "log_analytics_workspace_id" in log_backend(_record("azure"), tmp_path).reason
    other = log_backend(_record("cloudflare", provider_display="Cloudflare Workers"), tmp_path)
    assert not other.supported and "Cloudflare Workers" in other.reason
    with pytest.raises(LogError):
        other.delete(all=True)
    assert other.query()["entries"] == [] and other.streams()["items"] == []
    # unknown on-prem host
    assert "address is unknown" in log_backend(_record("onprem"), tmp_path).reason

    monkeypatch.setattr(cloud_logs, "_installed", lambda module: True)
    assert isinstance(log_backend(_record("aws"), tmp_path), AwsLogs)
    assert isinstance(log_backend(_record("gcp"), tmp_path), GcpLogs)
    az = log_backend(_record("azure", outputs={"log_analytics_workspace_id": "ws-1"}), tmp_path)
    assert isinstance(az, AzureLogs) and az.workspace == "ws-1"


# ---------------------------------------------------------------------- on-prem


class FakeControl:
    def __init__(self) -> None:
        self.cleared: List[Any] = []

    def logs(self, **kw: Any) -> Dict[str, Any]:
        return {"entries": [{"seq": 3, "message": "hi"}], "next": 3, "oldest": 1, "kw": kw}

    def log_streams(self) -> Dict[str, Any]:
        return {"items": [{"function": "api", "count": 2, "first": "a", "last": "b"}, {"function": None, "count": 1}]}

    def clear_logs(self, function: Any = None) -> Dict[str, Any]:
        self.cleared.append(function)
        return {"deleted": 2}


def test_onprem_backend():
    control = FakeControl()
    backend = OnPremLogs(_record("onprem"), control)
    page = backend.query(since=2, limit=5, level="ERROR")
    assert page["mode"] == "seq" and page["can_delete"] and page["entries"][0]["seq"] == 3
    assert page["kw"]["level"] == "ERROR"
    streams = backend.streams()["items"]
    assert [s["id"] for s in streams] == ["api", cloud_logs.HOST_STREAM] and streams[1]["name"] == "host"
    assert [s["id"] for s in backend.streams("api")["items"]] == ["api"]
    assert backend.delete(all=True)["deleted"] == 2 and control.cleared == [None]
    assert backend.delete(ids=["api", "api", cloud_logs.HOST_STREAM])["deleted"] == 4
    assert control.cleared[1:] == ["api", cloud_logs.HOST_STREAM]
    backend.delete(function="worker")
    assert control.cleared[-1] == "worker"
    with pytest.raises(ValueError):
        backend.delete()


# ---------------------------------------------------------------------- AWS


class FakeNotFound(Exception):
    response = {"Error": {"Code": "ResourceNotFoundException"}}


class FakeLogsClient:
    def __init__(self) -> None:
        self.calls: List[Dict[str, Any]] = []
        self.deleted: List[tuple] = []
        self.streams = {
            "/aws/lambda/svc-dev-api": [
                {
                    "logStreamName": "2024/01/01/[$LATEST]aaa",
                    "lastEventTimestamp": 1_700_000_000_000,
                    "storedBytes": 10,
                },
                {"logStreamName": "2024/01/01/[$LATEST]bbb", "firstEventTimestamp": 1_600_000_000_000},
            ],
        }

    def filter_log_events(self, **kw: Any) -> Dict[str, Any]:
        self.calls.append(kw)
        if kw["logGroupName"] == "/aws/lambda/svc-dev-worker":
            raise FakeNotFound("no group yet")
        return {
            "events": [
                {"timestamp": 2000, "message": "START RequestId: r1 Version: $LATEST", "logStreamName": "s"},
                {"timestamp": 2000, "message": json.dumps({"level": "ERROR", "message": "bad"}), "logStreamName": "s"},
                {"timestamp": 3000, "message": "[INFO]\tt\tr1\tok", "logStreamName": "s"},
            ]
        }

    def describe_log_streams(self, **kw: Any) -> Dict[str, Any]:
        if kw["logGroupName"] not in self.streams:
            raise FakeNotFound("missing")
        return {"logStreams": self.streams[kw["logGroupName"]]}

    def delete_log_stream(self, logGroupName: str, logStreamName: str) -> None:  # noqa: N803 - boto3 names
        if logStreamName.endswith("bbb"):
            raise RuntimeError("AccessDenied")
        self.deleted.append((logGroupName, logStreamName))


def test_aws_query_streams_delete():
    client = FakeLogsClient()
    backend = AwsLogs(_record("aws"), client=client)
    page = backend.query(since=1000, limit=10, q="ok")
    assert page["mode"] == "time" and page["supported"] and page["can_delete"]
    assert client.calls[0]["startTime"] == 1000 and client.calls[0]["filterPattern"] == '"ok"'
    seqs = [e["seq"] for e in page["entries"]]
    assert seqs == sorted(seqs) and len(set(seqs)) == 3 and seqs[0] == 2_000_000 and seqs[1] == 2_000_001
    assert page["next"] == 3001
    assert [e["level"] for e in page["entries"]] == ["INFO", "ERROR", "INFO"]
    assert page["entries"][0]["source"] == "invocation" and page["entries"][0]["function"] == "api"
    assert [e["message"] for e in backend.query(since=1000, level="error")["entries"]] == ["bad"]
    assert [e["message"] for e in backend.query(since=1000, source="invocation")["entries"]][0].startswith("START")
    with pytest.raises(KeyError):
        backend.query(function="nope")
    # nothing new: the cursor stays put
    client.filter_log_events = lambda **kw: {"events": []}  # type: ignore[method-assign]
    assert backend.query(since=5000)["next"] == 5000

    items = backend.streams()["items"]
    assert [i["id"] for i in items][0] == "/aws/lambda/svc-dev-api|2024/01/01/[$LATEST]aaa"
    assert items[0]["bytes"] == 10 and items[0]["last"].startswith("2023-")

    result = backend.delete(ids=[items[0]["id"]])
    assert result == {"deleted": 1, "errors": []}
    with pytest.raises(ValueError):
        backend.delete(ids=["/aws/lambda/other|x"])
    with pytest.raises(ValueError):
        backend.delete(ids=["no-separator"])
    everything = backend.delete(all=True)
    assert everything["deleted"] == 1 and "AccessDenied" in everything["errors"][0]
    assert all(group == "/aws/lambda/svc-dev-api" for group, _ in client.deleted)


def test_aws_errors_become_log_errors():
    class Broken:
        def filter_log_events(self, **kw: Any) -> Dict[str, Any]:
            raise RuntimeError("Unable to locate credentials")

    with pytest.raises(LogError, match="credentials"):
        AwsLogs(_record("aws"), client=Broken()).query()


# ---------------------------------------------------------------------- GCP


class FakeEntry:
    def __init__(self, ts: datetime, payload: Any, severity: str, service: str) -> None:
        self.timestamp = ts
        self.payload = payload
        self.severity = severity
        self.resource = types.SimpleNamespace(labels={"service_name": service})
        self.labels = {"execution_id": "ex1"}


class FakeGcpClient:
    def __init__(self) -> None:
        self.filters: List[str] = []

    def list_entries(self, filter_: str, order_by: str, max_results: int) -> List[FakeEntry]:
        self.filters.append(filter_)
        ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
        return [
            FakeEntry(ts, {"message": "hello", "level": "INFO"}, "WARNING", "svc-dev-api"),
            FakeEntry(ts, "plain text", "", "svc-dev-worker"),
        ]


def test_gcp_query_and_streams():
    record = _record("gcp")
    record["functions"][0]["id"] = "projects/my-proj/locations/europe-west1/functions/svc-dev-api"
    client = FakeGcpClient()
    backend = GcpLogs(record, client=client)
    assert backend.project() == "my-proj"
    page = backend.query(since=5, level="warning", q="hello")
    assert page["mode"] == "time" and not page["can_delete"]
    assert "severity>=WARNING" in client.filters[0] and '"hello"' in client.filters[0]
    assert '"svc-dev-api"' in client.filters[0] and "cloud_run_revision" in client.filters[0]
    assert [e["function"] for e in page["entries"]] == ["api", "worker"]
    assert page["entries"][0]["level"] == "WARNING" and page["entries"][1]["request_id"] == "ex1"
    assert page["entries"][1]["seq"] == page["entries"][0]["seq"] + 1
    assert [s["id"] for s in backend.streams()["items"]] == ["api", "worker"]
    with pytest.raises(LogError):
        backend.delete(all=True)


# ---------------------------------------------------------------------- Azure


def test_azure_query():
    class Client:
        query: str = ""

        def query_workspace(self, workspace: str, query: str, timespan: Any) -> Any:
            Client.query = query
            col = types.SimpleNamespace
            table = types.SimpleNamespace(
                columns=[
                    col(name=n) for n in ("TimeGenerated", "Message", "SeverityLevel", "OperationName", "OperationId")
                ],
                rows=[[datetime(2024, 1, 1, tzinfo=timezone.utc), "boom", 3, "api_http_0", "op1"]],
            )
            return types.SimpleNamespace(tables=[table])

    backend = AzureLogs(_record("azure"), "ws", client=Client())
    page = backend.query(level="error", q="bo")
    assert 'OperationName startswith "api_"' in Client.query and "SeverityLevel >= 3" in Client.query
    assert page["entries"][0]["function"] == "api" and page["entries"][0]["level"] == "ERROR"
    assert page["entries"][0]["request_id"] == "op1"


# ---------------------------------------------------------------------- CLI


CONFIG = "service: logsvc\nprovider: {name: aws}\nfunctions:\n  api: {handler: app.handlers.hello}\n"


def test_cli_logs_streams_and_delete(make_project, monkeypatch):
    from py_serverless_kit.cli.main import cli
    from py_serverless_kit.core.describe import build_record

    project = make_project(CONFIG)
    project.work_dir.mkdir(parents=True)
    (project.work_dir / "deployment.json").write_text(json.dumps(build_record(project)), "utf-8")
    client = FakeLogsClient()
    client.streams["/aws/lambda/logsvc-dev-api"] = client.streams.pop("/aws/lambda/svc-dev-api")
    fake_boto3 = types.ModuleType("boto3")
    fake_boto3.client = lambda service, region_name=None: client  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "boto3", fake_boto3)
    monkeypatch.setattr(cloud_logs, "_installed", lambda module: True)
    monkeypatch.chdir(project.root)
    runner = CliRunner()

    result = runner.invoke(cli, ["logs", "-n", "5"])
    assert result.exit_code == 0, result.output
    assert "bad" in result.output and "[api]" in result.output

    result = runner.invoke(cli, ["logs", "--streams"])
    assert result.exit_code == 0 and "/aws/lambda/logsvc-dev-api|2024/01/01/[$LATEST]aaa" in result.output

    result = runner.invoke(cli, ["logs", "--delete-all"], input="n\n")
    assert result.exit_code != 0 and not client.deleted
    result = runner.invoke(cli, ["logs", "--delete", "/aws/lambda/logsvc-dev-api|2024/01/01/[$LATEST]aaa", "--yes"])
    assert result.exit_code == 0 and "Deleted 1 log stream" in result.output
    result = runner.invoke(cli, ["logs", "--delete", "/aws/lambda/elsewhere|x", "--yes"])
    assert result.exit_code != 0 and "does not belong" in result.output


def test_cli_logs_unsupported_provider(make_project, monkeypatch):
    from py_serverless_kit.cli.main import cli
    from py_serverless_kit.core.describe import build_record

    project = make_project(CONFIG.replace("aws", "cloudflare"))
    project.work_dir.mkdir(parents=True)
    (project.work_dir / "deployment.json").write_text(json.dumps(build_record(project)), "utf-8")
    monkeypatch.chdir(project.root)
    result = CliRunner().invoke(cli, ["logs"])
    assert result.exit_code != 0 and "can't read" in result.output
