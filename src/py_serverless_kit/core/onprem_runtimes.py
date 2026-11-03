"""Software pskit installs on an SSH server: language runtimes, web servers and tools.

Each entry has a POSIX ``sh`` install script (apt-get, dnf, yum or apk) that runs after the shared header
(``as_root``, ``dk``), a ``check`` command whose output is the installed version, and optional ``versions``.
Scripts only add packages / binaries and start services; nothing is removed.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

# Package manager dispatch: one line per manager, the same packages in their names.
_PM = (
    "pm_install() {{\n"
    "  if command -v apt-get >/dev/null 2>&1; then\n"
    "    export DEBIAN_FRONTEND=noninteractive; as_root apt-get update -q; as_root apt-get install -y -q {apt}\n"
    "  elif command -v dnf >/dev/null 2>&1; then as_root dnf install -y {dnf}\n"
    "  elif command -v yum >/dev/null 2>&1; then as_root yum install -y {dnf}\n"
    "  elif command -v apk >/dev/null 2>&1; then as_root apk add --no-cache {apk}\n"
    "  else echo 'pskit: no apt-get, dnf, yum or apk on this server; install it by hand' >&2; exit 1; fi\n"
    "}}\n"
)

_ARCH = (
    'case "$(uname -m)" in x86_64|amd64) arch=amd64;; aarch64|arm64) arch=arm64;; '
    '*) echo "pskit: unsupported CPU $(uname -m)" >&2; exit 1;; esac\n'
)

_SERVICE_START = (
    "start_service() {\n"
    "  if command -v systemctl >/dev/null 2>&1; then as_root systemctl enable --now \"$1\" || true\n"
    "  elif command -v rc-service >/dev/null 2>&1; then as_root rc-update add \"$1\" default 2>/dev/null || true; "
    "as_root rc-service \"$1\" start || true\n"
    "  elif command -v service >/dev/null 2>&1; then as_root service \"$1\" start || true; fi\n"
    "}\n"
)


def _pkg(apt: str, dnf: Optional[str] = None, apk: Optional[str] = None) -> str:
    return _PM.format(apt=apt, dnf=dnf or apt, apk=apk or apt)


def _need_curl() -> str:
    return "command -v curl >/dev/null 2>&1 || { " + _pkg("curl ca-certificates", "curl", "curl ca-certificates") \
        + "pm_install; }\n"


def _nodejs(version: str) -> str:
    major = version.split(".")[0]
    return (
        _need_curl()
        + "have=$(node -v 2>/dev/null | sed 's/^v//; s/\\..*//')\n"
        + f'if [ "$have" != "{major}" ]; then\n'
        + "  if command -v apt-get >/dev/null 2>&1; then\n"
        + f"    curl -fsSL https://deb.nodesource.com/setup_{major}.x -o /tmp/pskit-node.sh && as_root bash /tmp/pskit-node.sh"
        + " && rm -f /tmp/pskit-node.sh\n"
        + "    as_root apt-get install -y -q nodejs\n"
        + "  elif command -v dnf >/dev/null 2>&1 || command -v yum >/dev/null 2>&1; then\n"
        + f"    curl -fsSL https://rpm.nodesource.com/setup_{major}.x -o /tmp/pskit-node.sh && as_root bash /tmp/pskit-node.sh"
        + " && rm -f /tmp/pskit-node.sh\n"
        + "    if command -v dnf >/dev/null 2>&1; then as_root dnf install -y nodejs; else as_root yum install -y nodejs; fi\n"
        + "  elif command -v apk >/dev/null 2>&1; then\n"
        + "    echo 'pskit: Alpine installs its own Node.js version (apk), not a chosen one'\n"
        + "    as_root apk add --no-cache nodejs npm\n"
        + "  else echo 'pskit: no apt-get, dnf, yum or apk on this server' >&2; exit 1; fi\n"
        + "fi\n"
        + "node -v && npm -v\n"
    )


_PY_DISTRO = (
    _pkg("python3 python3-venv python3-pip", "python3 python3-pip", "python3 py3-pip")
    + "if ! command -v python3 >/dev/null 2>&1 || ! python3 -m venv --help >/dev/null 2>&1; then pm_install; fi\n"
    + "python3 --version\n"
)
_PY_DIR = "/opt/pskit-python"


def _python(version: str) -> str:
    """``system``: the distribution's python3 (with venv and pip). ``3.X``: a standalone CPython 3.X from
    python-build-standalone (through uv) in /opt/pskit-python, linked as /usr/local/bin/python3.X, on any distro.
    The on-prem host picks python3.X first when the project's runtime is python3.X."""
    if version in ("", "system"):
        return _PY_DISTRO
    exe = f"python{version}"
    return (
        _need_curl()
        + f"if command -v {exe} >/dev/null 2>&1 && {exe} -m venv --help >/dev/null 2>&1; then\n"
        + f"  echo 'pskit: {exe} is already installed'\n"
        + "else\n"
        + "  if ! command -v uv >/dev/null 2>&1; then\n"
        + "    curl -LsSf https://astral.sh/uv/install.sh -o /tmp/pskit-uv.sh\n"
        + "    as_root env UV_INSTALL_DIR=/usr/local/bin UV_NO_MODIFY_PATH=1 sh /tmp/pskit-uv.sh && rm -f /tmp/pskit-uv.sh\n"
        + "  fi\n"
        + f"  as_root env UV_PYTHON_INSTALL_DIR={_PY_DIR} \"$(command -v uv || echo /usr/local/bin/uv)\" python install {version}\n"
        + f"  py=$(ls -d {_PY_DIR}/cpython-{version}.*/bin/{exe} 2>/dev/null | sort -V | tail -1)\n"
        + f'  [ -n "$py" ] || {{ echo "pskit: uv did not install Python {version}" >&2; exit 1; }}\n'
        + f'  as_root ln -sf "$py" /usr/local/bin/{exe}\n'
        + "  command -v python3 >/dev/null 2>&1 || as_root ln -sf \"$py\" /usr/local/bin/python3\n"
        + "fi\n"
        + f"{exe} --version && {exe} -m pip --version\n"
    )


