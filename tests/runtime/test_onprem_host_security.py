"""Security regressions of the on-premises host: admin auth, object keys and health output."""

from __future__ import annotations

import http.client
import json
from pathlib import Path

import pytest

from py_serverless_kit.runtime.onprem_host import _key_parts, _object_path, is_loopback_bind

from .test_onprem_host import _project, _server


def _call(base, method, path, body=None, headers=None):
    """Raw request: the path is sent exactly as written, and every header can be set."""
    address = base.split("//", 1)[1]
    conn = http.client.HTTPConnection(address, timeout=10)
    conn.request(method, path, body=body, headers=headers or {})
    reply = conn.getresponse()
    data = reply.read()
    conn.close()
    return reply.status, data


@pytest.fixture
def running(make_project, tmp_path):
    host, _out, _all = _project(make_project, tmp_path)
    started = []

    def start(**spec):
        host.spec.update(spec)
        httpd, base = _server(host)
        started.append(httpd)
        return host, base

    yield start
    for httpd in started:
        httpd.shutdown()
        httpd.server_close()


@pytest.mark.parametrize("key", [
    "%252E%252E%252Fescaped.txt",                  # the reported exploit: decoded twice
    "%252e%252e%252f%252e%252e%252fescaped.txt",
    "ok/%252E%252E%252F%252E%252E%252Fescaped.txt",
    "%2E%2E/escaped.txt",
    "..%2Fescaped.txt",
    "../escaped.txt",
])
def test_an_object_key_cannot_leave_its_bucket(running, tmp_path, key):
    host, base = running()
    root = Path(host.broker.bucket_dir("uploads")).resolve()
    status, _ = _call(base, "PUT", f"/__pskit/storage/uploads/{key}", body=b"owned")
    written = [p.resolve() for p in tmp_path.rglob("*") if p.is_file() and p.read_bytes() == b"owned"]
    outside = [p for p in written if root not in p.parents]
    assert not outside, f"{key} wrote {outside} (status {status})"


def test_a_percent_in_a_key_is_literal_and_round_trips(running):
    host, base = running()
    assert _call(base, "PUT", "/__pskit/storage/uploads/100%2525.txt", body=b"full")[0] < 300
    assert _call(base, "GET", "/__pskit/storage/uploads/100%2525.txt") == (200, b"full")
    assert (Path(host.broker.bucket_dir("uploads")) / "100%25.txt").read_bytes() == b"full"
    # The %2F left after the one decode is three plain characters, not a folder separator.
    assert _call(base, "PUT", "/__pskit/storage/uploads/a%252Fb", body=b"x")[0] < 300
    assert (Path(host.broker.bucket_dir("uploads")) / "a%2Fb").is_file()


def test_key_parts_does_not_decode_and_rejects_bad_segments():
    assert _key_parts("a/%2E%2E/b") == ["a", "%2E%2E", "b"]
    for bad in ("", "/", "..", "a/../b", "a/\x00b"):
        with pytest.raises(ValueError):
            _key_parts(bad)


def test_object_path_stays_inside_even_through_a_symlink(tmp_path):
    root = tmp_path / "bucket"
    root.mkdir()
    (tmp_path / "secret").mkdir()
    assert _object_path(root, "a/b.txt") == root.resolve() / "a" / "b.txt"
    try:
        (root / "link").symlink_to(tmp_path / "secret", target_is_directory=True)
    except OSError:
        pytest.skip("symlinks need privileges on this machine")
    with pytest.raises(ValueError):
        _object_path(root, "link/x.txt")


@pytest.mark.parametrize("bind, loopback", [
    ("127.0.0.1", True), ("127.1.2.3", True), ("localhost", True), ("::1", True), ("[::1]", True),
    ("0.0.0.0", False), ("::", False), ("[::]", False), ("10.0.0.5", False), ("example.com", False), ("", False),
])
def test_is_loopback_bind(bind, loopback):
    assert is_loopback_bind(bind) is loopback


