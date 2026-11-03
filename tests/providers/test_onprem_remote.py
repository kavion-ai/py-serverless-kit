"""Laptop-side on-prem apply/destroy: ssh, docker, and bundled CPython."""

from __future__ import annotations

import io
import json
import subprocess
import sys
import tarfile
from pathlib import Path
from types import SimpleNamespace

from py_serverless_kit.providers.onprem_remote import (
    DeployError,
    _ensure_python,
    _pack_release,
    apply_docker,
    apply_ssh,
    destroy_docker,
    destroy_ssh,
    dockerfile_text,
    extract_bundle_for_tests,
)
from py_serverless_kit.providers.onprem_spec import parse_deploy, python_bin_for, standalone_url


class _Proc:
    def __init__(self):
        self.calls = []

    def __call__(self, argv, **_kwargs):
        self.calls.append(list(argv))
        return subprocess.CompletedProcess(argv, 0, "", "")


def test_standalone_url_linux_x86():
    url = standalone_url("python3.12", "linux", "x86_64")
    assert "cpython-3.12.12+20251010-x86_64-unknown-linux-gnu-install_only.tar.gz" in url


def test_python_bin_bundle_linux():
    spec = parse_deploy(
        {"deploy": {"method": "ssh", "host": "10.0.0.1", "python": "bundle", "target_os": "linux"}},
        service="demo",
        stage="dev",
        runtime="python3.12",
        architecture="x86_64",
    )
    assert python_bin_for(spec, "/opt/pskit/demo") == "/opt/pskit/demo/python/bin/python3"


def test_apply_ssh_copies_and_starts(tmp_path: Path):
    root = tmp_path / "onprem_app"
    root.mkdir()
    (root / "onprem_ctl.py").write_text("print(1)\n", "utf-8")
    (root / "pskit_host.json").write_text("{}", "utf-8")
    staging = root / "staging"
    staging.mkdir()
    (staging / "app.py").write_text("x\n", "utf-8")
    spec = {
        "deploy": {
            "method": "ssh",
            "python": "system",
            "target_os": "linux",
            "target_arch": "x86_64",
            "runtime": "python3.12",
            "install": "process",
            "sudo": False,
            "ssh": {
                "host": "10.0.1.12",
                "user": "pskit",
                "port": 22,
                "identity_file": "",
                "known_hosts": "accept-new",
                "path": "/opt/pskit/demo",
            },
            "docker": {},
            "python_bundle": {},
        }
    }
    runner = _Proc()
    apply_ssh(root, spec, run=runner)
    assert any(c[0] == "ssh" and "mkdir -p" in " ".join(c) for c in runner.calls)
    assert any(c[0] == "scp" and "release.tar.gz" in " ".join(c) for c in runner.calls)
    assert any(c[0] == "ssh" and "remote_apply.sh" in " ".join(c) for c in runner.calls)
    script = (root / "remote_apply.sh").read_text(encoding="utf-8")
    assert "tar -xf" in script
    assert "rm -rf" in script and "staging" in script
    assert 'onprem_ctl.py" start' in script
    assert "sudo -n" in script or "SUDO=0" in script
    assert not (root / "release.tar.gz").exists()


def test_apply_ssh_systemd_restarts_and_checks_health(tmp_path: Path):
    root = tmp_path / "onprem_app"
    root.mkdir()
    (root / "onprem_ctl.py").write_text("print(1)\n", encoding="utf-8")
    (root / "pskit_host.json").write_text("{}\n", encoding="utf-8")
    (root / "pskit.service").write_text("[Service]\nExecStart=/opt/pskit/demo/pskit-run.sh\n", encoding="utf-8")
    (root / "staging").mkdir()
    spec = {
        "port": 9090,
        "unit_name": "pskit-demo-dev",
        "deploy": {
            "method": "ssh",
            "python": "system",
            "target_os": "linux",
            "runtime": "python3.12",
            "install": "systemd",
            "sudo": True,
            "ssh": {
                "host": "10.0.1.12",
                "user": "pskit",
                "port": 22,
                "identity_file": "",
                "known_hosts": "accept-new",
                "path": "/opt/pskit/demo",
            },
        },
    }
    runner = _Proc()
    apply_ssh(root, spec, run=runner)
    mkdir = next(" ".join(call) for call in runner.calls if call[0] == "ssh" and "mkdir -p" in " ".join(call))
    assert "sudo -n mkdir -p" in mkdir
    assert "sudo -n chown 'pskit'" in mkdir
    script = (root / "remote_apply.sh").read_text(encoding="utf-8")
    assert "systemctl restart" in script
    assert "systemctl enable" in script
    assert "http://127.0.0.1:9090/__pskit/health" in script
    assert "journalctl" in script
    assert "sudo -n" in script
    assert 'export PATH="$PATH:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"' in script


