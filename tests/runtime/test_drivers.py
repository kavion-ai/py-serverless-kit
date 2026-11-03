"""On-premises queue / storage drivers, against in-process fakes."""

from __future__ import annotations

import socketserver
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Dict, List
from urllib.parse import parse_qsl, unquote, urlsplit

import pytest

from py_serverless_kit.runtime.drivers import make_queue_driver, make_storage_driver
from py_serverless_kit.runtime.drivers.redis import RedisError, RedisQueue, encode_command, parse_url
from py_serverless_kit.runtime.drivers.s3 import EMPTY_SHA256, S3Error, S3Storage, sign

# --------------------------------------------------------------------------- fake redis


class FakeRedisState:
    def __init__(self, password: str = "") -> None:
        self.password = password
        self.lists: Dict[bytes, List[bytes]] = {}
        self.hashes: Dict[bytes, Dict[bytes, bytes]] = {}
        self.lock = threading.Lock()
        self.commands: List[str] = []


def _bulk(value):
    if value is None:
        return b"$-1\r\n"
    return b"$%d\r\n%s\r\n" % (len(value), value)


def _make_redis_handler(state: FakeRedisState):
    class Handler(socketserver.StreamRequestHandler):
        def handle(self) -> None:
            authed = not state.password
            while True:
                line = self.rfile.readline()
                if not line:
                    return
                count = int(line[1:].strip())
                args = []
                for _ in range(count):
                    size = int(self.rfile.readline()[1:].strip())
                    args.append(self.rfile.read(size + 2)[:-2])
                cmd = args[0].decode().upper()
                state.commands.append(cmd)
                if cmd == "AUTH":
                    authed = args[-1].decode() == state.password
                    self.wfile.write(b"+OK\r\n" if authed else b"-WRONGPASS invalid password\r\n")
                    continue
                if not authed:
                    self.wfile.write(b"-NOAUTH Authentication required.\r\n")
                    continue
                with state.lock:
                    self.wfile.write(self._run(cmd, args[1:]))

        def _run(self, cmd: str, a: List[bytes]) -> bytes:
            lists, hashes = state.lists, state.hashes
            if cmd == "SELECT":
                return b"+OK\r\n"
            if cmd == "LPUSH":
                lst = lists.setdefault(a[0], [])
                for item in a[1:]:
                    lst.insert(0, item)
                return b":%d\r\n" % len(lst)
            if cmd == "RPUSH":
                lst = lists.setdefault(a[0], [])
                lst.extend(a[1:])
                return b":%d\r\n" % len(lst)
            if cmd == "RPOPLPUSH":
                src = lists.get(a[0]) or []
                if not src:
                    return _bulk(None)
                item = src.pop()
                lists.setdefault(a[1], []).insert(0, item)
                return _bulk(item)
            if cmd == "LREM":
                lst = lists.get(a[0]) or []
                if a[2] in lst:
                    lst.remove(a[2])
                    return b":1\r\n"
                return b":0\r\n"
            if cmd == "LLEN":
                return b":%d\r\n" % len(lists.get(a[0]) or [])
            if cmd == "LRANGE":
                items = list(lists.get(a[0]) or [])
                return b"*%d\r\n" % len(items) + b"".join(_bulk(i) for i in items)
            if cmd == "HSET":
                hashes.setdefault(a[0], {})[a[1]] = a[2]
                return b":1\r\n"
            if cmd == "HDEL":
                return b":%d\r\n" % (1 if hashes.get(a[0], {}).pop(a[1], None) is not None else 0)
            if cmd == "HGETALL":
                flat = [x for kv in (hashes.get(a[0]) or {}).items() for x in kv]
                return b"*%d\r\n" % len(flat) + b"".join(_bulk(i) for i in flat)
            return b"-ERR unknown command\r\n"

    return Handler


@pytest.fixture
def redis_server():
    state = FakeRedisState(password="s3cret")

    class Server(socketserver.ThreadingTCPServer):
        allow_reuse_address = True
        daemon_threads = True

    server = Server(("127.0.0.1", 0), _make_redis_handler(state))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"redis://:s3cret@127.0.0.1:{server.server_address[1]}/2", state
    server.shutdown()
    server.server_close()


