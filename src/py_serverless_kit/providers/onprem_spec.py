"""Parse and validate ``provider.options.deploy`` for the on-premises provider.

Deploy still goes through Terraform ``local-exec``. This module only decides
*where* that provisioner copies the host and which interpreter starts it.
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import unquote, urlsplit

METHODS = ("local", "ssh", "docker")
PYTHON_MODES = ("auto", "system", "bundle")
NODE_MODES = ("auto", "system", "bundle")
# The host process is Python even for Node.js services; this is its interpreter when not pinned.
DEFAULT_HOST_PYTHON = "python3.12"
INSTALLS = ("process", "systemd")
TARGET_OS = ("auto", "linux", "windows", "darwin")
TARGET_ARCH = ("auto", "x86_64", "arm64")
KNOWN_HOSTS_SPECIAL = ("accept-new", "ignore")

# python-build-standalone install_only archives. Override with python_url.
_STANDALONE = {
    "python3.9": ("3.9.24", "20251010"),
    "python3.10": ("3.10.19", "20251010"),
    "python3.11": ("3.11.14", "20251010"),
    "python3.12": ("3.12.12", "20251010"),
    "python3.13": ("3.13.8", "20251007"),
    "python3.14": ("3.14.0", "20251007"),
}
# Official Node.js builds (nodejs.org/dist) for `node: bundle`. Override with node_url.
NODE_VERSIONS = {
    "nodejs18": "18.20.8",
    "nodejs20": "20.19.5",
    "nodejs22": "22.20.0",
    "nodejs24": "24.9.0",
}
_NODE_PLATFORM = {
    ("linux", "x86_64"): ("linux-x64", "tar.gz"),
    ("linux", "arm64"): ("linux-arm64", "tar.gz"),
    ("darwin", "x86_64"): ("darwin-x64", "tar.gz"),
    ("darwin", "arm64"): ("darwin-arm64", "tar.gz"),
    ("windows", "x86_64"): ("win-x64", "zip"),
    ("windows", "arm64"): ("win-arm64", "zip"),
}
_TRIPLE = {
    ("linux", "x86_64"): "x86_64-unknown-linux-gnu",
    ("linux", "arm64"): "aarch64-unknown-linux-gnu",
    ("windows", "x86_64"): "x86_64-pc-windows-msvc",
    ("windows", "arm64"): "aarch64-pc-windows-msvc",
    ("darwin", "x86_64"): "x86_64-apple-darwin",
    ("darwin", "arm64"): "aarch64-apple-darwin",
}

_SAFE_HOST = re.compile(r"^[A-Za-z0-9._:\[\]-]+$")
_SAFE_USER = re.compile(r"^[A-Za-z0-9._-]+$")
_SAFE_PATH = re.compile(r"^[A-Za-z0-9._/~:\\+@=-]+$")
_SAFE_IMAGE = re.compile(r"^[A-Za-z0-9._/:@+-]+$")
_SSH_URL = re.compile(r"^ssh://", re.I)


@dataclass
class DeploySpec:
    method: str
    python: str
    target_os: str
    target_arch: str
    runtime: str
    ssh_host: str = ""
    ssh_user: str = ""
    ssh_port: int = 22
    identity_file: str = ""
    known_hosts: str = "accept-new"
    # SSH login without a key: a password read by sshpass from this file, or from $SSHPASS (auth: password).
    password_file: str = ""
    auth: str = ""
    remote_path: str = ""
    sudo: bool = False
    install: str = "process"
    image: str = ""
    container: str = ""
    docker_host: str = ""
    restart: str = "unless-stopped"
    publish: str = ""
    docker_args: List[str] = field(default_factory=list)
    install_docker: bool = False
    python_url: str = ""
    python_sha256: str = ""
    python_home: str = ""
    # Node.js services: `runtime` above is then the host's Python, `node_runtime` the functions' runtime.
    language: str = "python"
    node: str = "system"
    node_runtime: str = ""
    node_url: str = ""
    node_sha256: str = ""
    node_home: str = ""

    def as_json(self) -> Dict[str, Any]:
        out = self._json()
        if self.language == "node":
            out["language"] = "node"
            out["node"] = self.node
            out["node_runtime"] = self.node_runtime
            out["node_bundle"] = {
                "url": self.node_url or node_dist_url(self.node_runtime, self.target_os, self.target_arch),
                "sha256": self.node_sha256,
                "home": self.node_home,
            }
        return out

    def _json(self) -> Dict[str, Any]:
        return {
            "method": self.method,
            "python": self.python,
            "target_os": self.target_os,
            "target_arch": self.target_arch,
            "runtime": self.runtime,
            "install": self.install,
            "sudo": self.sudo,
            "ssh": {
                "host": self.ssh_host,
                "user": self.ssh_user,
                "port": self.ssh_port,
                "identity_file": self.identity_file,
                "known_hosts": self.known_hosts,
                "path": self.remote_path,
                **({"password_file": self.password_file} if self.password_file else {}),
                **({"auth": self.auth} if self.auth else {}),
            },
            "docker": {
                "image": self.image,
                "container": self.container,
                "host": self.docker_host,
                "restart": self.restart,
                "publish": self.publish,
                "args": list(self.docker_args),
                "install_docker": self.install_docker,
            },
            "python_bundle": {
                "url": self.python_url or standalone_url(self.runtime, self.target_os, self.target_arch),
                "sha256": self.python_sha256,
                "home": self.python_home,
            },
        }


def local_os() -> str:
    if sys.platform == "win32":
        return "windows"
    if sys.platform == "darwin":
        return "darwin"
    return "linux"


def local_arch() -> str:
    machine = os.environ.get("PROCESSOR_ARCHITECTURE") or ""
    if sys.platform != "win32":
        machine = os.uname().machine  # type: ignore[attr-defined]
    lowered = machine.lower()
    if lowered in ("arm64", "aarch64"):
        return "arm64"
    return "x86_64"


def node_dist_url(runtime: str, target_os: str, target_arch: str) -> str:
    """Official nodejs.org archive for ``nodejs20`` on a target, or ``""`` when none is published."""
    version = NODE_VERSIONS.get(runtime)
    platform = _NODE_PLATFORM.get((target_os, target_arch))
    if version is None or platform is None:
        return ""
    name, ext = platform
    return f"https://nodejs.org/dist/v{version}/node-v{version}-{name}.{ext}"


def standalone_url(runtime: str, target_os: str, target_arch: str) -> str:
    pair = _STANDALONE.get(runtime)
    triple = _TRIPLE.get((target_os, target_arch))
    if pair is None or triple is None:
        return ""
    version, tag = pair
    name = f"cpython-{version}+{tag}-{triple}-install_only.tar.gz"
    return f"https://github.com/astral-sh/python-build-standalone/releases/download/{tag}/{name}"


def _as_mapping(raw: Any) -> Dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, str):
        text = raw.strip()
        if text in METHODS:
            return {"method": text}
        if _SSH_URL.match(text):
            parsed = urlsplit(text)
            body: Dict[str, Any] = {"method": "ssh", "host": parsed.hostname or ""}
            if parsed.username:
                body["user"] = unquote(parsed.username)
            if parsed.port:
                body["port"] = parsed.port
            if parsed.path and parsed.path != "/":
                body["path"] = unquote(parsed.path)
            return body
        raise ValueError(
            "options.deploy must be local, ssh, docker, an ssh://user@host/path URL, or a mapping with method"
        )
    if not isinstance(raw, dict):
        raise ValueError("options.deploy must be a string or a mapping")
    return dict(raw)


def _str(body: Dict[str, Any], *keys: str, default: str = "") -> str:
    for key in keys:
        if key in body and body[key] is not None:
            return str(body[key]).strip()
    return default


def _bool(body: Dict[str, Any], key: str, default: bool = False) -> bool:
    value = body.get(key, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in ("1", "true", "yes"):
        return True
    if isinstance(value, str) and value.strip().lower() in ("0", "false", "no", ""):
        return False
    raise ValueError(f"options.deploy.{key} must be a boolean")


def _port(value: Any, where: str, default: int) -> int:
    if value is None or value == "":
        return default
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 65535:
        raise ValueError(f"{where} must be an integer from 1 to 65535")
    return value


def parse_deploy(
    options: Dict[str, Any],
    *,
    service: str,
    stage: str,
    runtime: str,
    architecture: str,
) -> DeploySpec:
    raw = options.get("deploy")
    nested: Dict[str, Any] = {}
    body = _as_mapping(raw)
    if isinstance(body.get("ssh"), dict):
        nested.update(body["ssh"])
    if isinstance(body.get("docker"), dict):
        nested.update(body["docker"])
    merged = {
        **nested,
        **{k: v for k, v in body.items() if k not in ("ssh", "docker", "python_bundle", "node_bundle")},
    }
    if isinstance(body.get("python_bundle"), dict):
        bundle = body["python_bundle"]
        merged.setdefault("python_url", bundle.get("url"))
        merged.setdefault("python_sha256", bundle.get("sha256"))
        merged.setdefault("python_home", bundle.get("home"))
    if isinstance(body.get("node_bundle"), dict):
        bundle = body["node_bundle"]
        merged.setdefault("node_url", bundle.get("url"))
        merged.setdefault("node_sha256", bundle.get("sha256"))
        merged.setdefault("node_home", bundle.get("home"))

    # A Node.js service still runs the Python host; `runtime` becomes the host's interpreter.
    language = "node" if str(runtime).startswith("nodejs") else "python"
    node_runtime = ""
    if language == "node":
        node_runtime = runtime
        runtime = _str(merged, "host_python", default=DEFAULT_HOST_PYTHON) or DEFAULT_HOST_PYTHON
        if runtime not in _STANDALONE:
            raise ValueError(f"options.deploy.host_python must be one of {', '.join(_STANDALONE)}")
    node = _str(merged, "node", default="auto").lower() or "auto"
    if node not in NODE_MODES:
        raise ValueError(f"options.deploy.node must be one of {', '.join(NODE_MODES)}")

    method = _str(merged, "method", "via", default="local").lower() or "local"
    if method == "scp":
        # Same transport as ssh: one archive, copied with scp, started over ssh.
        method = "ssh"
    if method not in METHODS:
        raise ValueError(f"options.deploy.method must be one of {', '.join(METHODS)} (scp is an alias of ssh)")

    python = _str(merged, "python", default="auto").lower() or "auto"
    if python not in PYTHON_MODES:
        raise ValueError(f"options.deploy.python must be one of {', '.join(PYTHON_MODES)}")

    target_os = _str(merged, "target_os", "os", default="auto").lower() or "auto"
    if target_os not in TARGET_OS:
        raise ValueError(f"options.deploy.target_os must be one of {', '.join(TARGET_OS)}")

    target_arch = _str(merged, "target_arch", "arch", default="auto").lower() or "auto"
    if target_arch == "amd64":
        target_arch = "x86_64"
    if target_arch == "aarch64":
        target_arch = "arm64"
    if target_arch not in TARGET_ARCH:
        raise ValueError("options.deploy.target_arch must be auto, x86_64 or arm64")

    if target_os == "auto":
        target_os = local_os() if method == "local" else "linux"
    if target_arch == "auto":
        if method == "local":
            target_arch = local_arch()
        elif architecture in ("x86_64", "arm64"):
            target_arch = architecture
        else:
            target_arch = "x86_64"
    if python == "auto":
        python = "system"

    install = _str(merged, "install", default="process").lower() or "process"
    if install not in INSTALLS:
        raise ValueError("options.deploy.install must be process or systemd")
    if install == "systemd" and target_os != "linux":
        raise ValueError("options.deploy.install: systemd is only valid when target_os is linux")
    if install == "systemd" and method == "docker":
        raise ValueError("options.deploy.install: systemd is not used with method docker")

    slug = re.sub(r"[^a-z0-9-]+", "-", f"{service}-{stage}".lower()).strip("-") or "pskit"
    spec = DeploySpec(
        method=method,
        python=python,
        target_os=target_os,
        target_arch=target_arch,
        runtime=runtime,
        install=install,
        sudo=_bool(merged, "sudo", False),
        ssh_host=_str(merged, "host"),
        ssh_user=_str(merged, "user"),
        ssh_port=_port(merged.get("port"), "options.deploy.port", 22),
        identity_file=os.path.expanduser(_str(merged, "identity_file", "identity", "pem")),
        known_hosts=_str(merged, "known_hosts", default="accept-new") or "accept-new",
        password_file=os.path.expanduser(_str(merged, "password_file")),
        auth=_str(merged, "auth").lower(),
        remote_path=_str(merged, "path", "remote_path"),
        image=_str(merged, "image"),
        container=_str(merged, "container", "name"),
        docker_host=_str(merged, "docker_host"),
        restart=_str(merged, "restart", default="unless-stopped") or "unless-stopped",
        publish=_str(merged, "publish"),
        python_url=_str(merged, "python_url", "url"),
        python_sha256=_str(merged, "python_sha256", "sha256"),
        python_home=os.path.expanduser(_str(merged, "python_home")),
        language=language,
        node="system" if node == "auto" else node,
        node_runtime=node_runtime,
        node_url=_str(merged, "node_url"),
        node_sha256=_str(merged, "node_sha256"),
        node_home=os.path.expanduser(_str(merged, "node_home")),
    )
    args = merged.get("docker_args") or merged.get("args") or []
    if args:
        if not isinstance(args, list) or any(not isinstance(item, str) for item in args):
            raise ValueError("options.deploy.docker_args must be a list of strings")
        for item in args:
            if "\n" in item or "\r" in item:
                raise ValueError("options.deploy.docker_args values cannot contain newlines")
        spec.docker_args = list(args)

    if method == "ssh":
        if not spec.ssh_host:
            raise ValueError("options.deploy.host is required when method is ssh")
        if not _SAFE_HOST.match(spec.ssh_host):
            raise ValueError("options.deploy.host contains characters that are not safe to pass to ssh")
        if not spec.ssh_user:
            spec.ssh_user = os.environ.get("PSKIT_ONPREM_USER") or os.environ.get("USER") or os.environ.get("USERNAME") or "pskit"
        if not _SAFE_USER.match(spec.ssh_user):
            raise ValueError("options.deploy.user contains characters that are not safe to pass to ssh")
        if not spec.remote_path:
            home = _str(merged, "home").rstrip("/") or "/opt/pskit"  # a saved server's home path
            spec.remote_path = f"{home}/{slug}" if target_os != "windows" else f"C:/pskit/{slug}"
        if not _SAFE_PATH.match(spec.remote_path):
            raise ValueError("options.deploy.path contains characters that are not safe to pass to ssh")
        if spec.known_hosts not in KNOWN_HOSTS_SPECIAL and spec.known_hosts:
            spec.known_hosts = os.path.expanduser(spec.known_hosts)
        if spec.python == "bundle" and not spec.python_url and not spec.python_home:
            if not standalone_url(runtime, spec.target_os, spec.target_arch):
                raise ValueError(
                    f"no bundled CPython is published for {runtime} on {spec.target_os}/{spec.target_arch}; "
                    "set options.deploy.python_url or python_home"
                )

    if method == "docker":
        if not spec.image:
            spec.image = f"pskit-{slug}:{stage}"
        if not _SAFE_IMAGE.match(spec.image):
            raise ValueError("options.deploy.image contains characters that are not safe to pass to docker")
        if not spec.container:
            spec.container = f"pskit-{slug}"
        if not _SAFE_IMAGE.match(spec.container):
            raise ValueError("options.deploy.container contains characters that are not safe to pass to docker")
        if spec.docker_host and not (
            spec.docker_host.startswith("unix://")
            or spec.docker_host.startswith("tcp://")
            or spec.docker_host.startswith("npipe://")
            or spec.docker_host.startswith("ssh://")
        ):
            raise ValueError("options.deploy.docker_host must be a docker host URL (unix://, tcp://, npipe://, ssh://)")
        if spec.publish and ("\n" in spec.publish or "\r" in spec.publish):
            raise ValueError("options.deploy.publish cannot contain newlines")
        if "\n" in spec.restart or "\r" in spec.restart:
            raise ValueError("options.deploy.restart cannot contain newlines")
        if spec.docker_host.startswith("ssh://"):
            parsed = urlsplit(spec.docker_host)
            if not spec.ssh_host:
                spec.ssh_host = parsed.hostname or ""
            if parsed.username and "user" not in merged:
                spec.ssh_user = unquote(parsed.username)
            if parsed.port and "port" not in merged:
                spec.ssh_port = int(parsed.port)
        if spec.ssh_host and not is_docker_daemon_url(spec.docker_host):
            if not _SAFE_HOST.match(spec.ssh_host):
                raise ValueError("options.deploy.host contains characters that are not safe to pass to ssh")
            if not spec.ssh_user:
                spec.ssh_user = (
                    os.environ.get("PSKIT_ONPREM_USER")
                    or os.environ.get("USER")
                    or os.environ.get("USERNAME")
                    or "pskit"
                )
            if not _SAFE_USER.match(spec.ssh_user):
                raise ValueError("options.deploy.user contains characters that are not safe to pass to ssh")
            if not spec.remote_path:
                spec.remote_path = f"{_str(merged, 'home').rstrip('/') or '/opt/pskit'}/{slug}"
            if not _SAFE_PATH.match(spec.remote_path):
                raise ValueError("options.deploy.path contains characters that are not safe to pass to ssh")
            if spec.known_hosts not in KNOWN_HOSTS_SPECIAL and spec.known_hosts:
                spec.known_hosts = os.path.expanduser(spec.known_hosts)
            spec.install_docker = _bool(merged, "install_docker", True) if "install_docker" in merged else True
            if "sudo" not in merged:
                spec.sudo = True
        spec.python = "system"
        spec.node = "system"  # the image is built from an official node base

    if language == "node" and spec.node == "bundle" and not spec.node_url and not spec.node_home:
        url = node_dist_url(node_runtime, spec.target_os, spec.target_arch)
        if not url:
            raise ValueError(
                f"no Node.js build is published for {node_runtime} on {spec.target_os}/{spec.target_arch}; "
                "set options.deploy.node_url or node_home"
            )
        spec.node_url = url

    if spec.python == "bundle" and method == "local":
        if not spec.python_url and not spec.python_home:
            url = standalone_url(runtime, spec.target_os, spec.target_arch)
            if not url:
                raise ValueError(
                    f"no bundled CPython is published for {runtime} on {spec.target_os}/{spec.target_arch}; "
                    "set options.deploy.python_url or python_home"
                )
            spec.python_url = url
    return spec


def advertise_host(options: Dict[str, Any], spec: DeploySpec, bind_host: str, port: int) -> str:
    advertise = options.get("advertise")
    if advertise:
        return str(advertise).rstrip("/")
    shown = bind_host
    if spec.method == "ssh" and spec.ssh_host:
        shown = spec.ssh_host
    elif spec.method == "docker" and spec.ssh_host and not is_docker_daemon_url(spec.docker_host):
        shown = spec.ssh_host
    elif spec.method == "docker" and spec.docker_host.startswith("ssh://"):
        parsed = urlsplit(spec.docker_host)
        shown = parsed.hostname or bind_host
    if shown in ("0.0.0.0", "::", "[::]"):  # noqa: S104
        shown = "127.0.0.1"
    if ":" in shown and not shown.startswith("["):
        shown = "[" + shown + "]"
    return f"http://{shown}:{port}"


def pip_flags(spec: DeploySpec, runtime: str) -> List[str]:
    """Cross-compile wheels when the host will not run on this interpreter."""
    if spec.method == "local" and spec.python != "bundle":
        return []
    version = runtime.replace("python", "")
    os_name = spec.target_os
    arch = spec.target_arch
    if spec.method == "docker":
        os_name = "linux"
    if os_name == "linux":
        machine = "aarch64" if arch == "arm64" else "x86_64"
        platform = f"manylinux2014_{machine}"
    elif os_name == "windows":
        platform = "win_arm64" if arch == "arm64" else "win_amd64"
    elif os_name == "darwin":
        platform = "macosx_11_0_arm64" if arch == "arm64" else "macosx_10_9_x86_64"
    else:
        return []
    return [
        "--platform",
        platform,
        "--implementation",
        "cp",
        "--python-version",
        version,
        "--only-binary=:all:",
    ]


def docker_base_image(runtime: str) -> str:
    """Base image: ``python:3.x-slim`` for Python, the official ``node:NN-bookworm-slim`` for Node.js."""
    if runtime.startswith("nodejs"):
        return f"node:{runtime[6:]}-bookworm-slim"
    minor = runtime.replace("python", "")
    return f"python:{minor}-slim-bookworm"


def python_bin_for(spec: DeploySpec, root_posix: str) -> str:
    if spec.python != "bundle":
        if spec.target_os == "windows":
            return "python"
        minor = spec.runtime.replace("python", "")
        return f"python{minor}"
    if spec.target_os == "windows":
        return f"{root_posix}/python/python.exe".replace("/", "\\")
    return f"{root_posix}/python/bin/python3"


def is_docker_daemon_url(host: str) -> bool:
    """True when ``docker_host`` names a daemon (``DOCKER_HOST``), not an SSH server."""
    return host.startswith("unix://") or host.startswith("tcp://") or host.startswith("npipe://")


def targets_remote_docker(spec: DeploySpec) -> bool:
    """Build the image locally and copy it to a server over SSH."""
    return spec.method == "docker" and bool(spec.ssh_host) and not is_docker_daemon_url(spec.docker_host)


def json_targets_remote_docker(deploy: Dict[str, Any]) -> bool:
    docker = deploy.get("docker") or {}
    ssh = deploy.get("ssh") or {}
    return bool(ssh.get("host")) and not is_docker_daemon_url(str(docker.get("host") or ""))


def assign_pem(options: Dict[str, Any], path: str) -> str:
    """Store an absolute ``.pem`` path on ``options.deploy`` and return it."""
    resolved = str(Path(path).expanduser().resolve())
    deploy = options.get("deploy")
    if not isinstance(deploy, dict):
        options["deploy"] = {"method": str(deploy or "docker"), "pem": resolved}
        return resolved
    deploy["pem"] = resolved
    deploy["identity_file"] = resolved
    return resolved


def validate_identity(spec: DeploySpec) -> Optional[str]:
    """A warning about the SSH login (key file, password file), or None.

    No key means the SSH agent or the default key (``~/.ssh/id_*``); a password uses sshpass.
    """
    if spec.method != "ssh" and not targets_remote_docker(spec):
        return None
    if spec.auth and spec.auth not in ("key", "agent", "password"):
        return f"options.deploy.auth must be key, agent or password, not {spec.auth!r}"
    if spec.password_file and not os.path.isfile(spec.password_file):
        return f"options.deploy.password_file {spec.password_file!r} does not exist yet (needed at apply)"
    if spec.identity_file and not os.path.isfile(spec.identity_file):
        name = "pem" if targets_remote_docker(spec) else "identity_file"
        return f"options.deploy.{name} {spec.identity_file!r} does not exist yet (needed at apply)"
    return None


def uses_password(spec: DeploySpec) -> bool:
    return bool(spec.password_file) or spec.auth == "password"


def unit_name(service: str, stage: str) -> str:
    slug = re.sub(r"[^a-z0-9-]+", "-", f"pskit-{service}-{stage}".lower()).strip("-")
    return slug or "pskit-host"
