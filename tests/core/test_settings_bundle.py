"""Export / import of the .pskit settings and secrets: encryption, path rewriting, SSH keys, merge and replace."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from click.testing import CliRunner

from py_serverless_kit.cli.main import cli
from py_serverless_kit.core import onprem_cluster as clu
from py_serverless_kit.core import onprem_servers as srv
from py_serverless_kit.core import onprem_services as svc
from py_serverless_kit.core import settings_bundle as bundle

PASS = "correct horse battery"


def _source(tmp_path: Path) -> Path:
    """A project with saved servers (agent, password, key outside the project), a cluster, a service and a deploy."""
    root = tmp_path / "laptop" / "shop"
    (root / ".pskit").mkdir(parents=True)
    keys = tmp_path / "home" / ".ssh"
    keys.mkdir(parents=True)
    (keys / "edge.pem").write_bytes(b"-----BEGIN OPENSSH PRIVATE KEY-----\nabc\n")
    srv.save_server(root, "edge1", {"host": "10.0.0.5", "user": "root", "identity_file": str(keys / "edge.pem")})
    srv.save_server(root, "edge2", {"host": "10.0.0.6", "user": "root", "auth": "password", "password": "s3cret!"})
    srv.save_server(root, "lb1", {"host": "10.0.0.9", "user": "root", "auth": "agent"})
    clusters = {"prod": {"orchestrator": "nomad", "master": "edge1", "advertise": "10.0.0.5",
                         "nodes": {"edge1": {"role": "master", "node": "n1", "address": "10.0.0.5"}},
                         "balancer": {"server": "lb1", "address": "10.0.0.9", "port": 80}}}
    clu._save(root, clusters)
    svc.save_state(root, {"services": {"cache": {"service": "redis", "password": "redis-pw",
                                                 "target": {"server": "edge2"}}}})
    stage = root / ".pskit" / "onprem-dev"
    stage.mkdir()
    (stage / "onprem_deployed.json").write_text(json.dumps(
        {"server": None, "cluster": "prod", "spec": {"admin_token": "tok", "data_dir": str(stage / "data")}}), "utf-8")
    (stage / "terraform.tfstate").write_text("{}", "utf-8")
    (root / ".env.prod").write_text("API_KEY=xyz\n", "utf-8")
    return root


def _export(root: Path, passphrase: str = PASS) -> str:
    text, _summary = bundle.export_settings(root, passphrase, env_files=[".env.prod"], pskit_version="2.1.0")
    return text


def test_round_trip_to_another_folder(tmp_path):
    source = _source(tmp_path)
    text = _export(source)
    assert "s3cret" not in text and "redis-pw" not in text and "BEGIN OPENSSH" not in text  # encrypted
    target = tmp_path / "server" / "work" / "shop"
    target.mkdir(parents=True)
    payload = bundle.decrypt(text, PASS)
    assert ".pskit/onprem-dev/terraform.tfstate" not in payload["files"]
    result = bundle.import_settings(target, payload)
    assert result["backup"] is None  # nothing to back up in an empty project

    servers = srv.load_servers(target)
    assert set(servers) == {"edge1", "edge2", "lb1"}
    key = Path(servers["edge1"]["identity_file"])
    assert key.parent == target.resolve() / ".pskit" / "ssh" / "keys"
    assert key.read_bytes().startswith(b"-----BEGIN OPENSSH")
    password = Path(servers["edge2"]["password_file"])
    assert password.parent == target.resolve() / ".pskit" / "ssh" and password.read_text("utf-8") == "s3cret!"
    if os.name != "nt":
        assert (key.stat().st_mode & 0o777) == 0o600
    assert clu.get_cluster(target, "prod")["balancer"]["server"] == "lb1"
    assert svc.load_state(target)["services"]["cache"]["password"] == "redis-pw"
    deployed = json.loads((target / ".pskit" / "onprem-dev" / "onprem_deployed.json").read_text("utf-8"))
    assert deployed["spec"]["data_dir"] == str(target.resolve() / ".pskit" / "onprem-dev" / "data")
    assert (target / ".env.prod").read_text("utf-8") == "API_KEY=xyz\n"

    again = _export(target)  # an imported project exports the same settings (keys now inside it)
    assert set(bundle.decrypt(again, PASS)["keys"]) == set()


def test_wrong_passphrase_and_changed_file_are_refused(tmp_path):
    text = _export(_source(tmp_path))
    with pytest.raises(bundle.SettingsError, match="wrong passphrase"):
        bundle.decrypt(text, "not the passphrase")
    doc = json.loads(text)
    doc["ciphertext"] = ("A" if doc["ciphertext"][0] != "A" else "B") + doc["ciphertext"][1:]
    with pytest.raises(bundle.SettingsError, match="wrong passphrase, or the settings file was changed"):
        bundle.decrypt(json.dumps(doc), PASS)
    with pytest.raises(bundle.SettingsError, match="not a pskit settings file"):
        bundle.decrypt('{"format": "other"}', PASS)
    with pytest.raises(bundle.SettingsError, match="at least 8"):
        bundle.export_settings(tmp_path, "short")


def test_merge_keeps_and_replace_drops_local_entries(tmp_path):
    payload = bundle.decrypt(_export(_source(tmp_path)), PASS)
    target = tmp_path / "other"
    (target / ".pskit").mkdir(parents=True)
    srv.save_server(target, "mine", {"host": "10.1.1.1", "user": "root", "auth": "agent"})
    srv.save_server(target, "edge1", {"host": "10.9.9.9", "user": "ops", "auth": "agent"})

    plan = bundle.preview(target, payload)
    assert plan["stores"]["onprem-servers.servers"] == {"add": ["edge2", "lb1"], "replace": ["edge1"], "keep": ["mine"]}
    result = bundle.import_settings(target, payload)
    assert set(srv.load_servers(target)) == {"mine", "edge1", "edge2", "lb1"}
    assert srv.load_servers(target)["edge1"]["host"] == "10.0.0.5"  # the imported entry wins
    backup = json.loads(Path(result["backup"]).read_text("utf-8"))
    assert "mine" in json.loads(backup["files"][".pskit/onprem-servers.json"]["json"])["servers"]

    replaced = bundle.preview(target, payload, replace=True)
    assert replaced["stores"]["onprem-servers.servers"]["remove"] == ["mine"]
    bundle.import_settings(target, payload, replace=True)
    assert set(srv.load_servers(target)) == {"edge1", "edge2", "lb1"}


def test_unsafe_paths_write_nothing(tmp_path):
    for rel in ("../evil.txt", "/etc/passwd", "C:/x.txt", ".pskit/../../x"):
        payload = {"format": bundle.FORMAT, "files": {rel: {"b64": "eA=="}}, "keys": {}}
        with pytest.raises(bundle.SettingsError, match="unsafe path"):
            bundle.import_settings(tmp_path / "p", payload)
    assert not (tmp_path / "evil.txt").exists() and not (tmp_path / "p").exists()


def test_cli_export_and_import(tmp_path, monkeypatch):
    source = _source(tmp_path)
    (source / "pskit.yml").write_text("service: shop\nprovider:\n  name: onprem\n  options:\n    env_file: .env.prod\n",
                                      "utf-8")
    monkeypatch.setenv("PSKIT_SETTINGS_PASSPHRASE", PASS)
    monkeypatch.chdir(source)
    out = CliRunner().invoke(cli, ["settings", "export"], catch_exceptions=False)
    assert out.exit_code == 0, out.output
    assert "onprem-servers.servers: edge1, edge2, lb1" in out.output and (source / "shop.pskit-settings").is_file()

    target = tmp_path / "fresh"
    target.mkdir()
    (target / "pskit.yml").write_text("service: shop\n", "utf-8")
    monkeypatch.chdir(target)
    dry = CliRunner().invoke(cli, ["settings", "import", str(source / "shop.pskit-settings"), "--dry-run"])
    assert dry.exit_code == 0 and "add      .pskit/onprem-servers.json" in dry.output
    assert not (target / ".pskit").exists()
    done = CliRunner().invoke(cli, ["settings", "import", str(source / "shop.pskit-settings"), "--yes"])
    assert done.exit_code == 0, done.output
    assert (target / ".env.prod").is_file() and set(srv.load_servers(target)) == {"edge1", "edge2", "lb1"}

    monkeypatch.setenv("PSKIT_SETTINGS_PASSPHRASE", "wrong passphrase")
    bad = CliRunner().invoke(cli, ["settings", "import", str(source / "shop.pskit-settings"), "--yes"])
    assert bad.exit_code == 1 and "wrong passphrase" in bad.output