def test_parse_url_and_encoding():
    s = parse_url("rediss://user:p%40ss@cache.local:6380/3")
    assert s == {"host": "cache.local", "port": 6380, "username": "user", "password": "p@ss", "db": 3, "tls": True}
    assert parse_url("redis://h")["port"] == 6379
    with pytest.raises(ValueError):
        parse_url("http://h")
    assert encode_command("SET", "k", 1) == b"*3\r\n$3\r\nSET\r\n$1\r\nk\r\n$1\r\n1\r\n"


def test_redis_queue_roundtrip(redis_server):
    url, state = redis_server
    q = make_queue_driver({"use": "redis", "url": url, "key": "jobs"})
    assert isinstance(q, RedisQueue)
    ids = [q.submit('{"n": 1}', {"a": "1"}), q.submit("two", {})]
    assert q.depth() == 2
    assert "AUTH" in state.commands and "SELECT" in state.commands
    claimed = q.claim(10, 30, time.time())
    assert [m["id"] for m in claimed] == ids  # FIFO
    assert claimed[0]["attributes"] == {"a": "1"} and claimed[1]["body"] == "two"
    assert q.depth() == 0
    q.settle(claimed, {ids[1]}, max_receive=5, dead_letter=None, now=time.time())
    assert state.lists[b"jobs:processing"] == []
    again = q.claim(10, 30, time.time())
    assert [m["id"] for m in again] == [ids[1]] and again[0]["receives"] == 1


def test_redis_dead_letter_and_recover(redis_server):
    url, state = redis_server
    q = RedisQueue(url, "jobs")
    dlq = RedisQueue(url, "jobs-dlq")
    ident = q.submit("boom", {})
    msg = q.claim(1, 30, time.time())
    q.settle(msg, {ident}, max_receive=1, dead_letter=dlq, now=time.time())
    assert q.depth() == 0 and dlq.depth() == 1
    moved = dlq.claim(1, 30, time.time())[0]
    assert moved["body"] == "boom" and moved["attributes"]["pskit_source_queue"] == "jobs"

    q.submit("crash", {})
    q.claim(1, 30, now=100.0)
    q.recover(now=110.0, visibility=30)  # still invisible
    assert q.depth() == 0
    q.recover(now=200.0, visibility=30)
    assert q.depth() == 1 and not state.hashes[b"jobs:claims"]


def test_redis_plain_values_and_orphans(redis_server):
    url, state = redis_server
    q = RedisQueue(url, "ext")
    q.client.execute("LPUSH", "ext", "plain text")  # pushed by another producer
    msg = q.claim(1, 30, time.time())[0]
    assert msg["body"] == "plain text"
    q.recover(now=time.time(), visibility=30)  # claimed and recorded: not an orphan
    assert q.depth() == 0
    state.lists[b"ext:processing"].append(b"orphan")  # moved but never recorded
    q.recover(now=time.time(), visibility=30)
    assert q.depth() == 1


def test_redis_bad_password_and_unreachable(redis_server):
    url, _ = redis_server
    with pytest.raises(RedisError, match="WRONGPASS"):
        RedisQueue(url.replace("s3cret", "nope"), "x").depth()
    with pytest.raises(RedisError, match="unreachable"):
        RedisQueue("redis://127.0.0.1:1/0", "x").depth()


# --------------------------------------------------------------------------- s3


def test_sigv4_matches_aws_documentation_example():
    # "Example: GET Object" from the AWS Signature Version 4 documentation for S3.
    headers = sign(
        "GET",
        "examplebucket.s3.amazonaws.com",
        "/test.txt",
        {},
        {"Range": "bytes=0-9"},
        EMPTY_SHA256,
        "AKIAIOSFODNN7EXAMPLE",
        "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        "us-east-1",
        datetime(2013, 5, 24, tzinfo=timezone.utc),
    )
    assert headers["authorization"] == (
        "AWS4-HMAC-SHA256 Credential=AKIAIOSFODNN7EXAMPLE/20130524/us-east-1/s3/aws4_request, "
        "SignedHeaders=host;range;x-amz-content-sha256;x-amz-date, "
        "Signature=f0e8bdb87c964420e857bd35b5d6ed310bd44f0170aba48dd91039c6036bdb41"
    )


