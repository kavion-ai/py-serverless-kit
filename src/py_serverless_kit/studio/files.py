"""Project file access for the studio's code editor, confined to the project root."""

from __future__ import annotations

import os
import uuid
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional

from .project import StudioError

EXCLUDED = {
    ".pskit",
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".idea",
    ".tox",
}
MAX_FILE = 1024 * 1024
MAX_ENTRIES = 5000
_LANGUAGES = {
    ".py": "python",
    ".yml": "yaml",
    ".yaml": "yaml",
    ".json": "json",
    ".md": "markdown",
    ".txt": "text",
    ".toml": "toml",
    ".cfg": "ini",
    ".ini": "ini",
    ".js": "javascript",
    ".ts": "typescript",
    ".html": "html",
    ".css": "css",
    ".sh": "shell",
    ".env": "shell",
    ".tf": "hcl",
}


def language(path: str) -> str:
    name = PurePosixPath(path).name.lower()
    if name == "dockerfile":
        return "dockerfile"
    return _LANGUAGES.get(PurePosixPath(name).suffix, "text")


def resolve(root: Path, rel: Any, *, must_exist: bool = True) -> Path:
    """Map a client path to a file under ``root``; raise StudioError for anything else."""
    text = str(rel or "").strip().replace("\\", "/")
    if not text or "\x00" in text:
        raise StudioError(400, "path is required")
    if text.startswith("/") or (len(text) > 1 and text[1] == ":") or text.startswith("~"):
        raise StudioError(400, "path must be relative to the project")
    parts = [p for p in text.split("/") if p not in ("", ".")]
    if not parts or any(p == ".." for p in parts):
        raise StudioError(400, "path must stay inside the project")
    if any(p in EXCLUDED for p in parts):
        raise StudioError(403, f"{parts[0] if parts[0] in EXCLUDED else 'that folder'} is not editable here")
    base = root.resolve()
    target = base.joinpath(*parts)
    real = target.resolve()
    try:
        real.relative_to(base)
    except ValueError:
        raise StudioError(403, "path resolves outside the project (symlink?)") from None
    if must_exist and not real.is_file():
        raise StudioError(404, f"no such file: {'/'.join(parts)}")
    return real


def tree(root: Path) -> Dict[str, Any]:
    base = root.resolve()
    entries: List[Dict[str, Any]] = []
    truncated = False
    for current, dirs, files in os.walk(base, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDED and not d.startswith(".pskit-studio"))
        folder = Path(current)
        rel_dir = folder.relative_to(base).as_posix()
        if rel_dir != ".":
            entries.append({"path": rel_dir, "type": "dir", "size": 0})
        for name in sorted(files):
            if name.startswith(".pskit-studio-draft-"):
                continue
            path = folder / name
            try:
                size = path.stat().st_size
            except OSError:
                continue
            entries.append({"path": path.relative_to(base).as_posix(), "type": "file", "size": size})
        if len(entries) > MAX_ENTRIES:
            truncated = True
            break
    entries.sort(key=lambda e: e["path"])
    return {"entries": entries[:MAX_ENTRIES], "truncated": truncated}


def read_file(root: Path, rel: Any) -> Dict[str, Any]:
    path = resolve(root, rel)
    stat = path.stat()
    if stat.st_size > MAX_FILE:
        raise StudioError(413, f"file is larger than {MAX_FILE // 1024} KiB")
    data = path.read_bytes()
    if b"\x00" in data:
        raise StudioError(415, "binary files cannot be edited here")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise StudioError(415, "file is not UTF-8 text") from None
    rel_path = path.relative_to(root.resolve()).as_posix()
    return {"path": rel_path, "text": text, "mtime": stat.st_mtime, "language": language(rel_path)}


def write_file(root: Path, rel: Any, text: Any, mtime: Optional[float] = None, force: bool = False) -> Dict[str, Any]:
    if not isinstance(text, str):
        raise StudioError(400, "text must be a string")
    data = text.replace("\r\n", "\n").encode("utf-8")
    if len(data) > MAX_FILE:
        raise StudioError(413, f"file is larger than {MAX_FILE // 1024} KiB")
    path = resolve(root, rel, must_exist=False)
    if path.is_dir():
        raise StudioError(400, "path is a directory")
    if path.is_file():
        current = path.stat().st_mtime
        if mtime is not None and not force and abs(current - float(mtime)) > 0.0005:
            raise StudioError(409, "the file changed on disk since it was opened", code="conflict", mtime=current)
        if b"\x00" in path.read_bytes()[:8192]:
            raise StudioError(415, "binary files cannot be edited here")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex[:8]}.tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)
    return {"path": path.relative_to(root.resolve()).as_posix(), "mtime": path.stat().st_mtime}
