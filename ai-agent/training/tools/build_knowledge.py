"""Merge raw Hana conversations into train and validation files.

Shuffle seed is 2100. The split is 95 percent train and 5 percent validation,
stratified by category. cards_train.jsonl is one explanation per knowledge card
and is not part of the 4600.
"""

from __future__ import annotations

import json
import random
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "ai-agent" / "training" / "tools"))

from check_knowledge import SYSTEM_BEFORE_ENV  # noqa: E402

TRAIN = ROOT / "ai-agent" / "training"
RAW = TRAIN / "data" / "raw"
FINAL = TRAIN / "data" / "final"
KNOW = TRAIN / "knowledge"
SEED = 2100

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_docs",
            "description": "Search the pskit docs and return verbatim excerpts. Each excerpt starts with [path#anchor].",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "What to look up in the pskit docs."}},
                "required": ["query"],
            },
        },
    }
]

EXPLAIN = [
    "Explain {title}.",
    "Teach me {title}.",
    "Summarize {title}.",
    "What should I know about {title}?",
]


def load_raw() -> list[dict]:
    rows = []
    for path in sorted(RAW.glob("k_*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            row["tools"] = TOOLS
            rows.append(row)
    return rows


def val_counts(by_cat: dict[str, list[dict]], target: int) -> dict[str, int]:
    exact = {cat: len(rows) * 0.05 for cat, rows in by_cat.items()}
    counts = {cat: int(value) for cat, value in exact.items()}
    left = target - sum(counts.values())
    ranked = sorted(exact, key=lambda cat: (exact[cat] - counts[cat], cat), reverse=True)
    for cat in ranked:
        if left <= 0:
            break
        counts[cat] += 1
        left -= 1
    return counts


def write_jsonl(path: Path, rows: list[dict]) -> None:
    payload = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    path.write_bytes(payload.encode("utf-8"))


def card_conversations() -> list[dict]:
    cards = []
    for line in (KNOW / "cards.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            cards.append(json.loads(line))
    rows = []
    for index, card in enumerate(cards):
        provider = ["aws", "azure", "gcp", "onprem"][index % 4]
        stage = ["dev", "staging", "prod"][index % 3]
        system = (
            SYSTEM_BEFORE_ENV
            + f"Environment: provider={provider} stage={stage} mode=ask page=none"
        )
        rows.append(
            {
                "id": "card_" + card["id"],
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": EXPLAIN[index % len(EXPLAIN)].format(title=card["title"])},
                    {"role": "assistant", "content": card["text"]},
                ],
                "meta": {
                    "category": "card",
                    "card_ids": [card["id"]],
                    "grounding": "closed",
                    "persona": "beginner",
                    "sources": card.get("sources") or [],
                },
            }
        )
    return rows


def readme(rows: list[dict], train_n: int, val_n: int, card_n: int) -> str:
    version = (ROOT / "src" / "py_serverless_kit" / "_version.py").read_text(encoding="utf-8")
    ver = "2.10.0"
    for line in version.splitlines():
        if "__version__" in line and '"' in line:
            ver = line.split('"', 2)[1]
            break
    cat = Counter(row["meta"]["category"] for row in rows)
    persona = Counter(row["meta"]["persona"] for row in rows)
    grounding = Counter(row["meta"]["grounding"] for row in rows)
    howto = 0
    for row in rows:
        text = "\n".join(
            message.get("content") or ""
            for message in row["messages"]
            if message.get("role") == "assistant"
        )
        if "In studio" in text or "In the terminal" in text:
            howto += 1
    lines = [
        "# Hana knowledge dataset",
        "",
        f"Package version `{ver}` from `src/py_serverless_kit/_version.py`.",
        "",
        "These files are the stage-1 knowledge set. The conversations teach py-serverless-kit from this repository.",
        "",
        f"Conversations: {len(rows)}.",
        f"Train: {train_n} in `knowledge_train.jsonl` (95%).",
        f"Validation: {val_n} in `knowledge_val.jsonl` (5%), stratified by category.",
        f"Shuffle seed: {SEED}.",
        f"Card explanations: {card_n} in `cards_train.jsonl`. That file is separate from the {len(rows)} conversations.",
        "",
        "## Category",
        "",
    ]
    for name in sorted(cat):
        lines.append(f"- {name}: {cat[name]}")
    lines.extend(["", "## Persona", ""])
    for name in sorted(persona):
        lines.append(f"- {name}: {persona[name]} ({persona[name] / len(rows):.1%})")
    lines.extend(["", "## Grounding", ""])
    for name in sorted(grounding):
        lines.append(f"- {name}: {grounding[name]} ({grounding[name] / len(rows):.1%})")
    lines.extend(
        [
            "",
            "## How-to share",
            "",
            f"{howto}/{len(rows)} = {howto / len(rows):.1%} of conversations have an assistant reply containing \"In studio\" or \"In the terminal\".",
            "",
            "## Files",
            "",
            "- `ai-agent/training/data/raw/k_*.jsonl` is the source split by category.",
            "- `ai-agent/training/data/final/knowledge_train.jsonl` and `knowledge_val.jsonl` add the `search_docs` tool definition.",
            "- `ai-agent/training/knowledge/index_source.jsonl` is a copy of `knowledge/cards.jsonl`.",
            "- `ai-agent/training/knowledge/cards/` holds the same card text as the JSONL.",
            "",
            "Cards for deploy, remove, and server changes come from `--help`, docs, and code.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    rows = load_raw()
    by_cat: dict[str, list[dict]] = {}
    for row in rows:
        by_cat.setdefault(row["meta"]["category"], []).append(row)
    target = round(len(rows) * 0.05)
    counts = val_counts(by_cat, target)
    rng = random.Random(SEED)
    train: list[dict] = []
    val: list[dict] = []
    for cat in sorted(by_cat):
        bucket = list(by_cat[cat])
        rng.shuffle(bucket)
        take = counts[cat]
        val.extend(bucket[:take])
        train.extend(bucket[take:])
    rng.shuffle(train)
    rng.shuffle(val)
    FINAL.mkdir(parents=True, exist_ok=True)
    write_jsonl(FINAL / "knowledge_train.jsonl", train)
    write_jsonl(FINAL / "knowledge_val.jsonl", val)
    cards = card_conversations()
    write_jsonl(FINAL / "cards_train.jsonl", cards)
    source = (KNOW / "cards.jsonl").read_bytes()
    (KNOW / "index_source.jsonl").write_bytes(source)
    text = readme(rows, len(train), len(val), len(cards))
    (FINAL / "KNOWLEDGE_README.md").write_bytes(text.encode("utf-8"))
    print(f"train={len(train)} val={len(val)} cards={len(cards)} val_by={counts}")


if __name__ == "__main__":
    main()
