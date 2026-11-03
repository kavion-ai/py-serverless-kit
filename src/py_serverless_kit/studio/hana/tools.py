"""Hana's 10 tools on the studio's project, with the outputs she saw in training.

Read tools: ``search_docs``, ``get_project``, ``read_file``, ``get_validation``, ``validate``.
Changing tools: ``set_config`` (pskit.yml, saved like the studio's Save: backup first), ``write_file``,
``invoke_local`` (runs a handler on this machine). ``propose_plan`` and ``ask_user`` are answered by the user and
handled by the chat loop (``session.py``), not here.

Nothing here deploys, plans, removes or contacts a cloud: validate and local invoke only. Paths are confined to the
project (``studio/files.py``); ``.env`` files, keys and ``.pskit/`` are refused.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Dict, List, Optional

from .. import files, project
from ..project import StudioError
from .knowledge import search

READ_TOOLS = ("search_docs", "get_project", "read_file", "get_validation", "validate")
CHANGE_TOOLS = ("set_config", "write_file", "invoke_local")
USER_TOOLS = ("propose_plan", "ask_user")
MAX_OUTPUT = 6000  # characters of one tool result (the model's context is 8,192 tokens)
_SECRET_FILE = re.compile(r"(^|/)(\.env(\..*)?|.*\.(pem|key|p12|pfx)|id_rsa.*|id_ed25519.*)$", re.I)
_SECRET_LINE = re.compile(
    r"^(\s*[\w.-]*(password|passwd|secret|token|api_key|apikey|access_key|private_key)[\w.-]*\s*:\s*)(?!\$\{)(\S.*)$",
    re.I,
)
Runner = Callable[[List[str], Path, float], str]


class ToolError(Exception):
    """A tool call the model got wrong: the message goes back to the model as the tool result."""


def _clean(text: str, root: Path) -> str:
    """Same as the training data: CRLF -> LF, the project path -> ".", trailing spaces trimmed."""
    out = text.replace("\r\n", "\n")
    config = root / "pskit.yml"
    for form in {str(config), str(config).replace("\\", "/")}:
        out = out.replace(form, "pskit.yml")
    for form in {str(root), str(root).replace("\\", "/")}:
        out = out.replace(form, ".")
    return "\n".join(line.rstrip() for line in out.split("\n")).strip("\n")


def _pskit(argv: List[str], cwd: Path, timeout: float) -> str:
    env = dict(os.environ)
    env.update({"PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8", "PSKIT_LOG_FORMAT": "text"})
    env.pop("PSKIT_DEBUG", None)
    try:
        proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
            [sys.executable, "-m", "py_serverless_kit", *argv], cwd=str(cwd), env=env, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return f"error: `pskit {argv[0]}` did not finish within {int(timeout)} s"
    return proc.stdout.decode("utf-8", errors="replace")


def truncate(text: str, limit: int = MAX_OUTPUT) -> str:
    if len(text) <= limit:
        return text
    head, tail = text[: limit * 2 // 3], text[-limit // 3:]
    return f"{head}\n... ({len(text) - len(head) - len(tail)} characters cut) ...\n{tail}"


def redact(text: str) -> str:
    """Literal secrets in pskit.yml lines (``password: hunter2``) -> ``<redacted>``; ``${env:...}`` stays."""
    return "\n".join(_SECRET_LINE.sub(r"\1<redacted>", line) for line in text.split("\n"))


_INVENTED = re.compile(r"unknown option|Extra inputs are not permitted", re.I)


def _touches(line: str, dotted: str) -> bool:
    """The validate line is about ``dotted`` or a key under it / above it."""
    m = re.search(r"\[([\w.\-]+)\]|^\s*-\s*([\w.\-]+):", line)
    where = (m.group(1) or m.group(2)) if m else ""
    return bool(where) and (where.startswith(dotted) or dotted.startswith(where))


def _exists(cfg: Any, parts: List[str]) -> bool:
    node = cfg
    for part in parts:
        if isinstance(node, list) and part.isdigit() and int(part) < len(node):
            node = node[int(part)]
        elif isinstance(node, dict) and part in node:
            node = node[part]
        else:
            return False
    return True


def set_dotted(cfg: Any, dotted: str, value: Any) -> None:
    """Dots separate keys, a number selects a list item, ``None`` deletes the key (as in training)."""
    parts = [p for p in str(dotted).split(".") if p != ""]
    if not parts:
        raise ToolError("error: path is empty")
    if value is None and not _exists(cfg, parts):
        raise ToolError(f"error: {dotted} doesn't exist in pskit.yml, so there is nothing to delete")
    node = cfg
    for i, part in enumerate(parts[:-1]):
        nxt = parts[i + 1]
        if isinstance(node, list):
            if not part.isdigit() or int(part) >= len(node):
                raise ToolError(f"error: {'.'.join(parts[: i + 1])} is not an item of the list")
            node = node[int(part)]
            continue
        if not isinstance(node, dict):
            raise ToolError(f"error: {'.'.join(parts[:i])} is not a mapping")
        if part not in node or node[part] is None:
            node[part] = [] if nxt.isdigit() else {}
        node = node[part]
    last = parts[-1]
    if isinstance(node, list):
        if not last.isdigit():
            raise ToolError(f"error: {dotted}: a list item needs a number")
        idx = int(last)
        if value is None:
            if idx < len(node):
                node.pop(idx)
        elif idx == len(node):
            node.append(value)
        elif idx < len(node):
            node[idx] = value
        else:
            raise ToolError(f"error: {dotted}: the list has {len(node)} item(s)")
    elif isinstance(node, dict):
        if value is None:
            node.pop(last, None)
        else:
            node[last] = value
    else:
        raise ToolError(f"error: {'.'.join(parts[:-1])} is not a mapping")


class ProjectTools:
    """The project tools for one studio project. ``provider`` / ``stage`` are the studio's current target."""

    def __init__(self, root: Path, runner: Optional[Runner] = None) -> None:
        self.root = Path(root).resolve()
        self.runner: Runner = runner or _pskit
        self.changed: List[str] = []  # files written by set_config / write_file during the current turn

    # ------------------------------------------------------------------ dispatch
    def run(self, name: str, args: Dict[str, Any], provider: str, stage: str) -> str:
        if not isinstance(args, dict):
            return "error: arguments must be a JSON object"
        try:
            if name == "search_docs":
                return search()(str(args.get("query") or ""))[0]
            if name == "get_project":
                return self.get_project()
            if name == "read_file":
                return self.read_file(str(args.get("path") or ""))
            if name in ("get_validation", "validate"):
                return self.validate(str(args.get("provider") or provider), stage)
            if name == "set_config":
                if "path" not in args or "value" not in args:
                    return "error: set_config needs path and value"
                return self.set_config(str(args["path"]), args["value"], provider, stage)
            if name == "write_file":
                return self.write_file(str(args.get("path") or ""), args.get("content"))
            if name == "invoke_local":
                return self.invoke(args, provider, stage)
        except ToolError as exc:
            return str(exc)
        except StudioError as exc:
            return f"error: {exc.message}"
        return f"error: unknown tool {name}"

    # ------------------------------------------------------------------ reading
    def _config(self) -> Path:
        path = project.config_path(self.root)
        if path is None:
            raise ToolError("error: this folder has no pskit.yml yet (create the project on the Overview page)")
        return path

    def file_list(self) -> List[str]:
        return [e["path"] for e in files.tree(self.root)["entries"] if e["type"] == "file"]

    def get_project(self) -> str:
        text = self._config().read_text(encoding="utf-8").replace("\r\n", "\n").rstrip("\n")
        return truncate(redact(text) + "\nfiles:\n" + "\n".join(self.file_list()))

    def _safe(self, rel: str, *, must_exist: bool) -> Path:
        clean = rel.strip().replace("\\", "/")
        if _SECRET_FILE.search(clean):
            raise ToolError(f"error: {clean} may hold secrets; Hana does not read or write it")
        return files.resolve(self.root, clean, must_exist=must_exist)

    def read_file(self, rel: str, max_lines: int = 200) -> str:
        path = self._safe(rel, must_exist=True)
        text = files.read_file(self.root, path.relative_to(self.root).as_posix())["text"]
        lines = text.replace("\r\n", "\n").split("\n")
        if lines and lines[-1] == "":
            lines = lines[:-1]
        out = "\n".join(lines[:max_lines])
        if PurePosixPath(rel).name in ("pskit.yml", "pskit.yaml"):
            out = redact(out)
        return truncate(out)

    def validate(self, provider: str, stage: str) -> str:
        config = self._config()
        argv = ["validate", "-c", config.name]
        if provider:
            argv += ["-p", provider]
        if stage:
            argv += ["-s", stage]
        return truncate(_clean(self.runner(argv, self.root, 300), self.root))

    # ------------------------------------------------------------------ changing
    def set_config(self, dotted: str, value: Any, provider: str, stage: str) -> str:
        config = self._config()
        original = config.read_bytes()
        raw, issues = project.parse_text(original.decode("utf-8"))
        if raw is None:
            problems = "; ".join(i.get("message", "") for i in issues) or "it is not valid YAML"
            raise ToolError(f"error: pskit.yml can't be read: {problems}")
        before = self.validate(provider, stage)
        set_dotted(raw, dotted, value)
        project.save_project(self.root, raw, force=True)  # backup in .pskit/studio/backups/, then write
        after = self.validate(provider, stage)
        # A key pskit doesn't have (an invented option): undo, and say so, instead of "ok" with a buried warning.
        known = set(before.splitlines())
        invented = [line.strip() for line in after.splitlines() if line not in known and _INVENTED.search(line)
                    and _touches(line, dotted)]
        if invented:
            config.write_bytes(original)
            return (f"error: {dotted} is not a pskit.yml option ({invented[0]}); the change was undone. "
                    "Use search_docs to find the right key.")
        self.changed.append(config.name)
        return "ok\n" + after

    def write_file(self, rel: str, content: Any) -> str:
        if not isinstance(content, str):
            raise ToolError("error: content must be a string")
        path = self._safe(rel, must_exist=False)
        rel_path = path.relative_to(self.root).as_posix()
        files.write_file(self.root, rel_path, content, force=True)
        self.changed.append(rel_path)
        return "ok"

    def invoke(self, args: Dict[str, Any], provider: str, stage: str) -> str:
        function = str(args.get("function") or "")
        if not function:
            raise ToolError("error: invoke_local needs function")
        argv = ["invoke", "-c", self._config().name, "-f", function]
        if provider:
            argv += ["-p", provider]
        if stage:
            argv += ["-s", stage]
        if args.get("type"):
            argv += ["-t", str(args["type"])]
        data = args.get("data")
        if data is not None:
            argv += ["-d", data if isinstance(data, str) else json.dumps(data)]
        if args.get("method"):
            argv += ["--method", str(args["method"])]
        if args.get("path"):
            argv += ["--path", str(args["path"])]
        return truncate(_clean(self.runner(argv, self.root, 120), self.root))
