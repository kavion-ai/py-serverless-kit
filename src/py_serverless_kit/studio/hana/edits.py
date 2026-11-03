"""Removing things from the project completely: a function, workflow or resource from ``pskit.yml`` and, for a
function, its handler code. Used by Hana's remove cards (the user confirms) so a removal never leaves half of a
thing behind (the code gone but the ``pskit.yml`` entry still there, or the reverse).

``plan_removal`` says what would change (shown on the card); ``remove`` does it, with the studio's ``pskit.yml``
backup first. A function still used by a workflow state is not removed: the card names the workflow instead.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .. import project
from ..project import StudioError

KINDS = {"function": "functions", "workflow": "workflows", "resource": "resources"}
_HANDLER = re.compile(r"^([A-Za-z_][\w.]*)\.([A-Za-z_]\w*)$")


def raw_config(root: Path) -> Dict[str, Any]:
    path = project.config_path(root)
    if path is None:
        return {}
    raw, _ = project.parse_text(path.read_text("utf-8"))
    return raw if isinstance(raw, dict) else {}


def names(raw: Dict[str, Any], kind: str) -> List[str]:
    section = raw.get(KINDS[kind])
    return [str(k) for k in section] if isinstance(section, dict) else []


def _workflow_users(raw: Dict[str, Any], function: str) -> List[str]:
    """Workflows with a state that runs ``function``."""
    out = []
    for name, wf in (raw.get("workflows") or {}).items():
        states = (wf or {}).get("states") if isinstance(wf, dict) else None
        text = repr(states)
        if isinstance(states, dict) and re.search(rf"'function': '{re.escape(function)}'", text):
            out.append(str(name))
    return out


def _resource_users(raw: Dict[str, Any], key: str) -> List[str]:
    """Functions whose config mentions the resource key (``resources: [db]``, ``${resource:db...}``, ...)."""
    out = []
    for name, fn in (raw.get("functions") or {}).items():
        if re.search(rf"(?<![\w-]){re.escape(key)}(?![\w-])", repr(fn)):
            out.append(str(name))
    return out


def handler_file(root: Path, handler: str) -> Optional[Path]:
    """The file that defines ``handler`` (``app.handlers.hello`` -> ``app/handlers.py``), if it exists."""
    match = _HANDLER.match(str(handler or "").strip())
    if not match:
        return None
    try:
        source = project._source_dir(root)
    except StudioError:
        return None
    parts = match.group(1).split(".")
    candidates = [source.joinpath(*parts, "__init__.py"), source.joinpath(*parts[:-1], parts[-1] + ".py")]
    candidates += [source.joinpath(*parts[:-1], parts[-1] + ext) for ext in (".js", ".mjs", ".cjs", ".ts")]
    return next((c for c in candidates if c.is_file()), None)


def _module_of(handler: str) -> str:
    match = _HANDLER.match(str(handler or "").strip())
    return match.group(1) if match else ""


def _python_def_range(text: str, func: str) -> Optional[Tuple[int, int]]:
    """1-based first..last line of ``def func`` (decorators included) at module level."""
    tree = ast.parse(text)
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func:
            first = min([node.lineno] + [d.lineno for d in node.decorator_list])
            return first, int(getattr(node, "end_lineno", node.lineno))
    return None


def _only_imports_left(text: str) -> bool:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return False
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        if isinstance(node, ast.Expr) and isinstance(getattr(node, "value", None), ast.Constant):
            continue  # a docstring
        return False
    return True


def plan_removal(root: Path, kind: str, name: str) -> Dict[str, Any]:
    """What removing ``name`` would do: ``{"ok", "kind", "name", "yml": "functions.x", "code": {...}|None,
    "blocked": str|None, "warnings": [...]}``."""
    if kind not in KINDS:
        raise StudioError(400, "kind must be function, workflow or resource")
    raw = raw_config(root)
    if name not in names(raw, kind):
        raise StudioError(404, f"there is no {kind} {name!r} in pskit.yml")
    out: Dict[str, Any] = {"kind": kind, "name": name, "yml": f"{KINDS[kind]}.{name}", "code": None,
                           "blocked": None, "warnings": []}
    if kind == "function":
        users = _workflow_users(raw, name)
        if users:
            out["blocked"] = (f"workflow {', '.join(users)} still runs {name}: change or remove "
                              f"{'that workflow' if len(users) == 1 else 'those workflows'} first")
        handler = str(((raw.get("functions") or {}).get(name) or {}).get("handler") or "")
        path = handler_file(root, handler)
        if path is not None:
            rel = path.relative_to(root.resolve()).as_posix()
            module = _module_of(handler)
            shared = sorted(str(n) for n, fn in (raw.get("functions") or {}).items()
                            if n != name and isinstance(fn, dict) and _module_of(str(fn.get("handler") or "")) == module)
            same_handler = [n for n in shared if str((raw["functions"][n] or {}).get("handler")) == handler]
            code: Dict[str, Any] = {"file": rel, "handler": handler, "shared_with": shared}
            if same_handler:
                code["action"] = "keep"
                code["why"] = f"{', '.join(same_handler)} uses the same handler"
            elif path.suffix == ".py":
                func = handler.rsplit(".", 1)[1]
                text = path.read_text("utf-8")
                try:
                    span = _python_def_range(text, func)
                except SyntaxError:
                    span = None
                if span is None:
                    code["action"] = "keep"
                    code["why"] = f"{func}() isn't defined at the top of {rel}"
                else:
                    lines = text.split("\n")
                    rest = "\n".join(lines[: span[0] - 1] + lines[span[1]:])
                    code["action"] = "delete-file" if not shared and _only_imports_left(rest) else "delete-function"
                    code["lines"] = list(span)
            else:
                code["action"] = "delete-file" if not shared else "keep"
                if shared:
                    code["why"] = f"{rel} is also used by {', '.join(shared)}"
            out["code"] = code
    elif kind == "resource":
        users = _resource_users(raw, name)
        if users:
            out["warnings"].append(f"{', '.join(users)} still mention{'s' if len(users) == 1 else ''} {name}; "
                                   "validate will show what to change")
    return out


def remove(root: Path, kind: str, name: str, delete_code: bool = True) -> Dict[str, Any]:
    """Remove ``name`` from pskit.yml (backup first) and, for a function, its handler code as planned."""
    plan = plan_removal(root, kind, name)
    if plan["blocked"]:
        raise StudioError(409, plan["blocked"])
    raw = raw_config(root)
    section = dict(raw.get(KINDS[kind]) or {})
    section.pop(name, None)
    raw[KINDS[kind]] = section
    project.save_project(root, raw, force=True)
    config = project.config_path(root)
    changed = [config.name if config is not None else "pskit.yml"]
    code = plan.get("code") or {}
    done = "kept"
    if kind == "function" and delete_code and code.get("action") in ("delete-file", "delete-function"):
        path = (root / code["file"]).resolve()
        if code["action"] == "delete-file":
            path.unlink()
            done = "deleted"
        else:
            text = path.read_text("utf-8")
            lines = text.split("\n")
            first, last = code["lines"]
            # drop the def and the blank lines right after it, so the file keeps its spacing
            while last < len(lines) and not lines[last].strip():
                last += 1
            path.write_bytes(("\n".join(lines[: first - 1] + lines[last:])).encode("utf-8"))
            done = "function removed"
        changed.append(code["file"])
    return {"removed": name, "kind": kind, "changed": changed, "code": done, "plan": plan}


_WF_NAME = re.compile(r"^[a-z][a-z0-9-]{0,62}$")


def _state_name(function: str, taken: List[str]) -> str:
    base = "".join(p[:1].upper() + p[1:] for p in re.split(r"[-_.]", function) if p) or "Step"
    name, n = base, 2
    while name in taken:
        name, n = f"{base}{n}", n + 1
    return name


_FN_NAME = re.compile(r"^[a-z][a-z0-9-]{0,62}$")


def handler_module(raw: Dict[str, Any]) -> str:
    """Where new handlers go: the module most existing functions use (``app.handlers``), else ``app.handlers``."""
    modules = [_module_of(str((fn or {}).get("handler") or "")) for fn in (raw.get("functions") or {}).values()
               if isinstance(fn, dict)]
    modules = [m for m in modules if m]
    return max(set(modules), key=modules.count) if modules else "app.handlers"


def py_name(function: str) -> str:
    """``step-01`` -> ``step_01`` (a Python function name for the handler)."""
    out = re.sub(r"\W", "_", function).strip("_") or "handler"
    return out if not out[0].isdigit() else f"fn_{out}"


def create_workflow(root: Path, name: str, steps: List[str], description: str = "", wait_seconds: float = 0,
                    create_functions: Optional[List[str]] = None) -> Dict[str, Any]:
    """A workflow that runs ``steps`` (functions of this project) one after the other, each getting the previous
    one's result, with a ``wait`` step of ``wait_seconds`` between them when it is above 0. Functions listed in
    ``create_functions`` that don't exist yet are added first (no trigger, a handler stub). Written to pskit.yml
    (backup first) and validated."""
    from .tools import ProjectTools

    raw = raw_config(root)
    if not raw:
        raise StudioError(400, "this folder has no pskit.yml yet")
    if not _WF_NAME.match(name or ""):
        raise StudioError(400, "workflow name: lowercase letters, digits and -, starting with a letter")
    if name in names(raw, "workflow"):
        raise StudioError(409, f"there is already a workflow {name!r}")
    if not 0 <= float(wait_seconds or 0) <= 31_536_000:
        raise StudioError(400, "wait_seconds must be between 0 and one year")
    functions = names(raw, "function")
    new = [str(f) for f in create_functions or [] if str(f) not in functions]
    bad = [f for f in new if not _FN_NAME.match(f)]
    if bad:
        raise StudioError(400, f"function names: lowercase letters, digits and -, starting with a letter ({', '.join(bad)})")
    steps = [str(s) for s in steps or []]
    unknown = [s for s in steps if s not in functions and s not in new]
    if not steps or unknown:
        raise StudioError(400, f"pick the steps from the project's functions ({', '.join(functions) or 'none yet'})"
                          + (f"; unknown: {', '.join(unknown)}" if unknown else ""))
    module = handler_module(raw)
    created_handlers = []
    if new:
        section = dict(raw.get("functions") or {})
        for fn in new:
            handler = f"{module}.{py_name(fn)}"
            section[fn] = {"handler": handler, "description": f"Step of workflow {name}"}
            created_handlers.append(handler)
        raw["functions"] = section
    order: List[str] = []
    for fn in steps:
        order.append(_state_name(fn, order))
    wait = float(wait_seconds or 0)
    sequence: List[Tuple[str, Dict[str, Any]]] = []
    for i, (state, fn) in enumerate(zip(order, steps)):
        sequence.append((state, {"type": "task", "function": fn}))
        if wait and i + 1 < len(steps):
            sequence.append((f"Wait{i + 1}", {"type": "wait", "seconds": int(wait) if wait == int(wait) else wait}))
    states: Dict[str, Any] = {}
    for i, (state, body) in enumerate(sequence):
        states[state] = {**body, **({"next": sequence[i + 1][0]} if i + 1 < len(sequence) else {"end": True})}
    workflow: Dict[str, Any] = {"start_at": sequence[0][0], "states": states}
    if description:
        workflow["description"] = description[:200]
    workflows = dict(raw.get("workflows") or {})
    workflows[name] = workflow
    raw["workflows"] = workflows
    project.save_project(root, raw, force=True)
    stubs = []
    for handler in created_handlers:  # the same stub as studio's "Create function" (one file per module)
        result = project.ensure_handler(root, handler, ["invoke"])
        stubs.append(str(result.get("path") or result.get("file") or handler))
    provider = str((raw.get("provider") or {}).get("name") or "")
    return {"created": name, "states": [s for s, _b in sequence], "functions": new, "stubs": stubs,
            "validate": ProjectTools(root).validate(provider, "")}


TRIGGERS = ("none", "http", "schedule")
# Where a new function's code goes: its own app (functions/<name>/ with its own requirements.txt, see
# packaging/subprojects.py) or an existing module shared with other functions (app/handlers.py).
PLACEMENTS = ("separate", "module")
# What to do with a name that is already in pskit.yml: change that function, create it under another name, or skip.
ON_EXISTING = ("update", "rename", "skip")
_MODULE = re.compile(r"^[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*$")


def free_name(name: str, taken: List[str]) -> str:
    """``step01`` -> ``step01-2`` (the first ``-N`` not in ``taken``)."""
    n = 2
    while f"{name}-{n}" in taken:
        n += 1
    return f"{name}-{n}"


def _language(raw: Dict[str, Any]) -> str:
    runtime = str((raw.get("provider") or {}).get("runtime") or "") if isinstance(raw.get("provider"), dict) else ""
    return "node" if runtime.startswith("nodejs") else "python"


def separate_handler(function: str, language: str = "python") -> str:
    """The handler of a function that is its own app: ``step-01`` -> ``functions.step_01.handler.main`` (the same
    layout as the Functions page's "Own folder" and ``pskit function split``)."""
    from ...core.function_split import folder_name

    folder = folder_name(function)
    folder = folder if not folder[:1].isdigit() else f"fn_{folder}"
    return f"functions.{folder}.{'index' if language == 'node' else 'handler'}.main"


def modules(root: Path, raw: Dict[str, Any]) -> List[str]:
    """The shared code modules the project's functions use (``app.handlers`` ...), most used first; functions that
    are their own app (a folder with its own requirements.txt / package.json) are left out."""
    from ...packaging.subprojects import function_dir

    try:
        source: Optional[Path] = project._source_dir(root)
    except StudioError:
        source = None
    language = _language(raw)
    found: List[str] = []
    for fn in (raw.get("functions") or {}).values():
        if not isinstance(fn, dict):
            continue
        handler = str(fn.get("handler") or "")
        module = _module_of(handler)
        if not module or (source is not None and function_dir(source, handler, language) is not None):
            continue
        found.append(module)
    return sorted(set(found), key=lambda m: (-found.count(m), m))


def create_functions(root: Path, new: List[str], trigger: str = "none", schedule: str = "5 minutes",
                     placement: str = "module", module: str = "",
                     existing: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Add functions to pskit.yml (backup first) AND write their handler code (a stub per function, the same as
    studio's Create function), then validate.

    ``trigger``: none (called directly or by a workflow), http (``GET /<name>``) or schedule (every ``schedule``).
    ``placement``: ``separate`` gives each function its own app (``functions/<name>/handler.py`` with its own
    ``requirements.txt``); ``module`` puts the handlers in ``module`` (default: the module most functions use).
    ``existing``: for each name already in pskit.yml, ``update`` (keep its code, apply the trigger and, with
    ``separate``, move its code into its own app), ``rename`` (create ``<name>-2``) or ``skip``. A name already
    there without a decision is refused (409), so nothing is overwritten by accident."""
    from .tools import ProjectTools

    raw = raw_config(root)
    if not raw:
        raise StudioError(400, "this folder has no pskit.yml yet")
    if trigger not in TRIGGERS:
        raise StudioError(400, "trigger must be none, http or schedule")
    if placement not in PLACEMENTS:
        raise StudioError(400, "placement must be separate (each function its own app) or module (an existing file)")
    language = _language(raw)
    if placement == "module":
        module = module or handler_module(raw)
        if not _MODULE.match(module):
            raise StudioError(400, f"module {module!r} must look like app.handlers")
    decisions = {str(k): str(v) for k, v in (existing or {}).items()}
    wrong = [f"{k}: {v}" for k, v in decisions.items() if v not in ON_EXISTING]
    if wrong:
        raise StudioError(400, f"for an existing function pick update, rename or skip ({', '.join(wrong)})")
    current = names(raw, "function")
    asked = [str(n) for n in dict.fromkeys(new or [])]
    bad = [n for n in asked if not _FN_NAME.match(n)]
    if not asked or bad:
        raise StudioError(400, "function names: lowercase letters, digits and -, starting with a letter"
                          + (f" ({', '.join(bad)})" if bad else ""))
    undecided = [n for n in asked if n in current and n not in decisions]
    if undecided:
        raise StudioError(409, f"already in pskit.yml: {', '.join(undecided)} (choose update, rename or skip for each)")
    taken = current + asked
    create: List[str] = []
    update: List[str] = []
    renamed: Dict[str, str] = {}
    skipped: List[str] = []
    for n in asked:
        choice = decisions.get(n) if n in current else "create"
        if choice == "skip":
            skipped.append(n)
        elif choice == "update":
            update.append(n)
        elif choice == "rename":
            other = free_name(n, taken)
            taken.append(other)
            renamed[n] = other
            create.append(other)
        else:
            create.append(n)
    if not create and not update:
        return {"created": [], "updated": [], "renamed": {}, "skipped": skipped, "code": [], "moved": [],
                "validate": "nothing to do: every name was skipped"}

    def events(fn: str) -> List[Dict[str, Any]]:
        if trigger == "http":
            return [{"http": f"GET /{fn}"}]
        if trigger == "schedule":
            return [{"schedule": schedule or "5 minutes"}]
        return []

    section = dict(raw.get("functions") or {})
    for fn in create:
        handler = separate_handler(fn, language) if placement == "separate" else f"{module}.{py_name(fn)}"
        entry: Dict[str, Any] = {"handler": handler}
        if events(fn):
            entry["events"] = events(fn)
        section[fn] = entry
    for fn in update:  # keep the function and its code; only the trigger changes (when one was picked)
        if events(fn):
            section[fn] = {**dict(section.get(fn) or {}), "events": events(fn)}
    raw["functions"] = section
    project.save_project(root, raw, force=True)
    code = []
    kind = {"http": "http", "schedule": "schedule"}.get(trigger, "invoke")
    for fn in create:
        result = project.ensure_handler(root, section[fn]["handler"], [kind], subproject=placement == "separate")
        code.append({"function": fn, "handler": section[fn]["handler"], "file": result.get("path"),
                     "written": bool(result.get("created"))})
    split: Dict[str, Any] = {"moved": [], "errors": [], "deleted": []}
    if placement == "separate" and update:
        split = separate_functions(root, update, validate=False)
    provider = str((raw.get("provider") or {}).get("name") or "")
    return {"created": create, "updated": update, "renamed": renamed, "skipped": skipped, "code": code,
            "moved": split["moved"], "move_errors": split["errors"], "deleted": split["deleted"],
            "validate": ProjectTools(root).validate(provider, "")}


def _imported_elsewhere(root: Path, path: Path) -> bool:
    """Whether another Python file of the project imports the module in ``path`` (``app/steps.py``): ``import
    app.steps``, ``from app.steps import x``, ``from app import steps`` or a relative ``from .steps import x``. The
    helpers a moved function used were copied into its own app, so a file nobody imports can go."""
    try:
        source = project._source_dir(root)
        parts = path.relative_to(source).with_suffix("").parts
    except (StudioError, ValueError):
        return True  # outside the source folder: don't touch
    if parts and parts[-1] == "__init__":
        return True
    module = ".".join(parts)
    parent, leaf = ".".join(parts[:-1]), parts[-1]
    skip = {"node_modules", ".venv", "venv", ".pskit", ".git", "__pycache__", "functions"}
    for other in source.rglob("*.py"):
        if other == path or skip & set(other.relative_to(source).parts):
            continue
        try:
            tree = ast.parse(other.read_text("utf-8"))
        except (OSError, SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import) and any(a.name == module or a.name.startswith(module + ".")
                                                    for a in node.names):
                return True
            if isinstance(node, ast.ImportFrom):
                base = node.module or ""
                if node.level and other.parent == path.parent and (base == leaf or (not base and any(
                        a.name == leaf for a in node.names))):
                    return True
                if not node.level and (base == module or (base == parent and any(a.name == leaf for a in node.names))):
                    return True
    return False


def separate_functions(root: Path, functions: List[str], validate: bool = True) -> Dict[str, Any]:
    """Give each listed function its own app: its code moves from the shared file into
    ``functions/<name>/handler.py`` with its own ``requirements.txt`` (``pskit function split``). A shared file left
    with nothing but imports is deleted. Functions that already have their own folder are reported, not changed."""
    from ...core import function_split
    from .tools import ProjectTools

    raw = raw_config(root)
    if not raw:
        raise StudioError(400, "this folder has no pskit.yml yet")
    unknown = [f for f in functions if f not in names(raw, "function")]
    if unknown:
        raise StudioError(404, f"not in pskit.yml: {', '.join(unknown)}")
    moved: List[Dict[str, Any]] = []
    already: List[str] = []
    errors: List[str] = []
    sources: List[str] = []
    for fn in dict.fromkeys(functions):
        try:
            result = function_split.split(root, fn)
        except function_split.SplitError as exc:
            (already if "already has its own folder" in str(exc) else errors).append(
                fn if "already has its own folder" in str(exc) else f"{fn}: {exc}")
            continue
        moved.append(result)
        if result["from"] not in sources:
            sources.append(result["from"])
    deleted: List[str] = []
    in_use = {handler_file(root, str((fn or {}).get("handler") or "")) for fn in
              (raw_config(root).get("functions") or {}).values() if isinstance(fn, dict)}
    for rel in sources:  # "remove app/steps.py": the shared file goes when no function and no other file uses it
        path = (root / rel).resolve()
        if path.is_file() and path not in in_use and (_only_imports_left(path.read_text("utf-8"))
                                                      or not _imported_elsewhere(root, path)):
            path.unlink()
            deleted.append(rel)
    out: Dict[str, Any] = {"moved": moved, "already": already, "errors": errors, "deleted": deleted}
    if validate:
        provider = str((raw.get("provider") or {}).get("name") or "")
        out["validate"] = ProjectTools(root).validate(provider, "")
    return out


def _event_kind(fn: Dict[str, Any]) -> str:
    events = fn.get("events") if isinstance(fn.get("events"), list) else []
    first = events[0] if events and isinstance(events[0], dict) else {}
    return next(iter(first), "invoke") if first else "invoke"


def missing_code(root: Path, only: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """Functions whose handler code doesn't exist yet: no file, or the file has no such function."""
    raw = raw_config(root)
    out = []
    for name, fn in (raw.get("functions") or {}).items():
        if only and name not in only or not isinstance(fn, dict):
            continue
        handler = str(fn.get("handler") or "")
        path = handler_file(root, handler)
        has_def = False
        if path is not None and path.suffix == ".py":
            try:
                has_def = _python_def_range(path.read_text("utf-8"), handler.rsplit(".", 1)[-1]) is not None
            except (SyntaxError, OSError):
                has_def = True  # a broken file: don't touch it
        elif path is not None:
            has_def = True  # Node.js: the file exists; ensure_handler adds a missing export itself
        if not has_def and _HANDLER.match(handler):
            out.append({"function": str(name), "handler": handler, "kind": _event_kind(fn),
                        "file": path.relative_to(root.resolve()).as_posix() if path is not None else None})
    return out


def write_code(root: Path, functions: List[str]) -> Dict[str, Any]:
    """Write the handler stub of each listed function whose code is missing (existing code is never changed)."""
    todo = {m["function"]: m for m in missing_code(root, functions)}
    written = []
    for fn in functions:
        if fn in todo:
            result = project.ensure_handler(root, todo[fn]["handler"], [todo[fn]["kind"]])
            written.append({"function": fn, "handler": todo[fn]["handler"], "file": result.get("path"),
                            "written": bool(result.get("created"))})
    return {"written": written}


MANAGED_RESOURCES = ("storage", "queue", "topic", "smtp")
EXTERNAL_RESOURCES = ("database", "cache", "custom")
_DEFAULT_PORTS = {"database": 5432, "cache": 6379}


def resource_entry(item: Dict[str, Any]) -> Dict[str, Any]:
    """One ``resources:`` entry. Buckets, queues, topics and smtp are created by pskit; databases, caches and custom
    services already exist, so they are ``external`` with connection details (a secret only as an env var NAME)."""
    kind = str(item.get("type") or "")
    if kind in MANAGED_RESOURCES:
        return {"type": kind}
    if kind not in EXTERNAL_RESOURCES:
        raise StudioError(400, f"resource type must be one of {', '.join(MANAGED_RESOURCES + EXTERNAL_RESOURCES)}")
    key = str(item.get("key") or kind)
    env = re.sub(r"[^A-Z0-9]", "_", key.upper())
    connection: Dict[str, Any] = {
        "host": str(item.get("host") or f"${{env:{env}_HOST, localhost}}"),
        "port": int(item.get("port") or _DEFAULT_PORTS.get(kind, 8080)),
    }
    if kind == "database":
        connection["database"] = str(item.get("database") or key.replace("-", "_"))
    if kind in ("database", "cache"):
        connection["password_env"] = str(item.get("password_env") or f"{env}_PASSWORD")
    return {"type": kind, "external": True, "connection": connection}


def create_resources(root: Path, items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Add resources to pskit.yml (backup first), then validate. An item with ``"replace": true`` replaces the
    resource of the same name (the user picked "replace it" on the card); otherwise a taken name is refused."""
    from .tools import ProjectTools

    raw = raw_config(root)
    if not raw:
        raise StudioError(400, "this folder has no pskit.yml yet")
    existing = names(raw, "resource")
    section = dict(raw.get("resources") or {})
    added: List[str] = []
    replaced: List[str] = []
    for item in items or []:
        key = str(item.get("key") or "")
        if not _FN_NAME.match(key):
            raise StudioError(400, f"resource name {key!r}: lowercase letters, digits and -, starting with a letter")
        if key in added:
            raise StudioError(409, f"resource {key!r} is listed twice")
        if key in existing and not item.get("replace"):
            raise StudioError(409, f"there is already a resource {key!r} (replace it, or pick another name)")
        section[key] = resource_entry(item)
        (replaced if key in existing else added).append(key)
    if not added and not replaced:
        raise StudioError(400, "no resources to add")
    raw["resources"] = section
    project.save_project(root, raw, force=True)
    provider = str((raw.get("provider") or {}).get("name") or "")
    return {"created": added, "replaced": replaced, "validate": ProjectTools(root).validate(provider, "")}
