"""Content-quality gates for Hana knowledge cards and conversations.

check_knowledge.py checks form (JSON, tool calls, commands, anchors). This file checks whether the content
is worth training on. Every gate is a hard failure. check_knowledge.py calls ``run()``; it can also run alone:

    .venv\\Scripts\\python ai-agent\\training\\tools\\check_quality.py [--examples N]

Gates
  Cards
    C1  a card whose docs source section has a ```yaml / ```python block must contain at least one code block
    C2  no empty sections (a heading followed directly by another heading)
    C3  no paragraph repeated inside one card
    C4  no doc text glued onto a heading line ("## Title Each deployment ...")
  Conversations
    Q1  at least 90% of final assistant answers are unique, and no answer text is used more than 2 times
    Q2  no generator filler or meta talk ("from the card", "This item does not list ...", ...)
    Q3  user messages do not contain card titles ("Concept: x", "Procedure: y", "Resource: z", ...)
    Q4  an "In code" part contains a code block
    Q5  answers do not start mid-sentence or with a broken table fragment
    Q6  no user-message opening (first 4 words) is used by more than 2% of conversations
    Q7  a "search" answer is not just the first line of the tool result
    Q8  a how-to answer has a studio, terminal or code step that is more than a placeholder
"""

from __future__ import annotations

import collections
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TRAIN = ROOT / "ai-agent" / "training"
KNOW = TRAIN / "knowledge"
RAW = TRAIN / "data" / "raw"

FILLER = [
    "from the card",
    "still from the card",
    "the card does not",
    "this card",
    "this item does not list",
    "use the purpose wording",
    "the doc excerpt above",
    "is the source for this answer",
    "same steps",
    "the excerpt says",
    "according to the inventory",
]

TITLE_LEAK = re.compile(
    r"\b(Concept|Procedure|Resource|Studio|On-premises|On-premises service|Troubleshooting|Example|Code|Command): [A-Za-z`]"
)
FENCE = re.compile(r"```[a-zA-Z0-9_+-]*\n.*?```", re.S)
CODE_FENCE_LANG = re.compile(r"^```(yaml|yml|python|py|js|javascript|ts|typescript|json)\s*$", re.M)
IN_CODE = re.compile(r"\*\*In code\*\*|^#+ In code\s*$", re.M)
NEXT_PART = re.compile(r"\*\*In (studio|the terminal)\*\*|^#+ In (studio|the terminal)\s*$|^Sources?:", re.M)
HEADING_LINE = re.compile(r"^(#{1,6}) (.+)$", re.M)


def final_answer(messages: list) -> str:
    for message in reversed(messages):
        if message.get("role") == "assistant" and (message.get("content") or "").strip():
            return message["content"]
    return ""


def doc_section(rel: str, anchor: str) -> str:
    """Text of one docs section (up to the next heading of the same or higher level)."""
    sys.path.insert(0, str(TRAIN / "tools"))
    from extract_docs import github_anchor

    path = ROOT / rel
    if not path.is_file():
        return ""
    lines = path.read_text(encoding="utf-8").splitlines()
    start, level, in_fence = None, 0, False
    for i, line in enumerate(lines):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
        if in_fence:
            continue
        match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if not match:
            continue
        if start is None and github_anchor(match.group(2)) == anchor:
            level = len(match.group(1))
            start = i
            continue
        if start is None:
            continue
        if len(match.group(1)) <= level:
            return "\n".join(lines[start:i])
    if start is not None:
        return "\n".join(lines[start:])
    return ""


def check_cards(errors: list[str]) -> None:
    path = KNOW / "cards.jsonl"
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        card = json.loads(line)
        cid = card.get("id")
        text = card.get("text") or ""
        if not FENCE.search(text):
            for source in card.get("sources") or []:
                if "#" not in source or not source.startswith("docs/"):
                    continue
                rel, anchor = source.split("#", 1)
                if not CODE_FENCE_LANG.search(doc_section(rel, anchor)):
                    continue
                errors.append(f"C1 {cid}: source {source} has a yaml/python block, the card has none")
                break
        body = FENCE.sub("CODE", text)
        if re.search(r"^#{1,6} .+\n\s*\n#{1,6} ", body, re.M) or re.search(r"^#{1,6} .+\n\s*\Z", body, re.M):
            errors.append(f"C2 {cid}: empty section")
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", body) if len(p.strip()) > 60]
        dup = [p for p, n in collections.Counter(paragraphs).items() if n > 1]
        if dup:
            errors.append(f"C3 {cid}: repeated paragraph: {dup[0][:60]!r}")
        for match in HEADING_LINE.finditer(body):
            if len(match.group(2)) > 90:
                errors.append(f"C4 {cid}: text glued onto heading: {match.group(2)[:60]!r}")
                break


