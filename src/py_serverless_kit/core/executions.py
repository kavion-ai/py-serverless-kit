"""List, inspect, start and cancel workflow executions of a deployment.

One interface over every engine pskit deploys:

* **on-premises** - the host's execution store (``/__pskit/executions``);
* **AWS Step Functions** (native) - ``boto3`` (``pip install py-serverless-kit[aws]``);
* **Google Cloud Workflows** (native) - ``google-cloud-workflows`` (``[gcp]``);
* **embedded engine on a cloud function** - start only: the run is synchronous
  and its ``execution_id`` comes back in the response, but no history is kept.

Records use the shapes documented in :mod:`py_serverless_kit.runtime.executions`.
Cloud SDK calls use the default credential chain of the machine running pskit.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .onprem_control import HostControl, HostUnavailable, control_for

EXECUTION_STATUSES = ("RUNNING", "SUCCEEDED", "FAILED", "TIMED_OUT", "CANCELLED", "ABORTED")


class ExecutionError(Exception):
    pass


def _iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat(timespec="milliseconds")
    return str(value)


def _duration(started: Optional[datetime], stopped: Optional[datetime]) -> Optional[float]:
    if not started or not stopped:
        return None
    return round((stopped - started).total_seconds() * 1000, 2)


def _loads(text: Any) -> Any:
    if text is None or text == "":
        return None
    if not isinstance(text, str):
        return text
    try:
        return json.loads(text)
    except ValueError:
        return text


def _check_status(status: Optional[str]) -> Optional[str]:
    if not status:
        return None
    upper = status.upper()
    if upper not in EXECUTION_STATUSES:
        raise ValueError(f"status must be one of {', '.join(EXECUTION_STATUSES)}")
    return upper


class ExecutionBackend:
    supported: bool = True
    reason: str = ""
    can_start: bool = True  # start() works even where listing is not supported

    def __init__(self, record: Dict[str, Any]) -> None:
        self.record = record

    def workflows(self) -> Dict[str, Dict[str, Any]]:
        return {w["name"]: w for w in self.record.get("workflows") or []}

    def _workflow(self, name: str) -> Dict[str, Any]:
        found = self.workflows().get(name)
        if found is None:
            known = ", ".join(sorted(self.workflows())) or "<none>"
            raise KeyError(f"unknown workflow {name!r}; known: {known}")
        return found

    def list(
        self,
        workflow: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
        token: Optional[str] = None,
    ) -> Dict[str, Any]:
        return {"items": [], "total": 0, "next_token": None, "supported": self.supported, "reason": self.reason}

    def get(self, execution_id: str, workflow: Optional[str] = None) -> Dict[str, Any]:
        raise ExecutionError(self.reason or "execution details are not available for this deployment")

    def start(self, workflow: str, data: Any, wait: bool = False) -> Dict[str, Any]:
        raise ExecutionError(self.reason or "workflows cannot be started for this deployment")

    def cancel(self, execution_id: str, workflow: Optional[str] = None) -> Dict[str, Any]:
        raise ExecutionError(self.reason or "executions cannot be cancelled for this deployment")


class UnsupportedBackend(ExecutionBackend):
    supported = False
    can_start = False

    def __init__(self, record: Dict[str, Any], reason: str) -> None:
        super().__init__(record)
        self.reason = reason


# ---------------------------------------------------------------------- on-prem


class OnPremBackend(ExecutionBackend):
    def __init__(self, record: Dict[str, Any], control: HostControl) -> None:
        super().__init__(record)
        self.control = control

    def list(
        self,
        workflow: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
        token: Optional[str] = None,
    ) -> Dict[str, Any]:
        if workflow:
            self._workflow(workflow)
        listed = self.control.executions(workflow=workflow, status=_check_status(status), limit=limit, offset=offset)
        total = listed.get("total")
        items = listed.get("items") or []
        more = isinstance(total, int) and offset + len(items) < total
        return {
            "items": items,
            "total": total,
            "next_token": str(offset + len(items)) if more else None,
            "supported": True,
            "reason": "",
        }

    def get(self, execution_id: str, workflow: Optional[str] = None) -> Dict[str, Any]:
        return self.control.execution(execution_id)

    def start(self, workflow: str, data: Any, wait: bool = False) -> Dict[str, Any]:
        self._workflow(workflow)
        return self.control.start_workflow(workflow, data, wait=wait)

    def cancel(self, execution_id: str, workflow: Optional[str] = None) -> Dict[str, Any]:
        return self.control.cancel(execution_id)


# ---------------------------------------------------------------------- AWS Step Functions

_AWS_STATUS = {"PENDING_REDRIVE": "RUNNING"}


class AwsBackend(ExecutionBackend):
    """Step Functions through boto3. Execution ids are execution ARNs."""

    def __init__(self, record: Dict[str, Any], client: Any = None) -> None:
        super().__init__(record)
        self._client = client

    @property
    def client(self) -> Any:
        if self._client is None:
            try:
                import boto3  # type: ignore[import-not-found,import-untyped,unused-ignore]
            except ImportError:
                raise ExecutionError(
                    "listing Step Functions executions needs boto3: pip install 'py-serverless-kit[aws]'"
                ) from None
            self._client = boto3.client("stepfunctions", region_name=self.record.get("region") or None)
        return self._client

    def _arn(self, workflow: str) -> str:
        wf = self._workflow(workflow)
        if wf.get("engine") != "native":
            raise ExecutionError(f"workflow {workflow!r} runs on the embedded engine, not Step Functions")
        if not wf.get("id"):
            raise ExecutionError(f"workflow {workflow!r} has no state machine ARN yet; run `pskit deploy`")
        return str(wf["id"])

    def _console(self, arn: str) -> str:
        region = self.record.get("region") or "us-east-1"
        return f"https://{region}.console.aws.amazon.com/states/home?region={region}#/v2/executions/details/{arn}"

    def _summary(self, item: Dict[str, Any], workflow: str) -> Dict[str, Any]:
        started, stopped = item.get("startDate"), item.get("stopDate")
        arn = str(item.get("executionArn"))
        status = str(item.get("status") or "RUNNING")
        return {
            "execution_id": arn,
            "workflow": workflow,
            "status": _AWS_STATUS.get(status, status),
            "started_at": _iso(started),
            "stopped_at": _iso(stopped),
            "duration_ms": _duration(started, stopped),
            "current_state": None,
            "source": "aws",
            "console": self._console(arn),
        }

    def _native_workflows(self) -> List[str]:
        return sorted(n for n, w in self.workflows().items() if w.get("engine") == "native" and w.get("id"))

    def list(
        self,
        workflow: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
        token: Optional[str] = None,
    ) -> Dict[str, Any]:
        status = _check_status(status)
        aws_status = "ABORTED" if status == "CANCELLED" else status
        limit = max(1, min(int(limit or 20), 100))
        names = [workflow] if workflow else self._native_workflows()
        items: List[Dict[str, Any]] = []
        next_token = None
        for name in names:
            kwargs: Dict[str, Any] = {"stateMachineArn": self._arn(name), "maxResults": limit}
            if aws_status:
                kwargs["statusFilter"] = aws_status
            if token and workflow:
                kwargs["nextToken"] = token
            page = self.client.list_executions(**kwargs)
            items.extend(self._summary(item, name) for item in page.get("executions") or [])
            if workflow:
                next_token = page.get("nextToken")
        items.sort(key=lambda i: str(i.get("started_at") or ""), reverse=True)
        return {"items": items[:limit], "total": None, "next_token": next_token, "supported": True, "reason": ""}

    def _workflow_of(self, arn: str) -> str:
        machine = arn.replace(":execution:", ":stateMachine:").rsplit(":", 1)[0]
        for name, wf in self.workflows().items():
            if wf.get("id") == machine:
                return name
        return machine.rsplit(":", 1)[-1]

    def get(self, execution_id: str, workflow: Optional[str] = None) -> Dict[str, Any]:
        desc = self.client.describe_execution(executionArn=execution_id)
        record = self._summary(desc, workflow or self._workflow_of(execution_id))
        history, current = self._history(execution_id)
        record.update(
            input=_loads(desc.get("input")),
            output=_loads(desc.get("output")),
            error=desc.get("error"),
            cause=desc.get("cause"),
            history=history,
            current_state=current if record["status"] == "RUNNING" else None,
        )
        return record

    def _history(self, arn: str) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        events: List[Dict[str, Any]] = []
        token = None
        while len(events) < 1000:
            kwargs: Dict[str, Any] = {"executionArn": arn, "maxResults": 500, "reverseOrder": False}
            if token:
                kwargs["nextToken"] = token
            page = self.client.get_execution_history(**kwargs)
            events.extend(page.get("events") or [])
            token = page.get("nextToken")
            if not token:
                break
        history: List[Dict[str, Any]] = []
        current = None
        for ev in events:
            kind = str(ev.get("type") or "")
            entered = ev.get("stateEnteredEventDetails") or {}
            exited = ev.get("stateExitedEventDetails") or {}
            entry: Dict[str, Any] = {"ts": _iso(ev.get("timestamp")), "aws_type": kind}
            if kind.endswith("StateEntered"):
                current = entered.get("name")
                entry.update(state=current, type=kind[: -len("StateEntered")].lower() or "state", event="enter")
            elif kind.endswith("StateExited"):
                entry.update(
                    state=exited.get("name"), type=kind[: -len("StateExited")].lower() or "state", event="exit"
                )
            elif kind.endswith("Failed") or kind.endswith("TimedOut") or kind.endswith("Aborted"):
                details = next((v for k, v in ev.items() if k.endswith("EventDetails") and isinstance(v, dict)), {})
                entry.update(state=current, type="task", event="fail", error=details.get("error"))
            else:
                continue
            history.append(entry)
        return history, current

    def start(self, workflow: str, data: Any, wait: bool = False) -> Dict[str, Any]:
        arn = self._arn(workflow)
        started = self.client.start_execution(
            stateMachineArn=arn, name=uuid.uuid4().hex, input=json.dumps(data if data is not None else {})
        )
        execution_arn = str(started["executionArn"])
        return {
            "execution_id": execution_arn,
            "workflow": workflow,
            "status": "RUNNING",
            "started_at": _iso(started.get("startDate")),
            "source": "aws",
            "console": self._console(execution_arn),
        }

    def cancel(self, execution_id: str, workflow: Optional[str] = None) -> Dict[str, Any]:
        self.client.stop_execution(executionArn=execution_id, cause="cancelled with pskit")
        return self.get(execution_id, workflow)


# ---------------------------------------------------------------------- Google Cloud Workflows

_GCP_STATUS = {
    "ACTIVE": "RUNNING",
    "QUEUED": "RUNNING",
    "SUCCEEDED": "SUCCEEDED",
    "FAILED": "FAILED",
    "CANCELLED": "CANCELLED",
    "UNAVAILABLE": "FAILED",
}


class GcpBackend(ExecutionBackend):
    """Cloud Workflows executions API. Execution ids are full execution resource names."""

    def __init__(self, record: Dict[str, Any], client: Any = None) -> None:
        super().__init__(record)
        self._client = client

    @property
    def client(self) -> Any:
        if self._client is None:
            try:
                from google.cloud.workflows import executions_v1  # type: ignore[import-not-found,unused-ignore]
            except ImportError:
                raise ExecutionError(
                    "listing Cloud Workflows executions needs google-cloud-workflows: "
                    "pip install 'py-serverless-kit[gcp]'"
                ) from None
            self._client = executions_v1.ExecutionsClient()
        return self._client

    def _parent(self, workflow: str) -> str:
        wf = self._workflow(workflow)
        if wf.get("engine") != "native":
            raise ExecutionError(f"workflow {workflow!r} runs on the embedded engine, not Cloud Workflows")
        if not wf.get("id"):
            raise ExecutionError(f"workflow {workflow!r} has no Cloud Workflows id yet; run `pskit deploy`")
        return str(wf["id"])

    def _summary(self, ex: Any, workflow: str) -> Dict[str, Any]:
        state = getattr(getattr(ex, "state", None), "name", None) or str(getattr(ex, "state", "") or "")
        started, stopped = getattr(ex, "start_time", None), getattr(ex, "end_time", None)
        name = str(getattr(ex, "name", ""))
        console = None
        parts = name.split("/")
        if len(parts) >= 8:
            project, location, wf_name, exec_id = parts[1], parts[3], parts[5], parts[7]
            console = (
                f"https://console.cloud.google.com/workflows/workflow/{location}/{wf_name}/execution/{exec_id}"
                f"?project={project}"
            )
        current = None
        steps = getattr(getattr(ex, "status", None), "current_steps", None) or []
        if steps:
            current = getattr(steps[-1], "step", None)
        return {
            "execution_id": name,
            "workflow": workflow,
            "status": _GCP_STATUS.get(state.upper(), "RUNNING"),
            "started_at": _iso(started),
            "stopped_at": _iso(stopped),
            "duration_ms": _duration(started, stopped),
            "current_state": current,
            "source": "gcp",
            "console": console,
        }

    def _workflow_of(self, name: str) -> str:
        parent = name.split("/executions/")[0]
        for wf_name, wf in self.workflows().items():
            if wf.get("id") == parent:
                return wf_name
        return parent.rsplit("/", 1)[-1]

    def list(
        self,
        workflow: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
        token: Optional[str] = None,
    ) -> Dict[str, Any]:
        status = _check_status(status)
        limit = max(1, min(int(limit or 20), 100))
        names = (
            [workflow]
            if workflow
            else sorted(n for n, w in self.workflows().items() if w.get("engine") == "native" and w.get("id"))
        )
        items: List[Dict[str, Any]] = []
        next_token = None
        for name in names:
            request: Dict[str, Any] = {"parent": self._parent(name), "page_size": limit}
            if token and workflow:
                request["page_token"] = token
            pager = self.client.list_executions(request=request)
            page = next(iter(pager.pages), None)
            for ex in getattr(page, "executions", None) or []:
                summary = self._summary(ex, name)
                if not status or summary["status"] == status:
                    items.append(summary)
            if workflow and page is not None:
                next_token = getattr(page, "next_page_token", None) or None
        items.sort(key=lambda i: str(i.get("started_at") or ""), reverse=True)
        return {"items": items[:limit], "total": None, "next_token": next_token, "supported": True, "reason": ""}

    def get(self, execution_id: str, workflow: Optional[str] = None) -> Dict[str, Any]:
        ex = self.client.get_execution(request={"name": execution_id})
        record = self._summary(ex, workflow or self._workflow_of(execution_id))
        error = getattr(ex, "error", None)
        payload = getattr(error, "payload", None) if error else None
        record.update(
            input=_loads(getattr(ex, "argument", None)),
            output=_loads(getattr(ex, "result", None)),
            error="ExecutionFailed" if payload else None,
            cause=payload or None,
            history=[
                {"ts": None, "state": getattr(step, "step", None), "type": "step", "event": "enter"}
                for step in (getattr(getattr(ex, "status", None), "current_steps", None) or [])
            ],
        )
        return record

    def start(self, workflow: str, data: Any, wait: bool = False) -> Dict[str, Any]:
        parent = self._parent(workflow)
        ex = self.client.create_execution(
            request={"parent": parent, "execution": {"argument": json.dumps(data if data is not None else {})}}
        )
        return self._summary(ex, workflow)

    def cancel(self, execution_id: str, workflow: Optional[str] = None) -> Dict[str, Any]:
        ex = self.client.cancel_execution(request={"name": execution_id})
        return self._summary(ex, workflow or self._workflow_of(execution_id))


# ---------------------------------------------------------------------- embedded on a cloud function


class EmbeddedCloudBackend(ExecutionBackend):
    supported = False

    def __init__(self, record: Dict[str, Any]) -> None:
        super().__init__(record)
        self.reason = (
            f"embedded workflows on {record.get('provider_display') or record.get('provider')} run inside one "
            "function call and keep no execution history; each run returns its execution_id in the response. "
            "Use the on-prem provider or a native engine (AWS/GCP) for a browsable history."
        )

    def _url(self, workflow: str) -> str:
        wf = self._workflow(workflow)
        if wf.get("engine") == "native" and wf.get("url"):
            return str(wf["url"])  # e.g. the Azure Logic Apps HTTP trigger (callback URL)
        orchestrator = f"{workflow}-orchestrator"
        for fn in self.record.get("functions") or []:
            if fn.get("name") != orchestrator:
                continue
            for item in fn.get("urls") or []:
                if item.get("method") in ("POST", "ANY") and item.get("url"):
                    return str(item["url"])
            if fn.get("url"):
                return str(fn["url"]).rstrip("/") + f"/workflows/{workflow}"
        raise ExecutionError(f"workflow {workflow!r} has no HTTP URL; start it with invoke() instead")

    def start(self, workflow: str, data: Any, wait: bool = True) -> Dict[str, Any]:
        url = self._url(workflow)
        if not url.lower().startswith(("http://", "https://")):
            raise ExecutionError(f"unexpected orchestrator URL {url!r}")
        req = urllib.request.Request(  # noqa: S310 - scheme checked above
            url, data=json.dumps(data).encode("utf-8"), method="POST"
        )
        req.add_header("content-type", "application/json")
        failed = False
        try:
            with urllib.request.urlopen(req, timeout=900) as resp:  # noqa: S310
                body = json.loads(resp.read().decode("utf-8") or "null")
        except urllib.error.HTTPError as exc:
            failed = True
            try:
                body = json.loads(exc.read().decode("utf-8") or "null")
            except ValueError:
                raise ExecutionError(f"{url} answered HTTP {exc.code}") from None
        except (urllib.error.URLError, OSError) as exc:
            raise ExecutionError(f"could not reach {url}: {exc}") from None
        if self._workflow(workflow).get("engine") == "native":
            # A native engine behind an HTTP trigger answers with the workflow output itself.
            out = {"workflow": workflow, "status": "FAILED" if failed else "SUCCEEDED", "source": self.record.get("provider")}
            out["error" if failed else "output"] = body
            return out
        if not isinstance(body, dict):
            raise ExecutionError(f"unexpected response from {url}: {body!r}")
        body.setdefault("workflow", workflow)
        body.setdefault("source", "embedded")
        return body


def backend_for(record: Dict[str, Any], root: Path) -> ExecutionBackend:
    """Pick the execution backend for one deployment record (``deployment.json``)."""
    if not record.get("workflows"):
        return UnsupportedBackend(record, "this deployment has no workflows")
    if record.get("status") in ("local", "not deployed", "removed"):
        return UnsupportedBackend(record, "not deployed yet; run `pskit deploy` (or `pskit workflow run --local`)")
    provider = record.get("provider")
    if provider == "onprem":
        control = control_for(record, root)
        if control is None:
            return UnsupportedBackend(record, "the on-prem host address is unknown; run `pskit deploy`")
        return OnPremBackend(record, control)
    engines = {w.get("engine") for w in record.get("workflows") or []}
    if provider == "aws" and "native" in engines:
        return AwsBackend(record)
    if provider == "gcp" and "native" in engines:
        return GcpBackend(record)
    return EmbeddedCloudBackend(record)


__all__ = [
    "AwsBackend",
    "EmbeddedCloudBackend",
    "ExecutionBackend",
    "ExecutionError",
    "GcpBackend",
    "HostUnavailable",
    "OnPremBackend",
    "UnsupportedBackend",
    "backend_for",
]
