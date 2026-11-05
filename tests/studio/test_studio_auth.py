"""Accounts in the studio: first-run admin, login, permissions on every kind of route, sealing, audit."""

from __future__ import annotations

import json
import shutil
import threading
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from py_serverless_kit.studio.server import make_server
from py_serverless_kit.vault import crypto
from py_serverless_kit.vault import workspace as ws
from py_serverless_kit.vault.store import Vault

TOKEN = "test-token-123"
ADMIN_PW = "correct horse battery"
USER_PW = "first password here"
USER_PW2 = "my own password now"
CONFIG = """
service: auth-demo
provider: {name: aws, region: us-east-1}
functions:
  hello: {handler: app.hello, events: [{http: GET /hello}]}
"""


@pytest.fixture(autouse=True)
def fast_kdf(monkeypatch, tmp_path_factory):
    monkeypatch.setattr(crypto, "SCRYPT_N", 2**14)
    monkeypatch.setenv("PSKIT_HOME", str(tmp_path_factory.mktemp("home")))


def _serve(root):
    httpd = make_server(root, "127.0.0.1", 0, token=TOKEN)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}"


@pytest.fixture
def server(tmp_path):
    (tmp_path / "pskit.yml").write_text(CONFIG)
    (tmp_path / "app.py").write_text("def hello(event, ctx):\n    return {}\n")
    (tmp_path / ".env.onprem").write_text("DB_PASSWORD=hunter2\n")
    httpd, base = _serve(tmp_path)
    yield base, tmp_path, httpd
    if httpd.studio and httpd.studio.auth:
        httpd.studio.auth.shutdown()
    httpd.shutdown()
    httpd.server_close()


def call(base, method, path, body=None, session=None, token=TOKEN):
    headers = {"accept": "application/json"}
    if token:
        headers["x-studio-token"] = token
    if session:
        headers["x-pskit-session"] = session
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["content-type"] = "application/json"
    try:
        with urlopen(Request(base + path, data=data, method=method, headers=headers), timeout=30) as resp:
            return resp.status, json.loads(resp.read() or b"null")
    except HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"null")


KEYS = {}


def setup_admin(base):
    status, doc = call(base, "POST", "/api/auth/setup", {"username": "root-admin", "password": ADMIN_PW})
    assert status == 201, doc
    KEYS["master"] = doc["master_key"]
    return doc


def login(base, username, password):
    return call(base, "POST", "/api/auth/login", {"master_key": KEYS["master"], "username": username, "password": password})


def add_user(base, admin, perms, name="dev"):
    status, doc = call(base, "POST", "/api/auth/users",
                       {"username": name, "password": USER_PW, "permissions": perms}, admin)
    assert status == 201, doc
    status, doc = login(base, name, USER_PW)
    assert status == 200, doc
    session = doc["session"]
    assert doc["state"] == "password_change"
    status, doc = call(base, "POST", "/api/auth/password", {"old": USER_PW, "new": USER_PW2}, session)
    assert status == 200 and doc["state"] == "ready", doc
    return session


def test_first_start_asks_for_an_admin_and_blocks_the_rest(server):
    base, _root, _httpd = server
    assert call(base, "GET", "/api/auth/status")[1]["state"] == "setup"
    status, doc = call(base, "GET", "/api/project")
    assert status == 401 and doc["code"] == "setup"


def test_setup_needs_the_startup_token(server):
    base, root, _httpd = server
    status, _doc = call(base, "POST", "/api/auth/setup", {"username": "evil", "password": ADMIN_PW}, token=None)
    assert status == 401
    assert not (root / ".pskit-vault").exists()


def test_setup_returns_keys_once_and_seals(server):
    base, root, _httpd = server
    doc = setup_admin(base)
    assert doc["master_key"].startswith("pskm-") and doc["recovery_code"].startswith("pskr-")
    assert doc["sealed"] == [".env.onprem"] and doc["state"] == "ready"
    assert ".env.*" in (root / ".gitignore").read_text()
    status, again = call(base, "POST", "/api/auth/setup", {"username": "second", "password": ADMIN_PW})
    assert status == 409 and "master_key" not in again
    status, state = call(base, "GET", "/api/auth/status", session=doc["session"])
    assert status == 200 and "master_key" not in state
    assert b"hunter2" not in b"".join(p.read_bytes() for p in (root / ".pskit-vault").rglob("*") if p.is_file())


