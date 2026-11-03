"""Real tool outputs for Hana's stage-2 task dataset (12-task-dataset-prompt.md, section 3).

Every validate / invoke / set_config / get_project / read_file result in a task conversation must be the real
output of pskit on a real scratch project. This script makes those projects and runs pskit there. It never
deploys, plans, removes or contacts a cloud: it only runs `pskit validate` and `pskit invoke` (local).

Scratch projects live in ai-agent/training/scratch/<name>/ (git-ignored by ai-agent/training/.gitignore).

Run from anywhere with the repo's venv python (Windows: .venv\\Scripts\\python.exe, Linux/macOS: .venv/bin/python):

    PY=.venv/Scripts/python.exe ; T=ai-agent/training/tools/run_tool.py

    # 1. create a project: copy an example (pskit.yml, app/, requirements.txt) and/or write files
    $PY $T new demo --from examples/04-queue-worker
    $PY $T new demo2 --yml my.yml --file app/__init__.py= --file app/jobs.py=@local_jobs.py
        (--file REL=TEXT writes TEXT, REL=@PATH copies a local file, REL= writes an empty file)

    # 2. get the exact text a tool returns
    $PY $T project  demo                         # get_project  -> pskit.yml text + "files:" list
    $PY $T read     demo app/worker.py           # read_file
    $PY $T validate demo -p gcp [-s prod]        # get_validation / validate
    $PY $T set      demo functions.enqueue.timeout 20 -p aws        # set_config: applies it, "ok" + validate
    $PY $T set      demo functions.worker.events.0.queue.batch_size null   (null deletes the key)
    $PY $T write    demo app/new.py @local.py    # write_file (prints "ok"); TEXT or @PATH
    $PY $T invoke   demo -f enqueue -t http --method POST --path /jobs -d '{"kind": "email"}'
    $PY $T docs     docs/events.md queue [--start "TEXT"] [--end "TEXT"] [--words 220]   # search_docs excerpt
    $PY $T clean    demo                         # delete the scratch project

    Add --json to any command to print the output as a JSON string (ready to paste into a JSONL line).

Python API (used by tools/assemble.py):  Scratch(name).create(base=..., files={...}); .validate(provider, stage);
.invoke(function, type=..., data=..., method=..., path=..., provider=...); .set_config(path, value, provider, stage);
.write_file(rel, text); .read_file(rel); .get_project(); and doc_excerpt(path, anchor, start=, end=, words=).

Output rules (same as studio): stdout and stderr are merged in the order pskit prints them; the absolute scratch
path, if pskit prints it, is replaced by "." (and the config path by "pskit.yml"); trailing whitespace is trimmed.
`invoke` log lines keep pskit's real timestamps. pskit's own files in tracebacks are shown under "site-packages"
instead of this checkout's path.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

TRAIN = Path(__file__).resolve().parents[1]          # ai-agent/training
REPO = TRAIN.parents[1]                               # repository root
SCRATCH = TRAIN / "scratch"
HEADINGS = TRAIN / "knowledge" / "docs_headings.json"
SKIP_DIRS = {"__pycache__", ".pskit", ".venv", "node_modules", ".pytest_cache", ".git"}
COPY_FROM_EXAMPLE = ("pskit.yml", "requirements.txt", "app", "src", "package.json", "tsconfig.json", ".env.example")


def venv_python() -> str:
    for rel in (".venv/Scripts/python.exe", ".venv/bin/python"):
        p = REPO / rel
        if p.exists():
            return str(p)
    return sys.executable


def _clean(text: str, root: Path) -> str:
    out = text.replace("\r\n", "\n")
    for form in {str(root / "pskit.yml"), str(root / "pskit.yml").replace("\\", "/")}:
        out = out.replace(form, "pskit.yml")
    for form in {str(root), str(root).replace("\\", "/")}:
        out = out.replace(form, ".")
    # pskit's own files in tracebacks: show them where an installed pskit lives, not this checkout's path
    src = REPO / "src"
    for form, repl in ((str(src), "site-packages"), (str(src).replace("\\", "/"), "site-packages")):
        out = out.replace(form, repl)
    return "\n".join(line.rstrip() for line in out.split("\n")).strip("\n")


def _yaml():
    import yaml  # pyyaml ships with pskit

    return yaml


def dump_yaml(data: Any) -> str:
    return _yaml().safe_dump(data, sort_keys=False, allow_unicode=True, default_flow_style=False, width=110)


class Scratch:
    def __init__(self, name: str) -> None:
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", name):
            raise SystemExit(f"bad scratch name {name!r}")
        self.name = name
        self.root = SCRATCH / name

    # ---------------------------------------------------------------- files
    def create(self, base: Optional[str] = None, files: Optional[Dict[str, str]] = None, fresh: bool = True) -> "Scratch":
        if fresh and self.root.exists():
            shutil.rmtree(self.root)
        self.root.mkdir(parents=True, exist_ok=True)
        if base:
            src = (REPO / base).resolve()
            if not (src / "pskit.yml").exists():
                raise SystemExit(f"{base} has no pskit.yml")
            for item in COPY_FROM_EXAMPLE:
                p = src / item
                if p.is_dir():
                    shutil.copytree(p, self.root / item, ignore=shutil.ignore_patterns(*SKIP_DIRS, "*.pyc"))
                elif p.is_file():
                    shutil.copy2(p, self.root / item)
        for rel, text in (files or {}).items():
            self.write_file(rel, text)
        return self

    def _path(self, rel: str) -> Path:
        p = (self.root / rel).resolve()
        if self.root.resolve() not in p.parents and p != self.root.resolve():
            raise SystemExit(f"{rel} is outside the project")
        return p

    def write_file(self, rel: str, text: str) -> str:
        p = self._path(rel)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(text.encode("utf-8"))
        return "ok"

    def read_file(self, rel: str, max_lines: int = 200) -> str:
        lines = self._path(rel).read_text(encoding="utf-8").replace("\r\n", "\n").split("\n")
        if lines and lines[-1] == "":
            lines = lines[:-1]
        return "\n".join(lines[:max_lines])

    def files(self) -> List[str]:
        out = []
        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
            for f in sorted(filenames):
                if f.endswith(".pyc"):
                    continue
                out.append(Path(dirpath, f).relative_to(self.root).as_posix())
        return sorted(out)

    def get_project(self) -> str:
        text = self.read_file("pskit.yml", max_lines=10_000)
        return text + "\nfiles:\n" + "\n".join(self.files())

    # ---------------------------------------------------------------- pskit
    def _run(self, args: List[str]) -> str:
        env = dict(os.environ)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        env.pop("PSKIT_DEBUG", None)
        proc = subprocess.run(
            [venv_python(), "-m", "py_serverless_kit", *args],
            cwd=str(self.root), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=300,
        )
        return _clean(proc.stdout.decode("utf-8", errors="replace"), self.root)

    def validate(self, provider: Optional[str] = None, stage: Optional[str] = None) -> str:
        args = ["validate", "-c", "pskit.yml"]
        if provider:
            args += ["-p", provider]
        if stage:
            args += ["-s", stage]
        return self._run(args)

    def invoke(self, function: str, type: Optional[str] = None, data: Any = None, method: Optional[str] = None,
               path: Optional[str] = None, provider: Optional[str] = None, stage: Optional[str] = None,
               headers: Optional[List[str]] = None) -> str:
        args = ["invoke", "-c", "pskit.yml", "-f", function]
        if provider:
            args += ["-p", provider]
        if stage:
            args += ["-s", stage]
        if type:
            args += ["-t", type]
        if data is not None:
            args += ["-d", data if isinstance(data, str) else json.dumps(data)]
        if method:
            args += ["--method", method]
        if path:
            args += ["--path", path]
        for h in headers or []:
            args += ["-H", h]
        return self._run(args)

    def set_config(self, dotted: str, value: Any, provider: Optional[str] = None, stage: Optional[str] = None) -> str:
        yaml = _yaml()
        cfg = yaml.safe_load(self.read_file("pskit.yml", max_lines=10_000)) or {}
        set_dotted(cfg, dotted, value)
        self.write_file("pskit.yml", dump_yaml(cfg))
        return "ok\n" + self.validate(provider, stage)

    def clean(self) -> None:
        if self.root.exists():
            shutil.rmtree(self.root)


def set_dotted(cfg: Any, dotted: str, value: Any) -> None:
    """studio's set_config: dots separate keys, a number selects a list item, None deletes the key."""
    parts = dotted.split(".")
    node = cfg
    for i, part in enumerate(parts[:-1]):
        nxt = parts[i + 1]
        if isinstance(node, list):
            node = node[int(part)]
            continue
        if part not in node or node[part] is None:
            node[part] = [] if nxt.isdigit() else {}
        node = node[part]
    last = parts[-1]
    if isinstance(node, list):
        idx = int(last)
        if value is None:
            node.pop(idx)
        elif idx == len(node):
            node.append(value)
        else:
            node[idx] = value
    elif value is None:
        node.pop(last, None)
    else:
        node[last] = value


