"""SSH private keys given as text for a saved server, the defaults of a new server, and their place in the vault."""

from __future__ import annotations

import base64
import json
import shutil
import struct
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from py_serverless_kit.cli.main import cli
from py_serverless_kit.core import onprem_servers as srv
from py_serverless_kit.core.ssh_keys import clean_private_key
from py_serverless_kit.vault import crypto
from py_serverless_kit.vault import workspace as ws
from py_serverless_kit.vault.store import MASTER_PREFIX, Vault

PASSWORD = "correct horse battery"  # noqa: S105


def _openssh(cipher: bytes = b"none") -> str:
    data = b"openssh-key-v1\0" + struct.pack(">I", len(cipher)) + cipher + b"\0" * 300
    text = base64.b64encode(data).decode("ascii")
    lines = [text[i : i + 70] for i in range(0, len(text), 70)]
    return "-----BEGIN OPENSSH PRIVATE KEY-----\n" + "\n".join(lines) + "\n-----END OPENSSH PRIVATE KEY-----\n"


KEY = _openssh()
BODY = KEY.splitlines()[1]


@pytest.mark.parametrize(
    "pasted",
    [KEY, KEY.replace("\n", "\r\n"), KEY.strip(), "\n  " + KEY + "\n\n", KEY.replace("\n", "\\n"), KEY.replace("\n", " ")],
    ids=["as-is", "crlf", "no-final-newline", "surrounding-space", "literal-backslash-n", "newlines-lost"],
)
def test_pasted_keys_become_what_openssh_reads(pasted):
    assert clean_private_key(pasted) == KEY


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("", "not an SSH private key"),
        ("hello", "not an SSH private key"),
        ("ssh-ed25519 AAAAC3Nza me@laptop", "public key"),
        ("-----BEGIN PUBLIC KEY-----\nAAAA\n-----END PUBLIC KEY-----", "public key"),
        ("PuTTY-User-Key-File-3: ssh-ed25519\n", "PuTTY"),
        ("-----BEGIN RSA PRIVATE KEY-----\nAAAA", "not an SSH private key"),
        ("-----BEGIN RSA PRIVATE KEY-----\nnot*base64\n-----END RSA PRIVATE KEY-----", "damaged"),
        ("-----BEGIN ENCRYPTED PRIVATE KEY-----\nAAAA\n-----END ENCRYPTED PRIVATE KEY-----", "passphrase"),
        ("-----BEGIN RSA PRIVATE KEY-----\nProc-Type: 4,ENCRYPTED\n\nAAAA\n-----END RSA PRIVATE KEY-----", "passphrase"),
        (_openssh(b"aes256-ctr"), "passphrase"),
        ("x" * 70000, "too long"),
    ],
)
def test_unusable_keys_are_refused_without_quoting_them(text, message):
    with pytest.raises(ValueError, match=message) as info:
        clean_private_key(text)
    assert "AAAA" not in str(info.value)


@pytest.mark.skipif(not shutil.which("ssh-keygen"), reason="needs OpenSSH")
@pytest.mark.parametrize("kind", [["-t", "ed25519"], ["-t", "rsa", "-b", "2048", "-m", "PEM"]], ids=["openssh", "pem"])
def test_openssh_accepts_a_saved_key(tmp_path, kind):
    """A real key, pasted with its line breaks lost, then used by the real ssh-keygen (which checks the file's access)."""
    original = tmp_path / "original"
    subprocess.run(["ssh-keygen", *kind, "-N", "", "-q", "-f", str(original)], check=True)  # noqa: S603, S607
    srv.save_server(tmp_path, "edge1", {
        "host": "10.0.0.5", "user": "ubuntu", "private_key": original.read_text("ascii").replace("\n", " "),
    })
    saved = srv.get_server(tmp_path, "edge1")["identity_file"]
    done = subprocess.run(["ssh-keygen", "-y", "-f", saved], capture_output=True, text=True, check=False)  # noqa: S603, S607
    assert done.returncode == 0, done.stderr
    assert done.stdout.split()[:2] == Path(str(original) + ".pub").read_text("ascii").split()[:2]


def test_the_key_stays_out_of_the_settings_and_of_every_answer(tmp_path):
    item = srv.save_server(tmp_path, "edge1", {"host": "10.0.0.5", "user": "ubuntu", "auth": "key", "private_key": KEY})
    assert "private_key" not in item
    raw = (tmp_path / ".pskit" / "onprem-servers.json").read_text("utf-8")
    assert BODY not in raw and json.loads(raw)["servers"]["edge1"]["identity_file"] == ".pskit/ssh/keys/edge1.pem"
    assert (tmp_path / ".pskit" / "ssh" / "keys" / "edge1.pem").read_text("ascii") == KEY
    listed = srv.list_servers(tmp_path)[0]
    assert listed["key_stored"] is True and BODY not in json.dumps(listed)
    assert srv.server_target(tmp_path, "edge1")["identity_file"] == str(tmp_path / ".pskit" / "ssh" / "keys" / "edge1.pem")


