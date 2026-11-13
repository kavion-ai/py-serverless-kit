"""SSH password login without ``sshpass`` (Windows, macOS, Linux).

``sshpass`` is not available on Windows and is missing from many machines. OpenSSH 8.4+ can take the password
from an *askpass* program instead (``SSH_ASKPASS`` + ``SSH_ASKPASS_REQUIRE=force``). This module is both:

* the wrapper, used like sshpass in front of ssh/scp::

      python -m py_serverless_kit.core.ssh_password -f /path/to/password-file ssh -p 22 user@host true
      python -m py_serverless_kit.core.ssh_password -e ssh user@host true      # password in $SSHPASS

* and the askpass program ssh runs (``--askpass``), which prints the password from the file or ``$SSHPASS``.

The password never appears on a command line: only the path of the file, or nothing (``-e``).
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, List, Optional, Sequence

MODULE = "py_serverless_kit.core.ssh_password"
FILE_VAR = "PSKIT_SSH_PASSWORD_FILE"
_jobs: List[Any] = []  # Windows job handles, kept open for the life of this process


def prefix(password_file: str = "") -> List[str]:
    """What goes in front of ``ssh``/``scp`` for a password login: sshpass when installed, else this module."""
    flag = ["-f", password_file] if password_file else ["-e"]
    if shutil.which("sshpass"):
        return ["sshpass", *flag]
    return [sys.executable, "-m", MODULE, *flag]


def is_wrapper(argv: Sequence[str]) -> bool:
    """Does this command start with a password wrapper (sshpass or this module)?"""
    argv = list(argv)
    if not argv:
        return False
    if Path(str(argv[0])).name.lower() in ("sshpass", "sshpass.exe"):
        return True
    return len(argv) > 2 and argv[1] == "-m" and argv[2] == MODULE


def _password() -> str:
    path = os.environ.get(FILE_VAR) or ""
    if path:
        text = Path(path).read_bytes().decode("utf-8")
        return text.splitlines()[0] if text else ""
    return str(os.environ.get("SSHPASS") or "")


def _askpass(prompt: str) -> int:
    """Run by ssh: print the answer to ``prompt`` on stdout."""
    if "(yes/no" in prompt.lower():
        # A host key question. Never answer it with the password.
        sys.stdout.write("no\n")
        return 0
    try:
        sys.stdout.write(_password() + "\n")
    except OSError as exc:
        sys.stderr.write(f"pskit askpass: can't read the password file: {exc}\n")
        return 1
    sys.stdout.flush()
    return 0


def _write_helper(folder: Path) -> Path:
    """A tiny script ssh can run as SSH_ASKPASS (it calls this module with ``--askpass``)."""
    python = sys.executable
    if sys.platform == "win32":
        helper = folder / "askpass.cmd"
        helper.write_bytes(f'@"{python}" -m {MODULE} --askpass %*\r\n'.encode())
    else:
        helper = folder / "askpass.sh"
        quoted = "'" + python.replace("'", "'\"'\"'") + "'"
        helper.write_bytes(f'#!/bin/sh\nexec {quoted} -m {MODULE} --askpass "$@"\n'.encode())
        helper.chmod(stat.S_IRWXU)
    return helper


def _kill_with_this_process(proc: subprocess.Popen[bytes]) -> None:
    """On Windows, end ssh when this wrapper is terminated (``Popen.terminate`` does not reach children)."""
    if sys.platform != "win32":
        return
    import ctypes
    from ctypes import wintypes

    class _Basic(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD)]

    class _Io(ctypes.Structure):
        _fields_ = [(name, ctypes.c_uint64) for name in ("r", "w", "o", "rb", "wb", "ob")]

    class _Extended(ctypes.Structure):
        _fields_ = [("BasicLimitInformation", _Basic), ("IoInfo", _Io), ("ProcessMemoryLimit", ctypes.c_size_t),
                    ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                    ("PeakJobMemoryUsed", ctypes.c_size_t)]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        return
    info = _Extended()
    info.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    extended_limit_information = 9
    kernel32.SetInformationJobObject(wintypes.HANDLE(job), extended_limit_information, ctypes.byref(info),
                                     ctypes.sizeof(info))
    kernel32.AssignProcessToJobObject(wintypes.HANDLE(job), wintypes.HANDLE(int(proc._handle)))  # type: ignore[attr-defined]
    _jobs.append(job)


def run(argv: Sequence[str], *, password_file: str = "") -> int:
    """Run ``argv`` (ssh/scp ...) with the password answered by askpass. Returns its exit code."""
    if not argv:
        sys.stderr.write("pskit ssh_password: no command given\n")
        return 2
    env = dict(os.environ)
    if password_file:
        if not os.path.isfile(password_file):
            sys.stderr.write(f"pskit ssh_password: password file not found: {password_file}\n")
            return 2
        env[FILE_VAR] = os.path.abspath(password_file)
    elif not env.get("SSHPASS"):
        sys.stderr.write("pskit ssh_password: -e needs the SSHPASS environment variable\n")
        return 2
    folder = Path(tempfile.mkdtemp(prefix="pskit-askpass-"))
    try:
        env["SSH_ASKPASS"] = str(_write_helper(folder))
        env["SSH_ASKPASS_REQUIRE"] = "force"  # OpenSSH 8.4+: use askpass even with a terminal
        env.setdefault("DISPLAY", ":0")  # older OpenSSH only uses askpass when DISPLAY is set
        try:
            proc = subprocess.Popen(list(argv), env=env)  # noqa: S603 - argv chosen by pskit
        except FileNotFoundError:
            sys.stderr.write(f"pskit ssh_password: command not found: {argv[0]} (install the OpenSSH client)\n")
            return 127
        _kill_with_this_process(proc)
        while True:
            try:
                return int(proc.wait())
            except KeyboardInterrupt:
                continue  # Ctrl+C reaches ssh too; wait for it to exit
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def main(args: Optional[Sequence[str]] = None) -> int:
    args = list(sys.argv[1:] if args is None else args)
    if args[:1] == ["--askpass"]:
        return _askpass(" ".join(args[1:]))
    if args[:1] == ["-f"] and len(args) >= 2:
        return run(args[2:], password_file=args[1])
    if args[:1] == ["-e"]:
        return run(args[1:])
    sys.stderr.write("usage: python -m py_serverless_kit.core.ssh_password (-f FILE | -e) ssh|scp ...\n")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
