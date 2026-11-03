"""Collect module one-liners, resource-guide titles and studio UI strings.

Writes knowledge/facts.json. Used while building inventory.md. Strings are
copied from source files; this script does not interpret them.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "ai-agent" / "training" / "knowledge" / "facts.json"

DOC = re.compile(r'^"""(.*?)"""', re.DOTALL)
H1 = re.compile(r"^#\s+(.+)$", re.MULTILINE)
# Visible-ish JSX text and common label props. Noise is filtered below.
TEXT = re.compile(
    r"""(?:aria-label|title|label|placeholder|addLabel|emptyHint|subtitle|hint)=["']([^"']{2,120})["']"""
    r"""|>\s*([A-Za-z][^<>{}\n]{1,80})\s*<"""
)


def first_sentence(text: str) -> str:
    line = " ".join(part.strip() for part in text.strip().splitlines() if part.strip())
    line = line.replace("``", "`")
    if ". " in line:
        line = line.split(". ")[0].rstrip(".") + "."
    return line[:240]


def modules() -> list[dict[str, str]]:
    rows = []
    base = ROOT / "src" / "py_serverless_kit"
    for path in sorted(base.rglob("*.py")):
        if path.name == "__init__.py" and path.parent.name == "py_serverless_kit":
            rel = "src/py_serverless_kit/__init__.py"
        else:
            rel = path.relative_to(ROOT).as_posix()
        if "/__pycache__/" in rel or path.name.endswith(".pyc"):
            continue
        raw = path.read_text(encoding="utf-8")
        match = DOC.match(raw)
        summary = first_sentence(match.group(1)) if match else ""
        rows.append({"path": rel, "summary": summary})
    return rows


def guides() -> list[dict[str, str]]:
    rows = []
    base = ROOT / "docs" / "resource-guides"
    for path in sorted(base.rglob("*.md")):
        raw = path.read_text(encoding="utf-8")
        match = H1.search(raw)
        rows.append(
            {
                "path": path.relative_to(ROOT).as_posix(),
                "title": match.group(1).strip() if match else "",
            }
        )
    return rows


def studio_strings() -> dict[str, list[str]]:
    base = ROOT / "dashboard-ui" / "src" / "studio"
    out: dict[str, list[str]] = {}
    skip = re.compile(r"^(className|import |export |const |function |return |if |true|false|null|undefined)$")
    for path in sorted(base.rglob("*.tsx")):
        raw = path.read_text(encoding="utf-8")
        found: list[str] = []
        for match in TEXT.finditer(raw):
            text = (match.group(1) or match.group(2) or "").strip()
            text = re.sub(r"\s+", " ", text)
            if len(text) < 2 or skip.match(text):
                continue
            if text.startswith("{") or "className" in text:
                continue
            if text not in found:
                found.append(text)
        out[path.relative_to(ROOT).as_posix()] = found
    return out


def main() -> None:
    payload = {"modules": modules(), "guides": guides(), "studio_strings": studio_strings()}
    OUT.write_bytes((json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
    print(f"modules={len(payload['modules'])} guides={len(payload['guides'])} studio_files={len(payload['studio_strings'])}")


if __name__ == "__main__":
    main()
