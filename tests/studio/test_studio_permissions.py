"""A read-only account changes nothing, and each of create, update and delete on a function is its own permission."""

from __future__ import annotations

import threading

import pytest

from py_serverless_kit.studio.server import make_server
from py_serverless_kit.vault import crypto, permissions
from py_serverless_kit.vault.permissions import project_needs

from .test_studio_auth import ADMIN_PW, KEYS, TOKEN, USER_PW, USER_PW2, call, login

CONFIG = """
service: perm-demo
provider: {name: aws, region: us-east-1}
functions:
  hello: {handler: app.hello}
workflows:
  flow:
    engine: embedded
    start_at: Go
    states:
      Go: {type: task, function: hello, end: true}
"""


@pytest.fixture(autouse=True)
def fast_kdf(monkeypatch, tmp_path_factory):
    monkeypatch.setattr(crypto, "SCRYPT_N", 2**14)
    monkeypatch.setenv("PSKIT_HOME", str(tmp_path_factory.mktemp("home")))


@pytest.fixture
def studio(tmp_path):
    (tmp_path / "pskit.yml").write_bytes(CONFIG.encode())
    (tmp_path / "app.py").write_bytes(b"def hello(event, ctx):\n    return {}\n")
    httpd = make_server(tmp_path, "127.0.0.1", 0, token=TOKEN)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    created = call(base, "POST", "/api/auth/setup", {"username": "boss", "password": ADMIN_PW})[1]
    KEYS["master"] = created["master_key"]
    yield base, tmp_path, created["session"]
    httpd.studio.auth.shutdown()
    httpd.shutdown()
    httpd.server_close()


def login_as(base, admin, perms, name="dev"):
    assert call(base, "POST", "/api/auth/users", {"username": name, "password": USER_PW, "permissions": perms}, admin)[0] == 201
    session = login(base, name, USER_PW)[1]["session"]
    assert call(base, "POST", "/api/auth/password", {"old": USER_PW, "new": USER_PW2}, session)[0] == 200
    return session


def save(base, session, change):
    project = call(base, "GET", "/api/project", session=session)[1]
    raw = change(project["raw"])
    return call(base, "PUT", "/api/project", {"raw": raw, "mtime": project.get("mtime")}, session)


def add_function(raw):
    raw["functions"]["added"] = {"handler": "app.hello"}
    return raw


def delete_function(raw):
    del raw["functions"]["hello"]
    raw.pop("workflows", None)
    return raw


def change_function(raw):
    raw["functions"]["hello"]["memory"] = 512
    return raw


ALL_READ = {name: "r" for name in permissions.FEATURES}


@pytest.mark.parametrize("name,perms", [("read on all", ALL_READ), ("nothing", {}), ("read on functions", {"functions": "r"})])
def test_read_only_changes_nothing(studio, name, perms):
    base, root, admin = studio
    session = login_as(base, admin, perms)
    before = (root / "pskit.yml").read_bytes(), (root / "app.py").read_bytes()
    assert call(base, "GET", "/api/project", session=session)[0] == 200
    for change in (add_function, delete_function, change_function):
        status, doc = save(base, session, change)
        assert status == 403 and doc["code"] == "forbidden", doc
    for method, path, body in (
        ("POST", "/api/handlers/ensure", {"handler": "app.added", "events": []}),
        ("POST", "/api/functions/hello/split", {}),
        ("PUT", "/api/files", {"path": "app.py", "text": "x = 1\n"}),
        ("PUT", "/api/files", {"path": "pskit.yml", "text": "service: gone\n"}),
        ("POST", "/api/project/init", {"service": "x", "provider": "aws", "force": True}),
        ("POST", "/api/jobs", {"command": "deploy"}),
        ("POST", "/api/jobs", {"command": "remove"}),
        ("POST", "/api/jobs", {"command": "invoke"}),
        ("PUT", "/api/test-events", {"events": []}),
        ("POST", "/api/hana/messages", {"text": "delete everything"}),
    ):
        assert call(base, method, path, body, session)[0] == 403, path
    assert ((root / "pskit.yml").read_bytes(), (root / "app.py").read_bytes()) == before


