"""On-premises host: one process for HTTP, schedules, queues, storage and topics.

Deploy writes ``pskit_host.json`` plus the function bundle. This module is
stdlib-only and is copied into that bundle. Backing services default to
directories created at startup. A ``directory`` binding in the manifest uses a
path you already have instead.

* ``POST /__pskit/queues/<name>`` publishes a message (JSON body, or ``{"messages": [...]}``).
* ``POST /__pskit/topics/<name>`` publishes. ``{"message": ..., "attributes": {...}}``
  sets attributes used by topic filters.
* ``GET /__pskit/storage/<bucket>[?prefix=&offset=&limit=]`` lists objects; ``GET .../<key>`` returns one.
* ``PUT`` / ``DELETE /__pskit/storage/<bucket>/<key>`` writes an object and emits
  ``created`` / ``deleted``. Dropping a file in the bucket directory does the same.
* ``POST /__pskit/invoke/<function>`` calls a function.
* ``POST /__pskit/workflows/<name>`` starts a workflow and answers ``202`` with its
  ``execution_id`` (``?wait=true`` waits and returns the result). With ``?entry=true`` the body is
  ``{"input": ..., "entry_result": ...}``: the first task's function already ran (another group's host).
* A workflow whose first state is a task also starts when that function runs on its own (HTTP, ``invoke()``,
  a schedule, a queue...): the run uses that call's result for the first state. ``options.start_on_entry: false``
  turns this off.
  ``GET /__pskit/executions[?workflow=&status=&limit=&offset=]``,
  ``GET /__pskit/executions/<id>`` and ``POST /__pskit/executions/<id>/cancel``
  inspect and control runs; records live under ``<data_dir>/executions``.
* ``GET /__pskit/logs?since=&limit=&level=&function=&q=&source=&before=`` returns
  captured logs (handler logging, print output, one entry per invocation, host
  notes). A web replica forwards that route to the main replica.
  ``GET /__pskit/logs/local`` is this replica's own buffer.
  ``GET /__pskit/logs/streams`` summarises them per function and
  ``DELETE /__pskit/logs[?function=]`` clears them. ``GET /__pskit/stats``
  returns per-function invocation counters.

* ``POST /__pskit/smtp/<resource>`` (JSON: a parsed mail, sent by the ``smtp`` on-prem service) runs every
  function with an ``smtp`` trigger on that resource; ``500`` when one fails, so the sender retries.

* ``POST /__pskit/queues/<name>/lease`` (``{"batch", "visibility"}``), ``.../ack`` and
  ``.../nack`` (``{"receipts": [...]}``) let a host elsewhere consume a built-in queue
  with at-least-once leases (the ``pskit_host`` driver).
* ``GET /__pskit/resources`` lists ``resources:`` with their backend and queue depth.
* AWS-compatible: ``POST /2015-03-31/functions/<name|ARN>/invocations`` is the Lambda Invoke API,
  and ``POST /`` with ``X-Amz-Target: AmazonSQS.*`` serves SendMessage(Batch), ReceiveMessage,
  DeleteMessage(Batch), ChangeMessageVisibility, GetQueueUrl, GetQueueAttributes, ListQueues,
  CreateQueue and PurgeQueue over the host's queues, so boto3 code only changes ``endpoint_url``.
  With an ``admin_token``, pass it as the AWS access key id.

Queue, storage and topic resources may carry a ``driver`` binding. ``directory``
moves that queue/bucket to its own path; the others use ``runtime/drivers``.
Bindings come from ``resources`` (so a queue only published to, or used as a
dead-letter queue, still uses its driver) and from the events that consume them.

``host.env`` next to ``pskit_host.json`` (from ``provider.options.env_file``) is
loaded at start for variables the process environment does not already set.
"""

from __future__ import annotations

import base64
import inspect
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, quote, unquote, urlsplit
from urllib.request import Request, urlopen

from . import hostlog
from .batch import BatchResult
from .context import Context
from .cron import CronError, next_cron, rate_seconds, resolve_zone
from .dispatch import execute
from .event import Event, EventType, Headers, HttpRequest, Record
from .executions import NO_ENTRY, Executor, FileExecutionStore, entry_function, valid_id
from .invoke import NOT_ROUTED, install_router
from .manifest import load_manifest, set_manifest
from .peers import HOP_HEADER, Peers, run_peer_call
from .response import Response, dumps
from .routing import match_path, method_matches
from .workflow import install_executor, wants_wait

_BROKER: Optional[Broker] = None
_MAX_BODY = 64 * 1024 * 1024
# Copied from provider.options.env_file next to pskit_host.json; never in Terraform state.
ENV_FILE = "host.env"
# Cluster deploys (provider.options.cluster) run the same image twice: one `main` replica that owns schedules,
# built-in queues / topics / buckets, workflow executions and logs, and N `web` replicas behind the load balancer
# that run HTTP and invoke() and hand everything stateful to the main replica (PSKIT_MAIN_URL).
ROLES = ("all", "main", "web")
# /__pskit/... calls a web replica answers itself; every other one goes to the main replica.
# GET /__pskit/logs/local is also local (see _route): it is this replica's own buffer.
_WEB_LOCAL = ("health", "invoke", "peer")


def parse_env_text(text: str) -> Dict[str, str]:
    """``KEY=VALUE`` lines (dotenv style): ``#`` comments, optional ``export``, quoted values."""
    out: Dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].rstrip()
        if key and (key[0].isalpha() or key[0] == "_") and all(c.isalnum() or c == "_" for c in key):
            out[key] = value
    return out


def load_env_file(path: Path) -> List[str]:
    """Set variables from ``path`` that the process environment does not already define."""
    try:
        text = path.read_text("utf-8")
    except OSError:
        return []
    added = []
    for key, value in parse_env_text(text).items():
        if key not in os.environ:
            os.environ[key] = value
            added.append(key)
    return added


def install_broker(broker: Optional[Broker]) -> None:
    global _BROKER
    _BROKER = broker


def current_broker() -> Broker:
    if _BROKER is not None:
        return _BROKER
    root = os.environ.get("PSKIT_ONPREM_ROOT")
    if not root:
        raise RuntimeError("not running inside an on-premises host (PSKIT_ONPREM_ROOT is unset)")
    spec = json.loads((Path(root) / "pskit_host.json").read_text("utf-8"))
    spec["root"] = str(Path(root))
    broker = Broker(spec)
    install_broker(broker)
    return broker


def submit_queue(name: str, message: Any, attributes: Optional[Dict[str, Any]] = None) -> str:
    """Publish one message to an on-prem queue. Works from a handler in this process."""
    return current_broker().submit_queue(name, message, attributes or {})


def submit_topic(name: str, message: Any, attributes: Optional[Dict[str, Any]] = None) -> str:
    return current_broker().submit_topic(name, message, attributes or {})


def put_object(bucket: str, key: str, data: bytes) -> None:
    current_broker().put_object(bucket, key, data)


def delete_object(bucket: str, key: str) -> None:
    current_broker().delete_object(bucket, key)


def _segment(name: str, what: str) -> str:
    text = str(name).strip()
    if not text or text in (".", "..") or "/" in text or "\\" in text or "\x00" in text:
        raise ValueError(f"invalid {what} name {name!r}")
    return text


def _key_parts(key: str) -> List[str]:
    parts = [unquote(part) for part in str(key).split("/") if part not in ("", ".")]
    if not parts or any(part == ".." for part in parts):
        raise ValueError(f"invalid object key {key!r}")
    return parts


def _body_text(message: Any) -> str:
    if isinstance(message, str):
        return message
    if isinstance(message, bytes):
        return message.decode("utf-8", "replace")
    return json.dumps(message)


_PREVIEW = 4000


def _md5(text: str) -> str:
    import hashlib

    return hashlib.md5(text.encode("utf-8")).hexdigest()  # noqa: S324 - SQS's message checksum, not security


def _brief(msg: Dict[str, Any]) -> Dict[str, Any]:
    """A message for the data browser: body cut to a preview, no private keys."""
    body = msg.get("body")
    text = body if isinstance(body, str) else json.dumps(body)
    out = {
        "id": str(msg.get("id") or ""),
        "body": text[:_PREVIEW],
        "truncated": len(text) > _PREVIEW,
        "attributes": msg.get("attributes") or {},
        "receives": msg.get("receives"),
        "enqueued_at": msg.get("enqueued_at"),
    }
    if "leased" in msg:
        out["leased"] = bool(msg["leased"])
    if "delivered" in msg:
        out["delivered_to"] = msg.get("delivered") or []
    return out


def _split_message(item: Any) -> Tuple[Any, Dict[str, Any]]:
    if isinstance(item, dict) and "message" in item and set(item) <= {"message", "attributes"}:
        raw = item.get("attributes") or {}
        return item.get("message"), dict(raw) if isinstance(raw, dict) else {}
    return item, {}


def _messages_of(payload: Any) -> List[Tuple[Any, Dict[str, Any]]]:
    if isinstance(payload, dict) and isinstance(payload.get("messages"), list):
        return [_split_message(item) for item in payload["messages"]]
    if isinstance(payload, list):
        return [_split_message(item) for item in payload]
    return [_split_message(payload)]


def _write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(json.dumps(data, separators=(",", ":")).encode("utf-8"))
    os.replace(tmp, path)


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return default


