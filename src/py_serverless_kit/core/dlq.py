"""``pskit dlq``: which dead-letter queues a project has, what they hold, and sending their messages back.

On premises the host does the work (``/__pskit/queues/<name>/messages`` and ``/replay``). On AWS, Azure and GCP this
machine talks to the queue service, with the credentials ``pskit resources send`` uses, through the same queue interface
the on-prem host uses for its drivers (``runtime/dead_letters.py``).
"""

from __future__ import annotations

import os
import shutil
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import quote

from ..runtime import dead_letters
from .testing import TriggerError, _boto3, azure_connections

SUPPORTED = ("aws", "azure", "gcp", "onprem")
GCP_SUBSCRIPTION_SUFFIX = "-sub"  # the pull subscription that keeps a GCP dead-letter topic's messages


class DlqError(TriggerError):
    pass


@dataclass
class DeadLetterQueue:
    name: str
    functions: List[str] = field(default_factory=list)
    sources: List[str] = field(default_factory=list)
    max_receive: int = 0


def dead_letter_queues(config: Any) -> List[DeadLetterQueue]:
    """Every dead-letter queue of the project, from ``dlq:`` and from ``dead_letter`` on queue events."""
    provider = config.provider.name
    found: Dict[str, DeadLetterQueue] = {}
    for fn_name, fn in config.functions.items():
        for ev in fn.events_of("queue"):
            source = ev.name
            if provider == "azure":  # Azure Functions moves poison messages to this queue itself
                name = f"{ev.name}-poison"
            elif provider == "gcp" and fn.dlq is None:  # dead_letter on an event alone is not applied there
                continue
            elif ev.dead_letter:
                name = ev.dead_letter
                if name in config.resources:
                    name = config.resources[name].native_name(name)
                if provider == "aws" and ev.fifo:
                    source += "" if source.endswith(".fifo") else ".fifo"
                    name += "" if name.endswith(".fifo") else ".fifo"
            else:
                continue
            item = found.setdefault(name, DeadLetterQueue(name, max_receive=ev.max_receive))
            if fn_name not in item.functions:
                item.functions.append(fn_name)
            if source not in item.sources:
                item.sources.append(source)
    return sorted(found.values(), key=lambda q: q.name)


def find_queue(config: Any, which: str) -> DeadLetterQueue:
    """``which``: a function name or a dead-letter queue's name."""
    queues = dead_letter_queues(config)
    for queue in queues:
        if queue.name == which:
            return queue
    theirs = [q for q in queues if which in q.functions]
    if len(theirs) == 1:
        return theirs[0]
    if theirs:
        names = " or ".join(q.name for q in theirs)
        raise DlqError(f"function {which!r} has several dead-letter queues: name {names}")
    known = ", ".join(sorted({q.name for q in queues} | {f for q in queues for f in q.functions})) or "none"
    raise DlqError(f"no dead-letter queue for {which!r}. Functions and queues that have one: {known}. "
                   "Add `dlq:` to the function in pskit.yml and deploy")


