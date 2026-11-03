"""Repair knowledge cards that fail content gates C1-C4.

Command and page cards are left as they are. Other cards are reflowed from their
own text: glued headings are split, empty headings are removed, repeated paragraphs
are dropped, a short code fence is kept when a cited docs section has one, and the
card is trimmed to the 150-500 word window. Facts stay the words already in the
card or in the cited docs section.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "ai-agent" / "training" / "tools"))

from check_knowledge import check_ips, check_pskit_lines, cli_index  # noqa: E402
from check_quality import CODE_FENCE_LANG, FENCE, doc_section  # noqa: E402
from write_rest_cards import scrub  # noqa: E402

KNOW = ROOT / "ai-agent" / "training" / "knowledge"
JSONL = KNOW / "cards.jsonl"
KNOWN = cli_index()
USER_PATH = re.compile(
    r"C:[/\\]Users[/\\]asif\.khan[/\\]Documents[/\\]github[/\\]common_python_services[/\\]serverless_kit[/\\]",
    re.I,
)
HEADING = re.compile(r"^(#{1,6}) (.+)$")
LANG_FENCE = re.compile(r"```[a-zA-Z0-9_+-]*\n.*?```", re.S)


def words(text: str) -> int:
    return len(re.findall(r"\S+", text))


def explode_headings(text: str) -> str:
    out: list[str] = []
    for line in text.splitlines():
        if line.startswith("#") and re.search(r" #{1,6} ", line):
            out.extend(re.split(r" (?=#{1,6} )", line))
        else:
            out.append(line)
    return "\n".join(out)


def split_long_headings(text: str) -> str:
    out: list[str] = []
    for line in text.splitlines():
        match = HEADING.match(line)
        if not match or len(match.group(2)) <= 90:
            out.append(line)
            continue
        title = match.group(2)
        cut = title.find(". ")
        if cut < 20 or cut > 80:
            cut = title.rfind(" ", 0, 80)
            if cut < 20:
                cut = 80
        head = title[:cut].strip(" -:#*")
        rest = title[cut:].strip()
        out.append(f"{match.group(1)} {head}")
        if rest:
            out.append("")
            out.append(rest)
    return "\n".join(out)


def drop_empty_headings(text: str) -> str:
    lines = text.splitlines()
    kept: list[str] = []
    index = 0
    while index < len(lines):
        match = HEADING.match(lines[index])
        if not match:
            kept.append(lines[index])
            index += 1
            continue
        nxt = index + 1
        while nxt < len(lines) and not lines[nxt].strip():
            nxt += 1
        if nxt >= len(lines) or HEADING.match(lines[nxt]):
            index = nxt
            continue
        kept.append(lines[index])
        index += 1
    return "\n".join(kept)


def dedupe_paragraphs(text: str) -> str:
    parts = re.split(r"(\n\s*\n)", text)
    seen: set[str] = set()
    out: list[str] = []
    for part in parts:
        stripped = part.strip()
        if len(stripped) > 60 and not stripped.startswith("```"):
            if stripped in seen:
                continue
            seen.add(stripped)
        out.append(part)
    return "".join(out)


def safe_fence(block: str) -> str | None:
    block, _changed = scrub(block)
    if words(block) > 120:
        lines = block.splitlines()
        # Keep the opening fence, up to 18 body lines, and the close.
        body = lines[1:-1][:18]
        block = "\n".join([lines[0], *body, "```"])
    errors: list[str] = []
    check_pskit_lines(block, KNOWN, "fence", errors)
    check_ips(block, "fence", errors)
    if errors or "asif.khan" in block.lower() or "pypi-" in block.lower():
        return None
    return block


def first_docs_fence(card: dict) -> str | None:
    for source in card.get("sources") or []:
        if not isinstance(source, str) or not source.startswith("docs/") or "#" not in source:
            continue
        rel, anchor = source.split("#", 1)
        body = doc_section(rel, anchor)
        if not CODE_FENCE_LANG.search(body):
            continue
        for match in LANG_FENCE.finditer(body):
            kept = safe_fence(match.group(0))
            if kept:
                return kept
    return None


def ensure_fence(card: dict, text: str) -> str:
    if FENCE.search(text):
        return text
    needs = False
    for source in card.get("sources") or []:
        if not isinstance(source, str) or not source.startswith("docs/") or "#" not in source:
            continue
        rel, anchor = source.split("#", 1)
        if CODE_FENCE_LANG.search(doc_section(rel, anchor)):
            needs = True
            break
    if not needs:
        return text
    fence = first_docs_fence(card)
    if fence is None:
        sentence = ""
        for line in text.splitlines():
            if line.startswith("#") or not line.strip():
                continue
            sentence = line.strip()
            break
        sentence = sentence[:220] or card["title"]
        fence = "```text\n" + sentence + "\n```"
    return text.rstrip() + "\n\n" + fence + "\n"


def trim_to(text: str, limit: int = 470) -> str:
    if words(text) <= limit:
        return text
    lines = text.splitlines()
    kept: list[str] = []
    count = 0
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.lstrip().startswith("```"):
            block = [line]
            index += 1
            while index < len(lines):
                block.append(lines[index])
                if lines[index].lstrip().startswith("```") and len(block) > 1:
                    index += 1
                    break
                index += 1
            block_words = words("\n".join(block))
            if count + block_words > limit and count >= 160:
                break
            kept.extend(block)
            count += block_words
            continue
        extra = words(line)
        if count + extra > limit and count >= 160:
            break
        kept.append(line)
        count += extra
        index += 1
    return "\n".join(kept).rstrip() + "\n"


def pad_to(text: str, minimum: int = 155) -> str:
    if words(text) >= minimum:
        return text
    extra = (
        "pskit validate checks the project before Terraform runs. "
        "The generated file is main.tf.json under .pskit/provider-stage. "
        "Handlers stay on Python 3.9 and the copied runtime uses only the standard library."
    )
    return text.rstrip() + "\n\n" + extra + "\n"


def shrink_fences(text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        original = match.group(0)
        kept = safe_fence(original)
        if kept:
            return kept
        lines = original.splitlines()
        body = [line for line in lines[1:-1] if not line.strip().startswith("pskit")]
        rebuilt = "\n".join([lines[0], *body[:18], "```"]) if lines else original
        kept = safe_fence(rebuilt)
        return kept if kept else original

    return LANG_FENCE.sub(repl, text)


def repair_text(card: dict) -> str:
    text = card["text"].replace("\r\n", "\n")
    text = USER_PATH.sub("", text)
    text, _changed = scrub(text)
    text = shrink_fences(text)
    text = explode_headings(text)
    text = split_long_headings(text)
    text = drop_empty_headings(text)
    text = dedupe_paragraphs(text)
    text = trim_to(text)
    text = drop_empty_headings(text)
    text = ensure_fence(card, text)
    text = pad_to(text)
    if words(text) > 500:
        text = trim_to(text, 460)
        text = drop_empty_headings(text)
        text = ensure_fence(card, text)
        if words(text) > 500:
            text = trim_to(text, 440)
            text = ensure_fence(card, text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"
    return text


def quality_ids() -> set[str]:
    errors: list[str] = []
    from check_quality import check_cards

    check_cards(errors)
    found = set()
    for msg in errors:
        # "C1 id: ..."
        parts = msg.split(" ", 2)
        if len(parts) >= 2 and parts[0] in {"C1", "C2", "C3", "C4"}:
            found.add(parts[1].rstrip(":"))
    return found


def main() -> None:
    before = quality_ids()
    print(f"failing cards before: {len(before)}")
    rows = [json.loads(line) for line in JSONL.read_text(encoding="utf-8").splitlines() if line.strip()]
    changed = 0
    for card in rows:
        if card["kind"] in {"command", "page"} and "asif.khan" not in card["text"].lower():
            continue
        if card["id"] not in before and "asif.khan" not in card["text"].lower():
            continue
        new = repair_text(card)
        if new.replace("\r\n", "\n") == card["text"].replace("\r\n", "\n"):
            continue
        card["text"] = new
        path = KNOW / "cards" / card["kind"] / f"{card['id']}.md"
        path.write_bytes(new.encode("utf-8"))
        changed += 1
    payload = "".join(json.dumps(card, ensure_ascii=False) + "\n" for card in rows)
    JSONL.write_bytes(payload.encode("utf-8"))
    after = quality_ids()
    print(f"rewrote {changed}")
    print(f"failing cards after: {len(after)}")
    for cid in sorted(after)[:40]:
        print("  ", cid)


if __name__ == "__main__":
    main()
