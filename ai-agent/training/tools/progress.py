"""Recompute data/progress.json from data/raw/*.jsonl (stage-2 task files only). Safe to run from parallel agents:
it never keeps counts of its own, it only counts what is on disk.

    python tools/progress.py
"""

from __future__ import annotations

import datetime
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from task_common import CATEGORIES, STAGE2_PROVIDERS  # noqa: E402

TRAIN = Path(__file__).resolve().parents[1]
TARGETS = {"a_qa": 900, "b_build": 700, "c_fix": 700, "d_debug": 350, "e_safety": 200, "f_explain": 150, "g_hana": 100}


def main() -> int:
    raw = TRAIN / "data" / "raw"
    prog = {"stage": 2, "updated": datetime.date.today().isoformat(), "scope": list(STAGE2_PROVIDERS),
            "targets_in_scope": TARGETS, "in_scope": {}, "all": {}, "batches": {}}
    for cat in CATEGORIES:
        path = raw / f"{cat}.jsonl"
        recs = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()] if path.exists() else []
        prog["all"][cat] = len(recs)
        prog["in_scope"][cat] = sum(r["meta"]["provider"] in STAGE2_PROVIDERS for r in recs)
        prog["batches"][cat] = sorted(p.name for p in (TRAIN / "data" / "task_src").glob(f"{cat}_*.py"))
    (TRAIN / "data" / "progress.json").write_bytes(json.dumps(prog, indent=2).encode("utf-8"))
    print(" ".join(f"{c}={prog['in_scope'][c]}/{TARGETS[c]}" for c in CATEGORIES),
          f"total={sum(prog['in_scope'].values())}/{sum(TARGETS.values())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
