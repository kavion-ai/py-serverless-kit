"""Step 6: chat with the merged model, with a working search_docs (keyword search over the 426 knowledge cards).

Run in Colab:  MERGED=/content/drive/MyDrive/hana/hana-stage1-merged python ./training/train/step6_chat.py
Env (optional):
  MERGED   folder from step 5 (default <repo>/ai-agent/training/train/work/hana-stage1-merged)
  ENV      the Environment line, default "provider=onprem stage=dev mode=ask page=none"
  Q        ask one question and exit (no typing needed), e.g. Q="how do I add a queue?"
  TEMPERATURE  0 = greedy (default); e.g. 0.3 to sample
  ONE_WAY  1 (default) adds "If the user names one way ..., give only that way." to the rules; 0 = training prompt
In the chat: /reset clears the conversation, /quit exits. Search results are printed as [search] lines.
Needs ai-agent/training/knowledge/index_source.jsonl (the search index) next to this folder.
"""

import json
import math
import os
import re
import sys
from collections import Counter
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

HERE = Path(__file__).resolve().parent
TRAIN = HERE.parent
MERGED = Path(os.environ.get("MERGED", str(HERE / "work" / "hana-stage1-merged")))
ENV = os.environ.get("ENV", "provider=onprem stage=dev mode=ask page=none")
TEMP = float(os.environ.get("TEMPERATURE", "0"))
ONE_WAY = os.environ.get("ONE_WAY", "1") == "1"
ONE_WAY_RULE = "If the user names one way (studio/GUI, terminal/CLI or code), give only that way."
INDEX = TRAIN / "knowledge" / "index_source.jsonl"
BUDGET = 1100  # excerpt characters per card, as in training
WORD = re.compile(r"[a-z0-9_][a-z0-9_.\-]*")
TOOL_CALL = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.S)


def words(text):
    return WORD.findall(text.lower())


class Search:
    """BM25 over cards; returns the best 2 cards, each cut to the paragraphs that match the query."""

    def __init__(self, path):
        self.cards = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        self.docs = [Counter(words(" ".join([c["title"], " ".join(c.get("tags", [])), c["text"]])))
                     for c in self.cards]
        self.avg = sum(sum(d.values()) for d in self.docs) / len(self.docs)
        df = Counter(w for d in self.docs for w in d)
        self.idf = {w: math.log(1 + (len(self.docs) - n + 0.5) / (n + 0.5)) for w, n in df.items()}

    def score(self, q, d):
        size = sum(d.values())
        return sum(self.idf.get(w, 0) * d[w] * 2.2 / (d[w] + 1.2 * (0.25 + 0.75 * size / self.avg)) for w in q if w in d)

    def excerpt(self, card, q):
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

    def __call__(self, query):
        q = words(query)
        best = sorted(range(len(self.cards)), key=lambda i: -self.score(q, self.docs[i]))[:2]
        return "\n\n".join(self.excerpt(self.cards[i], q) for i in best), [self.cards[i]["id"] for i in best]


def system_and_tools():
    for name in ("data/final_v2/knowledge_val.jsonl", "data/final/knowledge_val.jsonl"):
        path = TRAIN / name
        if path.exists():
            row = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
            system = row["messages"][0]["content"].rsplit("\nEnvironment:", 1)[0]
            if ONE_WAY:  # the rule studio's prompt carries from stage 2 on
                system = system.replace("  or current page.\n", "  or current page. " + ONE_WAY_RULE + "\n", 1)
            return f"{system}\nEnvironment: {ENV}", row["tools"]
    raise SystemExit("knowledge_val.jsonl not found under training/data/final_v2 or final")


def generate(model, tok, messages, tools):
    text = tok.apply_chat_template(messages, tools=tools, tokenize=False, add_generation_prompt=True)
    ids = tok(text, return_tensors="pt", add_special_tokens=False).to(model.device)
    extra = {"do_sample": True, "temperature": TEMP, "top_p": 0.9} if TEMP > 0 else {"do_sample": False}
    with torch.no_grad():
        out = model.generate(**ids, max_new_tokens=600, repetition_penalty=1.05, **extra)
    return tok.decode(out[0][ids["input_ids"].shape[1]:], skip_special_tokens=True).strip()


def turn(model, tok, search, messages, tools):
    """One user turn: let Hana search (up to 3 times), then return her answer."""
    for _ in range(3):
        reply = generate(model, tok, messages, tools)
        calls = TOOL_CALL.findall(reply)
        if not calls:
            messages.append({"role": "assistant", "content": reply})
            return reply
        tool_calls, results = [], []
        for n, raw in enumerate(calls):
            try:
                call = json.loads(raw)
                query = call.get("arguments", {}).get("query", "")
            except (json.JSONDecodeError, AttributeError):
                query = ""
            text, ids = search(query) if query else ("error: search_docs needs a query", [])
            print(f"[search] {query!r} -> {', '.join(ids) or 'nothing'}")
            tool_calls.append({"type": "function", "function": {"name": "search_docs", "arguments": {"query": query}}})
            results.append({"role": "tool", "name": "search_docs", "content": text, "tool_call_id": f"call_{n:02d}"})
        messages.append({"role": "assistant", "content": "", "tool_calls": tool_calls})
        messages.extend(results)
    reply = "(Hana kept searching without answering)"
    messages.append({"role": "assistant", "content": reply})
    return reply


def main():
    if not INDEX.exists():
        raise SystemExit(f"search index missing: upload index_source.jsonl to {INDEX}")
    search = Search(INDEX)
    system, tools = system_and_tools()
    tok = AutoTokenizer.from_pretrained(str(MERGED))
    bf16 = torch.cuda.is_available() and torch.cuda.get_device_capability(0)[0] >= 8
    dtype = torch.bfloat16 if bf16 else (torch.float16 if torch.cuda.is_available() else torch.float32)
    model = AutoModelForCausalLM.from_pretrained(str(MERGED), dtype=dtype,
                                                 device_map="cuda" if torch.cuda.is_available() else None).eval()
    print(f"Hana from {MERGED}, {len(search.cards)} cards indexed, Environment: {ENV}")
    messages = [{"role": "system", "content": system}]
    one = os.environ.get("Q")
    if one:
        print(f"\nyou> {one}")
        messages.append({"role": "user", "content": one})
        print(f"hana> {turn(model, tok, search, messages, tools)}")
        return
    print("type a question; /reset clears the chat, /quit exits\n")
    while True:
        try:
            q = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if q in ("/quit", "/exit"):
            break
        if q == "/reset":
            messages = messages[:1]
            print("(chat cleared)")
            continue
        if q:
            messages.append({"role": "user", "content": q})
            print(f"hana> {turn(model, tok, search, messages, tools)}\n")
    sys.exit(0)


if __name__ == "__main__":
    main()