# -------------------------------------------------------------------- search_docs excerpts


def _anchor_map() -> Dict[str, Dict[str, int]]:
    data = json.loads(HEADINGS.read_text(encoding="utf-8"))
    return {f["path"]: {h["anchor"]: h["line"] for h in f.get("headings", [])} for f in data["files"]}


def slug(title: str) -> str:
    s = title.strip().lower()
    s = re.sub(r"[^\w\- ]", "", s)
    return s.replace(" ", "-")


def doc_excerpt(path: str, anchor: str, start: Optional[str] = None, end: Optional[str] = None,
                words: int = 220) -> str:
    """Verbatim section of a docs file: from heading `anchor` (or from the line containing `start`) up to the
    next heading of the same or higher level (or the line containing `end`), cut at a line boundary so it stays
    under `words` words. Output: "[path#anchor]\\n<text>"."""
    lines = (REPO / path).read_text(encoding="utf-8").replace("\r\n", "\n").split("\n")
    headings = _anchor_map().get(path, {})
    if anchor not in headings:
        raise SystemExit(f"{path} has no heading #{anchor}; known: {', '.join(sorted(headings))[:600]}")
    first = headings[anchor] - 1
    level = len(lines[first]) - len(lines[first].lstrip("#"))
    stop = len(lines)
    in_fence = False
    for j in range(first + 1, len(lines)):
        if lines[j].startswith("```"):
            in_fence = not in_fence
        if not in_fence and lines[j].startswith("#"):
            lv = len(lines[j]) - len(lines[j].lstrip("#"))
            if lv <= level and lines[j][lv:lv + 1] == " ":
                stop = j
                break
    body = lines[first:stop]
    if start:
        k = next((i for i, l in enumerate(body) if start in l), None)
        if k is None:
            raise SystemExit(f"start text {start!r} not in {path}#{anchor}")
        body = body[k:]
    if end:
        k = next((i for i, l in enumerate(body) if end in l), None)
        if k is None:
            raise SystemExit(f"end text {end!r} not in {path}#{anchor}")
        body = body[:k + 1]
    out: List[str] = []
    count = 0
    fence = False
    for l in body:
        n = len(l.split())
        if count + n > words and out and not fence:
            break
        out.append(l)
        count += n
        if l.startswith("```"):
            fence = not fence
    if fence:  # never cut inside a code block
        while out and not out[-1].startswith("```"):
            out.pop()
        if out:
            out.pop()
    while out and out[-1].strip() in ("", "---"):
        out.pop()
    text = "\n".join(out).strip("\n")
    return f"[{path}#{anchor}]\n{text}"