def _go(version: str) -> str:
    return (
        _need_curl()
        + _ARCH
        + f'if [ "$(/usr/local/go/bin/go version 2>/dev/null | awk \'{{print $3}}\')" != "go{version}" ]; then\n'
        + f"  curl -fsSL https://go.dev/dl/go{version}.linux-$arch.tar.gz -o /tmp/pskit-go.tgz\n"
        + "  as_root rm -rf /usr/local/go && as_root tar -C /usr/local -xzf /tmp/pskit-go.tgz && rm -f /tmp/pskit-go.tgz\n"
        + "  as_root ln -sf /usr/local/go/bin/go /usr/local/bin/go && as_root ln -sf /usr/local/go/bin/gofmt /usr/local/bin/gofmt\n"
        + "fi\n"
        + "go version\n"
    )


def _caddy(version: str) -> str:
    return (
        _need_curl()
        + _ARCH
        + f"curl -fsSL https://github.com/caddyserver/caddy/releases/download/v{version}/caddy_{version}_linux_$arch.tar.gz"
        + " -o /tmp/pskit-caddy.tgz\n"
        + "mkdir -p /tmp/pskit-caddy && tar -C /tmp/pskit-caddy -xzf /tmp/pskit-caddy.tgz caddy\n"
        + "as_root install -m 0755 /tmp/pskit-caddy/caddy /usr/local/bin/caddy && rm -rf /tmp/pskit-caddy /tmp/pskit-caddy.tgz\n"
        + "caddy version\n"
    )


def _java(version: str) -> str:
    return (
        _pkg(f"openjdk-{version}-jre-headless", f"java-{version}-openjdk-headless", f"openjdk{version}-jre-headless")
        + "pm_install\njava -version 2>&1 | head -1\n"
    )