def test_a_bad_key_saves_nothing(tmp_path):
    with pytest.raises(srv.ServerError, match="private key: this is a public key"):
        srv.save_server(tmp_path, "edge1", {"host": "10.0.0.5", "auth": "key", "private_key": "ssh-rsa AAAA me"})
    assert srv.load_servers(tmp_path) == {} and not (tmp_path / ".pskit" / "ssh").exists()


def test_key_text_is_ignored_for_other_logins(tmp_path):
    srv.save_server(tmp_path, "edge1", {"host": "10.0.0.5", "auth": "agent", "private_key": KEY})
    assert "identity_file" not in srv.get_server(tmp_path, "edge1")
    assert not (tmp_path / ".pskit" / "ssh").exists()


def test_a_file_path_is_kept_as_given_and_not_reported_as_stored(tmp_path):
    srv.save_server(tmp_path, "edge1", {"host": "10.0.0.5", "auth": "key", "identity_file": "/keys/k.pem"})
    assert srv.list_servers(tmp_path)[0]["key_stored"] is False
    assert srv.get_server(tmp_path, "edge1")["identity_file"].endswith("k.pem")


def test_editing_keeps_replaces_and_removes_the_saved_key(tmp_path):
    path = tmp_path / ".pskit" / "ssh" / "keys" / "edge1.pem"
    srv.save_server(tmp_path, "edge1", {"host": "10.0.0.5", "auth": "key", "private_key": KEY})
    # The studio sends the saved path back when the box is left empty.
    srv.save_server(tmp_path, "edge1", {"host": "10.0.0.6", "auth": "key", "identity_file": str(path)})
    assert path.read_text("ascii") == KEY and srv.get_server(tmp_path, "edge1")["host"] == "10.0.0.6"
    srv.save_server(tmp_path, "edge1", {"host": "10.0.0.6", "auth": "key", "private_key": KEY})
    assert path.is_file()
    # Another way to log in: the secret must not stay behind.
    srv.save_server(tmp_path, "edge1", {"host": "10.0.0.6", "auth": "agent"})
    assert not path.exists()


def test_removing_a_server_deletes_its_key(tmp_path):
    srv.save_server(tmp_path, "edge1", {"host": "10.0.0.5", "auth": "key", "private_key": KEY})
    srv.remove_server(tmp_path, "edge1")
    assert not (tmp_path / ".pskit" / "ssh" / "keys" / "edge1.pem").exists()


def test_a_path_from_another_clone_points_into_this_one(tmp_path):
    (tmp_path / ".pskit" / "ssh" / "keys").mkdir(parents=True)
    (tmp_path / ".pskit" / "onprem-servers.json").write_text(json.dumps({"servers": {
        "old": {"host": "h", "password_file": "/home/priya/proj/.pskit/ssh/root_h-22.pass"},
        "win": {"host": "h", "identity_file": "C:\\Users\\priya\\proj\\.pskit\\ssh\\keys\\win.pem"},
        "own": {"host": "h", "identity_file": "/home/priya/.ssh/own.pem"},
    }}))
    servers = srv.load_servers(tmp_path)
    assert servers["old"]["password_file"] == str(tmp_path / ".pskit" / "ssh" / "root_h-22.pass")
    assert servers["win"]["identity_file"] == str(tmp_path / ".pskit" / "ssh" / "keys" / "win.pem")
    assert servers["own"]["identity_file"] == "/home/priya/.ssh/own.pem"


# ------------------------------------------------------------------------- vault
@pytest.fixture
def team(tmp_path, monkeypatch):
    monkeypatch.setattr(crypto, "SCRYPT_N", 2**14)
    monkeypatch.setenv("PSKIT_HOME", str(tmp_path / "home"))
    root = tmp_path / "proj"
    root.mkdir()
    vault, admin, master_key, _recovery = Vault.create(root, "root-admin", PASSWORD)
    srv.save_server(root, "edge1", {"host": "10.0.0.5", "user": "ubuntu", "auth": "key", "private_key": KEY})
    vault.add_user(admin, "ops", PASSWORD, perms={"servers": "r"})
    vault.add_user(admin, "dev", PASSWORD, perms={"code": "crud"})
    ws.seal(vault, admin)
    return tmp_path, vault, master_key


