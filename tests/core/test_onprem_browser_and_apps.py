"""pskit's own service browsers (S3, Cloud Storage, OpenBao, Secrets Manager) and the extra one-click services."""

from __future__ import annotations

import base64
import json
from typing import Any, Dict, List, Tuple
from urllib.parse import parse_qs, urlsplit

import pytest

from py_serverless_kit.core import onprem_browser as brw
from py_serverless_kit.core import onprem_services as svc

from .test_onprem_services import RAW, FakeDocker

MINIO = {"service": "minio", "address": "10.0.0.5", "port": 9000, "target": {"method": "local"},
         "user": "admin", "env": {"PSKIT_FILES_ACCESS_KEY": "admin", "PSKIT_FILES_SECRET_KEY": "secret-key"}}


class FakeService:
    """Stands in for HostControl.fetch: records requests, answers from a list."""

    def __init__(self, answers: List[Tuple[int, Dict[str, str], bytes]]) -> None:
        self.answers = list(answers)
        self.calls: List[Dict[str, Any]] = []

    def __call__(self, control, method, path, data, headers, timeout=None):
        self.calls.append({"method": method, "path": path, "data": data, "headers": dict(headers),
                           "base": control.base_url})
        return self.answers.pop(0)


def test_browsers_per_service_and_catalog():
    ids = {c["id"]: c for c in svc.catalog() if c["kind"] == "service"}
    assert ids["minio"]["browsers"] == ["s3"] and ids["openbao"]["browsers"] == ["vault"]
    assert ids["localemu"]["browsers"] == ["s3", "aws-secrets"] and ids["redis"]["browsers"] == []
    assert not ids["openbao"]["gui"]  # the release image has no web UI: pskit's browser instead
    with pytest.raises(brw.BrowseError, match="has no 's3' browser"):
        brw.browse({"service": "redis"}, "s3", "buckets", {})


def test_s3_list_is_signed_and_paginated(monkeypatch):
    xml = (b'<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/"><IsTruncated>true</IsTruncated>'
           b"<Contents><Key>in/a.txt</Key><Size>3</Size><LastModified>2026-10-23T10:00:00Z</LastModified>"
           b'<ETag>"e1"</ETag></Contents><CommonPrefixes><Prefix>in/sub/</Prefix></CommonPrefixes>'
           b"<NextContinuationToken>tok2</NextContinuationToken></ListBucketResult>")
    fake = FakeService([(200, {}, xml)])
    monkeypatch.setattr(brw, "_fetch", fake)
    page = brw.browse(MINIO, "s3", "list", {"bucket": "files", "prefix": "in/", "limit": 1})
    assert page == {"folders": ["in/sub/"], "next": "tok2", "objects": [
        {"key": "in/a.txt", "size": 3, "modified": "2026-10-23T10:00:00Z", "etag": "e1", "storage_class": None}]}
    call = fake.calls[0]
    query = parse_qs(urlsplit(call["path"]).query)
    assert call["method"] == "GET" and urlsplit(call["path"]).path == "/files"
    assert query["list-type"] == ["2"] and query["max-keys"] == ["1"] and query["delimiter"] == ["/"]
    assert call["headers"]["authorization"].startswith("AWS4-HMAC-SHA256 Credential=admin/")
    assert call["headers"]["host"] == "10.0.0.5:9000"  # signed for the address it is sent as


def test_s3_upload_metadata_errors_and_share(monkeypatch):
    fake = FakeService([(200, {}, b""), (403, {}, b"<Error><Code>AccessDenied</Code><Message>no</Message></Error>")])
    monkeypatch.setattr(brw, "_fetch", fake)
    out = brw.browse(MINIO, "s3", "put", {"bucket": "files", "key": "a b.txt", "content": base64.b64encode(b"hi").decode(),
                                          "content_type": "text/plain", "metadata": {"owner": "ann"}})
    assert out == {"uploaded": "a b.txt", "size": 2}
    assert fake.calls[0]["path"] == "/files/a%20b.txt" and fake.calls[0]["data"] == b"hi"
    assert fake.calls[0]["headers"]["x-amz-meta-owner"] == "ann"
    with pytest.raises(brw.BrowseError, match="HTTP 403 AccessDenied no"):
        brw.browse(MINIO, "s3", "bucket-create", {"bucket": "other"})
    with pytest.raises(brw.BrowseError, match="bucket names"):
        brw.browse(MINIO, "s3", "list", {"bucket": "Bad_Name"})
    url = brw.browse(MINIO, "s3", "share", {"bucket": "files", "key": "a b.txt", "expires": 600})["url"]
    parts = urlsplit(url)
    q = parse_qs(parts.query)
    assert parts.netloc == "10.0.0.5:9000" and parts.path == "/files/a%20b.txt"
    assert q["X-Amz-Expires"] == ["600"] and q["X-Amz-SignedHeaders"] == ["host"] and len(q["X-Amz-Signature"][0]) == 64



def test_s3_make_private_also_blocks_public_access_where_the_service_has_it(monkeypatch):
    nope = (501, {}, b"<Error><Code>NotImplemented</Code></Error>")
    fake = FakeService([(204, {}, b""), nope, nope, (404, {}, b""), nope])  # MinIO: no ACLs, no public access block
    monkeypatch.setattr(brw, "_fetch", fake)
    assert brw.browse(MINIO, "s3", "policy", {"bucket": "files", "preset": "private"}) == {"policy": "", "blocked": False}
    assert [(c["method"], urlsplit(c["path"]).query) for c in fake.calls] == [
        ("DELETE", "policy="), ("PUT", "acl="), ("PUT", "publicAccessBlock="), ("GET", "policy="),
        ("GET", "publicAccessBlock=")]
    assert fake.calls[1]["headers"]["x-amz-acl"] == "private"
    assert fake.calls[2]["data"].count(b">true<") == 4
    with pytest.raises(brw.BrowseError, match="1 second to 7 days"):
        brw.browse(MINIO, "s3", "share", {"bucket": "files", "key": "a", "expires": 8 * 24 * 3600})
    assert "X-Amz-Expires=5&" in brw.browse(MINIO, "s3", "share", {"bucket": "files", "key": "a", "expires": 5})["url"]