class Broker:
    """File-backed queues, buckets and topic pending files. Safe inside one process."""

    def __init__(self, spec: Dict[str, Any]) -> None:
        self.spec = spec
        self.data_dir = Path(spec["data_dir"])
        self.services = spec.get("services") or {}
        self._lock = threading.RLock()
        # Per-queue / per-bucket overrides from `driver` bindings on events.
        self._queue_paths: Dict[str, Path] = {}
        self._bucket_paths: Dict[str, Path] = {}
        self._queue_drivers: Dict[str, Any] = {}
        self._storage_drivers: Dict[str, Any] = {}
        # Resources first: a driver-backed queue that no event consumes (only published
        # to, or used as a dead-letter queue) must still go through its driver.
        self._bind_resources(spec.get("resources") or {})
        self._bind_drivers(spec.get("functions") or {})

    def _bind_resources(self, resources: Dict[str, Any]) -> None:
        for res in resources.values():
            binding = res.get("driver") if isinstance(res, dict) else None
            kind = res.get("type") if isinstance(res, dict) else None
            if isinstance(binding, dict) and kind in ("queue", "storage", "topic") and res.get("name"):
                self._bind(binding, str(res["name"]), str(kind))

    def _bind_drivers(self, functions: Dict[str, Any]) -> None:
        for fn in functions.values():
            for ev in fn.get("events") or []:
                binding = ev.get("driver")
                if not isinstance(binding, dict):
                    continue
                kind = ev.get("type")
                if kind == "queue":
                    self._bind(binding, str(ev["name"]), "queue")
                elif kind == "storage":
                    self._bind(binding, str(ev["bucket"]), "storage")
                elif kind == "topic":
                    self._bind(binding, str(ev["name"]), "topic")

    def _bind(self, binding: Dict[str, Any], name: str, kind: str) -> None:
        driver = str(binding.get("driver") or binding.get("use") or binding.get("type") or "builtin").lower()
        if driver == "directory" and binding.get("path"):
            target = self._queue_paths if kind in ("queue", "topic") else self._bucket_paths
            target[name] = Path(str(binding["path"]))
            return
        if driver in ("builtin", "directory"):
            return
        from .drivers import make_queue_driver, make_storage_driver

        if kind == "queue" and name not in self._queue_drivers:
            queue = make_queue_driver(binding, name)
            if queue is not None:
                self._queue_drivers[name] = queue
        elif kind == "storage" and name not in self._storage_drivers:
            storage = make_storage_driver(binding, name)
            if storage is not None:
                self._storage_drivers[name] = storage

    def queue_driver(self, name: str) -> Any:
        return self._queue_drivers.get(name)

    def storage_driver(self, bucket: str) -> Any:
        return self._storage_drivers.get(bucket)

    def path_for(self, kind: str) -> Path:
        service = self.services.get(kind) or {}
        raw = service.get("path")
        if raw:
            return Path(raw)
        return self.data_dir / kind

    def queue_dir(self, name: str) -> Path:
        override = self._queue_paths.get(name)
        if override is not None:
            return override
        return self.path_for("queue") / _segment(name, "queue")

    def bucket_dir(self, bucket: str) -> Path:
        override = self._bucket_paths.get(bucket)
        if override is not None:
            return override
        return self.path_for("storage") / _segment(bucket, "bucket")

    def topic_dir(self, name: str) -> Path:
        override = self._queue_paths.get(name)
        if override is not None:
            return override
        return self.path_for("topic") / _segment(name, "topic")

    def ensure(self, functions: Dict[str, Any]) -> List[str]:
        notes: List[str] = []
        self.data_dir.mkdir(parents=True, exist_ok=True)
        for fn in functions.values():
            for ev in fn.get("events") or []:
                kind = ev.get("type")
                if kind == "queue":
                    if ev["name"] not in self._queue_drivers:
                        notes.extend(self._ensure_named(self.queue_dir(ev["name"]), ev, "queue"))
                    dead = ev.get("dead_letter")
                    if dead and dead not in self._queue_drivers:
                        notes.extend(self._ensure_named(self.queue_dir(dead), {"existing": False}, "queue"))
                elif kind == "storage":
                    if ev["bucket"] not in self._storage_drivers:
                        notes.extend(self._ensure_named(self.bucket_dir(ev["bucket"]), ev, "bucket"))
                elif kind == "topic":
                    notes.extend(self._ensure_named(self.topic_dir(ev["name"]) / "pending", ev, "topic"))
        # Managed resources no event uses (published to from handlers) exist from the start too.
        for res in (self.spec.get("resources") or {}).values():
            if not isinstance(res, dict) or res.get("external") or not res.get("name"):
                continue
            name = str(res["name"])
            kind = res.get("type")
            if kind == "queue" and name not in self._queue_drivers:
                notes.extend(self._ensure_named(self.queue_dir(name), {}, "queue"))
            elif kind == "storage" and name not in self._storage_drivers:
                notes.extend(self._ensure_named(self.bucket_dir(name), {}, "bucket"))
            elif kind == "topic":
                notes.extend(self._ensure_named(self.topic_dir(name) / "pending", {}, "topic"))
        return notes

    def _ensure_named(self, path: Path, ev: Dict[str, Any], kind: str) -> List[str]:
        leaf = path if path.name == "pending" or path.name == "messages" else path / "messages"
        if kind == "bucket":
            leaf = path
        if kind == "topic":
            leaf = path
        if ev.get("existing") and not leaf.exists():
            label = ev.get("name") or ev.get("bucket") or leaf.name
            return [f"{kind} {label} is marked existing but {leaf} is not there yet; it will be picked up when it appears"]
        if kind == "bucket":
            leaf.mkdir(parents=True, exist_ok=True)
        else:
            (leaf if kind == "topic" else leaf).mkdir(parents=True, exist_ok=True)
        return []

    # ---------------------------------------------------------------- queue
    def submit_queue(self, name: str, message: Any, attributes: Optional[Dict[str, Any]] = None) -> str:
        driver = self._queue_drivers.get(name)
        if driver is not None:
            return str(driver.submit(_body_text(message), dict(attributes or {})))
        with self._lock:
            directory = self.queue_dir(name) / "messages"
            directory.mkdir(parents=True, exist_ok=True)
            seq = self._next_seq(self.queue_dir(name))
            ident = uuid.uuid4().hex
            record = {
                "id": ident,
                "body": _body_text(message),
                "attributes": attributes or {},
                "receives": 0,
                "visible_at": 0,
                "enqueued_at": time.time(),
                "seq": seq,
            }
            _write_json(directory / f"{seq:016d}-{ident}.json", record)
            return ident

    def queue_depth(self, name: str) -> int:
        driver = self._queue_drivers.get(name)
        if driver is not None:
            return int(driver.depth())
        directory = self.queue_dir(name) / "messages"
        if not directory.is_dir():
            return 0
        return sum(1 for _ in directory.glob("*.json"))

    def claim_queue(self, ev: Dict[str, Any], now: float) -> List[Dict[str, Any]]:
        driver = self._queue_drivers.get(ev["name"])
        if driver is not None:
            visibility = float(ev.get("visibility_timeout") or 30)
            return list(driver.claim(int(ev.get("batch_size") or 1), visibility, now))
        with self._lock:
            directory = self.queue_dir(ev["name"]) / "messages"
            if not directory.is_dir():
                return []
            batch = int(ev.get("batch_size") or 1)
            window = float(ev.get("batch_window") or 0)
            fifo = bool(ev.get("fifo"))
            chosen: List[Tuple[Path, Dict[str, Any]]] = []
            for path in sorted(directory.glob("*.json")):
                msg = _read_json(path, None)
                if not isinstance(msg, dict):
                    continue
                visible = float(msg.get("visible_at") or 0) <= now
                if not visible:
                    if fifo:
                        break
                    continue
                chosen.append((path, msg))
                if len(chosen) >= batch:
                    break
            if not chosen:
                return []
            if window and len(chosen) < batch:
                oldest = min(float(msg.get("enqueued_at") or now) for _, msg in chosen)
                if now - oldest < window:
                    return []
            visibility = float(ev.get("visibility_timeout") or 30)
            claimed = []
            for path, msg in chosen:
                msg["visible_at"] = now + visibility
                msg["deliveries"] = int(msg.get("deliveries") or 0) + 1
                _write_json(path, msg)
                msg["path"] = str(path)
                claimed.append(msg)
            return claimed

    def settle_queue(self, ev: Dict[str, Any], claimed: List[Dict[str, Any]], failed: Iterable[str], now: float) -> None:
        failed_ids = {str(item) for item in failed}
        max_receive = int(ev.get("max_receive") or 5)
        dead = ev.get("dead_letter")
        driver = self._queue_drivers.get(ev["name"])
        if driver is not None:
            target = None
            if dead:
                target = self._queue_drivers.get(str(dead)) or _BuiltinQueue(self, str(dead), str(ev["name"]))
            driver.settle(claimed, failed_ids, max_receive, target, now)
            return
        with self._lock:
            for msg in claimed:
                path = Path(msg["path"])
                if str(msg.get("id")) not in failed_ids:
                    path.unlink(missing_ok=True)
                    continue
                current = _read_json(path, msg)
                current["receives"] = int(current.get("receives") or 0) + 1
                if dead and current["receives"] >= max_receive:
                    path.unlink(missing_ok=True)
                    self.submit_queue(
                        str(dead),
                        current.get("body"),
                        {"pskit_source_queue": ev["name"], "pskit_receives": current["receives"]},
                    )
                else:
                    current["visible_at"] = now
                    _write_json(path, current)

    # Leases for a consumer on another host (the `pskit_host` driver). Only file-backed
    # queues: a driver queue already has its own service to lease from.
    def lease_queue(self, name: str, batch: int, visibility: float, now: float) -> List[Dict[str, Any]]:
        if name in self._queue_drivers:
            raise ValueError(f"queue {name} uses a driver; consume it from that service directly")
        ev = {"name": name, "batch_size": max(1, min(int(batch), 100)), "visibility_timeout": max(1.0, visibility)}
        out = []
        for msg in self.claim_queue(ev, now):
            out.append(
                {
                    "id": msg.get("id"),
                    "body": msg.get("body"),
                    "attributes": msg.get("attributes") or {},
                    # Deliveries so far, counting this one (like SQS's ApproximateReceiveCount).
                    "receives": int(msg.get("deliveries") or int(msg.get("receives") or 0) + 1),
                    "enqueued_at": msg.get("enqueued_at"),
                    "receipt": Path(msg["path"]).name,
                }
            )
        return out

    def _leased_path(self, name: str, receipt: str) -> Path:
        text = str(receipt)
        if not text.endswith(".json") or "/" in text or "\\" in text or text.startswith("."):
            raise ValueError(f"invalid receipt {receipt!r}")
        return self.queue_dir(name) / "messages" / text

    def ack_queue(self, name: str, receipts: Iterable[str]) -> int:
        done = 0
        with self._lock:
            for receipt in receipts:
                path = self._leased_path(name, receipt)
                if path.is_file():
                    path.unlink()
                    done += 1
        return done

    def nack_queue(self, name: str, receipts: Iterable[str], now: float) -> int:
        done = 0
        with self._lock:
            for receipt in receipts:
                path = self._leased_path(name, receipt)
                current = _read_json(path, None)
                if not isinstance(current, dict):
                    continue
                current["receives"] = int(current.get("receives") or 0) + 1
                current["visible_at"] = now
                _write_json(path, current)
                done += 1
        return done

    # ---------------------------------------------------------------- browse
    def peek_queue(self, name: str, offset: int, limit: int, now: float) -> Dict[str, Any]:
        """A page of waiting messages, oldest first, without receiving them."""
        driver = self._queue_drivers.get(name)
        if driver is not None:
            # A custom class is wrapped; it may implement peek(offset, limit) -> (items, total).
            peek = getattr(getattr(driver, "inner", driver), "peek", None)
            if peek is None:
                depth = int(driver.depth())
                return {"supported": False, "total": depth if depth >= 0 else None, "items": [],
                        "note": "this driver cannot list messages without receiving them; only the depth is shown"}
            items, total = peek(offset, limit)
            return {"supported": True, "total": total, "items": [_brief(m) for m in items]}
        with self._lock:
            directory = self.queue_dir(name) / "messages"
            files = sorted(directory.glob("*.json")) if directory.is_dir() else []
            items = []
            for path in files[offset : offset + limit]:
                msg = _read_json(path, None)
                if isinstance(msg, dict):
                    msg["leased"] = float(msg.get("visible_at") or 0) > now
                    items.append(_brief(msg))
        return {"supported": True, "total": len(files), "items": items}

    def peek_topic(self, name: str, offset: int, limit: int) -> Dict[str, Any]:
        with self._lock:
            directory = self.topic_dir(name) / "pending"
            files = sorted(directory.glob("*.json")) if directory.is_dir() else []
            items = [_brief(m) for m in (_read_json(p, None) for p in files[offset : offset + limit]) if isinstance(m, dict)]
        return {"supported": True, "total": len(files), "items": items}

    def list_bucket(self, bucket: str, offset: int, limit: int, prefix: str = "") -> Dict[str, Any]:
        found = self.scan_bucket(bucket)
        keys = sorted(k for k in found if k.startswith(prefix))
        items = [{"key": k, "size": found[k][1], "etag": str(found[k][0])} for k in keys[offset : offset + limit]]
        return {"supported": True, "total": len(keys), "items": items}

    def change_visibility(self, name: str, receipt: str, seconds: float) -> None:
        with self._lock:
            path = self._leased_path(name, receipt)
            current = _read_json(path, None)
            if isinstance(current, dict):
                current["visible_at"] = time.time() + max(0.0, seconds)
                _write_json(path, current)

    def purge_queue(self, name: str) -> int:
        if name in self._queue_drivers:
            raise ValueError(f"queue {name} uses a driver; purge it in that service")
        removed = 0
        with self._lock:
            for path in (self.queue_dir(name) / "messages").glob("*.json"):
                path.unlink()
                removed += 1
        return removed

    def delete_message(self, name: str, ident: str) -> bool:
        if name in self._queue_drivers:
            raise ValueError(f"queue {name} uses a driver; delete messages in that service")
        if not ident or any(c in ident for c in "/\\*?["):
            raise ValueError("invalid message id")
        with self._lock:
            for path in (self.queue_dir(name) / "messages").glob(f"*-{ident}.json"):
                path.unlink()
                return True
        return False

    def _next_seq(self, queue: Path) -> int:
        seq_path = queue / "seq"
        try:
            current = int(seq_path.read_text("ascii").strip() or "0")
        except (OSError, ValueError):
            current = 0
        current += 1
        seq_path.parent.mkdir(parents=True, exist_ok=True)
        seq_path.write_text(str(current), "ascii")
        return current

    # ---------------------------------------------------------------- topic
    def submit_topic(self, name: str, message: Any, attributes: Optional[Dict[str, Any]] = None) -> str:
        with self._lock:
            directory = self.topic_dir(name) / "pending"
            directory.mkdir(parents=True, exist_ok=True)
            ident = uuid.uuid4().hex
            record = {
                "id": ident,
                "body": _body_text(message),
                "attributes": attributes or {},
                "delivered": [],
                "enqueued_at": time.time(),
            }
            _write_json(directory / f"{ident}.json", record)
            return ident

    def claim_topic(self, name: str) -> List[Dict[str, Any]]:
        with self._lock:
            directory = self.topic_dir(name) / "pending"
            if not directory.is_dir():
                return []
            claimed = []
            for path in sorted(directory.glob("*.json")):
                msg = _read_json(path, None)
                if isinstance(msg, dict):
                    msg["path"] = str(path)
                    claimed.append(msg)
            return claimed

    def settle_topic(self, msg: Dict[str, Any], delivered_to: Iterable[str], done: bool) -> None:
        path = Path(msg["path"])
        with self._lock:
            if done or not path.is_file():
                path.unlink(missing_ok=True)
                return
            current = _read_json(path, msg)
            have = set(current.get("delivered") or [])
            have.update(delivered_to)
            current["delivered"] = sorted(have)
            _write_json(path, current)

    # ---------------------------------------------------------------- storage
    def put_object(self, bucket: str, key: str, data: bytes) -> Optional[Path]:
        driver = self._storage_drivers.get(bucket)
        if driver is not None:
            driver.put("/".join(_key_parts(key)), data)
            return None
        parts = _key_parts(key)
        path = self.bucket_dir(bucket)
        for part in parts:
            path = path / part
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def get_object(self, bucket: str, key: str) -> bytes:
        driver = self._storage_drivers.get(bucket)
        if driver is not None:
            return bytes(driver.get("/".join(_key_parts(key))))
        path = self.bucket_dir(bucket)
        for part in _key_parts(key):
            path = path / part
        return path.read_bytes()

    def delete_object(self, bucket: str, key: str) -> bool:
        driver = self._storage_drivers.get(bucket)
        if driver is not None:
            return bool(driver.delete("/".join(_key_parts(key))))
        parts = _key_parts(key)
        path = self.bucket_dir(bucket)
        for part in parts:
            path = path / part
        if not path.is_file():
            return False
        path.unlink()
        return True

    def scan_bucket(self, bucket: str) -> Dict[str, Tuple[Any, int]]:
        driver = self._storage_drivers.get(bucket)
        if driver is not None:
            return {str(k): (v[0], int(v[1])) for k, v in driver.scan().items()}
        root = self.bucket_dir(bucket)
        found: Dict[str, Tuple[Any, int]] = {}
        if not root.is_dir():
            return found
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(root).as_posix()
            stat = path.stat()
            found[rel] = (stat.st_mtime_ns, stat.st_size)
        return found


class _BuiltinQueue:
    """Dead-letter target for a driver queue whose DLQ is a builtin queue."""

    def __init__(self, broker: Broker, name: str, source: str) -> None:
        self._broker = broker
        self._name = name
        self._source = source

    def submit(self, body: str, attributes: Dict[str, Any]) -> str:
        attrs: Dict[str, Any] = {"pskit_source_queue": self._source}
        attrs.update(attributes or {})
        return self._broker.submit_queue(self._name, body, attrs)


def main_request(
    main_url: str, token: str, method: str, path: str, body: Optional[bytes] = None,
    headers: Optional[Dict[str, str]] = None, timeout: float = 30.0,
) -> Tuple[int, Dict[str, str], bytes]:
    """One HTTP call to the main replica: ``(status, headers, body)`` for any status; OSError when it is down."""
    sent = {k: v for k, v in (headers or {}).items() if v}
    if token:
        sent["x-pskit-token"] = token
    req = Request(main_url.rstrip("/") + path, data=body, method=method, headers=sent)  # noqa: S310 - our own URL
    try:
        with urlopen(req, timeout=timeout) as resp:  # noqa: S310
            return resp.status, dict(resp.headers), resp.read()
    except HTTPError as exc:
        return exc.code, dict(exc.headers or {}), exc.read()