@pytest.mark.parametrize("bind", ["0.0.0.0", "::", "10.0.0.5"])
def test_refuses_to_listen_on_the_network_without_a_token(make_project, tmp_path, bind):
    host, _out, _all = _project(make_project, tmp_path)
    host.spec.update(host=bind, admin_token="", peer_token="")
    with pytest.raises(ValueError, match="admin_token"):
        host.make_server(0)


def test_a_peer_token_alone_also_closes_the_admin_api(running):
    # The socket is on loopback so the test needs no network; the spec says what a network host would have.
    host, base = running(admin_token="", peer_token="peer-secret")
    host.spec["host"] = "0.0.0.0"
    assert _call(base, "POST", "/__pskit/queues/jobs", body=b'{"a":1}')[0] == 401
    assert _call(base, "POST", "/__pskit/queues/jobs", body=b'{"a":1}', headers={"x-pskit-token": "wrong"})[0] == 401
    assert _call(base, "POST", "/__pskit/queues/jobs", body=b'{"a":1}', headers={"x-pskit-token": "peer-secret"})[0] == 202
    assert _call(base, "POST", "/2015-03-31/functions/hello/invocations", body=b"{}")[0] == 403


def test_loopback_without_a_token_stays_open_for_local_tools(running):
    _host, base = running(admin_token="")
    assert _call(base, "POST", "/__pskit/queues/jobs", body=b'{"a":1}')[0] == 202


@pytest.mark.parametrize("headers", [
    {"Origin": "https://evil.example"},                         # a web page calling localhost
    {"Origin": "null"},                                         # a sandboxed iframe
    {"Sec-Fetch-Site": "cross-site"},
    {"Host": "rebind.evil.example:8080"},                       # DNS rebinding
])
def test_loopback_without_a_token_refuses_browser_attacks(running, headers):
    _host, base = running(admin_token="")
    assert _call(base, "POST", "/__pskit/queues/jobs", body=b'{"a":1}', headers=headers)[0] == 401
    assert _call(base, "POST", "/2015-03-31/functions/hello/invocations", body=b"{}", headers=headers)[0] == 403


def test_loopback_without_a_token_allows_a_local_page(running):
    _host, base = running(admin_token="")
    headers = {"Origin": "http://localhost:5173", "Sec-Fetch-Site": "same-site"}
    assert _call(base, "POST", "/__pskit/queues/jobs", body=b'{"a":1}', headers=headers)[0] == 202


@pytest.mark.parametrize("authorization, allowed", [
    ("AWS4-HMAC-SHA256 Credential=tok3n/20260101/us-east-1/lambda/aws4_request, SignedHeaders=host, Signature=ab", True),
    ("AWS4-HMAC-SHA256 Credential=tok3nX/20260101/us-east-1/lambda/aws4_request", False),
    ("AWS4-HMAC-SHA256 Credential=Xtok3n/20260101/us-east-1/lambda/aws4_request", False),
    ("AWS4-HMAC-SHA256 SignedHeaders=host, Signature=xCredential=tok3n/", False),   # not the Credential field
    ("", False),
])
def test_the_aws_credential_must_be_exactly_the_token(running, authorization, allowed):
    _host, base = running(admin_token="tok3n")
    headers = {"Authorization": authorization} if authorization else {}
    status, _ = _call(base, "POST", "/2015-03-31/functions/hello/invocations", body=b"{}", headers=headers)
    assert (status != 403) is allowed


def test_a_non_ascii_token_guess_is_a_401_not_a_crash(running):
    _host, base = running(admin_token="secret")
    status, _ = _call(base, "GET", "/__pskit/stats", headers={"x-pskit-token": "sécret"})
    assert status == 401


def test_health_says_little_without_the_token(running):
    _host, base = running(admin_token="secret")
    status, body = _call(base, "GET", "/__pskit/health")
    assert status == 200 and json.loads(body) == {"ok": True}
    status, body = _call(base, "GET", "/__pskit/health", headers={"x-pskit-token": "secret"})
    assert status == 200 and "pid" in json.loads(body)
