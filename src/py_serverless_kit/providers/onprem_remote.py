"""Laptop-side apply/destroy for an on-premises host.

Terraform ``local-exec`` runs this with the same interpreter as ``pskit deploy``.
The target never needs pskit installed. ``python: bundle`` ships a portable
CPython; ``method: docker`` builds an image that already contains Python.

Remote SSH (``method: ssh`` or ``scp``) packs one ``release.tar.gz`` and copies
that file. A shell script on the server extracts it, restarts the process or
the systemd unit, and waits until ``/__pskit/health`` answers on loopback.
A remote Docker target builds the image on this machine, installs Docker on
the server when it is missing, copies the image with the ``.pem``, and waits
until the container is healthy.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence
from urllib.error import URLError
from urllib.request import Request, urlopen

from .onprem_spec import json_targets_remote_docker

_CACHE = Path(os.environ.get("PSKIT_CACHE_DIR") or (Path.home() / ".cache" / "pskit"))
RunFn = Callable[..., "subprocess.CompletedProcess[Any]"]


class DeployError(Exception):
    pass


def main(root: Path) -> int:
    action = sys.argv[1] if len(sys.argv) > 1 else "apply"
    spec_path = root / "pskit_host.json"
    if not spec_path.is_file():
        sys.stderr.write(f"missing {spec_path}\n")
        return 2
    import json

    spec = json.loads(spec_path.read_text("utf-8"))
    deploy = spec.get("deploy") or {}
    method = str(deploy.get("method") or "local")
    try:
        if method == "cluster" and action in ("apply", "destroy"):
            _cluster(root, spec, action)
            return 0
        if action == "apply":
            if method == "ssh":
                apply_ssh(root, spec)
            elif method == "docker":
                apply_docker(root, spec)
            else:
                apply_local(root, spec)
            return 0
        if action == "destroy":
            if method == "ssh":
                destroy_ssh(root, spec)
            elif method == "docker":
                destroy_docker(root, spec)
            else:
                destroy_local(root, spec)
            return 0
    except DeployError as exc:
        sys.stderr.write(str(exc) + "\n")
        return 1
    sys.stderr.write("usage: onprem_deploy.py [apply|destroy]\n")
    return 2


def _cluster(root: Path, spec: Dict[str, Any], action: str) -> None:
    """``provider.options.cluster``: Docker Swarm, Kubernetes (k3s) or Nomad on saved servers."""
    from ..core import onprem_cluster
    from ..core.onprem_services import ServiceError

    def emit(line: str) -> None:
        print(line, flush=True)

    try:
        if action == "apply":
            onprem_cluster.deploy(root, spec, emit)
        else:
            onprem_cluster.destroy(root, spec, emit)
    except (ServiceError, onprem_cluster.ClusterError, OSError) as exc:
        raise DeployError(f"cluster {action} failed: {exc}") from None


def apply_local(root: Path, spec: Dict[str, Any], *, run: Optional[RunFn] = None) -> None:
    py = _ensure_python(root, spec)
    _ensure_node(root, spec)
    _run([str(py), str(root / "onprem_ctl.py"), "start"], cwd=root, run=run)


def destroy_local(root: Path, spec: Dict[str, Any], *, run: Optional[RunFn] = None) -> None:
    py = _python_exe(root, spec, require_bundle=False)
    _run([str(py), str(root / "onprem_ctl.py"), "stop"], cwd=root, run=run, check=False)


def apply_ssh(root: Path, spec: Dict[str, Any], *, run: Optional[RunFn] = None) -> None:
    """Copy one archive with scp and start it from a script that runs on the server.

    A single ``release.tar.gz`` avoids the nested-directory redeploy that
    ``scp -r`` does when the destination already exists. The remote script
    restarts systemd (``enable --now`` leaves the old process running) and
    waits until ``/__pskit/health`` answers on the server's loopback.
    """
    deploy = spec["deploy"]
    ssh = deploy["ssh"]
    _check_identity(ssh)
    _ensure_python(root, spec)
    _ensure_node(root, spec)
    if not (root / "pskit-run.sh").is_file():
        _write_text(
            root / "pskit-run.sh",
            launcher_text(str(deploy.get("runtime") or "python3.12"), node=deploy.get("language") == "node"),
        )
    remote = str(ssh["path"])
    archive = root / "release.tar.gz"
    script_path = root / "remote_apply.sh"
    try:
        _pack_release(root, archive)
        _write_text(script_path, _ssh_apply_script(spec))
        _prepare_remote_dir(ssh, remote, sudo=bool(deploy.get("sudo")), run=run)
        _scp(ssh, archive, f"{remote}/release.tar.gz", run=run)
        _scp(ssh, script_path, f"{remote}/remote_apply.sh", run=run)
        _ssh(ssh, f"sh {_shq(remote + '/remote_apply.sh')}", run=run)
    finally:
        if archive.is_file():
            archive.unlink()


def destroy_ssh(root: Path, spec: Dict[str, Any], *, run: Optional[RunFn] = None) -> None:
    deploy = spec["deploy"]
    ssh = deploy["ssh"]
    remote = str(ssh["path"])
    script_path = root / "remote_destroy.sh"
    _write_text(script_path, _ssh_destroy_script(spec))
    _prepare_remote_dir(ssh, remote, sudo=bool(deploy.get("sudo")), run=run, check=False)
    _scp(ssh, script_path, f"{remote}/remote_destroy.sh", run=run, check=False)
    _ssh(ssh, f"sh {_shq(remote + '/remote_destroy.sh')}", run=run, check=False)


def apply_docker(root: Path, spec: Dict[str, Any], *, run: Optional[RunFn] = None) -> None:
    deploy = spec["deploy"]
    if json_targets_remote_docker(deploy):
        apply_docker_remote(root, spec, run=run)
        return
    docker = deploy["docker"]
    env = _docker_env(docker.get("host") or "")
    image = docker["image"]
    container = docker["container"]
    _run(["docker", "build", "-t", image, "."], cwd=root, run=run, env=env)
    _run(["docker", "rm", "-f", container], cwd=root, run=run, env=env, check=False)
    _run(_docker_run_argv(docker, spec), cwd=root, run=run, env=env)


def apply_docker_remote(root: Path, spec: Dict[str, Any], *, run: Optional[RunFn] = None) -> None:
    """Build on this machine, install Docker on the server if needed, then load and run.

    The server script is a file, copied with scp. Passing a multi-line script as
    the SSH command is unreliable from Windows OpenSSH, which re-quotes arguments.
    """
    deploy = spec["deploy"]
    docker = deploy["docker"]
    ssh = deploy["ssh"]
    image = str(docker["image"])
    _check_identity(ssh)
    _run(["docker", "build", "-t", image, "."], cwd=root, run=run)
    tar_path = root / "image.tar"
    try:
        _run(["docker", "save", "-o", str(tar_path), image], cwd=root, run=run)
        remote_tar = _remote_tar(str(docker["container"]))
        remote_dir = remote_tar.rsplit("/", 1)[0]
        script_path = root / "remote_docker.sh"
        _write_text(script_path, _docker_remote_script(docker, spec, remote_tar))
        _ssh(ssh, f"mkdir -p {_shq(remote_dir)}", run=run)
        _scp(ssh, tar_path, remote_tar, run=run)
        _scp(ssh, script_path, f"{remote_dir}/remote_docker.sh", run=run)
        _ssh(ssh, f"sh {_shq(remote_dir + '/remote_docker.sh')}", run=run)
    finally:
        if tar_path.is_file():
            tar_path.unlink()


def destroy_docker(root: Path, spec: Dict[str, Any], *, run: Optional[RunFn] = None) -> None:
    deploy = spec["deploy"]
    docker = deploy["docker"]
    if json_targets_remote_docker(deploy):
        ssh = deploy["ssh"]
        container = str(docker["container"])
        remote_tar = _remote_tar(container)
        remote_dir = remote_tar.rsplit("/", 1)[0]
        script_path = root / "remote_docker_destroy.sh"
        _write_text(script_path, _docker_shell_header() + f"dk rm -f {_shq(container)} || true\n")
        _ssh(ssh, f"mkdir -p {_shq(remote_dir)}", run=run, check=False)
        _scp(ssh, script_path, f"{remote_dir}/remote_docker_destroy.sh", run=run, check=False)
        _ssh(ssh, f"sh {_shq(remote_dir + '/remote_docker_destroy.sh')}", run=run, check=False)
        return
    env = _docker_env(docker.get("host") or "")
    _run(["docker", "rm", "-f", docker["container"]], cwd=root, run=run, env=env, check=False)


def _docker_run_argv(docker: Dict[str, Any], spec: Dict[str, Any]) -> List[str]:
    publish = str(docker.get("publish") or f"{spec.get('port') or 8080}:{spec.get('port') or 8080}")
    argv = [
        "docker",
        "run",
        "-d",
        "--name",
        str(docker["container"]),
        "--restart",
        str(docker.get("restart") or "unless-stopped"),
        "-p",
        publish,
        "-v",
        f"{docker['container']}-data:/var/pskit/data",
    ]
    argv.extend(str(item) for item in (docker.get("args") or []))
    argv.append(str(docker["image"]))
    return argv


def _remote_tar(container: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", container).strip("-") or "pskit"
    # Home-relative so the SSH user can write it, and so it is not a shared temp dir.
    return f"pskit-images/{slug}/image.tar"


def _shell_prelude() -> str:
    """PATH is often tiny on a non-login SSH session, so systemctl and python3 are missed: add the usual dirs after it."""
    return (
        "#!/bin/sh\n"
        "set -eu\n"
        'export PATH="$PATH:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"\n'
    )


def _docker_shell_header() -> str:
    return (
        _shell_prelude()
        + 'as_root() { if [ "$(id -u)" -eq 0 ]; then "$@"; else sudo -n "$@"; fi; }\n'
        + 'dk() { if docker info >/dev/null 2>&1; then docker "$@"; else as_root docker "$@"; fi; }\n'
    )


def _docker_install_block() -> str:
    return (
        "if ! command -v docker >/dev/null 2>&1; then\n"
        "  if command -v apt-get >/dev/null 2>&1; then\n"
        "    export DEBIAN_FRONTEND=noninteractive\n"
        "    as_root apt-get update\n"
        "    as_root apt-get install -y docker.io\n"
        "  elif command -v dnf >/dev/null 2>&1; then\n"
        "    as_root dnf install -y docker\n"
        "  elif command -v yum >/dev/null 2>&1; then\n"
        "    as_root yum install -y docker\n"
        "  elif command -v apk >/dev/null 2>&1; then\n"
        "    as_root apk add --no-cache docker\n"
        "    as_root rc-update add docker default 2>/dev/null || true\n"
        "  else\n"
        '    echo "pskit: Docker is not installed and this server has no apt-get, dnf, yum, or apk" >&2\n'
        "    exit 1\n"
        "  fi\n"
        "  if command -v systemctl >/dev/null 2>&1; then\n"
        "    as_root systemctl enable --now docker || as_root service docker start || true\n"
        "  elif command -v service >/dev/null 2>&1; then\n"
        "    as_root service docker start || true\n"
        "  fi\n"
        "fi\n"
    )


def _docker_ready_block() -> str:
    return (
        "if ! command -v docker >/dev/null 2>&1; then\n"
        '  echo "pskit: Docker is not installed on the server. Set options.deploy.install_docker: true or install it, then redeploy." >&2\n'
        "  exit 1\n"
        "fi\n"
        "ready=0\n"
        "i=0\n"
        'while [ "$i" -lt 30 ]; do\n'
        "  if dk info >/dev/null 2>&1; then\n"
        "    ready=1\n"
        "    break\n"
        "  fi\n"
        "  i=$((i + 1))\n"
        "  sleep 1\n"
        "done\n"
        'if [ "$ready" != "1" ]; then\n'
        '  echo "pskit: Docker is installed but the daemon did not become ready." >&2\n'
        "  exit 1\n"
        "fi\n"
    )


def _docker_remote_script(docker: Dict[str, Any], spec: Dict[str, Any], remote_tar: str) -> str:
    port = int(spec.get("port") or 8080)
    publish = str(docker.get("publish") or f"{port}:{port}")
    restart = str(docker.get("restart") or "unless-stopped")
    container = str(docker["container"])
    image = str(docker["image"])
    parts = [
        "dk",
        "run",
        "-d",
        "--name",
        _shq(container),
        "--restart",
        _shq(restart),
        "-p",
        _shq(publish),
        "-v",
        _shq(f"{container}-data:/var/pskit/data"),
    ]
    for item in docker.get("args") or []:
        parts.append(_shq(str(item)))
    parts.append(_shq(image))
    run = " ".join(parts)
    url = f"http://127.0.0.1:{port}/__pskit/health"
    code = "import sys, urllib.request; urllib.request.urlopen(sys.argv[1], timeout=2).read()"
    lines = [_docker_shell_header()]
    if bool(docker.get("install_docker", True)):
        lines.append(_docker_install_block())
    lines.append(_docker_ready_block())
    lines.append(f"dk load -i {_shq(remote_tar)}\n")
    lines.append(f"dk rm -f {_shq(container)} || true\n")
    lines.append(run + "\n")
    lines.append(f"rm -f {_shq(remote_tar)}\n")
    lines.append(
        "ok=0\n"
        "i=0\n"
        'while [ "$i" -lt 40 ]; do\n'
        f"  if dk exec {_shq(container)} python -c {_shq(code)} {_shq(url)} >/dev/null 2>&1; then\n"
        "    ok=1\n"
        "    break\n"
        "  fi\n"
        f"  running=$(dk inspect -f '{{{{.State.Running}}}}' {_shq(container)} 2>/dev/null || echo false)\n"
        '  if [ "$running" != "true" ]; then\n'
        f"    dk logs --tail 120 {_shq(container)} || true\n"
        '    echo "pskit: container exited before it became healthy" >&2\n'
        "    exit 1\n"
        "  fi\n"
        "  i=$((i + 1))\n"
        "  sleep 1\n"
        "done\n"
        'if [ "$ok" != "1" ]; then\n'
        f"  dk logs --tail 120 {_shq(container)} || true\n"
        f'  echo "pskit: container did not answer {url}" >&2\n'
        "  exit 1\n"
        "fi\n"
    )
    return "".join(lines)


def dockerfile_text(runtime: str, port: int, node_runtime: str = "") -> str:
    """The host image. Python services start from ``python:3.x-slim``.

    Node.js services start from the official ``node:NN-bookworm-slim`` image and add
    Debian's ``python3`` (3.11) for the host process: one apt package is smaller and
    simpler than downloading and verifying a Node.js build on top of the Python image.
    """
    from .onprem_spec import docker_base_image

    if node_runtime:
        return (
            f"FROM {docker_base_image(node_runtime)}\n"
            "RUN apt-get update \\\n"
            " && apt-get install -y --no-install-recommends python3 tzdata \\\n"
            " && rm -rf /var/lib/apt/lists/*\n"
            "WORKDIR /opt/pskit\n"
            "COPY staging/ /opt/pskit/app/\n"
            "COPY pskit_host.json onprem_ctl.py host.env* /opt/pskit/\n"
            "ENV PYTHONUNBUFFERED=1\n"
            f"EXPOSE {port}\n"
            'CMD ["python3", "onprem_ctl.py", "foreground"]\n'
        )
    base = docker_base_image(runtime)
    return (
        f"FROM {base}\n"
        "WORKDIR /opt/pskit\n"
        "COPY staging/ /opt/pskit/app/\n"
        "COPY pskit_host.json onprem_ctl.py host.env* /opt/pskit/\n"
        "ENV PYTHONUNBUFFERED=1\n"
        f"EXPOSE {port}\n"
        'CMD ["python", "onprem_ctl.py", "foreground"]\n'
    )


def launcher_text(runtime: str, node: bool = False) -> str:
    """Pick a bundled interpreter, then the configured Python, then ``python3``.

    Node.js services also need ``node``: a bundled ``./node/bin/node`` or one on PATH.
    """
    minor = runtime.replace("python", "").strip() or "3"
    preferred = f"python{minor}"
    node_check = ""
    if node:
        node_check = (
            'if [ ! -x ./node/bin/node ] && ! command -v node >/dev/null 2>&1; then\n'
            '  echo "pskit: no Node.js on this machine. Install it or redeploy with node: bundle." >&2\n'
            "  exit 1\n"
            "fi\n"
        )
    return (
        "#!/bin/sh\n"
        "set -eu\n"
        'cd "$(dirname "$0")"\n'
        + node_check
        +         'if [ -x ./python/bin/python3 ]; then\n'
        "  exec ./python/bin/python3 ./onprem_ctl.py foreground\n"
        "fi\n"
        'if [ -x ./python/python.exe ]; then\n'
        "  exec ./python/python.exe ./onprem_ctl.py foreground\n"
        "fi\n"
        f'if command -v {preferred} >/dev/null 2>&1; then\n'
        f"  exec {preferred} ./onprem_ctl.py foreground\n"
        "fi\n"
        'if command -v python3 >/dev/null 2>&1; then\n'
        "  exec python3 ./onprem_ctl.py foreground\n"
        "fi\n"
        'echo "pskit: no Python on this machine. Redeploy with python: bundle or method: docker." >&2\n'
        "exit 1\n"
    )


def systemd_unit_text(desc: str, remote_path: str, user: str) -> str:
    launch = remote_path.rstrip("/") + "/pskit-run.sh"
    return (
        "[Unit]\n"
        f"Description={desc}\n"
        "After=network-online.target\n"
        "Wants=network-online.target\n"
        "\n"
        "[Service]\n"
        "Type=simple\n"
        f"WorkingDirectory={remote_path}\n"
        f"ExecStart={launch}\n"
        "Restart=on-failure\n"
        "RestartSec=5\n"
        f"User={user}\n"
        "\n"
        "[Install]\n"
        "WantedBy=multi-user.target\n"
    )


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.replace("\r\n", "\n").encode("utf-8"))


def _tar_filter(info: tarfile.TarInfo) -> tarfile.TarInfo:
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    if info.name.endswith("pskit-run.sh") or info.name == "node/bin/node":
        info.mode = 0o755
    return info


def _pack_release(root: Path, dest: Path) -> None:
    """One archive: host files, the staged bundle, and a bundled interpreter when present."""
    if dest.exists():
        dest.unlink()
    with tarfile.open(dest, "w:gz") as tar:
        for name in ("pskit_host.json", "onprem_ctl.py", "pskit-run.sh", "pskit.service", "host.env"):
            path = root / name
            if path.is_file():
                tar.add(str(path), arcname=name, filter=_tar_filter)
        staging = root / "staging"
        if staging.is_dir():
            tar.add(str(staging), arcname="staging", filter=_tar_filter)
        _pack_python(tar, root / "python")
        node_dir = root / "node"
        if node_dir.is_dir():
            tar.add(str(node_dir), arcname="node", filter=_tar_filter)


def _pack_python(tar: tarfile.TarFile, python_dir: Path) -> None:
    """Copy a bundled interpreter into the release archive.

    On Windows a Linux ``install_only`` tree contains setuptools test eggs whose
    paths exceed ``MAX_PATH`` (WinError 206). Those files are not unpacked on
    the laptop: the downloaded tarball is streamed in, minus ``site-packages``
    test data.
    """
    marker = python_dir / ".pskit-from-archive"
    if marker.is_file():
        archive = Path(marker.read_text("utf-8").strip())
        if not archive.is_file():
            raise DeployError(f"bundled CPython archive is missing: {archive}")
        _add_standalone_archive(tar, archive)
        return
    if python_dir.is_dir():
        tar.add(str(python_dir), arcname="python", filter=_tar_filter)


def _preferred_python(runtime: str) -> str:
    minor = runtime.replace("python", "").strip() or "3"
    return f"python{minor}"


def _as_root_function(sudo: bool) -> str:
    flag = "1" if sudo else "0"
    return (
        f"SUDO={flag}\n"
        "as_root() {\n"
        '  if [ "$SUDO" = "1" ] && [ "$(id -u)" -ne 0 ]; then\n'
        '    sudo -n "$@"\n'
        "  else\n"
        '    "$@"\n'
        "  fi\n"
        "}\n"
    )


def _pick_python_function(remote: str, runtime: str) -> str:
    preferred = _preferred_python(runtime)
    return (
        "pick_python() {\n"
        f'  if [ -x {_shq(remote + "/python/bin/python3")} ]; then\n'
        f"    printf '%s\\n' {_shq(remote + '/python/bin/python3')}\n"
        "    return 0\n"
        "  fi\n"
        f"  if command -v {_shq(preferred)} >/dev/null 2>&1; then\n"
        f"    command -v {_shq(preferred)}\n"
        "    return 0\n"
        "  fi\n"
        "  if command -v python3 >/dev/null 2>&1; then\n"
        "    command -v python3\n"
        "    return 0\n"
        "  fi\n"
        '  echo "pskit: no Python on this machine. Redeploy with python: bundle or method: docker." >&2\n'
        "  return 1\n"
        "}\n"
    )


def _ssh_apply_script(spec: Dict[str, Any]) -> str:
    deploy = spec["deploy"]
    ssh = deploy["ssh"]
    remote = str(ssh["path"])
    port = int(spec.get("port") or 8080)
    unit = str(spec.get("unit_name") or "pskit-host")
    install = str(deploy.get("install") or "process")
    runtime = str(deploy.get("runtime") or "python3.12")
    url = f"http://127.0.0.1:{port}/__pskit/health"
    code = "import sys, urllib.request; urllib.request.urlopen(sys.argv[1], timeout=2).read()"
    body = (
        _shell_prelude()
        + f"REMOTE={_shq(remote)}\n"
        + f"PORT={port}\n"
        + f"UNIT={_shq(unit)}\n"
        + f"INSTALL={_shq(install)}\n"
        + _as_root_function(bool(deploy.get("sudo")))
        + _pick_python_function(remote, runtime)
        + 'mkdir -p "$REMOTE"\n'
        + 'rm -rf "$REMOTE/staging" "$REMOTE/python" "$REMOTE/node"\n'
        + 'tar -xf "$REMOTE/release.tar.gz" -C "$REMOTE"\n'
        + 'rm -f "$REMOTE/release.tar.gz"\n'
        + 'chmod 755 "$REMOTE/pskit-run.sh" 2>/dev/null || true\n'
        + 'if [ "$INSTALL" = "systemd" ]; then\n'
        + "  if ! command -v systemctl >/dev/null 2>&1; then\n"
        + '    echo "pskit: systemd is not on this server. Set options.deploy.install: process." >&2\n'
        + "    exit 1\n"
        + "  fi\n"
        + '  as_root cp "$REMOTE/pskit.service" "/etc/systemd/system/${UNIT}.service"\n'
        + "  as_root systemctl daemon-reload\n"
        + '  as_root systemctl enable "$UNIT"\n'
        + '  as_root systemctl restart "$UNIT"\n'
        + "  ok=0\n"
        + "  i=0\n"
        + '  while [ "$i" -lt 40 ]; do\n'
        + '    py="$(pick_python)"\n'
        + f"    if \"$py\" -c {_shq(code)} {_shq(url)} >/dev/null 2>&1; then\n"
        + "      ok=1\n"
        + "      break\n"
        + "    fi\n"
        + "    i=$((i + 1))\n"
        + "    sleep 1\n"
        + "  done\n"
        + '  if [ "$ok" != "1" ]; then\n'
        + f'    echo "pskit: host did not answer {url}" >&2\n'
        + '    as_root systemctl status "$UNIT" --no-pager || true\n'
        + '    as_root journalctl -u "$UNIT" -n 120 --no-pager || true\n'
        + "    exit 1\n"
        + "  fi\n"
        + "else\n"
        + '  py="$(pick_python)"\n'
        + '  "$py" "$REMOTE/onprem_ctl.py" start\n'
        + "fi\n"
    )
    return body


def _ssh_destroy_script(spec: Dict[str, Any]) -> str:
    deploy = spec["deploy"]
    ssh = deploy["ssh"]
    remote = str(ssh["path"])
    unit = str(spec.get("unit_name") or "pskit-host")
    install = str(deploy.get("install") or "process")
    runtime = str(deploy.get("runtime") or "python3.12")
    return (
        _shell_prelude()
        + f"REMOTE={_shq(remote)}\n"
        + f"UNIT={_shq(unit)}\n"
        + f"INSTALL={_shq(install)}\n"
        + _as_root_function(bool(deploy.get("sudo")))
        + _pick_python_function(remote, runtime)
        + 'if [ "$INSTALL" = "systemd" ]; then\n'
        + '  as_root systemctl disable --now "$UNIT" || true\n'
        + "else\n"
        + '  py="$(pick_python)" || exit 0\n'
        + '  "$py" "$REMOTE/onprem_ctl.py" stop || true\n'
        + "fi\n"
    )


def _python_exe(root: Path, spec: Dict[str, Any], *, require_bundle: bool) -> Path:
    deploy = spec.get("deploy") or {}
    if deploy.get("python") == "bundle":
        exe = root / "python" / ("python.exe" if (deploy.get("target_os") == "windows") else Path("bin") / "python3")
        if exe.is_file():
            return exe
        if require_bundle:
            raise DeployError(f"bundled interpreter missing at {exe}")
    return Path(sys.executable)


def _ensure_python(root: Path, spec: Dict[str, Any]) -> Path:
    deploy = spec.get("deploy") or {}
    if deploy.get("python") != "bundle":
        return Path(sys.executable) if deploy.get("method") == "local" else _python_exe(root, spec, require_bundle=False)
    dest = root / "python"
    marker = dest / ".pskit-python"
    bundle = deploy.get("python_bundle") or {}
    home = str(bundle.get("home") or "")
    url = str(bundle.get("url") or "")
    sha = str(bundle.get("sha256") or "")
    if dest.is_dir() and marker.is_file() and marker.read_text("utf-8").strip() in (url, home, "ok"):
        if (dest / ".pskit-from-archive").is_file():
            return dest / "bin" / "python3"
        return _python_exe(root, spec, require_bundle=True)
    if dest.exists():
        _rmtree(dest)
    if home:
        src = Path(home)
        if not src.is_dir():
            raise DeployError(f"options.deploy.python_home {home!r} is not a directory")
        shutil.copytree(src, dest)
        marker.write_text(home, "utf-8")
        return _python_exe(root, spec, require_bundle=True)
    if not url:
        raise DeployError("python: bundle needs options.deploy.python_url or python_home")
    archive = _download(url, sha)
    if _stream_bundle(spec):
        # The interpreter runs on the server. Writing it under the project on
        # Windows hits MAX_PATH inside setuptools' test data.
        dest.mkdir(parents=True)
        (dest / ".pskit-from-archive").write_bytes(str(archive).encode("utf-8"))
        marker.write_text(url, "utf-8")
        return dest / "bin" / "python3"
    dest.mkdir(parents=True)
    with tarfile.open(archive, "r:*") as tar:
        _extract_tar(tar, dest.parent)
    extracted = dest.parent / "python"
    if extracted.resolve() != dest.resolve() and extracted.is_dir():
        if dest.exists():
            shutil.rmtree(dest)
        extracted.rename(dest)
    if not dest.is_dir():
        raise DeployError(f"bundle at {url} did not contain a python/ directory")
    marker.write_text(url, "utf-8")
    return _python_exe(root, spec, require_bundle=True)


def node_bin_rel(target_os: str) -> str:
    """Where a bundled ``node`` lives in the host root."""
    return "node/node.exe" if target_os == "windows" else "node/bin/node"


def _ensure_node(root: Path, spec: Dict[str, Any]) -> Optional[Path]:
    """Node.js services: copy or download the ``node`` binary for ``node: bundle``; check PATH otherwise."""
    deploy = spec.get("deploy") or {}
    if deploy.get("language") != "node":
        return None
    method = str(deploy.get("method") or "local")
    if deploy.get("node") != "bundle":
        if method == "local" and shutil.which("node") is None:
            raise DeployError(
                "this Node.js service needs `node` on PATH (https://nodejs.org/en/download). "
                "Or set options.deploy.node: bundle to download it."
            )
        return None
    target_os = str(deploy.get("target_os") or "linux")
    dest = root / node_bin_rel(target_os)
    bundle = deploy.get("node_bundle") or {}
    home = str(bundle.get("home") or "")
    url = str(bundle.get("url") or "")
    marker = root / "node" / ".pskit-node"
    if dest.is_file() and marker.is_file() and marker.read_text("utf-8").strip() in (url, home):
        return dest
    if (root / "node").exists():
        _rmtree(root / "node")
    dest.parent.mkdir(parents=True, exist_ok=True)
    if home:
        src = Path(home)
        exe = src / ("node.exe" if target_os == "windows" else Path("bin") / "node")
        if not exe.is_file():
            raise DeployError(f"options.deploy.node_home {home!r} has no {exe.relative_to(src).as_posix()}")
        shutil.copy2(exe, dest)
    else:
        if not url:
            raise DeployError("node: bundle needs options.deploy.node_url or node_home")
        archive = _download(url, str(bundle.get("sha256") or ""), folder="nodejs")
        _extract_node_binary(archive, dest, windows=target_os == "windows")
    if target_os != "windows":
        os.chmod(dest, 0o755)  # noqa: S103 - an executable, like the bundled CPython
    marker.write_text(home or url, "utf-8")
    return dest


def _extract_node_binary(archive: Path, dest: Path, *, windows: bool) -> None:
    """Only the ``node`` executable: it is self-contained (npm and its symlinks are not needed)."""
    want = "node.exe" if windows else "bin/node"
    if archive.name.endswith(".zip"):
        with zipfile.ZipFile(archive) as zf:
            for name in zf.namelist():
                if name.replace("\\", "/").split("/", 1)[-1] == want:
                    with zf.open(name) as src, open(dest, "wb") as out:
                        shutil.copyfileobj(src, out)
                    return
    else:
        with tarfile.open(archive, "r:*") as tar:
            for member in tar.getmembers():
                rel = _member_rel(member.name) or ""
                if member.isfile() and rel.split("/", 1)[-1] == want:
                    payload = tar.extractfile(member)
                    if payload is not None:
                        with open(dest, "wb") as out:
                            shutil.copyfileobj(payload, out)
                        return
    raise DeployError(f"{archive.name} does not contain {want}")


def _download(url: str, sha256: str, folder: str = "python-standalone") -> Path:
    _CACHE.mkdir(parents=True, exist_ok=True)
    name = url.rstrip("/").rsplit("/", 1)[-1] or "python.tgz"
    path = _CACHE / folder / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file() and (not sha256 or _sha256(path) == sha256.lower()):
        return path
    req = Request(url, headers={"User-Agent": "py-serverless-kit"})  # noqa: S310 - URL from config
    try:
        with urlopen(req, timeout=120) as resp:  # noqa: S310
            data = resp.read()
    except (URLError, OSError, TimeoutError) as exc:
        what = "Node.js" if folder == "nodejs" else "CPython"
        hint = "node_home" if folder == "nodejs" else "python_home"
        raise DeployError(
            f"could not download bundled {what} from {url}: {exc}. "
            f"Set options.deploy.{hint} to a local copy, or use method: docker."
        ) from exc
    if sha256 and hashlib.sha256(data).hexdigest() != sha256.lower():
        raise DeployError(f"sha256 mismatch for {url}")
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)
    return path


def _stream_bundle(spec: Dict[str, Any]) -> bool:
    """True when the bundle is for another OS and this machine is Windows."""
    if sys.platform != "win32":
        return False
    deploy = spec.get("deploy") or {}
    if str(deploy.get("method") or "local") == "local":
        return False
    return str(deploy.get("target_os") or "") != "windows"


def _member_rel(name: str) -> Optional[str]:
    text = name.replace("\\", "/").strip()
    if not text or text.startswith("/"):
        return None
    parts = []
    for part in text.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            return None
        parts.append(part)
    if not parts:
        return None
    return "/".join(parts)


def _skip_bundle_member(rel: str) -> bool:
    """setuptools and pkg_resources ship test eggs whose paths exceed MAX_PATH."""
    parts = rel.split("/")
    if "site-packages" not in parts:
        return False
    return "tests" in parts


def _safe_link(link: str) -> bool:
    text = link.replace("\\", "/")
    if text.startswith("/") or (len(text) >= 2 and text[1] == ":"):
        return False
    return ".." not in text.split("/")


def _extended_path(path: Path) -> str:
    text = os.path.abspath(str(path))
    if text.startswith("\\\\?\\"):
        return text
    if text.startswith("\\\\"):
        return "\\\\?\\UNC\\" + text.lstrip("\\")
    return "\\\\?\\" + text


def _fs_path(dest: Path, rel: str) -> str:
    full = dest.joinpath(*rel.split("/"))
    if sys.platform == "win32":
        return _extended_path(full)
    return str(full)


def _rmtree(path: Path) -> None:
    target = _extended_path(path) if sys.platform == "win32" else str(path)
    if not os.path.exists(target):
        return

    def _onerror(func, failed, _exc):  # noqa: ANN001
        os.chmod(failed, 0o700)
        func(failed)

    shutil.rmtree(target, onerror=_onerror)


def _extract_tar(tar: tarfile.TarFile, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for member in tar.getmembers():
        rel = _member_rel(member.name)
        if rel is None or _skip_bundle_member(rel):
            continue
        if member.issym() or member.islnk():
            if _safe_link(member.linkname):
                _extract_link(dest, rel, member.linkname, symlink=member.issym())
            continue
        if member.isdir():
            os.makedirs(_fs_path(dest, rel), exist_ok=True)
            continue
        if not member.isfile():
            continue
        parent = rel.rsplit("/", 1)[0] if "/" in rel else ""
        if parent:
            os.makedirs(_fs_path(dest, parent), exist_ok=True)
        src = tar.extractfile(member)
        if src is None:
            continue
        target = _fs_path(dest, rel)
        with open(target, "wb") as out:  # noqa: SIM115
            shutil.copyfileobj(src, out)
        if member.mode:
            try:
                os.chmod(target, member.mode)
            except OSError:
                pass


def _extract_link(dest: Path, rel: str, linkname: str, *, symlink: bool) -> None:
    parent = rel.rsplit("/", 1)[0] if "/" in rel else ""
    if parent:
        os.makedirs(_fs_path(dest, parent), exist_ok=True)
    target = _fs_path(dest, rel)
    if os.path.lexists(target):
        os.unlink(target)
    try:
        if symlink:
            os.symlink(linkname, target)
        else:
            os.link(_fs_path(dest, _member_rel(linkname) or linkname), target)
    except OSError:
        # Windows often refuses symlinks without extra privileges. The Linux
        # target still receives the link, because remote bundles are streamed.
        return


def _add_standalone_archive(tar: tarfile.TarFile, archive: Path) -> None:
    with tarfile.open(archive, "r:*") as src:
        for member in src.getmembers():
            rel = _member_rel(member.name)
            if rel is None or not rel.startswith("python/") or _skip_bundle_member(rel):
                continue
            cloned = tarfile.TarInfo(rel)
            cloned.mtime = member.mtime
            cloned.mode = member.mode or 0o644
            cloned.uid = 0
            cloned.gid = 0
            cloned.uname = ""
            cloned.gname = ""
            if member.isdir():
                cloned.type = tarfile.DIRTYPE
                tar.addfile(cloned)
                continue
            if member.issym() or member.islnk():
                if not _safe_link(member.linkname):
                    continue
                cloned.type = tarfile.SYMTYPE if member.issym() else tarfile.LNKTYPE
                cloned.linkname = member.linkname
                tar.addfile(cloned)
                continue
            if not member.isfile():
                continue
            cloned.size = member.size
            cloned.type = tarfile.REGTYPE
            payload = src.extractfile(member)
            if payload is None:
                continue
            tar.addfile(cloned, payload)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _docker_env(host: str) -> Dict[str, str]:
    env = dict(os.environ)
    if host:
        env["DOCKER_HOST"] = host
    return env


def _prepare_remote_dir(
    ssh: Dict[str, Any],
    remote: str,
    *,
    sudo: bool,
    run: Optional[RunFn],
    check: bool = True,
) -> None:
    """Create the install directory as a user who can write it.

    ``azureuser`` can log in and use sudo, and cannot create ``/opt/pskit``.
    ``sudo mkdir`` plus ``chown`` lets the later ``scp`` run as that user.
    """
    user = str(ssh.get("user") or "")
    quoted = _shq(remote)
    if sudo and user and user != "root":
        command = f"sudo -n mkdir -p {quoted} && sudo -n chown {_shq(user)} {quoted}"
    else:
        command = f"mkdir -p {quoted}"
    _ssh(ssh, command, run=run, check=check)


def _check_identity(ssh: Dict[str, Any], *, required: bool = False) -> None:
    """Check the SSH login before a deploy: a key file, a password (``sshpass``), or the agent/default key.

    ``required`` is kept for callers; an empty key now means the SSH agent or ``~/.ssh/id_*``.
    """
    problem = ssh_auth_problem(ssh)
    if problem:
        raise DeployError(problem)


def uses_password(ssh: Dict[str, Any]) -> bool:
    return bool(ssh.get("password_file")) or str(ssh.get("auth") or "") == "password"


def ssh_auth_problem(ssh: Dict[str, Any]) -> Optional[str]:
    """Why this SSH login cannot work from here, or None."""
    identity = str(ssh.get("identity_file") or "")
    if identity and not os.path.isfile(identity):
        return f"SSH private key not found: {identity}"
    if not uses_password(ssh):
        return None
    password_file = str(ssh.get("password_file") or "")
    if password_file and not os.path.isfile(password_file):
        return f"SSH password file not found: {password_file}"
    if not password_file and not os.environ.get("SSHPASS"):
        return "SSH password login: set the SSHPASS environment variable, or options.deploy.password_file"
    if not shutil.which("sshpass"):
        return (
            "SSH password login uses sshpass, which is not installed on this machine "
            "(Linux: apt install sshpass / dnf install sshpass; macOS: brew install hudochenkov/sshpass/sshpass). "
            "On Windows, or to stop using the password: run `pskit resources onprem ssh-key user@host` once "
            "(it asks the password one time and installs a key), then use that key."
        )
    return None


def _sshpass(ssh: Dict[str, Any]) -> List[str]:
    """``sshpass`` in front of ssh/scp when the server takes a password (never on the command line)."""
    if not uses_password(ssh):
        return []
    password_file = str(ssh.get("password_file") or "")
    return ["sshpass", "-f", password_file] if password_file else ["sshpass", "-e"]


def _ssh_options(ssh: Dict[str, Any], *, port_flag: str) -> List[str]:
    password = uses_password(ssh)
    argv = [
        "-o",
        # sshpass answers the password prompt, which BatchMode would switch off.
        "BatchMode=no" if password else "BatchMode=yes",
        "-o",
        "ConnectTimeout=20",
        "-o",
        "ServerAliveInterval=15",
        port_flag,
        str(ssh.get("port") or 22),
    ]
    identity = str(ssh.get("identity_file") or "")
    if password:
        argv.extend(["-o", "PreferredAuthentications=password,keyboard-interactive", "-o", "PubkeyAuthentication=no",
                     "-o", "NumberOfPasswordPrompts=1"])
    elif identity:
        # Do not offer other keys. A wrong default key makes the server close the connection.
        argv.extend(["-i", identity, "-o", "IdentitiesOnly=yes"])
    known = str(ssh.get("known_hosts") or "accept-new")
    if known == "accept-new":
        argv.extend(["-o", "StrictHostKeyChecking=accept-new"])
    elif known == "ignore":
        null = "NUL" if sys.platform == "win32" else "/dev/null"
        argv.extend(["-o", "StrictHostKeyChecking=no", "-o", f"UserKnownHostsFile={null}"])
    elif known:
        argv.extend(["-o", f"UserKnownHostsFile={known}", "-o", "StrictHostKeyChecking=yes"])
    return argv


def _ssh_base(ssh: Dict[str, Any]) -> List[str]:
    return [*_sshpass(ssh), "ssh", *_ssh_options(ssh, port_flag="-p")]


def scp_argv(ssh: Dict[str, Any], src: str, dest: str) -> List[str]:
    return [*_sshpass(ssh), "scp", *_ssh_options(ssh, port_flag="-P"), src, f"{_target(ssh)}:{dest}"]


def _target(ssh: Dict[str, Any]) -> str:
    return f"{ssh['user']}@{ssh['host']}"


def _ssh(ssh: Dict[str, Any], command: str, *, run: Optional[RunFn], check: bool = True) -> None:
    argv = _ssh_base(ssh) + [_target(ssh), command]
    _run(argv, run=run, check=check)


def _scp(ssh: Dict[str, Any], src: Path, dest: str, *, run: Optional[RunFn], check: bool = True) -> None:
    _run(scp_argv(ssh, str(src), dest), run=run, check=check)


def _shq(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def _run(
    argv: Sequence[str],
    *,
    cwd: Optional[Path] = None,
    run: Optional[RunFn] = None,
    env: Optional[Dict[str, str]] = None,
    check: bool = True,
) -> None:
    fn = run or subprocess.run
    try:
        proc = fn(list(argv), cwd=str(cwd) if cwd else None, env=env, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise DeployError(f"command not found: {argv[0]}. Install it on this machine and retry.") from exc
    code = int(proc.returncode or 0)
    if check and code:
        err = _annotate_ssh_error(list(argv), str(proc.stderr or proc.stdout or "")[-4000:])
        raise DeployError(f"command failed ({code}): {' '.join(argv)}\n{err}")


def _annotate_ssh_error(argv: Sequence[str], err: str) -> str:
    if argv and argv[0] == "sshpass":
        if "permission denied" in err.lower():
            return err + "\nThe server rejected the SSH password: check the user, the password, and that the server allows "
            "PasswordAuthentication (many cloud images only accept keys)."
        return err
    if not argv or argv[0] not in ("ssh", "scp"):
        return err
    lowered = err.lower()
    extra = ""
    if "unprotected private key" in lowered or "permissions are too open" in lowered or "bad permissions" in lowered:
        extra += (
            "\nThe .pem is too open for OpenSSH. "
            "On Linux or macOS run: chmod 600 /path/to/key.pem. "
            'On Windows run: icacls C:\\path\\to\\key.pem /inheritance:r /grant:r "%USERNAME%:R"'
        )
    if "permission denied" in lowered and "publickey" in lowered:
        extra += (
            "\nSSH rejected the key. Check options.deploy.pem (or identity_file), the user, "
            "and that the matching public key is in authorized_keys on the server."
        )
    if "a password is required" in lowered or "a terminal is required to read the password" in lowered:
        extra += (
            "\nThe SSH user needs passwordless sudo for this deploy (sudo -n). "
            "Add a sudoers rule for systemctl or docker, or SSH in as root."
        )
    return err + extra


def extract_bundle_for_tests(archive: Path, dest: Path) -> Path:
    """Used by tests: unpack an install_only-style archive into dest/python."""
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:*") as tar:
        _extract_tar(tar, dest)
    python = dest / "python"
    if not python.is_dir():
        raise DeployError("archive did not contain python/")
    return python
