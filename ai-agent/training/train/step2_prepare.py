"""Step 2: turn the stage-1 data into tokenized train/val sets with loss on assistant tokens only.

Run from the folder that holds ai-agent/:   python ai-agent/training/train/step2_prepare.py
Optional:  MODEL_ID=meta-llama/Llama-3.2-1B-Instruct  MAX_LEN=2048  DATA=final_v2 (folder under data/, default final)
Writes ai-agent/training/train/work/tok_train and tok_val (datasets.save_to_disk). Prints a report to paste back.
If the data folder has identity_train.jsonl, its rows are added to train 3 times (they are few).
"""

import json
import os
import re
from pathlib import Path

from datasets import Dataset
from transformers import AutoTokenizer

MODEL_ID = os.environ.get("MODEL_ID", "Qwen/Qwen2.5-1.5B-Instruct")
MAX_LEN = int(os.environ.get("MAX_LEN", "2048"))
TRAIN = Path(__file__).resolve().parents[1]
FINAL = TRAIN / "data" / os.environ.get("DATA", "final")
WORK = Path(__file__).resolve().parent / "work"

# The one card with a literal example password: never train on it.
PASSWORD = re.compile(r"""(PASSWORD=)(['"])(?!\$)[^'"\n]+\2""")


def load(name):
    path = FINAL / name
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def clean(record, stats):
    """OpenAI-style record -> messages/tools the HF chat template expects."""
    messages = []
    for m in record["messages"]:
        msg = {"role": m["role"], "content": m.get("content") or ""}
        new = PASSWORD.sub(r"\1\2${ORDERS_DB_PASSWORD}\2", msg["content"])
        stats["redacted"] += new != msg["content"]
        msg["content"] = new
        if m.get("tool_calls"):
            calls = []
            for call in m["tool_calls"]:
                fn = call["function"]
                args = fn.get("arguments") or "{}"
                calls.append({"type": "function", "function": {
                    "name": fn["name"], "arguments": json.loads(args) if isinstance(args, str) else args}})
            msg["tool_calls"] = calls
        if m["role"] == "tool":
            msg["name"] = m.get("name", "search_docs")
        messages.append(msg)
    return messages, record.get("tools") or None


def render(tok, messages, tools, gen=False):
    text = tok.apply_chat_template(messages, tools=tools, tokenize=False, add_generation_prompt=gen)
    return tok(text, add_special_tokens=False)["input_ids"]


def encode(tok, messages, tools, stats):
    full = render(tok, messages, tools)
    labels = [-100] * len(full)
    for i, m in enumerate(messages):
        if m["role"] != "assistant":
            continue
        start = len(render(tok, messages[:i], tools, gen=True))
        upto = render(tok, messages[: i + 1], tools)
        if full[: len(upto)] != upto or start > len(upto):
            stats["unstable"] += 1
            return None
        labels[start: len(upto)] = full[start: len(upto)]
    return {"input_ids": full, "labels": labels}


def build(tok, rows, stats):
    out = []
    for r in rows:
        messages, tools = clean(r, stats)
        enc = encode(tok, messages, tools, stats)
        if enc is None:
            continue
        if len(enc["input_ids"]) > MAX_LEN:
            stats["too_long"] += 1
            continue
        stats["lengths"].append(len(enc["input_ids"]))
        stats["trainable"] += sum(1 for x in enc["labels"] if x != -100)
        stats["tokens"] += len(enc["input_ids"])
        out.append(enc)
    return out


def report(name, rows, stats):
    lens = sorted(stats["lengths"])
    p = lambda q: lens[min(len(lens) - 1, int(q * len(lens)))]  # noqa: E731
    print(f"{name}: in={len(rows)} kept={len(lens)} too_long={stats['too_long']} unstable_template={stats['unstable']} "
          f"tokens p50={p(.5)} p95={p(.95)} max={lens[-1]} trainable={stats['trainable'] / stats['tokens']:.1%} "
          f"redacted_passwords={stats['redacted']}")


def main():
    print("model:", MODEL_ID, "max_len:", MAX_LEN, "data:", FINAL)
    tok = AutoTokenizer.from_pretrained(MODEL_ID)
    new = lambda: {"redacted": 0, "unstable": 0, "too_long": 0, "lengths": [], "trainable": 0, "tokens": 0}  # noqa: E731
    train_rows = load("knowledge_train.jsonl") + load("cards_train.jsonl")
    if (FINAL / "identity_train.jsonl").exists():
        train_rows += load("identity_train.jsonl") * 3
    val_rows = load("knowledge_val.jsonl")
    s_train, s_val = new(), new()
    train = build(tok, train_rows, s_train)
    val = build(tok, val_rows, s_val)
    report("train (knowledge + cards)", train_rows, s_train)
    report("val", val_rows, s_val)

    # Show one search conversation: trained text in [[ ]], context left plain.
    sample_row = next(r for r in load("knowledge_val.jsonl") if any(m.get("tool_calls") for m in r["messages"]))
    messages, tools = clean(sample_row, new())
    enc = encode(tok, messages, tools, new())
    pieces, cur, flag = [], [], None
    for tid, lab in zip(enc["input_ids"], enc["labels"]):
        f = lab != -100
        if flag is not None and f != flag:
            pieces.append(("[[" + tok.decode(cur) + "]]") if flag else tok.decode(cur))
            cur = []
        cur.append(tid)
        flag = f
    pieces.append(("[[" + tok.decode(cur) + "]]") if flag else tok.decode(cur))
    text = "".join(pieces)
    print("\n--- sample (tail, trained parts in [[ ]]) ---")
    print(text[-1500:])

    WORK.mkdir(parents=True, exist_ok=True)
    Dataset.from_list(train).save_to_disk(str(WORK / "tok_train"))
    Dataset.from_list(val).save_to_disk(str(WORK / "tok_val"))
    print(f"\nsaved {len(train)} train / {len(val)} val to {WORK}")


if __name__ == "__main__":
    main()
