"""Print button and nav-link labels from dashboard-ui/src/studio."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
STUDIO = ROOT / "dashboard-ui" / "src" / "studio"
PAT = re.compile(r"<(button|a)\b([^>]*)>(.*?)</\1>", re.S)
TAG = re.compile(r"<[^>]+>")
LIT = re.compile(r"""["']([A-Za-z][^"']{1,70})["']""")


def label(body: str) -> str:
    text = TAG.sub(" ", body)
    text = re.sub(r"\s+", " ", text).strip()
    text = text.replace("&amp;", "&").replace("&apos;", "'")
    if text and not text.startswith("{") and len(text) > 1:
        return text[:120]
    lits = LIT.findall(body)
    return " | ".join(lits)[:120]


def main() -> None:
    for path in sorted(STUDIO.rglob("*.tsx")):
        raw = path.read_text(encoding="utf-8")
        rows = []
        for match in PAT.finditer(raw):
            attrs = match.group(2)
            if match.group(1) == "a" and "btn" not in attrs and "nav-item" not in attrs:
                continue
            text = label(match.group(3))
            if text and text not in rows:
                rows.append(text)
        if not rows:
            continue
        print("==", path.relative_to(ROOT).as_posix())
        for row in rows:
            print(" *", row)


if __name__ == "__main__":
    main()
