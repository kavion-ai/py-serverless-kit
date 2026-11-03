"""Read, list and delete the logs of a deployment, whatever cloud it runs on.

One interface (:class:`LogBackend`) over:

* **on-premises** - the host's log buffer (``/__pskit/logs``); ``seq`` cursors;
* **AWS** - CloudWatch Logs groups ``/aws/lambda/<function>`` through ``boto3``
  (``pip install py-serverless-kit[aws]``); streams can be deleted, the log group
  itself never is (Terraform owns it);
* **GCP** - Cloud Logging through ``google-cloud-logging`` (read only);
* **Azure** - Log Analytics through ``azure-monitor-query`` + ``azure-identity``
  when the deployment exposes a workspace id output (read only);
* anything else - ``supported: False`` with the function's console link.

Cloud backends use ``mode == "time"``: ``since`` is a millisecond timestamp
(``0`` = the last 15 minutes) and ``next`` is the last event's timestamp + 1.
``seq`` is still strictly increasing (``ms * 1000 + n``) so tails can de-duplicate.
Entries share the on-prem shape: ``seq, ts, level, source, function, request_id,
message, fields``. SDK calls use the default credential chain of this machine.
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

LEVELS = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}
WINDOW_MS = 15 * 60 * 1000
HOST_STREAM = "__host__"
MAX_DELETE = 1000
_NOT_DEPLOYED = ("local", "not deployed", "removed")


class LogError(Exception):
    """Logs could not be read or deleted (credentials, network, unsupported)."""


def _now_ms() -> int:
    return int(time.time() * 1000)


def _iso_ms(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat(timespec="milliseconds")


def _level(text: Any) -> str:
    upper = str(text or "INFO").upper()
    if upper == "WARN":
        upper = "WARNING"
    if upper in ("FATAL",):
        upper = "CRITICAL"
    return upper if upper in LEVELS else "INFO"


def _level_ok(entry: Dict[str, Any], level: Optional[str]) -> bool:
    if not level:
        return True
    return LEVELS.get(entry.get("level", "INFO"), 20) >= LEVELS.get(_level(level), 0)


def _text_ok(entry: Dict[str, Any], q: Optional[str]) -> bool:
    return not q or q.lower() in str(entry.get("message", "")).lower()


def _number(entries: List[Dict[str, Any]]) -> None:
    """Give time-ordered entries (``_ms`` set) a strictly increasing ``seq``."""
    last_ms, n = None, 0
    for entry in entries:
        ms = int(entry.pop("_ms"))
        n = n + 1 if ms == last_ms else 0
        last_ms = ms
        entry["seq"] = ms * 1000 + min(n, 999)


def parse_line(message: str) -> Dict[str, Any]:
    """Split one log line into ``level / source / message / request_id / fields``.

    Understands pskit's JSON lines (``runtime/log.py``), the AWS Lambda Python
    format (``[LEVEL]\\t<ts>\\t<request id>\\t<message>``) and the platform
    ``START`` / ``END`` / ``REPORT`` lines.
    """
    text = (message or "").rstrip("\r\n")
    stripped = text.strip()
    out: Dict[str, Any] = {"level": "INFO", "source": "function", "message": text, "request_id": None, "fields": {}}
    if stripped.startswith("{"):
        try:
            payload = json.loads(stripped)
        except ValueError:
            payload = None
        if isinstance(payload, dict) and ("message" in payload or "msg" in payload):
            out["level"] = _level(payload.pop("level", None) or payload.pop("levelname", None))
            out["message"] = str(payload.pop("message", payload.pop("msg", "")))
            out["request_id"] = payload.pop("request_id", None) or payload.pop("aws_request_id", None)
            payload.pop("ts", None)
            if payload.get("exception"):
                out["message"] += "\n" + str(payload.pop("exception"))
            out["fields"] = payload
            return out
    match = re.match(r"^\[(\w+)\]\t(\S+)\t(\S+)\t(.*)$", text, re.S)
    if match:
        out.update(level=_level(match.group(1)), request_id=match.group(3), message=match.group(4))
        return out
    platform = re.match(r"^(START|END|REPORT|INIT_START|INIT_REPORT)\b", stripped)
    if platform:
        out["source"] = "invocation"
        rid = re.search(r"RequestId:\s*(\S+)", stripped)
        out["request_id"] = rid.group(1) if rid else None
        if "Status: error" in stripped or "Status: timeout" in stripped:
            out["level"] = "ERROR"
        out["message"] = stripped
        return out
    if stripped.startswith("Traceback") or re.match(r"^\w*(Error|Exception)\b", stripped):
        out["level"] = "ERROR"
    return out


# ---------------------------------------------------------------------- base


class LogBackend:
    supported: bool = True
    reason: str = ""
    can_delete: bool = False
    mode: str = "time"
    console: Optional[str] = None

    def __init__(self, record: Dict[str, Any]) -> None:
        self.record = record
        self.console = self.console or _first_console(record)

    def functions(self) -> List[Dict[str, Any]]:
        return [f for f in self.record.get("functions") or [] if isinstance(f, dict) and f.get("name")]

    def _function(self, name: str) -> Dict[str, Any]:
        for fn in self.functions():
            if fn.get("name") == name:
                return fn
        known = ", ".join(sorted(str(f.get("name")) for f in self.functions())) or "<none>"
        raise KeyError(f"unknown function {name!r}; known: {known}")

    def info(self) -> Dict[str, Any]:
        return {
            "supported": self.supported,
            "reason": self.reason,
            "mode": self.mode,
            "can_delete": self.can_delete,
            "console": self.console,
        }

    def query(
        self,
        since: int = 0,
        limit: int = 200,
        level: Optional[str] = None,
        function: Optional[str] = None,
        q: Optional[str] = None,
        source: Optional[str] = None,
    ) -> Dict[str, Any]:
        return {**self.info(), "entries": [], "next": 0}

    def streams(self, function: Optional[str] = None) -> Dict[str, Any]:
        return {**self.info(), "items": []}

    def delete(
        self, ids: Optional[List[str]] = None, function: Optional[str] = None, all: bool = False
    ) -> Dict[str, Any]:  # noqa: A002
        raise LogError(self.reason or "deleting logs is not supported for this deployment")


class UnsupportedLogs(LogBackend):
    supported = False

    def __init__(self, record: Dict[str, Any], reason: str) -> None:
        super().__init__(record)
        self.reason = reason


def _first_console(record: Dict[str, Any]) -> Optional[str]:
    for fn in record.get("functions") or []:
        if isinstance(fn, dict) and fn.get("console"):
            return str(fn["console"])
    return None


# ---------------------------------------------------------------------- on-prem


class OnPremLogs(LogBackend):
    mode = "seq"
    can_delete = True

    def __init__(self, record: Dict[str, Any], control: Any, root: Optional[Path] = None) -> None:
        super().__init__(record)
        self.control = control
        self.root = root
        self.console = None

    def _nomad_logs(
        self,
        since: int,
        limit: int,
        level: Optional[str],
        function: Optional[str],
        q: Optional[str],
        source: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        """Nomad keeps a log buffer on every server. Read them all, unless this client has no SSH login
        (a host on this machine) or the stage was not deployed to a Nomad cluster."""
        if self.root is None or not getattr(self.control, "ssh", None):
            return None
        from .onprem_cluster import ClusterError, get_cluster, logs_feed
        from .onprem_control import deployed_host

        deployed = deployed_host(self.root, str(self.record.get("stage") or ""), self.record) or {}
        name = str(deployed.get("cluster") or "")
        if not name:
            return None
        try:
            cluster = get_cluster(self.root, name)
        except ClusterError:
            return None
        if str(cluster.get("orchestrator") or "") != "nomad":
            return None
        spec = deployed.get("spec") if isinstance(deployed.get("spec"), dict) else {}
        port = int((spec or {}).get("port") or 8080)
        token = str((spec or {}).get("admin_token") or "")
        master = str(cluster.get("master") or "")
        nodes = list((cluster.get("nodes") or {}).keys())
        chosen = getattr(self.control, "server", None)
        servers = [str(chosen)] if chosen and chosen != master and chosen in nodes else nodes
        return logs_feed(
            self.root, name, servers, master=master, port=port, token=token, since=since, limit=limit,
            level=level, function=function, q=q, source=source,
        )

    def query(
        self,
        since: int = 0,
        limit: int = 200,
        level: Optional[str] = None,
        function: Optional[str] = None,
        q: Optional[str] = None,
        source: Optional[str] = None,
    ) -> Dict[str, Any]:
        merged = self._nomad_logs(since, limit, level, function, q, source)
        if merged is None:
            result = dict(
                self.control.logs(since=since, limit=limit, level=level, function=function, q=q, source=source) or {}
            )
        else:
            result = dict(merged)
        result.setdefault("entries", [])
        result.setdefault("next", 0)
        result.update(self.info())
        return result

    def streams(self, function: Optional[str] = None) -> Dict[str, Any]:
        items = []
        for item in (self.control.log_streams() or {}).get("items") or []:
            name = item.get("function")
            if function and name != function:
                continue
            items.append(
                {
                    "id": name or HOST_STREAM,
                    "function": name,
                    "name": name or "host",
                    "first": item.get("first"),
                    "last": item.get("last"),
                    "count": item.get("count"),
                }
            )
        return {**self.info(), "items": items}

    def delete(
        self, ids: Optional[List[str]] = None, function: Optional[str] = None, all: bool = False
    ) -> Dict[str, Any]:  # noqa: A002
        if all:
            return {"deleted": int((self.control.clear_logs() or {}).get("deleted") or 0), "errors": []}
        targets = list(ids or []) or ([function] if function else [])
        if not targets:
            raise ValueError("pass ids, function or all")
        deleted = 0
        for target in dict.fromkeys(targets):
            deleted += int((self.control.clear_logs(str(target)) or {}).get("deleted") or 0)
        return {"deleted": deleted, "errors": []}


# ---------------------------------------------------------------------- AWS


class AwsLogs(LogBackend):
    """CloudWatch Logs: one group per Lambda function, streams per container."""

    can_delete = True

    def __init__(self, record: Dict[str, Any], client: Any = None) -> None:
        super().__init__(record)
        self._client = client

    @property
    def client(self) -> Any:
        if self._client is None:
            try:
                import boto3  # type: ignore[import-not-found,import-untyped,unused-ignore]
            except ImportError:
                raise LogError("reading CloudWatch Logs needs boto3: pip install 'py-serverless-kit[aws]'") from None
            self._client = boto3.client("logs", region_name=self.record.get("region") or None)
        return self._client

    @staticmethod
    def group_of(fn: Dict[str, Any]) -> str:
        name = fn.get("resource_name") or str(fn.get("id") or fn.get("name"))
        return f"/aws/lambda/{name}"

    def _groups(self, function: Optional[str]) -> List[Tuple[str, str]]:
        fns = [self._function(function)] if function else self.functions()
        return [(str(fn["name"]), self.group_of(fn)) for fn in fns]

    def _call(self, method: str, kwargs: Dict[str, Any]) -> Any:
        """Call a CloudWatch Logs API; a missing log group (no invocation yet) reads as empty."""
        try:
            return getattr(self.client, method)(**kwargs)
        except LogError:
            raise
        except Exception as exc:  # noqa: BLE001 - botocore errors: credentials, network, permissions
            if type(exc).__name__ == "ResourceNotFoundException" or _aws_code(exc) == "ResourceNotFoundException":
                return None
            raise LogError(f"CloudWatch Logs: {exc}") from exc

    def query(
        self,
        since: int = 0,
        limit: int = 200,
        level: Optional[str] = None,
        function: Optional[str] = None,
        q: Optional[str] = None,
        source: Optional[str] = None,
    ) -> Dict[str, Any]:
        limit = max(1, min(int(limit or 200), 1000))
        start = int(since) if since and since > 0 else _now_ms() - WINDOW_MS
        raw: List[Dict[str, Any]] = []
        for name, group in self._groups(function):
            kwargs: Dict[str, Any] = {"logGroupName": group, "startTime": start, "limit": min(limit, 10000)}
            if q:
                kwargs["filterPattern"] = json.dumps(q)
            page = self._call("filter_log_events", kwargs) or {}
            for event in page.get("events") or []:
                parsed = parse_line(str(event.get("message") or ""))
                ms = int(event.get("timestamp") or 0)
                entry = {
                    "_ms": ms,
                    "ts": _iso_ms(ms),
                    "level": parsed["level"],
                    "source": parsed["source"],
                    "function": name,
                    "request_id": parsed["request_id"],
                    "message": parsed["message"],
                    "fields": dict(parsed["fields"], stream=event.get("logStreamName")),
                }
                if _level_ok(entry, level) and (not source or entry["source"] == source):
                    raw.append(entry)
        raw.sort(key=lambda e: e["_ms"])
        raw = raw[:limit]
        last = raw[-1]["_ms"] if raw else None
        _number(raw)
        next_ms = last + 1 if last is not None else max(start, int(since or 0))
        return {**self.info(), "entries": raw, "next": next_ms}

    def _all_streams(self, group: str, cap: int = MAX_DELETE) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        token = None
        while len(out) < cap:
            kwargs: Dict[str, Any] = {"logGroupName": group, "orderBy": "LastEventTime", "descending": True}
            if token:
                kwargs["nextToken"] = token
            page = self._call("describe_log_streams", kwargs) or {}
            out.extend(page.get("logStreams") or [])
            token = page.get("nextToken")
            if not token:
                break
        return out[:cap]

    def streams(self, function: Optional[str] = None) -> Dict[str, Any]:
        items = []
        for name, group in self._groups(function):
            for stream in self._all_streams(group, cap=50):
                first, last = stream.get("firstEventTimestamp"), stream.get("lastEventTimestamp")
                items.append(
                    {
                        "id": f"{group}|{stream.get('logStreamName')}",
                        "function": name,
                        "name": stream.get("logStreamName"),
                        "group": group,
                        "first": _iso_ms(int(first)) if first else None,
                        "last": _iso_ms(int(last)) if last else None,
                        "bytes": stream.get("storedBytes"),
                    }
                )
        items.sort(key=lambda i: str(i.get("last") or ""), reverse=True)
        return {**self.info(), "items": items}

    def delete(
        self, ids: Optional[List[str]] = None, function: Optional[str] = None, all: bool = False
    ) -> Dict[str, Any]:  # noqa: A002
        groups = dict((g, n) for n, g in self._groups(None))
        targets: List[Tuple[str, str]] = []
        if all or (function and not ids):
            for _name, group in self._groups(None if all else function):
                targets.extend((group, str(s.get("logStreamName"))) for s in self._all_streams(group))
        else:
            for item in ids or []:
                group, sep, stream = str(item).partition("|")
                if not sep or not stream:
                    raise ValueError(f"invalid log stream id {item!r}")
                if group not in groups:
                    raise ValueError(f"log group {group!r} does not belong to this deployment")
                targets.append((group, stream))
        if not targets and not (all or function):
            raise ValueError("pass ids, function or all")
        deleted, errors = 0, []
        for group, stream in targets[:MAX_DELETE]:
            try:
                self.client.delete_log_stream(logGroupName=group, logStreamName=stream)
                deleted += 1
            except Exception as exc:  # noqa: BLE001 - report per stream, keep going
                if _aws_code(exc) == "ResourceNotFoundException":
                    continue
                errors.append(f"{stream}: {exc}")
        return {"deleted": deleted, "errors": errors}


def _aws_code(exc: Exception) -> str:
    response = getattr(exc, "response", None)
    if isinstance(response, dict):
        return str((response.get("Error") or {}).get("Code") or "")
    return ""


# ---------------------------------------------------------------------- GCP


_GCP_SEVERITY = {
    "DEFAULT": "INFO",
    "DEBUG": "DEBUG",
    "INFO": "INFO",
    "NOTICE": "INFO",
    "WARNING": "WARNING",
    "ERROR": "ERROR",
    "CRITICAL": "CRITICAL",
    "ALERT": "CRITICAL",
    "EMERGENCY": "CRITICAL",
}


class GcpLogs(LogBackend):
    """Cloud Logging entries of Cloud Functions (gen2 runs on Cloud Run)."""

    reason = "Cloud Logging entries can't be deleted one by one; set a retention on the log bucket instead"

    def __init__(self, record: Dict[str, Any], client: Any = None) -> None:
        super().__init__(record)
        self._client = client

    def project(self) -> Optional[str]:
        import os

        for fn in self.functions():
            match = re.match(r"^projects/([^/]+)/", str(fn.get("id") or ""))
            if match:
                return match.group(1)
        found = re.search(r"[?&]project=([^&]+)", str(self.console or ""))
        if found:
            return found.group(1)
        return os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCLOUD_PROJECT")

    @property
    def client(self) -> Any:
        if self._client is None:
            try:
                from google.cloud import logging as gcl  # type: ignore[import-not-found,import-untyped,unused-ignore]
            except ImportError:
                raise LogError(
                    "reading Cloud Logging needs google-cloud-logging: pip install google-cloud-logging"
                ) from None
            self._client = gcl.Client(project=self.project())
        return self._client

    @staticmethod
    def names_of(fn: Dict[str, Any]) -> List[str]:
        names = {str(fn.get("resource_name") or fn.get("name"))}
        for ident in [fn.get("id"), *(fn.get("extra") or [])]:
            if ident:
                names.add(str(ident).rstrip("/").rsplit("/", 1)[-1])
        return sorted(n for n in names if n and n != "None")

    def _filter(
        self, start_ms: int, function: Optional[str], level: Optional[str], q: Optional[str]
    ) -> Tuple[str, Dict[str, str]]:
        fns = [self._function(function)] if function else self.functions()
        owner: Dict[str, str] = {}
        for fn in fns:
            for name in self.names_of(fn):
                owner[name.lower()] = str(fn["name"])
        quoted = " OR ".join(json.dumps(n) for n in sorted(owner)) or '""'
        parts = [
            f'timestamp>="{_iso_ms(start_ms)}"',
            f'((resource.type="cloud_run_revision" AND resource.labels.service_name=({quoted})) OR '
            f'(resource.type="cloud_function" AND resource.labels.function_name=({quoted})))',
        ]
        if level:
            parts.append(f"severity>={_level(level)}")
        if q:
            parts.append(json.dumps(q))
        return " AND ".join(parts), owner

    def query(
        self,
        since: int = 0,
        limit: int = 200,
        level: Optional[str] = None,
        function: Optional[str] = None,
        q: Optional[str] = None,
        source: Optional[str] = None,
    ) -> Dict[str, Any]:
        limit = max(1, min(int(limit or 200), 1000))
        start = int(since) if since and since > 0 else _now_ms() - WINDOW_MS
        flt, owner = self._filter(start, function, level, q)
        try:
            found = list(self.client.list_entries(filter_=flt, order_by="timestamp asc", max_results=limit))
        except LogError:
            raise
        except Exception as exc:  # noqa: BLE001 - google-api-core errors
            raise LogError(f"Cloud Logging: {exc}") from exc
        entries: List[Dict[str, Any]] = []
        for item in found:
            stamp = getattr(item, "timestamp", None)
            ms = int(stamp.timestamp() * 1000) if isinstance(stamp, datetime) else start
            labels = dict(getattr(getattr(item, "resource", None), "labels", None) or {})
            service = str(labels.get("service_name") or labels.get("function_name") or "").lower()
            payload = getattr(item, "payload", None)
            if isinstance(payload, dict):
                parsed = parse_line(json.dumps(payload, default=str))
            else:
                parsed = parse_line(str(payload or ""))
            severity = str(getattr(item, "severity", "") or "").upper()
            entry = {
                "_ms": ms,
                "ts": _iso_ms(ms),
                "level": _GCP_SEVERITY.get(severity, parsed["level"]) if severity else parsed["level"],
                "source": parsed["source"],
                "function": owner.get(service, service or None),
                "request_id": parsed["request_id"] or (getattr(item, "labels", None) or {}).get("execution_id"),
                "message": parsed["message"],
                "fields": parsed["fields"],
            }
            if not source or entry["source"] == source:
                entries.append(entry)
        entries.sort(key=lambda e: e["_ms"])
        last = entries[-1]["_ms"] if entries else None
        _number(entries)
        return {**self.info(), "entries": entries, "next": last + 1 if last is not None else start}

    def streams(self, function: Optional[str] = None) -> Dict[str, Any]:
        fns = [self._function(function)] if function else self.functions()
        items = [
            {
                "id": str(fn["name"]),
                "function": fn["name"],
                "name": ", ".join(self.names_of(fn)),
                "first": None,
                "last": None,
            }
            for fn in fns
        ]
        return {**self.info(), "items": items}


# ---------------------------------------------------------------------- Azure

_AZURE_WORKSPACE_OUTPUTS = ("log_analytics_workspace_id", "logs_workspace_id", "workspace_id")
_AZURE_SEVERITY = {0: "DEBUG", 1: "INFO", 2: "WARNING", 3: "ERROR", 4: "CRITICAL"}


def azure_workspace(record: Dict[str, Any]) -> Optional[str]:
    outputs = record.get("outputs") or {}
    for key in _AZURE_WORKSPACE_OUTPUTS:
        value = outputs.get(key)
        if isinstance(value, dict):
            value = value.get("value")
        if value:
            return str(value)
    return None


class AzureLogs(LogBackend):
    """Function App traces (``AppTraces``) in the Log Analytics workspace."""

    reason = "Log Analytics data can't be deleted from pskit; it expires with the workspace retention"

    def __init__(self, record: Dict[str, Any], workspace: str, client: Any = None) -> None:
        super().__init__(record)
        self.workspace = workspace
        self._client = client

    @property
    def client(self) -> Any:
        if self._client is None:
            try:
                from azure.identity import DefaultAzureCredential  # type: ignore[import-not-found,import-untyped,unused-ignore]
                from azure.monitor.query import LogsQueryClient  # type: ignore[import-not-found,import-untyped,unused-ignore]
            except ImportError:
                raise LogError("reading Azure logs needs: pip install azure-monitor-query azure-identity") from None
            self._client = LogsQueryClient(DefaultAzureCredential())
        return self._client

    def query(
        self,
        since: int = 0,
        limit: int = 200,
        level: Optional[str] = None,
        function: Optional[str] = None,
        q: Optional[str] = None,
        source: Optional[str] = None,
    ) -> Dict[str, Any]:
        limit = max(1, min(int(limit or 200), 1000))
        start = int(since) if since and since > 0 else _now_ms() - WINDOW_MS
        fns = [self._function(function)] if function else self.functions()
        prefixes = {re.sub(r"\W", "_", str(fn["name"])): str(fn["name"]) for fn in fns}
        kql = [f"AppTraces | where TimeGenerated >= datetime({_iso_ms(start)})"]
        if prefixes:
            kql.append("| where " + " or ".join(f"OperationName startswith {json.dumps(p + '_')}" for p in prefixes))
        if level:
            floor = {"DEBUG": 0, "INFO": 1, "WARNING": 2, "ERROR": 3, "CRITICAL": 4}[_level(level)]
            kql.append(f"| where SeverityLevel >= {floor}")
        if q:
            kql.append(f"| where Message contains {json.dumps(q)}")
        kql.append(
            f"| project TimeGenerated, Message, SeverityLevel, OperationName, OperationId | order by TimeGenerated asc | take {limit}"
        )
        try:
            response = self.client.query_workspace(self.workspace, " ".join(kql), timespan=timedelta(days=30))
        except LogError:
            raise
        except Exception as exc:  # noqa: BLE001 - azure-core errors
            raise LogError(f"Azure Log Analytics: {exc}") from exc
        entries: List[Dict[str, Any]] = []
        for table in getattr(response, "tables", None) or []:
            columns = [getattr(c, "name", c) for c in getattr(table, "columns", [])]
            for row in getattr(table, "rows", []):
                data = dict(zip(columns, row))
                stamp = data.get("TimeGenerated")
                ms = int(stamp.timestamp() * 1000) if isinstance(stamp, datetime) else start
                op = str(data.get("OperationName") or "")
                fn_name = next((n for p, n in prefixes.items() if op.startswith(p + "_")), op or None)
                parsed = parse_line(str(data.get("Message") or ""))
                entries.append(
                    {
                        "_ms": ms,
                        "ts": _iso_ms(ms),
                        "level": _AZURE_SEVERITY.get(int(data.get("SeverityLevel") or 1), parsed["level"]),
                        "source": parsed["source"],
                        "function": fn_name,
                        "request_id": data.get("OperationId"),
                        "message": parsed["message"],
                        "fields": parsed["fields"],
                    }
                )
        entries.sort(key=lambda e: e["_ms"])
        last = entries[-1]["_ms"] if entries else None
        _number(entries)
        return {**self.info(), "entries": entries, "next": last + 1 if last is not None else start}

    def streams(self, function: Optional[str] = None) -> Dict[str, Any]:
        fns = [self._function(function)] if function else self.functions()
        items = [
            {"id": str(fn["name"]), "function": fn["name"], "name": fn["name"], "first": None, "last": None}
            for fn in fns
        ]
        return {**self.info(), "items": items}


# ---------------------------------------------------------------------- factory


def _installed(module: str) -> bool:
    import importlib.util

    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        return False


def log_backend(record: Dict[str, Any], root: Path, server: Optional[str] = None) -> LogBackend:
    """Pick the log backend for one deployment record (``deployment.json``); ``server``: an on-prem saved server."""
    provider = str(record.get("provider") or "")
    if provider == "onprem":
        from .onprem_control import control_for

        control = control_for(record, root, server)
        if control is None:
            return UnsupportedLogs(record, "the on-premises host address is unknown; run `pskit deploy` first")
        return OnPremLogs(record, control, root)
    if record.get("status") in _NOT_DEPLOYED:
        return UnsupportedLogs(record, "not deployed yet; run `pskit deploy` to read its logs")
    console_hint = " Open the function's console link instead."
    if provider == "aws":
        if not _installed("boto3"):
            return UnsupportedLogs(
                record, "reading CloudWatch Logs needs boto3: pip install 'py-serverless-kit[aws]'." + console_hint
            )
        return AwsLogs(record)
    if provider == "gcp":
        if not _installed("google.cloud.logging"):
            return UnsupportedLogs(
                record,
                "reading Cloud Logging needs google-cloud-logging: pip install google-cloud-logging." + console_hint,
            )
        return GcpLogs(record)
    if provider == "azure":
        workspace = azure_workspace(record)
        if not workspace:
            return UnsupportedLogs(
                record,
                "Azure logs are in Application Insights. Add a Terraform output `log_analytics_workspace_id` "
                "(provider.terraform.extra) to read them here, or open the function's console link.",
            )
        if not (_installed("azure.monitor.query") and _installed("azure.identity")):
            return UnsupportedLogs(record, "reading Azure logs needs: pip install azure-monitor-query azure-identity.")
        return AzureLogs(record, workspace)
    name = record.get("provider_display") or provider or "this provider"
    return UnsupportedLogs(record, f"pskit can't read {name} logs yet.{console_hint}")


__all__ = [
    "AwsLogs",
    "AzureLogs",
    "GcpLogs",
    "LogBackend",
    "LogError",
    "OnPremLogs",
    "UnsupportedLogs",
    "log_backend",
    "parse_line",
]
