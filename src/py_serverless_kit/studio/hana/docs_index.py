"""The docs cards Hana searches next to her trained knowledge cards: every ``docs/**/*.md`` cut at its H2 headings.

``docs.jsonl.gz`` (next to this file) is generated, not edited: run ``python scripts/build_hana_docs_index.py`` after
changing anything under ``docs/``. ``tests/studio/test_hana.py`` fails when the shipped file is out of date.

A card is ``{"id", "kind": "doc", "title", "tags", "text", "sources": ["docs/<path>.md#<anchor>"]}``. Its text starts
with a title paragraph (``<page title> > <section>``) so the excerpt Hana gets names the page; the page's
``Search terms:`` line goes into ``tags`` of every card of that page, so a section is found by the page's synonyms.
The output is byte-reproducible (sorted files, LF, gzip mtime 0).
"""

from __future__ import annotations

import gzip
import io
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

INDEX = Path(__file__).with_name("docs.jsonl.gz")
MAX_CARD = 6000  # characters; a longer section is cut again at its H3 headings
_TERMS = re.compile(r"^\s*search terms\s*:\s*(.+)$", re.I | re.M)
_FENCE = re.compile(r"^\s*(```|~~~)")


def anchor(heading: str) -> str:
    """The GitHub anchor of a heading: lower case, punctuation except ``-`` and ``_`` dropped, spaces to dashes."""
    text = re.sub(r"[^\w\- ]", "", heading.strip().lower())
    return text.replace(" ", "-")


def _sections(lines: List[str], level: str) -> List[Dict[str, Any]]:
    """Split ``lines`` at headings of ``level`` (``"## "`` or ``"### "``) outside code fences."""
    out: List[Dict[str, Any]] = [{"heading": "", "lines": []}]
    fenced = False
    for line in lines:
        if _FENCE.match(line):
            fenced = not fenced
        if not fenced and line.startswith(level):
            out.append({"heading": line[len(level):].strip(), "lines": []})
        else:
            out[-1]["lines"].append(line)
    return out


def _body(lines: List[str]) -> str:
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def page_cards(rel: str, text: str) -> List[Dict[str, Any]]:
    """The cards of one page. ``rel`` is the repo path (``docs/guide/README.md``)."""
    text = text.replace("\r\n", "\n")
    terms_match = _TERMS.search(text)
    tags = [t.strip() for t in terms_match.group(1).split(",") if t.strip()] if terms_match else []
    lines = [ln for ln in text.split("\n") if not _TERMS.match(ln)]
    title = next((ln[2:].strip() for ln in lines if ln.startswith("# ")), Path(rel).stem)
    lines = [ln for ln in lines if not (ln.startswith("# ") and ln[2:].strip() == title)]
    cards: List[Dict[str, Any]] = []

    def add(heading: str, sub: Optional[str], body: str) -> None:
        if not body or heading.lower() == "see also":
            return
        name = sub or heading
        label = " > ".join(x for x in (title, heading, sub) if x)
        cards.append({
            "id": f"{rel}#{anchor(name) if name else ''}".rstrip("#"),
            "kind": "doc",
            "title": label,
            "tags": tags,
            "text": f"{label}\n\n{body}",
            "sources": [f"{rel}#{anchor(name)}" if name else rel],
        })

    for sec in _sections(lines, "## "):
        body = _body(sec["lines"])
        if len(body) <= MAX_CARD:
            add(sec["heading"], None, body)
            continue
        for i, part in enumerate(_sections(sec["lines"], "### ")):
            add(sec["heading"], part["heading"] or None if i else None, _body(part["lines"]))
    return cards


def build(repo: Path) -> List[Dict[str, Any]]:
    docs = repo / "docs"
    cards: List[Dict[str, Any]] = []
    for path in sorted(docs.rglob("*.md"), key=lambda p: p.relative_to(repo).as_posix()):
        rel = path.relative_to(repo).as_posix()
        cards.extend(page_cards(rel, path.read_text(encoding="utf-8")))
    return cards


def encode(cards: List[Dict[str, Any]]) -> bytes:
    """The gzip bytes of ``cards``, identical for identical input on every OS."""
    raw = "".join(json.dumps(c, ensure_ascii=False, sort_keys=True) + "\n" for c in cards).encode("utf-8")
    buf = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=buf, mtime=0) as handle:
        handle.write(raw)
    return buf.getvalue()


def load() -> List[Dict[str, Any]]:
    if not INDEX.is_file():
        return []
    with gzip.open(INDEX, "rt", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]
