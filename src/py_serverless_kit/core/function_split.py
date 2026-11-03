"""Move a function that shares a code file with others into its own sub-project folder.

``pskit function split get-item`` (and the studio's "Own folder" button) turns::

    app/handlers.py              # hello, get_item, create_item side by side
    requirements.txt

into::

    app/handlers.py              # hello, create_item
    functions/get_item/__init__.py
    functions/get_item/handler.py        # get_item, the helpers and imports it uses
    functions/get_item/requirements.txt  # the project requirements its imports name

and points ``functions.get-item.handler`` at ``functions.get_item.handler.get_item``. With
``provider.options.placement`` the server that runs get-item then gets only that folder and its requirements
(``packaging/subprojects.py``); other servers do not get its code.

Helpers used by the function are copied (other functions may still use them); the function itself is removed from
the shared file unless something left there still calls it. Python only: a Node.js handler is moved by hand.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

import yaml

from ..packaging.subprojects import PYTHON_MARKER, function_dir

_HANDLER_RE = re.compile(r"^([A-Za-z_][\w]*(?:\.[A-Za-z_][\w]*)*)[.:]([A-Za-z_]\w*)$")
# Import name -> distribution name, for the common ones whose names differ.
_DISTRIBUTIONS = {"pil": "pillow", "yaml": "pyyaml", "cv2": "opencv-python", "sklearn": "scikit-learn",
                  "bs4": "beautifulsoup4", "dateutil": "python-dateutil", "jwt": "pyjwt", "dotenv": "python-dotenv",
                  "google": "google-cloud", "magic": "python-magic", "docx": "python-docx"}
_REQ_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


class SplitError(ValueError):
    pass


def _config_path(root: Path) -> Path:
    for name in ("pskit.yml", "pskit.yaml"):
        if (root / name).is_file():
            return root / name
    raise SplitError("no pskit.yml in this folder")


def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def folder_name(function: str) -> str:
    return re.sub(r"\W", "_", function.replace("-", "_")).lower()


def plan(root: Path, function: str) -> Dict[str, Any]:
    """What a split would do, without writing: ``{function, from, to, handler, requirements, keeps, shared}``."""
    return _split(Path(root), function, write=False)


def split(root: Path, function: str) -> Dict[str, Any]:
    return _split(Path(root), function, write=True)


def shared_functions(root: Path, functions: Dict[str, Any], source: Path) -> Dict[str, List[str]]:
    """``{code file: [functions]}`` for files that hold the handlers of more than one function and are not a
    sub-project (so every server of a placement gets all of them)."""
    out: Dict[str, List[str]] = {}
    for name, fn in functions.items():
        if not getattr(fn, "enabled", True):
            continue
        handler = str(getattr(fn, "handler", "") or "")
        if function_dir(source, handler) is not None:
            continue
        match = _HANDLER_RE.match(handler)
        if not match:
            continue
        out.setdefault(match.group(1), []).append(name)
    return {module: sorted(names) for module, names in out.items() if len(names) > 1}


def shared_in_project(root: Path) -> Dict[str, List[str]]:
    """``shared_functions`` of the project in ``root`` (pskit.yml as written)."""
    raw = yaml.safe_load(_config_path(Path(root)).read_text("utf-8")) or {}
    package = raw.get("package") or {}
    source = (Path(root) / str(package.get("source") or ".")).resolve() if isinstance(package, dict) else Path(root)
    functions = {k: _Fn(v) for k, v in (raw.get("functions") or {}).items()}
    return shared_functions(Path(root), functions, source)


class _Fn:
    def __init__(self, body: Any) -> None:
        body = body if isinstance(body, dict) else {}
        self.handler = str(body.get("handler") or "")
        self.enabled = body.get("enabled", True) is not False


def _split(root: Path, function: str, write: bool) -> Dict[str, Any]:
    path = _config_path(root)
    raw = yaml.safe_load(path.read_text("utf-8")) or {}
    functions = raw.get("functions") or {}
    if function not in functions:
        raise SplitError(f"no function {function!r} in {path.name} (functions: {', '.join(functions) or 'none'})")
    runtime = str((raw.get("provider") or {}).get("runtime") or "")
    if runtime.startswith("nodejs"):
        raise SplitError("moving a Node.js handler is not automated yet: move it to functions/<name>/index.js with a"
                         " package.json and update its handler in pskit.yml")
    handler = str((functions[function] or {}).get("handler") or "")
    match = _HANDLER_RE.match(handler)
    if not match:
        raise SplitError(f"function {function} has no handler like package.module.function ({handler!r})")
    module, func = match.group(1), match.group(2)
    package = raw.get("package") or {}
    source = (root / str(package.get("source") or ".")).resolve() if isinstance(package, dict) else root.resolve()
    if function_dir(source, handler) is not None:
        raise SplitError(f"{function} already has its own folder ({function_dir(source, handler)})")
    parts = module.split(".")
    file = source.joinpath(*parts, "__init__.py")
    if not file.is_file():
        file = source.joinpath(*parts[:-1], parts[-1] + ".py")
    if not file.is_file():
        raise SplitError(f"cannot find the code of {handler} ({file.relative_to(root).as_posix()})")
    text = file.read_text("utf-8")
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        raise SplitError(f"{file.name} has a syntax error at line {exc.lineno}; fix it first") from None
    target = next((n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == func),
                  None)
    if target is None:
        raise SplitError(f"{file.relative_to(root).as_posix()} has no function {func}")

    folder = folder_name(function)
    dest = source / "functions" / folder
    if (dest / "handler.py").exists():
        raise SplitError(f"{dest.relative_to(root).as_posix()}/handler.py already exists")
    lines = text.splitlines()
    package_parts = parts if file.name == "__init__.py" else parts[:-1]
    imports, helpers = _needed(tree, target)
    used = set().union(*(_uses(n) for n in helpers + [target]))
    body: List[str] = ['"""' + f"Function {function} (moved from {file.relative_to(root).as_posix()})." + '"""', ""]
    body += [_absolute(_import_code(node, used), node, package_parts) for node in imports]
    if imports:
        body.append("")
    for node in helpers + [target]:
        body += ["", _segment(lines, node), ""]
    new_code = "\n".join(body).rstrip() + "\n"
    new_code = re.sub(r"\n{4,}", "\n\n\n", new_code)

    third_party = _third_party(imports, source)
    reqs, unknown = _matching_requirements(root, third_party)
    req_text = ("# Dependencies of this function only. pskit installs them with the function: on premises with\n"
                "# provider.options.placement only on the server this function runs on.\n")
    req_text += "".join(f"{line}\n" for line in reqs)
    if unknown:
        req_text += f"# Also imported, add its package if it is not in the standard library: {', '.join(unknown)}\n"

    still_used = _used_elsewhere(tree, target)
    new_handler = f"functions.{folder}.handler.{func}"
    result = {"function": function, "from": file.relative_to(root).as_posix(),
              "to": (dest / "handler.py").relative_to(root).as_posix(), "handler": new_handler,
              "requirements": reqs, "unknown_imports": unknown, "helpers": [_name(n) for n in helpers],
              "kept_in_source": still_used}
    if not write:
        return result
    for pkg in (source / "functions", dest):
        pkg.mkdir(parents=True, exist_ok=True)
        init = pkg / "__init__.py"
        if not init.exists():
            init.write_bytes(b"")
    (dest / "handler.py").write_bytes(new_code.encode("utf-8"))
    if not (dest / PYTHON_MARKER).exists():
        (dest / PYTHON_MARKER).write_bytes(req_text.encode("utf-8"))
    if not still_used:
        file.write_bytes(_without(lines, tree, target).encode("utf-8"))
    _set_handler(path, function, handler, new_handler)
    return result


def _import_code(node: ast.stmt, used: Set[str]) -> str:
    """``node`` with only the names in ``used`` ("" when none is)."""
    assert isinstance(node, (ast.Import, ast.ImportFrom))
    if isinstance(node, ast.ImportFrom) and node.module == "__future__":
        return f"from __future__ import {', '.join(a.name for a in node.names)}"
    names = [a for a in node.names if (a.asname or a.name).split(".")[0] in used]
    if not names:
        return ""
    listed = ", ".join(a.name + (f" as {a.asname}" if a.asname else "") for a in names)
    if isinstance(node, ast.ImportFrom):
        return f"from {'.' * node.level}{node.module or ''} import {listed}"
    return f"import {listed}"


def _without(lines: List[str], tree: ast.Module, target: ast.stmt) -> str:
    """The shared file without ``target``, and without the imported names only it used."""
    rest = [n for n in tree.body if n is not target and not isinstance(n, (ast.Import, ast.ImportFrom))]
    still: Set[str] = set().union(*(_uses(n) for n in rest)) if rest else set()
    only_target = _uses(target) - still
    edits: List[Tuple[int, int, str]] = [(*_span(target), "")]
    for node in tree.body:
        if not isinstance(node, (ast.Import, ast.ImportFrom)) or not (_bound(node) & only_target):
            continue
        keep = {(a.asname or a.name).split(".")[0] for a in node.names} - only_target
        edits.append((*_span(node), _import_code(node, keep)))
    out = list(lines)
    for start, end, code in sorted(edits, reverse=True):
        out[start:end] = [code] if code else []
    return re.sub(r"\n{4,}", "\n\n\n", "\n".join(out)).rstrip() + "\n"


def _name(node: ast.stmt) -> str:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return node.name
    return ", ".join(sorted(_bound(node)))


def _bound(node: ast.stmt) -> Set[str]:
    """Names a module-level statement defines."""
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return {node.name}
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        return {(a.asname or a.name).split(".")[0] for a in node.names}
    targets: List[ast.AST] = []
    if isinstance(node, ast.Assign):
        targets = list(node.targets)
    elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
        targets = [node.target]
    return {n.id for t in targets for n in ast.walk(t) if isinstance(n, ast.Name)}


def _uses(node: ast.AST) -> Set[str]:
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}


def _needed(tree: ast.Module, target: ast.stmt) -> Tuple[List[ast.stmt], List[ast.stmt]]:
    """The imports and module-level helpers ``target`` uses, directly or through those helpers (in file order)."""
    defs: Dict[str, ast.stmt] = {}
    for node in tree.body:
        if node is target or isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        for name in _bound(node):
            defs.setdefault(name, node)
    wanted: List[ast.stmt] = []
    todo = [target]
    seen_names: Set[str] = set()
    while todo:
        node = todo.pop()
        for name in sorted(_uses(node) - seen_names):
            seen_names.add(name)
            helper = defs.get(name)
            if helper is not None and helper not in wanted:
                wanted.append(helper)
                todo.append(helper)
    helpers = [n for n in tree.body if n in wanted]
    imports: List[ast.stmt] = [n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom)) and (
        _bound(n) & seen_names or (isinstance(n, ast.ImportFrom) and n.module == "__future__"))]
    return imports, helpers


def _span(node: ast.stmt) -> Tuple[int, int]:
    """0-based [start, end) line span of a statement with its decorators."""
    first = min([node.lineno] + [d.lineno for d in getattr(node, "decorator_list", [])])
    return first - 1, int(getattr(node, "end_lineno", node.lineno))


def _segment(lines: List[str], node: ast.stmt) -> str:
    start, end = _span(node)
    return "\n".join(lines[start:end])


def _absolute(code: str, node: ast.stmt, package: List[str]) -> str:
    """``from .util import x`` in app/handlers.py -> ``from app.util import x`` (the new file lives elsewhere)."""
    if not isinstance(node, ast.ImportFrom) or not node.level:
        return code
    base = package[: len(package) - (node.level - 1)] if node.level > 1 else list(package)
    module = ".".join(base + ([node.module] if node.module else []))
    names = ", ".join(a.name + (f" as {a.asname}" if a.asname else "") for a in node.names)
    return f"from {module} import {names}"


def _third_party(imports: List[ast.stmt], source: Path) -> List[str]:
    stdlib = set(getattr(sys, "stdlib_module_names", ()))
    out: List[str] = []
    for node in imports:
        if isinstance(node, ast.ImportFrom):
            if node.level or not node.module:
                continue
            tops = [node.module.split(".")[0]]
        else:
            tops = [a.name.split(".")[0] for a in node.names]  # type: ignore[attr-defined]
        for top in tops:
            local = (source / top).is_dir() or (source / f"{top}.py").is_file()
            if top in stdlib or local or top in ("py_serverless_kit", "__future__") or top in out:
                continue
            out.append(top)
    return out


def _matching_requirements(root: Path, modules: List[str]) -> Tuple[List[str], List[str]]:
    """The lines of the project's requirements.txt that name ``modules``, and the modules no line names."""
    path = root / PYTHON_MARKER
    lines = path.read_text("utf-8").splitlines() if path.is_file() else []
    by_name: Dict[str, str] = {}
    for line in lines:
        match = _REQ_NAME.match(line.split("#", 1)[0])
        if match and not line.lstrip().startswith("-"):
            by_name.setdefault(_norm(match.group(1)), line.strip())
    found: List[str] = []
    unknown: List[str] = []
    for module in modules:
        key = _norm(module)
        match_line = by_name.get(key) or by_name.get(_DISTRIBUTIONS.get(key, ""))
        if match_line is None and sys.version_info < (3, 10):
            continue  # no stdlib list on 3.9: do not guess
        if match_line:
            line = match_line
            if line not in found:
                found.append(line)
        else:
            unknown.append(module)
    return found, unknown