# -------------------------------------------------------------------- CLI


def _value(text: str) -> Any:
    try:
        return json.loads(text)
    except ValueError:
        return text


def _text_arg(text: str) -> str:
    if text.startswith("@"):
        return Path(text[1:]).read_text(encoding="utf-8")
    return text


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Real tool outputs for Hana's task dataset.")
    ap.add_argument("--json", action="store_true", help="print the output as a JSON string")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("new")
    p.add_argument("name")
    p.add_argument("--from", dest="base")
    p.add_argument("--yml", help="local pskit.yml to use")
    p.add_argument("--file", action="append", default=[], help="REL=TEXT or REL=@PATH")
    for name in ("project", "clean"):
        sub.add_parser(name).add_argument("name")
    p = sub.add_parser("read")
    p.add_argument("name")
    p.add_argument("rel")
    p = sub.add_parser("write")
    p.add_argument("name")
    p.add_argument("rel")
    p.add_argument("text")
    p = sub.add_parser("validate")
    p.add_argument("name")
    p.add_argument("-p", "--provider")
    p.add_argument("-s", "--stage")
    p = sub.add_parser("set")
    p.add_argument("name")
    p.add_argument("path")
    p.add_argument("value", help="JSON value (null deletes); non-JSON text is a string")
    p.add_argument("-p", "--provider")
    p.add_argument("-s", "--stage")
    p = sub.add_parser("invoke")
    p.add_argument("name")
    p.add_argument("-f", "--function", required=True)
    p.add_argument("-t", "--type")
    p.add_argument("-d", "--data")
    p.add_argument("--method")
    p.add_argument("--path")
    p.add_argument("-H", "--header", action="append", default=[])
    p.add_argument("-p", "--provider")
    p.add_argument("-s", "--stage")
    p = sub.add_parser("docs")
    p.add_argument("path")
    p.add_argument("anchor")
    p.add_argument("--start")
    p.add_argument("--end")
    p.add_argument("--words", type=int, default=220)
    a = ap.parse_args(argv)

    out = ""
    if a.cmd == "new":
        files: Dict[str, str] = {}
        if a.yml:
            files["pskit.yml"] = Path(a.yml).read_text(encoding="utf-8")
        for spec in a.file:
            rel, _, text = spec.partition("=")
            files[rel] = _text_arg(text)
        s = Scratch(a.name).create(base=a.base, files=files)
        out = f"created {s.root}\nfiles:\n" + "\n".join(s.files())
    elif a.cmd == "project":
        out = Scratch(a.name).get_project()
    elif a.cmd == "clean":
        Scratch(a.name).clean()
        out = "removed"
    elif a.cmd == "read":
        out = Scratch(a.name).read_file(a.rel)
    elif a.cmd == "write":
        out = Scratch(a.name).write_file(a.rel, _text_arg(a.text))
    elif a.cmd == "validate":
        out = Scratch(a.name).validate(a.provider, a.stage)
    elif a.cmd == "set":
        out = Scratch(a.name).set_config(a.path, _value(a.value), a.provider, a.stage)
    elif a.cmd == "invoke":
        out = Scratch(a.name).invoke(a.function, a.type, a.data, a.method, a.path, a.provider, a.stage, a.header)
    elif a.cmd == "docs":
        out = doc_excerpt(a.path, a.anchor, a.start, a.end, a.words)
    text = json.dumps(out, ensure_ascii=False) if a.json else out
    sys.stdout.buffer.write((text + "\n").encode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
