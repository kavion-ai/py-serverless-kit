"""Use an on-premises pskit host from any Python program (standard library only).

``pip install py-serverless-kit``, then::

    from py_serverless_kit.client import PskitClient

    client = PskitClient("http://10.0.0.5:8080", token="...")   # or PSKIT_HOST / PSKIT_ADMIN_TOKEN
    client = PskitClient.from_project(".")                      # the host this project deployed

    jobs = client.queue("jobs")                 # a resource key or a native queue name
    jobs.send({"order_id": 1}, attributes={"kind": "new"})
    page = jobs.peek(limit=20)                  # look without consuming
    for msg in jobs.receive(batch=10, visibility=60):
        print(msg.body); msg.ack()              # or msg.nack() to retry

    files = client.bucket("uploads")
    files.put("in/a.csv", b"a,b\\n"); files.get("in/a.csv"); files.list(prefix="in/"); files.delete("in/a.csv")
    client.topic("events").publish({"id": 1}, attributes={"type": "paid"})
    client.invoke("report", {"day": "2026-10-22"})

Everything goes through the host's ``/__pskit`` HTTP API, so only the host port has to be
reachable: the queue or bucket may use any driver (built-in folders, Redis, Kafka, SQS,
MinIO, ...) and may sit behind a firewall the host can pass. Errors raise
:class:`PskitClientError` quickly (``timeout`` seconds) with what to check.
"""

from __future__ import annotations

import json
import os
import socket
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Union

__all__ = ["Bucket", "Message", "Page", "PskitClient", "PskitClientError", "Queue", "Topic"]


class PskitClientError(RuntimeError):
    """A call to the host failed. ``status`` is the HTTP status (0 when the host was not reached)."""

    def __init__(self, message: str, status: int = 0) -> None:
        super().__init__(message)
        self.status = status


@dataclass
class Page:
    """One page of messages or objects. ``total`` is None when the backend cannot tell."""

    items: List[Dict[str, Any]]
    total: Optional[int]
    offset: int
    limit: int
    supported: bool = True
    note: str = ""

    @property
    def has_more(self) -> bool:
        return self.total is not None and self.offset + len(self.items) < self.total


@dataclass
class Message:
    """A leased message; settle it with :meth:`ack` (done) or :meth:`nack` (deliver again)."""

    id: str
    body: Any
    attributes: Dict[str, Any]
    receives: int
    receipt: str
    queue: Queue = field(repr=False)

    def json(self, default: Any = None) -> Any:
        try:
            return json.loads(self.body) if isinstance(self.body, str) else self.body
        except ValueError:
            return default

    def ack(self) -> None:
        self.queue.ack([self])

    def nack(self) -> None:
        self.queue.nack([self])


