"""Rejoin card paragraphs that were split mid-sentence. One-shot repair."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "ai-agent" / "training" / "tools"))

from check_quality import doc_section  # noqa: E402

KNOW = ROOT / "ai-agent" / "training" / "knowledge"
JSONL = KNOW / "cards.jsonl"
CARDS = KNOW / "cards"

DANGLING = {
    "a", "an", "the", "of", "to", "in", "on", "for", "and", "or", "with", "from", "by",
    "how", "that", "as", "at", "into", "over", "its", "their", "your", "this", "when",
    "which", "who", "than", "per", "via", "if", "is", "are", "was", "be", "one", "each",
    "all", "any", "no", "not", "also", "only", "both", "such", "these", "those", "where",
    "while", "after", "before", "about", "between", "under", "without", "within",
    "during", "plus", "using", "including", "like", "through", "across", "around",
    "against", "until", "onto", "off", "out", "because", "since", "although", "though",
    "whether", "either", "every", "some", "many", "most", "other", "another", "same",
    "own", "more", "less", "what", "why", "whose", "can", "will", "may", "must",
    "should", "would", "could", "has", "have", "had", "does", "did", "but", "nor",
    "yet", "so", "up", "down", "it", "they", "we", "you", "he", "she", "them",
    "his", "her", "our", "my", "there", "here", "then", "just", "still", "already",
    "very", "too", "enough", "been", "being", "were", "am", "do", "don", "isn",
    "aren", "wasn", "weren", "won", "wouldn", "shouldn", "couldn", "mustn",
}

HEADING = re.compile(r"^(#{1,6}) (.+)$")
END_SENT = re.compile(r"[.!?][\"'`)\]]*\s*$")


def last_word(text: str) -> str:
    words = re.findall(r"[A-Za-z']+", text)
    return words[-1].lower() if words else ""


def unbalanced(text: str) -> bool:
    if text.count("(") != text.count(")"):
        return True
    if text.count("`") % 2:
        return True
    if text.count("**") % 2:
        return True
    # A single leftover italic marker, ignoring ** pairs.
    bare = text.replace("**", "")
    return bare.count("*") % 2 == 1


def end_ok(text: str) -> bool:
    return bool(END_SENT.search(text.rstrip()))


def continuation(nxt: str) -> bool:
    stripped = nxt.lstrip()
    if not stripped:
        return False
    if stripped.startswith(("#", "```", "|", "-", "*")):
        return False
    return True


def should_join(prev: str, nxt: str) -> bool:
    if not continuation(nxt):
        return False
    bare = prev.strip()
    if bare.startswith(("|", "-", "*", ">", "```")):
        return False
    if re.match(r"^pskit(\s|$)", bare):
        return False
    if re.match(
        r"^(Related|Sources|Safety|Studio equivalent|Purpose|When to use|Usage|Options|Examples)\b",
        nxt.lstrip(),
    ):
        return False
    if end_ok(bare):
        return False
    body = HEADING.sub(r"\2", bare) if bare.startswith("#") else bare
    if unbalanced(body) or last_word(body) in DANGLING:
        return True
    if len(body) >= 68 and (nxt.lstrip()[:1].islower() or nxt.lstrip()[:1] in "+0123456789"):
        return True
    return False


def rejoin(text: str) -> tuple[str, int]:
    lines = text.splitlines()
    joins = 0
    changed = True
    while changed:
        changed = False
        in_fence = False
        i = 0
        while i < len(lines):
            if lines[i].lstrip().startswith("```"):
                in_fence = not in_fence
                i += 1
                continue
            if in_fence or not lines[i].strip():
                i += 1
                continue
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines) and j > i + 1 and not in_fence and should_join(lines[i], lines[j]):
                lines[i] = lines[i].rstrip() + " " + lines[j].lstrip()
                del lines[i + 1 : j + 1]
                joins += 1
                changed = True
                continue
            i += 1
    return "\n".join(lines), joins


def peel_heading(line: str) -> list[str]:
    match = HEADING.match(line)
    if not match or len(match.group(2)) <= 90:
        return [line]
    hashes, title = match.group(1), match.group(2)

    def split_at(cut: int) -> list[str] | None:
        head = title[:cut].strip()
        if not 12 <= len(head) <= 90:
            return None
        rest = title[cut:].strip()
        out = [f"{hashes} {head}"]
        if rest:
            out.extend(["", rest])
        return out

    for punct in re.finditer(r"[.!?](?:\s|$)", title):
        chosen = split_at(punct.end())
        if chosen:
            return chosen
    # After a short parenthetical, e.g. "storage (`type: storage`) Run...".
    paren = re.match(r"^(.{12,80}?\([^)]{0,40}\))(\s+\S.+)$", title)
    if paren and paren.group(1).count("(") == paren.group(1).count(")"):
        chosen = split_at(len(paren.group(1)))
        if chosen and chosen[0].count("(") == chosen[0].count(")"):
            return chosen
    for boundary in re.finditer(r"\s+(?=[A-Z])", title):
        left = title[: boundary.start()]
        if last_word(left) in DANGLING or unbalanced(left):
            continue
        chosen = split_at(boundary.start())
        if chosen:
            return chosen
    cut = title.rfind(" ", 0, 88)
    if cut < 12:
        cut = 88
    return split_at(cut) or [line]


def peel(text: str) -> str:
    out: list[str] = []
    in_fence = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            out.append(line)
            continue
        if in_fence:
            out.append(line)
            continue
        out.extend(peel_heading(line))
    return "\n".join(out)


def paragraphs(text: str) -> list[tuple[int, int]]:
    """Return (start, end) line indexes of non-fence paragraphs, end exclusive."""
    lines = text.splitlines()
    spans = []
    in_fence = False
    start = None
    for i, line in enumerate(lines):
        if line.lstrip().startswith("```"):
            if start is not None:
                spans.append((start, i))
                start = None
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if line.lstrip().startswith("#"):
            if start is not None:
                spans.append((start, i))
                start = None
            spans.append((i, i + 1))
            continue
        if line.strip():
            if start is None:
                start = i
        elif start is not None:
            spans.append((start, i))
            start = None
    if start is not None:
        spans.append((start, len(lines)))
    return spans


def para_text(lines: list[str], start: int, end: int) -> str:
    return " ".join(line.strip() for line in lines[start:end])


def is_skippable(text: str) -> bool:
    stripped = text.strip()
    if stripped.startswith("#") or stripped.startswith("|") or stripped.startswith("- ") or stripped.startswith("* "):
        return True
    if stripped.startswith("```"):
        return True
    return False


def scrub_ips(text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        ip = match.group(0)
        parts = [int(p) for p in ip.split(".")]
        if parts[0] == 127 or ip == "0.0.0.0":
            return ip
        if tuple(parts[:3]) in {(192, 0, 2), (198, 51, 100), (203, 0, 113)}:
            return ip
        return "192.0.2.10"

    return re.sub(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", repl, text)


def finish_cutoffs(text: str, sources: list[str]) -> tuple[str, int]:
    """Finish a cut-off paragraph from its own doc section, or drop only the dangling tail."""
    docs = []
    for source in sources:
        if isinstance(source, str) and source.startswith("docs/") and "#" in source:
            rel, anchor = source.split("#", 1)
            body = doc_section(rel, anchor)
            if body:
                docs.append(re.sub(r"\s+", " ", body))
    lines = text.splitlines()
    fixes = 0
    spans = paragraphs(text)
    for start, end in reversed(spans):
        blob = para_text(lines, start, end)
        if len(blob) <= 80 or END_SENT.search(blob) or is_skippable(blob):
            continue
        if blob.lstrip().startswith("|") or "\n|" in "\n".join(lines[start:end]):
            # A broken table stays a table. Closing it with a period would invent a sentence.
            continue
        tail_words = blob.split()[-10:]
        tail = " ".join(tail_words)
        completed = ""
        if len(tail) >= 40:
            for doc in docs:
                at = doc.find(tail)
                if at < 0:
                    continue
                rest = doc[at + len(tail) :]
                stop = len(rest)
                for mark in (". ", "! ", "? "):
                    pos = rest.find(mark)
                    if 0 <= pos < stop:
                        stop = pos + 1
                extra = rest[:stop].strip()
                if not extra or len(extra) > 220:
                    continue
                if re.search(r"(?i)password\s*[:=]|:[A-Za-z0-9]{3,}@", extra):
                    continue
                completed = scrub_ips(blob + (" " if not blob.endswith(" ") else "") + extra)
                break
        if not completed:
            sentence_end = max(blob.rfind(". "), blob.rfind("! "), blob.rfind("? "))
            if sentence_end >= 40:
                completed = blob[: sentence_end + 1].rstrip()
            else:
                continue
        lines[start:end] = [completed]
        fixes += 1
    text = "\n".join(lines).rstrip() + "\n"
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text, fixes


def main() -> None:
    source = KNOW / "index_source.jsonl"
    rows = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines() if line.strip()]
    joined = peeled = cut = 0
    for card in rows:
        original = card["text"].replace("\r\n", "\n")
        text, njoin = rejoin(original)
        joined += njoin
        text = peel(text)
        if text != original:
            peeled += 1
        ncut = 0
        cut += ncut
        card["text"] = text if text.endswith("\n") else text + "\n"
        path = CARDS / card["kind"] / f"{card['id']}.md"
        path.write_text(card["text"], encoding="utf-8", newline="\n")
    JSONL.write_text("".join(json.dumps(card, ensure_ascii=False) + "\n" for card in rows), encoding="utf-8")
    print(f"cards={len(rows)} joins={joined} changed_cards={peeled} cutoff_fixes={cut}")


if __name__ == "__main__":
    main()
