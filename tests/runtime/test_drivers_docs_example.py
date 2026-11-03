"""The RabbitMQ `custom` driver shown in docs/resources.md runs against a fake `pika`."""

from __future__ import annotations

import re
import sys
import types
from pathlib import Path
from typing import Any, Dict, List

from py_serverless_kit.runtime.drivers import make_queue_driver

DOC = Path(__file__).resolve().parents[2] / "docs" / "resources.md"


def _fake_pika() -> types.ModuleType:
    broker: Dict[str, List[Any]] = {"ready": [], "unacked": {}}
    tags = iter(range(1, 10_000))

    class Props:
        def __init__(self, message_id=None, headers=None, delivery_mode=None):
            self.message_id, self.headers, self.delivery_mode = message_id, headers, delivery_mode

    class Method:
        def __init__(self, tag, redelivered):
            self.delivery_tag, self.redelivered = tag, redelivered

    class Channel:
        is_closed = False

        def queue_declare(self, queue, durable=False, passive=False):
            return types.SimpleNamespace(method=types.SimpleNamespace(message_count=len(broker["ready"])))

        def basic_publish(self, exchange, routing_key, body, properties):
            broker["ready"].append((properties, body, False))

        def basic_get(self, queue, auto_ack):
            assert auto_ack is False
            if not broker["ready"]:
                return None, None, None
            props, body, redelivered = broker["ready"].pop(0)
            tag = next(tags)
            broker["unacked"][tag] = (props, body)
            return Method(tag, redelivered), props, body

        def basic_ack(self, delivery_tag):
            del broker["unacked"][delivery_tag]

        def basic_nack(self, delivery_tag, requeue):
            props, body = broker["unacked"].pop(delivery_tag)
            if requeue:
                broker["ready"].append((props, body, True))

    class BlockingConnection:
        def __init__(self, params):
            assert params.url.startswith("amqp://")

        def channel(self):
            return Channel()

    mod = types.ModuleType("pika")
    mod.URLParameters = lambda url: types.SimpleNamespace(url=url)  # type: ignore[attr-defined]
    mod.BlockingConnection = BlockingConnection  # type: ignore[attr-defined]
    mod.BasicProperties = Props  # type: ignore[attr-defined]
    mod.broker = broker  # type: ignore[attr-defined]
    return mod


def test_documented_rabbitmq_class_is_at_least_once(monkeypatch):
    text = DOC.read_text("utf-8")
    block = re.search(r"```python\n(# app/backends\.py  \(requirements\.txt: pika\)\n.*?)```", text, re.S)
    assert block, "RabbitMQ example missing from docs/resources.md"
    pika = _fake_pika()
    monkeypatch.setitem(sys.modules, "pika", pika)
    module = types.ModuleType("doc_rabbit_backend")
    exec(compile(block.group(1), str(DOC), "exec"), module.__dict__)  # noqa: S102 - our own docs
    monkeypatch.setitem(sys.modules, "doc_rabbit_backend", module)

    monkeypatch.setenv("RABBITMQ_URL", "amqp://guest:guest@localhost/")
    q = make_queue_driver(
        {"use": "custom", "class": "doc_rabbit_backend:RabbitQueue", "url_env": "RABBITMQ_URL", "queue": "orders"},
        "orders",
    )
    q.submit("ok", {"k": "v"})
    q.submit("bad", {})
    assert q.depth() == 2
    claimed = q.claim(10, 30, 0)
    assert [m["body"] for m in claimed] == ["ok", "bad"] and claimed[0]["attributes"] == {"k": "v"}
    dead: List[str] = []

    class Dead:
        def submit(self, body, attributes):
            dead.append(body)

    q.settle(claimed, {claimed[1]["id"]}, max_receive=2, dead_letter=Dead(), now=0)
    assert q.depth() == 1 and not pika.broker["unacked"]
    again = q.claim(10, 30, 0)
    assert again[0]["receives"] == 2  # redelivered
    q.settle(again, {again[0]["id"]}, max_receive=2, dead_letter=Dead(), now=0)
    assert q.depth() == 0 and dead == ["bad"]
