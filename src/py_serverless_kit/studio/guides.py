"""The step-by-step resource guides (``docs/resource-guides``) for the studio.

The wheel ships them as ``py_serverless_kit/studio/guides`` (hatch ``force-include``);
a source checkout reads ``docs/resource-guides`` directly, so there is one copy.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from .project import StudioError

_PAGE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,40}$")
_TITLE = re.compile(r"^#\s+(.+)$", re.MULTILINE)
_ORDER = ["onprem", "aws", "gcp", "azure", "alibaba", "tencent", "huawei", "oracle", "ibm", "digitalocean", "cloudflare"]


def guides_dir() -> Optional[Path]:
    here = Path(__file__).resolve().parent
    for candidate in (here / "guides", here.parents[2] / "docs" / "resource-guides"):
        if (candidate / "README.md").is_file():
            return candidate
    return None


def _title(path: Path) -> str:
    match = _TITLE.search(path.read_text("utf-8"))
    return match.group(1).strip() if match else path.stem


def index() -> Dict[str, Any]:
    base = guides_dir()
    if base is None:
        return {"available": False, "clouds": []}
    clouds: List[Dict[str, Any]] = []
    # Pages next to README (compatibility, ...): the "General" group, shown first.
    general = [{"id": "readme", "title": _title(base / "README.md")}] + [
        {"id": page.stem.lower(), "title": _title(page)} for page in sorted(base.glob("*.md")) if page.stem != "README"
    ]
    clouds.append({"id": "index", "title": "General", "pages": general})
    for folder in sorted((p for p in base.iterdir() if p.is_dir()), key=lambda p: (_ORDER + [p.name]).index(p.name)):
        pages = [
            {"id": page.stem.lower(), "title": _title(page)}
            for page in sorted(folder.glob("*.md"), key=lambda p: (p.stem != "README", p.stem))
        ]
        if pages:
            clouds.append({"id": folder.name, "title": pages[0]["title"], "pages": pages})
    return {"available": True, "clouds": clouds}


def page(cloud: str, name: str) -> Dict[str, Any]:
    base = guides_dir()
    if base is None:
        raise StudioError(404, "resource guides are not installed")
    if not _PAGE.match(cloud) or not _PAGE.match(name):
        raise StudioError(400, "invalid guide name")
    folder = base if cloud == "index" else base / cloud
    filename = "README.md" if name in ("readme", "index") else f"{name}.md"
    path = folder / filename
    if not path.is_file():
        raise StudioError(404, f"no guide {cloud}/{name}")
    return {"cloud": cloud, "page": name, "title": _title(path), "markdown": path.read_text("utf-8")}
