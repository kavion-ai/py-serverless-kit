"""Skip helpers for tests that need Node.js (and tsc for TypeScript)."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Optional

from py_serverless_kit.packaging.node import RUNTIME_JS

REPO = Path(__file__).resolve().parents[1]
# The dashboard UI's dev dependencies include typescript and esbuild; reuse them when installed.
UI_BIN = REPO / "dashboard-ui" / "node_modules" / ".bin"


def tool_path() -> str:
    """PATH with the UI's ``node_modules/.bin`` appended (when it exists)."""
    path = os.environ.get("PATH", "")
    return path + os.pathsep + str(UI_BIN) if UI_BIN.is_dir() and str(UI_BIN) not in path else path


def node_skip_reason(typescript: bool = False) -> Optional[str]:
    if not shutil.which("node"):
        return "Node.js is not installed"
    if not (RUNTIME_JS / "worker.js").is_file():
        return "runtime_js/worker.js is not available"
    try:
        from py_serverless_kit.runtime.event import Event

        if not hasattr(Event, "to_wire"):
            return "Event.to_wire is not available"
        import py_serverless_kit.runtime.node_worker  # noqa: F401
    except ImportError:
        return "runtime/node_worker.py is not available"
    if typescript and not (RUNTIME_JS / "index.d.ts").is_file():
        return "runtime_js/index.d.ts is not available"
    if typescript and not shutil.which("tsc", path=tool_path()):
        return "tsc is not installed (npm i -g typescript, or npm ci in dashboard-ui)"
    return None
