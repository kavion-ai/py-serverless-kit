"""The project's local environment: a ``.venv`` with ``requirements.txt`` (Python) or ``npm install`` (Node.js).

Used by the studio (Setup page) and ``pskit venv``. Interpreters are found on
this machine: the one running pskit, ``python3.X`` on PATH, and on Windows the
``py`` launcher's list.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

VENV = ".venv"
_TIMEOUT = 8


def _version(exe: str) -> Optional[str]:
    try:
        proc = subprocess.run(  # noqa: S603 - fixed argv
            [exe, "-c", "import sys; print('%d.%d.%d' % sys.version_info[:3])"],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    out = (proc.stdout or "").strip()
    return out if proc.returncode == 0 and re.fullmatch(r"\d+\.\d+\.\d+", out) else None


def interpreters() -> List[Dict[str, str]]:
    """Python interpreters found on this machine: ``[{"path", "version"}]``, newest first, unique by path."""
    candidates: List[str] = [sys.executable]
    for minor in range(14, 8, -1):
        found = shutil.which(f"python3.{minor}")
        if found:
            candidates.append(found)
    for name in ("python3", "python"):
        found = shutil.which(name)
        if found:
            candidates.append(found)
    if sys.platform == "win32" and shutil.which("py"):
        try:
            proc = subprocess.run(  # noqa: S603, S607 - the py launcher
                ["py", "-0p"], capture_output=True, text=True, timeout=_TIMEOUT, stdin=subprocess.DEVNULL
            )
            for line in (proc.stdout or "").splitlines():
                match = re.search(r"([A-Za-z]:\\.*python(?:w)?\.exe)\s*$", line.strip(), re.I)
                if match:
                    candidates.append(match.group(1))
        except (OSError, subprocess.SubprocessError):
            pass
    seen = set()
    out: List[Dict[str, str]] = []
    for exe in candidates:
        key = os.path.normcase(os.path.realpath(exe))
        if key in seen or ".venv" in key.split(os.sep):
            continue
        seen.add(key)
        version = _version(exe)
        if version:
            out.append({"path": exe, "version": version})
    out.sort(key=lambda i: tuple(int(p) for p in i["version"].split(".")), reverse=True)
    return out


def venv_python(root: Path) -> Path:
    folder = root / VENV
    return folder / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def status(root: Path, requirements: str = "requirements.txt") -> Dict[str, Any]:
    py = venv_python(root)
    node = shutil.which("node")
    npm = shutil.which("npm")
    return {
        "venv": {
            "path": str(root / VENV),
            "exists": py.is_file(),
            "python": _version(str(py)) if py.is_file() else None,
        },
        "requirements": {"path": requirements, "exists": (root / requirements).is_file()},
        "package_json": (root / "package.json").is_file(),
        "node_modules": (root / "node_modules").is_dir(),
        "node": {"path": node, "version": _node_version(node) if node else None, "npm": npm},
        "interpreters": interpreters(),
    }


def _node_version(node: str) -> Optional[str]:
    try:
        proc = subprocess.run(  # noqa: S603
            [node, "--version"], capture_output=True, text=True, timeout=_TIMEOUT, stdin=subprocess.DEVNULL
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return (proc.stdout or "").strip().lstrip("v") or None


def plan(
    root: Path,
    *,
    language: str = "python",
    python: Optional[str] = None,
    recreate: bool = False,
    requirements: str = "requirements.txt",
) -> List[List[str]]:
    """The commands that create the environment, in order (each an argv, run in ``root``)."""
    steps: List[List[str]] = []
    if language == "node":
        npm = shutil.which("npm")
        if not npm:
            raise ValueError("npm is not on PATH: install Node.js from https://nodejs.org/")
        if not (root / "package.json").is_file():
            raise ValueError("there is no package.json in the project")
        lock = (root / "package-lock.json").is_file()
        steps.append([npm, "ci" if lock else "install", "--no-audit", "--no-fund"])
        return steps
    exe = python or sys.executable
    known = {i["path"] for i in interpreters()}
    if python and python not in known and not Path(python).is_file():
        raise ValueError(f"{python} is not a Python interpreter on this machine")
    venv = root / VENV
    if recreate or not venv_python(root).is_file():
        args = [exe, "-m", "venv"]
        if recreate and venv.exists():
            args.append("--clear")
        steps.append([*args, str(venv)])
    py = str(venv_python(root))
    steps.append([py, "-m", "pip", "install", "--upgrade", "pip"])
    if (root / requirements).is_file():
        steps.append([py, "-m", "pip", "install", "-r", str(root / requirements)])
    return steps


def run_steps(root: Path, steps: List[List[str]], emit: Callable[[str, str], None]) -> int:
    """Run ``steps`` in ``root``, streaming output through ``emit(text, stream)``. Returns the exit code."""
    env = dict(os.environ)
    env.update({"PYTHONUNBUFFERED": "1", "PIP_DISABLE_PIP_VERSION_CHECK": "1", "PYTHONIOENCODING": "utf-8"})
    env.pop("VIRTUAL_ENV", None)
    for argv in steps:
        emit("$ " + " ".join(argv), "system")
        try:
            proc = subprocess.Popen(  # noqa: S603 - argv from plan()
                argv,
                cwd=str(root),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=env,
            )
        except OSError as exc:
            emit(f"could not start: {exc}", "stderr")
            return 127
        assert proc.stdout is not None
        for raw in iter(proc.stdout.readline, b""):
            emit(raw.decode("utf-8", "replace").rstrip("\r\n"), "stdout")
        code = proc.wait()
        if code != 0:
            emit(f"failed with exit code {code}", "stderr")
            return code
    emit("environment ready", "system")
    return 0


__all__ = ["VENV", "interpreters", "plan", "run_steps", "status", "venv_python"]
