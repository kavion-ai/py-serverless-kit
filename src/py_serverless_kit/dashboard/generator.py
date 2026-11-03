"""Generate the deployment dashboard: one self-contained ``index.html``.

The page lists every deployment found under ``.pskit/*/deployment.json`` (all
providers and stages of the project) with functions, triggers, endpoints,
resource identifiers and workflows. It has no external dependencies, so it can
be opened from disk, served by ``pskit dashboard --serve``, or uploaded to any
static host / bucket.

``template.html`` is the build output of the React app in ``dashboard-ui/``
(``npm run build``); do not edit it by hand.
"""

from __future__ import annotations

import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..core.describe import RECORD_FILE, build_record
from ..core.project import WORK_DIR, Project

TEMPLATE = Path(__file__).with_name("template.html")
_PLACEHOLDER = re.compile(r"\{\{(TITLE|DATA)\}\}")


def record_key(record: Dict[str, Any]) -> str:
    """Identifier of a deployment in URLs: its ``.pskit/<provider>-<stage>`` directory name."""
    return str(record.get("key") or f"{record.get('provider', '')}-{record.get('stage', '')}")


def collect_records(root: Path) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    base = root / WORK_DIR
    if not base.is_dir():
        return records
    for path in sorted(base.glob(f"*/{RECORD_FILE}")):
        try:
            record = json.loads(path.read_text("utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(record, dict):
            continue
        record.setdefault("key", path.parent.name)
        records.append(record)
    records.sort(key=lambda r: (r.get("service", ""), r.get("provider", ""), r.get("stage", "")))
    return records


def local_record(project: Project) -> Dict[str, Any]:
    """A record built from config only (nothing deployed yet / local dev)."""
    record = build_record(project, outputs=None, status="local")
    record.setdefault("key", project.work_dir.name)
    return record


def render_html(records: List[Dict[str, Any]], title: str = "Serverless dashboard") -> str:
    payload = json.dumps(
        {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "deployments": records},
        default=str,
    )
    # Make the JSON safe inside a <script> element.
    payload = payload.replace("</", "<\\/").replace("<!--", "<\\!--")
    values = {"TITLE": html.escape(title), "DATA": payload}
    template = TEMPLATE.read_text("utf-8")
    # One pass, so a title containing a placeholder is never substituted again.
    return _PLACEHOLDER.sub(lambda m: values[m.group(1)], template)


def default_title(records: List[Dict[str, Any]]) -> str:
    services = sorted({r.get("service", "") for r in records if r.get("service")})
    return (" / ".join(services) or "Serverless") + " dashboard"


def write_dashboard(
    root: Path,
    records: Optional[List[Dict[str, Any]]] = None,
    output: Optional[Path] = None,
    title: Optional[str] = None,
) -> Path:
    records = collect_records(root) if records is None else records
    out = output or (root / WORK_DIR / "dashboard" / "index.html")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(render_html(records, title or default_title(records)).encode("utf-8"))
    return out
