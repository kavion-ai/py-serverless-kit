"""Build the stage-2 task dataset (12-task-dataset-prompt.md section 7).

Merges data/raw/*.jsonl EXCEPT k_*.jsonl (stage 1), adds the 10 tool definitions as "tools" to every record,
shuffles with a fixed seed, splits 95/5 per category, and writes
    data/final/task_train.jsonl, data/final/task_val.jsonl, data/final/TASK_README.md
It never reads or writes k_*.jsonl or anything in data/final_v2.

    python tools/build_dataset.py [--seed 2200] [--val 0.05]
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from task_common import STAGE2_PROVIDERS, TOOLS  # noqa: E402

TRAIN = Path(__file__).resolve().parents[1]
REPO = TRAIN.parents[1]
RAW = TRAIN / "data" / "raw"
OUT = TRAIN / "data" / "final"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=2200)
    ap.add_argument("--val", type=float, default=0.05)
    a = ap.parse_args()
    files = sorted(p for p in RAW.glob("*.jsonl") if not p.name.startswith("k_"))
    by_cat = {}
    skipped = Counter()
    for f in files:
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rec = json.loads(line)
                if rec["meta"]["provider"] not in STAGE2_PROVIDERS:
                    skipped[rec["meta"]["provider"]] += 1
                    continue
                rec["tools"] = TOOLS
                by_cat.setdefault(rec["meta"]["category"], []).append(rec)
    rng = random.Random(a.seed)
    train, val = [], []
    for cat in sorted(by_cat):
        recs = sorted(by_cat[cat], key=lambda r: r["id"])
        rng.shuffle(recs)
        n_val = max(1, round(len(recs) * a.val)) if len(recs) >= 10 else 0
        val += recs[:n_val]
        train += recs[n_val:]
    rng.shuffle(train)
    rng.shuffle(val)
    OUT.mkdir(parents=True, exist_ok=True)
    for name, recs in (("task_train.jsonl", train), ("task_val.jsonl", val)):
        (OUT / name).write_bytes("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in recs).encode("utf-8"))
    allr = train + val
    version = re.search(r'__version__\s*=\s*"([^"]+)"',
                        (REPO / "src/py_serverless_kit/_version.py").read_text(encoding="utf-8")).group(1)

    def table(title, counter):
        rows = "\n".join(f"| {k} | {v} |" for k, v in sorted(counter.items()))
        return f"## {title}\n\n| {title.split()[-1]} | count |\n|---|---|\n{rows}\n"

    env = Counter()
    for r in allr:
        m = re.search(r"mode=(\S+)", r["messages"][0]["content"])
        env[m.group(1) if m else "?"] += 1
    readme = (
        f"# Hana task dataset (stage 2)\n\npskit version {version}. Built by `tools/build_dataset.py` "
        f"(seed {a.seed}, {int(a.val * 100)}% validation per category) from {', '.join(f.name for f in files)}.\n\n"
        f"Providers: {', '.join(STAGE2_PROVIDERS)} only; left out {sum(skipped.values())} older records "
        f"({', '.join(f'{k} {v}' for k, v in sorted(skipped.items()))}).\n\n"
        f"- train: {len(train)}\n- val: {len(val)}\n\n"
        + table("Per category", Counter(r["meta"]["category"] for r in allr)) + "\n"
        + table("Per provider", Counter(r["meta"]["provider"] for r in allr)) + "\n"
        + table("Per persona", Counter(r["meta"]["persona"] for r in allr)) + "\n"
        + table("Per mode", env) + "\n"
        + table("Per validate result", Counter(r["meta"]["verified"]["validate"] for r in allr)) + "\n"
        + table("Per invoke result", Counter(r["meta"]["verified"]["invoke"] for r in allr))
    )
    (OUT / "TASK_README.md").write_bytes(readme.encode("utf-8"))
    print(f"train {len(train)}, val {len(val)} -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
