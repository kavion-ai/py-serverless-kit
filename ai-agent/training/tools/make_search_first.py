"""Make the search decision learnable: every pskit question starts with search_docs.

Stage-1 v1 picked "search" for 45% of conversations at random, so the model could not learn when to search
(eval: 46/99 searched when expected, 29/131 when not). This writes data/final_v2/ where the rule is fixed:

- conversations with a card (grounding "closed") get a search_docs call before their first answer; the tool
  returns the paragraphs of that card that best match the answer the conversation already has. The query is the
  user's question. Answer text is not changed.
- conversations that already search are copied unchanged.
- conversations without a card (k_about: identity, modes, small talk) stay without a search.

Run from ai-agent/training:  python tools/make_search_first.py
"""

import json
import re
from pathlib import Path

TRAIN = Path(__file__).resolve().parents[1]
SRC = TRAIN / "data" / "final"
DST = TRAIN / "data" / "final_v2"
CARDS = {c["id"]: c for c in map(json.loads, (TRAIN / "knowledge" / "index_source.jsonl").read_text(
    encoding="utf-8").splitlines())}
BUDGET = 1100  # excerpt characters per conversation, close to the longest v1 excerpt (1103)
SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z`\"*])")
WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_.\-/]{2,}")


def excerpt(card, answer):
    """The card's paragraphs that share the most words with the answer, in card order, within BUDGET."""
    paras = [p.strip() for p in re.split(r"\n\s*\n", card["text"]) if p.strip()]
    title, body = paras[0], []  # body: (paragraph number, text)
    for n, p in enumerate(paras[1:]):  # long prose is split into sentences so one paragraph can't fill the budget
        pieces = [p] if len(p) <= 500 or p.startswith(("```", "|", "-")) else SENTENCE.split(p)
        body += [(n, s) for s in pieces if len(s) <= BUDGET - len(title)]
    want = {w.lower() for w in WORD.findall(answer)}
    ranked = sorted(range(len(body)), key=lambda i: -len(want & {w.lower() for w in WORD.findall(body[i][1])}))
    keep, size = set(), len(title)
    for i in ranked:
        if size + len(body[i][1]) + 2 <= BUDGET:
            keep.add(i)
            size += len(body[i][1]) + 2
    paras_out, last = [title], None
    for i in sorted(keep):  # sentences of the same paragraph stay on one line
        n, text = body[i]
        if n == last:
            paras_out[-1] += " " + text
        else:
            paras_out.append(text)
        last = n
    src = card["sources"][0] if card.get("sources") else card["id"]
    return f"[{src}]\n" + "\n\n".join(paras_out)


def search_first(r):
    if r["meta"]["grounding"] != "closed" or not r["meta"]["card_ids"]:
        return r, False
    msgs = r["messages"]
    u = next(i for i, m in enumerate(msgs) if m["role"] == "user")
    a = next(i for i in range(u + 1, len(msgs)) if msgs[i]["role"] == "assistant")
    question = " ".join(msgs[u]["content"].split())[:160]
    text = "\n\n".join(excerpt(CARDS[c], msgs[a]["content"]) for c in r["meta"]["card_ids"] if c in CARDS)
    if not text:
        return r, False
    call = {"role": "assistant", "content": "", "tool_calls": [{"id": "call_01", "type": "function", "function": {
        "name": "search_docs", "arguments": json.dumps({"query": question}, ensure_ascii=False)}}]}
    tool = {"role": "tool", "tool_call_id": "call_01", "name": "search_docs", "content": text}
    out = dict(r, messages=msgs[:a] + [call, tool] + msgs[a:], meta=dict(r["meta"], grounding="search_added"))
    return out, True


def main():
    DST.mkdir(parents=True, exist_ok=True)
    for name in ("knowledge_train.jsonl", "knowledge_val.jsonl", "cards_train.jsonl"):
        rows = [json.loads(line) for line in (SRC / name).read_text(encoding="utf-8").splitlines() if line.strip()]
        added = 0
        if name.startswith("knowledge"):
            converted = [search_first(r) for r in rows]
            rows, added = [r for r, _ in converted], sum(flag for _, flag in converted)
        (DST / name).write_bytes("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows).encode("utf-8"))
        print(f"{name}: {len(rows)} rows, search added to {added}")


if __name__ == "__main__":
    main()
