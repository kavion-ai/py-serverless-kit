"""Run pskit commands (validate, deploy, ...) for the studio and stream their output.

Every job is ``sys.executable -m py_serverless_kit <argv>`` with an explicit
argument list (never a shell string). Deploy-like commands are exclusive.
"""

from __future__ import annotations

import collections
import json
import os
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Deque, Dict, List, Optional

from .project import StudioError

MAX_LINES = 5000
KEEP_JOBS = 20
EXCLUSIVE = ("package", "plan", "deploy", "remove", "resources-delete")
COMMANDS = (
    "validate",
    "package",
    "plan",
    "deploy",
    "remove",
    "info",
    "invoke",
    "workflow-run",
    "resources-delete",
    "trigger",
    "resource-send",
)
_ADDRESS = r'^[A-Za-z_][A-Za-z0-9_.\-]*(\[[A-Za-z0-9_"\-]+\])?$'
_NAME = r"^[A-Za-z][A-Za-z0-9_-]{0,62}$"


def _flag_value(value: Any, what: str) -> str:
    import re

    text = str(value or "").strip()
    if not re.fullmatch(_NAME, text):
        raise StudioError(400, f"invalid {what} {value!r}")
    return text


def build_argv(
    command: str, provider: Optional[str] = None, stage: Optional[str] = None, args: Optional[Dict[str, Any]] = None
) -> List[str]:
    """Map a studio job request to CLI arguments."""
    import re

    args = dict(args or {})
    if command not in COMMANDS:
        raise StudioError(400, f"command must be one of {', '.join(COMMANDS)}")
    common: List[str] = []
    if provider:
        if not re.fullmatch(r"[a-z][a-z0-9_-]{1,31}", str(provider)):
            raise StudioError(400, "invalid provider")
        common += ["--provider", str(provider)]
    if stage:
        if not re.fullmatch(r"[a-z][a-z0-9-]{0,15}", str(stage)):
            raise StudioError(400, "invalid stage")
        common += ["--stage", str(stage)]
    server = args.get("server")
    if server and command in ("package", "plan", "deploy", "remove", "info", "trigger", "resource-send", "workflow-run"):
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{0,62}", str(server)):
            raise StudioError(400, "invalid server name")
        common += ["--server", str(server)]
    cluster = args.get("cluster")
    if cluster and command in ("package", "plan", "deploy", "remove", "info"):
        if server:
            raise StudioError(400, "pick a server or a cluster, not both")
        if not re.fullmatch(r"[a-z][a-z0-9-]{0,30}", str(cluster)):
            raise StudioError(400, "invalid cluster name")
        common += ["--cluster", str(cluster)]
    if command == "validate":
        return ["validate", *common]
    if command == "info":
        return ["info", *common]
    if command == "package":
        return ["package", *common] + (["--skip-deps"] if args.get("skip_deps") else [])
    if command == "plan":
        return ["plan", *common] + (["--skip-deps"] if args.get("skip_deps") else [])
    if command == "deploy":
        return ["deploy", *common] + (["--skip-deps"] if args.get("skip_deps") else [])
    if command == "resource-send":
        argv = ["resources", "send", *common, _flag_value(args.get("resource"), "resource"), "--json"]
        if args.get("data") is not None:
            data = args["data"] if isinstance(args["data"], str) else json.dumps(args["data"])
            if data.startswith("@"):
                raise StudioError(400, "data must be JSON, not a file reference")
            argv += ["-d", data]
        return argv
    if command == "trigger":
        argv = ["trigger", *common, "-f", _flag_value(args.get("function"), "function"), "--json"]
        event = args.get("event")
        if event is None or event == -1 or args.get("direct"):
            argv.append("--direct")
        else:
            if not isinstance(event, int) or isinstance(event, bool) or not 0 <= event < 1000:
                raise StudioError(400, "event must be the trigger number")
            argv += ["-e", str(event)]
        if args.get("path"):
            path = str(args["path"]).strip()
            if not path.startswith("/") or any(c.isspace() or ord(c) < 32 for c in path) or len(path) > 2048:
                raise StudioError(400, "HTTP path must start with / and contain no spaces")
            argv += ["--path", path]
        if args.get("data") is not None:
            data = args["data"] if isinstance(args["data"], str) else json.dumps(args["data"])
            if data.startswith("@"):
                raise StudioError(400, "data must be JSON, not a file reference")
            argv += ["-d", data]
        return argv
    if command == "resources-delete":
        addresses = args.get("addresses") or []
        if not isinstance(addresses, list) or not addresses or len(addresses) > 200:
            raise StudioError(400, "addresses must be a non-empty list")
        for address in addresses:
            if not isinstance(address, str) or not re.fullmatch(_ADDRESS, address):
                raise StudioError(400, f"invalid resource address {address!r}")
        return ["resources", "delete", *common, "--yes", *addresses]
    if command == "remove":
        return ["remove", *common, "--yes"] + (["--keep-resources"] if args.get("keep_resources") else [])
    if command == "invoke":
        argv = ["invoke", *common, "-f", _flag_value(args.get("function"), "function")]
        if args.get("type"):
            argv += ["-t", _flag_value(args["type"], "event type")]
        if args.get("method"):
            method = str(args["method"]).strip().upper()
            if method not in ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"):
                raise StudioError(400, f"invalid HTTP method {args['method']!r}")
            argv += ["--method", method]
        if args.get("path"):
            path = str(args["path"]).strip()
            if not path.startswith("/") or any(c.isspace() or ord(c) < 32 for c in path) or len(path) > 2048:
                raise StudioError(400, "HTTP path must start with / and contain no spaces")
            argv += ["--path", path]
        if args.get("data") is not None:
            data = args["data"] if isinstance(args["data"], str) else json.dumps(args["data"])
            if data.startswith("@"):
                raise StudioError(400, "data must be JSON, not a file reference")
            argv += ["-d", data]
        return argv
    argv = ["workflow", "run", *common, _flag_value(args.get("workflow"), "workflow")]
    if args.get("data") is not None:
        data = args["data"] if isinstance(args["data"], str) else json.dumps(args["data"])
        if data.startswith("@"):
            raise StudioError(400, "data must be JSON, not a file reference")
        argv += ["-i", data]
    return argv