class ForwardingBroker(Broker):
    """The broker of a ``web`` replica: built-in queues, topics and buckets live on the main replica.

    A resource with a driver (redis, sqs, s3, ...) is used directly, as on any host.
    """

    def __init__(self, spec: Dict[str, Any], main_url: str, token: str) -> None:
        super().__init__(spec)
        self.main_url = main_url
        self.token = token

    def _request(self, method: str, path: str, body: Optional[bytes] = None,
                 headers: Optional[Dict[str, str]] = None) -> Tuple[int, Dict[str, str], bytes]:
        """``main_request``, retried for about 8 s while the main replica cannot be reached at all (it is restarting
        during a deploy, or its address is not routable yet). A request that reached it is never sent twice."""
        for delay in (0.5, 1.0, 2.0, 4.0, 0.0):
            try:
                return main_request(self.main_url, self.token, method, path, body, headers)
            except URLError as exc:
                if not delay or not isinstance(exc.reason, (ConnectionError, socket.gaierror)):
                    raise
            time.sleep(delay)
        raise AssertionError("unreachable")  # pragma: no cover

    def _call(self, method: str, path: str, payload: Any = None, raw: Optional[bytes] = None) -> Any:
        body = raw if raw is not None else (dumps(payload).encode("utf-8") if payload is not None else None)
        kind = "application/octet-stream" if raw is not None else "application/json"
        status, _headers, data = self._request(method, path, body, {"content-type": kind})
        if status >= 300:
            raise RuntimeError(f"main replica answered {status} to {method} {path}: {data[:300].decode('utf-8', 'replace')}")
        return json.loads(data.decode("utf-8") or "null") if data else None

    def submit_queue(self, name: str, message: Any, attributes: Optional[Dict[str, Any]] = None) -> str:
        if self.queue_driver(name) is not None:
            return super().submit_queue(name, message, attributes)
        reply = self._call("POST", f"/__pskit/queues/{quote(name, safe='')}",
                           {"messages": [{"message": message, "attributes": dict(attributes or {})}]})
        return str((reply or {}).get("queued", [""])[0])

    def submit_topic(self, name: str, message: Any, attributes: Optional[Dict[str, Any]] = None) -> str:
        reply = self._call("POST", f"/__pskit/topics/{quote(name, safe='')}",
                           {"messages": [{"message": message, "attributes": dict(attributes or {})}]})
        return str((reply or {}).get("published", [""])[0])

    def _object_path(self, bucket: str, key: str) -> str:
        return f"/__pskit/storage/{quote(bucket, safe='')}/" + "/".join(quote(p, safe="") for p in _key_parts(key))

    def put_object(self, bucket: str, key: str, data: bytes) -> Optional[Path]:
        if self.storage_driver(bucket) is not None:
            return super().put_object(bucket, key, data)
        self._call("PUT", self._object_path(bucket, key), raw=bytes(data))
        return None

    def get_object(self, bucket: str, key: str) -> bytes:
        if self.storage_driver(bucket) is not None:
            return super().get_object(bucket, key)
        status, _headers, data = self._request("GET", self._object_path(bucket, key))
        if status == 404:
            raise FileNotFoundError(f"no object {key!r} in {bucket}")
        if status >= 300:
            raise RuntimeError(f"main replica answered {status} reading {bucket}/{key}")
        return data

    def delete_object(self, bucket: str, key: str) -> bool:
        if self.storage_driver(bucket) is not None:
            return super().delete_object(bucket, key)
        return bool((self._call("DELETE", self._object_path(bucket, key)) or {}).get("deleted"))


class PeerBroker(Broker):
    """The broker of a host whose project runs on several servers (``provider.options.placement``).

    A built-in queue or bucket belongs to the group of the function it triggers: here it is used directly,
    elsewhere through that group's host. A topic is published to every group with a subscriber. A resource with a
    driver (redis, sqs, s3, ...) is used directly, as on any host. ``local=True`` (a call from another group) never
    forwards again."""

    def __init__(self, spec: Dict[str, Any], peers: Peers) -> None:
        super().__init__(spec)
        self.peers = peers

    def submit_queue(self, name: str, message: Any, attributes: Optional[Dict[str, Any]] = None,
                     local: bool = False) -> str:
        group = None if local or self.queue_driver(name) is not None else self.peers.owner("queue", name)
        if group is None:
            return super().submit_queue(name, message, attributes)
        reply = self.peers.call(group, "POST", f"/__pskit/queues/{quote(name, safe='')}",
                                {"messages": [{"message": message, "attributes": dict(attributes or {})}]})
        return str((reply or {}).get("queued", [""])[0])

    def submit_topic(self, name: str, message: Any, attributes: Optional[Dict[str, Any]] = None,
                     local: bool = False) -> str:
        groups = [self.peers.group] if local else self.peers.subscribers("topic", name)
        ident = ""
        for group in groups:
            if group == self.peers.group:
                ident = super().submit_topic(name, message, attributes) or ident
            else:
                reply = self.peers.call(group, "POST", f"/__pskit/topics/{quote(name, safe='')}",
                                        {"messages": [{"message": message, "attributes": dict(attributes or {})}]})
                ident = ident or str((reply or {}).get("published", [""])[0])
        return ident

    def _object_path(self, bucket: str, key: str) -> str:
        return f"/__pskit/storage/{quote(bucket, safe='')}/" + "/".join(quote(p, safe="") for p in _key_parts(key))

    def _bucket_owner(self, bucket: str, local: bool) -> Optional[str]:
        return None if local or self.storage_driver(bucket) is not None else self.peers.owner("storage", bucket)

    def put_object(self, bucket: str, key: str, data: bytes, local: bool = False) -> Optional[Path]:
        group = self._bucket_owner(bucket, local)
        if group is None:
            return super().put_object(bucket, key, data)
        self.peers.call(group, "PUT", self._object_path(bucket, key), raw=bytes(data))
        return None

    def get_object(self, bucket: str, key: str, local: bool = False) -> bytes:
        group = self._bucket_owner(bucket, local)
        if group is None:
            return super().get_object(bucket, key)
        status, _headers, data = self.peers.request(group, "GET", self._object_path(bucket, key))
        if status == 404:
            raise FileNotFoundError(f"no object {key!r} in {bucket}")
        if status >= 300:
            raise RuntimeError(f"group {group} answered {status} reading {bucket}/{key}")
        return data

    def delete_object(self, bucket: str, key: str, local: bool = False) -> bool:
        group = self._bucket_owner(bucket, local)
        if group is None:
            return super().delete_object(bucket, key)
        return bool((self.peers.call(group, "DELETE", self._object_path(bucket, key)) or {}).get("deleted"))


class RemoteExecutor:
    """Workflow starts on a ``web`` replica: the run happens (and is recorded) on the main replica."""

    def __init__(self, main_url: str, token: str, workflows: Iterable[str]) -> None:
        self.main_url = main_url
        self.token = token
        self.workflows = set(workflows)

    def knows(self, name: str) -> bool:
        return name in self.workflows

    def start(
        self, name: str, data: Any, wait: bool = False, task_runner: Any = None, entry_result: Any = NO_ENTRY
    ) -> Dict[str, Any]:
        args = (["wait=true"] if wait else []) + (["entry=true"] if entry_result is not NO_ENTRY else [])
        path = f"/__pskit/workflows/{quote(name, safe='')}" + ("?" + "&".join(args) if args else "")
        if entry_result is not NO_ENTRY:
            data = {"input": data, "entry_result": entry_result}
        status, _headers, raw = main_request(
            self.main_url, self.token, "POST", path, dumps(data).encode("utf-8"), {"content-type": "application/json"},
            timeout=24 * 3600 if wait else 30,
        )
        body = json.loads(raw.decode("utf-8") or "null") if raw else {}
        if not wait:
            if status >= 300:
                raise RuntimeError(f"main replica answered {status} starting workflow {name}: {body}")
            return body
        record = dict(body) if isinstance(body, dict) else {"output": body}
        record.setdefault("status", "SUCCEEDED" if status < 300 else "FAILED")
        record["_body"] = body
        return record

    def result_body(self, record: Dict[str, Any]) -> Any:
        return record.get("_body")

    def shutdown(self) -> None:
        return None


def _response_value(resp: Response) -> Any:
    """The body of a function's HTTP answer as a workflow value: parsed JSON, else text."""
    body = resp.body
    if isinstance(body, (bytes, bytearray)):
        try:
            body = bytes(body).decode("utf-8")
        except UnicodeDecodeError:
            return base64.b64encode(bytes(body)).decode("ascii")
    if isinstance(body, str):
        try:
            return json.loads(body)
        except ValueError:
            return body
    return body


def _filter_match(policy: Optional[Dict[str, Any]], attributes: Dict[str, Any], body: Any) -> bool:
    if not policy:
        return True
    source = dict(attributes or {})
    if isinstance(body, dict):
        for key, value in body.items():
            source.setdefault(str(key), value)
    for key, expected in policy.items():
        allowed = expected if isinstance(expected, list) else [expected]
        allowed_text = {str(item) for item in allowed}
        actual = source.get(key)
        if isinstance(actual, list):
            if not any(item in allowed or str(item) in allowed_text for item in actual):
                return False
        elif actual not in allowed and str(actual) not in allowed_text:
            return False
    return True


def _key_selected(key: str, ev: Dict[str, Any]) -> bool:
    prefix = ev.get("prefix") or ""
    suffix = ev.get("suffix") or ""
    if prefix and not key.startswith(prefix):
        return False
    if suffix and not key.endswith(suffix):
        return False
    return True