class FakeS3(BaseHTTPRequestHandler):
    objects: Dict[str, bytes] = {}
    auth_headers: List[str] = []
    paths: List[str] = []
    v1_only = False  # answers ListObjectsV2 with 400, pages ListObjects without NextMarker
    home_region = ""  # requests signed for another region get AWS's 400 naming this one
    bucket_bodies: List[bytes] = []

    def log_message(self, *args) -> None:
        return None

    def _parts(self):
        url = urlsplit(self.path)
        path = unquote(url.path)
        type(self).paths.append(path)
        type(self).auth_headers.append(self.headers.get("authorization", ""))
        bucket, _, key = path[1:].partition("/")
        return bucket, key, dict(parse_qsl(url.query))

    def _wrong_region(self) -> bool:
        home = type(self).home_region
        if home and f"/{home}/s3/" not in self.headers.get("authorization", ""):
            self._reply(400, f"<Error><Code>AuthorizationHeaderMalformed</Code><Region>{home}</Region></Error>".encode(),
                        {"x-amz-bucket-region": home})
            return True
        return False

    def _list_v1(self, query) -> None:
        keys = sorted(k for k in self.objects if k > query.get("marker", ""))
        page = keys[:2]
        items = "".join(f"<Contents><Key>{k}</Key><Size>{len(self.objects[k])}</Size></Contents>" for k in page)
        more = "true" if len(keys) > 2 else "false"
        self._reply(200, f"<ListBucketResult><IsTruncated>{more}</IsTruncated>{items}</ListBucketResult>".encode())

    def _reply(self, status: int, body: bytes = b"", headers=None) -> None:
        self.send_response(status)
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        bucket, key, query = self._parts()
        if self._wrong_region():
            return None
        if bucket != "media":
            return self._reply(404, b"<Error><Code>NoSuchBucket</Code></Error>")
        if self.v1_only and not key:
            if query.get("list-type") == "2":
                return self._reply(400, b"<Error><Code>InvalidArgument</Code></Error>")
            return self._list_v1(query)
        if query.get("list-type") == "2":
            keys = sorted(k for k in self.objects if k.startswith(query.get("prefix", "")))
            start = int(query.get("continuation-token", "0"))
            page = keys[start : start + 2]
            more = start + 2 < len(keys)
            items = "".join(
                f"<Contents><Key>{k}</Key><ETag>&quot;e{len(self.objects[k])}&quot;</ETag>"
                f"<Size>{len(self.objects[k])}</Size></Contents>"
                for k in page
            )
            token = f"<NextContinuationToken>{start + 2}</NextContinuationToken>" if more else ""
            xml = (
                '<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
                f"<IsTruncated>{'true' if more else 'false'}</IsTruncated>{token}{items}</ListBucketResult>"
            )
            return self._reply(200, xml.encode())
        if key not in self.objects:
            return self._reply(404)
        return self._reply(200, self.objects[key])

    def do_HEAD(self) -> None:  # noqa: N802
        _bucket, key, _ = self._parts()
        self._reply(200 if key in self.objects else 404)

    def do_PUT(self) -> None:  # noqa: N802
        _bucket, key, _ = self._parts()
        data = self.rfile.read(int(self.headers.get("content-length") or 0))
        if not key:  # CreateBucket
            type(self).bucket_bodies.append(data)
            return self._reply(409 if _bucket == "media" else 200)
        self.objects[key] = data
        self._reply(200)

    def do_DELETE(self) -> None:  # noqa: N802
        _bucket, key, _ = self._parts()
        self.objects.pop(key, None)
        self._reply(204)


