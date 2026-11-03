"""``search_docs`` for Hana: BM25 over the knowledge cards she was trained with (``knowledge.jsonl.gz``).

The cards are the pskit docs, CLI commands and studio pages cut into topics. The excerpt format is the one in the
training data: ``[docs/path.md#anchor]`` then the card's title paragraph and the paragraphs that match the query,
at most ~1,100 characters per card, best 2 cards.
"""

from __future__ import annotations

import gzip
import json
import math
import re
import threading
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import docs_index

INDEX = Path(__file__).with_name("knowledge.jsonl.gz")
BUDGET = 1100  # excerpt characters per card, as in training
_WORD = re.compile(r"[a-z0-9_][a-z0-9_.\-]*")


def words(text: str) -> List[str]:
    return _WORD.findall(text.lower())


class Search:
    def __init__(self, cards: List[Dict[str, Any]]) -> None:
        self.cards = cards
        self.docs = [Counter(words(" ".join([c["title"], " ".join(c.get("tags", [])), c["text"]]))) for c in cards]
        self.avg = sum(sum(d.values()) for d in self.docs) / max(len(self.docs), 1)
        df = Counter(w for d in self.docs for w in d)
        n = len(self.docs)
        self.idf = {w: math.log(1 + (n - k + 0.5) / (k + 0.5)) for w, k in df.items()}

    def _score(self, q: List[str], d: Counter) -> float:
        size = sum(d.values())
        return sum(
            self.idf.get(w, 0) * d[w] * 2.2 / (d[w] + 1.2 * (0.25 + 0.75 * size / self.avg)) for w in q if w in d
        )

    def _excerpt(self, card: Dict[str, Any], q: List[str]) -> str:
        paras = [p.strip() for p in re.split(r"\n\s*\n", card["text"]) if p.strip()]
        title, body = paras[0], paras[1:]
        ranked = sorted(range(len(body)), key=lambda i: -len(set(q) & set(words(body[i]))))
        keep, size = set(), len(title)
        for i in ranked:
            if size + len(body[i]) + 2 <= BUDGET:
                keep.add(i)
                size += len(body[i]) + 2
        src = card["sources"][0] if card.get("sources") else card["id"]
        return f"[{src}]\n" + "\n\n".join([title] + [body[i] for i in sorted(keep)])

    def __call__(self, query: str, k: int = 2) -> Tuple[str, List[str]]:
        q = words(query)
        if not q or not self.cards:
            return "No results.", []
        best = sorted(range(len(self.cards)), key=lambda i: -self._score(q, self.docs[i]))[:k]
        return "\n\n".join(self._excerpt(self.cards[i], q) for i in best), [self.cards[i]["id"] for i in best]


_lock = threading.Lock()
_search: Optional[Search] = None


def search() -> Search:
    """The shared index (loaded on first use, about 0.5 s): the trained knowledge cards plus every docs section
    (``docs.jsonl.gz``, see ``docs_index.py``), so new docs are found before the model is retrained."""
    global _search
    with _lock:
        if _search is None:
            cards: List[Dict[str, Any]] = []
            if INDEX.is_file():
                with gzip.open(INDEX, "rt", encoding="utf-8") as handle:
                    cards = [json.loads(line) for line in handle if line.strip()]
            cards.extend(docs_index.load())
            _search = Search(cards)
        return _search
