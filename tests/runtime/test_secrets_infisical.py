"""get_secret / put_secret with the infisical driver (Universal Auth machine identity or a token)."""

from __future__ import annotations

import json
from urllib.parse import parse_qs, urlsplit

import pytest

from py_serverless_kit.runtime import secrets as sec


@pytest.fixture
def store(monkeypatch):
    sec._cache.clear()
    sec._tokens.clear()
    for name, value in {"DRIVER": "infisical", "URL": "http://inf.local:8080/", "CLIENT_ID": "cid",
                        "CLIENT_SECRET": "csec", "PROJECT_ID": "p1", "ENVIRONMENT": "prod"}.items():
        monkeypatch.setenv(f"PSKIT_VAULT_{name}", value)
    calls = []
    values = {"DB": '{"user": "app", "password": "pw"}', "TOKEN": "plain"}

    def http(method, url, headers, body=None):
        calls.append((method, url, dict(headers), json.loads(body) if body else None))
        path = urlsplit(url).path
        if path.endswith("/universal-auth/login"):
            return 200, json.dumps({"accessToken": "acc", "expiresIn": 7200}).encode()
        name = path.rsplit("/", 1)[1]
        if method == "GET":
            if name not in values:
                return 404, b'{"message": "not found"}'
            return 200, json.dumps({"secret": {"secretKey": name, "secretValue": values[name]}}).encode()
        if method == "PATCH" and name not in values:
            return 400, b'{"message": "Secret not found"}'
        values[name] = json.loads(body)["secretValue"]
        return 200, b"{}"

    monkeypatch.setattr(sec, "_http", http)
    return calls, values


def test_read_fields_plain_values_and_one_login(store):
    calls, _values = store
    assert sec.get_secret("DB", "password", store="vault") == "pw"
    assert sec.get_secret("TOKEN", store="vault") == "plain"
    logins = [c for c in calls if c[1].endswith("/login")]
    assert len(logins) == 1 and logins[0][3] == {"clientId": "cid", "clientSecret": "csec"}
    read = next(c for c in calls if c[0] == "GET")
    assert read[2]["Authorization"] == "Bearer acc" and read[1].startswith("http://inf.local:8080/api/v3/secrets/raw/DB?")
    assert parse_qs(urlsplit(read[1]).query) == {"workspaceId": ["p1"], "environment": ["prod"], "secretPath": ["/"]}
    with pytest.raises(sec.SecretNotFound):
        sec.get_secret("MISSING", store="vault")
    assert sec.get_secret("MISSING", store="vault", default="d") == "d"


def test_write_creates_then_updates(store, monkeypatch):
    calls, values = store
    sec.put_secret("NEW", {"a": "1"}, store="vault")
    assert [c[0] for c in calls if "/raw/NEW" in c[1]] == ["PATCH", "POST"] and values["NEW"] == '{"a": "1"}'
    sec.put_secret("NEW", "x", store="vault")
    assert values["NEW"] == "x"
    monkeypatch.delenv("PSKIT_VAULT_PROJECT_ID")
    with pytest.raises(sec.SecretError, match="PROJECT_ID"):
        sec.get_secret("OTHER", store="vault")


def test_token_instead_of_a_machine_identity(store, monkeypatch):
    calls, _values = store
    monkeypatch.delenv("PSKIT_VAULT_CLIENT_ID")
    monkeypatch.setenv("PSKIT_VAULT_TOKEN", "st.123")
    assert sec.get_secret("TOKEN", store="vault") == "plain"
    assert not [c for c in calls if c[1].endswith("/login")] and calls[0][2]["Authorization"] == "Bearer st.123"
