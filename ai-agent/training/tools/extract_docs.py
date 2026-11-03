"""List every Markdown file under docs/ with heading text and GitHub-style anchors.

Writes ai-agent/training/knowledge/docs_headings.json. Anchors follow GitHub's
algorithm (lowercase, strip punctuation, collapse spaces to hyphens) so later
cards can cite docs/file.md#anchor.
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DOCS = ROOT / "docs"
OUT = ROOT / "ai-agent" / "training" / "knowledge" / "docs_headings.json"

HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


def github_anchor(text: str) -> str:
    """GitHub heading slug (github-slugger): lowercase, drop punctuation, keep underscores.

    Link text is kept and the URL is dropped. Emphasis markers and other
    punctuation in the github-slugger set are removed. Spaces become hyphens.
    """
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = unicodedata.normalize("NFKD", text)
    text = text.lower().strip()
    text = re.sub(r"[\u2000-\u206F\u2E00-\u2E7F\\'\"!#$%&()*+,./:;<=>?@\[\]^`{|}~]", "", text)
    text = re.sub(r"\s+", "-", text)
    return text


def main() -> None:
    files = []
    for path in sorted(DOCS.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT).as_posix()
        if path.suffix.lower() != ".md":
            files.append({"path": rel, "kind": "other", "headings": []})
            continue
        headings = []
        seen: dict[str, int] = {}
        in_fence = False
        for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if line.lstrip().startswith("```"):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            match = HEADING.match(line)
            if not match:
                continue
            title = match.group(2).strip()
            anchor = github_anchor(title)
            count = seen.get(anchor, 0)
            seen[anchor] = count + 1
            if count:
                anchor = f"{anchor}-{count}"
            headings.append(
                {
                    "level": len(match.group(1)),
                    "title": title,
                    "anchor": anchor,
                    "line": index,
                }
            )
        files.append({"path": rel, "kind": "markdown", "headings": headings})
    payload = {
        "root": "docs",
        "file_count": len(files),
        "markdown_count": sum(1 for item in files if item["kind"] == "markdown"),
        "heading_count": sum(len(item["headings"]) for item in files),
        "files": files,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes((json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
    print(f"files={payload['file_count']} markdown={payload['markdown_count']} headings={payload['heading_count']}")


if __name__ == "__main__":
    main()