class PskitClient:
    def __init__(self, endpoint: Optional[str] = None, token: Optional[str] = None, timeout: float = 10.0) -> None:
        base = endpoint or os.environ.get("PSKIT_HOST") or os.environ.get("PSKIT_ENDPOINT") or ""
        if not base:
            raise PskitClientError("no host: pass PskitClient('http://host:8080') or set PSKIT_HOST")
        if not base.startswith(("http://", "https://")):
            base = "http://" + base
        self.endpoint = base.rstrip("/")
        self.token = token if token is not None else os.environ.get("PSKIT_ADMIN_TOKEN", "")
        self.timeout = timeout
        self._names: Optional[Dict[str, Dict[str, Any]]] = None

    @classmethod
    def from_project(
        cls, path: Union[str, Path] = ".", stage: Optional[str] = None, timeout: float = 10.0
    ) -> PskitClient:
        """The host a pskit project deployed (``provider: onprem``), with its admin token."""
        from .core.deployer import Deployer
        from .core.onprem_control import control_for
        from .core.project import Project

        project = Project.load(cwd=Path(path), provider="onprem", stage=stage)
        record = Deployer(project, echo=lambda _m: None).load_record()
        control = control_for(record or {}, project.root) if record else None
        if control is None:
            raise PskitClientError(f"{project.config.service} is not deployed on premises yet: run `pskit deploy`")
        return cls(control.base_url, control.token, timeout)

    # ------------------------------------------------------------------ transport
    def request(self, method: str, path: str, body: Any = None, *, raw: Optional[bytes] = None,
                query: Optional[Dict[str, Any]] = None, binary: bool = False) -> Any:
        url = self.endpoint + path
        params = {k: v for k, v in (query or {}).items() if v is not None and v != ""}
        if params:
            url += "?" + urllib.parse.urlencode(params)
        data = raw if raw is not None else (None if body is None else json.dumps(body).encode("utf-8"))
        req = urllib.request.Request(url, data=data, method=method)  # noqa: S310 - the caller's host
        if raw is None and data is not None:
            req.add_header("content-type", "application/json")
        if self.token:
            req.add_header("x-pskit-token", self.token)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # noqa: S310
                payload = resp.read()
        except urllib.error.HTTPError as exc:
            text = exc.read().decode("utf-8", "replace")
            try:
                text = json.loads(text).get("error") or json.loads(text).get("cause") or text
            except (ValueError, AttributeError):
                pass
            hint = " (set token= or PSKIT_ADMIN_TOKEN to the host's admin_token)" if exc.code == 401 else ""
            raise PskitClientError(f"{method} {path}: HTTP {exc.code}: {text}{hint}", exc.code) from None
        except (urllib.error.URLError, socket.timeout, OSError) as exc:
            reason = getattr(exc, "reason", exc)
            raise PskitClientError(
                f"the pskit host at {self.endpoint} is not reachable ({reason}). Check that it runs "
                "(`pskit info`), that its port is open from this machine (cloud firewall / security group), "
                "or reach it through an SSH tunnel: ssh -N -L 8080:127.0.0.1:<port> user@server"
            ) from None
        if binary:
            return payload
        return json.loads(payload.decode("utf-8")) if payload else None

    # ------------------------------------------------------------------ host
    def health(self) -> Dict[str, Any]:
        return dict(self.request("GET", "/__pskit/health"))

    def resources(self) -> List[Dict[str, Any]]:
        """Every ``resources:`` entry: key, type, native name, driver, depth (queues)."""
        return list(self.request("GET", "/__pskit/resources")["items"])

    def _resolve(self, name: str, kind: str) -> Dict[str, Any]:
        if self._names is None:
            try:
                self._names = {r["key"]: r for r in self.resources()}
            except PskitClientError:
                self._names = {}
        found = self._names.get(name) or next(
            (r for r in self._names.values() if r.get("name") == name and r.get("type") == kind), None
        )
        return found or {"key": None, "name": name, "type": kind}

    def queue(self, name: str) -> Queue:
        return Queue(self, self._resolve(name, "queue"))

    def bucket(self, name: str) -> Bucket:
        return Bucket(self, self._resolve(name, "storage"))

    def topic(self, name: str) -> Topic:
        return Topic(self, self._resolve(name, "topic"))

    def check(self, key: str) -> Dict[str, Any]:
        """Is resource ``key`` reachable from the host? (queue depth, bucket count, database connection)."""
        return dict(self.request("POST", f"/__pskit/resources/{_seg(key)}/check", {}))

    def invoke(self, function: str, data: Any = None) -> Any:
        out = self.request("POST", f"/__pskit/invoke/{_seg(function)}", data)
        return out.get("result") if isinstance(out, dict) and "result" in out else out

    def start_workflow(self, workflow: str, data: Any = None, wait: bool = False) -> Dict[str, Any]:
        return dict(self.request("POST", f"/__pskit/workflows/{_seg(workflow)}", data, query={"wait": "true" if wait else None}))

    def execution(self, execution_id: str) -> Dict[str, Any]:
        return dict(self.request("GET", f"/__pskit/executions/{_seg(execution_id)}"))

    def logs(self, function: Optional[str] = None, limit: int = 100) -> Dict[str, Any]:
        return dict(self.request("GET", "/__pskit/logs", query={"function": function, "limit": limit}))


class _Resource:
    def __init__(self, client: PskitClient, info: Dict[str, Any]) -> None:
        self.client = client
        self.key: Optional[str] = info.get("key")
        self.name: str = str(info.get("name"))
        self.driver: str = str(info.get("driver") or "")

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.name!r}, key={self.key!r}, driver={self.driver!r})"

    def _page(self, path: str, query: Dict[str, Any]) -> Page:
        out = self.client.request("GET", path, query=query)
        return Page(list(out.get("items") or []), out.get("total"), int(query.get("offset") or 0),
                    int(query.get("limit") or 0), bool(out.get("supported", True)), str(out.get("note") or ""))