@pytest.mark.parametrize("letters,add,change,delete", [
    ("c", 200, 403, 403),
    ("u", 403, 200, 403),
    ("d", 403, 403, 200),
    ("crud", 200, 200, 200),
])
def test_each_action_on_a_function_is_its_own_permission(studio, letters, add, change, delete):
    base, _root, admin = studio
    session = login_as(base, admin, {"functions": letters, "workflows": "d"})
    assert save(base, session, add_function)[0] == add
    assert save(base, session, change_function)[0] == change
    assert save(base, session, delete_function)[0] == delete


def test_workflows_are_separate_from_functions(studio):
    base, _root, admin = studio
    session = login_as(base, admin, {"functions": "crud"})

    def drop(raw):
        del raw["workflows"]
        return raw

    status, doc = save(base, session, drop)
    assert status == 403 and doc["feature"] == "workflows" and doc["action"] == "d"


def test_project_settings_need_their_own_update(studio):
    base, _root, admin = studio
    session = login_as(base, admin, {"functions": "crud"})

    def rename(raw):
        raw["service"] = "other"
        return raw

    status, doc = save(base, session, rename)
    assert status == 403 and doc["feature"] == "project"


def test_code_permission_cannot_rewrite_pskit_yml(studio):
    base, root, admin = studio
    session = login_as(base, admin, {"code": "crud"})
    before = (root / "pskit.yml").read_bytes()
    text = CONFIG + "  extra: {handler: app.hello}\n"
    for path in ("pskit.yml", "./pskit.yml", "PSKIT.YML", "sub/../pskit.yml", "pskit.yml."):
        assert call(base, "PUT", "/api/files", {"path": path, "text": "service: gone\n"}, session)[0] in (400, 403), path
    assert call(base, "PUT", "/api/files", {"path": "pskit.yml", "text": text}, session)[0] == 403
    assert (root / "pskit.yml").read_bytes() == before
    assert call(base, "PUT", "/api/files", {"path": "app.py", "text": "x = 1\n"}, session)[0] == 200


def test_saving_a_file_that_does_not_parse_needs_project_update(studio):
    base, _root, admin = studio
    session = login_as(base, admin, {"code": "crud", "functions": "crud", "workflows": "crud", "resources": "crud"})
    assert call(base, "PUT", "/api/files", {"path": "pskit.yml", "text": "a: [unclosed\n"}, session)[0] == 403


def test_saving_with_no_change_is_fine(studio):
    base, _root, admin = studio
    session = login_as(base, admin, {})
    assert save(base, session, lambda raw: raw)[0] != 403


def test_split_needs_functions_update_too(studio):
    base, _root, admin = studio
    session = login_as(base, admin, {"code": "crud"})
    status, doc = call(base, "POST", "/api/functions/hello/split", {}, session)
    assert status == 403 and doc["feature"] == "functions"


def test_replacing_the_project_needs_delete_on_what_it_holds(studio):
    base, _root, admin = studio
    session = login_as(base, admin, {"project": "cu"})
    status, doc = call(base, "POST", "/api/project/init", {"service": "x", "provider": "aws", "force": True}, session)
    assert status == 403 and doc["action"] == "d"


def test_audit_says_what_was_created_and_what_was_refused(studio):
    base, _root, admin = studio
    session = login_as(base, admin, {"functions": "c"})
    assert save(base, session, add_function)[0] == 200
    assert save(base, session, delete_function)[0] == 403
    entries = call(base, "GET", "/api/auth/audit?user=dev", session=admin)[1]["entries"]
    assert any(e["details"].get("changes") == "created functions.added" and e["outcome"] == "ok" for e in entries)
    assert any(e["action"] == "functions.d" and e["outcome"] == "denied" for e in entries)


def test_project_needs():
    base = {"service": "a", "functions": {"f": {"handler": "x"}}}
    assert project_needs(base, dict(base)) == ([], [])
    assert project_needs(base, {**base, "functions": {}}) == ([("functions", "d")], ["deleted functions.f"])
    assert project_needs(base, {"service": "a"}) == ([("functions", "d")], ["deleted functions.f"])
    assert project_needs(base, {**base, "functions": "x"})[0] == [("functions", "u")]
    assert project_needs(base, None)[0] == [("project", "u")]


def test_presets_only_name_real_features():
    for perms in permissions.PRESETS.values():
        assert permissions.clean(perms) == dict(sorted(perms.items()))
    assert not set("cud") & set("".join(permissions.PRESETS["viewer"].values()))
