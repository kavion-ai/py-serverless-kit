"""Reads ``pskit_manifest.json`` - the per-bundle description of every function.

The CLI writes this file into the root of each deployment artifact. It lets a
single shared bundle serve many functions (Azure Function Apps, the embedded
workflow engine, ...) without depending on per-function environment variables.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

MANIFEST_FILE = "pskit_manifest.json"


@dataclass
class Route:
    method: str
    path: str
    cors: Optional[Dict[str, Any]] = None


@dataclass
class FunctionSpec:
    name: str
    handler: str
    routes: List[Route] = field(default_factory=list)
    timeout: Optional[int] = None
    memory: Optional[int] = None
    resource_name: Optional[str] = None


@dataclass
class BundleManifest:
    service: str = ""
    stage: str = ""
    provider: str = "local"
    region: str = ""
    functions: Dict[str, FunctionSpec] = field(default_factory=dict)
    workflows: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> BundleManifest:
        functions = {}
        for name, spec in (raw.get("functions") or {}).items():
            routes = [Route(r["method"], r["path"], r.get("cors")) for r in spec.get("routes", [])]
            functions[name] = FunctionSpec(
                name=name,
                handler=spec["handler"],
                routes=routes,
                timeout=spec.get("timeout"),
                memory=spec.get("memory"),
                resource_name=spec.get("resource_name"),
            )
        return cls(
            service=raw.get("service", ""),
            stage=raw.get("stage", ""),
            provider=raw.get("provider", "local"),
            region=raw.get("region", ""),
            functions=functions,
            workflows=raw.get("workflows") or {},
        )


_CACHE: Optional[BundleManifest] = None


def _candidates() -> List[Path]:
    here = Path(__file__).resolve()
    paths = []
    if os.environ.get("PSKIT_MANIFEST"):
        paths.append(Path(os.environ["PSKIT_MANIFEST"]))
    paths.append(here.parents[2] / MANIFEST_FILE)  # <bundle>/py_serverless_kit/runtime/manifest.py
    for env in ("LAMBDA_TASK_ROOT", "FC_FUNC_CODE_PATH", "RUNTIME_CODE_ROOT"):
        if os.environ.get(env):
            paths.append(Path(os.environ[env]) / MANIFEST_FILE)
    paths.append(Path.cwd() / MANIFEST_FILE)
    return paths


def load_manifest(reload: bool = False) -> BundleManifest:
    global _CACHE
    if _CACHE is not None and not reload:
        return _CACHE
    for path in _candidates():
        if path.is_file():
            _CACHE = BundleManifest.from_dict(json.loads(path.read_text("utf-8")))
            return _CACHE
    _CACHE = BundleManifest(
        service=os.environ.get("PSKIT_SERVICE", ""),
        stage=os.environ.get("PSKIT_STAGE", ""),
        provider=os.environ.get("PSKIT_PROVIDER", "local"),
    )
    return _CACHE


def set_manifest(manifest: Optional[BundleManifest]) -> None:
    """Install a manifest programmatically (local runner and tests)."""
    global _CACHE
    _CACHE = manifest


def resolve_function(name: Optional[str] = None) -> FunctionSpec:
    """Find the spec for ``name`` (default: ``$PSKIT_FUNCTION``)."""
    manifest = load_manifest()
    name = name or os.environ.get("PSKIT_FUNCTION", "")
    if name and name in manifest.functions:
        return manifest.functions[name]
    handler = os.environ.get("PSKIT_HANDLER")
    if handler:
        return FunctionSpec(name=name or handler, handler=handler)
    if len(manifest.functions) == 1 and not name:
        return next(iter(manifest.functions.values()))
    known = ", ".join(sorted(manifest.functions)) or "<none>"
    raise LookupError(
        f"Cannot resolve function {name!r}. Set PSKIT_FUNCTION/PSKIT_HANDLER or check "
        f"{MANIFEST_FILE}. Known functions: {known}"
    )
