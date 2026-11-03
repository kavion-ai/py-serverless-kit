"""Plan conversation slots. Does not write questions or answers."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "ai-agent" / "training" / "tools"))

from check_quality import doc_section  # noqa: E402

KNOW = ROOT / "ai-agent" / "training" / "knowledge"
SLOTS = ROOT / "ai-agent" / "training" / "data" / "slots"
CARDS = [json.loads(line) for line in (KNOW / "cards.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]

TARGETS = {
    "k_cmd": 1100,
    "k_nav": 600,
    "k_res": 700,
    "k_onprem": 700,
    "k_scale": 450,
    "k_arch": 450,
    "k_proc": 350,
    "k_trouble": 150,
    "k_about": 100,
}
PERSONAS = (
    [("beginner", 20), ("informal_non_native", 25), ("terse_expert", 15), ("ops_engineer", 15), ("aws_migrator", 10), ("contributor", 15)]
)
PROVIDERS = ["aws", "azure", "gcp", "alibaba", "tencent", "huawei", "oracle", "ibm", "digitalocean", "cloudflare", "onprem"]
STAGES = ["dev", "staging", "prod"]
MODES = ["ask", "auto"]
PAGES = [
    "Overview", "Setup", "Functions", "Workflows", "Resources", "Cluster",
    "Load balancers", "Network map", "Code", "Test", "Deploy", "Logs", "YAML", "none",
]


def bucket_of(card: dict) -> str:
    kind = card["kind"]
    cid = card["id"]
    if kind == "command":
        return "k_cmd"
    if kind == "page":
        return "k_nav"
    if kind == "resource":
        return "k_res"
    if kind == "troubleshooting":
        return "k_trouble"
    if kind == "procedure":
        return "k_proc"
    if kind == "onprem":
        if any(tok in cid for tok in ("cluster", "lb-", "firewall", "network", "placement", "tunnel")):
            return "k_scale"
        return "k_onprem"
    return "k_arch"


def spread(count: int, total: int) -> list[int]:
    base, extra = divmod(total, count)
    return [base + (1 if i < extra else 0) for i in range(count)]


def paragraph_excerpt(source: str) -> str:
    if not source.startswith("docs/") or "#" not in source:
        return ""
    rel, anchor = source.split("#", 1)
    body = doc_section(rel, anchor)
    if not body:
        return ""
    # Keep the cited heading's own text. A child heading is a different topic.
    kept = []
    for line in body.splitlines()[1:]:
        if line.startswith("#"):
            break
        kept.append(line)
    body = "\n".join(kept)
    chunks = []
    buf: list[str] = []
    in_fence = False
    for line in body.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence or line.lstrip().startswith("#"):
            if buf:
                chunks.append(" ".join(x.strip() for x in buf if x.strip()))
                buf = []
            continue
        if not line.strip():
            if buf:
                chunks.append(" ".join(x.strip() for x in buf if x.strip()))
                buf = []
            continue
        buf.append(line)
    if buf:
        chunks.append(" ".join(x.strip() for x in buf if x.strip()))
    # Prefer a real paragraph in the 300-1500 window. Join short neighbors if needed.
    text = ""
    for chunk in chunks:
        if 300 <= len(chunk) <= 1500 and chunk[-1] in ".!?":
            text = chunk
            break
    if not text:
        joined = ""
        for chunk in chunks:
            if chunk.startswith("|") or chunk.startswith("-"):
                continue
            piece = (joined + " " + chunk).strip()
            if len(piece) > 1500:
                break
            joined = piece
            if len(joined) >= 300 and joined[-1] in ".!?":
                text = joined
                break
        if not text and len(joined) >= 300:
            text = joined[:1500]
            cut = max(text.rfind(". "), text.rfind("! "), text.rfind("? "))
            if cut >= 300:
                text = text[: cut + 1]
    if len(text) < 300 or text[-1] not in ".!?":
        return ""
    if re.search(r"(?i)password\s*=\s*['\"]|password\s*:\s*['\"]", text):
        return ""

    def scrub_ip(match: re.Match[str]) -> str:
        ip = match.group(0)
        parts = [int(part) for part in ip.split(".")]
        if parts[0] == 127 or ip == "0.0.0.0":
            return ip
        if tuple(parts[:3]) in {(192, 0, 2), (198, 51, 100), (203, 0, 113)}:
            return ip
        return "192.0.2.10"

    text = re.sub(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", scrub_ip, text)
    text = re.sub(r"\b(?:azureuser|ubuntu|root)@", "deploy@", text)
    return f"[{source}]\n{text.strip()}"


def persona_cycle(n: int) -> list[str]:
    bag = []
    for name, weight in PERSONAS:
        bag.extend([name] * weight)
    return [bag[i % len(bag)] for i in range(n)]


def main() -> None:
    grouped: dict[str, list[dict]] = {name: [] for name in TARGETS if name != "k_about"}
    for card in CARDS:
        grouped[bucket_of(card)].append(card)
    for name, cards in grouped.items():
        cards.sort(key=lambda card: card["id"])
        print(name, "cards", len(cards), "target", TARGETS[name])
    slots = []
    number = {name: 1 for name in TARGETS}
    personas = persona_cycle(4600)
    persona_at = 0
    for name, cards in grouped.items():
        counts = spread(len(cards), TARGETS[name])
        if name == "k_cmd" and min(counts) < 8:
            raise SystemExit(f"command spread under 8: {min(counts)}")
        for card, count in zip(cards, counts):
            excerpt = ""
            source = ""
            for item in card.get("sources") or []:
                excerpt = paragraph_excerpt(item)
                if excerpt:
                    source = item
                    break
            for _index in range(count):
                onprem = name in {"k_onprem", "k_scale"}
                provider = "onprem" if onprem else PROVIDERS[len(slots) % len(PROVIDERS)]
                slots.append(
                    {
                        "id": f"{name}_{number[name]:04d}",
                        "category": name,
                        "card_ids": [card["id"]],
                        "card_path": f"ai-agent/training/knowledge/cards/{card['kind']}/{card['id']}.md",
                        "persona": personas[persona_at],
                        "grounding": "closed",
                        "sources": [s for s in (card.get("sources") or [])[:2]],
                        "excerpt": excerpt,
                        "provider": provider,
                        "stage": STAGES[len(slots) % 3],
                        "mode": MODES[len(slots) % 2],
                        "page": PAGES[len(slots) % len(PAGES)],
                        "multi_turn": name == "k_proc",
                    }
                )
                persona_at += 1
                number[name] += 1
    # About Hana. Closed. No card id in the text.
    for index in range(TARGETS["k_about"]):
        slots.append(
            {
                "id": f"k_about_{number['k_about']:04d}",
                "category": "k_about",
                "card_ids": [],
                "card_path": "",
                "persona": personas[persona_at % 4600],
                "grounding": "closed",
                "sources": [],
                "excerpt": "",
                "provider": PROVIDERS[index % len(PROVIDERS)],
                "stage": STAGES[index % 3],
                "mode": MODES[index % 2],
                "page": "none",
                "multi_turn": False,
            }
        )
        number["k_about"] += 1
        persona_at += 1
    # 45% search, only where a real doc paragraph of at least 300 characters exists.
    eligible = [slot for slot in slots if len(slot.get("excerpt") or "") >= 300]
    want = min(2070, len(eligible))
    chosen: set[int] = set()
    cursor = 0.0
    stride = max(1.0, len(eligible) / want) if want else 1.0
    guard = 0
    while len(chosen) < want and guard < len(eligible) * 4:
        chosen.add(int(cursor) % len(eligible))
        cursor += stride
        guard += 1
    if len(chosen) < want:
        for index in range(len(eligible)):
            if len(chosen) >= want:
                break
            chosen.add(index)
    chosen_ids = {id(eligible[index]) for index in chosen}
    for slot in slots:
        if id(slot) in chosen_ids:
            slot["grounding"] = "search"
            header = slot["excerpt"].split("]", 1)[0][1:]
            slot["sources"] = [header]
        else:
            slot["excerpt"] = ""
    search_slots = [slot for slot in slots if slot["grounding"] == "search"]
    print("slots", len(slots), "search", len(search_slots))
    by_cat: dict[str, int] = {}
    for slot in slots:
        by_cat[slot["category"]] = by_cat.get(slot["category"], 0) + 1
    print(by_cat)
    if SLOTS.exists():
        for old in SLOTS.glob("*.json"):
            old.unlink()
    SLOTS.mkdir(parents=True, exist_ok=True)
    width = 40
    for start in range(0, len(slots), width):
        shard = slots[start : start + width]
        path = SLOTS / f"shard_{start // width:03d}.json"
        path.write_text(json.dumps(shard, ensure_ascii=False, indent=1), encoding="utf-8")
    print("shards", (len(slots) + width - 1) // width)


if __name__ == "__main__":
    main()