@pytest.fixture
def s3_server():
    FakeS3.objects = {}
    FakeS3.auth_headers = []
    FakeS3.paths = []
    FakeS3.v1_only = False
    FakeS3.home_region = ""
    FakeS3.bucket_bodies = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeS3)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def test_s3_storage_roundtrip(s3_server):
    store = make_storage_driver(
        {
            "use": "s3",
            "endpoint": s3_server,
            "bucket": "media",
            "access_key": "AK",
            "secret_key": "SK",
            "prefix": "app/",
            "path_style": True,
        }
    )
    assert isinstance(store, S3Storage)
    for i in range(5):
        store.put(f"in/file {i}.txt", b"x" * i)
    FakeS3.objects["other/skip.txt"] = b"no"
    assert "/media/app/in/file 0.txt" in FakeS3.paths
    scanned = store.scan()  # 3 pages of 2
    assert sorted(scanned) == [f"in/file {i}.txt" for i in range(5)]
    assert scanned["in/file 3.txt"] == ("e3", 3)
    assert store.get("in/file 2.txt") == b"xx"
    assert store.delete("in/file 2.txt") is True
    assert store.delete("in/file 2.txt") is False
    with pytest.raises(KeyError):
        store.get("missing")
    assert all(h.startswith("AWS4-HMAC-SHA256 Credential=AK/") for h in FakeS3.auth_headers)


def test_s3_errors(s3_server):
    with pytest.raises(S3Error) as exc:
        S3Storage(s3_server, "nope").scan()
    assert exc.value.status == 404
    with pytest.raises(S3Error):
        S3Storage("http://127.0.0.1:1", "media", timeout=2).scan()
    with pytest.raises(ValueError):
        S3Storage("ftp://x", "b")


def test_s3_scan_falls_back_to_list_objects_v1(s3_server):
    FakeS3.v1_only = True
    FakeS3.objects = {f"k{i}": b"x" * i for i in range(5)}
    assert sorted(S3Storage(s3_server, "media").scan()) == [f"k{i}" for i in range(5)]


def test_s3_follows_the_bucket_region(s3_server):
    FakeS3.home_region = "eu-west-1"
    FakeS3.objects = {"a.txt": b"hi"}
    store = S3Storage(s3_server, "media", region="us-east-1", access_key="AK", secret_key="SK")
    assert store.get("a.txt") == b"hi"
    assert store.region == "eu-west-1"
    assert "/eu-west-1/s3/" in FakeS3.auth_headers[-1]


def test_s3_create_bucket_sends_the_region(s3_server):
    created = make_storage_driver(
        {"use": "s3", "endpoint": s3_server, "bucket": "fresh", "region": "eu-central-1", "access_key": "AK",
         "secret_key": "SK", "create_bucket": True}
    )
    created.put("a.txt", b"1")
    assert b"<LocationConstraint>eu-central-1</LocationConstraint>" in FakeS3.bucket_bodies[0]
    S3Storage(s3_server, "media").create_bucket()  # us-east-1: no body; 409 = already there
    assert FakeS3.bucket_bodies[-1] == b""


@pytest.mark.parametrize(
    "use,binding,endpoint",
    [
        ("wasabi", {"region": "eu-central-1"}, "https://s3.eu-central-1.wasabisys.com"),
        ("b2", {"region": "us-west-004"}, "https://s3.us-west-004.backblazeb2.com"),
        ("linode", {"region": "us-east-1"}, "https://us-east-1.linodeobjects.com"),
        ("scaleway", {"region": "fr-par"}, "https://s3.fr-par.scw.cloud"),
    ],
)
def test_more_s3_presets(use, binding, endpoint):
    store = make_storage_driver({"use": use, "bucket": "b", **binding})
    assert f"{store.scheme}://{store.netloc}" == endpoint
    assert store.path_style is False


def test_dotted_bucket_uses_path_style_over_https():
    store = S3Storage("https://s3.us-east-1.amazonaws.com", "my.site", path_style=False)
    assert store._target("k") == ("s3.us-east-1.amazonaws.com", "/my.site/k")
    assert S3Storage("https://s3.us-east-1.amazonaws.com", "plain", path_style=False)._target("k")[0] == (
        "plain.s3.us-east-1.amazonaws.com"
    )


def test_factories_return_none_for_file_backends():
    assert make_queue_driver(None) is None
    assert make_queue_driver({"use": "builtin"}) is None
    assert make_storage_driver({"use": "directory", "path": "/x"}) is None
    with pytest.raises(ValueError):
        make_queue_driver({"use": "kafka"})
