"""On-premises deploys: a host on the network always has a token, and secrets are owner-only files."""

from __future__ import annotations

import json
import shlex
import stat
import sys
import tarfile

import pytest

from py_serverless_kit.core import onprem_terminal as term
from py_serverless_kit.core.deployer import Deployer
from py_serverless_kit.providers.onprem_remote import _pack_release, _ssh_apply_script, dockerfile_text

CONFIG = """
service: demo
provider:
  name: onprem
  stage: dev
  options:
    {options}
functions:
  hello:
    handler: app.handlers.hello
    events:
      - http: GET /hello
"""
HANDLERS = {"app/__init__.py": "", "app/handlers.py": "def hello(event, ctx):\n    return {}\n"}


def _deploy_files(make_project, options, **kwargs):
    project = make_project(CONFIG.format(options=options), files=HANDLERS, **kwargs)
    messages = []
    result = Deployer(project, echo=messages.append).package(skip_deps=True)
    root = project.work_dir / "onprem_app"
    return project, root, json.loads((root / "pskit_host.json").read_text("utf-8")), result, messages


def test_a_network_host_without_a_token_gets_a_stable_generated_one(make_project):
    project, _root, spec, _result, _msgs = _deploy_files(make_project, "{host: 0.0.0.0, port: 9090}")
    assert spec["host"] == "0.0.0.0" and len(spec["admin_token"]) >= 32
    saved = project.root / ".pskit" / "onprem-dev" / "admin-token"
    assert saved.read_text("utf-8") == spec["admin_token"]
    again = Deployer(project, echo=lambda _m: None).package(skip_deps=True)
    assert again.tf_file.is_file()
    rendered = json.loads((project.work_dir / "onprem_app" / "pskit_host.json").read_text("utf-8"))
    assert rendered["admin_token"] == spec["admin_token"], "a new token on every render would redeploy every time"


def test_docker_is_treated_as_a_network_host(make_project):
    _project, _root, spec, _result, _msgs = _deploy_files(make_project, "{port: 9090, deploy: {method: docker}}")
    assert spec["host"] == "0.0.0.0" and spec["admin_token"]


def test_a_loopback_host_stays_without_a_token(make_project):
    project, _root, spec, _result, _msgs = _deploy_files(make_project, "{host: 127.0.0.1, port: 9090}")
    assert spec["admin_token"] == ""
    assert not (project.root / ".pskit" / "onprem-dev" / "admin-token").exists()


def test_a_configured_token_is_kept(make_project):
    project, _root, spec, _result, _msgs = _deploy_files(make_project, "{host: 0.0.0.0, port: 9090, admin_token: mine}")
    assert spec["admin_token"] == "mine"
    assert not (project.root / ".pskit" / "onprem-dev" / "admin-token").exists()


@pytest.mark.skipif(sys.platform == "win32", reason="Windows has no POSIX file modes")
def test_secret_files_are_owner_only_on_disk(make_project):
    project, root, _spec, _result, _msgs = _deploy_files(make_project, "{host: 0.0.0.0, port: 9090}")
    for path in (root / "pskit_host.json", project.root / ".pskit" / "onprem-dev" / "admin-token"):
        assert stat.S_IMODE(path.stat().st_mode) == 0o600, path


def test_the_release_archive_marks_secrets_owner_only(tmp_path):
    (tmp_path / "pskit_host.json").write_text("{}", "utf-8")
    (tmp_path / "host.env").write_text("A=1\n", "utf-8")
    (tmp_path / "onprem_ctl.py").write_text("", "utf-8")
    archive = tmp_path / "release.tar.gz"
    _pack_release(tmp_path, archive)
    with tarfile.open(archive) as tar:
        modes = {m.name: stat.S_IMODE(m.mode) for m in tar.getmembers()}
    assert modes["pskit_host.json"] == 0o600 and modes["host.env"] == 0o600


def test_remote_install_and_images_tighten_secret_modes():
    script = _ssh_apply_script({"port": 8080, "deploy": {"ssh": {"path": "/opt/pskit"}}})
    assert 'chmod 600 "$REMOTE/pskit_host.json" "$REMOTE/host.env"' in script
    for text in (dockerfile_text("python3.12", 8080), dockerfile_text("python3.12", 8080, "nodejs22")):
        assert text.index("COPY pskit_host.json") < text.index("RUN chmod 600 pskit_host.json") < text.index("CMD")


# ----------------------------------------------------------------------------- browser terminals


def _terminal(tmp_path, monkeypatch, known=None, keys=True):
    home = tmp_path / "home"
    (home / ".ssh").mkdir(parents=True)
    if keys:
        (home / ".ssh" / "known_hosts").write_text("10.0.0.5 ssh-ed25519 AAAA\n", "utf-8")
    monkeypatch.setattr(term.Path, "home", classmethod(lambda _cls: home))
    target = {"user": "ubuntu", "host": "10.0.0.5", **({"known_hosts": known} if known else {})}
    mounts, prelude, ssh = term._ssh_parts(tmp_path, target)
    return mounts, prelude, ssh


def test_terminal_keeps_host_keys_so_a_changed_key_is_refused(tmp_path, monkeypatch):
    mounts, prelude, ssh = _terminal(tmp_path, monkeypatch)
    assert "rm -f /root/.ssh/known_hosts" not in prelude
    assert "StrictHostKeyChecking=accept-new" in ssh
    assert "UserKnownHostsFile=/pskit/hosts/known_hosts /pskit/my_known_hosts" in ssh
    # The file ssh adds to outlives the container: otherwise every connection would be a "first" one.
    folder = tmp_path.resolve() / ".pskit" / "terminal"
    assert folder.is_dir() and f"{folder}:/pskit/hosts" in mounts
    assert any(m.endswith(":/pskit/my_known_hosts:ro") for m in mounts)
    # Survives the shell quoting of the terminal's command line as one ssh argument.
    assert "UserKnownHostsFile=/pskit/hosts/known_hosts /pskit/my_known_hosts" in shlex.split(" ".join(shlex.quote(a) for a in ssh))


def test_terminal_works_without_a_personal_known_hosts_file(tmp_path, monkeypatch):
    mounts, _prelude, ssh = _terminal(tmp_path, monkeypatch, keys=False)
    assert "UserKnownHostsFile=/pskit/hosts/known_hosts" in ssh
    assert not any("my_known_hosts" in m for m in mounts)


def test_terminal_honours_a_pinned_known_hosts_file(tmp_path, monkeypatch):
    mounts, _prelude, ssh = _terminal(tmp_path, monkeypatch, known="/keys/pinned")
    assert "/keys/pinned:/pskit/known_hosts:ro" in mounts
    assert "StrictHostKeyChecking=yes" in ssh and "UserKnownHostsFile=/pskit/known_hosts" in ssh


def test_terminal_honours_an_explicit_ignore(tmp_path, monkeypatch):
    _mounts, _prelude, ssh = _terminal(tmp_path, monkeypatch, known="ignore")
    assert "StrictHostKeyChecking=no" in ssh