# ------------------------------------------------------------------ cloud queues
class _Sqs:
    """The queue interface on boto3, which finds credentials like the AWS CLI does."""

    def __init__(self, session: Any, name: str) -> None:
        self.client = session.client("sqs")
        self.url = self.client.get_queue_url(QueueName=name)["QueueUrl"]
        self.fifo = self.url.endswith(".fifo")

    def submit(self, body: str, attributes: Dict[str, Any]) -> str:
        args: Dict[str, Any] = {"QueueUrl": self.url, "MessageBody": body}
        attrs = {str(k): {"DataType": "String", "StringValue": str(v)} for k, v in attributes.items() if str(v)}
        if attrs:
            args["MessageAttributes"] = attrs
        if self.fifo:
            args.update(MessageGroupId="pskit-replay", MessageDeduplicationId=os.urandom(16).hex())
        return str(self.client.send_message(**args).get("MessageId") or "")

    def claim(self, batch: int, visibility: float, now: float) -> List[Dict[str, Any]]:
        reply = self.client.receive_message(
            QueueUrl=self.url, MaxNumberOfMessages=min(10, int(batch)), VisibilityTimeout=int(visibility),
            WaitTimeSeconds=1, AttributeNames=["All"], MessageAttributeNames=["All"],
        )
        out = []
        for msg in reply.get("Messages") or []:
            system = msg.get("Attributes") or {}
            attrs = {k: v.get("StringValue") for k, v in (msg.get("MessageAttributes") or {}).items()}
            source = str(system.get("DeadLetterQueueSourceArn") or "").rsplit(":", 1)[-1]
            if source:
                attrs[dead_letters.SOURCE_ATTRIBUTE] = source
            sent = system.get("SentTimestamp")
            out.append({
                "id": str(msg.get("MessageId")), "body": msg.get("Body", ""), "attributes": attrs,
                "receives": int(system.get("ApproximateReceiveCount") or 1),
                "enqueued_at": int(sent) / 1000.0 if sent else None, "_handle": msg.get("ReceiptHandle"),
            })
        return out

    def settle(self, claimed: List[Dict[str, Any]], failed_ids: Iterable[str], max_receive: int, dead_letter: Any,
               now: float) -> None:
        keep = set(failed_ids)
        for msg in claimed:
            if msg["id"] in keep:
                self.client.change_message_visibility(QueueUrl=self.url, ReceiptHandle=msg["_handle"], VisibilityTimeout=0)
            else:
                self.client.delete_message(QueueUrl=self.url, ReceiptHandle=msg["_handle"])

    def depth(self) -> int:
        reply = self.client.get_queue_attributes(QueueUrl=self.url, AttributeNames=["ApproximateNumberOfMessages"])
        return int((reply.get("Attributes") or {}).get("ApproximateNumberOfMessages") or 0)


def _gcp_binding(project: Any) -> Dict[str, Any]:
    binding: Dict[str, Any] = {"project": project.config.provider.options.get("project") or ""}
    token = os.environ.get("GOOGLE_OAUTH_ACCESS_TOKEN")
    if token:
        binding["access_token"] = token
    else:
        binding["token_command"] = [shutil.which("gcloud") or "gcloud", "auth", "print-access-token"]
    return binding


def _driver(project: Any, name: str, *, dead: bool = True) -> Any:
    """Queue ``name``; on GCP, ``dead`` reads the dead-letter topic's subscription and otherwise publishes to the topic."""
    provider = project.config.provider.name
    if provider == "aws":
        return _Sqs(_boto3(project.region), name)
    if provider == "azure":
        from ..runtime.drivers.azure import AzureQueue

        conn = azure_connections(project).get("storage")
        if not conn:
            raise DlqError("no storage connection string: deploy first, or set AZURE_STORAGE_CONNECTION_STRING")
        return AzureQueue.from_binding({"connection_string": conn, "queue": name}, name)
    from ..runtime.drivers.gcp import PubSubQueue

    binding = _gcp_binding(project)
    if not binding["project"]:
        raise DlqError("GCP needs provider.options.project")
    if dead:
        binding["subscription"] = name + GCP_SUBSCRIPTION_SUFFIX
    else:
        binding.update(subscription=name, topic=name)
    return PubSubQueue.from_binding(binding, name)


def _destination(queue: DeadLetterQueue, to: Optional[str]) -> Any:
    def where(msg: Dict[str, Any]) -> Optional[str]:
        if to:
            return to
        recorded = str((msg.get("attributes") or {}).get(dead_letters.SOURCE_ATTRIBUTE) or "")
        if recorded:
            return recorded
        return queue.sources[0] if len(queue.sources) == 1 else None

    return where


# ------------------------------------------------------------------ on premises
def _host(project: Any, record: Optional[Dict[str, Any]]) -> Any:
    from .onprem_control import control_for

    control = control_for(record or {}, project.root) if record else None
    if control is None:
        raise DlqError("the on-prem host is not deployed yet: run `pskit deploy`")
    return control


def _host_request(project: Any, record: Optional[Dict[str, Any]], method: str, path: str, **kwargs: Any) -> Any:
    try:
        return _host(project, record).request(method, path, **kwargs)
    except KeyError as exc:
        raise DlqError(f"{exc.args[0] if exc.args else exc} (redeploy if you just added it)") from None
    except (ValueError, OSError, PermissionError) as exc:
        raise DlqError(str(exc)) from None


