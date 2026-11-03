"""Queue / storage drivers for external providers (SQS, Azure, GCP, MNS, Cloudflare, S3 presets, custom).

Every test talks to an in-process fake that follows the provider's documented REST API.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import sys
import threading
import time
import uuid
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List
from urllib.parse import parse_qsl, unquote, urlsplit

import pytest

from py_serverless_kit.runtime.drivers import (
    CustomQueue,
    make_queue_driver,
    make_storage_driver,
    resolve_env,
    s3_preset,
)
from py_serverless_kit.runtime.drivers._aws import region_from_host
from py_serverless_kit.runtime.drivers._http import DriverError
from py_serverless_kit.runtime.drivers.azure import DEV_ACCOUNT, DEV_KEY, parse_connection_string, string_to_sign
from py_serverless_kit.runtime.drivers.mns import signature as mns_signature
from py_serverless_kit.runtime.drivers.mns import string_to_sign as mns_string_to_sign


@contextmanager
def serve(handler: type):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


class _Base(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args: Any) -> None:
        return None

    def _body(self) -> bytes:
        return self.rfile.read(int(self.headers.get("content-length") or 0))

    def _reply(self, status: int, body: bytes = b"", headers: Dict[str, str] = None) -> None:  # type: ignore[assignment]
        self.send_response(status)
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class Msg:
    def __init__(self, body: str, attrs: Dict[str, str] = None) -> None:  # type: ignore[assignment]
        self.id = uuid.uuid4().hex
        self.body = body
        self.attrs = attrs or {}
        self.receives = 0
        self.visible_at = 0.0
        self.handle = ""


def _visible(msgs: List[Msg], n: int, seconds: float) -> List[Msg]:
    now = time.time()
    picked = [m for m in msgs if m.visible_at <= now][:n]
    for m in picked:
        m.receives += 1
        m.visible_at = now + seconds
        m.handle = uuid.uuid4().hex
    return picked


# --------------------------------------------------------------------------- common helpers


def test_resolve_env_reads_variables_and_names_missing_ones(monkeypatch):
    monkeypatch.setenv("MY_SECRET", "s3cr3t")
    out = resolve_env({"use": "sqs", "secret_key_env": "MY_SECRET", "access_key": "AK"})
    assert out == {"use": "sqs", "secret_key": "s3cr3t", "access_key": "AK"}
    assert resolve_env({"secret_key": "explicit", "secret_key_env": "MY_SECRET"})["secret_key"] == "explicit"
    monkeypatch.delenv("NOPE_VAR", raising=False)
    with pytest.raises(ValueError, match="NOPE_VAR.*queue jobs"):
        make_queue_driver({"use": "sqs", "queue_url": "http://x/1/q", "secret_key_env": "NOPE_VAR"}, "jobs")


def test_region_from_host():
    assert region_from_host("sqs.eu-west-1.amazonaws.com") == "eu-west-1"
    assert region_from_host("queue.amazonaws.com") == "us-east-1"
    assert region_from_host("localhost:4566", "ap-south-1") == "ap-south-1"


def test_unknown_drivers_are_rejected():
    with pytest.raises(ValueError, match="unsupported queue driver 'kafka'"):
        make_queue_driver({"use": "kafka"}, "jobs")
    with pytest.raises(ValueError, match="unsupported storage driver"):
        make_storage_driver({"use": "ftp"})


def test_unreachable_endpoints_raise_driver_errors():
    q = make_queue_driver({"use": "sqs", "queue_url": "http://127.0.0.1:1/1/q", "access_key": "a", "secret_key": "b"})
    with pytest.raises(DriverError, match="sqs: .*unreachable"):
        q.depth()


# --------------------------------------------------------------------------- SQS


def _sqs_handler(queues: Dict[str, List[Msg]], calls: List[str]) -> type:
    class Handler(_Base):
        def do_POST(self) -> None:  # noqa: N802
            data = json.loads(self._body())
            action = self.headers["x-amz-target"].split(".", 1)[1]
            calls.append(action)
            auth = self.headers.get("authorization", "")
            assert self.headers["content-type"] == "application/x-amz-json-1.0"
            if "/sqs/aws4_request" not in auth or "Credential=AK/" not in auth:
                return self._reply(403, b'{"__type":"InvalidSignature","message":"bad auth"}')
            msgs = queues.get(data["QueueUrl"])
            if msgs is None:
                err = {"__type": "com.amazonaws.sqs#QueueDoesNotExist", "message": "The queue does not exist"}
                return self._reply(400, json.dumps(err).encode())
            out: Dict[str, Any] = {}
            if action == "SendMessage":
                attrs = {k: v["StringValue"] for k, v in (data.get("MessageAttributes") or {}).items()}
                if data["QueueUrl"].endswith(".fifo"):
                    assert data["MessageGroupId"] and data["MessageDeduplicationId"]
                m = Msg(data["MessageBody"], attrs)
                msgs.append(m)
                out = {"MessageId": m.id}
            elif action == "ReceiveMessage":
                assert data["MaxNumberOfMessages"] <= 10
                picked = _visible(msgs, data["MaxNumberOfMessages"], data["VisibilityTimeout"])
                out = {
                    "Messages": [
                        {
                            "MessageId": m.id,
                            "ReceiptHandle": m.handle,
                            "Body": m.body,
                            "Attributes": {"ApproximateReceiveCount": str(m.receives), "SentTimestamp": "1700000000000"},
                            "MessageAttributes": {k: {"DataType": "String", "StringValue": v} for k, v in m.attrs.items()},
                        }
                        for m in picked
                    ]
                }
            elif action == "DeleteMessageBatch":
                handles = {e["ReceiptHandle"] for e in data["Entries"]}
                assert len(data["Entries"]) <= 10
                msgs[:] = [m for m in msgs if m.handle not in handles]
                out = {"Successful": [{"Id": e["Id"]} for e in data["Entries"]], "Failed": []}
            elif action == "ChangeMessageVisibility":
                for m in msgs:
                    if m.handle == data["ReceiptHandle"]:
                        m.visible_at = time.time() + data["VisibilityTimeout"]
            elif action == "GetQueueAttributes":
                out = {"Attributes": {"ApproximateNumberOfMessages": str(len(msgs))}}
            self._reply(200, json.dumps(out).encode())

    return Handler


def test_sqs_queue_roundtrip_retry_and_dead_letter(monkeypatch):
    calls: List[str] = []
    queues: Dict[str, List[Msg]] = {}
    with serve(_sqs_handler(queues, calls)) as base:
        url, dlq_url = f"{base}/123/jobs", f"{base}/123/jobs-dlq"
        queues[url], queues[dlq_url] = [], []
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AK")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "SK")
        q = make_queue_driver({"use": "sqs", "queue_url": url, "region": "eu-west-1"}, "jobs")
        dlq = make_queue_driver(
            {"use": "sqs", "account_id": "123", "name": "jobs-dlq", "region": "eu-west-1", "endpoint": base}
        )
        for i in range(12):
            q.submit(f"m{i}", {"n": i} if i == 0 else {})
        assert q.depth() == 12
        claimed = q.claim(12, 30, time.time())
        assert len(claimed) == 12 and calls.count("ReceiveMessage") == 2  # 10 + 2
        assert claimed[0]["attributes"] == {"n": "0"} and claimed[0]["receives"] == 1
        assert claimed[0]["enqueued_at"] == 1700000000.0
        assert q.claim(5, 30, time.time()) == []  # all leased
        failed = {claimed[0]["id"], claimed[1]["id"]}
        q.settle(claimed, failed, max_receive=2, dead_letter=dlq, now=time.time())
        assert q.depth() == 2 and calls.count("DeleteMessageBatch") == 1  # 10 deletes, one batch
        assert calls.count("ChangeMessageVisibility") == 2
        again = q.claim(10, 30, time.time())
        assert {m["receives"] for m in again} == {2}
        q.settle(again, {m["id"] for m in again}, max_receive=2, dead_letter=dlq, now=time.time())
        assert q.depth() == 0 and dlq.depth() == 2
        with pytest.raises(DriverError, match="QueueDoesNotExist"):
            make_queue_driver({"use": "sqs", "queue_url": f"{base}/123/nope"}).depth()


def test_sqs_fifo_and_missing_credentials(monkeypatch):
    monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("AWS_SECRET_ACCESS_KEY", raising=False)
    with pytest.raises(ValueError, match="no credentials"):
        make_queue_driver({"use": "sqs", "queue_url": "https://sqs.us-east-1.amazonaws.com/1/q"})
    with pytest.raises(ValueError, match="queue_url, or account_id"):
        make_queue_driver({"use": "sqs", "access_key": "a", "secret_key": "b"})
    queues: Dict[str, List[Msg]] = {}
    with serve(_sqs_handler(queues, [])) as base:
        url = f"{base}/1/orders.fifo"
        queues[url] = []
        q = make_queue_driver({"use": "sqs", "queue_url": url, "access_key": "AK", "secret_key": "SK"})
        q.submit("x", {})
        assert len(queues[url]) == 1


# --------------------------------------------------------------------------- Azure


def test_azure_shared_key_string_to_sign_matches_the_documented_layout():
    headers = {
        "x-ms-date": "Fri, 26 Jun 2015 23:39:12 GMT",
        "x-ms-version": "2015-02-21",
        "Content-Length": "0",
    }
    text = string_to_sign(
        "GET", "myaccount", "/mycontainer", {"restype": "container", "comp": "list", "prefix": "a b"}, headers
    )
    expected = (
        "GET\n\n\n\n\n\n\n\n\n\n\n\n"  # verb + 11 empty standard headers (length 0 -> empty)
        "x-ms-date:Fri, 26 Jun 2015 23:39:12 GMT\nx-ms-version:2015-02-21\n"
        "/myaccount/mycontainer\ncomp:list\nprefix:a b\nrestype:container"
    )
    assert text == expected
    key = base64.b64encode(b"secret-key").decode()
    from py_serverless_kit.runtime.drivers.azure import shared_key

    sig = base64.b64encode(hmac.new(b"secret-key", expected.encode(), hashlib.sha256).digest()).decode()
    assert shared_key("myaccount", key, "GET", "/mycontainer", {"restype": "container", "comp": "list", "prefix": "a b"}, headers) == f"SharedKey myaccount:{sig}"


def test_azure_connection_strings():
    dev = parse_connection_string("UseDevelopmentStorage=true")
    assert dev["AccountName"] == DEV_ACCOUNT and dev["QueueEndpoint"].endswith(":10001/devstoreaccount1")
    prod = parse_connection_string(
        "DefaultEndpointsProtocol=https;AccountName=acct;AccountKey=a2V5;EndpointSuffix=core.windows.net"
    )
    assert prod == {
        "DefaultEndpointsProtocol": "https",
        "AccountName": "acct",
        "AccountKey": "a2V5",
        "EndpointSuffix": "core.windows.net",
    }
    q = make_queue_driver({"use": "azure_queue", "connection_string": "AccountName=acct;AccountKey=a2V5"}, "jobs")
    assert q.auth.endpoint == "https://acct.queue.core.windows.net" and q.queue == "jobs"
    with pytest.raises(ValueError, match="account_key, sas_token or connection_string"):
        make_queue_driver({"use": "azure_queue", "account": "acct"}, "jobs")
    with pytest.raises(ValueError, match="base64"):
        make_queue_driver({"use": "azure_queue", "account": "acct", "account_key": "!!notb64"}, "jobs").depth()


def _azure_handler(state: Dict[str, Any]) -> type:
    """Azurite-like fake for queues (/<account>/<queue>/...) and blobs (/<account>/<container>/<blob>)."""

    class Handler(_Base):
        def _authorized(self, url: Any) -> bool:
            query = dict(parse_qsl(url.query, keep_blank_values=True))
            if "sig" in query:
                return query["sig"] == "good"
            auth = self.headers.get("authorization", "")
            headers = {k.lower(): v for k, v in self.headers.items()}
            expected = base64.b64encode(
                hmac.new(
                    base64.b64decode(DEV_KEY),
                    string_to_sign(self.command, DEV_ACCOUNT, url.path, query, headers).encode(),
                    hashlib.sha256,
                ).digest()
            ).decode()
            return auth == f"SharedKey {DEV_ACCOUNT}:{expected}"

        def _handle(self) -> None:
            url = urlsplit(self.path)
            body = self._body()
            if not self._authorized(url):
                return self._reply(403, b"<Error><Code>AuthenticationFailed</Code></Error>")
            parts = [unquote(p) for p in url.path.split("/") if p][1:]
            query = dict(parse_qsl(url.query))
            if parts[0] == "work":  # queue
                msgs: List[Msg] = state["queue"]
                if len(parts) == 1 and query.get("comp") == "metadata":
                    return self._reply(200, headers={"x-ms-approximate-messages-count": str(len(msgs))})
                if self.command == "POST":
                    text = ET.fromstring(body).findtext("MessageText")
                    m = Msg(text or "")
                    msgs.append(m)
                    xml = f"<QueueMessagesList><QueueMessage><MessageId>{m.id}</MessageId></QueueMessage></QueueMessagesList>"
                    return self._reply(201, xml.encode())
                if self.command == "GET":
                    n = int(query["numofmessages"])
                    assert n <= 32
                    picked = _visible(msgs, n, float(query["visibilitytimeout"]))
                    items = "".join(
                        f"<QueueMessage><MessageId>{m.id}</MessageId><PopReceipt>{m.handle}</PopReceipt>"
                        f"<DequeueCount>{m.receives}</DequeueCount><MessageText>{m.body}</MessageText></QueueMessage>"
                        for m in picked
                    )
                    return self._reply(200, f"<QueueMessagesList>{items}</QueueMessagesList>".encode())
                target = next((m for m in msgs if m.id == parts[2] and m.handle == query.get("popreceipt")), None)
                if target is None:
                    return self._reply(404)
                if self.command == "DELETE":
                    msgs.remove(target)
                else:  # PUT update visibility
                    target.visible_at = time.time() + int(query["visibilitytimeout"])
                return self._reply(204)
            blobs: Dict[str, bytes] = state["blobs"]
            if len(parts) == 1:  # list
                names = sorted(n for n in blobs if n.startswith(query.get("prefix", "")))
                start = int(query.get("marker") or 0)
                page, more = names[start : start + 2], start + 2 < len(names)
                items = "".join(
                    f"<Blob><Name>{n}</Name><Properties><Etag>\"0x{len(blobs[n])}\"</Etag>"
                    f"<Content-Length>{len(blobs[n])}</Content-Length></Properties></Blob>"
                    for n in page
                )
                marker = f"<NextMarker>{start + 2}</NextMarker>" if more else "<NextMarker />"
                xml = f'<?xml version="1.0"?><EnumerationResults><Blobs>{items}</Blobs>{marker}</EnumerationResults>'
                return self._reply(200, xml.encode())
            name = "/".join(parts[1:])
            if self.command == "PUT":
                assert self.headers["x-ms-blob-type"] == "BlockBlob"
                blobs[name] = body
                return self._reply(201)
            if name not in blobs:
                return self._reply(404)
            if self.command == "DELETE":
                del blobs[name]
                return self._reply(202)
            return self._reply(200, blobs[name])

        do_GET = do_POST = do_PUT = do_DELETE = _handle  # noqa: N815

    return Handler


def test_azure_queue_and_blob_against_azurite_like_fake():
    state: Dict[str, Any] = {"queue": [], "blobs": {}}
    with serve(_azure_handler(state)) as base:
        conn = f"UseDevelopmentStorage=true;QueueEndpoint={base}/{DEV_ACCOUNT};BlobEndpoint={base}/{DEV_ACCOUNT}"
        q = make_queue_driver({"use": "azure_queue", "connection_string": conn, "queue": "work"})
        dlq_state: List[str] = []

        class Dead:
            def submit(self, body: str, attributes: Dict[str, Any]) -> str:
                dlq_state.append(body)
                return "d"

        q.submit("héllo <&>", {})
        q.submit("two", {})
        assert state["queue"][0].body == base64.b64encode("héllo <&>".encode()).decode()
        assert q.depth() == 2
        claimed = q.claim(5, 30, time.time())
        assert [m["body"] for m in claimed] == ["héllo <&>", "two"] and claimed[0]["receives"] == 1
        q.settle(claimed, {claimed[1]["id"]}, max_receive=2, dead_letter=Dead(), now=time.time())
        assert q.depth() == 1
        again = q.claim(5, 30, time.time())
        assert again[0]["receives"] == 2
        q.settle(again, {again[0]["id"]}, max_receive=2, dead_letter=Dead(), now=time.time())
        assert q.depth() == 0 and dlq_state == ["two"]

        sas = make_queue_driver(
            {"use": "azure_queue", "endpoint": f"{base}/{DEV_ACCOUNT}", "sas_token": "?sv=1&sig=good", "queue": "work"}
        )
        assert sas.depth() == 0
        bad = make_queue_driver(
            {"use": "azure_queue", "endpoint": f"{base}/{DEV_ACCOUNT}", "sas_token": "sig=bad", "queue": "work"}
        )
        with pytest.raises(DriverError, match="403"):
            bad.depth()

        store = make_storage_driver({"use": "azure_blob", "connection_string": conn, "prefix": "in"}, "media")
        for i in range(5):
            store.put(f"dir/file {i}.txt", b"x" * i)
        state["blobs"]["other.txt"] = b"zz"
        scanned = store.scan()
        assert sorted(scanned) == [f"dir/file {i}.txt" for i in range(5)] and scanned["dir/file 3.txt"] == ("0x3", 3)
        assert store.get("dir/file 2.txt") == b"xx"
        assert store.delete("dir/file 2.txt") is True and store.delete("dir/file 2.txt") is False
        with pytest.raises(KeyError):
            store.get("nope")


# --------------------------------------------------------------------------- GCP


def _gcp_handler(state: Dict[str, Any], tokens: List[str]) -> type:
    class Handler(_Base):
        def _handle(self) -> None:
            tokens.append(self.headers.get("authorization", ""))
            url = urlsplit(self.path)
            body = self._body()
            query = dict(parse_qsl(url.query))
            path = url.path
            if path.startswith("/v1/"):
                resource, _, verb = path[4:].rpartition(":")
                data = json.loads(body or b"{}")
                msgs: List[Msg] = state["sub"]
                if verb == "publish":
                    assert resource == "projects/p/topics/t"
                    ids = []
                    for m in data["messages"]:
                        msg = Msg(base64.b64decode(m["data"]).decode(), m.get("attributes") or {})
                        msgs.append(msg)
                        ids.append(msg.id)
                    return self._reply(200, json.dumps({"messageIds": ids}).encode())
                assert resource == "projects/p/subscriptions/s"
                if verb == "pull":
                    picked = _visible(msgs, data["maxMessages"], 10)
                    out = {
                        "receivedMessages": [
                            {
                                "ackId": m.handle,
                                "message": {
                                    "data": base64.b64encode(m.body.encode()).decode(),
                                    "attributes": m.attrs,
                                    "messageId": m.id,
                                },
                            }
                            for m in picked
                        ]
                    }
                    return self._reply(200, json.dumps(out).encode())
                if verb == "modifyAckDeadline":
                    for m in msgs:
                        if m.handle in data["ackIds"]:
                            m.visible_at = time.time() + data["ackDeadlineSeconds"]
                            state.setdefault("deadlines", []).append(data["ackDeadlineSeconds"])
                    return self._reply(200, b"{}")
                if verb == "acknowledge":
                    msgs[:] = [m for m in msgs if m.handle not in data["ackIds"]]
                    return self._reply(200, b"{}")
            objects: Dict[str, bytes] = state["objects"]
            if path == "/upload/storage/v1/b/bkt/o":
                assert query["uploadType"] == "media"
                objects[query["name"]] = body
                return self._reply(200, b"{}")
            if path == "/storage/v1/b/bkt/o":
                names = sorted(n for n in objects if n.startswith(query.get("prefix", "")))
                start = int(query.get("pageToken") or 0)
                page = names[start : start + 2]
                out: Dict[str, Any] = {"items": [{"name": n, "etag": f"e{len(objects[n])}", "size": str(len(objects[n]))} for n in page]}
                if start + 2 < len(names):
                    out["nextPageToken"] = str(start + 2)
                return self._reply(200, json.dumps(out).encode())
            if path.startswith("/storage/v1/b/bkt/o/"):
                name = unquote(path[len("/storage/v1/b/bkt/o/") :])
                if name not in objects:
                    return self._reply(404, b'{"error": {"code": 404}}')
                if self.command == "DELETE":
                    del objects[name]
                    return self._reply(204)
                assert query.get("alt") == "media"
                return self._reply(200, objects[name])
            self._reply(404)

        do_GET = do_POST = do_DELETE = _handle  # noqa: N815

    return Handler


def test_pubsub_pull_ack_retry_and_dead_letter():
    state: Dict[str, Any] = {"sub": [], "objects": {}}
    tokens: List[str] = []
    with serve(_gcp_handler(state, tokens)) as base:
        q = make_queue_driver(
            {"use": "pubsub", "endpoint": base, "emulator": True, "project": "p", "topic": "t"}, "s"
        )
        for i in range(3):
            q.submit(f"m{i}", {"i": i})
        assert q.depth() == -1
        claimed = q.claim(10, 120, time.time())
        assert [m["body"] for m in claimed] == ["m0", "m1", "m2"] and claimed[0]["attributes"] == {"i": "0"}
        assert state["deadlines"] == [120, 120, 120]
        dead: List[str] = []

        class Dead:
            def submit(self, body: str, attributes: Dict[str, Any]) -> str:
                dead.append(body)
                return "x"

        q.settle(claimed, {claimed[0]["id"]}, max_receive=2, dead_letter=Dead(), now=time.time())
        assert [m.body for m in state["sub"]] == ["m0"]
        again = q.claim(10, 120, time.time())
        assert again[0]["receives"] == 2  # counted locally without deliveryAttempt
        q.settle(again, {again[0]["id"]}, max_receive=2, dead_letter=Dead(), now=time.time())
        assert state["sub"] == [] and dead == ["m0"]
        assert set(tokens) == {""}  # emulator: no auth

        cmd = make_queue_driver(
            {
                "use": "pubsub",
                "endpoint": base,
                "subscription": "projects/p/subscriptions/s",
                "token_command": [sys.executable, "-c", "print('tok-123')"],
            }
        )
        cmd.claim(1, 30, time.time())
        cmd.claim(1, 30, time.time())
        assert tokens[-1] == "Bearer tok-123"
        assert cmd.tokens._expires > time.time() + 60  # cached
        with pytest.raises(ValueError, match="needs `project`"):
            make_queue_driver({"use": "pubsub", "access_token": "x"}, "short-name")
        with pytest.raises(ValueError, match="set `topic`"):
            make_queue_driver({"use": "pubsub", "endpoint": base, "emulator": True, "project": "p"}, "s").submit("x", {})


def test_gcs_storage_roundtrip_with_token():
    state: Dict[str, Any] = {"sub": [], "objects": {}}
    tokens: List[str] = []
    with serve(_gcp_handler(state, tokens)) as base:
        store = make_storage_driver({"use": "gcs", "endpoint": base, "access_token": "at", "prefix": "app/"}, "bkt")
        for i in range(5):
            store.put(f"in/f{i}.bin", bytes(i))
        state["objects"]["zzz"] = b"no"
        scanned = store.scan()
        assert sorted(scanned) == [f"in/f{i}.bin" for i in range(5)] and scanned["in/f2.bin"] == ("e2", 2)
        assert store.get("in/f3.bin") == bytes(3)
        assert store.delete("in/f3.bin") is True and store.delete("in/f3.bin") is False
        with pytest.raises(KeyError):
            store.get("missing")
        assert set(tokens) == {"Bearer at"}


def test_gcp_without_credentials_reports_clearly(monkeypatch):
    from py_serverless_kit.runtime.drivers import gcp

    monkeypatch.setattr(gcp, "METADATA_TOKEN", "http://127.0.0.1:1/token")
    store = make_storage_driver({"use": "gcs"}, "bkt")
    with pytest.raises(DriverError, match="no credentials"):
        store.scan()


# --------------------------------------------------------------------------- Alibaba MNS


def test_mns_string_to_sign_and_signature():
    text = mns_string_to_sign(
        "GET",
        "",
        "text/xml;charset=utf-8",
        "Thu, 17 Mar 2016 02:05:50 GMT",
        {"x-mns-version": "2015-06-06", "Date": "ignored"},
        "/queues/q/messages?numOfMessages=16",
    )
    assert text == (
        "GET\n\ntext/xml;charset=utf-8\nThu, 17 Mar 2016 02:05:50 GMT\nx-mns-version:2015-06-06\n"
        "/queues/q/messages?numOfMessages=16"
    )
    expected = base64.b64encode(hmac.new(b"secret", text.encode(), hashlib.sha1).digest()).decode()
    assert mns_signature("secret", text) == expected


def _mns_handler(msgs: List[Msg]) -> type:
    ns = "http://mns.aliyuncs.com/doc/v1/"

    class Handler(_Base):
        def _handle(self) -> None:
            url = urlsplit(self.path)
            body = self._body()
            resource = url.path + (f"?{url.query}" if url.query else "")
            text = mns_string_to_sign(
                self.command, "", self.headers["content-type"], self.headers["date"], dict(self.headers.items()), resource
            )
            if self.headers.get("authorization") != f"MNS AK:{mns_signature('SK', text)}":
                return self._reply(403, f'<Error xmlns="{ns}"><Code>SignatureDoesNotMatch</Code></Error>'.encode())
            assert self.headers["x-mns-version"] == "2015-06-06"
            query = dict(parse_qsl(url.query))
            if url.path == "/queues/jobs" and self.command == "GET":
                xml = f'<Queue xmlns="{ns}"><ActiveMessages>{len(msgs)}</ActiveMessages></Queue>'
                return self._reply(200, xml.encode())
            if self.command == "POST":
                text_body = ET.fromstring(body).findtext(f"{{{ns}}}MessageBody")
                m = Msg(text_body or "")
                msgs.append(m)
                return self._reply(201, f'<Message xmlns="{ns}"><MessageId>{m.id}</MessageId></Message>'.encode())
            if self.command == "GET":
                n = int(query["numOfMessages"])
                assert n <= 16
                picked = _visible(msgs, n, 30)
                if not picked:
                    return self._reply(404, f'<Error xmlns="{ns}"><Code>MessageNotExist</Code></Error>'.encode())
                items = "".join(
                    f"<Message><MessageId>{m.id}</MessageId><ReceiptHandle>{m.handle}</ReceiptHandle>"
                    f"<MessageBody>{m.body}</MessageBody><EnqueueTime>1700000000000</EnqueueTime>"
                    f"<DequeueCount>{m.receives}</DequeueCount></Message>"
                    for m in picked
                )
                return self._reply(200, f'<Messages xmlns="{ns}">{items}</Messages>'.encode())
            handle = query.get("receiptHandle") or query.get("ReceiptHandle")
            target = next((m for m in msgs if m.handle == handle), None)
            if target is None:
                return self._reply(404, f'<Error xmlns="{ns}"><Code>ReceiptHandleError</Code></Error>'.encode())
            if self.command == "DELETE":
                msgs.remove(target)
                return self._reply(204)
            target.visible_at = time.time() + int(query["visibilityTimeout"])
            target.handle = uuid.uuid4().hex
            xml = f'<ChangeVisibility xmlns="{ns}"><ReceiptHandle>{target.handle}</ReceiptHandle></ChangeVisibility>'
            return self._reply(200, xml.encode())

        do_GET = do_POST = do_PUT = do_DELETE = _handle  # noqa: N815

    return Handler


def test_mns_queue_roundtrip(monkeypatch):
    msgs: List[Msg] = []
    with serve(_mns_handler(msgs)) as base:
        monkeypatch.setenv("MNS_SECRET", "SK")
        q = make_queue_driver({"use": "mns", "endpoint": base, "access_key": "AK", "secret_key_env": "MNS_SECRET"}, "jobs")
        q.submit("a", {})
        q.submit("b", {})
        assert msgs[0].body == base64.b64encode(b"a").decode() and q.depth() == 2
        claimed = q.claim(20, 60, time.time())
        assert [m["body"] for m in claimed] == ["a", "b"] and claimed[0]["enqueued_at"] == 1700000000.0
        q.settle(claimed, {claimed[1]["id"]}, max_receive=5, dead_letter=None, now=time.time())
        assert len(msgs) == 1 and msgs[0].visible_at <= time.time() + 1.5
        time.sleep(1.1)
        assert q.claim(5, 60, time.time())[0]["receives"] == 2
        assert q.claim(5, 60, time.time()) == []  # MessageNotExist -> empty
        wrong = make_queue_driver({"use": "mns", "endpoint": base, "access_key": "AK", "secret_key": "bad"}, "jobs")
        with pytest.raises(DriverError, match="SignatureDoesNotMatch"):
            wrong.depth()
    with pytest.raises(ValueError, match="endpoint, or account_id"):
        make_queue_driver({"use": "mns", "access_key": "a", "secret_key": "b"}, "q")


# --------------------------------------------------------------------------- Cloudflare Queues


def _cf_handler(msgs: List[Msg], seen: List[Dict[str, Any]]) -> type:
    class Handler(_Base):
        def do_POST(self) -> None:  # noqa: N802
            data = json.loads(self._body())
            seen.append({"path": self.path, "auth": self.headers.get("authorization"), "data": data})
            if self.headers.get("authorization") != "Bearer tok":
                return self._reply(403, json.dumps({"success": False, "errors": [{"message": "Authentication error"}]}).encode())
            base = "/client/v4/accounts/acc/queues/qid/messages"
            result: Any = None
            if self.path == base:
                msgs.append(Msg(data["body"]))
            elif self.path == base + "/pull":
                picked = _visible(msgs, data["batch_size"], data["visibility_timeout_ms"] / 1000)
                result = {
                    "messages": [
                        {"id": m.id, "body": m.body, "attempts": m.receives, "lease_id": m.handle, "timestamp_ms": 1700000000000}
                        for m in picked
                    ]
                }
            elif self.path == base + "/ack":
                acked = {a["lease_id"] for a in data["acks"]}
                msgs[:] = [m for m in msgs if m.handle not in acked]
                for r in data["retries"]:
                    for m in msgs:
                        if m.handle == r["lease_id"]:
                            m.visible_at = 0
            else:
                return self._reply(404, b'{"success": false, "errors": [{"message": "not found"}]}')
            self._reply(200, json.dumps({"success": True, "errors": [], "result": result}).encode())

    return Handler


def test_cloudflare_queue_pull_ack_and_retry():
    msgs: List[Msg] = []
    seen: List[Dict[str, Any]] = []
    with serve(_cf_handler(msgs, seen)) as base:
        q = make_queue_driver(
            {"use": "cloudflare_queue", "endpoint": base, "account_id": "acc", "queue_id": "qid", "api_token": "tok"}
        )
        q.submit("one", {})
        q.submit("two", {})
        claimed = q.claim(10, 45, time.time())
        assert seen[-1]["data"] == {"batch_size": 10, "visibility_timeout_ms": 45000}
        assert [m["body"] for m in claimed] == ["one", "two"] and claimed[0]["receives"] == 1
        q.settle(claimed, {claimed[1]["id"]}, max_receive=3, dead_letter=None, now=time.time())
        assert [m.body for m in msgs] == ["two"]
        assert q.claim(10, 45, time.time())[0]["receives"] == 2
        assert q.depth() == -1
        bad = make_queue_driver(
            {"use": "cloudflare_queue", "endpoint": base, "account_id": "acc", "queue_id": "qid", "api_token": "no"}
        )
        with pytest.raises(DriverError, match="Authentication error"):
            bad.claim(1, 10, time.time())
    with pytest.raises(ValueError, match="queue_id, api_token"):
        make_queue_driver({"use": "cloudflare_queue", "account_id": "acc"})


# --------------------------------------------------------------------------- S3 presets


@pytest.mark.parametrize(
    "provider,options,endpoint,path_style,region",
    [
        ("aws", {"region": "eu-west-1"}, "https://s3.eu-west-1.amazonaws.com", False, "eu-west-1"),
        ("oss", {"region": "cn-hangzhou"}, "https://oss-cn-hangzhou.aliyuncs.com", False, "cn-hangzhou"),
        ("cos", {"region": "ap-guangzhou"}, "https://cos.ap-guangzhou.myqcloud.com", False, "ap-guangzhou"),
        ("obs", {"region": "cn-north-4"}, "https://obs.cn-north-4.myhuaweicloud.com", False, "cn-north-4"),
        (
            "oci",
            {"region": "us-ashburn-1", "namespace": "axaxnpcrorw5"},
            "https://axaxnpcrorw5.compat.objectstorage.us-ashburn-1.oraclecloud.com",
            True,
            "us-ashburn-1",
        ),
        ("ibm_cos", {"region": "us-south"}, "https://s3.us-south.cloud-object-storage.appdomain.cloud", True, "us-south"),
        ("spaces", {"region": "nyc3"}, "https://nyc3.digitaloceanspaces.com", False, "nyc3"),
        ("r2", {"account_id": "abc123"}, "https://abc123.r2.cloudflarestorage.com", True, "auto"),
        ("minio", {"endpoint": "http://minio:9000"}, "http://minio:9000", True, "us-east-1"),
    ],
)
def test_s3_presets(provider, options, endpoint, path_style, region):
    assert s3_preset(provider, options) == (endpoint, path_style, region)
    store = make_storage_driver({"use": provider, "access_key": "a", "secret_key": "b", **options}, "bkt")
    assert store.region == region and store.path_style is path_style and store.bucket == "bkt"
    host, path = store._target("k")
    if path_style:
        assert path.startswith("/bkt/") and host == urlsplit(endpoint).netloc
    else:
        assert host == "bkt." + urlsplit(endpoint).netloc and path == "/k"


def test_s3_preset_requirements_and_overrides(monkeypatch):
    with pytest.raises(ValueError, match="oci storage preset needs namespace"):
        make_storage_driver({"use": "oci", "region": "x"}, "b")
    with pytest.raises(ValueError, match="needs account_id"):
        make_storage_driver({"use": "s3", "provider": "r2"}, "b")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "ENVAK")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "ENVSK")
    aws = make_storage_driver({"use": "s3"}, "b")  # no endpoint: AWS, credentials from the environment
    assert aws.access_key == "ENVAK" and aws.netloc == "s3.us-east-1.amazonaws.com" and aws.path_style is False
    local = make_storage_driver({"use": "aws", "endpoint": "http://localhost:4566", "path_style": True}, "b")
    assert local.netloc == "localhost:4566" and local.path_style is True
    legacy = make_storage_driver({"use": "s3", "endpoint": "http://minio:9000", "region": "x"}, "b")
    assert legacy.path_style is True and legacy.region == "x"


# --------------------------------------------------------------------------- custom


class GoodQueue:
    def __init__(self, url: str = "", token: str = "") -> None:
        self.url, self.token = url, token

    def submit(self, body: str, attributes: Dict[str, Any]) -> str:
        return "1"

    def claim(self, batch: int, visibility: float, now: float) -> List[Dict[str, Any]]:
        return []

    def settle(self, *args: Any) -> None:
        return None


class HalfQueue:
    def submit(self, body: str, attributes: Dict[str, Any]) -> str:
        return "1"


class Exploding:
    def __init__(self, **kwargs: Any) -> None:
        raise RuntimeError("cannot connect")


def test_custom_driver_loading_and_errors(monkeypatch):
    monkeypatch.setenv("CUSTOM_TOKEN", "t0k")
    here = __name__
    q = make_queue_driver({"use": "custom", "class": f"{here}:GoodQueue", "url": "u", "token_env": "CUSTOM_TOKEN"}, "jobs")
    assert isinstance(q, CustomQueue) and q.inner.url == "u" and q.inner.token == "t0k"
    assert q.depth() == -1 and q.recover(0, 0) is None and q.submit("x", {}) == "1"
    with pytest.raises(ValueError, match=r"'package.module:ClassName'"):
        make_queue_driver({"use": "custom", "class": "nocolon"}, "jobs")
    with pytest.raises(ValueError, match="cannot import 'no_such_mod_xyz'"):
        make_queue_driver({"use": "custom", "class": "no_such_mod_xyz:Q"}, "jobs")
    with pytest.raises(ValueError, match="has no attribute 'Missing'"):
        make_queue_driver({"use": "custom", "class": f"{here}:Missing"}, "jobs")
    with pytest.raises(ValueError, match="HalfQueue does not implement claim, settle"):
        make_queue_driver({"use": "custom", "class": f"{here}:HalfQueue"}, "jobs")
    with pytest.raises(ValueError, match=r"Exploding\(\*\*options\) failed: RuntimeError: cannot connect"):
        make_storage_driver({"use": "custom", "class": f"{here}:Exploding"}, "media")
    with pytest.raises(ValueError, match="does not implement scan, put, get, delete"):
        make_storage_driver({"use": "custom", "class": f"{here}:GoodQueue"}, "media")
