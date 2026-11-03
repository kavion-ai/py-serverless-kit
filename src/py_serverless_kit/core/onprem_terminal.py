"""A full terminal in the browser (ttyd in Docker on this machine): SSH to a server, or a shell / client inside a
service's container. Works from Windows, macOS and Linux; only Docker is needed.

The terminal listens on ``127.0.0.1`` only, under a random secret path (``http://127.0.0.1:<port>/<token>/``), so the
studio can embed it. Keys are mounted read-only and copied with mode 600 inside the container; a saved password file
is used with sshpass. Stop it with :func:`stop_terminal` (or ``docker rm -f``); it is removed when it stops.
"""

from __future__ import annotations

import secrets
import shlex
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

IMAGE = "pskit-terminal:1"
BASE_IMAGE = "tsl0922/ttyd:1.7.7-alpine"
DOCKERFILE = f"FROM {BASE_IMAGE}\nRUN apk add --no-cache openssh-client sshpass docker-cli bash ncurses\n"
LABEL = "pskit.terminal"
FIRST_PORT = 7681

RunFn = Callable[[List[str], Optional[Path]], Tuple[int, str]]
Emit = Callable[[str], None]


class TerminalError(Exception):
    pass


def _runner(run: Optional[RunFn]) -> RunFn:
    from .onprem_services import _default_run

    return run or _default_run