def test_weak_password_refused(server):
    base, root, _httpd = server
    status, doc = call(base, "POST", "/api/auth/setup", {"username": "root-admin", "password": "short"})
    assert status == 400 and doc["code"] == "weak_password"
    assert not (root / ".pskit-vault").exists()


def test_logout_removes_plaintext_and_login_brings_it_back(server):
    base, root, _httpd = server
    session = setup_admin(base)["session"]
    assert call(base, "POST", "/api/auth/logout", {}, session)[0] == 200
    assert not (root / ".env.onprem").exists()
    assert call(base, "GET", "/api/project", session=session)[0] == 401
    status, doc = login(base, "root-admin", ADMIN_PW)
    assert status == 200, doc
    assert (root / ".env.onprem").read_text() == "DB_PASSWORD=hunter2\n"


def test_login_needs_the_master_key(server):
    base, _root, _httpd = server
    key = setup_admin(base)["master_key"]
    assert call(base, "GET", "/api/auth/status")[1] == {"state": "login"}
    status, doc = call(base, "POST", "/api/auth/login", {"username": "root-admin", "password": ADMIN_PW})
    assert status == 401 and doc["code"] == "bad_master_key"
    other = crypto.format_secret("pskm", crypto.random_key())
    status, doc = call(base, "POST", "/api/auth/login", {"master_key": other, "username": "root-admin", "password": ADMIN_PW})
    assert status == 401 and doc["code"] == "bad_master_key"
    status, doc = call(base, "POST", "/api/auth/login", {"master_key": key, "username": "root-admin", "password": ADMIN_PW})
    assert status == 200, doc