class Job:
    def __init__(self, command: str, argv: List[str], cwd: Path, label: Optional[str] = None) -> None:
        self.id = uuid.uuid4().hex[:16]
        self.command = command
        self.label = label or command
        self.argv = argv
        self.cwd = cwd
        self.status = "running"
        self.exit_code: Optional[int] = None
        self.started_at = time.time()
        self.finished_at: Optional[float] = None
        self._lines: Deque[Dict[str, Any]] = collections.deque(maxlen=MAX_LINES)
        self._seq = 0
        self._lock = threading.Lock()
        self.proc: Optional[subprocess.Popen] = None
        self.cancelled = False
        self.on_finish: Optional[Callable[[Job], None]] = None

    def emit(self, text: str, stream: str = "stdout") -> None:
        with self._lock:
            self._seq += 1
            self._lines.append({"seq": self._seq, "text": text.rstrip("\r\n"), "stream": stream})

    def finish(self, code: int) -> None:
        with self._lock:
            self.exit_code = code
            self.finished_at = time.time()
            if self.cancelled:
                self.status = "cancelled"
            else:
                self.status = "succeeded" if code == 0 else "failed"
        if self.on_finish is not None:
            try:
                self.on_finish(self)
            except Exception as exc:  # noqa: BLE001
                self.emit(f"post-step failed: {exc}", "stderr")

    def snapshot(self, since: int = 0) -> Dict[str, Any]:
        with self._lock:
            lines = [line for line in self._lines if line["seq"] > since]
            return {
                "job_id": self.id,
                "command": self.command,
                "label": self.label,
                "status": self.status,
                "exit_code": self.exit_code,
                "started_at": self.started_at,
                "finished_at": self.finished_at,
                "lines": lines,
                "next": self._seq,
            }