def _clone(tmp_path: Path, vault: Vault, name: str, user: str, master_key: str) -> Path:
    """A teammate's clone at another path: the vault, and no plaintext."""
    clone = tmp_path / name
    clone.mkdir()
    shutil.copytree(vault.dir, clone / vault.dir.name)
    theirs = Vault(clone)
    session = ws.login(theirs, crypto.parse_secret(MASTER_PREFIX, master_key, "k"), user, PASSWORD, "cli")
    ws.open_workspace(theirs, session)
    return clone


def test_the_vault_holds_the_key_only_encrypted(team):
    _tmp, vault, _key = team
    sealed = b"".join(p.read_bytes() for p in vault.dir.rglob("*") if p.is_file())
    assert BODY.encode() not in sealed and b"PRIVATE KEY" not in sealed and b"edge1" not in sealed


def test_an_account_with_read_on_servers_can_use_the_key_in_its_own_clone(team):
    tmp, vault, key = team
    clone = _clone(tmp, vault, "ops-clone", "ops", key)
    saved = srv.server_target(clone, "edge1")["identity_file"]
    assert saved == str(clone / ".pskit" / "ssh" / "keys" / "edge1.pem")
    assert Path(saved).read_text("ascii") == KEY


def test_an_account_without_it_gets_neither_the_key_nor_the_means_to_decrypt_it(team):
    tmp, vault, key = team
    clone = _clone(tmp, vault, "dev-clone", "dev", key)
    assert not (clone / ".pskit" / "ssh").exists() and srv.load_servers(clone) == {}
    theirs = Vault(clone)
    session = ws.login(theirs, crypto.parse_secret(MASTER_PREFIX, key, "k"), "dev", PASSWORD, "cli")
    assert "servers" not in theirs.area_keys(session.identity)


# ------------------------------------------------------------------------- defaults of a new server
@pytest.mark.parametrize(("user", "home"), [("ubuntu", "/home/ubuntu"), ("root", "/root")])
def test_defaults_of_a_new_server(user, home):
    assert srv.default_settings(user) == {"home": home, "data_dir": home, "bind": "0.0.0.0"}
    assert srv.server_settings(srv.default_settings(user)) == srv.default_settings(user)  # they pass validation


def _project(tmp_path: Path) -> None:
    (tmp_path / "pskit.yml").write_text("service: s\nprovider: {name: onprem}\nfunctions: {}\n")


def test_cli_servers_add_uses_the_defaults_and_keeps_what_was_asked(tmp_path, monkeypatch):
    _project(tmp_path)
    monkeypatch.chdir(tmp_path)
    run = CliRunner().invoke
    add = ["resources", "onprem", "servers", "add"]
    assert run(cli, [*add, "a", "--ssh", "azureuser@10.0.0.5", "--no-test"]).exit_code == 0
    assert run(cli, [*add, "b", "--ssh", "ubuntu@10.0.0.6", "--no-test", "--home", "/srv/x", "--bind", ""]).exit_code == 0
    servers = srv.load_servers(tmp_path)
    assert (servers["a"]["home"], servers["a"]["data_dir"], servers["a"]["bind"]) == (
        "/home/azureuser", "/home/azureuser", "0.0.0.0")
    assert servers["b"]["home"] == "/srv/x" and servers["b"]["data_dir"] == "/home/ubuntu" and "bind" not in servers["b"]


def test_cli_saves_key_text_from_a_variable_or_stdin(tmp_path, monkeypatch):
    _project(tmp_path)
    monkeypatch.chdir(tmp_path)
    run = CliRunner().invoke
    add = ["resources", "onprem", "servers", "add"]
    monkeypatch.setenv("EDGE_KEY", KEY.replace("\n", "\\n"))
    assert run(cli, [*add, "a", "--ssh", "u@h1", "--no-test", "--ssh-key-env", "EDGE_KEY"]).exit_code == 0
    assert run(cli, [*add, "b", "--ssh", "u@h2", "--no-test", "--ssh-key-stdin"], input=KEY).exit_code == 0
    for name in ("a", "b"):
        assert (tmp_path / ".pskit" / "ssh" / "keys" / f"{name}.pem").read_text("ascii") == KEY
    both = run(cli, [*add, "c", "--ssh", "u@h", "--no-test", "--ssh-key-env", "EDGE_KEY", "--ssh-key-stdin"])
    assert both.exit_code != 0 and "pick one" in both.output
    bad = run(cli, [*add, "d", "--ssh", "u@h", "--no-test", "--ssh-key-stdin"], input="ssh-rsa AAAA me")
    assert bad.exit_code != 0 and "public key" in bad.output
