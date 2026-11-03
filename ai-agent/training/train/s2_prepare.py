"""Stage 2, step A: tokenize the task data plus a replay of stage-1 knowledge, loss on assistant tokens only.

Run in Colab:  BASE=/content/drive/MyDrive/hana/hana-stage1-merged python ./training/train/s2_prepare.py
Env (optional):
  BASE      stage-1 merged model (checkpoint K); its tokenizer is used. Default: Qwen/Qwen2.5-1.5B-Instruct
  MAX_LEN   default 4096 (task conversations carry 10 tool schemas, so they are longer than stage 1)
  REPLAY    knowledge rows added, as a share of the task rows, default 0.25
  KDATA     stage-1 data folder under data/, default final_v2
Reads data/final/task_train.jsonl + task_val.jsonl (stage 2) and data/<KDATA>/knowledge_train.jsonl,
identity_train.jsonl, knowledge_val.jsonl (stage 1). Writes train/work/s2_train, s2_val_task, s2_val_knowledge.
"""

import json
import os
import random
import sys
from pathlib import Path

from datasets import Dataset
from transformers import AutoTokenizer

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from step2_prepare import clean, encode  # noqa: E402

BASE = os.environ.get("BASE", "Qwen/Qwen2.5-1.5B-Instruct")
MAX_LEN = int(os.environ.get("MAX_LEN", "4096"))
REPLAY = float(os.environ.get("REPLAY", "0.25"))
DATA = HERE.parent / "data"
TASK = DATA / "final"
KNOW = DATA / os.environ.get("KDATA", "final_v2")
WORK = HERE / "work"
SEED = 2200


def load(path):
    if not path.exists():
        raise SystemExit(f"missing {path}: is it in the zip?")
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def build(tok, rows):
    stats = {"redacted": 0, "unstable": 0, "too_long": 0}
    out, lens, trainable, tokens = [], [], 0, 0
    for r in rows:
        messages, tools = clean(r, stats)
        enc = encode(tok, messages, tools, stats)
        if enc is None:
            continue
        if len(enc["input_ids"]) > MAX_LEN:
            stats["too_long"] += 1
            continue
        out.append(enc)
        lens.append(len(enc["input_ids"]))
        trainable += sum(1 for x in enc["labels"] if x != -100)
        tokens += len(enc["input_ids"])
    return out, stats, sorted(lens), trainable / max(tokens, 1)


def report(name, rows, built):
    out, stats, lens, share = built
    p = lambda q: lens[min(len(lens) - 1, int(q * len(lens)))]  # noqa: E731
    print(f"{name}: in={len(rows)} kept={len(out)} too_long={stats['too_long']} unstable={stats['unstable']} "
          f"tokens p50={p(.5)} p95={p(.95)} max={lens[-1]} trainable={share:.1%}")


def main():
    rng = random.Random(SEED)
    print("tokenizer:", BASE, "max_len:", MAX_LEN, "replay:", REPLAY)
    tok = AutoTokenizer.from_pretrained(BASE)
    task_train = load(TASK / "task_train.jsonl")
    task_val = load(TASK / "task_val.jsonl")
    know = load(KNOW / "knowledge_train.jsonl")
    ident = load(KNOW / "identity_train.jsonl") if (KNOW / "identity_train.jsonl").exists() else []
    replay = rng.sample(know, min(len(know), int(len(task_train) * REPLAY))) + ident
    know_val = load(KNOW / "knowledge_val.jsonl")
    know_val = rng.sample(know_val, min(100, len(know_val)))

    train_rows = task_train + replay
    rng.shuffle(train_rows)
    built = {name: build(tok, rows) for name, rows in
             (("train", train_rows), ("val_task", task_val), ("val_knowledge", know_val))}
    report(f"train (task {len(task_train)} + replay {len(replay)})", train_rows, built["train"])
    report("val task", task_val, built["val_task"])
    report("val knowledge (forgetting check)", know_val, built["val_knowledge"])

    WORK.mkdir(parents=True, exist_ok=True)
    for name, (out, *_rest) in built.items():
        Dataset.from_list(out).save_to_disk(str(WORK / f"s2_{name}"))
    print(f"\nsaved to {WORK}: s2_train, s2_val_task, s2_val_knowledge")


if __name__ == "__main__":
    main()