class Queue(_Resource):
    def send(self, message: Any, attributes: Optional[Dict[str, Any]] = None) -> str:
        """Add one message (dicts and lists are sent as JSON). Returns its id."""
        out = self.client.request("POST", f"/__pskit/queues/{_seg(self.name)}", {"message": message, "attributes": attributes or {}})
        return str((out.get("queued") or [""])[0])

    def send_batch(self, messages: List[Any]) -> List[str]:
        out = self.client.request("POST", f"/__pskit/queues/{_seg(self.name)}", {"messages": list(messages)})
        return [str(i) for i in out.get("queued") or []]

    def depth(self) -> Optional[int]:
        depth = self.client.request("GET", f"/__pskit/queues/{_seg(self.name)}").get("depth")
        return depth if isinstance(depth, int) and depth >= 0 else None

    def peek(self, offset: int = 0, limit: int = 20) -> Page:
        """Waiting messages, oldest first, without consuming them."""
        query = {"offset": offset, "limit": limit}
        if self.key:
            return self._page(f"/__pskit/resources/{_seg(self.key)}/data", query)
        return self._page(f"/__pskit/queues/{_seg(self.name)}/peek", query)

    def receive(self, batch: int = 10, visibility: float = 60) -> List[Message]:
        """Lease up to ``batch`` messages (built-in queues): hidden for ``visibility`` seconds until settled.

        Don't receive from a queue a pskit trigger consumes: the two would share its messages.
        """
        out = self.client.request("POST", f"/__pskit/queues/{_seg(self.name)}/lease", {"batch": batch, "visibility": visibility})
        return [
            Message(str(m.get("id")), m.get("body"), dict(m.get("attributes") or {}), int(m.get("receives") or 1),
                    str(m.get("receipt")), self)
            for m in out.get("messages") or []
        ]

    def ack(self, messages: List[Message]) -> int:
        out = self.client.request("POST", f"/__pskit/queues/{_seg(self.name)}/ack", {"receipts": [m.receipt for m in messages]})
        return int(out.get("acked") or 0)

    def nack(self, messages: List[Message]) -> int:
        out = self.client.request("POST", f"/__pskit/queues/{_seg(self.name)}/nack", {"receipts": [m.receipt for m in messages]})
        return int(out.get("released") or 0)


class Topic(_Resource):
    def publish(self, message: Any, attributes: Optional[Dict[str, Any]] = None) -> str:
        out = self.client.request("POST", f"/__pskit/topics/{_seg(self.name)}", {"message": message, "attributes": attributes or {}})
        return str((out.get("published") or [""])[0])

    def peek(self, offset: int = 0, limit: int = 20) -> Page:
        if not self.key:
            raise PskitClientError(f"topic {self.name!r} is not a resource of this host")
        return self._page(f"/__pskit/resources/{_seg(self.key)}/data", {"offset": offset, "limit": limit})


class Bucket(_Resource):
    def put(self, key: str, data: Union[bytes, str]) -> None:
        raw = data.encode("utf-8") if isinstance(data, str) else bytes(data)
        self.client.request("PUT", f"/__pskit/storage/{_seg(self.name)}/{_path(key)}", raw=raw)

    def get(self, key: str) -> bytes:
        return bytes(self.client.request("GET", f"/__pskit/storage/{_seg(self.name)}/{_path(key)}", binary=True))

    def delete(self, key: str) -> bool:
        return bool(self.client.request("DELETE", f"/__pskit/storage/{_seg(self.name)}/{_path(key)}").get("deleted"))

    def list(self, prefix: str = "", offset: int = 0, limit: int = 100) -> Page:
        return self._page(f"/__pskit/storage/{_seg(self.name)}", {"prefix": prefix, "offset": offset, "limit": limit})

    def keys(self, prefix: str = "", page_size: int = 500) -> Iterator[str]:
        """Every key below ``prefix``, fetched page by page."""
        offset = 0
        while True:
            page = self.list(prefix, offset, page_size)
            for item in page.items:
                yield str(item["key"])
            if not page.has_more:
                return
            offset += len(page.items)


def _seg(text: str) -> str:
    return urllib.parse.quote(str(text), safe="")


def _path(key: str) -> str:
    return "/".join(urllib.parse.quote(p, safe="") for p in str(key).split("/") if p)
