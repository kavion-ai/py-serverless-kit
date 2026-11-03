"""Node.js / TypeScript build steps shared by packaging and local runs.

See ``deploy_docs/NODE_RUNTIME.md`` for the bundle layout. Tools are looked up in
the project first (``node_modules/.bin``), then on ``PATH``, then fetched with
``npx`` where that works (``tsc``, ``esbuild``). A missing ``node`` / ``npm`` is a
:class:`BuildError` with an install hint.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, Iterable, List, Optional

if TYPE_CHECKING:  # pragma: no cover
    from ..core.project import Project

RUNTIME_JS = Path(__file__).resolve().parents[1] / "runtime_js"
RUNTIME_DIR = "pskit_runtime"
TYPES_DIR = Path(".pskit") / "types" / "pskit"
TS_SUFFIXES = (".ts", ".tsx", ".mts", ".cts")
JS_SUFFIXES = (".js", ".mjs", ".cjs")
NODE_HINT = "Install Node.js 18+ (which includes npm): https://nodejs.org/en/download"
TSC_NPX = ["-p", "typescript@5", "tsc"]
ESBUILD_NPX = ["esbuild@0.24"]

Log = Callable[[str], Any]


class NodeBuildError(Exception):
    """A Node.js build step failed (converted to ``BuildError`` by the builder)."""


# --------------------------------------------------------------------- tools


def _which(name: str) -> Optional[str]:
    return shutil.which(name)


def local_bin(root: Path, name: str) -> Optional[str]:
    """``<root>/node_modules/.bin/<name>`` (``.cmd`` on Windows) if present."""
    folder = root / "node_modules" / ".bin"
    for candidate in ([f"{name}.cmd", f"{name}.exe", name] if sys.platform == "win32" else [name]):
        path = folder / candidate
        if path.is_file():
            return str(path)
    return None


def node_exe() -> str:
    found = _which("node")
    if not found:
        raise NodeBuildError(f"`node` was not found on PATH; Node.js services need it. {NODE_HINT}")
    return found


def npm_exe() -> str:
    found = _which("npm")
    if not found:
        raise NodeBuildError(f"`npm` was not found on PATH. {NODE_HINT}")
    return found


def tool_command(root: Path, name: str, npx_args: List[str], hint: str) -> List[str]:
    """Command for a build tool: project ``node_modules/.bin`` → ``PATH`` → ``npx --yes``."""
    found = local_bin(root, name) or _which(name)
    if found:
        return [found]
    npx = _which("npx")
    if npx:
        return [npx, "--yes", *npx_args]
    raise NodeBuildError(f"`{name}` was not found ({hint}). {NODE_HINT}")


def tsc_command(root: Path) -> List[str]:
    return tool_command(root, "tsc", TSC_NPX, "npm install --save-dev typescript")


def esbuild_command(root: Path) -> List[str]:
    return tool_command(root, "esbuild", ESBUILD_NPX, "npm install --save-dev esbuild")


def run(cmd: List[str], cwd: Path, what: str, env: Optional[Dict[str, str]] = None) -> str:
    try:
        proc = subprocess.run(  # noqa: S603 - explicit argv, no shell
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env={**os.environ, **(env or {})},
            stdin=subprocess.DEVNULL,
        )
    except OSError as exc:
        raise NodeBuildError(f"{what}: could not run {cmd[0]}: {exc}. {NODE_HINT}") from None
    if proc.returncode != 0:
        output = (proc.stdout or "") + (proc.stderr or "")
        raise NodeBuildError(f"{what} failed (exit {proc.returncode}):\n{output[-4000:]}")
    return proc.stdout or ""


# --------------------------------------------------------------------- runtime / types


def runtime_available() -> bool:
    return (RUNTIME_JS / "index.js").is_file()


def _runtime_package_json() -> bytes:
    from .._version import __version__

    meta = {"name": "pskit", "version": __version__, "main": "index.js", "types": "index.d.ts", "type": "commonjs"}
    return (json.dumps(meta, indent=2) + "\n").encode("utf-8")


def copy_runtime(dest: Path) -> None:
    """Copy the JS runtime to ``dest`` (e.g. ``<build>/pskit_runtime`` or ``node_modules/pskit``)."""
    if not runtime_available():
        raise NodeBuildError(f"the Node.js runtime is missing from this install ({RUNTIME_JS})")
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(RUNTIME_JS, dest, ignore=shutil.ignore_patterns("node_modules", "*.test.js", "test", "tests"))
    if not (dest / "package.json").is_file():
        (dest / "package.json").write_bytes(_runtime_package_json())


def write_types(project_root: Path) -> Optional[Path]:
    """Write ``.pskit/types/pskit/index.d.ts`` so editors and ``tsc`` resolve ``import ... from "pskit"``."""
    source = RUNTIME_JS / "index.d.ts"
    if not source.is_file():
        return None
    target = project_root / TYPES_DIR
    target.mkdir(parents=True, exist_ok=True)
    (target / "index.d.ts").write_bytes(source.read_bytes())
    (target / "package.json").write_bytes(_runtime_package_json())
    return target


# --------------------------------------------------------------------- TypeScript


def handler_file(source: Path, handler: str) -> Optional[Path]:
    """The file a ``module.function`` handler points at, any JS/TS extension."""
    module = handler.replace(":", ".").rsplit(".", 1)[0]
    base = source.joinpath(*module.split("."))
    for suffix in JS_SUFFIXES + TS_SUFFIXES:
        if base.with_suffix(suffix).is_file():
            return base.with_suffix(suffix)
    for suffix in JS_SUFFIXES + TS_SUFFIXES:
        if (base / f"index{suffix}").is_file():
            return base / f"index{suffix}"
    return None


def wants_typescript(explicit: Optional[bool], project_root: Path, source: Path, handlers: Iterable[str]) -> bool:
    if explicit is not None:
        return explicit
    if (source / "tsconfig.json").is_file() or (project_root / "tsconfig.json").is_file():
        return True
    for handler in handlers:
        found = handler_file(source, handler)
        if found is not None and found.suffix in TS_SUFFIXES:
            return True
    return False


def _posix(path: Path) -> str:
    return path.resolve().as_posix()


def compile_typescript(project_root: Path, source: Path, out_dir: Path, work: Path, log: Log) -> None:
    """Compile every ``.ts`` file under ``source`` into ``out_dir`` (same relative paths).

    A generated tsconfig extends the user's ``tsconfig.json`` when there is one and only
    overrides output settings; without one it uses CommonJS / ES2022 defaults and maps
    ``pskit`` to the types written by :func:`write_types`.
    """
    user_cfg = next((p for p in (source / "tsconfig.json", project_root / "tsconfig.json") if p.is_file()), None)
    types = write_types(project_root)
    options: Dict[str, Any] = {
        "outDir": _posix(out_dir),
        "rootDir": _posix(source),
        "noEmit": False,
        "declaration": False,
        "sourceMap": False,
        "incremental": False,
        "composite": False,
        "skipLibCheck": True,
    }
    config: Dict[str, Any] = {}
    if user_cfg is not None:
        config["extends"] = _posix(user_cfg)
    else:
        # No baseUrl / moduleResolution: TypeScript 7 removed both (and node10 resolution).
        options.update({"module": "commonjs", "target": "es2022", "esModuleInterop": True})
        if types is not None:
            options["paths"] = {"pskit": [_posix(types / "index.d.ts")]}
    config["compilerOptions"] = options
    config["include"] = [f"{_posix(source)}/**/*{suffix}" for suffix in TS_SUFFIXES]
    config["exclude"] = [f"{_posix(source)}/{name}/**" for name in ("node_modules", ".pskit", "dist", "build", "tests")]
    work.mkdir(parents=True, exist_ok=True)
    tsconfig = work / "tsconfig.pskit.json"
    tsconfig.write_bytes((json.dumps(config, indent=2) + "\n").encode("utf-8"))
    log("  compiling TypeScript (tsc)")
    run([*tsc_command(project_root), "-p", str(tsconfig)], project_root, "TypeScript compile (tsc)")


# --------------------------------------------------------------------- source tree


def prepare_tree(
    project: Project,
    dest: Path,
    manifest: Dict[str, Any],
    log: Log = print,
    *,
    node_modules_runtime: bool = False,
) -> Path:
    """Fill ``dest`` with the sources (TypeScript compiled), the runtime and the manifest.

    Returns the source folder that was used (``package.source`` or ``package.node.out_dir``).
    """
    from .builder import collect_sources

    cfg = project.config
    node_cfg = cfg.package.node
    root = project.root
    if node_cfg.build:
        log(f"  build: {' '.join(node_cfg.build)}")
        cmd = list(node_cfg.build)
        resolved = local_bin(root, cmd[0]) or _which(cmd[0])
        if resolved:
            cmd[0] = resolved
        run(cmd, root, "package.node.build")
    source = (root / (node_cfg.out_dir or cfg.package.source)).resolve()
    if not source.is_dir():
        raise NodeBuildError(f"source folder {source} does not exist")
    handlers = [fn.handler for fn in cfg.functions.values()]
    typescript = wants_typescript(node_cfg.typescript, root, source, handlers)
    files = collect_sources(source, cfg.package.include, cfg.package.exclude)
    copied = 0
    for f in files:
        if typescript and (f.suffix in TS_SUFFIXES and not f.name.endswith(".d.ts") or f.name == "tsconfig.json"):
            continue
        target = dest / f.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, target)
        copied += 1
    log(f"  collected {copied} source file(s) from {source}")
    if typescript:
        compile_typescript(root, source, dest, project.work_dir, log)
    copy_runtime(dest / RUNTIME_DIR)
    if node_modules_runtime:
        copy_runtime(dest / "node_modules" / "pskit")
    (dest / "pskit_manifest.json").write_bytes(json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8"))
    return source


def read_package_json(project: Project, source: Path) -> Optional[Dict[str, Any]]:
    for path in (source / "package.json", project.root / "package.json"):
        if path.is_file():
            try:
                data = json.loads(path.read_text("utf-8"))
            except ValueError as exc:
                raise NodeBuildError(f"{path} is not valid JSON: {exc}") from None
            return data if isinstance(data, dict) else {}
    return None


def write_json(path: Path, data: Dict[str, Any]) -> None:
    path.write_bytes((json.dumps(data, indent=2) + "\n").encode("utf-8"))


def npm_install(build_dir: Path, args: List[str], log: Log) -> None:
    lock = "package-lock.json" if (build_dir / "package-lock.json").is_file() else None
    verb = ["ci"] if lock else ["install"]
    log(f"  npm {verb[0]} --omit=dev")
    run(
        [npm_exe(), *verb, "--omit=dev", "--no-audit", "--no-fund", "--ignore-scripts", "--no-package-lock", *args]
        if not lock
        else [npm_exe(), *verb, "--omit=dev", "--no-audit", "--no-fund", "--ignore-scripts", *args],
        build_dir,
        "npm install",
        env={"npm_config_update_notifier": "false"},
    )


def esbuild_bundle(project_root: Path, build_dir: Path, entry: str, out: str, options: List[str], log: Log) -> None:
    log(f"  esbuild {entry} -> {out}")
    run(
        [*esbuild_command(project_root), entry, "--bundle", f"--outfile={out}", "--log-level=warning", *options],
        build_dir,
        "esbuild bundle",
    )