def test_vault_secrets(monkeypatch):
    bao = {"service": "openbao", "address": "127.0.0.1", "port": 8200, "target": {"method": "local"},
           "env": {"PSKIT_S_TOKEN": "tok", "PSKIT_S_MOUNT": "secret"}}
    fake = FakeService([
        (200, {}, json.dumps({"data": {"keys": ["app/", "api-key"]}}).encode()),
        (200, {}, json.dumps({"data": {"data": {"u": "a"}, "metadata": {"version": 2}}}).encode()),
        (200, {}, json.dumps({"data": {"versions": {"1": {"created_time": "t1"}, "2": {"created_time": "t2"}}}}).encode()),
    ])
    monkeypatch.setattr(brw, "_fetch", fake)
    listing = brw.browse(bao, "vault", "list", {})
    assert listing["items"] == [{"name": "api-key", "folder": False, "path": "api-key"},
                                {"name": "app", "folder": True, "path": "app"}]
    got = brw.browse(bao, "vault", "get", {"path": "app/db"})
    assert got["data"] == {"u": "a"} and got["version"] == 2 and [v["version"] for v in got["versions"]] == [2, 1]
    assert fake.calls[0]["headers"]["x-vault-token"] == "tok" and fake.calls[1]["path"] == "/v1/secret/data/app/db"
    with pytest.raises(brw.BrowseError, match="secret names"):
        brw.browse(bao, "vault", "get", {"path": "../etc"})


def test_gcs_pages_on_our_side(monkeypatch):
    gcs = {"service": "fake-gcs", "address": "127.0.0.1", "port": 4443, "target": {"method": "local"}}
    items = [{"name": f"in/f{i}.txt", "size": "1"} for i in range(5)]
    fake = FakeService([(200, {}, json.dumps({"items": items}).encode())] * 3)
    monkeypatch.setattr(brw, "_fetch", fake)
    seen, token = [], None
    while True:
        page = brw.browse(gcs, "gcs", "list", {"bucket": "media", "prefix": "in/", "limit": 2, "token": token})
        seen.append([o["key"] for o in page["objects"]])
        token = page["next"]
        if not token:
            break
    assert seen == [["in/f0.txt", "in/f1.txt"], ["in/f2.txt", "in/f3.txt"], ["in/f4.txt"]]


# ----------------------------------------------------------------------------- extra services


@pytest.fixture
def answers(monkeypatch):
    monkeypatch.setattr(svc, "_http_answers", lambda url: True)


def test_infisical_sidecars_generated_keys_and_removal(tmp_path, answers):
    fake = FakeDocker()
    entry = svc.create(tmp_path, {"key": "vault", "service": "infisical"}, RAW, lambda _l: None, run=fake,
                       wait_seconds=1)
    runs = [c for c in fake.calls if c[:2] == ["docker", "run"]]
    names = [c[c.index("--name") + 1] for c in runs]
    assert names[-1] == entry["container"] and names[:2] == [f"{entry['container']}-db", f"{entry['container']}-redis"]
    assert all("--network" in c for c in runs) and entry["sidecars"] == names[:2]
    env = (tmp_path / ".env.onprem").read_text("utf-8")
    first_key = next(line for line in env.splitlines() if line.startswith("PSKIT_VAULT_ENCRYPTION_KEY="))
    assert "PSKIT_VAULT_DRIVER=infisical" in env and len(first_key.split("=", 1)[1]) == 32
    # Created again: the same encryption key (data written with it stays readable).
    svc.create(tmp_path, {"key": "vault", "service": "infisical", "replace": True}, RAW, lambda _l: None,
               run=FakeDocker(), wait_seconds=1)
    assert first_key in (tmp_path / ".env.onprem").read_text("utf-8")
    fake = FakeDocker()
    svc.remove(tmp_path, "vault", lambda _l: None, delete_data=True, run=fake)
    removed = " ".join(" ".join(c) for c in fake.calls)
    assert f"rm -f {entry['container']}-db" in removed and f"volume rm {entry['container']}-db-data" in removed


def test_new_services_credentials_and_connections(tmp_path, answers):
    with pytest.raises(svc.ServiceError, match="admin account on the first visit"):
        svc.check_request({"key": "git", "service": "gitea", "password": "Secret-123"}, tmp_path, RAW)
    with pytest.raises(svc.ServiceError, match="always neo4j"):
        svc.check_request({"key": "graph", "service": "neo4j", "user": "bob"}, tmp_path, RAW)
    entry = svc.create(tmp_path, {"key": "traces", "service": "jaeger", "port": 16687}, RAW, lambda _l: None,
                       run=FakeDocker(), wait_seconds=1)
    assert entry["resource"]["connection"]["otlp_http"] == "http://127.0.0.1:4319"  # extra port moved with the main
    graf = svc.create(tmp_path, {"key": "dash", "service": "grafana", "password": "Graf-pass-1"}, RAW,
                      lambda _l: None, run=FakeDocker(), wait_seconds=1)
    assert graf["env"]["PSKIT_DASH_PASSWORD"] == "Graf-pass-1"
    assert graf["resource"]["connection"]["password_env"] == "PSKIT_DASH_PASSWORD"
    assert svc._mask("-e ENCRYPTION_KEY=abc") == "-e ENCRYPTION_KEY=***"