def in_code_part(answer: str) -> str | None:
    match = IN_CODE.search(answer)
    if not match:
        return None
    rest = answer[match.end() :]
    nxt = NEXT_PART.search(rest)
    if nxt:
        return rest[: nxt.start()]
    return rest


def check_conversations(errors: list[str], examples: int) -> None:
    rows: list[dict] = []
    for path in sorted(RAW.glob("k_*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rows.append(json.loads(line))
    if not rows:
        return
    found: dict[str, list[str]] = collections.defaultdict(list)

    def hit(gate: str, cid: str, detail: str) -> None:
        found[gate].append(f"{cid}: {detail}")

    answers: collections.Counter[str] = collections.Counter()
    openings: collections.Counter[str] = collections.Counter()
    for row in rows:
        cid = row.get("id")
        messages = row.get("messages") or []
        for message in messages:
            if message.get("role") == "assistant" and (message.get("content") or "").strip():
                answers[message["content"].strip()] += 1
        for message in messages:
            if message.get("role") != "user":
                continue
            text = message.get("content") or ""
            openings[" ".join(text.lower().split()[:4])] += 1
            leaked = TITLE_LEAK.search(text)
            if leaked:
                hit("Q3", cid, f"card title in user message: {text[:70]!r}")
        for message in messages:
            if message.get("role") != "assistant":
                continue
            text = message.get("content") or ""
            low = text.lower()
            for phrase in FILLER:
                if phrase in low:
                    hit("Q2", cid, f"filler {phrase!r}")
                    break
            part = in_code_part(text)
            if part is not None and "```" not in part:
                hit("Q4", cid, "In code part has no code block")
            first = text.strip().splitlines()[0] if text.strip() else ""
            word = first.split()[0] if first.split() else ""
            mid_sentence = word[:1].islower() and word.isalpha() and word not in ("pskit", "hi", "hello")
            if first and (mid_sentence or re.search(r"\|\s*\|---", first)):
                hit("Q5", cid, f"bad start {first[:60]!r}")
            if re.search(r"\S \|---\|", text):
                hit("Q5", cid, "broken table fragment")
        answer = final_answer(messages)
        tools = [m.get("content") or "" for m in messages if m.get("role") == "tool"]
        if tools and answer:
            lines = [ln for ln in tools[0].splitlines() if ln.strip() and not ln.startswith("[")]
            if lines and answer.strip().splitlines()[0].strip() == lines[0].strip():
                hit("Q7", cid, "answer opens with the excerpt's first line copied")
        if "**In studio**" in answer or "**In the terminal**" in answer:
            placeholders = ("does not list a studio button", "does not include a sample command")
            if any(p in answer for p in placeholders):
                hit("Q8", cid, "placeholder step instead of a real one")
    total = sum(answers.values())
    unique_share = (len(answers) / total) if total else 1
    if unique_share < 0.9:
        found["Q1"].append(f"only {unique_share:.1%} of assistant messages are unique ({len(answers)}/{total})")
    for text, n in answers.most_common():
        if n <= 2:
            break
        found["Q1"].append(f"answer used {n} times: {text[:60]!r}")
    limit = max(1, int(0.02 * len(rows)))
    for opening, n in openings.most_common():
        if n <= limit:
            break
        found["Q6"].append(f"opening {opening!r} used {n} times (limit {limit})")
    for gate in sorted(found):
        items = found[gate]
        bad_ids = {item.split(":", 1)[0] for item in items}
        errors.append(f"{gate}: {len(items)} hits in {len(bad_ids)} items")
        for item in items[:examples]:
            errors.append(f"  {gate} {item}")


def run(errors: list[str], examples: int = 3) -> None:
    check_cards(errors)
    check_conversations(errors, examples)


def main() -> int:
    examples = 3
    if "--examples" in sys.argv:
        examples = int(sys.argv[sys.argv.index("--examples") + 1])
    errors: list[str] = []
    run(errors, examples)
    for msg in errors:
        print(("" if msg.startswith("  ") else "QUALITY ") + msg)
    print("quality errors=" + str(sum(1 for msg in errors if not msg.startswith("  "))))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
