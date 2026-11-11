"""The vault: keys, grants and revocation, sealing, conflicts, the audit log and the CLI login."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import click
import pytest
from click.testing import CliRunner

from py_serverless_kit.cli.main import cli
from py_serverless_kit.vault import audit, crypto, permissions
from py_serverless_kit.vault import workspace as ws
from py_serverless_kit.vault.errors import VaultError
from py_serverless_kit.vault.store import MASTER_PREFIX, Vault

ADMIN_PW = "correct horse battery"
USER_PW = "first password here"
SECRET = "DB_PASSWORD=hunter2-very-secret\n"


@pytest.fixture(autouse=True)
def fast_kdf(monkeypatch, tmp_path):
    monkeypatch.setattr(crypto, "SCRYPT_N", 2**14)
    monkeypatch.setenv("PSKIT_HOME", str(tmp_path / "home"))
    for name in ("PSKIT_MASTER_KEY", "PSKIT_USER", "PSKIT_PASSWORD", "PSKIT_VAULT_SESSION"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    (root / ".env.onprem").write_bytes(SECRET.encode())
    (root / ".pskit").mkdir()
    (root / ".pskit" / "onprem-servers.json").write_text('{"edge": {"password": "ssh-secret-value"}}')
    return root


@pytest.fixture
def created(project):
    vault, admin, master_key, recovery = Vault.create(project, "root-admin", ADMIN_PW)
    ws.seal(vault, admin)
    return vault, admin, master_key, recovery


def all_vault_bytes(vault: Vault) -> bytes:
    return b"".join(p.read_bytes() for p in vault.dir.rglob("*") if p.is_file())


def test_vault_files_hold_no_plaintext(created):
    vault, _admin, _key, _recovery = created
    raw = all_vault_bytes(vault)
    for needle in (b"hunter2", b"ssh-secret", b"root-admin", b".env.onprem", b"onprem-servers", b"permissions"):
        assert needle not in raw


def test_master_key_alone_opens_no_data(created):
    vault, _admin, master_key, _recovery = created
    master = crypto.parse_secret(MASTER_PREFIX, master_key, "master key")
    doc = vault.accounts(master)  # it can read the accounts, which hold only wrapped keys
    assert "hunter2" not in json.dumps(doc)
    with pytest.raises(VaultError, match="wrong username"):
        vault.authenticate(master, "root-admin", "not the right password")


def test_login_needs_the_master_key_and_the_password(created):
    vault, admin, master_key, _recovery = created
    with pytest.raises(VaultError, match="wrong master key"):
        vault.authenticate(crypto.random_key(), "root-admin", ADMIN_PW)
    with pytest.raises(VaultError, match="wrong username"):
        vault.authenticate(admin.master, "nobody", ADMIN_PW)
    assert vault.authenticate(crypto.parse_secret(MASTER_PREFIX, master_key, "k"), "root-admin", ADMIN_PW).username


def test_master_key_typo_is_told_apart(created):
    _vault, _admin, master_key, _recovery = created
    typo = master_key[:10] + ("A" if master_key[10] != "A" else "B") + master_key[11:]
    with pytest.raises(VaultError, match="typo"):
        crypto.parse_secret(MASTER_PREFIX, typo, "master key")
    with pytest.raises(VaultError, match="starts with"):
        crypto.parse_secret(MASTER_PREFIX, "nonsense", "master key")


def test_weak_kdf_in_a_changed_vault_is_refused():
    with pytest.raises(VaultError, match="unsafe"):
        crypto.password_key("x", b"s" * 16, 2**4, 8, 1)


def test_second_developer_gets_only_what_was_granted(created, tmp_path):
    vault, admin, master_key, _recovery = created
    vault.add_user(admin, "dev", USER_PW, perms={"code": "crud", "env": "r"})

    # The other developer's clone: the vault, no plaintext.
    clone = tmp_path / "clone"
    clone.mkdir()
    subprocess.run(["cp", "-r", str(vault.dir), str(clone)], check=False)
    theirs = Vault(clone)
    master = crypto.parse_secret(MASTER_PREFIX, master_key, "k")
    session = ws.login(theirs, master, "dev", USER_PW, "cli")
    ws.open_workspace(theirs, session)
    assert (clone / ".env.onprem").read_text() == SECRET
    assert not (clone / ".pskit" / "onprem-servers.json").exists()  # no read on servers
    assert set(theirs.area_keys(session.identity)) == {"env"}


def test_revoking_rotates_the_key_and_keeps_the_data(created):
    vault, admin, _key, _recovery = created
    vault.add_user(admin, "dev", USER_PW, perms={"env": "r"})
    dev = vault.authenticate(admin.master, "dev", USER_PW)
    old_key = vault.area_keys(dev)["env"]

    vault.update_user(admin, "dev", {"permissions": {}})
    assert vault.area_keys(dev) == {}
    doc = vault.accounts(admin.master)
    assert doc["areas"]["env"]["generation"] == 2
    new_key = vault.area_keys(admin)["env"]
    assert new_key != old_key
    assert dict(vault.read_area("env", new_key, 2)) == {".env.onprem": SECRET.encode()}
    assert list(vault.data_dir("env").glob("*.enc"))
    assert list(vault.read_area("env", new_key, 1)) == []  # old generation gone


def test_granting_later_works_without_the_users_password(created):
    vault, admin, _key, _recovery = created
    vault.add_user(admin, "dev", USER_PW, perms={})
    dev = vault.authenticate(admin.master, "dev", USER_PW)
    assert vault.area_keys(dev) == {}
    vault.update_user(admin, "dev", {"permissions": {"servers": "r"}})
    assert set(vault.area_keys(dev)) == {"servers"}


def test_deploy_permission_decrypts_only_its_own_area(created):
    vault, admin, _key, _recovery = created
    vault.add_user(admin, "ops", USER_PW, perms={"deploy": "c"})
    assert set(vault.area_keys(vault.authenticate(admin.master, "ops", USER_PW))) == {"deployments"}


@pytest.mark.parametrize(
    ("feature", "area"),
    [("env", "env"), ("servers", "servers"), ("services", "services"), ("clusters", "clusters"),
     ("balancers", "clusters"), ("test", "studio"), ("hana", "studio"), ("deploy", "deployments")],
)
def test_read_on_one_feature_decrypts_only_its_area(feature, area):
    assert permissions.areas_for({"permissions": {feature: "r"}}) == {area}


def test_keys_from_the_wider_old_rules_stop_working_and_are_rotated_at_the_admin_login(created, monkeypatch):
    vault, admin, _key, _recovery = created
    with monkeypatch.context() as old_rules:
        old_rules.setattr(permissions, "areas_for", lambda user: frozenset(permissions.AREAS))
        vault.add_user(admin, "ops", USER_PW, perms={"deploy": "c"})
    ops = vault.authenticate(admin.master, "ops", USER_PW)
    assert "ops" in vault.accounts(admin.master)["areas"]["servers"]["wraps"]
    assert set(vault.area_keys(ops)) == {"deployments"}

    assert vault.apply_grants(ops) is False  # not an admin
    assert vault.apply_grants(admin) is True
    doc = vault.accounts(admin.master)
    assert "ops" not in doc["areas"]["servers"]["wraps"]
    assert doc["areas"]["servers"]["generation"] == 2
    assert vault.apply_grants(admin) is False


def test_a_logged_in_account_gets_and_loses_files_without_a_new_login(created, project):
    vault, admin, master_key, _recovery = created
    vault.add_user(admin, "dev", USER_PW, perms={})
    master = crypto.parse_secret(MASTER_PREFIX, master_key, "k")
    ws.open_workspace(vault, ws.login(vault, master, "dev", USER_PW, "cli"))
    servers, env = project / ".pskit" / "onprem-servers.json", project / ".env.onprem"
    assert not servers.exists() and not env.exists()
    ws.sync_access(vault)
    assert ws.sync_access(vault) is False  # nothing changed

    vault.update_user(admin, "dev", {"permissions": {"servers": "r"}})
    assert ws.sync_access(vault) is True
    assert servers.exists() and not env.exists()  # only what was granted

    vault.update_user(admin, "dev", {"permissions": {"env": "r"}})
    assert ws.sync_access(vault) is True
    assert env.exists() and not servers.exists()

    vault.remove_user(admin, "dev")
    assert ws.sync_access(vault) is True
    assert not env.exists()


def test_a_user_cannot_grant(created):
    vault, admin, _key, _recovery = created
    vault.add_user(admin, "dev", USER_PW, perms={"env": "r"})
    dev = vault.authenticate(admin.master, "dev", USER_PW)
    with pytest.raises(VaultError, match="do not hold"):
        vault.update_user(dev, "dev", {"permissions": {"servers": "r"}})


def test_vault_keeps_an_admin(created):
    vault, admin, _key, _recovery = created
    with pytest.raises(VaultError, match="at least one active admin"):
        vault.update_user(admin, "root-admin", {"role": "user"})
    with pytest.raises(VaultError, match="at least one active admin"):
        vault.update_user(admin, "root-admin", {"disabled": True})


def test_change_and_reset_password(created):
    vault, admin, _key, _recovery = created
    vault.add_user(admin, "dev", USER_PW, perms={"env": "r"})
    dev = vault.authenticate(admin.master, "dev", USER_PW)
    assert vault.user(dev)["must_change"] is True
    vault.change_password(dev, USER_PW, "my own new password")
    assert vault.user(dev)["must_change"] is False
    with pytest.raises(VaultError):
        vault.authenticate(admin.master, "dev", USER_PW)

    vault.reset_password(admin, "dev", "admin chose this one")
    fresh = vault.authenticate(admin.master, "dev", "admin chose this one")
    assert set(vault.area_keys(fresh)) == {"env"}
    assert vault.area_keys(dev) == {}  # the session from before the reset lost its keys


def test_recovery_code_restores_a_lost_admin(created):
    vault, admin, _key, recovery = created
    with pytest.raises(VaultError, match="wrong recovery"):
        vault.recover(admin.master, crypto.format_secret("pskr", crypto.random_key()), "root-admin", "brand new password")
    vault.recover(admin.master, recovery, "root-admin", "brand new password")
    back = vault.authenticate(admin.master, "root-admin", "brand new password")
    assert dict(vault.read_area("env", vault.area_keys(back)["env"], 1))[".env.onprem"] == SECRET.encode()


def test_replacing_the_recovery_code_revokes_the_old_one(created):
    vault, admin, _key, old_code = created
    old_doc = vault.accounts(admin.master)
    old_keys = vault.area_keys(admin)
    old_files = {p.name for p in vault.data_dir("env").glob("*.enc")}

    new_code = ws.rotate_recovery(vault, admin)

    assert new_code != old_code
    with pytest.raises(VaultError, match="wrong recovery"):
        vault.recover(admin.master, old_code, "root-admin", "brand new password")
    # An old vault.json from git history opens old keys only, and those no longer open today's data.
    new_keys = vault.area_keys(admin)
    assert all(new_keys[area] != old_keys[area] for area in old_keys)
    assert old_doc["areas"]["env"]["generation"] + 1 == vault.accounts(admin.master)["areas"]["env"]["generation"]
    assert not old_files & {p.name for p in vault.data_dir("env").glob("*.enc")}
    generation = vault.accounts(admin.master)["areas"]["env"]["generation"]
    assert dict(vault.read_area("env", new_keys["env"], generation))[".env.onprem"] == SECRET.encode()
    assert dict(vault.read_area("env", old_keys["env"], generation - 1)) == {}

    vault.recover(admin.master, new_code, "root-admin", "brand new password")
    assert vault.authenticate(admin.master, "root-admin", "brand new password").username == "root-admin"


def test_replacing_the_recovery_code_keeps_what_each_account_holds(created):
    vault, admin, _key, _recovery = created
    vault.add_user(admin, "reader", USER_PW, "user", {"env": "r"})
    ws.rotate_recovery(vault, admin)
    reader = vault.authenticate(admin.master, "reader", USER_PW)
    keys = vault.area_keys(reader)
    assert set(keys) == {"env"}
    generation = vault.accounts(admin.master)["areas"]["env"]["generation"]
    assert dict(vault.read_area("env", keys["env"], generation))[".env.onprem"] == SECRET.encode()


def test_the_viewer_preset_decrypts_nothing():
    assert permissions.areas_for({"role": "user", "permissions": permissions.PRESETS["viewer"]}) == frozenset()


def test_rotating_the_master_key_keeps_the_audit_log(created):
    vault, admin, old_key, _recovery = created
    audit.record(vault, admin.master, "root-admin", "cli", "before")
    new_key = vault.rotate_master(admin)
    with pytest.raises(VaultError, match="wrong master key"):
        vault.accounts(crypto.parse_secret(MASTER_PREFIX, old_key, "k"))
    master = crypto.parse_secret(MASTER_PREFIX, new_key, "k")
    audit.record(vault, master, "root-admin", "cli", "after")
    result = audit.read(vault, master)
    assert {e["action"] for e in result["entries"]} == {"before", "after"}
    assert result["tampered"] == []


def test_changing_a_sealed_file_is_detected(created):
    vault, admin, _key, _recovery = created
    enc = next(vault.data_dir("env").glob("*.enc"))
    raw = bytearray(enc.read_bytes())
    raw[-1] ^= 1
    enc.write_bytes(bytes(raw))
    with pytest.raises(VaultError, match="changed or is damaged"):
        ws.unseal(vault, admin)


def test_accounts_cannot_be_edited_without_the_master_key(created):
    vault, admin, _key, _recovery = created
    header = json.loads(vault.path.read_text())
    blob = bytearray(crypto.unb64(header["accounts"]))
    blob[-1] ^= 1
    header["accounts"] = crypto.b64(bytes(blob))
    vault.path.write_text(json.dumps(header))
    with pytest.raises(VaultError, match="changed or are damaged"):
        vault.accounts(admin.master)


def test_sealed_files_cannot_be_moved_between_areas(created):
    vault, admin, _key, _recovery = created
    keys = vault.area_keys(admin)
    enc = next(vault.data_dir("env").glob("*.enc"))
    target = vault.data_dir("servers") / enc.name
    target.write_bytes(enc.read_bytes())
    with pytest.raises(VaultError):
        list(vault.read_area("servers", keys["servers"], 1))


def test_a_vault_file_cannot_write_over_code(created):
    vault, admin, _key, _recovery = created
    key = vault.area_keys(admin)["env"]
    vault.seal_file("env", key, 1, "../evil.py", b"x")
    with pytest.raises(VaultError, match="outside the project"):
        ws.unseal(vault, admin)
    vault.remove_file("env", key, "../evil.py")
    vault.seal_file("env", key, 1, "app/handlers.py", b"x")
    with pytest.raises(VaultError, match="may not write"):
        ws.unseal(vault, admin)


def test_only_changed_files_are_rewritten(created, project):
    vault, admin, _key, _recovery = created
    enc = next(vault.data_dir("env").glob("*.enc"))
    before = enc.read_bytes()
    assert ws.seal(vault, admin)["sealed"] == []
    assert enc.read_bytes() == before
    (project / ".env.onprem").write_bytes((SECRET + "MORE=1\n").encode())
    assert ws.seal(vault, admin)["sealed"] == [".env.onprem"]
    assert enc.read_bytes() != before  # same file name: git sees an update
    assert len(list(vault.data_dir("env").glob("*.enc"))) == 1


def test_deleted_file_leaves_the_vault(created, project):
    vault, admin, _key, _recovery = created
    (project / ".env.onprem").unlink()
    assert ws.seal(vault, admin)["removed"] == [".env.onprem"]
    assert list(vault.data_dir("env").glob("*.enc")) == []


def test_read_only_account_does_not_write_the_vault(created, project):
    vault, admin, _key, _recovery = created
    vault.add_user(admin, "dev", USER_PW, perms={"env": "r"})
    dev = vault.authenticate(admin.master, "dev", USER_PW)
    (project / ".env.onprem").write_bytes(b"EDITED=1\n")
    assert ws.seal(vault, dev) == {"sealed": [], "removed": [], "skipped": [".env.onprem"]}


def test_logout_removes_plaintext_but_not_unsealed_edits_from_a_read_only_account(created, project):
    vault, admin, _key, _recovery = created
    session = ws.Session("s1", admin, "cli", 9e12)
    ws.write_session(project, session)
    ws.close_session(vault, session)
    assert not (project / ".env.onprem").exists()
    assert not (project / ".pskit" / "onprem-servers.json").exists()

    session = ws.login(vault, admin.master, "root-admin", ADMIN_PW, "cli")
    ws.open_workspace(vault, session)
    assert (project / ".env.onprem").read_text() == SECRET


def test_revoked_account_loses_the_plaintext_at_its_next_sync(created, project):
    vault, admin, master_key, _recovery = created
    vault.add_user(admin, "dev", USER_PW, perms={"servers": "r"})
    master = crypto.parse_secret(MASTER_PREFIX, master_key, "k")
    session = ws.login(vault, master, "dev", USER_PW, "cli")
    ws.open_workspace(vault, session)
    servers = project / ".pskit" / "onprem-servers.json"
    assert servers.exists()

    vault.update_user(admin, "dev", {"permissions": {}})
    assert ".pskit/onprem-servers.json" in ws.unseal(vault, session.identity)["removed"]
    assert not servers.exists()
    assert dict(vault.read_area("servers", vault.area_keys(admin)["servers"], 2))  # the vault keeps it


def test_sync_keeps_the_plaintext_another_session_holds(created, project):
    vault, admin, master_key, _recovery = created
    vault.add_user(admin, "dev", USER_PW, perms={"servers": "r"})
    master = crypto.parse_secret(MASTER_PREFIX, master_key, "k")
    ws.login(vault, master, "root-admin", ADMIN_PW, "cli")
    session = ws.login(vault, master, "dev", USER_PW, "cli")
    ws.open_workspace(vault, session)

    vault.update_user(admin, "dev", {"permissions": {}})
    assert ws.unseal(vault, session.identity)["removed"] == []
    assert (project / ".pskit" / "onprem-servers.json").exists()


def test_plaintext_stays_while_another_session_holds_it(created, project):
    vault, admin, _key, _recovery = created
    one = ws.login(vault, admin.master, "root-admin", ADMIN_PW, "cli")
    two = ws.login(vault, admin.master, "root-admin", ADMIN_PW, "cli")
    ws.close_session(vault, one)
    assert (project / ".env.onprem").exists()
    ws.close_session(vault, two)
    assert not (project / ".env.onprem").exists()


def test_expired_session_is_sealed_and_cleaned_up(created, project):
    vault, admin, _key, _recovery = created
    ws.write_session(project, ws.Session("old", admin, "cli", 1.0))
    (project / ".env.onprem").write_bytes(b"CHANGED=1\n")
    assert ws.live_sessions(vault) == []
    assert not (project / ".env.onprem").exists()
    assert dict(vault.read_area("env", vault.area_keys(admin)["env"], 1))[".env.onprem"] == b"CHANGED=1\n"


def test_pull_with_local_edit_keeps_both(created, project):
    vault, admin, _key, _recovery = created
    ws.seal(vault, admin)
    key = vault.area_keys(admin)["env"]
    vault.seal_file("env", key, 1, ".env.onprem", b"FROM_TEAMMATE=1\n")  # what a git pull brings
    (project / ".env.onprem").write_bytes(b"MY_EDIT=1\n")
    result = ws.unseal(vault, admin)
    assert result["conflicts"] == [".env.onprem"]
    assert (project / ".env.onprem").read_text() == "FROM_TEAMMATE=1\n"
    assert (project / ".env.onprem.vault-conflict").read_text() == "MY_EDIT=1\n"


def test_local_edit_after_a_crash_is_not_overwritten(created, project):
    vault, admin, _key, _recovery = created
    (project / ".env.onprem").write_bytes(b"EDITED_BEFORE_CRASH=1\n")
    session = ws.login(vault, admin.master, "root-admin", ADMIN_PW, "cli")
    opened = ws.open_workspace(vault, session)
    assert opened["kept"] == [".env.onprem"] and opened["conflicts"] == []
    assert dict(vault.read_area("env", vault.area_keys(admin)["env"], 1))[".env.onprem"] == b"EDITED_BEFORE_CRASH=1\n"


def test_env_detection():
    for name in (".env", ".env.onprem", "sub/.env.local", ".ENV", ".env.", ".env/", ".env::$DATA", "a\\.env"):
        assert ws.is_env_file(name), name
    for name in (".env.example", ".env.sample", "app/env.py", ".environment", ".env.onprem.vault-conflict"):
        assert not ws.is_env_file(name), name


def test_gitignore_is_added_once_and_keeps_the_vault(project):
    (project / ".gitignore").write_text("build/")
    assert ".env.*" in ws.ensure_gitignore(project)
    text = (project / ".gitignore").read_text()
    assert text.startswith("build/\n") and ".pskit/" in text and ".pskit-vault" not in text.replace("(encrypted)", "").split("\n", 2)[2]
    assert ws.ensure_gitignore(project) == []


def test_tracked_plaintext_is_reported(project):
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)
    subprocess.run(["git", "add", "-f", ".env.onprem"], cwd=project, check=True)
    assert ws.tracked_plaintext(project) == [".env.onprem"]


def test_audit_detects_changed_and_removed_lines(created):
    vault, admin, _key, _recovery = created
    for name in ("one", "two", "three"):
        audit.record(vault, admin.master, "root-admin", "cli", name)
    path = next((vault.dir / "audit").glob("*.log"))
    assert audit.read(vault, admin.master)["tampered"] == []
    lines = path.read_text().splitlines()
    path.write_text("\n".join([lines[0], lines[2]]) + "\n")  # one line taken out
    assert audit.read(vault, admin.master)["tampered"] == [path.name]


def test_audit_pages_newest_first_with_filters(created):
    vault, admin, _key, _recovery = created
    for i in range(7):
        audit.record(vault, admin.master, "root-admin" if i % 2 else "dev", "cli", f"step.{i}")
    all_entries = audit.read(vault, admin.master)["entries"]
    first = audit.read(vault, admin.master, limit=3)
    second = audit.read(vault, admin.master, limit=3, offset=3)
    last = audit.read(vault, admin.master, limit=3, offset=6)
    assert first["total"] == second["total"] == last["total"] == 7
    assert (first["offset"], second["offset"], first["limit"]) == (0, 3, 3)
    assert first["entries"] + second["entries"] + last["entries"] == all_entries and len(last["entries"]) == 1
    assert audit.read(vault, admin.master, limit=3, offset=99)["entries"] == []
    assert audit.read(vault, admin.master, limit=0, offset=-5)["offset"] == 0
    dev = audit.read(vault, admin.master, user="dev", limit=2, offset=2)
    assert dev["total"] == 4 and len(dev["entries"]) == 2 and {e["user"] for e in dev["entries"]} == {"dev"}


def test_audit_details_drop_secrets():
    details = audit.safe_details({
        "path": "app.py", "password": "x", "passphrase": "x", "text": "x", "api_key": "x", "master_key": "x",
        "token": "x", "env": {"A": "x"}, "value": "x", "command": "deploy", "stage": "dev",
    })
    assert details == {"path": "app.py", "command": "deploy", "stage": "dev"}


# ------------------------------------------------------------------------------- permissions
def _commands(group: click.Group, prefix=()):
    for name, command in group.commands.items():
        path = (*prefix, name)
        if isinstance(command, click.Group):
            yield from _commands(command, path)
        else:
            yield path


def test_every_cli_command_has_a_permission():
    missing = [
        " ".join(path) for path in _commands(cli)
        if path[0] not in permissions.OPEN_COMMANDS and permissions.cli_permission(path) == permissions.ADMIN_ONLY
    ]
    assert missing == []


def test_no_one_can_be_granted_admin_only():
    with pytest.raises(VaultError):
        permissions.clean({"admin": "u"})
    user = {"role": "user", "permissions": {name: "crud" for name in permissions.FEATURES}}
    assert not permissions.allowed(user, *permissions.ADMIN_ONLY)


@pytest.mark.parametrize("method,parts,expected", [
    ("PUT", ["project"], ("project", "u")),
    ("GET", ["files"], ("code", "r")),
    ("PUT", ["files"], ("code", "u")),
    ("POST", ["onprem-services"], ("services", "c")),
    ("GET", ["onprem-services", "pg"], ("services", "r")),
    ("POST", ["onprem-services", "pg", "remove"], ("services", "d")),
    ("POST", ["onprem-services", "pg", "backup"], ("services", "u")),
    ("POST", ["onprem-services", "pg", "browse", "s3", "list"], ("services", "r")),
    ("POST", ["onprem-services", "pg", "browse", "s3", "delete"], ("services", "u")),
    ("POST", ["onprem-servers", "edge", "shell"], ("shell", "u")),
    ("POST", ["onprem-terminals"], ("shell", "u")),
    ("POST", ["vscode", "start"], ("shell", "u")),
    ("POST", ["hana", "messages"], ("hana", "u")),
    ("GET", ["workflow-test"], ("test", "r")),
    ("POST", ["workflow-test"], ("test", "c")),
    ("GET", ["workflow-test", "abc"], ("test", "r")),
    ("POST", ["workflow-test", "abc", "cancel"], ("test", "u")),
    ("POST", ["settings-bundle", "export"], permissions.ADMIN_ONLY),
    ("POST", ["something-new"], permissions.ADMIN_ONLY),
    ("DELETE", ["project"], permissions.ADMIN_ONLY),
])
def test_studio_routes(method, parts, expected):
    assert permissions.studio_permission(method, parts) == expected


def test_jobs_by_command():
    assert permissions.job_permission("deploy") == ("deploy", "c")
    assert permissions.job_permission("remove") == ("deploy", "d")
    assert permissions.job_permission("invented") == permissions.ADMIN_ONLY


def test_project_read_is_for_everyone_and_disabled_means_nothing():
    assert permissions.allowed({"role": "user"}, "project", "r")
    assert not permissions.allowed({"role": "user"}, "project", "u")
    assert not permissions.allowed({"role": "admin", "disabled": True}, "project", "r")
    assert permissions.areas_for({"role": "admin", "disabled": True}) == frozenset()


# ------------------------------------------------------------------------------- CLI
@pytest.fixture
def cli_project(project, monkeypatch):
    (project / "pskit.yml").write_text(
        "service: demo\nprovider: {name: aws, region: us-east-1}\n"
        "functions:\n  hello: {handler: app.hello, events: [{http: GET /hello}]}\n"
    )
    (project / "app.py").write_text("def hello(event, ctx):\n    return {}\n")
    monkeypatch.chdir(project)
    return project


def _init(runner):
    result = runner.invoke(cli, ["vault", "init", "-u", "root-admin"], input=f"{ADMIN_PW}\n{ADMIN_PW}\n")
    assert result.exit_code == 0, result.output
    line = next(ln for ln in result.output.splitlines() if ln.startswith("MASTER KEY"))
    return line.split()[-1]


def test_no_vault_changes_nothing(cli_project):
    assert CliRunner().invoke(cli, ["validate"]).exit_code == 0


def test_cli_flow(cli_project, tmp_path):
    runner = CliRunner()
    key = _init(runner)
    assert (cli_project / ".pskit-vault" / "vault.json").is_file()
    assert ".env.*" in (cli_project / ".gitignore").read_text()

    assert runner.invoke(cli, ["validate"]).exit_code == 0  # logged in by init
    assert runner.invoke(cli, ["logout"]).exit_code == 0
    assert not (cli_project / ".env.onprem").exists()

    result = runner.invoke(cli, ["validate"])
    assert result.exit_code != 0 and "pskit login" in result.output
    assert runner.invoke(cli, ["validate", "--help"]).exit_code == 0  # help needs no login

    result = runner.invoke(cli, ["login", "-u", "root-admin"], input=f"{key}\n{ADMIN_PW}\n")
    assert result.exit_code == 0, result.output
    assert "master key" in result.output.lower()
    assert (cli_project / ".env.onprem").read_text() == SECRET

    # the master key is not saved: the password alone is refused, on this computer too
    runner.invoke(cli, ["logout"])
    assert not (tmp_path / "home" / "vault-keys").exists()
    assert runner.invoke(cli, ["login", "-u", "root-admin"], input=f"{ADMIN_PW}\n").exit_code != 0
    assert not (cli_project / ".env.onprem").exists()
    assert runner.invoke(cli, ["login", "-u", "root-admin"], input=f"{key}\n{ADMIN_PW}\n").exit_code == 0

    # a command's change is sealed when it ends
    (cli_project / ".env.onprem").write_bytes(b"NEW=1\n")
    assert runner.invoke(cli, ["validate"]).exit_code == 0
    vault = Vault(cli_project)
    master = crypto.parse_secret(MASTER_PREFIX, key, "master key")
    admin = vault.authenticate(master, "root-admin", ADMIN_PW)
    assert dict(vault.read_area("env", vault.area_keys(admin)["env"], 1))[".env.onprem"].startswith(b"NEW=1")
    audit_out = runner.invoke(cli, ["vault", "audit"]).output
    assert "cli.validate" in audit_out and "auth.login" in audit_out


def test_cli_permissions(cli_project):
    runner = CliRunner()
    key = _init(runner)
    args = ["vault", "users", "add", "reader", "--allow", "deploy=r"]
    assert runner.invoke(cli, args, input=f"{USER_PW}\n{USER_PW}\n").exit_code == 0
    runner.invoke(cli, ["logout"])

    assert runner.invoke(cli, ["login", "-u", "reader"], input=f"{key}\n{USER_PW}\n").exit_code == 0
    refused = runner.invoke(cli, ["validate"])
    assert "new password" in refused.output
    changed = runner.invoke(cli, ["vault", "password"], input=f"{USER_PW}\nreader own password\nreader own password\n")
    assert changed.exit_code == 0, changed.output

    assert runner.invoke(cli, ["validate"]).exit_code == 0
    refused = runner.invoke(cli, ["deploy"])
    assert refused.exit_code != 0 and "create permission on deploy" in refused.output
    assert runner.invoke(cli, ["vault", "users", "list"]).exit_code != 0
    assert runner.invoke(cli, ["vault", "audit"]).exit_code != 0

    runner.invoke(cli, ["logout"])
    runner.invoke(cli, ["login", "-u", "root-admin"], input=f"{key}\n{ADMIN_PW}\n")
    out = runner.invoke(cli, ["vault", "audit", "--user", "reader"]).output
    assert "cli.deploy" in out and "denied" in out


def test_cli_replaces_the_recovery_code(cli_project):
    runner = CliRunner()
    _init(runner)
    result = runner.invoke(cli, ["vault", "rotate-recovery-code"])
    assert result.exit_code == 0, result.output
    assert "NEW RECOVERY CODE  pskr-" in result.output
    assert "cli" in runner.invoke(cli, ["vault", "audit", "--action", "rotate-recovery-code"]).output


def test_cli_env_login_for_scripts(cli_project, monkeypatch):
    runner = CliRunner()
    key = _init(runner)
    runner.invoke(cli, ["logout"])
    monkeypatch.setenv("PSKIT_MASTER_KEY", key)
    monkeypatch.setenv("PSKIT_USER", "root-admin")
    monkeypatch.setenv("PSKIT_PASSWORD", ADMIN_PW)
    assert runner.invoke(cli, ["validate"]).exit_code == 0
    assert not (cli_project / ".env.onprem").exists()  # closed again at the end of the command


def test_packaging_leaves_the_vault_out(cli_project):
    from py_serverless_kit.packaging.builder import DEFAULT_EXCLUDES

    assert ".pskit-vault/**" in DEFAULT_EXCLUDES


def test_paths_are_strings(project):
    assert all(isinstance(p, str) for p in ws.scan_area(Path(project), "env"))