class Host:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.spec = json.loads((self.root / "pskit_host.json").read_text("utf-8"))
        self.spec["root"] = str(self.root)
        self.app_dir = self.root / "app"
        # Secrets for `<name>_env` driver options and handlers (provider.options.env_file),
        # loaded before the broker builds drivers.
        load_env_file(self.root / ENV_FILE)
        # `custom` drivers import classes from the app while the broker is built, and may
        # resolve relative paths against the host root.
        self._prepare_imports()
        os.environ["PSKIT_ONPREM_ROOT"] = str(self.root)
        self.role = str(os.environ.get("PSKIT_HOST_ROLE") or self.spec.get("role") or "all")
        if self.role not in ROLES:
            raise ValueError(f"PSKIT_HOST_ROLE must be one of {', '.join(ROLES)}, got {self.role!r}")
        self.main_url = str(os.environ.get("PSKIT_MAIN_URL") or "").rstrip("/")
        if self.role == "web" and not self.main_url:
            raise ValueError("a web replica needs PSKIT_MAIN_URL (the main replica)")
        self.replica = str(os.environ.get("PSKIT_REPLICA") or socket.gethostname())
        # The cluster server (orchestrator node) this replica runs on: shown with each request.
        self.node = str(os.environ.get("PSKIT_NODE") or "")
        token = str(self.spec.get("admin_token") or "")
        # Functions of this project in other groups (provider.options.placement), or None.
        self.peers = Peers.from_spec(self.spec)
        if self.role == "web":
            self.broker: Broker = ForwardingBroker(self.spec, self.main_url, token)
        elif self.peers is not None:
            self.broker = PeerBroker(self.spec, self.peers)
        else:
            self.broker = Broker(self.spec)
        # A group other than the default one sends its logs and counts there, so one place shows every group.
        self.log_url = ""
        if self.peers is not None and self.role != "web" and self.peers.group != self.peers.default:
            self.log_url = self.peers.urls.get(self.peers.default, "")
        # web: invocations and log entries not yet sent to the main replica.
        self._shipped = 0
        self._unshipped: List[Dict[str, Any]] = []
        self.notes: List[str] = []
        self._stop = threading.Event()
        self._env_lock = threading.RLock()
        self._rr: Dict[str, int] = {}
        self._snapshot: Dict[str, Dict[str, Tuple[int, int]]] = {}
        self._sched = _read_json(self._sched_path(), {"origin": None, "last": {}})
        self._booted = False
        self.started_at = time.time()
        self.logs = hostlog.LogBuffer(
            self.broker.data_dir / "logs" / "host.jsonl",
            capacity=int(self.spec.get("log_buffer") or 5000),
        )
        self.executor: Any = None  # Executor; RemoteExecutor on a web replica
        self._stats: Dict[str, Dict[str, Any]] = {}
        self._stats_lock = threading.Lock()
        self._last_recover = 0.0
        # Node.js services: one `node pskit_runtime/worker.js` per function (its own environment).
        self.language = str(self.spec.get("language") or "python")
        self._workers: Dict[str, Any] = {}
        self._workers_lock = threading.Lock()

    # ---------------------------------------------------------------- lifecycle
    def open(self) -> None:
        if not (self.app_dir / "pskit_manifest.json").is_file():
            raise FileNotFoundError(f"bundle manifest missing: {self.app_dir / 'pskit_manifest.json'}")
        self._prepare_imports()
        os.environ["PSKIT_MANIFEST"] = str(self.app_dir / "pskit_manifest.json")
        os.environ["PSKIT_ONPREM_ROOT"] = str(self.root)
        set_manifest(None)
        self.manifest = load_manifest(reload=True)
        install_broker(self.broker)
        install_router(self._route_remote if self.peers is not None else None)
        for note in self.broker.ensure(self.spec.get("functions") or {}):
            self._note(note)
        if self.role == "web":
            workflows = sorted(self.manifest.workflows or {})
            self.executor = RemoteExecutor(self.main_url, str(self.spec.get("admin_token") or ""), workflows)
            install_executor(self.executor)
            self._booted = True
            return
        if self.log_url and self.peers is not None:
            # Workflows run (and are recorded) on the default group; their steps come back here when they are ours.
            self.executor = RemoteExecutor(self.log_url, self.peers.token, sorted(self.manifest.workflows or {}))
            install_executor(self.executor)
        else:
            self._start_executor()
        self._baseline_storage()
        if not self._sched.get("origin"):
            self._sched["origin"] = time.time()
            self._sched.setdefault("last", {})
            self._save_sched()
        self._booted = True

    def _start_executor(self) -> None:
        if self.executor is not None:
            self.executor.shutdown()
        workflows: Dict[str, Dict[str, Any]] = {}
        for name, wf in (self.manifest.workflows or {}).items():
            entry: Dict[str, Any] = {"definition": wf.get("definition") or {}, "orchestrator": wf.get("orchestrator")}
            if wf.get("timeout"):
                entry["timeout"] = wf["timeout"]
            workflows[name] = entry
        store = FileExecutionStore(
            self.broker.data_dir / "executions", retention=int(self.spec.get("execution_retention") or 500)
        )
        self.executor = Executor(
            store,
            workflows,
            self._task_runner,
            max_workers=int(self.spec.get("workflow_workers") or 8),
        )
        aborted = self.executor.recover()
        if aborted:
            self._note(f"{aborted} workflow execution(s) were still running when the host stopped; marked ABORTED")
        install_executor(self.executor)

    def _task_runner(self, function: str, data: Any) -> Any:
        return self.invoke(function, Event(type=EventType.WORKFLOW, data=data, source="onprem.workflow"))

    def orchestrated(self, function: str) -> Optional[str]:
        """Workflow name when ``function`` is an embedded orchestrator."""
        manifest = getattr(self, "manifest", None)
        for name, wf in ((manifest.workflows if manifest else None) or {}).items():
            if wf.get("orchestrator") == function:
                return name
        return None

    def entry_workflows(self, function: str) -> List[str]:
        """Workflows whose first state is a task of ``function``: they start when it runs on its own."""
        manifest = getattr(self, "manifest", None)
        return [
            name
            for name, wf in sorted(((manifest.workflows if manifest else None) or {}).items())
            if wf.get("start_on_entry", True) and entry_function(wf.get("definition") or {}) == function
        ]

    def _start_entry_workflows(self, function: str, event: Event, result: Any) -> None:
        """``function`` ran on its own (not as a workflow step): start each workflow it is the first task of.

        The run takes the call's input as the workflow input and its result as the first state's result, so the
        function does not run twice. A failed HTTP answer (status >= 400) starts nothing.
        """
        names = self.entry_workflows(function)
        executor = self.executor
        if not names or executor is None:
            return
        output = result
        if isinstance(result, Response):
            if result.status >= 400:
                return
            output = _response_value(result)
        elif isinstance(result, BatchResult):
            if not result.ok:
                return
            output = None
        if event.http is not None:
            data = event.http.json(default=None) if event.http.body else dict(event.http.query)
        elif event.records:
            bodies = [r.json(default=r.text()) for r in event.records]
            data = bodies[0] if len(bodies) == 1 else bodies
        else:
            data = event.data
        started: List[str] = []
        for name in names:
            if not executor.knows(name):
                continue
            try:
                run = executor.start(name, data, entry_result=output)
            except Exception as exc:  # noqa: BLE001 - the function's own answer must not fail because of it
                self.logs.append("ERROR", "host", f"workflow {name} did not start after {function}: {exc}",
                                 function=function)
                continue
            execution_id = str((run or {}).get("execution_id") or "")
            started.append(execution_id)
            self.logs.append("INFO", "host", f"{function} started workflow {name} (execution {execution_id})",
                             function=function)
        if isinstance(result, Response) and started:
            result.headers.setdefault("x-pskit-execution-id", ", ".join(started))

    def capture_output(self) -> None:
        """Send this process's logging and stdout/stderr into the log buffer."""
        level = str(self.spec.get("log_level") or os.environ.get("PSKIT_LOG_LEVEL") or "INFO")
        hostlog.install(self.logs, level=level, capture_streams=bool(self.spec.get("capture_output", True)))

    def _prepare_imports(self) -> None:
        app = str(self.app_dir)
        while app in sys.path:
            sys.path.remove(app)
        sys.path.insert(0, app)
        from . import dispatch

        dispatch._HANDLERS.clear()
        for name, module in list(sys.modules.items()):
            if name != "app" and not name.startswith("app."):
                continue
            loaded = getattr(module, "__file__", None) or ""
            if not loaded.startswith(app):
                del sys.modules[name]

    def _baseline_storage(self) -> None:
        path = self.broker.data_dir / "storage-snapshot.json"
        saved = _read_json(path, None)
        if isinstance(saved, dict):
            self._snapshot = {
                bucket: {key: (pair[0], int(pair[1])) for key, pair in files.items()}
                for bucket, files in saved.items()
                if isinstance(files, dict)
            }
            return
        for ev in self._events("storage"):
            bucket = ev["bucket"]
            try:
                self._snapshot.setdefault(bucket, self.broker.scan_bucket(bucket))
            except Exception as exc:  # noqa: BLE001
                self._note(f"storage {bucket}: {exc}")
        self._save_snapshot()

    def _save_snapshot(self) -> None:
        _write_json(self.broker.data_dir / "storage-snapshot.json", self._snapshot)

    def _sched_path(self) -> Path:
        return self.broker.data_dir / "schedule-state.json"

    def _save_sched(self) -> None:
        self.broker.data_dir.mkdir(parents=True, exist_ok=True)
        _write_json(self._sched_path(), self._sched)

    def rewind_schedules(self, seconds: float) -> None:
        """Test helper: pretend the last fire was ``seconds`` ago."""
        past = time.time() - seconds
        self._sched["origin"] = past
        last = self._sched.setdefault("last", {})
        for key in self._schedule_ids():
            last[key] = past
        self._save_sched()

    # ---------------------------------------------------------------- invoke
    def invoke(self, function: str, event: Event, from_peer: bool = False) -> Any:
        fns = self.spec.get("functions") or {}
        group = self.peers.remote(function) if self.peers is not None and function not in fns else None
        if group:
            if from_peer:  # never a second hop, even when two hosts disagree about where it runs
                raise KeyError(f"function {function!r} runs in group {group}, not here")
            return self._invoke_remote(function, group, event)
        if function not in fns and function not in getattr(self, "manifest", load_manifest()).functions:
            known = ", ".join(sorted(fns)) or "<none>"
            raise KeyError(f"unknown function {function!r}; known: {known}")
        spec = fns.get(function) or {}
        event.function = function
        event.provider = "onprem"
        timeout = int(spec.get("timeout") or 30)
        request_id = uuid.uuid4().hex
        started = time.time()
        t0 = time.perf_counter()
        error: Optional[BaseException] = None
        result: Any = None
        with hostlog.invocation(function, request_id):
            try:
                if self.language == "node":
                    ctx = Context(request_id=request_id, function=function, provider="onprem", deadline=started + timeout)
                    result = self._invoke_node(function, spec, event, ctx, timeout)
                else:
                    with self._call_env(function, spec):
                        ctx = Context(
                            request_id=request_id,
                            function=function,
                            provider="onprem",
                            deadline=started + timeout,
                        )
                        result = execute(event, ctx, function)
            except BaseException as exc:
                error = exc
                raise
            finally:
                self._record_invocation(function, event, t0, result, error)
        if event.type != EventType.WORKFLOW and self.orchestrated(function) is None:
            try:
                self._start_entry_workflows(function, event, result)
            except Exception as exc:  # noqa: BLE001 - never fails the call that already succeeded
                self.logs.append("ERROR", "host", f"workflows after {function} not started: {exc}", function=function)
        return result

    def _invoke_remote(self, function: str, group: str, event: Event) -> Any:
        """Run ``function`` on the host of ``group``: HTTP requests pass through as they are."""
        assert self.peers is not None
        event.function = function
        event.provider = "onprem"
        if event.http is not None:
            return self.peers.forward_http(group, event.http, self.peers.timeout(function))
        return self.peers.invoke(function, event, group)

    @property
    def group(self) -> str:
        return str(self.spec.get("group") or "")

    def served_elsewhere(self, function: str) -> Optional[Tuple[str, str]]:
        """``(group, url)`` when an HTTP request for ``function`` reached a host that does not run it and does not
        pass routes on (with ``placement.gateway`` every group does; a list: only those groups' routes)."""
        fns = self.spec.get("functions") or {}
        passes = self.spec.get("gateway")
        if self.peers is None or function in fns or passes is True:
            return None
        group = self.peers.remote(function)
        if not group or (isinstance(passes, list) and group in passes):
            return None
        url = str(((self.spec.get("groups") or {}).get(group) or {}).get("url") or "")
        return group, url

    def _route_remote(self, function: str, event: Event) -> Any:
        """``invoke()`` and workflow steps: functions of other groups go to their host."""
        fns = self.spec.get("functions") or {}
        group = self.peers.remote(function) if self.peers is not None and function not in fns else None
        if not group:
            return NOT_ROUTED
        return self._invoke_remote(function, group, event)

    def _record_invocation(
        self, function: str, event: Event, t0: float, result: Any, error: Optional[BaseException]
    ) -> None:
        duration = round((time.perf_counter() - t0) * 1000, 2)
        kind = getattr(event.type, "value", str(event.type))
        fields: Dict[str, Any] = {"event_type": kind, "duration_ms": duration}
        failed = error is not None
        if event.http is not None:
            status = result.status if isinstance(result, Response) else (500 if failed else 200)
            fields.update(method=event.http.method, path=event.http.path, status=status)
            failed = failed or status >= 500
            summary = f"{event.http.method} {event.http.path} -> {status}"
        else:
            summary = f"{kind} -> {'error' if failed else 'ok'}"
            if isinstance(result, BatchResult) and result.failed:
                fields["failed_records"] = len(result.failed)
        if error is not None:
            fields["error"] = f"{type(error).__name__}: {error}"
        if self.role != "all":  # a cluster replica: which one (and which server) handled it
            fields["replica"] = self.replica
            if self.node:
                fields["node"] = self.node
        message = f"{summary} ({duration} ms)"
        if error is not None:
            message += f" {fields['error']}"
        self.logs.append("ERROR" if failed else "INFO", "invocation", message, fields=fields)
        error_text = (fields.get("error") or f"HTTP {fields.get('status')}") if failed else ""
        self._count(function, duration, failed, error_text, ship=self.role == "web" or bool(self.log_url))

    def _count(self, function: str, duration: float, failed: bool, error: str, *, ship: bool) -> None:
        with self._stats_lock:
            item = self._stats.setdefault(function, _empty_stats())
            item["invocations"] += 1
            item["total_ms"] += duration
            item["last_duration_ms"] = duration
            item["last_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            if failed:
                item["errors"] += 1
                item["last_error"] = error
            if ship:
                self._unshipped.append({"function": function, "duration_ms": duration, "failed": failed, "error": error})

    def stats(self) -> Dict[str, Any]:
        with self._stats_lock:
            raw = {name: dict(item) for name, item in self._stats.items()}
        for name in self.spec.get("functions") or {}:
            raw.setdefault(name, _empty_stats())
        functions = {}
        for name, item in sorted(raw.items()):
            count = item["invocations"]
            functions[name] = {
                "invocations": count,
                "errors": item["errors"],
                "avg_duration_ms": round(item["total_ms"] / count, 2) if count else None,
                "last_duration_ms": item["last_duration_ms"],
                "last_at": item["last_at"],
                "last_error": item["last_error"],
            }
        queues: Dict[str, Any] = {}
        for ev in self._events("queue"):
            for name in (ev["name"], ev.get("dead_letter")):
                if not name or name in queues:
                    continue
                try:
                    depth = self.broker.queue_depth(name)
                    queues[name] = depth if depth >= 0 else None  # -1: the service cannot tell
                except Exception as exc:  # noqa: BLE001 - a remote queue may be down
                    queues[name] = None
                    self._note(f"queue {name}: depth unavailable: {exc}")
        return {
            "started_at": datetime.fromtimestamp(self.started_at, timezone.utc).isoformat(timespec="seconds"),
            "uptime_s": round(time.time() - self.started_at, 1),
            "functions": functions,
            "queues": queues,
        }

    # ---------------------------------------------------------------- Node.js
    def _invoke_node(self, function: str, spec: Dict[str, Any], event: Event, ctx: Context, timeout: int) -> Any:
        """Run one invocation in the function's Node.js worker and map the answer back.

        Embedded workflow orchestrators stay in this (Python) process: the executor
        runs the definition and calls each task function through its worker.
        """
        workflow = self.orchestrated(function)
        if workflow is not None:
            return self._orchestrate_node(workflow, event)
        worker = self._worker(function, spec)
        if ctx.memory_mb is None and spec.get("memory"):
            ctx.memory_mb = int(spec["memory"])
        reply = worker.call(function, event, ctx, timeout)
        return node_result(reply)

    def _orchestrate_node(self, workflow: str, event: Event) -> Any:
        executor = self.executor
        if executor is None or not executor.knows(workflow):
            raise LookupError(f"unknown workflow {workflow!r}")
        if event.http is not None:
            data = event.http.json(default=None) if event.http.body else dict(event.http.query)
        else:
            data = event.data
        if not wants_wait(event):
            return Response.json(executor.start(workflow, data), 202)
        record = executor.start(workflow, data, wait=True)
        body = executor.result_body(record)
        if record.get("status") != "SUCCEEDED":
            if event.http is not None:
                return Response.json(body, 500)
            raise RuntimeError(f"{record.get('error') or 'States.Runtime'}: {record.get('cause') or ''}")
        return body

    def _node_bin(self) -> str:
        rel = str(self.spec.get("node_bin") or "node")
        if "/" in rel:
            bundled = self.root / rel
            if bundled.is_file():
                return str(bundled)
        found = shutil.which("node")
        if not found:
            raise RuntimeError(
                "Node.js (`node`) is not on PATH on this machine; install it or redeploy with options.deploy.node: bundle"
            )
        return found

    def _worker(self, function: str, spec: Dict[str, Any]) -> Any:
        with self._workers_lock:
            worker = self._workers.get(function)
            if worker is not None and getattr(worker, "alive", True):
                return worker
            from .node_worker import NodeWorker

            env = dict(os.environ)
            env.update(self._function_env(function, spec))
            env["PSKIT_BUNDLE_ROOT"] = str(self.app_dir)
            env.setdefault("PSKIT_LOG_LEVEL", str(self.spec.get("log_level") or "INFO"))
            kwargs: Dict[str, Any] = {"env": env, "node": self._node_bin()}
            if "on_log" in inspect.signature(NodeWorker).parameters:
                kwargs["on_log"] = lambda line, fn=function: self._worker_log(fn, line)
            worker = NodeWorker(self.app_dir, **kwargs)
            self._workers[function] = worker
            return worker

    def _worker_log(self, function: str, line: str) -> None:
        """A stderr line of a worker: JSON from the pskit logger, or plain text (console output, crashes).

        The worker moves handlers' stdout to stderr (stdout is the protocol), so plain lines
        are recorded like ``print()`` output of Python handlers.
        """
        text = line.rstrip("\r\n")
        if not text:
            return
        try:
            entry = json.loads(text)
        except ValueError:
            entry = None
        if not isinstance(entry, dict) or "message" not in entry:
            self.logs.append("INFO", "stdout", text, function=function)
            return
        fields = {k: v for k, v in entry.items() if k not in ("ts", "level", "message", "function", "request_id")}
        self.logs.append(
            str(entry.get("level") or "INFO"),
            "function",
            str(entry.get("message")),
            function=str(entry.get("function") or function),
            request_id=entry.get("request_id"),
            fields=fields or None,
        )

    def close_workers(self) -> None:
        with self._workers_lock:
            workers, self._workers = list(self._workers.values()), {}
        for worker in workers:
            try:
                worker.close()
            except Exception:  # noqa: BLE001, S110 - best effort at shutdown
                pass

    def _function_env(self, function: str, spec: Dict[str, Any]) -> Dict[str, str]:
        forced = {
            "PSKIT_PROVIDER": "onprem",
            "PSKIT_SERVICE": str(self.spec.get("service") or ""),
            "PSKIT_STAGE": str(self.spec.get("stage") or ""),
            "PSKIT_REGION": str(self.spec.get("region") or "local"),
            "PSKIT_FUNCTION": function,
            "PSKIT_HANDLER": str(spec.get("handler") or ""),
            "PSKIT_ONPREM_ROOT": str(self.root),
            "PSKIT_MANIFEST": str(self.app_dir / "pskit_manifest.json"),
            "PSKIT_ENDPOINT": str(self.spec.get("endpoint") or ""),
            # This host on loopback: Node.js handlers publish through it (pskit submitQueue & co).
            "PSKIT_HOST_URL": health_url(self.spec).rsplit("/__pskit/", 1)[0],
        }
        if self.language == "node" and self.spec.get("admin_token"):
            forced["PSKIT_ADMIN_TOKEN"] = str(self.spec["admin_token"])
        env = {str(k): str(v) for k, v in (spec.get("environment") or {}).items()}
        env.update(forced)
        return env

    def _call_env(self, function: str, spec: Dict[str, Any]):
        return self._swap_env(self._function_env(function, spec))

    def _swap_env(self, env: Dict[str, str]):
        host = self

        class _Env:
            def __enter__(self) -> None:
                host._env_lock.acquire()
                self.saved = {key: os.environ.get(key) for key in env}
                os.environ.update(env)

            def __exit__(self, *exc: Any) -> None:
                for key, old in self.saved.items():
                    if old is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = old
                host._env_lock.release()

        return _Env()

    # ---------------------------------------------------------------- pump
    def pump(self, now: Optional[float] = None) -> None:
        if not self._booted:
            self.open()
        moment = time.time() if now is None else now
        self.pump_schedules(moment)
        self.pump_queues(moment)
        self.pump_topics(moment)
        self.pump_storage(moment)

    def _events(self, kind: str) -> List[Dict[str, Any]]:
        found = []
        for fn in (self.spec.get("functions") or {}).values():
            for ev in fn.get("events") or []:
                if ev.get("type") == kind:
                    found.append(ev)
        return found

    def _schedule_ids(self) -> List[str]:
        ids = []
        for name, fn in (self.spec.get("functions") or {}).items():
            index = 0
            for ev in fn.get("events") or []:
                if ev.get("type") == "schedule":
                    ids.append(f"{name}:{ev.get('name') or index}")
                    index += 1
        return ids

    def pump_schedules(self, now: float) -> None:
        last: Dict[str, float] = self._sched.setdefault("last", {})
        origin = float(self._sched.get("origin") or now)
        changed = False
        for name, fn in (self.spec.get("functions") or {}).items():
            index = 0
            for ev in fn.get("events") or []:
                if ev.get("type") != "schedule":
                    continue
                ident = f"{name}:{ev.get('name') or index}"
                index += 1
                if not ev.get("enabled", True):
                    continue
                seen = float(last.get(ident) or origin)
                try:
                    due = self._schedule_due(ev, seen, now, ident)
                except CronError as exc:
                    self._note(f"schedule {ident}: {exc}")
                    continue
                if not due:
                    continue
                event = Event(
                    type=EventType.SCHEDULE,
                    provider="onprem",
                    function=name,
                    data=ev.get("input"),
                    source="onprem.schedule",
                )
                try:
                    self.invoke(name, event)
                except Exception as exc:  # noqa: BLE001 - one bad job must not stop the host
                    self._note(f"schedule {ident} failed: {exc}")
                last[ident] = now
                changed = True
        if changed:
            self._save_sched()

    def _schedule_due(self, ev: Dict[str, Any], last: float, now: float, ident: str) -> bool:
        if ev.get("cron"):
            name = str(ev.get("timezone") or "UTC")
            zone = resolve_zone(name)
            if zone is None:
                self._note(f"schedule {ident}: timezone {name} is unavailable; using UTC (pip install tzdata)")
                zone = timezone.utc
            nxt = next_cron(str(ev["cron"]), datetime.fromtimestamp(last, zone), zone)
            return now >= nxt.timestamp()
        interval = rate_seconds(str(ev.get("rate") or "1 minutes"))
        return now >= last + interval

    def pump_queues(self, now: float) -> None:
        groups: Dict[str, List[Tuple[str, Dict[str, Any]]]] = {}
        for name, fn in (self.spec.get("functions") or {}).items():
            for ev in fn.get("events") or []:
                if ev.get("type") == "queue":
                    groups.setdefault(ev["name"], []).append((name, ev))
        for queue, consumers in groups.items():
            slot = self._rr.get(queue, 0) % len(consumers)
            function, ev = consumers[slot]
            visibility = ev.get("visibility_timeout")
            if visibility is None:
                ev = dict(ev)
                ev["visibility_timeout"] = max(30, 6 * int(self.spec["functions"][function].get("timeout") or 30))
            driver = self.broker.queue_driver(queue)
            try:
                if driver is not None and now - self._last_recover >= 5:
                    driver.recover(now, float(ev.get("visibility_timeout") or 30))
                claimed = self.broker.claim_queue(ev, now)
            except Exception as exc:  # noqa: BLE001 - an unreachable queue must not stop the others
                self._note(f"queue {queue}: {exc}")
                continue
            if not claimed:
                continue
            self._rr[queue] = slot + 1
            records = [
                Record(
                    id=msg.get("id"),
                    body=msg.get("body"),
                    attributes=dict(msg.get("attributes") or {}),
                    source="onprem.queue",
                )
                for msg in claimed
            ]
            failed: List[str]
            try:
                result = self.invoke(function, Event(type=EventType.QUEUE, records=records, source="onprem.queue"))
            except Exception as exc:  # noqa: BLE001
                self._note(f"queue {queue} -> {function} failed: {exc}")
                failed = [str(msg.get("id")) for msg in claimed]
            else:
                failed = list(result.failed) if isinstance(result, BatchResult) else []
            try:
                self.broker.settle_queue(ev, claimed, failed, now)
            except Exception as exc:  # noqa: BLE001
                self._note(f"queue {queue}: could not settle messages: {exc}")
        if now - self._last_recover >= 5:
            self._last_recover = now

    def pump_topics(self, now: float) -> None:
        del now
        groups: Dict[str, List[Tuple[str, Dict[str, Any]]]] = {}
        for name, fn in (self.spec.get("functions") or {}).items():
            for ev in fn.get("events") or []:
                if ev.get("type") == "topic":
                    groups.setdefault(ev["name"], []).append((name, ev))
        for topic, consumers in groups.items():
            for msg in self.broker.claim_topic(topic):
                already = set(msg.get("delivered") or [])
                body = msg.get("body")
                try:
                    parsed = json.loads(body) if isinstance(body, str) else body
                except ValueError:
                    parsed = body
                delivered: List[str] = []
                pending = False
                for function, ev in consumers:
                    if function in already:
                        delivered.append(function)
                        continue
                    if not _filter_match(ev.get("filter"), dict(msg.get("attributes") or {}), parsed):
                        delivered.append(function)
                        continue
                    record = Record(
                        id=msg.get("id"),
                        body=body,
                        attributes=dict(msg.get("attributes") or {}),
                        source="onprem.topic",
                    )
                    try:
                        self.invoke(function, Event(type=EventType.TOPIC, records=[record], source="onprem.topic"))
                    except Exception as exc:  # noqa: BLE001
                        self._note(f"topic {topic} -> {function} failed: {exc}")
                        pending = True
                    else:
                        delivered.append(function)
                self.broker.settle_topic(msg, delivered, done=not pending)

    def pump_storage(self, now: float) -> None:
        del now
        listeners: Dict[str, List[Tuple[str, Dict[str, Any]]]] = {}
        for name, fn in (self.spec.get("functions") or {}).items():
            for ev in fn.get("events") or []:
                if ev.get("type") == "storage":
                    listeners.setdefault(ev["bucket"], []).append((name, ev))
        changed = False
        for bucket, consumers in listeners.items():
            try:
                current = self.broker.scan_bucket(bucket)
            except Exception as exc:  # noqa: BLE001 - e.g. S3 endpoint unreachable
                self._note(f"storage {bucket}: {exc}")
                continue
            previous = self._snapshot.get(bucket) or {}
            events: List[Tuple[str, str, int]] = []
            for key, (mtime, size) in current.items():
                old = previous.get(key)
                if old is None or old != (mtime, size):
                    events.append((key, "created", size))
            for key in previous:
                if key not in current:
                    events.append((key, "deleted", 0))
            if not events:
                self._snapshot[bucket] = current
                continue
            ok = True
            for function, ev in consumers:
                wanted = set(ev.get("events") or ["created"])
                records = [
                    Record(id=f"{bucket}/{key}", bucket=bucket, key=key, size=size, action=action, source="onprem.storage")
                    for key, action, size in events
                    if action in wanted and _key_selected(key, ev)
                ]
                if not records:
                    continue
                try:
                    self.invoke(function, Event(type=EventType.STORAGE, records=records, source="onprem.storage"))
                except Exception as exc:  # noqa: BLE001
                    self._note(f"storage {bucket} -> {function} failed: {exc}")
                    ok = False
            if ok:
                self._snapshot[bucket] = current
                changed = True
        if changed:
            self._save_snapshot()

    def _note(self, text: str) -> None:
        if text in self.notes:
            return
        self.notes.append(text)
        del self.notes[:-50]
        self.logs.append("WARNING", "host", text)

    # ---------------------------------------------------------------- http
    def make_server(self, port: Optional[int] = None) -> ThreadingHTTPServer:
        bind = str(self.spec.get("host") or "127.0.0.1")
        chosen = int(self.spec.get("port") or 8080) if port is None else port
        httpd = _Server((bind, chosen), self._handler())
        httpd.host = self  # type: ignore[attr-defined]
        return httpd

    def serve_forever(self) -> None:
        if not self._booted:
            self.open()
        self.capture_output()
        # A web replica has no schedules or built-in queues to poll: the main replica runs those triggers.
        loop = self._ship_loop if self.role == "web" else self._poll_loop
        threading.Thread(target=loop, name="pskit-onprem", daemon=True).start()
        if self.log_url:
            threading.Thread(target=self._ship_loop, name="pskit-onprem-ship", daemon=True).start()
        server = self.make_server()
        bound = server.server_address
        role = "" if self.role == "all" else f" as the {self.role} replica ({self.replica})"
        if self.peers is not None:
            role += f" (group {self.peers.group})"
        self.logs.append("INFO", "host", f"listening on {bound[0]!s}:{bound[1]}{role}")
        try:
            server.serve_forever()
        finally:
            self._stop.set()
            if self.executor is not None:
                self.executor.shutdown()
            self.close_workers()
            server.server_close()
            self.logs.close()

    def _poll_loop(self) -> None:
        interval = float(self.spec.get("poll_seconds") or 0.5)
        while not self._stop.wait(interval):
            try:
                self.pump()
            except Exception as exc:  # noqa: BLE001
                self._note(f"pump failed: {exc}")

    def _ship_loop(self) -> None:
        while not self._stop.wait(1.0):
            self.ship_logs()

    def ship_logs(self) -> bool:
        """web replica (to the main replica) or a group other than the default one (to the default group's host):
        send new log entries and invocation counts, so logs and stats stay in one place."""
        page = self.logs.query(since=self._shipped, limit=500)
        entries = page.get("entries") or []
        with self._stats_lock:
            invocations, self._unshipped = self._unshipped, []
        if not entries and not invocations:
            return True
        group = self.peers.group if self.peers is not None else ""
        body = dumps({"replica": self.replica, "group": group, "entries": entries,
                      "invocations": invocations}).encode("utf-8")
        target = self.main_url or self.log_url
        token = str(self.spec.get("admin_token") or "") if self.main_url else str(self.spec.get("peer_token") or "")
        try:
            status, _headers, _raw = main_request(
                target, token, "POST", "/__pskit/logs/ingest", body, {"content-type": "application/json"},
            )
        except OSError:
            status = 0
        if status == 200:
            if entries:
                self._shipped = int(entries[-1]["seq"])
            return True
        with self._stats_lock:  # the main replica is restarting: keep the counts (bounded) and retry
            self._unshipped = (invocations + self._unshipped)[-5000:]
        return False

    def requests(self, since: int = 0, limit: int = 200) -> Dict[str, Any]:
        """Recent invocations (HTTP requests and other events), oldest first, with the replica and server that ran
        each one: the live request view. Poll with ``since=next``."""
        page = self.logs.query(since=since, limit=limit, source="invocation")
        items = []
        for entry in page.get("entries") or []:
            fields = entry.get("fields") or {}
            items.append({
                "seq": entry.get("seq"), "ts": entry.get("ts"), "function": entry.get("function"),
                "level": entry.get("level"), "request_id": entry.get("request_id"),
                **{k: fields.get(k) for k in ("event_type", "method", "path", "status", "duration_ms", "error",
                                              "replica", "node")},
            })
        return {"items": items, "next": page.get("next"), "role": self.role, "replica": self.replica,
                "node": self.node}

    def ingest_logs(self, payload: Any) -> Dict[str, Any]:
        """main: log entries and invocation counts sent by a web replica."""
        if not isinstance(payload, dict):
            raise ValueError("send {replica, entries, invocations}")
        replica = str(payload.get("replica") or "web")[:120]
        group = str(payload.get("group") or "")[:40]
        added = 0
        for entry in payload.get("entries") or []:
            if not isinstance(entry, dict):
                continue
            fields = dict(entry.get("fields") or {})
            fields.setdefault("replica", replica)
            if group:
                fields.setdefault("group", group)
            self.logs.append(
                str(entry.get("level") or "INFO"), str(entry.get("source") or "host"), str(entry.get("message") or ""),
                function=entry.get("function") or None, request_id=entry.get("request_id") or None, fields=fields,
            )
            added += 1
        for item in payload.get("invocations") or []:
            if isinstance(item, dict) and item.get("function"):
                self._count(str(item["function"]), float(item.get("duration_ms") or 0), bool(item.get("failed")),
                            str(item.get("error") or ""), ship=bool(self.log_url))
        return {"entries": added}

    def _handler(self):
        host = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "pskit-onprem"
            protocol_version = "HTTP/1.1"

            def log_message(self, fmt: str, *args: Any) -> None:
                return None

            def _send(self, status: int, headers: Dict[str, str], body: bytes, cookies: Optional[List[str]] = None) -> None:
                self.send_response(status)
                for key, value in headers.items():
                    self.send_header(key, value)
                for cookie in cookies or []:
                    self.send_header("set-cookie", cookie)
                self.send_header("content-length", str(len(body)))
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(body)

            def _json(self, status: int, payload: Any) -> None:
                self._send(status, {"content-type": "application/json"}, dumps(payload).encode("utf-8"))

            def _read(self) -> bytes:
                length = int(self.headers.get("content-length") or 0)
                if length > _MAX_BODY:
                    raise ValueError("request body is too large")
                return self.rfile.read(length) if length else b""

            def _admin_ok(self) -> bool:
                token = str(host.spec.get("admin_token") or "")
                if not token:
                    return True
                sent = self.headers.get("x-pskit-token")
                peer = str(host.spec.get("peer_token") or "")
                return sent == token or bool(peer and sent == peer)

            @property
            def _from_peer(self) -> bool:
                """A call from another group of this project (it is never forwarded again)."""
                return host.peers is not None and bool(self.headers.get(HOP_HEADER))

            def do_GET(self) -> None:  # noqa: N802
                self._route()

            def do_POST(self) -> None:  # noqa: N802
                self._route()

            def do_PUT(self) -> None:  # noqa: N802
                self._route()

            def do_DELETE(self) -> None:  # noqa: N802
                self._route()

            def do_HEAD(self) -> None:  # noqa: N802
                self._route()

            def do_OPTIONS(self) -> None:  # noqa: N802
                self._route()

            def do_PATCH(self) -> None:  # noqa: N802
                self._route()

            def _route(self) -> None:
                try:
                    url = urlsplit(self.path)
                    if url.path == "/__pskit/health" or url.path == "/__pskit":
                        return self._json(200, host.health())
                    if url.path == "/__pskit/logs/local":
                        return self._local_logs(url)
                    # AWS-compatible APIs: existing boto3 / AWS SDK code only changes endpoint_url.
                    if url.path.startswith("/2015-03-31/functions/"):
                        return self._lambda(url.path)
                    target = self.headers.get("x-amz-target") or ""
                    if host.role == "web" and (
                        (url.path.startswith("/__pskit/") and url.path.split("/")[2] not in _WEB_LOCAL)
                        or (self.command == "POST" and target.startswith("AmazonSQS."))
                    ):
                        return self._to_main()
                    if self.command == "POST" and target.startswith("AmazonSQS."):
                        return self._sqs(target.split(".", 1)[1])
                    if url.path.startswith("/__pskit/"):
                        if not self._admin_ok():
                            # Drain the body first: closing with unread data resets the connection (Windows).
                            self._read()
                            return self._json(401, {"error": "admin token required"})
                        return self._admin(url)
                    self._user(url)
                except ValueError as exc:
                    self._json(400, {"error": str(exc)})
                except KeyError as exc:
                    self._json(404, {"error": str(exc.args[0] if exc.args else exc)})
                except Exception as exc:  # noqa: BLE001 - last-resort response
                    self._json(500, {"errorType": type(exc).__name__, "cause": str(exc)})

            def _to_main(self) -> None:
                """web replica: the main replica answers (state, logs, executions and the SQS API live there)."""
                raw = self._read()
                keep = ("content-type", "accept", "prefer", "x-pskit-wait", "x-pskit-token", "x-amz-target", "authorization")
                headers = {k: self.headers.get(k) or "" for k in keep}
                body = raw if raw or self.command in ("POST", "PUT", "PATCH") else None
                try:
                    status, reply, data = main_request(host.main_url, "", self.command, self.path, body, headers,
                                                       timeout=24 * 3600)
                except OSError as exc:
                    reason = getattr(exc, "reason", exc)
                    return self._json(503, {"error": f"the main replica is not reachable: {reason}"})
                passed = {k: v for k, v in reply.items() if k.lower() in ("content-type", "x-amzn-errortype", "x-amzn-query-error")}
                self._send(status, passed or {"content-type": "application/json"}, data)

            def _admin(self, url: Any) -> None:
                parts = [unquote(part) for part in url.path.split("/") if part][1:]
                query = dict(parse_qsl(url.query, keep_blank_values=True))
                raw = self._read()
                if parts == ["logs", "ingest"]:
                    if self.command != "POST":
                        return self._json(405, {"error": "POST log entries"})
                    return self._json(200, host.ingest_logs(json.loads(raw.decode("utf-8") or "null")))
                if parts == ["logs"]:
                    return self._logs(query)
                if parts == ["logs", "streams"]:
                    if self.command != "GET":
                        return self._json(405, {"error": "GET log streams"})
                    return self._json(200, {"items": host.logs.functions()})
                if parts == ["stats"]:
                    return self._json(200, host.stats())
                if parts == ["requests"]:
                    if self.command != "GET":
                        return self._json(405, {"error": "GET the recent requests"})
                    return self._json(200, host.requests(_int_arg(query, "since", 0),
                                                         min(500, _int_arg(query, "limit", 200))))
                if len(parts) == 2 and parts[0] == "smtp":
                    if self.command != "POST":
                        return self._json(405, {"error": "POST the mail"})
                    try:
                        mail = json.loads(raw.decode("utf-8"))
                    except ValueError:
                        return self._json(400, {"error": "the mail must be JSON"})
                    return self._json(*host.deliver_mail(parts[1], mail, from_peer=self._from_peer))
                if parts and parts[0] == "executions":
                    return self._executions(parts[1:], query)
                if parts == ["resources"]:
                    if self.command != "GET":
                        return self._json(405, {"error": "GET the resource list"})
                    return self._json(200, host.resources())
                if len(parts) == 3 and parts[0] == "resources" and parts[2] in ("check", "data", "object", "message"):
                    return self._resource_admin(parts[1], parts[2], query)
                if parts and parts[0] == "queues" and len(parts) == 3 and parts[2] == "peek":
                    page = host.broker.peek_queue(
                        parts[1], _int_arg(query, "offset", 0), min(500, _int_arg(query, "limit", 50)), time.time()
                    )
                    return self._json(200, page)
                if parts and parts[0] == "queues" and len(parts) == 2:
                    return self._queue(parts[1], raw)
                if parts and parts[0] == "queues" and len(parts) == 3 and parts[2] in ("lease", "ack", "nack"):
                    return self._lease(parts[1], parts[2], raw)
                if parts and parts[0] == "topics" and len(parts) == 2:
                    return self._topic(parts[1], raw)
                if parts and parts[0] == "storage" and len(parts) == 2 and self.command == "GET":
                    page = host.broker.list_bucket(
                        parts[1], _int_arg(query, "offset", 0), min(1000, _int_arg(query, "limit", 100)), query.get("prefix") or ""
                    )
                    return self._json(200, {"bucket": parts[1], **page})
                if parts and parts[0] == "storage" and len(parts) >= 3:
                    return self._storage(parts[1], "/".join(parts[2:]), raw)
                if parts and parts[0] == "invoke" and len(parts) == 2:
                    return self._invoke(parts[1], raw)
                if parts and parts[0] == "peer" and len(parts) == 2:
                    if self.command != "POST":
                        return self._json(405, {"error": "POST an event"})
                    return self._json(200, run_peer_call(host, parts[1], raw))
                if parts and parts[0] == "workflows" and len(parts) == 2:
                    return self._workflow(parts[1], raw, query)
                self._json(404, {"error": "unknown on-prem endpoint"})

            def _local_logs(self, url: Any) -> None:
                """This process's buffer. A web replica does not forward this route."""
                if self.command != "GET":
                    self._read()
                    return self._json(405, {"error": "GET this replica's logs"})
                if not self._admin_ok():
                    self._read()
                    return self._json(401, {"error": "admin token required"})
                query = dict(parse_qsl(url.query, keep_blank_values=True))
                result = host.logs.query(
                    since=_int_arg(query, "since", 0),
                    limit=_int_arg(query, "limit", 200),
                    level=query.get("level") or None,
                    function=query.get("function") or None,
                    q=query.get("q") or None,
                    source=query.get("source") or None,
                    before=_int_arg(query, "before", 0) or None,
                )
                result["replica"] = host.replica
                result["node"] = host.node
                result["role"] = host.role
                self._json(200, result)

            def _logs(self, query: Dict[str, str]) -> None:
                if self.command == "DELETE":
                    removed = host.logs.clear(query.get("function") or None)
                    return self._json(200, {"deleted": removed})
                if self.command != "GET":
                    return self._json(405, {"error": "GET or DELETE logs"})
                result = host.logs.query(
                    since=_int_arg(query, "since", 0),
                    limit=_int_arg(query, "limit", 200),
                    level=query.get("level") or None,
                    function=query.get("function") or None,
                    q=query.get("q") or None,
                    source=query.get("source") or None,
                    before=_int_arg(query, "before", 0) or None,
                )
                return self._json(200, result)

            def _executions(self, rest: List[str], query: Dict[str, str]) -> None:
                executor = host.executor
                if executor is None:
                    return self._json(503, {"error": "workflow executor is not running"})
                if not rest:
                    if self.command != "GET":
                        return self._json(405, {"error": "GET the execution list"})
                    listed = executor.list(
                        workflow=query.get("workflow") or None,
                        status=query.get("status") or None,
                        limit=_int_arg(query, "limit", 20),
                        offset=_int_arg(query, "offset", 0),
                    )
                    return self._json(200, listed)
                execution_id = rest[0]
                if not valid_id(execution_id):
                    return self._json(404, {"error": f"unknown execution {execution_id!r}"})
                if len(rest) == 2 and rest[1] == "cancel":
                    if self.command != "POST":
                        return self._json(405, {"error": "POST to cancel"})
                    record = executor.cancel(execution_id)
                elif len(rest) == 1:
                    record = executor.get(execution_id)
                else:
                    return self._json(404, {"error": "unknown on-prem endpoint"})
                if record is None:
                    return self._json(404, {"error": f"unknown execution {execution_id!r}"})
                return self._json(200, record)

            def _queue(self, name: str, raw: bytes) -> None:
                if self.command == "GET":
                    return self._json(200, {"queue": name, "depth": host.broker.queue_depth(name)})
                if self.command != "POST":
                    return self._json(405, {"error": "POST a JSON message"})
                payload = json.loads(raw.decode("utf-8") or "null")
                local = {"local": True} if self._from_peer else {}
                ids = [host.broker.submit_queue(name, message, attrs, **local) for message, attrs in _messages_of(payload)]
                return self._json(202, {"queued": ids})

            # ------------------------------------------------------------ AWS-compatible APIs
            def _aws_ok(self) -> bool:
                """No token, the pskit header, or the token used as the AWS access key id (SigV4 credential)."""
                token = str(host.spec.get("admin_token") or "")
                if not token or self.headers.get("x-pskit-token") == token:
                    return True
                return f"Credential={token}/" in (self.headers.get("authorization") or "")

            def _aws_error(self, status: int, code: str, message: str, query_code: str = "") -> None:
                headers = {"content-type": "application/x-amz-json-1.0", "x-amzn-errortype": code}
                if query_code:
                    headers["x-amzn-query-error"] = f"{query_code};Sender"
                body = {"__type": f"com.amazonaws.sqs#{code}" if query_code else code, "message": message, "Message": message}
                self._send(status, headers, dumps(body).encode("utf-8"))

            def _lambda(self, path: str) -> None:
                """``POST /2015-03-31/functions/<name|ARN>/invocations`` (the Lambda Invoke API)."""
                raw = self._read()
                parts = path.split("/")
                if self.command != "POST" or len(parts) != 5 or parts[4] != "invocations":
                    return self._aws_error(404, "ResourceNotFoundException", "only Invoke is supported")
                if not self._aws_ok():
                    return self._aws_error(403, "AccessDeniedException", "use the host's admin_token as aws_access_key_id")
                name = host.function_for(unquote(parts[3]))
                if name is None:
                    return self._aws_error(404, "ResourceNotFoundException", f"Function not found: {unquote(parts[3])}")
                try:
                    payload = json.loads(raw.decode("utf-8")) if raw else None
                except ValueError:
                    return self._aws_error(400, "InvalidRequestContentException", "the payload must be JSON")
                if isinstance(payload, dict) and payload.get("__pskit") == "invoke":
                    payload = payload.get("data")
                kind = self.headers.get("x-amz-invocation-type") or "RequestResponse"
                if kind == "DryRun":
                    return self._send(204, {}, b"")
                event = Event(type=EventType.INVOKE, data=payload, source="onprem.lambda")
                if kind == "Event":

                    def run() -> None:
                        try:
                            host.invoke(name, event)
                        except Exception as exc:  # noqa: BLE001 - asynchronous: logged as a host note
                            host._note(f"async invoke of {name} failed: {exc}")

                    threading.Thread(target=run, name=f"pskit-event-{name}", daemon=True).start()
                    return self._send(202, {"content-type": "application/json"}, b"")
                headers = {"content-type": "application/json", "x-amz-executed-version": "$LATEST"}
                try:
                    result = host.invoke(name, event)
                except Exception as exc:  # noqa: BLE001 - Lambda reports handler errors with status 200
                    error = {"errorMessage": str(exc), "errorType": type(exc).__name__}
                    return self._send(200, dict(headers, **{"x-amz-function-error": "Unhandled"}), dumps(error).encode())
                if isinstance(result, Response):
                    _status, _h, body = result.render()
                    return self._send(200, headers, body)
                return self._send(200, headers, dumps(result).encode("utf-8"))

            def _sqs(self, action: str) -> None:
                """A subset of the SQS JSON protocol over the host's queues (boto3 with endpoint_url)."""
                raw = self._read()
                if not self._aws_ok():
                    return self._aws_error(403, "AccessDenied", "use the host's admin_token as aws_access_key_id")
                try:
                    req = json.loads(raw.decode("utf-8") or "{}")
                except ValueError:
                    return self._aws_error(400, "InvalidParameterValue", "the body must be JSON", "InvalidParameterValue")
                base = f"http://{self.headers.get('host') or '127.0.0.1'}/000000000000/"
                known = host.queue_names()
                if action == "ListQueues":
                    prefix = str(req.get("QueueNamePrefix") or "")
                    return self._json(200, {"QueueUrls": [base + q for q in sorted(known) if q.startswith(prefix)]})
                name = str(req.get("QueueName") or str(req.get("QueueUrl") or "").rstrip("/").rsplit("/", 1)[-1])
                if action == "CreateQueue":
                    return self._json(200, {"QueueUrl": base + name})
                if name not in known:
                    return self._aws_error(400, "QueueDoesNotExist", f"The specified queue {name} does not exist.",
                                           "AWS.SimpleQueueService.NonExistentQueue")
                broker = host.broker
                if action == "GetQueueUrl":
                    return self._json(200, {"QueueUrl": base + name})
                if action == "GetQueueAttributes":
                    depth = broker.queue_depth(name)
                    attrs = {"QueueArn": f"arn:pskit:sqs:{host.spec.get('region') or 'local'}:000000000000:{name}"}
                    if depth >= 0:
                        attrs["ApproximateNumberOfMessages"] = str(depth)
                    return self._json(200, {"Attributes": attrs})
                if action in ("SendMessage", "SendMessageBatch"):
                    entries = req.get("Entries") or [] if action == "SendMessageBatch" else [req]
                    done = []
                    for entry in entries:
                        attributes = {k: v.get("StringValue", v.get("BinaryValue", ""))
                                      for k, v in (entry.get("MessageAttributes") or {}).items() if isinstance(v, dict)}
                        body = str(entry.get("MessageBody") or "")
                        ident = broker.submit_queue(name, body, attributes)
                        done.append({"Id": entry.get("Id"), "MessageId": ident, "MD5OfMessageBody": _md5(body)})
                    if action == "SendMessage":
                        return self._json(200, {"MessageId": done[0]["MessageId"], "MD5OfMessageBody": done[0]["MD5OfMessageBody"]})
                    return self._json(200, {"Successful": done, "Failed": []})
                if action == "ReceiveMessage":
                    batch = max(1, min(int(req.get("MaxNumberOfMessages") or 1), 10))
                    visibility = float(req.get("VisibilityTimeout") or 30)
                    deadline = time.time() + max(0, min(int(req.get("WaitTimeSeconds") or 0), 20))
                    try:
                        leased = broker.lease_queue(name, batch, visibility, time.time())
                        while not leased and time.time() < deadline:
                            time.sleep(0.5)
                            leased = broker.lease_queue(name, batch, visibility, time.time())
                    except ValueError as exc:
                        return self._aws_error(400, "UnsupportedOperation", str(exc), "AWS.SimpleQueueService.UnsupportedOperation")
                    wanted = req.get("MessageAttributeNames") or []
                    out = []
                    for m in leased:
                        body = m["body"] if isinstance(m["body"], str) else json.dumps(m["body"])
                        item: Dict[str, Any] = {
                            "MessageId": m["id"], "ReceiptHandle": m["receipt"], "Body": body, "MD5OfBody": _md5(body),
                            "Attributes": {"ApproximateReceiveCount": str(m["receives"]),
                                           "SentTimestamp": str(int(float(m.get("enqueued_at") or 0) * 1000))},
                        }
                        if wanted and m.get("attributes"):
                            item["MessageAttributes"] = {k: {"DataType": "String", "StringValue": str(v)}
                                                         for k, v in m["attributes"].items()}
                        out.append(item)
                    return self._json(200, {"Messages": out} if out else {})
                if action in ("DeleteMessage", "DeleteMessageBatch"):
                    entries = req.get("Entries") or [] if action == "DeleteMessageBatch" else [req]
                    broker.ack_queue(name, [str(e.get("ReceiptHandle")) for e in entries])
                    if action == "DeleteMessage":
                        return self._json(200, {})
                    return self._json(200, {"Successful": [{"Id": e.get("Id")} for e in entries], "Failed": []})
                if action == "ChangeMessageVisibility":
                    broker.change_visibility(name, str(req.get("ReceiptHandle")), float(req.get("VisibilityTimeout") or 0))
                    return self._json(200, {})
                if action == "PurgeQueue":
                    broker.purge_queue(name)
                    return self._json(200, {})
                return self._aws_error(400, "InvalidAction", f"{action} is not supported by the pskit host",
                                       "AWS.SimpleQueueService.InvalidAction")

            def _resource_admin(self, key: str, action: str, query: Dict[str, str]) -> None:
                if action == "check" and self.command in ("GET", "POST"):
                    return self._json(200, host.check_resource(key))
                if action == "data" and self.command == "GET":
                    page = host.browse_resource(
                        key, _int_arg(query, "offset", 0), _int_arg(query, "limit", 50), query.get("prefix") or ""
                    )
                    return self._json(200, page)
                if action == "data" and self.command == "DELETE":
                    return self._json(200, host.purge_resource(key))
                if action == "object" and self.command == "GET":
                    return self._json(200, host.read_object(key, query.get("key") or ""))
                if action == "object" and self.command == "DELETE":
                    res = host._resource(key)
                    removed = host.broker.delete_object(str(res.get("name") or key), query.get("key") or "")
                    host.pump_storage(time.time())
                    return self._json(200, {"deleted": removed})
                if action == "message" and self.command == "DELETE":
                    res = host._resource(key)
                    return self._json(200, {"deleted": host.broker.delete_message(str(res.get("name") or key), query.get("id") or "")})
                return self._json(405, {"error": f"method not allowed on .../{action}"})

            def _lease(self, name: str, action: str, raw: bytes) -> None:
                if self.command != "POST":
                    return self._json(405, {"error": f"POST to {action}"})
                body = json.loads(raw.decode("utf-8") or "{}")
                if not isinstance(body, dict):
                    raise ValueError("body must be a JSON object")
                now = time.time()
                if action == "lease":
                    batch = int(body.get("batch") or 1)
                    visibility = float(body.get("visibility") or 30)
                    return self._json(200, {"messages": host.broker.lease_queue(name, batch, visibility, now)})
                receipts = body.get("receipts") or []
                if not isinstance(receipts, list):
                    raise ValueError("receipts must be a list")
                if action == "ack":
                    return self._json(200, {"acked": host.broker.ack_queue(name, receipts)})
                return self._json(200, {"released": host.broker.nack_queue(name, receipts, now)})

            def _topic(self, name: str, raw: bytes) -> None:
                if self.command != "POST":
                    return self._json(405, {"error": "POST a JSON message"})
                payload = json.loads(raw.decode("utf-8") or "null")
                local = {"local": True} if self._from_peer else {}
                ids = [host.broker.submit_topic(name, message, attrs, **local) for message, attrs in _messages_of(payload)]
                host.pump_topics(time.time())
                return self._json(202, {"published": ids})

            def _storage(self, bucket: str, key: str, raw: bytes) -> None:
                local = {"local": True} if self._from_peer else {}
                if self.command == "PUT":
                    host.broker.put_object(bucket, key, raw, **local)
                    host.pump_storage(time.time())
                    return self._json(201, {"bucket": bucket, "key": key, "size": len(raw)})
                if self.command == "DELETE":
                    removed = host.broker.delete_object(bucket, key, **local)
                    host.pump_storage(time.time())
                    return self._json(200, {"deleted": removed, "bucket": bucket, "key": key})
                if self.command in ("GET", "HEAD"):
                    try:
                        data = host.broker.get_object(bucket, key, **local)
                    except (FileNotFoundError, KeyError):
                        return self._json(404, {"error": f"no object {key!r} in {bucket}"})
                    return self._send(200, {"content-type": "application/octet-stream"}, data)
                self._json(405, {"error": "GET, PUT or DELETE an object"})

            def _invoke(self, function: str, raw: bytes) -> None:
                try:
                    data = json.loads(raw.decode("utf-8")) if raw else None
                except ValueError:
                    data = raw.decode("utf-8", "replace")
                kind = EventType.INVOKE
                if isinstance(data, dict) and data.get("__pskit") in (EventType.INVOKE, EventType.SCHEDULE):
                    # pskit trigger / the studio's Test send {"__pskit": kind, "data": ...}: the function gets data.
                    kind, data = data["__pskit"], data.get("data")
                try:
                    result = host.invoke(function, Event(type=kind, data=data, source="onprem.invoke"))
                except KeyError as exc:
                    return self._json(404, {"error": str(exc)})
                except Exception as exc:  # noqa: BLE001
                    return self._json(500, {"errorType": type(exc).__name__, "cause": str(exc)})
                if isinstance(result, Response):
                    status, headers, body = result.render()
                    return self._send(status, headers, body, result.cookies)
                self._json(200, {"result": result})

            def _workflow(self, name: str, raw: bytes, query: Dict[str, str]) -> None:
                if self.command != "POST":
                    return self._json(405, {"error": "POST the workflow input"})
                req = HttpRequest(
                    method="POST",
                    path=f"/workflows/{name}",
                    headers=Headers(list(self.headers.items())),
                    query=query,
                    body=raw,
                )
                return self._start_workflow(name, req)

            def _start_workflow(self, name: str, req: HttpRequest) -> None:
                executor = host.executor
                if executor is None or not executor.knows(name):
                    return self._json(404, {"error": f"unknown workflow {name!r}"})
                if req.body:
                    try:
                        data = json.loads(req.body.decode("utf-8"))
                    except ValueError:
                        raise ValueError("workflow input must be JSON") from None
                else:
                    data = {k: v for k, v in req.query.items() if k not in ("wait", "entry")} or None
                entry: Dict[str, Any] = {}
                if str(req.query.get("entry") or "").lower() in ("1", "true", "yes") and isinstance(data, dict):
                    # Another group's host ran the first task's function: the run starts with its result.
                    entry = {"entry_result": data.get("entry_result")}
                    data = data.get("input")
                if not wants_wait(Event(type=EventType.HTTP, http=req)):
                    started = executor.start(name, data, **entry)
                    started["status_url"] = f"/__pskit/executions/{started['execution_id']}"
                    return self._json(202, started)
                record = executor.start(name, data, wait=True, **entry)
                body = executor.result_body(record)
                return self._json(200 if record.get("status") == "SUCCEEDED" else 500, body)

            def _user(self, url: Any) -> None:
                routes = _routes(host)
                for method, pattern, function in routes:
                    params = match_path(pattern, url.path, tolerant=False)
                    if params is None or not (method_matches(method, self.command) or self.command == "OPTIONS"):
                        continue
                    req = HttpRequest(
                        method=self.command,
                        path=url.path,
                        headers=Headers(list(self.headers.items())),
                        query=dict(parse_qsl(url.query, keep_blank_values=True)),
                        path_params=params,
                        body=self._read(),
                        source_ip=self.client_address[0],
                        route=pattern,
                    )
                    elsewhere = None if self._from_peer else host.served_elsewhere(function)
                    if elsewhere is not None:
                        # Its code is not on this server: say where it runs instead of passing it on.
                        group, base = elsewhere
                        return self._json(404, {
                            "error": "Not Found",
                            "message": f"{function} runs on group {group}, not on this server ({host.group})",
                            "url": base.rstrip("/") + self.path,
                        })
                    workflow = host.orchestrated(function)
                    if workflow is not None and self.command == "POST":
                        # Through the executor directly: tracked, async by default, no env lock held.
                        return self._start_workflow(workflow, req)
                    resp = host.invoke(function, Event(type=EventType.HTTP, http=req), from_peer=self._from_peer)
                    if not isinstance(resp, Response):
                        resp = Response.json(resp)
                    status, headers, body = resp.render()
                    return self._send(status, headers, body, resp.cookies)
                self._json(404, {"error": "Not Found", "routes": [f"{m} {p}" for m, p, _ in routes]})

        return Handler

    def resources(self) -> Dict[str, Any]:
        """Each ``resources:`` entry with its backend and, for queues, the current depth."""
        consumers: Dict[str, List[str]] = {}
        for fname, fn in (self.spec.get("functions") or {}).items():
            for ev in fn.get("events") or []:
                target = ev.get("bucket") if ev.get("type") == "storage" else ev.get("name")
                if ev.get("type") in ("queue", "storage", "topic") and target:
                    consumers.setdefault(f"{ev['type']}:{target}", []).append(fname)
        items = []
        for key, res in sorted((self.spec.get("resources") or {}).items()):
            if not isinstance(res, dict):
                continue
            kind = str(res.get("type") or "")
            name = str(res.get("name") or key)
            raw_driver = res.get("driver")
            driver: Dict[str, Any] = raw_driver if isinstance(raw_driver, dict) else {}
            item: Dict[str, Any] = {
                "key": key,
                "type": kind,
                "name": name,
                "external": bool(res.get("external")),
                "driver": str(driver.get("use") or ("builtin" if kind in ("queue", "storage", "topic") else "")),
                "functions": list(res.get("functions") or []),
                "consumers": consumers.get(f"{kind}:{name}", []),
            }
            if kind == "queue":
                try:
                    depth = self.broker.queue_depth(name)
                    item["depth"] = depth if depth >= 0 else None
                except Exception as exc:  # noqa: BLE001 - a remote queue may be down
                    item["depth"] = None
                    item["error"] = str(exc)
            elif kind == "storage" and item["driver"] in ("builtin", "directory"):
                item["path"] = str(self.broker.bucket_dir(name))
            items.append(item)
        return {"items": items}

    def deliver_mail(self, server: str, mail: Any, from_peer: bool = False) -> Tuple[int, Dict[str, Any]]:
        """Run every function with an ``smtp`` trigger on resource ``server`` with ``mail`` (from the smtp service).

        ``(200, results)`` when all succeeded; ``500`` when one failed and ``404`` when none listens, so the SMTP
        service answers 451 and the sending server retries later.
        """
        if not isinstance(mail, dict):
            return 400, {"error": "the mail must be a JSON object"}
        listeners = [
            name for name, fn in (self.spec.get("functions") or {}).items()
            if any(ev.get("type") == "smtp" and server in (ev.get("resource"), ev.get("name"))
                   for ev in fn.get("events") or [])
        ]
        summary = (f"mail {mail.get('id') or ''} from {mail.get('from') or '?'} to "
                   f"{', '.join((mail.get('envelope') or {}).get('rcpt_to') or mail.get('to') or [])} "
                   f"{json.dumps(str(mail.get('subject') or ''))}")
        fields = {"server": server, "from": mail.get("from"), "to": mail.get("to"), "subject": mail.get("subject"),
                  "attachments": [a.get("filename") for a in mail.get("attachments") or [] if isinstance(a, dict)]}
        others = [] if from_peer or self.peers is None else [
            g for g in self.peers.subscribers("smtp", server) if g != self.peers.group]
        if not listeners and not others:
            self.logs.append("WARNING", "smtp", f"{summary}: no function has an smtp trigger on {server!r}",
                             fields=fields)
            return 404, {"error": f"no function has an smtp trigger on {server!r}"}
        results: Dict[str, Any] = {}
        for group in others:  # functions on this SMTP server in other groups run there
            try:
                assert self.peers is not None
                reply = self.peers.call(group, "POST", f"/__pskit/smtp/{quote(server, safe='')}", mail)
                results.update((reply or {}).get("delivered") or {})
            except Exception as exc:  # noqa: BLE001 - the SMTP service makes the sender retry
                results[f"group {group}"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        for name in listeners:
            self.logs.append("INFO", "smtp", f"{summary} -> {name}", function=name, fields=fields)
            try:
                self.invoke(name, Event(type=EventType.SMTP, data=mail, source=f"onprem.smtp.{server}"))
                results[name] = {"ok": True}
            except Exception as exc:  # noqa: BLE001 - reported to the SMTP service, which makes the sender retry
                results[name] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
                self.logs.append("ERROR", "smtp", f"{summary} -> {name} failed: {type(exc).__name__}: {exc}",
                                 function=name, fields=fields)
        ok = all(r["ok"] for r in results.values())
        return (200 if ok else 500), {"delivered": results}

    def function_for(self, name: str) -> Optional[str]:
        """This host's function for a pskit name, a deployed name or a Lambda ARN (None if unknown)."""
        text = str(name)
        if text.startswith("arn:"):
            parts = text.split(":")
            text = parts[6] if len(parts) > 6 and parts[5] == "function" else parts[-1]
        functions = self.spec.get("functions") or {}
        if text in functions:
            return text
        prefix = "-".join(p for p in (str(self.spec.get("service") or ""), str(self.spec.get("stage") or "")) if p) + "-"
        if text.startswith(prefix) and text[len(prefix):] in functions:
            return text[len(prefix):]
        return None

    def queue_names(self) -> List[str]:
        """Queues this host knows: queue resources, queue triggers and their dead-letter queues."""
        names = {str(r.get("name")) for r in (self.spec.get("resources") or {}).values()
                 if isinstance(r, dict) and r.get("type") == "queue" and r.get("name")}
        for ev in self._events("queue"):
            names.add(str(ev["name"]))
            if ev.get("dead_letter"):
                names.add(str(ev["dead_letter"]))
        return sorted(names)

    def _resource(self, key: str) -> Dict[str, Any]:
        res = (self.spec.get("resources") or {}).get(key)
        if not isinstance(res, dict):
            known = ", ".join(sorted(self.spec.get("resources") or {})) or "<none>"
            raise KeyError(f"unknown resource {key!r}; known: {known}")
        return res

    def connection_values(self, key: str) -> Dict[str, str]:
        """Connection values of resource ``key`` as handlers see them, ``<name>_env`` resolved."""
        prefix = "PSKIT_RESOURCE_" + "".join(c if c.isalnum() else "_" for c in key).upper() + "_"
        res = self._resource(key)
        names = list(res.get("functions") or []) + list(self.spec.get("functions") or {})
        values: Dict[str, str] = {}
        for fname in names:
            env = (self.spec.get("functions") or {}).get(fname, {}).get("environment") or {}
            found = {k[len(prefix) :].lower(): str(v) for k, v in env.items() if k.startswith(prefix)}
            if found:
                values = found
                break
        for name in list(values):
            if name.endswith("_env") and values[name] in os.environ and not values.get(name[:-4]):
                values[name[:-4]] = os.environ[values[name]]
        return values

    def check_resource(self, key: str) -> Dict[str, Any]:
        """Is the resource reachable from this host? Queues report depth, buckets their object count."""
        from .drivers.probe import probe

        res = self._resource(key)
        kind = str(res.get("type") or "")
        name = str(res.get("name") or key)
        started = time.monotonic()
        try:
            if kind == "queue":
                depth = self.broker.queue_depth(name)
                detail = f"queue {name} is reachable" + (f"; {depth} message(s) waiting" if depth >= 0 else "")
            elif kind == "storage":
                detail = f"bucket {name} is reachable; {len(self.broker.scan_bucket(name))} object(s)"
            elif kind == "topic":
                detail = f"topic {name} uses the folder {self.broker.topic_dir(name)}"
            else:
                detail = probe(self.connection_values(key))
            ok = True
        except Exception as exc:  # noqa: BLE001 - the answer is the error
            ok, detail = False, f"{type(exc).__name__}: {exc}"
        ms = round((time.monotonic() - started) * 1000, 1)
        return {"key": key, "type": kind, "name": name, "ok": ok, "detail": detail, "ms": ms, "checked_from": "host"}

    def browse_resource(self, key: str, offset: int = 0, limit: int = 50, prefix: str = "") -> Dict[str, Any]:
        """A page of what the resource holds: messages (queue / topic) or objects (storage)."""
        res = self._resource(key)
        kind = str(res.get("type") or "")
        name = str(res.get("name") or key)
        offset, limit = max(0, int(offset)), max(1, min(int(limit), 500))
        base = {"key": key, "type": kind, "name": name, "offset": offset, "limit": limit}
        if kind == "queue":
            page = self.broker.peek_queue(name, offset, limit, time.time())
        elif kind == "topic":
            page = self.broker.peek_topic(name, offset, limit)
        elif kind == "storage":
            page = self.broker.list_bucket(name, offset, limit, prefix)
        else:
            page = {"supported": False, "total": None, "items": [],
                    "note": f"pskit does not browse {kind} resources; connect with the client shown in How to use"}
        return {**base, **page}

    def read_object(self, key: str, object_key: str, max_bytes: int = 256 * 1024) -> Dict[str, Any]:
        res = self._resource(key)
        if res.get("type") != "storage":
            raise ValueError(f"{key} is not a storage resource")
        data = self.broker.get_object(str(res.get("name") or key), object_key)
        head = data[:max_bytes]
        try:
            content, encoding = head.decode("utf-8"), "text"
        except UnicodeDecodeError:
            content, encoding = base64.b64encode(head).decode("ascii"), "base64"
        return {"key": object_key, "size": len(data), "encoding": encoding, "content": content,
                "truncated": len(data) > max_bytes}

    def purge_resource(self, key: str) -> Dict[str, Any]:
        """Delete the data of a built-in / directory queue, bucket or topic (the folder stays)."""
        res = self._resource(key)
        kind = str(res.get("type") or "")
        name = str(res.get("name") or key)
        driver = res.get("driver") if isinstance(res.get("driver"), dict) else {}
        use = str((driver or {}).get("use") or "builtin")
        if kind not in ("queue", "storage", "topic"):
            raise ValueError(f"{kind} resources keep no data on the host")
        if use not in ("builtin", "directory"):
            raise ValueError(f"{key} keeps its data in {use}; delete it there (or remove the on-prem service)")
        if kind == "queue":
            folder = self.broker.queue_dir(name) / "messages"
        elif kind == "topic":
            folder = self.broker.topic_dir(name) / "pending"
        else:
            folder = self.broker.bucket_dir(name)
        removed = 0
        with self.broker._lock:
            if folder.is_dir():
                for path in sorted(folder.rglob("*"), reverse=True):
                    if path.is_file():
                        path.unlink()
                        removed += 1
                    elif path.is_dir():
                        path.rmdir()
        if kind == "storage":
            self._snapshot[name] = {}
            self._save_snapshot()
        return {"key": key, "deleted": removed, "path": str(folder)}

    def health(self) -> Dict[str, Any]:
        manifest = getattr(self, "manifest", None)
        return {
            "ok": True,
            "service": self.spec.get("service"),
            "stage": self.spec.get("stage"),
            "endpoint": self.spec.get("endpoint"),
            "pid": os.getpid(),
            "role": self.role,
            "replica": self.replica,
            **({"group": self.peers.group, "default_group": self.peers.default, "groups": sorted(self.peers.urls)}
               if self.peers is not None else {}),
            "started_at": datetime.fromtimestamp(self.started_at, timezone.utc).isoformat(timespec="seconds"),
            "workflows": sorted((manifest.workflows if manifest else None) or {}),
            "services": {
                kind: {"use": (svc or {}).get("use"), "path": (svc or {}).get("path")}
                for kind, svc in (self.spec.get("services") or {}).items()
            },
            "notes": list(self.notes),
        }


class NodeFunctionError(RuntimeError):
    """A Node.js handler failed outside an HTTP request (the worker answered ``ok: false``)."""

    def __init__(self, error: Dict[str, Any]) -> None:
        self.error_type = str(error.get("type") or "Error")
        self.stack = str(error.get("stack") or "")
        super().__init__(f"{self.error_type}: {error.get('message') or ''}")


def node_result(reply: Dict[str, Any]) -> Any:
    """Worker response (``deploy_docs/NODE_RUNTIME.md``) -> what the Python dispatcher would return."""
    if not reply.get("ok"):
        raise NodeFunctionError(dict(reply.get("error") or {}))
    kind = reply.get("kind")
    if kind == "http":
        body = base64.b64decode(reply.get("body_b64") or "")
        headers: Dict[str, Any] = {}
        cookies: List[str] = []
        for key, value in dict(reply.get("headers") or {}).items():
            if isinstance(value, list):
                if key.lower() == "set-cookie":
                    cookies.extend(str(v) for v in value)
                else:
                    headers[key] = ", ".join(str(v) for v in value)
            else:
                headers[key] = str(value)
        return Response(int(reply.get("status") or 200), body, headers, cookies)
    if kind == "batch":
        return BatchResult(failed=[str(i) for i in reply.get("failed") or []])
    return reply.get("value")


def _empty_stats() -> Dict[str, Any]:
    return {
        "invocations": 0,
        "errors": 0,
        "total_ms": 0.0,
        "last_duration_ms": None,
        "last_at": None,
        "last_error": None,
    }


def _int_arg(query: Dict[str, str], key: str, default: int) -> int:
    raw = query.get(key)
    if raw in (None, ""):
        return default
    try:
        return int(str(raw))
    except ValueError:
        raise ValueError(f"{key} must be an integer") from None


def _routes(host: Host) -> List[Tuple[str, str, str]]:
    routes = []
    functions = host.manifest.functions if getattr(host, "manifest", None) else {}
    for name, spec in functions.items():
        for route in spec.routes:
            routes.append((route.method, route.path, name))
    routes.sort(key=lambda item: (item[1].count("{"), -len(item[1])))
    return routes


class _Server(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def activate_layout(root: Path) -> None:
    """Swap ``staging`` (written by package) into ``app`` (what the host runs)."""
    root = Path(root)
    staging = root / "staging"
    app = root / "app"
    if not staging.is_dir():
        if not app.is_dir():
            raise FileNotFoundError(f"on-prem bundle is missing under {root}")
        return
    if app.exists():
        shutil.rmtree(app)
    try:
        staging.rename(app)
    except OSError:
        # Windows will not rename a tree the current process already imported.
        shutil.copytree(staging, app)
        shutil.rmtree(staging, ignore_errors=True)


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes

        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def stop(root: Path) -> int:
    root = Path(root)
    pidfile = root / "host.pid"
    if not pidfile.is_file():
        return 0
    try:
        pid = int(pidfile.read_text("ascii").strip() or "0")
    except ValueError:
        pid = 0
    if _pid_alive(pid):
        if sys.platform == "win32":
            subprocess.call(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            os.kill(pid, signal.SIGTERM)
            for _ in range(50):
                if not _pid_alive(pid):
                    break
                time.sleep(0.1)
            if _pid_alive(pid):
                os.kill(pid, getattr(signal, "SIGKILL", signal.SIGTERM))
    pidfile.unlink(missing_ok=True)
    return 0


def health_url(spec: Dict[str, Any]) -> str:
    """Loopback URL of ``/__pskit/health`` on the address this process binds.

    ``endpoint`` may be a public advertise URL. A host that binds ``0.0.0.0``
    still answers on ``127.0.0.1``, including when the public address is not
    reachable from the machine itself.
    """
    host = str(spec.get("host") or "127.0.0.1").strip() or "127.0.0.1"
    if host in ("0.0.0.0", "::", "[::]"):  # noqa: S104 - wildcard bind is probed on loopback
        host = "127.0.0.1"
    elif ":" in host and not host.startswith("["):
        host = "[" + host + "]"
    try:
        port = int(spec.get("port") or 8080)
    except (TypeError, ValueError):
        port = 8080
    return f"http://{host}:{port}/__pskit/health"


def _wait_healthy(url: str, timeout: float, proc: Optional[subprocess.Popen[bytes]] = None) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc is not None and proc.poll() is not None:
            return False  # the host exited (a crash at start-up): no point waiting
        try:
            with urlopen(url, timeout=1) as resp:  # noqa: S310 - local host URL from our own spec
                if resp.status == 200:
                    return True
        except (URLError, OSError, TimeoutError, ValueError):
            time.sleep(0.2)
    return False


def start(root: Path) -> int:
    """Stop any previous host, activate the new bundle, and daemonize."""
    root = Path(root)
    stop(root)
    activate_layout(root)
    log_path = root / "host.log"
    log = open(log_path, "ab")  # noqa: SIM115 - inherited by the child process
    offset = log.tell()
    cmd = [sys.executable, str(root / "onprem_ctl.py"), "foreground"]
    kwargs: Dict[str, Any] = {
        "cwd": str(root),
        "stdin": subprocess.DEVNULL,
        "stdout": log,
        "stderr": subprocess.STDOUT,
        "close_fds": True,
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    proc = subprocess.Popen(cmd, **kwargs)  # noqa: S603 - fixed argv, this interpreter
    spec = json.loads((root / "pskit_host.json").read_text("utf-8"))
    if _wait_healthy(health_url(spec), 30, proc):
        return 0
    sys.stderr.write(f"on-prem host did not become healthy; see {log_path}\n")
    sys.stderr.write(_log_tail(log_path, offset))
    return 1


def _log_tail(path: Path, offset: int, lines: int = 25) -> str:
    """The end of what this start wrote to host.log, so a failed deploy shows why without logging in."""
    try:
        with open(path, "rb") as fh:
            fh.seek(offset)
            text = fh.read().decode("utf-8", "replace")
    except OSError:
        return ""
    tail = [line for line in text.splitlines() if line.strip()][-lines:]
    return "".join(f"  | {line}\n" for line in tail)


def foreground(root: Path) -> int:
    root = Path(root)
    activate_layout(root)
    host = Host(root)
    host.open()
    (root / "host.pid").write_text(str(os.getpid()), "ascii")
    try:
        host.serve_forever()
    finally:
        pidfile = root / "host.pid"
        if pidfile.is_file() and pidfile.read_text("ascii").strip() == str(os.getpid()):
            pidfile.unlink(missing_ok=True)
    return 0


def main(root: Path) -> int:
    command = sys.argv[1] if len(sys.argv) > 1 else "start"
    if command == "stop":
        return stop(root)
    if command == "foreground":
        return foreground(root)
    if command == "start":
        return start(root)
    sys.stderr.write("usage: onprem_ctl.py [start|stop|foreground]\n")
    return 2
