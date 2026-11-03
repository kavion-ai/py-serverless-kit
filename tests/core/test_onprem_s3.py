"""pskit's Amazon S3 compatible server (aws/s3) and its on-prem service.

The servers run for real here (Python always, Node.js when ``node`` is installed) and are driven through pskit's own
SigV4 signer and ``s3`` storage driver, raw HTTP, the web console and, when installed, boto3.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import http.cookiejar
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from py_serverless_kit.core import onprem_browser, onprem_console, onprem_s3
from py_serverless_kit.core import onprem_services as svc
from py_serverless_kit.runtime.drivers._aws import canonical_query, sign, uri_encode
from py_serverless_kit.runtime.drivers.s3 import S3Storage

from .test_onprem_services import RAW, FakeDocker

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "aws" / "s3"
SSH = {"method": "ssh", "host": "20.40.60.80", "user": "ubuntu", "identity_file": "key.pem"}
NODE = shutil.which("node")
IMPLS = [
    pytest.param([sys.executable, str(SOURCE / "python" / "server.py")], id="python"),
    pytest.param([NODE or "node", str(SOURCE / "nodejs" / "server.js")], id="nodejs",
                 marks=pytest.mark.skipif(not NODE, reason="node is not installed")),
]
ACCESS, SECRET = "AKIDPSKIT", "correct-horse-battery"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _strip(root: ET.Element) -> ET.Element:
    for el in root.iter():
        el.tag = el.tag.split("}", 1)[-1]
    return root


class Server:
    def __init__(self, argv, data: Path, **env) -> None:
        self.argv = argv
        self.port = _free_port()
        self.host = f"127.0.0.1:{self.port}"
        self.url = f"http://{self.host}"
        self.data = data
        full = {**os.environ, "S3_PORT": str(self.port), "S3_BIND": "127.0.0.1", "S3_DATA_DIR": str(data),
                "S3_ACCESS_KEY_ID": ACCESS, "S3_SECRET_ACCESS_KEY": SECRET, "S3_MIN_PART_SIZE": "5", **env}
        self.proc = subprocess.Popen(argv, env=full, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        deadline = time.monotonic() + 15
        while True:
            try:
                with urllib.request.urlopen(self.url + "/-/health", timeout=1) as resp:
                    if resp.status == 200:
                        return
            except OSError:
                if self.proc.poll() is not None or time.monotonic() > deadline:
                    out = self.proc.stdout.read().decode() if self.proc.stdout else ""
                    raise RuntimeError(f"server did not start: {out}") from None
                time.sleep(0.1)

    def stop(self) -> None:
        if self.proc.poll() is None:
            self.proc.terminate()
            self.proc.wait(10)
        if self.proc.stdout:
            self.proc.stdout.close()

    def call(self, method, bucket="", key="", query=None, body=b"", headers=None, *, access=ACCESS, secret=SECRET,
             signed=True, when=None):
        path = "/" + (uri_encode(bucket) if bucket else "") + ("/" + uri_encode(key, keep_slash=True) if key else "")
        query = dict(query or {})
        hdrs = dict(headers or {})
        if signed:
            hdrs = sign(method, self.host, path, query, hdrs, hashlib.sha256(body).hexdigest(), access, secret,
                        "us-east-1", when or datetime.now(timezone.utc))
        url = self.url + path + (f"?{canonical_query(query)}" if query else "")
        return self.raw(method, url, body, hdrs)

    @staticmethod
    def raw(method, url, body=b"", headers=None):
        req = urllib.request.Request(url, data=body if method in ("PUT", "POST") else None, method=method)
        for k, v in (headers or {}).items():
            if k != "host":
                req.add_header(k, v)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.status, {k.lower(): v for k, v in resp.headers.items()}, resp.read()
        except urllib.error.HTTPError as exc:
            return exc.code, {k.lower(): v for k, v in exc.headers.items()}, exc.read()

    def ok(self, *args, expect=(200,), **kwargs):
        status, headers, body = self.call(*args, **kwargs)
        assert status in expect, (status, body[:500])
        return headers, body

    def xml(self, *args, **kwargs) -> ET.Element:
        return _strip(ET.fromstring(self.ok(*args, **kwargs)[1]))

    def code(self, *args, **kwargs):
        status, _h, body = self.call(*args, **kwargs)
        return status, (_strip(ET.fromstring(body)).findtext("Code") if body.strip() else "")

    def presign(self, method, bucket, key, expires=300, when=None, secret=SECRET):
        now = when or datetime.now(timezone.utc)
        amz, day = now.strftime("%Y%m%dT%H%M%SZ"), now.strftime("%Y%m%d")
        path = f"/{bucket}/{uri_encode(key, keep_slash=True)}"
        query = {"X-Amz-Algorithm": "AWS4-HMAC-SHA256", "X-Amz-Credential": f"{ACCESS}/{day}/us-east-1/s3/aws4_request",
                 "X-Amz-Date": amz, "X-Amz-Expires": str(expires), "X-Amz-SignedHeaders": "host"}
        canonical = "\n".join([method, path, canonical_query(query), f"host:{self.host}\n", "host", "UNSIGNED-PAYLOAD"])
        to_sign = "\n".join(["AWS4-HMAC-SHA256", amz, f"{day}/us-east-1/s3/aws4_request",
                             hashlib.sha256(canonical.encode()).hexdigest()])
        k = ("AWS4" + secret).encode()
        for part in (day, "us-east-1", "s3", "aws4_request"):
            k = hmac.new(k, part.encode(), hashlib.sha256).digest()
        query["X-Amz-Signature"] = hmac.new(k, to_sign.encode(), hashlib.sha256).hexdigest()
        return f"{self.url}{path}?{canonical_query(query)}"


@pytest.fixture(params=IMPLS)
def server(request, tmp_path):
    srv = Server(request.param, tmp_path / "data")
    yield srv
    srv.stop()


# ----------------------------------------------------------------------------- the servers


def test_objects_metadata_ranges_and_conditions(server):
    server.ok("PUT", "photos")
    assert server.code("PUT", "photos") == (409, "BucketAlreadyOwnedByYou")
    assert server.code("PUT", "Bad_Name") == (400, "InvalidBucketName")
    headers, _ = server.ok("PUT", "photos", "2024/a b+c.txt", body=b"hello world",
                           headers={"content-type": "text/plain", "x-amz-meta-camera": "phone",
                                    "cache-control": "max-age=60", "x-amz-tagging": "album=pets&year=2024"})
    etag = headers["etag"]
    assert etag == f'"{hashlib.md5(b"hello world").hexdigest()}"'  # noqa: S324
    got, body = server.ok("GET", "photos", "2024/a b+c.txt")
    assert body == b"hello world" and got["content-type"] == "text/plain" and got["x-amz-meta-camera"] == "phone"
    assert got["cache-control"] == "max-age=60" and got["x-amz-tagging-count"] == "2"
    part, body = server.ok("GET", "photos", "2024/a b+c.txt", headers={"range": "bytes=6-"}, expect=(206,))
    assert body == b"world" and part["content-range"] == "bytes 6-10/11"
    assert server.code("GET", "photos", "2024/a b+c.txt", headers={"range": "bytes=50-"}) == (416, "InvalidRange")
    assert server.call("GET", "photos", "2024/a b+c.txt", headers={"if-none-match": etag})[0] == 304
    assert server.code("GET", "photos", "2024/a b+c.txt", headers={"if-match": '"nope"'}) == (412, "PreconditionFailed")
    assert server.code("PUT", "photos", "2024/a b+c.txt", body=b"x", headers={"if-none-match": "*"}) == (
        412, "PreconditionFailed")
    assert server.code("GET", "photos", "missing") == (404, "NoSuchKey")
    bad_md5 = base64.b64encode(hashlib.md5(b"other").digest()).decode()  # noqa: S324
    assert server.code("PUT", "photos", "x", body=b"data", headers={"content-md5": bad_md5}) == (400, "BadDigest")
    crc = base64.b64encode(hashlib.sha256(b"data").digest()).decode()
    stored, _ = server.ok("PUT", "photos", "sha", body=b"data", headers={"x-amz-checksum-sha256": crc})
    assert stored["x-amz-checksum-sha256"] == crc
    assert server.code("PUT", "photos", "sha", body=b"datx", headers={"x-amz-checksum-sha256": crc}) == (
        400, "BadDigest")
    tags = server.xml("GET", "photos", "2024/a b+c.txt", query={"tagging": ""})
    assert {t.findtext("Key"): t.findtext("Value") for t in tags.iter("Tag")} == {"album": "pets", "year": "2024"}
    copied = server.xml("PUT", "photos", "copy.txt", headers={"x-amz-copy-source": "/photos/2024/a%20b%2Bc.txt"})
    assert copied.findtext("ETag") == etag
    assert server.ok("GET", "photos", "copy.txt")[1] == b"hello world"
    assert server.code("PUT", "photos", "copy.txt", headers={"x-amz-copy-source": "/photos/copy.txt"})[1] == (
        "InvalidRequest")


def test_listing_with_delimiters_paging_and_url_encoding(server):
    server.ok("PUT", "list")
    for key in ("a/1", "a/2", "b/1", "c", "d e", "f"):
        server.ok("PUT", "list", key, body=b"x")
    root = server.xml("GET", "list", query={"list-type": "2", "delimiter": "/"})
    assert [p.findtext("Prefix") for p in root.iter("CommonPrefixes")] == ["a/", "b/"]
    assert [c.findtext("Key") for c in root.iter("Contents")] == ["c", "d e", "f"]
    keys, token = [], None
    while True:
        query = {"list-type": "2", "max-keys": "2", **({"continuation-token": token} if token else {})}
        page = server.xml("GET", "list", query=query)
        keys += [c.findtext("Key") for c in page.iter("Contents")]
        token = page.findtext("NextContinuationToken")
        if page.findtext("IsTruncated") != "true":
            break
    assert keys == ["a/1", "a/2", "b/1", "c", "d e", "f"]
    v1 = server.xml("GET", "list", query={"marker": "b/1", "encoding-type": "url"})
    assert [c.findtext("Key") for c in v1.iter("Contents")] == ["c", "d%20e", "f"]
    deleted = server.xml("POST", "list", query={"delete": ""},
                         body=b"<Delete><Object><Key>c</Key></Object><Object><Key>f</Key></Object></Delete>")
    assert sorted(d.findtext("Key") for d in deleted.iter("Deleted")) == ["c", "f"]
    assert server.code("DELETE", "list") == (409, "BucketNotEmpty")


def test_versioning_and_delete_markers(server):
    server.ok("PUT", "ver")
    server.ok("PUT", "ver", query={"versioning": ""},
              body=b"<VersioningConfiguration><Status>Enabled</Status></VersioningConfiguration>")
    v1 = server.ok("PUT", "ver", "f", body=b"one")[0]["x-amz-version-id"]
    server.ok("PUT", "ver", "f", body=b"two")
    gone = server.ok("DELETE", "ver", "f", expect=(204,))[0]
    assert gone["x-amz-delete-marker"] == "true"
    assert server.code("GET", "ver", "f") == (404, "NoSuchKey")
    assert server.ok("GET", "ver", "f", query={"versionId": v1})[1] == b"one"
    versions = server.xml("GET", "ver", query={"versions": ""})
    assert len(versions.findall("Version")) == 2 and len(versions.findall("DeleteMarker")) == 1
    assert versions.find("DeleteMarker").findtext("IsLatest") == "true"
    server.ok("DELETE", "ver", "f", query={"versionId": gone["x-amz-version-id"]}, expect=(204,))
    assert server.ok("GET", "ver", "f")[1] == b"two"
    assert server.xml("GET", "ver", query={"versioning": ""}).findtext("Status") == "Enabled"


def test_multipart_upload_with_checksums(server):
    server.ok("PUT", "mpu")
    init = server.xml("POST", "mpu", "big.bin", query={"uploads": ""}, headers={"x-amz-checksum-algorithm": "CRC32"})
    upload_id = init.findtext("UploadId")
    parts = [b"a" * 10, b"b" * 10, b"c" * 3]
    etags = []
    for n, data in enumerate(parts, 1):
        headers, _ = server.ok("PUT", "mpu", "big.bin", query={"partNumber": str(n), "uploadId": upload_id}, body=data)
        etags.append(headers["etag"])
    listed = server.xml("GET", "mpu", "big.bin", query={"uploadId": upload_id})
    assert [p.findtext("PartNumber") for p in listed.iter("Part")] == ["1", "2", "3"]
    uploads = server.xml("GET", "mpu", query={"uploads": ""})
    assert [u.findtext("UploadId") for u in uploads.iter("Upload")] == [upload_id]
    wrong = "".join(f"<Part><PartNumber>{n}</PartNumber><ETag>{e}</ETag></Part>" for n, e in ((2, etags[1]), (1, etags[0])))
    assert server.code("POST", "mpu", "big.bin", query={"uploadId": upload_id},
                       body=f"<CompleteMultipartUpload>{wrong}</CompleteMultipartUpload>".encode()) == (
        400, "InvalidPartOrder")
    body = "".join(f"<Part><PartNumber>{n}</PartNumber><ETag>{e}</ETag></Part>" for n, e in enumerate(etags, 1))
    done = server.xml("POST", "mpu", "big.bin", query={"uploadId": upload_id},
                      body=f"<CompleteMultipartUpload>{body}</CompleteMultipartUpload>".encode())
    expected = hashlib.md5(b"".join(hashlib.md5(p).digest() for p in parts)).hexdigest() + "-3"  # noqa: S324
    assert done.findtext("ETag") == f'"{expected}"' and done.findtext("ChecksumCRC32").endswith("-3")
    got, data = server.ok("GET", "mpu", "big.bin")
    assert data == b"".join(parts) and got["x-amz-mp-parts-count"] == "3"
    assert server.ok("GET", "mpu", "big.bin", query={"partNumber": "2"}, expect=(206,))[1] == b"b" * 10
    assert server.code("GET", "mpu", "big.bin", query={"uploadId": upload_id}) == (404, "NoSuchUpload")


def test_signatures_presigned_urls_and_anonymous_access(server):
    server.ok("PUT", "pub")
    server.ok("PUT", "pub", "doc.txt", body=b"public?")
    assert server.code("GET", "", secret="wrong") == (403, "SignatureDoesNotMatch")
    assert server.code("GET", "", access="NOBODY") == (403, "InvalidAccessKeyId")
    old = datetime.now(timezone.utc) - timedelta(hours=1)
    assert server.code("GET", "", when=old) == (403, "RequestTimeTooSkewed")
    assert server.raw("GET", server.presign("GET", "pub", "doc.txt"))[2] == b"public?"
    assert server.raw("GET", server.presign("GET", "pub", "doc.txt", secret="wrong"))[0] == 403
    expired = server.presign("GET", "pub", "doc.txt", expires=60, when=datetime.now(timezone.utc) - timedelta(hours=1))
    assert server.raw("GET", expired)[0] == 403
    assert server.raw("PUT", server.presign("PUT", "pub", "up.txt"), b"via link")[0] == 200
    assert server.ok("GET", "pub", "up.txt")[1] == b"via link"
    assert server.call("GET", "pub", "doc.txt", signed=False)[0] == 403
    policy = {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Principal": "*", "Action": "s3:GetObject",
                                                      "Resource": "arn:aws:s3:::pub/*"}]}
    server.ok("PUT", "pub", query={"policy": ""}, body=json.dumps(policy).encode(), expect=(204,))
    assert server.call("GET", "pub", "doc.txt", signed=False)[2] == b"public?"
    assert server.call("GET", "pub", signed=False)[0] == 403              # listing was not granted
    assert server.call("PUT", "pub", "x", body=b"no", signed=False)[0] == 403
    status = server.xml("GET", "pub", query={"policyStatus": ""})
    assert status.findtext("IsPublic") == "true"
    block = (b"<PublicAccessBlockConfiguration><RestrictPublicBuckets>true</RestrictPublicBuckets>"
             b"</PublicAccessBlockConfiguration>")
    server.ok("PUT", "pub", query={"publicAccessBlock": ""}, body=block)
    assert server.call("GET", "pub", "doc.txt", signed=False)[0] == 403


@pytest.mark.parametrize("argv", IMPLS)
def test_cors_lifecycle_object_lock_and_website(tmp_path, argv):
    server = Server(argv, tmp_path / "data", S3_LIFECYCLE_DAY_SECONDS="1")
    try:
        server.ok("PUT", "cfg")
        cors = (b"<CORSConfiguration><CORSRule><AllowedOrigin>https://app.example</AllowedOrigin>"
                b"<AllowedMethod>GET</AllowedMethod><AllowedHeader>*</AllowedHeader><MaxAgeSeconds>60</MaxAgeSeconds>"
                b"</CORSRule></CORSConfiguration>")
        server.ok("PUT", "cfg", query={"cors": ""}, body=cors)
        status, headers, _ = server.raw("OPTIONS", server.url + "/cfg/x", headers={
            "Origin": "https://app.example", "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "x-custom"})
        assert status == 200 and headers["access-control-allow-origin"] == "https://app.example"
        assert server.raw("OPTIONS", server.url + "/cfg/x", headers={
            "Origin": "https://evil.example", "Access-Control-Request-Method": "GET"})[0] == 403
        server.ok("PUT", "cfg", "tmp/old", body=b"x")
        server.ok("PUT", "cfg", "keep/new", body=b"x")
        rules = (b"<LifecycleConfiguration><Rule><ID>tmp</ID><Filter><Prefix>tmp/</Prefix></Filter>"
                 b"<Status>Enabled</Status><Expiration><Days>1</Days></Expiration></Rule></LifecycleConfiguration>")
        server.ok("PUT", "cfg", query={"lifecycle": ""}, body=rules)
        time.sleep(1.2)
        _console_post(server, "RunLifecycle", {})
        assert server.code("GET", "cfg", "tmp/old") == (404, "NoSuchKey")
        assert server.ok("GET", "cfg", "keep/new")[1] == b"x"

        server.ok("PUT", "locked", headers={"x-amz-bucket-object-lock-enabled": "true"})
        until = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        vid = server.ok("PUT", "locked", "x", body=b"1", headers={
            "x-amz-object-lock-mode": "GOVERNANCE", "x-amz-object-lock-retain-until-date": until})[0]["x-amz-version-id"]
        assert server.code("DELETE", "locked", "x", query={"versionId": vid}) == (403, "AccessDenied")
        server.ok("DELETE", "locked", "x", query={"versionId": vid},
                  headers={"x-amz-bypass-governance-retention": "true"}, expect=(204,))

        server.ok("PUT", "site")
        server.ok("PUT", "site", "index.html", body=b"<h1>home</h1>", headers={"content-type": "text/html",
                                                                               "x-amz-acl": "public-read"})
        server.ok("PUT", "site", query={"website": ""}, body=b"<WebsiteConfiguration><IndexDocument><Suffix>"
                  b"index.html</Suffix></IndexDocument></WebsiteConfiguration>")
        status, headers, body = server.raw("GET", server.url + "/-/website/site/")
        assert status == 200 and body == b"<h1>home</h1>" and headers["content-type"] == "text/html"
    finally:
        server.stop()


def test_streaming_chunked_upload_signatures(server):
    server.ok("PUT", "stream")
    now = datetime.now(timezone.utc)
    amz, day = now.strftime("%Y%m%dT%H%M%SZ"), now.strftime("%Y%m%d")
    scope = f"{day}/us-east-1/s3/aws4_request"
    chunks = [b"x" * 70000, b"tail", b""]
    encoded_len = sum(len(f"{len(c):x};chunk-signature=".encode()) + 64 + 4 + len(c) for c in chunks)
    headers = {"x-amz-content-sha256": "STREAMING-AWS4-HMAC-SHA256-PAYLOAD", "content-encoding": "aws-chunked",
               "x-amz-decoded-content-length": str(sum(map(len, chunks))), "content-length": str(encoded_len)}
    signed = sign("PUT", server.host, "/stream/chunked", {}, headers, headers["x-amz-content-sha256"], ACCESS, SECRET,
                  "us-east-1", now)
    key = ("AWS4" + SECRET).encode()
    for part in (day, "us-east-1", "s3", "aws4_request"):
        key = hmac.new(key, part.encode(), hashlib.sha256).digest()
    prev = signed["authorization"].rsplit("Signature=", 1)[1]
    body = b""
    for chunk in chunks:
        to_sign = "\n".join(["AWS4-HMAC-SHA256-PAYLOAD", amz, scope, prev, hashlib.sha256(b"").hexdigest(),
                             hashlib.sha256(chunk).hexdigest()])
        prev = hmac.new(key, to_sign.encode(), hashlib.sha256).hexdigest()
        body += f"{len(chunk):x};chunk-signature={prev}\r\n".encode() + chunk + b"\r\n"
    assert server.raw("PUT", server.url + "/stream/chunked", body, signed)[0] == 200
    assert server.ok("GET", "stream", "chunked")[1] == b"x" * 70000 + b"tail"
    tampered = body.replace(b"tail", b"TAIL")
    assert server.raw("PUT", server.url + "/stream/chunked", tampered, signed)[0] == 403


def test_pskit_s3_driver_works_with_it(server):
    store = S3Storage(server.url, "driver", access_key=ACCESS, secret_key=SECRET)
    server.ok("PUT", "driver")
    store.put("in/a.csv", b"1,2")
    store.put("in/b.csv", b"3,4")
    assert store.get("in/a.csv") == b"1,2"
    assert sorted(store.scan()) == ["in/a.csv", "in/b.csv"]
    assert store.delete("in/a.csv")
    assert store.keys() == ["in/b.csv"]


def test_data_survives_a_restart_and_the_other_server_reads_it(server):
    server.ok("PUT", "kept")
    server.ok("PUT", "kept", "deep/key.txt", body=b"still here", headers={"x-amz-meta-a": "1"})
    server.stop()
    record = next((server.data / "buckets" / "kept" / "objects").glob("*/*.json"))
    assert json.loads(record.read_text())["key"] == "deep/key.txt"
    if os.name != "nt":
        assert record.stat().st_mode & 0o777 == 0o600
    other = IMPLS[1].values[0] if server.argv[0] == sys.executable else IMPLS[0].values[0]
    if not Path(other[1]).is_file() or (other[1].endswith(".js") and not NODE):
        return
    again = Server(other, server.data)
    try:
        got, body = again.ok("GET", "kept", "deep/key.txt")
        assert body == b"still here" and got["x-amz-meta-a"] == "1"
    finally:
        again.stop()


def test_boto3_works_unchanged(server):
    boto3 = pytest.importorskip("boto3")
    from botocore.config import Config

    s3 = boto3.client("s3", endpoint_url=server.url, region_name="us-east-1", aws_access_key_id=ACCESS,
                      aws_secret_access_key=SECRET, config=Config(s3={"addressing_style": "path"}))
    s3.create_bucket(Bucket="boto")
    s3.put_object(Bucket="boto", Key="k", Body=b"v", Metadata={"m": "1"})
    assert s3.get_object(Bucket="boto", Key="k")["Body"].read() == b"v"
    pages = s3.get_paginator("list_objects_v2").paginate(Bucket="boto", PaginationConfig={"PageSize": 1})
    assert [c["Key"] for p in pages for c in p.get("Contents", [])] == ["k"]
    url = s3.generate_presigned_url("get_object", Params={"Bucket": "boto", "Key": "k"}, ExpiresIn=60)
    assert urllib.request.urlopen(url, timeout=5).read() == b"v"  # noqa: S310 - local test server
    with pytest.raises(s3.exceptions.NoSuchKey):
        s3.get_object(Bucket="boto", Key="nope")


def _console(server):
    jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def _console_post(server, op, body, opener=None, csrf=None):
    opener = opener or _console(server)
    if csrf is None:
        req = urllib.request.Request(server.url + "/ui/login", method="POST", headers={"Content-Type": "application/json"},
                                     data=json.dumps({"user": ACCESS, "password": SECRET}).encode())
        csrf = json.loads(opener.open(req, timeout=5).read())["csrf"]
    req = urllib.request.Request(server.url + "/ui/api/" + op, method="POST", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "X-S3-CSRF": csrf})
    return json.loads(opener.open(req, timeout=10).read())


def test_web_console_needs_a_login_and_the_csrf_token(server):
    opener = _console(server)

    def post(path, body, headers=None):
        req = urllib.request.Request(server.url + path, data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json", **(headers or {})})
        try:
            with opener.open(req, timeout=5) as resp:
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())

    with opener.open(server.url + "/ui/", timeout=5) as resp:
        page = resp.read().decode()
        assert "S3 console" in page and "frame-ancestors 'none'" in resp.headers["Content-Security-Policy"]
    assert post("/ui/api/ListBuckets", {})[0] == 401
    assert post("/ui/login", {"user": ACCESS, "password": "wrong"})[0] == 401
    status, login = post("/ui/login", {"user": ACCESS, "password": SECRET})
    assert status == 200 and login["csrf"]
    assert post("/ui/api/ListBuckets", {})[0] == 403
    headers = {"X-S3-CSRF": login["csrf"]}
    assert post("/ui/api/CreateBucket", {"bucket": "from-ui", "versioning": True}, headers)[0] == 200
    up = urllib.request.Request(server.url + "/ui/upload?bucket=from-ui&key=docs%2Fnote.txt", data=b"console text",
                                method="PUT", headers={"Content-Type": "text/plain", **headers})
    assert json.loads(opener.open(up, timeout=5).read())["key"] == "docs/note.txt"
    status, listed = post("/ui/api/ListObjects", {"bucket": "from-ui", "prefix": ""}, headers)
    assert listed["folders"] == ["docs/"]
    status, listed = post("/ui/api/ListObjects", {"bucket": "from-ui", "prefix": "docs/"}, headers)
    assert [o["key"] for o in listed["objects"]] == ["docs/note.txt"]
    with opener.open(server.url + "/ui/download?bucket=from-ui&key=docs%2Fnote.txt", timeout=5) as resp:
        assert resp.read() == b"console text" and resp.headers["Content-Disposition"].startswith("attachment")
    status, info = post("/ui/api/BucketInfo", {"bucket": "from-ui"}, headers)
    assert info["versioning"] == "Enabled" and info["stats"]["objects"] == 1
    status, link = post("/ui/api/Presign", {"bucket": "from-ui", "key": "docs/note.txt", "host": server.host}, headers)
    assert urllib.request.urlopen(link["url"], timeout=5).read() == b"console text"  # noqa: S310 - local test server
    status, err = post("/ui/api/DeleteBucket", {"bucket": "from-ui"}, headers)
    assert status == 409 and err["code"] == "BucketNotEmpty"
    assert post("/ui/api/DeleteBucket", {"bucket": "from-ui", "force": True}, headers)[0] == 200
    post("/ui/logout", {}, headers)
    assert post("/ui/api/ListBuckets", {}, headers)[0] == 401


def test_refuses_to_start_without_credentials(tmp_path):
    env = {k: v for k, v in os.environ.items() if not k.startswith("S3_")}
    out = subprocess.run([sys.executable, str(SOURCE / "python" / "server.py")], env=env, capture_output=True,
                         text=True, timeout=30)
    assert out.returncode == 2 and "S3_SECRET_ACCESS_KEY" in out.stderr


# ----------------------------------------------------------------------------- the on-prem service


def _create(tmp_path, **body):
    fake = FakeDocker()
    req = {"key": "files", "service": "s3", "password": "Sup3r-secret-pw", **body}
    entry = svc.create(tmp_path, req, RAW, lambda _l: None, run=fake, wait_seconds=1)
    return entry, fake.calls


def test_catalog_lists_both_servers():
    items = {i["id"]: i for i in svc.catalog()}
    for sid, lang in (("s3", "Python"), ("s3-node", "Node.js")):
        item = items[sid]
        assert item["auth"] and item["port"] == 9000 and item["backup"] and "storage" in item["roles"]
        assert lang in item["label"] and item["gui"] == ["S3 console"]
        assert item["browsers"] == ["s3"] and onprem_console.CONSOLES[sid]["input"] == "cli"


def test_create_copies_the_server_into_a_stock_image(tmp_path):
    entry, calls = _create(tmp_path, user="AKIDLOCAL")
    create = next(c for c in calls if c[:2] == ["docker", "create"])
    env = dict(create[i + 1].split("=", 1) for i, arg in enumerate(create) if arg == "-e")
    assert env["S3_ACCESS_KEY_ID"] == "AKIDLOCAL" and env["S3_SECRET_ACCESS_KEY"] == "Sup3r-secret-pw"
    assert "127.0.0.1:9000:9000" in create and create[-3:] == ["python:3.12-alpine", "python", "/app/server.py"]
    cp = next(c for c in calls if c[:2] == ["docker", "cp"])
    assert cp[-1].endswith(":/app")
    assert calls.index(create) < calls.index(cp) < calls.index(["docker", "start", entry["container"]])
    assert entry["env"] == {"PSKIT_FILES_ACCESS_KEY": "AKIDLOCAL", "PSKIT_FILES_SECRET_KEY": "Sup3r-secret-pw",
                            "PSKIT_FILES_URL": "http://127.0.0.1:9000"}
    res = entry["resource"]
    assert res["type"] == "storage" and res["options"]["driver"] == "s3" and res["options"]["bucket"] == "files"
    assert res["options"]["path_style"] and res["options"]["create_bucket"]
    assert res["options"]["secret_key_env"] == "PSKIT_FILES_SECRET_KEY"
    links = svc.gui_links(entry)
    assert links[0]["url"] == "http://127.0.0.1:9000/ui/" and "AKIDLOCAL" in links[0]["login"]


def test_create_over_ssh_copies_with_scp_then_docker_cp(tmp_path, monkeypatch):
    monkeypatch.setattr(svc, "check_ssh_login", lambda _t: None)
    entry, calls = _create(tmp_path, service="s3-node", target=SSH)
    texts = [" ".join(c) for c in calls]
    scps = [t for t in texts if t.startswith("scp") or " scp " in t]
    assert sorted(t.rsplit("/", 1)[-1] for t in scps) == ["index.html", "server.js"]
    create = next(t for t in texts if "docker 'create'" in t)
    assert "'node:22-alpine' 'node' '/app/server.js'" in create and "'0.0.0.0:9000:9000'" in create
    assert entry["env"]["PSKIT_FILES_URL"] == "http://20.40.60.80:9000"


def test_copied_files_are_the_repository_copy():
    files = onprem_s3.app_files("s3")
    assert files["server.py"] == (SOURCE / "python" / "server.py").read_bytes()
    assert files["index.html"] == (SOURCE / "ui" / "index.html").read_bytes()


def test_usage_guide_and_browser_use_the_service_keys(tmp_path, monkeypatch):
    entry, _calls = _create(tmp_path, user="AKIDLOCAL", key="media")
    usage = svc.service_usage(tmp_path, "media", probe=False)["markdown"]
    assert 'boto3.client(\n    "s3"' in usage and "PSKIT_MEDIA_SECRET_KEY" in usage
    assert "http://127.0.0.1:9000/ui/" in usage and "forcePathStyle: true" in usage
    seen = {}

    def fake_fetch(_control, _method, _path, _data, headers, timeout=None):
        seen.update(headers)
        return 200, {}, b"<ListAllMyBucketsResult><Buckets/></ListAllMyBucketsResult>"

    monkeypatch.setattr(onprem_browser, "_fetch", fake_fetch)
    assert onprem_browser.browse(entry, "s3", "buckets", {}) == {"buckets": []}
    assert seen["authorization"].startswith("AWS4-HMAC-SHA256 Credential=AKIDLOCAL/")


def test_private_bucket_refuses_requests_without_keys_but_share_links_work_until_they_expire(server):
    entry = {"service": "s3", "address": "127.0.0.1", "port": server.port, "target": {"method": "local"},
             "user": ACCESS, "env": {"PSKIT_M_ACCESS_KEY": ACCESS, "PSKIT_M_SECRET_KEY": SECRET}}
    server.ok("PUT", "media")
    server.ok("PUT", "media", "open.txt", body=b"was public", headers={"x-amz-acl": "public-read"})
    assert server.call("GET", "media", "open.txt", signed=False)[2] == b"was public"
    out = onprem_browser.browse(entry, "s3", "policy", {"bucket": "media", "preset": "public-read"})
    assert out["blocked"] is False and server.call("GET", "media", "open.txt", signed=False)[0] == 200

    out = onprem_browser.browse(entry, "s3", "policy", {"bucket": "media", "preset": "private"})
    assert out == {"policy": "", "blocked": True}
    assert server.call("GET", "media", "open.txt", signed=False)[0] == 403   # the object ACL is ignored now
    assert server.raw("GET", server.url + "/-/website/media/open.txt")[0] in (403, 404)
    assert server.ok("GET", "media", "open.txt")[1] == b"was public"          # keys still work

    url = onprem_browser.browse(entry, "s3", "share", {"bucket": "media", "key": "open.txt", "expires": 2})["url"]
    assert "X-Amz-Expires=2&" in url and server.raw("GET", url)[2] == b"was public"
    time.sleep(3.1)
    assert server.raw("GET", url)[0] == 403
    for bad in (0, 604801, "soon"):
        with pytest.raises(onprem_browser.BrowseError, match="expires|1 second"):
            onprem_browser.browse(entry, "s3", "share", {"bucket": "media", "key": "open.txt", "expires": bad})
    console = _console_post(server, "Presign", {"bucket": "media", "key": "open.txt", "expires": 90})
    assert console["expires"] == 90 and "X-Amz-Expires=90&" in console["url"]