def ensure_image(emit: Emit, *, run: Optional[RunFn] = None, build: Optional[Callable[[str], int]] = None) -> None:
    """Build ``pskit-terminal:1`` (ttyd + OpenSSH + sshpass + docker CLI) once on this machine."""
    import subprocess

    code, _ = _runner(run)(["docker", "image", "inspect", IMAGE], None)
    if code == 0:
        return
    emit(f"Building {IMAGE} (once): {BASE_IMAGE} + openssh-client, sshpass, docker-cli")
    if build is not None:
        built = build(DOCKERFILE)
    else:
        proc = subprocess.run(["docker", "build", "-t", IMAGE, "-"], input=DOCKERFILE.encode("utf-8"),  # noqa: S603, S607
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        built = proc.returncode
        if built:
            emit(proc.stdout.decode("utf-8", "replace")[-2000:])
    if built:
        raise TerminalError("could not build the terminal image; is Docker running on this machine?")


def _used_ports(run: RunFn) -> List[int]:
    _code, text = run(["docker", "ps", "--filter", f"label={LABEL}", "--format", '{{.Label "pskit.port"}}'], None)
    return [int(p) for p in text.split() if p.isdigit()]


def _ssh_parts(target: Dict[str, Any]) -> Tuple[List[str], str, List[str]]:
    """(docker -v mounts, the shell prelude that prepares keys, the ssh command) for a server target."""
    mounts: List[str] = []
    prelude = ["mkdir -p /root/.ssh", "chmod 700 /root/.ssh"]
    ssh = ["ssh", "-t", "-p", str(int(target.get("port") or 22)), "-o", "StrictHostKeyChecking=accept-new",
           "-o", "ServerAliveInterval=30"]
    identity = str(target.get("identity_file") or "")
    password_file = str(target.get("password_file") or "")
    if password_file:
        mounts += ["-v", f"{password_file}:/pskit/pass:ro"]
        ssh = ["sshpass", "-f", "/pskit/pass", *ssh, "-o", "PreferredAuthentications=password,keyboard-interactive",
               "-o", "PubkeyAuthentication=no"]
    elif identity:
        mounts += ["-v", f"{identity}:/pskit/key:ro"]
        prelude += ["cp /pskit/key /root/.ssh/pskit_key", "chmod 600 /root/.ssh/pskit_key"]
        ssh += ["-i", "/root/.ssh/pskit_key", "-o", "IdentitiesOnly=yes"]
    else:
        # The SSH agent / default key: your ~/.ssh (keys and config), copied with safe permissions.
        home_ssh = Path.home() / ".ssh"
        if home_ssh.is_dir():
            mounts += ["-v", f"{home_ssh}:/pskit/ssh:ro"]
            prelude += ["cp -r /pskit/ssh/. /root/.ssh/ 2>/dev/null", "chmod 600 /root/.ssh/* 2>/dev/null",
                        "rm -f /root/.ssh/known_hosts"]
    ssh.append(f"{target['user']}@{target['host']}")
    return mounts, " && ".join(prelude) + " ; ", ssh


def start_terminal(
    root: Path,
    emit: Emit,
    *,
    server: Optional[str] = None,
    target: Optional[Dict[str, Any]] = None,
    key: Optional[str] = None,
    shell: bool = False,
    run: Optional[RunFn] = None,
    build: Optional[Callable[[str], int]] = None,
) -> Dict[str, Any]:
    """Start a browser terminal. ``server`` / ``target``: SSH to that machine. ``key``: inside that service
    (its client, or ``sh`` with ``shell``). Returns ``{name, url, port, title}``."""
    from .onprem_console import interactive_args
    from .onprem_servers import ServerError, server_target
    from .onprem_services import _entry, describe_target

    runner = _runner(run)
    ensure_image(emit, run=run, build=build)
    mounts: List[str] = []
    if key:
        entry = _entry(root, key)
        inner = " ".join(shlex.quote(a) for a in interactive_args(entry, shell=shell))
        tgt = entry["target"]
        title = f"{key} ({entry.get('service')})"
        if tgt.get("method") == "ssh":
            mounts, prelude, ssh = _ssh_parts(tgt)
            remote = f"if docker info >/dev/null 2>&1; then docker {inner}; else sudo -n docker {inner}; fi"
            command = prelude + "exec " + " ".join(shlex.quote(a) for a in ssh) + " " + shlex.quote(remote)
        else:
            # Docker on this machine: the terminal talks to it through the socket (127.0.0.1 + secret path only).
            mounts = ["-v", "/var/run/docker.sock:/var/run/docker.sock"]
            command = "exec docker " + inner
    else:
        if server:
            try:
                tgt = server_target(root, server)
            except ServerError as exc:
                raise TerminalError(str(exc)) from None
        elif target and target.get("method") == "ssh":
            tgt = target
        else:
            raise TerminalError("pick a saved server, an SSH target or a service")
        title = describe_target(tgt)
        mounts, prelude, ssh = _ssh_parts(tgt)
        command = prelude + "exec " + " ".join(shlex.quote(a) for a in ssh)
    used = _used_ports(runner)
    port = FIRST_PORT
    while port in used:
        port += 1
    token = secrets.token_urlsafe(18)
    name = f"pskit-term-{port}"
    runner(["docker", "rm", "-f", name], None)
    argv = ["docker", "run", "-d", "--rm", "--name", name, "--label", f"{LABEL}=1", "--label", f"pskit.port={port}",
            "--label", f"pskit.title={title}", "-p", f"127.0.0.1:{port}:7681", *mounts, IMAGE,
            "ttyd", "-W", "-b", f"/{token}", "-t", f"titleFixed=pskit: {title}", "-t", "fontSize=14",
            "bash", "-c", command]
    code, out = runner(argv, None)
    if code:
        raise TerminalError(f"could not start the terminal: {out.strip()[-400:]}")
    url = f"http://127.0.0.1:{port}/{token}/"
    emit(f"Terminal for {title}: {url}")
    return {"name": name, "url": url, "port": port, "title": title}


def list_terminals(*, run: Optional[RunFn] = None) -> List[Dict[str, Any]]:
    fmt = '{{.Names}}|{{.Label "pskit.port"}}|{{.Label "pskit.title"}}|{{.Status}}'
    _code, text = _runner(run)(["docker", "ps", "--filter", f"label={LABEL}", "--format", fmt], None)
    out = []
    for line in text.splitlines():
        parts = line.split("|")
        if len(parts) == 4 and parts[0].startswith("pskit-term-"):
            out.append({"name": parts[0], "port": int(parts[1] or 0), "title": parts[2], "status": parts[3]})
    return out


def stop_terminal(name: str, *, run: Optional[RunFn] = None) -> None:
    if not name.startswith("pskit-term-") or not name[len("pskit-term-"):].isdigit():
        raise TerminalError("not a pskit terminal")
    _runner(run)(["docker", "rm", "-f", name], None)
