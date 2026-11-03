"""Find card paragraphs split mid-sentence. Inspection only."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
cards = [
    json.loads(line)
    for line in (ROOT / "ai-agent/training/knowledge/cards.jsonl").read_text(encoding="utf-8").splitlines()
    if line.strip()
]
END = re.compile(r"[.!?:`)\]]\s*$")
hits = []
for card in cards:
    lines = card["text"].splitlines()
    in_fence = False
    for i, line in enumerate(lines):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence or not line.strip():
            continue
        if line.lstrip().startswith(("-", "*", "|", ">")):
            continue
        if END.search(line.rstrip()) and not line.lstrip().startswith("#"):
            continue
        j = i + 1
        while j < len(lines) and not lines[j].strip():
            j += 1
        if j >= len(lines):
            if len(line.strip()) > 80:
                hits.append((card["id"], "cutoff-eof", line.strip()[:90]))
            continue
        nxt = lines[j].strip()
        if nxt.startswith(("```", "#", "-", "*", "|")):
            if len(line.strip()) > 80:
                hits.append((card["id"], "cutoff-next", line.strip()[:90]))
            continue
        blank = j > i + 1
        kind = "blank-split" if blank else "wrap"
        if nxt[:1].islower():
            hits.append((card["id"], kind, line.strip() + " || " + nxt))
from collections import Counter
out = ROOT / "ai-agent/training/tools/_card_breaks.txt"
lines_out = [
    f"hits {len(hits)} cards {len({h[0] for h in hits})}",
    str(Counter(h[1] for h in hits)),
    "",
]
for kind in ("blank-split", "cutoff-eof", "cutoff-next"):
    lines_out.append(f"===== {kind} =====")
    for row in hits:
        if row[1] == kind:
            lines_out.append(f"--- {row[0]}")
            lines_out.append(row[2])
            lines_out.append("")
out.write_text("\n".join(lines_out), encoding="utf-8")
print("wrote", out, "hits", len(hits))