def strip_functions(text: str, names: List[str]) -> Tuple[str, List[str]]:
    """``text`` (a Python module) without the functions ``names`` and the imports only they used: what a
    placement group's copy of a shared code file keeps. A function that code left in the file still calls stays.
    Returns the new text and the names removed."""
    removed: List[str] = []
    for name in names:
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return text, removed
        target = next((n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                       and n.name == name), None)
        if target is None or _used_elsewhere(tree, target):
            continue
        text = _without(text.splitlines(), tree, target)
        removed.append(name)
    return text, removed


def _used_elsewhere(tree: ast.Module, target: ast.stmt) -> bool:
    name = getattr(target, "name", "")
    return any(name in _uses(node) for node in tree.body if node is not target)


def _set_handler(path: Path, function: str, old: str, new: str) -> None:
    """Point ``functions.<function>.handler`` at ``new``, keeping pskit.yml's comments and layout when the old
    value is written once (else rewrite the file)."""
    text = path.read_text("utf-8")
    pattern = re.compile(r"(^\s*handler:\s*['\"]?)" + re.escape(old) + r"(['\"]?\s*(?:#.*)?$)", re.M)
    if len(pattern.findall(text)) == 1:
        text = pattern.sub(lambda m: m.group(1) + new + m.group(2), text)
        path.write_bytes(text.encode("utf-8"))
        return
    raw = yaml.safe_load(text) or {}
    raw["functions"][function]["handler"] = new
    path.write_bytes(yaml.safe_dump(raw, sort_keys=False, allow_unicode=True, width=120).encode("utf-8"))


def describe(result: Dict[str, Any]) -> List[str]:
    out = [f"{result['function']}: {result['from']} -> {result['to']} (handler {result['handler']})"]
    if result.get("helpers"):
        out.append(f"  copied helpers: {', '.join(result['helpers'])} (still in {result['from']} for the others)")
    if result.get("kept_in_source"):
        out.append(f"  kept in {result['from']} too: code there still calls it")
    if result.get("requirements"):
        out.append(f"  requirements.txt: {', '.join(result['requirements'])}")
    if result.get("unknown_imports"):
        out.append(f"  check requirements.txt for: {', '.join(result['unknown_imports'])}")
    return out
