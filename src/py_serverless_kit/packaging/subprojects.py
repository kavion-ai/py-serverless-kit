"""Function sub-projects: a function whose handler lives in its own folder with its own dependencies.

::

    functions/
      resize/
        __init__.py
        handler.py          # handler: functions.resize.handler.main
        requirements.txt    # only what resize needs (Pillow, ...)
      report/
        index.js            # handler: functions.report.index.main
        package.json        # only what report needs

The folder that holds a function's ``requirements.txt`` (Python) or ``package.json`` (Node.js), found by walking up
from its handler module to ``package.source`` (not included), is that function's sub-project. Its requirements are
added to the bundle on every cloud (code is unchanged between clouds). On premises with
``provider.options.placement``, each server gets only the requirements of the functions placed on it, and the
folders of functions placed elsewhere are left out of its bundle. Node.js sub-projects get their own
``node_modules`` inside their folder, so each function resolves its own package versions.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

PYTHON_MARKER = "requirements.txt"
NODE_MARKER = "package.json"


def marker(language: str) -> str:
    return NODE_MARKER if language == "node" else PYTHON_MARKER


def function_dir(source: Path, handler: str, language: str = "python") -> Optional[Path]:
    """The sub-project folder of a handler (below ``source``), or None when it uses the project's dependencies."""
    source = Path(source).resolve()
    module = str(handler).replace(":", ".").rsplit(".", 1)[0]
    parts = [p for p in module.split(".") if p]
    if not parts:
        return None
    package = source.joinpath(*parts)
    folder = package if package.is_dir() else source.joinpath(*parts[:-1])
    name = marker(language)
    while True:
        try:
            folder.relative_to(source)
        except ValueError:
            return None
        if folder == source:
            return None
        if (folder / name).is_file():
            return folder
        folder = folder.parent


def function_dirs(source: Path, functions: Dict[str, Any], language: str = "python") -> Dict[str, Path]:
    """``{function: sub-project folder}`` for the enabled functions that have one."""
    out: Dict[str, Path] = {}
    for name, fn in functions.items():
        if not getattr(fn, "enabled", True):
            continue
        folder = function_dir(source, str(getattr(fn, "handler", "") or ""), language)
        if folder is not None:
            out[name] = folder
    return out


def merge_requirements(*groups: Iterable[str]) -> List[str]:
    """Requirement lines in order, each once (identical lines only: pip resolves the rest, or explains a
    conflict)."""
    seen = set()
    out: List[str] = []
    for group in groups:
        for line in group:
            key = " ".join(line.split()).lower()
            if key and key not in seen:
                seen.add(key)
                out.append(line)
    return out


def function_requirements(source: Path, functions: Dict[str, Any], names: Optional[Iterable[str]] = None) -> List[str]:
    """The requirements of the Python sub-projects of ``names`` (default: every function)."""
    from .builder import read_requirements

    wanted = set(names) if names is not None else None
    folders = function_dirs(source, functions, "python")
    lists = [read_requirements(folder / PYTHON_MARKER) for name, folder in sorted(folders.items())
             if wanted is None or name in wanted]
    return merge_requirements(*lists)


def excluded_dirs(source: Path, functions: Dict[str, Any], keep: Iterable[str], language: str = "python") -> List[str]:
    """Sub-project folders (relative, posix) used only by functions not in ``keep``: left out of a server's bundle."""
    folders = function_dirs(source, functions, language)
    keep = set(keep)
    kept = {folders[n] for n in keep if n in folders}
    source = Path(source).resolve()
    out = set()
    for name, folder in folders.items():
        if name in keep or folder in kept or any(_inside(k, folder) for k in kept):
            continue
        out.add(folder.relative_to(source).as_posix())
    return sorted(out)


def _inside(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False