RUNTIME_SPECS: Dict[str, Dict[str, Any]] = {
    "python": {
        "label": "Python 3",
        "group": "Languages and Docker",
        "notes": "system: the distribution's python3 with venv and pip. 3.X: that exact CPython (standalone build "
        "through uv, any distro) as /usr/local/bin/python3.X, so the host runs with python: system and runtime "
        "python3.X.",
        "versions": ["system", "3.13", "3.12", "3.11", "3.10", "3.9", "3.14"],
        "check": "for p in python3.14 python3.13 python3.12 python3.11 python3.10 python3.9; do "
        "command -v $p >/dev/null 2>&1 && $p --version; done; python3 --version",
        "script": _python,
    },
    "nodejs": {
        "label": "Node.js",
        "group": "Languages",
        "notes": "Node.js and npm from NodeSource (apt / dnf; Alpine: its own version). Needed by Node.js functions "
        "with node: system, PM2 and npm-based tools.",
        "versions": ["22", "24", "20", "18"],
        "check": "node -v",
        "script": _nodejs,
    },
    "java": {
        "label": "Java (OpenJDK)",
        "group": "Languages",
        "notes": "Headless OpenJDK runtime from the distribution's packages.",
        "versions": ["21", "17"],
        "check": "java -version 2>&1 | head -1",
        "script": _java,
    },
    "go": {
        "label": "Go",
        "group": "Languages",
        "notes": "The official Go toolchain in /usr/local/go (linked into /usr/local/bin).",
        "versions": ["1.23.4", "1.22.10"],
        "check": "go version",
        "script": _go,
    },
    "nginx": {
        "label": "nginx",
        "group": "Web servers",
        "notes": "nginx from the distribution's packages, enabled and started. Put a reverse proxy to the pskit host "
        "(port 8080) in /etc/nginx/conf.d/.",
        "check": "nginx -v 2>&1",
        "script": lambda _v: _pkg("nginx") + _SERVICE_START + "pm_install\nstart_service nginx\nnginx -v 2>&1\n",
    },
    "caddy": {
        "label": "Caddy",
        "group": "Web servers",
        "notes": "The caddy binary in /usr/local/bin (automatic HTTPS). Try it with: caddy reverse-proxy --from :80 "
        "--to 127.0.0.1:8080.",
        "versions": ["2.8.4"],
        "check": "caddy version",
        "script": _caddy,
    },
    "certbot": {
        "label": "Certbot (Let's Encrypt)",
        "group": "Web servers",
        "notes": "certbot with its nginx plugin where the distribution has it (dnf needs EPEL).",
        "check": "certbot --version 2>&1",
        "script": lambda _v: _pkg("certbot python3-certbot-nginx", "certbot", "certbot certbot-nginx")
        + "pm_install\ncertbot --version 2>&1\n",
    },
    "pm2": {
        "label": "PM2",
        "group": "Process managers",
        "notes": "PM2 (npm install -g pm2) to keep Node.js apps running; install Node.js first.",
        "check": "pm2 --version",
        "script": lambda _v: "command -v npm >/dev/null 2>&1 || { echo 'pskit: install Node.js first' >&2; exit 1; }\n"
        "as_root npm install -g pm2\npm2 --version\n",
    },
    "git": {
        "label": "Git",
        "group": "Tools",
        "notes": "git from the distribution's packages.",
        "check": "git --version",
        "script": lambda _v: _pkg("git") + "pm_install\ngit --version\n",
    },
    "tools": {
        "label": "Basic tools",
        "group": "Tools",
        "notes": "curl, wget, unzip, jq, htop, tmux and netcat for working on the server.",
        "check": "jq --version",
        "script": lambda _v: _pkg("curl wget unzip jq htop tmux netcat-openbsd", "curl wget unzip jq htop tmux nmap-ncat",
                                  "curl wget unzip jq htop tmux netcat-openbsd")
        + "pm_install\njq --version\n",
    },
}

_VERSION = re.compile(r"^[0-9][0-9.]{0,15}$")


def runtime_catalog() -> List[Dict[str, Any]]:
    return [
        {"id": name, "label": rt["label"], "kind": "runtime", "roles": [], "notes": rt["notes"],
         "group": rt["group"], "versions": list(rt.get("versions") or [])}
        for name, rt in RUNTIME_SPECS.items()
    ]


def check_version(name: str, version: Any) -> str:
    """The version to install: the first listed one by default; any ``1.2.3``-style version is accepted."""
    versions = RUNTIME_SPECS[name].get("versions") or []
    text = str(version or "").strip()
    if not versions:
        if text:
            raise ValueError(f"{RUNTIME_SPECS[name]['label']} installs the distribution's version; leave version empty")
        return ""
    if not text:
        return str(versions[0])
    if text in versions:
        return text
    if not _VERSION.match(text):
        raise ValueError("version must look like 22 or 1.23.4")
    return text


def install_script(name: str, version: str) -> str:
    return str(RUNTIME_SPECS[name]["script"](version))
