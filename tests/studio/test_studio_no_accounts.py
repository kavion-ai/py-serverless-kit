"""Choosing no accounts: the studio and CLI work as before, and a project with a vault cannot opt out."""

from __future__ import annotations

import threading

import pytest
from click.testing import CliRunner

from py_serverless_kit.cli.main import cli
from py_serverless_kit.studio.auth import choose_no_accounts, open_mode_file
from py_serverless_kit.studio.server import make_server
from py_serverless_kit.vault import crypto
from py_serverless_kit.vault.errors import VaultError
from py_serverless_kit.vault.store import Vault

from .test_studio_auth import ADMIN_PW, CONFIG, TOKEN, call


@pytest.fixture(autouse=True)
def fast_kdf(monkeypatch, tmp_path_factory):
    monkeypatch.setattr(crypto, "SCRYPT_N", 2**14)
    monkeypatch.setenv("PSKIT_HOME", str(tmp_path_factory.mktemp("home")))


@pytest.fixture
def server(tmp_path):
    (tmp_path / "pskit.yml").write_text(CONFIG)
    (tmp_path / "app.py").write_text("def hello(event, ctx):\n    return {}\n")
    (tmp_path / ".env.onprem").write_bytes(b"DB_PASSWORD=hunter2\n")
    httpd = make_server(tmp_path, "127.0.0.1", 0, token=TOKEN)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", tmp_path, httpd
    httpd.studio.auth.shutdown()
    httpd.shutdown()
    httpd.server_close()


def test_a_new_project_asks_first_and_stays_closed_until_then(server):
    base, _root, _httpd = server
    assert call(base, "GET", "/api/auth/status")[1]["state"] == "setup"
    assert call(base, "GET", "/api/project")[0] == 401


def test_just_me_works_as_before(server):
    base, root, _httpd = server
    status, doc = call(base, "POST", "/api/auth/mode", {"mode": "none"})
    assert status == 200 and doc == {"state": "open"}

    assert call(base, "GET", "/api/project")[0] == 200
    assert call(base, "GET", "/api/files?path=.env.onprem")[1]["text"] == "DB_PASSWORD=hunter2\n"
    assert call(base, "PUT", "/api/files", {"path": "app.py", "text": "x = 1\n"})[0] == 200
    assert call(base, "GET", "/api/onprem-services")[0] == 200
    assert ".env.onprem" in [e["path"] for e in call(base, "GET", "/api/files/tree")[1]["entries"]]

    assert not (root / ".pskit-vault").exists()
    assert not (root / ".gitignore").exists()
    assert (root / ".env.onprem").is_file()


def test_the_startup_token_is_still_needed(server):
    base, root, _httpd = server
    assert call(base, "POST", "/api/auth/mode", {"mode": "none"}, token=None)[0] == 401
    assert not open_mode_file(root).exists()
    call(base, "POST", "/api/auth/mode", {"mode": "none"})
    assert call(base, "GET", "/api/project", token=None)[0] == 401


def test_stopping_the_studio_leaves_the_files(server):
    base, root, httpd = server
    call(base, "POST", "/api/auth/mode", {"mode": "none"})
    httpd.studio.auth.shutdown()
    assert (root / ".env.onprem").is_file()


def test_the_choice_survives_a_restart(server):
    base, root, _httpd = server
    call(base, "POST", "/api/auth/mode", {"mode": "none"})
    again = make_server(root, "127.0.0.1", 0, token=TOKEN)
    try:
        assert again.studio.auth.is_open()
    finally:
        again.server_close()


def test_turning_accounts_on_later(server):
    base, root, _httpd = server
    call(base, "POST", "/api/auth/mode", {"mode": "none"})
    assert call(base, "POST", "/api/auth/mode", {"mode": "accounts"})[1]["state"] == "setup"
    assert call(base, "GET", "/api/project")[0] == 401
    status, doc = call(base, "POST", "/api/auth/setup", {"username": "root-admin", "password": ADMIN_PW})
    assert status == 201 and doc["sealed"] == [".env.onprem"]
    assert call(base, "GET", "/api/project")[0] == 401
    assert call(base, "GET", "/api/project", session=doc["session"])[0] == 200


def test_a_vault_cannot_be_opted_out_of(server):
    base, root, _httpd = server
    session = call(base, "POST", "/api/auth/setup", {"username": "root-admin", "password": ADMIN_PW})[1]["session"]
    status, doc = call(base, "POST", "/api/auth/mode", {"mode": "none"}, session)
    assert status == 409 and doc["code"] == "exists"
    with pytest.raises(VaultError):
        choose_no_accounts(root)
    # Even with the file put there by hand, or shipped in a repository.
    open_mode_file(root).parent.mkdir(parents=True, exist_ok=True)
    open_mode_file(root).write_bytes(b"x")
    assert call(base, "GET", "/api/project")[0] == 401
    assert call(base, "GET", "/api/auth/status")[1]["state"] == "login"


def test_a_vault_made_from_the_terminal_closes_an_open_studio(server):
    base, root, _httpd = server
    call(base, "POST", "/api/auth/mode", {"mode": "none"})
    assert call(base, "GET", "/api/project")[0] == 200
    Vault.create(root, "root-admin", ADMIN_PW)
    assert call(base, "GET", "/api/project")[0] == 401


def test_unknown_mode_is_refused(server):
    base, root, _httpd = server
    assert call(base, "POST", "/api/auth/mode", {"mode": "whatever"})[0] == 400
    assert not open_mode_file(root).exists()


def test_cli_flag_refused_when_the_project_has_accounts(tmp_path):
    Vault.create(tmp_path, "root-admin", ADMIN_PW)
    result = CliRunner().invoke(cli, ["studio", "-d", str(tmp_path), "--no-auth"])
    assert result.exit_code != 0 and "has accounts" in result.output
    assert not open_mode_file(tmp_path).exists()


def test_cli_commands_need_no_login_without_a_vault(tmp_path, monkeypatch):
    (tmp_path / "pskit.yml").write_text(CONFIG)
    (tmp_path / "app.py").write_text("def hello(event, ctx):\n    return {}\n")
    choose_no_accounts(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert CliRunner().invoke(cli, ["validate"]).exit_code == 0
