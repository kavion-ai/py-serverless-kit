"""Hana's ``run_command`` tool: one shell command, after the user approved it (``session.py`` asks every time, in
every mode), in the project folder on this machine or on a saved server over SSH (the same login as the Servers
page). The exit code and the output (cut to fit the model's context) go back to the model, which answers from it.

``pskit ...`` runs with studio's own Python (``python -m py_serverless_kit``), so it is the same pskit as studio's.
A few commands that wreck a machine are refused even when approved.
"""

from __future__ import annotations

import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Callable, List, Optional

from .tools import truncate

TIMEOUT = 120.0
MAX_COMMAND = 2000
# refused even after the user's click: wiping disks / the root folder, shutting the machine down, fork bombs
_REFUSED = re.compile(
    r"\brm\s+(?:-[a-z]*\s+)*(?:--no-preserve-root\s+)?(?:/|/\*|~|\$HOME)(?:\s|$)|\bmkfs(?:\.\w+)?\b|"
    r"\bdd\s+[^|;&]*\bof=/dev/(?:sd|nvme|hd|xvd|vd|disk)|\b(?:shutdown|poweroff|halt|reboot)\b|"
    r":\s*\(\s*\)\s*\{\s*:\s*\|\s*:\s*&\s*\}|\bformat\s+[a-z]:|\bdel\s+/[sq]\s+[a-z]:\\\s*$", re.I)
Runner = Callable[[List[str], Optional[str], float, bool], "subprocess.CompletedProcess[str]"]


def _run(argv: List[str], cwd: Optional[str], timeout: float, shell: bool) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603,S602 - the user approved this exact command
        argv[0] if shell else argv, cwd=cwd, shell=shell, capture_output=True, text=True, timeout=timeout,
        encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL)


def check(command: str) -> str:
    """"" when the command may run, else why not."""
    if not command.strip():
        return "error: run_command needs a command"
    if len(command) > MAX_COMMAND:
        return f"error: the command is longer than {MAX_COMMAND} characters"
    if _REFUSED.search(command):
        return "error: studio does not run this command (it can wipe or stop the machine); run it yourself if you mean it"
    return ""


def local_command(command: str) -> str:
    """``pskit validate`` -> ``"<studio's python>" -m py_serverless_kit validate`` (the pskit studio runs)."""
    m = re.match(r"\s*pskit(?=\s|$)", command)
    if not m:
        return command
    python = f'"{sys.executable}"' if sys.platform == "win32" else shlex.quote(sys.executable)
    return f"{python} -m py_serverless_kit{command[m.end():]}"


def run_command(root: Path, command: str, server: str = "", runner: Optional[Runner] = None,
                timeout: float = TIMEOUT) -> str:
    """Run ``command`` (already approved) and return ``exit code N`` and its output."""
    command = str(command or "").strip()
    refused = check(command)
    if refused:
        return refused
    run = runner or _run
    where = "this machine, project folder"
    try:
        if server:
            from ...core.onprem_servers import server_target
            from ...core.onprem_services import _ssh_argv

            try:
                target = server_target(root, server)
            except Exception as exc:  # noqa: BLE001 - unknown server, broken servers file
                return f"error: no saved server {server!r} ({exc})"
            where = f"server {server}"
            proc = run(_ssh_argv(target, command), None, timeout, False)
        else:
            proc = run([local_command(command)], str(root), timeout, True)
    except subprocess.TimeoutExpired:
        return f"error: the command did not finish within {int(timeout)} s on {where}"
    except OSError as exc:
        return f"error: could not start the command: {exc}"
    output = ((proc.stdout or "") + (("\n" if proc.stdout and proc.stderr else "") + (proc.stderr or ""))).strip()
    return truncate(f"exit code {proc.returncode} ({where})\n{output or '(no output)'}")