# ------------------------------------------------------------------ the commands
def _call(fn: Any, *args: Any, **kwargs: Any) -> Any:
    """Credentials, permissions, a queue that is not deployed: said in one line."""
    try:
        return fn(*args, **kwargs)
    except TriggerError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise DlqError(f"{type(exc).__name__}: {exc}") from None


def _check_provider(project: Any) -> str:
    provider = str(project.config.provider.name)
    if provider not in SUPPORTED:
        raise DlqError(f"dead-letter queues work on {', '.join(SUPPORTED)}; this project deploys to {provider}")
    return provider


def overview(project: Any, record: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Each dead-letter queue with its functions, source queues and depth (None: the service cannot tell, or an error)."""
    provider = _check_provider(project)
    rows = []
    for queue in dead_letter_queues(project.config):
        row: Dict[str, Any] = {"queue": queue.name, "functions": queue.functions, "sources": queue.sources,
                               "max_receive": queue.max_receive, "depth": None}
        try:
            if provider == "onprem":
                reply = _host_request(project, record, "GET", f"/__pskit/queues/{quote(queue.name, safe='')}/messages",
                                      query={"limit": 1})
                row["depth"] = reply.get("total")
            else:
                depth = _call(lambda name=queue.name: _driver(project, name).depth())
                row["depth"] = depth if depth >= 0 else None
        except TriggerError as exc:
            row["error"] = str(exc)
        rows.append(row)
    return rows


def messages(project: Any, record: Optional[Dict[str, Any]], which: str, offset: int = 0, limit: int = 20) -> Dict[str, Any]:
    """A page of the messages waiting in a dead-letter queue. Nothing is consumed."""
    provider = _check_provider(project)
    queue = find_queue(project.config, which)
    offset, limit = max(0, offset), max(1, min(limit, 500))
    base = {"queue": queue.name, "sources": queue.sources, "offset": offset, "limit": limit}
    if provider == "onprem":
        reply = _host_request(project, record, "GET", f"/__pskit/queues/{quote(queue.name, safe='')}/messages",
                              query={"offset": offset, "limit": limit})
        return {**base, "total": reply.get("total"), "items": reply.get("items") or []}

    def read() -> Dict[str, Any]:
        driver = _driver(project, queue.name)
        items = dead_letters.page(driver, offset, limit, time.time())
        depth = driver.depth()
        return {**base, "total": depth if depth >= 0 else None, "items": items}

    return dict(_call(read))


def inspect(project: Any, record: Optional[Dict[str, Any]], which: str, ident: str) -> Dict[str, Any]:
    """One message, with its whole body and attributes."""
    provider = _check_provider(project)
    queue = find_queue(project.config, which)
    if provider == "onprem":
        reply = _host_request(project, record, "GET", f"/__pskit/queues/{quote(queue.name, safe='')}/messages",
                              query={"id": ident})
        items = reply.get("items") or []
    else:
        items = _call(lambda: dead_letters.page(_driver(project, queue.name), 0, 1, time.time(), ident=ident))
    if not items:
        raise DlqError(f"no message {ident!r} in {queue.name}: see `pskit dlq list {which}`")
    return {"queue": queue.name, "sources": queue.sources, **items[0]}


def replay(
    project: Any, record: Optional[Dict[str, Any]], which: str, ids: Optional[List[str]], to: Optional[str] = None,
) -> Dict[str, Any]:
    """Send messages ``ids`` (None: every one) back to the queue they came from, or to queue ``to``."""
    provider = _check_provider(project)
    queue = find_queue(project.config, which)
    if provider == "onprem":
        reply = _host_request(project, record, "POST", f"/__pskit/queues/{quote(queue.name, safe='')}/replay",
                              body={"ids": ids, "to": to or "", "sources": queue.sources}, timeout=900)
        return {"queue": queue.name, **reply}

    def run() -> Dict[str, Any]:
        targets: Dict[str, Any] = {}

        def submit(name: str, body: str, attributes: Dict[str, Any]) -> Any:
            if name not in targets:
                targets[name] = _driver(project, name, dead=False)
            return targets[name].submit(body, attributes)

        return dead_letters.replay(_driver(project, queue.name), submit, _destination(queue, to), ids, time.time())

    return {"queue": queue.name, **_call(run)}