def test_deleting_pskit_and_restarting_still_needs_the_master_key(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("PSKIT_HOME", str(home))
    project = tmp_path / "proj"
    project.mkdir()
    (project / "pskit.yml").write_text(CONFIG)
    (project / ".env.onprem").write_text("DB_PASSWORD=hunter2\n")
    httpd, base = _serve(project)
    key = setup_admin(base)["master_key"]
    httpd.studio.auth.shutdown()
    httpd.shutdown()
    httpd.server_close()
    assert not (home / "vault-keys").exists()

    shutil.rmtree(project / ".pskit")
    httpd, base = _serve(project)
    try:
        status, doc = call(base, "POST", "/api/auth/login", {"username": "root-admin", "password": ADMIN_PW})
        assert status == 401 and doc["code"] == "bad_master_key"
        assert not (project / ".env.onprem").exists()
        status, doc = call(base, "POST", "/api/auth/login", {"master_key": key, "username": "root-admin", "password": ADMIN_PW})
        assert status == 200, doc
        assert (project / ".env.onprem").read_text() == "DB_PASSWORD=hunter2\n"
    finally:
        httpd.studio.auth.shutdown()
        httpd.shutdown()
        httpd.server_close()


def test_a_key_saved_by_an_older_version_is_ignored_then_deleted(server):
    base, root, _httpd = server
    key = setup_admin(base)["master_key"]
    saved = ws.saved_master_path(Vault(root))
    saved.parent.mkdir(parents=True, exist_ok=True)
    saved.write_text(crypto.b64(crypto.parse_secret("pskm", key, "master key")))
    status, doc = call(base, "POST", "/api/auth/login", {"username": "root-admin", "password": ADMIN_PW})
    assert status == 401 and doc["code"] == "bad_master_key"
    assert saved.exists()  # a refused login removes nothing: it may be the only copy someone has
    status, doc = call(base, "POST", "/api/auth/login", {"master_key": key, "username": "root-admin", "password": ADMIN_PW})
    assert status == 200, doc
    assert not saved.exists()


def test_failed_logins_lock_and_are_audited(server):
    base, _root, _httpd = server
    session = setup_admin(base)["session"]
    for _ in range(5):
        status, doc = login(base, "root-admin", "wrong password!!")
        assert status == 401 and "wrong username or password" in doc["error"]
    status, doc = login(base, "root-admin", ADMIN_PW)
    assert status == 429 and doc["code"] == "locked"
    entries = call(base, "GET", "/api/auth/audit?action=auth.login", session=session)[1]["entries"]
    assert sum(e["outcome"] == "failed" for e in entries) == 5


def test_unknown_user_gets_the_same_answer(server):
    base, _root, _httpd = server
    setup_admin(base)
    _s, unknown = login(base, "nobody", "wrong password!!")
    _s, wrong = login(base, "root-admin", "wrong password!!")
    assert unknown["error"] == wrong["error"]


def test_must_change_password_blocks_everything_else(server):
    base, _root, _httpd = server
    admin = setup_admin(base)["session"]
    call(base, "POST", "/api/auth/users", {"username": "dev", "password": USER_PW, "permissions": {"code": "r"}}, admin)
    session = login(base, "dev", USER_PW)[1]["session"]
    status, doc = call(base, "GET", "/api/project", session=session)
    assert status == 403 and doc["code"] == "password_change"
    assert call(base, "GET", "/api/auth/users", session=session)[0] == 403


def test_permissions_are_enforced_per_action(server):
    base, root, _httpd = server
    admin = setup_admin(base)["session"]
    session = add_user(base, admin, {"code": "r"})
    assert call(base, "GET", "/api/project", session=session)[0] == 200  # always readable
    assert call(base, "GET", "/api/files?path=app.py", session=session)[0] == 200
    status, doc = call(base, "PUT", "/api/files", {"path": "app.py", "text": "hacked"}, session)
    assert status == 403 and doc["code"] == "forbidden" and doc["feature"] == "code"
    assert "hacked" not in (root / "app.py").read_text()
    assert call(base, "POST", "/api/jobs", {"command": "deploy"}, session)[0] == 403
    assert call(base, "GET", "/api/onprem-services", session=session)[0] == 403
    assert call(base, "POST", "/api/vscode/start", {}, session)[0] == 403
    assert call(base, "GET", "/api/hana", session=session)[0] == 403
    assert call(base, "POST", "/api/settings-bundle/export", {"passphrase": "long enough passphrase"}, session)[0] == 403


def test_permission_changes_apply_at_once(server):
    base, _root, _httpd = server
    admin = setup_admin(base)["session"]
    session = add_user(base, admin, {})
    assert call(base, "GET", "/api/files?path=app.py", session=session)[0] == 403
    assert call(base, "PUT", "/api/auth/users/dev", {"permissions": {"code": "r"}}, admin)[0] == 200
    assert call(base, "GET", "/api/files?path=app.py", session=session)[0] == 200
    assert call(base, "PUT", "/api/auth/users/dev", {"disabled": True}, admin)[0] == 200
    assert call(base, "GET", "/api/files?path=app.py", session=session)[0] == 401


@pytest.mark.parametrize("path", [
    ".env.onprem", "./.env.onprem", "sub/../.env.onprem", ".ENV.onprem", ".env.onprem.", ".env.onprem::$DATA",
    ".env.onprem/",
])
def test_env_files_need_the_env_permission(server, path):
    base, _root, _httpd = server
    admin = setup_admin(base)["session"]
    session = add_user(base, admin, {"code": "crud"})
    from urllib.parse import quote

    status, doc = call(base, "GET", f"/api/files?path={quote(path)}", session=session)
    assert status in (400, 403, 404), doc
    assert "hunter2" not in json.dumps(doc)
    status, _doc = call(base, "PUT", "/api/files", {"path": path, "text": "X=1"}, session)
    assert status in (400, 403), path


def test_env_files_hidden_from_the_tree(server):
    base, _root, _httpd = server
    admin = setup_admin(base)["session"]
    session = add_user(base, admin, {"code": "r"})
    assert ".env.onprem" in [e["path"] for e in call(base, "GET", "/api/files/tree", session=admin)[1]["entries"]]
    assert ".env.onprem" not in [e["path"] for e in call(base, "GET", "/api/files/tree", session=session)[1]["entries"]]


def test_the_vault_folder_is_not_reachable(server):
    base, _root, _httpd = server
    admin = setup_admin(base)["session"]
    assert call(base, "GET", "/api/files?path=.pskit-vault/vault.json", session=admin)[0] == 403
    assert call(base, "PUT", "/api/files", {"path": ".pskit-vault/x", "text": "x"}, admin)[0] == 403
    assert all(not e["path"].startswith(".pskit-vault") for e in call(base, "GET", "/api/files/tree", session=admin)[1]["entries"])


def test_accounts_are_admin_only_even_with_the_grid(server):
    base, _root, _httpd = server
    admin = setup_admin(base)["session"]
    session = add_user(base, admin, {"users": "crud"})
    assert call(base, "GET", "/api/auth/users", session=session)[0] == 200  # may look
    status, _doc = call(base, "PUT", "/api/auth/users/dev", {"role": "admin"}, session)
    assert status == 403
    assert call(base, "POST", "/api/auth/master-key/rotate", {}, session)[0] == 403
    assert call(base, "GET", "/api/auth/audit", session=session)[0] == 403


def test_user_lacking_areas_does_not_get_their_keys(server):
    base, _root, _httpd = server
    admin = setup_admin(base)["session"]
    session = add_user(base, admin, {"code": "r"})
    assert call(base, "GET", "/api/auth/status", session=session)[1]["areas"] == []
    assert "env" in call(base, "GET", "/api/auth/status", session=admin)[1]["areas"]


def test_saves_are_sealed_and_audited_before_the_response(server):
    base, root, _httpd = server
    admin = setup_admin(base)["session"]
    enc = list((root / ".pskit-vault" / "data" / "env").glob("*.enc"))
    before = enc[0].read_bytes()
    status, doc = call(base, "PUT", "/api/files", {"path": ".env.onprem", "text": "DB_PASSWORD=changed\n"}, admin)
    assert status == 200, doc
    assert enc[0].read_bytes() != before
    entries = call(base, "GET", "/api/auth/audit?user=root-admin", session=admin)[1]["entries"]
    assert any(e["action"] == "code.u" and e["details"].get("path") == ".env.onprem" for e in entries)
    assert "DB_PASSWORD" not in json.dumps(entries)


def test_denied_calls_are_audited(server):
    base, _root, _httpd = server
    admin = setup_admin(base)["session"]
    session = add_user(base, admin, {})
    call(base, "POST", "/api/jobs", {"command": "deploy", "provider": "aws"}, session)
    entries = call(base, "GET", "/api/auth/audit?user=dev", session=admin)[1]["entries"]
    denied = [e for e in entries if e["outcome"] == "denied"]
    assert denied and denied[0]["action"] == "deploy.c" and denied[0]["details"]["command"] == "deploy"


def test_jobs_run_as_the_session_and_are_audited(server):
    base, _root, _httpd = server
    admin = setup_admin(base)["session"]
    status, doc = call(base, "POST", "/api/jobs", {"command": "validate"}, admin)
    assert status == 202, doc
    for _ in range(600):
        job = call(base, "GET", f"/api/jobs/{doc['job_id']}", session=admin)[1]
        if job["status"] != "running":
            break
        time.sleep(0.1)
    assert job["status"] == "succeeded", job
    entries = call(base, "GET", "/api/auth/audit?action=job.validate", session=admin)[1]["entries"]
    assert entries and entries[0]["outcome"] == "ok" and entries[0]["user"] == "root-admin"


def test_removing_a_user_rotates_their_keys(server):
    base, root, _httpd = server
    admin = setup_admin(base)["session"]
    add_user(base, admin, {"env": "r"})
    assert call(base, "DELETE", "/api/auth/users/root-admin", session=admin)[0] == 409
    assert call(base, "DELETE", "/api/auth/users/dev", session=admin)[0] == 200
    assert (root / ".env.onprem").read_text() == "DB_PASSWORD=hunter2\n"
    assert call(base, "POST", "/api/auth/logout", {}, admin)[0] == 200
    assert login(base, "root-admin", ADMIN_PW)[0] == 200
    assert (root / ".env.onprem").read_text() == "DB_PASSWORD=hunter2\n"


def test_recovery_over_the_api(server):
    base, _root, _httpd = server
    doc = setup_admin(base)
    wrong_code = call(base, "POST", "/api/auth/recover", {
        "master_key": doc["master_key"], "recovery_code": crypto.format_secret("pskr", crypto.random_key()),
        "username": "root-admin", "password": "a brand new password",
    })
    assert wrong_code[0] == 401 and wrong_code[1]["code"] == "bad_key"
    no_master = call(base, "POST", "/api/auth/recover", {
        "recovery_code": doc["recovery_code"], "username": "root-admin", "password": "a brand new password",
    })
    assert no_master[0] == 401 and no_master[1]["code"] == "bad_master_key"
    good = call(base, "POST", "/api/auth/recover", {
        "master_key": doc["master_key"], "recovery_code": doc["recovery_code"],
        "username": "root-admin", "password": "a brand new password",
    })
    assert good[0] == 200, good
    assert login(base, "root-admin", "a brand new password")[0] == 200


def test_only_an_admin_replaces_the_recovery_code(server):
    base, _root, _httpd = server
    doc = setup_admin(base)
    dev = add_user(base, doc["session"], {"users": "crud"})
    assert call(base, "POST", "/api/auth/recovery-code/rotate", {}, dev)[0] == 403
    status, rotated = call(base, "POST", "/api/auth/recovery-code/rotate", {}, doc["session"])
    assert status == 200 and rotated["recovery_code"].startswith("pskr-")
    assert rotated["recovery_code"] != doc["recovery_code"]
    new_password = {"master_key": doc["master_key"], "username": "root-admin", "password": "a brand new password"}
    assert call(base, "POST", "/api/auth/recover", {**new_password, "recovery_code": doc["recovery_code"]})[0] == 401
    assert call(base, "POST", "/api/auth/recover", {**new_password, "recovery_code": rotated["recovery_code"]})[0] == 200


def test_rotating_the_master_key_over_the_api(server):
    base, _root, _httpd = server
    doc = setup_admin(base)
    status, rotated = call(base, "POST", "/api/auth/master-key/rotate", {}, doc["session"])
    assert status == 200 and rotated["master_key"] != doc["master_key"]
    assert call(base, "GET", "/api/project", session=doc["session"])[0] == 200  # this session goes on
    assert call(base, "POST", "/api/auth/login", {
        "master_key": doc["master_key"], "username": "root-admin", "password": ADMIN_PW,
    })[0] == 401


def test_stopping_the_studio_removes_plaintext(tmp_path):
    (tmp_path / "pskit.yml").write_text(CONFIG)
    (tmp_path / ".env.onprem").write_text("DB_PASSWORD=hunter2\n")
    httpd, base = _serve(tmp_path)
    setup_admin(base)
    (tmp_path / ".env.onprem").write_text("DB_PASSWORD=last-minute-edit\n")
    httpd.studio.auth.shutdown()
    httpd.shutdown()
    httpd.server_close()
    assert not (tmp_path / ".env.onprem").exists()
    httpd, base = _serve(tmp_path)
    try:
        assert login(base, "root-admin", ADMIN_PW)[0] == 200
        assert (tmp_path / ".env.onprem").read_text() == "DB_PASSWORD=last-minute-edit\n"
    finally:
        httpd.studio.auth.shutdown()
        httpd.shutdown()
        httpd.server_close()


def test_a_crashed_studio_is_cleaned_up_at_next_start(tmp_path, monkeypatch):
    (tmp_path / "pskit.yml").write_text(CONFIG)
    (tmp_path / ".env.onprem").write_text("DB_PASSWORD=hunter2\n")
    httpd, base = _serve(tmp_path)
    setup_admin(base)
    httpd.studio.auth._stop.set()  # dies without shutdown(): the session file and the plaintext stay
    httpd.shutdown()
    httpd.server_close()
    assert (tmp_path / ".env.onprem").exists()
    monkeypatch.setattr(ws, "STALE_STUDIO_SECONDS", -1)
    httpd, base = _serve(tmp_path)
    try:
        assert not (tmp_path / ".env.onprem").exists()
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_features_catalog(server):
    base, _root, _httpd = server
    admin = setup_admin(base)["session"]
    doc = call(base, "GET", "/api/auth/features", session=admin)[1]
    names = {f["name"] for f in doc["features"]}
    assert {"deploy", "env", "code", "hana", "audit"} <= names
    assert any(f["name"] == "shell" and f["full_access"] for f in doc["features"])