def test_release_archive_is_one_tree(tmp_path: Path):
    root = tmp_path / "onprem_app"
    root.mkdir()
    (root / "onprem_ctl.py").write_text("print(1)\n", encoding="utf-8")
    (root / "pskit-run.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    staging = root / "staging"
    staging.mkdir()
    (staging / "app.py").write_text("x\n", encoding="utf-8")
    dest = tmp_path / "release.tar.gz"
    _pack_release(root, dest)
    with tarfile.open(dest, "r:gz") as tar:
        names = set(tar.getnames())
    assert "onprem_ctl.py" in names
    assert "pskit-run.sh" in names
    assert "staging/app.py" in names or "staging\\app.py" in names
    assert not any("staging/staging" in name or "staging\\staging" in name for name in names)


def test_destroy_ssh_stops_systemd(tmp_path: Path):
    root = tmp_path / "onprem_app"
    root.mkdir()
    spec = {
        "unit_name": "pskit-demo-dev",
        "deploy": {
            "install": "systemd",
            "sudo": True,
            "runtime": "python3.12",
            "ssh": {"host": "10.0.1.12", "user": "pskit", "port": 22, "path": "/opt/pskit/demo"},
        },
    }
    runner = _Proc()
    destroy_ssh(root, spec, run=runner)
    script = (root / "remote_destroy.sh").read_text(encoding="utf-8")
    assert "systemctl disable --now" in script
    assert "apt-get" not in script
    assert any("remote_destroy.sh" in " ".join(c) for c in runner.calls)


def test_apply_docker_builds_and_runs(tmp_path: Path):
    root = tmp_path / "onprem_app"
    root.mkdir()
    spec = {
        "port": 8080,
        "deploy": {
            "method": "docker",
            "docker": {
                "image": "pskit-demo:dev",
                "container": "pskit-demo-dev",
                "host": "",
                "restart": "unless-stopped",
                "publish": "8080:8080",
                "args": [],
            },
        },
    }
    runner = _Proc()
    apply_docker(root, spec, run=runner)
    assert runner.calls[0][:4] == ["docker", "build", "-t", "pskit-demo:dev"]
    assert runner.calls[1][:3] == ["docker", "rm", "-f"]
    run = runner.calls[2]
    assert run[:3] == ["docker", "run", "-d"]
    assert "pskit-demo:dev" in run


def _remote_spec(pem: Path, *, install_docker: bool = True) -> dict:
    return {
        "port": 8080,
        "deploy": {
            "method": "docker",
            "sudo": True,
            "ssh": {
                "host": "10.0.1.12",
                "user": "pskit",
                "port": 22,
                "identity_file": str(pem),
                "known_hosts": "accept-new",
                "path": "/tmp/pskit-demo",
            },
            "docker": {
                "image": "pskit-demo:dev",
                "container": "pskit-demo-dev",
                "host": "",
                "restart": "unless-stopped",
                "publish": "8080:8080",
                "args": ["--memory", "256m"],
                "install_docker": install_docker,
            },
        },
    }


def test_apply_docker_remote_builds_locally_and_installs(tmp_path: Path):
    root = tmp_path / "onprem_app"
    root.mkdir()
    pem = tmp_path / "server.pem"
    pem.write_text("key\n", encoding="utf-8")
    runner = _Proc()
    apply_docker(root, _remote_spec(pem), run=runner)
    assert runner.calls[0][:4] == ["docker", "build", "-t", "pskit-demo:dev"]
    assert runner.calls[1][:3] == ["docker", "save", "-o"]
    assert runner.calls[1][-1] == "pskit-demo:dev"
    script = (root / "remote_docker.sh").read_text(encoding="utf-8")
    assert "apt-get install -y docker.io" in script
    assert "dnf install -y docker" in script
    assert "yum install -y docker" in script
    assert "apk add --no-cache docker" in script
    assert "command -v docker" in script
    assert "sudo -n" in script
    assert "dk load -i" in script
    assert "pskit-demo:dev" in script
    assert "--memory" in script
    assert "256m" in script
    assert "{{.State.Running}}" in script
    assert "http://127.0.0.1:8080/__pskit/health" in script
    assert any(
        c[0] == "scp" and "-i" in c and str(pem) in c and "IdentitiesOnly=yes" in c and "image.tar" in " ".join(c)
        for c in runner.calls
    )
    assert any(c[0] == "ssh" and "remote_docker.sh" in " ".join(c) for c in runner.calls)
    assert not (root / "image.tar").exists()


def test_apply_docker_remote_skips_install_when_disabled(tmp_path: Path):
    root = tmp_path / "onprem_app"
    root.mkdir()
    pem = tmp_path / "server.pem"
    pem.write_text("key\n", encoding="utf-8")
    runner = _Proc()
    apply_docker(root, _remote_spec(pem, install_docker=False), run=runner)
    script = (root / "remote_docker.sh").read_text(encoding="utf-8")
    assert "apt-get install" not in script
    assert "Docker is not installed on the server" in script


def test_apply_docker_remote_without_pem_uses_the_agent(tmp_path: Path):
    root = tmp_path / "onprem_app"
    root.mkdir()
    spec = _remote_spec(tmp_path / "missing.pem")
    spec["deploy"]["ssh"]["identity_file"] = ""
    proc = _Proc()
    apply_docker(root, spec, run=proc)
    ssh_calls = [c for c in proc.calls if c[0] in ("ssh", "scp")]
    assert ssh_calls and all("-i" not in c and "BatchMode=yes" in c for c in ssh_calls)


def test_missing_pem_file_is_an_error(tmp_path: Path):
    root = tmp_path / "onprem_app"
    root.mkdir()
    try:
        apply_docker(root, _remote_spec(tmp_path / "missing.pem"), run=_Proc())
    except DeployError as exc:
        assert "missing.pem" in str(exc)
    else:
        raise AssertionError("expected DeployError")


def test_password_login_goes_through_sshpass(tmp_path: Path, monkeypatch):
    from py_serverless_kit.providers import onprem_remote

    root = tmp_path / "onprem_app"
    root.mkdir()
    secret = tmp_path / "server.pass"
    secret.write_text("s3cret", "utf-8")
    spec = _remote_spec(tmp_path / "missing.pem")
    spec["deploy"]["ssh"].update({"identity_file": "", "password_file": str(secret)})
    monkeypatch.setattr(onprem_remote.shutil, "which", lambda name: "/usr/bin/" + name)
    proc = _Proc()
    apply_docker(root, spec, run=proc)
    remote = [c for c in proc.calls if c[0] == "sshpass"]
    assert remote and all(c[1:3] == ["-f", str(secret)] and c[3] in ("ssh", "scp") for c in remote)
    assert all("BatchMode=no" in c and "PubkeyAuthentication=no" in c for c in remote)
    assert not any(c[0] in ("ssh", "scp") for c in proc.calls)
    assert all("s3cret" not in " ".join(c) for c in proc.calls)


def test_password_login_needs_sshpass(tmp_path: Path, monkeypatch):
    from py_serverless_kit.providers import onprem_remote

    monkeypatch.setattr(onprem_remote.shutil, "which", lambda name: None)
    monkeypatch.setenv("SSHPASS", "x")
    problem = onprem_remote.ssh_auth_problem({"host": "h", "user": "u", "auth": "password"})
    assert problem and "sshpass" in problem and "ssh-key" in problem
    monkeypatch.delenv("SSHPASS")
    assert "SSHPASS" in (onprem_remote.ssh_auth_problem({"host": "h", "user": "u", "auth": "password"}) or "")


def test_destroy_docker_remote_does_not_install(tmp_path: Path):
    root = tmp_path / "onprem_app"
    root.mkdir()
    pem = tmp_path / "server.pem"
    pem.write_text("key\n", encoding="utf-8")
    runner = _Proc()
    destroy_docker(root, _remote_spec(pem), run=runner)
    script = (root / "remote_docker_destroy.sh").read_text(encoding="utf-8")
    assert "dk rm -f" in script
    assert "apt-get install" not in script
    assert any(c[0] == "ssh" and "remote_docker_destroy.sh" in " ".join(c) for c in runner.calls)


def test_parse_docker_pem_and_ssh_url():
    spec = parse_deploy(
        {"deploy": {"method": "docker", "host": "10.0.1.12", "user": "pskit", "pem": "keys/server.pem"}},
        service="demo",
        stage="dev",
        runtime="python3.12",
        architecture="x86_64",
    )
    assert spec.identity_file.replace("\\", "/").endswith("keys/server.pem")
    assert spec.install_docker is True
    assert spec.sudo is True
    assert spec.ssh_host == "10.0.1.12"
    via = parse_deploy(
        {"deploy": {"method": "docker", "docker_host": "ssh://ops@10.1.1.5:2222"}},
        service="demo",
        stage="dev",
        runtime="python3.12",
        architecture="x86_64",
    )
    assert via.ssh_host == "10.1.1.5"
    assert via.ssh_user == "ops"
    assert via.ssh_port == 2222
    assert via.install_docker is True
    local = parse_deploy(
        {"deploy": {"method": "docker", "image": "pskit-demo:dev"}},
        service="demo",
        stage="dev",
        runtime="python3.12",
        architecture="x86_64",
    )
    assert local.ssh_host == ""
    assert local.install_docker is False
    assert local.sudo is False


def test_dockerfile_uses_runtime():
    text = dockerfile_text("python3.11", 9090)
    assert "FROM python:3.11-slim-bookworm" in text
    assert "EXPOSE 9090" in text


def _standalone_archive(path: Path) -> None:
    long_name = (
        "python/lib/python3.10/site-packages/pkg_resources/tests/data/"
        "my-test-package_unpacked-egg/my_test_package-1.0-py3.7.egg/EGG-INFO"
    )
    body = b"#!/x\n"
    with tarfile.open(path, "w:gz") as tar:
        real = tarfile.TarInfo("python/bin/python3.12")
        real.size = len(body)
        real.mode = 0o755
        tar.addfile(real, io.BytesIO(body))
        link = tarfile.TarInfo("python/bin/python3")
        link.type = tarfile.SYMTYPE
        link.linkname = "python3.12"
        link.mode = 0o777
        tar.addfile(link)
        egg = tarfile.TarInfo(long_name)
        egg.size = 4
        tar.addfile(egg, io.BytesIO(b"egg\n"))


def test_extract_install_only_archive(tmp_path: Path):
    archive = tmp_path / "python.tgz"
    payload = tmp_path / "src"
    (payload / "python" / "bin").mkdir(parents=True)
    (payload / "python" / "bin" / "python3").write_text("#!/bin/sh\n", "utf-8")
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(payload / "python", arcname="python")
    dest = tmp_path / "out"
    python = extract_bundle_for_tests(archive, dest)
    assert (python / "bin" / "python3").is_file()


def test_extract_skips_setuptools_test_eggs(tmp_path: Path):
    archive = tmp_path / "python.tgz"
    _standalone_archive(archive)
    python = extract_bundle_for_tests(archive, tmp_path / "out")
    assert (python / "bin" / "python3.12").read_bytes() == b"#!/x\n"
    assert not (python / "lib").exists()


def test_windows_remote_bundle_is_streamed_into_the_release(tmp_path: Path, monkeypatch):
    archive = tmp_path / "cpython.tar.gz"
    _standalone_archive(archive)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(
        "py_serverless_kit.providers.onprem_remote._download",
        lambda _url, _sha: archive,
    )
    root = tmp_path / "onprem_app"
    root.mkdir()
    (root / "onprem_ctl.py").write_text("print(1)\n", encoding="utf-8")
    spec = {
        "deploy": {
            "method": "ssh",
            "python": "bundle",
            "target_os": "linux",
            "python_bundle": {"url": "https://example.invalid/cpython.tar.gz", "sha256": "", "home": ""},
        }
    }
    _ensure_python(root, spec)
    assert (root / "python" / ".pskit-from-archive").is_file()
    assert not (root / "python" / "lib").exists()
    dest = tmp_path / "release.tar.gz"
    _pack_release(root, dest)
    with tarfile.open(dest, "r:gz") as tar:
        names = set(tar.getnames())
        link = tar.getmember("python/bin/python3")
    assert "python/bin/python3.12" in names
    assert link.issym()
    assert link.linkname == "python3.12"
    assert not any("EGG-INFO" in name for name in names)
    assert not any(name.endswith(".pskit-from-archive") for name in names)


def test_parse_rejects_unsafe_host():
    try:
        parse_deploy(
            {"deploy": {"method": "ssh", "host": "10.0.0.1; rm -rf /"}},
            service="demo",
            stage="dev",
            runtime="python3.12",
            architecture="x86_64",
        )
    except ValueError as exc:
        assert "not safe" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_as_json_round_trip_bundle_url():
    spec = parse_deploy(
        {"deploy": {"method": "ssh", "host": "10.0.0.1", "python": "bundle"}},
        service="demo",
        stage="dev",
        runtime="python3.12",
        architecture="x86_64",
    )
    body = spec.as_json()
    assert "install_only.tar.gz" in body["python_bundle"]["url"]
    assert body["ssh"]["path"].startswith("/opt/pskit/")
    SimpleNamespace(**body["ssh"])
    json.dumps(body)
