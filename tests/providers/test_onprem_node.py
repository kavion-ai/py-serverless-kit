"""On-premises provider: Node.js services (deploy spec, validation, Dockerfile, bundled node)."""

from __future__ import annotations

import io
import json
import tarfile
import zipfile
from pathlib import Path

import pytest

from py_serverless_kit.providers.onprem_remote import (
    DeployError,
    _ensure_node,
    _pack_release,
    dockerfile_text,
    launcher_text,
)
from py_serverless_kit.providers.onprem_spec import node_dist_url, parse_deploy

NODE_CONFIG = """
service: nodedemo
provider:
  name: onprem
  runtime: nodejs20
  options:
    deploy: {deploy}
functions:
  hello:
    handler: src.handlers.hello
    events: [{{http: GET /hello}}]
"""


def _spec(deploy, runtime="nodejs20"):
    return parse_deploy({"deploy": deploy}, service="demo", stage="dev", runtime=runtime, architecture="x86_64")


def test_node_dist_url():
    assert node_dist_url("nodejs20", "linux", "arm64").endswith("/v20.19.5/node-v20.19.5-linux-arm64.tar.gz")
    assert node_dist_url("nodejs22", "windows", "x86_64").endswith("-win-x64.zip")
    assert node_dist_url("nodejs16", "linux", "x86_64") == ""


def test_node_service_keeps_a_python_host():
    spec = _spec({"method": "ssh", "host": "10.0.0.1", "node": "bundle", "python": "bundle"})
    data = spec.as_json()
    assert data["runtime"] == "python3.12"  # the host interpreter
    assert data["language"] == "node" and data["node"] == "bundle" and data["node_runtime"] == "nodejs20"
    assert data["node_bundle"]["url"].endswith("linux-x64.tar.gz")
    assert "python-build-standalone" in data["python_bundle"]["url"]
    pinned = _spec({"method": "ssh", "host": "h", "host_python": "python3.11", "node_url": "https://x/n.tar.gz"})
    assert pinned.runtime == "python3.11" and pinned.as_json()["node_bundle"]["url"] == "https://x/n.tar.gz"


def test_python_service_spec_is_unchanged():
    data = _spec({"method": "ssh", "host": "h"}, runtime="python3.12").as_json()
    assert "language" not in data and "node_bundle" not in data


@pytest.mark.parametrize(
    "deploy,message",
    [
        ({"node": "portable"}, "options.deploy.node"),
        ({"host_python": "python2.7"}, "options.deploy.host_python"),
    ],
)
def test_bad_node_options(deploy, message):
    with pytest.raises(ValueError, match=message):
        _spec(deploy)


def test_docker_uses_the_official_node_image():
    assert _spec({"method": "docker", "node": "bundle"}).node == "system"
    text = dockerfile_text("python3.12", 8080, "nodejs22")
    assert text.startswith("FROM node:22-bookworm-slim")
    assert "python3" in text and 'CMD ["python3", "onprem_ctl.py", "foreground"]' in text
    assert dockerfile_text("python3.12", 8080).startswith("FROM python:3.12-slim-bookworm")


def test_launcher_checks_for_node():
    assert "command -v node" in launcher_text("python3.12", node=True)
    assert "node" not in launcher_text("python3.12")


def _node_tar(path: Path, member: str) -> Path:
    with tarfile.open(path, "w:gz") as tar:
        payload = b"#!/bin/sh\necho node\n"
        info = tarfile.TarInfo(member)
        info.size = len(payload)
        tar.addfile(info, io.BytesIO(payload))
        link = tarfile.TarInfo("node-v20.19.5-linux-x64/bin/npm")
        link.type = tarfile.SYMTYPE
        link.linkname = "../lib/node_modules/npm/bin/npm-cli.js"
        tar.addfile(link)
    return path


def test_bundle_extracts_only_the_node_binary(tmp_path, monkeypatch):
    archive = _node_tar(tmp_path / "node.tar.gz", "node-v20.19.5-linux-x64/bin/node")
    monkeypatch.setattr("py_serverless_kit.providers.onprem_remote._download", lambda url, sha, folder="": archive)
    root = tmp_path / "app"
    root.mkdir()
    spec = {"deploy": {**_spec({"method": "ssh", "host": "h", "node": "bundle"}).as_json()}}
    binary = _ensure_node(root, spec)
    assert binary == root / "node" / "bin" / "node"
    assert binary.read_bytes().startswith(b"#!/bin/sh")
    assert not (root / "node" / "bin" / "npm").exists()
    # Cached by URL: a second apply does not download again.
    monkeypatch.setattr(
        "py_serverless_kit.providers.onprem_remote._download",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("downloaded twice")),
    )
    assert _ensure_node(root, spec) == binary
    # The release archive carries it, executable.
    (root / "pskit_host.json").write_text("{}", "utf-8")
    release = tmp_path / "release.tar.gz"
    _pack_release(root, release)
    with tarfile.open(release) as tar:
        member = tar.getmember("node/bin/node")
        assert member.mode & 0o111


def test_bundle_from_a_windows_zip(tmp_path, monkeypatch):
    archive = tmp_path / "node.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("node-v20.19.5-win-x64/node.exe", b"MZ")
    monkeypatch.setattr("py_serverless_kit.providers.onprem_remote._download", lambda url, sha, folder="": archive)
    root = tmp_path / "app"
    root.mkdir()
    deploy = _spec({"method": "ssh", "host": "h", "node": "bundle", "target_os": "windows"}).as_json()
    assert _ensure_node(root, {"deploy": deploy}) == root / "node" / "node.exe"


def test_local_system_node_must_be_on_path(tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)
    with pytest.raises(DeployError, match="needs `node` on PATH"):
        _ensure_node(tmp_path, {"deploy": _spec({}).as_json()})
    # Python services never look for node.
    assert _ensure_node(tmp_path, {"deploy": _spec({}, runtime="python3.12").as_json()}) is None


def test_validation_warns_about_missing_node(make_project, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)
    project = make_project(NODE_CONFIG.format(deploy="local"), files={"src/handlers.js": "exports.hello = () => 1;"})
    issues = project.validate()
    assert not [i for i in issues if i.level == "error" and "handler" not in i.where]
    assert any("node` on PATH" in i.message for i in issues if i.level == "warning")
    ssh = make_project(NODE_CONFIG.format(deploy="{method: ssh, host: 10.0.0.9}"))
    assert any("Node.js (nodejs20) on PATH" in i.message for i in ssh.validate())


def test_node_project_renders_a_node_host(make_project, render):
    from py_serverless_kit.packaging.builder import BuildError

    project = make_project(
        NODE_CONFIG.format(deploy="{method: docker}"),
        files={"src/handlers.js": "exports.hello = () => ({ok: true});", "package.json": json.dumps({"name": "n"})},
    )
    assert project.provider.shim_files(project.config) == {}
    assert project.provider.pip_platform_for(project.config) == []
    try:
        render(project)
    except BuildError as exc:  # the Node.js packaging step is not available on this machine
        pytest.skip(f"cannot package a Node.js project here: {exc}")
    root = project.work_dir / "onprem_app"
    spec = json.loads((root / "pskit_host.json").read_text("utf-8"))
    assert spec["language"] == "node" and spec["node_bin"] == "node"
    assert (root / "Dockerfile").read_text("utf-8").startswith("FROM node:20-bookworm-slim")
    # The Python host is always in the bundle, even when the builder ships only the JS runtime.
    assert (root / "staging" / "py_serverless_kit" / "runtime" / "onprem_host.py").is_file()