class JobManager:
    def __init__(self, root: Path) -> None:
        self.root = root
        self._jobs: collections.OrderedDict[str, Job] = collections.OrderedDict()
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ start
    def start(
        self,
        command: str,
        provider: Optional[str] = None,
        stage: Optional[str] = None,
        args: Optional[Dict[str, Any]] = None,
    ) -> Job:
        argv = build_argv(command, provider, stage, args)
        return self.run_process(
            command, [sys.executable, "-m", "py_serverless_kit", *argv], exclusive=command in EXCLUSIVE
        )

    def run_process(
        self,
        command: str,
        cmd: List[str],
        *,
        exclusive: bool = False,
        label: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        on_finish: Optional[Callable[[Job], None]] = None,
    ) -> Job:
        with self._lock:
            if exclusive:
                busy = [j for j in self._jobs.values() if j.status == "running" and j.command in EXCLUSIVE]
                if busy:
                    raise StudioError(409, f"`{busy[0].command}` is already running", code="busy", job_id=busy[0].id)
            job = Job(command, cmd, self.root, label)
            job.on_finish = on_finish
            self._add(job)
        child_env = dict(os.environ)
        child_env.update({"PSKIT_LOG_FORMAT": "text", "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"})
        child_env.update(env or {})
        kwargs: Dict[str, Any] = {
            "cwd": str(self.root),
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "env": child_env,
        }
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        job.emit("$ " + " ".join(_display(cmd)), "system")
        try:
            job.proc = subprocess.Popen(cmd, **kwargs)  # noqa: S603 - fixed argv, no shell
        except OSError as exc:
            job.emit(f"could not start: {exc}", "stderr")
            job.finish(127)
            return job
        readers = [
            threading.Thread(target=_pump, args=(job, job.proc.stdout, "stdout"), daemon=True),
            threading.Thread(target=_pump, args=(job, job.proc.stderr, "stderr"), daemon=True),
        ]
        for reader in readers:
            reader.start()

        def wait() -> None:
            assert job.proc is not None
            code = job.proc.wait()
            for reader in readers:
                reader.join(5)
            job.finish(code)

        threading.Thread(target=wait, name=f"pskit-job-{job.id}", daemon=True).start()
        return job

    def run_callable(self, command: str, fn: Callable[[Job], int], *, label: Optional[str] = None) -> Job:
        """Run Python code as a job (e.g. a docker pull + run sequence)."""
        with self._lock:
            job = Job(command, [], self.root, label)
            self._add(job)

        def run() -> None:
            try:
                code = fn(job)
            except Exception as exc:  # noqa: BLE001 - report in the job log
                job.emit(f"{type(exc).__name__}: {exc}", "stderr")
                code = 1
            job.finish(code)

        threading.Thread(target=run, name=f"pskit-job-{job.id}", daemon=True).start()
        return job

    def _add(self, job: Job) -> None:
        self._jobs[job.id] = job
        while len(self._jobs) > KEEP_JOBS:
            oldest = next((k for k, j in self._jobs.items() if j.status != "running"), None)
            if oldest is None:
                break
            del self._jobs[oldest]

    # ------------------------------------------------------------------ inspect / control
    def get(self, job_id: str) -> Job:
        job = self._jobs.get(job_id)
        if job is None:
            raise StudioError(404, f"unknown job {job_id!r}")
        return job

    def list(self) -> List[Dict[str, Any]]:
        out = []
        for job in reversed(list(self._jobs.values())):
            snap = job.snapshot(since=10**12)
            snap.pop("lines")
            out.append(snap)
        return out

    def clear(self, job_id: Optional[str] = None) -> Dict[str, Any]:
        """Forget finished jobs (all of them, or one). Running jobs are kept."""
        with self._lock:
            if job_id is not None:
                job = self.get(job_id)
                if job.status == "running":
                    raise StudioError(409, "the job is still running; cancel it first", code="busy", job_id=job.id)
                del self._jobs[job_id]
                return {"removed": 1}
            done = [k for k, j in self._jobs.items() if j.status != "running"]
            for key in done:
                del self._jobs[key]
            return {"removed": len(done)}

    def cancel(self, job_id: str) -> Dict[str, Any]:
        job = self.get(job_id)
        if job.status != "running":
            return job.snapshot(since=10**12)
        job.cancelled = True
        proc = job.proc
        if proc is not None and proc.poll() is None:
            job.emit("cancelling...", "system")
            _terminate(proc)
        return job.snapshot(since=10**12)


def _pump(job: Job, stream: Any, name: str) -> None:
    if stream is None:
        return
    for raw in iter(stream.readline, b""):
        job.emit(raw.decode("utf-8", "replace"), name)
    stream.close()


def _terminate(proc: subprocess.Popen) -> None:
    if sys.platform == "win32":
        subprocess.call(
            ["taskkill", "/PID", str(proc.pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
    else:
        proc.terminate()
    try:
        proc.wait(10)
    except subprocess.TimeoutExpired:
        proc.kill()


def _display(cmd: List[str]) -> List[str]:
    out = []
    for part in cmd:
        if part == sys.executable:
            out.append("python")
        elif " " in part or '"' in part:
            out.append(json.dumps(part))
        else:
            out.append(part)
    return out
